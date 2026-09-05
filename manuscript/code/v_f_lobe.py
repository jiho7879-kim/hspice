"""§V-F lobe correction  ->  results/lobe.json   (N040-N042)

SNMR is min(L, R) of the two butterfly lobes. The production flow reports only
mean/std of that minimum and extrapolates a Gaussian to Z_t, which is
optimistic because min-of-two has a fatter lower tail. How optimistic depends
on one number: the lobe correlation rho_LR.

The fab returned a summary table for nine 100k-sample conditions
(python/data/infab_snmr_tail.xlsx) -- shape statistics only, no raw samples.
This script estimates rho_LR from that table by TWO independent routes and
converts the resulting z-bias into mV of Vmin:

  1. skewness inversion (primary).  min(L,R) = (S - |D|)/2 with S = L+R and
     D = L-R independent, so its skewness has a closed form in rho:

         a^2 = 2(1-rho)
         mu2 = 1 - a^2/(2 pi)
         mu3 = -a^3 (2c^3 - c) / 8,      c = sqrt(2/pi)
         g1  = mu3 / mu2^{3/2}                                     (monotone)

     No Monte-Carlo reference table is needed -- invert g1 by bisection.
     (The fab table's skew_ref column reproduces this to 3 decimals.)

  2. quantile-ladder chi2 (cross-check).  Fit the five standardised empirical
     quantiles against min-of-two references on a fine rho grid. The fab only
     evaluated rho in {-0.50,-0.25,0,+0.25}, so its "best rho" is a grid label,
     not an estimate; this refines it.

Everything is evaluated at Z_t = 6.3984 (D-01), NOT at the 6.50 the fab table
was written against -- z-bias is a function of the target quantile.

    .venv/bin/python manuscript/code/v_f_lobe.py
"""
import json
import math

import numpy as np
import pandas as pd

import _paths  # noqa: F401
from _paths import DATA, DEVICE_COLS, RESULTS, V_T0, Z_TARGET

from infab_snmr_tail_diag import _phi_inv, bias_at_target, min_of_two_reference
from src.final_data import Audit, load_final_snmr, load_final_vtrip

SEED = 12345
LADDER = ["p50", "p15.9", "p2.28", "p0.135", "p0.02"]
RHO_GRID = np.round(np.arange(-0.70, 0.001, 0.025), 4)   # for the qq cross-check
N_REF = 2_000_000        # samples per rho in the qq reference
N_SE_REPS = 400          # replicates for the skewness standard error
C = math.sqrt(2.0 / math.pi)
rng = np.random.default_rng(SEED)


# --- closed-form skewness of min(L,R) -----------------------------------------
def skew_min2(rho):
    a2 = 2.0 * (1.0 - rho)
    mu2 = 1.0 - a2 / (2.0 * math.pi)
    mu3 = -(a2 ** 1.5) * (2 * C ** 3 - C) / 8.0
    return mu3 / mu2 ** 1.5


def rho_from_skew(g, lo=-0.999, hi=0.999):
    """Invert skew_min2. Monotone increasing in rho (less negative as rho->1)."""
    if g >= skew_min2(hi):
        return float("nan")
    if g <= skew_min2(lo):
        return float("nan")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if skew_min2(mid) < g:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


assert abs(skew_min2(-0.25) - (-0.2317)) < 2e-3, "closed form disagrees with fab ref"
assert abs(skew_min2(-0.50) - (-0.3741)) < 2e-3, "closed form disagrees with fab ref"
assert abs(rho_from_skew(skew_min2(-0.37)) + 0.37) < 1e-6, "inversion broken"

# --- fab summary table ---------------------------------------------------------
tail = pd.read_excel(DATA / "infab_snmr_tail.xlsx")
tail.columns = [c.replace("naïve", "naive") for c in tail.columns]
n_mc = int(tail["n"].iloc[0])
assert (tail["n"] == n_mc).all(), "mixed sample sizes -- SE must be per-row"

