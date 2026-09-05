"""Two checks on how far the 8.35 mV of §V-B can be trusted  ->  results/robustness.json

    .venv/bin/python manuscript/code/v_b_robustness.py [--write]

Both were raised in review and both are answerable from data already on disk, so
neither refits the GP -- the §V-B checkpoint is loaded and re-scored.

  A. Repaired labels in the hold-out (O-09a).  The QC audit of §III-E repaired 31
     read cells, 22 of them by fitting a quadratic in Vop through the *same
     condition's* other voltage points. A GP is also smooth in Vop, so any repaired
     cell that landed in the hold-out is a label the model is nearly guaranteed to
     match, and the headline RMSE would be partly self-confirming. This counts them
     and re-scores with those conditions removed.

  B. A baseline the paper never had (O-09b).  Nothing in the manuscript compares the
     GP against any alternative. The cheapest fair baseline is the one the paper
     already fits elsewhere as a defect criterion: a full quadratic response surface
     in the same ten inputs, least squares on the same training rows, through the
     same physics layer, scored on the same hold-out.
"""
import argparse
import json

import numpy as np
import torch

import _paths  # noqa: F401
from _paths import DEVICE_COLS, RESULTS, Z_TARGET

from src.final_data import Audit, load_final_snmr, load_final_vtrip
from src.surrogate import Surrogate
from src.data import grouped_train_test_split
from src.physics_layer import compute_vmin_from_z

N_DEVICE = len(DEVICE_COLS)
VOP_COL = N_DEVICE
SEED = 42

ap = argparse.ArgumentParser()
ap.add_argument("--write", action="store_true")
args = ap.parse_args()
MODE = "write" if args.write else "read"
AVG, STD = ("vtrip_avg", "vtrip_std") if args.write else ("snmr_avg", "snmr_std")
TAG = "_write" if args.write else ""
torch.manual_seed(SEED)

# --- same data, same split as §V-B -------------------------------------------------
audit = Audit()
df = (load_final_vtrip if args.write else load_final_snmr)(audit)
df = df[df[AVG].notna() & df[STD].notna() & df["n_mc"].notna()].copy()
X = df[DEVICE_COLS + ["vop"]].to_numpy(float)
y = df[[AVG, STD]].to_numpy(float) * 1e-3
deck = df["deck_no"].to_numpy()
_, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
X_tr, X_te, y_tr, y_te = grouped_train_test_split(X, y, cond_idx, 0.15, SEED)

# rows -> which deck each hold-out row came from. The split is by condition, so a
# deck is entirely in one side or the other; assert that rather than assume it.
row_key = {tuple(r): i for i, r in enumerate(X)}
te_rows = np.array([row_key[tuple(r)] for r in X_te])
tr_rows = np.array([row_key[tuple(r)] for r in X_tr])
te_decks, tr_decks = set(deck[te_rows]), set(deck[tr_rows])
assert not (te_decks & tr_decks), "a deck appears on both sides of the split"
print(f"mode={MODE}  train {len(X_tr)} rows / hold-out {len(X_te)} rows  "
      f"({len(tr_decks)}/{len(te_decks)} decks)")

surr = Surrogate.load(RESULTS / f"surrogate_vb{TAG}.pth", X_tr, y_tr,
                      device="cpu", n_device=N_DEVICE)
mu_gp, _, sig_gp, _ = surr.predict(X_te)


def vmin_pairs(mu_pred, sig_pred):
    """-> (true Vmin, predicted Vmin, censored, deck) per hold-out condition."""
    _, grp = np.unique(X_te[:, :N_DEVICE], axis=0, return_inverse=True)
    vt, vp, cen, dk = [], [], [], []
    for gid in np.unique(grp):
        m = grp == gid
        o = np.argsort(X_te[m, VOP_COL])
        vg = X_te[m, VOP_COL][o]
        zt = y_te[m, 0][o] / (y_te[m, 1][o] + 1e-12)
        zp = mu_pred[m][o] / (sig_pred[m][o] + 1e-12)
        a, ca = compute_vmin_from_z(zt.reshape(1, -1), Z_TARGET, vops=vg, return_censored=True)
        b, _ = compute_vmin_from_z(zp.reshape(1, -1), Z_TARGET, vops=vg, return_censored=True)
        vt.append(a[0]); vp.append(b[0]); cen.append(bool(ca[0]))
        dk.append(deck[te_rows[m]][0])
    return (np.array(vt), np.array(vp), np.array(cen), np.array(dk))


def score(vt, vp, cen, keep=None):
    ok = ~cen & np.isfinite(vt) & np.isfinite(vp)
    if keep is not None:
        ok &= keep
    e = (vp[ok] - vt[ok]) * 1e3
    return dict(n=int(ok.sum()), rmse_mV=float(np.sqrt(np.mean(e ** 2))),
                p90_mV=float(np.percentile(np.abs(e), 90)),
                max_mV=float(np.abs(e).max()))


