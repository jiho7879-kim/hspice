"""노드 설정 파일(JSON) 읽기와 검사. Python 3.8 표준 라이브러리만 쓴다."""
from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict

RESULT_TYPES = ("single", "min_left_right")


class ConfigError(ValueError):
    pass


def _require(d: Dict[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise ConfigError(f"설정 파일에 '{where}.{key}' 가 없습니다")
    return d[key]


def load_config(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    _require(cfg, "node", "")
    cfg.setdefault("work_dir", f"work/{cfg['node']}")
    cfg.setdefault("yield_target", {"array_mb": 128, "yield": 0.99})
    deck = cfg.setdefault("deck", {})
    deck.setdefault("pattern", "*.in")
    deck.setdefault("vth_unit", "V")
    if deck["vth_unit"] not in ("V", "mV"):
        raise ConfigError("deck.vth_unit 은 'V' 또는 'mV' 여야 합니다")

    modes = _require(cfg, "modes", "")
    if not modes:
        raise ConfigError("modes 가 비어 있습니다")
    for name, m in modes.items():
        where = f"modes.{name}"
        _require(m, "metric", where)
        dirs = _require(m, "sim_dirs", where)
        if isinstance(dirs, str):
            m["sim_dirs"] = [dirs]
        res = _require(m, "result", where)
        rtype = _require(res, "type", where + ".result")
        if rtype not in RESULT_TYPES:
            raise ConfigError(f"{where}.result.type 은 {RESULT_TYPES} 중 하나여야 합니다")
        if rtype == "single":
            res.setdefault("pattern", "{stem}.mt0")
            res.setdefault("measure", None)
        else:
            for k in ("left_pattern", "right_pattern"):
                _require(res, k, where + ".result")
            res.setdefault("left_measure", None)
            res.setdefault("right_measure", None)
        m.setdefault("value_unit", "V")
        if m["value_unit"] not in ("V", "mV"):
            raise ConfigError(f"{where}.value_unit 은 'V' 또는 'mV' 여야 합니다")
        m.setdefault("temperature_C", None)
        m.setdefault("snm_floor_mV", None)

    cfg["_path"] = str(path.resolve())
    cfg["z_target"] = z_target(cfg["yield_target"])
    return cfg


def z_target(yt: Dict[str, Any]) -> float:
    """어레이 수율 목표 → 셀 단위 z (Poisson, 논문 D-01과 같은 식).

    Y = exp(-N p)  →  p = -ln(Y) / N,  z = -Φ⁻¹(p).  N = array_mb × 10^6 bit
    (python/src/utils.py derive_z_target 과 같은 정의). 128 Mb @ 99 % → 6.398.
    """
    if "z" in yt and yt["z"] is not None:
        return float(yt["z"])
    n_bits = float(yt["array_mb"]) * float(yt.get("bits_per_mb", 1e6))
    p = -math.log(float(yt["yield"])) / n_bits
    return -NormalDist().inv_cdf(p)
