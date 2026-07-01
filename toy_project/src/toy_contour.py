"""
PVTA contour identification and validation.

Given a trained surrogate + physics layer, evaluate Vmin on a 50x50 grid
of (common_N, PU) and extract the Vmin = 0.6V contour line.
Compare with true HSPICE contour via Hausdorff distance.

Usage:
    python src/toy_contour.py --surrogate ./results/model.pt --data ./data/dataset.npz
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import (
    COMMON_N_MIN,
    COMMON_N_MAX,
    PU_MIN,
    PU_MAX,
    VOPS,
    Z_FIXED,
    load_intermediate,
)
from src.toy_physics_layer import (
    PhysicsLayer,
    compute_vmin_on_grid,
    compute_vmin_from_z,
    compute_zscore,
)


def extract_contour(
    vmin_grid: np.ndarray,
    cn_grid: np.ndarray,
    pu_grid: np.ndarray,
    contour_level: float = 0.6,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract Vmin = contour_level contour as (common_N, PU) point set.

    Uses matplotlib's contour path extraction.

    Returns:
        cn_contour: (M,) common_N coordinates of contour points
        pu_contour: (M,) PU coordinates of contour points
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    cs = ax.contour(cn_grid, pu_grid, vmin_grid, levels=[contour_level])
    # Collect vertices from all contour segments
    verts = []
    for path in cs.get_paths():
        v = path.vertices
        if len(v) > 1:
            verts.append(v)

    if not verts:
        return np.array([]), np.array([])

    all_verts = np.concatenate(verts, axis=0)
    plt.close(fig)
    return all_verts[:, 0], all_verts[:, 1]


def hausdorff_distance(
    true_cn: np.ndarray, true_pu: np.ndarray,
    pred_cn: np.ndarray, pred_pu: np.ndarray,
) -> float:
    """Compute directed Hausdorff distance between two contour point sets.

    Uses scipy.spatial.distance.directed_hausdorff.

    Returns:
        max distance (mV in common_N/PU space).
    """
    from scipy.spatial.distance import directed_hausdorff

    if len(true_cn) == 0 or len(pred_cn) == 0:
        return float("inf")

    true_pts = np.column_stack([true_cn, true_pu])
    pred_pts = np.column_stack([pred_cn, pred_pu])

    d1 = directed_hausdorff(true_pts, pred_pts)[0]
    d2 = directed_hausdorff(pred_pts, true_pts)[0]
    return max(d1, d2)


def area_overlap_ratio(
    true_cn: np.ndarray, true_pu: np.ndarray,
    pred_cn: np.ndarray, pred_pu: np.ndarray,
    n_grid: int = 200,
) -> float:
    """Compute overlap ratio of feasible (Vmin <= 0.6V) regions.

    Uses Monte Carlo sampling over the (common_N, PU) rectangle.

    Returns:
        overlap_ratio = 2 * |A ^ B| / (|A| + |B|) in [0, 1].
        1.0 = perfect overlap, 0.0 = no overlap.
    """
    # Monte Carlo estimation
    rng = np.random.default_rng(42)
    pts = rng.uniform(
        low=[COMMON_N_MIN, PU_MIN],
        high=[COMMON_N_MAX, PU_MAX],
        size=(n_grid, 2),
    )

    # Check if each point is inside true/pred feasible region using
    # matplotlib Path.contains_points
    import matplotlib.path as mpath

    def _inside(pts_xy: np.ndarray, boundary_cn: np.ndarray, boundary_pu: np.ndarray) -> np.ndarray:
        if len(boundary_cn) == 0:
            return np.zeros(len(pts_xy), dtype=bool)
        # Sort boundary points by angle around centroid for proper polygon ordering
        cx, cy = np.mean(boundary_cn), np.mean(boundary_pu)
        angles = np.arctan2(boundary_pu - cy, boundary_cn - cx)
        order = np.argsort(angles)
        boundary = np.column_stack([boundary_cn[order], boundary_pu[order]])
        path = mpath.Path(boundary)
        return path.contains_points(pts_xy)

    in_true = _inside(pts, true_cn, true_pu)
    in_pred = _inside(pts, pred_cn, pred_pu)

    intersect = np.sum(in_true & in_pred)
    union_approx = np.sum(in_true) + np.sum(in_pred)
    if union_approx == 0:
        return 1.0
    return 2.0 * intersect / union_approx


def compute_full_pipeline(
    surrogate_fn: callable,
    holdout_cn: np.ndarray,
    holdout_pu: np.ndarray,
    holdout_vmin: np.ndarray,
    n_grid: int = 50,
    contour_level: float = 0.6,
) -> dict:
    """Run full contour pipeline and compute validation metrics.

    Args:
        surrogate_fn: callable(X_grid) -> mu, sigma
        holdout_cn: (H,) common_N values for true contour points
        holdout_pu: (H,) PU values for true contour points
        holdout_vmin: (H,) true Vmin at those points
        n_grid: Grid resolution for contour inference.

    Returns:
        dict with keys:
            - 'hausdorff_distance_mV': Hausdorff distance
            - 'area_overlap_ratio': overlap of feasible region
            - 'max_vmin_error_mV': max |Vmin_pred - Vmin_true| at holdout points
            - 'rmse_vmin_mV': RMSE of Vmin at holdout points
    """
    # Compute predicted Vmin on grid
    CN, PU, vmin_grid = compute_vmin_on_grid(
        surrogate_fn, n_grid=n_grid,
    )

    # Extract predicted contour
    pred_cn, pred_pu = extract_contour(vmin_grid, CN, PU, contour_level)

    # True contour from holdout
    # (Holdout points are already near Vmin=0.6V -- extract boundary)
    true_cn, true_pu = extract_contour(
        holdout_vmin.reshape(
            int(np.sqrt(len(holdout_vmin))),
            int(np.sqrt(len(holdout_vmin))),
        ),
        holdout_cn.reshape(
            int(np.sqrt(len(holdout_cn))),
            int(np.sqrt(len(holdout_cn))),
        ),
        holdout_pu.reshape(
            int(np.sqrt(len(holdout_pu))),
            int(np.sqrt(len(holdout_pu))),
        ),
        contour_level,
    )

    # Metrics
    h = hausdorff_distance(true_cn, true_pu, pred_cn, pred_pu)
    overlap = area_overlap_ratio(true_cn, true_pu, pred_cn, pred_pu)

    # Vmin error at holdout points
    # Predict Vmin at each holdout condition
    holdout_vmin_pred = np.full(len(holdout_cn), np.nan)
    for i in range(len(holdout_cn)):
        X_pt = np.zeros((len(VOPS), 3))
        X_pt[:, 0] = holdout_cn[i]
        X_pt[:, 1] = holdout_pu[i]
        X_pt[:, 2] = VOPS
        mu, _, sigma, _ = surrogate_fn(X_pt)
        z = compute_zscore(mu, sigma)
        v = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED)
        holdout_vmin_pred[i] = v[0]

    valid = ~np.isnan(holdout_vmin_pred) & ~np.isnan(holdout_vmin)
    vmin_errors = holdout_vmin_pred[valid] - holdout_vmin[valid]
    rmse_vmin = float(np.sqrt(np.mean(vmin_errors ** 2))) * 1000  # V -> mV
    max_error = float(np.max(np.abs(vmin_errors))) * 1000  # V -> mV

    result = {
        "hausdorff_distance_mV": float(h),
        "area_overlap_ratio": float(overlap),
        "rmse_vmin_mV": rmse_vmin,
        "max_vmin_error_mV": max_error,
        "n_contour_pred": len(pred_cn),
        "n_contour_true": len(true_cn),
    }

    print(f"\n--- Contour Validation ---")
    print(f"  Hausdorff distance:        {h:.3f} mV")
    print(f"  Area overlap ratio:         {overlap:.4f}")
    print(f"  Vmin RMSE (hold-out):       {rmse_vmin:.3f} mV")
    print(f"  Vmin max error (hold-out):  {max_error:.3f} mV")

    return result


def plot_contour_comparison(
    cn_grid: np.ndarray,
    pu_grid: np.ndarray,
    vmin_grid_pred: np.ndarray,
    true_cn: np.ndarray,
    true_pu: np.ndarray,
    contour_level: float = 0.6,
    save_path: str | Path | None = None,
) -> None:
    """Plot predicted vs true Vmin contour overlay."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 6))

    # Filled contour of predicted Vmin
    cf = ax.contourf(cn_grid, pu_grid, vmin_grid_pred, levels=20, cmap="viridis", alpha=0.6)
    plt.colorbar(cf, ax=ax, label="Vmin (V)")

    # Predicted contour line
    pred_cn, pred_pu = extract_contour(vmin_grid_pred, cn_grid, pu_grid, contour_level)
    ax.plot(pred_cn, pred_pu, "b-", linewidth=2, label=f"Predicted Vmin={contour_level}V")

    # True contour (from hold-out HSPICE data)
    ax.scatter(true_cn, true_pu, c="red", s=10, alpha=0.7, label="True HSPICE contour points")

    # Corner markers
    corners = {
        "FSG": (-60, 60),
        "SFG": (60, -60),
        "FFG": (-60, -60),
        "SSG": (60, 60),
    }
    for name, (cn, pu) in corners.items():
        ax.plot(cn, pu, marker="D", markersize=8, color="red")
        ax.annotate(name, (cn, pu), xytext=(5, 5),
                    textcoords="offset points", fontsize=9)

    ax.set_xlabel("common_N_shift (mV)")
    ax.set_ylabel("PU_shift (mV)")
    ax.set_title(f"Vmin = {contour_level}V Contour -- Predicted vs True")
    ax.legend()
    ax.grid(True, alpha=0.3)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Contour plot saved: {save_path}")

    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="PVTA contour extraction + validation")
    parser.add_argument("--data", default="./data/dataset.npz")
    parser.add_argument("--out_dir", default="./results")
    parser.add_argument("--n_grid", type=int, default=50)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    X, y = load_intermediate(args.data)

    # Train surrogate
    print("Training surrogate...")
    from src.toy_surrogate import Surrogate, stratified_train_test_split

    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.2)
    surr = Surrogate(device="cpu")
    surr.fit(X_tr, y_tr, verbose=True)

    # Predict function for contour pipeline
    def surrogate_fn(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        mu, _, sigma, _ = surr.predict(x)
        return mu, sigma

    # Run validation
    # (Note: in actual usage, pass true HSPICE hold-out data)
    print("\n--- Contour Pipeline ---")
    CN, PU, vmin_grid = compute_vmin_on_grid(surrogate_fn, n_grid=args.n_grid)

    # Extract and save contour
    pred_cn, pred_pu = extract_contour(vmin_grid, CN, PU, contour_level=0.6)
    print(f"Predicted contour: {len(pred_cn)} points")

    # Save results
    np.savez(out_dir / "contour_pred.npz",
             cn_contour=pred_cn, pu_contour=pred_pu,
             cn_grid=CN, pu_grid=PU, vmin_grid=vmin_grid)

    # Plot
    # (Without true HSPICE contour data, we skip validation metrics)
    plot_contour_comparison(
        CN, PU, vmin_grid,
        true_cn=np.array([]), true_pu=np.array([]),
        save_path=out_dir / "contour_predicted.png",
    )

    print(f"\nResults saved to {out_dir}")


if __name__ == "__main__":
    main()