# --- standard error of the sample skewness at this n ---------------------------
# sqrt(6/n) is the Gaussian null value; min-of-two is heavier-tailed, so measure
# the SE by simulation at the pooled rho instead of assuming it.
rho_seed = rho_from_skew(float(tail["skew"].mean()))
_s = rng.standard_normal((N_SE_REPS, n_mc))
_d = rng.standard_normal((N_SE_REPS, n_mc))
_m = (math.sqrt(2 * (1 + rho_seed)) * _s - math.sqrt(2 * (1 - rho_seed)) * np.abs(_d)) / 2
_z = (_m - _m.mean(1, keepdims=True)) / _m.std(1, ddof=0, keepdims=True)
SE_SKEW = float((_z ** 3).mean(1).std(ddof=1))
del _s, _d, _m, _z
print(f"SE(skew) @ n={n_mc}, rho={rho_seed:+.3f}: {SE_SKEW:.5f} "
      f"(Gaussian null sqrt(6/n) = {math.sqrt(6/n_mc):.5f})")

# --- min-of-two quantile references on a fine rho grid -------------------------
ps = [0.5, 0.1587, 0.0228, 0.00135, 0.0002]
qref = {}
for r in RHO_GRID:
    ref = min_of_two_reference(float(r), N_REF, rng)
    qref[float(r)] = np.quantile(ref, ps)
qz_gauss = np.array([_phi_inv(p) for p in ps])

# Blom plotting position for the minimum of n draws -- the Gaussian expectation
# the observed minimum is compared against.
z_min_gauss = _phi_inv((1 - 0.375) / (n_mc + 0.25))

rows = []
for _, r in tail.iterrows():
    emp = np.array([r[f"qz_emp_{k}"] for k in LADDER], float)
    se = np.array([r[f"qz_se_{k}"] for k in LADDER], float)

    rho_skew = rho_from_skew(float(r["skew"]))
    # dg/drho at the estimate -> SE(rho) by the delta method
    h = 1e-4
    dg = (skew_min2(rho_skew + h) - skew_min2(rho_skew - h)) / (2 * h)
    se_rho = SE_SKEW / abs(dg)

    chi2 = {rho: float((((emp - q) / se) ** 2).sum()) for rho, q in qref.items()}
    rho_best = min(chi2, key=chi2.get)
    grid = sorted(chi2)
    i = grid.index(rho_best)
    if 0 < i < len(grid) - 1:                      # parabolic refinement
        y0, y1, y2 = chi2[grid[i - 1]], chi2[grid[i]], chi2[grid[i + 1]]
        step = grid[i + 1] - grid[i]
        denom = y0 - 2 * y1 + y2
        rho_qq = rho_best + (0.5 * step * (y0 - y2) / denom if denom > 0 else 0.0)
    else:
        rho_qq = rho_best
    gauss_chi2 = float((((emp - qz_gauss) / se) ** 2).sum())

    rows.append(dict(deck=int(r["deck"]), vop=float(r["vop"]),
                     z_naive=float(r["z_naive"]), skew=float(r["skew"]),
                     exkurt=float(r["exkurt"]),
                     rho_skew=rho_skew, se_rho=se_rho,
                     rho_qq=float(rho_qq), chi2_at_rho_qq=float(chi2[rho_best]),
                     gauss_chi2=gauss_chi2,
                     obs_min=float(r["obs_min"]),
                     min_ratio=float(r["obs_min"] / z_min_gauss)))

df = pd.DataFrame(rows)
print(f"\n{'deck':>5} {'vop':>4} | {'skew':>7} {'rho_skew':>9} {'+-':>6} | "
      f"{'rho_qq':>7} | {'gauss_chi2':>10} | {'min/E[min]':>10}")
print("-" * 78)
for _, r in df.iterrows():
    print(f"{int(r['deck']):>5} {r['vop']:>4.1f} | {r['skew']:>+7.4f} "
          f"{r['rho_skew']:>+9.3f} {r['se_rho']:>6.3f} | {r['rho_qq']:>+7.3f} | "
          f"{r['gauss_chi2']:>10.1f} | {r['min_ratio']:>10.2f}")

# --- N040: pooled rho + between-condition uniformity ---------------------------
w = 1.0 / df.se_rho ** 2
rho_pool = float((df.rho_skew * w).sum() / w.sum())
se_pool = float(1.0 / math.sqrt(w.sum()))
chi2_unif = float((w * (df.rho_skew - rho_pool) ** 2).sum())
dof_unif = len(df) - 1
# survival function of chi2 without scipy: regularised upper incomplete gamma
# for integer/half-integer dof via the standard series (dof=8 here -> integer k)
k = dof_unif / 2.0
x = chi2_unif / 2.0
if abs(k - round(k)) < 1e-9:                       # even dof -> closed form
    kk = int(round(k))
    p_unif = math.exp(-x) * sum(x ** j / math.factorial(j) for j in range(kk))
