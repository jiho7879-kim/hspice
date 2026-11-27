"""00_gen_decks 시험.

1) 기본 설정 조건이 논문 덱 생성 코드(python/src/inhouse_deck_gen.py)와 완전히 같은지
2) template → 덱 → (가짜 시뮬레이션) → 01_extract 로 읽은 9D 가 조건표와 같은지

    python vminkit/tests/test_gen_decks.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


gen = load("gen_decks", ROOT / "00_gen_decks.py")
extract = load("extract", ROOT / "01_extract.py")
from core.doe import DEFAULT_DOE, generate_conditions  # noqa: E402

TEMPLATE = """* 6T SRAM {metric} MC  TT-1  {vop}V
.temp '({temp}) +(0)'
.param VOP='({vop}) +(0)'
.param VWL='({vop}) +(0)'
""" + "".join(
    f".param {fam}_{dev}{i} = ' ({dflt}) + (0)'\n"
    for fam, dflt in (("VTMSKEW", 0), ("VTSGSKEW", 1), ("VTSLSKEW", 1), ("MOMSKEW", 1))
    for dev in ("PU", "PG", "PD") for i in (1, 2)) + ".end\n"


def test_paper_equivalence():
    paper_file = REPO / "python" / "src" / "inhouse_deck_gen.py"
    if not paper_file.exists():
        print("  (논문 코드가 없어 동등성 시험 생략)")
        return
    paper = load("paper_gen", paper_file)
    for mode, metric in (("read", "snmr"), ("write", "vtrip")):
        _, ref = paper.generate_conditions("D", 2000, DEFAULT_DOE["seeds"][mode], metric, "rng")
        mine = generate_conditions(DEFAULT_DOE, mode)
        assert np.array_equal(ref, mine), f"{mode}: 논문 조건과 다름"
        print(f"  {mode}: 논문 조건과 2000 x 9 모두 일치 (checksum {mine.sum():.6f})")


def test_roundtrip():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        tdir = tmp / "tmpl_read"
        tdir.mkdir()
        for v in DEFAULT_DOE["vops"]:
            (tdir / f"02-sp-bc-snmr-TT-1_{v:g}V-125C-LOC-MC.in").write_text(
                TEMPLATE.format(metric="snmr", vop=v, temp=125))
        sim = tmp / "sim_read"
        cfg = json.load(open(ROOT / "configs" / "example_node.json", encoding="utf-8"))
        cfg["work_dir"] = str(tmp / "work")
        cfg["modes"] = {"read": cfg["modes"]["read"]}
        cfg["modes"]["read"].pop("template")  # 옛 방식(.param 치환) 시험
        cfg["modes"]["read"].update(template_dir=str(tdir), deck_out_dir=str(sim),
                                    sim_dirs=[str(sim)])
        cfg["modes"]["read"]["result"]["measure"] = "snmr"
        cp = tmp / "node.json"
        cp.write_text(json.dumps(cfg))

        gen.main(["--config", str(cp), "--preview"])
        gen.main(["--config", str(cp), "--limit", "4"])
        decks = sorted(sim.glob("*.in"))
        assert len(decks) == 20, len(decks)
        assert (sim / "02-sp-bc-snmr-TT-3_0.6V-125C-LOC-MC.in").exists()
        cond = pd.read_csv(sim / "conditions_read.csv")

        # 가짜 시뮬레이션: 덱마다 .mt0
        rng = np.random.default_rng(0)
        for d in decks:
            s = rng.normal(0.1, 0.01, 200)
            body = "\n".join(f"{i + 1} {x:.6e} 125 1" for i, x in enumerate(s))
            d.with_suffix(".mt0").write_text("$DATA1\n.TITLE 'x'\nindex snmr temper alter#\n" + body + "\n")

        extract.main(["--config", str(cp)])
        ds = pd.read_csv(tmp / "work" / "01_extract" / "dataset_read.csv")
        m = ds.merge(cond, left_on="deck", right_on=cond["deck_file"].str[:-3], suffixes=("", "_gen"))
        assert len(m) == 20, len(m)
        for c in ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk", "wl_ratio", "vop"]:
            assert np.allclose(m[c], m[c + "_gen"], atol=1e-6), c
        assert ds["cond_id"].nunique() == 4
        print("  template → 덱 20개 → 가짜 결과 → 01_extract: 9D·Vop 모두 조건표와 일치")

        # 덮어쓰기 방지
        try:
            gen.main(["--config", str(cp), "--limit", "4"])
            raise AssertionError("--force 없이 덮어씀")
        except SystemExit as e:
            assert "--force" in str(e)


# 사내 include.param.tpl / snmr template 과 같은 자리표시자 이름을 쓰는 최소 예시
INCLUDE = """* include
.temp '(#TEMP#) + (#OFFSET_TEMP#)'
.param VOP='(#VDDA#) + (#OFFSET_VDDA#)'
.param VOPP=VOP
""" + "".join(
    f".param {s}_L='(#{s}_L#)*1n + (#SZOFFSET_{s}L#*1n)'\n.param NFIN_{s}='#NFIN_{s}#'\n"
    for s in ("PU", "PG", "PD")) + "".join(
    f".param {fam}_{dev}{i}='(#{fam}_{dev}#) + (#OFFSET_{fam}_{dev}#)'\n"
    for fam in ("VTMSKEW", "VTSLSKEW", "VTSGSKEW", "MOMSKEW")
    for dev in ("PU", "PG", "PD") for i in (1, 2)) + \
    ".param VDDA='(#VDDA#) + (#OFFSET_VDDA#)'\n.param VSSA='(#VSSA#)'\n" \
    ".param VWL='(#VWL#) + (#OFFSET_VDDA#)'\n.param VBL='(#VBL#) + (#OFFSET_VDDA#)'\n"
SNMR = """.param are_you_monte=#ARE_YOU_MONTE#
.lib "/#SPICE_LIB#" #CORNER#
xmpu out in vdda nwell #SPICE_MODEL_PU1# nfin=NFIN_PU L='PU_L'
.dc vu '-VOP' VOP 0.01 sweep monte=#MONTE_EVENT#
.measure dc snmr_diagonal param="1"
.end
"""


def test_placeholder():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        (tmp / "include.param.tpl").write_text(INCLUDE)
        (tmp / "snmr.tpl").write_text(SNMR)
        sim = tmp / "sim"
        cfg = json.load(open(ROOT / "configs" / "example_node.json", encoding="utf-8"))
        cfg["work_dir"] = str(tmp / "work")
        cfg["deck_template"]["include"] = str(tmp / "include.param.tpl")
        vals = cfg["deck_template"]["values"]
        for k, v in list(vals.items()):
            if v == "TODO":
                vals[k] = "lib.l" if k == "SPICE_LIB" else ("tt" if k == "CORNER" else 1)
        cfg["modes"] = {"read": cfg["modes"]["read"]}
        cfg["modes"]["read"].update(template=str(tmp / "snmr.tpl"), deck_out_dir=str(sim),
                                    sim_dirs=[str(sim)])
        cp = tmp / "node.json"
        cp.write_text(json.dumps(cfg))

        gen.main(["--config", str(cp), "--preview"])
        gen.main(["--config", str(cp), "--limit", "3"])
        decks = sorted(sim.glob("*.in"))
        assert len(decks) == 15, len(decks)
        txt = (sim / "SNMR_TT-2_0.6V.in").read_text()
        assert "#" not in txt.replace("* include", ""), "자리표시자가 남음"
        cond = pd.read_csv(sim / "conditions_read.csv")
        r = cond[cond["deck_file"] == "SNMR_TT-2_0.6V.in"].iloc[0]
        assert ".param VOP='(0.6) + (0)'" in txt
        assert f".param VWL='({0.6 * r['wl_ratio']:.6g}) + (0)'" in txt, (r["wl_ratio"], txt[-400:])
        assert 0.8 <= cond["wl_ratio"].min() and cond["wl_ratio"].max() <= 1.0
        # 같은 조건은 모든 Vop 에서 같은 비율
        assert (cond.groupby("deck_no")["wl_ratio"].nunique() == 1).all()
        assert ".temp '(125) + (0)'" in txt
        cond = pd.read_csv(sim / "conditions_read.csv")

        for d in decks:
            body = "\n".join(f"{i + 1} {0.1 + 0.001 * i:.6e} 125 1" for i in range(50))
            d.with_suffix(".mt0").write_text("$DATA1\n.TITLE 'x'\nindex snmr_diagonal temper alter#\n"
                                             + body + "\n")
        extract.main(["--config", str(cp)])
        ds = pd.read_csv(tmp / "work" / "01_extract" / "dataset_read.csv")
        m = ds.merge(cond, left_on="deck", right_on=cond["deck_file"].str[:-3], suffixes=("", "_gen"))
        assert len(m) == 15
        for c in ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk", "wl_ratio", "vop"]:
            assert np.allclose(m[c], m[c + "_gen"], atol=1e-6), c
        assert (ds["temp"] == 125).all()
        assert ds["cond_id"].nunique() == 3
        print("  include + snmr template → 덱 15개 → 01_extract: 9D·Vop·온도 일치")

        # 값이 빠지거나 '#' 짝이 안 맞으면 멈춰야 한다
        cfg["deck_template"]["values"]["NFIN_PU"] = "TODO"
        cp.write_text(json.dumps(cfg))
        try:
            gen.main(["--config", str(cp), "--preview"])
            raise AssertionError("TODO 값을 통과시킴")
        except SystemExit as e:
            assert "NFIN_PU" in str(e)
        cfg["deck_template"]["values"]["NFIN_PU"] = 2
        (tmp / "include.param.tpl").write_text(INCLUDE.replace("(#OFFSET_TEMP#)", "(#OFFSET_TEMP)"))
        cp.write_text(json.dumps(cfg))
        try:
            gen.main(["--config", str(cp), "--preview"])
            raise AssertionError("'#' 오타를 통과시킴")
        except (SystemExit, RuntimeError) as e:
            assert "OFFSET_TEMP" in str(e), e
        print("  TODO 값, '#' 짝 오타 모두 멈춤")


if __name__ == "__main__":
    test_paper_equivalence()
    test_roundtrip()
    test_placeholder()
    print("OK test_gen_decks")
