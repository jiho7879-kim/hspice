"""
Tests for GP model definitions (ExactGPModel, AdditiveGPModel).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch

from src.models import ExactGPModel, AdditiveGPModel


def test_exact_gp_model_3d() -> None:
    """ExactGPModel with 3D input produces correct output shapes."""
    rng = np.random.default_rng(42)
    n = 50
    x = torch.from_numpy(rng.uniform(-1, 1, size=(n, 3)).astype(np.float32))
    y = torch.from_numpy(rng.uniform(0, 1, size=(n,)).astype(np.float32))

    model = ExactGPModel(x, y)
    model.eval()
    model.likelihood.eval()

    with torch.no_grad():
        out = model(x)

    assert out.mean.shape == (n,), f"Expected ({n},), got {out.mean.shape}"
    assert out.stddev.shape == (n,), f"Expected ({n},), got {out.stddev.shape}"
    assert torch.isfinite(out.mean).all(), "Non-finite mean values"
    assert torch.isfinite(out.stddev).all(), "Non-finite stddev values"
    print(f"  [OK] ExactGPModel 3D: mean={out.mean.mean():.4f}, stddev={out.stddev.mean():.4f}")


def test_exact_gp_model_8d() -> None:
    """ExactGPModel auto-adapts to 8D input (ARD dims match input dims)."""
    rng = np.random.default_rng(42)
    n = 50
    x = torch.from_numpy(rng.uniform(-1, 1, size=(n, 8)).astype(np.float32))
    y = torch.from_numpy(rng.uniform(0, 1, size=(n,)).astype(np.float32))

    model = ExactGPModel(x, y)
    model.eval()
    model.likelihood.eval()

    ls = model.covar_module.base_kernel.lengthscale
    assert ls.shape[-1] == 8, f"Expected 8 ARD dims, got {ls.shape[-1]}"

    with torch.no_grad():
        out = model(x)
    assert out.mean.shape == (n,)
    print(f"  [OK] ExactGPModel 8D: ARD dims={ls.shape[-1]}")


def test_additive_gp_model_structure() -> None:
    """AdditiveGPModel has k_Vop(Vop) + k_cnpu(cn, pu) kernel structure."""
    rng = np.random.default_rng(42)
    n = 50
    x = torch.from_numpy(rng.uniform(-1, 1, size=(n, 3)).astype(np.float32))
    y = torch.from_numpy(rng.uniform(0, 1, size=(n,)).astype(np.float32))

    model = AdditiveGPModel(x, y)
    kernel = model.covar_module

    # Should be an additive kernel with 2 sub-kernels
    assert hasattr(kernel, "kernels"), "Expected additive kernel (SumKernel)"
    n_kernels = len(kernel.kernels)
    assert n_kernels == 2, f"Expected 2 sub-kernels, got {n_kernels}"

    # Sub-kernel 0: Vop-only kernel (active_dims=[2])
    k0 = kernel.kernels[0]
    assert hasattr(k0, "base_kernel"), "Expected ScaleKernel wrapping"
    assert k0.base_kernel.active_dims.tolist() == [2], \
        f"Expected Vop kernel active_dims=[2], got {k0.base_kernel.active_dims}"

    # Sub-kernel 1: cn+pu kernel (active_dims=[0, 1], ard_num_dims=2)
    k1 = kernel.kernels[1]
    assert k1.base_kernel.active_dims.tolist() == [0, 1], \
        f"Expected cn+pu kernel active_dims=[0,1], got {k1.base_kernel.active_dims}"
    assert k1.base_kernel.ard_num_dims == 2, \
        f"Expected ard_num_dims=2, got {k1.base_kernel.ard_num_dims}"

    model.eval()
    model.likelihood.eval()
    with torch.no_grad():
        out = model(x)
    assert out.mean.shape == (n,)
    assert torch.isfinite(out.mean).all()
    print(f"  [OK] AdditiveGPModel: 2 sub-kernels (Vop + cn,pu)")


def test_model_training_loop() -> None:
    """Both models can complete a short training loop without errors."""
    import gpytorch

    rng = np.random.default_rng(42)
    n = 30
    x = torch.from_numpy(rng.uniform(-1, 1, size=(n, 3)).astype(np.float32))
    y = torch.from_numpy(rng.uniform(0, 1, size=(n,)).astype(np.float32))

    for name, Model in [("ExactGPModel", ExactGPModel),
                        ("AdditiveGPModel", AdditiveGPModel)]:
        model = Model(x, y)
        model.train()
        model.likelihood.train()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.1)
        mll = gpytorch.mlls.ExactMarginalLogLikelihood(model.likelihood, model)

        loss_initial: float | None = None
        loss_final: float | None = None
        for i in range(20):
            optimizer.zero_grad()
            output = model(x)
            loss = -mll(output, model.train_targets)
            loss.backward()
            optimizer.step()
            if i == 0:
                loss_initial = loss.item()
            if i == 19:
                loss_final = loss.item()

        assert loss_initial is not None and loss_final is not None
        assert loss_final <= loss_initial + 0.01, \
            f"{name}: loss did not decrease ({loss_initial:.4f} -> {loss_final:.4f})"
        print(f"  [OK] {name} training: {loss_initial:.4f} -> {loss_final:.4f}")


if __name__ == "__main__":
    print("=== test_models ===")
    test_exact_gp_model_3d()
    test_exact_gp_model_8d()
    test_additive_gp_model_structure()
    test_model_training_loop()
    print("\n=== ALL MODELS TESTS PASSED ===")
