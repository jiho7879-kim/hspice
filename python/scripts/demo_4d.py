"""
Demo Stage 2: 4D (+WLUD) analytic SNMR -> GP surrogate -> Vmin contour -> WLUD sensitivity.

The 4th input dimension is WLUD ratio (Vwl/Vop), not absolute Vwl.
When evaluating analytic_snmr, compute Vwl = WLUD * Vop per point.

Usage:
    python scripts/demo_4d.py
"""

import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils import (
    Z_FIXED, VOPS, N_VOP, VOP_COL, WLUD_COL,
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
    WLUD_FACTORS, N_WLUD,
)
from src.data import build_dataset, stratified_train_test_split, save_intermediate
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z, compute_vmin_on_grid
from src.physics import analytic_snmr

OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "stage2_4d_wlud"
OUT_DIR.mkdir(parents=True, exist_ok=True)

N_COND = 50
MU_NOISE_STD = 0.002
SIGMA_NOISE_STD = 0.0005

# ============================================================
# 1. Generate 4D analytic training data
# ============================================================
print("=" * 60)
print("Stage 2: 4D+WLUD Analytic Demo")
print("=" * 60)

print("\n=== 1. Generate 4D synthetic data ===")
rng = np.random.default_rng(42)

# Sample (cn, pu) conditions
X_cnpu = build_dataset(N_COND)  # (N_COND*6, 3): [cn, pu, Vop]
n_base = len(X_cnpu)

# Expand to 4D: replicate each row for every WLUD level
# 4th dimension = WLUD ratio (Vwl/Vop), not absolute Vwl
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
        # Vwl = WLUD * Vop — compute here for analytic_snmr call
        vwl = vop * wlud
        mu, sigma = analytic_snmr(cn, pu, vop, vwl_v=vwl)
        y_4d[start + j] = [
            mu + rng.normal(0, MU_NOISE_STD),
            sigma + rng.normal(0, SIGMA_NOISE_STD),
        ]

print(f"  4D dataset: X {X_4d.shape}, y {y_4d.shape}")
print(f"  cn range:    [{X_4d[:,0].min():.1f}, {X_4d[:,0].max():.1f}]")
print(f"  WLUD range:  [{X_4d[:,WLUD_COL].min():.2f}, {X_4d[:,WLUD_COL].max():.2f}]")
print(f"  mu range:    [{y_4d[:,0].min():.4f}, {y_4d[:,0].max():.4f}]")
print(f"  sigma range: [{y_4d[:,1].min():.5f}, {y_4d[:,1].max():.5f}]")

# ============================================================
# 2. Train GP surrogate (4D)
# ============================================================
print("\n=== 2. Train GP surrogate (4D) ===")
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
# 3. Vmin contour at each WLUD level
# ============================================================
print("\n=== 3. Vmin contours across WLUD levels ===")

n_grid = 40
cna = np.linspace(COMMON_N_MIN, COMMON_N_MAX, n_grid)
pua = np.linspace(PU_MIN, PU_MAX, n_grid)
CN, PU = np.meshgrid(cna, pua, indexing="xy")

true_vmin_all = np.zeros((n_grid, n_grid, N_WLUD))
pred_vmin_all = np.zeros((n_grid, n_grid, N_WLUD))
wlud_monotonic_ok = 0
total_points = 0

for k, wlud in enumerate(WLUD_FACTORS):
    # Predicted Vmin at this WLUD ratio via surrogate
    _, _, vm_pred = compute_vmin_on_grid(
        surrogate_fn, n_grid=n_grid, wlud_fixed=wlud,
    )
    pred_vmin_all[:, :, k] = vm_pred

    # True Vmin at this WLUD: Vwl = WLUD * Vop per Vop level
    vm_true = np.full((n_grid, n_grid), np.nan)
    for i in range(n_grid):
        for j in range(n_grid):
            cn = float(CN[i, j])
            pu = float(PU[i, j])
            z_vals = []
            for vop in VOPS:
                vwl = vop * wlud  # Vwl scales with Vop
                mu, sigma = analytic_snmr(cn, pu, vop, vwl_v=vwl)
                z_vals.append(mu / (sigma + 1e-12))
            z_arr = np.array(z_vals)
            v = compute_vmin_from_z(z_arr.reshape(1, -1), z_target=Z_FIXED)
            vm_true[i, j] = float(v[0])
    true_vmin_all[:, :, k] = vm_true

