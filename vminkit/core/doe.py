"""조건 생성(DOE)과 덱 파라미터 치환.

논문 덱 생성 코드(python/src/inhouse_deck_gen.py v2.1, stage D)와 같은 알고리즘이다.
다른 점은 범위·사분면 가중치·seed 를 설정 파일에서 받는다는 것뿐이고,
기본값(DEFAULT_DOE)으로 돌리면 논문 조건과 숫자 하나까지 같다 (tests/test_gen_decks.py).

조건 → 덱 파라미터 (01_extract 의 core/axes.py 가 역변환):
    Vth shift (mV):  PG = cn + sk,      PD = cn - sk,      PU = pu
    Local sigma:     PG = l_com + l_sk, PD = l_com - l_sk, PU = lpu
    Mobility:        PG = m_com + m_sk, PD = m_com - m_sk, PU = mpu
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterator, List, Tuple

import numpy as np

from .axes import AXES, MODEL_AXES, WL_AXIS

# 논문 값. 사분면 key 는 "cn부호,pu부호" (+ = 느린 쪽).
DEFAULT_DOE: Dict[str, Any] = {
    "n_cond": 2000,
    "method": "rng",          # numpy PCG64 (논문). "sobol" 은 scipy 필요
    "vops": [0.4, 0.5, 0.6, 0.7, 0.8],
    "deck_prefix": "TT",
    "start": 1,
    "ranges": {
        "cn": [-60.0, 60.0], "pu": [-60.0, 60.0], "sk": [-20.0, 20.0],
        "loc": [0.7, 1.3], "mom": [0.7, 1.3],
        "l_sk": [-0.075, 0.075], "m_sk": [-0.075, 0.075],
    },
    "seeds": {"read": 2027, "write": 2028},
    # read 는 FSG(cn-, pu+), write 는 SFG(cn+, pu-) 쪽을 더 촘촘히
    "quadrant_weights": {
        "read":  {"-,+": 0.45, "-,-": 0.20, "+,+": 0.15, "+,-": 0.20},
        "write": {"-,+": 0.10, "-,-": 0.15, "+,+": 0.30, "+,-": 0.45},
    },
    # 10번째 축 (논문에는 없음). 9D 와 다른 난수열(seed + 200)이라 9D 조건은 논문과 그대로.
    # range 를 null 로 두면 모든 덱이 1.0 (VWL = Vop, 논문과 같은 덱).
    "wl_ratio": {"range": [0.8, 1.0], "decimals": 3},
}
WL_SEED_OFFSET = 200

INT_AXES = ("cn", "sk", "pu")


def merge_doe(user: Dict[str, Any] | None) -> Dict[str, Any]:
    """설정 파일의 doe 블록을 기본값 위에 덮는다 (한 단계 깊이까지)."""
    out = copy.deepcopy(DEFAULT_DOE)
    for k, v in (user or {}).items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            for kk, vv in v.items():
                out[k][kk] = copy.deepcopy(vv)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _unit(n: int, d: int, seed: int, method: str) -> np.ndarray:
    if method == "rng":
        return np.random.default_rng(seed).random((n, d))
    if method == "sobol":
        from scipy.stats import qmc
        s = qmc.Sobol(d=d, scramble=True, seed=seed)
        m = int(np.ceil(np.log2(max(n, 1))))
        return s.random_base2(m=m)[:n]
    raise ValueError(f"method 는 'rng' 또는 'sobol' 이어야 합니다: {method!r}")


def _parse_quadrants(w: Dict[str, float]) -> List[Tuple[Tuple[int, int], float]]:
    out = []
    for key, val in w.items():
        a, b = (s.strip() for s in key.split(","))
        out.append(((1 if a == "+" else -1, 1 if b == "+" else -1), float(val)))
    return out


def _quadrant_cnpu(n_total: int, weights, seed: int, method: str, r) -> np.ndarray:
    cn_min, cn_max = r["cn"]
    pu_min, pu_max = r["pu"]
    parts = []
    for i, ((cs, ps), w) in enumerate(weights):
        n = int(round(n_total * w))
        if n <= 0:
            continue
        u = _unit(n, 2, seed + 1 + i, method)
        cn_lo, cn_hi = (0.0, cn_max) if cs > 0 else (cn_min, 0.0)
        pu_lo, pu_hi = (0.0, pu_max) if ps > 0 else (pu_min, 0.0)
        parts.append(np.column_stack([cn_lo + (cn_hi - cn_lo) * u[:, 0],
                                      pu_lo + (pu_hi - pu_lo) * u[:, 1]]))
    pts = np.vstack(parts)
    np.random.default_rng(seed).shuffle(pts)
    if len(pts) < n_total:
        e = _unit(n_total - len(pts), 2, seed + 999, method)
        pts = np.vstack([pts, np.column_stack([cn_min + (cn_max - cn_min) * e[:, 0],
                                               pu_min + (pu_max - pu_min) * e[:, 1]])])
    return pts[:n_total]


def generate_conditions(doe: Dict[str, Any], mode: str) -> np.ndarray:
    """(n_cond, 9) 조건 배열, 열 순서는 AXES. 같은 설정이면 항상 같은 결과."""
    r = doe["ranges"]
    n = int(doe["n_cond"])
    seed = int(doe["seeds"][mode])
    method = doe["method"]
    qw = doe["quadrant_weights"].get(mode)
    if qw:
        cnpu = _quadrant_cnpu(n, _parse_quadrants(qw), seed, method, r)
    else:
        u = _unit(n, 2, seed, method)
        cnpu = np.column_stack([r["cn"][0] + (r["cn"][1] - r["cn"][0]) * u[:, 0],
                                r["pu"][0] + (r["pu"][1] - r["pu"][0]) * u[:, 1]])
    cn = np.round(cnpu[:, 0])
    pu = np.round(cnpu[:, 1])
    e = _unit(n, 7, seed + 100, method)

    def span(key, col, nd):
        lo, hi = r[key]
        return np.round(lo + (hi - lo) * e[:, col], nd)

    sk = span("sk", 0, 0)
    lpu, l_com, l_sk = span("loc", 1, 2), span("loc", 2, 2), span("l_sk", 3, 2)
    mpu, m_com, m_sk = span("mom", 4, 2), span("mom", 5, 2), span("m_sk", 6, 2)
    return np.column_stack([cn, sk, pu, lpu, l_com, l_sk, mpu, m_com, m_sk]).astype(float)


def generate_wl_ratio(doe: Dict[str, Any], mode: str) -> np.ndarray:
    """조건마다 VWL/VDDA 비율. 같은 조건이면 모든 Vop 에서 같은 비율."""
    n = int(doe["n_cond"])
    w = doe.get("wl_ratio") or {}
    rng_ = w.get("range")
    if not rng_:
        return np.ones(n)
    lo, hi = float(rng_[0]), float(rng_[1])
    u = _unit(n, 1, int(doe["seeds"][mode]) + WL_SEED_OFFSET, doe["method"])[:, 0]
    return np.round(lo + (hi - lo) * u, int(w.get("decimals", 3)))


def iter_decks(doe: Dict[str, Any], mode: str) -> Iterator[Dict[str, Any]]:
    """(Vop, 조건) 마다 한 레코드. 바깥 루프 Vop, 번호는 Vop 마다 start 부터 다시."""
    cond = generate_conditions(doe, mode)
    wl = generate_wl_ratio(doe, mode)
    for v in doe["vops"]:
        for i in range(len(cond)):
            no = int(doe["start"]) + i
            rec: Dict[str, Any] = {"deck_no": no, "deck_id": f"{doe['deck_prefix']}-{no}",
                                   "vop": float(v)}
            for j, c in enumerate(AXES):
                rec[c] = int(cond[i, j]) if c in INT_AXES else round(float(cond[i, j]), 2) + 0.0
            rec[WL_AXIS] = float(wl[i]) + 0.0
            rec["VWL"] = round(float(v) * rec[WL_AXIS], 6)
            yield rec


# ---------------------------------------------------------------------------
# 덱 치환
# ---------------------------------------------------------------------------

# .param VTMSKEW_PU1 = '( <A> ) + <B>'  에서 괄호 안 A 만 바꾼다. '+ <B>' 는 그대로.
PARAM_PATTERN = r"(\.param\s+{name}\s*=\s*'\s*\(\s*)[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?(\s*\))"
FAMILIES = [f"{fam}_{dev}" for fam in ("VTMSKEW", "VTSLSKEW", "MOMSKEW")
            for dev in ("PU", "PG", "PD")]


def deck_params(rec: Dict[str, Any], vth_unit: str = "V") -> Dict[str, str]:
    cn, sk, pu = rec["cn"], rec["sk"], rec["pu"]
    vals = {
        "VTMSKEW_PG": cn + sk, "VTMSKEW_PD": cn - sk, "VTMSKEW_PU": pu,
        "VTSLSKEW_PG": rec["l_com"] + rec["l_sk"], "VTSLSKEW_PD": rec["l_com"] - rec["l_sk"],
        "VTSLSKEW_PU": rec["lpu"],
        "MOMSKEW_PG": rec["m_com"] + rec["m_sk"], "MOMSKEW_PD": rec["m_com"] - rec["m_sk"],
        "MOMSKEW_PU": rec["mpu"],
    }
    scale = 1e-3 if vth_unit == "V" else 1.0
    return {k: f"{v * scale:.6f}" if k.startswith("VTMSKEW") else f"{v:.6f}"
            for k, v in vals.items()}


VWL_PATTERN = r"(\.param\s+VWL\s*=\s*'\s*\(\s*)[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?(\s*\))"


def set_vwl(text: str, vwl: float, src_name: str) -> str:
    """예전 방식 template: .param VWL='( A ) + B' 의 A 를 Vop x wl_ratio 로."""
    text, n = re.subn(VWL_PATTERN, lambda m: m.group(1) + f"{vwl:.6f}" + m.group(2),
                      text, flags=re.IGNORECASE | re.MULTILINE)
    if n != 1:
        raise RuntimeError(f"[{src_name}] .param VWL='( A ) + B' 가 {n}번 매치됨 (기대 1번)")
    return text


def replace_params(text: str, values: Dict[str, str], src_name: str,
                   expected: int = 2) -> str:
    """template 의 파라미터 값을 조건값으로 치환. 개수가 expected 와 다르면 멈춘다."""
    for fam in FAMILIES:
        pat = PARAM_PATTERN.format(name=fam + r"\d")
        text, n = re.subn(pat, lambda m, v=values[fam]: m.group(1) + v + m.group(2),
                          text, flags=re.IGNORECASE | re.MULTILINE)
        if n != expected:
            raise RuntimeError(
                f"[{src_name}] '{fam}1/2' 가 {n}번 매치됨 (기대 {expected}번). "
                f"template 문법을 확인하세요. 그냥 넘어가면 조건이 틀어집니다.")
    return text
