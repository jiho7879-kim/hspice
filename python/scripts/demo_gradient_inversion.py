"""
Gradient-based inverse Vmin estimation (plan sec 4.1).

Demonstrates the *differentiable* claim of the physics layer: instead of a
grid + bisection search, back-propagate through the GP posterior mean and
the Vmin transform to optimise the design variables directly with Adam.

Scenario (multi-parameter, so gradient genuinely beats grid search --
review B2): 3 free variables x = (common_N, PU, WLUD).  We seek, from many
starts, the minimum-assist design on the Vmin = target manifold:

    minimise   (Vmin(x) - target)^2          # hit the target Vmin
             + w_assist * (1 - WLUD)^2        # prefer least wordline assist
             + barrier(x)                     # push out of the censored floor

A 3-D grid scan would cost O(K^3); the gradient walk touches O(iters) points
per start.  We cross-check each converged design against a 1-D bisection on
WLUD at its own (cn, pu) slice (review: gradient vs bisection WLUD < 0.005).

Usage:
    python scripts/demo_gradient_inversion.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils import (
    VOPS, N_VOP, VOP_COL, WLUD_COL, Z_FIXED,
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
    WLUD_FACTORS, N_WLUD,
)
from src.data import build_dataset, stratified_train_test_split
from src.surrogate import Surrogate
from src.physics import analytic_snmr
from src.physics_layer import estimate_required_assist, compute_vmin_from_z

OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "gradient_inversion"

TARGET_VMIN = 0.60
WLUD_LO = 0.90
N_COND = 50


# ---------------------------------------------------------------------------
# Differentiable Vmin: x_free (cn, pu, WLUD) -> Vmin, all in torch
# ---------------------------------------------------------------------------

class DifferentiableVmin:
    """Wrap a trained Surrogate as a differentiable x -> Vmin map.

    Uses the eval-mode posterior mean (prediction_strategy=None so the
    Cholesky is rebuilt with current params and gradients flow to the
    inputs -- same trick as the L_mono penalty).  The StandardScaler is
    replayed in torch so gradients reach the raw design variables.
    Vmin is a soft z-crossing interpolation (differentiable within a
    Vop segment; piecewise across segments -- see plan sec 4.1).
    """

    def __init__(self, surr: Surrogate, device: str = "cpu") -> None:
        self.surr = surr
        self.device = device
        surr.mu_gp.eval(); surr.mu_gp.likelihood.eval()
        surr.sigma_gp.eval(); surr.sigma_gp.likelihood.eval()
        surr.mu_gp.prediction_strategy = None
        surr.sigma_gp.prediction_strategy = None
        self.mean_ = torch.tensor(surr._x_scaler.mean_, dtype=torch.float32, device=device)
        self.std_ = torch.tensor(surr._x_scaler.std_, dtype=torch.float32, device=device)
        self.vops = torch.tensor(VOPS, dtype=torch.float32, device=device)

    def _design_to_X(self, cn: torch.Tensor, pu: torch.Tensor,
                     wlud: torch.Tensor) -> torch.Tensor:
        """(scalars) -> (N_VOP, 4) raw design matrix over the Vop sweep."""
        nv = N_VOP
        X = torch.stack([
            cn.expand(nv), pu.expand(nv), self.vops, wlud.expand(nv),
        ], dim=1)
        return X

    def vmin(self, cn: torch.Tensor, pu: torch.Tensor, wlud: torch.Tensor):
        """Return (Vmin, z_curve).  z_curve used for the censored barrier."""
        X = self._design_to_X(cn, pu, wlud)
        Xs = (X - self.mean_) / self.std_
        mu = self.surr.mu_gp(Xs).mean
        sg = self.surr.sigma_gp(Xs).mean
        z = mu / (sg + 1e-9)                       # (N_VOP,)

        # soft z-crossing interpolation of Vmin at z == Z_FIXED
        zt = Z_FIXED
        # linear interpolation weight in each adjacent Vop pair
        z0, z1 = z[:-1], z[1:]
        v0, v1 = self.vops[:-1], self.vops[1:]
        # segment that brackets the crossing (z0 <= zt <= z1)
        brackets = ((z0 <= zt) & (z1 >= zt)).float()
        t = (zt - z0) / (z1 - z0 + 1e-9)
        v_cross = v0 + t * (v1 - v0)
        # pick the lowest-Vop bracket via a soft argmax over bracket flags
        # (weights favour the first bracket; here brackets is 0/1, one-hot
        # in the monotone case)
        w = brackets / (brackets.sum() + 1e-9)
        vmin = (w * v_cross).sum()
        # if no bracket (all z above/below target), fall back to nearest end
        no_bracket = (brackets.sum() < 0.5)
        vmin = torch.where(no_bracket,
                           torch.where(z[0] > zt, self.vops[0] - 0.05, self.vops[-1]),
                           vmin)
        return vmin, z


def invert(dv: DifferentiableVmin, start, target=TARGET_VMIN,
           w_assist=0.02, n_iter=300, lr=0.05):
    """Adam inversion from a start design.  Returns dict with trajectory."""
    dev = dv.device
    # sigmoid box reparam: theta in R -> design in [lo, hi]
    lo = torch.tensor([COMMON_N_MIN, PU_MIN, WLUD_LO], dtype=torch.float32, device=dev)
    hi = torch.tensor([COMMON_N_MAX, PU_MAX, 1.0], dtype=torch.float32, device=dev)
    x0 = torch.tensor(start, dtype=torch.float32, device=dev)
    theta = torch.logit(((x0 - lo) / (hi - lo)).clamp(1e-4, 1 - 1e-4))
    theta = theta.clone().requires_grad_(True)

    opt = torch.optim.Adam([theta], lr=lr)
    traj = []
    for _ in range(n_iter):
        opt.zero_grad()
        design = lo + (hi - lo) * torch.sigmoid(theta)
        cn, pu, wlud = design[0], design[1], design[2]
        vmin, z = dv.vmin(cn, pu, wlud)

        loss_target = (vmin - target) ** 2
        loss_assist = w_assist * (1.0 - wlud) ** 2
        # Feasibility barriers (review C8) keep gradients alive where the
        # Vmin transform is flat (z never crosses the target within the Vop
        # sweep, so vmin() returns a constant):
        #   - z[0] > Z: whole curve above target -> Vmin pinned to the floor,
        #     push z(Vop_min) down to re-enter the interpolable band.
        #   - max(z) < Z: whole curve below target (read-fail corner) -> push
        #     z up, which drives WLUD toward stronger assist (lower WLUD).
        barrier_floor = torch.relu(z[0] - Z_FIXED) ** 2 * 0.01
        barrier_fail = torch.relu(Z_FIXED - z.max()) ** 2 * 0.05
        loss = loss_target + loss_assist + barrier_floor + barrier_fail
        loss.backward()
        opt.step()
        with torch.no_grad():
            traj.append([cn.item(), pu.item(), wlud.item(), vmin.item()])

    traj = np.array(traj)
    final = traj[-1]
    return {
        "cn": final[0], "pu": final[1], "wlud": final[2], "vmin": final[3],
        "trajectory": traj,
    }


# ---------------------------------------------------------------------------
# Bisection cross-check (1-D WLUD at a fixed cn, pu slice)
# ---------------------------------------------------------------------------

def bisection_wlud(surr, cn, pu, target=TARGET_VMIN):
    """Required WLUD at fixed (cn, pu) via the existing grid/bisection path.

    Returns NaN if infeasible / no assist needed within [WLUD_LO, 1]."""
    def surr_fn(x):
        mu, _, sg, _ = surr.predict(x)
        return mu, sg
    # single-point grid: reuse estimate_required_assist by embedding (cn,pu)
    # in a tiny 2x2 grid whose corners collapse to the same point
    CN, PU, wlud_req, _ = estimate_required_assist(
        surr_fn, target_vmin=target, n_grid=2,
        common_n_range=(cn, cn), pu_range=(pu, pu),
        wlud_lo=WLUD_LO, n_wlud_eval=25,
    )
    return float(wlud_req[0, 0])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("Gradient-based inverse Vmin estimation")
    print("=" * 60)

    # 1. Train a 4D surrogate (same analytic data as demo_assist)
    rng = np.random.default_rng(42)
    X_cnpu = build_dataset(N_COND)
    n_base = len(X_cnpu)
    X = np.zeros((n_base * N_WLUD, 4))
    y = np.zeros((n_base * N_WLUD, 2))
    for i in range(N_WLUD):
        wlud = WLUD_FACTORS[i]
        s, e = i * n_base, (i + 1) * n_base
        X[s:e, :3] = X_cnpu
        X[s:e, WLUD_COL] = wlud
        for j in range(n_base):
            cn, pu, vop = X_cnpu[j]
            mu, sg = analytic_snmr(cn, pu, vop, vwl_v=vop * wlud)
            y[s + j] = [mu + rng.normal(0, 0.002), sg + rng.normal(0, 0.0005)]
    X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.15)
    surr = Surrogate(device="cpu")
    surr.fit(X_tr, y_tr, n_iter=120, verbose=False)
    mu_p, _, sg_p, _ = surr.predict(X_te)
    print(f"  4D surrogate: mu RMSE={np.sqrt(np.mean((mu_p-y_te[:,0])**2)):.5f}")

    dv = DifferentiableVmin(surr)

    # 2. Gradient inversion from several starts across the (cn, pu) plane
    starts = [
        (-40.0, 40.0, 0.98), (40.0, -40.0, 0.98), (0.0, 0.0, 0.98),
        (-20.0, 20.0, 0.95), (20.0, 20.0, 0.99), (-40.0, -20.0, 0.97),
        (30.0, 10.0, 0.98), (-10.0, 45.0, 0.96),
    ]
    print(f"\n  Inverting from {len(starts)} starts (target Vmin={TARGET_VMIN}V)...")
    results, cross, feas_err = [], [], []
    for st in starts:
        r = invert(dv, st)
        # gradient result Vmin against the ANALYTIC truth (not the surrogate)
        z_true = np.array([
            analytic_snmr(r["cn"], r["pu"], v, vwl_v=v * r["wlud"])[0] /
            analytic_snmr(r["cn"], r["pu"], v, vwl_v=v * r["wlud"])[1]
            for v in VOPS
        ])
        vmin_true = float(compute_vmin_from_z(z_true.reshape(1, -1))[0])
        # bisection cross-check at the SAME (cn, pu) the gradient converged to
        wlud_bis = bisection_wlud(surr, r["cn"], r["pu"])
        # feasible = target reachable within [WLUD_LO, 1] at this (cn, pu);
        # bisection returns a finite WLUD only when it is
        feasible = not np.isnan(wlud_bis)
        # gradient at the assist limit => it correctly gave up (drove WLUD low)
        at_limit = r["wlud"] <= WLUD_LO + 0.01
        r.update(vmin_true=vmin_true, wlud_bisection=wlud_bis, feasible=feasible)
        results.append(r)

        tag = "feasible " if feasible else "INFEASIBLE"
        line = (f"    [{tag}] start=({st[0]:+5.0f},{st[1]:+5.0f}) -> "
                f"cn={r['cn']:+6.1f} pu={r['pu']:+6.1f} WLUD={r['wlud']:.4f}")
        if feasible:
            d = abs(r["wlud"] - wlud_bis)
            cross.append(d)
            feas_err.append(abs(vmin_true - TARGET_VMIN))
            line += (f"  Vmin_true={vmin_true:.4f}  |WLUD-bisect|={d:.4f}")
        else:
            line += f"  Vmin_true={'nan (read-fail)' if np.isnan(vmin_true) else f'{vmin_true:.3f}'}"
            line += f"  {'-> hit assist limit (correct)' if at_limit else '-> NOT at limit (check)'}"
        print(line)

    # 3. Accuracy summary (on feasible starts only)
    n_feas = sum(r["feasible"] for r in results)
    n_infeas = len(results) - n_feas
    feas_err = np.array(feas_err)
    cross = np.array(cross)
    print(f"\n  Feasible starts: {n_feas}/{len(results)}  "
          f"(infeasible worst-corner starts: {n_infeas})")
    print(f"  Gradient |Vmin_true - target| (feasible): "
          f"mean={feas_err.mean()*1e3:.2f}mV  max={feas_err.max()*1e3:.2f}mV")
    print(f"  Gradient vs bisection WLUD (feasible): "
          f"mean={cross.mean():.4f} max={cross.max():.4f} "
          f"({'PASS' if cross.max() < 0.005 else 'CHECK'} < 0.005)")
    # infeasible starts must all have driven WLUD to the assist limit
    infeas_ok = all(r["wlud"] <= WLUD_LO + 0.01
                    for r in results if not r["feasible"])
    print(f"  Infeasible starts drove WLUD to assist limit: "
          f"{'YES (correct)' if infeas_ok else 'NO (barrier failed)'}")

    # 4. Plot convergence trajectories over the Vmin(no-assist) surface
    _plot(surr, results)

    # 5. Go/No-Go: accuracy on feasible starts + bisection agreement +
    #    correct infeasibility handling on worst-corner starts
    ok = (feas_err.max() < 0.015 and cross.max() < 0.005 and infeas_ok)
    with open(OUT_DIR / "go_decision.txt", "w") as f:
        f.write("GO\n" if ok else "NO-GO\n")
        f.write(f"n_feasible={n_feas}/{len(results)}\n")
        f.write(f"feasible_vmin_max_err_mV={feas_err.max()*1e3:.2f}\n")
        f.write(f"wlud_vs_bisection_max={cross.max():.4f}\n")
        f.write(f"infeasible_handled={infeas_ok}\n")
    print(f"\n  >>> {'GO' if ok else 'NO-GO'} <<<")
    print("=== done ===")


def _plot(surr, results) -> None:
    # background: Vmin at WLUD=1.0 (no assist) over (cn, pu)
    n = 60
    cna = np.linspace(COMMON_N_MIN, COMMON_N_MAX, n)
    pua = np.linspace(PU_MIN, PU_MAX, n)
    CN, PU = np.meshgrid(cna, pua, indexing="xy")
    X = np.zeros((n * n * N_VOP, 4))
    idx = 0
    for i in range(n):
        for j in range(n):
            for v in VOPS:
                X[idx] = [CN[i, j], PU[i, j], v, 1.0]
                idx += 1
    mu, _, sg, _ = surr.predict(X)
    z = (mu / (sg + 1e-12)).reshape(n * n, N_VOP)
    vmin = compute_vmin_from_z(z, z_target=Z_FIXED).reshape(n, n)

    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    cf = ax.contourf(CN, PU, vmin, levels=20, cmap="viridis", alpha=0.75)
    fig.colorbar(cf, ax=ax, label="Vmin at WLUD=1.0 (V)")
    cs = ax.contour(CN, PU, vmin, levels=[TARGET_VMIN], colors="white",
                    linewidths=2, linestyles="--")
    ax.clabel(cs, fmt=f"Vmin={TARGET_VMIN}V", fontsize=9)

    for r in results:
        tr = r["trajectory"]
        ax.plot(tr[:, 0], tr[:, 1], "-", color="orange", lw=1.0, alpha=0.8)
        ax.plot(tr[0, 0], tr[0, 1], "o", color="black", ms=5)
        ax.plot(r["cn"], r["pu"], "*", color="red", ms=13)
    ax.plot([], [], "o", color="black", label="start")
    ax.plot([], [], "*", color="red", label="converged design")
    ax.set_xlabel("common_N (mV)")
    ax.set_ylabel("PU (mV)")
    ax.set_title("Gradient inversion trajectories\n"
                 "(min-assist designs on the Vmin=0.6V manifold)")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.15)
    fig.savefig(OUT_DIR / "inversion_trajectories.png", dpi=150, bbox_inches="tight")
    print(f"  Saved: {OUT_DIR / 'inversion_trajectories.png'}")
    plt.close(fig)


if __name__ == "__main__":
    main()
