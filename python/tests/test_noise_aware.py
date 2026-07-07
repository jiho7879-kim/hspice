"""
Tests for the noise-aware GP option (Surrogate.fit(y_noise=...)).

Noise-aware = FixedNoiseGaussianLikelihood with per-point observation-noise
variances (MC standard errors).  The GP should downweight points that
declare large noise instead of letting them corrupt the surface — this is
the mechanism that unifies mixed MC budgets (plan sec 3.5 / 4.4).
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch

from src.utils import VOPS
from src.surrogate import Surrogate


def _make_data(n_cond: int = 40, seed: int = 3):
    """3D toy data (cn, pu, Vop) with a corrupted high-noise subset."""
    rng = np.random.default_rng(seed)
    cn = rng.uniform(-60, 60, n_cond)
    pu = rng.uniform(-60, 60, n_cond)

    rows = []
    for i in range(n_cond):
        for v in VOPS:
            rows.append([cn[i], pu[i], v])
    X = np.array(rows, dtype=np.float64)

    mu_true = 0.15 * X[:, 2] + 0.001 * X[:, 0] - 0.0015 * X[:, 1]
    sg_true = 0.015 + 0.004 * (0.9 - X[:, 2])
    y_true = np.column_stack([mu_true, sg_true])

    n = len(X)
    corrupted = rng.random(n) < 0.3
    sem = np.full((n, 2), 0.001)
    sem[corrupted] = 0.05

    y_obs = y_true.copy()
    y_obs[:, 0] += rng.normal(0, sem[:, 0])
    y_obs[:, 1] += rng.normal(0, sem[:, 1] * 0.2)  # sigma channel: milder
    sem_arr = sem.copy()
    sem_arr[:, 1] *= 0.2

    return X, y_obs, y_true, sem_arr, corrupted


def test_noise_aware_downweights_corrupted() -> None:
    X, y_obs, y_true, sem, corrupted = _make_data()

    torch.manual_seed(0)
    plain = Surrogate(device="cpu")
    plain.fit(X, y_obs, n_iter=100, verbose=False)

    torch.manual_seed(0)
    aware = Surrogate(device="cpu")
    aware.fit(X, y_obs, n_iter=100, verbose=False, y_noise=sem)

    # Evaluate against the CLEAN truth at the training locations
    mu_p, _, _, _ = plain.predict(X)
    mu_a, _, _, _ = aware.predict(X)
    rmse_p = float(np.sqrt(np.mean((mu_p - y_true[:, 0]) ** 2)))
    rmse_a = float(np.sqrt(np.mean((mu_a - y_true[:, 0]) ** 2)))

    print(f"  mu RMSE vs clean truth: plain={rmse_p:.5f}  noise-aware={rmse_a:.5f}")
    assert rmse_a < rmse_p, "noise-aware should beat plain on corrupted data"
    assert rmse_a < 0.004, f"noise-aware absolute accuracy too low: {rmse_a:.5f}"
    print("  [OK] noise-aware GP downweights high-SEM points")


def test_noise_aware_save_load_roundtrip() -> None:
    X, y_obs, _, sem, _ = _make_data(n_cond=20, seed=5)

    torch.manual_seed(0)
    surr = Surrogate(device="cpu")
    surr.fit(X, y_obs, n_iter=50, verbose=False, y_noise=sem)
    mu_before, _, sg_before, _ = surr.predict(X)

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ckpt.pth"
        surr.save(path)
        loaded = Surrogate.load(path, X, y_obs, device="cpu")
        assert loaded._y_noise is not None
        mu_after, _, sg_after, _ = loaded.predict(X)

    assert np.allclose(mu_before, mu_after, atol=1e-6), "mu changed after load"
    assert np.allclose(sg_before, sg_after, atol=1e-6), "sigma changed after load"
    print("  [OK] noise-aware save/load roundtrip (predictions identical)")


def test_backward_compat_no_noise() -> None:
    """y_noise=None path is unchanged; old-style checkpoints still load."""
    X, y_obs, _, _, _ = _make_data(n_cond=15, seed=7)

    torch.manual_seed(0)
    surr = Surrogate(device="cpu")
    surr.fit(X, y_obs, n_iter=30, verbose=False)  # no y_noise
    assert surr._y_noise is None

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ckpt.pth"
        surr.save(path)
        loaded = Surrogate.load(path, X, y_obs, device="cpu")
        assert loaded._y_noise is None
        mu_a, _, _, _ = surr.predict(X)
        mu_b, _, _, _ = loaded.predict(X)
        assert np.allclose(mu_a, mu_b, atol=1e-6)
    print("  [OK] backward-compat: homoscedastic path unchanged")


if __name__ == "__main__":
    print("=== test_noise_aware ===")
    test_noise_aware_downweights_corrupted()
    test_noise_aware_save_load_roundtrip()
    test_backward_compat_no_noise()
    print("\n=== ALL NOISE-AWARE TESTS PASSED ===")
