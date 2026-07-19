"""
corner_retrain_pvta_contour.py — PVTA contour 비교

Original vs Data Duplication (50x) vs Per-corner Bias Correction
의 Vmin contour를 (common_N, PU) 공간에서 비교.

Usage:
    cd python
    python scripts/corner_retrain_pvta_contour.py

Output:
    results/corner_retrain_contour/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy.interpolate import RBFInterpolator

from src.utils import Z_FIXED, VOPS, N_VOP, VOP_COL
from src.utils import COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z, compute_vmin_on_grid
from src.contour import extract_contour

# ============================================================================
# Paths
# ============================================================================
TRAINING_NPZ = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "dataset_real.npz"
ORIGINAL_PTH  = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "surrogate_real.pth"
DUP_PTH       = Path(__file__).resolve().parent.parent / "results" / "corner_retrain_dup" / "surrogate_retrained.pth"
CORNER_XLSX   = Path(__file__).resolve().parent.parent / "data" / "hspice_real_corner.xlsx"
OUT_DIR       = Path(__file__).resolve().parent.parent / "results" / "corner_retrain_contour"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORNER_SHIFTS = {"TT": (0.0, 0.0), "SSG": (36.3, 44.79998), "SFG": (31.63, -36.76),
                 "FSG": (-29.16, 38.64), "FFG": (-36.42, -44.32)}
CORNER_NAMES = ["FFG", "FSG", "SFG", "SSG"]

N_GRID = 80
CONTOUR_LEVEL = 0.55  # V - FSG Vmin 근처에서 비교 (FSG Vmin=0.545V)

print("=" * 70)
print("PVTA Contour Comparison: Original vs Data Dup vs Per-corner Correction")
print("=" * 70)

# ============================================================================
# 1. Load original surrogate
# ============================================================================
print("\n[1] Loading original surrogate ...")
train = np.load(TRAINING_NPZ)
X_tt, y_tt = train["X"], train["y"]
surr_orig = Surrogate.load(ORIGINAL_PTH, X_tt, y_tt, device="cpu")

def surrogate_orig_fn(x):
    mu, _, sigma, _ = surr_orig.predict(x)
    return mu, sigma

# ============================================================================
# 2. Load data duplication surrogate (50x, if available)
# ============================================================================
print("[2] Loading data duplication surrogate (50x) ...")
df = pd.read_excel(CORNER_XLSX).dropna(how="all")
df["mu_V"] = df["snmr_avg"] / 1000.0
df["sigma_V"] = df["snmr_std"] / 1000.0

surr_dup = None
if DUP_PTH.exists():
    # Reconstruct training data (same as in corner_retrain_test_dup.py)
    DUP_FACTOR = 50
    X_c, y_c = [], []
    for cn_name in CORNER_NAMES:
        cn_sh, pu_sh = CORNER_SHIFTS[cn_name]
        sub = df[df["corner"] == cn_name]
        for vop in VOPS:
            row = sub[sub["vop"] == vop]
            if len(row) == 0: continue
            X_c.append([cn_sh, pu_sh, vop])
            y_c.append([row["mu_V"].mean(), row["sigma_V"].mean()])
    X_corner = np.array(X_c, dtype=np.float64)
    y_corner = np.array(y_c, dtype=np.float64)
    X_cdup = np.tile(X_corner, (DUP_FACTOR, 1))
    y_cdup = np.tile(y_corner, (DUP_FACTOR, 1))
    X_comb = np.vstack([X_tt, X_cdup])
    y_comb = np.vstack([y_tt, y_cdup])
    surr_dup = Surrogate.load(DUP_PTH, X_comb, y_comb, device="cpu")
else:
    print("  [SKIP] Checkpoint not found:", DUP_PTH.name)

def surrogate_dup_fn(x):
    assert surr_dup is not None
    mu, _, sigma, _ = surr_dup.predict(x)
    return mu, sigma

# ============================================================================
# 3. Build per-corner bias correction
# ============================================================================
print("[3] Building per-corner bias correction interpolator ...")

# Compute residuals at each corner (for each Vop)
# residual(corner, Vop) = measured - original_prediction
corner_mu_res = {}   # cn_name -> array of 6 residuals
corner_sigma_res = {}
corner_cnpu = {}     # cn_name -> (cn, pu)

for cn_name in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn_name]
    corner_cnpu[cn_name] = (cn_sh, pu_sh)

    sub = df[df["corner"] == cn_name]
    grp = sub.groupby("vop")[["mu_V", "sigma_V"]].mean().sort_index()
    mu_meas = grp["mu_V"].values
    sigma_meas = grp["sigma_V"].values

    Xp = np.zeros((N_VOP, 3), dtype=np.float64)
    Xp[:, 0] = cn_sh; Xp[:, 1] = pu_sh; Xp[:, 2] = VOPS
    mu_pred, _, sigma_pred, _ = surr_orig.predict(Xp)

    corner_mu_res[cn_name] = mu_meas - mu_pred
    corner_sigma_res[cn_name] = sigma_meas - sigma_pred

# Build RBF interpolator for each Vop: (cn, pu) -> residual
# Training points: 4 corners + TT(0,0) with zero residual.
# The TT anchor ensures the correction decays to zero at the origin,
# preventing the 4-corner RBF from distorting the TT region.
rbf_points = np.array(
    [corner_cnpu[cn] for cn in CORNER_NAMES] + [(0.0, 0.0)],
    dtype=np.float64,
)  # (5, 2)
rbf_mu = []   # list of 6 RBFInterpolator objects
rbf_sigma = []
for vop_idx in range(N_VOP):
    mu_res_vals = np.array([corner_mu_res[cn][vop_idx] for cn in CORNER_NAMES] + [0.0])
    sigma_res_vals = np.array([corner_sigma_res[cn][vop_idx] for cn in CORNER_NAMES] + [0.0])
    # RBF with linear kernel (5 points -> TT-anchored, preserves origin accuracy)
    rbf_mu.append(RBFInterpolator(rbf_points, mu_res_vals.reshape(-1, 1),
                                  kernel="linear", epsilon=1.0))
    rbf_sigma.append(RBFInterpolator(rbf_points, sigma_res_vals.reshape(-1, 1),
                                     kernel="linear", epsilon=1.0))

def surrogate_corrected_fn(x):
    """Original GP + RBF-interpolated per-corner correction."""
    mu_base, _, sigma_base, _ = surr_orig.predict(x)
    # x: (N, 3) = [cn, pu, Vop]
    cn = x[:, 0]
    pu = x[:, 1]
    vop = x[:, 2]
    query = np.column_stack([cn, pu])

    mu_corr = mu_base.copy()
    sigma_corr = sigma_base.copy()

    for vop_idx, vop_val in enumerate(VOPS):
        mask = np.isclose(vop, vop_val)
        if not mask.any():
            continue
        mu_delta = rbf_mu[vop_idx](query[mask]).ravel()
        sigma_delta = rbf_sigma[vop_idx](query[mask]).ravel()
        mu_corr[mask] += mu_delta
        sigma_corr[mask] += sigma_delta

    sigma_corr = np.clip(sigma_corr, 1e-6, None)
    return mu_corr, sigma_corr

# ============================================================================
# 4. Generate Vmin contours for all 3 models
# ============================================================================
print("\n[4] Generating Vmin contours (grid=%dx%d) ..." % (N_GRID, N_GRID))

MODEL_LIST = [
    ("Original GP", surrogate_orig_fn),
    ("Corner-corrected", surrogate_corrected_fn),
]
if surr_dup is not None:
    MODEL_LIST.insert(1, ("Data Dup 50x", surrogate_dup_fn))

results = {}
for label, fn in MODEL_LIST:
    print(f"  Computing {label} ...")
    CN, PU, vmin_grid = compute_vmin_on_grid(
        fn, n_grid=N_GRID,
        common_n_range=(COMMON_N_MIN, COMMON_N_MAX),
        pu_range=(PU_MIN, PU_MAX),
    )
    finite = np.isfinite(vmin_grid)
    vmin_range = (np.nanmin(vmin_grid[finite]), np.nanmax(vmin_grid[finite]))
    print(f"    Vmin range: [{vmin_range[0]:.3f}, {vmin_range[1]:.3f}] V "
          f"({int(finite.sum())}/{finite.size} finite)")

    # Extract contour at CONTOUR_LEVEL
    cn_c, pu_c = extract_contour(vmin_grid, CN, PU, contour_level=CONTOUR_LEVEL)
    print(f"    Contour @{CONTOUR_LEVEL}V: {len(cn_c)} points")

    # Extract multiple contour levels for richer visualization
    levels = sorted([0.45, 0.50, 0.55, 0.60, 0.65])
    contours = {}
    for lvl in levels:
        c, p = extract_contour(vmin_grid, CN, PU, contour_level=lvl)
        if len(c) > 0:
            contours[lvl] = (c, p)

    results[label] = {
        "CN": CN, "PU": PU, "vmin_grid": vmin_grid,
        "contours": contours,
        "vmin_range": vmin_range,
    }

# ============================================================================
# 5. Plot comparison
# ============================================================================
print("\n[5] Generating figures ...")

N_MODELS = len(results)
# ---- Figure 1: N-panel contour comparison ----
fig, axes = plt.subplots(1, N_MODELS, figsize=(7 * N_MODELS, 7))
levels_fill = np.linspace(0.35, 0.75, 20)
contour_cmap = "RdYlBu_r"

for idx, (label, res) in enumerate(results.items()):
    ax = axes[idx] if N_MODELS > 1 else axes
    CN, PU = res["CN"], res["PU"]
    vmin_grid = res["vmin_grid"]

    cf = ax.contourf(CN, PU, vmin_grid, levels=levels_fill, cmap=contour_cmap, alpha=0.85, extend="both")
    for lvl, (c, p) in res["contours"].items():
        ls = ":" if lvl == CONTOUR_LEVEL else "-"
        lw = 2.5 if lvl == CONTOUR_LEVEL else 1.0
        color = "k" if lvl == CONTOUR_LEVEL else "gray"
        ax.plot(c, p, ls, color=color, linewidth=lw, label=f"Vmin={lvl:.2f}V" if idx == N_MODELS - 1 else "")

    if CONTOUR_LEVEL in res["contours"]:
        c, p = res["contours"][CONTOUR_LEVEL]
        ax.plot(c, p, "k-", linewidth=2.5, label=f"Vmin={CONTOUR_LEVEL:.2f}V")

    for cn_name, (cn_sh, pu_sh) in CORNER_SHIFTS.items():
        if cn_name == "TT": continue
        color = "darkred" if cn_name == "FSG" else "dimgray"
        ax.plot(cn_sh, pu_sh, "D", markersize=7, color=color, zorder=5)
        ax.annotate(cn_name, (cn_sh, pu_sh), xytext=(4, 4),
                    textcoords="offset points", fontsize=8, color=color, fontweight="bold")

    ax.plot(0, 0, "o", markersize=5, color="k", zorder=5)
    ax.annotate("TT", (0, 0), xytext=(4, 4), textcoords="offset points", fontsize=7, color="k")

    ax.set_xlabel("common_N_shift (mV)")
    ax.set_ylabel("PU_shift (mV)")
    ax.set_title(f"({chr(97+idx)}) {label}", fontsize=11)
    ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX)
    ax.set_ylim(PU_MIN, PU_MAX)
    ax.grid(True, alpha=0.15)

    if idx == 0:
        ax.legend(fontsize=7, loc="upper left")

fig.subplots_adjust(right=0.915)
cbar_ax = fig.add_axes([0.925, 0.12, 0.012, 0.76])
cbar = fig.colorbar(cf, cax=cbar_ax, label="Vmin (V)")
model_names = " vs ".join(results.keys())
fig.suptitle(f"PVTA Vmin Contour: {model_names}", fontsize=13, y=1.02)
fig.savefig(OUT_DIR / "pvta_contour_comparison.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: pvta_contour_comparison.png")

# ---- Figure 2: Difference maps (new - original) ----
has_dup = "Data Dup 50x" in results
diff_panels = [("Corner-corrected - Original", "Corner-corrected")]
if has_dup:
    diff_panels.insert(0, ("Data Dup 50x - Original", "Data Dup 50x"))
n_diff = len(diff_panels)
fig, axes = plt.subplots(1, n_diff, figsize=(7 * n_diff, 6))
for idx, (label, key) in enumerate(diff_panels):
    res_new = results[key]
    ax = axes[idx] if n_diff > 1 else axes
    diff = res_new["vmin_grid"] - results["Original GP"]["vmin_grid"]
    max_abs = max(abs(np.nanmin(diff)), abs(np.nanmax(diff)))
    vlim = max(0.05, max_abs)

    cf = ax.contourf(res_new["CN"], res_new["PU"], diff,
                      levels=np.linspace(-vlim, vlim, 21),
                      cmap="RdBu", alpha=0.85, extend="both")
    ax.contour(res_new["CN"], res_new["PU"], diff, levels=[0],
               colors="gray", linewidths=0.8, linestyles=":")

    for cn_name in CORNER_NAMES:
        cn_sh, pu_sh = CORNER_SHIFTS[cn_name]
        ax.plot(cn_sh, pu_sh, "D", markersize=6, color="k", zorder=5)

    ax.set_xlabel("common_N_shift (mV)")
    ax.set_ylabel("PU_shift (mV)")
    ax.set_title(f"({chr(97+idx)}) {label}")
    ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX)
    ax.set_ylim(PU_MIN, PU_MAX)
    ax.grid(True, alpha=0.15)
    fig.colorbar(cf, ax=ax, label="Delta Vmin (V)", pad=0.02)

fig.suptitle("Vmin Difference: Retrained - Original GP", fontsize=13)
fig.tight_layout()
fig.savefig(OUT_DIR / "vmin_difference_maps.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: vmin_difference_maps.png")

# ---- Figure 3: Corner Vmin bar chart (all 3 models) ----
print("\n--- Corner Vmin comparison (all 3 models) ---")

def predict_vmin(surrogate_fn, cn_sh, pu_sh):
    Xp = np.zeros((N_VOP, 3), dtype=np.float64)
    Xp[:, 0] = cn_sh; Xp[:, 1] = pu_sh; Xp[:, 2] = VOPS
    mu, sigma = surrogate_fn(Xp)
    z = mu / (sigma + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    return float(v[0]), bool(cens[0])

def true_vmin(cn_name):
    sub = df[df["corner"] == cn_name]
    grp = sub.groupby("vop")[["mu_V", "sigma_V"]].mean().sort_index()
    z = grp["mu_V"].values / (grp["sigma_V"].values + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, return_censored=True)
    return float(v[0]), bool(cens[0])

corner_table = []
for cn in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn]
    v_t, c_t = true_vmin(cn)
    row = {"corner": cn, "vmin_true": v_t, "censored": c_t}
    for label, fn in MODEL_LIST:
        v, c = predict_vmin(fn, cn_sh, pu_sh)
        row[f"vmin_{label.replace(' ', '_')}"] = v
        row[f"cens_{label.replace(' ', '_')}"] = c
    corner_table.append(row)

    parts = [f"true={v_t:.4f}" if not c_t else "true=CENSORED"]
    for label, fn in MODEL_LIST:
        key = f"vmin_{label.replace(' ', '_')}"
        c_key = f"cens_{label.replace(' ', '_')}"
        val = f"{row[key]:.4f}" if not row[c_key] else "CENSORED"
        parts.append(f"{label.split()[0]}={val}")
    print(f"  {cn}:  " + "  ".join(parts))

# Bar chart
bar_labels = ["Measured"] + [label for label, _ in MODEL_LIST]
n_bars = len(bar_labels)
fig, ax = plt.subplots(figsize=(10, 5))
x = np.arange(len(CORNER_NAMES)); w = min(0.22, 0.8 / n_bars)
colors = ["steelblue", "coral", "seagreen", "goldenrod", "purple"]

for bi, bl in enumerate(bar_labels):
    offset = (bi - (n_bars - 1) / 2) * w
    if bl == "Measured":
        vals = [r["vmin_true"] for r in corner_table]
    else:
        key = f"vmin_{bl.replace(' ', '_')}"
        vals = [r[key] for r in corner_table]
    ax.bar(x + offset, vals, w, label=bl, color=colors[bi % len(colors)], alpha=0.85)
    for xi, val in enumerate(vals):
        if not np.isnan(val):
            ax.text(xi + offset, val + 0.003, f"{val:.3f}",
                    ha="center", va="bottom", fontsize=6, rotation=45)

ax.set_xticks(x); ax.set_xticklabels(CORNER_NAMES)
ax.set_ylabel("Vmin (V)")
model_str = " vs ".join(bl for bl in bar_labels)
ax.set_title(f"Corner Vmin: {model_str}")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.15, axis="y")
fig.tight_layout()
fig.savefig(OUT_DIR / "corner_vmin_all_models.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: corner_vmin_all_models.png")

# Save summary data
pd.DataFrame(corner_table).to_csv(OUT_DIR / "comparison.csv", index=False)

print(f"\n=== complete -> {OUT_DIR} ===")
