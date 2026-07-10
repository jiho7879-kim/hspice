"""
gen_condition_sheet.py — pre-generate a condition table for hand-entry.

Decision (2026-07-09): the in-house deck (.in) is NOT exportable, so the
user must hand-transcribe conditions too. BUT we generate the Sobol design,
so we already know every condition. Therefore we ship a sheet with the
conditions PRE-FILLED and blank result columns; the user fills only the
measured results (snmr_avg, snmr_std [, n_mc]) next to each row. This cuts
9D-pilot transcription ~3.7x (27,500 -> 7,500 numbers) and removes any
loc/mom precision worry (we set full precision, user never types them).

Transcription precision applied to the pre-filled conditions (so the sheet
matches what the user would see on a deck, and round-trips cleanly):
  cn, pu, skew : integer mV      (rounding Vmin error <= 0.7 mV, negligible)
  loc, mom     : 2 decimals      (0.01 ratio; 0.1 too coarse, 0.001 overkill)

Stages:
  A (3D): cn, pu, Vop                         -> matches hspice_real.xlsx
  B (4D): cn, sk, pu, Vop                     -> adds PG-PD skew (+-20 mV)
  D (9D): cn, sk, pu, lpu,lpg,lpd, mpu,mpg,mpd, Vop  -> full pilot

Result columns (blank, for the user): snmr_avg, snmr_std, n_mc.
Vmin / z-score are computed downstream (parse_manual_xlsx + physics layer).

Usage:
    python scripts/gen_condition_sheet.py --stage A --n_cond 200 -o data/sheet_stageA.xlsx
    python scripts/gen_condition_sheet.py --stage B --n_cond 400 --seed 42
    python scripts/gen_condition_sheet.py --stage D --n_cond 500 --metric snmr
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.utils import (
    VOPS, COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
    sample_common_n_pu,
)

# Vop levels for real data: 5 levels 0.4-0.8 (0.9 dropped -- 0/201 conditions
# cross Vmin in [0.8,0.9] at Z=6.5; see deck_scenarios.md / revised_plan_review).
VOPS_REAL = np.array([0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float64)

SKEW_MIN, SKEW_MAX = -20.0, 20.0        # PG-PD skew, mV (decision 2026-07-09)
LOC_MIN, LOC_MAX = 0.7, 1.3             # VTSL ratio
MOM_MIN, MOM_MAX = 0.7, 1.3             # MOM ratio

# Quadrant weights (SNMR: Q2/FSG focus; Vtrip: Q4/SFG focus) -- deck_scenarios 1.5
QW_SNMR = {(-1, +1): 0.45, (-1, -1): 0.20, (+1, +1): 0.15, (+1, -1): 0.20}
QW_VTRIP = {(-1, +1): 0.10, (-1, -1): 0.15, (+1, +1): 0.30, (+1, -1): 0.45}


def _sobol(n: int, d: int, seed: int) -> np.ndarray:
    from scipy.stats import qmc
    s = qmc.Sobol(d=d, scramble=True, seed=seed)
    m = int(np.ceil(np.log2(max(n, 1))))
    pts = s.random_base2(m=m)
    return pts[:n]


def _quadrant_cnpu(n_total: int, weights: dict, seed: int) -> np.ndarray:
    """(n,2) cn,pu with quadrant weighting; cn/pu signs set by quadrant."""
    out = []
    for i, ((cn_s, pu_s), w) in enumerate(weights.items()):
        n = int(round(n_total * w))
        if n == 0:
            continue
        s = _sobol(n, 2, seed + i)
        cn_lo, cn_hi = (0.0, COMMON_N_MAX) if cn_s > 0 else (COMMON_N_MIN, 0.0)
        pu_lo, pu_hi = (0.0, PU_MAX) if pu_s > 0 else (PU_MIN, 0.0)
        cn = cn_lo + (cn_hi - cn_lo) * s[:, 0]
        pu = pu_lo + (pu_hi - pu_lo) * s[:, 1]
        out.append(np.column_stack([cn, pu]))
    pts = np.vstack(out)
    rng = np.random.default_rng(seed)
    rng.shuffle(pts)
    return pts[:n_total]


def build_conditions(stage: str, n_cond: int, seed: int, metric: str) -> tuple[list[str], np.ndarray]:
    """Return (column_names, conditions array) for the requested stage.

    conditions columns exclude Vop (added per-row in the sheet).
    Precision: cn/pu/sk integer mV, loc/mom 2 decimals.
    """
    if stage == "A":
        cnpu = sample_common_n_pu(n_cond, seed=seed)          # stratified (reuse)
        cn = np.round(cnpu[:, 0]).astype(int)
        pu = np.round(cnpu[:, 1]).astype(int)
        return ["cn", "pu"], np.column_stack([cn, pu]).astype(float)

    if stage == "B":
        weights = QW_SNMR if metric == "snmr" else QW_VTRIP
        cnpu = _quadrant_cnpu(n_cond, weights, seed)
        cn = np.round(cnpu[:, 0]).astype(int)
        pu = np.round(cnpu[:, 1]).astype(int)
        sk = np.round(SKEW_MIN + (SKEW_MAX - SKEW_MIN) * _sobol(n_cond, 1, seed + 99)[:, 0]).astype(int)
        return ["cn", "sk", "pu"], np.column_stack([cn, sk, pu]).astype(float)

    if stage == "D":
        weights = QW_SNMR if metric == "snmr" else QW_VTRIP
        cnpu = _quadrant_cnpu(n_cond, weights, seed)
        cn = np.round(cnpu[:, 0]).astype(int)
        pu = np.round(cnpu[:, 1]).astype(int)
        s = _sobol(n_cond, 7, seed + 7)     # sk, lpu,lpg,lpd, mpu,mpg,mpd
        sk = np.round(SKEW_MIN + (SKEW_MAX - SKEW_MIN) * s[:, 0]).astype(int)
        loc = np.round(LOC_MIN + (LOC_MAX - LOC_MIN) * s[:, 1:4], 2)
        mom = np.round(MOM_MIN + (MOM_MAX - MOM_MIN) * s[:, 4:7], 2)
        cols = ["cn", "sk", "pu", "lpu", "lpg", "lpd", "mpu", "mpg", "mpd"]
        arr = np.column_stack([cn, sk, pu, loc, mom]).astype(float)
        return cols, arr

    raise ValueError(f"unknown stage {stage!r} (use A / B / D)")


def write_sheet(stage: str, n_cond: int, seed: int, metric: str,
                out_path: str | Path, vops: np.ndarray) -> None:
    import pandas as pd

    cond_cols, cond = build_conditions(stage, n_cond, seed, metric)
    n_vop = len(vops)
    rows = []
    row_id = 0
    for i in range(len(cond)):
        for v in vops:
            row_id += 1
            rec = {"row_id": row_id}
            for j, c in enumerate(cond_cols):
                val = cond[i, j]
                # ints stay ints in the sheet (cn/pu/sk); loc/mom keep 2 dec
                rec[c] = int(val) if c in ("cn", "sk", "pu") else round(float(val), 2)
            rec["vop"] = float(v)
            # blank result columns for the user
            rec["snmr_avg"] = ""
            rec["snmr_std"] = ""
            rec["n_mc"] = ""
            rows.append(rec)

    df = pd.DataFrame(rows)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() in (".xlsx", ".xlsm"):
        df.to_excel(out_path, index=False)
    else:
        df.to_csv(out_path, index=False)

    print(f"  stage {stage} [{metric}]: {len(cond)} conditions x {n_vop} Vop "
          f"= {len(rows)} rows")
    print(f"  condition columns (pre-filled): {cond_cols + ['vop']}")
    print(f"  result columns (user fills):    ['snmr_avg', 'snmr_std', 'n_mc']")
    print(f"  precision: cn/pu/sk integer mV, loc/mom 2 decimals")
    print(f"  -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pre-generate hand-entry condition sheet")
    ap.add_argument("--stage", choices=["A", "B", "D"], required=True)
    ap.add_argument("--n_cond", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--metric", choices=["snmr", "vtrip"], default="snmr",
                    help="quadrant weighting target (B/D only)")
    ap.add_argument("--vop6", action="store_true",
                    help="use 6 Vop levels 0.4-0.9 (default: 5 levels 0.4-0.8)")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    vops = VOPS if args.vop6 else VOPS_REAL
    out = args.out or f"data/sheet_stage{args.stage}_{args.metric}.xlsx"
    write_sheet(args.stage, args.n_cond, args.seed, args.metric, out, vops)


if __name__ == "__main__":
    main()
