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
}
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
