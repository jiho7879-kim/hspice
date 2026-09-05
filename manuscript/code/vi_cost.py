"""§VI simulation budget  ->  results/cost_{part}[_write].json   (N060-N063)

The campaign cost factorises as  (voltage levels) x (conditions) x (MC samples
per condition). Each factor gets one experiment, all scored on the SAME §V-B
hold-out so the three curves are comparable.

    .venv/bin/python manuscript/code/vi_cost.py --part voltage    [--write]
    .venv/bin/python manuscript/code/vi_cost.py --part conditions [--write]
    .venv/bin/python manuscript/code/vi_cost.py --part mc         [--write]

part=voltage      does one Vop level earn its share of the budget? The 0.6/0.7
                  bracket carries the T0 decision and can never go; read drops
                  its top level (0.8 V), write's grid stops at 0.7 so its only
                  candidate is the bottom one (0.4 V). Override with --drop-level.
part=conditions   Pareto over the number of simulated conditions.
part=combined     all three cuts at once -- tests whether the single-factor
                  savings multiply, which nothing else here establishes.
part=mc           Pareto over MC samples per condition. n' < n_mc is emulated by
                  adding the extra sampling noise an n'-sample run would have had:
                  Var(mu_n') - Var(mu_n) = sigma^2 (1/n' - 1/n), and likewise
                  Var(sigma_n') - Var(sigma_n) = sigma^2 (1/2n' - 1/2n). Only
                  n' < n can be emulated, and the hold-out labels keep their own
                  n-sample noise, which floors every curve.

A full-size fit takes ~10 min on CPU, so each part reuses results/surrogate_vb*.pth
for its baseline point instead of refitting it.
"""
import argparse
import json
import time

import numpy as np
import torch

import _paths  # noqa: F401
from _paths import DEVICE_COLS, RESULTS, V_T0, Z_EFF, Z_TARGET, ZBIAS

from src.final_data import Audit, load_final_snmr, load_final_vtrip
from src.surrogate import Surrogate
from src.data import grouped_train_test_split
from src.physics_layer import compute_vmin_from_z

N_DEVICE = len(DEVICE_COLS)
VOP_COL = N_DEVICE
SEED = 42
N_ITER = 150

ap = argparse.ArgumentParser()
ap.add_argument("--part", required=True, choices=["voltage", "conditions", "mc", "combined"])
ap.add_argument("--write", action="store_true")
ap.add_argument("--combo-conditions", type=int, default=400,
                help="combined part: how many training conditions to keep.")
ap.add_argument("--combo-mc", type=int, default=500,
                help="combined part: emulated MC samples per condition.")
ap.add_argument("--seed-offset", type=int, default=0,
                help="conditions part: shifts the subset draw so the same sizes "
                     "can be re-run on different condition subsets.")
ap.add_argument("--sizes", type=lambda s: [int(v) for v in s.split(",")],
                default=[100, 200, 400, 800, 1200],
                help="conditions part: comma-separated subset sizes.")
ap.add_argument("--drop-level", type=float, default=None,
                help="voltage part: which Vop level to remove. Default: the top "
                     "level if the grid extends above the 0.6/0.7 T0 bracket "
                     "(read -> 0.8 V), otherwise the bottom one (write -> 0.4 V).")
args = ap.parse_args()
MODE, TEMP = ("write", -40) if args.write else ("read", 125)
AVG, STD = ("vtrip_avg", "vtrip_std") if args.write else ("snmr_avg", "snmr_std")
TAG = "_write" if args.write else ""
CKPT = RESULTS / f"surrogate_vb{TAG}.pth"
torch.manual_seed(SEED)

# --- data, split identical to §V-B ---------------------------------------------
audit = Audit()
df = (load_final_vtrip if args.write else load_final_snmr)(audit)
df = df[df[AVG].notna() & df[STD].notna() & df["n_mc"].notna()].copy()
X = df[DEVICE_COLS + ["vop"]].to_numpy(float)
y = df[[AVG, STD]].to_numpy(float) * 1e-3
n_mc = np.clip(df["n_mc"].to_numpy(float), 2, None)
y_noise = np.column_stack([np.maximum(y[:, 1] / np.sqrt(n_mc), 1e-9),
                           np.maximum(y[:, 1] / np.sqrt(2 * n_mc), 1e-9)])
_, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
X_tr, X_te, y_tr, y_te = grouped_train_test_split(X, y, cond_idx, 0.15, SEED)
_, _, noise_tr, _ = grouped_train_test_split(X, y_noise, cond_idx, 0.15, SEED)
_, tr_group = np.unique(X_tr[:, :N_DEVICE], axis=0, return_inverse=True)
_, te_group = np.unique(X_te[:, :N_DEVICE], axis=0, return_inverse=True)
VOPS_ALL = np.array(sorted(np.unique(X[:, VOP_COL])), float)
N_TR_COND = tr_group.max() + 1
print(f"mode={MODE} @{TEMP} C  Vop {list(VOPS_ALL)}  "
      f"train {N_TR_COND} conditions / hold-out {te_group.max() + 1}")


def vmin_pairs(Xq, yq, group, mu_p, sig_p, z_target=Z_TARGET):
    """Per-condition (measured, predicted) Vmin on that condition's own Vop grid."""
    vt, vp, cen = [], [], []
    for gid in np.unique(group):
        m = group == gid
        o = np.argsort(Xq[m, VOP_COL])
        vg = Xq[m, VOP_COL][o]
        zt = yq[m, 0][o] / (yq[m, 1][o] + 1e-12)
        zp = mu_p[m][o] / (sig_p[m][o] + 1e-12)
        a, ca = compute_vmin_from_z(zt.reshape(1, -1), z_target, vops=vg,
                                    return_censored=True)
        b, _ = compute_vmin_from_z(zp.reshape(1, -1), z_target, vops=vg,
                                   return_censored=True)
        vt.append(a[0]); vp.append(b[0]); cen.append(bool(ca[0]))
    return np.array(vt), np.array(vp), np.array(cen)


def score(surr, Xq=None, yq=None, group=None):
    """mu/sigma RMSE and Vmin RMSE on the fixed hold-out."""
    Xq = X_te if Xq is None else Xq
    yq = y_te if yq is None else yq
    group = te_group if group is None else group
    mu_p, _, sig_p, _ = surr.predict(Xq)
    mu_rmse = float(np.sqrt(np.mean((mu_p - yq[:, 0]) ** 2))) * 1e3
    sig_rmse = float(np.sqrt(np.mean((sig_p - yq[:, 1]) ** 2))) * 1e3
    mu_r2 = float(1 - np.sum((mu_p - yq[:, 0]) ** 2)
                  / np.sum((yq[:, 0] - yq[:, 0].mean()) ** 2))
    vt, vp, cen = vmin_pairs(Xq, yq, group, mu_p, sig_p)
    ok = ~cen & ~np.isnan(vt) & ~np.isnan(vp)
    err = (vp[ok] - vt[ok]) * 1e3
    return dict(mu_rmse_mV=mu_rmse, mu_r2=mu_r2, sigma_rmse_mV=sig_rmse,
                vmin_rmse_mV=float(np.sqrt(np.mean(err ** 2))),
                vmin_abs_p90_mV=float(np.percentile(np.abs(err), 90)),
                n_scored=int(ok.sum()), n_censored=int(cen.sum()))


def fit(Xa, ya, na):
    t = time.time()
    s = Surrogate(device="cpu", n_device=N_DEVICE)
    s.fit(Xa, ya, y_noise=na, n_iter=N_ITER, verbose=False)
    return s, time.time() - t


baseline = Surrogate.load(CKPT, X_tr, y_tr, device="cpu", n_device=N_DEVICE)
base = score(baseline)
print(f"baseline (full budget): mu {base['mu_rmse_mV']:.3f} mV  "
      f"Vmin {base['vmin_rmse_mV']:.2f} mV")

out = dict(mode=MODE, temp_C=TEMP, part=args.part, seed=SEED, n_iter=N_ITER,
           z_target=Z_TARGET, z_eff=Z_EFF, zbias=ZBIAS, v_t0=V_T0,
           vops=VOPS_ALL.tolist(), n_train_conditions=int(N_TR_COND),
           baseline=base, qc_audit=audit.records)

