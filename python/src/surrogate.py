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

from src.models import ExactGPModel, AdditiveGPModel  # noqa: F401  (Additive kept for old code paths)
from src.utils import StandardScaler, VOP_COL, vop_col_for


def _positive_sigma(y_train: np.ndarray) -> np.ndarray:
    """Training sigma column, guarded so log() is defined.

    A zero or negative sigma is a data defect, not something to clamp past
    silently — every caller feeds MC standard deviations in volts.
    """
    s = np.asarray(y_train[:, 1], dtype=np.float64)
    assert np.all(np.isfinite(s)) and np.all(s > 0), (
        f"sigma targets must be finite and positive for the log fit; "
        f"got min={np.nanmin(s):.3e}, {np.sum(~(s > 0))} non-positive")
    return s


class Surrogate:
    """Dual-output GP surrogate: mu and sigma modeled independently.

    mu:    ExactGPModel (full Matern 5/2 + ARD across all input dims)
    sigma: ExactGPModel on LOG sigma (full Matern 5/2 + ARD, same as mu)

    sigma used to be an AdditiveGPModel (k_Vop(Vop) + k_dev(device axes)) fitted
    on a linear scale.  Both parts were wrong and they interact (D-16, N020-N021):

      * Additive cannot represent any device x Vop interaction, i.e. it assumes
        the sigma-vs-Vop curve has one shape everywhere in the 9D window.
      * sigma's own observation noise is sem_sigma = sigma/sqrt(2N), which is
        proportional, so the scale where that noise is homoscedastic is log sigma.

    Fixing both halves the hold-out Vmin RMSE (read 8.35 -> 4.04 mV, write
    14.45 -> 7.21 mV).  fit/predict still speak LINEAR sigma at the API boundary;
    the log transform and its delta-method noise are internal.

    Input X is standardized inside fit/predict — callers pass raw values.
    Trained checkpoints include the scaler, so load() restores everything.
    """

    # bumped when the sigma model changes, so an old checkpoint fails loudly
    # instead of loading its AdditiveGPModel weights into the wrong module
    SIGMA_MODEL = "log_full_ard"

    def __init__(self, device: str = "cpu",
                 n_device: int = VOP_COL) -> None:
        self.device = device
        self._n_device = n_device
        self._vop_col = vop_col_for(n_device)
        self.mu_gp: ExactGPModel | None = None
        self.sigma_gp: ExactGPModel | None = None
        self._x_train: np.ndarray | None = None
        self._x_scaler = StandardScaler()
        self._y_noise: np.ndarray | None = None
        self._sigma_train: np.ndarray | None = None   # linear sigma, for the delta method

    def _to_tensor(self, arr: np.ndarray) -> torch.Tensor:
        return torch.from_numpy(arr.astype(np.float32)).to(self.device)

    def _make_likelihood(self, col: int):
        """Homoscedastic likelihood, or noise-aware when y_noise was given.

        y_noise holds per-point observation-noise STDs (e.g. MC standard
        errors: sem_mu = sigma/sqrt(N), sem_sigma ~ bootstrap).  The GP then
        automatically downweights high-noise points — this is also how
        mixed MC budgets (200 vs 10k samples) are unified in one model
        (noise-aware MC budget allocation, plan sec 3.5/4.4).
        """
        if self._y_noise is None:
            from gpytorch.likelihoods import GaussianLikelihood
            return GaussianLikelihood()
        from gpytorch.likelihoods import FixedNoiseGaussianLikelihood
        noise = self._y_noise[:, col]
        if col == 1:
            # sigma is fitted on log sigma, so its noise transforms with it:
            # sd(log s) = sd(s)/s  (delta method).  _y_noise stays raw on disk.
            assert self._sigma_train is not None
            noise = noise / self._sigma_train
        noise_var = self._to_tensor(noise ** 2)
        return FixedNoiseGaussianLikelihood(
            noise=noise_var, learn_additional_noise=True,
        )

    def fit(self, X_train: np.ndarray, y_train: np.ndarray,
            n_iter: int = 200, lr: float = 0.1, verbose: bool = True,
            y_noise: np.ndarray | None = None) -> None:
        """Train both mu and sigma GPs on standardized inputs.

        Args:
            X_train: (N, d) training inputs [common_N, PU, Vop, ...]
            y_train: (N, 2) training targets [mu, sigma]
            n_iter: Training iterations
            lr: Learning rate for Adam
            y_noise: optional (N, 2) per-point observation-noise STDs
                [sem_mu, sem_sigma].  When given, FixedNoiseGaussianLikelihood
                is used (noise-aware GP); when None, behaviour is unchanged.
        """
        if y_noise is not None:
            y_noise = np.asarray(y_noise, dtype=np.float64)
            assert y_noise.shape == y_train.shape, (
                f"y_noise shape {y_noise.shape} != y_train shape {y_train.shape}")
            assert np.all(y_noise > 0), "y_noise must be positive STDs"
        self._y_noise = y_noise.copy() if y_noise is not None else None

        self._x_train = X_train.copy()
        self._sigma_train = _positive_sigma(y_train)
        X_scaled = self._x_scaler.fit_transform(X_train)
        xt = self._to_tensor(X_scaled)
        yt_mu = self._to_tensor(y_train[:, 0])
        yt_sigma = self._to_tensor(np.log(self._sigma_train))

        self.mu_gp = ExactGPModel(xt, yt_mu, likelihood=self._make_likelihood(0)).to(self.device)
        self.sigma_gp = ExactGPModel(xt, yt_sigma,
                                     likelihood=self._make_likelihood(1)).to(self.device)

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
                    labels = ["cn"]
                    if self._n_device > 2:
                        labels.append("sk")
                    labels.append("pu")
                    labels.append("Vop")
                    labels += [f"d{i}" for i in range(len(labels), len(ls))]
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

        # sigma_gp lives on log sigma; undo it here so callers keep seeing volts.
        # sd(s) = s * sd(log s) by the delta method.
        def _lin(pred):
            s = np.exp(pred.mean.cpu().numpy())
            return s, s * pred.stddev.cpu().numpy()

        n = len(X)
        if n <= batch_size:
            xt = self._to_tensor(X)
            with torch.no_grad():
                mu_pred = self.mu_gp(xt)
                sigma_pred = self.sigma_gp(xt)
            s_mean, s_std = _lin(sigma_pred)
            return (mu_pred.mean.cpu().numpy(), mu_pred.stddev.cpu().numpy(),
                    s_mean, s_std)

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
            sigma_mean[start:end], sigma_std[start:end] = _lin(sigma_pred)

        return mu_mean, mu_std, sigma_mean, sigma_std

    def predict_mean(self, X_test: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Posterior means only (mu, sigma), skipping predictive variances.

        Exists so callers that only need the means -- inversion, Sobol sampling --
        do not pay for the covariance, AND do not reach into self.sigma_gp
        themselves: that posterior is on LOG sigma, so a raw .mean is not sigma.
        """
        assert self.mu_gp is not None and self.sigma_gp is not None
        xt = self._to_tensor(self._x_scaler.transform(X_test))
        with torch.no_grad(), gpytorch.settings.skip_posterior_variances(True):
            return (self.mu_gp(xt).mean.cpu().numpy(),
                    np.exp(self.sigma_gp(xt).mean.cpu().numpy()))

    def save(self, path: str | Path) -> None:
        """Save trained GP state dicts + scaler (+ noise) to a .pth checkpoint."""
        state = {
            "mu_gp": self.mu_gp.state_dict() if self.mu_gp is not None else None,
            "sigma_gp": self.sigma_gp.state_dict() if self.sigma_gp is not None else None,
            "x_train": self._x_train,
            "x_scaler_mean": self._x_scaler.mean_,
            "x_scaler_std": self._x_scaler.std_,
            "y_noise": self._y_noise,
            "sigma_model": self.SIGMA_MODEL,
        }
        torch.save(state, path)
        print(f"  [save] checkpoint -> {path}")

    @classmethod
    def load(cls, path: str | Path, X_train: np.ndarray,
             y_train: np.ndarray, device: str = "cpu",
             n_device: int = VOP_COL) -> "Surrogate":
        """Load trained GP state dicts + scaler from a .pth checkpoint.

        X_train/y_train must match original training data shape because
        ExactGP requires them at construction.  The checkpoint's scaler
        (and per-point noise, when the model was noise-aware) is restored
        so predict() works on raw inputs.
        n_device controls the device/operating kernel split in AdditiveGPModel
        (Stage A default 2; pass 3 for Stage B with sk).
        """
        # weights_only=False: this checkpoint bundles numpy metadata
        # (scaler stats, x_train, y_noise) alongside the tensor state dicts,
        # which the weights_only unpickler rejects.  These files are always
        # self-produced by Surrogate.save() (trusted source).
        state = torch.load(path, map_location=device, weights_only=False)
        # Pre-D-16 checkpoints hold AdditiveGPModel weights fitted on linear sigma.
        # Loading those into the log/full-ARD module would silently produce garbage
        # sigma, so refuse instead of guessing.
        ckpt_sigma = state.get("sigma_model", "additive_linear")
        assert ckpt_sigma == cls.SIGMA_MODEL, (
            f"{path} was written with sigma_model={ckpt_sigma!r} but this Surrogate "
            f"expects {cls.SIGMA_MODEL!r} (D-16). Re-train with --refit.")
        surr = cls(device=device, n_device=n_device)
        surr._x_train = X_train.copy()
        # old checkpoints (pre noise-aware) have no "y_noise" key
        surr._y_noise = state.get("y_noise", None)
        surr._sigma_train = _positive_sigma(y_train)

        if state["x_scaler_mean"] is not None:
            surr._x_scaler.mean_ = state["x_scaler_mean"]
            surr._x_scaler.std_ = state["x_scaler_std"]

        X_scaled = surr._x_scaler.transform(X_train)
        xt = surr._to_tensor(X_scaled)
        yt_mu = surr._to_tensor(y_train[:, 0])
        yt_sigma = surr._to_tensor(np.log(surr._sigma_train))

        surr.mu_gp = ExactGPModel(xt, yt_mu, likelihood=surr._make_likelihood(0)).to(device)
        surr.sigma_gp = ExactGPModel(xt, yt_sigma,
                                     likelihood=surr._make_likelihood(1)).to(device)

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
        """Return ARD lengthscales (on the *standardized* input scale).

        Both GPs are now full-ARD ExactGPModels (D-16), so both return one
        lengthscale per input column, already in input order (DEVICE + [Vop]).
        Before D-16, sigma was an AdditiveGPModel and this returned the
        sub-kernel blocks Vop-first, which callers had to reorder -- they must
        not do that any more.
        """
        gp = self.mu_gp if model == "mu" else self.sigma_gp
        assert gp is not None, f"{model} GP not fitted"
        return gp.covar_module.base_kernel.lengthscale.detach().cpu().numpy().flatten()


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
