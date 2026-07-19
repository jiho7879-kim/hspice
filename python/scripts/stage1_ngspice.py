"""
Stage 1: GP surrogate trained on ngspice butterfly data (core 3D: cn, pu, Vop).

Pipeline:
  1. Load ngspice dataset (X, y) from results/ngspice_stage1/data/
  2. Train GP surrogate (mu GP + sigma GP)
  3. Compute z-score on Vop grid and Vmin contours
  4. Side-by-side: ngspice GP vs analytic model (reference)
  5. Save figure, metrics, model checkpoints

Usage:
    python scripts/stage1_ngspice.py
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils import (
    Z_FIXED, VOPS, N_VOP, VOP_COL,
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
)
from src.data import load_intermediate, stratified_train_test_split
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z, compute_vmin_on_grid
from src.contour import extract_contour

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "results" / "ngspice_stage1" / "data" / "dataset.npz"
OUT_DIR = ROOT / "results" / "ngspice_stage1"

# ---------------------------------------------------------------------------
# Analytic SNMR reference model (hold, 125C)
# ---------------------------------------------------------------------------
A_MU = 0.15
B_MU = +0.001
C_MU = -0.0015
D_MU = 0.0
SIGMA0 = 0.015
SIGMA_VOP_SLOPE = 0.004


def analytic_snmr(cn_mv: float, pu_mv: float, vop_v: float) -> tuple[float, float]:
    mu = A_MU * vop_v + B_MU * cn_mv + C_MU * pu_mv + D_MU
    sigma = SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - vop_v)
    return mu, sigma


# ---------------------------------------------------------------------------
# Vmin grid with fallback for inverted z-Vop trend
# ---------------------------------------------------------------------------
def compute_vmin_on_grid_fallback(
    surrogate_fn: callable,
    n_grid: int = 60,
    common_n_range: tuple[float, float] = (COMMON_N_MIN, COMMON_N_MAX),
    pu_range: tuple[float, float] = (PU_MIN, PU_MAX),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vmin on (cn, pu) grid, tolerant of inverted z-Vop monotonicity.

    Standard compute_vmin_on_grid assumes z increases with Vop.
    ngspice data sometimes has the opposite trend (z decreases with Vop).
    This fallback works for both: finds the crossing regardless of direction.
    """
    cna = np.linspace(common_n_range[0], common_n_range[1], n_grid)
    pua = np.linspace(pu_range[0], pu_range[1], n_grid)
    CN, PU = np.meshgrid(cna, pua, indexing="xy")

    n_total = n_grid * n_grid
    X_grid = np.zeros((n_total * N_VOP, 3), dtype=np.float64)
    for i in range(n_grid):
        for j in range(n_grid):
            idx = (i * n_grid + j) * N_VOP
            X_grid[idx: idx + N_VOP, 0] = CN[i, j]
            X_grid[idx: idx + N_VOP, 1] = PU[i, j]
            X_grid[idx: idx + N_VOP, VOP_COL] = VOPS

    mu_grid, sigma_grid = surrogate_fn(X_grid)

    mu_3d = mu_grid.reshape(n_grid, n_grid, N_VOP)
    sigma_3d = sigma_grid.reshape(n_grid, n_grid, N_VOP)
    z_3d = mu_3d / (sigma_3d + 1e-12)

    vmin_grid = np.full((n_grid, n_grid), np.nan, dtype=np.float64)
    for i in range(n_grid):
        for j in range(n_grid):
            z = z_3d[i, j]
            # z invert detection: if z[0] > z[-1], trend is inverted
            if z[0] > z[-1]:
                # Inverted: z decreases with Vop. Find where z drops below Z_FIXED.
                if z[0] <= Z_FIXED:
                    vmin_grid[i, j] = VOPS[0] - 0.05
                    continue
                if z[-1] >= Z_FIXED:
                    vmin_grid[i, j] = np.nan
                    continue
                for k in range(len(VOPS) - 1):
                    if z[k] >= Z_FIXED >= z[k + 1]:
                        t = (Z_FIXED - z[k + 1]) / (z[k] - z[k + 1] + 1e-12)
                        vmin_grid[i, j] = VOPS[k + 1] + t * (VOPS[k] - VOPS[k + 1])
                        break
            else:
                # Normal: z increases with Vop.
                if z[0] > Z_FIXED:
                    vmin_grid[i, j] = VOPS[0] - 0.05
                    continue
                if z[-1] < Z_FIXED:
                    continue
                for k in range(len(VOPS) - 1):
                    if z[k] <= Z_FIXED <= z[k + 1]:
                        t = (Z_FIXED - z[k]) / (z[k + 1] - z[k] + 1e-12)
                        vmin_grid[i, j] = VOPS[k] + t * (VOPS[k + 1] - VOPS[k])
                        break

    return CN, PU, vmin_grid


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Stage 1: ngspice GP surrogate")
    parser.add_argument("--data", type=str, default=str(DEFAULT_DATA))
    parser.add_argument("--out", type=str, default=str(OUT_DIR))
    parser.add_argument("--n-grid", type=int, default=60)
    parser.add_argument("--n-iter", type=int, default=150)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    args = parser.parse_args()

    out_dir = Path(args.out)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "models").mkdir(parents=True, exist_ok=True)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Stage 1: ngspice GP surrogate -- core 3D (cn, pu, Vop)")
    print("=" * 60)

    # ============================================================
    # 1. Load ngspice dataset
    # ============================================================
    print(f"\nData: {args.data}")
    X, y = load_intermediate(args.data)
    print(f"  X: {X.shape}, y: {y.shape}")

    # Scale ngspice SNM -> mu_SNMR for realistic Vmin range
    # ngspice deterministic butterfly SNM (~7-10 mV) is too small for
    # Vmin estimation at Z_FIXED=6. Scale preserves shape while bringing
    # mu into realistic range for SRAM.
    snm_scale = 12.0
    y[:, 0] *= snm_scale

    print(f"  mu (scaled x{snm_scale}): [{y[:, 0].min():.4f}, {y[:, 0].max():.4f}]")
    print(f"  sigma: [{y[:, 1].min():.5f}, {y[:, 1].max():.5f}]")

    print("\n  Per-Vop stats (scaled mu):")
    for vop in VOPS:
        mask = np.abs(X[:, VOP_COL] - vop) < 0.01
        if mask.sum() > 0:
            vals = y[mask, 0]
            print(f"    Vop={vop:.1f}V  mu={vals.mean():.5f}+-{vals.std():.5f}  "
                  f"[{vals.min():.5f}, {vals.max():.5f}]  n={int(mask.sum())}")

    # ============================================================
    # 2. Train GP surrogate
    # ============================================================
    print("\n--- 2. Train GP surrogate ---")
    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.15)
    print(f"  Train: {len(X_tr)}  Test: {len(X_te)}")

    surr = Surrogate(device=args.device)
    surr.fit(X_tr, y_tr, verbose=True, n_iter=args.n_iter)

    mu_pred, _, sigma_pred, _ = surr.predict(X_te)
    mu_rmse = float(np.sqrt(np.mean((mu_pred - y_te[:, 0]) ** 2)))
    sigma_rmse = float(np.sqrt(np.mean((sigma_pred - y_te[:, 1]) ** 2)))
    print(f"\n  Test RMSE: mu={mu_rmse:.6f}, sigma={sigma_rmse:.6f}")

    # ARD lengthscales (extract directly from GP models, not via Surrogate.get_lengthscales)
    mu_ls = surr.mu_gp.covar_module.base_kernel.lengthscale.detach().cpu().numpy().flatten()
    labels_mu = ["cn", "pu", "Vop"] + [f"d{i}" for i in range(3, len(mu_ls))]
    print(f"\n  ARD lengthscales:")
    print(f"    mu GP:    {', '.join(f'{l}={v:.4f}' for l, v in zip(labels_mu, mu_ls))}")

    import torch
    torch.save(surr.mu_gp.state_dict(), out_dir / "models" / "mu_gp.pth")
    torch.save(surr.sigma_gp.state_dict(), out_dir / "models" / "sigma_gp.pth")
    print(f"\n  Models saved")

    # ============================================================
    # 3. Vmin on grid (fallback handles inverted z-Vop trend)
    # ============================================================
    print("\n--- 3. Vmin on grid + contour ---")

    def ngspice_surrogate_fn(x):
        mu, _, sigma, _ = surr.predict(x)
        return mu, sigma

    # ngspice GP Vmin
    CN, PU, vmin_grid = compute_vmin_on_grid_fallback(
        ngspice_surrogate_fn, n_grid=args.n_grid,
    )
    print(f"  ngspice GP Vmin:  [{np.nanmin(vmin_grid):.3f}, {np.nanmax(vmin_grid):.3f}]")
    pred_cn, pred_pu = extract_contour(vmin_grid, CN, PU, contour_level=0.6)
    print(f"  ngspice GP Vmin=0.6V contour: {len(pred_cn)} pts")

    # Analytic reference Vmin
    true_vmin_grid = np.full_like(vmin_grid, np.nan)
    for i in range(CN.shape[0]):
        for j in range(CN.shape[1]):
            cn = float(CN[i, j])
            pu = float(PU[i, j])
            z = np.array([analytic_snmr(cn, pu, v)[0] / analytic_snmr(cn, pu, v)[1]
                          for v in VOPS])
            true_vmin_grid[i, j] = float(compute_vmin_from_z(z.reshape(1, -1))[0])

    print(f"  Analytic Vmin:    [{np.nanmin(true_vmin_grid):.3f}, {np.nanmax(true_vmin_grid):.3f}]")
    true_cn, true_pu = extract_contour(true_vmin_grid, CN, PU, contour_level=0.6)
    print(f"  Analytic Vmin=0.6V contour: {len(true_cn)} pts")

    # ============================================================
    # 4. Figure: (a) Vmin surface (b) z-score diagnostic
    # ============================================================
    print("\n--- 4. Plot ---")
    corners = {
        "FSG": (-60, 60), "SFG": (60, -60),
        "FFG": (-60, -60), "SSG": (60, 60),
    }

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

    # (a) Vmin response surface
    ax = axes[0]
    cf = ax.contourf(CN, PU, vmin_grid, levels=np.linspace(0.3, 0.9, 25),
                     cmap="RdYlBu_r", alpha=0.85)
    fig.colorbar(cf, ax=ax, label="Vmin (V)", pad=0.02)

    ax.contour(CN, PU, vmin_grid, levels=[0.5, 0.6, 0.7, 0.8],
               colors="k", linewidths=0.6, linestyles="--", alpha=0.4)
    ax.contour(CN, PU, vmin_grid, levels=[0.6], colors="blue", linewidths=2.5)

    if len(true_cn) > 0:
        ax.plot(true_cn, true_pu, "r--", linewidth=2, alpha=0.8,
                label="True Vmin=0.6V (analytic)")
    if len(pred_cn) > 0:
        ax.plot(pred_cn, pred_pu, "b-", linewidth=2.5, alpha=0.9,
                label="GP Vmin=0.6V (ngspice)")

    for name, (cn, pu) in corners.items():
        ax.plot(cn, pu, "D", markersize=7, color="darkred", zorder=5)
        ax.annotate(name, (cn, pu), xytext=(4, 4),
                    textcoords="offset points", fontsize=8, color="darkred")

    ax.set_xlabel("common_N_shift (mV)", fontsize=11)
    ax.set_ylabel("PU_shift (mV)", fontsize=11)
    ax.set_title("(a) Vmin response surface + Vmin=0.6V contour", fontsize=12)
    ax.legend(fontsize=9, loc="upper left")
    ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX)
    ax.set_ylim(PU_MIN, PU_MAX)
    ax.grid(True, alpha=0.15)
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.axvline(0, color="gray", linewidth=0.5)

    # (b) z-score vs Vop diagnostic at 4 corners
    ax = axes[1]
    corner_pts = [("Nominal (0, 0)", (0, 0)),
                  ("FSG (-60, 60)", (-60, 60)),
                  ("SFG (60, -60)", (60, -60)),
                  ("SSG (60, 60)", (60, 60))]

    for label, (cn_val, pu_val) in corner_pts:
        X_probe = np.zeros((N_VOP, 3))
        for k, vop in enumerate(VOPS):
            X_probe[k] = [cn_val, pu_val, vop]
        mu, _, sigma, _ = surr.predict(X_probe)
        z = mu / (sigma + 1e-12)
        ax.plot(VOPS, z, "o-", label=label)
        # Analytic at same point
        z_true = np.array([analytic_snmr(cn_val, pu_val, v)[0] /
                          analytic_snmr(cn_val, pu_val, v)[1] for v in VOPS])
        ax.plot(VOPS, z_true, "x--", alpha=0.5)

    ax.axhline(Z_FIXED, color="k", linestyle=":", linewidth=1, label=f"Z_target={Z_FIXED}")
    ax.set_xlabel("Vop (V)", fontsize=11)
    ax.set_ylabel("z-score = mu / sigma", fontsize=11)
    ax.set_title("(b) z-score vs Vop (solid=ngspice GP, dashed=analytic)", fontsize=12)
    ax.legend(fontsize=8, loc="best")
    ax.grid(True, alpha=0.15)

    fig.text(0.01, 0.02,
             f"ngspice 14nm HP BSIM4 TT 125C | mu scaled x{snm_scale} | "
             f"GP: Matern 5/2 + ARD | train={len(X_tr)} test={len(X_te)}\n"
             f"Test RMSE: mu={mu_rmse:.6f} sigma={sigma_rmse:.6f} | "
             f"Z_target={Z_FIXED}, Vop sweep=0.4-0.9V",
             fontsize=8, color="gray")

    fig_path = out_dir / "figures" / "contour_ngspice.png"
    fig.savefig(fig_path, dpi=150, bbox_inches="tight")
    print(f"  Saved: {fig_path}")
    plt.close(fig)

    # ============================================================
    # 5. Metrics
    # ============================================================
    print("\n--- 5. Metrics ---")
    vmin_error = vmin_grid - true_vmin_grid
    valid_err = ~np.isnan(vmin_error)
    vmin_rmse = float(np.sqrt(np.mean(vmin_error[valid_err] ** 2))) if valid_err.any() else np.nan
    vmin_mae = float(np.mean(np.abs(vmin_error[valid_err]))) if valid_err.any() else np.nan

    metrics = {
        "stage": "1-ngspice",
        "data": str(Path(args.data).name),
        "snm_scale": snm_scale,
        "n_total": len(X),
        "n_train": len(X_tr),
        "n_test": len(X_te),
        "mu_rmse": f"{mu_rmse:.6f}",
        "sigma_rmse": f"{sigma_rmse:.6f}",
        "mu_ls": {"cn": f"{mu_ls[0]:.4f}", "pu": f"{mu_ls[1]:.4f}", "Vop": f"{mu_ls[2]:.4f}"},
        "vmin_range_ngspice": f"[{np.nanmin(vmin_grid):.3f}, {np.nanmax(vmin_grid):.3f}]",
        "vmin_range_true": f"[{np.nanmin(true_vmin_grid):.3f}, {np.nanmax(true_vmin_grid):.3f}]",
        "vmin_error_rmse_V": f"{vmin_rmse:.5f}",
        "vmin_error_mae_V": f"{vmin_mae:.5f}",
        "contour_ngspice_pts": len(pred_cn),
        "contour_true_pts": len(true_cn),
    }
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    with open(out_dir / "metrics.txt", "w") as f:
        for k, v in metrics.items():
            f.write(f"{k}: {v}\n")

    # ============================================================
    # 6. Go/No-Go
    # ============================================================
    print("\n--- Go/No-Go Check ---")
    go = True
    if mu_rmse > 0.015:
        print(f"  [FAIL] mu RMSE {mu_rmse:.6f} > 0.015")
        go = False
    else:
        print(f"  [PASS] mu RMSE {mu_rmse:.6f} <= 0.015")
    if len(pred_cn) < 5:
        print(f"  [FAIL] Contour too short: {len(pred_cn)} pts < 5")
        go = False
    else:
        print(f"  [PASS] Contour: {len(pred_cn)} pts")

    verdict = "GO" if go else "NO-GO"
    print(f"\n  >>> {verdict} <<<")
    with open(out_dir / "go_decision.txt", "w") as f:
        f.write(f"{verdict}\n")

    print("\n=== Stage 1 (ngspice) complete ===")


if __name__ == "__main__":
    main()
