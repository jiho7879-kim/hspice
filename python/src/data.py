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
    conditions = X[:, :2]
    _, inverse = np.unique(conditions, axis=0, return_inverse=True)
    cond_ids = np.unique(inverse)

    rng.shuffle(cond_ids)
    n_test = max(1, int(len(cond_ids) * test_frac))
    test_cond_ids = set(cond_ids[:n_test])

    test_mask = np.array([i in test_cond_ids for i in inverse])
    train_mask = ~test_mask

    return X[train_mask], X[test_mask], y[train_mask], y[test_mask]
