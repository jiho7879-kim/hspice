"""
Demo: analytic SNMR model -> GP surrogate -> PVTA contour plot.

Runs the full pipeline with a known analytic model so you can visually
verify that the contour extraction works before touching HSPICE data.

Usage:
    python scripts/demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils import (
    Z_FIXED, VOPS, COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
)
from src.data import build_dataset, save_intermediate, stratified_train_test_split
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z, compute_vmin_on_grid
from src.contour import extract_contour

# ============================================================
# Analytic SNMR model (hold, 125C)
# ============================================================
A_MU = 0.15
B_MU = +0.001
C_MU = -0.0015
D_MU = 0.0
SIGMA0 = 0.015
SIGMA_VOP_SLOPE = 0.004

MU_NOISE_STD = 0.002
SIGMA_NOISE_STD = 0.0005


def analytic_snmr(cn_mv, pu_mv, vop_v):
    mu = A_MU * vop_v + B_MU * cn_mv + C_MU * pu_mv + D_MU
    sigma = SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - vop_v)
    return mu, sigma


# ============================================================
# 1. Generate synthetic training data
# ============================================================
print("=== 1. Generate synthetic data from analytic model ===")
rng = np.random.default_rng(42)
N_COND = 400
X = build_dataset(N_COND)

y = np.zeros((len(X), 2))
for i in range(len(X)):
    cn, pu, vop = X[i]
    mu, sigma = analytic_snmr(cn, pu, vop)
    y[i] = [mu + rng.normal(0, MU_NOISE_STD),
            sigma + rng.normal(0, SIGMA_NOISE_STD)]

data_path = Path(__file__).resolve().parent.parent / "data" / "demo_analytic.npz"
save_intermediate(data_path, X, y)
print(f"  Generated {len(X)} samples ({N_COND} conditions x 6 Vop)")
print(f"  mu range:    [{y[:,0].min():.4f}, {y[:,0].max():.4f}]")
print(f"  sigma range: [{y[:,1].min():.5f}, {y[:,1].max():.5f}]")

# ============================================================
# 2. Train GP surrogate
# ============================================================
print("\n=== 2. Train GP surrogate ===")
X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.15)
surr = Surrogate(device="cpu")
surr.fit(X_tr, y_tr, verbose=True, n_iter=150)

mu_pred, _, sigma_pred, _ = surr.predict(X_te)
mu_rmse = np.sqrt(np.mean((mu_pred - y_te[:, 0]) ** 2))
sigma_rmse = np.sqrt(np.mean((sigma_pred - y_te[:, 1]) ** 2))
print(f"\n  Test RMSE: mu={mu_rmse:.5f}, sigma={sigma_rmse:.5f}")

# ============================================================
# 3. Vmin on grid -> contour
# ============================================================
print("\n=== 3. PVTA contour inference ===")


def surrogate_fn(x):
    mu, _, sigma, _ = surr.predict(x)
    return mu, sigma


CN, PU, vmin_grid = compute_vmin_on_grid(
    surrogate_fn, n_grid=60,
    common_n_range=(COMMON_N_MIN, COMMON_N_MAX),
    pu_range=(PU_MIN, PU_MAX),
)

# True contour from analytic model
true_vmin_grid = np.full_like(vmin_grid, np.nan)
for i in range(CN.shape[0]):
    for j in range(CN.shape[1]):
        cn = float(CN[i, j])
        pu = float(PU[i, j])
        z = np.array([analytic_snmr(cn, pu, v)[0] / analytic_snmr(cn, pu, v)[1]
                      for v in VOPS])
        true_vmin_grid[i, j] = float(compute_vmin_from_z(z.reshape(1, -1))[0])

print(f"  True Vmin range:  [{np.nanmin(true_vmin_grid):.3f}, {np.nanmax(true_vmin_grid):.3f}]")
print(f"  Pred Vmin range:  [{np.nanmin(vmin_grid):.3f}, {np.nanmax(vmin_grid):.3f}]")

pred_cn, pred_pu = extract_contour(vmin_grid, CN, PU, contour_level=0.6)
true_cn, true_pu = extract_contour(true_vmin_grid, CN, PU, contour_level=0.6)
print(f"  True contour  at Vmin=0.6V: {len(true_cn)} pts")
print(f"  Pred contour at Vmin=0.6V:  {len(pred_cn)} pts")

# ============================================================
# 4. Plot
# ============================================================
print("\n=== 4. Plot ===")

corners = {
    "FSG": (-60, 60), "SFG": (60, -60),
    "FFG": (-60, -60), "SSG": (60, 60),
}

fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

# (a) Vmin response surface
ax = axes[0]
cf = ax.contourf(CN, PU, vmin_grid, levels=np.linspace(0.3, 0.9, 25),
                 cmap="RdYlBu_r", alpha=0.85)
cbar = fig.colorbar(cf, ax=ax, label="Vmin (V)", pad=0.02)

ax.contour(CN, PU, vmin_grid, levels=[0.5, 0.6, 0.7, 0.8],
           colors="k", linewidths=0.6, linestyles="--", alpha=0.4)
ax.contour(CN, PU, vmin_grid, levels=[0.6], colors="blue", linewidths=2.5)

if len(true_cn) > 0:
    ax.plot(true_cn, true_pu, "r--", linewidth=2, alpha=0.8,
            label="True Vmin=0.6V")

for name, (cn, pu) in corners.items():
    ax.plot(cn, pu, "D", markersize=7, color="darkred", zorder=5)
    ax.annotate(name, (cn, pu), xytext=(4, 4),
                textcoords="offset points", fontsize=8, color="darkred")

if len(pred_cn) > 0:
    ax.plot(pred_cn, pred_pu, "b-", linewidth=2.5, alpha=0.9,
            label="GP Vmin=0.6V")

ax.set_xlabel("common_N_shift (mV)  [positive = slower NMOS]", fontsize=11)
ax.set_ylabel("PU_shift (mV)  [positive = slower PMOS]", fontsize=11)
ax.set_title("(a) Vmin response surface + Vmin=0.6V contour", fontsize=12)
ax.legend(fontsize=9, loc="upper left")
ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX)
ax.set_ylim(PU_MIN, PU_MAX)
ax.grid(True, alpha=0.15)
ax.axhline(0, color="gray", linewidth=0.5)
ax.axvline(0, color="gray", linewidth=0.5)

# (b) Error map
ax = axes[1]
vmin_error = vmin_grid - true_vmin_grid
valid = ~np.isnan(vmin_error)
vmin_error[~valid] = 0.0

vmax = max(abs(vmin_error[valid].min()), abs(vmin_error[valid].max()))
cf2 = ax.contourf(CN, PU, vmin_error, levels=np.linspace(-vmax, vmax, 21),
                  cmap="bwr", alpha=0.85)
cbar2 = fig.colorbar(cf2, ax=ax, label="Vmin error (V)", pad=0.02)

if len(true_cn) > 0:
    ax.plot(true_cn, true_pu, "k--", linewidth=1.5, alpha=0.6,
            label="True Vmin=0.6V")
if len(pred_cn) > 0:
    ax.plot(pred_cn, pred_pu, "g-", linewidth=1.5, alpha=0.8,
            label="GP Vmin=0.6V")

ax.set_xlabel("common_N_shift (mV)", fontsize=11)
ax.set_ylabel("PU_shift (mV)", fontsize=11)
ax.set_title(f"(b) GP error: Vmin_pred - Vmin_true  |v|max={vmax:.3f}V", fontsize=12)
ax.legend(fontsize=9, loc="upper left")
ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX)
ax.set_ylim(PU_MIN, PU_MAX)
ax.grid(True, alpha=0.15)
ax.axhline(0, color="gray", linewidth=0.5)
ax.axvline(0, color="gray", linewidth=0.5)

fig.text(0.01, 0.02,
    f"Analytic: mu={A_MU}*Vop + ({B_MU})*cn + ({C_MU})*pu + {D_MU}, "
    f"sigma={SIGMA0}+{SIGMA_VOP_SLOPE}*(0.9-Vop)\n"
    f"GP: Matern 5/2 + ARD, train={len(X_tr)}, test={len(X_te)}\n"
    f"Test RMSE: mu={mu_rmse:.5f}, sigma={sigma_rmse:.5f}  |  "
    f"Z_target={Z_FIXED}, Vop sweep=0.4-0.9V step 0.1V",
    fontsize=8, color="gray")

out_path = Path(__file__).resolve().parent.parent / "results" / "stage1_3d" / "contour.png"
out_path.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"\n  Figure saved: {out_path}")
plt.close(fig)

# ============================================================
# 5. Metrics + Go/No-Go
# ============================================================
stage1_dir = Path(__file__).resolve().parent.parent / "results" / "stage1_3d"
stage1_dir.mkdir(parents=True, exist_ok=True)

vmin_error_flat = vmin_grid - true_vmin_grid
valid_err = ~np.isnan(vmin_error_flat)
vmin_rmse = float(np.sqrt(np.mean(vmin_error_flat[valid_err] ** 2))) if valid_err.any() else np.nan
vmin_mae = float(np.mean(np.abs(vmin_error_flat[valid_err]))) if valid_err.any() else np.nan

metrics = {
    "stage": 1,
    "n_cond": N_COND,
    "mu_rmse": f"{mu_rmse:.5f}",
    "sigma_rmse": f"{sigma_rmse:.5f}",
    "true_vmin_range": f"[{np.nanmin(true_vmin_grid):.3f}, {np.nanmax(true_vmin_grid):.3f}]",
    "pred_vmin_range": f"[{np.nanmin(vmin_grid):.3f}, {np.nanmax(vmin_grid):.3f}]",
    "vmin_error_rmse_V": f"{vmin_rmse:.5f}",
    "vmin_error_mae_V": f"{vmin_mae:.5f}",
    "contour_true_pts": len(true_cn),
    "contour_pred_pts": len(pred_cn),
}
print("\n--- Metrics ---")
for k, v in metrics.items():
    print(f"  {k}: {v}")

with open(stage1_dir / "metrics.txt", "w") as f:
    for k, v in metrics.items():
        f.write(f"{k}: {v}\n")

print("\n--- Go/No-Go Check ---")
go = True
if mu_rmse > 0.015:
    print(f"  [FAIL] mu RMSE {mu_rmse:.5f} > 0.015")
    go = False
else:
    print(f"  [PASS] mu RMSE {mu_rmse:.5f} <= 0.015")
if abs(len(pred_cn) - len(true_cn)) > max(5, 0.1 * len(true_cn)) if len(true_cn) > 0 else len(pred_cn) > 5:
    print(f"  [FAIL] Contour pts mismatch: pred={len(pred_cn)} true={len(true_cn)}")
    go = False
else:
    print(f"  [PASS] Contour pts match: pred={len(pred_cn)} true={len(true_cn)}")

print(f"\n  >>> {'GO' if go else 'NO-GO'} <<<")
with open(stage1_dir / "go_decision.txt", "w") as f:
    f.write("GO\n" if go else "NO-GO\n")

print("\n=== Stage 1 complete ===")