vt, vp, cen, dk = vmin_pairs(mu_gp, sig_gp)
base = score(vt, vp, cen)
print(f"\nbaseline (all scorable hold-out conditions): "
      f"Vmin RMSE {base['rmse_mV']:.2f} mV over {base['n']}")

# =============================================================================
# A. repaired labels in the hold-out
# =============================================================================
# The audit records every touched cell. "Quadratic" repairs are the ones that
# borrow smoothness in Vop; decade restorations (x10) and parse typos do not, so
# they are counted separately.
rec = audit.records
# The audit's own wording is the classifier: "quad fit ->" marks a cell rebuilt from a
# quadratic through the condition's other Vop points, "x10" a restored decade, and the
# rest are parse-stage typos. Only the first borrows the smoothness a GP also assumes.
quad = {r["deck"] for r in rec if "quad fit" in str(r["why"]).lower()}
decade = {r["deck"] for r in rec if "x10" in str(r["why"]).lower()} - quad
typo = {r["deck"] for r in rec} - quad - decade
repaired_all = {r["deck"] for r in rec}
assert quad, "no quadratic repairs found -- the audit wording changed, fix the classifier"

in_holdout = {k: sorted(v & te_decks) for k, v in
              dict(quadratic=quad, decade=decade, typo=typo, any=repaired_all).items()}
print("\nrepaired decks:", {k: len(v) for k, v in
                            dict(quadratic=quad, decade=decade, typo=typo).items()})
print("of those, in the hold-out:", {k: len(v) for k, v in in_holdout.items()})

keep_quad = ~np.isin(dk, in_holdout["quadratic"])
keep_any = ~np.isin(dk, in_holdout["any"])
no_quad, no_any = score(vt, vp, cen, keep_quad), score(vt, vp, cen, keep_any)
print(f"excluding quadratic-repaired conditions: {no_quad['rmse_mV']:.2f} mV "
      f"over {no_quad['n']}  (baseline {base['rmse_mV']:.2f} over {base['n']})")
print(f"excluding every repaired condition     : {no_any['rmse_mV']:.2f} mV "
      f"over {no_any['n']}")

# =============================================================================
# B. quadratic response surface baseline
# =============================================================================
def quad_features(Xa):
    """1, x_i, x_i^2, x_i x_j over the ten inputs -- 66 columns."""
    n, d = Xa.shape
    cols = [np.ones(n)] + [Xa[:, i] for i in range(d)]
    for i in range(d):
        for j in range(i, d):
            cols.append(Xa[:, i] * Xa[:, j])
    return np.column_stack(cols)


# standardise first: the raw axes differ by four orders of magnitude, and the
# normal equations are badly conditioned without it
lo, hi = X_tr.min(axis=0), X_tr.max(axis=0)
span = np.where(hi > lo, hi - lo, 1.0)
Ptr, Pte = quad_features((X_tr - lo) / span), quad_features((X_te - lo) / span)
coef, *_ = np.linalg.lstsq(Ptr, y_tr, rcond=None)
pred = Pte @ coef
mu_q, sig_q = pred[:, 0], np.clip(pred[:, 1], 1e-6, None)

def rmse_r2(p, t):
    return (float(np.sqrt(np.mean((p - t) ** 2))),
            float(1 - np.sum((p - t) ** 2) / np.sum((t - t.mean()) ** 2)))

qmu, qmu_r2 = rmse_r2(mu_q, y_te[:, 0])
qsg, qsg_r2 = rmse_r2(sig_q, y_te[:, 1])
gmu, gmu_r2 = rmse_r2(mu_gp, y_te[:, 0])
gsg, gsg_r2 = rmse_r2(sig_gp, y_te[:, 1])
vtq, vpq, cenq, _ = vmin_pairs(mu_q, sig_q)
quad_score = score(vtq, vpq, cenq)
print(f"\nquadratic surface ({Ptr.shape[1]} terms): mu {qmu*1e3:.3f} mV (R2 {qmu_r2:.4f})  "
      f"sigma {qsg*1e3:.3f} mV (R2 {qsg_r2:.4f})  Vmin RMSE {quad_score['rmse_mV']:.2f} mV "
      f"over {quad_score['n']}")
print(f"GP                              : mu {gmu*1e3:.3f} mV (R2 {gmu_r2:.4f})  "
      f"sigma {gsg*1e3:.3f} mV (R2 {gsg_r2:.4f})  Vmin RMSE {base['rmse_mV']:.2f} mV")

# =============================================================================
# C. does the baseline still hold outside the batch it was fitted on?
# =============================================================================
# In-batch the quadratic wins, which on its own says only that this response is
# smooth. The question that matters for a sign-off flow is what happens on runs the
# fit never saw, so both models are scored at the four PDK corners of §V-D.
from src.final_data import load_corner
from _paths import V_T0  # noqa: E402

