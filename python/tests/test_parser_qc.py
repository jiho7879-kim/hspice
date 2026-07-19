"""
Tests for HSPICE parser QC extensions (src/hspice_io.py) and the
noise/censoring npz round-trip (src/data.py).

Real .mt0 files arrive in Phase-2 Step A; until then these use synthetic
MC sample vectors so the statistics/QC code is validated and ready.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.hspice_io import (
    bootstrap_sem, condition_qc, lobe_mc_summary, write_qc_report,
)
from src.utils import z_eff_from_lobes
from src.data import save_with_noise, load_with_noise, load_intermediate


def test_bootstrap_sem_matches_gaussian() -> None:
    """Bootstrap SEM ~ Gaussian closed form on Gaussian data."""
    rng = np.random.default_rng(0)
    n, sigma = 4000, 0.02
    x = rng.normal(0.1, sigma, n)
    sem_mean = bootstrap_sem(x, "mean", n_boot=800)
    sem_std = bootstrap_sem(x, "std", n_boot=800)
    # closed forms
    assert abs(sem_mean - sigma / np.sqrt(n)) < 0.15 * sigma / np.sqrt(n)
    assert abs(sem_std - sigma / np.sqrt(2 * n)) < 0.2 * sigma / np.sqrt(2 * n)
    print(f"  [OK] bootstrap SEM vs Gaussian: mean {sem_mean:.2e}, std {sem_std:.2e}")


def test_condition_qc_flags() -> None:
    """Normal data passes; bimodal fail-mix is flagged."""
    rng = np.random.default_rng(1)
    good = rng.normal(0.12, 0.02, 5000)
    q = condition_qc(good, snm_floor=0.0)
    assert q["normal_ok"], "clean Gaussian should pass AD"
    assert q["frac_below_floor"] < 1e-3
    assert abs(q["skew"]) < 0.2

    # fail-mixed: 5% of samples pushed below zero (read-fail contamination)
    bad = good.copy()
    k = int(0.05 * len(bad))
    bad[:k] = rng.normal(-0.05, 0.01, k)
    qb = condition_qc(bad, snm_floor=0.0)
    assert qb["frac_below_floor"] > 0.01, "should detect fail-mixing"
    assert (not qb["normal_ok"]) or abs(qb["skew"]) > 0.3
    print(f"  [OK] condition_qc: clean normal_ok={q['normal_ok']}, "
          f"failmix frac={qb['frac_below_floor']:.3f}")


def test_lobe_summary_consistency() -> None:
    """lobe_mc_summary's effective ratio equals the closed-form Z_eff."""
    rng = np.random.default_rng(2)
    n = 8000
    # anticorrelated lobes (the dangerous case from review A1)
    rho_true = -0.4
    cov = [[0.02**2, rho_true * 0.02 * 0.022],
           [rho_true * 0.02 * 0.022, 0.022**2]]
    LR = rng.multivariate_normal([0.13, 0.125], cov, size=n)
    L, R = LR[:, 0], LR[:, 1]

    s = lobe_mc_summary(L, R, snm_floor=0.0)
    # ratio identity
    assert abs(s["mu_eff"] / s["sigma_eff"] - s["z_eff"]) < 1e-6
    # rho recovered
    assert abs(s["rho_LR"] - rho_true) < 0.05
    # z_eff consistent with util from the summarized moments
    z_ref = float(z_eff_from_lobes(s["mu_L"], s["sigma_L"],
                                   s["mu_R"], s["sigma_R"], s["rho_LR"]))
    assert abs(s["z_eff"] - z_ref) < 1e-9
    # effective z must be BELOW the naive min-stats z (optimism removed)
    mn = np.minimum(L, R)
    z_naive = mn.mean() / mn.std(ddof=1)
    assert s["z_eff"] < z_naive, "effective z should be stricter than min-stats"
    assert s["sem_mu_eff"] > 0 and s["sem_sigma_eff"] > 0
    print(f"  [OK] lobe summary: z_eff={s['z_eff']:.3f} < z_naive={z_naive:.3f} "
          f"(rho={s['rho_LR']:.2f})")


def test_qc_report_written() -> None:
    rng = np.random.default_rng(3)
    rows = []
    for job in range(1, 6):
        x = rng.normal(0.12, 0.02, 2000)
        q = condition_qc(x)
        q.update(job_id=job, cn=-60 + 20 * job, pu=10 * job, vop=0.6)
        rows.append(q)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "qc.md"
        write_qc_report(rows, p)
        txt = p.read_text(encoding="utf-8")
        assert "QC report" in txt and "conditions: **5**" in txt
        assert txt.count("|") > 20  # table rendered
    print("  [OK] write_qc_report renders markdown table")


def test_save_load_with_noise_roundtrip() -> None:
    rng = np.random.default_rng(4)
    N, d = 30, 3
    X = rng.uniform(-60, 60, (N, d))
    y = np.column_stack([rng.uniform(0.05, 0.2, N), rng.uniform(0.01, 0.03, N)])
    y_noise = np.column_stack([np.full(N, 5e-4), np.full(N, 2e-4)])
    n_mc = np.full(N, 2000)
    censored = rng.random(N) < 0.1

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ds.npz"
        save_with_noise(p, X, y, y_noise=y_noise, n_mc=n_mc, censored=censored,
                        extras={"rho_LR": rng.uniform(-0.5, 0.5, N)})
        # new loader sees everything
        d_ = load_with_noise(p)
        assert set(["X", "y", "y_noise", "n_mc", "censored", "rho_LR"]).issubset(d_)
        assert np.allclose(d_["y_noise"], y_noise)
        assert d_["censored"].dtype == bool
        # old loader still works (backward compat)
        X2, y2 = load_intermediate(p)
        assert np.allclose(X2, X) and np.allclose(y2, y)
    print("  [OK] save_with_noise / load_with_noise roundtrip + backward compat")


if __name__ == "__main__":
    print("=== test_parser_qc ===")
    test_bootstrap_sem_matches_gaussian()
    test_condition_qc_flags()
    test_lobe_summary_consistency()
    test_qc_report_written()
    test_save_load_with_noise_roundtrip()
    print("\n=== ALL PARSER-QC TESTS PASSED ===")
