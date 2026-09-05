"""§V-B forward surrogate accuracy  ->  results/forward[_write].json  (N010-N018)

Re-derivation of python/scripts/forward_model_clean.py with the two things the
ledger was missing: the QC audit trail is recorded next to the numbers, and the
grouped-split assumption is asserted rather than assumed.

Read (SNMR @125 C) and write (Vtrip @-40 C) are separate batches at separate
temperatures -- each mode is characterised at its own worst-case temperature by
design -- so they get one model each, from this one script.

    .venv/bin/python manuscript/code/v_b_forward.py [--write] [--refit]
"""
import json
import sys

import numpy as np
import torch

import _paths  # noqa: F401
from _paths import DEVICE_COLS, RESULTS, Z_TARGET

from src.final_data import Audit, load_final_snmr, load_final_vtrip
from src.surrogate import Surrogate
from src.data import grouped_train_test_split
from src.physics_layer import compute_vmin_from_z

N_DEVICE = len(DEVICE_COLS)
VOP_COL = N_DEVICE
SEED = 42
MIRROR_FREE_COLS = ["sk", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]

WRITE = "--write" in sys.argv
MODE, TEMP = ("write", "-40 C") if WRITE else ("read", "125 C")
AVG, STD = ("vtrip_avg", "vtrip_std") if WRITE else ("snmr_avg", "snmr_std")
TAG = "_write" if WRITE else ""

torch.manual_seed(SEED)

audit = Audit()
df = (load_final_vtrip if WRITE else load_final_snmr)(audit)
n_raw = len(df)
df = df[df[AVG].notna() & df[STD].notna() & df["n_mc"].notna()].copy()
print(f"mode={MODE} ({TEMP})")
print(f"rows {len(df)}/{n_raw} usable  conditions {df['deck_no'].nunique()}  "
      f"Z_target={Z_TARGET:.4f}")
print(audit.report())

# Grouping: src.data.grouped_train_test_split exists because the seed=2026
# batches re-used one Sobol stream across quadrants (mirror twins share the 7
# non-(cn,pu) coordinates). seed2027 was generated per-quadrant, so condition
# grouping is already leakage-free -- assert it instead of trusting it.
one_vop = df[df["vop"] == df["vop"].min()]
assert one_vop.groupby(MIRROR_FREE_COLS).size().max() == 1, \
    "mirror twins present: group by gen_idx, not by condition"

X = df[DEVICE_COLS + ["vop"]].to_numpy(float)
y = df[[AVG, STD]].to_numpy(float) * 1e-3                        # mV -> V
n_mc = np.clip(df["n_mc"].to_numpy(float), 2, None)
y_noise = np.column_stack([np.maximum(y[:, 1] / np.sqrt(n_mc), 1e-9),
                           np.maximum(y[:, 1] / np.sqrt(2 * n_mc), 1e-9)])

_, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
X_tr, X_te, y_tr, y_te = grouped_train_test_split(X, y, cond_idx, 0.15, SEED)
_, _, noise_tr, _ = grouped_train_test_split(X, y_noise, cond_idx, 0.15, SEED)
print(f"train {len(X_tr)} rows / hold-out {len(X_te)} rows (noise-aware)")

CKPT = RESULTS / f"surrogate_vb{TAG}.pth"
if CKPT.exists() and "--refit" not in sys.argv:
    surr = Surrogate.load(CKPT, X_tr, y_tr, device="cpu", n_device=N_DEVICE)
else:
    surr = Surrogate(device="cpu", n_device=N_DEVICE)
    surr.fit(X_tr, y_tr, y_noise=noise_tr, n_iter=150, verbose=True)
    surr.save(CKPT)

mu_p, _, sig_p, _ = surr.predict(X_te)


def rmse_r2(pred, true):
    rmse = float(np.sqrt(np.mean((pred - true) ** 2)))
    r2 = float(1 - np.sum((pred - true) ** 2) / np.sum((true - true.mean()) ** 2))
    return rmse, r2


