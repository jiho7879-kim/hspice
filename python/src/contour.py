"""
PVTA contour identification and validation.

Given a trained surrogate + physics layer, evaluate Vmin on a grid
of (common_N, PU) and extract the Vmin = 0.6V contour line.
Compare with true contour via Hausdorff distance.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from src.utils import (
    COMMON_N_MIN,
    COMMON_N_MAX,
    PU_MIN,
    PU_MAX,
    VOPS,
    VOP_COL,
    WLUD_COL,
    Z_FIXED,
    CN_COL,
    vop_col_for, pu_col_for,
)
from src.physics_layer import (
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
        cn_contour: (M,) common_N coordinates
        pu_contour: (M,) PU coordinates
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    cs = ax.contour(cn_grid, pu_grid, vmin_grid, levels=[contour_level])
    verts = []
    for path in cs.get_paths():
        v = path.vertices
        if len(v) > 1:
            verts.append(v)

    if not verts:
        plt.close(fig)
        return np.array([]), np.array([])

    all_verts = np.concatenate(verts, axis=0)
    plt.close(fig)
    return all_verts[:, 0], all_verts[:, 1]


def hausdorff_distance(
    true_cn: np.ndarray, true_pu: np.ndarray,
    pred_cn: np.ndarray, pred_pu: np.ndarray,
) -> float:
    """Compute Hausdorff distance between two contour point sets.

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
    """Compute overlap ratio of feasible (Vmin <= contour_level) regions.

    Uses Monte Carlo sampling over the (common_N, PU) rectangle.

    Returns:
        overlap_ratio = 2 * |A ^ B| / (|A| + |B|) in [0, 1].
        1.0 = perfect overlap, 0.0 = no overlap.
    """
    import matplotlib.path as mpath

    rng = np.random.default_rng(42)
    pts = rng.uniform(
        low=[COMMON_N_MIN, PU_MIN],
        high=[COMMON_N_MAX, PU_MAX],
        size=(n_grid, 2),
    )

    def _inside(pts_xy: np.ndarray, boundary_cn: np.ndarray, boundary_pu: np.ndarray) -> np.ndarray:
        if len(boundary_cn) == 0:
            return np.zeros(len(pts_xy), dtype=bool)
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
    wlud_fixed: float | None = None,
    holdout_wlud: np.ndarray | None = None,
    vop_col: int = VOP_COL,
) -> dict:
    """Run full contour pipeline and compute validation metrics.

    3D mode (wlud_fixed=None): standard cn, pu, Vop.
    4D mode (wlud_fixed=float): WLUD ratio (Vwl/Vop) held constant.
        If holdout_wlud is provided, it overrides wlud_fixed per holdout point.
    vop_col controls column layout (default VOP_COL=2 for Stage A).

    Returns:
        dict with keys:
            - 'hausdorff_distance_mV'
            - 'area_overlap_ratio'
            - 'max_vmin_error_mV'
            - 'rmse_vmin_mV'
    """
    n_device = vop_col
    pu_col = vop_col - 1
    CN, PU, vmin_grid = compute_vmin_on_grid(
        surrogate_fn, n_grid=n_grid, wlud_fixed=wlud_fixed,
        vop_col=vop_col,
    )

    pred_cn, pred_pu = extract_contour(vmin_grid, CN, PU, contour_level)

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

    h = hausdorff_distance(true_cn, true_pu, pred_cn, pred_pu)
    overlap = area_overlap_ratio(true_cn, true_pu, pred_cn, pred_pu)

    has_wlud = wlud_fixed is not None
    n_dims = (n_device + 1) + (1 if has_wlud else 0)
    holdout_vmin_pred = np.full(len(holdout_cn), np.nan)
    for i in range(len(holdout_cn)):
        X_pt = np.zeros((len(VOPS), n_dims))
        X_pt[:, CN_COL] = holdout_cn[i]
        if n_device > 2:
            X_pt[:, SK_COL] = 0.0
        X_pt[:, pu_col] = holdout_pu[i]
        X_pt[:, vop_col] = VOPS
        if has_wlud:
            wlud = holdout_wlud[i] if holdout_wlud is not None else wlud_fixed
            X_pt[:, WLUD_COL] = wlud
        mu, _, sigma, _ = surrogate_fn(X_pt)
        z = compute_zscore(mu, sigma)
        v = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED)
        holdout_vmin_pred[i] = v[0]

    valid = ~np.isnan(holdout_vmin_pred) & ~np.isnan(holdout_vmin)
    vmin_errors = holdout_vmin_pred[valid] - holdout_vmin[valid]
    rmse_vmin = float(np.sqrt(np.mean(vmin_errors ** 2))) * 1000
    max_error = float(np.max(np.abs(vmin_errors))) * 1000

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
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 6))

    cf = ax.contourf(cn_grid, pu_grid, vmin_grid_pred, levels=20, cmap="viridis", alpha=0.6)
    plt.colorbar(cf, ax=ax, label="Vmin (V)")

    pred_cn, pred_pu = extract_contour(vmin_grid_pred, cn_grid, pu_grid, contour_level)
    ax.plot(pred_cn, pred_pu, "b-", linewidth=2, label=f"Predicted Vmin={contour_level}V")

    ax.scatter(true_cn, true_pu, c="red", s=10, alpha=0.7, label="True contour points")

    corners = {
        "FSG": (-60, 60), "SFG": (60, -60),
        "FFG": (-60, -60), "SSG": (60, 60),
    }
    for name, (cn, pu) in corners.items():
        ax.plot(cn, pu, marker="D", markersize=8, color="red")
        ax.annotate(name, (cn, pu), xytext=(5, 5),
                    textcoords="offset points", fontsize=9)

    ax.set_xlabel("common_N_shift (mV)")
    ax.set_ylabel("PU_shift (mV)")
    ax.set_title(f"Vmin = {contour_level}V Contour - Predicted vs True")
    ax.legend()
    ax.grid(True, alpha=0.3)

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"Contour plot saved: {save_path}")

    plt.close(fig)
