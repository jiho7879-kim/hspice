"""
Data handling utilities: dataset construction, save/load, train/test split.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from src.utils import VOPS, sample_common_n_pu


def build_dataset(
    n_cond: int = 200,
    vops: np.ndarray = VOPS,
    seed: int = 42,
) -> np.ndarray:
    """Return (n_cond * len(vops), 3) input array X (core 3D only).

    Column order: [common_N_shift (mV), PU_shift (mV), Vop (V)].
    For extended dims (8D), append columns after calling this function.
    """
    common_n_pu = sample_common_n_pu(n_cond, seed=seed)
    X = np.zeros((n_cond * len(vops), 3), dtype=np.float64)
    for i, (cn, pu) in enumerate(common_n_pu):
        for j, vop in enumerate(vops):
            row = i * len(vops) + j
            X[row, 0] = cn
            X[row, 1] = pu
            X[row, 2] = vop
    return X


def save_intermediate(filepath: str | Path, X: np.ndarray, y: np.ndarray) -> None:
    """Save processed data to compressed .npz.

    X: (N, d) with d >= 3, y: (N, 2)
    """
    np.savez_compressed(filepath, X=X, y=y)


def load_intermediate(filepath: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Load processed data from .npz (X, y only — backward compatible)."""
    data = np.load(filepath)
    return data["X"], data["y"]


def save_with_noise(
    filepath: str | Path,
    X: np.ndarray,
    y: np.ndarray,
    *,
    y_noise: np.ndarray | None = None,
    n_mc: np.ndarray | None = None,
    censored: np.ndarray | None = None,
    extras: dict[str, np.ndarray] | None = None,
) -> None:
    """Save dataset with optional MC-noise / censoring metadata.

    X: (N, d), y: (N, 2) = [mu, sigma].  Optional:
        y_noise:  (N, 2) per-point observation-noise STDs [sem_mu, sem_sigma]
                  for noise-aware GP training (Surrogate.fit(y_noise=...)).
        n_mc:     (N,) MC sample count per condition.
        censored: (N,) bool — Vmin left-censored below the lowest Vop.
        extras:   any additional named arrays (e.g. lobe stats mu_L, rho_LR).

    Readable by both load_intermediate (X, y) and load_with_noise.
    """
    payload: dict[str, np.ndarray] = {"X": X, "y": y}
    if y_noise is not None:
        payload["y_noise"] = y_noise
    if n_mc is not None:
        payload["n_mc"] = n_mc
    if censored is not None:
        payload["censored"] = censored
    if extras:
        payload.update(extras)
    np.savez_compressed(filepath, **payload)


def load_with_noise(filepath: str | Path) -> dict[str, np.ndarray]:
    """Load a dataset saved by save_with_noise (or a plain X/y npz).

    Returns a dict with at least 'X', 'y' and whichever optional arrays are
    present ('y_noise', 'n_mc', 'censored', plus any extras).  Missing
    optional keys are simply absent — callers use dict.get(...).
    """
    data = np.load(filepath, allow_pickle=False)
    return {k: data[k] for k in data.files}


def stratified_train_test_split(
    X: np.ndarray, y: np.ndarray, test_frac: float = 0.2, seed: int = 42
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Stratified train/test split that preserves quadrant balance.

    Splits by (common_N, PU) point (i.e., group all Vop for each condition),
    not by individual row, to avoid data leakage.
    """
    rng = np.random.default_rng(seed)
    conditions = X[:, :2]
    _, inverse = np.unique(conditions, axis=0, return_inverse=True)
    cond_ids = np.unique(inverse)

    rng.shuffle(cond_ids)
    n_test = max(1, int(len(cond_ids) * test_frac))
    test_cond_ids = set(cond_ids[:n_test])

    test_mask = np.array([i in test_cond_ids for i in inverse])
    train_mask = ~test_mask

    return X[train_mask], X[test_mask], y[train_mask], y[test_mask]


def grouped_train_test_split(
    X: np.ndarray, y: np.ndarray, groups: np.ndarray,
    test_frac: float = 0.2, seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Train/test split that keeps every member of a GROUP on the same side.

    REQUIRED for the in-house legacy batches (StageD n=500, final n=2000,
    seed=2026).  Those designs re-used one Sobol stream across all four
    (cn, pu) quadrants, so each base Sobol point k appears 2-4 times, differing
    ONLY in the sign of cn and/or pu -- the other 7 coordinates
    (sk, lpu, l_com, l_sk, mpu, m_com, m_sk) are byte-identical.  A random or
    condition-level split therefore puts mirror twins on both sides and
    inflates test scores.

    Pass groups = gen_idx (the Sobol row index, column `gen_idx` of the
    regenerated condition table): 900 groups for n=2000, 225 for n=500.
    See docs/decisions/legacy_design_audit_20260714.md.
    """
    groups = np.asarray(groups)
    if len(groups) != len(X):
        raise ValueError(f"groups length {len(groups)} != X length {len(X)}")
    rng = np.random.default_rng(seed)
    uniq = np.unique(groups)
    rng.shuffle(uniq)
    n_test = max(1, int(round(len(uniq) * test_frac)))
    test_groups = set(uniq[:n_test].tolist())

    test_mask = np.array([g in test_groups for g in groups])
    train_mask = ~test_mask
    return X[train_mask], X[test_mask], y[train_mask], y[test_mask]
