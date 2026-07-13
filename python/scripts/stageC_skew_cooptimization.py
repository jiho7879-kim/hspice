"""
Stage C read-write skew co-optimization (SNMR + Vtrip, 4D cn/sk/pu/Vop).

Positive PG-PD skew (slower PG) HELPS read (less read disturb -> lower Vmin_SNMR)
but is expected to HURT write (weaker pass-gate -> higher Vmin_Vtrip). If so, the
worst-case array Vmin (max over process corners of the combined read-write Vmin)
has an interior-optimal skew. This script quantifies that trade-off:

  A. combined Vmin (+ read/write components) vs skew at the real PDK 3-sigma
     corners (FSG read-binding, SFG write-binding).
  B. worst-case array Vmin = max over the 4 real corners, vs a global skew ->
     optimal skew*.
  C. GP-based Sobol sensitivity of the COMBINED Vmin over (cn, sk, pu).

Real 3-sigma corner shifts (cn,pu), from stage4_real_data_gate.md sec 5.
Usage:  cd python && python scripts/stageC_skew_cooptimization.py
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
from src.hspice_io import parse_manual_xlsx

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "260713_stageB_snmr.xlsx"
OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "stageC_readwrite"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_VOPS = np.array([0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float64)
ALPHA = 0.002
FL, CE = 0.35, 0.85
SK_MIN, SK_MAX = -20.0, 20.0
sk_col, pu_col, vop_col = 1, 2, 3

# real PDK 3-sigma corners (cn, pu) mV
CORNERS = {"FSG": (-29, 39), "SFG": (32, -37), "FFG": (-36, -44), "SSG": (36, 45)}

print("=" * 68)
print("Stage C: read-write PG-PD skew co-optimization")
print("=" * 68)


def fit_all(sheet):
    d = parse_manual_xlsx(DATA_PATH, sheet_name=sheet)
    s = Surrogate(device="cpu")
    s.fit(d["X"], d["y"], verbose=False, n_iter=200)
    return s


print("\nTrain GP_SNMR (read) + GP_Vtrip (write) on all data ...")
gR = fit_all("stageB_snmr")
gW = fit_all("stageB_bwrm")
print("  done.")


def vmin_pts(surr, cn, sk, pu):
    """Clipped Vmin at arrays of (cn,sk,pu)."""
    cn, sk, pu = np.atleast_1d(cn).astype(float), np.atleast_1d(sk).astype(float), np.atleast_1d(pu).astype(float)
    n = len(cn); nv = len(DATA_VOPS)
    X = np.empty((n * nv, 4))
    for i in range(n):
        b = i * nv
        X[b:b+nv, 0] = cn[i]; X[b:b+nv, sk_col] = sk[i]
        X[b:b+nv, pu_col] = pu[i]; X[b:b+nv, vop_col] = DATA_VOPS
    mu, _, sig, _ = surr.predict(X)
    z = (mu / (sig + 1e-12)).reshape(n, nv)
    v, cens = compute_vmin_from_z(z, z_target=Z_FIXED, vops=DATA_VOPS, return_censored=True)
    v = np.where(cens, FL, v)
    v = np.where(np.isnan(v), CE, v)
    return np.clip(v, FL, CE)


def smooth_max(a, b, alpha=ALPHA):
    return np.maximum(a, b) + alpha * np.log1p(np.exp(-np.abs(a - b) / alpha))


def comb(cn, sk, pu):
    return smooth_max(vmin_pts(gR, cn, sk, pu), vmin_pts(gW, cn, sk, pu))


# ============================================================
# A. per-corner skew curves
# ============================================================
print("\n=== A. read/write/combined Vmin vs skew at real corners ===")
sk_grid = np.linspace(SK_MIN, SK_MAX, 41)
fig, axes = plt.subplots(1, 4, figsize=(19, 4.6), sharey=True)
cornerA = {}
for ax, (name, (c, p)) in zip(axes, CORNERS.items()):
    vR = vmin_pts(gR, np.full_like(sk_grid, c), sk_grid, np.full_like(sk_grid, p))
    vW = vmin_pts(gW, np.full_like(sk_grid, c), sk_grid, np.full_like(sk_grid, p))
    vC = smooth_max(vR, vW)
    ax.plot(sk_grid, vR * 1e3, "--", color="tab:blue", label="read (SNMR)")
    ax.plot(sk_grid, vW * 1e3, "--", color="tab:red", label="write (Vtrip)")
    ax.plot(sk_grid, vC * 1e3, "-", color="k", lw=2, label="combined")
    ax.set_title(f"{name} ({c:+d},{p:+d})"); ax.set_xlabel("skew sk (mV)"); ax.grid(True, alpha=0.25)
    i_best = int(np.argmin(vC))
    cornerA[name] = {"sk_best": float(sk_grid[i_best]), "vC_best_mV": float(vC[i_best] * 1e3),
                     "read_slope": float((vR[-1]-vR[0])/(sk_grid[-1]-sk_grid[0])*1e3),
                     "write_slope": float((vW[-1]-vW[0])/(sk_grid[-1]-sk_grid[0])*1e3)}
    print(f"  {name}: read dVmin/dsk={cornerA[name]['read_slope']:+.2f} "
          f"write dVmin/dsk={cornerA[name]['write_slope']:+.2f} mV/mV; "
          f"comb min {cornerA[name]['vC_best_mV']:.1f}mV @ sk={cornerA[name]['sk_best']:+.0f}")
axes[0].set_ylabel("Vmin (mV)"); axes[0].legend(fontsize=8)
fig.suptitle("A. Read vs Write vs Combined Vmin over PG-PD skew (real corners)")
fig.savefig(OUT_DIR / "stageC_skew_corners.png", dpi=140, bbox_inches="tight")
plt.close(fig)
print(f"  saved: {OUT_DIR/'stageC_skew_corners.png'}")

# ============================================================
# B. worst-case array Vmin vs global skew -> optimal skew*
# ============================================================
print("\n=== B. worst-case array Vmin (max over corners) vs global skew ===")
cs = np.array([c for c, _ in CORNERS.values()], float)
ps = np.array([p for _, p in CORNERS.values()], float)
names = list(CORNERS.keys())
wc, binder = [], []
for sk in sk_grid:
    vc = comb(cs, np.full_like(cs, sk), ps)   # (4,) combined at each corner
    j = int(np.argmax(vc)); wc.append(float(vc[j])); binder.append(names[j])
wc = np.array(wc)
j_opt = int(np.argmin(wc))
sk_opt, wc_opt = sk_grid[j_opt], wc[j_opt]
# baseline sk=0
j0 = int(np.argmin(np.abs(sk_grid)))
print(f"  worst-case Vmin @ sk=0 : {wc[j0]*1e3:.1f} mV (binds {binder[j0]})")
print(f"  optimal skew sk* = {sk_opt:+.1f} mV -> worst-case {wc_opt*1e3:.1f} mV "
      f"(binds {binder[j_opt]}); improvement {(wc[j0]-wc_opt)*1e3:+.1f} mV vs sk=0")
# per-corner curves for context
fig, ax = plt.subplots(figsize=(7.6, 5.2))
for k, name in enumerate(names):
    vk = np.array([comb(cs[k], sk, ps[k])[0] for sk in sk_grid])
    ax.plot(sk_grid, vk * 1e3, "--", alpha=0.6, label=f"{name}")
ax.plot(sk_grid, wc * 1e3, "k-", lw=2.5, label="worst-case (max)")
ax.axvline(sk_opt, color="green", ls=":", label=f"sk*={sk_opt:+.0f}mV")
ax.plot(sk_opt, wc_opt * 1e3, "go", ms=8)
ax.set_xlabel("global PG-PD skew sk (mV)"); ax.set_ylabel("combined Vmin (mV)")
ax.set_title("B. Worst-case array Vmin vs skew -> optimal skew")
ax.grid(True, alpha=0.25); ax.legend(fontsize=8)
fig.savefig(OUT_DIR / "stageC_worstcase_vs_skew.png", dpi=140, bbox_inches="tight")
plt.close(fig)
print(f"  saved: {OUT_DIR/'stageC_worstcase_vs_skew.png'}")

# ============================================================
# C. Sobol sensitivity of COMBINED Vmin over (cn, sk, pu)
# ============================================================
print("\n=== C. GP-based Sobol sensitivity of COMBINED Vmin ===")
from scipy.stats.qmc import Sobol
lows = np.array([COMMON_N_MIN, SK_MIN, PU_MIN]); highs = np.array([COMMON_N_MAX, SK_MAX, PU_MAX])
N = 2 ** 11
raw = Sobol(d=6, scramble=True, seed=11).random(N)
A = lows + (highs - lows) * raw[:, :3]; B = lows + (highs - lows) * raw[:, 3:]
fY = lambda M: comb(M[:, 0], M[:, 1], M[:, 2])
fA, fB = fY(A), fY(B)
varY = np.var(np.concatenate([fA, fB]))
dims = ["cn", "sk", "pu"]; Si, STi = {}, {}
for i, nm in enumerate(dims):
    AB = A.copy(); AB[:, i] = B[:, i]; fAB = fY(AB)
    Si[nm] = float(np.mean(fB * (fAB - fA)) / varY)
    STi[nm] = float(0.5 * np.mean((fA - fAB) ** 2) / varY)
print(f"  Var[Vmin_comb]={varY:.3e}")
for nm in dims:
    print(f"  {nm}: S1={Si[nm]:.3f} ST={STi[nm]:.3f}")
fig, ax = plt.subplots(figsize=(6, 4.1))
xp = np.arange(3)
ax.bar(xp - 0.19, [Si[d] for d in dims], 0.38, label="S1")
ax.bar(xp + 0.19, [STi[d] for d in dims], 0.38, label="ST")
ax.set_xticks(xp); ax.set_xticklabels(dims); ax.set_ylabel("Sobol index")
ax.set_title("C. Combined Vmin sensitivity (GP Sobol)"); ax.legend(); ax.grid(True, alpha=0.2, axis="y")
fig.savefig(OUT_DIR / "stageC_combined_sensitivity.png", dpi=140, bbox_inches="tight")
plt.close(fig)
print(f"  saved: {OUT_DIR/'stageC_combined_sensitivity.png'}")

# summary
with open(OUT_DIR / "stageC_skew_coopt_summary.txt", "w") as f:
    f.write("Stage C read-write skew co-optimization\n\n")
    f.write("A. per-corner read/write dVmin/dsk (mV/mV) + combined-min skew:\n")
    for nm, r in cornerA.items():
        f.write(f"  {nm}: read={r['read_slope']:+.2f} write={r['write_slope']:+.2f} "
                f"comb_min={r['vC_best_mV']:.1f}mV@sk{r['sk_best']:+.0f}\n")
    f.write(f"\nB. worst-case Vmin: sk=0 -> {wc[j0]*1e3:.1f}mV ({binder[j0]}); "
            f"optimal sk*={sk_opt:+.1f}mV -> {wc_opt*1e3:.1f}mV ({binder[j_opt]}); "
            f"gain {(wc[j0]-wc_opt)*1e3:+.1f}mV\n")
    f.write("\nC. combined-Vmin Sobol:\n")
    for nm in dims:
        f.write(f"  {nm}: S1={Si[nm]:.3f} ST={STi[nm]:.3f}\n")
print(f"  saved: {OUT_DIR/'stageC_skew_coopt_summary.txt'}")
print("\n=== done ===")
