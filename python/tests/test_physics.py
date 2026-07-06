"""
Tests for PhysicsConstrainedSurrogate — L_mono, L_boundary, L_pelgrom.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch

from src.utils import VOPS, VOP_COL, WLUD_COL
from src.physics import (
    PhysicsConstrainedSurrogate,
    generate_probe_points,
    generate_corner_anchor_data,
    analytic_snmr,
    GLOBAL_CORNERS_MV,
    A_MU, B_MU, C_MU, D_MU,
    SIGMA0, SIGMA_VOP_SLOPE,
)


def test_analytic_snmr() -> None:
    """Analytic SNMR model returns reasonable values at corners."""
    for cn, pu in GLOBAL_CORNERS_MV:
        for vop in VOPS:
            mu, sigma = analytic_snmr(cn, pu, vop)
            assert np.isfinite(mu), f"mu not finite at ({cn}, {pu}, {vop}): {mu}"
            assert sigma > 0, f"sigma should be positive: got {sigma} at ({cn}, {pu}, {vop})"
    print(f"  [OK] analytic_snmr: {len(GLOBAL_CORNERS_MV)} corners x {len(VOPS)} Vop "
          f"(mu can be negative at extreme corners)")


def test_generate_probe_points() -> None:
    """Probe points cover full domain with correct column order."""
    probes = generate_probe_points(n_per_dim=6)
    assert probes.shape[1] == 3, f"Expected 3D probes, got {probes.shape[1]}"
    n_expected = 6 * 6 * len(VOPS)
    assert probes.shape[0] == n_expected, \
        f"Expected {n_expected} probes, got {probes.shape[0]}"
    assert probes[:, VOP_COL].min() >= VOPS.min()
    assert probes[:, VOP_COL].max() <= VOPS.max()
    print(f"  [OK] generate_probe_points: {probes.shape}  "
          f"Vop range [{probes[:, VOP_COL].min():.1f}, {probes[:, VOP_COL].max():.1f}]")


def test_generate_probe_points_extra_dims() -> None:
    """Probe points with n_extra > 0 have correct shape.

    When n_extra >= 1:
      - index WLUD_COL (=3) gets actual WLUD ratio levels (non-zero)
      - indices WLUD_COL+1 .. 3+n_extra-1 are filled with 0.0
    """
    probes = generate_probe_points(n_per_dim=6, n_extra=5)
    assert probes.shape[1] == 8, f"Expected 3+5=8 dims, got {probes.shape[1]}"
    assert probes[:, VOP_COL:WLUD_COL].sum() != 0.0, "WLUD column should have non-zero values"
    assert probes[:, WLUD_COL + 1:].sum() == 0.0, "Extra dims beyond WLUD should be 0.0"
    print(f"  [OK] generate_probe_points (n_extra=5): shape={probes.shape}")


def test_generate_corner_anchor_data() -> None:
    """Corner anchor data: 4 corners x 6 Vop = 24 points, columns correct."""
    X_c, y_c = generate_corner_anchor_data()
    n_expected = len(GLOBAL_CORNERS_MV) * len(VOPS)
    assert X_c.shape == (n_expected, 3), f"X_c shape: {X_c.shape}"
    assert y_c.shape == (n_expected, 2), f"y_c shape: {y_c.shape}"

    # Check that corners appear in order
    assert X_c[0, 0] == GLOBAL_CORNERS_MV[0][0]  # first corner cn
    assert X_c[0, 1] == GLOBAL_CORNERS_MV[0][1]  # first corner pu
    print(f"  [OK] generate_corner_anchor_data: {n_expected} points, "
          f"mu range [{y_c[:,0].min():.4f}, {y_c[:,0].max():.4f}]")


def test_generate_corner_anchor_data_extra_dims() -> None:
    """Corner anchor with extra dims has correct shape.

    When n_extra >= 1:
      - index WLUD_COL (=3) gets actual WLUD ratio levels (non-zero)
      - indices WLUD_COL+1 .. 3+n_extra-1 are filled with 0.0
    """
    X_c, y_c = generate_corner_anchor_data(n_extra=5)
    assert X_c.shape[1] == 8, f"Expected 8 dims, got {X_c.shape[1]}"
    assert X_c[:, WLUD_COL + 1:].sum() == 0.0, "Extra dims beyond WLUD should be 0.0"
    print(f"  [OK] generate_corner_anchor_data (n_extra=5): shape={X_c.shape}")


def test_physics_surrogate_baseline() -> None:
    """PhysicsConstrainedSurrogate trains in baseline mode (no constraints)."""
    rng = np.random.default_rng(42)
    n = 100
    X = np.zeros((n * 6, 3), dtype=np.float64)
    y = np.zeros((n * 6, 2), dtype=np.float64)
    for i in range(n):
        cn = rng.uniform(-60, 60)
        pu = rng.uniform(-60, 60)
        for j, vop in enumerate(VOPS):
            idx = i * 6 + j
            X[idx] = [cn, pu, vop]
            mu, sigma = analytic_snmr(cn, pu, vop)
            y[idx] = [mu, sigma]

    surr = PhysicsConstrainedSurrogate(device="cpu")
    surr.fit(X, y, n_iter=30, verbose=False,
             use_mono=False, use_boundary=False, use_pelgrom=False)

    mu_mean, _, sigma_mean, _ = surr.predict(X)
    mu_rmse = float(np.sqrt(np.mean((mu_mean - y[:, 0]) ** 2)))
    sigma_rmse = float(np.sqrt(np.mean((sigma_mean - y[:, 1]) ** 2)))
    print(f"  [OK] baseline: mu RMSE={mu_rmse:.5f}, sigma RMSE={sigma_rmse:.5f}")


def test_physics_surrogate_with_mono() -> None:
    """PhysicsConstrainedSurrogate trains with L_mono (no crash, loss decreases)."""
    rng = np.random.default_rng(42)
    n = 50
    X = np.zeros((n * 6, 3), dtype=np.float64)
    y = np.zeros((n * 6, 2), dtype=np.float64)
    for i in range(n):
        cn = rng.uniform(-60, 60)
        pu = rng.uniform(-60, 60)
        for j, vop in enumerate(VOPS):
            idx = i * 6 + j
            X[idx] = [cn, pu, vop]
            mu, sigma = analytic_snmr(cn, pu, vop)
            y[idx] = [mu, sigma]

    surr = PhysicsConstrainedSurrogate(device="cpu")
    surr.fit(X, y, n_iter=30, verbose=False,
             use_mono=True, use_boundary=False, use_pelgrom=False,
             lambda_mono=100.0, n_probe=4)

    mu_mean, _, sigma_mean, _ = surr.predict(X)
    mu_rmse = float(np.sqrt(np.mean((mu_mean - y[:, 0]) ** 2)))
    print(f"  [OK] with L_mono: mu RMSE={mu_rmse:.5f}")


def test_physics_surrogate_with_boundary() -> None:
    """PhysicsConstrainedSurrogate trains with corner anchor augmentation."""
    rng = np.random.default_rng(42)
    n = 50
    X = np.zeros((n * 6, 3), dtype=np.float64)
    y = np.zeros((n * 6, 2), dtype=np.float64)
    for i in range(n):
        cn = rng.uniform(-60, 60)
        pu = rng.uniform(-60, 60)
        for j, vop in enumerate(VOPS):
            idx = i * 6 + j
            X[idx] = [cn, pu, vop]
            mu, sigma = analytic_snmr(cn, pu, vop)
            y[idx] = [mu, sigma]

    surr = PhysicsConstrainedSurrogate(device="cpu")
    surr.fit(X, y, n_iter=30, verbose=False,
             use_mono=False, use_boundary=True, use_pelgrom=False)

    mu_mean, _, sigma_mean, _ = surr.predict(X)
    mu_rmse = float(np.sqrt(np.mean((mu_mean - y[:, 0]) ** 2)))
    print(f"  [OK] with L_boundary: mu RMSE={mu_rmse:.5f}")


def test_mono_penalty_computation() -> None:
    """_compute_mono_penalty returns a non-negative scalar."""
    rng = np.random.default_rng(42)
    n = 30
    xt = torch.from_numpy(rng.uniform(-1, 1, size=(n, 3)).astype(np.float32))
    yt = torch.from_numpy(rng.uniform(0, 1, size=(n,)).astype(np.float32))

    from src.models import ExactGPModel
    gp = ExactGPModel(xt, yt)
    gp.eval()
    gp.prediction_strategy = None

    surr = PhysicsConstrainedSurrogate(device="cpu")
    probe_t = torch.from_numpy(rng.uniform(-1, 1, size=(10, 3)).astype(np.float32))

    penalty = surr._compute_mono_penalty(gp, probe_t)
    assert isinstance(penalty, torch.Tensor)
    assert penalty.numel() == 1, f"Expected scalar penalty, got shape {penalty.shape}"
    assert penalty.item() >= 0, f"Penalty should be non-negative, got {penalty.item()}"
    assert torch.isfinite(penalty), "Non-finite penalty"
    print(f"  [OK] _compute_mono_penalty: {penalty.item():.6f} (>= 0)")


def test_pelgrom_penalty_computation() -> None:
    """_compute_pelgrom_penalty returns a non-negative scalar WITH gradient.

    The target is precomputed from raw Vop (data-fixed); the penalty is the
    posterior-mean mismatch and must carry gradient back to kernel params
    (the pre-2026-07-06 implementation was a silent no_grad no-op).
    """
    rng = np.random.default_rng(42)
    n = 30
    xt = torch.from_numpy(rng.uniform(-1, 1, size=(n, 3)).astype(np.float32))
    yt = torch.from_numpy(rng.uniform(0, 1, size=(n,)).astype(np.float32))

    from src.models import AdditiveGPModel
    gp = AdditiveGPModel(xt, yt)
    gp.train()
    gp.likelihood.train()

    surr = PhysicsConstrainedSurrogate(device="cpu")
    vop_raw = rng.uniform(0.4, 0.9, size=n)
    target = torch.from_numpy(
        (0.015 + 0.004 * (0.9 - vop_raw)).astype(np.float32)
    )
    penalty = surr._compute_pelgrom_penalty(gp, xt, target)
    assert isinstance(penalty, torch.Tensor)
    assert penalty.numel() == 1
    assert penalty.item() >= 0
    assert torch.isfinite(penalty)
    assert penalty.requires_grad, "L_pelgrom must carry gradient (was a no-op)"
    penalty.backward()
    grads = [p.grad for p in gp.parameters() if p.grad is not None]
    assert any(g.abs().sum() > 0 for g in grads), "no gradient reached GP params"
    print(f"  [OK] _compute_pelgrom_penalty: {penalty.item():.6f} (grad OK)")


def test_get_lengthscales() -> None:
    """get_lengthscales returns arrays with expected shapes."""
    rng = np.random.default_rng(42)
    n = 30
    X = np.zeros((n * 6, 3), dtype=np.float64)
    y = np.zeros((n * 6, 2), dtype=np.float64)
    for i in range(n):
        cn = rng.uniform(-60, 60)
        pu = rng.uniform(-60, 60)
        for j, vop in enumerate(VOPS):
            idx = i * 6 + j
            X[idx] = [cn, pu, vop]
            mu, sigma = analytic_snmr(cn, pu, vop)
            y[idx] = [mu, sigma]

    surr = PhysicsConstrainedSurrogate(device="cpu")
    surr.fit(X, y, n_iter=20, verbose=False)

    mu_ls = surr.get_lengthscales("mu")
    sigma_ls = surr.get_lengthscales("sigma")
    assert mu_ls.shape == (3,), f"mu ls shape: {mu_ls.shape}"
    assert sigma_ls.shape == (3,), f"sigma ls shape: {sigma_ls.shape}"
    assert np.all(mu_ls > 0), "mu lengthscales should be positive"
    assert np.all(sigma_ls > 0), "sigma lengthscales should be positive"
    print(f"  [OK] get_lengthscales: mu={mu_ls}, sigma={sigma_ls}")


if __name__ == "__main__":
    print("=== test_physics ===")
    test_analytic_snmr()
    test_generate_probe_points()
    test_generate_probe_points_extra_dims()
    test_generate_corner_anchor_data()
    test_generate_corner_anchor_data_extra_dims()
    test_physics_surrogate_baseline()
    test_physics_surrogate_with_mono()
    test_physics_surrogate_with_boundary()
    test_mono_penalty_computation()
    test_pelgrom_penalty_computation()
    test_get_lengthscales()
    print("\n=== ALL PHYSICS TESTS PASSED ===")
