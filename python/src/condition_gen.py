"""
condition_gen.py — SELF-CONTAINED, PORTABLE SRAM condition generator.

WHY THIS FILE EXISTS
--------------------
In-house decks are built by a Python script that runs INSIDE the fab
environment (paths / filenames / flow differ from ours, so our full
gen_hspice.py is impractical to run there directly). But the *conditions*
(cn, pu, skew, local-sigma, mobility) must be IDENTICAL between:
  - the in-house deck-generation run, and
  - our local re-generation (so the user never has to transcribe conditions,
    only the measured results).

This module is the single source of truth for that. It has ZERO project
imports and depends ONLY on numpy (optionally scipy for Sobol). Copy it, or
hand it to an in-house code assistant, and it will reproduce the exact same
conditions given the same (stage, n_cond, seed, method).

REPRODUCIBILITY CONTRACT (must match on both sides)
---------------------------------------------------
  stage, n_cond, seed, method, and this file's version.
  Default method="rng" uses numpy Generator(PCG64), whose stream numpy
  guarantees stable across versions (documented). method="sobol" uses
  scipy.stats.qmc.Sobol(scramble=True) which is better space-filling but
  can differ across scipy versions -- only use it if both sides pin scipy.

PRECISION (decided 2026-07-09)
------------------------------
  cn, pu, skew : integer mV        (rounding -> Vmin error <= 0.7 mV)
  loc, mom     : 2 decimals (ratio, nominal 1.0, range 0.7-1.3)

STAGES
------
  A (3D): cn, pu                          + Vop grid downstream
  B (4D): cn, sk, pu
  D (9D): cn, sk, pu, lpu,lpg,lpd, mpu,mpg,mpd

Quadrant weighting (SNMR -> Q2/FSG focus, Vtrip -> Q4/SFG focus) is optional
and applied to the (cn, pu) plane only.
"""

from __future__ import annotations

import numpy as np

CONDITION_GEN_VERSION = "1.0"

# --- ranges (mV for shifts, ratio for loc/mom) ---
CN_MIN, CN_MAX = -60.0, 60.0
PU_MIN, PU_MAX = -60.0, 60.0
SK_MIN, SK_MAX = -20.0, 20.0        # PG-PD skew
LOC_MIN, LOC_MAX = 0.7, 1.3         # VTSL local-sigma ratio
MOM_MIN, MOM_MAX = 0.7, 1.3         # MOM mobility ratio

# quadrant weights on (cn_sign, pu_sign); keys: -1 = negative half, +1 = positive
QW_SNMR = {(-1, +1): 0.45, (-1, -1): 0.20, (+1, +1): 0.15, (+1, -1): 0.20}
QW_VTRIP = {(-1, +1): 0.10, (-1, -1): 0.15, (+1, +1): 0.30, (+1, -1): 0.45}

STAGE_COLUMNS = {
    "A": ["cn", "pu"],
    "B": ["cn", "sk", "pu"],
    "D": ["cn", "sk", "pu", "lpu", "lpg", "lpd", "mpu", "mpg", "mpd"],
}


def _unit_samples(n: int, d: int, seed: int, method: str) -> np.ndarray:
    """Return (n, d) samples in the unit hypercube [0,1]^d.

    method="rng"   : numpy Generator(PCG64) uniform -- portable, version-stable.
    method="sobol" : scipy Sobol (scramble=True)   -- better fill, scipy-pinned.
    """
    if method == "rng":
        return np.random.default_rng(seed).random((n, d))
    if method == "sobol":
        from scipy.stats import qmc
        s = qmc.Sobol(d=d, scramble=True, seed=seed)
        m = int(np.ceil(np.log2(max(n, 1))))
        return s.random_base2(m=m)[:n]
    raise ValueError(f"unknown method {method!r} (use 'rng' or 'sobol')")


def _quadrant_cnpu(n_total: int, weights: dict, seed: int, method: str) -> np.ndarray:
    """(n_total, 2) cn,pu with quadrant weighting. Deterministic given seed."""
    parts = []
    for i, ((cn_s, pu_s), w) in enumerate(weights.items()):
        n = int(round(n_total * w))
        if n <= 0:
            continue
        u = _unit_samples(n, 2, seed + 1 + i, method)
        cn_lo, cn_hi = (0.0, CN_MAX) if cn_s > 0 else (CN_MIN, 0.0)
        pu_lo, pu_hi = (0.0, PU_MAX) if pu_s > 0 else (PU_MIN, 0.0)
        cn = cn_lo + (cn_hi - cn_lo) * u[:, 0]
        pu = pu_lo + (pu_hi - pu_lo) * u[:, 1]
        parts.append(np.column_stack([cn, pu]))
    pts = np.vstack(parts)
    # deterministic shuffle + trim/pad to exactly n_total
    np.random.default_rng(seed).shuffle(pts)
    if len(pts) < n_total:  # rounding shortfall: top up uniformly
        extra = _unit_samples(n_total - len(pts), 2, seed + 999, method)
        extra = np.column_stack([CN_MIN + (CN_MAX - CN_MIN) * extra[:, 0],
                                 PU_MIN + (PU_MAX - PU_MIN) * extra[:, 1]])
        pts = np.vstack([pts, extra])
    return pts[:n_total]


