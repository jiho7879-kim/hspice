"""§V-D corner verification  ->  results/corner.json   (N020-N023)

Independent check: the surrogate is trained on the 2,000-condition Sobol batch
only. The four PDK corner decks (FFG/FSG/SFG/SSG, 125 C) were simulated
separately and never entered training. Two questions:

  1. How far is the predicted worst-case Vmin from the corner-deck Vmin? (mV)
  2. Does the model reproduce the corner ORDER, i.e. FSG as read-limiting?

Corner -> 9D coordinate: the PDK corner is a (Vth_n, Vth_pu) shift pair; the
remaining seven length/multiplier coordinates sit at their nominal values, so
the corner is an interior point of the training box, not an extrapolation.

Reuses results/surrogate_vb.pth (fit in v_b_forward.py) -- pass --refit to
retrain from scratch.

    .venv/bin/python manuscript/code/v_d_corner.py
"""
import json
import sys

import numpy as np
import torch

import _paths  # noqa: F401
from _paths import DEVICE_COLS, RESULTS, V_T0, Z_TARGET

from src.final_data import Audit, load_corner, load_final_snmr, load_final_vtrip
from src.surrogate import Surrogate
from src.data import grouped_train_test_split
from src.physics_layer import compute_vmin_from_z

N_DEVICE = len(DEVICE_COLS)
SEED = 42
WRITE = "--write" in sys.argv
MODE, TEMP = ("write", -40) if WRITE else ("read", 125)
AVG, STD = ("vtrip_avg", "vtrip_std") if WRITE else ("snmr_avg", "snmr_std")
TAG = "_write" if WRITE else ""
CKPT = RESULTS / f"surrogate_vb{TAG}.pth"
torch.manual_seed(SEED)

# PDK corner model equivalent Vth shifts (mV), supplied by the process owner
# 2026-07-09: (cn = NMOS pass-gate, pu = PMOS load). The shift pair describes the
# device corner itself, so the same coordinates serve read (125 C) and write
# (-40 C) -- only the batch, the target and the temperature differ.
CORNER_SHIFTS = {"FFG": (-36.42, -44.32), "FSG": (-29.16, 38.64),
                 "SFG": (31.63, -36.76), "SSG": (36.30, 44.80)}

# --- training data, identical split to v_b_forward -----------------------------
audit = Audit()
df = (load_final_vtrip if WRITE else load_final_snmr)(audit)
df = df[df[AVG].notna() & df[STD].notna() & df["n_mc"].notna()].copy()
X = df[DEVICE_COLS + ["vop"]].to_numpy(float)
y = df[[AVG, STD]].to_numpy(float) * 1e-3
n_mc = np.clip(df["n_mc"].to_numpy(float), 2, None)
y_noise = np.column_stack([np.maximum(y[:, 1] / np.sqrt(n_mc), 1e-9),
                           np.maximum(y[:, 1] / np.sqrt(2 * n_mc), 1e-9)])
_, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
X_tr, _, y_tr, _ = grouped_train_test_split(X, y, cond_idx, 0.15, SEED)
_, _, noise_tr, _ = grouped_train_test_split(X, y_noise, cond_idx, 0.15, SEED)

if CKPT.exists() and "--refit" not in sys.argv:
    surr = Surrogate.load(CKPT, X_tr, y_tr, device="cpu", n_device=N_DEVICE)
else:
    surr = Surrogate(device="cpu", n_device=N_DEVICE)
    surr.fit(X_tr, y_tr, y_noise=noise_tr, n_iter=150, verbose=True)
    surr.save(CKPT)

# nominal (median) value of the seven non-corner coordinates, from the batch
nominal = {c: float(np.median(df[c])) for c in DEVICE_COLS}
print("nominal coords:", {k: round(v, 3) for k, v in nominal.items()})

# --- corner decks --------------------------------------------------------------
corner = load_corner()
corner = corner[(corner["cat"] == MODE.replace("read", "snmr").replace("write", "vtrip"))
                & (corner["temp"] == TEMP) & corner["avg"].notna()].copy()
# never score outside the supply range the model was trained on
vlo, vhi = X[:, N_DEVICE].min(), X[:, N_DEVICE].max()
corner = corner[(corner["vop"] >= vlo) & (corner["vop"] <= vhi)]
print(f"mode={MODE} @{TEMP} C, corner Vop restricted to [{vlo}, {vhi}]")

