"""§V-G external validation  ->  results/external[_write].json   (N050-N057)

The §V-B hold-out is 300 conditions drawn from the SAME Sobol batch as training,
so it shares the batch's generation, deck template and MC settings. A stronger
question is whether the surrogate generalises to a batch it has nothing to do
with.

The Stage-B pilot batch (python/data/260713_stageB_snmr.xlsx) was designed
independently and earlier. It carries BOTH metrics -- sheet `stageB_snmr`
(read, 348 conditions) and sheet `stageB_bwrm` (write; BWRM and Vtrip are the
same measurement, 399 conditions). It sweeps only (cn, sk, pu) and holds every
length/multiplier axis at exact nominal, so its conditions sit on the 3-D
subspace

    lpu = l_com = mpu = m_com = 1,   l_sk = m_sk = 0

of the 9-D input space -- inside the training box on all nine axes, but on a
plane the Sobol draw never lands on (its l/m coordinates are continuous, so the
probability of hitting the plane is zero). Nothing here enters training; the
§V-B checkpoints are evaluated as-is.

Stage-B is a PROCESS batch, not final raw. `260713_stageB_snmr_pre_fix_backup`
shows nine cells were already hand-corrected in it (decimal-point typos such as
993.88 -> 93.88 and a three-row value shift), so residual transcription defects
must be expected and are audited for below -- by a criterion that does not
involve the surrogate.

    .venv/bin/python manuscript/code/v_g_external.py [--write]
"""
import json
import sys

import numpy as np
import pandas as pd
import torch

import _paths  # noqa: F401
from _paths import DATA, DEVICE_COLS, RESULTS, Z_TARGET

from src.final_data import Audit, load_final_snmr, load_final_vtrip
from src.surrogate import Surrogate
from src.data import grouped_train_test_split
from src.physics_layer import compute_vmin_from_z

N_DEVICE = len(DEVICE_COLS)
SEED = 42
WRITE = "--write" in sys.argv
MODE, TEMP = ("write", -40) if WRITE else ("read", 125)
SHEET = "stageB_bwrm" if WRITE else "stageB_snmr"
AVG, STD = ("vtrip_avg", "vtrip_std") if WRITE else ("snmr_avg", "snmr_std")
TAG = "_write" if WRITE else ""
CKPT = RESULTS / f"surrogate_vb{TAG}.pth"
# the pilot deck's own MC count is not recorded in the sheet; the 9-D batches use
# 5,000 and the two agree on sigma to a few 0.1 mV, so 5,000 is the assumption
N_MC_ASSUMED = 5000
PLANE = dict(lpu=1.0, l_com=1.0, l_sk=0.0, mpu=1.0, m_com=1.0, m_sk=0.0)
torch.manual_seed(SEED)

# --- the model, exactly as §V-B left it ----------------------------------------
audit = Audit()
df = (load_final_vtrip if WRITE else load_final_snmr)(audit)
df = df[df[AVG].notna() & df[STD].notna() & df["n_mc"].notna()].copy()
X = df[DEVICE_COLS + ["vop"]].to_numpy(float)
y = df[[AVG, STD]].to_numpy(float) * 1e-3
_, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
X_tr, _, y_tr, _ = grouped_train_test_split(X, y, cond_idx, 0.15, SEED)
assert CKPT.exists(), f"run v_b_forward.py{' --write' if WRITE else ''} first"
surr = Surrogate.load(CKPT, X_tr, y_tr, device="cpu", n_device=N_DEVICE)
vlo, vhi = float(X[:, N_DEVICE].min()), float(X[:, N_DEVICE].max())
print(f"mode={MODE} @{TEMP} C   trained on Vop [{vlo}, {vhi}]")

# --- the pilot batch ------------------------------------------------------------
raw = pd.read_excel(DATA / "260713_stageB_snmr.xlsx", sheet_name=SHEET)
raw = raw.rename(columns={"skew": "sk", "num": "row", "avg": AVG, "std": STD})
for c, v in PLANE.items():
    raw[c] = v
raw["n_mc"] = N_MC_ASSUMED
raw["z"] = raw[AVG] / raw[STD]

