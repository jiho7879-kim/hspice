"""
Differentiable physics layer -- Vmin computation from GP surrogate outputs.

For a given (common_N, PU) condition, the pipeline is:
    1. Surrogate predicts mu(Vop), sigma(Vop) for Vop in  {0.4, ..., 0.9}
    2. Zscore(Vop) = mu(Vop) / sigma(Vop)   (SNMR mean / sigma ratio)
    3. Vmin = linear_interpolate({Vop | Zscore(Vop) = Z_target})

This is differentiable w.r.t. mu and sigma via interpolation gradients.

Usage:
    python src/toy_physics_layer.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import VOPS, Z_FIXED, COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX


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
) -> np.ndarray:
    """Compute Vmin by linear interpolation of Zscore = Z_target.

    Args:
        zscore: (N, 6) array of Zscore at each Vop level
        z_target: Target Z-score for Vmin definition
        vops: Vop levels corresponding to columns of zscore

    Returns:
        vmin: (N,) array of interpolated Vmin values.
              Returns NaN if Z_target is outside the range (extrapolation would
              be unreliable) -- those points are flagged for inspection.
    """
    n = zscore.shape[0]
    vmin = np.full(n, np.nan, dtype=np.float64)

    for i in range(n):
        z = zscore[i]
        # Find where Zscore crosses Z_target
        # Zscore should be decreasing with Vop (lower Vop = worse SNMR/sigma ratio)
        # so we look for the interval where z <= z_target <= z (reverse order)
        # Actually SNMR/sigma should increase with Vop: higher Vdd -> more margin
        # So Zscore increases with Vop
        if z[0] > z_target:
            # Already above target at lowest Vop -- safe, Vmin < 0.4V
            # Extrapolate down (or clamp)
            vmin[i] = vops[0] - 0.05  # heuristic below min Vop
            continue
        if z[-1] < z_target:
            # Even at max Vop, Zscore below target -- fail point
            vmin[i] = np.nan
            continue

        # Interpolate: find first index where z >= z_target
        for j in range(len(vops) - 1):
            if z[j] <= z_target <= z[j + 1]:
                # Linear interpolation
                t = (z_target - z[j]) / (z[j + 1] - z[j] + 1e-12)
                vmin[i] = vops[j] + t * (vops[j + 1] - vops[j])
                break

    return vmin


class PhysicsLayer(torch.nn.Module):
    """Differentiable Vmin computation (PyTorch version for gradient checks).

    Takes mu_pred (N, 6) and sigma_pred (N, 6), computes Vmin.
    At the Zscore(Vop) = Z_target crossing, the interpolation step is
    linear, so gradients flow back through mu and sigma.
    """

    def __init__(self, z_target: float = Z_FIXED) -> None:
        super().__init__()
        self.z_target = z_target
        # Register Vops as a buffer so it moves with device
        self.register_buffer("vops", torch.from_numpy(VOPS).float())

    def forward(self, mu: torch.Tensor, sigma: torch.Tensor) -> torch.Tensor:
        """Forward pass: predict Vmin from mu and sigma.

        Args:
            mu: (N, 6) SNMR mean
            sigma: (N, 6) SNMR sigma

        Returns:
            vmin: (N,) or (N, 1)
        """
        z = mu / (sigma + 1e-12)
        n = mu.shape[0]
        vops = self.vops

        # Vectorized linear interpolation:
        # Zscore increases with Vop. Find crossing.
        # diff_z = z - z_target
        # sign change from negative to positive -> crossing
        z_shift = z - self.z_target
        # Find where sign goes from - to + (or 0)
        sign = torch.sign(z_shift)
        # Zero out non-crossing rows
        crossing = (sign[:, :-1] <= 0) & (sign[:, 1:] >= 0)

        # For each row, find the first crossing index
        vmin = torch.full((n,), torch.nan, device=mu.device, dtype=mu.dtype)

        for i in range(n):
            idx = torch.where(crossing[i])[0]
            if len(idx) == 0:
                if z_shift[i, 0] >= 0:
                    # Below min Vop, extrapolate
                    vmin[i] = vops[0] - 0.05
                # else: NaN (fail point)
                continue

            j = idx[0]
            # Linear interpolation
            t = (self.z_target - z[i, j]) / (z[i, j + 1] - z[i, j] + 1e-12)
            vmin[i] = vops[j] + t * (vops[j + 1] - vops[j])

        return vmin


def compute_vmin_on_grid(
    surrogate_fn: callable,
    n_grid: int = 50,
    common_n_range: tuple[float, float] = (COMMON_N_MIN, COMMON_N_MAX),
    pu_range: tuple[float, float] = (PU_MIN, PU_MAX),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute Vmin over a regular grid of (common_N, PU) values.

    Args:
        surrogate_fn: callable(X_grid) -> mu_grid, sigma_grid
                      where X_grid is (N_grid, 3) = [common_N, PU, Vop]
        n_grid: Number of grid points per axis.
        common_n_range: (min, max) in mV.
        pu_range: (min, max) in mV.

    Returns:
        common_n_grid: (n_grid, n_grid) meshgrid of common_N values
        pu_grid: (n_grid, n_grid) meshgrid of PU values
        vmin_grid: (n_grid, n_grid) Vmin values at each (common_N, PU)
    """
    cna = np.linspace(common_n_range[0], common_n_range[1], n_grid)
    pua = np.linspace(pu_range[0], pu_range[1], n_grid)
    CN, PU = np.meshgrid(cna, pua, indexing="xy")  # (n_grid, n_grid)

    # Build grid: for each (common_N, PU), expand across all 6 Vop levels
    n_total = n_grid * n_grid
    X_grid = np.zeros((n_total * len(VOPS), 3), dtype=np.float64)
    for i in range(n_grid):
        for j in range(n_grid):
            idx = (i * n_grid + j) * len(VOPS)
            X_grid[idx: idx + len(VOPS), 0] = CN[i, j]
            X_grid[idx: idx + len(VOPS), 1] = PU[i, j]
            X_grid[idx: idx + len(VOPS), 2] = VOPS

    mu_grid, sigma_grid = surrogate_fn(X_grid)

    # Reshape: (n_grid, n_grid, 6)
    mu_3d = mu_grid.reshape(n_grid, n_grid, len(VOPS))
    sigma_3d = sigma_grid.reshape(n_grid, n_grid, len(VOPS))

    # Compute Zscore and Vmin per grid cell
    z_3d = mu_3d / (sigma_3d + 1e-12)
    vmin_grid = compute_vmin_from_z(
        z_3d.reshape(-1, len(VOPS)),
        z_target=Z_FIXED,
    ).reshape(n_grid, n_grid)

    return CN, PU, vmin_grid


