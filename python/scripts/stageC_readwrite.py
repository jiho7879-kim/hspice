"""
Stage C: read-write integrated Vmin (4D: cn, sk, pu, Vop).

Combines the Stage B SNMR read-margin surrogate with the new Vtrip write-margin
surrogate into a unified Vmin = smooth_max(Vmin_SNMR, Vmin_Vtrip), per
docs/plans/deck_scenarios.md sec 1.5 / revised_sim_plan_20260709.md sec 3.

  SNMR (read)  @125C  -> GP_SNMR  -> Vmin_SNMR  (worst corner FSG: cn-,pu+)
  Vtrip (write) @-40C -> GP_Vtrip -> Vmin_Vtrip (worst corner SFG: cn+,pu-)
  Vmin(p) = smooth_max(Vmin_SNMR, Vmin_Vtrip, alpha)   (alpha=2mV, <=2mV per
            revised_plan_review_20260709: alpha=10mV gave 6.93mV crossing bias)

Part 1 gates the Vtrip surrogate (mirror of the SNMR gate, with Vtrip's
opposite worst-corner / gradient signs). Part 2 builds the combined surface.

Data: 260713_stageB_snmr.xlsx, sheets stageB_snmr (read) + stageB_bwrm (write).
Usage:  cd python && python scripts/stageC_readwrite.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils import Z_FIXED, COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z
from src.contour import extract_contour
from src.hspice_io import parse_manual_xlsx

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "260713_stageB_snmr.xlsx"
OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "stageC_readwrite"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_VOPS = np.array([0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float64)
ALPHA = 0.002  # smooth_max softness (V)
CORNERS = {"FSG": (-60, 60), "SFG": (60, -60), "FFG": (-60, -60), "SSG": (60, 60)}
sk_col, pu_col, vop_col = 1, 2, 3

print("=" * 70)
print("Stage C: read-write integrated Vmin  (SNMR + Vtrip)")
print("=" * 70)


def load(sheet):
    d = parse_manual_xlsx(DATA_PATH, sheet_name=sheet)
    return d["X"], d["y"], len(d["qc_flags"])


def fit_all(X, y, n_iter=200):
    s = Surrogate(device="cpu")
    s.fit(X, y, verbose=False, n_iter=n_iter)
    return s


def vmin_curve(surr, cn, sk, pu, vops=DATA_VOPS):
    cn, sk, pu = np.atleast_1d(cn), np.atleast_1d(sk), np.atleast_1d(pu)
    n = len(cn)
    Xp = np.empty((n * len(vops), 4))
    for i in range(n):
        s = i * len(vops)
        Xp[s:s + len(vops), 0] = cn[i]
        Xp[s:s + len(vops), sk_col] = sk[i]
        Xp[s:s + len(vops), pu_col] = pu[i]
        Xp[s:s + len(vops), vop_col] = vops
    mu, _, sigma, _ = surr.predict(Xp)
    z = (mu / (sigma + 1e-12)).reshape(n, len(vops))
    v, cens = compute_vmin_from_z(z, z_target=Z_FIXED, vops=vops, return_censored=True)
    return v, cens


def cond_split(X, y, frac=0.15, seed=42):
    _, inv = np.unique(X[:, :vop_col], axis=0, return_inverse=True)
    ids = np.unique(inv); np.random.default_rng(seed).shuffle(ids)
    nt = max(1, int(len(ids) * frac)); test = set(ids[:nt].tolist())
    m = np.array([i in test for i in inv])
    return X[~m], X[m], y[~m], y[m], len(ids) - nt, nt


# ============================================================
# Load
# ============================================================
print("\n=== Load ===")
Xr, yr, qr = load("stageB_snmr")   # read / SNMR
Xw, yw, qw = load("stageB_bwrm")   # write / Vtrip
print(f"  SNMR : X{Xr.shape} mu[{yr[:,0].min():.4f},{yr[:,0].max():.4f}]V  QC={qr}")
print(f"  Vtrip: X{Xw.shape} mu[{yw[:,0].min():.4f},{yw[:,0].max():.4f}]V  QC={qw}")

# ============================================================
# PART 1 -- Vtrip surrogate gate (mirror SNMR gate, opposite corner/signs)
# ============================================================
print("\n" + "=" * 50)
print("PART 1: Vtrip write-margin surrogate gate")
print("=" * 50)
Xw_tr, Xw_te, yw_tr, yw_te, ntr, nte = cond_split(Xw, yw)
print(f"  split: train={ntr} hold-out={nte} conditions")
gw = fit_all(Xw_tr, yw_tr)
mu_p, _, sig_p, _ = gw.predict(Xw_te)
mu_rmse = float(np.sqrt(np.mean((mu_p - yw_te[:, 0]) ** 2)))
mu_r2 = float(1 - np.sum((mu_p - yw_te[:, 0]) ** 2) / np.sum((yw_te[:, 0] - yw_te[:, 0].mean()) ** 2))
sig_r2 = float(1 - np.sum((sig_p - yw_te[:, 1]) ** 2) / np.sum((yw_te[:, 1] - yw_te[:, 1].mean()) ** 2))
print(f"  hold-out Vtrip: mu RMSE={mu_rmse:.5f} R2={mu_r2:.4f}  sigma R2={sig_r2:.4f}")

ls = gw.get_lengthscales("mu")
print(f"  ell: cn={ls[0]:.3f} sk={ls[sk_col]:.3f} pu={ls[pu_col]:.3f} Vop={ls[vop_col]:.3f}")

# corners (Vtrip worst expected SFG = cn+,pu-)
uniqw = np.unique(Xw[:, :vop_col], axis=0)
cvmin = {}
for name, (c, p) in CORNERS.items():
    ideal = np.array([c, 0.0, p]); i = int(np.argmin(np.sum((uniqw - ideal) ** 2, axis=1)))
    cn_i, sk_i, pu_i = uniqw[i]
    v, cens = vmin_curve(gw, cn_i, sk_i, pu_i)
    cvmin[name] = None if (np.isnan(v[0]) or cens[0]) else float(v[0])
    tag = "CENSORED(<0.4)" if cens[0] else ("FAIL(>0.8)" if np.isnan(v[0]) else f"{v[0]:.3f}V")
    print(f"  {name}: nearest=({cn_i:+.0f},{sk_i:+.0f},{pu_i:+.0f}) Vmin_Vtrip={tag}")
fin = {k: v for k, v in cvmin.items() if v is not None}
sfg_worst = (("SFG" in fin and fin["SFG"] == max(fin.values())) if "SFG" in fin
             else (all(cvmin[k] is None or True for k in [])))  # placeholder
# SFG worst if SFG is censored-high (FAIL) while others finite, OR SFG max of finite
sfg_worst = None
if cvmin.get("SFG") is None and any(v is not None for k, v in cvmin.items() if k != "SFG"):
    sfg_worst = True  # SFG censored-high (>0.8) while others finite => worst
elif "SFG" in fin:
    sfg_worst = (fin["SFG"] == max(fin.values()))
print(f"  SFG worst-corner (Vtrip): {'PASS' if sfg_worst else ('N/A' if sfg_worst is None else 'FAIL')}")

# gradient (Vtrip worst SFG => expect dVmin/dcn>0, dVmin/dpu<0)
eps = 5.0
def gwrad(dcn, dsk, dpu):
    vp, cp = vmin_curve(gw, dcn, dsk, dpu); vm, cm = vmin_curve(gw, -dcn, -dsk, -dpu)
    if np.isnan(vp[0]) or np.isnan(vm[0]) or cp[0] or cm[0]:
        return float("nan")
    return (vp[0] - vm[0]) / (2 * eps)
gcn, gpu = gwrad(eps, 0, 0), gwrad(0, 0, eps)
print(f"  dVmin_Vtrip/dcn={gcn:+.5f} (expect >0)  dVmin_Vtrip/dpu={gpu:+.5f} (expect <0)")
grad_ok = (not np.isnan(gcn) and not np.isnan(gpu) and gcn > 0 and gpu < 0)

vtrip_go = (mu_r2 >= 0.95) and grad_ok and (sfg_worst is not False)
print(f"\n  Vtrip gate: mu_R2>=0.95 {'PASS' if mu_r2>=0.95 else 'FAIL'} | "
      f"grad {'PASS' if grad_ok else 'FAIL'} | SFG-worst {'PASS' if sfg_worst else 'SKIP'}")
print(f"  >>> Vtrip surrogate {'GO' if vtrip_go else 'NO-GO'} <<<")

# ============================================================
# PART 2 -- combined read-write Vmin surface
# ============================================================
print("\n" + "=" * 50)
print("PART 2: combined Vmin = smooth_max(Vmin_SNMR, Vmin_Vtrip)")
print("=" * 50)
print("  retrain both GPs on all data ...")
gR = fit_all(Xr, yr)   # SNMR all
gW = fit_all(Xw, yw)   # Vtrip all


def vmin_grid(surr, CN, PU, sk=0.0):
    ng = CN.shape[0]; nv = len(DATA_VOPS)
    Xg = np.empty((ng * ng * nv, 4))
    for i in range(ng):
        for j in range(ng):
            b = (i * ng + j) * nv
            Xg[b:b+nv, 0] = CN[i, j]; Xg[b:b+nv, sk_col] = sk
            Xg[b:b+nv, pu_col] = PU[i, j]; Xg[b:b+nv, vop_col] = DATA_VOPS
    mu, _, sig, _ = surr.predict(Xg)
    z = (mu / (sig + 1e-12)).reshape(ng * ng, nv)
    return compute_vmin_from_z(z, z_target=Z_FIXED, vops=DATA_VOPS).reshape(ng, ng)


def smooth_max(a, b, alpha=ALPHA):
    return np.maximum(a, b) + alpha * np.log1p(np.exp(-np.abs(a - b) / alpha))


ng = 60
CN, PU = np.meshgrid(np.linspace(COMMON_N_MIN, COMMON_N_MAX, ng),
                     np.linspace(PU_MIN, PU_MAX, ng), indexing="xy")
vR = vmin_grid(gR, CN, PU)
vW = vmin_grid(gW, CN, PU)
# clip censored/fail to [floor, ceil] for the max
FL, CE = 0.35, 0.85
vRc = np.clip(np.nan_to_num(vR, nan=CE), FL, CE)
vWc = np.clip(np.nan_to_num(vW, nan=CE), FL, CE)
vC = smooth_max(vRc, vWc)
# which metric binds where
read_binds = vRc >= vWc
print(f"  Vmin_SNMR  range [{vRc.min():.3f},{vRc.max():.3f}]V")
print(f"  Vmin_Vtrip range [{vWc.min():.3f},{vWc.max():.3f}]V")
print(f"  Vmin_comb  range [{vC.min():.3f},{vC.max():.3f}]V")
print(f"  read-limited cells: {100*read_binds.mean():.1f}%  write-limited: {100*(~read_binds).mean():.1f}%")

# combined worst-corner readout
for name, (c, p) in CORNERS.items():
    ii = np.argmin((CN - c) ** 2 + (PU - p) ** 2)
    r, w, cc = vRc.flat[ii], vWc.flat[ii], vC.flat[ii]
    lim = "READ" if r >= w else "WRITE"
    print(f"  corner {name} ({c:+d},{p:+d}): SNMR={r:.3f} Vtrip={w:.3f} comb={cc:.3f} [{lim}-limited]")

# plot 3-panel + combined contour
fig, ax = plt.subplots(1, 3, figsize=(18, 5.2))
for a, (grid, title) in zip(ax, [(vRc, "Vmin_SNMR (read)"), (vWc, "Vmin_Vtrip (write)"),
                                 (vC, "Vmin combined = smooth_max")]):
    cf = a.contourf(CN, PU, grid, levels=20, cmap="RdYlBu_r")
    fig.colorbar(cf, ax=a, label="Vmin (V)", pad=0.02)
    for name, (c, p) in CORNERS.items():
        a.plot(c, p, "D", ms=6, color="k", zorder=5)
        a.annotate(name, (c, p), xytext=(4, 4), textcoords="offset points", fontsize=8)
    a.set_xlabel("common_N (mV)"); a.set_ylabel("PU (mV)"); a.set_title(title)
tgt = 0.60
pc, pp = extract_contour(vC, CN, PU, contour_level=tgt)
if len(pc):
    ax[2].plot(pc, pp, "k-", lw=2, label=f"comb Vmin={tgt}V")
    ax[2].legend(fontsize=8)
fig.savefig(OUT_DIR / "stageC_combined_vmin.png", dpi=140, bbox_inches="tight")
plt.close(fig)
print(f"  saved: {OUT_DIR/'stageC_combined_vmin.png'}")

# read/write limiting-region map
fig, a = plt.subplots(figsize=(6.4, 5.6))
a.contourf(CN, PU, read_binds.astype(float), levels=[-0.5, 0.5, 1.5],
           colors=["#4a90d9", "#d96a4a"], alpha=0.6)
cs = a.contour(CN, PU, vC, levels=[0.5, 0.55, 0.6, 0.65, 0.7], colors="k", linewidths=0.8)
a.clabel(cs, inline=True, fontsize=7, fmt="%.2f")
for name, (c, p) in CORNERS.items():
    a.plot(c, p, "kD", ms=6); a.annotate(name, (c, p), xytext=(4, 4), textcoords="offset points", fontsize=8)
a.set_xlabel("common_N (mV)"); a.set_ylabel("PU (mV)")
a.set_title("Read-limited (blue) vs Write-limited (red) + combined Vmin")
fig.savefig(OUT_DIR / "stageC_limiting_region.png", dpi=140, bbox_inches="tight")
plt.close(fig)
print(f"  saved: {OUT_DIR/'stageC_limiting_region.png'}")

# summary
with open(OUT_DIR / "stageC_summary.txt", "w") as f:
    f.write("Stage C read-write integrated Vmin\n\n")
    f.write(f"Vtrip gate: mu_R2={mu_r2:.4f} grad(cn={gcn:+.5f},pu={gpu:+.5f}) "
            f"SFG_worst={sfg_worst} -> {'GO' if vtrip_go else 'NO-GO'}\n")
    f.write(f"Vtrip corners: " + " ".join(f"{k}={cvmin[k]}" for k in CORNERS) + "\n\n")
    f.write(f"combined Vmin range [{vC.min():.3f},{vC.max():.3f}]V; "
            f"read-limited {100*read_binds.mean():.1f}% write-limited {100*(~read_binds).mean():.1f}%\n")
    for name, (c, p) in CORNERS.items():
        ii = np.argmin((CN - c) ** 2 + (PU - p) ** 2)
        f.write(f"  {name}: SNMR={vRc.flat[ii]:.3f} Vtrip={vWc.flat[ii]:.3f} comb={vC.flat[ii]:.3f}\n")
print(f"  saved: {OUT_DIR/'stageC_summary.txt'}")
print("\n=== Stage C complete ===")
