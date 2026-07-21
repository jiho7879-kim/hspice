"""
Result #2 (paper spine = inverse estimation): FORWARD surrogate quality on the
CLEAN final SNMR data. Regenerated from the canonical QC loader (src/final_data)
so every number traces to the audited dataset. Z target = 128 Mb @ 99% = 6.398.

Methodology identical to final_snmr_seed2027_analysis.py section B
(noise-aware GP via MC standard error, condition-level grouped hold-out,
censoring-aware Vmin RMSE) -- only the data source (clean loader) and Z differ.
Outputs -> results/final_snmr_clean/ (does not touch committed artifacts).
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.final_data import load_final_snmr
from src.surrogate import Surrogate
from src.data import grouped_train_test_split
from src.physics_layer import compute_vmin_from_z

DEVICE_COLS = ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]
N_DEVICE = len(DEVICE_COLS)
VOP_COL = N_DEVICE
Z = float(norm.isf(-np.log(0.99) / 128e6))          # 6.398
OUT = ROOT / "results" / "final_snmr_clean"
OUT.mkdir(parents=True, exist_ok=True)

df = load_final_snmr()
df = df[df["snmr_avg"].notna() & df["snmr_std"].notna() & df["n_mc"].notna()].copy()
print(f"clean usable rows: {len(df)}  conditions: {df['deck_no'].nunique()}  Z_target={Z:.4f}")

X = df[DEVICE_COLS + ["vop"]].to_numpy(float)
y = df[["snmr_avg", "snmr_std"]].to_numpy(float) * 1e-3        # mV -> V
n_mc = np.clip(df["n_mc"].to_numpy(float), 2, None)
y_noise = np.column_stack([np.maximum(y[:, 1] / np.sqrt(n_mc), 1e-9),
                           np.maximum(y[:, 1] / np.sqrt(2 * n_mc), 1e-9)])

_, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
X_tr, X_te, y_tr, y_te = grouped_train_test_split(X, y, groups=cond_idx, test_frac=0.15, seed=42)
_, _, noise_tr, _ = grouped_train_test_split(X, y_noise, groups=cond_idx, test_frac=0.15, seed=42)
print(f"train rows={len(X_tr)}  hold-out rows={len(X_te)}  (noise-aware)")

surr = Surrogate(device="cpu", n_device=N_DEVICE)
surr.fit(X_tr, y_tr, y_noise=noise_tr, n_iter=150, verbose=True)

mu_p, _, sig_p, _ = surr.predict(X_te)
mu_rmse = float(np.sqrt(np.mean((mu_p - y_te[:, 0]) ** 2)))
sig_rmse = float(np.sqrt(np.mean((sig_p - y_te[:, 1]) ** 2)))
mu_r2 = float(1 - np.sum((mu_p - y_te[:, 0])**2) / np.sum((y_te[:, 0]-y_te[:, 0].mean())**2))
sig_r2 = float(1 - np.sum((sig_p - y_te[:, 1])**2) / np.sum((y_te[:, 1]-y_te[:, 1].mean())**2))
print(f"\nHold-out mu RMSE={mu_rmse*1e3:.3f}mV R2={mu_r2:.4f} | "
      f"sigma RMSE={sig_rmse*1e3:.3f}mV R2={sig_r2:.4f}")

ls = surr.get_lengthscales("mu")
labels = DEVICE_COLS + ["Vop"]
print("mu lengthscales:", {l: round(float(v), 3) for l, v in zip(labels, ls)})

# censoring-aware Vmin RMSE on hold-out conditions
vops_all = np.array(sorted(df["vop"].unique()))
_, te_group = np.unique(X_te[:, :N_DEVICE], axis=0, return_inverse=True)
vt, vp, ct = [], [], []
for gid in np.unique(te_group):
    m = te_group == gid
    o = np.argsort(X_te[m, VOP_COL]); vg = X_te[m, VOP_COL][o]
    zt = (y_te[m, 0][o] / (y_te[m, 1][o] + 1e-12))
    zp = (mu_p[m][o] / (sig_p[m][o] + 1e-12))
    a, ca = compute_vmin_from_z(zt.reshape(1, -1), z_target=Z, vops=vg, return_censored=True)
    b, _ = compute_vmin_from_z(zp.reshape(1, -1), z_target=Z, vops=vg, return_censored=True)
    vt.append(a[0]); vp.append(b[0]); ct.append(bool(ca[0]))
vt, vp, ct = np.array(vt), np.array(vp), np.array(ct)
sc = ~ct & ~np.isnan(vt) & ~np.isnan(vp)
vmin_rmse = float(np.sqrt(np.mean((vp[sc]-vt[sc])**2)) * 1e3)
print(f"Vmin RMSE (hold-out, {sc.sum()}/{len(vt)} scored): {vmin_rmse:.2f} mV")

metrics = dict(z_target=Z, n_rows=len(df), n_conditions=int(df["deck_no"].nunique()),
               n_train=len(X_tr), n_holdout=len(X_te),
               mu_rmse_mV=mu_rmse*1e3, mu_r2=mu_r2, sigma_rmse_mV=sig_rmse*1e3,
               sigma_r2=sig_r2, vmin_rmse_mV_holdout=vmin_rmse,
               ell_mu={l: float(v) for l, v in zip(labels, ls)})
json.dump(metrics, open(OUT / "forward_metrics.json", "w"), indent=2)
surr.save(OUT / "surrogate_clean.pth")
print(f"\nsaved: {OUT/'forward_metrics.json'}  and  surrogate_clean.pth")