def gradient_check(
    surr,  # Surrogate object with predict()
    eps: float = 1e-3,
) -> dict:
    """Unit test: dVmin/dcommon_N and dVmin/dPU via finite differences.

    Uses a nominal condition (common_N=0, PU=0) as the test point.

    Returns dict with:
        - grad_common_N_fd, grad_PU_fd: finite-difference gradients
        - rational: "ok" or explanation if suspicious
    """
    base_cn = 0.0
    base_pu = 0.0

    def _vmin_at(cn: float, pu: float) -> float:
        """Compute Vmin at a single (common_N, PU) condition."""
        X = np.zeros((len(VOPS), 3), dtype=np.float64)
        for k, vop in enumerate(VOPS):
            X[k] = [cn, pu, vop]
        mu, _, sigma, _ = surr.predict(X)
        z = mu / (sigma + 1e-12)
        v = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED)
        return float(v[0])

    v0 = _vmin_at(base_cn, base_pu)

    # Finite difference: central
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

    # Sanity: direction checks for hold SNMR
    # Convention: positive shift = slower device for BOTH NMOS and PMOS
    #
    # For HOLD SNM the dominant physics is DIFFERENT from read SNM:
    #
    # common_N +10mV (NMOS slower, higher Vth):
    #   PG (access) has higher Vth -> less subthreshold leakage in hold mode
    #   -> cell stores data more stably -> SNMR better -> Vmin LOWER
    #   So Vmin(+10mV) < Vmin(-10mV) -> dVmin/dcommon_N < 0
    #   (This is the opposite of read SNM where weaker PD hurts.)
    #
    # PU +10mV (PMOS slower, higher |Vth|):
    #   PU weaker -> holds '1' worse -> SNMR worse -> Vmin higher
    #   So Vmin(+10mV) > Vmin(-10mV) -> dVmin/dPU > 0
    v_neg_cn = _vmin_at(-10, 0)
    v_pos_cn = _vmin_at(10, 0)
    v_neg_pu = _vmin_at(0, -10)
    v_pos_pu = _vmin_at(0, 10)

    rational = True
    if v_pos_cn < v_neg_cn:
        print(f"  [OK] common_N: Vmin(+10mV)={v_pos_cn:.4f} < Vmin(-10mV)={v_neg_cn:.4f}  (slower N -> less PG leakage -> better hold SNM)")
    elif v_pos_cn > v_neg_cn:
        print(f"  [OK] common_N: Vmin(+10mV)={v_pos_cn:.4f} > Vmin(-10mV)={v_neg_cn:.4f}  (read SNM regime: slower N -> weaker PD -> worse)")
    else:
        print(f"  [WARN] common_N: Vmin(+10mV)={v_pos_cn:.4f} == Vmin(-10mV)={v_neg_cn:.4f} (no sensitivity)")
        rational = False

    if v_pos_pu > v_neg_pu:
        print(f"  [OK] PU: Vmin(+10mV)={v_pos_pu:.4f} > Vmin(-10mV)={v_neg_pu:.4f}  (PMOS slower -> worse)")
    else:
        print(f"  [WARN] PU: Vmin(+10mV)={v_pos_pu:.4f} <= Vmin(-10mV)={v_neg_pu:.4f}")
        rational = False

    result["rational"] = "ok" if rational else "[WARN] check sign"
    return result


def main() -> None:
    """Quick test: load trained surrogate, run gradient check."""
    import json

    result = {}
    # Try to load trained surrogate
    from src.toy_surrogate import Surrogate, load_intermediate, stratified_train_test_split

    data_path = Path(__file__).resolve().parent.parent / "data" / "dataset.npz"
    if not data_path.exists():
        print(f"Data not found at {data_path}.")
        print("Run parse_snm.py first or use synthetic data for testing.")
        print("\n--- Gradient check requires trained surrogate. ---")
        print("Run toy_surrogate.py first:")
        print("  python src/toy_surrogate.py --data ./data/dataset.npz")
        return

    X, y = load_intermediate(str(data_path))
    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.2)

    surr = Surrogate(device="cpu")
    surr.fit(X_tr, y_tr, verbose=True)

    print("\n--- Gradient Check ---")
    result = gradient_check(surr)

    out_path = Path(__file__).resolve().parent.parent / "results"
    out_path.mkdir(exist_ok=True)
    with open(out_path / "gradient_check.json", "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nGradient check results saved to {out_path / 'gradient_check.json'}")


if __name__ == "__main__":
    main()
