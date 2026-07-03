#!/usr/bin/env python3
"""
Physics-Constrained GP Ablation Study — Toy Project (Analytic Data).

Compares 5 configurations:
    1. baseline:  Standard GP (no physics constraints)
    2. mono:      GP + L_mono (Vop up => mu up)
    3. boundary:  GP + corner anchor data augmentation
    4. mono+bnd:  GP + L_mono + corner anchors
    5. all:       GP + L_mono + corner anchors + L_pelgrom

Metrics:
    - mu/sigma RMSE & R^2 on hold-out test set
    - Vmin RMSE on hold-out test set
    - Contour Hausdorff distance (Vmin=0.6V boundary)
    - Area overlap ratio of feasible region
    - Gradient direction check (dVmin/dcn, dVmin/dpu)
    - Lengthscale analysis

Output:
    python/results/ablation/
        contour_comparison.png
        metrics_comparison.png
        error_maps.png
        gradient_table.txt
        lengthscale_table.txt
        ablation_results.json

Usage:
    python scripts/ablation.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import (
    Z_FIXED, VOPS, COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
)
from src.data import load_intermediate, stratified_train_test_split
from src.physics_layer import (
    compute_vmin_from_z, compute_vmin_on_grid, compute_zscore,
)
from src.contour import extract_contour, hausdorff_distance, area_overlap_ratio
from src.physics import (
    PhysicsConstrainedSurrogate,
    analytic_snmr,
    GLOBAL_CORNERS_MV,
)

# ===================================================================
# Configuration
# ===================================================================

OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "ablation"
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_analytic.npz"

N_COND = 400
N_ITER = 120
LR = 0.1

CONFIGS = {
    "baseline": {
        "label": "Baseline GP",
        "color": "#7f8c8d",
        "marker": "o",
        "use_mono": False,
        "use_boundary": False,
        "use_pelgrom": False,
    },
    "mono": {
        "label": "+L_mono",
        "color": "#3498db",
        "marker": "s",
        "use_mono": True,
        "use_boundary": False,
        "use_pelgrom": False,
    },
    "boundary": {
        "label": "+L_boundary",
        "color": "#2ecc71",
        "marker": "^",
        "use_mono": False,
        "use_boundary": True,
        "use_pelgrom": False,
    },
    "mono_boundary": {
        "label": "+Mono+Boundary",
        "color": "#9b59b6",
        "marker": "D",
        "use_mono": True,
        "use_boundary": True,
        "use_pelgrom": False,
    },
    "all": {
        "label": "+Mono+Boundary+Pelgrom",
        "color": "#e67e22",
        "marker": "v",
        "use_mono": True,
        "use_boundary": True,
        "use_pelgrom": True,
    },
}


# ===================================================================
# True Vmin from analytic model
# ===================================================================

def compute_true_vmin_grid(n_grid: int = 60) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute true Vmin on (common_N, PU) grid from analytic model."""
    cna = np.linspace(COMMON_N_MIN, COMMON_N_MAX, n_grid)
    pua = np.linspace(PU_MIN, PU_MAX, n_grid)
    CN, PU = np.meshgrid(cna, pua, indexing="xy")
    true_vmin = np.full_like(CN, np.nan)
    for i in range(n_grid):
        for j in range(n_grid):
            z = np.array([
                analytic_snmr(float(CN[i, j]), float(PU[i, j]), v)[0]
                / analytic_snmr(float(CN[i, j]), float(PU[i, j]), v)[1]
                for v in VOPS
            ])
            true_vmin[i, j] = float(compute_vmin_from_z(z.reshape(1, -1))[0])
    return CN, PU, true_vmin


def compute_true_vmin_at_points(cn_vals: np.ndarray, pu_vals: np.ndarray) -> np.ndarray:
    vmin = np.full(len(cn_vals), np.nan)
    for i in range(len(cn_vals)):
        z = np.array([
            analytic_snmr(float(cn_vals[i]), float(pu_vals[i]), v)[0]
            / analytic_snmr(float(cn_vals[i]), float(pu_vals[i]), v)[1]
            for v in VOPS
        ])
        vmin[i] = float(compute_vmin_from_z(z.reshape(1, -1))[0])
    return vmin


