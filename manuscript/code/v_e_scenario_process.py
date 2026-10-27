"""§IV-B variant: bounded process levers  ->  results/scenario_process.json (+ _contours.npz)

Same question as v_e_scenario.py -- what has to improve so that

    Vmin(FSG, read) <= V_TARGET   AND   Vmin(SFG, write) <= V_TARGET

-- but each lever now has a realistic ceiling and they are spent in a fixed order:

    lever        axis              ceiling   priority source
    local  N     k_sigmaN (l_com)  -10 %     S_T top axis in §VII (0.834 read)
    global N     cn corner offset  -20 %     steeper Vmin slope than global P
    global P     pu corner offset  -20 %

"Global -x %" pulls the corner's offset from nominal in by x % on that axis only
(the global Vth distribution gets x % tighter). Two answers are reported:

  priority   fill the levers in order, bisect only on the last one needed
  balanced   every lever at the same fraction t of its ceiling (minimax burden),
             bisect on t -- nothing is pushed to its limit

    .venv/bin/python manuscript/code/v_e_scenario_process.py [--target 0.575]

Needs surrogate_vb.pth and surrogate_vb_write.pth (both post-D-16 checkpoints).
"""
import argparse
import json

import numpy as np
import torch

import _paths  # noqa: F401
from _paths import DEVICE_COLS, RESULTS, V_T0, Z_TARGET

from src.data import grouped_train_test_split
from src.final_data import load_final_snmr, load_final_vtrip
from src.physics_layer import compute_vmin_from_z
from src.surrogate import Surrogate

ap = argparse.ArgumentParser()
ap.add_argument("--target", type=float, default=V_T0 - 0.050)
V_TARGET = ap.parse_args().target

N_DEVICE = len(DEVICE_COLS)
SEED = 42
NG = 100
torch.manual_seed(SEED)

CORNER_SHIFTS = {"FFG": (-36.42, -44.32), "FSG": (-29.16, 38.64),
                 "SFG": (31.63, -36.76), "SSG": (36.30, 44.80)}
LIMITING = {"read": "FSG", "write": "SFG"}
I = {c: i for i, c in enumerate(DEVICE_COLS)}

# lever -> ceiling (fractional improvement); order = priority
CEIL = {"local_N": 0.10, "global_N": 0.20, "global_P": 0.20}
ORDER = list(CEIL)


def load_mode(write):
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
    return dict(surr=surr,
                nominal=np.array([float(np.median(df[c])) for c in DEVICE_COLS]),
                vops=np.array(sorted(df["vop"].unique())),
                box=np.array([[X[:, i].min(), X[:, i].max()] for i in range(N_DEVICE)]))


M = {"read": load_mode(False), "write": load_mode(True)}


def vmin(mode, rows):
    m = M[mode]
    rows = np.atleast_2d(rows)
    n, vops = len(rows), m["vops"]
    Xq = np.column_stack([np.repeat(rows, len(vops), axis=0), np.tile(vops, n)])
    mu, sg = m["surr"].predict_mean(Xq)
    z = (mu / (sg + 1e-12)).reshape(n, len(vops))
    return compute_vmin_from_z(z, Z_TARGET, vops=vops)


def corner_row(mode, cname, imp):
    """Limiting corner after improvement imp = {lever: fraction in [0, ceiling]}."""
    m = M[mode]
    row = m["nominal"].copy()
    d_cn, d_pu = CORNER_SHIFTS[cname]
    row[I["cn"]] += (1 - imp.get("global_N", 0)) * (d_cn - row[I["cn"]])
    row[I["pu"]] += (1 - imp.get("global_P", 0)) * (d_pu - row[I["pu"]])
    row[I["l_com"]] = np.clip(row[I["l_com"]] * (1 - imp.get("local_N", 0)),
                              *m["box"][I["l_com"]])
    return row


def binding(imp):
    v = {m: float(vmin(m, corner_row(m, LIMITING[m], imp))[0]) for m in LIMITING}
    return max(v.values()), v


def bisect(f, lo=0.0, hi=1.0, n=40):
    """Smallest x in [lo, hi] with f(x) <= V_TARGET; f decreasing in x."""
    for _ in range(n):
        mid = 0.5 * (lo + hi)
        lo, hi = (lo, mid) if f(mid) <= V_TARGET else (mid, hi)
    return hi


def full(t_by_lever):
    return {k: t * CEIL[k] for k, t in t_by_lever.items()}


base_v, base_modes = binding({})
print(f"target {V_TARGET:.3f} V   baseline binding {base_v:.4f} V  {base_modes}")

# ---- marginal slope per lever, mV per 1 % improvement, at baseline -----------
slope = {}
for k in ORDER:
    v1, _ = binding({k: 0.01})
    slope[k] = (base_v - v1) * 1e3
print("slope mV/% :", {k: round(s, 3) for k, s in slope.items()})

