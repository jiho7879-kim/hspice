"""
Shared constants, StandardScaler, and sampling utilities.

Data shape:
    X: (N, d) where d ≥ 3
       Core 3D:   [common_N_shift (mV), PU_shift (mV), Vop (V)]
       Extended:  [..., W (norm), sigmaL_mult, sigmaG, mu_mobility_mult, Temp (degC)]
    y: (N, 2) = [mu_SNMR (V), sigma_SNMR (V)]

    Vop is always at column index VOP_COL (= 2) regardless of d.
    Extended dims (indices 3+) are optional; when absent code defaults to 3D.

SHIFT CONVENTION (consistent for both NMOS and PMOS):
    positive shift = slower device
    negative shift = faster device

    common_N_shift > 0  -> NMOS Vth higher -> NMOS slower
    common_N_shift < 0  -> NMOS Vth lower  -> NMOS faster

    PU_shift > 0  -> |PMOS Vth| larger -> PMOS slower
    PU_shift < 0  -> |PMOS Vth| smaller -> PMOS faster

Corner mapping:
    FSG = (common_N < 0, PU > 0)  = (fast N, slow P)  -- SNMR worst @ hot
    SFG = (common_N > 0, PU < 0)  = (slow N, fast P)  -- Vtrip worst @ cold
    FFG = (common_N < 0, PU < 0)  = (fast N, fast P)
    SSG = (common_N > 0, PU > 0)  = (slow N, slow P)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.stats import qmc
from typing import Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Yield target
MB = 64  # memory block size in Mb
Y_TARGET = 0.999  # per-block yield target
Z_TARGET = 3.0  # simplified single-bit sigma target (adjustable)


def derive_z_target(mb: float = MB, y_target: float = Y_TARGET,
                    bits_per_mb: float = 1e6) -> float:
    """Exact Z_target from the Poisson/binomial yield model.

    P_fail_per_bit = 1 - y_target^(1/Nbits),  Nbits = mb * bits_per_mb
    Z_target = Phi^-1(1 - P_fail_per_bit) = norm.isf(P_fail_per_bit)

    For 64 Mb @ 99.9%:  P_bit ~ 1.56e-11  ->  Z ~ 6.65.
    Note: Nbits is the CELL (bit) count — do not multiply by 6 for the
    six transistors of a 6T cell; the failure unit is the cell.
    """
    from scipy.stats import norm
    nbits = mb * bits_per_mb
    p_fail_bit = 1.0 - y_target ** (1.0 / nbits)
    return float(norm.isf(p_fail_bit))


# Fixed Z-score threshold used by the physics layer for Vmin interpolation.
#
# NOTE: 6.0 is a SIMPLIFIED toy value, kept fixed so results stay comparable
# across sessions.  The exact value for 64Mb @ 99.9% is derive_z_target()
# ~ 6.65, i.e. Z_FIXED = 6.0 is slightly OPTIMISTIC (lower Vmin), not
# "conservative" as earlier comments claimed (higher Z = stricter = higher
# Vmin).  Switch to derive_z_target() when absolute Vmin accuracy matters
# (HSPICE deployment / paper numbers); expect a fixed +shift in all Vmin
# values, no change to contour SHAPES or GP quality metrics.
Z_FIXED = 6.0


# ---------------------------------------------------------------------------
# Lobe-resolved effective z-score (adversarial review 2026-07-07, finding A1)
#
# Read SNM is the MIN of the two butterfly lobes.  Applying a Gaussian
# z-score to the min's (mu, sigma) underestimates the fail tail by
# +0.7 sigma (independent lobes) to +1.9 sigma (anticorrelated lobes) at
# Z ~ 6, i.e. ~70-190 mV of optimistic Vmin bias.  The correct treatment
# works from per-lobe statistics:
#
#     p_fail = P(L < t) + P(R < t) - P(L < t, R < t)
#     Z_eff  = Phi^-1(1 - p_fail)
#
# which is closed-form (bivariate normal CDF via Owen's T), vectorized,
# and smooth in all inputs (differentiable for the physics layer).
# ---------------------------------------------------------------------------

def bvn_cdf(h: np.ndarray, k: np.ndarray, rho: np.ndarray) -> np.ndarray:
    """Standard bivariate normal CDF  P(X <= h, Y <= k), corr(X, Y) = rho.

    Vectorized over (h, k, rho) via Owen's T function (Owen 1956):

        Phi2(h, k, rho) = 0.5*(Phi(h) + Phi(k)) - T(h, a_h) - T(k, a_k) - c
        a_h = (k - rho*h) / (h * sqrt(1 - rho^2)),  a_k symmetric
        c   = 0.5 if h*k < 0 (or h*k == 0 and h + k < 0), else 0

    Exact up to floating point; the subtractive cancellation only becomes
    relatively large when the result is negligibly small (rho -> 0 deep in
    the joint tail), where it does not matter for the union probability.
    Results are clipped to the Frechet bounds for safety.
    """
    from scipy.stats import norm
    from scipy.special import owens_t

    h = np.asarray(h, dtype=np.float64)
    k = np.asarray(k, dtype=np.float64)
    rho = np.asarray(rho, dtype=np.float64)
    h, k, rho = np.broadcast_arrays(h, k, rho)

    out = np.empty(h.shape, dtype=np.float64)

    # Degenerate correlations handled exactly
    hi_r = rho >= 1.0 - 1e-12
    lo_r = rho <= -1.0 + 1e-12
    mid = ~(hi_r | lo_r)

    if hi_r.any():
        out[hi_r] = norm.cdf(np.minimum(h[hi_r], k[hi_r]))
    if lo_r.any():
        out[lo_r] = np.maximum(0.0, norm.cdf(h[lo_r]) + norm.cdf(k[lo_r]) - 1.0)

    if mid.any():
        hm, km, rm = h[mid], k[mid], rho[mid]
        # Avoid division by zero at h == 0 / k == 0 (limit is well-defined;
        # nudging by ~1e-14 changes Phi2 by O(1e-14))
        eps = 1e-14
        hs = np.where(np.abs(hm) < eps, eps, hm)
        ks = np.where(np.abs(km) < eps, eps, km)
        den = np.sqrt(1.0 - rm * rm)
        a_h = (ks - rm * hs) / (hs * den)
        a_k = (hs - rm * ks) / (ks * den)
        c = np.where(
            (hs * ks < 0) | ((hs * ks == 0) & (hs + ks < 0)),
            0.5, 0.0,
        )
        val = (0.5 * (norm.cdf(hs) + norm.cdf(ks))
               - owens_t(hs, a_h) - owens_t(ks, a_k) - c)
        # Frechet bounds clip (guards tiny negative values from cancellation)
        upper = np.minimum(norm.cdf(hs), norm.cdf(ks))
        lower = np.maximum(0.0, norm.cdf(hs) + norm.cdf(ks) - 1.0)
        out[mid] = np.clip(val, lower, upper)

    return out


def z_eff_from_lobes(
    mu_l: np.ndarray, sigma_l: np.ndarray,
    mu_r: np.ndarray, sigma_r: np.ndarray,
    rho: np.ndarray,
    threshold: float = 0.0,
) -> np.ndarray:
    """Effective z-score for cell SNM = min(L, R) failing below `threshold`.

    Args:
        mu_l, sigma_l: left-lobe SNM mean / std (any consistent unit)
        mu_r, sigma_r: right-lobe SNM mean / std
        rho:           correlation between lobe SNMs (from the same MC run)
        threshold:     fail threshold on SNM (default 0)

    Returns:
        Z_eff = Phi^-1(1 - p_fail), vectorized.  Use in place of mu/sigma
        of the min-statistics (which is optimistically biased, see module
        comment).  Smooth in all inputs.
    """
    from scipy.stats import norm

    z_l = (np.asarray(mu_l, dtype=np.float64) - threshold) / np.asarray(sigma_l, dtype=np.float64)
    z_r = (np.asarray(mu_r, dtype=np.float64) - threshold) / np.asarray(sigma_r, dtype=np.float64)
    p_l = norm.sf(z_l)
    p_r = norm.sf(z_r)
    p_both = bvn_cdf(-z_l, -z_r, rho)
    p_fail = np.clip(p_l + p_r - p_both, 1e-300, 1.0 - 1e-16)
    return norm.isf(p_fail)


def effective_mu_sigma(
    mu_l: np.ndarray, sigma_l: np.ndarray,
    mu_r: np.ndarray, sigma_r: np.ndarray,
    rho: np.ndarray,
    threshold: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Map lobe statistics to an effective (mu, sigma) pair.

    Preserves the project-wide y = (N, 2) = [mu, sigma] convention while
    guaranteeing  mu_eff / sigma_eff == z_eff_from_lobes(...) exactly, so
    the existing GP + physics-layer pipeline needs no modification.

    sigma_eff is the geometric mean of the lobe sigmas — a smooth,
    symmetric scale choice (only the mu/sigma RATIO affects Vmin; a
    worst-lobe sigma would introduce a kink where the lobes cross).

    Note: the fail threshold is ABSORBED into z_eff (downstream code
    computes z = mu/sigma with an implicit fail-at-zero), so
    mu_eff = z_eff * sigma_eff with no threshold offset.
    """
    z_eff = z_eff_from_lobes(mu_l, sigma_l, mu_r, sigma_r, rho, threshold)
    sigma_eff = np.sqrt(np.asarray(sigma_l, dtype=np.float64)
                        * np.asarray(sigma_r, dtype=np.float64))
    mu_eff = z_eff * sigma_eff
    return mu_eff, sigma_eff

