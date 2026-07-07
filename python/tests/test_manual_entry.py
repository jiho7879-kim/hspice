"""
Tests for the hand-entry ingestion path (src/hspice_io.parse_manual_csv).

The real bottleneck in Phase 2 is manual transcription of simulator results
(sim is fast, but results are copied to a notebook by hand).  These verify
that both the simple and lobe schemas convert correctly, that Vwl->WLUD and
n_mc->SEM derivations are right, and that the shipped templates parse.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.hspice_io import parse_manual_csv, write_entry_templates
from src.utils import effective_mu_sigma, z_eff_from_lobes


def _write(tmp: Path, name: str, text: str) -> Path:
    p = tmp / name
    p.write_text(text, encoding="utf-8")
    return p


def test_simple_schema() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        p = _write(tmp, "s.csv",
                   "common_N_shift,PU_shift,Vop,mu_SNMR,sigma_SNMR,n_mc\n"
                   "-60,60,0.6,0.072,0.020,2000\n"
                   "0,0,0.6,0.118,0.0198,500\n")
        d = parse_manual_csv(p)
    assert d["schema"] == "simple"
    assert d["X"].shape == (2, 3) and d["y"].shape == (2, 2)
    assert np.allclose(d["y"][0], [0.072, 0.020])
    # SEM derivation: sem_mu = sigma/sqrt(N); N=500 row noisier than N=2000
    assert d["y_noise"] is not None
    assert np.isclose(d["y_noise"][0, 0], 0.020 / np.sqrt(2000))
    assert d["y_noise"][1, 0] > d["y_noise"][0, 0]
    print("  [OK] simple schema + n_mc -> SEM")


def test_lobe_schema_matches_effective() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        p = _write(tmp, "l.csv",
                   "common_N_shift,PU_shift,Vop,mu_L,sigma_L,mu_R,sigma_R,rho_LR\n"
                   "-60,60,0.6,0.073,0.0205,0.0725,0.0201,-0.35\n")
        d = parse_manual_csv(p)
    assert d["schema"] == "lobe"
    mu_e, sg_e = effective_mu_sigma(0.073, 0.0205, 0.0725, 0.0201, -0.35)
    assert np.allclose(d["y"][0], [mu_e, sg_e])
    # effective z equals the closed-form util
    z = z_eff_from_lobes(0.073, 0.0205, 0.0725, 0.0201, -0.35)
    assert np.isclose(d["y"][0, 0] / d["y"][0, 1], float(z))
    assert d["rho_LR"] is not None and np.isclose(d["rho_LR"][0], -0.35)
    print("  [OK] lobe schema -> effective (mu,sigma), z matches util")


def test_vwl_to_wlud() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        p = _write(tmp, "v.csv",
                   "common_N_shift,PU_shift,Vop,Vwl,mu_SNMR,sigma_SNMR\n"
                   "0,0,0.8,0.72,0.12,0.02\n")   # WLUD = 0.72/0.8 = 0.9
        d = parse_manual_csv(p)
    assert d["X"].shape == (1, 4)
    assert np.isclose(d["X"][0, 3], 0.9), "Vwl not converted to WLUD ratio"
    print("  [OK] Vwl -> WLUD ratio conversion")


def test_comment_and_aliases() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # header aliases + comment lines + blank line
        p = _write(tmp, "c.csv",
                   "# note: my run\n"
                   "cn,pu,vop,mu,sigma\n"
                   "10,-10,0.7,0.10,0.02\n"
                   "\n"
                   "# mid-file comment\n"
                   "20,-20,0.7,0.09,0.02\n")
        d = parse_manual_csv(p)
    assert d["X"].shape == (2, 3)
    assert np.allclose(d["X"][:, 0], [10, 20])
    print("  [OK] comment lines + column aliases + blank rows")


def test_missing_columns_raises() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        p = _write(tmp, "bad.csv", "common_N_shift,PU_shift,mu_SNMR\n-60,60,0.07\n")
        try:
            parse_manual_csv(p)
        except ValueError as e:
            assert "vop" in str(e).lower() or "base" in str(e).lower()
            print("  [OK] missing base column raises")
            return
        assert False, "expected ValueError for missing Vop"


def test_shipped_templates_parse() -> None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        write_entry_templates(tmp)
        ds = parse_manual_csv(tmp / "manual_entry_standard.csv")
        dl = parse_manual_csv(tmp / "manual_entry_lobe.csv")
    assert ds["schema"] == "simple" and ds["X"].shape[0] == 2
    assert dl["schema"] == "lobe" and dl["rho_LR"] is not None
    print("  [OK] shipped templates parse (standard + lobe)")


if __name__ == "__main__":
    print("=== test_manual_entry ===")
    test_simple_schema()
    test_lobe_schema_matches_effective()
    test_vwl_to_wlud()
    test_comment_and_aliases()
    test_missing_columns_raises()
    test_shipped_templates_parse()
    print("\n=== ALL MANUAL-ENTRY TESTS PASSED ===")
