"""
Tests for lobe-resolved effective z-score (src/utils.py):
bvn_cdf, z_eff_from_lobes, effective_mu_sigma.

Background (adversarial review 2026-07-07, finding A1): read SNM is the min
of the two butterfly lobes; a Gaussian z-score on the min's (mu, sigma) is
optimistically biased by +0.7 to +1.9 sigma at Z ~ 6.  These utilities
compute the exact union-based effective z from per-lobe statistics.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from scipy.stats import norm, multivariate_normal

from src.utils import bvn_cdf, z_eff_from_lobes, effective_mu_sigma


def test_bvn_cdf_vs_scipy() -> None:
    """bvn_cdf matches scipy multivariate_normal.cdf on a moderate grid."""
    hs = [-3.0, -1.0, 0.0, 0.5, 2.0]
    ks = [-2.5, -0.5, 0.0, 1.5]
    rhos = [-0.95, -0.5, 0.0, 0.5, 0.95]
    max_err = 0.0
    for rho in rhos:
        mvn = multivariate_normal(mean=[0.0, 0.0], cov=[[1.0, rho], [rho, 1.0]])
        for h in hs:
            for k in ks:
                ours = float(bvn_cdf(h, k, rho))
                ref = float(mvn.cdf([h, k]))
                max_err = max(max_err, abs(ours - ref))
    assert max_err < 5e-8, f"bvn_cdf mismatch vs scipy: {max_err:.2e}"
    print(f"  [OK] bvn_cdf vs scipy mvn.cdf: max |err| = {max_err:.2e}")


def test_bvn_cdf_degenerate_rho() -> None:
    """rho = +-1 exact limits."""
    h, k = -1.2, -0.4
    assert abs(float(bvn_cdf(h, k, 1.0)) - norm.cdf(min(h, k))) < 1e-14
    expect = max(0.0, norm.cdf(h) + norm.cdf(k) - 1.0)
    assert abs(float(bvn_cdf(h, k, -1.0)) - expect) < 1e-14
    # deep tail, rho=-1: P(both) = 0
    assert float(bvn_cdf(-6.0, -6.0, -1.0)) == 0.0
    print("  [OK] bvn_cdf degenerate rho = +-1 limits")


def test_zeff_symmetric_references() -> None:
    """Symmetric lobes: closed-form references at Z=6."""
    z = 6.0
    # rho -> 1: min == single lobe, Z_eff -> z
    ze = float(z_eff_from_lobes(z, 1.0, z, 1.0, 1.0))
    assert abs(ze - z) < 1e-9, f"rho=1 limit: {ze}"

    # rho = 0: p = 2*Phi(-z) - Phi(-z)^2
    p_ref = 2 * norm.sf(z) - norm.sf(z) ** 2
    ze0 = float(z_eff_from_lobes(z, 1.0, z, 1.0, 0.0))
    assert abs(ze0 - norm.isf(p_ref)) < 1e-9
    # adversarial review A1 table: Z_true ~ 5.886 at rho <= 0.7
    assert 5.88 < ze0 < 5.90, f"review A1 regression: {ze0}"

    # rho = -1: p = 2*Phi(-z) exactly (disjoint tails)
    zem = float(z_eff_from_lobes(z, 1.0, z, 1.0, -1.0))
    assert abs(zem - norm.isf(2 * norm.sf(z))) < 1e-9

    # monotonic in rho: less correlation => more fail mass => lower Z_eff
    zs = [float(z_eff_from_lobes(z, 1.0, z, 1.0, r))
          for r in (-0.9, -0.5, 0.0, 0.5, 0.9)]
    assert all(a < b + 1e-12 for a, b in zip(zs, zs[1:])), f"not monotonic: {zs}"
    print(f"  [OK] z_eff symmetric refs: rho=0 -> {ze0:.4f} (Gauss-min would say 6.58)")


def test_zeff_weak_lobe_dominates() -> None:
    """Asymmetric lobes: Z_eff ~ weak lobe's z (strong lobe negligible)."""
    ze = float(z_eff_from_lobes(4.0, 1.0, 10.0, 1.0, 0.0))
    assert abs(ze - 4.0) < 1e-6, f"weak-lobe limit: {ze}"
    # different sigmas: z_l = 80/20 = 4 dominates vs z_r = 120/15 = 8
    ze2 = float(z_eff_from_lobes(80.0, 20.0, 120.0, 15.0, 0.3))
    assert abs(ze2 - 4.0) < 1e-3, f"unit-consistency: {ze2}"
    print("  [OK] weak lobe dominates; unit-invariant")