def generate_conditions(
    stage: str,
    n_cond: int,
    seed: int = 42,
    metric: str = "snmr",
    method: str = "rng",
    quadrant_weighted: bool = True,
) -> tuple[list[str], np.ndarray]:
    """Generate (column_names, conditions) for a stage. DETERMINISTIC.

    conditions: (n_cond, n_col) at the decided precision (cn/pu/sk integer mV,
    loc/mom 2 decimals). Vop is NOT included (added as a grid downstream).

    The SAME (stage, n_cond, seed, metric, method) reproduces byte-identical
    conditions in any environment with the same numpy (method='rng').
    """
    stage = stage.upper()
    if stage not in STAGE_COLUMNS:
        raise ValueError(f"stage must be A/B/D, got {stage!r}")
    weights = QW_SNMR if metric == "snmr" else QW_VTRIP

    # (cn, pu) plane
    if quadrant_weighted and stage in ("B", "D"):
        cnpu = _quadrant_cnpu(n_cond, weights, seed, method)
    else:
        u = _unit_samples(n_cond, 2, seed, method)
        cnpu = np.column_stack([CN_MIN + (CN_MAX - CN_MIN) * u[:, 0],
                                PU_MIN + (PU_MAX - PU_MIN) * u[:, 1]])
    cn = np.round(cnpu[:, 0]).astype(int)
    pu = np.round(cnpu[:, 1]).astype(int)

    if stage == "A":
        return STAGE_COLUMNS["A"], np.column_stack([cn, pu]).astype(float)

    # extra dims (sk for B; sk + 6 ratios for D) from an independent stream
    n_extra = 1 if stage == "B" else 7
    e = _unit_samples(n_cond, n_extra, seed + 100, method)
    sk = np.round(SK_MIN + (SK_MAX - SK_MIN) * e[:, 0]).astype(int)
    if stage == "B":
        return STAGE_COLUMNS["B"], np.column_stack([cn, sk, pu]).astype(float)

    loc = np.round(LOC_MIN + (LOC_MAX - LOC_MIN) * e[:, 1:4], 2)
    mom = np.round(MOM_MIN + (MOM_MAX - MOM_MIN) * e[:, 4:7], 2)
    arr = np.column_stack([cn, sk, pu, loc, mom]).astype(float)
    return STAGE_COLUMNS["D"], arr


def conditions_to_records(
    cols: list[str], cond: np.ndarray, vops,
    deck_prefix: str = "TT", start: int = 1,
) -> list[dict]:
    """Expand conditions x Vop into flat row dicts (for a sheet / deck loop).

    DECK NUMBERING (matches the in-house reference deck TT-N naming):
      numbering restarts at `start` FOR EACH Vop and increments over the
      condition index. So condition i (0-based) at Vop level gets:
          deck_no = start + i
          deck_id = f"{deck_prefix}-{deck_no}"   e.g. "TT-1", "TT-2", ...
      i.e. every Vop has its own TT-1..TT-N running over the same condition
      order. The match key back from results is therefore (vop, deck_no).

    This ordering is DETERMINISTIC given (cols, cond, vops), so results
    labelled only by (vop, deck_no) re-attach to conditions with no
    condition transcription. Integer cols (cn/sk/pu) stay int; loc/mom 2 dec.
    """
    int_cols = {"cn", "sk", "pu"}
    rows = []
    for v in vops:                       # outer loop = Vop (each restarts numbering)
        for i in range(len(cond)):       # inner loop = condition index -> deck_no
            deck_no = start + i
            rec = {"deck_no": deck_no,
                   "deck_id": f"{deck_prefix}-{deck_no}"}
            for j, c in enumerate(cols):
                val = cond[i, j]
                rec[c] = int(val) if c in int_cols else round(float(val), 2)
            rec["vop"] = float(v)
            rows.append(rec)
    return rows


if __name__ == "__main__":
    # tiny self-test: determinism + precision
    for st in ("A", "B", "D"):
        c1 = generate_conditions(st, 16, seed=42)[1]
        c2 = generate_conditions(st, 16, seed=42)[1]
        assert np.array_equal(c1, c2), f"{st} not deterministic"
        c3 = generate_conditions(st, 16, seed=7)[1]
        assert not np.array_equal(c1, c3), f"{st} seed had no effect"
    cols, cond = generate_conditions("D", 16, seed=42)
    assert np.array_equal(cond[:, :3], np.round(cond[:, :3])), "cn/sk/pu not integer"
    assert np.allclose(cond[:, 3:], np.round(cond[:, 3:], 2)), "loc/mom not 2-dec"
    print(f"condition_gen v{CONDITION_GEN_VERSION}: self-test OK "
          f"(deterministic, seed-sensitive, precision correct)")
    print("D columns:", cols)
    print("D[0]:", cond[0])