# ===================================================================
# Train a single configuration
# ===================================================================

def train_and_evaluate(
    config_name: str,
    X_train: np.ndarray, y_train: np.ndarray,
    X_test: np.ndarray, y_test: np.ndarray,
    cn_test: np.ndarray, pu_test: np.ndarray,
    true_vmin_test: np.ndarray,
    CN_true: np.ndarray, PU_true: np.ndarray, vmin_true_grid: np.ndarray,
) -> dict:
    """Train model for one config, return all metrics."""
    cfg = CONFIGS[config_name]
    print(f"\n{'=' * 60}")
    print(f"Config: {cfg['label']}")
    print(f"{'=' * 60}")

    surr = PhysicsConstrainedSurrogate(device="cpu", checkpoint_dir=str(OUT_DIR))
    start_t = time.time()
    surr.fit(
        X_train, y_train,
        n_iter=N_ITER, lr=LR, verbose=True,
        use_mono=cfg["use_mono"],
        use_boundary=cfg["use_boundary"],
        use_pelgrom=cfg["use_pelgrom"],
        lambda_mono=100.0,
        lambda_pelgrom=1.0,
        n_probe=5,
        ckpt_tag=config_name,
    )
    train_time = time.time() - start_t

    # Test set evaluation
    mu_pred, mu_std, sigma_pred, sigma_std = surr.predict(X_test)
    mu_rmse = float(np.sqrt(np.mean((mu_pred - y_test[:, 0]) ** 2)))
    mu_r2 = float(1 - np.sum((mu_pred - y_test[:, 0]) ** 2)
                  / np.sum((y_test[:, 0] - np.mean(y_test[:, 0])) ** 2))
    sigma_rmse = float(np.sqrt(np.mean((sigma_pred - y_test[:, 1]) ** 2)))
    sigma_r2 = float(1 - np.sum((sigma_pred - y_test[:, 1]) ** 2)
                     / np.sum((y_test[:, 1] - np.mean(y_test[:, 1])) ** 2))

    def surrogate_fn(x):
        m, _, s, _ = surr.predict(x)
        return m, s

    # Vmin on test conditions
    vmin_pred_test = np.full(len(cn_test), np.nan)
    for i in range(len(cn_test)):
        X_pt = np.zeros((len(VOPS), 3))
        X_pt[:, 0] = cn_test[i]
        X_pt[:, 1] = pu_test[i]
        X_pt[:, 2] = VOPS
        mu, _, sigma, _ = surr.predict(X_pt)
        z = compute_zscore(mu, sigma)
        v = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED)
        vmin_pred_test[i] = float(v[0])

    valid = ~np.isnan(true_vmin_test) & ~np.isnan(vmin_pred_test)
    vmin_errors = vmin_pred_test[valid] - true_vmin_test[valid]
    vmin_rmse = float(np.sqrt(np.mean(vmin_errors ** 2))) * 1000
    vmin_max_err = float(np.max(np.abs(vmin_errors))) * 1000
    vmin_bias = float(np.mean(vmin_errors)) * 1000

    # Vmin contour on full grid
    CN_pred, PU_pred, vmin_grid_pred = compute_vmin_on_grid(
        surrogate_fn, n_grid=40,
    )
    pred_cn, pred_pu = extract_contour(vmin_grid_pred, CN_pred, PU_pred, 0.6)
    true_cn, true_pu = extract_contour(vmin_true_grid, CN_true, PU_true, 0.6)

    if len(pred_cn) > 0 and len(true_cn) > 0:
        h_dist = hausdorff_distance(true_cn, true_pu, pred_cn, pred_pu)
        overlap = area_overlap_ratio(true_cn, true_pu, pred_cn, pred_pu, n_grid=200)
    else:
        h_dist = float("inf")
        overlap = 0.0

    # Gradient check (finite difference at center)
    eps = 1e-2
    def _vmin_at(cn, pu):
        X_pt = np.zeros((len(VOPS), 3))
        X_pt[:, 0] = cn
        X_pt[:, 1] = pu
        X_pt[:, 2] = VOPS
        mu, _, sigma, _ = surr.predict(X_pt)
        z = compute_zscore(mu, sigma)
        v = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED)
        return float(v[0])

    v0 = _vmin_at(0, 0)
    grad_cn_fd = (_vmin_at(eps, 0) - _vmin_at(-eps, 0)) / (2 * eps)
    grad_pu_fd = (_vmin_at(0, eps) - _vmin_at(0, -eps)) / (2 * eps)

    def _true_vmin_at(cn, pu):
        z = np.array([analytic_snmr(cn, pu, v)[0] / analytic_snmr(cn, pu, v)[1] for v in VOPS])
        return float(compute_vmin_from_z(z.reshape(1, -1))[0])
    v0_true = _true_vmin_at(0, 0)
    grad_cn_true = (_true_vmin_at(eps, 0) - _true_vmin_at(-eps, 0)) / (2 * eps)
    grad_pu_true = (_true_vmin_at(0, eps) - _true_vmin_at(0, -eps)) / (2 * eps)

    pred_grad = np.array([grad_cn_fd, grad_pu_fd])
    true_grad = np.array([grad_cn_true, grad_pu_true])
    cos_sim = float(np.dot(pred_grad, true_grad)
                    / (np.linalg.norm(pred_grad) * np.linalg.norm(true_grad) + 1e-12))
    mag_ratio = float(np.linalg.norm(pred_grad) / (np.linalg.norm(true_grad) + 1e-12))

    mu_ls = surr.get_lengthscales("mu").tolist()
    sigma_ls = surr.get_lengthscales("sigma").tolist()

    metrics = {
        "config": config_name,
        "label": cfg["label"],
        "train_time_s": round(train_time, 1),
        "mu_rmse": round(mu_rmse, 6),
        "mu_r2": round(mu_r2, 4),
        "sigma_rmse": round(sigma_rmse, 6),
        "sigma_r2": round(sigma_r2, 4),
        "vmin_rmse_mV": round(vmin_rmse, 3),
        "vmin_max_err_mV": round(vmin_max_err, 3),
        "vmin_bias_mV": round(vmin_bias, 3),
        "hausdorff_mV": round(h_dist, 3) if np.isfinite(h_dist) else None,
        "area_overlap": round(overlap, 4),
        "dVmin_dcn": round(grad_cn_fd, 5),
        "dVmin_dpu": round(grad_pu_fd, 5),
        "grad_cosine_sim": round(cos_sim, 4),
        "grad_mag_ratio": round(mag_ratio, 4),
        "lengthscales_mu": mu_ls,
        "lengthscales_sigma": sigma_ls,
    }

    print(f"\n--- {cfg['label']} Results ---")
    print(f"  mu RMSE={mu_rmse:.6f}  R^2={mu_r2:.4f}")
    print(f"  sigma RMSE={sigma_rmse:.6f}  R^2={sigma_r2:.4f}")
    print(f"  Vmin RMSE={vmin_rmse:.3f} mV  max|err|={vmin_max_err:.3f} mV  bias={vmin_bias:.3f} mV")
    print(f"  Hausdorff={h_dist:.3f} mV  Overlap={overlap:.4f}")
    print(f"  dVmin/dcn={grad_cn_fd:.5f}  dVmin/dpu={grad_pu_fd:.5f}  "
          f"cos_sim={cos_sim:.4f}  mag_ratio={mag_ratio:.4f}")

    return metrics, surr, vmin_grid_pred, CN_pred, PU_pred, pred_cn, pred_pu


