"""
Tests for PrimeSim/HSPICE MC .mt0 parsing (src/primesim_io.py).

Real .mt0 files are in-house; these use synthetic fixtures that reproduce
the two reported pain points:
  1. rows wrapped across multiple physical lines after ~5 columns
  2. Vtrip written to separate left/right files needing per-index min
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.primesim_io import (
    parse_mt0_wrapped, mc_stats, vtrip_min_stats,
    parse_in_deck, parse_result_md, merge_deck_dir,
)


_DECK_TMPL = """.option post=0 co=128
.temp '(25) +(0)'
.param VOP='({vop}) +(0)'
.param VTMSKEW_PU1=' ({pu}) + (0)'
.param VTMSKEW_PG1=' ({pg}) + (0)'
.param VTMSKEW_PD1=' ({pd}) + (0)'
.param VTMSKEW_PU2=' ({pu}) + (0)'
.param VTMSKEW_PG2=' ({pg}) + (0)'
.param VTMSKEW_PD2=' ({pd}) + (0)'
.param VTSGSKEW_PU1=' ({sg}) + (0)'
.param VTSGSKEW_PG1=' ({sg}) + (0)'
.param VTSGSKEW_PD1=' ({sg}) + (0)'
.param VTSGSKEW_PU2=' ({sg}) + (0)'
.param VTSGSKEW_PG2=' ({sg}) + (0)'
.param VTSGSKEW_PD2=' ({sg}) + (0)'
.param VTSLSKEW_PU1=' ({sl}) + (0)'
.param VTSLSKEW_PG1=' ({sl}) + (0)'
.param VTSLSKEW_PD1=' ({sl}) + (0)'
.param VTSLSKEW_PU2=' ({sl}) + (0)'
.param VTSLSKEW_PG2=' ({sl}) + (0)'
.param VTSLSKEW_PD2=' ({sl}) + (0)'
.param MOMSKEW_PU1=' ({mom}) + (0)'
.param MOMSKEW_PG1=' ({mom}) + (0)'
.param MOMSKEW_PD1=' ({mom}) + (0)'
.param MOMSKEW_PU2=' ({mom}) + (0)'
.param MOMSKEW_PG2=' ({mom}) + (0)'
.param MOMSKEW_PD2=' ({mom}) + (0)'
.end
"""


def _deck(vop=0.75, pu=0, pg=0, pd=0, sg=1, sl=1, mom=1):
    return _DECK_TMPL.format(vop=vop, pu=pu, pg=pg, pd=pd, sg=sg, sl=sl, mom=mom)


def _write_wrapped_mt0(path: Path, col_names, data, per_line=5, header=True):
    """Write an .mt0-style file wrapping tokens after `per_line` columns.

    data: (n_rows, n_cols) array. Both the header and each data row are
    wrapped after `per_line` tokens, mimicking PrimeSim's auto-wrap.
    """
    lines = ["$DATA1 SOURCE='PrimeSim' VERSION='X'", ".TITLE '* mc run'"]

    def wrap(tokens):
        out = []
        for i in range(0, len(tokens), per_line):
            chunk = tokens[i:i + per_line]
            out.append("   " + "   ".join(chunk))
        return out

    if header:
        lines += wrap(list(col_names))
    for row in data:
        lines += wrap([f"{v:.12e}" for v in row])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_wrap_reshape_roundtrip() -> None:
    rng = np.random.default_rng(0)
    cols = ["index", "snmr", "temper", "alter#", "vread", "iread", "extra"]
    n = 40
    data = np.zeros((n, len(cols)))
    data[:, 0] = np.arange(1, n + 1)             # index
    data[:, 1] = rng.normal(0.12, 0.02, n)       # snmr
    data[:, 2] = 25.0                            # temper
    data[:, 3] = 1.0                            # alter#
    data[:, 4:] = rng.normal(0.3, 0.05, (n, 3))

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "snm.mt0"
        _write_wrapped_mt0(p, cols, data, per_line=5)  # 7 cols -> wraps
        parsed, order = parse_mt0_wrapped(p)

    assert order == [c.lower() for c in cols], f"columns: {order}"
    assert len(parsed["snmr"]) == n
    assert np.allclose(parsed["index"], np.arange(1, n + 1))
    assert np.allclose(parsed["snmr"], data[:, 1])
    print(f"  [OK] wrapped {len(cols)}-col file reshaped correctly (n={n})")


def test_wrap_various_widths() -> None:
    """Parser must be immune to the wrap width."""
    cols = ["index", "snmr", "temper", "alter#", "a", "b", "c", "d"]
    n = 25
    data = np.arange(n * len(cols), dtype=float).reshape(n, len(cols))
    for per_line in (3, 4, 5, 8, 100):  # 100 = no wrap
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "w.mt0"
            _write_wrapped_mt0(p, cols, data, per_line=per_line)
            parsed, _ = parse_mt0_wrapped(p)
        assert np.allclose(parsed["snmr"], data[:, 1]), f"per_line={per_line}"
        assert len(parsed["a"]) == n
    print("  [OK] wrap-agnostic across widths {3,4,5,8,none}")


def test_snmr_stats() -> None:
    rng = np.random.default_rng(1)
    cols = ["index", "snmr", "temper", "alter#", "x", "y"]
    n = 2000
    vals = rng.normal(0.115, 0.019, n)
    data = np.zeros((n, len(cols)))
    data[:, 0] = np.arange(1, n + 1)
    data[:, 1] = vals
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "snm.mt0"
        _write_wrapped_mt0(p, cols, data, per_line=5)
        r = mc_stats(p, measure="snmr", snm_floor=0.0)
    assert abs(r["mu"] - vals.mean()) < 1e-9
    assert abs(r["sigma"] - vals.std(ddof=1)) < 1e-9
    assert r["n"] == n and r["frac_below_floor"] == 0.0
    print(f"  [OK] SNMR mc_stats mu={r['mu']:.5f} sigma={r['sigma']:.5f}")


def test_vtrip_min_join_by_index() -> None:
    """Per-index min(left,right), then mean/median — with shuffled right."""
    rng = np.random.default_rng(2)
    n = 1500
    cols = ["index", "vtrip", "temper", "alter#", "z", "w"]
    idx = np.arange(1, n + 1)
    vl = rng.normal(0.30, 0.03, n)
    vr = rng.normal(0.31, 0.03, n)

    def make(idx_arr, v):
        d = np.zeros((len(idx_arr), len(cols)))
        d[:, 0] = idx_arr
        d[:, 1] = v
        d[:, 4:] = rng.normal(0, 1, (len(idx_arr), 2))
        return d

    # shuffle the right file's row order to exercise index-join
    perm = rng.permutation(n)
    with tempfile.TemporaryDirectory() as td:
        pl = Path(td) / "vtrip_left.mt0"
        pr = Path(td) / "vtrip_right.mt0"
        _write_wrapped_mt0(pl, cols, make(idx, vl), per_line=4)
        _write_wrapped_mt0(pr, cols, make(idx[perm], vr[perm]), per_line=5)
        r = vtrip_min_stats(pl, pr, measure="vtrip")

    expected = np.minimum(vl, vr)  # aligned by index
    assert r["n"] == n
    assert abs(r["mu"] - expected.mean()) < 1e-9, "index-join min wrong"
    assert abs(r["median"] - np.median(expected)) < 1e-9
    # min of two ~N(0.30/0.31) is below both means
    assert r["mu"] < vl.mean() and r["mu"] < vr.mean()
    print(f"  [OK] Vtrip min-join mu={r['mu']:.5f} median={r['median']:.5f} "
          f"(< left {vl.mean():.5f}, right {vr.mean():.5f})")


def test_vtrip_distinct_columns_a0_a1() -> None:
    """In-house layout: left value = bwrm_1 in a0, right value = bwrm_2 in a1
    (a1's bwrm_1 is pinned to Vop and must be ignored)."""
    rng = np.random.default_rng(5)
    n = 1200
    vop = 0.8
    idx = np.arange(1, n + 1)
    left_bwrm1 = rng.normal(0.30, 0.03, n)    # a0: the value we want
    right_bwrm2 = rng.normal(0.31, 0.03, n)   # a1: the value we want

    # a0.mt0 columns: index, bwrm_1 (wanted), bwrm_2 (unused here), temper
    a0 = np.column_stack([idx, left_bwrm1, rng.normal(0.5, 0.05, n),
                          np.full(n, 25.0)])
    # a1.mt0 columns: index, bwrm_1 (== Vop, meaningless), bwrm_2 (wanted), temper
    a1 = np.column_stack([idx, np.full(n, vop), right_bwrm2,
                          np.full(n, 25.0)])
    cols = ["index", "bwrm_1", "bwrm_2", "temper"]

    with tempfile.TemporaryDirectory() as td:
        pa0 = Path(td) / "cell_a0.mt0"
        pa1 = Path(td) / "cell_a1.mt0"
        _write_wrapped_mt0(pa0, cols, a0, per_line=5)
        _write_wrapped_mt0(pa1, cols, a1, per_line=5)
        r = vtrip_min_stats(pa0, pa1,
                            measure_left="bwrm_1", measure_right="bwrm_2")

    expected = np.minimum(left_bwrm1, right_bwrm2)
    assert r["n"] == n
    assert abs(r["mu"] - expected.mean()) < 1e-9, "picked wrong columns"
    assert abs(r["median"] - np.median(expected)) < 1e-9
    # sanity: if a1's pinned bwrm_1 (=Vop=0.8) had leaked in, min would be
    # dominated by ~0.30 and mu would differ; guard against that regression
    assert r["mu"] < 0.31, "a1.bwrm_1 (Vop) may have leaked in"
    print(f"  [OK] a0.bwrm_1 x a1.bwrm_2 distinct-column min mu={r['mu']:.5f}")


def test_vtrip_positional_when_no_index() -> None:
    """No index column -> positional pairing (equal length required)."""
    rng = np.random.default_rng(3)
    n = 500
    cols = ["vtrip", "temper"]   # no index
    vl = rng.normal(0.30, 0.03, n)
    vr = rng.normal(0.31, 0.03, n)
    with tempfile.TemporaryDirectory() as td:
        pl = Path(td) / "l.mt0"
        pr = Path(td) / "r.mt0"
        _write_wrapped_mt0(pl, cols, np.column_stack([vl, np.full(n, 25.0)]), per_line=5)
        _write_wrapped_mt0(pr, cols, np.column_stack([vr, np.full(n, 25.0)]), per_line=5)
        r = vtrip_min_stats(pl, pr, measure="vtrip")
    assert abs(r["mu"] - np.minimum(vl, vr).mean()) < 1e-9
    print("  [OK] Vtrip positional pairing (no index column)")


def test_summary_block_ignored() -> None:
    """A trailing text-labelled summary block must not corrupt the data."""
    cols = ["index", "snmr"]
    n = 100
    rng = np.random.default_rng(4)
    vals = rng.normal(0.12, 0.02, n)
    data = np.column_stack([np.arange(1, n + 1), vals])
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "snm.mt0"
        _write_wrapped_mt0(p, cols, data, per_line=5)
        # append a summary block (text label + numbers) as some tools do
        with open(p, "a", encoding="utf-8") as f:
            f.write("mean_snmr\n   1.200000e-01\nsigma_snmr\n   2.000000e-02\n")
        r = mc_stats(p, measure="snmr")
    assert r["n"] == n, f"summary block leaked into data: n={r['n']}"
    assert abs(r["mu"] - vals.mean()) < 1e-9
    print("  [OK] trailing summary block ignored (n stays exact)")


def test_parse_in_deck() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cond_007.in"
        p.write_text(_deck(vop=0.7, pu=30, pg=-40, pd=-40, sg=1.5, sl=2.0, mom=0.9),
                     encoding="utf-8")
        row = parse_in_deck(p)
    assert row["deck"] == "cond_007"
    assert abs(row["VOP"] - 0.7) < 1e-12
    assert abs(row["temp"] - 25) < 1e-12
    assert abs(row["VTMSKEW_PU"] - 30) < 1e-12
    assert abs(row["VTMSKEW_PG"] - (-40)) < 1e-12
    # project-convention convenience: common_N = PG, PU_shift = PU
    assert abs(row["common_N_shift"] - (-40)) < 1e-12
    assert abs(row["PU_shift"] - 30) < 1e-12
    assert abs(row["VTSGSKEW_PU"] - 1.5) < 1e-12
    assert abs(row["VTSLSKEW_PU"] - 2.0) < 1e-12
    assert abs(row["MOMSKEW_PU"] - 0.9) < 1e-12
    print("  [OK] parse_in_deck: VTMSKEW/VTSG/VTSL/MOM + VOP/temp + convenience")


def test_deck_instance_mismatch_flag() -> None:
    """PU1 != PU2 should be flagged (normally they are equal)."""
    deck = _deck(pu=10).replace(
        ".param VTMSKEW_PU2=' (10) + (0)'", ".param VTMSKEW_PU2=' (14) + (0)'")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "d.in"
        p.write_text(deck, encoding="utf-8")
        row = parse_in_deck(p)
    assert "VTMSKEW_PU_mismatch" in row
    assert abs(row["VTMSKEW_PU_mismatch"] - 4.0) < 1e-9
    assert abs(row["VTMSKEW_PU"] - 10.0) < 1e-9  # representative = instance 1
    print("  [OK] instance 1/2 mismatch flagged")


def test_merge_deck_dir() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # two decks + matching result .md (stem contained, loose match)
        (tmp / "cond_001.in").write_text(_deck(pu=0, pg=0), encoding="utf-8")
        (tmp / "cond_002.in").write_text(_deck(pu=30, pg=-40), encoding="utf-8")
        (tmp / "cond_001_result.md").write_text(
            "# hand notes\nmu_SNMR = 0.118\nsigma_SNMR = 0.0198\n", encoding="utf-8")
        (tmp / "cond_002_result.md").write_text(
            "mu_SNMR: 0.072\nsigma_SNMR: 0.0203\nvtrip_min_mu 0.281\n", encoding="utf-8")
        df = merge_deck_dir(tmp, out_csv=tmp / "merged.csv")

    assert len(df) == 2
    r1 = df[df["deck"] == "cond_001"].iloc[0]
    r2 = df[df["deck"] == "cond_002"].iloc[0]
    assert abs(r1["mu_snmr"] - 0.118) < 1e-9        # from result md (lowercased)
    assert abs(r2["common_N_shift"] - (-40)) < 1e-9  # from deck (project convention)
    assert abs(r2["vtrip_min_mu"] - 0.281) < 1e-9
    assert r1["result_file"] == "cond_001_result.md"
    print("  [OK] merge_deck_dir: deck conditions + result md -> one table")


def test_merge_missing_result() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "cond_009.in").write_text(_deck(), encoding="utf-8")
        df = merge_deck_dir(tmp)   # no .md present
    assert len(df) == 1 and df.iloc[0]["result_file"] == ""
    assert "VTMSKEW_PU" in df.columns  # conditions still populated
    print("  [OK] merge with no result file leaves result columns blank")


if __name__ == "__main__":
    print("=== test_primesim_io ===")
    test_wrap_reshape_roundtrip()
    test_wrap_various_widths()
    test_snmr_stats()
    test_vtrip_min_join_by_index()
    test_vtrip_distinct_columns_a0_a1()
    test_vtrip_positional_when_no_index()
    test_summary_block_ignored()
    test_parse_in_deck()
    test_deck_instance_mismatch_flag()
    test_merge_deck_dir()
    test_merge_missing_result()
    print("\n=== ALL PRIMESIM-IO TESTS PASSED ===")