def test_zeff_monte_carlo() -> None:
    """Empirical min-fail rate matches closed form at a moderate Z."""
    rng = np.random.default_rng(7)
    z, rho, n = 2.5, -0.5, 4_000_000
    cov = [[1.0, rho], [rho, 1.0]]
    L, R = rng.multivariate_normal([z, z], cov, size=n).T
    p_emp = float(np.mean(np.minimum(L, R) < 0.0))
    ze = float(z_eff_from_lobes(z, 1.0, z, 1.0, rho))
    p_closed = float(norm.sf(ze))
    se = np.sqrt(p_closed * (1 - p_closed) / n)
    assert abs(p_emp - p_closed) < 4 * se, (
        f"MC {p_emp:.6e} vs closed {p_closed:.6e} (4se={4*se:.2e})")
    print(f"  [OK] MC validation: p_emp={p_emp:.5e} vs closed={p_closed:.5e}")


def test_zeff_threshold_and_vectorization() -> None:
    """Threshold shift and array broadcasting."""
    # threshold t: same as shifting means by -t
    a = float(z_eff_from_lobes(0.10, 0.02, 0.12, 0.02, 0.2, threshold=0.03))
    b = float(z_eff_from_lobes(0.07, 0.02, 0.09, 0.02, 0.2, threshold=0.0))
    assert abs(a - b) < 1e-12

    n = 50
    rng = np.random.default_rng(0)
    mu_l = rng.uniform(0.06, 0.15, n)
    mu_r = rng.uniform(0.06, 0.15, n)
    sg = rng.uniform(0.01, 0.03, n)
    rho = rng.uniform(-0.8, 0.8, n)
    ze = z_eff_from_lobes(mu_l, sg, mu_r, sg, rho)
    assert ze.shape == (n,) and np.all(np.isfinite(ze))
    print("  [OK] threshold shift identity + vectorization (N=50)")


def test_effective_mu_sigma_adapter() -> None:
    """mu_eff/sigma_eff reproduces Z_eff exactly; outputs are smooth-scale."""
    n = 40
    rng = np.random.default_rng(1)
    mu_l = rng.uniform(0.06, 0.15, n)
    mu_r = rng.uniform(0.06, 0.15, n)
    sg_l = rng.uniform(0.01, 0.03, n)
    sg_r = rng.uniform(0.01, 0.03, n)
    rho = rng.uniform(-0.8, 0.8, n)

    ze = z_eff_from_lobes(mu_l, sg_l, mu_r, sg_r, rho)
    mu_e, sg_e = effective_mu_sigma(mu_l, sg_l, mu_r, sg_r, rho)
    assert np.allclose(mu_e / sg_e, ze, atol=1e-10), "ratio identity broken"
    assert np.all(sg_e > 0)
    assert np.allclose(sg_e, np.sqrt(sg_l * sg_r))
    print("  [OK] effective (mu, sigma) adapter: mu_eff/sigma_eff == Z_eff")


def test_min_stats_bias_demonstration() -> None:
    """Regression-pin the A1 finding: Gaussian z on min-stats is optimistic."""
    z, rho = 6.0, 0.0
    # moment-matched Gaussian of min(L,R), iid case
    theta = np.sqrt(2 * (1 - rho))
    mu_min = z - 0.5 * theta * np.sqrt(2 / np.pi)
    var_min = (1 + rho) / 2 + 0.25 * theta ** 2 * (1 - 2 / np.pi)
    z_gauss = mu_min / np.sqrt(var_min)
    z_true = float(z_eff_from_lobes(z, 1.0, z, 1.0, rho))
    bias = z_gauss - z_true
    assert 0.6 < bias < 0.8, f"A1 bias out of expected band: {bias:.3f}"
    print(f"  [OK] A1 regression: min-stats Gaussian z bias = +{bias:.3f} sigma @ Z=6, rho=0")


if __name__ == "__main__":
    print("=== test_zeff ===")
    test_bvn_cdf_vs_scipy()
    test_bvn_cdf_degenerate_rho()
    test_zeff_symmetric_references()
    test_zeff_weak_lobe_dominates()
    test_zeff_monte_carlo()
    test_zeff_threshold_and_vectorization()
    test_effective_mu_sigma_adapter()
    test_min_stats_bias_demonstration()
    print("\n=== ALL ZEFF TESTS PASSED ===")
