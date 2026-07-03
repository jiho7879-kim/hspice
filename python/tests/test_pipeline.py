"""
End-to-end pipeline test using synthetic data (analytical demo model).

Trains a GP surrogate on analytic data, runs physics layer, checks Vmin
contour extraction.  Mirrors the old toy_project test but with updated imports.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.utils import VOPS, Z_FIXED
from src.data import build_dataset, stratified_train_test_split
from src.surrogate import Surrogate
from src.physics_layer import (
    compute_vmin_from_z, compute_vmin_on_grid, gradient_check,
)
from src.contour import extract_contour


def test_surrogate_predict_shape() -> None:
    """surrogate.predict returns 4 arrays of shape (N,)."""
    rng = np.random.default_rng(42)
    n_cond = 30
    X = build_dataset(n_cond)
    y = np.zeros((len(X), 2))
    for i in range(len(X)):
        cn, pu, vop = X[i]
        y[i] = [0.15 * vop + 0.001 * cn - 0.0015 * pu,
                0.015 + 0.004 * (0.9 - vop)]

    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.2)
    surr = Surrogate(device="cpu")
    surr.fit(X_tr, y_tr, verbose=False, n_iter=100)

    mu_mean, mu_std, sigma_mean, sigma_std = surr.predict(X_te)
    assert mu_mean.shape == (len(X_te),)
    assert mu_std.shape == (len(X_te),)
    assert sigma_mean.shape == (len(X_te),)
    assert sigma_std.shape == (len(X_te),)
    print(f"  [OK] predict shapes: mu({mu_mean.shape}), sigma({sigma_mean.shape})")


def test_compute_vmin_from_z() -> None:
    """compute_vmin_from_z returns reasonable Vmin values."""
    z = np.array([[3.0, 3.5, 4.0, 4.5, 5.0, 5.5]], dtype=np.float64)
    vmin = compute_vmin_from_z(z, z_target=4.0, vops=VOPS)
    assert vmin.shape == (1,)
    assert vmin[0] >= VOPS[0] - 0.1
    assert vmin[0] <= VOPS[-1] + 0.1
    print(f"  [OK] compute_vmin_from_z: Vmin={vmin[0]:.4f} V  (z_target=4.0)")


def test_compute_vmin_on_grid() -> None:
    """compute_vmin_on_grid returns grids with correct shape."""
    def _surr_fn(x):
        n = len(x)
        mu = 0.15 * x[:, 2] + 0.001 * x[:, 0] - 0.0015 * x[:, 1]
        sigma = np.full(n, 0.015)
        return mu, sigma

    CN, PU, vmin_grid = compute_vmin_on_grid(_surr_fn, n_grid=20)
    assert CN.shape == (20, 20)
    assert PU.shape == (20, 20)
    assert vmin_grid.shape == (20, 20)
    valid = vmin_grid[~np.isnan(vmin_grid)]
    assert len(valid) > 0, "All Vmin values are NaN"
    print(f"  [OK] compute_vmin_on_grid: grid(20,20), "
          f"Vmin=[{np.nanmin(vmin_grid):.3f}, {np.nanmax(vmin_grid):.3f}]")


def test_extract_contour() -> None:
    """extract_contour returns contour points for a valid level."""
    rng = np.random.default_rng(42)
    n = 30
    cna = np.linspace(-60, 60, n)
    pua = np.linspace(-60, 60, n)
    CN, PU = np.meshgrid(cna, pua, indexing="xy")
    vmin = 0.5 + 0.3 * (CN / 60) ** 2 + 0.3 * (PU / 60) ** 2

    cn_c, pu_c = extract_contour(vmin, CN, PU, contour_level=0.6)
    assert len(cn_c) > 0, "No contour points found"
    assert len(cn_c) == len(pu_c)
    print(f"  [OK] extract_contour: {len(cn_c)} points at Vmin=0.6V")


def test_gradient_check() -> None:
    """gradient_check runs without error and returns dict with keys."""
    rng = np.random.default_rng(42)
    n_cond = 30
    X = build_dataset(n_cond)
    y = np.zeros((len(X), 2))
    for i in range(len(X)):
        cn, pu, vop = X[i]
        y[i] = [0.15 * vop + 0.001 * cn - 0.0015 * pu,
                0.015 + 0.004 * (0.9 - vop)]

    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.2)
    surr = Surrogate(device="cpu")
    surr.fit(X_tr, y_tr, verbose=False, n_iter=100)

    result = gradient_check(surr, eps=1e-2)
    assert "Vmin at (0,0)" in result
    assert "dVmin/dcommon_N" in result
    assert "dVmin/dPU" in result
    assert "rational" in result
    print(f"  [OK] gradient_check: {result}")


def run_pipeline() -> None:
    """Full pipeline: build data -> train -> predict -> Vmin -> contour."""
    print("\n--- Full pipeline test ---")
    rng = np.random.default_rng(42)
    N_COND = 50
    X = build_dataset(N_COND)
    y = np.zeros((len(X), 2))
    for i in range(len(X)):
        cn, pu, vop = X[i]
        y[i] = [0.15 * vop + 0.001 * cn - 0.0015 * pu,
                0.015 + 0.004 * (0.9 - vop)]

    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.2)
    surr = Surrogate(device="cpu")
    surr.fit(X_tr, y_tr, verbose=False, n_iter=200)

    mu_mean, _, sigma_mean, _ = surr.predict(X_te)
    mu_rmse = float(np.sqrt(np.mean((mu_mean - y_te[:, 0]) ** 2)))
    sigma_rmse = float(np.sqrt(np.mean((sigma_mean - y_te[:, 1]) ** 2)))
    print(f"  mu RMSE:    {mu_rmse:.5f}")
    print(f"  sigma RMSE: {sigma_rmse:.5f}")
    assert mu_rmse < 0.05, f"mu RMSE too high: {mu_rmse}"
    assert sigma_rmse < 0.008, f"sigma RMSE too high: {sigma_rmse}"

    def surrogate_fn(x):
        mu, _, sigma, _ = surr.predict(x)
        return mu, sigma

    CN, PU, vmin_grid = compute_vmin_on_grid(surrogate_fn, n_grid=30)
    print(f"  Vmin range: [{np.nanmin(vmin_grid):.3f}, {np.nanmax(vmin_grid):.3f}]")
    assert not np.all(np.isnan(vmin_grid)), "All Vmin grid values are NaN"

    pred_cn, pred_pu = extract_contour(vmin_grid, CN, PU, contour_level=0.6)
    print(f"  Contour at Vmin=0.6V: {len(pred_cn)} points")

    print("\n=== ALL PIPELINE CHECKS PASSED ===")


if __name__ == "__main__":
    print("=== test_pipeline ===")
    test_surrogate_predict_shape()
    test_compute_vmin_from_z()
    test_compute_vmin_on_grid()
    test_extract_contour()
    test_gradient_check()
    run_pipeline()
