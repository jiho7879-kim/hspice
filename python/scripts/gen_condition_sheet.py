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

from src.utils import VOPS
from src.condition_gen import (
    generate_conditions, conditions_to_records, CONDITION_GEN_VERSION,
)

# Vop levels for real data: 5 levels 0.4-0.8 (0.9 dropped -- 0/201 conditions
# cross Vmin in [0.8,0.9] at Z=6.5; see deck_scenarios.md / revised_plan_review).
VOPS_REAL = np.array([0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float64)


def write_sheet(stage: str, n_cond: int, seed: int, metric: str,
                out_path: str | Path, vops: np.ndarray, method: str = "rng") -> None:
    """Write a hand-entry sheet: conditions pre-filled, results blank.

    Conditions come from the SHARED, PORTABLE src/condition_gen.py so the
    in-house deck run and this local run produce identical conditions given
    the same (stage, n_cond, seed, metric, method).
    """
    import pandas as pd

    cond_cols, cond = generate_conditions(stage, n_cond, seed, metric, method)
    rows = conditions_to_records(cond_cols, cond, vops)
    for rec in rows:            # blank result columns for the user
        rec["snmr_avg"] = ""
        rec["snmr_std"] = ""
        rec["n_mc"] = ""
    n_vop = len(vops)

    df = pd.DataFrame(rows)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() in (".xlsx", ".xlsm"):
        df.to_excel(out_path, index=False)
    else:
        df.to_csv(out_path, index=False)

    print(f"  stage {stage} [{metric}] method={method} seed={seed} "
          f"(condition_gen v{CONDITION_GEN_VERSION})")
    print(f"  {len(cond)} conditions x {n_vop} Vop = {len(rows)} rows")
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
    ap.add_argument("--method", choices=["rng", "sobol"], default="rng",
                    help="rng=numpy PCG64 (portable, default); sobol=scipy (scipy-pinned)")
    ap.add_argument("--vop6", action="store_true",
                    help="use 6 Vop levels 0.4-0.9 (default: 5 levels 0.4-0.8)")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    vops = VOPS if args.vop6 else VOPS_REAL
    out = args.out or f"data/sheet_stage{args.stage}_{args.metric}.xlsx"
    write_sheet(args.stage, args.n_cond, args.seed, args.metric, out, vops, args.method)


if __name__ == "__main__":
    main()
