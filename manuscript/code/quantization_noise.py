"""Quantization-noise attribution for the holdout Vmin RMSE  ->  results/quantization_noise.json

Scope (user decision, 2026-09): the analysis runs on the WRITE (Vtrip) batch ONLY.
The read (SNMR) batch was transcribed properly with decimals preserved, so its
holdout RMSE carries no transcription-quantization component to attribute.  The
write batch was transcribed sloppily: the decimal-grid audit shows 69 % of its
labels on the integer-mV grid (decimals dropped), 73 % on 0.1 mV and the rest on
0.01 mV.  The reported hold-out write Vmin RMSE (forward_write.json: 14.447 mV) is
therefore measured against labels that carry a transcription-quantization
component which the surrogate can never reproduce.  This script quantifies that
component for write and reports the error three ways:

  Mode 1  (as reported)      raw  mu/sigma  prediction  vs  quantized label
  Mode 2  (grid-aligned)     prediction quantized onto the same grid first
  Mode 3  (deconvolved)      sqrt(RMSE1^2 - mean_jitter^2), jitter = Monte-Carlo
                             label dequantization (independent re-draw of the
                             discarded fractional mV part, propagated through the
                             same z-inversion that produced the Vmin label)
  Mode 4  (midpoint-restored) both label AND prediction shifted by +grid/2 before
                             the z-inversion, then re-scored -- isolates how much
                             of the Vmin error comes from inverting z at a
                             biased-low sigma rather than from label noise

Transcription model (user, 2026-09-06): the write sheet was hand-transcribed and
the fractional mV was DROPPED (floor), not rounded.  Both models are reported:

  DEQUANT='round'   truth ~ U(value - grid/2,  value + grid/2)
  DEQUANT='trunc'   truth ~ U(value,           value + grid)      <- actual

The two have IDENTICAL variance (grid^2/12); they differ only by a +grid/2 mean
shift.  Mode 3 deconvolves a variance, so it is insensitive to the choice --
Mode 4 is the mode that sees the shift.

Replays v_b_forward.py's data path, split, surrogate load and per-condition Vmin
scoring exactly (same SEED=42 grouped split, same checkpoints) so that Mode 1
reproduces forward_write.json before any analysis is added.

    .venv/bin/python manuscript/code/quantization_noise.py
"""
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
MQ_MV = 1.0                        # transcription grid: 1 mV
R_DRAWS = 300                      # dequantization MC draws
MIRROR_FREE_COLS = ["sk", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]

MODES = [
    # Write (Vtrip) batch only -- read was transcribed properly (decimals kept),
    # so its RMSE carries no transcription-quantization component to attribute.
    ("write", "load_final_vtrip", "vtrip_avg", "vtrip_std", -40.0, "_write"),
]
LOADERS = {"load_final_snmr": load_final_snmr, "load_final_vtrip": load_final_vtrip}


def q_round_mV(x):
    """Round an array in volts onto the integer-mV grid."""
    return np.round(x * 1e3) / 1e3


def q_trunc_mV(x):
    """Truncate an array in volts onto the integer-mV grid (floor for positives)."""
    return np.trunc(x * 1e3) / 1e3


def grid_mV(v):
    """Transcription grid size (mV) of a value v in volts: the coarsest of
    {1, 0.1, 0.01} mV on which v is exactly representable (audit: the write
    batch is 69 % integer-mV, 73 % 0.1-mV, the rest 0.01-mV)."""
    mv = float(v) * 1e3
    for g in (1.0, 0.1, 0.01):
        if abs(mv / g - np.round(mv / g)) < 1e-6:
            return g
    return 0.01       # fallback: finest observed transcription grid


def grid_volts(v):
    """Transcription grid size in volts."""
    return grid_mV(v) * 1e-3