# =============================================================================
if args.part == "voltage":
    # (a) structural: the T0 decision is an interpolation inside the 0.6-0.7
    #     bracket, so the top level cannot enter it. Prove it on every condition
    #     rather than asserting it.
    g = df.pivot_table(index="deck_no", columns="vop", values="z", aggfunc="mean").dropna()
    vops = np.array(sorted(g.columns), float)
    Z = g.to_numpy(float)
    z_full = np.array([np.interp(V_T0, vops, r) for r in Z])
    lo, hi = int(np.searchsorted(vops, 0.6)), int(np.searchsorted(vops, 0.7))
    z_brac = Z[:, lo] + (V_T0 - vops[lo]) / (vops[hi] - vops[lo]) * (Z[:, hi] - Z[:, lo])
    dz_max = float(np.abs(z_full - z_brac).max())
    print(f"\nT0 decision from the full grid vs the 0.6/0.7 bracket alone: "
          f"max |dz| = {dz_max:.2e} over {len(g)} conditions")

    # (b) but the Vmin CONTOUR does use the top level -- count how often, before
    #     and after the lobe correction (D-07)
    cens = {}
    for label, zt in (("z_target", Z_TARGET), ("z_eff", Z_EFF)):
        v, c = compute_vmin_from_z(Z, zt, vops=vops, return_censored=True)
        nan = np.isnan(v)
        cens[label] = dict(
            z=float(zt), n_conditions=int(len(g)),
            left_censored=int(c.sum()), left_pct=float(c.mean() * 100),
            right_censored=int(nan.sum()), right_pct=float(nan.mean() * 100),
            # which bracket each condition's Vmin crossing falls in -- this is
            # what says whether a level earns its share of the budget
            bracket_pct={f"[{vops[j]},{vops[j + 1]}]": float(
                ((~nan) & (~c) & (v >= vops[j]) & (v <= vops[j + 1])).mean() * 100)
                for j in range(len(vops) - 1)},
            t0_pass=int((z_full >= zt).sum()), t0_pass_pct=float((z_full >= zt).mean() * 100))
        d = cens[label]
        print(f"  {label}={zt:.3f}: left-censored {d['left_pct']:.1f}%  "
              f"right-censored(>{vops[-1]} V) {d['right_pct']:.1f}%  "
              f"T0 pass {d['t0_pass_pct']:.1f}%")
        print(f"      crossing bracket: " + "  ".join(
            f"{k} {p:.1f}%" for k, p in d["bracket_pct"].items()))

    # (c) cost of dropping ONE level from TRAINING, not just from scoring.
    # Which level is droppable differs by mode. The 0.6/0.7 bracket is
    # load-bearing for the T0 decision and can never go. Read has a level above
    # that bracket (0.8) and drops it; write's grid STOPS at 0.7, so its only
    # candidate is the bottom level (0.4). Default to the least-used level of
    # the Vmin crossing distribution, which picks exactly those two.
    if args.drop_level is not None:
        drop = float(args.drop_level)
    else:
        drop = float(VOPS_ALL[-1]) if VOPS_ALL[-1] > 0.7 else float(VOPS_ALL[0])
    assert drop not in (0.6, 0.7), f"{drop} V carries the T0 bracket -- not droppable"
    assert drop in set(VOPS_ALL.tolist()), f"{drop} V not in the grid {list(VOPS_ALL)}"
    keep_tr = X_tr[:, VOP_COL] != drop
    keep_te = X_te[:, VOP_COL] != drop
    print(f"\nrefit without the {drop} V level: {int(keep_tr.sum())} rows "
          f"({100 * keep_tr.mean():.0f}% of {len(X_tr)}) ...")
    surr_red, secs = fit(X_tr[keep_tr], y_tr[keep_tr], noise_tr[keep_tr])
    print(f"  fit {secs / 60:.1f} min")
    # score two ways: on the reduced grid (what a 4-level campaign would deliver)
    # and on the full grid (the reduced model asked to extrapolate to the top)
    red_on_red = score(surr_red, X_te[keep_te], y_te[keep_te], te_group[keep_te])
    red_on_full = score(surr_red)
    full_on_red = score(baseline, X_te[keep_te], y_te[keep_te], te_group[keep_te])
    mu_x, _, _, _ = surr_red.predict(X_te[~keep_te])
    bias_drop = float((mu_x - y_te[~keep_te, 0]).mean() * 1e3)
    rmse_drop = float(np.sqrt(np.mean((mu_x - y_te[~keep_te, 0]) ** 2)) * 1e3)
    print(f"  reduced model, reduced grid : mu {red_on_red['mu_rmse_mV']:.3f} mV  "
          f"Vmin {red_on_red['vmin_rmse_mV']:.2f} mV  "
          f"({red_on_red['n_scored']} scored, {red_on_red['n_censored']} censored)")
    print(f"  full    model, reduced grid : mu {full_on_red['mu_rmse_mV']:.3f} mV  "
          f"Vmin {full_on_red['vmin_rmse_mV']:.2f} mV  "
          f"({full_on_red['n_scored']} scored, {full_on_red['n_censored']} censored)")
    print(f"  full    model, full    grid : mu {base['mu_rmse_mV']:.3f} mV  "
          f"Vmin {base['vmin_rmse_mV']:.2f} mV  "
          f"({base['n_scored']} scored, {base['n_censored']} censored)")
    print(f"  reduced model AT the dropped {drop} V level: mu RMSE {rmse_drop:.3f} mV, "
          f"bias {bias_drop:+.2f} mV")
    out.update(t0_bracket_max_dz=dz_max, censoring=cens, dropped_level=float(drop),
               saving_pct=100.0 / len(VOPS_ALL), fit_seconds=secs,
               reduced_on_reduced=red_on_red, reduced_on_full=red_on_full,
               full_on_reduced=full_on_red,
               dropped_level_mu_bias_mV=bias_drop,
               dropped_level_mu_rmse_mV=rmse_drop)

