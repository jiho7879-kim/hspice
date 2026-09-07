"""§V-B sigma-model ablation  ->  results/sigma_model[_write].json  (N020a-N020d)

Why this script exists.  `src/surrogate.Surrogate` fits mu with a full 10-dim ARD
Matern (`ExactGPModel`) but sigma with an ADDITIVE kernel
(`AdditiveGPModel` = k_op(Vop) + k_dev(9 device axes)).  Additive means the model
cannot represent any interaction between the device coordinates and Vop -- it
assumes the sigma-vs-Vop curve has the same shape everywhere in the 9D window,
up to an offset.  That assumption is nearly harmless for read (sigma is close to
flat) and badly wrong for write, and it is the reason N013 reads 0.7318.

Second issue, independent of the kernel: sigma is fitted on a LINEAR scale, but
its own observation noise is sem_sigma = sigma/sqrt(2N) -- proportional, not
additive.  The scale on which that noise is homoscedastic is log sigma.

This script crosses the two changes (2x2) and scores each cell the same way
`v_b_forward.py` does, so the numbers are directly comparable to N012-N014.

    .venv/bin/python manuscript/code/v_b_sigma_model.py [--write]

NOTE: this is a measurement, not a change to the production model.  Adopting the
winning cell means editing `python/src/surrogate.py` and re-deriving EVERY
downstream result that loads `surrogate_vb*.pth` (§V-D corner, §V-E inverse,
§V-F lobe, §VI cost, §VII sensitivity).  That re-derivation is a separate job.
"""
import json
import sys
import time

import gpytorch
import numpy as np
import torch

import _paths  # noqa: F401
from _paths import DEVICE_COLS, RESULTS, Z_TARGET

from src.data import grouped_train_test_split
from src.final_data import Audit, load_final_snmr, load_final_vtrip
from src.models import AdditiveGPModel, ExactGPModel
from src.physics_layer import compute_vmin_from_z
from src.utils import StandardScaler

N_DEVICE = len(DEVICE_COLS)
VOP_COL = N_DEVICE
SEED = 42
N_ITER = 150

WRITE = "--write" in sys.argv
MODE, TEMP = ("write", "-40 C") if WRITE else ("read", "125 C")
AVG, STD = ("vtrip_avg", "vtrip_std") if WRITE else ("snmr_avg", "snmr_std")
TAG = "_write" if WRITE else ""

torch.manual_seed(SEED)

# --- same data path as v_b_forward.py, so the split is bit-identical -----------
audit = Audit()
df = (load_final_vtrip if WRITE else load_final_snmr)(audit)
df = df[df[AVG].notna() & df[STD].notna() & df["n_mc"].notna()].copy()
X = df[DEVICE_COLS + ["vop"]].to_numpy(float)
y = df[[AVG, STD]].to_numpy(float) * 1e-3                          # mV -> V
n_mc = np.clip(df["n_mc"].to_numpy(float), 2, None)
y_noise = np.column_stack([np.maximum(y[:, 1] / np.sqrt(n_mc), 1e-9),
                           np.maximum(y[:, 1] / np.sqrt(2 * n_mc), 1e-9)])
_, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
X_tr, X_te, y_tr, y_te = grouped_train_test_split(X, y, cond_idx, 0.15, SEED)
_, _, noise_tr, _ = grouped_train_test_split(X, y_noise, cond_idx, 0.15, SEED)
print(f"mode={MODE} ({TEMP})  train {len(X_tr)} / hold-out {len(X_te)} rows")

scaler = StandardScaler()
xt_tr = torch.tensor(scaler.fit_transform(X_tr), dtype=torch.float32)
xt_te = torch.tensor(scaler.transform(X_te), dtype=torch.float32)


def fit_gp(target, noise_std, kernel):
    """One GP, noise-aware, returns hold-out posterior mean."""
    yy = torch.tensor(target, dtype=torch.float32)
    lik = gpytorch.likelihoods.FixedNoiseGaussianLikelihood(
        noise=torch.tensor(noise_std ** 2, dtype=torch.float32),
        learn_additional_noise=True)
    gp = (ExactGPModel(xt_tr, yy, likelihood=lik) if kernel == "full"
          else AdditiveGPModel(xt_tr, yy, likelihood=lik, n_device=N_DEVICE))
    gp.train(); lik.train()
    opt = torch.optim.Adam(gp.parameters(), lr=0.1)
    mll = gpytorch.mlls.ExactMarginalLogLikelihood(lik, gp)
    for _ in range(N_ITER):
        opt.zero_grad()
        loss = -mll(gp(xt_tr), gp.train_targets)
        loss.backward()
        opt.step()
    gp.eval(); lik.eval()
    with torch.no_grad():
        return gp(xt_te).mean.numpy().astype(np.float64)