def transcription_audit(df, AVG, STD):
    """Which cells lost their decimals, and was it floor or round?  (no surrogate)

    Two facts, both measured inside the sheet:

    (a) The transcription style is set by V_op, not by cell -- 0.4 V keeps its
        decimals, 0.6/0.7 V are almost all integers, 0.5 V is the one genuinely
        mixed level.  Any integer-vs-exact contrast pooled over V_op is therefore
        a V_op contrast in disguise.

    (b) Floor vs round, tested at 0.5 V only.  Reference for a condition's 0.5 V
        cell is the quadratic through its OWN 0.4/0.6/0.7 cells -- built the same
        way for both classes, so the reference's own quantization cancels in the
        difference:  floor -> +grid/2 = +0.5 mV,  round -> 0.
    """
    def is_int(mv):
        return np.abs(mv - np.round(mv)) < 1e-6

    out = {"int_grid_frac_by_vop": {}, "floor_vs_round_at_0p5V": {}}
    for c in (AVG, STD):
        by = df.groupby("vop")[c].apply(lambda s: float(is_int(s.to_numpy(float)).mean()))
        out["int_grid_frac_by_vop"][c] = {f"{v:.1f}": f for v, f in by.items()}

    for c in (AVG, STD):
        r_int, r_exact = [], []
        for _, g in df.groupby("deck_no"):
            g = g.sort_values("vop")
            v = g["vop"].to_numpy(float); y = g[c].to_numpy(float)
            if len(v) != 4 or not np.isclose(v[1], 0.5):
                continue
            p = np.polyfit(v[[0, 2, 3]], y[[0, 2, 3]], 2)
            (r_int if is_int(y[1]) else r_exact).append(y[1] - np.polyval(p, 0.5))
        a, b = np.array(r_int), np.array(r_exact)
        sea, seb = a.std(ddof=1) / np.sqrt(len(a)), b.std(ddof=1) / np.sqrt(len(b))
        d, sed = float(b.mean() - a.mean()), float(np.hypot(sea, seb))
        out["floor_vs_round_at_0p5V"][c] = dict(
            n_integer=len(a), n_exact=len(b),
            resid_integer_mV=float(a.mean()), resid_exact_mV=float(b.mean()),
            diff_mV=d, diff_se_mV=sed, z_vs_round=d / sed,
            floor_predicts_mV=0.5, round_predicts_mV=0.0)
        print(f"  transcription[{c}] 0.5 V exact-minus-integer {d:+.3f} +- {sed:.3f} mV "
              f"(floor +0.500 / round 0.000)  z={d/sed:+.1f}")
    return out


def per_condition_vmin(mu, sig, X_te, te_group):
    """v_b_forward.py scoring: per-condition inverse-z Vmin + censored mask.

    mu, sig: (n_te,) prediction-or-label margin statistics (V).
    Returns (vmin (n_cond,), censored (n_cond,) bool).
    """
    vt, cs = [], []
    for gid in np.unique(te_group):
        m = te_group == gid
        o = np.argsort(X_te[m, VOP_COL])
        vg = X_te[m, VOP_COL][o]
        z = mu[m][o] / (sig[m][o] + 1e-12)
        a, ca = compute_vmin_from_z(z.reshape(1, -1), Z_TARGET, vops=vg, return_censored=True)
        vt.append(a[0]); cs.append(bool(ca[0]))
    return np.array(vt), np.array(cs)


def rmse_mV(err):
    return float(np.sqrt(np.mean(err ** 2)))


