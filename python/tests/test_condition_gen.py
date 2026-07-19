"""
Tests for the portable condition generator (src/condition_gen.py) and the
in-house deck-gen core (src/inhouse_deck_gen.py).

The whole point of these two files is that the fab-side deck run and our
local sheet run produce IDENTICAL conditions + deck numbering, so results
labelled only by (vop, deck_no) re-attach to conditions without any
condition transcription. These tests pin that contract.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src import condition_gen as cg
from src import inhouse_deck_gen as idg

VOPS = [0.4, 0.5, 0.6, 0.7, 0.8]


def test_determinism_and_seed_sensitivity() -> None:
    for st in ("A", "B", "D"):
        a = cg.generate_conditions(st, 30, seed=42)[1]
        b = cg.generate_conditions(st, 30, seed=42)[1]
        assert np.array_equal(a, b), f"{st} not deterministic"
        c = cg.generate_conditions(st, 30, seed=7)[1]
        assert not np.array_equal(a, c), f"{st} ignored seed"
    print("  [OK] deterministic given seed; different seed -> different conditions")


def test_precision() -> None:
    cols, cond = cg.generate_conditions("D", 40, seed=1)
    i = {c: k for k, c in enumerate(cols)}
    assert np.array_equal(cond[:, :3], np.round(cond[:, :3])), "cn/sk/pu not integer"
    assert np.allclose(cond[:, 3:], np.round(cond[:, 3:], 2)), "loc/mom not 2-dec"
    for c in ("lpu", "l_com", "mpu", "m_com"):
        assert cond[:, i[c]].min() >= 0.7 - 1e-9 and cond[:, i[c]].max() <= 1.3 + 1e-9, c
    for c in ("l_sk", "m_sk"):
        assert np.abs(cond[:, i[c]]).max() <= 0.075 + 1e-9, c
    assert cond[:, 0].min() >= -60 and cond[:, 0].max() <= 60
    print("  [OK] precision: cn/sk/pu integer mV, ratios 2-dec in [0.7,1.3], skew <= 0.075")


def test_design_domain_constraint() -> None:
    """v2.1: com and skew independent (no clamp); box support, spill allowed."""
    cols, cond = cg.generate_conditions("D", 200, seed=3)
    i = {c: k for k, c in enumerate(cols)}
    ok = cg.in_design_domain(cond[:, i["l_com"]], cond[:, i["l_sk"]],
                             cond[:, i["m_com"]], cond[:, i["m_sk"]])
    assert ok.all(), f"{(~ok).sum()} conditions outside the box support"
    # nominal common with nonzero skew IS inside the v2.1 support (no clamp)
    assert cg.in_design_domain(1.0, 0.04, 1.0, 0.0).item()
    assert not cg.in_design_domain(1.0, 0.09, 1.0, 0.0).item()   # |skew| > 0.075
    assert not cg.in_design_domain(1.35, 0.0, 1.0, 0.0).item()   # common out of range
    # derived PG/PD ratios stay within the spill band [0.625, 1.375]
    for com_c, sk_c in (("l_com", "l_sk"), ("m_com", "m_sk")):
        pg = cond[:, i[com_c]] + cond[:, i[sk_c]]
        pd = cond[:, i[com_c]] - cond[:, i[sk_c]]
        assert pg.min() >= 0.625 - 1e-9 and pg.max() <= 1.375 + 1e-9
        assert pd.min() >= 0.625 - 1e-9 and pd.max() <= 1.375 + 1e-9
    # independence sanity: skew must NOT shrink near nominal common (anti-clamp)
    near = np.abs(cond[:, i["l_com"]] - 1.0) < 0.05
    if near.sum() >= 10:
        assert np.abs(cond[near, i["l_sk"]]).max() > 0.04, \
            "skew suppressed near nominal common -- clamp regression?"
    print("  [OK] in_design_domain: independent com/skew box, spill bounded, no clamp")


def test_stage_d_columns_match_utils() -> None:
    """condition_gen and utils.STAGE_DEVICE_COLS must agree on the D layout."""
    from src.utils import STAGE_DEVICE_COLS
    for st in ("A", "B", "D"):
        assert tuple(cg.STAGE_COLUMNS[st]) == STAGE_DEVICE_COLS[st], st
    assert "lpg" not in cg.STAGE_COLUMNS["D"], "v1.0 independent-lpg/lpd layout is retired"
    print("  [OK] Stage-D layout (com/skew) consistent across condition_gen and utils")


def test_frozen_core_identical_across_files() -> None:
    """condition_gen and inhouse_deck_gen must share a byte-identical core."""
    for st in ("A", "B", "D"):
        for metric in ("snmr", "vtrip"):
            c1 = cg.generate_conditions(st, 50, seed=42, metric=metric)[1]
            c2 = idg.generate_conditions(st, 50, seed=42, metric=metric)[1]
            assert np.array_equal(c1, c2), f"core differs: {st}/{metric}"
    print("  [OK] FROZEN CORE identical: condition_gen == inhouse_deck_gen")


def test_deck_numbering_restarts_per_vop() -> None:
    cols, cond = cg.generate_conditions("D", 20, seed=42)
    recs = cg.conditions_to_records(cols, cond, VOPS, deck_prefix="TT", start=1)
    # each Vop block should have deck_no 1..20 in the same condition order
    by_vop = {}
    for r in recs:
        by_vop.setdefault(r["vop"], []).append(r)
    for v, block in by_vop.items():
        assert [r["deck_no"] for r in block] == list(range(1, 21)), f"vop {v} numbering"
        assert block[0]["deck_id"] == "TT-1" and block[-1]["deck_id"] == "TT-20"
    # TT-k at different Vops must carry the SAME condition (numbering restarts)
    for k in (1, 7, 20):
        rows_k = [r for r in recs if r["deck_no"] == k]
        for c in cols:
            vals = {r[c] for r in rows_k}
            assert len(vals) == 1, f"TT-{k} condition {c} not constant across Vop"
    print("  [OK] TT-N restarts each Vop, same condition order (matched by (vop,deck_no))")


def test_sheet_and_fab_records_match() -> None:
    """Our sheet records and the fab iter_decks must agree field-by-field."""
    cols, cond = cg.generate_conditions("D", 20, seed=42, metric="snmr")
    ours = cg.conditions_to_records(cols, cond, VOPS, deck_prefix="TT", start=1)
    fab = list(idg.iter_decks("D", 20, VOPS, seed=42, metric="snmr",
                              method="rng", deck_prefix="TT", start=1))
    assert len(ours) == len(fab) == 20 * len(VOPS)
    keys = ["deck_id", "vop"] + cols
    for a, b in zip(ours, fab):
        for k in keys:
            assert a[k] == b[k], f"mismatch {k}: {a[k]} vs {b[k]}"
    print(f"  [OK] sheet == fab records ({len(ours)} rows, 0 mismatches)")


def test_condition_to_deck_params() -> None:
    """PG=cn+sk, PD=cn-sk, PU=pu; ratios split as common +- skew (v2.1)."""
    rec = {"cn": -30, "sk": 8, "pu": 40, "vop": 0.6,
           "lpu": 0.9, "l_com": 1.05, "l_sk": 0.05,
           "mpu": 1.2, "m_com": 0.80, "m_sk": -0.06}
    p = idg.condition_to_deck_params(rec)
    assert p["VTMSKEW_PG"] == -30 + 8 and p["VTMSKEW_PD"] == -30 - 8
    assert p["VTMSKEW_PU"] == 40 and p["VOP"] == 0.6
    assert np.isclose(p["VTSLSKEW_PG"], 1.05 + 0.05)
    assert np.isclose(p["VTSLSKEW_PD"], 1.05 - 0.05)
    assert np.isclose(p["VTSLSKEW_PU"], 0.9)
    assert np.isclose(p["MOMSKEW_PG"], 0.80 - 0.06)
    assert np.isclose(p["MOMSKEW_PD"], 0.80 + 0.06)
    assert np.isclose(p["MOMSKEW_PU"], 1.2)
    # Stage A record (no sk/loc/mom) -> PG=PD=cn, ratios default 1.0
    pa = idg.condition_to_deck_params({"cn": 12, "pu": -5, "vop": 0.5})
    assert pa["VTMSKEW_PG"] == 12 and pa["VTMSKEW_PD"] == 12
    assert pa["VTSLSKEW_PU"] == 1.0 and pa["MOMSKEW_PD"] == 1.0
    print("  [OK] condition_to_deck_params: PG/PD Vth skew + common+-skew ratios, Stage-A default")


def test_deck_param_substitution() -> None:
    """The in-house deck syntax  .param X = '(A) + B'  -- only A is replaced."""
    ref = ("* ref\n"
           ".param VTMSKEW_PU1 = '(0.0) + 0.005'\n"
           ".param VTMSKEW_PU2 = '(0.0) + 0.005'\n"
           ".param VTMSKEW_PG1 = '(0.0) + 0.003'\n"
           ".param VTMSKEW_PG2 = '(0.0) + 0.003'\n"
           ".param VTMSKEW_PD1 = '(0.0) + 0.003'\n"
           ".param VTMSKEW_PD2 = '(0.0) + 0.003'\n"
           ".param VTSLSKEW_PU1 = '(1.0) + 0.0'\n"
           ".param VTSLSKEW_PU2 = '(1.0) + 0.0'\n"
           ".param VTSLSKEW_PG1 = '(1.0) + 0.0'\n"
           ".param VTSLSKEW_PG2 = '(1.0) + 0.0'\n"
           ".param VTSLSKEW_PD1 = '(1.0) + 0.0'\n"
           ".param VTSLSKEW_PD2 = '(1.0) + 0.0'\n"
           ".param MOMSKEW_PU1 = '(1.0) + 0.0'\n"
           ".param MOMSKEW_PU2 = '(1.0) + 0.0'\n"
           ".param MOMSKEW_PG1 = '(1.0) + 0.0'\n"
           ".param MOMSKEW_PG2 = '(1.0) + 0.0'\n"
           ".param MOMSKEW_PD1 = '(1.0) + 0.0'\n"
           ".param MOMSKEW_PD2 = '(1.0) + 0.0'\n"
           ".end\n")
    rec = {"cn": -30, "sk": 8, "pu": 40, "vop": 0.6,
           "lpu": 0.9, "l_com": 1.05, "l_sk": 0.05,
           "mpu": 1.2, "m_com": 0.80, "m_sk": -0.06}
    out = idg.replace_params(ref, idg.deck_param_strings(rec), "ref")

    # mV -> V for Vth; the trailing '+ B' term must survive untouched
    assert ".param VTMSKEW_PU1 = '(0.040000) + 0.005'" in out
    assert ".param VTMSKEW_PG1 = '(-0.022000) + 0.003'" in out   # (cn+sk)/1000
    assert ".param VTMSKEW_PD1 = '(-0.038000) + 0.003'" in out   # (cn-sk)/1000
    assert ".param VTSLSKEW_PG2 = '(1.100000) + 0.0'" in out     # l_com + l_sk
    assert ".param MOMSKEW_PD2 = '(0.860000) + 0.0'" in out      # m_com - m_sk
    assert out.count("+ 0.005'") == 2 and out.count("+ 0.003'") == 4
    assert ".end" in out and out.count(".param") == ref.count(".param")

    # a reference deck missing a parameter must FAIL LOUDLY, not silently pass
    broken = ref.replace(".param MOMSKEW_PD2 = '(1.0) + 0.0'\n", "")
    try:
        idg.replace_params(broken, idg.deck_param_strings(rec), "broken")
    except RuntimeError as e:
        assert "MOMSKEW_PD" in str(e)
    else:
        raise AssertionError("missing parameter did not raise")
    print("  [OK] deck substitution: only the parenthesized value changes; "
          "missing param raises")


def test_grouped_split_blocks_mirror_leakage() -> None:
    """Mirror twins (same Sobol row, flipped cn/pu sign) must not straddle the split."""
    from src.data import grouped_train_test_split
    rng = np.random.default_rng(0)
    base = rng.random((50, 7))                       # 50 base Sobol points
    X, groups = [], []
    for k in range(50):
        for cn_s, pu_s in ((+1, +1), (-1, +1), (-1, -1), (+1, -1)):
            X.append(np.concatenate([[cn_s * 40.0, pu_s * 30.0], base[k]]))
            groups.append(k)
    X = np.asarray(X); groups = np.asarray(groups)
    y = np.zeros((len(X), 2))
    Xtr, Xte, _, _ = grouped_train_test_split(X, y, groups, test_frac=0.2, seed=1)
    # no base point (the 7 shared coords) may appear on both sides
    tr = {tuple(np.round(r[2:], 12)) for r in Xtr}
    te = {tuple(np.round(r[2:], 12)) for r in Xte}
    assert not (tr & te), f"{len(tr & te)} mirror groups leaked across the split"
    assert len(Xte) == 10 * 4, "grouped split must move whole mirror groups"
    print("  [OK] grouped_train_test_split: 0 mirror twins leaked (whole groups moved)")


if __name__ == "__main__":
    print("=== test_condition_gen ===")
    test_determinism_and_seed_sensitivity()
    test_precision()
    test_design_domain_constraint()
    test_stage_d_columns_match_utils()
    test_frozen_core_identical_across_files()
    test_deck_numbering_restarts_per_vop()
    test_sheet_and_fab_records_match()
    test_condition_to_deck_params()
    test_deck_param_substitution()
    test_grouped_split_blocks_mirror_leakage()
    print("\n=== ALL CONDITION-GEN TESTS PASSED ===")
