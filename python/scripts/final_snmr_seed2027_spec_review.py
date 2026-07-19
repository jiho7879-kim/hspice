"""
Spec-aware review: is 0.4-0.7V enough, given the real Vmin spec?

Design context (from the process owner):
  - nominal Vop = 0.75V
  - with on-chip + off-chip IR drop, the Vmin SPEC is:
        T0  (time-zero) : 0.625 V
        EOL (end-of-life): 0.675 V
  - a computed Vmin ABOVE ~0.8V is out of interest: those conditions already
    fail the spec by a wide margin, so their exact Vmin value is irrelevant --
    we only need to know "this fails".

Key geometric fact this exploits:
  Both spec voltages (0.625, 0.675) lie INSIDE [0.6, 0.7]. The pass/fail
  decision at a spec voltage is z(V_spec) >= Z_t, and z(V_spec) is linearly
  interpolated from the raw z-curve using ONLY the 0.6V and 0.7V points.
  => the 0.8V simulations cannot change any spec decision. This script
     demonstrates that quantitatively and then checks that a GP trained on
     0.4-0.7V alone reproduces the spec pass/fail decision.

Decision rule (Vmin = min operating voltage):
  PASS at V_spec  <=>  Vmin <= V_spec  <=>  z(V_spec) >= Z_t
  (z rises with Vop; if margin already meets target at V_spec, the cell works
   at or below the spec supply.)

Usage:  cd python && python scripts/final_snmr_seed2027_spec_review.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.utils import Z_FIXED
from src.surrogate import Surrogate
from src.data import grouped_train_test_split

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sheet_final_snmr_seed2027.xlsx"
OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "final_snmr_seed2027"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEVICE_COLS = ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]
N_DEVICE = len(DEVICE_COLS)
VOPS_FULL = np.array([0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float64)
VOPS_LOW = np.array([0.4, 0.5, 0.6, 0.7], dtype=np.float64)
V_T0, V_EOL = 0.625, 0.675          # Vmin spec voltages
SNMR_AVG_MIN, SNMR_AVG_MAX = -50.0, 300.0
SNMR_STD_MIN, SNMR_STD_MAX = 3.0, 30.0

print("=" * 70)
print("Spec-aware review: 0.4-0.7V sufficiency vs Vmin spec (T0=0.625, EOL=0.675)")
print("=" * 70)


def z_at(vops, zc, v):
    """Linear-interpolate z at voltage v from a z-curve zc on grid vops.
    Returns nan if v is outside [min,max] (never happens for spec V in [0.6,0.7])."""
    vops = np.asarray(vops, float); zc = np.asarray(zc, float)
    if v < vops[0] or v > vops[-1]:
        return np.nan
    j = np.searchsorted(vops, v) - 1
    j = max(0, min(j, len(vops) - 2))
    t = (v - vops[j]) / (vops[j + 1] - vops[j])
    return zc[j] + t * (zc[j + 1] - zc[j])


# ---- load + clean ----------------------------------------------------------
df = pd.read_excel(DATA_PATH, sheet_name=0)
df.columns = [str(c).strip().lower() for c in df.columns]
for c in ("snmr_avg", "snmr_std", "n_mc"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
a, s = df["snmr_avg"], df["snmr_std"]
outlier = (a.notna() & ((a < SNMR_AVG_MIN) | (a > SNMR_AVG_MAX))) | \
          (s.notna() & ((s < SNMR_STD_MIN) | (s > SNMR_STD_MAX)))
df.loc[outlier, ["snmr_avg", "snmr_std"]] = np.nan
df = df[df["snmr_avg"].notna() & df["snmr_std"].notna()].copy()

# ===========================================================================
# A. Raw-data spec decision: does 0.8V change ANY pass/fail at 0.625/0.675V?
# ===========================================================================
print("\n" + "=" * 70)
print("=== A. Raw-data spec pass/fail (no GP): 0.4-0.7V grid vs 0.4-0.8V grid ===")
print("=" * 70)

rows = []
for key, g in df.groupby(DEVICE_COLS, sort=False):
    g = g.sort_values("vop")
    vv = g["vop"].to_numpy(float)
    z = (g["snmr_avg"].to_numpy(float) / (g["snmr_std"].to_numpy(float) + 1e-12))
    zc = {float(v): float(zz) for v, zz in zip(vv, z)}
    # build z-curves on the two grids (need 0.6 & 0.7 present; skip if not)
    if not all(v in zc for v in (0.6, 0.7)):
        continue
    low_v = [v for v in VOPS_LOW if v in zc]
    full_v = [v for v in VOPS_FULL if v in zc]
    z_low = [zc[v] for v in low_v]
    z_full = [zc[v] for v in full_v]
    row = {}
    for grid, gv, gz in (("low", low_v, z_low), ("full", full_v, z_full)):
        row[f"z_t0_{grid}"] = z_at(gv, gz, V_T0)
        row[f"z_eol_{grid}"] = z_at(gv, gz, V_EOL)
    rows.append(row)

R = pd.DataFrame(rows)
n = len(R)
# pass = z(V_spec) >= Z_t
for grid in ("low", "full"):
    R[f"pass_t0_{grid}"] = R[f"z_t0_{grid}"] >= Z_FIXED
    R[f"pass_eol_{grid}"] = R[f"z_eol_{grid}"] >= Z_FIXED

agree_t0 = int((R["pass_t0_low"] == R["pass_t0_full"]).sum())
agree_eol = int((R["pass_eol_low"] == R["pass_eol_full"]).sum())
zmax_diff_t0 = float(np.nanmax(np.abs(R["z_t0_low"] - R["z_t0_full"])))
zmax_diff_eol = float(np.nanmax(np.abs(R["z_eol_low"] - R["z_eol_full"])))

print(f"\n  conditions with 0.6V & 0.7V present: {n}")
print(f"  T0  spec (0.625V): pass/fail identical on both grids for "
      f"{agree_t0}/{n} conditions  (max |z_low - z_full| = {zmax_diff_t0:.2e})")
print(f"  EOL spec (0.675V): pass/fail identical on both grids for "
      f"{agree_eol}/{n} conditions  (max |z_low - z_full| = {zmax_diff_eol:.2e})")
print("  -> as expected: 0.625 & 0.675 interpolate from the 0.6/0.7 points only,")
print("     so the 0.8V simulations are mathematically irrelevant to the spec.")

# population breakdown vs spec (using the full grid, which is authoritative)
pass_t0 = int(R["pass_t0_full"].sum())
pass_eol = int(R["pass_eol_full"].sum())
print(f"\n  Population vs spec (n={n}):")
print(f"    PASS T0  (Vmin <= 0.625V): {pass_t0:5d}  ({100*pass_t0/n:.1f}%)")
print(f"    PASS EOL (Vmin <= 0.675V): {pass_eol:5d}  ({100*pass_eol/n:.1f}%)")
print(f"    FAIL EOL (Vmin >  0.675V): {n-pass_eol:5d}  ({100*(n-pass_eol)/n:.1f}%) "
      f"-- these are 'out of interest'; exact Vmin not needed, only 'fail'.")

# ===========================================================================
# B. GP trained on 0.4-0.7V: reproduce the spec pass/fail on a hold-out?
# ===========================================================================
print("\n" + "=" * 70)
print("=== B. GP trained on 0.4-0.7V ONLY: spec pass/fail vs MC truth (hold-out) ===")
print("=" * 70)

low = df[np.isin(df["vop"], VOPS_LOW)].copy()
X = low[DEVICE_COLS + ["vop"]].to_numpy(float)
y = low[["snmr_avg", "snmr_std"]].to_numpy(float) * 1e-3
n_mc = np.clip(low["n_mc"].to_numpy(float), 2, None)
y_noise = np.column_stack([np.maximum(y[:, 1] / np.sqrt(n_mc), 1e-9),
                           np.maximum(y[:, 1] / np.sqrt(2 * n_mc), 1e-9)])
_, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
Xtr, Xte, ytr, yte = grouped_train_test_split(X, y, groups=cond_idx, test_frac=0.15, seed=42)
_, _, ntr, _ = grouped_train_test_split(X, y_noise, groups=cond_idx, test_frac=0.15, seed=42)
print(f"\n  train rows={len(Xtr)}  hold-out rows={len(Xte)}  (0.4-0.7V only)")
surr = Surrogate(device="cpu", n_device=N_DEVICE)
surr.fit(Xtr, ytr, y_noise=ntr, n_iter=150, verbose=False)

# hold-out condition set -> per condition z-curve on 0.4-0.7V from MC truth & GP
te_dev = Xte[:, :N_DEVICE]
ukeys, te_grp = np.unique(te_dev, axis=0, return_inverse=True)
mu_p, _, sig_p, _ = surr.predict(Xte)

def spec_labels(vops, zc):
    return (z_at(vops, zc, V_T0) >= Z_FIXED, z_at(vops, zc, V_EOL) >= Z_FIXED)

t0_true, t0_pred, eol_true, eol_pred = [], [], [], []
for gid in range(len(ukeys)):
    m = te_grp == gid
    order = np.argsort(Xte[m, N_DEVICE])
    vv = Xte[m, N_DEVICE][order]
    if not all(v in set(np.round(vv, 3)) for v in (0.6, 0.7)):
        continue
    z_true = (yte[m, 0][order] / (yte[m, 1][order] + 1e-12))
    z_pred = (mu_p[m][order] / (sig_p[m][order] + 1e-12))
    a0, a1 = spec_labels(vv, z_true)
    b0, b1 = spec_labels(vv, z_pred)
    t0_true.append(a0); t0_pred.append(b0); eol_true.append(a1); eol_pred.append(b1)

t0_true = np.array(t0_true); t0_pred = np.array(t0_pred)
eol_true = np.array(eol_true); eol_pred = np.array(eol_pred)
nte = len(t0_true)

def report(name, tt, pp):
    agree = int((tt == pp).sum())
    # confusion
    tp = int((tt & pp).sum()); tn = int((~tt & ~pp).sum())
    fp = int((~tt & pp).sum()); fn = int((tt & ~pp).sum())
    print(f"  {name}: agreement {agree}/{nte} ({100*agree/nte:.1f}%)  "
          f"[TP={tp} TN={tn} FP={fp} FN={fn}]  "
          f"(FP=predicted-pass-but-fails, FN=predicted-fail-but-passes)")
    return {"agreement": agree, "n": nte, "tp": tp, "tn": tn, "fp": fp, "fn": fn}

print(f"\n  hold-out conditions scored: {nte}")
r_t0 = report("T0  (0.625V)", t0_true, t0_pred)
r_eol = report("EOL (0.675V)", eol_true, eol_pred)

# margin RMSE at spec voltages (z units) -- how close, not just pass/fail
z_t0_true, z_t0_pred, z_eol_true, z_eol_pred = [], [], [], []
for gid in range(len(ukeys)):
    m = te_grp == gid
    order = np.argsort(Xte[m, N_DEVICE])
    vv = Xte[m, N_DEVICE][order]
    if not all(v in set(np.round(vv, 3)) for v in (0.6, 0.7)):
        continue
    zt = (yte[m, 0][order] / (yte[m, 1][order] + 1e-12))
    zp = (mu_p[m][order] / (sig_p[m][order] + 1e-12))
    z_t0_true.append(z_at(vv, zt, V_T0)); z_t0_pred.append(z_at(vv, zp, V_T0))
    z_eol_true.append(z_at(vv, zt, V_EOL)); z_eol_pred.append(z_at(vv, zp, V_EOL))
z_t0_rmse = float(np.sqrt(np.mean((np.array(z_t0_pred) - np.array(z_t0_true)) ** 2)))
z_eol_rmse = float(np.sqrt(np.mean((np.array(z_eol_pred) - np.array(z_eol_true)) ** 2)))
print(f"\n  z-margin RMSE at spec V (GP vs MC, hold-out): "
      f"T0={z_t0_rmse:.3f}  EOL={z_eol_rmse:.3f}  (Z_t={Z_FIXED})")

verdict = {
    "spec_t0_V": V_T0, "spec_eol_V": V_EOL, "z_target": Z_FIXED,
    "raw_0p8V_changes_spec_decision": {
        "t0_disagreements": n - agree_t0, "eol_disagreements": n - agree_eol,
        "max_abs_z_diff_t0": zmax_diff_t0, "max_abs_z_diff_eol": zmax_diff_eol,
    },
    "population": {"n": n, "pass_t0": pass_t0, "pass_eol": pass_eol,
                   "fail_eol": n - pass_eol},
    "gp_from_0p7V_spec_agreement": {"t0": r_t0, "eol": r_eol,
                                    "z_rmse_t0": z_t0_rmse, "z_rmse_eol": z_eol_rmse},
}
with open(OUT_DIR / "spec_review_0p7V.json", "w") as f:
    json.dump(verdict, f, indent=2)
print(f"\n  saved: {OUT_DIR / 'spec_review_0p7V.json'}")
print("\n=== Done ===")
