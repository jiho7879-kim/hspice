"""
Diagnostic plots for pred-true gap analysis.
Creates multi-panel figures analyzing error structure from multiple angles.

Usage:
    python scripts/diagnostics.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from scipy import stats

from src.utils import (
    Z_FIXED, VOPS, COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
)
from src.data import load_intermediate, stratified_train_test_split
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z

# Parameters (must match demo.py)
A_MU, B_MU, C_MU, D_MU = 0.15, 0.001, -0.0015, 0.0
SIGMA0, SIGMA_VOP_SLOPE = 0.015, 0.004


def analytic_snmr(cn_mv, pu_mv, vop_v):
    mu = A_MU * vop_v + B_MU * cn_mv + C_MU * pu_mv + D_MU
    sigma = SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - vop_v)
    return mu, sigma


def train_or_load():
    data_path = Path(__file__).resolve().parent.parent / "data" / "demo_analytic.npz"
    X, y = load_intermediate(str(data_path))
    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.15)
    surr = Surrogate(device="cpu")
    surr.fit(X_tr, y_tr, verbose=False, n_iter=150)
    return X, y, X_tr, X_te, y_tr, y_te, surr


def quadrant(cn, pu):
    if cn < 0 and pu > 0:
        return "FSG"
    if cn > 0 and pu < 0:
        return "SFG"
    if cn < 0 and pu < 0:
        return "FFG"
    return "SSG"


def main():
    out_dir = Path(__file__).resolve().parent.parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== Training surrogate ===")
    X, y, X_tr, X_te, y_tr, y_te, surr = train_or_load()

    mu_pred, mu_std, sigma_pred, sigma_std = surr.predict(X)

    true_mu = np.array([analytic_snmr(X[i, 0], X[i, 1], X[i, 2])[0] for i in range(len(X))])
    true_sigma = np.array([analytic_snmr(X[i, 0], X[i, 1], X[i, 2])[1] for i in range(len(X))])

    errors_mu = mu_pred - true_mu
    errors_sigma = sigma_pred - true_sigma

    def compute_vmin(mu_arr, sigma_arr):
        z = mu_arr / (sigma_arr + 1e-12)
        return compute_vmin_from_z(z.reshape(-1, 6), z_target=Z_FIXED)

    n_cond = len(X) // 6
    true_vmin_all = np.full(n_cond, np.nan)
    pred_vmin_all = np.full(n_cond, np.nan)
    cn_vals = np.zeros(n_cond)
    pu_vals = np.zeros(n_cond)
    quad_names = []
    for i in range(n_cond):
        idx = slice(i * 6, (i + 1) * 6)
        cn_vals[i], pu_vals[i] = X[idx][0, 0], X[idx][0, 1]
        quad_names.append(quadrant(cn_vals[i], pu_vals[i]))
        true_vmin_all[i] = compute_vmin(true_mu[idx].reshape(1, 6), true_sigma[idx].reshape(1, 6))[0]
        pred_vmin_all[i] = compute_vmin(mu_pred[idx].reshape(1, 6), sigma_pred[idx].reshape(1, 6))[0]

    vmin_error = pred_vmin_all - true_vmin_all
    valid_vmin = ~(np.isnan(true_vmin_all) | np.isnan(pred_vmin_all))

    mu_ls = surr.get_lengthscales("mu")
    sigma_ls = surr.get_lengthscales("sigma")

    # ================================================================
    # FIGURE 1: Error Profile by Vop
    # ================================================================
    print("  Figure 1: error_by_vop.png")
    fig1, axes1 = plt.subplots(1, 2, figsize=(12, 4.5))

    ax = axes1[0]
    mu_means, mu_stds = [], []
    for vop in VOPS:
        mask = X[:, 2] == vop
        e = errors_mu[mask]
        mu_means.append(e.mean())
        mu_stds.append(e.std())
    ax.errorbar(VOPS, mu_means, yerr=mu_stds, fmt="o-", capsize=4, capthick=1.5, color="C0")
    ax.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Vop (V)")
    ax.set_ylabel("mu error (V)")
    ax.set_title("(a) mu prediction error by Vop")
    ax.grid(True, alpha=0.2)

    ax = axes1[1]
    sg_means, sg_stds = [], []
    for vop in VOPS:
        mask = X[:, 2] == vop
        e = errors_sigma[mask]
        sg_means.append(e.mean())
        sg_stds.append(e.std())
    ax.errorbar(VOPS, sg_means, yerr=sg_stds, fmt="s-", capsize=4, capthick=1.5, color="C1")
    ax.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Vop (V)")
    ax.set_ylabel("sigma error (V)")
    ax.set_title("(b) sigma prediction error by Vop")
    ax.grid(True, alpha=0.2)

    fig1.text(0.01, 0.01,
        f"mu GP ls=[cn={mu_ls[0]:.1f}, pu={mu_ls[1]:.1f}, Vop={mu_ls[2]:.2f}]  |  "
        f"sigma GP (additive): Vop ls={sigma_ls[0]:.2f}, cn ls={sigma_ls[1]:.1f}, pu ls={sigma_ls[2]:.1f}",
        fontsize=7, color="gray")
    fig1.tight_layout(rect=[0, 0.04, 1, 1])
    fig1.savefig(out_dir / "diagnostic_error_by_vop.png", dpi=150, bbox_inches="tight")
    plt.close(fig1)

    # ================================================================
    # FIGURE 2: Sigma error spatial maps
    # ================================================================
    print("  Figure 2: sigma_error_spatial.png")
    n_grid = 40
    cna = np.linspace(COMMON_N_MIN, COMMON_N_MAX, n_grid)
    pua = np.linspace(PU_MIN, PU_MAX, n_grid)
    CNg, PUg = np.meshgrid(cna, pua, indexing="xy")

    n_total = n_grid * n_grid
    X_grid = np.zeros((n_total * 6, 3))
    for i in range(n_grid):
        for j in range(n_grid):
            idx = (i * n_grid + j) * 6
            X_grid[idx:idx + 6, 0] = CNg[i, j]
            X_grid[idx:idx + 6, 1] = PUg[i, j]
            X_grid[idx:idx + 6, 2] = VOPS

    mu_g, _, sigma_g, _ = surr.predict(X_grid)
    mu_g_3d = mu_g.reshape(n_grid, n_grid, 6)
    sigma_g_3d = sigma_g.reshape(n_grid, n_grid, 6)

    true_sigma_3d = np.zeros((n_grid, n_grid, 6))
    for j, vop in enumerate(VOPS):
        true_sigma_3d[:, :, j] = SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - vop)

    sigma_err_3d = sigma_g_3d - true_sigma_3d

    fig2, axes2 = plt.subplots(2, 3, figsize=(15, 9))
    for j, vop in enumerate(VOPS):
        ax = axes2[j // 3][j % 3]
        err = sigma_err_3d[:, :, j]
        vlim = max(abs(err.min()), abs(err.max()))
        cf = ax.contourf(CNg, PUg, err, levels=np.linspace(-vlim, vlim, 21),
                         cmap="bwr", alpha=0.85)
        ax.contour(CNg, PUg, err, levels=[0], colors="k", linewidths=0.5, linestyles="--")
        plt.colorbar(cf, ax=ax, label="sigma error (V)", shrink=0.8)
        ax.set_xlabel("common_N shift (mV)")
        ax.set_ylabel("PU shift (mV)")
        ax.set_title(f"Vop={vop:.1f} V  |  bias={err.mean():+.5f}")
        ax.axhline(0, color="gray", linewidth=0.4)
        ax.axvline(0, color="gray", linewidth=0.4)
        ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX)
        ax.set_ylim(PU_MIN, PU_MAX)
    fig2.suptitle("Sigma prediction error in (cn, pu) space per Vop", fontsize=13)
    fig2.tight_layout()
    fig2.savefig(out_dir / "diagnostic_sigma_error_spatial.png", dpi=150)
    plt.close(fig2)

    # ================================================================
    # FIGURE 3: Predicted vs True scatter
    # ================================================================
    print("  Figure 3: pred_vs_true_scatter.png")
    fig3, axes3 = plt.subplots(1, 2, figsize=(12, 5))
    colors = plt.cm.viridis(np.linspace(0.2, 0.9, 6))

    ax = axes3[0]
    for j, vop in enumerate(VOPS):
        mask = X[:, 2] == vop
        ax.scatter(true_mu[mask], mu_pred[mask], c=[colors[j]], s=6, alpha=0.5,
                   label=f"Vop={vop:.1f}", edgecolors="none")
    lims = [true_mu.min(), true_mu.max()]
    ax.plot(lims, lims, "k--", linewidth=0.8)
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel("True mu (V)")
    ax.set_ylabel("Predicted mu (V)")
    ax.set_title("(a) mu prediction")
    ax.legend(fontsize=7, markerscale=2, loc="upper left")
    ax.grid(True, alpha=0.15)
    ax.set_aspect("equal")

    ax = axes3[1]
    for j, vop in enumerate(VOPS):
        mask = X[:, 2] == vop
        ax.scatter(true_sigma[mask], sigma_pred[mask], c=[colors[j]], s=6, alpha=0.5,
                   label=f"Vop={vop:.1f}", edgecolors="none")
    lims = [true_sigma.min() * 0.95, true_sigma.max() * 1.05]
    ax.plot(lims, lims, "k--", linewidth=0.8)
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel("True sigma (V)")
    ax.set_ylabel("Predicted sigma (V)")
    ax.set_title("(b) sigma prediction")
    ax.legend(fontsize=7, markerscale=2, loc="upper left")
    ax.grid(True, alpha=0.15)
    ax.set_aspect("equal")

    fig3.tight_layout()
    fig3.savefig(out_dir / "diagnostic_pred_vs_true_scatter.png", dpi=150)
    plt.close(fig3)

    # ================================================================
    # FIGURE 4: Vmin error decomposition
    # ================================================================
    print("  Figure 4: vmin_error_decomposition.png")
    fig4 = plt.figure(figsize=(14, 5))
    gs = GridSpec(1, 3, figure=fig4, width_ratios=[1, 1, 1.2])

    ax = fig4.add_subplot(gs[0])
    quad_list = ["FSG", "SFG", "FFG", "SSG"]
    quad_colors = {"FSG": "#e74c3c", "SFG": "#3498db", "FFG": "#2ecc71", "SSG": "#f39c12"}
    for k, q in enumerate(quad_list):
        mask = np.array([quad_names[i] == q for i in range(n_cond)]) & valid_vmin
        errs = vmin_error[mask]
        if len(errs) == 0:
            continue
        bp = ax.boxplot(errs, positions=[k], widths=0.5, patch_artist=True,
                        boxprops=dict(facecolor=quad_colors[q], alpha=0.6),
                        medianprops=dict(color="black", linewidth=1.5))
        ax.scatter([k], [errs.mean()], color="black", marker="D", s=30, zorder=5)
    ax.set_xticks(range(len(quad_list)))
    ax.set_xticklabels(quad_list)
    ax.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_ylabel("Vmin error (V)")
    ax.set_title("(a) Vmin error by quadrant")
    ax.grid(True, alpha=0.15, axis="y")

    ax = fig4.add_subplot(gs[1])
    ax.hist(true_vmin_all[valid_vmin], bins=20, alpha=0.5, label="True Vmin", color="C0", density=True)
    ax.hist(pred_vmin_all[valid_vmin], bins=20, alpha=0.5, label="Pred Vmin", color="C1", density=True)
    ax.set_xlabel("Vmin (V)")
    ax.set_ylabel("Density")
    ax.set_title("(b) Vmin distribution")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.15)

    ax = fig4.add_subplot(gs[2])
    mu_err_cond = np.zeros(n_cond)
    sigma_err_cond = np.zeros(n_cond)
    for i in range(n_cond):
        idx = slice(i * 6, (i + 1) * 6)
        mu_err_cond[i] = errors_mu[idx].mean()
        sigma_err_cond[i] = errors_sigma[idx].mean()

    sc = ax.scatter(mu_err_cond[valid_vmin], sigma_err_cond[valid_vmin],
                    c=vmin_error[valid_vmin], cmap="RdYlBu_r", s=15, alpha=0.7,
                    vmin=-0.04, vmax=0.04)
    plt.colorbar(sc, ax=ax, label="Vmin error (V)")
    ax.set_xlabel("Mean mu error per condition (V)")
    ax.set_ylabel("Mean sigma error per condition (V)")
    ax.set_title("(c) mu_err vs sigma_err vs Vmin_err")
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.axvline(0, color="gray", linewidth=0.5)
    ax.grid(True, alpha=0.15)

    valid = valid_vmin
    r_mu_sigma, _ = stats.pearsonr(mu_err_cond[valid], sigma_err_cond[valid])
    r_mu_vmin, _ = stats.pearsonr(mu_err_cond[valid], vmin_error[valid])
    r_sigma_vmin, _ = stats.pearsonr(sigma_err_cond[valid], vmin_error[valid])
    ax.text(0.05, 0.95, f"r(mu_err, sigma_err)={r_mu_sigma:.3f}\n"
                        f"r(mu_err, Vmin_err)={r_mu_vmin:.3f}\n"
                        f"r(sigma_err, Vmin_err)={r_sigma_vmin:.3f}",
            transform=ax.transAxes, fontsize=8, verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    fig4.tight_layout()
    fig4.savefig(out_dir / "diagnostic_vmin_error_decomposition.png", dpi=150)
    plt.close(fig4)

    # ================================================================
    # FIGURE 5: Error propagation chain
    # ================================================================
    print("  Figure 5: error_propagation_chain.png")
    true_z = true_mu / (true_sigma + 1e-12)
    pred_z = mu_pred / (sigma_pred + 1e-12)
    z_err = pred_z - true_z

    fig5, axes5 = plt.subplots(1, 3, figsize=(14, 4.5))
    colors_v = plt.cm.viridis(np.linspace(0.2, 0.9, 6))

    ax = axes5[0]
    for j, vop in enumerate(VOPS):
        mask = X[:, 2] == vop
        ze = z_err[mask]
        ax.boxplot(ze, positions=[j], widths=0.4,
                   boxprops=dict(color=colors_v[j], alpha=0.6),
                   medianprops=dict(color="black", linewidth=1.5),
                   whiskerprops=dict(color=colors_v[j]),
                   capprops=dict(color=colors_v[j]))
    ax.set_xticks(range(6))
    ax.set_xticklabels([f"{v:.1f}" for v in VOPS])
    ax.axhline(0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Vop (V)")
    ax.set_ylabel("Z-score error")
    ax.set_title("(a) Z-score prediction error by Vop")
    ax.grid(True, alpha=0.15, axis="y")

    ax = axes5[1]
    ax.scatter(errors_sigma[::10], z_err[::10], c=X[::10, 2], cmap="viridis",
               s=5, alpha=0.6, edgecolors="none")
    plt.colorbar(ax.collections[0], ax=ax, label="Vop (V)")
    ax.set_xlabel("Sigma error (V)")
    ax.set_ylabel("Z-score error")
    ax.set_title("(b) sigma_err -> Z_err propagation")
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.axvline(0, color="gray", linewidth=0.5)
    ax.grid(True, alpha=0.15)

    ax = axes5[2]
    sigma_err_cond_mean = np.zeros(n_cond)
    for i in range(n_cond):
        idx = slice(i * 6, (i + 1) * 6)
        sigma_err_cond_mean[i] = errors_sigma[idx].mean()
    ax.scatter(sigma_err_cond_mean[valid_vmin], vmin_error[valid_vmin],
               c=np.array([stats.pearsonr(
                   true_sigma[i * 6:(i + 1) * 6], sigma_pred[i * 6:(i + 1) * 6])[0]
                   for i in range(n_cond) if valid_vmin[i]]),
               cmap="RdYlBu", s=15, alpha=0.7, edgecolors="none")
    plt.colorbar(ax.collections[0], ax=ax, label="r(sigma_true, sigma_pred)")
    ax.set_xlabel("Mean sigma error per condition (V)")
    ax.set_ylabel("Vmin error (V)")
    ax.set_title("(c) sigma_err -> Vmin_err")
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.axvline(0, color="gray", linewidth=0.5)
    ax.grid(True, alpha=0.15)

    fig5.tight_layout()
    fig5.savefig(out_dir / "diagnostic_error_propagation_chain.png", dpi=150)
    plt.close(fig5)

    # Summary
    print()
    print("=== Summary ===")
    print(f"  mu RMSE: {np.sqrt(np.mean(errors_mu**2)):.5f}")
    print(f"  sigma RMSE: {np.sqrt(np.mean(errors_sigma**2)):.5f}")
    print(f"  Vmin RMSE (valid): {np.sqrt(np.mean(vmin_error[valid_vmin]**2)):.5f}")
    print(f"  Vmin mean bias: {vmin_error[valid_vmin].mean():+.5f}")
    print(f"  Vmin valid frac: {valid_vmin.sum()}/{n_cond}")
    print()
    print("  Lengthscales:")
    print(f"    mu:    cn={mu_ls[0]:.1f}, pu={mu_ls[1]:.1f}, Vop={mu_ls[2]:.2f}")
    print(f"    sigma: Vop={sigma_ls[0]:.2f}, cn={sigma_ls[1]:.1f}, pu={sigma_ls[2]:.1f}")


if __name__ == "__main__":
    main()
