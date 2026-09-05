"""§VII sensitivity  ->  results/sensitivity[_write].json   (N070-N072)

Three views of "which of the nine axes matters", each answering a different
question and each with a different failure mode, so all three are reported.

  A. ARD lengthscales (N070).  Free -- read straight off the fitted kernels.
     Inputs are standardized, so lengthscales are comparable across axes and
     relevance ~ 1/ell. Says what the GP had to bend to fit, nothing about how
     much the OUTPUT actually moves.

  B. Sobol indices (N071).  Variance decomposition of the surrogate over a
     uniform prior on the training box. S1 = share explained by an axis alone,
     ST = share touched by that axis including every interaction.

     The Sobol output is z at the spec voltage, NOT Vmin. Vmin is undefined
     (NaN) wherever z never reaches Z_t inside the grid, and dropping those
     samples would break the Saltelli pairing that the estimator relies on.
     z(V_T0) is finite everywhere, is monotone in the sign-off margin, and is
     exactly what the T0 decision reads. mu(V_T0) and sigma(V_T0) are decomposed
     too -- sigma is the direct test of the §V-G prediction that the
     length/multiplier axes are what drive sigma.

  C. Skew tolerance (N072).  How wide can the sk axis roam before the T0
     margin is lost, scanned over the (cn, pu) plane. Reported at Z_t and at
     Z_eff (D-07), because the lobe correction eats tolerance.

Nothing here refits: it loads results/surrogate_vb[_write].pth.

    .venv/bin/python manuscript/code/vii_sensitivity.py [--write] [-n 1024]
"""
import argparse
import json

import gpytorch
import numpy as np
import torch

import _paths  # noqa: F401
from _paths import DEVICE_COLS, RESULTS, V_T0, Z_EFF, Z_TARGET

from src.final_data import Audit, load_final_snmr, load_final_vtrip
from src.surrogate import Surrogate
from src.data import grouped_train_test_split

N_DEVICE = len(DEVICE_COLS)
SEED = 42

ap = argparse.ArgumentParser()
ap.add_argument("--write", action="store_true")
ap.add_argument("-n", type=int, default=1024, help="Saltelli base sample size")
args = ap.parse_args()
MODE, TEMP = ("write", -40) if args.write else ("read", 125)
AVG, STD = ("vtrip_avg", "vtrip_std") if args.write else ("snmr_avg", "snmr_std")
TAG = "_write" if args.write else ""
torch.manual_seed(SEED)
rng = np.random.default_rng(SEED)

# --- model + training box -------------------------------------------------------
audit = Audit()
df = (load_final_vtrip if args.write else load_final_snmr)(audit)
df = df[df[AVG].notna() & df[STD].notna() & df["n_mc"].notna()].copy()
X = df[DEVICE_COLS + ["vop"]].to_numpy(float)
y = df[[AVG, STD]].to_numpy(float) * 1e-3
_, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
X_tr, _, y_tr, _ = grouped_train_test_split(X, y, cond_idx, 0.15, SEED)
surr = Surrogate.load(RESULTS / f"surrogate_vb{TAG}.pth", X_tr, y_tr,
                      device="cpu", n_device=N_DEVICE)
lo = X[:, :N_DEVICE].min(axis=0)
hi = X[:, :N_DEVICE].max(axis=0)
VOPS = np.array(sorted(np.unique(X[:, N_DEVICE])), float)
nominal = np.array([np.median(df[c]) for c in DEVICE_COLS], float)
print(f"mode={MODE} @{TEMP} C   box " +
      "  ".join(f"{c}[{a:g},{b:g}]" for c, a, b in zip(DEVICE_COLS, lo, hi)))

# =============================================================================
# A. ARD lengthscales (N070)
# =============================================================================
ell_mu = surr.get_lengthscales("mu")                    # order: DEVICE_COLS + [Vop]
ell_sig_raw = surr.get_lengthscales("sigma")
# AdditiveGPModel keeps sub-kernel 0 = OPERATING block (Vop), 1 = DEVICE block,
# so the concatenation comes back Vop-first -- undo that before comparing.
assert len(ell_sig_raw) == N_DEVICE + 1, f"unexpected sigma kernel: {ell_sig_raw.shape}"
ell_sig = np.concatenate([ell_sig_raw[1:], ell_sig_raw[:1]])
labels = DEVICE_COLS + ["Vop"]


def relevance(ell):
    """1/ell over the nine DEVICE axes, normalised to sum to 1."""
    r = 1.0 / np.asarray(ell[:N_DEVICE], float)
    return r / r.sum()


