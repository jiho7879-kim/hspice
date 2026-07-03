"""
Basic GP surrogate trainer — two independent GPs for mu and sigma.

Usage:
    surr = Surrogate(device="cpu")
    surr.fit(X_train, y_train)
    mu_mean, mu_std, sigma_mean, sigma_std = surr.predict(X_test)

Inputs are automatically standardized (zero-mean, unit-variance per dim)
inside fit/predict.  No manual scaling needed.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import torch
import gpytorch

from src.models import ExactGPModel, AdditiveGPModel
from src.utils import StandardScaler


class Surrogate:
    """Dual-output GP surrogate: mu and sigma modeled independently.

    mu:    ExactGPModel (full Matern 5/2 + ARD across all input dims)
    sigma: AdditiveGPModel (k_Vop(Vop) + k_cnpu(cn, pu))

    Input X is standardized inside fit/predict — callers pass raw values.
    Trained checkpoints include the scaler, so load() restores everything.
    """

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self.mu_gp: ExactGPModel | None = None
        self.sigma_gp: AdditiveGPModel | None = None
        self._x_train: np.ndarray | None = None
        self._x_scaler = StandardScaler()

    def _to_tensor(self, arr: np.ndarray) -> torch.Tensor:
        return torch.from_numpy(arr.astype(np.float32)).to(self.device)

    def fit(self, X_train: np.ndarray, y_train: np.ndarray,
            n_iter: int = 200, lr: float = 0.1, verbose: bool = True) -> None:
        """Train both mu and sigma GPs on standardized inputs.

        Args:
            X_train: (N, d) training inputs [common_N, PU, Vop, ...]
            y_train: (N, 2) training targets [mu, sigma]
            n_iter: Training iterations
            lr: Learning rate for Adam
        """
        self._x_train = X_train.copy()
        X_scaled = self._x_scaler.fit_transform(X_train)
        xt = self._to_tensor(X_scaled)
        yt_mu = self._to_tensor(y_train[:, 0])
        yt_sigma = self._to_tensor(y_train[:, 1])

        self.mu_gp = ExactGPModel(xt, yt_mu).to(self.device)
        self.sigma_gp = AdditiveGPModel(xt, yt_sigma).to(self.device)

        for name, gp in [("mu", self.mu_gp), ("sigma", self.sigma_gp)]:
            gp.train()
            gp.likelihood.train()

            optimizer = torch.optim.Adam(gp.parameters(), lr=lr)
            mll = gpytorch.mlls.ExactMarginalLogLikelihood(gp.likelihood, gp)

            start = time.time()
            for i in range(n_iter):
                optimizer.zero_grad()
                output = gp(xt)
                loss = -mll(output, gp.train_targets)
                loss.backward()
                optimizer.step()
                if verbose and (i + 1) % 50 == 0:
                    print(f"  [{name}] iter {i + 1:4d}/{n_iter} "
                          f"loss={loss.item():.4f}")

            gp.eval()
            gp.likelihood.eval()
            if verbose:
                elapsed = time.time() - start
                if name == "sigma" and isinstance(gp, AdditiveGPModel):
                    parts = []
                    for kidx in range(len(gp.covar_module.kernels)):
                        sub_ls = gp.covar_module.kernels[kidx].base_kernel.lengthscale.detach().cpu().numpy().flatten()
                        part_labels = [f"k{kidx}_d{i}" for i in range(len(sub_ls))]
                        parts.extend(f"{l}={v:.3f}" for l, v in zip(part_labels, sub_ls))
                    ls_str = "  ".join(parts)
                else:
                    ls = gp.covar_module.base_kernel.lengthscale.detach().cpu().numpy().flatten()
                    labels = ["cn", "pu", "Vop"] + [f"d{i}" for i in range(3, len(ls))]
                    ls_str = ", ".join(f"{l}={v:.3f}" for l, v in zip(labels, ls))
                print(f"  [{name}] done ({elapsed:.1f}s) "
                      f"lengthscales={ls_str} (on scaled X)")

    def predict(self, X_test: np.ndarray, batch_size: int = 5000) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Predict mu and sigma with uncertainty.

        Batches predictions to avoid OOM from materialising full K(test,test)
        for large test sets.

        Args:
            X_test: (N, d) test inputs (raw unscaled values).
            batch_size: Max rows per batch (default 5000 ≈ 100 MB covar).

        Returns:
            mu_mean, mu_std, sigma_mean, sigma_std: each (N,)
        """
        assert self.mu_gp is not None and self.sigma_gp is not None
        X = self._x_scaler.transform(X_test)

        n = len(X)
        if n <= batch_size:
            xt = self._to_tensor(X)
            with torch.no_grad():
                mu_pred = self.mu_gp(xt)
                sigma_pred = self.sigma_gp(xt)
            return (mu_pred.mean.cpu().numpy(), mu_pred.stddev.cpu().numpy(),
                    sigma_pred.mean.cpu().numpy(), sigma_pred.stddev.cpu().numpy())

        mu_mean = np.empty(n, dtype=np.float64)
        mu_std = np.empty(n, dtype=np.float64)
        sigma_mean = np.empty(n, dtype=np.float64)
        sigma_std = np.empty(n, dtype=np.float64)
        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            batch = X[start:end]
            xt = self._to_tensor(batch)
            with torch.no_grad():
                mu_pred = self.mu_gp(xt)
                sigma_pred = self.sigma_gp(xt)
            mu_mean[start:end] = mu_pred.mean.cpu().numpy()
            mu_std[start:end] = mu_pred.stddev.cpu().numpy()
            sigma_mean[start:end] = sigma_pred.mean.cpu().numpy()
            sigma_std[start:end] = sigma_pred.stddev.cpu().numpy()

        return mu_mean, mu_std, sigma_mean, sigma_std

    def save(self, path: str | Path) -> None:
        """Save trained GP state dicts + scaler to a .pth checkpoint."""
        state = {
            "mu_gp": self.mu_gp.state_dict() if self.mu_gp is not None else None,
            "sigma_gp": self.sigma_gp.state_dict() if self.sigma_gp is not None else None,
            "x_train": self._x_train,
            "x_scaler_mean": self._x_scaler.mean_,
            "x_scaler_std": self._x_scaler.std_,
        }
        torch.save(state, path)
        print(f"  [save] checkpoint -> {path}")

    @classmethod
    def load(cls, path: str | Path, X_train: np.ndarray,
             y_train: np.ndarray, device: str = "cpu") -> "Surrogate":
        """Load trained GP state dicts + scaler from a .pth checkpoint.

        X_train/y_train must match original training data shape because
        ExactGP requires them at construction.  The checkpoint's scaler
        is restored so predict() works on raw inputs.
        """
        state = torch.load(path, map_location=device, weights_only=True)
        surr = cls(device=device)
        surr._x_train = X_train.copy()

        if state["x_scaler_mean"] is not None:
            surr._x_scaler.mean_ = state["x_scaler_mean"]
            surr._x_scaler.std_ = state["x_scaler_std"]

        X_scaled = surr._x_scaler.transform(X_train)
        xt = surr._to_tensor(X_scaled)
        yt_mu = surr._to_tensor(y_train[:, 0])
        yt_sigma = surr._to_tensor(y_train[:, 1])

        surr.mu_gp = ExactGPModel(xt, yt_mu).to(device)
        surr.sigma_gp = AdditiveGPModel(xt, yt_sigma).to(device)

        if state["mu_gp"] is not None:
            surr.mu_gp.load_state_dict(state["mu_gp"])
            surr.mu_gp.eval()
            surr.mu_gp.likelihood.eval()
        if state["sigma_gp"] is not None:
            surr.sigma_gp.load_state_dict(state["sigma_gp"])
            surr.sigma_gp.eval()
            surr.sigma_gp.likelihood.eval()
        print(f"  [load] checkpoint <- {path}")
        return surr

    def get_lengthscales(self, model: str = "mu") -> np.ndarray:
        """Return ARD lengthscales (on the *standardized* input scale)."""
        if model == "mu":
            assert self.mu_gp is not None
            return self.mu_gp.covar_module.base_kernel.lengthscale.detach().cpu().numpy().flatten()
        else:
            assert self.sigma_gp is not None
            gp = self.sigma_gp
            parts = []
            for k in range(len(gp.covar_module.kernels)):
                km = gp.covar_module.kernels[k]
                ls = km.covar_module.base_kernel.lengthscale.detach().cpu().numpy().flatten()
                parts.append(ls)
            return np.concatenate(parts)


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def evaluate(X_test: np.ndarray, y_test: np.ndarray,
             mu_mean: np.ndarray, sigma_mean: np.ndarray) -> dict:
    """Compute RMSE and R^2 for mu and sigma predictions."""
    from scipy.stats import linregress

    result = {}
    for name, pred, true in [
        ("mu", mu_mean, y_test[:, 0]),
        ("sigma", sigma_mean, y_test[:, 1]),
    ]:
        resid = pred - true
        rmse = float(np.sqrt(np.mean(resid ** 2)))
        r2 = float(1 - np.sum(resid ** 2) / np.sum((true - np.mean(true)) ** 2))
        result[f"{name}_rmse"] = rmse
        result[f"{name}_r2"] = r2
        slope = float(linregress(true, pred).slope)
        result[f"{name}_slope"] = slope
        print(f"  {name}: RMSE={rmse:.5f}  R^2={r2:.4f}  slope={slope:.4f}")

    return result


def run_ablation(
    X: np.ndarray, y: np.ndarray,
    sizes: list[int],
    device: str = "cpu",
) -> dict[int, dict]:
    """Run ablation over training set sizes.

    Returns dict mapping size -> evaluation metrics.
    """
    results = {}
    for n in sizes:
        print(f"\n{'=' * 50}")
        print(f"Ablation: N_train = {n}")
        print(f"{'=' * 50}")

        rng = np.random.default_rng(42)
        idx = rng.permutation(len(X))
        X_shuf, y_shuf = X[idx], y[idx]

        X_tr, X_te, y_tr, y_te = (
            X_shuf[:n], X_shuf[n:], y_shuf[:n], y_shuf[n:]
        )

        surr = Surrogate(device=device)
        surr.fit(X_tr, y_tr, verbose=False)
        mu_mean, mu_std, sigma_mean, sigma_std = surr.predict(X_te)
        metrics = evaluate(X_te, y_te, mu_mean, sigma_mean)
        metrics["lengthscales_mu"] = surr.get_lengthscales("mu").tolist()
        metrics["lengthscales_sigma"] = surr.get_lengthscales("sigma").tolist()
        results[n] = metrics

    return results