print(f"  Vmin contours computed for {N_WLUD} WLUD levels")

# Monotonicity: Vmin should increase as WLUD increases
# WLUD_FACTORS[0]=0.50 (strongest assist) -> lowest Vmin
# WLUD_FACTORS[-1]=1.00 (no assist) -> highest Vmin
for i in range(n_grid):
    for j in range(n_grid):
        series = pred_vmin_all[i, j, :]
        if np.any(np.isnan(series)):
            continue
        diffs = np.diff(series)
        if np.all(diffs >= -1e-6):
            wlud_monotonic_ok += 1
        total_points += 1

mono_pct = wlud_monotonic_ok / total_points * 100 if total_points > 0 else 0
print(f"  WLUD monotonicity: {wlud_monotonic_ok}/{total_points} = {mono_pct:.1f}%")

# ============================================================
# 4. Plot: 2x3 grid of Vmin contours
# ============================================================
print("\n=== 4. Plot Vmin contours ===")

fig, axes = plt.subplots(2, 3, figsize=(16, 10))
axes = axes.flatten()
vmin_global = min(np.nanmin(pred_vmin_all), np.nanmin(true_vmin_all))
vmax_global = max(np.nanmax(pred_vmin_all), np.nanmax(true_vmin_all))

for k in range(N_WLUD):
    ax = axes[k]
    wlud = WLUD_FACTORS[k]
    ax.set_title(f"WLUD={wlud:.2f}  (Vwl={wlud*VOPS.mean():.3f}V@Vop=0.7)", fontsize=10)
    cf = ax.contourf(CN, PU, pred_vmin_all[:, :, k],
                     levels=np.linspace(vmin_global, vmax_global, 20),
                     cmap="RdYlBu_r", alpha=0.85)
    cs = ax.contour(CN, PU, pred_vmin_all[:, :, k],
                    levels=[0.55, 0.60, 0.65], colors="k", linewidths=0.6, linestyles="--", alpha=0.4)
    ax.clabel(cs, inline=True, fontsize=8, fmt="%.2f")
    ax.set_xlabel("common_N (mV)")
    ax.set_ylabel("PU (mV)")
    ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX)
    ax.set_ylim(PU_MIN, PU_MAX)
    ax.grid(True, alpha=0.15)

fig.colorbar(cf, ax=axes[:N_WLUD], label="Vmin (V)", location="right", shrink=0.6)

# Bottom-right: WLUD sensitivity at 4 corners
ax = axes[5]
corners = {"FSG": (-60, 60), "SFG": (60, -60), "FFG": (-60, -60), "SSG": (60, 60)}
colors_c = {"FSG": "red", "SFG": "blue", "FFG": "green", "SSG": "orange"}
for name, (cn, pu) in corners.items():
    wlud_vals = WLUD_FACTORS
    vmin_corner = []
    for wlud in wlud_vals:
        z_vals = [analytic_snmr(cn, pu, v, vwl_v=(v * wlud))[0] /
                  analytic_snmr(cn, pu, v, vwl_v=(v * wlud))[1]
                  for v in VOPS]
        v = float(compute_vmin_from_z(np.array(z_vals).reshape(1, -1))[0])
        vmin_corner.append(v)
    ax.plot(wlud_vals, vmin_corner, "o-", color=colors_c[name], label=name, markersize=4)
ax.set_xlabel("WLUD ratio (Vwl/Vop)")
ax.set_ylabel("Vmin (V)")
ax.set_title("WLUD sensitivity @ 4 corners", fontsize=10)
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

