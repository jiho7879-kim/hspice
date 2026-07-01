"""
Physics-Constrained GP Surrogate — L_mono, L_boundary, L_pelgrom.

Extends the standard GP surrogate with physics-informed constraints during training:

    1. L_mono (Monotonicity):
       Vop ↑ → mu_SNMR ↑  (∂mu/∂Vop > 0)
       Evaluated on probe points across the domain (PINN-style collocation).
       Penalty: ReLU(-∂mu/∂Vop)²

    2. L_boundary (Corner Anchor):
       4 global corners (FSG, SFG, FFG, SSG) × 6 Vop levels = 24 virtual observations.
       True values from analytic model (or measured HSPICE in production).
       Augments training data — hard anchor, exact constraint.

    3. L_pelgrom (Sigma Scaling):
       sigma(Vop) = SIGMA0 + SIGMA_VOP_SLOPE × (0.9 - Vop)
       Penalty: (sigma_pred - pelgrom_target)²

    All constraints are implemented as additive penalty terms to the
    negative marginal log likelihood during training:

        L_total = -log p(y|X,θ) + λ_mono·L_mono + λ_pelgrom·L_pelgrom

Usage:
    surr = PhysicsConstrainedSurrogate(device="cpu")
    surr.fit(X_train, y_train, use_mono=True, use_boundary=True, ...)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import torch
import gpytorch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.utils import VOPS, COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX
from src.toy_surrogate import ExactGPModel, AdditiveGPModel

# ---------------------------------------------------------------------------
# Constants — analytic model for corner anchor ground truth
# ---------------------------------------------------------------------------
# Must match demo_pvta_contour.py exactly for fair comparison
A_MU = 0.15
B_MU = +0.001
C_MU = -0.0015
D_MU = 0.0
SIGMA0 = 0.015
SIGMA_VOP_SLOPE = 0.004


def analytic_snmr(cn_mv: float, pu_mv: float, vop_v: float) -> tuple[float, float]:
    """Analytic SNMR model used for corner anchor ground truth."""
    mu = A_MU * vop_v + B_MU * cn_mv + C_MU * pu_mv + D_MU
    sigma = SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - vop_v)
    return mu, sigma


# ---------------------------------------------------------------------------
# Probe points for monotonicity constraint
# ---------------------------------------------------------------------------

def generate_probe_points(n_per_dim: int = 8) -> np.ndarray:
    """Generate (N, 3) probe points spread across [common_N, PU, Vop] space.

    These are collocation points for the L_mono constraint, analogous to
    PINN interior points where the PDE residual is evaluated.

    Returns:
        (n_per_dim^3, 3) array of [common_N, PU, Vop] values
    """
    cn = np.linspace(COMMON_N_MIN, COMMON_N_MAX, n_per_dim)
    pu = np.linspace(PU_MIN, PU_MAX, n_per_dim)
    vop = VOPS  # use the discrete Vop levels as probe Vop values
    CN, PU, VOP = np.meshgrid(cn, pu, vop, indexing="ij")
    probes = np.column_stack([CN.ravel(), PU.ravel(), VOP.ravel()])
    return probes.astype(np.float64)


# ---------------------------------------------------------------------------
# Corner anchor data
# ---------------------------------------------------------------------------

GLOBAL_CORNERS_MV = [
    (-60.0,  60.0),   # FSG — fast N, slow P   (SNMR worst @ hot)
    ( 60.0, -60.0),   # SFG — slow N, fast P   (Vtrip worst @ cold)
    (-60.0, -60.0),   # FFG — fast N, fast P
    ( 60.0,  60.0),   # SSG — slow N, slow P
]


def generate_corner_anchor_data() -> tuple[np.ndarray, np.ndarray]:
    """Generate virtual observations at 4 global corners × 6 Vop.

    Returns:
        X_corner: (24, 3) [common_N, PU, Vop]
        y_corner: (24, 2) [mu_SNMR, sigma_SNMR] from analytic model
    """
    n = len(GLOBAL_CORNERS_MV) * len(VOPS)
    X = np.zeros((n, 3), dtype=np.float64)
    y = np.zeros((n, 2), dtype=np.float64)
    for i, (cn, pu) in enumerate(GLOBAL_CORNERS_MV):
        for j, vop in enumerate(VOPS):
            idx = i * len(VOPS) + j
            X[idx] = [cn, pu, vop]
            mu, sigma = analytic_snmr(cn, pu, vop)
            y[idx] = [mu, sigma]
    return X, y


# ---------------------------------------------------------------------------
# Physics-Constrained Surrogate
# ---------------------------------------------------------------------------

class PhysicsConstrainedSurrogate:
    """GP surrogate with optional physics-informed constraint terms.

    Constraints are added as penalty terms to the negative marginal log
    likelihood during training. Each constraint has a configurable λ weight.

    Parameters
    ----------
    device : str
        'cpu' or 'cuda'
    """

    def __init__(self, device: str = "cpu", checkpoint_dir: str | None = None) -> None:
        self.device = device
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
        self.mu_gp: ExactGPModel | None = None
        self.sigma_gp: AdditiveGPModel | None = None
        self._x_train: np.ndarray | None = None
        self._probe_points: np.ndarray | None = None

    def _to_tensor(self, arr: np.ndarray) -> torch.Tensor:
        return torch.from_numpy(arr.astype(np.float32)).to(self.device)

    # -------------------------------------------------------------------
    # Main fit method
    # -------------------------------------------------------------------

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        n_iter: int = 150,
        lr: float = 0.1,
        verbose: bool = True,
        # --- Physics constraint flags ---
        use_mono: bool = True,
        use_boundary: bool = True,
        use_pelgrom: bool = True,
        # --- Lambda weights ---
        lambda_mono: float = 100.0,
        lambda_pelgrom: float = 1.0,
        # --- Probe configuration ---
        n_probe: int = 6,
        # --- Checkpoint ---
        ckpt_tag: str = "",
    ) -> None:
        """Train both mu and sigma GPs with optional physics constraints.

        Args:
            X_train: (N, 3) training inputs [common_N, PU, Vop]
            y_train: (N, 2) training targets [mu, sigma]
            n_iter: Number of training iterations.
            lr: Learning rate for Adam.
            use_mono: Apply L_mono (Vop↑→mu↑) constraint.
            use_boundary: Augment training data with 4 corner anchors.
            use_pelgrom: Apply L_pelgrom (sigma scaling) constraint.
            lambda_mono: Weight for monotonicity penalty.
            lambda_pelgrom: Weight for Pelgrom scaling penalty.
            n_probe: Grid points per dimension for L_mono probes.
        """
        self._x_train = X_train.copy()
        self._use_mono = use_mono
        self._use_pelgrom = use_pelgrom

        # --- Data augmentation for corner anchors ---
        if use_boundary:
            X_corner, y_corner = generate_corner_anchor_data()
            X_aug = np.concatenate([X_train, X_corner], axis=0)
            y_aug = np.concatenate([y_train, y_corner], axis=0)
            n_aug = len(X_corner)
            if verbose:
                print(f"  [boundary] Added {n_aug} corner anchor points "
                      f"(4 corners × {len(VOPS)} Vop)")
        else:
            X_aug, y_aug = X_train, y_train

        # Pre-generate probe points for L_mono (shared across training iterations)
        if use_mono:
            self._probe_points = generate_probe_points(n_per_dim=n_probe)
            if verbose:
                print(f"  [mono] {len(self._probe_points)} probe points "
                      f"({n_probe}³ × {n_probe} Vop)")

        # Convert to tensors
        xt_aug = self._to_tensor(X_aug)
        yt_aug_mu = self._to_tensor(y_aug[:, 0])
        yt_aug_sigma = self._to_tensor(y_aug[:, 1])

        # ---- Train mu GP ----
        if verbose:
            print("\n--- Training mu GP ---")
        self.mu_gp = ExactGPModel(xt_aug, yt_aug_mu).to(self.device)
        self._train_gp(
            self.mu_gp, xt_aug, yt_aug_mu,
            n_iter=n_iter, lr=lr, verbose=verbose,
            name="mu",
            apply_mono=use_mono,
            apply_pelgrom=False,
            lambda_mono=lambda_mono,
            lambda_pelgrom=0.0,
            ckpt_tag=ckpt_tag,
        )

        # ---- Train sigma GP ----
        if verbose:
            print("\n--- Training sigma GP ---")
        self.sigma_gp = AdditiveGPModel(xt_aug, yt_aug_sigma).to(self.device)
        self._train_gp(
            self.sigma_gp, xt_aug, yt_aug_sigma,
            n_iter=n_iter, lr=lr, verbose=verbose,
            name="sigma",
            apply_mono=False,  # monotonicity is mu-only
            apply_pelgrom=use_pelgrom,
            lambda_mono=0.0,
            lambda_pelgrom=lambda_pelgrom,
            ckpt_tag=ckpt_tag,
        )

    # -------------------------------------------------------------------
    # Checkpoint save/load
    # -------------------------------------------------------------------

    def _ckpt_path(self, tag: str) -> Path | None:
        if self.checkpoint_dir is None:
            return None
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        return self.checkpoint_dir / f"gp_{tag}.pth"

    def _save_checkpoint(self, gp: ExactGPModel | AdditiveGPModel, tag: str) -> None:
        ckpt = self._ckpt_path(tag)
        if ckpt is not None:
            torch.save(gp.state_dict(), ckpt)

    def _load_checkpoint(self, gp: ExactGPModel | AdditiveGPModel, tag: str) -> bool:
        ckpt = self._ckpt_path(tag)
        if ckpt is not None and ckpt.exists():
            gp.load_state_dict(torch.load(ckpt, map_location=self.device, weights_only=True))
            gp.eval()
            gp.likelihood.eval()
            return True
        return False

    # -------------------------------------------------------------------
    # Internal training with physics loss
    # -------------------------------------------------------------------

    def _train_gp(
        self,
        gp: ExactGPModel | AdditiveGPModel,
        xt: torch.Tensor,
        yt: torch.Tensor,
        n_iter: int,
        lr: float,
        verbose: bool,
        name: str,
        apply_mono: bool,
        apply_pelgrom: bool,
        lambda_mono: float,
        lambda_pelgrom: float,
        ckpt_tag: str = "",
    ) -> None:
        """Train a single GP with optional physics penalty terms.

        L_mono is expensive (eval-mode posterior Cholesky) so we apply it
        only after a warmup period and then every N iterations.
        """
        # Try loading checkpoint before training
        tag = f"{ckpt_tag}_{name}" if ckpt_tag else ""
        if tag:
            loaded = self._load_checkpoint(gp, tag)
            if loaded and verbose:
                print(f"  [{name}] Loaded checkpoint ({tag}) — skipping training")
                return

        gp.train()
        gp.likelihood.train()

        optimizer = torch.optim.Adam(gp.parameters(), lr=lr)
        mll = gpytorch.mlls.ExactMarginalLogLikelihood(gp.likelihood, gp)

        # Pre-tensorize probe points if needed
        if apply_mono and self._probe_points is not None:
            probe_t = self._to_tensor(self._probe_points)
        else:
            probe_t = None

        # Constraint scheduling: warmup + skip for speed
        mono_warmup = 30  # apply L_mono only after this many iters
        mono_interval = 3  # apply L_mono every N iters (not every iter)

        # Track loss components for logging
        data_losses, mono_losses, pelgrom_losses = [], [], []
        last_mono_penalty = 0.0

        start = time.time()
        for i in range(n_iter):
            optimizer.zero_grad()

            # Forward pass
            output = gp(xt)
            data_loss = -mll(output, gp.train_targets)

            # Physics constraints
            mono_penalty = torch.tensor(0.0, device=self.device)
            pelgrom_penalty = torch.tensor(0.0, device=self.device)

            if apply_mono and probe_t is not None and i >= mono_warmup and i % mono_interval == 0:
                mono_penalty = self._compute_mono_penalty(gp, probe_t)
                if torch.isnan(mono_penalty):
                    mono_penalty = torch.tensor(0.0, device=self.device)
            if apply_pelgrom and name == "sigma":
                pelgrom_penalty = self._compute_pelgrom_penalty(gp, xt)
                if torch.isnan(pelgrom_penalty):
                    pelgrom_penalty = torch.tensor(0.0, device=self.device)

            total_loss = data_loss + lambda_mono * mono_penalty + lambda_pelgrom * pelgrom_penalty
            total_loss.backward()
            optimizer.step()

            # Logging
            data_losses.append(data_loss.item())
            mono_losses.append(mono_penalty.item() if apply_mono else 0.0)
            pelgrom_losses.append(pelgrom_penalty.item() if apply_pelgrom else 0.0)

            if verbose and (i + 1) % 50 == 0:
                parts = [f"data={data_loss.item():.2f}"]
                if apply_mono:
                    parts.append(f"mono={mono_penalty.item():.6f}")
                if apply_pelgrom:
                    parts.append(f"pelgrom={pelgrom_penalty.item():.6f}")
                print(f"  [{name}] iter {i + 1:4d}/{n_iter}  "
                      f"loss={' + '.join(parts)}")

        gp.eval()
        gp.likelihood.eval()
        elapsed = time.time() - start

        # Print lengthscales
        ls_str = self._format_lengthscales(gp, name)
        if verbose:
            print(f"  [{name}] done ({elapsed:.1f}s)  "
                  f"final: data={data_losses[-1]:.2f}, "
                  f"mono={mono_losses[-1]:.6f}, "
                  f"pelgrom={pelgrom_losses[-1]:.6f}")
            print(f"  [{name}] lengthscales={ls_str}")

        # Save checkpoint
        if tag:
            self._save_checkpoint(gp, tag)

    # -------------------------------------------------------------------
    # Physics penalty computations
    # -------------------------------------------------------------------

    def _compute_mono_penalty(
        self, gp: ExactGPModel | AdditiveGPModel,
        probe_t: torch.Tensor,
    ) -> torch.Tensor:
        """Compute L_mono = mean(ReLU(-∂μ/∂Vop)²).

        POSTERIOR mean gradient at probe points via eval-mode forward pass.
        During train mode, ExactGP only returns the prior.  To get the
        posterior (which depends on the inputs through K(x_probe, X_train))
        we temporarily switch to eval mode, then switch back.

        Gradient flow: posterior_mean → K(probe, X_train) → lengthscale
        parameters, so penalty.backward() reaches the kernel hyperparameters.
        """
        probe_grad = probe_t.clone().detach().requires_grad_(True)

        was_training = gp.training
        gp.eval()
        # Reset cached prediction strategy so gp() recomputes it with the
        # CURRENT kernel parameters, preserving the gradient graph.
        # (Don't del — that removes the attribute and breaks __call__)
        gp.prediction_strategy = None

        output = gp(probe_grad)
        mean = output.mean
        grad = torch.autograd.grad(mean.sum(), probe_grad, create_graph=True)[0]
        dmu_dvop = grad[:, 2]  # Vop is column index 2
        penalty = torch.relu(-dmu_dvop).pow(2).mean()

        if was_training:
            gp.train()
            gp.likelihood.train()

        return penalty

    def _compute_pelgrom_penalty(
        self, gp: AdditiveGPModel,
        xt: torch.Tensor,
    ) -> torch.Tensor:
        """Compute L_pelgrom = mean((sigma - pelgrom_target)²).

        Pelgrom scaling: sigma(Vop) = SIGMA0 + SIGMA_VOP_SLOPE × (0.9 - Vop).
        Penalizes sigma predictions that deviate from this physical scaling.
        """
        with torch.no_grad():
            output = gp(xt)
            sigma_pred = output.mean
            # Pelgrom target: sigma decreases as Vop increases
            pelgrom_target = (
                SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - xt[:, 2])
            )
            penalty = (sigma_pred - pelgrom_target).pow(2).mean()
        return penalty

    # -------------------------------------------------------------------
    # Prediction
    # -------------------------------------------------------------------

    def predict(
        self, X_test: np.ndarray,
        batch_size: int = 1000,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Predict mu and sigma with uncertainty.

        Batched to avoid OOM from large joint covariance matrices.

        Returns:
            mu_mean, mu_std, sigma_mean, sigma_std: each (N,)
        """
        assert self.mu_gp is not None and self.sigma_gp is not None

        n = len(X_test)
        mu_mean = np.empty(n, dtype=np.float64)
        mu_std = np.empty(n, dtype=np.float64)
        sigma_mean = np.empty(n, dtype=np.float64)
        sigma_std = np.empty(n, dtype=np.float64)

        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            xt_batch = self._to_tensor(X_test[start:end])

            with torch.no_grad():
                mu_pred = self.mu_gp(xt_batch)
                sigma_pred = self.sigma_gp(xt_batch)

            mu_mean[start:end] = mu_pred.mean.cpu().numpy()
            mu_std[start:end] = mu_pred.stddev.cpu().numpy()
            sigma_mean[start:end] = sigma_pred.mean.cpu().numpy()
            sigma_std[start:end] = sigma_pred.stddev.cpu().numpy()

        return mu_mean, mu_std, sigma_mean, sigma_std

    # -------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------

    def _format_lengthscales(self, gp, name: str) -> str:
        """Format lengthscale string for display."""
        if name == "sigma" and isinstance(gp, AdditiveGPModel):
            ls_vop = gp.covar_module.kernels[0].base_kernel.lengthscale.detach()
            ls_cnpu = gp.covar_module.kernels[1].base_kernel.lengthscale.detach()
            return (f"Vop={ls_vop.item():.3f}, "
                    f"cn={ls_cnpu[0,0].item():.3f}, pu={ls_cnpu[0,1].item():.3f}")
        else:
            ls = gp.covar_module.base_kernel.lengthscale.detach().cpu().numpy().flatten()
            return f"[cn={ls[0]:.3f}, pu={ls[1]:.3f}, Vop={ls[2]:.3f}]"

    def get_lengthscales(self, model: str = "mu") -> np.ndarray:
        """Return ARD lengthscales. Shape depends on GP type."""
        if model == "mu":
            assert self.mu_gp is not None
            return self.mu_gp.covar_module.base_kernel.lengthscale.detach().cpu().numpy().flatten()
        else:
            assert self.sigma_gp is not None
            gp = self.sigma_gp
            ls_vop = gp.covar_module.kernels[0].base_kernel.lengthscale.detach().cpu().numpy().flatten()
            ls_cnpu = gp.covar_module.kernels[1].base_kernel.lengthscale.detach().cpu().numpy().flatten()
            return np.concatenate([ls_vop, ls_cnpu])
