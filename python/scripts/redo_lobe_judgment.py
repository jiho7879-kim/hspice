"""
Redo the SNMR tail LOBE judgment from the in-fab summary table.

The fab could not export raw MC samples, so instead of running
infab_snmr_tail_diag.py on raw dumps, they typed the per-condition summary
statistics into python/data/infab_snmr_tail.xlsx. This script reproduces the
SAME decision the diagnostic script would have made, straight from that table:

  1. gauss_chi2  = sum_k ((qz_emp_k - qz_gaus_k) / qz_se_k)^2     over the ladder
  2. best MIN2 rho = argmin over the provided chi2_rho_* columns
  3. gauss_ok  = gauss_chi2 < 3*dof            (script's rule, dof=5)
  4. verdict / zbias via bias_at_target(best_rho)   (imported from the script)

It then compares the recomputed verdict against the values the fab typed in,
and prints a clean summary table.
"""
import os
import sys

import numpy as np
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from infab_snmr_tail_diag import bias_at_target  # noqa: E402

XLSX = os.path.join(HERE, "..", "data", "infab_snmr_tail.xlsx")
Z_TARGET = 6.50
DOF = 5

# rho -> zbias, recomputed once (matches the script's Monte-Carlo estimator)
RNG = np.random.default_rng(12345)
RHO_GRID = [-0.50, -0.25, 0.00, 0.25]
ZBIAS = {}
for r in RHO_GRID:
    _zt, _b = bias_at_target(r, Z_TARGET, RNG)
    ZBIAS[r] = (_zt, _b)

wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb["Sheet1"]
rows = list(ws.iter_rows(values_only=True))
hdr = rows[0]
col = {name: i for i, name in enumerate(hdr)}

LADDER = ["p50", "p15.9", "p2.28", "p0.135", "p0.02"]
RHO_COLS = {-0.50: "chi2_rho_-0.50", -0.25: "chi2_rho_-0.25",
            0.00: "chi2_rho_0.00", 0.25: "chi2_rho_0.25"}

print(f"{'deck':>5} {'vop':>4} | {'gauss_chi2':>10} | "
      f"{'best_rho':>8} {'chi2':>7} | {'zbias':>6} {'verdict':<14} | fab_zbias fab_dist")
print("-" * 92)

out = []
for r in rows[1:]:
    deck = r[col["deck"]]
    vop = r[col["vop"]]
    emp = [r[col[f"qz_emp_{k}"]] for k in LADDER]
    gau = [r[col[f"qz_gaus_{k}"]] for k in LADDER]
    se = [r[col[f"qz_se_{k}"]] for k in LADDER]

    gauss_chi2 = sum(((a - b) / s) ** 2 for a, b, s in zip(emp, gau, se))

    chis = {rho: r[col[cname]] for rho, cname in RHO_COLS.items()}
    best_rho = min(chis, key=lambda k: chis[k])
    best_chi2 = chis[best_rho]

    gauss_ok = gauss_chi2 < 3.0 * DOF
    if gauss_ok:
        verdict = "GAUSS-CONSIST"
        z_true, zbias = Z_TARGET, 0.0
    else:
        verdict = "NON-GAUSSIAN"
        z_true, zbias = ZBIAS[best_rho]

    fab_zbias = r[col["zbias"]]
    fab_dist = r[col["distribution"]]
    match = "OK" if (round(zbias, 2) == round(fab_zbias, 2)) else "**MISMATCH**"

    print(f"{deck:>5} {vop:>4} | {gauss_chi2:>10.1f} | "
          f"{best_rho:>+8.2f} {best_chi2:>7.1f} | {zbias:>+6.3f} {verdict:<14} | "
          f"{fab_zbias:>+8.3f} {fab_dist:<12} {match}")
    out.append((deck, vop, gauss_chi2, best_rho, best_chi2, z_true, zbias))

print("-" * 92)
print("\nzbias(rho) reference (recomputed):")
for r in RHO_GRID:
    zt, b = ZBIAS[r]
    print(f"  rho={r:+.2f}: z_true@6.5={zt:.3f}  zbias={b:+.3f}")

# aggregate
zb = [o[6] for o in out]
print(f"\nAll {len(out)} SNMR conditions: NON-GAUSSIAN.")
print(f"zbias range: {min(zb):+.3f} .. {max(zb):+.3f} sigma  (median {np.median(zb):+.3f})")
dzdv = 13.2
print(f"Vmin optimism = zbias / (dz/dVop={dzdv}/V):")
print(f"  median  {np.median(zb):+.3f}s -> {1000*np.median(zb)/dzdv:5.1f} mV")
print(f"  min     {min(zb):+.3f}s -> {1000*min(zb)/dzdv:5.1f} mV")
print(f"  max     {max(zb):+.3f}s -> {1000*max(zb)/dzdv:5.1f} mV")
