"""
Result #3 (paper spine): INVERSE ESTIMATION with the clean surrogate.
=====================================================================
(a) Design boundary: extract the iso-Vmin = SPEC contour in the primary
    (cn, pu) Vth plane (other 7 knobs at nominal). This is the inverse answer:
    "which designs meet the Vmin spec?"
(b) Validation: on the held-out conditions (never seen in training), does the
    surrogate's Vmin classify pass/fail at the spec as the MEASURED data does?
    Reports the confusion matrix + agreement -- the credibility of the inverse.

Z target = 128 Mb @ 99% = 6.398 ; spec = T0 0.625 V.
Uses results/final_snmr_clean/surrogate_clean.pth (from forward_model_clean.py).
"""
import sys
from pathlib import Path

import numpy as np
from scipy.stats import norm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.final_data import load_final_snmr
from src.surrogate import Surrogate
from src.data import grouped_train_test_split
from src.physics_layer import compute_vmin_from_z

DEV = ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]
ND = len(DEV)
Z = float(norm.isf(-np.log(0.99) / 128e6))     # 6.398
SPEC = 0.625
NOMINAL = dict(sk=0.0, lpu=1.0, l_com=1.0, l_sk=0.0, mpu=1.0, m_com=1.0, m_sk=0.0)
OUT = ROOT / "results" / "final_snmr_clean"

# ---- reload clean data + reconstruct the exact train split to load the GP ----
df = load_final_snmr()
df = df[df["snmr_avg"].notna() & df["snmr_std"].notna() & df["n_mc"].notna()].copy()
X = df[DEV + ["vop"]].to_numpy(float)
y = df[["snmr_avg", "snmr_std"]].to_numpy(float) * 1e-3
_, cond_idx = np.unique(X[:, :ND], axis=0, return_inverse=True)
X_tr, X_te, y_tr, y_te = grouped_train_test_split(X, y, groups=cond_idx, test_frac=0.15, seed=42)
surr = Surrogate.load(OUT / "surrogate_clean.pth", X_tr, y_tr, device="cpu", n_device=ND)

VOPS = np.array(sorted(df["vop"].unique()))
NV = len(VOPS)


def vmin_of(Xrows):
    """Vmin for a set of conditions given as (n_cond, ND) design rows."""
    n = Xrows.shape[0]
    Xfull = np.zeros((n * NV, ND + 1))
    for k in range(n):
        Xfull_slice = slice(k * NV, (k + 1) * NV)
        Xfull[Xfull_slice, :ND] = Xrows[k]
        Xfull[Xfull_slice, ND] = VOPS
    mu, _, sig, _ = surr.predict(Xfull)
    z = (mu / (sig + 1e-12)).reshape(n, NV)
    return compute_vmin_from_z(z, z_target=Z, vops=VOPS, return_censored=True)


# ============================ (b) VALIDATION ============================
# measured Vmin per hold-out condition vs surrogate Vmin
te_dev, te_gi = np.unique(X_te[:, :ND], axis=0, return_inverse=True)
vt, ct = [], []
for gid in range(len(te_dev)):
    m = te_gi == gid
    o = np.argsort(X_te[m, ND]); vg = X_te[m, ND][o]
    z = y_te[m, 0][o] / (y_te[m, 1][o] + 1e-12)
    v, c = compute_vmin_from_z(z.reshape(1, -1), z_target=Z, vops=vg, return_censored=True)
    vt.append(v[0]); ct.append(bool(c[0]))
vt, ct = np.array(vt), np.array(ct)
vp, cp = vmin_of(te_dev)

# spec pass = Vmin <= SPEC (censored -> Vmin<0.4 -> pass). fail-to-cross -> NaN -> fail
pass_meas = np.where(np.isnan(vt), False, vt <= SPEC)
pass_pred = np.where(np.isnan(vp), False, vp <= SPEC)
tp = int((pass_meas & pass_pred).sum()); tn = int((~pass_meas & ~pass_pred).sum())
fp = int((~pass_meas & pass_pred).sum()); fn = int((pass_meas & ~pass_pred).sum())
agree = (tp + tn) / len(pass_meas)
sc = ~ct & ~cp & ~np.isnan(vt) & ~np.isnan(vp)
vmin_rmse = float(np.sqrt(np.mean((vp[sc] - vt[sc]) ** 2)) * 1e3)

