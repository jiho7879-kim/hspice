"""§V-E inverse estimation  ->  results/inverse.json   (N030-N032)

The forward surrogate answers "what is Vmin at this condition". The paper's
application is the other direction: "which conditions land on a target Vmin".
Two things are checked, both against MEASURED hold-out conditions rather than
against the model's own output:

  1. coordinate recovery -- hand back a hold-out condition's measured Vmin and
     eight of its nine coordinates, and ask for the ninth. Compare with the
     coordinate the deck actually had.                              (N030)
  2. multi-start inversion onto the T0 manifold from many starts.   (N031)
     Each start is a 1-D slice, so the solve is a vectorised bisection on the
     surrogate -- exact to machine precision, no optimiser to tune. The
     gradient path of IV-F is for the multi-dimensional case and is NOT
     exercised here; it still needs its own validation.
  3. design boundary -- the iso-Vmin contour that the inverse delivers. (N032)

Reuses results/surrogate_vb.pth. No retraining.

    .venv/bin/python manuscript/code/v_e_inverse.py
"""
import json
import sys

import gpytorch
import numpy as np
import torch

import _paths  # noqa: F401
from _paths import DEVICE_COLS, FIGURES, RESULTS, V_T0, Z_TARGET

from src.final_data import load_final_snmr
from src.surrogate import Surrogate
from src.data import grouped_train_test_split
from src.physics_layer import compute_vmin_from_z

N_DEVICE = len(DEVICE_COLS)
SEED = 42
RECOVER_AXES = ["cn", "pu"]          # the two knobs the design actually turns
rng = np.random.default_rng(SEED)
torch.manual_seed(SEED)

# --- data + surrogate, identical split to v_b_forward -------------------------
df = load_final_snmr()
df = df[df["snmr_avg"].notna() & df["snmr_std"].notna() & df["n_mc"].notna()].copy()
X = df[DEVICE_COLS + ["vop"]].to_numpy(float)
y = df[["snmr_avg", "snmr_std"]].to_numpy(float) * 1e-3
_, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
X_tr, X_te, y_tr, y_te = grouped_train_test_split(X, y, cond_idx, 0.15, SEED)
surr = Surrogate.load(RESULTS / "surrogate_vb.pth", X_tr, y_tr, n_device=N_DEVICE)

VOPS = np.array(sorted(df["vop"].unique()))
NV = len(VOPS)
BOX = {c: (float(X[:, i].min()), float(X[:, i].max())) for i, c in enumerate(DEVICE_COLS)}
print("design box:", {k: (round(v[0], 2), round(v[1], 2)) for k, v in BOX.items()})


def predict_mean(Xq):
    """Posterior means only. Inversion never uses the predictive variance, and
    computing it dominates the runtime, so skip it."""
    xt = surr._to_tensor(surr._x_scaler.transform(Xq))
    with torch.no_grad(), gpytorch.settings.skip_posterior_variances(True):
        return (surr.mu_gp(xt).mean.cpu().numpy(),
                surr.sigma_gp(xt).mean.cpu().numpy())


def vmin_of(rows):
    """Vmin for (n, 9) design rows -- one batched GP call over all supplies."""
    rows = np.atleast_2d(rows)
    n = len(rows)
    Xq = np.repeat(rows, NV, axis=0)
    Xq = np.column_stack([Xq, np.tile(VOPS, n)])
    mu, sig = predict_mean(Xq)
    z = (mu / (sig + 1e-12)).reshape(n, NV)
    v, c = compute_vmin_from_z(z, Z_TARGET, vops=VOPS, return_censored=True)
    return v, c


# --- measured Vmin per hold-out condition ------------------------------------
te_dev, te_gi = np.unique(X_te[:, :N_DEVICE], axis=0, return_inverse=True)
v_meas, cens = [], []
for gid in range(len(te_dev)):
    m = te_gi == gid
    o = np.argsort(X_te[m, N_DEVICE])
    vg = X_te[m, N_DEVICE][o]
    z = y_te[m, 0][o] / (y_te[m, 1][o] + 1e-12)
    v, c = compute_vmin_from_z(z.reshape(1, -1), Z_TARGET, vops=vg, return_censored=True)
    v_meas.append(v[0]); cens.append(bool(c[0]))
v_meas, cens = np.array(v_meas), np.array(cens)
usable = ~cens & ~np.isnan(v_meas)
print(f"hold-out conditions: {len(te_dev)}, usable targets: {usable.sum()}")