fig.suptitle("Stage 2: 4D WLUD ratio — Vmin Contour across WLUD levels", fontsize=13, y=1.01)
plt.tight_layout()
fig.savefig(OUT_DIR / "contour_wlud_sweep.png", dpi=150, bbox_inches="tight")
print(f"  Saved: {OUT_DIR / 'contour_wlud_sweep.png'}")
plt.close(fig)

# ============================================================
# 5. Single contour comparison: no assist vs strongest assist
# ============================================================
print("\n=== 5. Assist effect: WLUD=1.0 vs WLUD=0.5 ===")

fig, ax = plt.subplots(figsize=(8, 6))
vmin_no_assist = pred_vmin_all[:, :, -1]   # WLUD=1.0 (no assist)
vmin_full_assist = pred_vmin_all[:, :, 0]   # WLUD=0.50 (strongest)
vmin_diff = vmin_no_assist - vmin_full_assist

cf = ax.contourf(CN, PU, vmin_diff, levels=np.linspace(0, vmax_global - vmin_global, 20),
                 cmap="viridis", alpha=0.85)
fig.colorbar(cf, ax=ax, label="Vmin reduction from assist (V)")
cs = ax.contour(CN, PU, vmin_diff, levels=[0.05, 0.1, 0.15], colors="w", linewidths=1, linestyles="--")
ax.clabel(cs, inline=True, fontsize=9, fmt="%.2fV")
ax.set_xlabel("common_N (mV)")
ax.set_ylabel("PU (mV)")
ax.set_title("Vmin reduction: WLUD=1.0 -> WLUD=0.50", fontsize=12)
ax.grid(True, alpha=0.15)

fig.savefig(OUT_DIR / "assist_benefit.png", dpi=150, bbox_inches="tight")
print(f"  Saved: {OUT_DIR / 'assist_benefit.png'}")
plt.close(fig)

# ============================================================
# 6. Metrics
# ============================================================
metrics = {
    "stage": 2,
    "n_cond": N_COND,
    "n_wlud": N_WLUD,
    "mu_rmse": f"{mu_rmse:.5f}",
    "sigma_rmse": f"{sigma_rmse:.5f}",
    "wlud_monotonicity_pct": f"{mono_pct:.1f}",
    "vmin_range_no_assist": f"[{np.nanmin(vmin_no_assist):.3f}, {np.nanmax(vmin_no_assist):.3f}]",
    "vmin_range_full_assist": f"[{np.nanmin(vmin_full_assist):.3f}, {np.nanmax(vmin_full_assist):.3f}]",
    "max_assist_benefit_V": f"{np.nanmax(vmin_diff):.3f}",
}
print("\n--- Metrics ---")
for k, v in metrics.items():
    print(f"  {k}: {v}")

with open(OUT_DIR / "metrics.txt", "w") as f:
    for k, v in metrics.items():
        f.write(f"{k}: {v}\n")

print(f"\n  Metrics saved: {OUT_DIR / 'metrics.txt'}")

# Go / No-Go
print("\n--- Go/No-Go Check ---")
go = True
if mu_rmse > 0.015:
    print(f"  [FAIL] mu RMSE {mu_rmse:.5f} > 0.015")
    go = False
else:
    print(f"  [PASS] mu RMSE {mu_rmse:.5f} <= 0.015")
if mono_pct < 95:
    print(f"  [FAIL] WLUD monotonicity {mono_pct:.1f}% < 95%")
    go = False
else:
    print(f"  [PASS] WLUD monotonicity {mono_pct:.1f}% >= 95%")
if np.nanmax(vmin_diff) < 0.02:
    print(f"  [FAIL] Max assist benefit {np.nanmax(vmin_diff):.3f}V < 0.02V")
    go = False
else:
    print(f"  [PASS] Max assist benefit {np.nanmax(vmin_diff):.3f}V >= 0.02V")

print(f"\n  >>> {'GO' if go else 'NO-GO'} <<<")
with open(OUT_DIR / "go_decision.txt", "w") as f:
    f.write("GO\n" if go else "NO-GO\n")

print("\n=== Stage 2 complete ===")