mu_rmse, mu_r2 = rmse_r2(mu_p, y_te[:, 0])
sig_rmse, sig_r2 = rmse_r2(sig_p, y_te[:, 1])
print(f"\nhold-out  mu {mu_rmse*1e3:.3f} mV R2 {mu_r2:.4f} | "
      f"sigma {sig_rmse*1e3:.3f} mV R2 {sig_r2:.4f}")

# Vmin RMSE per hold-out condition, censored conditions excluded from scoring
_, te_group = np.unique(X_te[:, :N_DEVICE], axis=0, return_inverse=True)
vt, vp, censored = [], [], []
for gid in np.unique(te_group):
    m = te_group == gid
    o = np.argsort(X_te[m, VOP_COL])
    vg = X_te[m, VOP_COL][o]
    zt = y_te[m, 0][o] / (y_te[m, 1][o] + 1e-12)
    zp = mu_p[m][o] / (sig_p[m][o] + 1e-12)
    a, ca = compute_vmin_from_z(zt.reshape(1, -1), Z_TARGET, vops=vg, return_censored=True)
    b, _ = compute_vmin_from_z(zp.reshape(1, -1), Z_TARGET, vops=vg, return_censored=True)
    vt.append(a[0]); vp.append(b[0]); censored.append(bool(ca[0]))
vt, vp, censored = np.array(vt), np.array(vp), np.array(censored)
scored = ~censored & ~np.isnan(vt) & ~np.isnan(vp)
err = (vp[scored] - vt[scored]) * 1e3
vmin_rmse = float(np.sqrt(np.mean(err ** 2)))
# the Vmin contour is the deliverable: report its whole error distribution,
# and separately the band where the T0 decision actually lives
band = scored & (vt <= 0.7)
err_band = (vp[band] - vt[band]) * 1e3
vmin_rmse_band = float(np.sqrt(np.mean(err_band ** 2)))
p50, p90, emax = (float(np.percentile(np.abs(err), 50)),
                  float(np.percentile(np.abs(err), 90)), float(np.abs(err).max()))
print(f"Vmin RMSE {vmin_rmse:.2f} mV  ({scored.sum()}/{len(vt)} conditions scored, "
      f"{censored.sum()} censored)")
print(f"  |err| P50 {p50:.2f} / P90 {p90:.2f} / max {emax:.2f} mV")
print(f"  band Vmin <= 0.7 V: RMSE {vmin_rmse_band:.2f} mV over {band.sum()} conditions")

labels = DEVICE_COLS + ["Vop"]
out = dict(
    mode=MODE, temp=TEMP, z_target=Z_TARGET, seed=SEED,
    n_rows_raw=n_raw, n_rows_used=len(df),
    n_conditions=int(df["deck_no"].nunique()),
    n_train=len(X_tr), n_holdout=len(X_te),                       # N015
    mu_rmse_mV=mu_rmse * 1e3, mu_r2=mu_r2,                        # N010 N011
    sigma_rmse_mV=sig_rmse * 1e3, sigma_r2=sig_r2,                # N012 N013
    vmin_rmse_mV_holdout=vmin_rmse,                               # N014
    vmin_abs_err_p50_mV=p50, vmin_abs_err_p90_mV=p90,             # N016
    vmin_abs_err_max_mV=emax,
    vmin_rmse_mV_band_0p7=vmin_rmse_band,                         # N017
    vmin_conditions_band_0p7=int(band.sum()),
    vmin_conditions_scored=int(scored.sum()),
    vmin_conditions_censored=int(censored.sum()),
    ell_mu={l: float(v) for l, v in zip(labels, surr.get_lengthscales("mu"))},
    qc_audit=audit.records,
)
json.dump(out, open(RESULTS / f"forward{TAG}.json", "w"), indent=2, default=str)
# per-condition Vmin pairs feed the contour figure and any later error slicing
np.savez(RESULTS / f"forward_vmin{TAG}.npz", vmin_true=vt, vmin_pred=vp, censored=censored)
print(f"\nsaved {RESULTS}/forward{TAG}.json + forward_vmin{TAG}.npz")