else:
    p_unif = float("nan")

spread = float(df.rho_skew.std(ddof=1))
print(f"\nN040  rho_LR (skewness, pooled) = {rho_pool:+.3f} +- {se_pool:.3f} (SE)")
print(f"      between-condition SD = {spread:.3f}   "
      f"chi2 = {chi2_unif:.1f}, dof {dof_unif}, p = {p_unif:.2e}")
print(f"      rho_LR (quantile ladder, mean) = {df.rho_qq.mean():+.3f} "
      f"(SD {df.rho_qq.std(ddof=1):.3f})")
print(f"      Gaussian: rejected in {int((df.gauss_chi2 > 3 * 5).sum())}/{len(df)} "
      f"conditions (chi2 > 3*dof); skew < 0 in {int((df['skew'] < 0).sum())}/{len(df)}; "
      f"obs_min/E[min] mean {df.min_ratio.mean():.2f} (Gaussian = 1.00)")

# --- z-bias at Z_t, per condition and pooled -----------------------------------
def zbias(rho):
    _, b = bias_at_target(float(rho), Z_TARGET, np.random.default_rng(SEED))
    return float(b)


df["zbias_skew"] = [zbias(r) for r in df.rho_skew]
df["zbias_qq"] = [zbias(r) for r in df.rho_qq]
zb_pool = zbias(rho_pool)
zb_lo, zb_hi = float(df.zbias_skew.min()), float(df.zbias_skew.max())
print(f"\n      zbias @ Z_t={Z_TARGET:.4f}: pooled {zb_pool:+.3f} sigma "
       f"[{zb_lo:+.3f}, {zb_hi:+.3f}]  ->  Z_eff = {Z_TARGET + zb_pool:.3f}")
print(f"      (D-02 pinned +0.919 from the fab's 4-point rho grid; the "
      f"continuous fit gives {zb_pool:+.3f})")

# --- dz/dVop slopes, needed to turn sigma into mV ------------------------------
audit = Audit()


def band_slope(frame, avg, std):
    """Median d z / d Vop across conditions, over the 0.6-0.7 V spec band."""
    g = frame[frame["vop"].isin([0.6, 0.7])].copy()
    g["z"] = g[avg] / g[std]
    piv = g.pivot_table(index=DEVICE_COLS, columns="vop", values="z")
    piv = piv.dropna()
    s = (piv[0.7] - piv[0.6]) / 0.1
    return float(s.median()), float(s.quantile(0.25)), float(s.quantile(0.75)), len(s)


read = load_final_snmr(audit)
write = load_final_vtrip(audit)
s_read = band_slope(read, "snmr_avg", "snmr_std")
s_write = band_slope(write, "vtrip_avg", "vtrip_std")
print(f"\n      dz/dVop median: read {s_read[0]:.1f} /V (IQR {s_read[1]:.1f}-{s_read[2]:.1f}, "
      f"n={s_read[3]})   write {s_write[0]:.1f} /V (IQR {s_write[1]:.1f}-{s_write[2]:.1f}, "
      f"n={s_write[3]})")

# --- N041/N042: corner-local conversion and the T0 headroom --------------------
corner = json.load(open(RESULTS / "corner.json"))
corner_rows = []
for c in corner["corners"]:
    vops, z = np.array(c["vops"], float), np.array(c["z_meas"], float)
    lo, hi = np.searchsorted(vops, 0.6), np.searchsorted(vops, 0.7)
    slope = (z[hi] - z[lo]) / (vops[hi] - vops[lo])          # local, spec band
    z_t0 = c["z_at_T0_meas"]
    # Vmin after the correction: the Vop where z reaches Z_t + zbias
    z_eff = Z_TARGET + zb_pool
    v_corr = float(np.interp(z_eff, z, vops)) if z_eff <= z[-1] else float("nan")
    corner_rows.append(dict(
        corner=c["corner"], slope_per_V=float(slope),
        vmin_meas=c["vmin_meas"], vmin_corrected=v_corr,
        d_vmin_mV=(v_corr - c["vmin_meas"]) * 1e3,
        vmin_shift_from_slope_mV=zb_pool / slope * 1e3,
        z_at_T0=z_t0,
        zbias_headroom=z_t0 - Z_TARGET,                       # max bias that keeps T0
        t0_pass_naive=bool(z_t0 >= Z_TARGET),
        t0_pass_corrected=bool(z_t0 >= z_eff),
        t0_margin_corrected_mV=(V_T0 - v_corr) * 1e3))