# PVTA parameter bounds
COMMON_N_MIN, COMMON_N_MAX = -60.0, 60.0  # mV
PU_MIN, PU_MAX = -60.0, 60.0  # mV

# Vop sweep (discrete)
VOPS = np.array([0.4, 0.5, 0.6, 0.7, 0.8, 0.9], dtype=np.float64)
N_VOP = len(VOPS)

# Vop column index — always 2 regardless of total dims.
# NEVER hardcode 2 in physics constraint code; import and use VOP_COL.
VOP_COL = 2

# WLUD (wordline underdrive) ratio = Vwl / Vop
# The 4th input dimension is WLUD ratio (not absolute Vwl).
# When calling analytic_snmr, compute Vwl = WLUD * Vop for each point.
# Covers practical assist range from ~10% underdrive (0.90) to none (1.00).
WLUD_FACTORS = np.linspace(0.90, 1.00, 6, dtype=np.float64)
N_WLUD = len(WLUD_FACTORS)
N_VWL = N_WLUD  # backward compat alias

# WLUD column index — always 3 when dim >= 4.
# Stores the ratio Vwl/Vop (not absolute Vwl).
WLUD_COL = 3
VWL_COL = WLUD_COL  # backward compat alias

# Temperature (toy project: fixed hot)
TEMP_C = 125.0
TEMP_C_COLD = -40.0

