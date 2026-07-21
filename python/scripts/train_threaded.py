"""
CPU-thread-optimized GP surrogate training -- parallel BLAS on multi-core.
===============================================================================
Sets torch.set_num_threads() to physical core count and reports the
actual thread configuration. Uses the exact same model architecture as
baseline (ExactGP + AdditiveGP) to isolate the threading effect.

Output: results/gp_threaded/
  surrogate_threaded.pth
  metrics_threaded.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Path boilerplate
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PYTHON_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PYTHON_DIR))

import torch

# ---------------------------------------------------------------------------
# Thread configuration — BEFORE any heavy torch operation
# ---------------------------------------------------------------------------
physical_cores = os.cpu_count() or 1
# Cap at 8 to avoid oversubscription; leave 1 core for OS
n_threads = min(physical_cores, 8)
torch.set_num_threads(n_threads)
# interop threads must be set before first use; 1 is optimal for CPU-only
try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass  # already set

print(f"  CPU cores: {physical_cores}")
print(f"  torch.set_num_threads: {torch.get_num_threads()}")
print(f"  torch.get_num_interop_threads: {torch.get_num_interop_threads()}")

import gpytorch
from gpytorch.means import ConstantMean
from gpytorch.kernels import ScaleKernel, MaternKernel
from gpytorch.likelihoods import FixedNoiseGaussianLikelihood
from gpytorch.models import ExactGP

from src.final_data import load_final_snmr
from src.data import grouped_train_test_split
from src.utils import VOP_COL, vop_col_for
from src.physics_layer import compute_vmin_from_z

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
N_DEVICE = 9
DEVICE_COLS = ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]
VOP_COL_IDX = vop_col_for(N_DEVICE)
Z_TARGET = 6.398  # 128Mb @ 99%
OUT_DIR = _PYTHON_DIR / "results" / "gp_threaded"
N_ITER = 150
LR = 0.1


# ---------------------------------------------------------------------------
# GP models (same as baseline)
# ---------------------------------------------------------------------------
class ExactGPModel(ExactGP):
    def __init__(self, train_x, train_y, likelihood=None):
        if likelihood is None:
            from gpytorch.likelihoods import GaussianLikelihood
            likelihood = GaussianLikelihood()
        super().__init__(train_x, train_y, likelihood)
        self.mean_module = ConstantMean()
        n_dims = train_x.shape[-1]
        self.covar_module = ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=n_dims))

    def forward(self, x):
        return gpytorch.distributions.MultivariateNormal(
            self.mean_module(x), self.covar_module(x)
        )


class AdditiveGPModel(ExactGP):
    def __init__(self, train_x, train_y, likelihood=None, n_device=N_DEVICE):
        if likelihood is None:
            from gpytorch.likelihoods import GaussianLikelihood
            likelihood = GaussianLikelihood()
        super().__init__(train_x, train_y, likelihood)
        self.mean_module = ConstantMean()
        n_dims = train_x.shape[-1]
        n_op = n_dims - n_device
        self.covar_module = (
            ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=n_op,
                                     active_dims=list(range(n_device, n_dims)))) +
            ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=n_device,
                                     active_dims=list(range(n_device))))
        )

    def forward(self, x):
        return gpytorch.distributions.MultivariateNormal(
            self.mean_module(x), self.covar_module(x)
        )


# ---------------------------------------------------------------------------
# Training helper
# ---------------------------------------------------------------------------
def train_gp(model, likelihood, xt, yt, n_iter=N_ITER, lr=LR, name="gp"):
    model.train(); likelihood.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    mll = gpytorch.mlls.ExactMarginalLogLikelihood(likelihood, model)

    start = time.time()
    for i in range(n_iter):
        optimizer.zero_grad()
        loss = -mll(model(xt), yt)
        loss.backward()
        optimizer.step()
        if (i + 1) % 50 == 0:
            print(f"  [{name}] iter {i+1:4d}/{n_iter} loss={loss.item():.4f}")

    model.eval(); likelihood.eval()
    elapsed = time.time() - start
    print(f"  [{name}] done ({elapsed:.1f}s)")
    return model, elapsed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"Thread-Optimized GP Training -- {n_threads} threads")
    print("=" * 70)

    # --- Load data ---
    df = load_final_snmr()
    X = df[DEVICE_COLS + ["vop"]].to_numpy(dtype=np.float64)
    y = df[["snmr_avg", "snmr_std"]].to_numpy(dtype=np.float64) * 1e-3

    n_mc = np.clip(df["n_mc"].to_numpy(dtype=np.float64), 2, None)
    y_noise = np.column_stack([
        np.maximum(y[:, 1] / np.sqrt(n_mc), 1e-9),
        np.maximum(y[:, 1] / np.sqrt(2.0 * n_mc), 1e-9),
    ])

    _, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
    X_tr, X_te, y_tr, y_te = grouped_train_test_split(X, y, groups=cond_idx, test_frac=0.15, seed=42)
    _, _, noise_tr, noise_te = grouped_train_test_split(X, y_noise, groups=cond_idx, test_frac=0.15, seed=42)

    print(f"  train={len(X_tr)}  test={len(X_te)}  conditions={len(np.unique(cond_idx))}")

    # --- Standardize ---
    mu_x = X_tr.mean(axis=0)
    std_x = X_tr.std(axis=0) + 1e-8
    X_tr_s = (X_tr - mu_x) / std_x
    X_te_s = (X_te - mu_x) / std_x

    xt = torch.from_numpy(X_tr_s.astype(np.float64))  # float64 for precision
    yt_mu = torch.from_numpy(y_tr[:, 0].astype(np.float64))
    yt_sigma = torch.from_numpy(y_tr[:, 1].astype(np.float64))
    xte = torch.from_numpy(X_te_s.astype(np.float64))

    # --- Build likelihoods (noise-aware) ---
    noise_tr_t = torch.from_numpy(noise_tr.astype(np.float64))
    mu_like = FixedNoiseGaussianLikelihood(
        noise=noise_tr_t[:, 0] ** 2, learn_additional_noise=True
    )
    sigma_like = FixedNoiseGaussianLikelihood(
        noise=noise_tr_t[:, 1] ** 2, learn_additional_noise=True
    )

    # --- Train mu ---
    print("\n--- Training mu ---")
    mu_model = ExactGPModel(xt, yt_mu, likelihood=mu_like)
    mu_model, mu_time = train_gp(mu_model, mu_like, xt, yt_mu, name="mu")

    # --- Train sigma ---
    print("\n--- Training sigma ---")
    sigma_model = AdditiveGPModel(xt, yt_sigma, likelihood=sigma_like, n_device=N_DEVICE)
    sigma_model, sigma_time = train_gp(sigma_model, sigma_like, xt, yt_sigma, name="sigma")

    total_train = mu_time + sigma_time

    # --- Predict ---
    print("\n--- Predicting on hold-out ---")
    with torch.no_grad(), gpytorch.settings.fast_pred_var():
        mu_pred = mu_model(xte)
        sigma_pred = sigma_model(xte)
    mu_mean = mu_pred.mean.numpy()
    sigma_mean = sigma_pred.mean.numpy()

    # --- Metrics ---
    mu_resid = mu_mean - y_te[:, 0]
    sigma_resid = sigma_mean - y_te[:, 1]
    mu_rmse = float(np.sqrt(np.mean(mu_resid ** 2)))
    sigma_rmse = float(np.sqrt(np.mean(sigma_resid ** 2)))
    mu_r2 = float(1 - np.sum(mu_resid ** 2) / np.sum((y_te[:, 0] - y_te[:, 0].mean()) ** 2))
    sigma_r2 = float(1 - np.sum(sigma_resid ** 2) / np.sum((y_te[:, 1] - y_te[:, 1].mean()) ** 2))

    print(f"\n  mu:    RMSE={mu_rmse*1e3:.3f}mV  R2={mu_r2:.4f}")
    print(f"  sigma: RMSE={sigma_rmse*1e3:.3f}mV  R2={sigma_r2:.4f}")

    # --- Vmin RMSE ---
    vmin_true, vmin_pred, cens_true = [], [], []
    te_device = X_te[:, :N_DEVICE]
    _, te_group = np.unique(te_device, axis=0, return_inverse=True)
    for gid in np.unique(te_group):
        mask = te_group == gid
        vops_g = X_te[mask, VOP_COL_IDX]
        order = np.argsort(vops_g)
        vops_g = vops_g[order]
        z_true = y_te[mask, 0][order] / (y_te[mask, 1][order] + 1e-12)
        v_t, c_t = compute_vmin_from_z(z_true.reshape(1, -1), z_target=Z_TARGET,
                                        vops=vops_g, return_censored=True)
        z_pred = mu_mean[mask][order] / (sigma_mean[mask][order] + 1e-12)
        v_p, _ = compute_vmin_from_z(z_pred.reshape(1, -1), z_target=Z_TARGET,
                                      vops=vops_g, return_censored=True)
        vmin_true.append(v_t[0]); cens_true.append(bool(c_t[0])); vmin_pred.append(v_p[0])

    vmin_true = np.array(vmin_true); vmin_pred = np.array(vmin_pred)
    cens_true = np.array(cens_true)
    scoreable = ~cens_true & ~np.isnan(vmin_true) & ~np.isnan(vmin_pred)
    n_scored = int(scoreable.sum())
    vmin_rmse_mV = float(np.sqrt(np.mean(
        (vmin_pred[scoreable] - vmin_true[scoreable]) ** 2)) * 1e3) if n_scored > 0 else float("nan")
    print(f"  Vmin RMSE: {vmin_rmse_mV:.2f}mV ({n_scored}/{len(vmin_true)} scored)")

    # --- Save ---
    metrics = {
        "approach": "threaded_cpu",
        "n_threads": n_threads,
        "physical_cores": physical_cores,
        "n_iter": N_ITER,
        "train_rows": len(X_tr),
        "test_rows": len(X_te),
        "mu_rmse_mV": mu_rmse * 1e3,
        "mu_r2": mu_r2,
        "sigma_rmse_mV": sigma_rmse * 1e3,
        "sigma_r2": sigma_r2,
        "vmin_rmse_mV": vmin_rmse_mV,
        "n_holdout_scored": n_scored,
        "train_time_sec": total_train,
        "mu_train_sec": mu_time,
        "sigma_train_sec": sigma_time,
    }
    with open(OUT_DIR / "metrics_threaded.json", "w") as f:
        json.dump(metrics, f, indent=2)

    torch.save({
        "mu_model": mu_model.state_dict(),
        "sigma_model": sigma_model.state_dict(),
        "mu_likelihood": mu_like.state_dict(),
        "sigma_likelihood": sigma_like.state_dict(),
        "x_train": X_tr,
        "scaler_mean": mu_x,
        "scaler_std": std_x,
        "n_threads": n_threads,
    }, OUT_DIR / "surrogate_threaded.pth")

    print(f"\n  Saved: {OUT_DIR / 'metrics_threaded.json'}")
    print(f"  Saved: {OUT_DIR / 'surrogate_threaded.pth'}")
    print(f"\n  Total training time: {total_train:.1f}s (with {n_threads} threads)")


if __name__ == "__main__":
    main()
