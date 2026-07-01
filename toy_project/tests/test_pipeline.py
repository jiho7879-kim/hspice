"""End-to-end pipeline test using synthetic data."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from src.toy_surrogate import Surrogate, stratified_train_test_split
from src.toy_physics_layer import gradient_check, compute_vmin_on_grid
from src.utils import load_intermediate
from src.toy_contour import extract_contour


def main():
    X, y = load_intermediate(
        Path(__file__).resolve().parent.parent / "data" / "dataset_synth.npz"
    )
    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y)

    surr = Surrogate(device="cpu")
    surr.fit(X_tr, y_tr, verbose=False, n_iter=100)

    # Test mu prediction
    mu_mean, _, sigma_mean, _ = surr.predict(X_te)
    mu_rmse = float(np.sqrt(np.mean((mu_mean - y_te[:, 0]) ** 2)))
    sigma_rmse = float(np.sqrt(np.mean((sigma_mean - y_te[:, 1]) ** 2)))
    print(f"mu RMSE:    {mu_rmse:.5f}")
    print(f"sigma RMSE: {sigma_rmse:.5f}")
    assert mu_rmse < 0.05, f"mu RMSE too high: {mu_rmse}"
    assert sigma_rmse < 0.01, f"sigma RMSE too high: {sigma_rmse}"

    # Gradient check
    gc = gradient_check(surr)
    print(f"Gradient rational: {gc['rational']}")

    # Contour grid
    def surrogate_fn(x):
        mu, _, sigma, _ = surr.predict(x)
        return mu, sigma

    CN, PU, vmin_grid = compute_vmin_on_grid(surrogate_fn, n_grid=50)
    print(f"Vmin grid: [{np.nanmin(vmin_grid):.3f}, {np.nanmax(vmin_grid):.3f}]")
    print(f"NaN count: {np.isnan(vmin_grid).sum()}")

    pred_cn, pred_pu = extract_contour(vmin_grid, CN, PU, contour_level=0.6)
    print(f"Contour at 0.6V: {len(pred_cn)} points")

    print("\n=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    main()
