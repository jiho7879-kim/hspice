"""
GP surrogate model for PVTA toy project.

Trains a 3D->2D GP (Matern 5/2 + ARD) to predict:
    [common_N_shift, PU_shift, Vop] -> [mu_SNMR, sigma_SNMR]

Two independent GPs (one for mu, one for sigma) with shared kernel
structure. Supports ablation over training set size.

Usage:
    python src/toy_surrogate.py --data ./data/dataset.npz --out_dir ./results
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch
import gpytorch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import load_intermediate, stratified_train_test_split

# ---------------------------------------------------------------------------
# GP model (GPyTorch)
# ---------------------------------------------------------------------------

class ExactGPModel(gpytorch.models.ExactGP):
    """Single-output exact GP with Matern 5/2 + ARD kernel (standard, all dims)."""

    def __init__(self, train_x: torch.Tensor, train_y: torch.Tensor) -> None:
        from gpytorch.likelihoods import GaussianLikelihood
        from gpytorch.means import ConstantMean
        from gpytorch.kernels import ScaleKernel, MaternKernel

        likelihood = GaussianLikelihood()
        super().__init__(train_x, train_y, likelihood)
        self.mean_module = ConstantMean()
        # Matern 5/2 with ARD (one lengthscale per input dimension)
        self.covar_module = ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=3))

    def forward(self, x: torch.Tensor) -> gpytorch.distributions.MultivariateNormal:
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        return gpytorch.distributions.MultivariateNormal(mean_x, covar_x)


class AdditiveGPModel(gpytorch.models.ExactGP):
    """Additive GP: k_Vop(Vop) + k_cnpu(cn, pu). Separates Vop trend from corner effects."""

    def __init__(self, train_x: torch.Tensor, train_y: torch.Tensor) -> None:
        from gpytorch.likelihoods import GaussianLikelihood
        from gpytorch.means import ConstantMean
        from gpytorch.kernels import ScaleKernel, MaternKernel

        likelihood = GaussianLikelihood()
        super().__init__(train_x, train_y, likelihood)
        self.mean_module = ConstantMean()
        self.covar_module = (
            ScaleKernel(MaternKernel(nu=2.5, active_dims=[2])) +
            ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=2, active_dims=[0, 1]))
        )

    def forward(self, x: torch.Tensor) -> gpytorch.distributions.MultivariateNormal:
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        return gpytorch.distributions.MultivariateNormal(mean_x, covar_x)


class Surrogate:
    """Dual-output GP surrogate: mu and sigma modeled independently.

    mu:    ExactGPModel (full 3D Matern 5/2 + ARD)
    sigma: AdditiveGPModel (k_Vop(Vop) + k_cnpu(cn, pu))
    """

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self.mu_gp: ExactGPModel | None = None
        self.sigma_gp: AdditiveGPModel | None = None
        self._x_train: np.ndarray | None = None

    def _to_tensor(self, arr: np.ndarray) -> torch.Tensor:
        return torch.from_numpy(arr.astype(np.float32)).to(self.device)

    def fit(self, X_train: np.ndarray, y_train: np.ndarray,
            n_iter: int = 200, lr: float = 0.1, verbose: bool = True) -> None:
        """Train both mu and sigma GPs.

        Args:
            X_train: (N, 3) training inputs
            y_train: (N, 2) training targets [mu, sigma]
            n_iter: Training iterations
            lr: Learning rate for Adam
        """
        self._x_train = X_train.copy()
        xt = self._to_tensor(X_train)
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
                    ls_vop = gp.covar_module.kernels[0].base_kernel.lengthscale.detach()
                    ls_cnpu = gp.covar_module.kernels[1].base_kernel.lengthscale.detach()
                    ls_str = f"Vop={ls_vop.item():.3f}, cn={ls_cnpu[0,0].item():.3f}, pu={ls_cnpu[0,1].item():.3f}"
                else:
                    ls = gp.covar_module.base_kernel.lengthscale.detach().cpu().numpy().flatten()
                    ls_str = str(ls.round(3))
                print(f"  [{name}] done ({elapsed:.1f}s) "
                      f"lengthscales={ls_str}")

    def predict(self, X_test: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Predict mu and sigma with uncertainty.

        Returns:
            mu_mean, mu_std, sigma_mean, sigma_std: each (N,)
        """
        assert self.mu_gp is not None and self.sigma_gp is not None

        xt = self._to_tensor(X_test)

        with torch.no_grad():
            mu_pred = self.mu_gp(xt)
            sigma_pred = self.sigma_gp(xt)

        mu_mean = mu_pred.mean.cpu().numpy()
        mu_std = mu_pred.stddev.cpu().numpy()
        sigma_mean = sigma_pred.mean.cpu().numpy()
        sigma_std = sigma_pred.stddev.cpu().numpy()

        return mu_mean, mu_std, sigma_mean, sigma_std

    def get_lengthscales(self, model: str = "mu") -> np.ndarray:
        """Return ARD lengthscales.

        For ExactGPModel: shape (3,) = [cn, pu, Vop].
        For AdditiveGPModel: shape (3,) = [Vop, cn, pu] (reordered for display).
        """
        if model == "mu":
            assert self.mu_gp is not None
            return self.mu_gp.covar_module.base_kernel.lengthscale.detach().cpu().numpy().flatten()
        else:
            assert self.sigma_gp is not None
            gp = self.sigma_gp
            ls_vop = gp.covar_module.kernels[0].base_kernel.lengthscale.detach().cpu().numpy().flatten()
            ls_cnpu = gp.covar_module.kernels[1].base_kernel.lengthscale.detach().cpu().numpy().flatten()
            return np.concatenate([ls_vop, ls_cnpu])  # [Vop_lengthscale, cn_lengthscale, pu_lengthscale]


