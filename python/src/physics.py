"""
Physics-Constrained GP Surrogate — L_mono, L_boundary, L_pelgrom.

Extends the standard GP surrogate with physics-informed constraints:

    1. L_mono (Monotonicity):
       Vop up -> mu_SNMR up  (dmu/dVop > 0)
       Evaluated on probe points (PINN-style collocation).
       Penalty: ReLU(-dmu/dVop)^2

    2. L_boundary (Corner Anchor):
        4 global corners (FSG, SFG, FFG, SSG) x 6 Vop x 5 Vwl = 120 virtual obs (4D).
        True values from analytic model (or measured HSPICE in production).
        Augments training data — hard anchor, exact constraint.

    3. L_pelgrom (Sigma Scaling):
       sigma(Vop) = SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - Vop)
       Penalty: (sigma_pred - pelgrom_target)^2

    L_total = -log p(y|X,th) + lambda_mono * L_mono + lambda_pelgrom * L_pelgrom

Usage:
    surr = PhysicsConstrainedSurrogate(device="cpu")
    surr.fit(X_train, y_train, use_mono=True, use_boundary=True, ...)
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import torch
import gpytorch

from src.utils import (
    VOPS, VOP_COL, WLUD_COL, WLUD_FACTORS, N_WLUD,
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
)
from src.models import ExactGPModel, AdditiveGPModel

# ---------------------------------------------------------------------------
# Analytic model for corner anchor ground truth
# Must match demo/ablation scripts exactly
# ---------------------------------------------------------------------------
A_MU = 0.15
B_MU = +0.001
C_MU = -0.0015
D_MU = 0.0
E_MU = 0.25      # Vwl underdrive sensitivity: mu += E_MU * (Vop - Vwl)
SIGMA0 = 0.015
SIGMA_VOP_SLOPE = 0.004
SIGMA_VWL_SLOPE = 0.005  # sigma += SIGMA_VWL_SLOPE * (Vop - Vwl)


def analytic_snmr(
    cn_mv: float, pu_mv: float, vop_v: float,
    vwl_v: float | None = None,
) -> tuple[float, float]:
    """Analytic SNMR model used for corner anchor ground truth.

    3D (vwl_v=None): symmetric baseline model.
    4D (vwl_v given): Vwl underdrive adds mu boost via E_MU*(Vop - Vwl)
                       and slight sigma increase via SIGMA_VWL_SLOPE*(Vop - Vwl).
    """
    mu = A_MU * vop_v + B_MU * cn_mv + C_MU * pu_mv + D_MU
    sigma = SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - vop_v)
    if vwl_v is not None:
        wlud = vop_v - vwl_v  # positive when Vwl < Vop (assist active)
        mu += E_MU * wlud
        sigma += SIGMA_VWL_SLOPE * wlud
    return mu, sigma


# ---------------------------------------------------------------------------
# Probe points for monotonicity constraint
# ---------------------------------------------------------------------------

def generate_probe_points(n_per_dim: int = 8, n_extra: int = 0) -> np.ndarray:
    """Generate (N, 3 + n_extra) probe points for L_mono constraint.

    Core dims [common_N, PU, Vop] spread across full domain.
    When n_extra >= 1, WLUD ratio (Vwl/Vop) grid at index WLUD_COL.
    Extra dims beyond WLUD_COL filled with 0.0 (nominal after scaling).
    """
    cn = np.linspace(COMMON_N_MIN, COMMON_N_MAX, n_per_dim)
    pu = np.linspace(PU_MIN, PU_MAX, n_per_dim)
    vop = VOPS
    CN, PU_arr, VOP = np.meshgrid(cn, pu, vop, indexing="ij")
    probes = np.column_stack([CN.ravel(), PU_arr.ravel(), VOP.ravel()])

    if n_extra >= 1:
        n_wlud = min(n_per_dim, N_WLUD)
        wlud_levels = WLUD_FACTORS[:n_wlud]  # ratios, not absolute Vwl
        CN_e, PU_e, VOP_e, WLUD_e = np.meshgrid(
            cn, pu, vop, wlud_levels, indexing="ij",
        )
        probes_4d = np.column_stack([
            CN_e.ravel(), PU_e.ravel(), VOP_e.ravel(), WLUD_e.ravel(),
        ])
        if n_extra > 1:
            extra = np.zeros((len(probes_4d), n_extra - 1), dtype=np.float64)
            probes_4d = np.concatenate([probes_4d, extra], axis=1)
        return probes_4d.astype(np.float64)

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


def generate_corner_anchor_data(n_extra: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Generate virtual observations at global corners x Vop x WLUD.

    3D (n_extra=0): 4 corners x 6 Vop = 24 points, X = [cn, pu, Vop].
    4D (n_extra>=1): + WLUD ratio dimension across WLUD_FACTORS.
        Extra dims beyond WLUD_COL filled with 0.0 (nominal after scaling).
        Vwl for analytic_snmr computed as WLUD * Vop per point.

    Returns:
        X_corner: (24 or 120, 3 + n_extra) [common_N, PU, Vop, (WLUD, ...)]
        y_corner: (24 or 120, 2) [mu_SNMR, sigma_SNMR] from analytic model
    """
    n_wlud = N_WLUD if n_extra >= 1 else 1
    wlud_levels = WLUD_FACTORS if n_extra >= 1 else [0.0]
    n = len(GLOBAL_CORNERS_MV) * len(VOPS) * n_wlud
    X = np.zeros((n, 3 + n_extra), dtype=np.float64)
    y = np.zeros((n, 2), dtype=np.float64)
    idx = 0
    for cn, pu in GLOBAL_CORNERS_MV:
        for vop in VOPS:
            for wlud in wlud_levels:
                if n_extra >= 1:
                    X[idx] = [cn, pu, vop, wlud] + [0.0] * (n_extra - 1)
                else:
                    X[idx] = [cn, pu, vop]
                # Vwl = WLUD * Vop for each point
                vwl = wlud * vop if n_extra >= 1 else None
                mu, sigma = analytic_snmr(cn, pu, vop, vwl_v=vwl)
                y[idx] = [mu, sigma]
                idx += 1
    return X, y