# =============================== 1. coordinate recovery =======================
def bisect_axis(rows, axis, targets, lo, hi, iters=24):
    """Vectorised bisection: move column `axis` until vmin_of(rows) == targets.

    Vmin is monotone in each Vth knob but not in the same direction: it falls
    with cn (a faster pass-gate needs less supply) and rises with pu. The
    direction is read off the two endpoints rather than assumed. `a` is kept as
    the endpoint with the SMALLER Vmin and `b` the larger, so one loop serves
    both signs. Rows whose target lies outside [v_a, v_b] return NaN rather
    than a clipped answer.

    A NaN Vmin means the z curve never reaches the target inside the supply
    grid, i.e. Vmin is above the grid -- treated as +inf, not as missing.
    """
    r = rows.copy()
    r[:, axis] = lo; v_lo, _ = vmin_of(r)
    r[:, axis] = hi; v_hi, _ = vmin_of(r)
    v_lo = np.nan_to_num(v_lo, nan=9.0)
    v_hi = np.nan_to_num(v_hi, nan=9.0)

    falling = v_hi < v_lo
    a = np.where(falling, hi, lo).astype(float)   # -> smaller Vmin end
    b = np.where(falling, lo, hi).astype(float)   # -> larger  Vmin end
    inside = (np.minimum(v_lo, v_hi) <= targets) & (targets <= np.maximum(v_lo, v_hi))

    for _ in range(iters):
        mid = 0.5 * (a + b)
        r[:, axis] = mid
        v, _ = vmin_of(r)
        below = np.nan_to_num(v, nan=9.0) < targets
        a = np.where(below, mid, a)
        b = np.where(below, b, mid)
    return np.where(inside, 0.5 * (a + b), np.nan)


recovery = {}
for axis_name in RECOVER_AXES:
    axis = DEVICE_COLS.index(axis_name)
    rows = te_dev[usable].copy()
    truth = rows[:, axis].copy()
    lo, hi = BOX[axis_name]
    got = bisect_axis(rows, axis, v_meas[usable], lo, hi)
    ok = ~np.isnan(got)
    err = got[ok] - truth[ok]
    # local sensitivity, for translating a Vmin error into a coordinate error
    step = 2.0
    r2 = te_dev[usable][ok].copy(); r2[:, axis] = truth[ok] + step
    v2, _ = vmin_of(r2)
    r3 = te_dev[usable][ok].copy(); r3[:, axis] = truth[ok] - step
    v3, _ = vmin_of(r3)
    slope = np.abs((v2 - v3) / (2 * step)) * 1e3          # mV Vmin per mV Vth
    recovery[axis_name] = dict(
        n_target=int(usable.sum()), n_recovered=int(ok.sum()),
        rmse_mV=float(np.sqrt(np.mean(err ** 2))),
        p50_mV=float(np.percentile(np.abs(err), 50)),
        p90_mV=float(np.percentile(np.abs(err), 90)),
        max_mV=float(np.abs(err).max()), bias_mV=float(err.mean()),
        dvmin_dx_median=float(np.nanmedian(slope)),
        implied_from_forward_mV=float(8.35 / np.nanmedian(slope)),
    )
    r = recovery[axis_name]
    print(f"\n[{axis_name}] recovered {r['n_recovered']}/{r['n_target']} conditions")
    print(f"  error RMSE {r['rmse_mV']:.2f} mV  P50 {r['p50_mV']:.2f}  P90 {r['p90_mV']:.2f}  "
          f"max {r['max_mV']:.2f}  bias {r['bias_mV']:+.2f}")
    print(f"  |dVmin/d{axis_name}| median {r['dvmin_dx_median']:.3f} "
          f"-> forward 8.35 mV implies {r['implied_from_forward_mV']:.2f} mV of {axis_name}")


# =============================== 2. multi-start inversion =====================
# Target: land on Vmin = V_T0 while free in (cn, pu), other seven at nominal.
nominal = {c: float(np.median(df[c])) for c in DEVICE_COLS}
base = np.array([nominal[c] for c in DEVICE_COLS])
i_cn, i_pu = DEVICE_COLS.index("cn"), DEVICE_COLS.index("pu")

# The target manifold does not cross every 1-D slice: for a fast enough pu the
# whole cn range already meets T0 and there is no boundary to find. Sample the
# starts inside the reachable pu band (established by the boundary sweep below,
# pinned here so the two sections stay consistent) and report the band itself.
PU_REACHABLE_MIN = 5.0
starts = np.column_stack([rng.uniform(*BOX["cn"], 12),
                          rng.uniform(PU_REACHABLE_MIN, BOX["pu"][1], 12)])