# the write model was trained on 0.4-0.7 V only (0.8 V is 0/2000 in the 9-D write
# batch, D-03). The pilot HAS 0.8 V, so keep it aside as an extrapolation probe
# instead of silently scoring outside the training range.
extrap = raw[(raw["vop"] < vlo) | (raw["vop"] > vhi)].copy()
ext = raw[(raw["vop"] >= vlo) & (raw["vop"] <= vhi)].copy()
VOP_GRID = sorted(ext["vop"].unique())
ext["cond"] = ext.groupby(["cn", "sk", "pu"], sort=False).ngroup()
n_cond = ext["cond"].nunique()
print(f"pilot {SHEET}: {len(ext)} rows, {n_cond} conditions, Vop {VOP_GRID}"
      + (f"   (+{len(extrap)} rows at Vop {sorted(extrap['vop'].unique())} "
         f"held out as extrapolation)" if len(extrap) else ""))

# --- is it inside the training box, and is it really unseen? --------------------
box = {c: (X[:, i].min(), X[:, i].max()) for i, c in enumerate(DEVICE_COLS)}
outside = {c: int(((ext[c] < lo) | (ext[c] > hi)).sum()) for c, (lo, hi) in box.items()}
assert not any(outside.values()), f"pilot points outside the training box: {outside}"

train_pts = {tuple(np.round(r, 6)) for r in X_tr[:, :N_DEVICE]}
ext_pts = {tuple(np.round(r, 6))
           for r in ext[DEVICE_COLS].drop_duplicates().to_numpy(float)}
overlap = train_pts & ext_pts
print(f"in-box: yes (all 9 axes).  leakage: {len(overlap)} of {len(ext_pts)} pilot "
      f"coordinates also in training ({len(train_pts)} coords)")
assert not overlap, "pilot conditions appear in training -- not an external set"

# --- same monotonicity audit the 9-D batches got --------------------------------
sem = float((ext[STD] / np.sqrt(N_MC_ASSUMED)).mean())
viol = [int(c) for c, g in ext.groupby("cond")
        if np.diff(g.sort_values("vop")[AVG].to_numpy(float)).min() <= -3.0 * sem]
print(f"mu(Vop) monotonicity: {len(viol)}/{n_cond} conditions violate "
      f"(threshold 3 x SEM = {3 * sem:.2f} mV)")

# --- self-consistency audit: does the pilot batch agree with ITSELF? ------------
# Stage-B is a process file with known transcription defects (see the module
# docstring). The criterion must not involve the surrogate, or the exclusion
# becomes circular: fit a quadratic surface in (cn, sk, pu) to the pilot's OWN mu
# at each Vop and flag conditions whose whole curve sits far off it. mu is smooth
# in those three axes, so a condition many mV off its neighbours is a defect.
mu_meas_mV = ext[AVG].to_numpy(float)
vop_arr = ext["vop"].to_numpy(float)
resid = np.zeros(len(ext))
for v in VOP_GRID:
    m = vop_arr == v
    c, s, p = (ext.loc[m, k].to_numpy(float) for k in ("cn", "sk", "pu"))
    A = np.column_stack([np.ones(m.sum()), c, s, p, c * c, s * s, p * p,
                         c * s, c * p, s * p])
    beta, *_ = np.linalg.lstsq(A, mu_meas_mV[m], rcond=None)
    resid[m] = mu_meas_mV[m] - A @ beta
ext["resid_mV"] = resid
rob_sd = float(1.4826 * np.median(np.abs(resid - np.median(resid))))
cond_resid = ext.groupby("cond")["resid_mV"].mean()
suspect = sorted(cond_resid.index[np.abs(cond_resid) > 5 * rob_sd].tolist())
print(f"self-consistency: robust residual SD {rob_sd:.2f} mV; "
      f"{len(suspect)}/{n_cond} conditions off the batch's own surface by >5x "
      f"(worst |mean resid| {np.abs(cond_resid).max():.1f} mV)")

# --- predict --------------------------------------------------------------------
mu_p, _, sig_p, _ = surr.predict(ext[DEVICE_COLS + ["vop"]].to_numpy(float))
mu_m = ext[AVG].to_numpy(float) * 1e-3
sig_m = ext[STD].to_numpy(float) * 1e-3


def rmse(a, b):
    return float(np.sqrt(np.mean((a - b) ** 2)))


def r2(pred, meas):
    return float(1 - np.sum((pred - meas) ** 2) / np.sum((meas - meas.mean()) ** 2))


z_p, z_m = mu_p / (sig_p + 1e-12), mu_m / (sig_m + 1e-12)
print(f"\nmu    RMSE {rmse(mu_p, mu_m) * 1e3:.3f} mV   R2 {r2(mu_p, mu_m):.4f}")
print(f"sigma RMSE {rmse(sig_p, sig_m) * 1e3:.3f} mV   R2 {r2(sig_p, sig_m):.4f}")
print(f"z     RMSE {rmse(z_p, z_m):.3f}")