print(f"=== (b) inverse validation on {len(te_dev)} hold-out conditions (Z={Z:.3f}, spec {SPEC}V) ===")
print(f"  Vmin RMSE (scored {sc.sum()}): {vmin_rmse:.2f} mV")
print(f"  spec pass/fail agreement: {tp+tn}/{len(pass_meas)} = {100*agree:.1f}%")
print(f"  confusion: TP={tp} TN={tn} FP={fp} FN={fn}")

# ============================ (a) DESIGN CONTOUR ========================
NG = 90
cn_ax = np.linspace(-60, 60, NG); pu_ax = np.linspace(-60, 60, NG)
CN, PU = np.meshgrid(cn_ax, pu_ax)
grid = np.zeros((NG * NG, ND))
for j, name in enumerate(DEV):
    if name == "cn": grid[:, j] = CN.ravel()
    elif name == "pu": grid[:, j] = PU.ravel()
    else: grid[:, j] = NOMINAL[name]
vg, cg = vmin_of(grid)
VM = vg.reshape(NG, NG)

fig, ax = plt.subplots(1, 2, figsize=(15, 6.2))
# left: Vmin contour map + spec iso-line + hold-out conditions near the slice
cf = ax[0].contourf(CN, PU, VM, levels=np.arange(0.40, 0.81, 0.05), cmap="viridis", extend="both")
plt.colorbar(cf, ax=ax[0], label="Vmin (V)")
cs = ax[0].contour(CN, PU, VM, levels=[SPEC], colors="crimson", linewidths=2.6)
ax[0].clabel(cs, fmt=f"spec {SPEC}V", fontsize=9)
# overlay hold-out conditions whose 7 other knobs are near nominal, colored by measured pass
near = np.ones(len(te_dev), bool)
for j, name in enumerate(DEV):
    if name in ("cn", "pu"):
        continue
    tol = 6.0 if name in ("sk",) else (0.10 if name.startswith(("l", "m")) and "sk" not in name else 0.025)
    near &= np.abs(te_dev[:, j] - NOMINAL[name]) <= tol
for lab, msk, mk in [("meas pass", near & pass_meas, "o"), ("meas fail", near & ~pass_meas, "x")]:
    ax[0].scatter(te_dev[msk, 0], te_dev[msk, 2], marker=mk, s=55,
                  edgecolor="k", facecolor=("white" if mk == "o" else "red"),
                  linewidths=1.1, label=f"{lab} (n={msk.sum()})", zorder=5)
ax[0].set_xlabel("cn = common-N Vth (mV)"); ax[0].set_ylabel("pu = PU Vth (mV)")
ax[0].set_title(f"(a) inverse design boundary: iso-Vmin={SPEC}V contour\n"
                f"(other 7 knobs at nominal; dots = near-slice hold-out conditions)")
ax[0].legend(loc="upper left", fontsize=8)

# right: predicted vs measured Vmin (validation scatter)
ax[1].scatter(vt[sc], vp[sc], s=22, alpha=0.6, edgecolor="none", color="#3477b5")
lim = [0.38, 0.82]
ax[1].plot(lim, lim, "k--", lw=1.2, label="ideal")
ax[1].axhline(SPEC, color="crimson", ls=":", lw=1); ax[1].axvline(SPEC, color="crimson", ls=":", lw=1)
ax[1].text(SPEC+0.005, 0.40, f"spec {SPEC}", color="crimson", fontsize=8, rotation=90)
ax[1].set_xlim(lim); ax[1].set_ylim(lim)
ax[1].set_xlabel("measured Vmin (V)"); ax[1].set_ylabel("surrogate Vmin (V)")
ax[1].set_title(f"(b) inverse validation on hold-out\n"
                f"Vmin RMSE={vmin_rmse:.1f}mV | spec agreement {100*agree:.1f}% "
                f"(FP={fp}, FN={fn})")
ax[1].legend(fontsize=8); ax[1].grid(alpha=0.25)
fig.suptitle(f"Result #3 — inverse Vmin estimation (clean surrogate, 128Mb@99% Z={Z:.3f})",
             fontsize=13, weight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.95])
out = OUT / "result3_inverse.png"
fig.savefig(out, dpi=140)
print(f"\nsaved: {out}")