# one 1-D slice per start (pu held at the start value), all solved in one batch
rows0 = np.tile(base, (len(starts), 1))
rows0[:, i_cn], rows0[:, i_pu] = starts[:, 0], starts[:, 1]
sol = bisect_axis(rows0, i_cn, np.full(len(starts), V_T0), *BOX["cn"])
rows1 = rows0.copy()
rows1[:, i_cn] = np.where(np.isnan(sol), rows0[:, i_cn], sol)
v_sol, _ = vmin_of(rows1)
multi = []
for k, (cn0, pu0) in enumerate(starts):
    if np.isnan(sol[k]):
        multi.append(dict(pu=float(pu0), cn_start=float(cn0), cn_solution=None,
                          reason="target outside the cn bracket at this pu"))
    else:
        multi.append(dict(pu=float(pu0), cn_start=float(cn0), cn_solution=float(sol[k]),
                          vmin_at_solution=float(v_sol[k]),
                          residual_mV=float((v_sol[k] - V_T0) * 1e3)))
res = [m["residual_mV"] for m in multi if m.get("cn_solution") is not None]
print(f"\nmulti-start inversion onto Vmin = {V_T0} V: "
      f"{len(res)}/{len(multi)} starts converged, "
      f"max |residual| {max(np.abs(res)):.3f} mV" if res else "no start converged")


# =============================== 3. design boundary ===========================
NG = 70
cn_ax = np.linspace(*BOX["cn"], NG)
pu_ax = np.linspace(*BOX["pu"], NG)
CN, PU = np.meshgrid(cn_ax, pu_ax)
grid = np.tile(base, (NG * NG, 1))
grid[:, i_cn] = CN.ravel()
grid[:, i_pu] = PU.ravel()
vg, cg = vmin_of(grid)
VM = vg.reshape(NG, NG)
V = np.nan_to_num(VM, nan=9.0)
# where in pu does a T0 boundary exist at all? (rows whose cn sweep straddles it)
has_edge = (V.min(axis=1) <= V_T0) & (V_T0 <= V.max(axis=1))
pu_edge = pu_ax[has_edge]
# the inverse deliverable itself: cn*(pu) on the boundary
cn_star = np.full(NG, np.nan)
for i in np.where(has_edge)[0]:
    row = np.tile(base, (1, 1))
    row[0, i_pu] = pu_ax[i]
    cn_star[i] = bisect_axis(row, i_cn, np.array([V_T0]), *BOX["cn"])[0]
np.savez(RESULTS / "inverse_boundary.npz", cn=cn_ax, pu=pu_ax, vmin=VM,
         censored=cg.reshape(NG, NG), nominal=base, v_t0=V_T0,
         pu_axis=pu_ax, cn_star=cn_star)
print(f"\nboundary grid {NG}x{NG}: Vmin {np.nanmin(VM):.3f}-{np.nanmax(VM):.3f} V, "
      f"{100*np.mean(V <= V_T0):.1f}% of the plane meets {V_T0} V")
print(f"  a T0 boundary exists only for pu >= {pu_edge.min():.1f} mV "
      f"({has_edge.sum()}/{NG} pu rows); below that the whole cn range passes")
print(f"  cn* on the boundary: {np.nanmin(cn_star):.1f} .. {np.nanmax(cn_star):.1f} mV")

out = dict(z_target=Z_TARGET, v_t0=V_T0, seed=SEED,
           n_holdout_conditions=int(len(te_dev)), n_usable_targets=int(usable.sum()),
           recovery=recovery,                                        # N030
           multistart=multi,                                         # N031
           multistart_max_residual_mV=float(max(np.abs(res))) if res else None,
           boundary=dict(grid=NG, cn_range=BOX["cn"], pu_range=BOX["pu"],
                         frac_plane_meeting_T0=float(np.mean(V <= V_T0)),
                         pu_min_with_edge=float(pu_edge.min()),
                         n_pu_rows_with_edge=int(has_edge.sum()),
                         cn_star_min=float(np.nanmin(cn_star)),
                         cn_star_max=float(np.nanmax(cn_star))),       # N032
           design_box=BOX, nominal=nominal)
json.dump(out, open(RESULTS / "inverse.json", "w"), indent=2, default=str)
print(f"\nsaved {RESULTS}/inverse.json + inverse_boundary.npz")
