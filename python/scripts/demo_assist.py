"""
Demo Stage 3: Inverse assist estimation validation on analytic 4D model.

Validates estimate_required_assist():
  1. For each (cn, pu) point on a grid, find WLUD s.t. Vmin = target_vmin
  2. Verify against ground truth analytic model
  3. Plot assist map + accuracy

The 4th GP dimension stores WLUD ratio (Vwl/Vop), not absolute Vwl.
When evaluating analytic model, compute Vwl = WLUD * Vop.

Usage:
    python scripts/demo_assist.py
"""

import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils import (
    Z_FIXED, VOPS, VOP_COL, WLUD_COL,
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
    WLUD_FACTORS, N_WLUD,
)
from src.data import build_dataset, stratified_train_test_split
from src.surrogate import Surrogate
from src.physics import analytic_snmr
from src.physics_layer import (
    compute_vmin_from_z, compute_vmin_on_grid,
    compute_vmin_vs_vwl, estimate_required_assist,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "toy" / "stage3_inverse_assist"
OUT_DIR.mkdir(parents=True, exist_ok=True)

N_COND = 50
TARGET_VMIN = 0.55
VOP_FIXED = 0.7
MU_NOISE_STD = 0.002
SIGMA_NOISE_STD = 0.0005

print("=" * 60)
print("Stage 3: Inverse Assist Estimation Validation")
print("=" * 60)

# ============================================================
# 1. Train 4D surrogate (same as Stage 2)
# ============================================================
print("\n=== 1. Train 4D surrogate ===")
rng = np.random.default_rng(42)
X_cnpu = build_dataset(N_COND)
n_base = len(X_cnpu)

X_4d = np.zeros((n_base * N_WLUD, 4), dtype=np.float64)
y_4d = np.zeros((n_base * N_WLUD, 2), dtype=np.float64)
for i in range(N_WLUD):
    wlud = WLUD_FACTORS[i]
    start = i * n_base
    end = (i + 1) * n_base
    X_4d[start:end, :3] = X_cnpu
    X_4d[start:end, WLUD_COL] = wlud  # WLUD ratio, not absolute Vwl
    for j in range(n_base):
        cn, pu, vop = X_cnpu[j]
        vwl = vop * wlud  # Vwl = WLUD * Vop per point
        mu, sigma = analytic_snmr(cn, pu, vop, vwl_v=vwl)
        y_4d[start + j] = [mu + rng.normal(0, MU_NOISE_STD),
                           sigma + rng.normal(0, SIGMA_NOISE_STD)]

X_tr, X_te, y_tr, y_te = stratified_train_test_split(X_4d, y_4d, test_frac=0.15)
surr = Surrogate(device="cpu")
surr.fit(X_tr, y_tr, verbose=True, n_iter=100)
surr.save(OUT_DIR / "checkpoint.pth")

mu_pred, _, sigma_pred, _ = surr.predict(X_te)
mu_rmse = float(np.sqrt(np.mean((mu_pred - y_te[:, 0]) ** 2)))
sigma_rmse = float(np.sqrt(np.mean((sigma_pred - y_te[:, 1]) ** 2)))
print(f"\n  Test RMSE: mu={mu_rmse:.5f}, sigma={sigma_rmse:.5f}")

def surrogate_fn(x):
    mu, _, sigma, _ = surr.predict(x)
    return mu, sigma

# ============================================================
# 2. Ground truth Vmin_vs_WLUD for validation grid
# ============================================================
print("\n=== 2. Compute ground truth ===")
n_grid = 30
# WLUD ratio sweep from 0.50 (strongest) to 1.0 (none)
wlud_levels_dense = np.linspace(0.50, 1.0, 20, dtype=np.float64)

cna = np.linspace(COMMON_N_MIN, COMMON_N_MAX, n_grid)
pua = np.linspace(PU_MIN, PU_MAX, n_grid)
CN, PU = np.meshgrid(cna, pua, indexing="xy")

# True Vmin at each (cn, pu, WLUD): Vwl = WLUD * Vop per Vop level
true_vmin_3d = np.full((n_grid, n_grid, len(wlud_levels_dense)), np.nan)
for i in range(n_grid):
    for j in range(n_grid):
        cn = float(CN[i, j])
        pu = float(PU[i, j])
        for k, wlud in enumerate(wlud_levels_dense):
            z_vals = np.array([
                analytic_snmr(cn, pu, v, vwl_v=v * wlud)[0] /
                analytic_snmr(cn, pu, v, vwl_v=v * wlud)[1]
                for v in VOPS
            ])
            v = float(compute_vmin_from_z(z_vals.reshape(1, -1))[0])
            true_vmin_3d[i, j, k] = v
print(f"  True Vmin grid: {true_vmin_3d.shape}")

# ============================================================
# 3. Run estimate_required_assist (GP-based)
# ============================================================
print("\n=== 3. Estimate required assist (GP) ===")
CN_est, PU_est, wlud_required, vmin_achieved = estimate_required_assist(
    surrogate_fn, target_vmin=TARGET_VMIN, vop_fixed=VOP_FIXED,
    n_grid=n_grid, wlud_lo=0.90, n_wlud_eval=20,
)
assert CN_est.shape == (n_grid, n_grid)

# ============================================================
# 4. Validation: compare against ground truth
# ============================================================
print("\n=== 4. Validation ===")

# For each feasible point, compute what WLUD the ground truth would require
true_wlud_required = np.full((n_grid, n_grid), np.nan, dtype=np.float64)
true_vmin_at_found = np.full((n_grid, n_grid), np.nan, dtype=np.float64)

for i in range(n_grid):
    for j in range(n_grid):
        cn = float(CN[i, j])
        pu = float(PU[i, j])
        vmin_curve = true_vmin_3d[i, j, :]  # at each WLUD level

        if np.isnan(vmin_curve).all():
            continue

        # Vmin at max WLUD (= 1.0, no assist)
        vmin_no_assist = vmin_curve[-1]
        if np.isnan(vmin_no_assist):
            continue
        if vmin_no_assist <= TARGET_VMIN:
            true_wlud_required[i, j] = 1.0  # no assist needed
            true_vmin_at_found[i, j] = vmin_no_assist
            continue

        # Vmin at min WLUD (strongest assist)
        vmin_max_assist = vmin_curve[0]
        if np.isnan(vmin_max_assist) or vmin_max_assist > TARGET_VMIN:
            continue  # infeasible

        # Binary search on true model
        lo, hi = 0, len(wlud_levels_dense) - 1
        for _ in range(30):
            mid = (lo + hi) // 2
            if vmin_curve[mid] < TARGET_VMIN:
                lo = mid
            else:
                hi = mid
            if hi - lo <= 1:
                break

        v_lo, v_hi = vmin_curve[lo], vmin_curve[hi]
        if np.isnan(v_lo) or np.isnan(v_hi) or abs(v_hi - v_lo) < 1e-12:
            continue
        t = np.clip((TARGET_VMIN - v_lo) / (v_hi - v_lo), 0.0, 1.0)
        true_wlud_required[i, j] = wlud_levels_dense[lo] + t * (wlud_levels_dense[hi] - wlud_levels_dense[lo])
        true_vmin_at_found[i, j] = vmin_curve[lo] + t * (vmin_curve[hi] - vmin_curve[lo])

# Compare GP estimate vs true
feasible_mask = ~np.isnan(wlud_required) & ~np.isnan(true_wlud_required)
n_feasible = int(feasible_mask.sum())
n_total = n_grid * n_grid

wlud_error = wlud_required[feasible_mask] - true_wlud_required[feasible_mask]
wlud_rmse = float(np.sqrt(np.mean(wlud_error ** 2))) if len(wlud_error) > 0 else np.nan
wlud_mae = float(np.mean(np.abs(wlud_error))) if len(wlud_error) > 0 else np.nan

# Vmin achieved at GP-predicted WLUD — linear interpolation
vmin_achieved_at_gp_wlud = np.full((n_grid, n_grid), np.nan)
for idx in zip(*np.where(feasible_mask)):
    i, j = idx
    wlud_gp = wlud_required[i, j]

    if wlud_gp <= wlud_levels_dense[0]:
        vmin_achieved_at_gp_wlud[i, j] = true_vmin_3d[i, j, 0]
        continue
    if wlud_gp >= wlud_levels_dense[-1]:
        vmin_achieved_at_gp_wlud[i, j] = true_vmin_3d[i, j, -1]
        continue

    hi = np.searchsorted(wlud_levels_dense, wlud_gp)
    lo = hi - 1
    t = (wlud_gp - wlud_levels_dense[lo]) / (wlud_levels_dense[hi] - wlud_levels_dense[lo])
    v_lo = true_vmin_3d[i, j, lo]
    v_hi = true_vmin_3d[i, j, hi]
    if np.isnan(v_lo) or np.isnan(v_hi):
        continue
    vmin_achieved_at_gp_wlud[i, j] = v_lo + t * (v_hi - v_lo)

vmin_error = vmin_achieved_at_gp_wlud[feasible_mask] - TARGET_VMIN
vmin_rmse = float(np.sqrt(np.mean(vmin_error ** 2))) if len(vmin_error) > 0 else np.nan

# Feasibility agreement
gp_feasible = ~np.isnan(wlud_required)
true_feasible = ~np.isnan(true_wlud_required)
agree = (gp_feasible == true_feasible)
feas_agreement_pct = float(agree.sum() / n_total * 100)

print(f"  Feasible points (GP):   {int(gp_feasible.sum())}/{n_total}")
print(f"  Feasible points (true): {int(true_feasible.sum())}/{n_total}")
print(f"  Feasibility agreement:  {feas_agreement_pct:.1f}%")
print(f"  WLUD RMSE:              {wlud_rmse:.4f}" if not np.isnan(wlud_rmse) else "  WLUD RMSE: N/A")
print(f"  WLUD MAE:               {wlud_mae:.4f}" if not np.isnan(wlud_mae) else "  WLUD MAE: N/A")
print(f"  Vmin error RMSE:        {vmin_rmse:.4f} V" if not np.isnan(vmin_rmse) else "  Vmin error RMSE: N/A")

# ============================================================
# 5. Plots
# ============================================================
print("\n=== 5. Plots ===")

# 5a. Assist map: required WLUD ratio
fig, ax = plt.subplots(figsize=(8, 6))
cf = ax.contourf(CN, PU, wlud_required, levels=np.linspace(0.50, 1.0, 20),
                 cmap="viridis", alpha=0.85)
fig.colorbar(cf, ax=ax, label="Required WLUD ratio (Vwl/Vop)")
cs = ax.contour(CN, PU, wlud_required, levels=[0.6, 0.8, 1.0],
                colors="w", linewidths=1, linestyles="--")
ax.clabel(cs, inline=True, fontsize=9, fmt="%.2f")
infeasible = np.isnan(wlud_required)
if infeasible.any():
    ax.scatter(CN[infeasible], PU[infeasible], c="red", s=8, alpha=0.5, label="Infeasible")
ax.set_xlabel("common_N (mV)")
ax.set_ylabel("PU (mV)")
ax.set_title(f"Required WLUD for Vmin = {TARGET_VMIN}V @ Vop={VOP_FIXED}V", fontsize=12)
ax.legend(fontsize=9)
ax.grid(True, alpha=0.15)
fig.savefig(OUT_DIR / "assist_map.png", dpi=150, bbox_inches="tight")
print(f"  Saved: {OUT_DIR / 'assist_map.png'}")
plt.close(fig)

# 5b. Accuracy: WLUD predicted vs true (scatter)
fig, ax = plt.subplots(figsize=(7, 7))
if feasible_mask.sum() > 0:
    ax.scatter(true_wlud_required[feasible_mask], wlud_required[feasible_mask],
               c=vmin_achieved_at_gp_wlud[feasible_mask] - TARGET_VMIN,
               cmap="bwr", s=20, alpha=0.7, vmin=-0.03, vmax=0.03)
    cbar = fig.colorbar(ax.collections[0], ax=ax, label="Vmin - target (V)")
min_v = min(np.nanmin(true_wlud_required[feasible_mask]), np.nanmin(wlud_required[feasible_mask]))
max_v = max(np.nanmax(true_wlud_required[feasible_mask]), np.nanmax(wlud_required[feasible_mask]))
ax.plot([min_v, max_v], [min_v, max_v], "k--", linewidth=1, alpha=0.5)
ax.set_xlabel("True required WLUD ratio")
ax.set_ylabel("GP estimated WLUD ratio")
ax.set_title(f"WLUD estimation accuracy (RMSE={wlud_rmse:.4f})" if not np.isnan(wlud_rmse) else "WLUD estimation accuracy")
ax.grid(True, alpha=0.3)
ax.axis("equal")
fig.savefig(OUT_DIR / "assist_accuracy.png", dpi=150, bbox_inches="tight")
print(f"  Saved: {OUT_DIR / 'assist_accuracy.png'}")
plt.close(fig)

# 5c. Vmin achieved histogram
fig, ax = plt.subplots(figsize=(8, 4))
if feasible_mask.sum() > 0:
    ax.hist(vmin_achieved_at_gp_wlud[feasible_mask], bins=20, alpha=0.7, color="steelblue", edgecolor="white")
    ax.axvline(TARGET_VMIN, color="red", linewidth=2, linestyle="--", label=f"Target Vmin={TARGET_VMIN}V")
    ax.set_xlabel("Achieved Vmin (V)")
    ax.set_ylabel("Count")
    ax.set_title(f"Achieved Vmin at GP-estimated WLUD  |  RMSE={vmin_rmse:.4f}V" if not np.isnan(vmin_rmse) else "Achieved Vmin")
    ax.legend()
    ax.grid(True, alpha=0.3)
fig.savefig(OUT_DIR / "achieved_vmin_hist.png", dpi=150, bbox_inches="tight")
print(f"  Saved: {OUT_DIR / 'achieved_vmin_hist.png'}")
plt.close(fig)

# ============================================================
# 6. Metrics
# ============================================================
metrics = {
    "stage": 3,
    "target_vmin_V": f"{TARGET_VMIN:.2f}",
    "vop_fixed_V": f"{VOP_FIXED:.1f}",
    "mu_rmse": f"{mu_rmse:.5f}",
    "sigma_rmse": f"{sigma_rmse:.5f}",
    "n_grid": n_grid,
    "n_feasible_gp": int(gp_feasible.sum()),
    "n_feasible_true": int(true_feasible.sum()),
    "feasibility_agreement_pct": f"{feas_agreement_pct:.1f}",
    "wlud_rmse": f"{wlud_rmse:.4f}" if not np.isnan(wlud_rmse) else "N/A",
    "wlud_mae": f"{wlud_mae:.4f}" if not np.isnan(wlud_mae) else "N/A",
    "vmin_achieved_rmse_V": f"{vmin_rmse:.4f}" if not np.isnan(vmin_rmse) else "N/A",
}
print("\n--- Metrics ---")
for k, v in metrics.items():
    print(f"  {k}: {v}")

with open(OUT_DIR / "metrics.txt", "w") as f:
    for k, v in metrics.items():
        f.write(f"{k}: {v}\n")

# Go / No-Go
print("\n--- Go/No-Go Check ---")
go = True
if np.isnan(wlud_rmse) or wlud_rmse > 0.05:
    print(f"  [FAIL] WLUD RMSE {wlud_rmse:.4f} > 0.05 (or NaN)")
    go = False
else:
    print(f"  [PASS] WLUD RMSE {wlud_rmse:.4f} <= 0.05")
if feas_agreement_pct < 90:
    print(f"  [FAIL] Feasibility agreement {feas_agreement_pct:.1f}% < 90%")
    go = False
else:
    print(f"  [PASS] Feasibility agreement {feas_agreement_pct:.1f}% >= 90%")
if np.isnan(vmin_rmse) or vmin_rmse > 0.02:
    print(f"  [FAIL] Vmin achieved RMSE {vmin_rmse:.4f} > 0.02 V (or NaN)")
    go = False
else:
    print(f"  [PASS] Vmin achieved RMSE {vmin_rmse:.4f} <= 0.02 V")

print(f"\n  >>> {'GO' if go else 'NO-GO'} <<<")
with open(OUT_DIR / "go_decision.txt", "w") as f:
    f.write("GO\n" if go else "NO-GO\n")

print("\n=== Stage 3 complete ===")