# ---------------------------------------------------------------------------
# Physics-Constrained Surrogate
# ---------------------------------------------------------------------------

class PhysicsConstrainedSurrogate:
    """GP surrogate with optional physics-informed constraint terms.

    Parameters
    ----------
    device : str
        'cpu' or 'cuda'
    checkpoint_dir : str or None
        Directory for model checkpoint .pth files (None = no checkpointing).
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
        use_mono: bool = True,
        use_boundary: bool = True,
        use_pelgrom: bool = True,
        lambda_mono: float = 100.0,
        lambda_pelgrom: float = 1.0,
        n_probe: int = 6,
        ckpt_tag: str = "",
    ) -> None:
        """Train both mu and sigma GPs with optional physics constraints.

        Args:
            X_train: (N, d) training inputs [common_N, PU, Vop, ...]
            y_train: (N, 2) training targets [mu, sigma]
            n_iter: Number of training iterations.
            lr: Learning rate for Adam.
            use_mono: Apply L_mono (Vop up => mu up) constraint.
            use_boundary: Augment training data with corner anchors.
            use_pelgrom: Apply L_pelgrom (sigma scaling) constraint.
            lambda_mono: Weight for monotonicity penalty.
            lambda_pelgrom: Weight for Pelgrom scaling penalty.
            n_probe: Grid points per dimension for L_mono probes.
        """
        self._x_train = X_train.copy()
        self._use_mono = use_mono
        self._use_pelgrom = use_pelgrom
        n_extra = max(0, X_train.shape[1] - 3)

        # Data augmentation for corner anchors
        if use_boundary:
            X_corner, y_corner = generate_corner_anchor_data(n_extra=n_extra)
            X_aug = np.concatenate([X_train, X_corner], axis=0)
            y_aug = np.concatenate([y_train, y_corner], axis=0)
            n_aug = len(X_corner)
            if verbose:
                n_vop = len(VOPS)
                n_wlud = N_WLUD if n_extra >= 1 else 1
                print(f"  [boundary] Added {n_aug} corner anchor points "
                      f"(4 corners x {n_vop} Vop x {n_wlud} WLUD)")
        else:
            X_aug, y_aug = X_train, y_train

        # Pre-generate probe points for L_mono
        if use_mono:
            self._probe_points = generate_probe_points(n_per_dim=n_probe, n_extra=n_extra)
            n_pp = len(self._probe_points)
            if verbose:
                print(f"  [mono] {n_pp} probe points "
                      f"({n_probe}^3 x {n_probe} Vop{' x WLUD' if n_extra >= 1 else ''})")

        # Convert to tensors
        xt_aug = self._to_tensor(X_aug)
        yt_aug_mu = self._to_tensor(y_aug[:, 0])
        yt_aug_sigma = self._to_tensor(y_aug[:, 1])

        # Train mu GP
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

        # Train sigma GP
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
        """Train a single GP with optional physics penalty terms."""
        # Try loading checkpoint
        tag = f"{ckpt_tag}_{name}" if ckpt_tag else ""
        if tag:
            loaded = self._load_checkpoint(gp, tag)
            if loaded and verbose:
                print(f"  [{name}] Loaded checkpoint ({tag}) - skipping training")
                return

        gp.train()
        gp.likelihood.train()

        optimizer = torch.optim.Adam(gp.parameters(), lr=lr)
        mll = gpytorch.mlls.ExactMarginalLogLikelihood(gp.likelihood, gp)

        # Pre-tensorize probe points
        if apply_mono and self._probe_points is not None:
            probe_t = self._to_tensor(self._probe_points)
        else:
            probe_t = None

        # Constraint scheduling
        mono_warmup = 30
        mono_interval = 3

        data_losses, mono_losses, pelgrom_losses = [], [], []

        start = time.time()
        for i in range(n_iter):
            optimizer.zero_grad()

            output = gp(xt)
            data_loss = -mll(output, gp.train_targets)

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

        ls_str = self._format_lengthscales(gp, name)
        if verbose:
            print(f"  [{name}] done ({elapsed:.1f}s)  "
                  f"final: data={data_losses[-1]:.2f}, "
                  f"mono={mono_losses[-1]:.6f}, "
                  f"pelgrom={pelgrom_losses[-1]:.6f}")
            print(f"  [{name}] lengthscales={ls_str}")

        if tag:
            self._save_checkpoint(gp, tag)

    # -------------------------------------------------------------------
    # Physics penalty computations
    # -------------------------------------------------------------------

    def _compute_mono_penalty(
        self, gp: ExactGPModel | AdditiveGPModel,
        probe_t: torch.Tensor,
    ) -> torch.Tensor:
        """Compute L_mono = mean(ReLU(-dmu/dVop)^2).

        POSTERIOR mean gradient at probe points via eval-mode forward pass.
        """
        probe_grad = probe_t.clone().detach().requires_grad_(True)

        was_training = gp.training
        gp.eval()
        gp.prediction_strategy = None

        output = gp(probe_grad)
        mean = output.mean
        grad = torch.autograd.grad(mean.sum(), probe_grad, create_graph=True)[0]
        dmu_dvop = grad[:, VOP_COL]
        penalty = torch.relu(-dmu_dvop).pow(2).mean()

        if was_training:
            gp.train()
            gp.likelihood.train()

        return penalty

    def _compute_pelgrom_penalty(
        self, gp: AdditiveGPModel,
        xt: torch.Tensor,
    ) -> torch.Tensor:
        """Compute L_pelgrom = mean((sigma - pelgrom_target)^2)."""
        with torch.no_grad():
            output = gp(xt)
            sigma_pred = output.mean
            pelgrom_target = (
                SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - xt[:, VOP_COL])
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
        if name == "sigma" and isinstance(gp, AdditiveGPModel):
            ls_op = gp.covar_module.kernels[0].base_kernel.lengthscale.detach()
            ls_dev = gp.covar_module.kernels[1].base_kernel.lengthscale.detach()
            n_op = ls_op.shape[-1]
            n_dev = ls_dev.shape[-1]
            op_labels = (["Vop"] + [f"d{3 + i}" for i in range(n_op - 1)])[:n_op]
            dev_labels = (["cn", "pu"] + [f"d{2 + i}" for i in range(n_dev - 2)])[:n_dev]
            op_str = ", ".join(f"{l}={ls_op[0, i].item():.3f}" for i, l in enumerate(op_labels))
            dev_str = ", ".join(f"{l}={ls_dev[0, i].item():.3f}" for i, l in enumerate(dev_labels))
            return f"op=[{op_str}]  dev=[{dev_str}]"
        else:
            ls = gp.covar_module.base_kernel.lengthscale.detach().cpu().numpy().flatten()
            labels = ["cn", "pu", "Vop"] + [f"d{i}" for i in range(3, len(ls))]
            return ", ".join(f"{l}={v:.3f}" for l, v in zip(labels, ls))

    def get_lengthscales(self, model: str = "mu") -> np.ndarray:
        """Return ARD lengthscales. Shape depends on GP type."""
        if model == "mu":
            assert self.mu_gp is not None
            return self.mu_gp.covar_module.base_kernel.lengthscale.detach().cpu().numpy().flatten()
        else:
            assert self.sigma_gp is not None
            gp = self.sigma_gp
            ls_op = gp.covar_module.kernels[0].base_kernel.lengthscale.detach().cpu().numpy().flatten()
            ls_dev = gp.covar_module.kernels[1].base_kernel.lengthscale.detach().cpu().numpy().flatten()
            return np.concatenate([ls_op, ls_dev])