rel_mu, rel_sig = relevance(ell_mu), relevance(ell_sig)
print(f"\n{'axis':>7} | {'ell_mu':>7} {'rel_mu':>7} | {'ell_sig':>8} {'rel_sig':>8}")
print("-" * 46)
for i, lab in enumerate(labels):
    if i < N_DEVICE:
        print(f"{lab:>7} | {ell_mu[i]:>7.3f} {rel_mu[i]:>7.3f} | "
              f"{ell_sig[i]:>8.3f} {rel_sig[i]:>8.3f}")
    else:
        print(f"{lab:>7} | {ell_mu[i]:>7.3f} {'--':>7} | {ell_sig[i]:>8.3f} {'--':>8}")

# =============================================================================
# B. Sobol indices on z(V_T0), mu(V_T0), sigma(V_T0)   (N071)
# =============================================================================
def outputs(P):
    """(N,9) device points -> z, mu, sigma at the spec voltage.

    skip_posterior_variances: only the predictive MEAN is used here, and asking
    gpytorch for stddev as well is what makes this the slow part of the script
    (a solve against every test point). Same numbers, ~10x faster.
    """
    Xq = np.column_stack([P, np.full(len(P), V_T0)])
    with gpytorch.settings.skip_posterior_variances(True):
        mu, _, sg, _ = surr.predict(Xq)
    return np.column_stack([mu / (sg + 1e-12), mu * 1e3, sg * 1e3])


N = args.n
N_BOOT = 500
A = lo + (hi - lo) * rng.random((N, N_DEVICE))
B = lo + (hi - lo) * rng.random((N, N_DEVICE))
fA, fB = outputs(A), outputs(B)
n_out = fA.shape[1]
fABs = np.empty((N_DEVICE, N, n_out))
for i in range(N_DEVICE):
    AB = A.copy()
    AB[:, i] = B[:, i]
    fABs[i] = outputs(AB)


def indices(rows):
    """Saltelli 2010 (S1) / Jansen 1999 (ST) estimators on a row subset."""
    a, b = fA[rows], fB[rows]
    v = a.var(axis=0, ddof=1)
    s1 = np.stack([(b * (fABs[i][rows] - a)).mean(axis=0) / v for i in range(N_DEVICE)])
    st = np.stack([0.5 * ((a - fABs[i][rows]) ** 2).mean(axis=0) / v
                   for i in range(N_DEVICE)])
    return s1, st, v


all_rows = np.arange(N)
S1, ST, var = indices(all_rows)

# Both estimators are sample means, so their sampling error is what tells an index
# apart from zero. Resampling the Saltelli rows costs no further GP evaluations, and
# without it a negative S1 or an S1 above 1 looks like a result instead of noise.
boot_S1 = np.empty((N_BOOT, N_DEVICE, n_out))
boot_ST = np.empty((N_BOOT, N_DEVICE, n_out))
for b_i in range(N_BOOT):
    rows = rng.integers(0, N, N)
    boot_S1[b_i], boot_ST[b_i], _ = indices(rows)
S1_ci = np.percentile(boot_S1, [2.5, 97.5], axis=0)      # (2, 9, n_out)
ST_ci = np.percentile(boot_ST, [2.5, 97.5], axis=0)

print(f"\nSobol over the training box, N={N} "
      f"({N * (N_DEVICE + 2)} surrogate evaluations, {N_BOOT} bootstrap resamples)")
names = ["z(0.625V)", "mu(0.625V)", "sigma(0.625V)"]
for k, nm in enumerate(names):
    order = np.argsort(-ST[:, k])
    print(f"  {nm:>14}  (var {var[k]:.4g})")
    for i in order[:5]:
        print(f"      {DEVICE_COLS[i]:>6}  S1 {S1[i, k]:+.3f} "
              f"[{S1_ci[0, i, k]:+.3f},{S1_ci[1, i, k]:+.3f}]   "
              f"ST {ST[i, k]:.3f} [{ST_ci[0, i, k]:.3f},{ST_ci[1, i, k]:.3f}]")
    print(f"      {'':>6}  S1 sum {S1[:, k].sum():.3f}   ST sum {ST[:, k].sum():.3f}")

# =============================================================================
# C. skew tolerance (N072)
# =============================================================================
sk_i = DEVICE_COLS.index("sk")
cn_i, pu_i = DEVICE_COLS.index("cn"), DEVICE_COLS.index("pu")
GRID = 25
SK = np.linspace(lo[sk_i], hi[sk_i], 81)
cn_g = np.linspace(lo[cn_i], hi[cn_i], GRID)
pu_g = np.linspace(lo[pu_i], hi[pu_i], GRID)