rows = []
for name, (d_cn, d_pu) in CORNER_SHIFTS.items():
    g = corner[corner["corner"] == name].sort_values("vop")
    vops = g["vop"].to_numpy(float)
    z_meas = g["z"].to_numpy(float)

    pt = dict(nominal, cn=d_cn, pu=d_pu)
    Xq = np.array([[pt[c] for c in DEVICE_COLS] + [v] for v in vops])
    inside = all(X[:, i].min() <= Xq[0, i] <= X[:, i].max() for i in range(N_DEVICE))
    mu_p, _, sig_p, _ = surr.predict(Xq)
    z_pred = mu_p / (sig_p + 1e-12)

    v_meas, c_meas = compute_vmin_from_z(z_meas.reshape(1, -1), Z_TARGET,
                                         vops=vops, return_censored=True)
    v_pred, c_pred = compute_vmin_from_z(z_pred.reshape(1, -1), Z_TARGET,
                                         vops=vops, return_censored=True)
    rows.append(dict(corner=name, cn=d_cn, pu=d_pu, inside_training_box=bool(inside),
                     vops=vops.tolist(),
                     z_meas=z_meas.tolist(), z_pred=z_pred.tolist(),
                     z_rmse=float(np.sqrt(np.mean((z_pred - z_meas) ** 2))),
                     vmin_meas=float(v_meas[0]), vmin_pred=float(v_pred[0]),
                     censored_meas=bool(c_meas[0]), censored_pred=bool(c_pred[0]),
                     err_mV=float((v_pred[0] - v_meas[0]) * 1e3),
                     z_at_T0_meas=float(np.interp(V_T0, vops, z_meas)),
                     z_at_T0_pred=float(np.interp(V_T0, vops, z_pred))))

print(f"\n{'corner':>7} {'cn':>7} {'pu':>7} | {'Vmin meas':>10} {'Vmin GP':>9} "
      f"{'err':>8} | {'z RMSE':>7} | in-box")
print("-" * 74)
for r in rows:
    print(f"{r['corner']:>7} {r['cn']:>7.2f} {r['pu']:>7.2f} | "
          f"{r['vmin_meas']:>9.4f}V {r['vmin_pred']:>8.4f}V {r['err_mV']:>+7.1f}mV | "
          f"{r['z_rmse']:>7.3f} | {r['inside_training_box']}")

# a censored corner (Vmin below the 0.4 V floor) is clamped in BOTH series, so
# its error is an artefact of the clamp -- score it separately, never in RMSE
scored = [r for r in rows if not (r["censored_meas"] or r["censored_pred"])]
err = np.array([r["err_mV"] for r in scored])
order_meas = [r["corner"] for r in sorted(rows, key=lambda r: -r["vmin_meas"])]
order_pred = [r["corner"] for r in sorted(rows, key=lambda r: -r["vmin_pred"])]
# model check only: does the sign of the T0 margin agree at each corner?
t0_agree = sum((r["z_at_T0_meas"] >= Z_TARGET) == (r["z_at_T0_pred"] >= Z_TARGET)
               for r in rows)

cens = [r["corner"] for r in rows if r["censored_meas"] or r["censored_pred"]]
print(f"\nVmin error over {len(scored)} non-censored corners: "
      f"RMSE {np.sqrt(np.mean(err**2)):.1f} mV  max |err| {np.abs(err).max():.1f} mV")
if cens:
    print(f"  censored (Vmin below the 0.4 V floor, clamped in both series): {cens}")
print(f"worst-corner order  measured {order_meas}\n"
      f"                    predicted {order_pred}   "
      f"{'MATCH' if order_meas == order_pred else 'MISMATCH'}")
print(f"{MODE}-limiting corner: measured {order_meas[0]}, predicted {order_pred[0]}")
print(f"T0 ({V_T0} V) margin sign agrees at {t0_agree}/{len(rows)} corners")

out = dict(mode=MODE, temp_C=TEMP, z_target=Z_TARGET, v_t0=V_T0, seed=SEED,
           refit="--refit" in sys.argv,
           nominal=nominal, corners=rows,                              # N020
           n_scored=len(scored), censored_corners=cens,
           vmin_rmse_mV=float(np.sqrt(np.mean(err ** 2))),             # N021
           vmin_max_abs_err_mV=float(np.abs(err).max()),
           order_measured=order_meas, order_predicted=order_pred,      # N022
           order_match=order_meas == order_pred,
           t0_sign_agreement=f"{t0_agree}/{len(rows)}",                # N023
           qc_audit=audit.records)
json.dump(out, open(RESULTS / f"corner{TAG}.json", "w"), indent=2, default=str)
print(f"\nsaved {RESULTS}/corner{TAG}.json")
