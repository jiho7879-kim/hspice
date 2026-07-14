"""
gen_inhouse_condition_sheet.py — Excel 조건표 생성 (inhouse_deck_gen 기반)

inhouse_deck_gen.py의 frozen core를 그대로 사용하여 SNMR/Vtrip 각 metric별
조건표를 Excel로 생성한다. inhouse_deck_gen과 동일한 (stage, n_cond, seed, method)
계약을 사용하므로, fab 측 deck 생성과 조건이 정확히 일치한다.

출력:
  - data/inhouse_condition_snr2026.xlsx  (SNMR 조건표)
  - data/inhouse_condition_vtrip.xlsx  (Vtrip 조건표)

사용법:
    python scripts/gen_inhouse_condition_sheet.py
    python scripts/gen_inhouse_condition_sheet.py --n_cond 200
    python scripts/gen_inhouse_condition_sheet.py --metric snmr --n_cond 500
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.inhouse_deck_gen import (
    generate_conditions,
    STAGE,
    N_COND,
    SEEDS,
    VOPS,
    DECK_PREFIX,
    START,
    METHOD,
    VERSION,
    condition_to_deck_params,
)


def generate_sheet(
    metric: str,
    n_cond: int,
    seed: int,
    out_path: str | Path,
) -> None:
    """metric별 조건표를 Excel로 생성.

    출력 컬럼:
      deck_no, deck_id, vop, <condition columns>,
      VTMSKEW_PG, VTMSKEW_PD, VTMSKEW_PU,
      VTSLSKEW_PG, VTSLSKEW_PD, VTSLSKEW_PU,
      MOMSKEW_PG, MOMSKEW_PD, MOMSKEW_PU
    """
    cols, cond = generate_conditions(STAGE, n_cond, seed, metric, METHOD)

    rows = []
    for vop in VOPS:
        for i in range(len(cond)):
            deck_no = START + i
            deck_id = f"{DECK_PREFIX}-{deck_no}"
            rec = {
                "deck_no": deck_no,
                "deck_id": deck_id,
                "vop": float(vop),
            }
            int_cols = {"cn", "sk", "pu"}
            for j, c in enumerate(cols):
                val = cond[i, j]
                rec[c] = int(val) if c in int_cols else round(float(val), 2)

            # deck parameter 변환값 추가 (condition_to_deck_params)
            deck_params = condition_to_deck_params(rec)
            rec.update(deck_params)

            rows.append(rec)

    df = pd.DataFrame(rows)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(out_path, index=False)

    print(f"  [{metric}] inhouse_deck_gen v{VERSION}")
    print(f"  stage={STAGE} n_cond={n_cond} seed={seed} method={METHOD}")
    print(f"  {len(cond)} conditions x {len(VOPS)} Vop = {len(rows)} rows")
    print(f"  condition columns: {cols + ['vop']}")
    print(f"  deck params: VTMSKEW_*, VTSLSKEW_*, MOMSKEW_*")
    print(f"  precision: cn/pu/sk integer mV, loc/mom 2 decimals")
    print(f"  -> {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="inhouse_deck_gen 기반 Excel 조건표 생성"
    )
    ap.add_argument(
        "--metric",
        choices=["snmr", "vtrip", "both"],
        default="both",
        help="생성할 metric (기본: 둘 다)",
    )
    ap.add_argument(
        "--n_cond",
        type=int,
        default=N_COND,
        help=f"조건 수 (기본: {N_COND})",
    )
    ap.add_argument(
        "--seed_override",
        type=int,
        default=None,
        help="seed 덮어쓰기 (기본: metric별 기본값 snmr=2027, vtrip=2028)",
    )
    ap.add_argument(
        "--out_dir",
        default="data",
        help="출력 폴더 (기본: data/)",
    )
    args = ap.parse_args()

    metrics = (
        ["snmr", "vtrip"] if args.metric == "both" else [args.metric]
    )
    out_dir = Path(args.out_dir)

    print(f"inhouse condition sheet generator (inhouse_deck_gen v{VERSION})")
    for m in metrics:
        seed = (
            args.seed_override
            if args.seed_override is not None
            else SEEDS[m]
        )
        out_path = out_dir / f"inhouse_condition_{m}.xlsx"
        generate_sheet(m, args.n_cond, seed, out_path)
        print()

    print("done.")


if __name__ == "__main__":
    main()
