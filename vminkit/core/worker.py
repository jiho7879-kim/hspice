"""01_extract 의 덱 하나 처리. multiprocessing 이 import 할 수 있도록 별도 모듈에 둔다."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from . import primesim
from .axes import deck_to_axes


# ---------------------------------------------------------------------------

def _single_samples(path: Path, measure: Optional[str]) -> np.ndarray:
    cols, order = primesim.parse_mt0_wrapped(path)
    vals = primesim._pick_measure(cols, order, measure)
    return vals[primesim._index_order(cols, len(vals))]


def _find(sim_dir: Path, pattern: str, stem: str, exclude_ab: bool) -> List[Path]:
    hits = sorted(sim_dir.glob(pattern.format(stem=stem)))
    if exclude_ab:
        # SNMR 파일을 찾을 때 Vtrip a0/a1 파일을 잘못 집지 않게
        hits = [f for f in hits
                if "a0" not in f.stem[len(stem):] and "a1" not in f.stem[len(stem):]]
    return hits


def process_deck(job: Tuple[str, str, Dict[str, Any], str, bool, Optional[float]]) -> Dict[str, Any]:
    deck_path, sim_dir, res, vth_unit, keep, floor = job
    deck = Path(deck_path)
    sdir = Path(sim_dir)
    stem = deck.stem
    out: Dict[str, Any] = {"deck": stem, "sim_dir": sim_dir, "issues": []}
    try:
        row = primesim.parse_in_deck(deck)
    except Exception as e:  # 덱 하나가 깨져도 전체는 계속
        out["issues"].append(("deck_parse_error", str(e)))
        return out

    axes, warns = deck_to_axes(row, vth_unit)
    out.update(axes)
    out["vop"] = row.get("VOP", np.nan)
    out["temp"] = row.get("temp", np.nan)
    for w in warns:
        out["issues"].append(("deck_warning", w))
    if "VOP" not in row:
        out["issues"].append(("no_vop", "덱에 .param VOP 가 없음"))

    try:
        if res["type"] == "single":
            hits = _find(sdir, res["pattern"], stem, exclude_ab=True)
            if not hits:
                out["issues"].append(("missing_result", res["pattern"].format(stem=stem)))
                return out
            if len(hits) > 1:
                out["issues"].append(("multiple_results", ", ".join(h.name for h in hits)))
            raw = _single_samples(hits[0], res["measure"])
            n_raw = len(raw)
            out["result_file"] = hits[0].name
        else:
            a0 = _find(sdir, res["left_pattern"], stem, exclude_ab=False)
            a1 = _find(sdir, res["right_pattern"], stem, exclude_ab=False)
            if not a0 or not a1:
                out["issues"].append(("missing_result",
                                      f"a0 {len(a0)}개, a1 {len(a1)}개"))
                return out
            v = primesim.vtrip_min_stats(a0[0], a1[0],
                                         measure_left=res["left_measure"],
                                         measure_right=res["right_measure"])
            raw = v["min_samples"]
            n_raw = v["n"] + v["n_dropped"]
            if v["n_dropped"]:
                out["issues"].append(("mc_index_mismatch",
                                      f"a0/a1 짝이 안 맞는 표본 {v['n_dropped']}개 제외"))
            out["result_file"] = f"{a0[0].name} | {a1[0].name}"
    except Exception as e:
        out["issues"].append(("result_parse_error", str(e)))
        return out

    vals = raw[~np.isnan(raw)]
    out["n_nan"] = int(n_raw - len(vals))
    if len(vals) < 2:
        out["issues"].append(("too_few_samples", f"유효 표본 {len(vals)}개"))
        return out
    out["mu"] = float(np.mean(vals))
    out["sigma"] = float(np.std(vals, ddof=1))
    out["median"] = float(np.median(vals))
    out["n_mc"] = int(len(vals))
    if floor is not None:
        out["frac_below_floor"] = float(np.mean(vals <= floor))
    out["_samples"] = vals.astype(np.float32) if keep else None
    return out
