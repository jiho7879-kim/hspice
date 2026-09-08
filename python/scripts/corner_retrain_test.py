"""
corner_retrain_test.py — 실험: corner data를 noise-based weighting으로 포함 재학습

Goal:
  TT+skew training data에 corner measurement data를 추가하여 GP surrogate의
  corner Vmin prediction error를 5mV 이하로 개선할 수 있는지 확인.

Method:
  - Training data (stage4_real/dataset_real.npz): TT+skew sweep, N≈1200
  - Corner data (hspice_real_corner.xlsx): 4 corners × 6 Vop = 24 points (duplicated = 48)
  - Corner data에 매우 낮은 noise (1e-6) 할당 → GP가 corner를 거의 통과하도록 강제
  - TT data는 default homoscedastic noise (learned)
  - 재학습 후 corner Vmin error 측정 → 기존 결과와 비교

Usage:
    cd python
    python scripts/corner_retrain_test.py

Output:
    results/corner_retrain/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.utils import Z_FIXED, VOPS, N_VOP, VOP_COL
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z

# ============================================================================
# Paths
# ============================================================================
TRAINING_NPZ = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "dataset_real.npz"
ORIGINAL_PTH  = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "surrogate_real.pth"
CORNER_XLSX   = Path(__file__).resolve().parent.parent / "data" / "hspice_real_corner.xlsx"
OUT_DIR       = Path(__file__).resolve().parent.parent / "results" / "corner_retrain"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Corner definitions
# ============================================================================
CORNER_SHIFTS = {
    "TT":  (0.0,   0.0),
    "SSG": (36.3,  44.79998),
    "SFG": (31.63, -36.76),
    "FSG": (-29.16, 38.64),
    "FFG": (-36.42, -44.32),
}
CORNER_NAMES = ["FFG", "FSG", "SFG", "SSG"]

# ============================================================================
# 0. Load original surrogate & training data
# ============================================================================
print("=" * 70)
print("Corner Retrain Test - noise-based weighting of corner data")
print("=" * 70)

print(f"\n[0] Loading training data & original surrogate ...")
train = np.load(TRAINING_NPZ)
X_tt, y_tt = train["X"], train["y"]
print(f"    TT+skew data: X={X_tt.shape}, y={y_tt.shape}")

surr_orig = Surrogate.load(ORIGINAL_PTH, X_tt, y_tt, device="cpu")

# ============================================================================
# 1. Corner data 로드 (xlsx → X_corner, y_corner)
# ============================================================================
print(f"\n[1] Loading corner data from {CORNER_XLSX.name} ...")
df = pd.read_excel(CORNER_XLSX)
df = df.dropna(how="all")
df["mu_V"] = df["snmr_avg"] / 1000.0
df["sigma_V"] = df["snmr_std"] / 1000.0

X_corner_list, y_corner_list = [], []
for cn_name in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn_name]
    sub = df[df["corner"] == cn_name]
    for vop in VOPS:
        row = sub[sub["vop"] == vop]
        if len(row) == 0:
            continue
        mu = row["mu_V"].mean()
        sigma = row["sigma_V"].mean()
        X_corner_list.append([cn_sh, pu_sh, vop])
        y_corner_list.append([mu, sigma])

X_corner = np.array(X_corner_list, dtype=np.float64)
y_corner = np.array(y_corner_list, dtype=np.float64)
print(f"    Corner data: X={X_corner.shape}, y={y_corner.shape}")

# ============================================================================
# 2. Combined dataset with noise-based weighting
# ============================================================================
print(f"\n[2] Building combined dataset ...")
X_comb = np.vstack([X_tt, X_corner])
y_comb = np.vstack([y_tt, y_corner])

# Noise assignment:
#   Corner data → 매우 낮은 noise (1e-6 STD) → GP가 거의 통과하도록 강제
#   TT data → None (default homoscedastic, learned)
n_corner = len(X_corner)
n_tt = len(X_tt)
y_noise_comb = np.zeros((n_tt + n_corner, 2), dtype=np.float64)
y_noise_comb[:n_tt, :] = 5e-3      # TT: larger noise (variance=2.5e-5, above gpytorch floor)
y_noise_comb[n_tt:, :] = 1e-3      # Corner: lower noise (variance=1e-6)
print(f"    Combined X={X_comb.shape}, y={y_comb.shape}")
print(f"    TT noise STD:  1e-3")
print(f"    Corner noise STD: 1e-4 (higher confidence)")

# ============================================================================
# 3. Retrain surrogate
# ============================================================================
print(f"\n[3] Retraining surrogate with noise-based weighting ...")
surr_new = Surrogate(device="cpu")
surr_new.fit(X_comb, y_comb, y_noise=y_noise_comb, n_iter=300, verbose=True)

# ============================================================================
# 4. Corner prediction: original vs retrained vs ground truth
# ============================================================================
print(f"\n[4] Corner prediction comparison ...")

def predict_corner(surr, cn_sh, pu_sh):
    Xp = np.zeros((N_VOP, 3), dtype=np.float64)
    Xp[:, 0] = cn_sh
    Xp[:, 1] = pu_sh
    Xp[:, 2] = VOPS
    mu, mu_s, sigma, sigma_s = surr.predict(Xp)
    z = mu / (sigma + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    return mu, sigma, z, float(v[0]), bool(cens[0])

def true_vmin(cn_name):
    """Compute 'true' Vmin from corner measurement data."""
    sub = df[df["corner"] == cn_name]
    grp = sub.groupby("vop")[["mu_V", "sigma_V"]].mean().sort_index()
    z = grp["mu_V"].values / (grp["sigma_V"].values + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    return float(v[0]), bool(cens[0]), grp["mu_V"].values, grp["sigma_V"].values

# Comparison table
rows = []
print(f"\n{'Corner':<6} {'Vmin_true':<12} {'Vmin_orig':<12} {'Vmin_new':<12} "
      f"{'Orig_err':<10} {'New_err':<10} {'Improve':<10}")
print("-" * 72)
for cn in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn]

    v_t, c_t, mu_t, sigma_t = true_vmin(cn)
    mu_o, sigma_o, z_o, v_o, c_o = predict_corner(surr_orig, cn_sh, pu_sh)
    mu_n, sigma_n, z_n, v_n, c_n = predict_corner(surr_new, cn_sh, pu_sh)

    err_o = v_o - v_t if (not np.isnan(v_o) and not np.isnan(v_t)) else np.nan
    err_n = v_n - v_t if (not np.isnan(v_n) and not np.isnan(v_t)) else np.nan
    impr = abs(err_o) - abs(err_n) if (not np.isnan(err_o) and not np.isnan(err_n)) else np.nan

    vt_s = f"{v_t:.4f}" if not c_t else "CENSORED"
    vo_s = f"{v_o:.4f}" if not c_o else "CENSORED"
    vn_s = f"{v_n:.4f}" if not c_n else "CENSORED"
    eo_s = f"{err_o * 1000:+.1f}mV" if not np.isnan(err_o) else "N/A"
    en_s = f"{err_n * 1000:+.1f}mV" if not np.isnan(err_n) else "N/A"
    im_s = f"{impr * 1000:.1f}mV" if not np.isnan(impr) else "N/A"

    print(f"{cn:<6} {vt_s:<12} {vo_s:<12} {vn_s:<12} {eo_s:<10} {en_s:<10} {im_s:<10}")

    rows.append({
        "corner": cn, "cn_mV": cn_sh, "pu_mV": pu_sh,
        "vmin_true": v_t, "vmin_true_censored": c_t,
        "vmin_orig_pred": v_o, "vmin_orig_censored": c_o,
        "vmin_new_pred": v_n, "vmin_new_censored": c_n,
        "orig_err_mV": err_o * 1000 if not np.isnan(err_o) else np.nan,
        "new_err_mV": err_n * 1000 if not np.isnan(err_n) else np.nan,
        "improvement_mV": impr * 1000 if not np.isnan(impr) else np.nan,
    })

    # Also store per-Vop for detailed comparison
    rows[-1]["mu_true"] = mu_t
    rows[-1]["sigma_true"] = sigma_t
    rows[-1]["mu_orig"] = mu_o
    rows[-1]["sigma_orig"] = sigma_o
    rows[-1]["mu_new"] = mu_n
    rows[-1]["sigma_new"] = sigma_n

# Per-corner mu/sigma RMSE comparison
print(f"\n\n--- Per-corner mu/sigma RMSE (original vs retrained) ---")
rmse_rows = []
for cn in CORNER_NAMES:
    info = next(r for r in rows if r["corner"] == cn)
    mu_t = info["mu_true"]
    sigma_t = info["sigma_true"]
    mu_o = info["mu_orig"]
    sigma_o = info["sigma_orig"]
    mu_n = info["mu_new"]
    sigma_n = info["sigma_new"]

    mu_rmse_o = np.sqrt(np.mean((mu_o - mu_t) ** 2)) * 1000  # mV
    mu_rmse_n = np.sqrt(np.mean((mu_n - mu_t) ** 2)) * 1000
    sg_rmse_o = np.sqrt(np.mean((sigma_o - sigma_t) ** 2)) * 1000
    sg_rmse_n = np.sqrt(np.mean((sigma_n - sigma_t) ** 2)) * 1000
    rmse_rows.append((cn, mu_rmse_o, mu_rmse_n, sg_rmse_o, sg_rmse_n))
    print(f"  {cn}: mu_RMSE orig={mu_rmse_o:.2f}→new={mu_rmse_n:.2f} mV  |  "
          f"sigma_RMSE orig={sg_rmse_o:.2f}→new={sg_rmse_n:.2f} mV")

# ============================================================================
# 5. Plots
# ============================================================================
print(f"\n[5] Generating figures → {OUT_DIR} ...")
colors = {"FFG": "tab:blue", "FSG": "tab:red", "SFG": "tab:green", "SSG": "tab:orange"}

# ---- Figure 1: mu(Vop) — original vs retrained vs true ----
fig, axes = plt.subplots(2, 4, figsize=(22, 10))

for col, cn in enumerate(CORNER_NAMES):
    info = next(r for r in rows if r["corner"] == cn)

    # (a) mu
    ax = axes[0, col]
    ax.plot(VOPS, info["mu_true"] * 1000, "ko-", label="Measured", markersize=6, linewidth=2)
    ax.plot(VOPS, info["mu_orig"] * 1000, "s--", color=colors[cn], label="Original GP", markersize=5, alpha=0.7)
    ax.plot(VOPS, info["mu_new"] * 1000, "o-", color=colors[cn], label="Retrained GP", markersize=5)
    ax.set_title(f"{cn}  mu_SNMR")
    ax.set_xlabel("Vop (V)")
    ax.set_ylabel("mu (mV)")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.15)

    # (b) sigma
    ax = axes[1, col]
    ax.plot(VOPS, info["sigma_true"] * 1000, "ko-", label="Measured", markersize=6, linewidth=2)
    ax.plot(VOPS, info["sigma_orig"] * 1000, "s--", color=colors[cn], label="Original GP", markersize=5, alpha=0.7)
    ax.plot(VOPS, info["sigma_new"] * 1000, "o-", color=colors[cn], label="Retrained GP", markersize=5)
    ax.set_title(f"{cn}  sigma_SNMR")
    ax.set_xlabel("Vop (V)")
    ax.set_ylabel("sigma (mV)")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.15)

fig.suptitle("Corner mu/sigma: Measured vs Original GP vs Retrained GP (noise-weighted)", fontsize=13, y=1.01)
fig.tight_layout()
fig.savefig(OUT_DIR / "corner_mu_sigma_comparison.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: corner_mu_sigma_comparison.png")

# ---- Figure 2: Vmin bar chart (true vs orig vs new) ----
fig, ax = plt.subplots(figsize=(10, 5))
x = np.arange(len(CORNER_NAMES))
width = 0.25
true_v = [r["vmin_true"] for r in rows]
orig_v = [r["vmin_orig_pred"] for r in rows]
new_v  = [r["vmin_new_pred"] for r in rows]

bars1 = ax.bar(x - width, true_v, width, label="Measured", color="steelblue", alpha=0.85)
bars2 = ax.bar(x, orig_v, width, label="Original GP", color="coral", alpha=0.7)
bars3 = ax.bar(x + width, new_v, width, label="Retrained GP", color="seagreen", alpha=0.85)

for bars, vals in [(bars1, true_v), (bars2, orig_v), (bars3, new_v)]:
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
                f"{val:.3f}", ha="center", va="bottom", fontsize=7, rotation=45)

ax.set_xticks(x)
ax.set_xticklabels(CORNER_NAMES)
ax.set_ylabel("Vmin (V)")
ax.set_title("Vmin Comparison: Measured vs Original GP vs Retrained GP")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.15, axis="y")
fig.tight_layout()
fig.savefig(OUT_DIR / "corner_vmin_comparison.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: corner_vmin_comparison.png")

# ---- Figure 3: Error improvement per corner ----
fig, ax = plt.subplots(figsize=(10, 5))
err_orig = np.array([r["orig_err_mV"] for r in rows])
err_new  = np.array([r["new_err_mV"] for r in rows])
x = np.arange(len(CORNER_NAMES))
width = 0.3
ax.bar(x - width/2, err_orig, width, label="Original GP error", color="coral", alpha=0.8)
ax.bar(x + width/2, err_new, width, label="Retrained GP error", color="seagreen", alpha=0.8)
ax.axhline(0, color="gray", linewidth=0.8)
ax.axhline(5, color="gray", linestyle="--", linewidth=0.5)
ax.axhline(-5, color="gray", linestyle="--", linewidth=0.5)
ax.text(x[-1] + 0.5, 5, "±5mV target", fontsize=8, color="gray")
ax.set_xticks(x)
ax.set_xticklabels(CORNER_NAMES)
ax.set_ylabel("Vmin error (mV)")
ax.set_title("Corner Vmin Prediction Error: Original vs Retrained GP")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.15, axis="y")
fig.tight_layout()
fig.savefig(OUT_DIR / "corner_error_comparison.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: corner_error_comparison.png")

# ============================================================================
# 6. Summary
# ============================================================================
print(f"\n[6] Summary → {OUT_DIR}")
print(f"\n{'=' * 70}")
print(f"Corner Retrain Test — Summary")
print(f"{'=' * 70}")

valid = [r for r in rows if not np.isnan(r["orig_err_mV"]) and not np.isnan(r["new_err_mV"])]
if valid:
    orig_mae = np.mean([abs(r["orig_err_mV"]) for r in valid])
    new_mae  = np.mean([abs(r["new_err_mV"]) for r in valid])
    max_orig = max(abs(r["orig_err_mV"]) for r in valid)
    max_new  = max(abs(r["new_err_mV"]) for r in valid)
    print(f"\n  Mean |error|:  Original={orig_mae:.2f}mV  →  Retrained={new_mae:.2f}mV")
    print(f"  Max  |error|:  Original={max_orig:.2f}mV  →  Retrained={max_new:.2f}mV")
    print(f"  Target: ±5mV")

    for r in valid:
        tag = "✅" if abs(r["new_err_mV"]) <= 5 else "❌"
        print(f"  {tag} {r['corner']}: orig={r['orig_err_mV']:+.2f}mV → "
              f"new={r['new_err_mV']:+.2f}mV  (improvement={r['improvement_mV']:+.2f}mV)")

# Save comparison table
df_out = pd.DataFrame(rows)
df_out.to_csv(OUT_DIR / "comparison.csv", index=False)
print(f"\n  Saved: comparison.csv")

# ============================================================================
# (Optional) Save retrained surrogate
# ============================================================================
surr_new.save(OUT_DIR / "surrogate_retrained.pth")

print(f"\n=== corner_retrain_test complete → {OUT_DIR} ===")