def run_mode(name, loader_name, AVG, STD, TEMP, TAG):
    print(f"\n================ {name.upper()} (TEMP {TEMP} C) ================")
    audit = Audit()
    df = LOADERS[loader_name](audit)
    n_raw = len(df)
    df = df[df[AVG].notna() & df[STD].notna() & df["n_mc"].notna()].copy()

    X = df[DEVICE_COLS + ["vop"]].to_numpy(float)
    y = df[[AVG, STD]].to_numpy(float) * 1e-3                       # mV -> V
    n_mc = np.clip(df["n_mc"].to_numpy(float), 2, None)
    y_noise = np.column_stack([np.maximum(y[:, 1] / np.sqrt(n_mc), 1e-9),
                               np.maximum(y[:, 1] / np.sqrt(2 * n_mc), 1e-9)])

    _, cond_idx = np.unique(X[:, :N_DEVICE], axis=0, return_inverse=True)
    X_tr, X_te, y_tr, y_te = grouped_train_test_split(X, y, cond_idx, 0.15, SEED)
    _, _, noise_tr, _ = grouped_train_test_split(X, y_noise, cond_idx, 0.15, SEED)

    ckpt = RESULTS / f"surrogate_vb{TAG}.pth"
    surr = Surrogate.load(ckpt, X_tr, y_tr, device="cpu", n_device=N_DEVICE)
    mu_p, _, sig_p, _ = surr.predict(X_te)

    _, te_group = np.unique(X_te[:, :N_DEVICE], axis=0, return_inverse=True)

    # measured (quantized) labels
    vmin_t, cens_t = per_condition_vmin(y_te[:, 0], y_te[:, 1], X_te, te_group)

    # Mode 1: raw prediction vs quantized label
    vmin_1, _ = per_condition_vmin(mu_p, sig_p, X_te, te_group)
    # scored == v_b_forward.py: censored comes from the TRUE label z only; a
    # prediction that is itself left-censored (finite Vmin) is still scored.
    sc1 = ~cens_t & ~np.isnan(vmin_t) & ~np.isnan(vmin_1)
    e1 = (vmin_1[sc1] - vmin_t[sc1]) * 1e3

    # Mode 2: prediction quantized onto the transcription grid, then inverted
    mode2 = {}
    for qname, qf in [("round", q_round_mV), ("trunc", q_trunc_mV)]:
        vmin_2, _ = per_condition_vmin(qf(mu_p), qf(sig_p), X_te, te_group)
        sc2 = ~cens_t & ~np.isnan(vmin_t) & ~np.isnan(vmin_2)
        e2 = (vmin_2[sc2] - vmin_t[sc2]) * 1e3
        mode2[qname] = dict(rmse_mV=rmse_mV(e2), n=int(sc2.sum()))
        print(f"  Mode2[{qname:5s}] Vmin RMSE {rmse_mV(e2):7.3f} mV  n={sc2.sum()}")

    # Mode 4: midpoint restoration.  Under truncation the MMSE point estimate of
    # the discarded part is +grid/2.  The GP was TRAINED on truncated labels, so
    # it predicts on the truncated scale -- restore BOTH sides by the same
    # per-cell +grid/2 and re-score.  mu/sigma RMSE is unchanged by construction;
    # only the nonlinear z = mu/sigma inversion moves.
    half_mu = 0.5 * np.array([grid_volts(v) for v in y_te[:, 0]])
    half_sig = 0.5 * np.array([grid_volts(v) for v in y_te[:, 1]])
    vmin_t4, cens_t4 = per_condition_vmin(y_te[:, 0] + half_mu, y_te[:, 1] + half_sig,
                                          X_te, te_group)
    vmin_p4, _ = per_condition_vmin(mu_p + half_mu, sig_p + half_sig, X_te, te_group)
    sc4 = ~cens_t4 & ~np.isnan(vmin_t4) & ~np.isnan(vmin_p4)
    e4 = (vmin_p4[sc4] - vmin_t4[sc4]) * 1e3
    print(f"  Mode4[restored] Vmin RMSE {rmse_mV(e4):7.3f} mV  n={sc4.sum()}  "
          f"(label Vmin shifted {np.nanmean(vmin_t4 - vmin_t)*1e3:+.3f} mV)")

    # Mode 3: Monte-Carlo label dequantization.  Each transcribed value was
    # rounded to the coarsest grid it lies exactly on (1 / 0.1 / 0.01 mV); the
    # truth is re-drawn uniformly within +-grid/2 of it and propagated through
    # the same z-inversion -- WITHOUT re-quantizing the re-drawn value.
    mu_t, sig_t = y_te[:, 0], y_te[:, 1]
    cond_id = np.unique(te_group)
    rmse1 = rmse_mV(e1)
    mode3 = {}
    # lo = lower edge of the redraw interval, in units of the grid.
    #   round -> U(-g/2, +g/2)   trunc -> U(0, +g)  (fractional part was dropped)
    for qname, lo in [("round", -0.5), ("trunc", 0.0)]:
        rng = np.random.default_rng(1234)
        j2 = np.zeros(len(cond_id))       # per-condition label jitter variance (V^2)
        jshift = np.full(len(cond_id), np.nan)   # mean Vmin shift vs the transcribed label
        for i, gid in enumerate(cond_id):
            m = te_group == gid
            if not sc1[i]:
                continue
            o = np.argsort(X_te[m, VOP_COL])
            vg = X_te[m, VOP_COL][o]
            mu_g = mu_t[m][o]; sig_g = sig_t[m][o]
            g_mu = np.array([grid_volts(v) for v in mu_g])
            g_sig = np.array([grid_volts(v) for v in sig_g])
            vj = np.empty(R_DRAWS)
            for r in range(R_DRAWS):
                mu_alt = mu_g + (lo + rng.uniform(0.0, 1.0, size=len(mu_g))) * g_mu
                sig_alt = sig_g + (lo + rng.uniform(0.0, 1.0, size=len(sig_g))) * g_sig
                z = mu_alt / (sig_alt + 1e-12)
                a, _ = compute_vmin_from_z(z.reshape(1, -1), Z_TARGET, vops=vg,
                                           return_censored=True)
                vj[r] = a[0]
            vv = vj[~np.isnan(vj)]
            j2[i] = float(vv.var()) if len(vv) > 1 else 0.0
            if len(vv):
                jshift[i] = float(vv.mean()) - vmin_t[i]
        j2_sc = j2[sc1]
        jitter_rms = float(np.sqrt(np.mean(j2_sc)))
        deconv = float(np.sqrt(max(rmse1 ** 2 - float(np.mean(j2_sc)) * 1e6, 0.0)))
        shift = float(np.nanmean(jshift[sc1])) * 1e3
        mode3[qname] = dict(jitter_rms_mV=jitter_rms * 1e3,
                            jitter_median_mV=float(np.sqrt(np.median(j2_sc))) * 1e3,
                            deconv_rmse_mV=deconv, mean_vmin_shift_mV=shift)
        print(f"  Mode3[{qname:5s}] jitter RMS {jitter_rms*1e3:6.3f} mV  "
              f"mean Vmin shift {shift:+6.3f} mV  ->  deconvolved {deconv:7.3f} mV "
              f"(from {rmse1:.3f})")

    # mu/sigma RMSE, raw and quantized-pred
    mu_e = (mu_p - y_te[:, 0]) * 1e3
    sig_e = (sig_p - y_te[:, 1]) * 1e3
    print(f"  mu RMSE {rmse_mV(mu_e):6.3f} mV   sigma RMSE {rmse_mV(sig_e):6.3f} mV")
    mu_eq = (q_round_mV(mu_p) - y_te[:, 0]) * 1e3
    sig_eq = (q_round_mV(sig_p) - y_te[:, 1]) * 1e3
    print(f"  mu RMSE (Q-pred) {rmse_mV(mu_eq):6.3f} mV   "
          f"sigma RMSE (Q-pred) {rmse_mV(sig_eq):6.3f} mV")

    # fraction of the transcription that lost its decimals, whole batch and holdout
    def int_frac(mv):
        return float(np.mean(np.abs(mv - np.round(mv)) < 1e-6))
    grid_audit = {
        f"{c}_int_grid_frac_all": int_frac(df[c].to_numpy(float)) for c in (AVG, STD)}
    grid_audit.update({f"{AVG}_int_grid_frac_holdout": int_frac(y_te[:, 0] * 1e3),
                       f"{STD}_int_grid_frac_holdout": int_frac(y_te[:, 1] * 1e3)})
    grid_audit.update(transcription_audit(df, AVG, STD))

    out = dict(
        mode=name, temp=TEMP, z_target=Z_TARGET, seed=SEED, grid_mV=MQ_MV,
        n_rows_raw=n_raw, n_rows_used=len(df), n_train=len(X_tr), n_holdout=len(X_te),
        grid_audit=grid_audit,
        mu_rmse_mV=rmse_mV(mu_e), sigma_rmse_mV=rmse_mV(sig_e),
        mu_rmse_Qpred_mV=rmse_mV(mu_eq), sigma_rmse_Qpred_mV=rmse_mV(sig_eq),
        vmin_rmse_mV_mode1_raw=rmse1, vmin_n_scored=int(sc1.sum()),
        vmin_mean_err_mV=float(np.mean(e1)),
        mode2_quantized_pred=mode2,
        mode3_deconvolved=mode3,
        mode4_midpoint_restored=dict(rmse_mV=rmse_mV(e4), n=int(sc4.sum()),
                                     mean_label_vmin_shift_mV=float(
                                         np.nanmean(vmin_t4 - vmin_t)) * 1e3),
        # kept for backward compatibility with the numbers already in the draft
        vmin_rmse_mV_mode3_deconv=mode3["round"]["deconv_rmse_mV"],
        vmin_label_jitter_rms_mV=mode3["round"]["jitter_rms_mV"],
        vmin_label_jitter_median_mV=mode3["round"]["jitter_median_mV"],
    )
    return out


def main():
    torch.manual_seed(SEED)
    all_out = {}
    for args in MODES:
        o = run_mode(*args)
        all_out[o["mode"]] = o
    json.dump(all_out, open(RESULTS / "quantization_noise.json", "w"), indent=2)
    print(f"\nsaved {RESULTS}/quantization_noise.json")


if __name__ == "__main__":
    main()