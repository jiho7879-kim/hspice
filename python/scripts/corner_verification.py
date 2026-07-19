"""
Corner verification: independent HSPICE corner data vs GP surrogate.

Data:
  - hspice_real_corner.xlsx - measurements at 4 process corners (FFG/FSG/SFG/SSG)
    across Vop=0.4-0.9V. snmr_avg/snmr_std in mV.
  - hspice_real.xlsx - TT-corner (vtmskew_n, vtmskew_pu) sweep used for training.
  - surrogate_real.pth - trained GP from stage4_real.

Two-phase analysis:
  Phase 1 - Data integrity + EDA (corner data alone)
  Phase 2 - Surrogate verification (corner data vs GP prediction)

Usage:
    python scripts/corner_verification.py
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
CORNER_XLSX = Path(__file__).resolve().parent.parent / "data" / "hspice_real_corner.xlsx"
TRAINING_NPZ = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "dataset_real.npz"
SURROGATE_PTH = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "surrogate_real.pth"
OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "corner_verification"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Corner definitions - PDK corner model equivalent shifts (mV)
# Provided by user (2026-07-09)
# ============================================================================
CORNER_SHIFTS = {
    "TT":  (0.0,   0.0),
    "SSG": (36.3,  44.79998),
    "SFG": (31.63, -36.76),
    "FSG": (-29.16, 38.64),
    "FFG": (-36.42, -44.32),
}
CORNER_NAMES = ["FFG", "FSG", "SFG", "SSG"]  # analysis order

# ============================================================================
# 1. Load corner data
# ============================================================================
print("=" * 70)
print("Corner Verification - Real HSPICE Corner Data vs GP Surrogate")
print("=" * 70)

print(f"\nLoading corner data from {CORNER_XLSX.name} ...")
df = pd.read_excel(CORNER_XLSX)
df = df.dropna(how="all")
print(f"  Shape: {df.shape}")
print(f"  Columns: {list(df.columns)}")
print(f"  Corners: {sorted(df['corner'].unique())}")
print(f"  Vop range: [{df['vop'].min()}, {df['vop'].max()}]")

# Convert mV -> V (snmr_avg, snmr_std are in mV from HSPICE)
df["mu_V"] = df["snmr_avg"] / 1000.0
df["sigma_V"] = df["snmr_std"] / 1000.0

# ============================================================================
# Phase 1: Data Integrity Checks
# ============================================================================
print("\n" + "=" * 70)
print("Phase 1: Data Integrity Checks")
print("=" * 70)

integrity_log: list[str] = []
def _check(ok: bool, label: str, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    msg = f"  [{status}] {label}" + (f" - {detail}" if detail else "")
    print(msg)
    integrity_log.append(msg)
    return ok

all_pass = True

# 1a. Each corner has all 6 Vop levels
print("\n--- 1a. Vop coverage ---")
for cn in CORNER_NAMES:
    sub = df[df["corner"] == cn]
    vops_present = sorted(sub["vop"].unique())
    missing = [v for v in VOPS if v not in vops_present]
    ok = len(missing) == 0
    detail = f"{cn}: {len(vops_present)}/6 Vops"
    if not ok:
        detail += f", missing {missing}"
    _check(ok, f"Vop coverage {cn}", detail)
    if not ok:
        all_pass = False

# 1b. Vop monotonicity: mu should increase with Vop (for a fixed corner)
print("\n--- 1b. mu(Vop) monotonicity ---")
for cn in CORNER_NAMES:
    sub = df[df["corner"] == cn]
    # average by Vop
    avg = sub.groupby("vop")["mu_V"].mean().sort_index()
    vals = avg.values
    mono_ok = all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1))
    detail = f"{cn}: mu [{vals[0]:.4f} → {vals[-1]:.4f}] V"
    _check(mono_ok, f"mu(Vop) monotonic {cn}", detail)
    if not mono_ok:
        all_pass = False

# 1c. sigma consistency: sigma should be within reasonable range
print("\n--- 1c. sigma_SNMR magnitude check ---")
for cn in CORNER_NAMES:
    sub = df[df["corner"] == cn]
    s_min, s_max = sub["sigma_V"].min(), sub["sigma_V"].max()
    ok = (s_min > 0.005) and (s_max < 0.030)
    detail = f"{cn}: sigma range [{s_min:.5f}, {s_max:.5f}] V"
    _check(ok, f"sigma range {cn}", detail)
    if not ok:
        all_pass = False

# 1d. Duplicate detection: any identical (corner, vop) pairs?
print("\n--- 1d. Duplicate (corner, vop) detection ---")
dup = df.groupby(["corner", "vop"]).size()
dup = dup[dup > 1]
if len(dup) > 0:
    print(f"  [INFO] {len(dup)} (corner, vop) groups with multiple entries:")
    for (c, v), n in dup.items():
        sub = df[(df["corner"] == c) & (df["vop"] == v)]
        mus = sub["mu_V"].values
        print(f"    {c} @ Vop={v}: {n} entries, mu={mus}")
else:
    print("  [INFO] No duplicate (corner, vop) entries")

# 1e. FSG should be worse (higher Vmin) than SFG (pre-check)
print("\n--- 1e. Corner ranking pre-check (FSG vs SFG) ---")
# Compute approximate Vmin for each corner from averaged data
approx_vmin = {}
for cn in CORNER_NAMES:
    sub = df[df["corner"] == cn]
    avg = sub.groupby("vop")[["mu_V", "sigma_V"]].mean().sort_index()
    z = avg["mu_V"].values / (avg["sigma_V"].values + 1e-12)
    v = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED)
    approx_vmin[cn] = float(v[0])
fsg_ok = approx_vmin.get("FSG", np.nan) > approx_vmin.get("SFG", np.nan)
detail = f"FSG Vmin~{approx_vmin.get('FSG',np.nan):.3f} vs SFG Vmin~{approx_vmin.get('SFG',np.nan):.3f} V"
_check(fsg_ok, "FSG Vmin > SFG Vmin (FSG worst corner)", detail)
if not fsg_ok:
    all_pass = False

# 1f. Corner separation: check that corners have distinct mu
print("\n--- 1f. Corner distinctness ---")
for i, c1 in enumerate(CORNER_NAMES):
    for c2 in CORNER_NAMES[i + 1:]:
        v1 = df[df["corner"] == c1].groupby("vop")["mu_V"].mean().sort_index().values
        v2 = df[df["corner"] == c2].groupby("vop")["mu_V"].mean().sort_index().values
        # correlation as a measure of similarity
        r = np.corrcoef(v1, v2)[0, 1]
        if r > 0.99:
            print(f"  [WARN] {c1} vs {c2}: mu corr={r:.4f} - very similar!")
        else:
            print(f"  [INFO] {c1} vs {c2}: mu corr={r:.4f} - distinct")

integrity_decision = "ALL CHECKS PASSED" if all_pass else "SOME CHECKS FAILED"
print(f"\n  >>> Data Integrity: {integrity_decision} <<<")

# Save integrity log
with open(OUT_DIR / "data_integrity.txt", "w") as f:
    f.write("Data Integrity Report\n")
    f.write("=" * 50 + "\n")
    for line in integrity_log:
        f.write(line + "\n")
    f.write(f"\n>>> {integrity_decision} <<<\n")

# ============================================================================
# Phase 1b: Corner Data Insights (EDA)
# ============================================================================
print("\n" + "=" * 70)
print("Phase 1b: Corner Data Insights")
print("=" * 70)

# Aggregate each corner: mean mu, sigma per Vop
corner_stats = {}
for cn in CORNER_NAMES:
    sub = df[df["corner"] == cn]
    grp = sub.groupby("vop")[["mu_V", "sigma_V"]].agg(["mean", "std", "count"])
    corner_stats[cn] = grp

print("\n--- Corner summary (mean mu, sigma per Vop) ---")
rows = []
for cn in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn]
    for vop in VOPS:
        mu_m = corner_stats[cn].loc[vop, ("mu_V", "mean")]
        mu_s = corner_stats[cn].loc[vop, ("mu_V", "std")]
        sg_m = corner_stats[cn].loc[vop, ("sigma_V", "mean")]
        n = int(corner_stats[cn].loc[vop, ("sigma_V", "count")])
        rows.append((cn, cn_sh, pu_sh, vop, mu_m, mu_s, sg_m, n))

summary = pd.DataFrame(rows, columns=[
    "corner", "cn_mV", "pu_mV", "Vop_V", "mu_mean_V", "mu_std_V", "sigma_mean_V", "N"])
print(summary.to_string(index=False, float_format=lambda x: f"{x:.5f}"))

# Vmin from corner data (true corner Vmin)
print("\n--- Corner Vmin (from measured SNMR across Vop) ---")
corner_vmin = {}
for cn in CORNER_NAMES:
    grp = corner_stats[cn]
    z = grp[("mu_V", "mean")].values / (grp[("sigma_V", "mean")].values + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    corner_vmin[cn] = {"vmin_V": float(v[0]), "censored": bool(cens[0])}
    cn_sh, pu_sh = CORNER_SHIFTS[cn]
    tag = "CENSORED" if cens[0] else f"{v[0]:.4f}V"
    z_str = "  ".join(f"{zv:.2f}" for zv in z)
    print(f"  {cn} (cn={cn_sh:+.1f}, pu={pu_sh:+.1f}): Vmin={tag}  Z(Vop)=[{z_str}]")

# Corner ranking
sorted_corners = sorted(corner_vmin.items(), key=lambda x: x[1]["vmin_V"] if not x[1]["censored"] else -1)
print("\n--- Corner Vmin ranking (best → worst) ---")
for rank, (cn, info) in enumerate(sorted_corners, 1):
    tag = f"{info['vmin_V']:.4f}V" if not info["censored"] else "CENSORED"
    print(f"  {rank}. {cn}: {tag}")

insights_log = []
insights_log.append(f"Corner Vmin ranking: {' < '.join(c for c, _ in sorted_corners)}")
insights_log.append(f"FSG worst-corner check: {'PASS' if approx_vmin.get('FSG',np.nan) == max(approx_vmin.values()) else 'FAIL'}")

# ============================================================================
# Phase 2: Surrogate Verification
# ============================================================================
print("\n" + "=" * 70)
print("Phase 2: Surrogate Verification (corner data vs GP prediction)")
print("=" * 70)

# Load training data (needed for Surrogate.load)
print(f"\nLoading training data from {TRAINING_NPZ.name} ...")
train = np.load(TRAINING_NPZ)
X_train, y_train = train["X"], train["y"]
print(f"  X_train: {X_train.shape}, y_train: {y_train.shape}")

# Load surrogate
print(f"Loading surrogate from {SURROGATE_PTH.name} ...")
surr = Surrogate.load(SURROGATE_PTH, X_train, y_train, device="cpu")

# Predict at each corner's equivalent (cn, pu)
print("\n--- Corner predictions from surrogate ---")
corner_pred = {}
for cn in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn]
    X_corner = np.zeros((N_VOP, 3), dtype=np.float64)
    X_corner[:, 0] = cn_sh
    X_corner[:, 1] = pu_sh
    X_corner[:, 2] = VOPS
    mu_pred, mu_std, sigma_pred, sigma_std = surr.predict(X_corner)
    corner_pred[cn] = {
        "cn": cn_sh, "pu": pu_sh,
        "mu_pred": mu_pred, "mu_std": mu_std,
        "sigma_pred": sigma_pred, "sigma_std": sigma_std,
    }
    # Surrogate Vmin
    z_pred = mu_pred / (sigma_pred + 1e-12)
    v, cens = compute_vmin_from_z(z_pred.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    corner_pred[cn]["vmin_pred"] = float(v[0])
    corner_pred[cn]["vmin_censored"] = bool(cens[0])
    tag = "CENSORED" if cens[0] else f"{v[0]:.4f}V"
    print(f"  {cn} (cn={cn_sh:+.1f}, pu={pu_sh:+.1f}): Vmin_pred={tag}")

# Compare corner truth vs prediction
print("\n--- Corner Vmin: measured vs predicted ---")
vmin_comparison = []
for cn in CORNER_NAMES:
    v_true = corner_vmin[cn]["vmin_V"]
    v_pred = corner_pred[cn]["vmin_pred"]
    diff = v_pred - v_true if (not np.isnan(v_pred) and not np.isnan(v_true)) else np.nan
    pct = (diff / v_true * 100) if (not np.isnan(diff) and abs(v_true) > 1e-6) else np.nan
    cn_sh, pu_sh = CORNER_SHIFTS[cn]
    tag_c = f"{v_true:.4f}" if not corner_vmin[cn]["censored"] else "CENSORED"
    tag_p = f"{v_pred:.4f}" if not corner_pred[cn]["vmin_censored"] else "CENSORED"
    diff_str = f"{diff:.4f}" if not np.isnan(diff) else "N/A"
    pct_str = f"{pct:.1f}%" if not np.isnan(pct) else "N/A"
    print(f"  {cn}: true={tag_c}  pred={tag_p}  diff={diff_str} ({pct_str})")
    vmin_comparison.append((cn, cn_sh, pu_sh, v_true, v_pred, diff, pct))

# Per-corner mu/sigma RMSE
print("\n--- Per-corner mu/sigma RMSE (across Vops) ---")
for cn in CORNER_NAMES:
    grp = corner_stats[cn]
    mu_true = grp[("mu_V", "mean")].values
    mu_pred = corner_pred[cn]["mu_pred"]
    mu_rmse = np.sqrt(np.mean((mu_pred - mu_true) ** 2))
    sigma_true = grp[("sigma_V", "mean")].values
    sigma_pred = corner_pred[cn]["sigma_pred"]
    sigma_rmse = np.sqrt(np.mean((sigma_pred - sigma_true) ** 2))
    print(f"  {cn}: mu RMSE={mu_rmse:.5f} V, sigma RMSE={sigma_rmse:.5f} V")

# ============================================================================
# Surrogate verification summary
# ============================================================================
print("\n--- Surrogate Verification Summary ---")
verification_log = []

# Check 1: Vmin error magnitude
vmin_errors = [d for d in vmin_comparison if not np.isnan(d[5])]
if vmin_errors:
    max_abs_err = max(abs(d[5]) for d in vmin_errors)
    ok = max_abs_err < 0.1  # 100mV threshold
    _check(ok, f"Max |Vmin error| < 0.1V", f"max |err| = {max_abs_err:.4f} V")
    verification_log.append(f"Vmin max abs error: {max_abs_err:.4f} V")
else:
    _check(False, "No valid Vmin comparisons")

# Check 2: FSG worst in prediction
pred_vmins = {cn: corner_pred[cn]["vmin_pred"] for cn in CORNER_NAMES
              if not corner_pred[cn]["vmin_censored"]}
if "FSG" in pred_vmins:
    fsg_worst_pred = pred_vmins["FSG"] == max(pred_vmins.values())
    _check(fsg_worst_pred, "FSG worst in surrogate prediction",
           f"FSG={pred_vmins['FSG']:.4f}, max={max(pred_vmins.values()):.4f}")
else:
    _check(False, "FSG has no valid Vmin prediction")

# Check 3: Vmin ranking consistency
true_ranking = sorted(corner_vmin.items(), key=lambda x: x[1]["vmin_V"] if not x[1]["censored"] else 999)
pred_ranking = sorted(pred_vmins.items(), key=lambda x: x[1])
true_order = [c for c, _ in true_ranking]
pred_order = [c for c, _ in pred_ranking]
if true_order == pred_order:
    _check(True, "Vmin ranking consistent", f"true={true_order}, pred={pred_order}")
else:
    _check(False, "Vmin ranking mismatch", f"true={true_order}, pred={pred_order}")

print(f"\n  >>> Surrogate Corner Verification complete <<<")

# ============================================================================
# Visualization
# ============================================================================
print(f"\n=== Generating figures → {OUT_DIR} ===")

# ---- Figure 1: mu(Vop) and sigma(Vop) per corner ----
fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
colors = {"FFG": "tab:blue", "FSG": "tab:red", "SFG": "tab:green", "SSG": "tab:orange"}

# (a) mu(Vop)
ax = axes[0]
for cn in CORNER_NAMES:
    grp = corner_stats[cn]
    vops = grp.index.values
    mu_m = grp[("mu_V", "mean")].values
    mu_s = grp[("mu_V", "std")].values
    ax.errorbar(vops, mu_m, yerr=mu_s, fmt="o-", color=colors[cn],
                label=f"{cn}", capsize=3, markersize=6)
    # Surrogate prediction
    ax.plot(vops, corner_pred[cn]["mu_pred"], "--", color=colors[cn], alpha=0.5,
            linewidth=1.5)
ax.set_xlabel("Vop (V)")
ax.set_ylabel("mu_SNMR (V)")
ax.set_title("(a) mu_SNMR vs Vop (solid=meas, dash=GP)")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.15)

# (b) sigma(Vop)
ax = axes[1]
for cn in CORNER_NAMES:
    grp = corner_stats[cn]
    vops = grp.index.values
    sg_m = grp[("sigma_V", "mean")].values
    ax.plot(vops, sg_m, "o-", color=colors[cn], label=f"{cn}", markersize=6)
    ax.plot(vops, corner_pred[cn]["sigma_pred"], "--", color=colors[cn], alpha=0.5,
            linewidth=1.5)
ax.set_xlabel("Vop (V)")
ax.set_ylabel("sigma_SNMR (V)")
ax.set_title("(b) sigma_SNMR vs Vop (solid=meas, dash=GP)")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.15)

# (c) Z(Vop) = mu/sigma
ax = axes[2]
for cn in CORNER_NAMES:
    grp = corner_stats[cn]
    vops = grp.index.values
    z_true = grp[("mu_V", "mean")].values / (grp[("sigma_V", "mean")].values + 1e-12)
    z_pred = corner_pred[cn]["mu_pred"] / (corner_pred[cn]["sigma_pred"] + 1e-12)
    ax.plot(vops, z_true, "o-", color=colors[cn], label=f"{cn} meas", markersize=6)
    ax.plot(vops, z_pred, "--", color=colors[cn], alpha=0.5, linewidth=1.5,
            label=f"{cn} GP" if cn == "FFG" else "")
ax.axhline(Z_FIXED, color="gray", linestyle=":", linewidth=1, label=f"Z_target={Z_FIXED}")
ax.set_xlabel("Vop (V)")
ax.set_ylabel("Zscore = mu/sigma")
ax.set_title("(c) Z(Vop) - Vmin crossing")
ax.legend(fontsize=7, ncol=2)
ax.grid(True, alpha=0.15)

fig.suptitle("Corner Verification: HSPICE Measurement vs GP Surrogate", fontsize=13, y=1.02)
fig.tight_layout()
fig.savefig(OUT_DIR / "corner_mu_sigma_z.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: corner_mu_sigma_z.png")

# ---- Figure 2: Vmin bar chart ----
fig, ax = plt.subplots(figsize=(10, 5))
x = np.arange(len(CORNER_NAMES))
width = 0.30
true_vmins = [corner_vmin[cn]["vmin_V"] for cn in CORNER_NAMES]
pred_vmins = [corner_pred[cn]["vmin_pred"] for cn in CORNER_NAMES]
bars1 = ax.bar(x - width/2, true_vmins, width, label="Measured (corner data)", color="steelblue", alpha=0.85)
bars2 = ax.bar(x + width/2, pred_vmins, width, label="GP surrogate", color="coral", alpha=0.85)
# Add value labels
for bar, val in zip(bars1, true_vmins):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
            f"{val:.3f}", ha="center", va="bottom", fontsize=8, color="steelblue")
for bar, val in zip(bars2, pred_vmins):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
            f"{val:.3f}", ha="center", va="bottom", fontsize=8, color="coral")
# Annotate corner (cn, pu)
for i, cn in enumerate(CORNER_NAMES):
    cn_sh, pu_sh = CORNER_SHIFTS[cn]
    ax.text(i, ax.get_ylim()[0] - 0.03, f"({cn_sh:+.0f}, {pu_sh:+.0f})",
            ha="center", va="top", fontsize=8, color="gray")
ax.set_xticks(x)
ax.set_xticklabels(CORNER_NAMES)
ax.set_ylabel("Vmin (V)")
ax.set_title("Corner Vmin: Measured vs GP Surrogate")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.15, axis="y")
fig.tight_layout()
fig.savefig(OUT_DIR / "corner_vmin_bar.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: corner_vmin_bar.png")

# ---- Figure 3: Prediction error decomposition ----
fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
# (a) mu error per Vop per corner
ax = axes[0]
for cn in CORNER_NAMES:
    grp = corner_stats[cn]
    mu_err = corner_pred[cn]["mu_pred"] - grp[("mu_V", "mean")].values
    ax.plot(VOPS, mu_err * 1000, "o-", color=colors[cn], label=cn, markersize=5)
ax.axhline(0, color="gray", linewidth=0.5)
ax.set_xlabel("Vop (V)")
ax.set_ylabel("mu error (mV)")
ax.set_title("(a) mu prediction error (GP - measured)")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.15)
# (b) sigma error per Vop per corner
ax = axes[1]
for cn in CORNER_NAMES:
    grp = corner_stats[cn]
    sigma_err = corner_pred[cn]["sigma_pred"] - grp[("sigma_V", "mean")].values
    ax.plot(VOPS, sigma_err * 1000, "o-", color=colors[cn], label=cn, markersize=5)
ax.axhline(0, color="gray", linewidth=0.5)
ax.set_xlabel("Vop (V)")
ax.set_ylabel("sigma error (mV)")
ax.set_title("(b) sigma prediction error (GP - measured)")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.15)
fig.suptitle("Corner Prediction Errors (GP - HSPICE Measurement)", fontsize=12)
fig.tight_layout()
fig.savefig(OUT_DIR / "corner_prediction_errors.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: corner_prediction_errors.png")

# ============================================================================
# Save results
# ============================================================================
# Insights text
with open(OUT_DIR / "corner_data_insights.txt", "w") as f:
    f.write("Corner Data Insights\n")
    f.write("=" * 50 + "\n")
    f.write(f"\nCorner (cn,pu) mapping:\n")
    for cn in CORNER_NAMES:
        cn_sh, pu_sh = CORNER_SHIFTS[cn]
        f.write(f"  {cn}: cn={cn_sh:+.2f} mV, pu={pu_sh:+.2f} mV\n")
    f.write(f"\nCorner Vmin (measured):\n")
    for cn in CORNER_NAMES:
        info = corner_vmin[cn]
        tag = f"{info['vmin_V']:.4f} V" if not info['censored'] else "CENSORED"
        f.write(f"  {cn}: {tag}\n")
    f.write(f"\nVmin ranking (best → worst):\n")
    for rank, (cn, info) in enumerate(sorted_corners, 1):
        tag = f"{info['vmin_V']:.4f} V" if not info['censored'] else "CENSORED"
        f.write(f"  {rank}. {cn}: {tag}\n")
    f.write(f"\nSummary table:\n")
    f.write(f"{'Corner':<6} {'(cn,pu)mV':<18} {'Vmin_meas(V)':<14} {'Vmin_pred(V)':<14} {'Delta(V)':<10} {'Delta(%)':<10}\n")
    f.write("-" * 72 + "\n")
    for cn in CORNER_NAMES:
        cn_sh, pu_sh = CORNER_SHIFTS[cn]
        vt = corner_vmin[cn]["vmin_V"]
        vp = corner_pred[cn]["vmin_pred"]
        d = vp - vt if (not np.isnan(vp) and not np.isnan(vt)) else np.nan
        pct = d / vt * 100 if (not np.isnan(d) and abs(vt) > 1e-6) else np.nan
        loc = f"({cn_sh:+.0f},{pu_sh:+.0f})"
        vt_s = f"{vt:.4f}" if not corner_vmin[cn]["censored"] else "CENSORED"
        vp_s = f"{vp:.4f}" if not corner_pred[cn]["vmin_censored"] else "CENSORED"
        d_s = f"{d:+.4f}" if not np.isnan(d) else "N/A"
        pct_s = f"{pct:+.1f}" if not np.isnan(pct) else "N/A"
        f.write(f"{cn:<6} {loc:<18} {vt_s:<14} {vp_s:<14} {d_s:<10} {pct_s:<10}\n")

# Verification metrics
with open(OUT_DIR / "verification_metrics.txt", "w") as f:
    f.write("Surrogate Corner Verification Metrics\n")
    f.write("=" * 50 + "\n")
    f.write(f"\nCorner Vmin comparison:\n")
    for cn in CORNER_NAMES:
        vt = corner_vmin[cn]["vmin_V"]
        vp = corner_pred[cn]["vmin_pred"]
        d = vp - vt if (not np.isnan(vp) and not np.isnan(vt)) else np.nan
        pct = d / vt * 100 if (not np.isnan(d) and abs(vt) > 1e-6) else np.nan
        f.write(f"  {cn}: true={vt:.5f}  pred={vp:.5f}  diff={d:+.5f} ({pct:+.1f}%)\n")
    f.write(f"\nPer-corner mu/sigma RMSE:\n")
    for cn in CORNER_NAMES:
        grp = corner_stats[cn]
        mu_t = grp[("mu_V", "mean")].values
        mu_p = corner_pred[cn]["mu_pred"]
        mu_r = np.sqrt(np.mean((mu_p - mu_t) ** 2))
        sg_t = grp[("sigma_V", "mean")].values
        sg_p = corner_pred[cn]["sigma_pred"]
        sg_r = np.sqrt(np.mean((sg_p - sg_t) ** 2))
        f.write(f"  {cn}: mu_RMSE={mu_r:.5f}  sigma_RMSE={sg_r:.5f}\n")
    f.write(f"\nLog:\n")
    for line in verification_log:
        f.write(f"  {line}\n")

print(f"\n=== Corner verification complete → {OUT_DIR} ===")