# --- condition-wise Vmin --------------------------------------------------------
# one condition is duplicated in each sheet -- average the replicate for scoring
# and report the pair separately as a repeatability floor
ext["z_pred"] = z_p
grid = ext.pivot_table(index="cond", columns="vop", values=["z", "z_pred"],
                       aggfunc="mean")
vg = np.array(VOP_GRID, float)
v_m, c_m = compute_vmin_from_z(grid["z"].to_numpy(float), Z_TARGET, vops=vg,
                               return_censored=True)
v_p, c_p = compute_vmin_from_z(grid["z_pred"].to_numpy(float), Z_TARGET, vops=vg,
                               return_censored=True)
# left-censored (clamped at the grid floor) or right-censored (z never reaches
# Z_t inside the grid -> NaN) conditions carry no continuous Vmin to score
keep = ~(c_m | c_p) & ~np.isnan(v_m) & ~np.isnan(v_p)
err = (v_p[keep] - v_m[keep]) * 1e3
q = np.percentile(np.abs(err), [50, 90])
print(f"\nVmin over {int(keep.sum())}/{n_cond} non-censored conditions: "
      f"RMSE {np.sqrt(np.mean(err ** 2)):.2f} mV   "
      f"|err| P50 {q[0]:.2f}  P90 {q[1]:.2f}  max {np.abs(err).max():.2f} mV   "
      f"bias {err.mean():+.2f} mV")
worst = np.argsort(-np.abs(err))[:5]
idx = np.where(keep)[0]
print("  worst 5 (Vmin_meas -> Vmin_pred):", ", ".join(
    f"{v_m[idx[i]]:.3f}->{v_p[idx[i]]:.3f}"
    f"{'*' if grid.index[idx[i]] in suspect else ''}" for i in worst)
    + "   (* = flagged by the self-consistency audit)")

# --- same metrics with the self-inconsistent conditions removed -----------------
clean_cond = ~np.isin(grid.index.to_numpy(), suspect)
clean_row = ~ext["cond"].isin(suspect).to_numpy()
keep_c = keep & clean_cond
err_c = (v_p[keep_c] - v_m[keep_c]) * 1e3
qc_ = np.percentile(np.abs(err_c), [50, 90])
print(f"\nexcluding the {len(suspect)} flagged conditions:")
print(f"  mu   RMSE {rmse(mu_p[clean_row], mu_m[clean_row]) * 1e3:.3f} mV   "
      f"R2 {r2(mu_p[clean_row], mu_m[clean_row]):.4f}")
print(f"  z    RMSE {rmse(z_p[clean_row], z_m[clean_row]):.3f}")
print(f"  Vmin over {int(keep_c.sum())} conditions: "
      f"RMSE {np.sqrt(np.mean(err_c ** 2)):.2f} mV   |err| P50 {qc_[0]:.2f}  "
      f"P90 {qc_[1]:.2f}  max {np.abs(err_c).max():.2f} mV   "
      f"bias {err_c.mean():+.2f} mV")

print(f"\nleft-censored: measured {int(c_m.sum())}, predicted {int(c_p.sum())}, "
      f"disagree {int((c_m != c_p).sum())};  right-censored (Vmin > {vhi} V): "
      f"measured {int(np.isnan(v_m).sum())}, predicted {int(np.isnan(v_p).sum())}")

# --- repeatability floor from the duplicated condition --------------------------
dup = ext[ext.duplicated(["cn", "sk", "pu", "vop"], keep=False)].sort_values(
    ["vop", "row"])
rep_vmin = rep_mu = None
if len(dup):
    pair = [dup[dup["row"] < dup["row"].median()],
            dup[dup["row"] >= dup["row"].median()]]
    vs = [float(compute_vmin_from_z(
        p.sort_values("vop")["z"].to_numpy(float).reshape(1, -1), Z_TARGET, vops=vg)[0])
        for p in pair]
    rep_vmin = abs(vs[0] - vs[1]) * 1e3
    rep_mu = float(np.abs(np.diff(
        [p.sort_values("vop")[AVG].to_numpy(float) for p in pair], axis=0)).max())
    print(f"repeatability (one condition simulated twice): max |dmu| {rep_mu:.2f} mV, "
          f"Vmin differs {rep_vmin:.2f} mV")

