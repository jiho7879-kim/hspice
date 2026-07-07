"""
Simulation-budget vs accuracy Pareto (plan sec 4.2).

Answers "how many simulated conditions buy how much Vmin accuracy?", and
whether physics constraints and sampling strategy shift the curve at low
budget.  This is the industrial-value figure of the paper.

Sweep:
    N_train (conditions)  x  strategy  x  {physics on/off}  x  seeds
    strategy in {random, sobol_uniform, stratified_sobol}
Metrics (on a FIXED hold-out, same across all cells):
    - contour Hausdorff at Vmin=0.6V (mV)
    - Vmin RMSE, censored-aware (assist-free 3D: left-censored points below
      the lowest Vop are excluded, not scored against the 0.35V floor)
    - mu RMSE
All with seed error bars.

Data is the analytic SNM testbed (no HSPICE); the same script re-runs on a
subsampled HSPICE pool once Phase 2 data exists.

Usage:
    python scripts/budget_pareto.py --smoke        # fast sanity (~1 min)
    python scripts/budget_pareto.py --full         # paper run (background)
"""

from __future__ import annotations

import sys
import time
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch
import gpytorch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils import (
    VOPS, Z_FIXED,
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
    sample_common_n_pu, sobol_2d_in_rect,
)
from src.surrogate import Surrogate
from src.physics import PhysicsConstrainedSurrogate, analytic_snmr
from src.physics_layer import compute_vmin_from_z
from src.contour import extract_contour, hausdorff_distance

OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "budget_pareto"

MU_NOISE_STD = 0.002
SIGMA_NOISE_STD = 0.0005
CONTOUR_LEVEL = 0.6
N_TRUE_GRID = 60          # dense grid for the true/pred contour (Hausdorff)
N_HOLDOUT_COND = 300      # random hold-out conditions for Vmin RMSE

STRATEGIES = ("random", "sobol_uniform", "stratified_sobol")


# ---------------------------------------------------------------------------
# Sampling strategies (conditions in (cn, pu) space)
# ---------------------------------------------------------------------------

def sample_conditions(strategy: str, n_cond: int, seed: int) -> np.ndarray:
    """Return (n_cond, 2) (cn, pu) samples for the given strategy."""
    if strategy == "random":
        rng = np.random.default_rng(seed)
        cn = rng.uniform(COMMON_N_MIN, COMMON_N_MAX, n_cond)
        pu = rng.uniform(PU_MIN, PU_MAX, n_cond)
        return np.column_stack([cn, pu])
    if strategy == "sobol_uniform":
        lo = np.array([COMMON_N_MIN, PU_MIN])
        hi = np.array([COMMON_N_MAX, PU_MAX])
        return sobol_2d_in_rect(n_cond, lo, hi, seed=seed)
    if strategy == "stratified_sobol":
        return sample_common_n_pu(n_cond, seed=seed)
    raise ValueError(f"unknown strategy: {strategy}")


# ---------------------------------------------------------------------------
# Analytic ground truth
# ---------------------------------------------------------------------------

