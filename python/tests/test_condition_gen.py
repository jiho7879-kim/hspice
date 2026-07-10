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
    assert np.array_equal(cond[:, :3], np.round(cond[:, :3])), "cn/sk/pu not integer"
    assert np.allclose(cond[:, 3:], np.round(cond[:, 3:], 2)), "loc/mom not 2-dec"
    assert cond[:, 3:].min() >= 0.7 - 1e-9 and cond[:, 3:].max() <= 1.3 + 1e-9
    assert cond[:, 0].min() >= -60 and cond[:, 0].max() <= 60
    print("  [OK] precision: cn/sk/pu integer mV, loc/mom 2-dec in [0.7,1.3]")


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
    """PG=cn+sk, PD=cn-sk, PU=pu; loc/mom mapped; Stage A has no sk."""
    rec = {"cn": -30, "sk": 8, "pu": 40, "vop": 0.6,
           "lpu": 0.9, "lpg": 1.1, "lpd": 1.0, "mpu": 1.2, "mpg": 0.8, "mpd": 1.0}
    p = idg.condition_to_deck_params(rec)
    assert p["VTMSKEW_PG1"] == -30 + 8 and p["VTMSKEW_PD1"] == -30 - 8
    assert p["VTMSKEW_PU1"] == 40 and p["VOP"] == 0.6
    assert p["VTSLSKEW_PG1"] == 1.1 and p["MOMSKEW_PU1"] == 1.2
    # Stage A record (no sk/loc/mom) -> PG=PD=cn, ratios default 1.0
    pa = idg.condition_to_deck_params({"cn": 12, "pu": -5, "vop": 0.5})
    assert pa["VTMSKEW_PG1"] == 12 and pa["VTMSKEW_PD1"] == 12
    assert pa["VTSLSKEW_PU1"] == 1.0 and pa["MOMSKEW_PD1"] == 1.0
    print("  [OK] condition_to_deck_params: PG/PD skew split, ratio mapping, Stage-A default")


if __name__ == "__main__":
    print("=== test_condition_gen ===")
    test_determinism_and_seed_sensitivity()
    test_precision()
    test_frozen_core_identical_across_files()
    test_deck_numbering_restarts_per_vop()
    test_sheet_and_fab_records_match()
    test_condition_to_deck_params()
    print("\n=== ALL CONDITION-GEN TESTS PASSED ===")