# =============================================================================
elif args.part == "conditions":
    # The subset draw is itself a source of variation: "400 conditions" is not one
    # number but a distribution over which 400 you happened to simulate. Re-run
    # with --seed-offset to sample that distribution; a single curve cannot tell
    # a real difference from draw luck.
    rng = np.random.default_rng(SEED + args.seed_offset)
    order = rng.permutation(N_TR_COND)          # nested subsets: prefixes of one
    sizes = [n for n in args.sizes if n < N_TR_COND]
    rows = []
    for n in sizes:
        keep = np.isin(tr_group, order[:n])
        s, secs = fit(X_tr[keep], y_tr[keep], noise_tr[keep])
        r = dict(n_conditions=int(n), n_rows=int(keep.sum()), fit_seconds=secs,
                 **score(s))
        rows.append(r)
        print(f"  {n:>5} conditions ({r['n_rows']:>5} rows, {secs / 60:4.1f} min): "
              f"mu {r['mu_rmse_mV']:.3f} mV  Vmin {r['vmin_rmse_mV']:.2f} mV")
    rows.append(dict(n_conditions=int(N_TR_COND), n_rows=int(len(X_tr)),
                     fit_seconds=None, **base))
    print(f"  {N_TR_COND:>5} conditions ({len(X_tr):>5} rows, baseline): "
          f"mu {base['mu_rmse_mV']:.3f} mV  Vmin {base['vmin_rmse_mV']:.2f} mV")
    out["pareto"] = rows

# =============================================================================
elif args.part == "mc":
    n_have = float(np.median(n_mc))
    sigma = y_tr[:, 1]
    rows = []
    for n_prime in (500, 1000, 2500):
        rng = np.random.default_rng(SEED + n_prime)
        # extra sampling noise an n'-sample campaign would have had
        sd_mu = sigma * np.sqrt(max(1.0 / n_prime - 1.0 / n_have, 0.0))
        sd_sg = sigma * np.sqrt(max(1.0 / (2 * n_prime) - 1.0 / (2 * n_have), 0.0))
        y_p = np.column_stack([y_tr[:, 0] + rng.normal(0, 1, len(sigma)) * sd_mu,
                               np.maximum(y_tr[:, 1] + rng.normal(0, 1, len(sigma)) * sd_sg,
                                          1e-6)])
        noise_p = np.column_stack([np.maximum(y_p[:, 1] / np.sqrt(n_prime), 1e-9),
                                   np.maximum(y_p[:, 1] / np.sqrt(2 * n_prime), 1e-9)])
        s, secs = fit(X_tr, y_p, noise_p)
        r = dict(n_mc=int(n_prime), fit_seconds=secs, **score(s))
        rows.append(r)
        print(f"  n_mc {n_prime:>5} ({secs / 60:4.1f} min): "
              f"mu {r['mu_rmse_mV']:.3f} mV  Vmin {r['vmin_rmse_mV']:.2f} mV")
    rows.append(dict(n_mc=int(n_have), fit_seconds=None, **base))
    print(f"  n_mc {int(n_have):>5} (baseline): mu {base['mu_rmse_mV']:.3f} mV  "
          f"Vmin {base['vmin_rmse_mV']:.2f} mV")
    out["pareto"] = rows
    out["n_mc_actual"] = n_have