def build_xy(conditions: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """(cn,pu) conditions -> (X 3D, y 2D) with observation noise."""
    rng = np.random.default_rng(seed + 10_000)
    rows_x, rows_y = [], []
    for cn, pu in conditions:
        for v in VOPS:
            mu, sigma = analytic_snmr(float(cn), float(pu), float(v))
            rows_x.append([cn, pu, v])
            rows_y.append([mu + rng.normal(0, MU_NOISE_STD),
                           sigma + rng.normal(0, SIGMA_NOISE_STD)])
    return np.asarray(rows_x, np.float64), np.asarray(rows_y, np.float64)


def true_vmin_points(cn: np.ndarray, pu: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Analytic Vmin at (cn, pu) points, censored-aware.

    Returns (vmin, censored_mask).  Vmin uses the noiseless analytic model.
    """
    n = len(cn)
    z = np.empty((n, len(VOPS)))
    for k, v in enumerate(VOPS):
        for i in range(n):
            mu, sg = analytic_snmr(float(cn[i]), float(pu[i]), float(v))
            z[i, k] = mu / sg
    vmin, cens = compute_vmin_from_z(z, z_target=Z_FIXED, return_censored=True)
    return vmin, cens


def true_vmin_grid(n_grid: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cna = np.linspace(COMMON_N_MIN, COMMON_N_MAX, n_grid)
    pua = np.linspace(PU_MIN, PU_MAX, n_grid)
    CN, PU = np.meshgrid(cna, pua, indexing="xy")
    vmin, _ = true_vmin_points(CN.ravel(), PU.ravel())
    return CN, PU, vmin.reshape(n_grid, n_grid)


# ---------------------------------------------------------------------------
# One (N, strategy, physics, seed) cell
# ---------------------------------------------------------------------------

def _stack_vop(cn: np.ndarray, pu: np.ndarray) -> np.ndarray:
    """(n,) cn/pu -> (n*N_VOP, 3) rows [cn, pu, Vop] in point-major order."""
    nv = len(VOPS)
    X = np.empty((len(cn) * nv, 3))
    X[:, 0] = np.repeat(cn, nv)
    X[:, 1] = np.repeat(pu, nv)
    X[:, 2] = np.tile(VOPS, len(cn))
    return X


def _predict_mean(surr, X: np.ndarray, batch: int = 2048) -> tuple[np.ndarray, np.ndarray]:
    """GP posterior MEANS only (mu, sigma).  Vmin needs no variance, so we
    skip it (skip_posterior_variances) and batch the test set to bound the
    test-test kernel memory -- a full predict() with variance over a large
    contour grid both wastes compute and can OOM."""
    Xs = surr._x_scaler.transform(X).astype(np.float32)
    mus, sgs = [], []
    with torch.no_grad(), gpytorch.settings.skip_posterior_variances(True):
        for i in range(0, len(Xs), batch):
            xt = torch.from_numpy(Xs[i:i + batch])
            mus.append(surr.mu_gp(xt).mean.cpu().numpy())
            sgs.append(surr.sigma_gp(xt).mean.cpu().numpy())
    return np.concatenate(mus), np.concatenate(sgs)


def _vmin_at(surr, cn: np.ndarray, pu: np.ndarray):
    """Surrogate Vmin at (cn, pu) points, censored-aware."""
    mu, sg = _predict_mean(surr, _stack_vop(cn, pu))
    z = (mu / (sg + 1e-12)).reshape(len(cn), len(VOPS))
    return compute_vmin_from_z(z, z_target=Z_FIXED, return_censored=True)


def gp_vmin_grid(surr, CN: np.ndarray, PU: np.ndarray) -> np.ndarray:
    """Predict Vmin over a (cn, pu) meshgrid via the surrogate."""
    vmin, _ = _vmin_at(surr, CN.ravel(), PU.ravel())
    return vmin.reshape(CN.shape)


def run_cell(
    strategy: str, n_cond: int, use_physics: bool, seed: int,
    holdout, true_grid, n_iter: int,
) -> dict:
    ho_cn, ho_pu, ho_vmin, ho_cens = holdout
    CN_t, PU_t, vmin_t = true_grid
    true_cn, true_pu = extract_contour(vmin_t, CN_t, PU_t, CONTOUR_LEVEL)

    conditions = sample_conditions(strategy, n_cond, seed)
    X, y = build_xy(conditions, seed)

    if use_physics:
        surr = PhysicsConstrainedSurrogate(device="cpu")
        surr.fit(X, y, n_iter=n_iter, verbose=False,
                 use_mono=False, use_boundary=True, use_pelgrom=True)
    else:
        surr = Surrogate(device="cpu")
        surr.fit(X, y, n_iter=n_iter, verbose=False)

    # mu RMSE on hold-out conditions (all Vop, noiseless analytic truth)
    Xho = _stack_vop(ho_cn, ho_pu)
    yho_mu = np.array([analytic_snmr(float(c), float(p), float(v))[0]
                       for c, p in zip(ho_cn, ho_pu) for v in VOPS])
    mu_p, _ = _predict_mean(surr, Xho)
    mu_rmse = float(np.sqrt(np.mean((mu_p - yho_mu) ** 2)))

    # Vmin RMSE (censored-aware): exclude points left-censored in either
    # the truth or the prediction (the 0.35V floor is not a measurement)
    vmin_p, cens_p = _vmin_at(surr, ho_cn, ho_pu)
    good = (~ho_cens) & (~cens_p) & ~np.isnan(vmin_p) & ~np.isnan(ho_vmin)
    if good.sum() > 0:
        vmin_rmse = float(np.sqrt(np.mean((vmin_p[good] - ho_vmin[good]) ** 2))) * 1000
    else:
        vmin_rmse = float("nan")

    # Contour Hausdorff
    vmin_grid_p = gp_vmin_grid(surr, CN_t, PU_t)
    pred_cn, pred_pu = extract_contour(vmin_grid_p, CN_t, PU_t, CONTOUR_LEVEL)
    haus = hausdorff_distance(true_cn, true_pu, pred_cn, pred_pu)

    return {
        "mu_rmse": mu_rmse,
        "vmin_rmse_mV": vmin_rmse,
        "hausdorff_mV": float(haus),
        "n_holdout_scored": int(good.sum()),
    }


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="fast sanity run")
    ap.add_argument("--full", action="store_true", help="paper-quality run")
    ap.add_argument("--n_iter", type=int, default=80)
    ap.add_argument("--seeds", type=int, default=6,
                    help="seed count for --full (error bars; 6 default, 10 for final figure)")
    args = ap.parse_args()

    if args.full:
        n_list = [50, 100, 200, 400, 800]
        strategies = list(STRATEGIES)
        physics_opts = [False, True]
        seeds = list(range(args.seeds))
    else:  # smoke
        n_list = [50, 100]
        strategies = ["random", "stratified_sobol"]
        physics_opts = [False]
        seeds = [0, 1]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Budget Pareto: N={n_list} strategies={strategies} "
          f"physics={physics_opts} seeds={len(seeds)}  "
          f"({len(n_list)*len(strategies)*len(physics_opts)*len(seeds)} cells)")

    # Fixed hold-out + true contour grid (shared across all cells)
    rng = np.random.default_rng(999)
    ho_cn = rng.uniform(COMMON_N_MIN, COMMON_N_MAX, N_HOLDOUT_COND)
    ho_pu = rng.uniform(PU_MIN, PU_MAX, N_HOLDOUT_COND)
    ho_vmin, ho_cens = true_vmin_points(ho_cn, ho_pu)
    holdout = (ho_cn, ho_pu, ho_vmin, ho_cens)
    true_grid = true_vmin_grid(N_TRUE_GRID)
    print(f"  hold-out: {N_HOLDOUT_COND} cond ({int(ho_cens.sum())} censored), "
          f"true contour pts: {len(extract_contour(true_grid[2], true_grid[0], true_grid[1], CONTOUR_LEVEL)[0])}")

    records = []
    t0 = time.time()
    for phys in physics_opts:
        for strat in strategies:
            for n_cond in n_list:
                for seed in seeds:
                    r = run_cell(strat, n_cond, phys, seed, holdout, true_grid, args.n_iter)
                    r.update(strategy=strat, n_cond=n_cond, physics=phys, seed=seed)
                    records.append(r)
                # aggregate print
                cell = [x for x in records
                        if x["strategy"] == strat and x["n_cond"] == n_cond and x["physics"] == phys]
                hv = np.array([c["hausdorff_mV"] for c in cell])
                vv = np.array([c["vmin_rmse_mV"] for c in cell])
                print(f"  [{'phys' if phys else 'plain'}] {strat:16s} N={n_cond:4d}  "
                      f"Haus={np.nanmean(hv):5.2f}+/-{np.nanstd(hv):4.2f}mV  "
                      f"VminRMSE={np.nanmean(vv):5.2f}+/-{np.nanstd(vv):4.2f}mV  "
                      f"[{len(records)} cells, {time.time()-t0:.0f}s]", flush=True)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s ({len(records)} cells)")

    # Save raw records
    with open(OUT_DIR / "pareto_results.json", "w") as f:
        json.dump({"records": records,
                   "config": {"n_list": n_list, "strategies": strategies,
                              "physics": physics_opts, "n_seeds": len(seeds),
                              "n_iter": args.n_iter}}, f, indent=2)
    print(f"  -> {OUT_DIR / 'pareto_results.json'}")

    _plot(records, n_list, strategies, physics_opts)


def _plot(records, n_list, strategies, physics_opts) -> None:
    def agg(metric, strat, phys):
        m, s = [], []
        for n in n_list:
            vals = np.array([r[metric] for r in records
                             if r["strategy"] == strat and r["n_cond"] == n
                             and r["physics"] == phys])
            m.append(np.nanmean(vals))
            s.append(np.nanstd(vals))
        return np.array(m), np.array(s)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    colors = {"random": "#e74c3c", "sobol_uniform": "#3498db",
              "stratified_sobol": "#2ecc71"}
    for ax, metric, title in [
        (axes[0], "hausdorff_mV", "Contour Hausdorff (mV)"),
        (axes[1], "vmin_rmse_mV", "Vmin RMSE, censored-aware (mV)"),
    ]:
        for strat in strategies:
            for phys in physics_opts:
                m, s = agg(metric, strat, phys)
                ls = "-" if phys else "--"
                lbl = f"{strat}{' +phys' if phys else ''}"
                ax.errorbar(n_list, m, yerr=s, marker="o", ls=ls,
                            color=colors[strat], capsize=3, label=lbl,
                            alpha=0.9 if phys else 0.6)
        ax.set_xlabel("N conditions (train)")
        ax.set_ylabel(title)
        ax.set_xscale("log")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    axes[0].set_title("Budget vs contour accuracy")
    axes[1].set_title("Budget vs Vmin accuracy")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "budget_pareto.png", dpi=150, bbox_inches="tight")
    print(f"  -> {OUT_DIR / 'budget_pareto.png'}")
    plt.close(fig)


if __name__ == "__main__":
    main()