# ---- per-lever monotone check over its own range -----------------------------
sweeps = {}
for k in ORDER:
    g = np.linspace(0, CEIL[k], 11)
    c = [binding({k: x})[0] for x in g]
    sweeps[k] = dict(frac=g.tolist(), vmin=c, monotone=bool(np.all(np.diff(c) <= 1e-9)))

# ---- priority path -----------------------------------------------------------
priority, imp = [], {}
for k in ORDER:
    if binding(imp)[0] <= V_TARGET:
        break
    if binding({**imp, k: CEIL[k]})[0] <= V_TARGET:
        imp[k] = bisect(lambda x: binding({**imp, k: x})[0], 0.0, CEIL[k])
    else:
        imp[k] = CEIL[k]
    v, modes = binding(imp)
    priority.append(dict(lever=k, imp=dict(imp), vmin=v, modes=modes,
                         reached=v <= V_TARGET + 1e-6))
    print(f"priority +{k:>8}: {({a: round(b*100, 2) for a, b in imp.items()})} %"
          f"  -> {v:.4f} V {modes}")
pri_ok = binding(imp)[0] <= V_TARGET + 1e-6

# ---- balanced (minimax burden) ----------------------------------------------
bal_f = lambda t: binding(full({k: t for k in ORDER}))[0]
bal_ok = bal_f(1.0) <= V_TARGET
t_bal = bisect(bal_f) if bal_ok else 1.0
bal_imp = full({k: t_bal for k in ORDER})
bal_v, bal_modes = binding(bal_imp)
print(f"balanced t={t_bal:.3f}: {({a: round(b*100, 2) for a, b in bal_imp.items()})} %"
      f"  -> {bal_v:.4f} V {bal_modes}")

# ---- feasible map: local_N x global_N at global_P = 0 and at the balanced P --
NF = 21
fl = np.linspace(0, CEIL["local_N"], NF)
fg = np.linspace(0, CEIL["global_N"], NF)
feas = {}
for gp_key, gp in (("p0", 0.0), ("pbal", bal_imp["global_P"])):
    feas[gp_key] = np.array([[binding({"local_N": a, "global_N": b, "global_P": gp})[0]
                              for a in fl] for b in fg])

# ---- contour planes ---------------------------------------------------------
# Local sigma changes the plane; global improvement moves the corners. Plotted on
# the training box only, so nothing in the figure is extrapolated.
HALF = 60.0
ax_ = np.linspace(-HALF, HALF, NG)
CN, PU = np.meshgrid(ax_, ax_)


def plane(mode, local_N):
    m = M[mode]
    rows = np.tile(m["nominal"], (NG * NG, 1))
    rows[:, I["cn"]], rows[:, I["pu"]] = CN.ravel(), PU.ravel()
    rows[:, I["l_com"]] = np.clip(rows[:, I["l_com"]] * (1 - local_N),
                                  *m["box"][I["l_com"]])
    # chunked: one 50k-row GP call is enough to get the process OOM-killed
    return np.concatenate([vmin(mode, r) for r in np.array_split(rows, 20)]
                          ).reshape(NG, NG)


panels = [("baseline", "baseline (today)", {}),
          ("local", "step 1: local-N only (ceiling)", {"local_N": CEIL["local_N"]}),
          ("priority", "priority path", dict(imp)),
          ("balanced", "balanced (minimax burden)", bal_imp)]
planes = dict(cn=ax_, pu=ax_, v_target=V_TARGET, v_t0=V_T0,
              feas_local=fl, feas_global=fg, **{f"feas_{k}": v for k, v in feas.items()})
pan_out = []
for key, lab, im in panels:
    for mode in LIMITING:
        planes[f"{key}_{mode}"] = plane(mode, im.get("local_N", 0.0))
    _, modes = binding(im)
    pan_out.append(dict(key=key, label=lab, imp=im,
                        corner_vmin={f"{LIMITING[m]}_{m}": modes[m] for m in LIMITING},
                        corner_xy={f"{LIMITING[m]}_{m}":
                                   [float(corner_row(m, LIMITING[m], im)[I["cn"]]),
                                    float(corner_row(m, LIMITING[m], im)[I["pu"]])]
                                   for m in LIMITING}))
np.savez(RESULTS / "scenario_process_contours.npz", **planes,
         panel_keys=np.array([p[0] for p in panels]))

json.dump(dict(v_t0=V_T0, v_target=V_TARGET, z_target=Z_TARGET, seed=SEED,
               ceilings=CEIL, priority_order=ORDER, limiting=LIMITING,
               corner_shifts=CORNER_SHIFTS,
               baseline_vmin=base_modes,
               baseline_gap_mV={k: (v - V_TARGET) * 1e3 for k, v in base_modes.items()},
               slope_mV_per_pct=slope, sweeps=sweeps,
               priority=dict(reached=pri_ok, steps=priority, final=imp),
               balanced=dict(reached=bal_ok, t=t_bal, imp=bal_imp, vmin=bal_v,
                             modes=bal_modes),
               panels=pan_out),
          open(RESULTS / "scenario_process.json", "w"), indent=2)
print(f"saved {RESULTS}/scenario_process.json + scenario_process_contours.npz")