def rmse(e):
    return float(np.sqrt(np.mean(e ** 2)))


def r2(pred, true):
    return float(1 - np.sum((pred - true) ** 2) / np.sum((true - true.mean()) ** 2))


def vmins(mu, sig):
    """Per-condition Vmin through the physics layer, same as v_b_forward.py."""
    _, g = np.unique(X_te[:, :N_DEVICE], axis=0, return_inverse=True)
    v, cen = [], []
    for gid in np.unique(g):
        m = g == gid
        o = np.argsort(X_te[m, VOP_COL])
        vg = X_te[m, VOP_COL][o]
        z = (mu[m][o] / (sig[m][o] + 1e-12)).reshape(1, -1)
        a, c = compute_vmin_from_z(z, Z_TARGET, vops=vg, return_censored=True)
        v.append(a[0]); cen.append(bool(c[0]))
    return np.array(v), np.array(cen)


# mu is held FIXED across the four cells -- only the sigma model changes, so any
# difference in Vmin RMSE is attributable to sigma alone.
t0 = time.time()
mu_p = fit_gp(y_tr[:, 0], noise_tr[:, 0], "full")
print(f"mu (full ARD, unchanged from production) [{time.time()-t0:.0f}s]  "
      f"RMSE {rmse(mu_p - y_te[:, 0])*1e3:.3f} mV  R2 {r2(mu_p, y_te[:, 0]):.4f}")

vt, cen_t = vmins(y_te[:, 0], y_te[:, 1])          # reference Vmin from the data

VARIANTS = [("additive", False), ("full", False), ("additive", True), ("full", True)]
rows = []
for kernel, log_target in VARIANTS:
    t0 = time.time()
    if log_target:
        # delta method: sd(log s) = sd(s)/s  -- the scale where the MC noise is
        # homoscedastic, since sem_sigma is proportional to sigma
        sig_p = np.exp(fit_gp(np.log(y_tr[:, 1]), noise_tr[:, 1] / y_tr[:, 1], kernel))
    else:
        sig_p = fit_gp(y_tr[:, 1], noise_tr[:, 1], kernel)
    vp, _ = vmins(mu_p, sig_p)
    ok = ~cen_t & np.isfinite(vt) & np.isfinite(vp)
    rows.append(dict(
        sigma_kernel=kernel, sigma_target="log" if log_target else "linear",
        sigma_rmse_mV=rmse(sig_p - y_te[:, 1]) * 1e3,
        sigma_r2=r2(sig_p, y_te[:, 1]),
        vmin_rmse_mV=rmse((vp[ok] - vt[ok]) * 1e3),
        vmin_conditions_scored=int(ok.sum()),
        fit_seconds=round(time.time() - t0, 1)))
    r = rows[-1]
    print(f"  sigma[{kernel:>8}, {r['sigma_target']:>6}] "
          f"RMSE {r['sigma_rmse_mV']:.3f} mV  R2 {r['sigma_r2']:.4f}  |  "
          f"Vmin RMSE {r['vmin_rmse_mV']:.2f} mV ({r['vmin_conditions_scored']} cond)")

base = rows[0]                                     # additive + linear = production
best = min(rows, key=lambda r: r["vmin_rmse_mV"])
print(f"\nproduction (additive, linear) -> best ({best['sigma_kernel']}, "
      f"{best['sigma_target']}):  Vmin RMSE {base['vmin_rmse_mV']:.2f} -> "
      f"{best['vmin_rmse_mV']:.2f} mV,  sigma R2 {base['sigma_r2']:.4f} -> "
      f"{best['sigma_r2']:.4f}")

json.dump(dict(
    mode=MODE, temp=TEMP, z_target=Z_TARGET, seed=SEED, n_iter=N_ITER,
    n_train=len(X_tr), n_holdout=len(X_te),
    mu_rmse_mV=rmse(mu_p - y_te[:, 0]) * 1e3, mu_r2=r2(mu_p, y_te[:, 0]),
    variants=rows,
    production=dict(sigma_kernel="additive", sigma_target="linear"),
    best=dict(sigma_kernel=best["sigma_kernel"], sigma_target=best["sigma_target"]),
    qc_audit=audit.records,
), open(RESULTS / f"sigma_model{TAG}.json", "w"), indent=2, default=str)
print(f"saved {RESULTS}/sigma_model{TAG}.json")