# =============================================================================
elif args.part == "combined":
    # A, B and C each cut ONE factor with the other two at full budget, so the
    # product of their savings assumes the three are independent. They need not
    # be: with fewer conditions each label has fewer neighbours to average
    # against, so label noise from a smaller MC budget could bite harder. Cut
    # all three at once and measure instead of assuming.
    n_have = float(np.median(n_mc))
    n_cond, n_prime = args.combo_conditions, args.combo_mc
    rng = np.random.default_rng(SEED)
    order = rng.permutation(N_TR_COND)
    keep = np.isin(tr_group, order[:n_cond])
    if args.drop_level is not None:
        drop = float(args.drop_level)
    else:
        drop = float(VOPS_ALL[-1]) if VOPS_ALL[-1] > 0.7 else None   # write: keep all
    if drop is not None:
        keep &= X_tr[:, VOP_COL] != drop
    sigma = y_tr[keep, 1]
    rng = np.random.default_rng(SEED + n_prime)
    sd_mu = sigma * np.sqrt(max(1.0 / n_prime - 1.0 / n_have, 0.0))
    sd_sg = sigma * np.sqrt(max(1.0 / (2 * n_prime) - 1.0 / (2 * n_have), 0.0))
    y_p = np.column_stack([y_tr[keep, 0] + rng.normal(0, 1, len(sigma)) * sd_mu,
                           np.maximum(y_tr[keep, 1] + rng.normal(0, 1, len(sigma)) * sd_sg,
                                      1e-6)])
    noise_p = np.column_stack([np.maximum(y_p[:, 1] / np.sqrt(n_prime), 1e-9),
                               np.maximum(y_p[:, 1] / np.sqrt(2 * n_prime), 1e-9)])
    print(f"\ncombined cut: {n_cond} conditions x "
          f"{'drop ' + str(drop) + ' V' if drop else 'all levels'} x n_mc {n_prime}"
          f"  ->  {int(keep.sum())} training rows "
          f"({100 * keep.sum() / len(X_tr):.1f}% of {len(X_tr)})")
    s, secs = fit(X_tr[keep], y_p, noise_p)
    full = score(s)
    keep_te = X_te[:, VOP_COL] != drop if drop is not None else np.ones(len(X_te), bool)
    red = score(s, X_te[keep_te], y_te[keep_te], te_group[keep_te])
    # what the three single-factor experiments would have predicted, naively
    sim_ratio = (n_cond / N_TR_COND) * (1.0 if drop is None else
                                        (len(VOPS_ALL) - 1) / len(VOPS_ALL)) * (n_prime / n_have)
    print(f"  fit {secs / 60:.1f} min")
    print(f"  combined model, full    grid: mu {full['mu_rmse_mV']:.3f} mV  "
          f"Vmin {full['vmin_rmse_mV']:.2f} mV ({full['n_scored']} scored)")
    print(f"  combined model, reduced grid: mu {red['mu_rmse_mV']:.3f} mV  "
          f"Vmin {red['vmin_rmse_mV']:.2f} mV ({red['n_scored']} scored)")
    print(f"  baseline      , full    grid: mu {base['mu_rmse_mV']:.3f} mV  "
          f"Vmin {base['vmin_rmse_mV']:.2f} mV ({base['n_scored']} scored)")
    print(f"  simulation budget ratio {sim_ratio:.4f}  = {1 / sim_ratio:.1f}x cheaper")
    out.update(combo_conditions=n_cond, combo_mc=n_prime, dropped_level=drop,
               n_train_rows=int(keep.sum()), fit_seconds=secs,
               simulation_budget_ratio=float(sim_ratio),
               speedup=float(1 / sim_ratio),
               combined_on_full=full, combined_on_reduced=red)

out["seed_offset"] = args.seed_offset
suffix = f"_s{args.seed_offset}" if args.seed_offset else ""
if args.part == "combined":
    # the combo point is part of the identity of the result -- without it a
    # second run silently overwrites the first
    suffix += f"_c{args.combo_conditions}_mc{args.combo_mc}"
path = RESULTS / f"cost_{args.part}{TAG}{suffix}.json"
json.dump(out, open(path, "w"), indent=2, default=str)
print(f"\nsaved {path}")
