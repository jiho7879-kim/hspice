"""0단계: template 덱 → 시뮬레이션용 .in 덱 (Vop 당 2000개, 논문 방식).

    python vminkit/00_gen_decks.py --config vminkit/configs/my_node.json --preview
    python vminkit/00_gen_decks.py --config ... --limit 3        # 스모크: Vop당 3개만
    python vminkit/00_gen_decks.py --config ...                  # 전체 생성
    python vminkit/00_gen_decks.py --config ... --mode read --force

설정의 modes 마다
  template_dir   : template 덱이 있는 폴더
  template_glob  : template 파일 이름 패턴. {prefix} {start} {vop} 가 채워진다.
                   기본 "*{prefix}-{start}_{vop}V*.in"  (예: 02-sp-bc-snmr-TT-1_0.4V-125C.in)
                   - {vop} 가 있으면 Vop 마다 template 하나 (논문 방식)
                   - {vop} 가 없으면 template 하나에서 .param VOP 값도 바꾼다
  deck_out_dir   : 덱을 쓸 폴더 (기본 work_dir/00_gen_decks/<mode>)

조건은 doe 설정(기본값 = 논문: stage D 9D, 2000 조건, PCG64, read seed 2027 / write
seed 2028, 사분면 가중)으로 만든다. 덱 이름은 template 이름의 "TT-1" 을 "TT-<번호>" 로
바꾼 것이고, 번호는 Vop 마다 1 부터 다시 시작한다.

출력:
  deck_out_dir/*.in              시뮬레이션에 넣을 덱
  deck_out_dir/conditions_<mode>.csv   덱 파일 ↔ 조건(9D, Vop) 표
  work_dir/00_gen_decks/gen_<mode>.md  사용한 설정과 범위 요약

시뮬레이션이 끝나면 결과(.mt0)가 있는 폴더를 설정의 sim_dirs 에 적고 01_extract.py 를 실행한다.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.axes import AXES, MODEL_AXES, WL_AXIS  # noqa: E402
from core.config import ConfigError, load_config  # noqa: E402
from core.doe import (deck_params, generate_conditions, generate_wl_ratio, iter_decks,  # noqa: E402
                      replace_params, set_vwl)
from core import template as tpl_mod  # noqa: E402

STEP_DIR = "00_gen_decks"
VOP_PATTERN = r"(\.param\s+VOP\s*=\s*'\s*\(\s*)[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?(\s*\))"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def find_templates(m: Dict[str, Any], doe: Dict[str, Any], name: str) -> Dict[float, Path]:
    if not m.get("template_dir"):
        raise SystemExit(f"[{name}] 설정에 template_dir 이 없습니다")
    tdir = Path(m["template_dir"])
    if not tdir.is_dir():
        raise SystemExit(f"[{name}] template_dir 가 없습니다: {tdir}")
    glob = m["template_glob"]
    out: Dict[float, Path] = {}
    per_vop = "{vop}" in glob
    for v in (doe["vops"] if per_vop else [None]):
        pat = glob.format(prefix=doe["deck_prefix"], start=doe["start"],
                          vop="" if v is None else f"{v:g}")
        hits = sorted(tdir.glob(pat))
        if len(hits) != 1:
            raise SystemExit(f"[{name}] template 패턴 '{pat}' 이 {len(hits)}개 매치됨 "
                             f"(정확히 1개 필요). 폴더: {tdir.resolve()}")
        if v is None:
            return {float(x): hits[0] for x in doe["vops"]}
        out[float(v)] = hits[0]
    return out


def deck_name(template: Path, rec: Dict[str, Any], doe: Dict[str, Any], per_vop: bool) -> str:
    pat = rf"{re.escape(doe['deck_prefix'])}-\d+"
    if re.search(pat, template.name):
        name = re.sub(pat, rec["deck_id"], template.name, count=1)
        if not per_vop:  # template 하나면 Vop 를 이름에 붙여 구분
            name = name[: len(name) - len(template.suffix)] + f"_{rec['vop']:g}V{template.suffix}"
        return name
    return f"{template.stem}_{rec['deck_id']}_{rec['vop']:g}V{template.suffix}"


def render(text: str, rec: Dict[str, Any], vth_unit: str, src: str, per_vop: bool) -> str:
    text = replace_params(text, deck_params(rec, vth_unit), src)
    text = set_vwl(text, rec["VWL"], src)
    if not per_vop:
        text, n = re.subn(VOP_PATTERN, lambda mm: mm.group(1) + f"{rec['vop']:.6f}" + mm.group(2),
                          text, flags=re.IGNORECASE | re.MULTILINE)
        if n != 1:
            raise RuntimeError(f"[{src}] .param VOP 가 {n}번 매치됨 (기대 1번)")
    return text


def gen_mode(cfg: Dict[str, Any], name: str, limit: Optional[int], preview: bool,
             force: bool) -> None:
    m = cfg["modes"][name]
    if m.get("template"):
        return gen_mode_placeholder(cfg, name, limit, preview, force)
    doe = cfg["doe"]
    vth_unit = cfg["deck"]["vth_unit"]
    per_vop = "{vop}" in m["template_glob"]
    tmpl = find_templates(m, doe, name)
    texts = {v: _read(p) for v, p in tmpl.items()}
    print(f"[{name}] n_cond={doe['n_cond']} seed={doe['seeds'][name]} method={doe['method']} "
          f"Vop={doe['vops']}")
    for v, p in tmpl.items():
        print(f"  template {v:g} V: {p.name}")

    if preview:
        rec = next(iter_decks(doe, name))
        src = tmpl[rec["vop"]]
        before = texts[rec["vop"]]
        after = render(before, rec, vth_unit, src.name, per_vop)
        print(f"\n--- preview: {src.name} -> {deck_name(src, rec, doe, per_vop)} ---")
        print("  조건: " + ", ".join(f"{c}={rec[c]}" for c in MODEL_AXES))
        n = 0
        for b, a in zip(before.splitlines(), after.splitlines()):
            if b != a:
                print(f"  BEFORE | {b.strip()}\n  AFTER  | {a.strip()}")
                n += 1
        print(f"  바뀐 줄 {n}개 (기대 {19 + (0 if per_vop else 1)}개, VWL 포함)")
        return

    out_dir = Path(m["deck_out_dir"] or Path(cfg["work_dir"]) / STEP_DIR / name)
    map_path = out_dir / f"conditions_{name}.csv"
    if map_path.exists() and not force:
        raise SystemExit(f"{map_path} 가 이미 있습니다. 덮어쓰려면 --force")
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    n_written = 0
    names = set()
    with open(map_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["deck_file", "deck_no", "vop"] + MODEL_AXES + ["VWL"])
        for rec in iter_decks(doe, name):
            if limit is not None and rec["deck_no"] >= doe["start"] + limit:
                continue
            src = tmpl[rec["vop"]]
            fn = deck_name(src, rec, doe, per_vop)
            if fn in names:
                raise RuntimeError(f"덱 이름이 겹칩니다: {fn} (template 이름을 확인하세요)")
            names.add(fn)
            (out_dir / fn).write_text(render(texts[rec["vop"]], rec, vth_unit, src.name, per_vop),
                                      encoding="utf-8")
            w.writerow([fn, rec["deck_no"], rec["vop"]] + [rec[c] for c in MODEL_AXES] + [rec["VWL"]])
            n_written += 1
    print(f"[{name}] 덱 {n_written}개 → {out_dir.resolve()} ({time.time() - t0:.0f}s)")
    write_report(cfg, name, out_dir, n_written, tmpl, limit)


def _placeholder_setup(cfg: Dict[str, Any], name: str):
    """include + mode template 읽기, 값 합치기, 빠진 이름 검사."""
    m = cfg["modes"][name]
    dt = cfg.get("deck_template") or {}
    inc_path = dt.get("include")
    texts = []
    for label, p in (("deck_template.include", inc_path), (f"modes.{name}.template", m["template"])):
        if not p:
            raise SystemExit(f"설정에 {label} 경로가 없습니다")
        if not Path(p).is_file():
            raise SystemExit(f"{label} 파일이 없습니다: {p}")
        texts.append(_read(Path(p)))
    inc, tpl = texts
    values: Dict[str, Any] = {k: v for k, v in (dt.get("values") or {}).items() if not k.startswith("_")}
    values.update({k: v for k, v in (m.get("values") or {}).items() if not k.startswith("_")})
    bad = tpl_mod.conflicting(values)
    if bad:
        raise SystemExit(f"[{name}] {bad} 는 덱마다 코드가 채우는 값이라 설정에서 빼야 합니다")
    probe = dict(values)
    probe.update({k: 0 for k in tpl_mod.AUTO_KEYS})
    missing, unused = tpl_mod.split_keys(inc, tpl, probe)
    if missing:
        raise SystemExit(f"[{name}] template 에 있는데 설정에 값이 없는 자리표시자: {', '.join(missing)}\n"
                         f"  → deck_template.values 또는 modes.{name}.values 에 추가하세요")
    if unused:
        print(f"  [참고] 설정에는 있지만 template 에 없는 값: {', '.join(unused)}")
    todo = [k for k in tpl_mod.todo_keys(values) if k not in unused]
    if todo:
        raise SystemExit(f"[{name}] 설정에 아직 \"TODO\" 인 값: {', '.join(todo)}")
    return inc, tpl, values, Path(inc_path), Path(m["template"])


def _placeholder_deck(inc: str, tpl: str, values: Dict[str, Any], rec: Dict[str, Any],
                      vth_unit: str, src: str) -> str:
    v = dict(values)
    v.update(tpl_mod.auto_values(deck_params(rec, vth_unit), rec["vop"], rec["VWL"]))
    sep = "" if inc.endswith("\n") else "\n"
    return tpl_mod.fill(inc + sep + tpl, v, rec["vop"], src)


def _placeholder_name(m: Dict[str, Any], rec: Dict[str, Any], doe: Dict[str, Any]) -> str:
    pat = m.get("deck_name") or "{metric}_{prefix}-{no}_{vop}V.in"
    return pat.format(metric=m["metric"], prefix=doe["deck_prefix"], no=rec["deck_no"],
                      vop=f"{rec['vop']:g}", mode=m.get("_name", ""))


def gen_mode_placeholder(cfg: Dict[str, Any], name: str, limit: Optional[int], preview: bool,
                         force: bool) -> None:
    m = cfg["modes"][name]
    doe = cfg["doe"]
    vth_unit = cfg["deck"]["vth_unit"]
    print(f"[{name}] n_cond={doe['n_cond']} seed={doe['seeds'][name]} method={doe['method']} "
          f"Vop={doe['vops']}")
    inc, tpl, values, inc_path, tpl_path = _placeholder_setup(cfg, name)
    print(f"  include : {inc_path}\n  template: {tpl_path}")

    if preview:
        rec = next(iter_decks(doe, name))
        text = _placeholder_deck(inc, tpl, values, rec, vth_unit, tpl_path.name)
        print(f"\n--- preview: {_placeholder_name(m, rec, doe)} ---")
        print("  조건: " + ", ".join(f"{c}={rec[c]}" for c in MODEL_AXES) + f", vop={rec['vop']}")
        src_lines = (inc + "\n" + tpl).splitlines()
        for b, a in zip(src_lines, text.splitlines()):
            if b != a:
                print(f"  {a.strip()}")
        return

    out_dir = Path(m["deck_out_dir"] or Path(cfg["work_dir"]) / STEP_DIR / name)
    map_path = out_dir / f"conditions_{name}.csv"
    if map_path.exists() and not force:
        raise SystemExit(f"{map_path} 가 이미 있습니다. 덮어쓰려면 --force")
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    n_written = 0
    names = set()
    with open(map_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["deck_file", "deck_no", "vop"] + MODEL_AXES + ["VWL"])
        for rec in iter_decks(doe, name):
            if limit is not None and rec["deck_no"] >= doe["start"] + limit:
                continue
            fn = _placeholder_name(m, rec, doe)
            if fn in names:
                raise RuntimeError(f"덱 이름이 겹칩니다: {fn} (deck_name 에 {{no}} 와 {{vop}} 를 넣으세요)")
            names.add(fn)
            (out_dir / fn).write_text(
                _placeholder_deck(inc, tpl, values, rec, vth_unit, tpl_path.name), encoding="utf-8")
            w.writerow([fn, rec["deck_no"], rec["vop"]] + [rec[c] for c in MODEL_AXES] + [rec["VWL"]])
            n_written += 1
    print(f"[{name}] 덱 {n_written}개 → {out_dir.resolve()} ({time.time() - t0:.0f}s)")
    write_report(cfg, name, out_dir, n_written, {"include": inc_path, "template": tpl_path}, limit)


def write_report(cfg, name, out_dir: Path, n_written: int, tmpl, limit) -> None:
    doe = cfg["doe"]
    cond = np.column_stack([generate_conditions(doe, name), generate_wl_ratio(doe, name)])
    rep_dir = Path(cfg["work_dir"]) / STEP_DIR
    rep_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# 00_gen_decks · {cfg['node']} · {name}",
        "",
        f"- 설정: `{cfg['_path']}`",
        f"- 생성: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 덱 {n_written}개 → `{out_dir.resolve()}`"
        + (f" (스모크: Vop당 {limit}개)" if limit is not None else ""),
        f"- 조건 {doe['n_cond']}개 x Vop {len(doe['vops'])}개, method {doe['method']}, "
        f"seed {doe['seeds'][name]}",
        f"- 조건 지문(checksum, 9D): {float(cond[:, :9].sum()):.6f}  (같은 설정이면 항상 같은 값)",
        f"- wl_ratio (VWL/VDDA): {doe.get('wl_ratio')}",
        "",
        "## template",
        "",
    ] + [f"- {k if isinstance(k, str) else f'{k:g} V'}: `{p}`" for k, p in tmpl.items()] + [
        "",
        "## 생성된 조건 범위",
        "",
        "| 축 | 최소 | 최대 | 평균 |",
        "| --- | --- | --- | --- |",
    ] + [f"| {c} | {cond[:, j].min():g} | {cond[:, j].max():g} | {cond[:, j].mean():.3f} |"
         for j, c in enumerate(MODEL_AXES)]
    qw = doe["quadrant_weights"].get(name)
    if qw:
        cn, pu = cond[:, 0], cond[:, 2]
        lines += ["", "## (cn, pu) 사분면 비율", "", "| 사분면 | 설정 | 실제 |", "| --- | --- | --- |"]
        for key, val in qw.items():
            a, b = (s.strip() for s in key.split(","))
            mc = (cn >= 0) if a == "+" else (cn <= 0)
            mp = (pu >= 0) if b == "+" else (pu <= 0)
            lines.append(f"| cn{a} pu{b} | {val:.2f} | {np.mean(mc & mp):.2f} |")
    lines += ["", "## doe 설정 전체", "", "```json", json.dumps(doe, indent=2, ensure_ascii=False),
              "```", "", "## 다음 단계", "",
              "덱을 PrimeSim 으로 돌린 뒤, 결과(.mt0)가 있는 폴더를 설정의 "
              f"`modes.{name}.sim_dirs` 에 적고 `01_extract.py` 를 실행한다."]
    (rep_dir / f"gen_{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[{name}] 요약 → {rep_dir / f'gen_{name}.md'}")


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="0단계: template → 시뮬레이션 덱")
    ap.add_argument("--config", required=True)
    ap.add_argument("--mode", default="all", help="read / write / all")
    ap.add_argument("--preview", action="store_true",
                    help="첫 덱의 바뀌는 .param 줄만 보여주고 파일은 안 씀")
    ap.add_argument("--limit", type=int, default=None, help="Vop당 앞 N개만 (스모크)")
    ap.add_argument("--force", action="store_true", help="기존 결과 덮어쓰기")
    a = ap.parse_args(argv)
    try:
        cfg = load_config(a.config)
    except ConfigError as e:
        raise SystemExit(f"설정 오류: {e}")
    names = list(cfg["modes"]) if a.mode == "all" else [a.mode]
    for n in names:
        if n not in cfg["modes"]:
            raise SystemExit(f"설정에 mode '{n}' 이 없습니다 ({list(cfg['modes'])})")
    for n in names:
        gen_mode(cfg, n, a.limit, a.preview, a.force)
    if not a.preview:
        print("\n완료. 덱으로 시뮬레이션을 돌린 뒤 01_extract.py 를 실행하세요.")


if __name__ == "__main__":
    main()
