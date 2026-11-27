"""#이름# 자리표시자 template 채우기 (사내 include.param.tpl + snmr/bwrm template 방식).

덱 한 개 = include template(채움) + mode template(채움).
값의 출처 (뒤에 오는 것이 앞의 것을 덮는다):
  1. deck_template.values            노드 공통 고정값 (라이브러리, 코너, MC 횟수, 사이즈, OFFSET_* ...)
  2. modes.<mode>.values             mode 별 고정값 (TEMP 등)
  3. 덱마다 자동으로 채우는 값        VTMSKEW_/VTSLSKEW_/MOMSKEW_{PU,PG,PD}, VDDA(=Vop)
값을 문자열 "=VOP" 로 적으면 그 덱의 Vop 가 들어간다 (예: VWL, VBL 을 Vop 에 맞출 때).

채운 뒤 '#이름' 이 하나라도 남으면 (값이 없거나 '#' 짝이 안 맞는 오타) 멈추고 목록을 보여준다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set, Tuple

TOKEN = re.compile(r"#([A-Za-z_][A-Za-z0-9_]*)#")
LEFTOVER = re.compile(r"#[A-Za-z_][A-Za-z0-9_]*#?")

# 덱마다 코드가 채우는 이름 (설정에 적으면 무시하지 않고 오류로 알린다)
AUTO_KEYS = tuple(f"{fam}_{dev}" for fam in ("VTMSKEW", "VTSLSKEW", "MOMSKEW")
                  for dev in ("PU", "PG", "PD")) + ("VDDA",)


def tokens(text: str) -> Set[str]:
    return set(TOKEN.findall(text))


def _fmt(v: Any) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return f"{v:.10g}"
    return str(v)


def todo_keys(values: Dict[str, Any]) -> List[str]:
    """설정에 아직 "TODO" 로 남은 값."""
    return sorted(k for k, v in values.items() if isinstance(v, str) and v.strip().upper() == "TODO")


def fill(text: str, values: Dict[str, Any], vop: float, src: str) -> str:
    def rep(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key not in values:
            return m.group(0)
        v = values[key]
        if isinstance(v, str) and v.strip().upper() == "=VOP":
            return _fmt(float(vop))
        return _fmt(v)

    out = TOKEN.sub(rep, text)
    left = check_leftover(out)
    if left:
        raise RuntimeError(f"[{src}] 채우지 못한 자리표시자: {', '.join(left)}")
    return out


def check_leftover(text: str) -> List[str]:
    """채운 뒤 남은 '#이름' 목록. 줄 번호를 같이 준다 (주석 줄 '*' 는 건너뜀)."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("*"):
            continue
        for m in LEFTOVER.finditer(line):
            out.append(f"{m.group(0)} ({i}행)")
    return out


def split_keys(include: str, mode_tpl: str, values: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """(template 에 있는데 값이 없는 이름, 값은 있는데 template 에 없는 이름)."""
    need = tokens(include) | tokens(mode_tpl)
    have = set(values)
    return sorted(need - have), sorted(have - need)


def auto_values(params: Dict[str, str], vop: float) -> Dict[str, Any]:
    """core.doe.deck_params 결과(문자열) + Vop → 자동 채움 값."""
    out: Dict[str, Any] = dict(params)
    out["VDDA"] = f"{vop:g}"
    return out


def conflicting(user_keys: Iterable[str]) -> List[str]:
    return sorted(set(user_keys) & set(AUTO_KEYS))
