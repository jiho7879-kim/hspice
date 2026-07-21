"""
Post-process the SNMR spec pass-rate under the tail (lobe) correction.

No re-simulation. The lobe diagnostic (redo_lobe_judgment.py) established that
the SNMR minimum is min-of-two-lobes, so the naive Gaussian z overstates margin.
The fix is a pure re-threshold: a condition passes at V_spec iff

        z_naive(V_spec) >= Z_t + zbias

instead of z_naive(V_spec) >= Z_t. This mirrors final_snmr_seed2027_spec_review.py
exactly (z-curve = snmr_avg/snmr_std, spec voltages interpolated from 0.6/0.7).
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data" / "sheet_final_snmr_seed2027.xlsx"
DEVICE_COLS = ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]
V_T0, V_EOL = 0.625, 0.675
Z_BASE = 6.50
SNMR_AVG_MIN, SNMR_AVG_MAX = -50.0, 300.0
SNMR_STD_MIN, SNMR_STD_MAX = 3.0, 30.0
ZBIAS_TYP = 0.945   # rho=-0.25, 8/9 conditions
ZBIAS_FSG = 1.233   # rho=-0.50, worst read corner (deck 458)


def z_at(vops, zc, v):
    vops = np.asarray(vops, float); zc = np.asarray(zc, float)
    j = max(0, min(np.searchsorted(vops, v) - 1, len(vops) - 2))
    t = (v - vops[j]) / (vops[j + 1] - vops[j])
    return zc[j] + t * (zc[j + 1] - zc[j])


df = pd.read_excel(DATA, sheet_name=0)
df.columns = [str(c).strip().lower() for c in df.columns]
for c in ("snmr_avg", "snmr_std"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
a, s = df["snmr_avg"], df["snmr_std"]
outlier = ((a < SNMR_AVG_MIN) | (a > SNMR_AVG_MAX) |
           (s < SNMR_STD_MIN) | (s > SNMR_STD_MAX))
df.loc[outlier, ["snmr_avg", "snmr_std"]] = np.nan
df = df[df["snmr_avg"].notna() & df["snmr_std"].notna()].copy()

z_t0, z_eol = [], []
for _, g in df.groupby(DEVICE_COLS, sort=False):
    g = g.sort_values("vop")
    zc = {float(v): float(av / (sd + 1e-12))
          for v, av, sd in zip(g["vop"], g["snmr_avg"], g["snmr_std"])}
    if not all(v in zc for v in (0.6, 0.7)):
        continue
    gv = sorted(zc)
    gz = [zc[v] for v in gv]
    z_t0.append(z_at(gv, gz, V_T0))
    z_eol.append(z_at(gv, gz, V_EOL))
z_t0 = np.array(z_t0); z_eol = np.array(z_eol)
n = len(z_t0)


def rates(zt):
    return (z_t0 >= zt).sum(), (z_eol >= zt).sum()


print(f"n conditions = {n}\n")
print(f"{'Z_t':>6} {'zbias':>6} | {'pass_T0':>10} | {'pass_EOL':>12} | {'fail_EOL':>10}")
print("-" * 58)
for label, zb in [("base", 0.0), ("typ", ZBIAS_TYP), ("FSG-worst", ZBIAS_FSG)]:
    zt = Z_BASE + zb
    pt0, peol = rates(zt)
    print(f"{zt:>6.3f} {zb:>+6.3f} | {pt0:5d} {100*pt0/n:4.1f}% | "
          f"{peol:5d} {100*peol/n:5.1f}% | {n-peol:5d} {100*(n-peol)/n:4.1f}%  [{label}]")

pt0_b, peol_b = rates(Z_BASE)
pt0_t, peol_t = rates(Z_BASE + ZBIAS_TYP)
print(f"\nEOL pass rate: {100*peol_b/n:.1f}% (uncorrected) -> "
      f"{100*peol_t/n:.1f}% (tail-corrected, +{ZBIAS_TYP:.2f} sigma)")
print(f"Newly-failing conditions: {peol_b - peol_t}  "
      f"({100*(peol_b-peol_t)/n:.1f} pp of the population)")