print(f"\n{'corner':>7} | {'dz/dV':>7} | {'Vmin':>7} {'Vmin_corr':>10} {'shift':>8} | "
      f"{'z(T0)':>6} {'headroom':>9} | T0 naive/corr")
print("-" * 84)
for c in corner_rows:
    print(f"{c['corner']:>7} | {c['slope_per_V']:>7.1f} | {c['vmin_meas']:>6.4f}V "
          f"{c['vmin_corrected']:>9.4f}V {c['d_vmin_mV']:>+7.1f}mV | "
          f"{c['z_at_T0']:>6.3f} {c['zbias_headroom']:>+9.3f} | "
          f"{'PASS' if c['t0_pass_naive'] else 'fail'}/"
          f"{'PASS' if c['t0_pass_corrected'] else 'FAIL'}")

lim = min(corner_rows, key=lambda c: c["zbias_headroom"])
# zbias decreases as rho increases -> the smallest rho whose bias still fits
rho_bound = next((float(r) for r in np.arange(-0.99, 0.99, 0.005)
                  if zbias(r) <= lim["zbias_headroom"]), None)
print(f"\nN041  Vmin optimism from zbias {zb_pool:+.3f} sigma: "
      f"population median slope -> {zb_pool / s_read[0] * 1e3:.0f} mV; "
      f"read-limiting corner {lim['corner']} -> {lim['vmin_shift_from_slope_mV']:.0f} mV")
print(f"N042  T0 headroom at the read-limiting corner {lim['corner']}: "
      f"z(0.625 V) = {lim['z_at_T0']:.3f}, so a correction up to "
      f"{lim['zbias_headroom']:+.3f} sigma keeps sign-off (rho_LR >= {rho_bound:+.3f}).")
print(f"      measured {zb_pool:+.3f} sigma {'EXCEEDS' if zb_pool > lim['zbias_headroom'] else 'is inside'} "
      f"that headroom -> corrected Vmin {lim['vmin_corrected']:.4f} V, "
      f"T0 margin {lim['t0_margin_corrected_mV']:+.1f} mV")

out = dict(
    z_target=Z_TARGET, v_t0=V_T0, seed=SEED, n_mc=n_mc, n_conditions=len(df),
    se_skew=SE_SKEW, se_skew_gaussian_null=math.sqrt(6 / n_mc),
    conditions=df.to_dict("records"),
    rho_pooled=rho_pool, rho_pooled_se=se_pool,                        # N040
    rho_between_condition_sd=spread,
    uniformity_chi2=chi2_unif, uniformity_dof=dof_unif, uniformity_p=p_unif,
    rho_qq_mean=float(df.rho_qq.mean()), rho_qq_sd=float(df.rho_qq.std(ddof=1)),
    gaussian_rejected=int((df.gauss_chi2 > 15).sum()),
    min_ratio_mean=float(df.min_ratio.mean()), z_min_gauss=z_min_gauss,
    zbias_pooled=zb_pool, zbias_range=[zb_lo, zb_hi],
    z_eff_pooled=Z_TARGET + zb_pool,
    slope_read_median_per_V=s_read[0], slope_read_iqr=[s_read[1], s_read[2]],
    slope_write_median_per_V=s_write[0], slope_write_iqr=[s_write[1], s_write[2]],
    vmin_optimism_population_mV=zb_pool / s_read[0] * 1e3,             # N041
    corners=corner_rows,
    limiting_corner=lim["corner"],                                     # N042
    zbias_headroom_sigma=lim["zbias_headroom"],
    rho_lower_bound_for_T0=rho_bound,
    headroom_exceeded=bool(zb_pool > lim["zbias_headroom"]),
    write_rho_measurable=False,   # D-03: no left/right split MC in the write batch
    qc_audit=audit.records)
json.dump(out, open(RESULTS / "lobe.json", "w"), indent=2, default=str)
print(f"\nsaved {RESULTS}/lobe.json")
