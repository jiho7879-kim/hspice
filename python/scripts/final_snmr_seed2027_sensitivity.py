"""
Sensitivity analysis on the FINAL 9D SNMR batch (seed 2027), 0.4-0.7V grid.

Fills the [TBD]s in paper section 7 from the final batch itself, replacing the
older 4D / Stage-C figures that were previously quoted as reference:

  A. ARD lengthscales, grouped (which axis does the GP find sensitive)
  B. GP-based Sobol indices (Saltelli first-order S1 + Jansen total ST) of Vmin
     over all 9 variation dimensions -- affordable ONLY because the surrogate
     replaces circuit simulation (see paper section 7)
  C. PG-PD skew tolerance: dVmin/dsk and the Vmin swing over sk in [-20,+20] mV
     at representative operating points

Voltage grid is the production 4-level grid {0.4,0.5,0.6,0.7} decided in
paper section 2.3 / 6.1.  Usage:  cd python && python scripts/final_snmr_seed2027_sensitivity.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.utils import Z_FIXED
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z

DATA = Path(__file__).resolve().parent.parent / "data" / "sheet_final_snmr_seed2027.xlsx"
OUT = Path(__file__).resolve().parent.parent / "results" / "final_snmr_seed2027"
OUT.mkdir(parents=True, exist_ok=True)

DEV = ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]
VOPS = np.array([0.4, 0.5, 0.6, 0.7], dtype=np.float64)
LO = np.array([-60., -20., -60., 0.7, 0.7, -0.075, 0.7, 0.7, -0.075])
HI = np.array([60., 20., 60., 1.3, 1.3, 0.075, 1.3, 1.3, 0.075])
# saturate censored / never-crossing so variance-based analysis stays finite
VMIN_FLOOR, VMIN_CEIL = 0.40, 0.75
SNMR_A = (-50., 300.)
SNMR_S = (3., 30.)

print("=" * 70)
print("Final 9D SNMR batch -- sensitivity (ARD / Sobol / skew tolerance)")
print("=" * 70)

df = pd.read_excel(DATA, sheet_name=0)
df.columns = [str(c).strip().lower() for c in df.columns]
for c in ("snmr_avg", "snmr_std", "n_mc"):
    df[c] = pd.to_numeric(df[c], errors="coerce")
a, s = df["snmr_avg"], df["snmr_std"]
bad = (a.notna() & ((a < SNMR_A[0]) | (a > SNMR_A[1]))) | \
      (s.notna() & ((s < SNMR_S[0]) | (s > SNMR_S[1])))
df.loc[bad, ["snmr_avg", "snmr_std"]] = np.nan
df = df.dropna(subset=["snmr_avg", "snmr_std"])
df = df[np.isin(np.round(df["vop"], 3), VOPS)].copy()

X = df[DEV + ["vop"]].to_numpy(float)
y = df[["snmr_avg", "snmr_std"]].to_numpy(float) * 1e-3
n_mc = np.clip(df["n_mc"].to_numpy(float), 2, None)
y_noise = np.column_stack([np.maximum(y[:, 1] / np.sqrt(n_mc), 1e-9),
                           np.maximum(y[:, 1] / np.sqrt(2 * n_mc), 1e-9)])
print(f"\n  rows={len(X)}  conditions={len(np.unique(X[:, :9], axis=0))}  "
      f"vops={sorted(set(np.round(df['vop'],3)))}")
print("  training GP on ALL data (no hold-out; accuracy already gated) ...")
surr = Surrogate(device="cpu", n_device=9)
surr.fit(X, y, y_noise=y_noise, n_iter=150, verbose=False)
print("  done.")


def vmin_of(M, batch=4000, clip=True):
    """Vmin for an (n,9) block of conditions, via the 4-Vop z-curve."""
    M = np.atleast_2d(M)
    out_v, out_c = [], []
    for i in range(0, len(M), batch):
        blk = M[i:i + batch]
        nb, nv = len(blk), len(VOPS)
        Xp = np.column_stack([np.repeat(blk, nv, axis=0), np.tile(VOPS, nb)])
        mu, _, sg, _ = surr.predict(Xp)
        z = (mu / (sg + 1e-12)).reshape(nb, nv)
        v, c = compute_vmin_from_z(z, z_target=Z_FIXED, vops=VOPS,
                                   return_censored=True)
        out_v.append(v); out_c.append(c)
    v = np.concatenate(out_v); c = np.concatenate(out_c)
    if clip:
        v = np.where(c, VMIN_FLOOR, v)
        v = np.where(np.isnan(v), VMIN_CEIL, v)
    return v


# ===================================================================== A. ARD
print("\n" + "=" * 70)
print("=== A. ARD lengthscales (standardised-input scale) ===")
print("=" * 70)
ls = surr.get_lengthscales("mu")
labels = DEV + ["Vop"]
ard = {k: float(v) for k, v in zip(labels, ls)}
order = sorted(ard.items(), key=lambda kv: kv[1])
print("\n  (shorter lengthscale = more sensitive)")
for k, v in order:
    print(f"    ell_{k:<8s} = {v:8.4f}")
print(f"\n  ell_pu/ell_cn = {ard['pu']/ard['cn']:.3f} "
      f"({'PG(cn) dominant' if ard['pu'] > ard['cn'] else 'PU dominant'})")

# =================================================================== B. Sobol
print("\n" + "=" * 70)
print("=== B. GP-based Sobol indices of Vmin over 9 dims ===")
print("=" * 70)
try:
    from scipy.stats import qmc
    m = 10                                  # N = 2^10 = 1024 base samples
    N = 2 ** m
    eng = qmc.Sobol(d=18, scramble=True, seed=7)
    raw = eng.random(N)
except ImportError:
    N = 1024
    rng0 = np.random.default_rng(7)
    raw = rng0.random((N, 18))
A = LO + (HI - LO) * raw[:, :9]
B = LO + (HI - LO) * raw[:, 9:]
print(f"  N={N} base samples -> {N*(9+2)} surrogate evaluations "
      f"(~{N*(9+2)*len(VOPS)/1000:.0f}k GP rows)")
fA, fB = vmin_of(A), vmin_of(B)
varY = float(np.var(np.concatenate([fA, fB])))
S1, ST = {}, {}
for i, nm in enumerate(DEV):
    AB = A.copy(); AB[:, i] = B[:, i]
    fAB = vmin_of(AB)
    S1[nm] = float(np.mean(fB * (fAB - fA)) / varY)          # Saltelli 2010
    ST[nm] = float(0.5 * np.mean((fA - fAB) ** 2) / varY)    # Jansen total
    print(f"    {nm:<7s} S1={S1[nm]:+.4f}  ST={ST[nm]:+.4f}")
print(f"\n  Var[Vmin] = {varY:.4e} V^2   (sd = {np.sqrt(varY)*1e3:.1f} mV)")
print(f"  sum S1 = {sum(S1.values()):.3f}  "
      f"({'near-additive' if sum(S1.values())>0.8 else 'interaction-heavy'})")
rank = sorted(ST.items(), key=lambda kv: -kv[1])
print("  ST ranking: " + " > ".join(f"{k}({v:.3f})" for k, v in rank))

# ========================================================= C. skew tolerance
print("\n" + "=" * 70)
print("=== C. PG-PD skew tolerance (final batch) ===")
print("=" * 70)
sk_grid = np.linspace(-20, 20, 41)
NOM = {"lpu": 1.0, "l_com": 1.0, "l_sk": 0.0, "mpu": 1.0, "m_com": 1.0, "m_sk": 0.0}
ops = {
    "TT (0,0)": (0, 0),
    "mild-FSG (-30,+30)": (-30, 30),
    "mild-SFG (+30,-30)": (30, -30),
    "FFG-ish (-30,-30)": (-30, -30),
    "SSG-ish (+30,+30)": (30, 30),
}
skew_rep = {}
for nm, (cn, pu) in ops.items():
    M = np.zeros((len(sk_grid), 9))
    M[:, 0] = cn; M[:, 1] = sk_grid; M[:, 2] = pu
    for j, k in enumerate(DEV[3:], start=3):
        M[:, j] = NOM[k]
    v = vmin_of(M, clip=False)
    fin = np.isfinite(v)
    swing = float(np.nanmax(v) - np.nanmin(v)) if fin.any() else float("nan")
    i0 = int(np.argmin(np.abs(sk_grid)))
    lo, hi = max(i0 - 4, 0), min(i0 + 4, len(sk_grid) - 1)
    slope = float((v[hi] - v[lo]) / (sk_grid[hi] - sk_grid[lo])) \
        if (np.isfinite(v[hi]) and np.isfinite(v[lo])) else float("nan")
    skew_rep[nm] = {"vmin_sk0_V": float(v[i0]), "swing_mV": swing * 1e3,
                    "dVmin_dsk_mV_per_mV": slope * 1e3}
    print(f"  {nm:<20s} Vmin(sk=0)={v[i0]*1e3:6.1f}mV  "
          f"swing={swing*1e3:6.1f}mV  dVmin/dsk={slope*1e3:+.2f} mV/mV")

# allowable skew window against the two spec points
print("\n  Allowable skew window (|sk| keeping Vmin <= spec):")
for spec, lab in ((0.625, "T0 "), (0.675, "EOL")):
    parts = []
    for nm, (cn, pu) in ops.items():
        M = np.zeros((len(sk_grid), 9))
        M[:, 0] = cn; M[:, 1] = sk_grid; M[:, 2] = pu
        for j, k in enumerate(DEV[3:], start=3):
            M[:, j] = NOM[k]
        v = vmin_of(M, clip=True)
        ok = sk_grid[v <= spec]
        parts.append(f"{nm.split()[0]}:" +
                     (f"[{ok.min():+.0f},{ok.max():+.0f}]" if ok.size else "none"))
    print(f"    {lab} {spec:.3f}V -> " + "  ".join(parts))

res = {"ard_lengthscales": ard, "ell_pu_over_cn": ard["pu"] / ard["cn"],
       "sobol_S1": S1, "sobol_ST": ST, "sobol_N": int(N),
       "var_vmin_V2": varY, "sum_S1": float(sum(S1.values())),
       "skew": skew_rep, "vops": VOPS.tolist()}
with open(OUT / "sensitivity_final9d.json", "w") as f:
    json.dump(res, f, indent=2)
print(f"\n  saved: {OUT / 'sensitivity_final9d.json'}")
print("\n=== Done ===")