# ---------------------------------------------------------------------------
# StandardScaler (numpy-only, no sklearn dependency)
# ---------------------------------------------------------------------------

class StandardScaler:
    """Per-dimension Z-score normalizer for GP input stability.

    Learns mean/std from training data, then transforms both train and
    test/probe data with the same statistics.  Inverse_transform restores
    original scale for interpretation.

    Usage:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_train)   # (N, d)
        X_test_scaled = scaler.transform(X_test)    # same stats
        X_back = scaler.inverse_transform(X_scaled)
    """
    def __init__(self) -> None:
        self.mean_: np.ndarray | None = None
        self.std_: np.ndarray | None = None

    def fit(self, X: np.ndarray) -> None:
        self.mean_ = X.mean(axis=0)
        self.std_ = X.std(axis=0, ddof=0)
        self.std_[self.std_ == 0] = 1.0  # avoid div-by-zero for constant dims

    def transform(self, X: np.ndarray) -> np.ndarray:
        assert self.mean_ is not None and self.std_ is not None, "call fit() first"
        return (X - self.mean_) / self.std_

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        self.fit(X)
        return self.transform(X)

    def inverse_transform(self, X: np.ndarray) -> np.ndarray:
        assert self.mean_ is not None and self.std_ is not None, "call fit() first"
        return X * self.std_ + self.mean_


