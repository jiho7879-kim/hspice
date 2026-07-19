"""
Final 9D SNMR batch (seed 2027) — partial-transcription analysis.

data/sheet_final_snmr_seed2027.xlsx is the production 2,000-condition x 5-Vop
SNMR sheet (9D: cn, sk, pu, lpu, l_com, l_sk, mpu, m_com, m_sk). As of this
run, Vop = 0.4-0.7V (8,000 rows) are hand-transcribed; Vop = 0.8V (2,000 rows)
is still blank.

Two independent analyses, run on whatever Vop levels are currently filled:

  A. Raw-data Vop-sufficiency check (no GP, no training). For every condition,
     using ONLY the transcribed Vop levels, checks whether z(Vop) already
     crosses the Z_t=6.50 target within the available range. Conditions that
     already resolve don't need the still-missing Vop level at all; this is
     the direct evidence for whether dropping a Vop level saves simulation
     cost without losing accuracy (same style check as the Stage-4 pilot,
     see docs/decisions -- there it justified dropping Vop=0.9).

  B. GP surrogate fit + hold-out accuracy on the currently available data,
     saved to a metrics JSON keyed by the max transcribed Vop. Re-running
     this script after Vop=0.8 is filled in produces a second JSON, and the
     script diffs the two automatically when both exist.

Usage:  cd python && python scripts/final_snmr_seed2027_analysis.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils import Z_FIXED, VOPS_REAL
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z
from src.data import grouped_train_test_split

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sheet_final_snmr_seed2027.xlsx"
OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "final_snmr_seed2027"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEVICE_COLS = ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]
N_DEVICE = len(DEVICE_COLS)  # 9
VOP_COL = N_DEVICE           # 9

print("=" * 70)
print("Final 9D SNMR batch (seed 2027) -- partial-transcription analysis")
print("=" * 70)

# ============================================================================
# 0. Load + filter to transcribed rows
# ============================================================================
print(f"\n=== 0. Load {DATA_PATH.name} ===")
df = pd.read_excel(DATA_PATH, sheet_name=0)
df.columns = [str(c).strip().lower() for c in df.columns]
n_raw = len(df)

# Numeric coercion + transcription-typo QC (flag, never silently "fix" -- only
# the person who transcribed the sheet can confirm the true value).
malformed_rows = []
for col in ("snmr_avg", "snmr_std", "n_mc"):
    raw = df[col]
    was_present = raw.notna()
    coerced = pd.to_numeric(raw, errors="coerce")
    newly_nan = was_present & coerced.isna()
    for idx in df.index[newly_nan]:
        malformed_rows.append({
            "row_excel": int(idx) + 2,  # +1 header, +1 for 1-indexing
            "deck_no": df.loc[idx, "deck_no"], "deck_id": df.loc[idx, "deck_id"],
            "vop": df.loc[idx, "vop"], "column": col,
            "raw_value": raw.loc[idx],
        })
    df[col] = coerced

if malformed_rows:
    print(f"  [QC] {len(malformed_rows)} cell(s) could not be parsed as numbers "
          "(likely a stray decimal point from manual transcription) -- "
          "EXCLUDED from this run, NOT auto-corrected:")
    for r in malformed_rows:
        print(f"    Excel row {r['row_excel']:6d}  deck_no={r['deck_no']} "
              f"({r['deck_id']})  Vop={r['vop']}  column={r['column']!r}  "
              f"raw value={r['raw_value']!r}")

# --- Gross-magnitude transcription-typo QC (physically-motivated band) -------
# SNMR at this node is ~0-200 mV (avg) and ~9-18 mV (std); values 100-1000x
# outside that are decimal-slip typos (e.g. 157082 -> 157.082, 10074 -> 10.074),
# the same class Stage B/C caught. Flag + EXCLUDE, never auto-correct: only the
# person who transcribed the sheet can confirm the true value.
SNMR_AVG_MIN, SNMR_AVG_MAX = -50.0, 300.0   # mV; generous vs legit max ~200
SNMR_STD_MIN, SNMR_STD_MAX = 3.0, 30.0      # mV; legit ~9-18, 99.9%tile ~17.8
avg = df["snmr_avg"]; std = df["snmr_std"]
outlier_mask = (
    (avg.notna() & ((avg < SNMR_AVG_MIN) | (avg > SNMR_AVG_MAX)))
    | (std.notna() & ((std < SNMR_STD_MIN) | (std > SNMR_STD_MAX)))
)
outlier_rows = []
for idx in df.index[outlier_mask]:
    outlier_rows.append({
        "row_excel": int(idx) + 2, "deck_no": df.loc[idx, "deck_no"],
        "deck_id": df.loc[idx, "deck_id"], "vop": df.loc[idx, "vop"],
        "snmr_avg": float(avg.loc[idx]), "snmr_std": float(std.loc[idx]),
    })
if outlier_rows:
    print(f"\n  [QC] {len(outlier_rows)} row(s) with physically-implausible "
          f"SNMR magnitude (avg not in [{SNMR_AVG_MIN:.0f},{SNMR_AVG_MAX:.0f}]mV "
          f"or std not in [{SNMR_STD_MIN:.0f},{SNMR_STD_MAX:.0f}]mV) -- likely "
          "decimal-slip typos, EXCLUDED from this run, NOT auto-corrected:")
    for r in outlier_rows:
        print(f"    Excel row {r['row_excel']:6d}  deck_no={r['deck_no']} "
              f"({r['deck_id']})  Vop={r['vop']}  "
              f"avg={r['snmr_avg']:.2f}  std={r['snmr_std']:.2f}")
    # NaN them out so they drop from both the sufficiency check and the GP fit
    df.loc[outlier_mask, ["snmr_avg", "snmr_std"]] = np.nan

n_flagged = len(malformed_rows) + len(outlier_rows)
if n_flagged:
    print(f"\n  -> {n_flagged} flagged cell/row(s) total. Please check these "
          "against the source fab results and fix in "
          "sheet_final_snmr_seed2027.xlsx, then re-run this script.")

transcribed = df["snmr_avg"].notna() & df["snmr_std"].notna()
n_done = int(transcribed.sum())
print(f"\n  sheet rows: {n_raw}  transcribed (snmr_avg & snmr_std present, "
      f"parseable, in-range): {n_done}")

vop_counts_all = df["vop"].value_counts().sort_index()
vop_counts_done = df.loc[transcribed, "vop"].value_counts().sort_index()
print("  Vop transcription status:")
for v in sorted(vop_counts_all.index):
    total = int(vop_counts_all[v])
    done = int(vop_counts_done.get(v, 0))
    print(f"    Vop={v:.1f}V: {done:5d}/{total:5d} filled"
          + ("  <-- INCOMPLETE" if done < total else ""))

df_ok = df.loc[transcribed].copy()
avail_vops = np.array(sorted(df_ok["vop"].unique()), dtype=np.float64)
max_vop = float(avail_vops.max())
print(f"\n  Currently usable Vop levels: {list(avail_vops)}  (max={max_vop:.1f}V)")
print(f"  Full production grid is {list(VOPS_REAL)} -- "
      f"{'COMPLETE' if max_vop >= VOPS_REAL.max() - 1e-9 else 'PARTIAL (missing '+str([v for v in VOPS_REAL if v not in avail_vops])+')'}")

n_mc_ok = df_ok["n_mc"].notna()
print(f"  n_mc present for {int(n_mc_ok.sum())}/{len(df_ok)} transcribed rows")

# ============================================================================
# A. Raw-data Vop-sufficiency check (no GP -- direct from transcribed MC stats)
# ============================================================================
print("\n" + "=" * 70)
print("=== A. Raw-data Vop-sufficiency check (no GP) ===")
print("=" * 70)

resolved, needs_more, left_censored = 0, 0, 0
vmin_resolved_mV = []
for cond_key, g in df_ok.groupby(DEVICE_COLS, sort=False):
    g = g.sort_values("vop")
    vops = g["vop"].to_numpy(dtype=np.float64)
    mu = g["snmr_avg"].to_numpy(dtype=np.float64)
    sig = g["snmr_std"].to_numpy(dtype=np.float64)
    z = mu / (sig + 1e-12)
    if z[0] > Z_FIXED:
        left_censored += 1
        continue
    if z[-1] < Z_FIXED:
        needs_more += 1
        continue
    for j in range(len(vops) - 1):
        if z[j] <= Z_FIXED <= z[j + 1]:
            t = (Z_FIXED - z[j]) / (z[j + 1] - z[j] + 1e-12)
            vmin_resolved_mV.append(vops[j] + t * (vops[j + 1] - vops[j]))
            break
    resolved += 1

n_cond = resolved + needs_more + left_censored
print(f"  distinct conditions checked: {n_cond}")
print(f"  [RESOLVED now, Vmin known within {avail_vops.min():.1f}-{max_vop:.1f}V]: "
      f"{resolved:5d}  ({100*resolved/n_cond:.1f}%)")
print(f"  [LEFT-CENSORED, Vmin < {avail_vops.min():.1f}V already]:              "
      f"{left_censored:5d}  ({100*left_censored/n_cond:.1f}%)")
print(f"  [STILL NEEDS a higher Vop than {max_vop:.1f}V to resolve]:            "
      f"{needs_more:5d}  ({100*needs_more/n_cond:.1f}%)")

if vmin_resolved_mV:
    v = np.array(vmin_resolved_mV)
    print(f"\n  Of the resolved conditions, Vmin distribution (V): "
          f"min={v.min():.3f} median={np.median(v):.3f} max={v.max():.3f}")
    near_ceiling = int(np.sum(v > max_vop - 0.02))
    print(f"  Resolved conditions within 20mV of the {max_vop:.1f}V ceiling: "
          f"{near_ceiling} ({100*near_ceiling/len(v):.1f}%) -- these are the ones "
          f"a missing higher Vop level would most plausibly have flipped.")

pct_needs_more = 100 * needs_more / n_cond
print(f"\n  >>> Cost-reduction read: {pct_needs_more:.1f}% of conditions still "
      f"require Vop={max_vop+0.1:.1f}V (or higher) to pin down Vmin at this point.")
if pct_needs_more == 0:
    print("      If this holds once ALL conditions are checked, Vop="
          f"{max_vop+0.1:.1f}V may be droppable entirely for this metric/target -- "
          "mirrors the Stage-4 finding that justified dropping Vop=0.9V.")
else:
    print(f"      Non-zero -- Vop={max_vop+0.1:.1f}V is still informative for at "
          "least some conditions; whether it's worth the simulation cost depends "
          "on whether those conditions are near the corners/tail that matter for "
          "the yield spec (see the GP-based check in Part B).")

with open(OUT_DIR / f"vop_sufficiency_maxVop{max_vop:.1f}.json", "w") as f:
    json.dump({
        "max_transcribed_vop": max_vop,
        "available_vops": list(avail_vops),
        "n_conditions": n_cond,
        "n_resolved": resolved,
        "n_left_censored": left_censored,
        "n_needs_higher_vop": needs_more,
        "pct_needs_higher_vop": pct_needs_more,
    }, f, indent=2)
print(f"\n  saved: {OUT_DIR / f'vop_sufficiency_maxVop{max_vop:.1f}.json'}")

# ============================================================================
# B. GP surrogate fit + hold-out accuracy on currently available data
# ============================================================================
print("\n" + "=" * 70)
print("=== B. GP surrogate fit on currently transcribed data ===")
print("=" * 70)

X = df_ok[DEVICE_COLS + ["vop"]].to_numpy(dtype=np.float64)
y = df_ok[["snmr_avg", "snmr_std"]].to_numpy(dtype=np.float64) * 1e-3  # mV -> V

y_noise = None
if n_mc_ok.all():
    n_mc = np.clip(df_ok["n_mc"].to_numpy(dtype=np.float64), 2, None)
    sigma_v = y[:, 1]
    y_noise = np.column_stack([
        np.maximum(sigma_v / np.sqrt(n_mc), 1e-9),
        np.maximum(sigma_v / np.sqrt(2.0 * n_mc), 1e-9),
    ])
    print("  n_mc present for all rows -> noise-aware GP (FixedNoiseGaussianLikelihood)")
else:
    print("  n_mc missing for some/all rows -> homoscedastic GP (no noise weighting)")

# condition-level grouping key (all 9 device dims; Vop excluded)
_, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
print(f"  distinct conditions: {len(np.unique(cond_idx))}  total rows: {len(X)}")

X_tr, X_te, y_tr, y_te = grouped_train_test_split(X, y, groups=cond_idx, test_frac=0.15, seed=42)
noise_tr = noise_te = None
if y_noise is not None:
    # same (groups, seed) as the X/y split above -> identical train/test rows
    _, _, noise_tr, noise_te = grouped_train_test_split(
        X, y_noise, groups=cond_idx, test_frac=0.15, seed=42)

print(f"  train rows={len(X_tr)}  hold-out rows={len(X_te)}")
print(f"\n  Training mu/sigma GPs (n_device={N_DEVICE}, this may take a while on CPU)...")
surr = Surrogate(device="cpu", n_device=N_DEVICE)
surr.fit(X_tr, y_tr, y_noise=noise_tr, n_iter=150, verbose=True)

mu_pred, _, sigma_pred, _ = surr.predict(X_te)
mu_rmse = float(np.sqrt(np.mean((mu_pred - y_te[:, 0]) ** 2)))
sigma_rmse = float(np.sqrt(np.mean((sigma_pred - y_te[:, 1]) ** 2)))
mu_r2 = float(1 - np.sum((mu_pred - y_te[:, 0]) ** 2) / np.sum((y_te[:, 0] - y_te[:, 0].mean()) ** 2))
sigma_r2 = float(1 - np.sum((sigma_pred - y_te[:, 1]) ** 2) / np.sum((y_te[:, 1] - y_te[:, 1].mean()) ** 2))
print(f"\n  Hold-out: mu RMSE={mu_rmse*1e3:.3f}mV R2={mu_r2:.4f}  "
      f"sigma RMSE={sigma_rmse*1e3:.3f}mV R2={sigma_r2:.4f}")

ls_mu = surr.get_lengthscales("mu")
labels = DEVICE_COLS + ["Vop"]
print("\n  mu lengthscales (standardized-input scale):")
for lbl, v in zip(labels, ls_mu):
    print(f"    ell_{lbl:6s} = {v:.4f}")
ell_cn, ell_pu = float(ls_mu[0]), float(ls_mu[2])
print(f"  ell_pu/ell_cn = {ell_pu/ell_cn:.3f} "
      f"({'PG(cn) more sensitive' if ell_pu > ell_cn else 'PU more sensitive/tied'})")

# Vmin RMSE on hold-out conditions, censoring-aware, using currently-available Vop grid
print("\n  Vmin RMSE on hold-out conditions (GP-predicted vs transcribed, "
      f"censoring-aware, Vop grid={list(avail_vops)}):")
vmin_true, vmin_pred_list, cens_true_list = [], [], []
te_device = X_te[:, :N_DEVICE]
_, te_group = np.unique(te_device, axis=0, return_inverse=True)
for gid in np.unique(te_group):
    mask = te_group == gid
    vops_g = X_te[mask, VOP_COL]
    order = np.argsort(vops_g)
    vops_g = vops_g[order]
    mu_true_g = y_te[mask, 0][order]
    sig_true_g = y_te[mask, 1][order]
    z_true = mu_true_g / (sig_true_g + 1e-12)
    v_true, c_true = compute_vmin_from_z(z_true.reshape(1, -1), z_target=Z_FIXED,
                                          vops=vops_g, return_censored=True)
    mu_pred_g = mu_pred[mask][order]
    sig_pred_g = sigma_pred[mask][order]
    z_pred = mu_pred_g / (sig_pred_g + 1e-12)
    v_pred, c_pred = compute_vmin_from_z(z_pred.reshape(1, -1), z_target=Z_FIXED,
                                          vops=vops_g, return_censored=True)
    vmin_true.append(v_true[0]); cens_true_list.append(bool(c_true[0]))
    vmin_pred_list.append(v_pred[0])

vmin_true = np.array(vmin_true); vmin_pred_arr = np.array(vmin_pred_list)
cens_true = np.array(cens_true_list)
scoreable = ~cens_true & ~np.isnan(vmin_true) & ~np.isnan(vmin_pred_arr)
n_scored = int(scoreable.sum())
if n_scored > 0:
    vmin_rmse_mV = float(np.sqrt(np.mean(
        (vmin_pred_arr[scoreable] - vmin_true[scoreable]) ** 2)) * 1e3)
    print(f"    scored {n_scored}/{len(vmin_true)} hold-out conditions "
          f"(excluded censored/never-cross): Vmin RMSE = {vmin_rmse_mV:.2f} mV")
else:
    vmin_rmse_mV = float("nan")
    print("    no scoreable hold-out conditions (all censored/never-cross at this Vop grid)")

# ============================================================================
# Save metrics for later comparison once Vop=0.8V is filled in
# ============================================================================
metrics = {
    "max_transcribed_vop": max_vop,
    "available_vops": list(avail_vops),
    "n_conditions_total": int(len(np.unique(cond_idx))),
    "n_train_rows": int(len(X_tr)),
    "n_holdout_rows": int(len(X_te)),
    "noise_aware": y_noise is not None,
    "mu_rmse_mV": mu_rmse * 1e3,
    "mu_r2": mu_r2,
    "sigma_rmse_mV": sigma_rmse * 1e3,
    "sigma_r2": sigma_r2,
    "ell_cn": ell_cn, "ell_pu": ell_pu, "ell_pu_over_cn": ell_pu / ell_cn,
    "vmin_rmse_mV_holdout": vmin_rmse_mV,
    "n_holdout_scored": n_scored,
    "n_holdout_conditions": int(len(vmin_true)),
    "vop_sufficiency": {
        "n_resolved": resolved, "n_left_censored": left_censored,
        "n_needs_higher_vop": needs_more, "pct_needs_higher_vop": pct_needs_more,
    },
}
metrics_path = OUT_DIR / f"metrics_maxVop{max_vop:.1f}.json"
with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)
surr.save(OUT_DIR / f"surrogate_maxVop{max_vop:.1f}.pth")
print(f"\n  saved: {metrics_path}")
print(f"  saved: {OUT_DIR / f'surrogate_maxVop{max_vop:.1f}.pth'}")

# ============================================================================
# Compare against a prior run, if one exists (e.g. after Vop=0.8V is filled)
# ============================================================================
print("\n" + "=" * 70)
print("=== Compare vs other available metrics_maxVop*.json runs ===")
print("=" * 70)
other_runs = sorted(OUT_DIR.glob("metrics_maxVop*.json"))
if len(other_runs) <= 1:
    print(f"  Only this run exists so far ({metrics_path.name}). "
          "Re-run this script once Vop=0.8V is transcribed to get a second "
          "file here, and this section will diff them automatically.")
else:
    print(f"  Found {len(other_runs)} runs:")
    rows = []
    for p in other_runs:
        with open(p) as f:
            m = json.load(f)
        rows.append(m)
        print(f"    {p.name}: max_vop={m['max_transcribed_vop']} "
              f"mu_R2={m['mu_r2']:.4f} sigma_R2={m['sigma_r2']:.4f} "
              f"VminRMSE={m['vmin_rmse_mV_holdout']:.2f}mV "
              f"pct_needs_higher_vop={m['vop_sufficiency']['pct_needs_higher_vop']:.1f}%")
    rows.sort(key=lambda m: m["max_transcribed_vop"])
    print("\n  Pairwise deltas (later max_vop vs earlier):")
    for a, b in zip(rows, rows[1:]):
        print(f"    {a['max_transcribed_vop']}V -> {b['max_transcribed_vop']}V:  "
              f"mu_R2 {a['mu_r2']:.4f}->{b['mu_r2']:.4f}  "
              f"VminRMSE {a['vmin_rmse_mV_holdout']:.2f}->{b['vmin_rmse_mV_holdout']:.2f}mV  "
              f"(delta {b['vmin_rmse_mV_holdout']-a['vmin_rmse_mV_holdout']:+.2f}mV)")

print("\n=== Done ===")
