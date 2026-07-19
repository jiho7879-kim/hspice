"""
corner_retrain_test_sep.py — Approach 2: Separate per-corner bias correction

Two-stage model:
  1. Main GP (original surrogate) predicts mu, sigma at TT+skew
  2. For each corner, compute residual = measured - predicted at 6 Vops
  3. Interpolate residual across Vop via cubic spline
  4. Final = main_pred + residual_interp

Usage:
    cd python
    python scripts/corner_retrain_test_sep.py

Output:
    results/corner_retrain_sep/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy.interpolate import CubicSpline

from src.utils import Z_FIXED, VOPS, N_VOP
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z

# ============================================================================
# Paths
# ============================================================================
TRAINING_NPZ = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "dataset_real.npz"
ORIGINAL_PTH  = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "surrogate_real.pth"
CORNER_XLSX   = Path(__file__).resolve().parent.parent / "data" / "hspice_real_corner.xlsx"
OUT_DIR       = Path(__file__).resolve().parent.parent / "results" / "corner_retrain_sep"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORNER_SHIFTS = {"TT": (0.0, 0.0), "SSG": (36.3, 44.79998), "SFG": (31.63, -36.76),
                 "FSG": (-29.16, 38.64), "FFG": (-36.42, -44.32)}
CORNER_NAMES = ["FFG", "FSG", "SFG", "SSG"]

print("=" * 70)
print("Corner Retrain [2/4] - Separate per-corner bias correction")
print("=" * 70)

# Load data + original surrogate
train = np.load(TRAINING_NPZ)
X_tt, y_tt = train["X"], train["y"]
surr = Surrogate.load(ORIGINAL_PTH, X_tt, y_tt, device="cpu")

df = pd.read_excel(CORNER_XLSX).dropna(how="all")
df["mu_V"] = df["snmr_avg"] / 1000.0
df["sigma_V"] = df["snmr_std"] / 1000.0

# ---------------------------------------------------------------
# Build per-corner residual interpolators
# ---------------------------------------------------------------
print("\nBuilding per-corner bias correction models ...")
corrections = {}  # cn_name -> {"mu_spline": CubicSpline, "sigma_spline": CubicSpline}

for cn_name in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn_name]
    sub = df[df["corner"] == cn_name]

    # Measured mu, sigma per Vop
    grp = sub.groupby("vop")[["mu_V", "sigma_V"]].mean().sort_index()
    vops = grp.index.values
    mu_meas = grp["mu_V"].values
    sigma_meas = grp["sigma_V"].values

    # Original GP prediction at corner
    Xp = np.zeros((len(vops), 3), dtype=np.float64)
    Xp[:, 0] = cn_sh
    Xp[:, 1] = pu_sh
    Xp[:, 2] = vops
    mu_pred, _, sigma_pred, _ = surr.predict(Xp)

    # Residual = measured - predicted
    mu_res = mu_meas - mu_pred
    sigma_res = sigma_meas - sigma_pred

    # Cubic spline interpolation of residual across Vop
    # Extrapolate flat outside [min_vop, max_vop]
    mu_spline = CubicSpline(vops, mu_res, bc_type="natural", extrapolate=True)
    sigma_spline = CubicSpline(vops, sigma_res, bc_type="natural", extrapolate=True)

    corrections[cn_name] = {"mu_spline": mu_spline, "sigma_spline": sigma_spline}

    print(f"  {cn_name} (cn={cn_sh:+.0f}, pu={pu_sh:+.0f}): "
          f"mu_res=[{mu_res[0]*1000:+.1f}..{mu_res[-1]*1000:+.1f}] mV, "
          f"sigma_res=[{sigma_res[0]*1000:+.1f}..{sigma_res[-1]*1000:+.1f}] mV")

# ---------------------------------------------------------------
# Prediction function: main GP + corner correction
# ---------------------------------------------------------------
def predict_sep(cn_name: str) -> tuple:
    cn_sh, pu_sh = CORNER_SHIFTS[cn_name]
    Xp = np.zeros((N_VOP, 3), dtype=np.float64)
    Xp[:, 0] = cn_sh; Xp[:, 1] = pu_sh; Xp[:, 2] = VOPS

    mu_base, _, sigma_base, _ = surr.predict(Xp)

    # Apply correction
    c = corrections[cn_name]
    mu_corrected = mu_base + c["mu_spline"](VOPS)
    sigma_corrected = sigma_base + c["sigma_spline"](VOPS)

    # Clamp sigma to positive
    sigma_corrected = np.clip(sigma_corrected, 1e-6, None)

    z = mu_corrected / (sigma_corrected + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    return mu_corrected, sigma_corrected, z, float(v[0]), bool(cens[0])

# ---------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------
def true_vmin(cn_name):
    sub = df[df["corner"] == cn_name]
    grp = sub.groupby("vop")[["mu_V", "sigma_V"]].mean().sort_index()
    z = grp["mu_V"].values / (grp["sigma_V"].values + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    return float(v[0]), bool(cens[0]), grp["mu_V"].values, grp["sigma_V"].values

def predict_orig(cn_sh, pu_sh):
    Xp = np.zeros((N_VOP, 3), dtype=np.float64)
    Xp[:, 0] = cn_sh; Xp[:, 1] = pu_sh; Xp[:, 2] = VOPS
    mu, _, sigma, _ = surr.predict(Xp)
    z = mu / (sigma + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    return mu, sigma, z, float(v[0]), bool(cens[0])

rows = []
print(f"\n{'Corner':<6} {'Vmin_true':<12} {'Vmin_orig':<12} {'Vmin_sep':<12} "
      f"{'Orig_err':<10} {'Sep_err':<10} {'Improve':<10}")
print("-" * 72)
for cn in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn]
    v_t, c_t, mu_t, sigma_t = true_vmin(cn)
    mu_o, sigma_o, z_o, v_o, c_o = predict_orig(cn_sh, pu_sh)
    mu_n, sigma_n, z_n, v_n, c_n = predict_sep(cn)
    err_o = v_o - v_t if (not np.isnan(v_o) and not np.isnan(v_t)) else np.nan
    err_n = v_n - v_t if (not np.isnan(v_n) and not np.isnan(v_t)) else np.nan
    impr = abs(err_o) - abs(err_n) if (not np.isnan(err_o) and not np.isnan(err_n)) else np.nan
    print(f"{cn:<6} {f'{v_t:.4f}' if not c_t else 'CENSORED':<12} "
          f"{f'{v_o:.4f}' if not c_o else 'CENSORED':<12} "
          f"{f'{v_n:.4f}' if not c_n else 'CENSORED':<12} "
          f"{err_o*1000:+.1f}mV" if not np.isnan(err_o) else f"{'N/A':<10}")
    print(f"{'':>6} {'':>12} {'':>12} {'':>12} "
          f"{err_n*1000:+.1f}mV" if not np.isnan(err_n) else f"{'N/A':<10}",
          f"{impr*1000:.1f}mV" if not np.isnan(impr) else f"{'N/A':<10}")
    rows.append({"corner": cn, "cn_mV": cn_sh, "pu_mV": pu_sh,
                 "vmin_true": v_t, "vmin_orig_pred": v_o, "vmin_sep_pred": v_n,
                 "orig_err_mV": err_o*1000 if not np.isnan(err_o) else np.nan,
                 "sep_err_mV": err_n*1000 if not np.isnan(err_n) else np.nan,
                 "improvement_mV": impr*1000 if not np.isnan(impr) else np.nan,
                 "mu_true": mu_t, "sigma_true": sigma_t,
                 "mu_orig": mu_o, "sigma_orig": sigma_o,
                 "mu_sep": mu_n, "sigma_sep": sigma_n})

# RMSE
print(f"\n--- Per-corner mu/sigma RMSE ---")
for r in rows:
    cn = r["corner"]
    mu_rmse_o = np.sqrt(np.mean((r["mu_orig"] - r["mu_true"]) ** 2)) * 1000
    mu_rmse_n = np.sqrt(np.mean((r["mu_sep"] - r["mu_true"]) ** 2)) * 1000
    sg_rmse_o = np.sqrt(np.mean((r["sigma_orig"] - r["sigma_true"]) ** 2)) * 1000
    sg_rmse_n = np.sqrt(np.mean((r["sigma_sep"] - r["sigma_true"]) ** 2)) * 1000
    print(f"  {cn}: mu_RMSE {mu_rmse_o:.2f}->{mu_rmse_n:.2f} mV  "
          f"sigma_RMSE {sg_rmse_o:.2f}->{sg_rmse_n:.2f} mV")

# Figures
colors = {"FFG": "tab:blue", "FSG": "tab:red", "SFG": "tab:green", "SSG": "tab:orange"}
fig, axes = plt.subplots(2, 4, figsize=(22, 10))
for col, cn in enumerate(CORNER_NAMES):
    r = next(x for x in rows if x["corner"] == cn)
    axes[0, col].plot(VOPS, r["mu_true"]*1000, "ko-", label="Measured", markersize=6, linewidth=2)
    axes[0, col].plot(VOPS, r["mu_orig"]*1000, "s--", color=colors[cn], label="Original GP", markersize=5, alpha=0.7)
    axes[0, col].plot(VOPS, r["mu_sep"]*1000, "o-", color=colors[cn], label="Sep-corrected", markersize=5)
    axes[0, col].set_title(f"{cn} mu"); axes[0, col].set_xlabel("Vop (V)"); axes[0, col].set_ylabel("mu (mV)")
    axes[0, col].legend(fontsize=7); axes[0, col].grid(True, alpha=0.15)
    axes[1, col].plot(VOPS, r["sigma_true"]*1000, "ko-", label="Measured", markersize=6, linewidth=2)
    axes[1, col].plot(VOPS, r["sigma_orig"]*1000, "s--", color=colors[cn], label="Original GP", markersize=5, alpha=0.7)
    axes[1, col].plot(VOPS, r["sigma_sep"]*1000, "o-", color=colors[cn], label="Sep-corrected", markersize=5)
    axes[1, col].set_title(f"{cn} sigma"); axes[1, col].set_xlabel("Vop (V)"); axes[1, col].set_ylabel("sigma (mV)")
    axes[1, col].legend(fontsize=7); axes[1, col].grid(True, alpha=0.15)
fig.suptitle("Per-corner Bias Correction (CubicSpline residual) - Corner mu/sigma", fontsize=13, y=1.01)
fig.tight_layout(); fig.savefig(OUT_DIR / "corner_mu_sigma.png", dpi=150, bbox_inches="tight"); plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 5))
x = np.arange(len(CORNER_NAMES)); w = 0.25
true_v = [r["vmin_true"] for r in rows]
orig_v = [r["vmin_orig_pred"] for r in rows]
sep_v = [r["vmin_sep_pred"] for r in rows]
ax.bar(x-w, true_v, w, label="Measured", color="steelblue", alpha=0.85)
ax.bar(x, orig_v, w, label="Original GP", color="coral", alpha=0.7)
ax.bar(x+w, sep_v, w, label="Sep-corrected GP", color="seagreen", alpha=0.85)
ax.set_xticks(x); ax.set_xticklabels(CORNER_NAMES)
ax.set_ylabel("Vmin (V)"); ax.set_title("Vmin Comparison (Per-corner Bias Correction)")
ax.legend(); ax.grid(True, alpha=0.15, axis="y")
fig.tight_layout(); fig.savefig(OUT_DIR / "corner_vmin.png", dpi=150, bbox_inches="tight"); plt.close(fig)

# Residual plot
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
for cn in CORNER_NAMES:
    r = next(x for x in rows if x["corner"] == cn)
    axes[0].plot(VOPS, (r["mu_sep"] - r["mu_true"])*1000, "o-", color=colors[cn], label=cn, markersize=5)
    axes[1].plot(VOPS, (r["sigma_sep"] - r["sigma_true"])*1000, "o-", color=colors[cn], label=cn, markersize=5)
axes[0].axhline(0, color="gray"); axes[0].set_xlabel("Vop (V)"); axes[0].set_ylabel("mu residual (mV)")
axes[0].set_title("Corrected mu residual"); axes[0].legend(); axes[0].grid(True, alpha=0.15)
axes[1].axhline(0, color="gray"); axes[1].set_xlabel("Vop (V)"); axes[1].set_ylabel("sigma residual (mV)")
axes[1].set_title("Corrected sigma residual"); axes[1].legend(); axes[1].grid(True, alpha=0.15)
fig.tight_layout(); fig.savefig(OUT_DIR / "residuals.png", dpi=150, bbox_inches="tight"); plt.close(fig)

# Summary
print(f"\n--- Summary ---")
valid = [r for r in rows if not np.isnan(r["orig_err_mV"]) and not np.isnan(r["sep_err_mV"])]
if valid:
    orig_mae = np.mean([abs(r["orig_err_mV"]) for r in valid])
    new_mae = np.mean([abs(r["sep_err_mV"]) for r in valid])
    print(f"  Mean |error|: Original={orig_mae:.2f}mV -> Sep-correction={new_mae:.2f}mV")
    for r in valid:
        tag = "PASS" if abs(r["sep_err_mV"]) <= 5 else "FAIL"
        print(f"  [{tag}] {r['corner']}: {r['orig_err_mV']:+.2f} -> {r['sep_err_mV']:+.2f} mV  "
              f"(improv={r['improvement_mV']:+.2f}mV)")

pd.DataFrame(rows).to_csv(OUT_DIR / "comparison.csv", index=False)
print(f"\n=== complete -> {OUT_DIR} ===")
