"""
Stage B SNMR-only analyses on the 4D surrogate [cn, sk, pu, Vop].

Downstream deliverables that need ONLY the SNMR read-margin data (no Vtrip /
write-margin), built on the Stage B gate surrogate (GO, 2026-07-13):

  A. PG-PD skew tolerance -- Vmin vs skew at representative operating points,
     local dVmin/dsk, and the allowable-skew window for a Vmin budget.
     (Reframes phase2_to_paper_plan sec 4.1 "required WLUD" -> "allowable skew".)
  B. GP-based global sensitivity -- Saltelli/Jansen Sobol first-order (Si) and
     total (STi) indices of Vmin over (cn, sk, pu). GP-based, not weighted-Sobol
     (avoids the Saltelli bias flagged in revised_plan_review_20260709.md).
  C. Skew-shifted Vmin contour -- how the pass/fail boundary at a fixed Vmin
     target moves as skew goes -20 -> 0 -> +20 mV.

Trains the mu/sigma GPs on ALL 1745 samples (no hold-out; accuracy already
gated). Usage:  cd python && python scripts/stageB_snmr_analysis.py
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
OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "stageB_real"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_VOPS = np.array([0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float64)
SK_MIN, SK_MAX = -20.0, 20.0
VMIN_FLOOR, VMIN_CEIL = 0.35, 0.85   # saturate censored/fail for finite analysis

print("=" * 70)
print("Stage B SNMR-only analyses (skew tolerance / sensitivity / contour)")
print("=" * 70)

# ---- load + train on all data ---------------------------------------------
d = parse_manual_xlsx(DATA_PATH)
X, y = d["X"], d["y"]
sk_col, pu_col, vop_col = 1, 2, 3
print(f"\nTrain surrogate on all {len(X)} samples ...")
surr = Surrogate(device="cpu")
surr.fit(X, y, verbose=False, n_iter=200)
print("  done.")


def vmin_of(cn, sk, pu, clip=False):
    """Vmin at a single (cn,sk,pu) via the 5-Vop z-curve. NaN if never crosses."""
    cn, sk, pu = np.atleast_1d(cn), np.atleast_1d(sk), np.atleast_1d(pu)
    n = len(cn)
    Xp = np.empty((n * len(DATA_VOPS), 4))
    for i in range(n):
        s = i * len(DATA_VOPS)
        Xp[s:s + len(DATA_VOPS), 0] = cn[i]
        Xp[s:s + len(DATA_VOPS), sk_col] = sk[i]
        Xp[s:s + len(DATA_VOPS), pu_col] = pu[i]
        Xp[s:s + len(DATA_VOPS), vop_col] = DATA_VOPS
    mu, _, sigma, _ = surr.predict(Xp)
    z = (mu / (sigma + 1e-12)).reshape(n, len(DATA_VOPS))
    v, cens = compute_vmin_from_z(z, z_target=Z_FIXED, vops=DATA_VOPS, return_censored=True)
    if clip:
        v = np.where(cens, VMIN_FLOOR, v)          # left-censored -> floor
        v = np.where(np.isnan(v), VMIN_CEIL, v)    # never-cross   -> ceil
    return v


# ===========================================================================
# A. Skew tolerance
# ===========================================================================
print("\n=== A. PG-PD skew tolerance ===")
sk_grid = np.linspace(SK_MIN, SK_MAX, 41)
op_points = {
    "TT (0,0)": (0, 0),
    "mild-FSG (-30,+30)": (-30, 30),
    "mild-SFG (+30,-30)": (30, -30),
    "FFG-ish (-30,-30)": (-30, -30),
    "SSG-ish (+30,+30)": (30, 30),
}
skew_report = {}
fig, ax = plt.subplots(figsize=(7.5, 5.2))
for name, (cn, pu) in op_points.items():
    vs = np.array([vmin_of(cn, s, pu)[0] for s in sk_grid])
    finite = np.isfinite(vs)
    swing = float(np.nanmax(vs) - np.nanmin(vs)) if finite.any() else float("nan")
    # central slope dVmin/dsk around sk=0
    i0 = np.argmin(np.abs(sk_grid))
    lo, hi = max(i0 - 4, 0), min(i0 + 4, len(sk_grid) - 1)
    slope = float((vs[hi] - vs[lo]) / (sk_grid[hi] - sk_grid[lo])) if np.isfinite(vs[hi]) and np.isfinite(vs[lo]) else float("nan")
    skew_report[name] = {"swing_mV": swing * 1e3, "dVmin_dsk_mV_per_mV": slope * 1e3,
                         "vmin_at_sk0": float(vs[i0])}
    ax.plot(sk_grid[finite], vs[finite] * 1e3, "-o", ms=3, label=name)
    print(f"  {name:22s}: Vmin(sk=0)={vs[i0]*1e3:6.1f}mV  swing over skew={swing*1e3:5.1f}mV  "
          f"dVmin/dsk~{slope*1e3:+.2f} mV/mV")
ax.set_xlabel("PG-PD skew sk (mV)   [PG=cn+sk, PD=cn-sk]")
ax.set_ylabel("Vmin (mV)")
ax.set_title("A. Vmin vs PG-PD skew at representative operating points")
ax.grid(True, alpha=0.25)
ax.legend(fontsize=8)
fig.savefig(OUT_DIR / "stageB_skew_tolerance.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  saved: {OUT_DIR/'stageB_skew_tolerance.png'}")

# allowable-skew window for a Vmin budget, over a (cn,pu) grid at each sk
print("\n  Allowable-skew window (|sk| keeping Vmin <= budget) at TT and mild corners:")
for budget in (0.55, 0.60, 0.65):
    line = []
    for name, (cn, pu) in op_points.items():
        vs = np.array([vmin_of(cn, s, pu, clip=True)[0] for s in sk_grid])
        ok = sk_grid[vs <= budget]
        win = f"[{ok.min():+.0f},{ok.max():+.0f}]" if ok.size else "none"
        line.append(f"{name.split()[0]}:{win}")
    print(f"    budget {budget:.2f}V -> " + "  ".join(line))

# ===========================================================================
# B. GP-based Sobol sensitivity of Vmin over (cn, sk, pu)   [Saltelli/Jansen]
# ===========================================================================
print("\n=== B. GP-based Sobol sensitivity of Vmin (cn, sk, pu) ===")
from scipy.stats.qmc import Sobol
dims = ["cn", "sk", "pu"]
lows = np.array([COMMON_N_MIN, SK_MIN, PU_MIN])
highs = np.array([COMMON_N_MAX, SK_MAX, PU_MAX])
m = 11                       # N = 2^11 = 2048 base samples
N = 2 ** m
eng = Sobol(d=6, scramble=True, seed=7)
raw = eng.random(N)          # (N,6) -> split into A,B
A = lows + (highs - lows) * raw[:, :3]
B = lows + (highs - lows) * raw[:, 3:]


def f_vmin(M):
    return vmin_of(M[:, 0], M[:, 1], M[:, 2], clip=True)


fA, fB = f_vmin(A), f_vmin(B)
varY = np.var(np.concatenate([fA, fB]))
Si, STi = {}, {}
for i, name in enumerate(dims):
    AB = A.copy(); AB[:, i] = B[:, i]
    fAB = f_vmin(AB)
    Si[name] = float(np.mean(fB * (fAB - fA)) / varY)              # Saltelli 2010 first-order
    STi[name] = float(0.5 * np.mean((fA - fAB) ** 2) / varY)        # Jansen total
print(f"  Var[Vmin] = {varY:.3e}  (N={N} base, {N*(3+2)} evals)")
print(f"  {'dim':4s} {'S1 (first)':>12s} {'ST (total)':>12s}")
for name in dims:
    print(f"  {name:4s} {Si[name]:12.3f} {STi[name]:12.3f}")

fig, ax = plt.subplots(figsize=(6.2, 4.2))
xpos = np.arange(len(dims))
ax.bar(xpos - 0.19, [Si[d] for d in dims], 0.38, label="S1 (first-order)")
ax.bar(xpos + 0.19, [STi[d] for d in dims], 0.38, label="ST (total)")
ax.set_xticks(xpos); ax.set_xticklabels(dims)
ax.set_ylabel("Sobol index"); ax.set_title("B. Vmin sensitivity (GP-based Sobol)")
ax.legend(); ax.grid(True, alpha=0.2, axis="y")
fig.savefig(OUT_DIR / "stageB_sensitivity.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  saved: {OUT_DIR/'stageB_sensitivity.png'}")

# ===========================================================================
# C. Skew-shifted Vmin contour at a fixed target
# ===========================================================================
print("\n=== C. Skew-shifted Vmin contour ===")
target = 0.60
n_grid = 55
cna = np.linspace(COMMON_N_MIN, COMMON_N_MAX, n_grid)
pua = np.linspace(PU_MIN, PU_MAX, n_grid)
CN, PU = np.meshgrid(cna, pua, indexing="xy")
fig, ax = plt.subplots(figsize=(7.2, 6.0))
colors = {-20: "tab:blue", 0: "k", 20: "tab:red"}
for sk_fixed in (-20, 0, 20):
    vg = np.empty((n_grid, n_grid))
    for a in range(n_grid):
        cn_row = CN[a]; pu_row = PU[a]
        vg[a] = vmin_of(cn_row, np.full(n_grid, sk_fixed), pu_row, clip=True)
    pcn, ppu = extract_contour(vg, CN, PU, contour_level=target)
    if len(pcn):
        ax.plot(pcn, ppu, color=colors[sk_fixed], lw=2.2, label=f"sk={sk_fixed:+d} mV")
    print(f"  sk={sk_fixed:+3d}: Vmin={target}V contour {len(pcn)} pts")
ax.set_xlabel("common_N_shift (mV)"); ax.set_ylabel("PU_shift (mV)")
ax.set_title(f"C. Vmin={target}V pass/fail boundary vs PG-PD skew")
ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX); ax.set_ylim(PU_MIN, PU_MAX)
ax.grid(True, alpha=0.2); ax.legend()
fig.savefig(OUT_DIR / "stageB_skew_contour_shift.png", dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  saved: {OUT_DIR/'stageB_skew_contour_shift.png'}")

# ---- summary --------------------------------------------------------------
with open(OUT_DIR / "snmr_analysis_summary.txt", "w") as f:
    f.write("Stage B SNMR-only analyses\n\n")
    f.write("A. skew tolerance (Vmin vs sk):\n")
    for name, r in skew_report.items():
        f.write(f"  {name}: Vmin(sk0)={r['vmin_at_sk0']*1e3:.1f}mV "
                f"swing={r['swing_mV']:.1f}mV dVmin/dsk={r['dVmin_dsk_mV_per_mV']:+.2f}mV/mV\n")
    f.write("\nB. Sobol sensitivity of Vmin:\n")
    for name in dims:
        f.write(f"  {name}: S1={Si[name]:.3f} ST={STi[name]:.3f}\n")
    f.write(f"\nC. Vmin={target}V contour extracted at sk=-20,0,+20 mV "
            f"(see stageB_skew_contour_shift.png)\n")
print(f"\n  saved: {OUT_DIR/'snmr_analysis_summary.txt'}")
print("\n=== Stage B SNMR analyses complete ===")