# --- Vop extrapolation probe (write only: the pilot has 0.8 V, training did not) -
xp = None
if len(extrap):
    mu_x, _, sig_x, _ = surr.predict(extrap[DEVICE_COLS + ["vop"]].to_numpy(float))
    mu_xm = extrap[AVG].to_numpy(float) * 1e-3
    sig_xm = extrap[STD].to_numpy(float) * 1e-3
    xp = dict(vop=sorted(extrap["vop"].unique()), n_rows=int(len(extrap)),
              mu_rmse_mV=rmse(mu_x, mu_xm) * 1e3, mu_r2=r2(mu_x, mu_xm),
              sigma_rmse_mV=rmse(sig_x, sig_xm) * 1e3,
              z_rmse=rmse(mu_x / sig_x, mu_xm / sig_xm),
              mu_bias_mV=float((mu_x - mu_xm).mean() * 1e3))
    print(f"\nVop extrapolation to {xp['vop']} ({xp['n_rows']} rows, outside the "
          f"training range): mu RMSE {xp['mu_rmse_mV']:.2f} mV "
          f"(bias {xp['mu_bias_mV']:+.2f}), R2 {xp['mu_r2']:.4f}, "
          f"z RMSE {xp['z_rmse']:.3f}")

# --- the number that matters: how much worse than the in-batch hold-out? --------
fwd = json.load(open(RESULTS / f"forward{TAG}.json"))
in_batch = {k: fwd[k] for k in ("mu_rmse_mV", "mu_r2", "sigma_rmse_mV", "sigma_r2",
                                "vmin_rmse_mV_holdout", "vmin_abs_err_p50_mV",
                                "vmin_abs_err_p90_mV", "vmin_abs_err_max_mV")}
print(f"\nin-batch hold-out (forward{TAG}.json): "
      + "  ".join(f"{k}={v:.4g}" for k, v in in_batch.items()))

out = dict(
    mode=MODE, temp_C=TEMP, source=f"260713_stageB_snmr.xlsx:{SHEET}", plane=PLANE,
    z_target=Z_TARGET, seed=SEED, n_mc_assumed=N_MC_ASSUMED,
    vop_grid=VOP_GRID, n_rows=len(ext), n_conditions=n_cond,
    inside_training_box=True, leakage_conditions=0,
    monotonicity_violations=viol, monotonicity_threshold_mV=3 * sem,
    self_consistency_robust_sd_mV=rob_sd,
    self_inconsistent_conditions=[
        dict(cond=int(c), mean_resid_mV=float(cond_resid[c]),
             **{k: float(ext.loc[ext["cond"] == c, k].iloc[0])
                for k in ("cn", "sk", "pu")}) for c in suspect],
    mu_rmse_mV=rmse(mu_p, mu_m) * 1e3, mu_r2=r2(mu_p, mu_m),
    sigma_rmse_mV=rmse(sig_p, sig_m) * 1e3, sigma_r2=r2(sig_p, sig_m),
    z_rmse=rmse(z_p, z_m),
    n_scored=int(keep.sum()),
    vmin_rmse_mV=float(np.sqrt(np.mean(err ** 2))),                     # N050
    vmin_abs_p50_mV=float(q[0]), vmin_abs_p90_mV=float(q[1]),
    vmin_abs_max_mV=float(np.abs(err).max()), vmin_bias_mV=float(err.mean()),
    censored_measured=int(c_m.sum()), censored_predicted=int(c_p.sum()),
    censored_disagree=int((c_m != c_p).sum()),
    right_censored_measured=int(np.isnan(v_m).sum()),
    right_censored_predicted=int(np.isnan(v_p).sum()),
    repeatability_vmin_mV=rep_vmin, repeatability_mu_mV=rep_mu,
    vop_extrapolation=xp,
    clean=dict(n_conditions=int(keep_c.sum()),
               mu_rmse_mV=rmse(mu_p[clean_row], mu_m[clean_row]) * 1e3,
               mu_r2=r2(mu_p[clean_row], mu_m[clean_row]),
               sigma_rmse_mV=rmse(sig_p[clean_row], sig_m[clean_row]) * 1e3,
               sigma_r2=r2(sig_p[clean_row], sig_m[clean_row]),
               z_rmse=rmse(z_p[clean_row], z_m[clean_row]),
               vmin_rmse_mV=float(np.sqrt(np.mean(err_c ** 2))),
               vmin_abs_p50_mV=float(qc_[0]), vmin_abs_p90_mV=float(qc_[1]),
               vmin_abs_max_mV=float(np.abs(err_c).max()),
               vmin_bias_mV=float(err_c.mean())),
    in_batch_holdout=in_batch, qc_audit=audit.records)
json.dump(out, open(RESULTS / f"external{TAG}.json", "w"), indent=2, default=str)
print(f"\nsaved {RESULTS}/external{TAG}.json")
