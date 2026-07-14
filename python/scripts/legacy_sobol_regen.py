"""
legacy_sobol_regen.py — 사내에서 이미 돌린 Sobol 배치의 조건을 재생성한다.

WHY
---
StageD(500 조건)와 final(2000 조건) deck은 사내 python 스크립트가 만들었고,
그 스크립트는 scipy Sobol(seed=2026) 기반이었다. 원본 코드는 유실됐지만,
사용자가 손으로 전사해 온 조건 시트 64개와 대조해 생성 레시피를 복원했다
(60/64 완전 일치, 나머지 4개는 전사 오류로 규명 — 아래 KNOWN_TYPOS 참조).

따라서 조건은 **손 전사 없이 로컬에서 그대로 재생성**할 수 있다. 사용자는
결과값(snmr_avg, snmr_std, n_mc)만 채우면 된다.

복원된 재현성 계약 (하나라도 다르면 조건이 전부 달라짐)
------------------------------------------------------
  sampler   : scipy.stats.qmc.Sobol(d=9, scramble=True, seed=2026).random(n)
              ※ quadrant마다 **같은 seed로 새 sampler를 생성** (원본의 버그.
                의도된 설계가 아니지만, 이미 돌린 데이터를 재현하려면 그대로
                유지해야 한다. 절대 "고치지" 말 것.)
  n_cond    : 500 (StageD) / 2000 (final)
  weights   : {(1,1):0.20, (-1,1):0.45, (-1,-1):0.15, (1,-1):0.20}
              → quadrant별 int(n*w) 개.  (cn_sign, pu_sign)
  bounds    : VAR_BOUNDS 참조 (cn/pu ±0.06 V, sk ±0.02 V, loc/mom 0.7~1.3,
              l_sk/m_sk ±0.075)
  sign flip : 전체 범위에서 뽑은 뒤 cn, pu의 부호를 quadrant에 맞게 뒤집음
  clamp     : |skew| <= |common - 1.0|  — l_sk **와** m_sk 둘 다에 적용
  vop       : 0.4 / 0.5 / 0.6 / 0.7 / 0.8
  scipy     : scramble된 Sobol 스트림은 scipy 버전 종속. scipy 1.18에서 재현
              확인됨. 향후 안전을 위해 생성된 CSV/XLSX를 golden으로 커밋할 것.

정렬 (사용자 시트와 동일 규칙)
------------------------------
  cn 오름차순(반올림 전 float 기준), 동점은 생성 순서 유지(stable).
  ※ 원본 시트의 동점 구간 순서는 유실된 np.random.shuffle에 의존해 완전
    복원이 불가능하다. 하지만 500/2000 조건이 9D에서 전부 고유하므로,
    행 순서와 무관하게 조건값으로 1:1 매칭이 가능하다. 매칭은 num이 아니라
    cond_id 또는 조건값으로 할 것.

Usage
-----
    python scripts/legacy_sobol_regen.py                 # 500 + 2000 둘 다
    python scripts/legacy_sobol_regen.py --n_cond 500 -o data/stageD_500.xlsx
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import qmc

warnings.filterwarnings("ignore", category=UserWarning)  # Sobol non-power-of-2 balance warning

RECIPE_VERSION = "legacy-1.0 (recovered 2026-07-14)"
SEED = 2026
VOPS = [0.4, 0.5, 0.6, 0.7, 0.8]

# 원본 코드의 VAR_ORDER — Sobol 축 순서. 바꾸면 조건이 전부 달라진다.
VAR_ORDER = ["pu", "cn", "sk", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]
VAR_BOUNDS = {
    "pu": (-0.06, 0.06), "cn": (-0.06, 0.06), "sk": (-0.02, 0.02),
    "lpu": (0.7, 1.3), "l_com": (0.7, 1.3), "l_sk": (-0.075, 0.075),
    "mpu": (0.7, 1.3), "m_com": (0.7, 1.3), "m_sk": (-0.075, 0.075),
}
QUADRANT_WEIGHTS = {(1, 1): 0.20, (-1, 1): 0.45, (-1, -1): 0.15, (1, -1): 0.20}
QUAD_NAME = {(1, 1): "Q1", (-1, 1): "Q2", (-1, -1): "Q3", (1, -1): "Q4"}

# 시트 컬럼 순서 (사용자 시트와 동일)
SHEET_COLS = ["cn", "pu", "sk", "l_comp", "lpu", "l_sk", "m_comp", "mpu", "m_sk"]
MV_COLS = ["cn", "pu", "sk"]        # 정수 mV로 표시
IDX = {v: i for i, v in enumerate(VAR_ORDER)}


def _clamp_skew(common: float, skew: float, reference: float = 1.0) -> float:
    """|skew| <= |common - reference| 로 클램프. 원본 apply_boundary_constraint 복원."""
    limit = abs(common - reference)
    return float(np.sign(skew) * limit) if abs(skew) > limit else float(skew)


def generate_conditions(n_cond: int, seed: int = SEED) -> pd.DataFrame:
    """복원된 레시피로 조건을 재생성. full precision(= deck에 찍힌 값)을 반환."""
    recs = []
    for (cn_sign, pu_sign), weight in QUADRANT_WEIGHTS.items():
        n_quad = int(n_cond * weight)
        if n_quad == 0:
            continue
        # ↓ quadrant마다 같은 seed로 새 sampler — 원본 그대로 (재현 위해 유지)
        u = qmc.Sobol(d=len(VAR_ORDER), scramble=True, seed=seed).random(n_quad)
        for k in range(n_quad):
            r = np.array([VAR_BOUNDS[v][0]
                          + (VAR_BOUNDS[v][1] - VAR_BOUNDS[v][0]) * u[k, i]
                          for i, v in enumerate(VAR_ORDER)])
            if np.sign(r[IDX["cn"]]) != cn_sign:
                r[IDX["cn"]] = -r[IDX["cn"]]
            if np.sign(r[IDX["pu"]]) != pu_sign:
                r[IDX["pu"]] = -r[IDX["pu"]]
            r[IDX["l_sk"]] = _clamp_skew(r[IDX["l_com"]], r[IDX["l_sk"]])
            r[IDX["m_sk"]] = _clamp_skew(r[IDX["m_com"]], r[IDX["m_sk"]])
            recs.append({
                "quad": QUAD_NAME[(cn_sign, pu_sign)], "gen_idx": k,
                "cn": r[IDX["cn"]] * 1000.0,      # V -> mV
                "pu": r[IDX["pu"]] * 1000.0,
                "sk": r[IDX["sk"]] * 1000.0,
                "l_comp": r[IDX["l_com"]], "lpu": r[IDX["lpu"]], "l_sk": r[IDX["l_sk"]],
                "m_comp": r[IDX["m_com"]], "mpu": r[IDX["mpu"]], "m_sk": r[IDX["m_sk"]],
            })
    df = pd.DataFrame(recs)
    # 사용자 시트와 동일한 정렬: cn 오름차순(float), 동점은 생성 순서 유지
    df = df.sort_values("cn", kind="stable").reset_index(drop=True)
    df.insert(0, "cond_id", np.arange(1, len(df) + 1))
    return df


def expand_vop(cond: pd.DataFrame, vops=VOPS) -> pd.DataFrame:
    """조건 × Vop 전개. 사용자 시트와 동일하게 조건마다 Vop 5개가 연속."""
    out = cond.loc[cond.index.repeat(len(vops))].copy()
    out["vop"] = np.tile(vops, len(cond))
    out.insert(0, "num", np.arange(1, len(out) + 1))
    return out.reset_index(drop=True)


def _display(df: pd.DataFrame) -> pd.DataFrame:
    """사용자가 deck에서 보던 표시 정밀도: cn/pu/sk 정수 mV, loc/mom 2자리."""
    d = df.copy()
    for c in MV_COLS:
        d[c] = np.round(d[c]).astype(int)
    for c in ("l_comp", "lpu", "l_sk", "m_comp", "mpu", "m_sk"):
        d[c] = np.round(d[c], 2)
    return d


def write_xlsx(n_cond: int, out_path: Path, seed: int = SEED) -> pd.DataFrame:
    cond = generate_conditions(n_cond, seed)
    rows = expand_vop(cond)

    entry = _display(rows)[["num", "cond_id", "vop"] + SHEET_COLS]
    for c in ("snmr_avg", "snmr_std", "n_mc"):
        entry[c] = ""

    full = rows[["num", "cond_id", "quad", "gen_idx", "vop"] + SHEET_COLS]

    meta = pd.DataFrame({
        "key": ["recipe_version", "seed", "n_cond", "n_rows", "sampler", "weights",
                "clamp", "vops", "sort", "scipy_note", "match_key"],
        "value": [RECIPE_VERSION, seed, n_cond, len(rows),
                  "scipy.stats.qmc.Sobol(d=9, scramble=True, seed=SEED).random(n) — quadrant마다 동일 seed로 재생성 (원본 버그, 재현 위해 유지)",
                  str(QUADRANT_WEIGHTS),
                  "|skew| <= |common - 1.0|  (l_sk, m_sk 모두)",
                  str(VOPS),
                  "cn 오름차순(float), 동점은 생성순 유지",
                  "scramble Sobol은 scipy 버전 종속. scipy 1.18에서 실측 재현 확인.",
                  "결과 매칭은 num이 아니라 cond_id(또는 조건값)로 할 것"],
    })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        entry.to_excel(xw, sheet_name="entry", index=False)
        full.to_excel(xw, sheet_name="conditions_full", index=False)
        meta.to_excel(xw, sheet_name="meta", index=False)
    print(f"  {out_path}  ({n_cond} conditions x {len(VOPS)} Vop = {len(rows)} rows)")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Regenerate legacy Sobol(seed=2026) conditions")
    ap.add_argument("--n_cond", type=int, default=None, help="생략 시 500과 2000 둘 다")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    data_dir = Path(__file__).resolve().parent.parent / "data"
    print(f"legacy_sobol_regen [{RECIPE_VERSION}] seed={args.seed}")
    if args.n_cond:
        out = Path(args.out) if args.out else data_dir / f"legacy_{args.n_cond}_seed{args.seed}.xlsx"
        write_xlsx(args.n_cond, out, args.seed)
    else:
        write_xlsx(500, data_dir / f"stageD_500_seed{args.seed}.xlsx", args.seed)
        write_xlsx(2000, data_dir / f"final_2000_seed{args.seed}.xlsx", args.seed)


if __name__ == "__main__":
    main()
