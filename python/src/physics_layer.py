"""
Differentiable physics layer — Vmin computation from GP surrogate outputs.

For a given (common_N, PU) condition, the pipeline is:
    1. Surrogate predicts mu(Vop), sigma(Vop) for Vop in {0.4, ..., 0.9}
    2. Zscore(Vop) = mu(Vop) / sigma(Vop)   (SNMR mean / sigma ratio)
    3. Vmin = linear_interpolate({Vop | Zscore(Vop) = Z_target})

With Vwl assist (4D+):
    4. estimate_required_assist(surrogate, target_vmin) → required Vwl map
       Finds Vwl ∈ [Vwl_min, Vop] such that Vmin(Vwl) = target_vmin
       via binary search for each (cn, pu) point (Vwl↓→Vmin↓ monotonic).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from src.utils import (
    VOPS, N_VOP, VOP_COL,
    WLUD_COL, WLUD_FACTORS, N_WLUD,
    Z_FIXED,
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
)


def compute_zscore(mu: np.ndarray | torch.Tensor,
                   sigma: np.ndarray | torch.Tensor) -> np.ndarray | torch.Tensor:
    """Compute Zscore = mu / sigma.

    Args:
        mu: (..., 6) SNMR mean at each Vop
        sigma: (..., 6) SNMR sigma at each Vop

    Returns:
        zscore: (..., 6)
    """
    return mu / (sigma + 1e-12)


def compute_vmin_from_z(
    zscore: np.ndarray,
    z_target: float = Z_FIXED,
    vops: np.ndarray = VOPS,
    return_censored: bool = False,
) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """Compute Vmin by linear interpolation of Zscore = Z_target.

    Args:
        zscore: (N, 6) array of Zscore at each Vop level
        z_target: Target Z-score for Vmin definition
        vops: Vop levels corresponding to columns of zscore
        return_censored: If True, also return a boolean mask marking rows
            whose true Vmin lies BELOW the lowest sampled Vop (left-censored).
            For those rows the returned value is the heuristic floor
            ``vops[0] - 0.05`` — a placeholder, not a measurement.  Continuous
            error metrics (RMSE etc.) must exclude censored rows; treating the
            floor as a real Vmin was the source of the inflated Stage 3
            "Vmin RMSE 0.16-0.26 V" artifact (2026-07-02).

    Returns:
        vmin: (N,) interpolated Vmin values (NaN when z never reaches
              z_target = fail point even at max Vop).
        censored: (N,) bool, only when return_censored=True.
    """
    n = zscore.shape[0]
    vmin = np.full(n, np.nan, dtype=np.float64)
    censored = np.zeros(n, dtype=bool)

    for i in range(n):
        z = zscore[i]
        if z[0] > z_target:
            vmin[i] = vops[0] - 0.05  # heuristic below min Vop
            censored[i] = True
            continue
        if z[-1] < z_target:
            vmin[i] = np.nan  # fail point
            continue

        for j in range(len(vops) - 1):
            if z[j] <= z_target <= z[j + 1]:
                t = (z_target - z[j]) / (z[j + 1] - z[j] + 1e-12)
                vmin[i] = vops[j] + t * (vops[j + 1] - vops[j])
                break

    if return_censored:
        return vmin, censored
    return vmin


class PhysicsLayer(torch.nn.Module):
    """Differentiable Vmin computation (PyTorch version for gradient checks).

    Takes mu_pred (N, 6) and sigma_pred (N, 6), computes Vmin.
    """

    def __init__(self, z_target: float = Z_FIXED) -> None:
        super().__init__()
        self.z_target = z_target
        self.register_buffer("vops", torch.from_numpy(VOPS).float())

    def forward(self, mu: torch.Tensor, sigma: torch.Tensor) -> torch.Tensor:
        """Forward pass: predict Vmin from mu and sigma.

        Args:
            mu: (N, 6) SNMR mean
            sigma: (N, 6) SNMR sigma

        Returns:
            vmin: (N,)
        """
        z = mu / (sigma + 1e-12)
        n = mu.shape[0]
        vops = self.vops

        z_shift = z - self.z_target
        sign = torch.sign(z_shift)
        crossing = (sign[:, :-1] <= 0) & (sign[:, 1:] >= 0)

        vmin = torch.full((n,), torch.nan, device=mu.device, dtype=mu.dtype)

        for i in range(n):
            idx = torch.where(crossing[i])[0]
            if len(idx) == 0:
                if z_shift[i, 0] >= 0:
                    vmin[i] = vops[0] - 0.05
                continue

            j = idx[0]
            t = (self.z_target - z[i, j]) / (z[i, j + 1] - z[i, j] + 1e-12)
            vmin[i] = vops[j] + t * (vops[j + 1] - vops[j])

        return vmin


def compute_vmin_on_grid(
    surrogate_fn: callable,
    n_grid: int = 50,
    common_n_range: tuple[float, float] = (COMMON_N_MIN, COMMON_N_MAX),
    pu_range: tuple[float, float] = (PU_MIN, PU_MAX),
    wlud_fixed: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute Vmin over a regular grid of (common_N, PU) values.

    3D mode (wlud_fixed=None): core cn, pu, Vop — original behaviour.
    4D mode (wlud_fixed=float): cn, pu, Vop + WLUD ratio (Vwl/Vop) held constant.

    Args:
        surrogate_fn: callable(X_grid) -> mu_grid, sigma_grid
                      X_grid shape: (n_total * N_VOP, d) where d=3 or d=4.
        n_grid: Number of grid points per axis.
        common_n_range: (min, max) in mV.
        pu_range: (min, max) in mV.
        wlud_fixed: If given, WLUD column is populated with this ratio (Vwl/Vop).

    Returns:
        common_n_grid: (n_grid, n_grid) meshgrid
        pu_grid: (n_grid, n_grid) meshgrid
        vmin_grid: (n_grid, n_grid) Vmin values
    """
    cna = np.linspace(common_n_range[0], common_n_range[1], n_grid)
    pua = np.linspace(pu_range[0], pu_range[1], n_grid)
    CN, PU = np.meshgrid(cna, pua, indexing="xy")

    n_dims = 4 if wlud_fixed is not None else 3
    n_total = n_grid * n_grid
    X_grid = np.zeros((n_total * N_VOP, n_dims), dtype=np.float64)
    for i in range(n_grid):
        for j in range(n_grid):
            idx = (i * n_grid + j) * N_VOP
            X_grid[idx: idx + N_VOP, 0] = CN[i, j]
            X_grid[idx: idx + N_VOP, 1] = PU[i, j]
            X_grid[idx: idx + N_VOP, VOP_COL] = VOPS
            if wlud_fixed is not None:
                X_grid[idx: idx + N_VOP, WLUD_COL] = wlud_fixed

    mu_grid, sigma_grid = surrogate_fn(X_grid)

    mu_3d = mu_grid.reshape(n_grid, n_grid, N_VOP)
    sigma_3d = sigma_grid.reshape(n_grid, n_grid, N_VOP)

    z_3d = mu_3d / (sigma_3d + 1e-12)
    vmin_grid = compute_vmin_from_z(
        z_3d.reshape(-1, N_VOP),
        z_target=Z_FIXED,
    ).reshape(n_grid, n_grid)

    return CN, PU, vmin_grid


