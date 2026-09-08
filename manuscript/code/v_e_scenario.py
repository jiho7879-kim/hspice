"""§IV-B  inverse scenario: "lower Vmin by 50 mV"  ->  results/scenario.json (N033-N034)

A customer asks for the spec to move from V_T0 = 0.625 V to 0.575 V.  The two
binding conditions are the mode-limiting corners found in §III-B: FSG limits
read, SFG limits write, and each is censored below 0.4 V in the other mode.  So
the question is what has to improve for

    Vmin(FSG, read) <= 0.575 V   AND   Vmin(SFG, write) <= 0.575 V

to hold at the same time.  For each candidate knob we bisect on the knob itself,
which is the same axis-wise inverse the paper already uses -- only the axis being
solved for is a process-improvement lever instead of a corner coordinate.

Cases (a)-(c) turn one lever, (d) turns two, so (d) shows what the interaction
buys over the single-axis answers.

    .venv/bin/python manuscript/code/v_e_scenario.py

Needs surrogate_vb.pth and surrogate_vb_write.pth (both post-D-16 checkpoints).
"""
import json

import numpy as np
import torch

import _paths  # noqa: F401
from _paths import DEVICE_COLS, RESULTS, V_T0, Z_TARGET

from src.data import grouped_train_test_split
from src.final_data import load_final_snmr, load_final_vtrip
from src.physics_layer import compute_vmin_from_z
from src.surrogate import Surrogate

N_DEVICE = len(DEVICE_COLS)
SEED = 42
V_TARGET = 0.575                     # the customer's ask: V_T0 - 50 mV
NG = 100                             # contour grid per side (~2 mV cells)
torch.manual_seed(SEED)

# same corner table as v_d_corner.py -- the shift pair defines the device corner,
# so the same coordinates serve both modes
CORNER_SHIFTS = {"FFG": (-36.42, -44.32), "FSG": (-29.16, 38.64),
                 "SFG": (31.63, -36.76), "SSG": (36.30, 44.80)}
LIMITING = {"read": "FSG", "write": "SFG"}      # from §III-B

I = {c: i for i, c in enumerate(DEVICE_COLS)}


def load_mode(write):
    """Data, surrogate, nominal coords and supply grid for one mode."""
    avg, std = ("vtrip_avg", "vtrip_std") if write else ("snmr_avg", "snmr_std")
    tag = "_write" if write else ""
    df = (load_final_vtrip if write else load_final_snmr)()
    df = df[df[avg].notna() & df[std].notna() & df["n_mc"].notna()].copy()
    X = df[DEVICE_COLS + ["vop"]].to_numpy(float)
    y = df[[avg, std]].to_numpy(float) * 1e-3
    _, cond = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
    X_tr, _, y_tr, _ = grouped_train_test_split(X, y, cond, 0.15, SEED)
    surr = Surrogate.load(RESULTS / f"surrogate_vb{tag}.pth", X_tr, y_tr,
                          n_device=N_DEVICE)
    return dict(
        surr=surr,
        nominal=np.array([float(np.median(df[c])) for c in DEVICE_COLS]),
        vops=np.array(sorted(df["vop"].unique())),
        box=np.array([[X[:, i].min(), X[:, i].max()] for i in range(N_DEVICE)]),
    )


M = {"read": load_mode(False), "write": load_mode(True)}
for k, m in M.items():
    print(f"{k}: nominal={dict(zip(DEVICE_COLS, np.round(m['nominal'], 3)))}  "
          f"vops={m['vops']}")


def vmin(mode, rows):
    """Vmin for (n, 9) device rows -- one batched GP call over all supplies."""
    m = M[mode]
    rows = np.atleast_2d(rows)
    n, vops = len(rows), m["vops"]
    Xq = np.repeat(rows, len(vops), axis=0)
    Xq = np.column_stack([Xq, np.tile(vops, n)])
    mu, sg = m["surr"].predict_mean(Xq)
    z = (mu / (sg + 1e-12)).reshape(n, len(vops))
    v, cen = compute_vmin_from_z(z, Z_TARGET, vops=vops, return_censored=True)
    return v, cen


