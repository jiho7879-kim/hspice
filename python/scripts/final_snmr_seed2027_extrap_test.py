"""
Decisive cost test: can a surrogate trained on 0.4-0.7V ALONE reproduce the
Vmin that only the (expensive) 0.8V simulations pin down?

The 0.7V-vs-0.8V metric comparison in final_snmr_seed2027_analysis.py is
apples-to-oranges: the two runs score Vmin on different Vop grids, so more
hard high-Vmin conditions become scoreable at 0.8V and nudge the average RMSE.
This script removes that ambiguity with a single held-fixed truth:

  truth      = Vmin from the FULL transcribed 0.4-0.8V MC z-curve (per condition)
  surrogate  = GP trained on 0.4-0.7V ONLY, then asked to predict (mu,sigma) at
               ALL five Vop incl. 0.8V (extrapolation) -> GP Vmin on 0.4-0.8 grid

If GP-from-0.7V Vmin matches the 0.8V-included MC truth -- especially on the
conditions that 0.4-0.7V raw data left UNRESOLVED -- then the 0.8V simulations
were redundant *for the surrogate* and can be dropped (a ~20% cost cut for this
metric). If it misses them, 0.8V carries genuine information the model cannot
extrapolate.

Usage:  cd python && python scripts/final_snmr_seed2027_extrap_test.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.utils import Z_FIXED
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z
from src.data import grouped_train_test_split

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sheet_final_snmr_seed2027.xlsx"
OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "final_snmr_seed2027"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEVICE_COLS = ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]
N_DEVICE = len(DEVICE_COLS)
VOPS_FULL = np.array([0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float64)
VOPS_LOW = np.array([0.4, 0.5, 0.6, 0.7], dtype=np.float64)
SNMR_AVG_MIN, SNMR_AVG_MAX = -50.0, 300.0
SNMR_STD_MIN, SNMR_STD_MAX = 3.0, 30.0

print("=" * 70)
print("Decisive cost test: 0.4-0.7V-trained surrogate vs 0.8V-included truth")
print("=" * 70)

# ---- load + clean (same QC as the main script) ----------------------------
df = pd.read_excel(DATA_PATH, sheet_name=0)
df.columns = [str(c).strip().lower() for c in df.columns]
for c in ("snmr_avg", "snmr_std", "n_mc"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
a, s = df["snmr_avg"], df["snmr_std"]
outlier = (a.notna() & ((a < SNMR_AVG_MIN) | (a > SNMR_AVG_MAX))) | \
          (s.notna() & ((s < SNMR_STD_MIN) | (s > SNMR_STD_MAX)))
df.loc[outlier, ["snmr_avg", "snmr_std"]] = np.nan
df = df[df["snmr_avg"].notna() & df["snmr_std"].notna()].copy()


def vmin_from_rows(sub, vops):
    """Vmin (V) + censored flag from one condition's transcribed rows at `vops`."""
    sub = sub[np.isin(sub["vop"], vops)].sort_values("vop")
    if len(sub) < 2:
        return np.nan, False, False  # not enough levels
    vv = sub["vop"].to_numpy(float)
    mu = sub["snmr_avg"].to_numpy(float) * 1e-3
    sg = sub["snmr_std"].to_numpy(float) * 1e-3
    z = mu / (sg + 1e-12)
    v, c = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, vops=vv, return_censored=True)
    never = bool(np.isnan(v[0]) and not c[0])
    return v[0], bool(c[0]), never


# ---- per-condition MC truth (full 0.4-0.8) and low-only (0.4-0.7) ----------
groups = df.groupby(DEVICE_COLS, sort=False)
cond_keys, vmin_full, cens_full, vmin_low, cens_low, never_low = [], [], [], [], [], []
for key, g in groups:
    vf, cf, nf = vmin_from_rows(g, VOPS_FULL)
    vl, cl, nl = vmin_from_rows(g, VOPS_LOW)
    cond_keys.append(key)
    vmin_full.append(vf); cens_full.append(cf)
    vmin_low.append(vl); cens_low.append(cl); never_low.append(nl)
vmin_full = np.array(vmin_full); cens_full = np.array(cens_full)
vmin_low = np.array(vmin_low); never_low = np.array(never_low)
n_cond = len(cond_keys)

# "conditions the 0.8V level newly resolved": unresolved from 0.4-0.7V raw data
# (never crossed within 0.7V) but resolved once 0.8V is included.
newly_resolved = never_low & np.isfinite(vmin_full) & ~cens_full
print(f"\n  conditions: {n_cond}")
print(f"  newly resolved BY the 0.8V level (never-cross <=0.7V -> finite Vmin <=0.8V): "
      f"{int(newly_resolved.sum())}")

