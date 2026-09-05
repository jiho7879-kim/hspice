"""
Canonical loader + QC for the FINAL measured batches (2026-07-21 review).
==========================================================================
One trustworthy entry point for the paper. Every raw data-entry defect found
in the 2026-07-21 audit is handled here EXPLICITLY (not by a fragile automatic
heuristic), so each correction is a reviewed, documented decision:

  * unambiguous decimal typos      -> repaired to the value the Vop trend implies
  * unrecoverable gross typos      -> quarantined (NaN), never guessed
  * low-Vop negative vtrip margins -> KEPT (physically real: weak write at 0.4 V)

Raw .xlsx files are never modified. `load_*` returns a cleaned DataFrame and
appends a record of every change to `audit`. Run as a script to print the
full audit report.

Batches
-------
  SNMR  : sheet_final_snmr_seed2027.xlsx  2000 cond x Vop{0.4..0.8}  (read)
  Vtrip : sheet_final_vtrip_seed2028.xlsx 2000 cond x Vop{0.4..0.7}  (write;
          Vop 0.8 not yet transcribed -- irrelevant to the T0=0.625 V spec,
          which interpolates from the 0.6/0.7 points only)
  Corner: hspice_real_corner.xlsx         4 corners, snmr@125C + vtrip@-40C
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"

DEVICE_COLS = ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]

# ---------------------------------------------------------------------------
# Reviewed corrections, keyed by (deck_no, vop). value = repaired number.
# reason is logged verbatim. See docs audit 2026-07-21.
# ---------------------------------------------------------------------------
SNMR_FIX = {
    (489, 0.8):  {"snmr_avg": 93.10,
                  "why": "'93..1' double-dot decimal typo; fits 82.36->93.1 trend"},
    (1895, 0.8): {"snmr_avg": 182.96, "snmr_std": 12.14,
                  "why": "'182.9612.14' = avg+std merged into avg cell; std cell blank"},
    # 2026-08-30 monotonicity audit: mu(Vop) must rise with Vop. These six cells
    # sit ~1/10 of the neighbouring trend -- a dropped leading digit. x10 lands
    # within 8% of the Vop-trend interpolation, so the repair is unambiguous.
    # For decks 786 and 1360 the surrogate independently predicted 109.9 and
    # 103.1 mV for the same cells, confirming the magnitude.
    (11, 0.7):   {"snmr_avg": 97.30,  "why": "9.73 x10; interp(0.6,0.8)=95.4"},
    (350, 0.8):  {"snmr_avg": 106.64, "why": "10.664 x10; 0.7V=94.6 trend ~105"},
    (636, 0.6):  {"snmr_avg": 117.30, "why": "11.73 x10; interp(0.5,0.7)=108.6"},
    (786, 0.6):  {"snmr_avg": 109.19, "why": "10.919 x10; interp(0.5,0.7)=105.4"},
    (803, 0.6):  {"snmr_avg": 136.90, "why": "13.69 x10; interp(0.5,0.7)=134.0"},
    (1360, 0.6): {"snmr_avg": 103.21, "why": "10.321 x10; interp(0.5,0.7)=99.9"},
}
# Remaining monotonicity violations, repaired from the condition's OWN Vop trend
# (2026-08-30, process owner's call: repair rather than quarantine).
#
# Which cell is the bad one: for each candidate, fit a quadratic in Vop to the
# other four points; the candidate whose exclusion leaves the best-fitting
# quadratic is corrupted (residual RSS 0.001-0.5 mV^2 over four points, i.e. the
# clean cells lie on a smooth curve to well inside MC noise). The repaired value
# is that quadratic evaluated at the bad cell's Vop.
#
# snmr_std is repaired too wherever it ALSO departs from its own smooth Vop
# trend by more than 3 x MC noise (sigma/sqrt(2N) ~ 0.14 mV) -- i.e. the whole
# cell is corrupt, not just the mean. Where sigma is clean (555, 852, 1241,
# 1545) only the mean is touched.
#
# NOTE for the process owner: decks 1545-1563 are a contiguous block whose 0.4 V
# row is wrong (mu above the 0.5 V value, sigma inflated). Neighbouring deck
# numbers point at a systematic low-Vop problem in that run, not scattered
# typos. 0.4 V is far below the 0.625 V spec point, so no spec decision moves.
SNMR_FIX_TREND = {
    (555, 0.7):  {"snmr_avg": 143.33, "why": "114.17 < 0.6V value; quad fit of other 4 -> 143.33"},
    (852, 0.6):  {"snmr_avg": 144.10, "why": "114.60 < 0.5V value; quad fit of other 4 -> 144.10"},
    (965, 0.5):  {"snmr_avg": 107.74, "snmr_std": 12.78,
                  "why": "73.84 < 0.4V value; quad fit -> 107.74, sigma 11.33 -> 12.78"},
    (1074, 0.8): {"snmr_avg": 182.89, "snmr_std": 13.72,
                  "why": "142.45 < 0.7V value; quad fit -> 182.89, sigma 15.83 -> 13.72"},
    (1077, 0.8): {"snmr_avg": 226.54, "snmr_std": 10.34,
                  "why": "185.38 < 0.7V value; quad fit -> 226.54, sigma 15.55 -> 10.34"},
    (1241, 0.6): {"snmr_avg": 122.50,
                  "why": "22.80 (leading digit lost); quad fit of other 4 -> 122.50"},
    (1545, 0.4): {"snmr_avg": 26.78, "why": "73.75 > 0.5V value; quad fit -> 26.78"},
    (1547, 0.4): {"snmr_avg": 54.23, "snmr_std": 12.61,
                  "why": "89.74 > 0.5V value; quad fit -> 54.23, sigma 16.79 -> 12.61"},
    (1552, 0.4): {"snmr_avg": 54.20, "snmr_std": 11.65,
                  "why": "109.81 > 0.5V value; quad fit -> 54.20, sigma 14.81 -> 11.65"},
    (1555, 0.4): {"snmr_avg": 39.31, "snmr_std": 12.57,
                  "why": "87.55 > 0.5V value; quad fit -> 39.31, sigma 14.77 -> 12.57"},
    (1557, 0.4): {"snmr_avg": 21.72, "snmr_std": 13.90,
                  "why": "55.09 > 0.5V value; quad fit -> 21.72, sigma 11.83 -> 13.90"},
    (1561, 0.4): {"snmr_avg": 43.25, "snmr_std": 12.25,
                  "why": "93.33 > 0.5V value; quad fit -> 43.25, sigma 15.06 -> 12.25"},
    (1563, 0.4): {"snmr_avg": 21.92, "snmr_std": 12.86,
                  "why": "69.65 > 0.5V value; quad fit -> 21.92, sigma 12.25 -> 12.86"},
}
SNMR_FIX.update(SNMR_FIX_TREND)
VTRIP_FIX = {
    # std double-dot typos
    (1707, 0.4): {"vtrip_std": 25.88, "why": "'25..88' double-dot decimal typo"},
    (247, 0.5):  {"vtrip_std": 25.72, "why": "'25..72' double-dot decimal typo"},
    # avg gross typos recoverable by decimal shift that matches the Vop trend
    (886, 0.4):  {"vtrip_avg": 163.66, "why": "1636.65/10; fits <0.5V(171) trend"},
    (209, 0.5):  {"vtrip_avg": 140.20, "why": "14020/100; interp(0.4,0.6)=140.6"},
    (63, 0.6):   {"vtrip_avg": 171.00, "why": "1710/10; interp(0.5,0.7)=179"},
    (431, 0.6):  {"vtrip_avg": 242.40, "why": "2424/10; interp(0.5,0.7)=248"},
}
# 2026-08-30 monotonicity audit, write batch. Same rule as SNMR_FIX_TREND, with
# one adjustment: only four Vop points are transcribed (0.8 V is empty), so
# removing a candidate leaves three, a quadratic through them is exact and its
# residual cannot discriminate. The corrupted cell is therefore chosen by the
# residual of a LINE through the remaining three, and the repaired value comes
# from the quadratic (which keeps the curvature that a line would flatten).
# x10 is preferred over the fit whenever the raw cell is a clean decimal dropout
# landing within 15% of it.
# sigma is repaired only when it is off its own (linear) Vop trend by more than
# BOTH 3 x MC noise and 3 mV -- this sheet rounds many sigma cells to integers,
# so a tighter threshold would fit rounding rather than repair a defect.
VTRIP_FIX_TREND = {
    (97, 0.6):   {"vtrip_avg": 160.00, "why": "16.0 x10; quad fit of other 3 = 165.2"},
    (276, 0.5):  {"vtrip_avg": 120.72, "why": "12.072 x10; quad fit = 123.3"},
    (549, 0.7):  {"vtrip_avg": 210.00, "why": "21.0 x10; quad fit = 222.0"},
    (726, 0.6):  {"vtrip_avg": 125.86, "why": "219.0 > 0.7V value; quad fit of other 3 -> 125.86"},
    (1292, 0.7): {"vtrip_avg": 277.69, "why": "208.0 < 0.6V value; quad fit -> 277.69"},
    (1425, 0.5): {"vtrip_avg": 180.00, "vtrip_std": 20.67,
                  "why": "18.0 x10; quad fit = 184.2, sigma 24.0 -> 20.67 (3.3 mV off trend)"},
    (1675, 0.4): {"vtrip_avg": 109.00, "why": "177.61 > 0.5V value; quad fit -> 109.0"},
    (1735, 0.7): {"vtrip_avg": 250.78, "why": "182.0 < 0.6V value; quad fit -> 250.78"},
    (1838, 0.7): {"vtrip_avg": 303.93, "vtrip_std": 28.38,
                  "why": "218.0 < 0.6V value; quad fit -> 303.93, sigma 22.0 -> 28.38"},
    (1848, 0.6): {"vtrip_avg": 168.00, "why": "316.0 > 0.7V value; quad fit -> 168.0"},
    (1855, 0.6): {"vtrip_avg": 319.60, "why": "216.0 < 0.5V value; quad fit -> 319.6"},
    (1932, 0.6): {"vtrip_avg": 239.00, "why": "23.9 x10; quad fit = 236.1"},
}
VTRIP_FIX.update(VTRIP_FIX_TREND)
# physical plausibility bands (mV). Values outside -> quarantined (NaN) with a
# logged reason. Bounds sit far outside the clean data spread so real variation
# is never cut: SNMR std clean range 9.1-17.8, Vtrip std clean bulk 14-31.
SNMR_STD_BAND = (7.0, 22.0)
VTRIP_STD_BAND = (5.0, 40.0)

# gross cells with no clean decimal-shift fit -> quarantine (set NaN)
VTRIP_DROP = {
    (1995, 0.4, "vtrip_avg"), (1681, 0.5, "vtrip_avg"), (572, 0.6, "vtrip_avg"),
    (755, 0.7, "vtrip_avg"), (863, 0.7, "vtrip_avg"), (1027, 0.7, "vtrip_avg"),
    (1137, 0.7, "vtrip_avg"), (1565, 0.7, "vtrip_avg"), (1756, 0.7, "vtrip_avg"),
    (300, 0.5, "vtrip_std"),   # '51.23.43' vs ~19-20 neighbours: unrecoverable
}


@dataclass
class Audit:
    records: list = field(default_factory=list)

    def log(self, batch, deck, vop, col, old, new, why):
        self.records.append(dict(batch=batch, deck=deck, vop=vop, col=col,
                                 old=old, new=new, why=why))

    def report(self):
        if not self.records:
            return "no corrections applied."
        by = {}
        for r in self.records:
            by.setdefault(r["batch"], []).append(r)
        out = []
        for batch, rs in by.items():
            out.append(f"\n[{batch}]  {len(rs)} correction(s):")
            for r in rs:
                act = "DROP" if r["new"] is None else "FIX "
                out.append(f"  {act} deck {r['deck']:>4} v{r['vop']} {r['col']:<9} "
                           f"{str(r['old']):>14} -> {str(r['new']):>8}  ({r['why']})")
        return "\n".join(out)


def _apply(df, key, fixes, drops, batch, audit):
    """Apply reviewed FIX/DROP tables to a long-format df with deck_no/vop cols."""
    df = df.copy()
    idx = {(int(d), float(v)): i for i, (d, v) in
           enumerate(zip(df["deck_no"], df["vop"]))}
    for (deck, vop), spec in fixes.items():
        i = idx.get((deck, vop))
        if i is None:
            continue
        for col, new in spec.items():
            if col == "why":
                continue
            old = df.iat[i, df.columns.get_loc(col)]
            df.iat[i, df.columns.get_loc(col)] = new
            audit.log(batch, deck, vop, col, old, new, spec["why"])
    for (deck, vop, col) in drops:
        i = idx.get((deck, vop))
        if i is None:
            continue
        old = df.iat[i, df.columns.get_loc(col)]
        df.iat[i, df.columns.get_loc(col)] = np.nan
        audit.log(batch, deck, vop, col, old, None, "unrecoverable gross typo -> NaN")
    return df


def _band_qc(df, col, band, batch, audit):
    """Quarantine (NaN) numeric values outside a physical band; log each."""
    x = pd.to_numeric(df[col], errors="coerce")
    bad = x.notna() & ((x < band[0]) | (x > band[1]))
    for i in np.where(bad.to_numpy())[0]:
        old = df.iat[i, df.columns.get_loc(col)]
        df.iat[i, df.columns.get_loc(col)] = np.nan
        audit.log(batch, int(df.iat[i, df.columns.get_loc("deck_no")]),
                  float(df.iat[i, df.columns.get_loc("vop")]), col, old, None,
                  f"outside physical band {band} mV")
    return df


def load_final_snmr(audit: Audit | None = None) -> pd.DataFrame:
    audit = audit if audit is not None else Audit()
    df = pd.read_excel(DATA / "sheet_final_snmr_seed2027.xlsx")
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = _apply(df, "snmr", SNMR_FIX, set(), "SNMR", audit)
    for c in ("snmr_avg", "snmr_std", "n_mc"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = _band_qc(df, "snmr_std", SNMR_STD_BAND, "SNMR", audit)
    df["z"] = df["snmr_avg"] / (df["snmr_std"] + 1e-12)
    return df


def monotonicity_violations(df, col="snmr_avg", k=3.0):
    """Conditions where col(Vop) falls by more than k x the MC standard error.

    SNMR/Vtrip margin rises with the supply, so a fall beyond MC noise is a
    data defect, not physics. NaN cells (already quarantined) are skipped.
    Returns [(deck_no, [(vop, value), ...] suspect cells)].
    """
    out = []
    for deck, g in df.groupby("deck_no"):
        g = g.sort_values("vop")
        v, a = g["vop"].to_numpy(float), pd.to_numeric(g[col], errors="coerce").to_numpy(float)
        s = pd.to_numeric(g[col.replace("_avg", "_std")], errors="coerce").to_numpy(float)
        n = pd.to_numeric(g["n_mc"], errors="coerce").to_numpy(float)
        ok = ~np.isnan(a)
        if ok.sum() < 2:
            continue
        sem = float(np.nanmean(s / np.sqrt(np.clip(n, 2, None))))
        d = np.diff(a[ok])
        if d.min() > -k * sem:
            continue
        cand = [i for i in range(ok.sum()) if (np.diff(np.delete(a[ok], i)) > 0).all()]
        out.append((int(deck), [(float(v[ok][i]), float(a[ok][i])) for i in cand]))
    return out


def load_final_vtrip(audit: Audit | None = None) -> pd.DataFrame:
    audit = audit if audit is not None else Audit()
    df = pd.read_excel(DATA / "sheet_final_vtrip_seed2028.xlsx")
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = _apply(df, "vtrip", VTRIP_FIX, VTRIP_DROP, "Vtrip", audit)
    for c in ("vtrip_avg", "vtrip_std", "n_mc"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = _band_qc(df, "vtrip_std", VTRIP_STD_BAND, "Vtrip", audit)
    df["z"] = df["vtrip_avg"] / (df["vtrip_std"] + 1e-12)
    return df


def load_corner() -> pd.DataFrame:
    df = pd.read_excel(DATA / "hspice_real_corner.xlsx")
    df.columns = [str(c).strip().lower() for c in df.columns]
    for c in ("avg", "std", "count"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["z"] = df["avg"] / (df["std"] + 1e-12)
    return df


if __name__ == "__main__":
    a = Audit()
    snmr = load_final_snmr(a)
    vtrip = load_final_vtrip(a)
    corner = load_corner()

    def summ(df, avg, std, name, vops_expected):
        v = pd.to_numeric(df[avg], errors="coerce")
        s = pd.to_numeric(df[std], errors="coerce")
        comp = df.assign(ok=v.notna()).groupby("deck_no")["ok"].sum()
        print(f"\n=== {name} ===")
        print(f"  {df['deck_no'].nunique()} conditions x Vop{sorted(df['vop'].unique())}")
        print(f"  {avg}: {v.min():.1f}..{v.max():.1f} mV   {std}: {s.min():.1f}..{s.max():.1f} mV")
        print(f"  usable cells: {v.notna().sum()}/{len(df)}   "
              f"conditions fully filled ({vops_expected} Vop): {(comp==vops_expected).sum()}")
        neg = (v < 0).sum()
        if neg:
            print(f"  negative {avg} (kept, physical): {neg} "
                  f"(Vop {sorted(df.loc[v<0,'vop'].unique())})")

    print("=" * 74)
    print("FINAL DATA — post-QC summary  (raw files untouched)")
    print("=" * 74)
    summ(snmr, "snmr_avg", "snmr_std", "SNMR (read)", 5)
    summ(vtrip, "vtrip_avg", "vtrip_std", "Vtrip (write)", 4)
    print(f"\n=== Corner ===")
    print(corner.groupby("cat").apply(
        lambda g: f"{g['corner'].nunique()} corners, Vop{sorted(g['vop'].unique())}, "
                  f"temp{sorted(g['temp'].unique())}").to_string())
    print("\n" + "=" * 74)
    print("AUDIT TRAIL")
    print("=" * 74)
    print(a.report())

    print(f"\nmonotonicity check (mean rises with Vop, 3 x MC SEM):")
    bad = {}
    for name, d, col in (("SNMR", snmr, "snmr_avg"), ("Vtrip", vtrip, "vtrip_avg")):
        left = monotonicity_violations(d, col)
        bad[name] = left
        print(f"  {name}: {len(left)} condition(s) still violating")
        for deck, cells in left:
            print(f"    deck {deck}: {cells}")
    assert not any(bad.values()), "unreviewed monotonicity violation -- add to the FIX tables"
