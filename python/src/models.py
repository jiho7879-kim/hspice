"""
GP model definitions (GPyTorch) for SRAM Vmin surrogate modeling.

Two architectures:
    - ExactGPModel:  Matern 5/2 + ARD over ALL input dims  (used for mu)
    - AdditiveGPModel:
        3D: k_Vop(Vop) + k_cnpu(cn, pu)
        4D+: k_op(Vop, Vwl) + k_cnpu(cn, pu, ...)
        where the operating group grows with extra dims
        and ARD automatically prunes irrelevant dims.

Both auto-adapt to input dimensionality d >= 3.
"""

from __future__ import annotations

import torch
import gpytorch

from src.utils import VOP_COL, VWL_COL


class ExactGPModel(gpytorch.models.ExactGP):
    """Single-output exact GP with Matern 5/2 + ARD kernel (all dims, auto-adapts).

    `likelihood=None` (default) constructs a homoscedastic GaussianLikelihood.
    Pass a FixedNoiseGaussianLikelihood for noise-aware training with known
    per-point observation noise (e.g. MC standard errors).
    """

    def __init__(self, train_x: torch.Tensor, train_y: torch.Tensor,
                 likelihood: "gpytorch.likelihoods.Likelihood | None" = None) -> None:
        from gpytorch.likelihoods import GaussianLikelihood
        from gpytorch.means import ConstantMean
        from gpytorch.kernels import ScaleKernel, MaternKernel

        if likelihood is None:
            likelihood = GaussianLikelihood()
        super().__init__(train_x, train_y, likelihood)
        self.mean_module = ConstantMean()
        n_dims = train_x.shape[-1]
        self.covar_module = ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=n_dims))

    def forward(self, x: torch.Tensor) -> gpytorch.distributions.MultivariateNormal:
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        return gpytorch.distributions.MultivariateNormal(mean_x, covar_x)


class AdditiveGPModel(gpytorch.models.ExactGP):
    """Additive GP: k_device(cn, [sk,] pu, ...) + k_op(Vop, Vwl, ...).

    The input splits into a leading DEVICE block (Vth-shift knobs) and a
    trailing OPERATING block (Vop and beyond).  `n_device` is the split point:

        Stage A (3D): n_device=2 -> k_cnpu(cn, pu)       + k_Vop(Vop)
        Stage B (4D): n_device=3 -> k_dev(cn, sk, pu)    + k_op(Vop)
        4D + WLUD   : n_device=2 -> k_cnpu(cn, pu)       + k_op(Vop, WLUD)

    n_device defaults to VOP_COL (=2, Stage A).  Pass n_device=3 for Stage B so
    skew is grouped with the device kernel (it is a device Vth param, not an
    operating condition).  ARD prunes irrelevant dims within each block.
    """

    def __init__(self, train_x: torch.Tensor, train_y: torch.Tensor,
                 likelihood: "gpytorch.likelihoods.Likelihood | None" = None,
                 n_device: int = VOP_COL) -> None:
        from gpytorch.likelihoods import GaussianLikelihood
        from gpytorch.means import ConstantMean
        from gpytorch.kernels import ScaleKernel, MaternKernel

        if likelihood is None:
            likelihood = GaussianLikelihood()
        super().__init__(train_x, train_y, likelihood)
        self.mean_module = ConstantMean()
        n_dims = train_x.shape[-1]
        if not (1 <= n_device < n_dims):
            raise ValueError(
                f"n_device must be in [1, n_dims); got n_device={n_device}, "
                f"n_dims={n_dims}")

        # Leading device block [0, n_device); trailing operating block
        # [n_device, n_dims).  Vop is the first operating dim (index n_device).
        # NOTE: operating kernel is kept as sub-kernel 0 and device kernel as
        # sub-kernel 1 (order preserved from the original 3D model) so saved
        # state_dicts (covar_module.kernels.{0,1}.*) stay load-compatible.
        n_op = n_dims - n_device
        self._n_device = n_device
        self._n_op = n_op
        self.covar_module = (
            ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=n_op,
                                     active_dims=list(range(n_device, n_dims)))) +
            ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=n_device,
                                     active_dims=list(range(n_device))))
        )

    def forward(self, x: torch.Tensor) -> gpytorch.distributions.MultivariateNormal:
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        return gpytorch.distributions.MultivariateNormal(mean_x, covar_x)


def make_additive_gp(train_x: torch.Tensor, train_y: torch.Tensor,
                     n_device: int = VOP_COL) -> AdditiveGPModel:
    """Factory: additive kernel with a device/operating split at `n_device`
    (default 2 = Stage A [cn, pu | Vop]; pass 3 for Stage B [cn, sk, pu | Vop])."""
    return AdditiveGPModel(train_x, train_y, n_device=n_device)