# ===================================================================
# Plotting
# ===================================================================

def plot_contour_comparison(CN_true, PU_true, vmin_true_grid, results, save_path):
    """5-panel contour comparison: true + each config."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    axes_flat = axes.flatten()
    corner_style = {"FSG": (-60, 60), "SFG": (60, -60),
                    "FFG": (-60, -60), "SSG": (60, 60)}

    for idx, (name, res) in enumerate(results.items()):
        ax = axes_flat[idx]
        cfg = CONFIGS[name]
        vmin_grid_pred = res["vmin_grid"]
        CN_pred, PU_pred = res["CN"], res["PU"]

        cf = ax.contourf(CN_pred, PU_pred, vmin_grid_pred,
                         levels=np.linspace(0.3, 0.9, 25),
                         cmap="RdYlBu_r", alpha=0.65)
        if idx == 0:
            plt.colorbar(cf, ax=ax, label="Vmin (V)", shrink=0.85)

        true_cn, true_pu = extract_contour(vmin_true_grid, CN_true, PU_true, 0.6)
        if len(true_cn) > 0:
            ax.plot(true_cn, true_pu, "k--", linewidth=2, alpha=0.8,
                    label="True Vmin=0.6V")

        pred_cn, pred_pu = res["pred_cn"], res["pred_pu"]
        if len(pred_cn) > 0:
            ax.plot(pred_cn, pred_pu, color=cfg["color"], linewidth=2.5,
                    label="Pred Vmin=0.6V")

        for cname, (cn, pu) in corner_style.items():
            ax.plot(cn, pu, "D", color="darkred", markersize=6, zorder=5)

        hausdorff = res["metrics"]["hausdorff_mV"]
        overlap = res["metrics"]["area_overlap"]
        h_str = f"{hausdorff:.1f}" if hausdorff is not None else "inf"

        ax.set_title(f"{cfg['label']}  |  H={h_str}mV  Ov={overlap:.3f}",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("common_N (mV)", fontsize=9)
        ax.set_ylabel("PU (mV)", fontsize=9)
        ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX)
        ax.set_ylim(PU_MIN, PU_MAX)
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(True, alpha=0.15)
        ax.axhline(0, color="gray", linewidth=0.5)
        ax.axvline(0, color="gray", linewidth=0.5)

    axes_flat[-1].set_visible(False)
    fig.suptitle("PVTA Contour (Vmin=0.6V): Baseline vs Physics-Constrained GP",
                 fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Contour comparison saved: {save_path}")


def plot_metrics_comparison(all_metrics, save_path):
    """Grouped bar chart of key metrics across configs."""
    configs_list = list(all_metrics.keys())
    metric_defs = [
        ("mu_rmse", "mu RMSE", 1e3, True, "{:.2f}"),
        ("sigma_rmse", "sigma RMSE", 1e3, True, "{:.2f}"),
        ("vmin_rmse_mV", "Vmin RMSE (mV)", 1, True, "{:.1f}"),
        ("hausdorff_mV", "Hausdorff (mV)", 1, True, "{:.1f}"),
        ("mu_r2", "mu R^2", 1, False, "{:.3f}"),
        ("sigma_r2", "sigma R^2", 1, False, "{:.3f}"),
        ("area_overlap", "Area Overlap", 1, False, "{:.3f}"),
        ("grad_cosine_sim", "Grad Cos Sim", 1, False, "{:.3f}"),
    ]

    fig, axes = plt.subplots(2, 4, figsize=(18, 9))
    axes_flat = axes.flatten()
    x = np.arange(len(configs_list))

    for ax_i, (key, label, scale, lower_better, fmt) in enumerate(metric_defs):
        ax = axes_flat[ax_i]
        values = [all_metrics[c][key] for c in configs_list]
        colors = [CONFIGS[c]["color"] for c in configs_list]
        bars = ax.bar(x, [v * scale for v in values], width=0.6,
                      color=colors, alpha=0.8, edgecolor="gray", linewidth=0.5)
        for bar, val in zip(bars, values):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2., height,
                    fmt.format(val), ha="center", va="bottom" if height > 0 else "top",
                    fontsize=7, rotation=45)
        ax.set_xticks(x)
        ax.set_xticklabels([CONFIGS[c]["label"] for c in configs_list],
                           fontsize=7, rotation=15, ha="right")
        ax.set_ylabel(label, fontsize=9)
        ax.set_title(f"{label} {'Down' if lower_better else 'Up'}",
                     fontsize=10, fontweight="bold")
        ax.grid(True, alpha=0.15, axis="y")

    fig.suptitle("Physics-Constrained Ablation: Metrics Comparison",
                 fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Metrics comparison saved: {save_path}")


def plot_error_map(CN_true, PU_true, vmin_true_grid, results, save_path):
    """Error maps for all configurations."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    axes_flat = axes.flatten()

    for idx, (name, res) in enumerate(results.items()):
        ax = axes_flat[idx]
        cfg = CONFIGS[name]
        vmin_pred = res["vmin_grid"]
        CN_pred, PU_pred = res["CN"], res["PU"]
        error = vmin_pred - vmin_true_grid
        vmax = max(abs(np.nanmin(error)), abs(np.nanmax(error)))
        cf = ax.contourf(CN_pred, PU_pred, error,
                         levels=np.linspace(-vmax, vmax, 21),
                         cmap="bwr", alpha=0.85)
        if idx == 0:
            plt.colorbar(cf, ax=ax, label="Vmin error (V)", shrink=0.85)
        ax.contour(CN_pred, PU_pred, error, levels=[0],
                   colors="k", linewidths=0.6, linestyles="--", alpha=0.4)
        true_cn, true_pu = extract_contour(vmin_true_grid, CN_true, PU_true, 0.6)
        if len(true_cn) > 0:
            ax.plot(true_cn, true_pu, "k--", linewidth=1.5, alpha=0.6)
        vmin_rmse = res["metrics"]["vmin_rmse_mV"]
        ax.set_title(f"{cfg['label']}  |  RMSE={vmin_rmse:.2f} mV",
                     fontsize=11, fontweight="bold")
        ax.set_xlabel("common_N (mV)", fontsize=9)
        ax.set_ylabel("PU (mV)", fontsize=9)
        ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX)
        ax.set_ylim(PU_MIN, PU_MAX)
        ax.grid(True, alpha=0.15)
        ax.axhline(0, color="gray", linewidth=0.5)
        ax.axvline(0, color="gray", linewidth=0.5)

    axes_flat[-1].set_visible(False)
    fig.suptitle("Vmin Prediction Error: Baseline vs Physics-Constrained",
                 fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Error maps saved: {save_path}")


# ===================================================================
# Tables
# ===================================================================

def print_gradient_table(all_metrics):
    lines = ["=" * 80]
    lines.append("Gradient Fidelity Comparison")
    lines.append("=" * 80)
    lines.append(f"{'Config':<25} {'dV/dcn':>10} {'dV/dpu':>10} "
                 f"{'Cos Sim':>10} {'Mag Ratio':>10} {'Phys OK?':>10}")
    lines.append("-" * 80)
    for name, m in all_metrics.items():
        label = CONFIGS[name]["label"]
        phys_ok = (m["dVmin_dcn"] < 0 and m["dVmin_dpu"] > 0)
        lines.append(
            f"{label:<25} {m['dVmin_dcn']:>10.5f} {m['dVmin_dpu']:>10.5f} "
            f"{m['grad_cosine_sim']:>10.4f} {m['grad_mag_ratio']:>10.4f} "
            f"{'[OK]' if phys_ok else '[NO]':>10}")
    lines.append("-" * 80)
    lines.append(f"{'Analytic True':<25} {'':>10} {'':>10} "
                 f"{'1.0000':>10} {'1.0000':>10} {'[OK]':>10}")
    lines.append("=" * 80)
    return "\n".join(lines)


def print_lengthscale_table(all_metrics):
    lines = ["=" * 70]
    lines.append("ARD Lengthscale Comparison (smaller = more important)")
    lines.append("=" * 70)
    lines.append(f"{'Config':<25} {'mu cn':>8} {'mu pu':>8} {'mu Vop':>8} "
                 f"{'l_pu/l_cn':>10} {'PG>>PU?':>10}")
    lines.append("-" * 70)
    for name, m in all_metrics.items():
        label = CONFIGS[name]["label"]
        ls = m["lengthscales_mu"]
        ratio = ls[1] / (ls[0] + 1e-12)
        pg_gt_pu = ratio > 1.3
        lines.append(
            f"{label:<25} {ls[0]:>8.2f} {ls[1]:>8.2f} {ls[2]:>8.2f} "
            f"{ratio:>10.2f} {'[OK]' if pg_gt_pu else '[NO]':>10}")
    lines.append("=" * 70)
    return "\n".join(lines)


# ===================================================================
# Main
# ===================================================================

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Physics-Constrained GP Ablation Study")
    print("=" * 60)
    print(f"Data: {DATA_PATH}")

    X, y = load_intermediate(str(DATA_PATH))
    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.15)
    conditions_te = X_te[::len(VOPS), :2]
    cn_test = conditions_te[:, 0]
    pu_test = conditions_te[:, 1]
    true_vmin_test = compute_true_vmin_at_points(cn_test, pu_test)

    print(f"Train: {len(X_tr)}  Test: {len(X_te)}")
    print(f"Test conditions: {len(cn_test)}")

    print("\nComputing true Vmin grid from analytic model...")
    CN_true, PU_true, vmin_true_grid = compute_true_vmin_grid(n_grid=40)

    all_results = {}
    all_metrics = {}

    for name in CONFIGS:
        metrics, surr, vmin_grid, CN_pred, PU_pred, pred_cn, pred_pu = \
            train_and_evaluate(
                name, X_tr, y_tr, X_te, y_te,
                cn_test, pu_test, true_vmin_test,
                CN_true, PU_true, vmin_true_grid,
            )
        all_metrics[name] = metrics
        all_results[name] = {
            "metrics": metrics, "surr": surr,
            "vmin_grid": vmin_grid, "CN": CN_pred, "PU": PU_pred,
            "pred_cn": pred_cn, "pred_pu": pred_pu,
        }

    # Summary table
    print("\n")
    print("=" * 80)
    print("SUMMARY: All Configurations")
    print("=" * 80)
    header = (f"{'Config':<22} {'mu R^2':>8} {'sigma R^2':>8} {'VminRMSE':>10} "
              f"{'Hausdorff':>10} {'Overlap':>8} {'GradCos':>8} {'Time(s)':>8}")
    print(header)
    print("-" * 80)
    for name in CONFIGS:
        m = all_metrics[name]
        h_str = f"{m['hausdorff_mV']:.1f}" if m['hausdorff_mV'] is not None else "inf"
        print(f"{CONFIGS[name]['label']:<22} {m['mu_r2']:>8.4f} {m['sigma_r2']:>8.4f} "
              f"{m['vmin_rmse_mV']:>8.2f}mV {h_str:>8}mV {m['area_overlap']:>8.4f} "
              f"{m['grad_cosine_sim']:>8.4f} {m['train_time_s']:>7.1f}s")
    print("=" * 80)

    # Tables
    grad_table = print_gradient_table(all_metrics)
    print(grad_table)
    ls_table = print_lengthscale_table(all_metrics)
    print(ls_table)

    with open(OUT_DIR / "gradient_table.txt", "w") as f:
        f.write(grad_table)
    with open(OUT_DIR / "lengthscale_table.txt", "w") as f:
        f.write(ls_table)

    # Save metrics JSON
    json_metrics = {name: {k: v for k, v in m.items()}
                    for name, m in all_metrics.items()}
    with open(OUT_DIR / "ablation_results.json", "w") as f:
        json.dump(json_metrics, f, indent=2)
    print(f"\nMetrics saved: {OUT_DIR / 'ablation_results.json'}")

    # Plots
    print("\n--- Generating plots ---")
    plot_contour_comparison(CN_true, PU_true, vmin_true_grid, all_results,
                            OUT_DIR / "contour_comparison.png")
    plot_metrics_comparison(all_metrics, OUT_DIR / "metrics_comparison.png")
    plot_error_map(CN_true, PU_true, vmin_true_grid, all_results,
                   OUT_DIR / "error_maps.png")

    print(f"\nAll results saved to: {OUT_DIR}")
    print("Done.")


if __name__ == "__main__":
    main()
