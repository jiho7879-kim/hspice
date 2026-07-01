"""
Shared constants, sampling, and data utilities for the SRAM PVTA toy project.

Data shape:
    X: (N, 3) = [common_N_shift (mV), PU_shift (mV), Vop (V)]
    y: (N, 2) = [mu_SNMR (V), sigma_SNMR (V)]

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

# Actually compute from yield model:
# Per-bit yield = Y_target^(1/(MB * 1e6)) ~ exp(-(Z^2/2))  ->  Z = sqrt(-2 * ln(1 - (1-Y_target)/(MB*1e6)))
# But for toy project we use a conservative fixed Z_target.
# The physics layer will use this as the Z-score threshold for Vmin interpolation.
# After Phase 3 validation the exact Z_target can be tuned.
Z_FIXED = 6.0  # conservative Z_target for 64Mb @ 99.9%

# PVTA parameter bounds
COMMON_N_MIN, COMMON_N_MAX = -60.0, 60.0  # mV
PU_MIN, PU_MAX = -60.0, 60.0  # mV

# Vop sweep (discrete)
VOPS = np.array([0.4, 0.5, 0.6, 0.7, 0.8, 0.9], dtype=np.float64)
N_VOP = len(VOPS)

# Temperature (toy project: fixed hot)
TEMP_C = 125.0

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
    """Return (n_pts, 2) Sobol sequence scaled to [lo, hi]."""
    sampler = qmc.Sobol(d=2, scramble=True, seed=seed)
    # Sobol requires power-of-2; we oversample and trim
    m = int(2 ** np.ceil(np.log2(n_pts)))
    pts = sampler.random(n=m)
    # scale
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


def build_dataset(
    n_cond: int = 200,
    vops: np.ndarray = VOPS,
    seed: int = 42,
) -> np.ndarray:
    """Return (n_cond * len(vops), 3) input array X.

    Column order: [common_N_shift (mV), PU_shift (mV), Vop (V)].
    """
    common_n_pu = sample_common_n_pu(n_cond, seed=seed)
    # Repeat each (common_N, PU) across all Vop values
    X = np.zeros((n_cond * len(vops), 3), dtype=np.float64)
    for i, (cn, pu) in enumerate(common_n_pu):
        for j, vop in enumerate(vops):
            row = i * len(vops) + j
            X[row, 0] = cn
            X[row, 1] = pu
            X[row, 2] = vop
    return X


def parse_mc_mt0(filepath: str | Path) -> dict[str, float]:
    """Parse an HSPICE .mt0 MC output file, extract mu / sigma of SNM.

    Returns dict with keys 'mu_snmr', 'sigma_snmr'.

    Placeholder -- actual parsing depends on HSPICE .measure output format.
    """
    raise NotImplementedError(
        "Implement based on your HSPICE .mt0 format. "
        "Expected columns: snm_meas values (one per MC run). "
        "Compute np.mean() and np.std() from the histogram."
    )


def save_intermediate(filepath: str | Path, X: np.ndarray, y: np.ndarray) -> None:
    """Save processed data to compressed .npz.

    X: (N, 3), y: (N, 2)
    """
    np.savez_compressed(filepath, X=X, y=y)


def load_intermediate(filepath: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Load processed data from .npz."""
    data = np.load(filepath)
    return data["X"], data["y"]


def stratified_train_test_split(
    X: np.ndarray, y: np.ndarray, test_frac: float = 0.2, seed: int = 42
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Stratified train/test split that preserves quadrant balance.

    Splits by (common_N, PU) point (i.e., group all Vop for each condition),
    not by individual row, to avoid data leakage.
    """
    rng = np.random.default_rng(seed)
    # Unique conditions (first 2 columns)
    conditions = X[:, :2]
    _, inverse = np.unique(conditions, axis=0, return_inverse=True)
    cond_ids = np.unique(inverse)

    rng.shuffle(cond_ids)
    n_test = max(1, int(len(cond_ids) * test_frac))
    test_cond_ids = set(cond_ids[:n_test])

    test_mask = np.array([i in test_cond_ids for i in inverse])
    train_mask = ~test_mask

    return X[train_mask], X[test_mask], y[train_mask], y[test_mask]