def corner_row(mode, name, scale=1.0, mods=None):
    """The limiting-corner point, optionally pulled toward nominal and/or edited.

    scale shrinks the corner's (cn, pu) offset from nominal -- scale=1 is the PDK
    corner, scale=0 is nominal.  mods maps an axis name to a multiplier on its
    nominal value (the local-sigma levers).
    """
    m = M[mode]
    row = m["nominal"].copy()
    d_cn, d_pu = CORNER_SHIFTS[name]
    row[I["cn"]] = row[I["cn"]] + scale * (d_cn - row[I["cn"]])
    row[I["pu"]] = row[I["pu"]] + scale * (d_pu - row[I["pu"]])
    for ax, mult in (mods or {}).items():
        row[I[ax]] = np.clip(row[I[ax]] * mult, *m["box"][I[ax]])
    return row


# ---- baseline: reproduce §III-B at the two limiting corners -------------------
base = {}
for mode, cname in LIMITING.items():
    v, cen = vmin(mode, corner_row(mode, cname))
    base[mode] = float(v[0])
    print(f"baseline {mode} @ {cname}: Vmin = {v[0]:.4f} V "
          f"(censored={bool(cen[0])})  needs {(v[0]-V_TARGET)*1e3:+.1f} mV")


def binding(scale=1.0, mods=None):
    """max over the two binding conditions -- both must clear V_TARGET."""
    out = []
    for m in ("read", "write"):
        v, _ = vmin(m, corner_row(m, LIMITING[m], scale, mods))
        out.append(float(v[0]))
    return max(out)


# ---- the four cases ----------------------------------------------------------
# Each is a scalar knob s, decreasing = more improvement, s=1 = today.
# lo is set by the design box: local-sigma multipliers bottom out at 0.70.
def lo_for(axes):
    return max(0.70 / M[m]["nominal"][I[ax]]
               for ax in axes for m in ("read", "write"))


CASES = [
    dict(key="k_sigmaN", axes=["l_com"], label="NMOS local-σ",
         desc="reduce the NMOS common local-σ multiplier k_σN"),
    dict(key="k_sigmaP", axes=["lpu"], label="PMOS local-σ",
         desc="reduce the PMOS local-σ multiplier k_σP"),
    dict(key="corner_pullin", axes=None, label="global Vth corner",
         desc="tighten the global Vth distribution, pulling FSG/SFG toward nominal"),
    dict(key="k_sigmaNP", axes=["l_com", "lpu"], label="NMOS + PMOS local-σ",
         desc="reduce both local-σ multipliers together"),
]


def evaluate(case, s):
    if case["axes"] is None:
        return binding(scale=s)
    return binding(mods={ax: s for ax in case["axes"]})


results = []
for case in CASES:
    lo = 0.0 if case["axes"] is None else lo_for(case["axes"])
    grid = np.linspace(lo, 1.0, 21)
    curve = [evaluate(case, s) for s in grid]
    # bisection is only valid on a monotone bracket; check instead of assuming
    mono = bool(np.all(np.diff(curve) >= -1e-9))
    if curve[0] <= V_TARGET:
        a, b = lo, 1.0
        for _ in range(40):
            mid = 0.5 * (a + b)
            if evaluate(case, mid) <= V_TARGET:
                a = mid
            else:
                b = mid
        s_req, reach = a, True
    else:
        s_req, reach = lo, False
    rec = dict(case=case["key"], label=case["label"], description=case["desc"],
               knob_floor=lo, monotone=mono, reachable=reach,
               s_required=float(s_req),
               vmin_at_s=float(evaluate(case, s_req)),
               vmin_at_floor=float(curve[0]),
               sweep_s=grid.tolist(), sweep_vmin=[float(c) for c in curve])
    if case["axes"] is not None:
        # Report the required sigma reduction and nothing further. Converting it to
        # device area (Pelgrom) would pick one lever out of several -- S/D profile,
        # implant/IIP optimisation and geometry all move local sigma -- and the
        # surrogate does not model any of them, so the choice is not ours to make.
        rec["sigma_reduction_pct"] = float((1 - s_req) * 100)
    else:
        rec["corner_shrink_pct"] = float((1 - s_req) * 100)
        rec["corner_cn_pu"] = {m: [float(corner_row(m, LIMITING[m], s_req)[I["cn"]]),
                                   float(corner_row(m, LIMITING[m], s_req)[I["pu"]])]
                               for m in ("read", "write")}
    results.append(rec)
    print(f"{case['label']:>22}: {'s=%.3f' % s_req if reach else 'UNREACHABLE'}"
          f"  Vmin_binding={rec['vmin_at_s']:.4f} V"
          f"  (floor s={lo:.3f} -> {curve[0]:.4f} V, monotone={mono})")