# ---------------------------------------------------------------------------
# Stratified sampling
# ---------------------------------------------------------------------------

# Quadrant definitions in (common_N, PU) space:
#   Q1 (FSG-like): common_N < 0, PU > 0   -- SNMR worst (35% density)
#   Q2 (SFG-like): common_N > 0, PU < 0   -- Vtrip worst (25% density)
#   Q3 (rest):     common_N <= 0, PU <= 0  --         (20% density)
#   Q4 (rest):     common_N >= 0, PU >= 0  --         (20% density)
# Balanced sampling ensures GP can separate cn and pu effects in all
# quadrants. FSG gets extra weight as the primary corner of interest.

@dataclass
class QuadrantSpec:
    n_pts: int
    common_n_range: Tuple[float, float]
    pu_range: Tuple[float, float]

def get_quadrant_specs(total_pts: int = 200) -> list[QuadrantSpec]:
    """Return stratified quadrant specs for (common_N, PU) sampling.

    Weights: FSG 35%, SFG 25%, Q3 20%, Q4 20%.

    More balanced than 50/25/12.5/12.5 to avoid GP blind spots in FFG/SSG
    quadrants where cn and pu effects compete. FSG still gets highest weight
    as the primary corner of interest (SNMR worst @ hot).
    """
    def _round_even(x: int) -> int:
        return x if x % 2 == 0 else x + 1

    n_fsg = _round_even(int(total_pts * 0.35))
    n_sfg = _round_even(int(total_pts * 0.25))
    n_rest = _round_even(total_pts - n_fsg - n_sfg)

    return [
        QuadrantSpec(n_fsg, (COMMON_N_MIN, 0.0), (0.0, PU_MAX)),  # FSG
        QuadrantSpec(n_sfg, (0.0, COMMON_N_MAX), (PU_MIN, 0.0)),  # SFG
        QuadrantSpec(n_rest // 2, (COMMON_N_MIN, 0.0), (PU_MIN, 0.0)),  # Q3 (--)
        QuadrantSpec(n_rest // 2, (0.0, COMMON_N_MAX), (0.0, PU_MAX)),  # Q4 (++)
    ]


def sobol_2d_in_rect(n_pts: int, lo: np.ndarray, hi: np.ndarray, seed: int | None = None) -> np.ndarray:
    """Return (n_pts, 2) Sobol sequence scaled to [lo, hi].

    Returns empty array if n_pts <= 0.
    """
    if n_pts <= 0:
        return np.empty((0, 2), dtype=np.float64)
    sampler = qmc.Sobol(d=2, scramble=True, seed=seed)
    m = int(2 ** np.ceil(np.log2(n_pts)))
    pts = sampler.random(n=m)
    pts = qmc.scale(pts, lo, hi)  # type: ignore[arg-type]
    return pts[:n_pts].astype(np.float64)


def sample_common_n_pu(total_pts: int = 200, seed: int = 42) -> np.ndarray:
    """Return (total_pts, 2) stratified (common_N, PU) samples in mV.

    Applies Sobol within each quadrant at the specified density, then
    concatenates. Shuffles before returning.
    """
    specs = get_quadrant_specs(total_pts)
    rng = np.random.default_rng(seed)

    all_pts = []
    for i, spec in enumerate(specs):
        lo = np.array([spec.common_n_range[0], spec.pu_range[0]], dtype=np.float64)
        hi = np.array([spec.common_n_range[1], spec.pu_range[1]], dtype=np.float64)
        pts = sobol_2d_in_rect(spec.n_pts, lo, hi, seed=seed + i)
        all_pts.append(pts)

    out = np.concatenate(all_pts, axis=0)
    rng.shuffle(out)
    return out  # shape (total_pts, 2)