pts = []
for c in cn_g:
    for p in pu_g:
        for s in SK:
            q = nominal.copy()
            q[cn_i], q[pu_i], q[sk_i] = c, p, s
            pts.append(q)
pts = np.asarray(pts)
z_grid = outputs(pts)[:, 0].reshape(GRID, GRID, len(SK))

tol = {}
for label, zt in (("z_target", Z_TARGET), ("z_eff", Z_EFF)):
    ok = z_grid >= zt
    # fraction of the swept sk axis that still passes, in mV.  Use the axis span
    # (not n * step) so a cell that passes everywhere reads exactly the full range.
    width = ok.mean(axis=2) * (SK[-1] - SK[0])
    any_ok = ok.any(axis=2)
    tol[label] = dict(
        z=float(zt),
        cells_with_any_margin=int(any_ok.sum()), cells=int(GRID * GRID),
        pct_cells_any=float(any_ok.mean() * 100),
        full_range_pct=float((width >= (SK[-1] - SK[0]) - 1e-9).mean() * 100),
        width_median_mV=float(np.median(width[any_ok])) if any_ok.any() else 0.0,
        width_p25_mV=float(np.percentile(width[any_ok], 25)) if any_ok.any() else 0.0,
        width_p75_mV=float(np.percentile(width[any_ok], 75)) if any_ok.any() else 0.0,
        sk_axis_range_mV=float(SK[-1] - SK[0]),
        # the (cn, pu) map itself, so Fig. 8 can show where the tolerance closes
        # instead of only how wide it is on average
        cn_axis=cn_g.tolist(), pu_axis=pu_g.tolist(), width_map_mV=width.tolist())
    d = tol[label]
    print(f"\nskew tolerance @ {label}={zt:.3f}  ({GRID}x{GRID} (cn,pu) cells, "
          f"sk swept {SK[0]:g}..{SK[-1]:g})")
    print(f"  cells with any passing sk : {d['pct_cells_any']:.1f}%")
    print(f"  cells passing at every sk : {d['full_range_pct']:.1f}%")
    print(f"  passing sk width (median) : {d['width_median_mV']:.1f} mV "
          f"of {d['sk_axis_range_mV']:.0f} mV "
          f"(IQR {d['width_p25_mV']:.1f}-{d['width_p75_mV']:.1f})")

out = dict(
    mode=MODE, temp_C=TEMP, seed=SEED, z_target=Z_TARGET, z_eff=Z_EFF, v_t0=V_T0,
    box={c: [float(a), float(b)] for c, a, b in zip(DEVICE_COLS, lo, hi)},
    nominal={c: float(v) for c, v in zip(DEVICE_COLS, nominal)},
    ard=dict(labels=labels,                                            # N070
             ell_mu={l: float(v) for l, v in zip(labels, ell_mu)},
             ell_sigma={l: float(v) for l, v in zip(labels, ell_sig)},
             relevance_mu={c: float(v) for c, v in zip(DEVICE_COLS, rel_mu)},
             relevance_sigma={c: float(v) for c, v in zip(DEVICE_COLS, rel_sig)}),
    sobol=dict(n_base=N, n_evaluations=int(N * (N_DEVICE + 2)),        # N071
               n_bootstrap=N_BOOT, outputs=names, variance=var.tolist(),
               S1={nm: {c: float(S1[i, k]) for i, c in enumerate(DEVICE_COLS)}
                   for k, nm in enumerate(names)},
               ST={nm: {c: float(ST[i, k]) for i, c in enumerate(DEVICE_COLS)}
                   for k, nm in enumerate(names)},
               S1_ci={nm: {c: [float(S1_ci[0, i, k]), float(S1_ci[1, i, k])]
                           for i, c in enumerate(DEVICE_COLS)}
                      for k, nm in enumerate(names)},
               ST_ci={nm: {c: [float(ST_ci[0, i, k]), float(ST_ci[1, i, k])]
                           for i, c in enumerate(DEVICE_COLS)}
                      for k, nm in enumerate(names)}),
    skew_tolerance=tol,                                                # N072
    qc_audit=audit.records)
json.dump(out, open(RESULTS / f"sensitivity{TAG}.json", "w"), indent=2, default=str)
print(f"\nsaved {RESULTS}/sensitivity{TAG}.json")