# ---------------------------------------------------------------------------
# Training + evaluation
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
        # slope of predicted vs true (should be ~1)
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

        # Subset training data (first n points after shuffle)
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="GP surrogate training + ablation")
    parser.add_argument("--data", default="./data/dataset.npz", help="Path to dataset.npz")
    parser.add_argument("--out_dir", default="./results", help="Output directory")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--ablation", action="store_true", help="Run ablation sweep")
    args = parser.parse_args()

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    # Load
    X, y = load_intermediate(args.data)
    print(f"Loaded: {args.data}  -- X: {X.shape}, y: {y.shape}")

    # Train/test split
    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.2)
    print(f"Train: {len(X_tr)}  Test: {len(X_te)}")

    # Train
    surr = Surrogate(device=args.device)
    surr.fit(X_tr, y_tr)

    # Evaluate
    print("\n--- Test set evaluation ---")
    mu_mean, mu_std, sigma_mean, sigma_std = surr.predict(X_te)
    metrics = evaluate(X_te, y_te, mu_mean, sigma_mean)

    mu_ls = surr.get_lengthscales("mu")
    sigma_ls = surr.get_lengthscales("sigma")
    print(f"\nARD lengthscales (smaller = more important):")
    print(f"  mu GP:    [cn={mu_ls[0]:.3f}, pu={mu_ls[1]:.3f}, Vop={mu_ls[2]:.3f}]")
    print(f"  sigma GP: [Vop={sigma_ls[0]:.3f}, cn={sigma_ls[1]:.3f}, pu={sigma_ls[2]:.3f}]  (additive kernel)")

    # Save results
    import json
    with open(Path(args.out_dir) / "surrogate_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    # Ablation
    if args.ablation:
        sizes = [50, 100, 200, 400, 800, 1000]
        ab_results = run_ablation(X, y, sizes, device=args.device)
        # Save ablation results
        ab_data = {str(k): v for k, v in ab_results.items()}
        with open(Path(args.out_dir) / "ablation_results.json", "w") as f:
            json.dump(ab_data, f, indent=2)
        print(f"\nAblation results saved to {args.out_dir}/ablation_results.json")


if __name__ == "__main__":
    main()