# ---- train surrogate on 0.4-0.7V ONLY --------------------------------------
low = df[np.isin(df["vop"], VOPS_LOW)].copy()
X = low[DEVICE_COLS + ["vop"]].to_numpy(float)
y = low[["snmr_avg", "snmr_std"]].to_numpy(float) * 1e-3
n_mc = np.clip(low["n_mc"].to_numpy(float), 2, None)
y_noise = np.column_stack([np.maximum(y[:, 1] / np.sqrt(n_mc), 1e-9),
                           np.maximum(y[:, 1] / np.sqrt(2 * n_mc), 1e-9)])
print(f"\n  training surrogate on 0.4-0.7V only ({len(X)} rows, {n_cond} conditions)...")
surr = Surrogate(device="cpu", n_device=N_DEVICE)
surr.fit(X, y, y_noise=y_noise, n_iter=150, verbose=False)
print("  done.")

# ---- GP-predicted Vmin over the FULL 0.4-0.8 grid (0.8 is extrapolation) ----
key_arr = np.array(cond_keys, dtype=float)  # (n_cond, 9)
nvf = len(VOPS_FULL)
Xg = np.repeat(key_arr, nvf, axis=0)
Xg = np.column_stack([Xg, np.tile(VOPS_FULL, n_cond)])
mu_g, _, sig_g, _ = surr.predict(Xg)
z_g = (mu_g / (sig_g + 1e-12)).reshape(n_cond, nvf)
vmin_gp_full, cens_gp_full = compute_vmin_from_z(
    z_g, z_target=Z_FIXED, vops=VOPS_FULL, return_censored=True)


def rmse_mV(pred, truth, mask):
    m = mask & np.isfinite(pred) & np.isfinite(truth)
    if not m.any():
        return float("nan"), 0
    return float(np.sqrt(np.mean((pred[m] - truth[m]) ** 2)) * 1e3), int(m.sum())


# ---- headline: does the 0.7V-trained GP reproduce the 0.8V-included truth? --
print("\n" + "=" * 70)
print("=== Can the 0.4-0.7V surrogate reproduce 0.8V-included Vmin truth? ===")
print("=" * 70)

all_scoreable = np.isfinite(vmin_full) & ~cens_full
r_all, n_all = rmse_mV(vmin_gp_full, vmin_full, all_scoreable)
print(f"\n  ALL resolved conditions (n={n_all}): "
      f"GP(trained 0.4-0.7V) Vmin vs full-0.8V MC truth  RMSE = {r_all:.2f} mV")

r_new, n_new = rmse_mV(vmin_gp_full, vmin_full, newly_resolved)
print(f"  ONLY the {int(newly_resolved.sum())} conditions the 0.8V sims newly "
      f"resolved (n_scored={n_new}):")
print(f"      GP(trained 0.4-0.7V, extrapolated to 0.8V) vs MC truth  "
      f"RMSE = {r_new:.2f} mV")

# how many of the newly-resolved does the GP also resolve (not censor/never)?
gp_resolves_new = newly_resolved & np.isfinite(vmin_gp_full) & ~cens_gp_full
print(f"      of those {int(newly_resolved.sum())}, GP also returns a finite Vmin "
      f"for {int(gp_resolves_new.sum())}")

# reference: GP error on the conditions already resolved by 0.4-0.7V raw data
already = all_scoreable & ~newly_resolved
r_old, n_old = rmse_mV(vmin_gp_full, vmin_full, already)
print(f"\n  reference -- conditions already resolved by 0.4-0.7V raw (n={n_old}): "
      f"RMSE = {r_old:.2f} mV")

verdict = {
    "n_conditions": n_cond,
    "n_newly_resolved_by_0p8V": int(newly_resolved.sum()),
    "gp_from_0p7V_rmse_mV_all_resolved": r_all,
    "gp_from_0p7V_rmse_mV_newly_resolved": r_new,
    "gp_from_0p7V_rmse_mV_already_resolved": r_old,
    "n_newly_resolved_gp_also_finite": int(gp_resolves_new.sum()),
}
with open(OUT_DIR / "extrap_test_0p7_vs_0p8.json", "w") as f:
    json.dump(verdict, f, indent=2)
print(f"\n  saved: {OUT_DIR / 'extrap_test_0p7_vs_0p8.json'}")

print("\n  Interpretation:")
print("    - If RMSE on the newly-resolved set is close to the already-resolved")
print("      reference, the 0.4-0.7V surrogate ALREADY predicts the 0.8V tail ->")
print("      the 0.8V simulations are largely redundant for the surrogate")
print("      (~20% budget cut for this metric).")
print("    - If it is much larger, 0.8V carries information the model cannot")
print("      extrapolate and should be kept.")
print("\n=== Done ===")
