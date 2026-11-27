"""덱 파라미터(PG/PD/PU별 skew) → 논문 9D 입력축.

논문 덱 생성 규칙(python/src/inhouse_deck_gen.py condition_to_deck_params)의 역변환:
    Vth shift (mV):  PG = cn + sk,      PD = cn - sk,      PU = pu
    Local sigma:     PG = l_com + l_sk, PD = l_com - l_sk, PU = lpu
    Mobility:        PG = m_com + m_sk, PD = m_com - m_sk, PU = mpu
"""
from __future__ import annotations

from typing import Dict, List, Tuple

AXES: List[str] = ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]
# 10번째 축: read/write assist 평가용 VWL / VDDA(=VOP) 비율. 덱의 VWL = Vop x wl_ratio.
WL_AXIS = "wl_ratio"
MODEL_AXES: List[str] = AXES + [WL_AXIS]

# (deck family, 값이 없을 때 기본값)
_FAMILIES = {
    "VTMSKEW": 0.0,   # Vth mean shift
    "VTSLSKEW": 1.0,  # local sigma multiplier
    "MOMSKEW": 1.0,   # mobility multiplier
}
_ROUND = 6


def deck_to_axes(row: Dict[str, object], vth_unit: str = "V") -> Tuple[Dict[str, float], List[str]]:
    """parse_in_deck 결과 한 행 → (9D 값 dict, 경고 목록)."""
    warns: List[str] = []

    def get(fam: str, dev: str) -> float:
        key = f"{fam}_{dev}"
        if key not in row:
            warns.append(f"{key} 없음 → 기본값 {_FAMILIES[fam]}")
            return _FAMILIES[fam]
        return float(row[key])  # type: ignore[arg-type]

    vscale = 1000.0 if vth_unit == "V" else 1.0
    vpg, vpd, vpu = (get("VTMSKEW", d) * vscale for d in ("PG", "PD", "PU"))
    lpg, lpd, lpu = (get("VTSLSKEW", d) for d in ("PG", "PD", "PU"))
    mpg, mpd, mpu = (get("MOMSKEW", d) for d in ("PG", "PD", "PU"))

    for k in row:
        if str(k).endswith("_mismatch"):
            warns.append(f"{k}: 인스턴스 1/2 값이 다름 (1번 값을 사용)")

    vop = row.get("VOP")
    if "VWL" in row and vop:
        wl = float(row["VWL"]) / float(vop)  # type: ignore[arg-type]
    else:
        wl = 1.0
        warns.append("VWL 또는 VOP 없음 → wl_ratio = 1")

    out = {
        "cn": (vpg + vpd) / 2, "sk": (vpg - vpd) / 2, "pu": vpu,
        "lpu": lpu, "l_com": (lpg + lpd) / 2, "l_sk": (lpg - lpd) / 2,
        "mpu": mpu, "m_com": (mpg + mpd) / 2, "m_sk": (mpg - mpd) / 2,
    }
    res = {k: round(v, _ROUND) + 0.0 for k, v in out.items()}
    res[WL_AXIS] = round(wl, 4) + 0.0
    return res, warns
