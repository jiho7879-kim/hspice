"""
corner_retrain_test_feat.py — Approach 4: Corner feature augmentation

Input feature에 corner indicator를 추가하여 GP가 corner별로 다른 Vop
sensitivity를 학습할 수 있도록 함.
  - Option A: corner ordinal feature (4-level: -2, -1, +1, +2)
  - Option B: one-hot corner features (4 binary dims)
  
Corner-specific Vop sensitivity는 (cn, pu) shift만으로는 부족한데,
corner ID feature를 추가하면 GP가 corner 간 차이를 더 잘 구분.

Usage:
    cd python
    python scripts/corner_retrain_test_feat.py

Output:
    results/corner_retrain_feat/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.utils import Z_FIXED, VOPS, N_VOP
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z

# ============================================================================
# Paths
# ============================================================================
TRAINING_NPZ = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "dataset_real.npz"
ORIGINAL_PTH  = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "surrogate_real.pth"
CORNER_XLSX   = Path(__file__).resolve().parent.parent / "data" / "hspice_real_corner.xlsx"
OUT_DIR       = Path(__file__).resolve().parent.parent / "results" / "corner_retrain_feat"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORNER_SHIFTS = {"TT": (0.0, 0.0), "SSG": (36.3, 44.79998), "SFG": (31.63, -36.76),
                 "FSG": (-29.16, 38.64), "FFG": (-36.42, -44.32)}
CORNER_NAMES = ["FFG", "FSG", "SFG", "SSG"]

# Corner ordinal mapping (FSG=-2, FFG=-1, SFG=+1, SSG=+2)
# This is physically motivated: FSG (fast N + slow P = worst) gets lowest value,
# SSG (slow N + slow P) gets highest, symmetric around TT.
CORNER_ORDINAL = {
    "FSG": -2.0,
    "FFG": -1.0,
    "SFG": 1.0,
    "SSG": 2.0,
}

# One-hot mapping (order: FFG, FSG, SFG, SSG)
CORNER_NAMES_SORTED = ["FFG", "FSG", "SFG", "SSG"]
CORNER_ONEHOT = {cn: np.eye(4)[i] for i, cn in enumerate(CORNER_NAMES_SORTED)}

# Which feature augmentation to use
FEAT_MODE = "onehot"  # "ordinal" or "onehot"

print("=" * 70)
print(f"Corner Retrain [4/4] - Feature augmentation (mode={FEAT_MODE})")
print("=" * 70)

# -------------------------------------------------------------------
# Build corner-labeled dataset: map each (cn,pu) -> corner label
# -------------------------------------------------------------------
# For TT training data, each point already has (cn, pu). We assign a corner
# label based on the nearest corner quadrant.
# Note: The original TT data is sampled from 4 quadrants already.
# But to keep it simple: train on combined data with augmented features.

def corner_label(cn, pu, mode="onehot"):
    """Assign corner label based on (cn, pu) quadrant."""
    # Map to one of the 5 regions: TT/near-TT, FFG, FSG, SFG, SSG
    # Use simple quadrant heuristic plus distance from origin
    if mode == "ordinal":
        # Not useful for TT points that aren't at exact corners
        # So use: sign(cn) * 1 + sign(pu) * 0.5  -> gives -1.5, -0.5, +0.5, +1.5
        cn_s = np.sign(cn)
        pu_s = np.sign(pu)
        return cn_s * 0.7 + pu_s * 0.7  # continuous mapping
    else:
        # One-hot: [is_FFG, is_FSG, is_SFG, is_SSG] based on quadrant
        if cn < -20 and pu < -20: return np.array([1, 0, 0, 0])  # FFG
        if cn < -20 and pu > 20:  return np.array([0, 1, 0, 0])  # FSG
        if cn > 20 and pu < -20:  return np.array([0, 0, 1, 0])  # SFG
        if cn > 20 and pu > 20:   return np.array([0, 0, 0, 1])  # SSG
        # Near TT: use continuous weighting
        d_cn = np.clip(cn / 60, -1, 1)
        d_pu = np.clip(pu / 60, -1, 1)
        w_ffg = max(0, -d_cn) * max(0, -d_pu)
        w_fsg = max(0, -d_cn) * max(0, d_pu)
        w_sfg = max(0, d_cn) * max(0, -d_pu)
        w_ssg = max(0, d_cn) * max(0, d_pu)
        total = w_ffg + w_fsg + w_sfg + w_ssg + 1e-12
        return np.array([w_ffg, w_fsg, w_sfg, w_ssg]) / total

# -------------------------------------------------------------------
# Load data
# -------------------------------------------------------------------
train = np.load(TRAINING_NPZ)
X_tt, y_tt = train["X"], train["y"]
print(f"\nTT data: X={X_tt.shape}")

df = pd.read_excel(CORNER_XLSX).dropna(how="all")
df["mu_V"] = df["snmr_avg"] / 1000.0
df["sigma_V"] = df["snmr_std"] / 1000.0

# -------------------------------------------------------------------
# Build augmented feature vectors
# -------------------------------------------------------------------
print("\nBuilding augmented feature vectors ...")

# Corner data
X_c_list, y_c_list = [], []
for cn_name in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn_name]
    sub = df[df["corner"] == cn_name]
    if FEAT_MODE == "ordinal":
        feat = np.array([CORNER_ORDINAL[cn_name]])
    else:
        feat = CORNER_ONEHOT[cn_name]
    for vop in VOPS:
        row = sub[sub["vop"] == vop]
        if len(row) == 0: continue
        X_c_list.append(np.concatenate([[cn_sh, pu_sh, vop], feat]))
        y_c_list.append([row["mu_V"].mean(), row["sigma_V"].mean()])

X_corner_aug = np.array(X_c_list, dtype=np.float64)
y_corner = np.array(y_c_list, dtype=np.float64)
n_feat = X_corner_aug.shape[1] - 3  # extra features
print(f"  Corner augmented: X={X_corner_aug.shape} (+{n_feat} corner features)")

# TT data with soft corner labels
X_tt_aug_list = []
for i in range(len(X_tt)):
    cn, pu, vop = X_tt[i]
    if FEAT_MODE == "ordinal":
        feat = np.array([corner_label(cn, pu, "ordinal")])
    else:
        feat = corner_label(cn, pu, "onehot")
    X_tt_aug_list.append(np.concatenate([[cn, pu, vop], feat]))

X_tt_aug = np.array(X_tt_aug_list, dtype=np.float64)
print(f"  TT augmented: X={X_tt_aug.shape}")

# Combined
X_comb = np.vstack([X_tt_aug, X_corner_aug])
y_comb = np.vstack([y_tt, y_corner])
print(f"  Combined: X={X_comb.shape}")

# -------------------------------------------------------------------
# Train
# -------------------------------------------------------------------
print("\nTraining with augmented features ...")
surr_new = Surrogate(device="cpu")
surr_new.fit(X_comb, y_comb, n_iter=300, verbose=True)

# Reference (original 3D model)
surr_orig = Surrogate.load(ORIGINAL_PTH, X_tt, y_tt, device="cpu")

# -------------------------------------------------------------------
# Predict corner with augmented features
# -------------------------------------------------------------------
def predict_corner_aug(cn_name: str) -> tuple:
    cn_sh, pu_sh = CORNER_SHIFTS[cn_name]
    if FEAT_MODE == "ordinal":
        feat = np.array([CORNER_ORDINAL[cn_name]])
    else:
        feat = CORNER_ONEHOT[cn_name]
    Xp = np.zeros((N_VOP, 3 + n_feat), dtype=np.float64)
    Xp[:, 0] = cn_sh
    Xp[:, 1] = pu_sh
    Xp[:, 2] = VOPS
    Xp[:, 3:] = feat  # broadcast
    mu, mu_s, sigma, sigma_s = surr_new.predict(Xp)
    z = mu / (sigma + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    return mu, sigma, z, float(v[0]), bool(cens[0])

def predict_orig(cn_sh, pu_sh):
    Xp = np.zeros((N_VOP, 3), dtype=np.float64)
    Xp[:, 0] = cn_sh; Xp[:, 1] = pu_sh; Xp[:, 2] = VOPS
    mu, _, sigma, _ = surr_orig.predict(Xp)
    z = mu / (sigma + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    return mu, sigma, z, float(v[0]), bool(cens[0])

def true_vmin(cn_name):
    sub = df[df["corner"] == cn_name]
    grp = sub.groupby("vop")[["mu_V", "sigma_V"]].mean().sort_index()
    z = grp["mu_V"].values / (grp["sigma_V"].values + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    return float(v[0]), bool(cens[0]), grp["mu_V"].values, grp["sigma_V"].values

# -------------------------------------------------------------------
# Evaluate
# -------------------------------------------------------------------
rows = []
print(f"\n{'Corner':<6} {'Vmin_true':<12} {'Vmin_orig':<12} {'Vmin_new':<12} "
      f"{'Orig_err':<10} {'New_err':<10} {'Improve':<10}")
print("-" * 72)
for cn in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn]
    v_t, c_t, mu_t, sigma_t = true_vmin(cn)
    mu_o, sigma_o, z_o, v_o, c_o = predict_orig(cn_sh, pu_sh)
    mu_n, sigma_n, z_n, v_n, c_n = predict_corner_aug(cn)
    err_o = v_o - v_t if (not np.isnan(v_o) and not np.isnan(v_t)) else np.nan
    err_n = v_n - v_t if (not np.isnan(v_n) and not np.isnan(v_t)) else np.nan
    impr = abs(err_o) - abs(err_n) if (not np.isnan(err_o) and not np.isnan(err_n)) else np.nan
    vt_s = f"{v_t:.4f}" if not c_t else "CENSORED"
    vo_s = f"{v_o:.4f}" if not c_o else "CENSORED"
    vn_s = f"{v_n:.4f}" if not c_n else "CENSORED"
    print(f"{cn:<6} {vt_s:<12} {vo_s:<12} {vn_s:<12} "
          f"{err_o*1000:+.1f}mV" if not np.isnan(err_o) else f"{'N/A':<10}")
    print(f"{'':>6} {'':>12} {'':>12} {'':>12} "
          f"{err_n*1000:+.1f}mV" if not np.isnan(err_n) else f"{'N/A':<10}",
          f"{impr*1000:.1f}mV" if not np.isnan(impr) else f"{'N/A':<10}")
    rows.append({"corner": cn, "cn_mV": cn_sh, "pu_mV": pu_sh,
                 "vmin_true": v_t, "vmin_orig_pred": v_o, "vmin_new_pred": v_n,
                 "orig_err_mV": err_o*1000 if not np.isnan(err_o) else np.nan,
                 "new_err_mV": err_n*1000 if not np.isnan(err_n) else np.nan,
                 "improvement_mV": impr*1000 if not np.isnan(impr) else np.nan,
                 "mu_true": mu_t, "sigma_true": sigma_t,
                 "mu_orig": mu_o, "sigma_orig": sigma_o,
                 "mu_new": mu_n, "sigma_new": sigma_n})

print(f"\n--- Per-corner mu/sigma RMSE ---")
for r in rows:
    cn = r["corner"]
    mu_rmse_o = np.sqrt(np.mean((r["mu_orig"] - r["mu_true"]) ** 2)) * 1000
    mu_rmse_n = np.sqrt(np.mean((r["mu_new"] - r["mu_true"]) ** 2)) * 1000
    sg_rmse_o = np.sqrt(np.mean((r["sigma_orig"] - r["sigma_true"]) ** 2)) * 1000
    sg_rmse_n = np.sqrt(np.mean((r["sigma_new"] - r["sigma_true"]) ** 2)) * 1000
    print(f"  {cn}: mu_RMSE {mu_rmse_o:.2f}->{mu_rmse_n:.2f} mV  "
          f"sigma_RMSE {sg_rmse_o:.2f}->{sg_rmse_n:.2f} mV")

# Figures
colors = {"FFG": "tab:blue", "FSG": "tab:red", "SFG": "tab:green", "SSG": "tab:orange"}
fig, axes = plt.subplots(2, 4, figsize=(22, 10))
for col, cn in enumerate(CORNER_NAMES):
    r = next(x for x in rows if x["corner"] == cn)
    axes[0, col].plot(VOPS, r["mu_true"]*1000, "ko-", label="Measured", markersize=6, linewidth=2)
    axes[0, col].plot(VOPS, r["mu_orig"]*1000, "s--", color=colors[cn], label="Original", markersize=5, alpha=0.7)
    axes[0, col].plot(VOPS, r["mu_new"]*1000, "o-", color=colors[cn], label="Feat-aug", markersize=5)
    axes[0, col].set_title(f"{cn} mu"); axes[0, col].set_xlabel("Vop (V)"); axes[0, col].set_ylabel("mu (mV)")
    axes[0, col].legend(fontsize=7); axes[0, col].grid(True, alpha=0.15)
    axes[1, col].plot(VOPS, r["sigma_true"]*1000, "ko-", label="Measured", markersize=6, linewidth=2)
    axes[1, col].plot(VOPS, r["sigma_orig"]*1000, "s--", color=colors[cn], label="Original", markersize=5, alpha=0.7)
    axes[1, col].plot(VOPS, r["sigma_new"]*1000, "o-", color=colors[cn], label="Feat-aug", markersize=5)
    axes[1, col].set_title(f"{cn} sigma"); axes[1, col].set_xlabel("Vop (V)"); axes[1, col].set_ylabel("sigma (mV)")
    axes[1, col].legend(fontsize=7); axes[1, col].grid(True, alpha=0.15)
fig.suptitle(f"Feature Augmentation (mode={FEAT_MODE}, +{n_feat} dims) - Corner mu/sigma", fontsize=13, y=1.01)
fig.tight_layout(); fig.savefig(OUT_DIR / "corner_mu_sigma.png", dpi=150, bbox_inches="tight"); plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 5))
x = np.arange(len(CORNER_NAMES)); w = 0.25
true_v = [r["vmin_true"] for r in rows]
orig_v = [r["vmin_orig_pred"] for r in rows]
new_v = [r["vmin_new_pred"] for r in rows]
ax.bar(x-w, true_v, w, label="Measured", color="steelblue", alpha=0.85)
ax.bar(x, orig_v, w, label="Original GP", color="coral", alpha=0.7)
ax.bar(x+w, new_v, w, label=f"Feat-aug GP", color="seagreen", alpha=0.85)
ax.set_xticks(x); ax.set_xticklabels(CORNER_NAMES)
ax.set_ylabel("Vmin (V)"); ax.set_title(f"Vmin Comparison (Feature Augmentation {FEAT_MODE})")
ax.legend(); ax.grid(True, alpha=0.15, axis="y")
fig.tight_layout(); fig.savefig(OUT_DIR / "corner_vmin.png", dpi=150, bbox_inches="tight"); plt.close(fig)

# Summary
print(f"\n--- Summary ---")
valid = [r for r in rows if not np.isnan(r["orig_err_mV"]) and not np.isnan(r["new_err_mV"])]
if valid:
    orig_mae = np.mean([abs(r["orig_err_mV"]) for r in valid])
    new_mae = np.mean([abs(r["new_err_mV"]) for r in valid])
    print(f"  Mean |error|: Original={orig_mae:.2f}mV -> New={new_mae:.2f}mV")
    for r in valid:
        tag = "PASS" if abs(r["new_err_mV"]) <= 5 else "FAIL"
        print(f"  [{tag}] {r['corner']}: {r['orig_err_mV']:+.2f} -> {r['new_err_mV']:+.2f} mV  "
              f"(improv={r['improvement_mV']:+.2f}mV)")

pd.DataFrame(rows).to_csv(OUT_DIR / "comparison.csv", index=False)
surr_new.save(OUT_DIR / "surrogate_retrained.pth")
print(f"\n=== complete -> {OUT_DIR} ===")