CORNER_SHIFTS = {"FFG": (-36.42, -44.32), "FSG": (-29.16, 38.64),
                 "SFG": (31.63, -36.76), "SSG": (36.30, 44.80)}
TEMP = -40 if args.write else 125
cor = load_corner()
cor = cor[(cor["cat"] == ("vtrip" if args.write else "snmr")) & (cor["temp"] == TEMP)
          & cor["avg"].notna()].copy()
vlo, vhi = X[:, N_DEVICE].min(), X[:, N_DEVICE].max()
cor = cor[(cor["vop"] >= vlo) & (cor["vop"] <= vhi)]
nominal = {c: float(np.median(df[c])) for c in DEVICE_COLS}

corner_rows = []
for name, (d_cn, d_pu) in CORNER_SHIFTS.items():
    g = cor[cor["corner"] == name].sort_values("vop")
    vops, z_ref = g["vop"].to_numpy(float), g["z"].to_numpy(float)
    pt = dict(nominal, cn=d_cn, pu=d_pu)
    Xq = np.array([[pt[c] for c in DEVICE_COLS] + [v] for v in vops])
    mu_g, _, sg_g, _ = surr.predict(Xq)
    pq = quad_features((Xq - lo) / span) @ coef
    mu_q2, sg_q2 = pq[:, 0], np.clip(pq[:, 1], 1e-6, None)
    row = dict(corner=name)
    for tag, zp in (("gp", mu_g / (sg_g + 1e-12)), ("quad", mu_q2 / (sg_q2 + 1e-12))):
        v_ref, c_ref = compute_vmin_from_z(z_ref.reshape(1, -1), Z_TARGET, vops=vops,
                                           return_censored=True)
        v_p, c_p = compute_vmin_from_z(zp.reshape(1, -1), Z_TARGET, vops=vops,
                                       return_censored=True)
        row[f"{tag}_z_rmse"] = float(np.sqrt(np.mean((zp - z_ref) ** 2)))
        row[f"{tag}_vmin"] = float(v_p[0])
        row[f"{tag}_censored"] = bool(c_p[0])
        row["vmin_ref"] = float(v_ref[0])
        row["censored_ref"] = bool(c_ref[0])
        row[f"{tag}_err_mV"] = float((v_p[0] - v_ref[0]) * 1e3)
    corner_rows.append(row)

scorable = [r for r in corner_rows if not (r["censored_ref"] or r["gp_censored"]
                                           or r["quad_censored"])]
corner_cmp = {}
for tag in ("gp", "quad"):
    e = np.array([r[f"{tag}_err_mV"] for r in scorable])
    corner_cmp[tag] = dict(n=len(e), rmse_mV=float(np.sqrt(np.mean(e ** 2))),
                           max_mV=float(np.abs(e).max()),
                           z_rmse_mean=float(np.mean([r[f"{tag}_z_rmse"]
                                                      for r in corner_rows])))
print(f"\ncorners ({corner_cmp['gp']['n']} scorable): "
      f"GP Vmin RMSE {corner_cmp['gp']['rmse_mV']:.2f} mV (z RMSE {corner_cmp['gp']['z_rmse_mean']:.3f})"
      f" | quadratic {corner_cmp['quad']['rmse_mV']:.2f} mV "
      f"(z RMSE {corner_cmp['quad']['z_rmse_mean']:.3f})")
for r in corner_rows:
    print(f"   {r['corner']}: ref {r['vmin_ref']:.4f}  GP {r['gp_err_mV']:+.1f}  "
          f"quad {r['quad_err_mV']:+.1f} mV")

out = dict(
    mode=MODE, seed=SEED, z_target=Z_TARGET,
    corners=dict(per_corner=corner_rows, comparison=corner_cmp),
    baseline_gp=base,
    repaired=dict(
        decks_total=len(repaired_all),
        decks_quadratic=len(quad), decks_decade=len(decade), decks_typo=len(typo),
        in_holdout={k: v for k, v in in_holdout.items()},
        n_in_holdout={k: len(v) for k, v in in_holdout.items()},
        rmse_excluding_quadratic=no_quad,
        rmse_excluding_any_repair=no_any),
    quadratic_surface=dict(
        n_terms=int(Ptr.shape[1]),
        mu_rmse_mV=qmu * 1e3, mu_r2=qmu_r2,
        sigma_rmse_mV=qsg * 1e3, sigma_r2=qsg_r2,
        vmin=quad_score),
    gp_reference=dict(mu_rmse_mV=gmu * 1e3, mu_r2=gmu_r2,
                      sigma_rmse_mV=gsg * 1e3, sigma_r2=gsg_r2))
json.dump(out, open(RESULTS / f"robustness{TAG}.json", "w"), indent=2, default=str)
print(f"\nsaved {RESULTS}/robustness{TAG}.json")