def compute_vmin_vs_vwl(
    surrogate_fn: callable,
    n_grid: int = 50,
    vop_fixed: float = 0.7,
    common_n_range: tuple[float, float] = (COMMON_N_MIN, COMMON_N_MAX),
    pu_range: tuple[float, float] = (PU_MIN, PU_MAX),
    wlud_levels: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Compute Vmin as a function of WLUD ratio over a (cn, pu) grid.

    For each (cn, pu, WLUD) the surrogate predicts mu/sigma across all Vop
    levels (with Vwl = WLUD * Vop implicit in the GP input), then Vmin is
    interpolated from Zscore = Z_FIXED.

    Returns:
        CN: (n_grid, n_grid) meshgrid
        PU: (n_grid, n_grid) meshgrid
        WLUD: (n_vwl,) WLUD ratio levels evaluated
        vmin_3d: (n_grid, n_grid, n_vwl) Vmin at each WLUD level
    """
    if wlud_levels is None:
        wlud_levels = WLUD_FACTORS
    n_vwl = len(wlud_levels)

    cna = np.linspace(common_n_range[0], common_n_range[1], n_grid)
    pua = np.linspace(pu_range[0], pu_range[1], n_grid)
    CN, PU = np.meshgrid(cna, pua, indexing="xy")

    n_total = n_grid * n_grid
    full_X = np.zeros((n_total * N_VOP * n_vwl, 4), dtype=np.float64)
    for i in range(n_grid):
        for j in range(n_grid):
            for k, wlud in enumerate(wlud_levels):
                base = ((i * n_grid + j) * n_vwl + k) * N_VOP
                full_X[base: base + N_VOP, 0] = CN[i, j]
                full_X[base: base + N_VOP, 1] = PU[i, j]
                full_X[base: base + N_VOP, VOP_COL] = VOPS
                full_X[base: base + N_VOP, WLUD_COL] = wlud

    mu_pred, sigma_pred = surrogate_fn(full_X)
    z = mu_pred / (sigma_pred + 1e-12)
    vmin_all = compute_vmin_from_z(z.reshape(-1, N_VOP), z_target=Z_FIXED)
    vmin_3d = vmin_all.reshape(n_grid, n_grid, n_vwl)

    return CN, PU, wlud_levels, vmin_3d


def estimate_required_assist(
    surrogate_fn: callable,
    target_vmin: float,
    vop_fixed: float = 0.7,
    n_grid: int = 50,
    common_n_range: tuple[float, float] = (COMMON_N_MIN, COMMON_N_MAX),
    pu_range: tuple[float, float] = (PU_MIN, PU_MAX),
    wlud_lo: float = 0.50,
    n_wlud_eval: int = 15,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Estimate required WLUD ratio to achieve target_Vmin at fixed Vop.

    For each (cn, pu) on a grid: binary search over WLUD ∈ [wlud_lo, 1.0]
    to find WLUD s.t. Vmin = target_vmin.  WLUD↓ → Vmin↓ is monotonic
    (lower WLUD = stronger assist = lower Vmin).

    Returns:
        CN: (n_grid, n_grid) meshgrid
        PU: (n_grid, n_grid) meshgrid
        wlud_required: (n_grid, n_grid) required WLUD ratio (NaN = infeasible/already met)
        vmin_achieved: (n_grid, n_grid) Vmin at the found WLUD
    """
    # Evaluate on discrete WLUD grid first
    wlud_levels = np.linspace(wlud_lo, 1.0, n_wlud_eval, dtype=np.float64)
    CN, PU, WLUD, vmin_vs_wlud = compute_vmin_vs_vwl(
        surrogate_fn, n_grid=n_grid, vop_fixed=vop_fixed,
        common_n_range=common_n_range, pu_range=pu_range,
        wlud_levels=wlud_levels,
    )

    wlud_required = np.full(CN.shape, np.nan, dtype=np.float64)
    vmin_achieved = np.full(CN.shape, np.nan, dtype=np.float64)

    for i in range(n_grid):
        for j in range(n_grid):
            vmin_curve = vmin_vs_wlud[i, j, :]  # (n_wlud_eval,)

            # If Vmin at max WLUD (WLUD=1.0, no assist) already ≤ target → no assist needed
            if np.isnan(vmin_curve[-1]):
                continue
            if vmin_curve[-1] <= target_vmin:
                wlud_required[i, j] = 1.0  # no assist
                vmin_achieved[i, j] = vmin_curve[-1]
                continue

            # If Vmin at min WLUD (strongest assist) still > target → infeasible
            if np.isnan(vmin_curve[0]):
                continue
            if vmin_curve[0] > target_vmin:
                continue

            # Binary search for WLUD
            lo, hi = 0, n_wlud_eval - 1
            for _ in range(20):  # bisection with WLUD resolution
                mid = (lo + hi) // 2
                if vmin_curve[mid] < target_vmin:
                    lo = mid
                else:
                    hi = mid
                if hi - lo <= 1:
                    break

            # Linear interpolate between WLUD[lo] and WLUD[hi]
            v_lo = vmin_curve[lo]
            v_hi = vmin_curve[hi]
            if np.isnan(v_lo) or np.isnan(v_hi) or abs(v_hi - v_lo) < 1e-12:
                continue
            t = (target_vmin - v_lo) / (v_hi - v_lo)
            t = np.clip(t, 0.0, 1.0)
            wlud_required[i, j] = wlud_levels[lo] + t * (wlud_levels[hi] - wlud_levels[lo])
            vmin_achieved[i, j] = vmin_curve[lo] + t * (vmin_curve[hi] - vmin_curve[lo])

    return CN, PU, wlud_required, vmin_achieved


def gradient_check(
    surr,  # Surrogate object with predict()
    eps: float = 1e-3,
) -> dict:
    """Check dVmin/dcommon_N and dVmin/dPU via finite differences.

    Args:
        surr: Surrogate object with predict() method.
        eps: Step size for finite difference.

    Returns:
        dict with gradient values and sanity check.
    """
    base_cn = 0.0
    base_pu = 0.0

    def _vmin_at(cn: float, pu: float) -> float:
        X = np.zeros((len(VOPS), 3), dtype=np.float64)
        for k, vop in enumerate(VOPS):
            X[k] = [cn, pu, vop]
        mu, _, sigma, _ = surr.predict(X)
        z = mu / (sigma + 1e-12)
        v = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED)
        return float(v[0])

    v0 = _vmin_at(base_cn, base_pu)

    v_cn_plus = _vmin_at(base_cn + eps, base_pu)
    v_cn_minus = _vmin_at(base_cn - eps, base_pu)
    grad_cn = (v_cn_plus - v_cn_minus) / (2 * eps)

    v_pu_plus = _vmin_at(base_cn, base_pu + eps)
    v_pu_minus = _vmin_at(base_cn, base_pu - eps)
    grad_pu = (v_pu_plus - v_pu_minus) / (2 * eps)

    result = {
        "Vmin at (0,0)": f"{v0:.5f}",
        "dVmin/dcommon_N": f"{grad_cn:.5f}",
        "dVmin/dPU": f"{grad_pu:.5f}",
    }
    print(f"Vmin at (common_N=0, PU=0) = {v0:.5f} V")
    print(f"dVmin/dcommon_N ~ {grad_cn:.5f}  ({v_cn_plus:.5f} @ +1mV, {v_cn_minus:.5f} @ -1mV)")
    print(f"dVmin/dPU      ~ {grad_pu:.5f}  ({v_pu_plus:.5f} @ +1mV, {v_pu_minus:.5f} @ -1mV)")

    # Sanity: direction checks for HOLD SNMR
    v_neg_cn = _vmin_at(-10, 0)
    v_pos_cn = _vmin_at(10, 0)
    v_neg_pu = _vmin_at(0, -10)
    v_pos_pu = _vmin_at(0, 10)

    rational = True
    if v_pos_cn < v_neg_cn:
        print(f"  [OK] common_N: Vmin(+10mV)={v_pos_cn:.4f} < Vmin(-10mV)={v_neg_cn:.4f}")
    elif v_pos_cn > v_neg_cn:
        print(f"  [OK] common_N: Vmin(+10mV)={v_pos_cn:.4f} > Vmin(-10mV)={v_neg_cn:.4f}")
    else:
        print(f"  [WARN] common_N: no sensitivity")
        rational = False

    if v_pos_pu > v_neg_pu:
        print(f"  [OK] PU: Vmin(+10mV)={v_pos_pu:.4f} > Vmin(-10mV)={v_neg_pu:.4f}")
    else:
        print(f"  [WARN] PU: check sign")
        rational = False

    result["rational"] = "ok" if rational else "[WARN] check sign"
    return result
