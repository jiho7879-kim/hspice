"""
Result #3 (polished design-boundary figure) + Result #4 (sensitivity) on the
clean surrogate. Z target = 128 Mb @ 99% = 6.398.

  #3a: clean iso-Vmin contour family in the (cn, pu) plane (other 7 knobs
       nominal) -- the inverse "design boundary", no sparse 2D overlay
       (validation is holistic in result3_inverse.py, 99.3% on hold-out).
  #4 : ARD lengthscales + GP-based Saltelli/Jansen Sobol (S1/ST) of Vmin over
       the 9 design dims + PG-PD skew tolerance.

Reuses results/final_snmr_clean/surrogate_clean.pth (85%-train clean model);
the (cn,pu) grid Vmin is cached to grid_vmin.npz for instant replotting.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import norm, qmc
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
VOPS = np.array([0.4, 0.5, 0.6, 0.7, 0.8])
LO = np.array([-60., -20., -60., 0.7, 0.7, -0.075, 0.7, 0.7, -0.075])
HI = np.array([60., 20., 60., 1.3, 1.3, 0.075, 1.3, 1.3, 0.075])
NOMINAL = dict(cn=-13.0, sk=0.0, pu=11.0, lpu=1.0, l_com=1.0, l_sk=0.0,
               mpu=1.0, m_com=1.0, m_sk=0.0)
OUT = ROOT / "results" / "final_snmr_clean"

# ---- load clean surrogate (reconstruct exact train split) ----
df = load_final_snmr()
df = df[df["snmr_avg"].notna() & df["snmr_std"].notna() & df["n_mc"].notna()].copy()
X = df[DEV + ["vop"]].to_numpy(float)
y = df[["snmr_avg", "snmr_std"]].to_numpy(float) * 1e-3
_, ci = np.unique(X[:, :ND], axis=0, return_inverse=True)
X_tr, _, y_tr, _ = grouped_train_test_split(X, y, groups=ci, test_frac=0.15, seed=42)
surr = Surrogate.load(OUT / "surrogate_clean.pth", X_tr, y_tr, device="cpu", n_device=ND)


def vmin_of(M, batch=4000, clip_floor=None, clip_ceil=None):
    M = np.atleast_2d(M); nv = len(VOPS)
    vv, cc = [], []
    for i in range(0, len(M), batch):
        blk = M[i:i+batch]; nb = len(blk)
        Xp = np.column_stack([np.repeat(blk, nv, axis=0), np.tile(VOPS, nb)])
        mu, _, sg, _ = surr.predict(Xp)
        z = (mu / (sg + 1e-12)).reshape(nb, nv)
        v, c = compute_vmin_from_z(z, z_target=Z, vops=VOPS, return_censored=True)
        vv.append(v); cc.append(c)
    v = np.concatenate(vv); c = np.concatenate(cc)
    if clip_floor is not None:
        v = np.where(c, clip_floor, v); v = np.where(np.isnan(v), clip_ceil, v)
    return v

# ==================== #3a: design-boundary contour (cached) ====================
cache = OUT / "grid_vmin.npz"
NG = 120
cn_ax = np.linspace(-60, 60, NG); pu_ax = np.linspace(-60, 60, NG)
CN, PU = np.meshgrid(cn_ax, pu_ax)
if cache.exists():
    VM = np.load(cache)["VM"]
    print("loaded cached grid")
else:
    grid = np.tile([NOMINAL[k] for k in DEV], (NG*NG, 1))
    grid[:, 0] = CN.ravel(); grid[:, 2] = PU.ravel()
    VM = vmin_of(grid).reshape(NG, NG)
    np.savez(cache, VM=VM)
    print("computed + cached grid")

fig, ax = plt.subplots(figsize=(7.6, 6.4))
cf = ax.contourf(CN, PU, VM, levels=np.arange(0.40, 0.81, 0.025), cmap="viridis", extend="both")
plt.colorbar(cf, ax=ax, label="Vmin (V)")
iso = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
cs = ax.contour(CN, PU, VM, levels=iso, colors="k", linewidths=0.7, alpha=0.6)
ax.clabel(cs, fmt="%.2f", fontsize=7)
csp = ax.contour(CN, PU, VM, levels=[SPEC], colors="crimson", linewidths=2.8)
ax.clabel(csp, fmt=f"spec {SPEC}V", fontsize=9)
ax.plot(NOMINAL["cn"], NOMINAL["pu"], "*", color="white", ms=18, mec="k", mew=1.2)
ax.annotate("nominal", (NOMINAL["cn"], NOMINAL["pu"]), textcoords="offset points",
            xytext=(10, -4), fontsize=9, color="white", weight="bold")
ax.set_xlabel("cn = common-N Vth shift (mV)"); ax.set_ylabel("pu = PU Vth shift (mV)")
ax.set_title(f"Result #3a — inverse design boundary\niso-Vmin contours, "
             f"spec {SPEC}V (128Mb@99%, Z={Z:.3f})\n"
             "region below/right of red line meets spec")
fig.tight_layout(); fig.savefig(OUT / "result3a_design_boundary.png", dpi=140)
print("saved result3a_design_boundary.png")

# ==================== #4: ARD + Sobol + skew ====================
ls = surr.get_lengthscales("mu")
ard = {k: float(v) for k, v in zip(DEV + ["Vop"], ls)}

N = 1024
raw = qmc.Sobol(d=18, scramble=True, seed=7).random(N)
A = LO + (HI - LO) * raw[:, :9]; B = LO + (HI - LO) * raw[:, 9:]
fA = vmin_of(A, clip_floor=0.40, clip_ceil=0.75)
fB = vmin_of(B, clip_floor=0.40, clip_ceil=0.75)
varY = float(np.var(np.concatenate([fA, fB])))
S1, ST = {}, {}
for i, nm in enumerate(DEV):
    AB = A.copy(); AB[:, i] = B[:, i]
    fAB = vmin_of(AB, clip_floor=0.40, clip_ceil=0.75)
    S1[nm] = float(np.mean(fB * (fAB - fA)) / varY)
    ST[nm] = float(0.5 * np.mean((fA - fAB) ** 2) / varY)
print(f"Sobol done. Var[Vmin]={varY:.3e} (sd {np.sqrt(varY)*1e3:.1f}mV) sumS1={sum(S1.values()):.3f}")
rank = sorted(ST.items(), key=lambda kv: -kv[1])
print("ST rank: " + " > ".join(f"{k}({v:.3f})" for k, v in rank))

# skew tolerance
sk_grid = np.linspace(-20, 20, 41)
ops = {"TT (0,0)": (0, 0), "mild-FSG (-30,+30)": (-30, 30), "mild-SFG (+30,-30)": (30, -30)}
skew_rep = {}
for nm, (cn, pu) in ops.items():
    M = np.tile([NOMINAL[k] for k in DEV], (len(sk_grid), 1))
    M[:, 0] = cn; M[:, 1] = sk_grid; M[:, 2] = pu
    v = vmin_of(M)
    fin = np.isfinite(v)
    i0 = int(np.argmin(np.abs(sk_grid)))
    lo, hi = max(i0-4, 0), min(i0+4, len(sk_grid)-1)
    slope = float((v[hi]-v[lo])/(sk_grid[hi]-sk_grid[lo])) if fin[lo] and fin[hi] else np.nan
    skew_rep[nm] = dict(vmin_sk0_V=float(v[i0]),
                        swing_mV=float(np.nanmax(v)-np.nanmin(v))*1e3,
                        dVmin_dsk_mV_per_mV=slope*1e3)

json.dump(dict(z_target=Z, ard=ard, sobol_S1=S1, sobol_ST=ST, sobol_N=N,
               var_vmin_V2=varY, sum_S1=float(sum(S1.values())), skew=skew_rep),
          open(OUT / "result4_sensitivity.json", "w"), indent=2)

# figure: Sobol bars + ARD + skew
fig, ax = plt.subplots(1, 3, figsize=(17, 5))
order = [k for k, _ in rank]
x = np.arange(len(order)); w = 0.4
ax[0].bar(x - w/2, [S1[k] for k in order], w, label="S1 (first-order)", color="#3477b5")
ax[0].bar(x + w/2, [ST[k] for k in order], w, label="ST (total)", color="#d1495b")
ax[0].set_xticks(x); ax[0].set_xticklabels(order, rotation=45, ha="right")
ax[0].set_ylabel("Sobol index of Vmin"); ax[0].legend()
ax[0].set_title(f"(#4a) Sobol sensitivity of Vmin\nsum S1={sum(S1.values()):.2f} "
                f"(sd={np.sqrt(varY)*1e3:.0f}mV)")
ax[0].grid(axis="y", alpha=0.3)
# ARD (1/ell = sensitivity)
al = sorted(ard.items(), key=lambda kv: kv[1])
ax[1].barh([k for k, _ in al][::-1], [1/v for _, v in al][::-1], color="#2a9d8f")
ax[1].set_xlabel("1 / lengthscale  (larger = more sensitive)")
ax[1].set_title("(#4b) ARD sensitivity (GP mu)")
ax[1].grid(axis="x", alpha=0.3)
# skew
for nm, (cn, pu) in ops.items():
    M = np.tile([NOMINAL[k] for k in DEV], (len(sk_grid), 1))
    M[:, 0] = cn; M[:, 1] = sk_grid; M[:, 2] = pu
    v = vmin_of(M)
    ax[2].plot(sk_grid, v*1e3, lw=2, label=f"{nm.split()[0]} slope={skew_rep[nm]['dVmin_dsk_mV_per_mV']:+.1f}")
ax[2].axhline(SPEC*1e3, color="crimson", ls="--", label=f"spec {SPEC}V")
ax[2].set_xlabel("PG-PD skew sk (mV)"); ax[2].set_ylabel("Vmin (mV)")
ax[2].set_title("(#4c) PG-PD skew tolerance"); ax[2].legend(fontsize=8); ax[2].grid(alpha=0.3)
fig.suptitle(f"Result #4 — Vmin sensitivity (clean surrogate, 128Mb@99% Z={Z:.3f})",
             fontsize=13, weight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.95])
fig.savefig(OUT / "result4_sensitivity.png", dpi=140)
print("saved result4_sensitivity.png + result4_sensitivity.json")
