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
    """Single-output exact GP with Matern 5/2 + ARD kernel (all dims, auto-adapts)."""

    def __init__(self, train_x: torch.Tensor, train_y: torch.Tensor) -> None:
        from gpytorch.likelihoods import GaussianLikelihood
        from gpytorch.means import ConstantMean
        from gpytorch.kernels import ScaleKernel, MaternKernel

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
    """Additive GP: k_op(Vop, Vwl, ...) + k_cnpu(cn, pu, ...).

    3D: k_Vop(Vop) + k_cnpu(cn, pu)
    4D+: k_op(Vop, Vwl, Temp, ...) + k_cnpu(cn, pu, ...)
         Operating-group dims: indices [VOP_COL .. n_dims-1] past core device dims.
    """

    def __init__(self, train_x: torch.Tensor, train_y: torch.Tensor) -> None:
        from gpytorch.likelihoods import GaussianLikelihood
        from gpytorch.means import ConstantMean
        from gpytorch.kernels import ScaleKernel, MaternKernel

        likelihood = GaussianLikelihood()
        super().__init__(train_x, train_y, likelihood)
        self.mean_module = ConstantMean()
        n_dims = train_x.shape[-1]

        if n_dims < 4:
            # 3D: k_Vop(Vop) + k_cnpu(cn, pu)
            self.covar_module = (
                ScaleKernel(MaternKernel(nu=2.5, active_dims=[VOP_COL])) +
                ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=2, active_dims=[0, 1]))
            )
        else:
            # 4D+: k_op(Vop, Vwl, ...) + k_cnpu(cn, pu, ...)
            # Operating-group starts at VOP_COL, spans the higher dims.
            n_op = n_dims - VOP_COL
            n_device = VOP_COL  # cn, pu
            self._n_op = n_op
            self.covar_module = (
                ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=n_op,
                                         active_dims=list(range(VOP_COL, n_dims)))) +
                ScaleKernel(MaternKernel(nu=2.5, ard_num_dims=n_device,
                                         active_dims=list(range(n_device))))
            )

    def forward(self, x: torch.Tensor) -> gpytorch.distributions.MultivariateNormal:
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        return gpytorch.distributions.MultivariateNormal(mean_x, covar_x)


def make_additive_gp(train_x: torch.Tensor, train_y: torch.Tensor) -> AdditiveGPModel:
    """Factory: select additive kernel group split based on input dimensionality."""
    return AdditiveGPModel(train_x, train_y)