# ---- contour planes: baseline + one per case ---------------------------------
# Plotted wider than the +-60 mV training box so the corners are not sitting on
# the frame. Everything past PLOT_BOX_TRAIN is GP extrapolation -- the figure
# draws that limit so the reader can see which part of the plane has data behind
# it. The case solutions are all evaluated AT the corners, inside the box.
PLOT_HALF = 100.0
TRAIN_HALF = 60.0
cn_ax = np.linspace(-PLOT_HALF, PLOT_HALF, NG)
pu_ax = np.linspace(-PLOT_HALF, PLOT_HALF, NG)
CN, PU = np.meshgrid(cn_ax, pu_ax)


def plane(mode, mods=None):
    m = M[mode]
    rows = np.tile(m["nominal"], (NG * NG, 1))
    rows[:, I["cn"]] = CN.ravel()
    rows[:, I["pu"]] = PU.ravel()
    for ax, mult in (mods or {}).items():
        rows[:, I[ax]] = np.clip(rows[:, I[ax]] * mult, *m["box"][I[ax]])
    v, _ = vmin(mode, rows)
    return v.reshape(NG, NG)


planes = {"cn": cn_ax, "pu": pu_ax, "v_target": V_TARGET, "v_t0": V_T0,
          "train_half": TRAIN_HALF}
panels = [dict(key="baseline", label="baseline (today)", mods=None, scale=1.0)]
for case, rec in zip(CASES, results):
    # corner_pullin moves the corners, not the plane, so it has no panel of its
    # own -- the table carries it. Unreachable levers DO get a panel, drawn at the
    # box floor: "even at 2.04x area the corner stays outside" is the result.
    if case["axes"] is None:
        continue
    s = rec["s_required"] if rec["reachable"] else rec["knob_floor"]
    panels.append(dict(key=case["key"],
                       label=case["label"] + ("" if rec["reachable"] else " (floor)"),
                       mods={ax: s for ax in case["axes"]}, scale=1.0, s=s))
for pan in panels:
    for mode in ("read", "write"):
        planes[f"{pan['key']}_{mode}"] = plane(mode, pan["mods"])
    # Exact Vmin at each binding corner for this panel. The contour grid is ~2 mV
    # per cell, so reading pass/fail off it would snap the corner to a neighbour
    # and can disagree with the table -- record the solved value instead.
    pan["corner_vmin"] = {
        f"{LIMITING[m]}_{m}": float(vmin(m, corner_row(m, LIMITING[m],
                                                       pan["scale"], pan["mods"]))[0][0])
        for m in ("read", "write")}
    print(f"  plane {pan['key']}: done  " +
          "  ".join(f"{k} {v:.4f}" for k, v in pan["corner_vmin"].items()))

np.savez(RESULTS / "scenario_contours.npz", **planes,
         panel_keys=np.array([p["key"] for p in panels]),
         panel_labels=np.array([p["label"] for p in panels]))

json.dump(dict(v_t0=V_T0, v_target=V_TARGET, z_target=Z_TARGET, seed=SEED,
               limiting=LIMITING, corner_shifts=CORNER_SHIFTS,
               baseline_vmin=base,
               baseline_gap_mV={k: (v - V_TARGET) * 1e3 for k, v in base.items()},
               cases=results,
               panels=[{k: v for k, v in p.items() if k != "mods"} for p in panels]),
          open(RESULTS / "scenario.json", "w"), indent=2, default=str)
print(f"\nsaved {RESULTS}/scenario.json + scenario_contours.npz")
