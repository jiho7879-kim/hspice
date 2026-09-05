"""Fig. 1-9  ->  figures/fig{n}_*.png|pdf     (LEDGER F001-F009)

Every panel is drawn from a file already in results/ (or, for Fig. 2, from the
raw design coordinates).  Nothing is re-fitted and nothing is re-derived here --
if a number is not in results/, it does not appear in a figure.

    .venv/bin/python manuscript/code/gen_figures.py [--only 3]
"""
import argparse
import json

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

import _paths  # noqa: F401
from _paths import DEVICE_COLS, FIGURES, RESULTS, V_T0, Z_EFF, Z_TARGET

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
    # text is serif, so math must be too -- the default sans mathtext puts a
    # different typeface inside every $V_{min}$ on the page.
    "mathtext.fontset": "dejavuserif",
    "axes.unicode_minus": True,
    "savefig.facecolor": "white",
    "axes.axisbelow": True,
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8.5,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.4,
    "lines.linewidth": 1.1,
    "figure.dpi": 300,
})
COL, DCOL = 3.5, 7.16          # IEEE single / double column width, inches
C_READ, C_WRITE = "#1f4e79", "#a63603"
C_ACC = "#2a7f62"

ap = argparse.ArgumentParser()
ap.add_argument("--only", type=int, default=None)
args = ap.parse_args()


def load(name):
    return json.load(open(RESULTS / name))


def save(fig, n, slug):
    fig.tight_layout(pad=0.4)
    for ext in ("png", "pdf"):
        fig.savefig(FIGURES / f"fig{n}_{slug}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote figures/fig{n}_{slug}.png|pdf")


def want(n):
    return args.only is None or args.only == n


def sgn(x, fmt="+.1f"):
    """Formatted number with a typographic minus, not a hyphen."""
    return format(x, fmt).replace("-", "−")


# =============================================================================
# Fig. 1 -- pipeline schematic
# =============================================================================
if want(1):
    print("Fig. 1  pipeline")
    fig, ax = plt.subplots(figsize=(DCOL, 2.05))
    ax.set_xlim(0, 100); ax.set_ylim(0, 34); ax.axis("off"); ax.grid(False)

    def box(x, y, w, h, text, fc="#eef2f7", ec="#33475b", fs=7.5, bold=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6",
                                    fc=fc, ec=ec, lw=0.9))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, fontweight="bold" if bold else "normal")

    def arrow(x0, y0, x1, y1, style="-|>", ls="-", c="#33475b"):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style,
                                     mutation_scale=9, lw=0.9, ls=ls, color=c,
                                     shrinkA=0, shrinkB=0))

    box(1, 14, 17, 12, "9 process axes\n$+\\;V_{op}$\n(Table II)")
    box(22, 14, 20, 12, "GP posterior\n$\\hat\\mu(\\mathbf{x},V)$, "
                        "$\\hat\\sigma(\\mathbf{x},V)$\nnoise-aware", fc="#e3ecf7")
    box(46, 14, 21, 12, "physics layer\n$z=\\mu/\\sigma$\n"
                        "$z(V_{min})=Z_{\\mathrm{eff}}$", fc="#e3ecf7")
    box(71, 19, 27, 8, "forward:  $V_{min}(\\mathbf{x})$", fc="#e8f3ee",
        ec=C_ACC, bold=True)
    box(71, 6, 27, 8, "inverse:  $x_j^{*}$ s.t. $V_{min}=V^{*}$",
        fc="#fdeee4", ec=C_WRITE, bold=True)

    arrow(18, 20, 22, 20); arrow(42, 20, 46, 20); arrow(67, 20, 71, 23)
    arrow(84.5, 19, 84.5, 14, style="<|-", c=C_WRITE)
    ax.text(86, 16.5, "axis-wise bisection\n(Sec. IV-F)", fontsize=6.6,
            color=C_WRITE, va="center", ha="left")
    box(46, 1, 21, 9, "lobe correction\n$Z_{\\mathrm{eff}}=Z_t+z_{bias}$",
        fc="#fdeee4", ec=C_WRITE, fs=7)
    arrow(56.5, 10, 56.5, 14, c=C_WRITE)
    ax.text(56.5, 30, "one GP fit per mode, then every query is free",
            ha="center", fontsize=7, style="italic", color="#55636f")
    save(fig, 1, "pipeline")

# =============================================================================
# Fig. 2 -- design of experiments
# =============================================================================
if want(2):
    print("Fig. 2  design")
    from src.final_data import Audit, load_final_snmr
    df = load_final_snmr(Audit())
    d = df.drop_duplicates(subset=DEVICE_COLS)
    fig, axes = plt.subplots(1, 2, figsize=(DCOL, 2.7))

    a = axes[0]
    a.scatter(d["cn"], d["pu"], s=1.4, alpha=0.35, c=C_READ, lw=0)
    a.axhline(0, color="k", lw=0.6); a.axvline(0, color="k", lw=0.6)
    for (x, y, lab, w) in [(-42, 42, "FSG", "45 %"), (42, 42, "SSG", "20 %"),
                           (-42, -42, "FFG", "20 %"), (42, -42, "SFG", "15 %")]:
        a.text(x, y, f"{lab}\n{w}", ha="center", va="center", fontsize=7,
               bbox=dict(fc="w", ec="0.6", lw=0.5, alpha=0.9, pad=1.6))
    a.set_xlabel("$c_n$: NMOS $V_{th}$ shift (mV)")
    a.set_ylabel("$p_u$: PMOS $V_{th}$ shift (mV)")
    a.set_title("(a) quadrant-weighted read design")

    b = axes[1]
    lpg, lpd = d["l_com"] + d["l_sk"], d["l_com"] - d["l_sk"]
    b.scatter(lpg, lpd, s=1.4, alpha=0.35, c=C_ACC, lw=0)
    lim = [0.60, 1.40]
    b.plot(lim, lim, color="k", lw=0.7, ls="--", label="perfect tracking")
    b.set_xlim(lim); b.set_ylim(lim)
    b.set_xlabel("pass-gate local $\\sigma$ multiplier")
    b.set_ylabel("pull-down local $\\sigma$ multiplier")
    b.set_title("(b) common/skew split $\\Rightarrow$ tracking band")
    b.legend(loc="upper left", frameon=False)
    r = np.corrcoef(lpg, lpd)[0, 1]
    b.text(0.97, 0.05, f"corr = {r:.2f}", transform=b.transAxes, ha="right",
           fontsize=7)
    save(fig, 2, "design")

# =============================================================================
# Fig. 3 -- forward accuracy
# =============================================================================
if want(3):
    print("Fig. 3  forward accuracy")
    fig, axes = plt.subplots(1, 2, figsize=(DCOL, 2.9))
    for ax, tag, mode, c, j in ((axes[0], "", "read (SNM, 125 $^\\circ$C)", C_READ,
                                "forward.json"),
                                (axes[1], "_write", "write ($V_{trip}$, $-40$ $^\\circ$C)",
                                 C_WRITE, "forward_write.json")):
        z = np.load(RESULTS / f"forward_vmin{tag}.npz")
        m, p, cen = z["vmin_true"], z["vmin_pred"], z["censored"]
        r = load(j)
        # `censored` marks the floor clamp only; conditions whose crossing lies above the
        # grid come back NaN. Both are excluded from the reported RMSE, so the legend has
        # to count them out too or it contradicts the n printed in the same panel.
        ok = ~cen & np.isfinite(m) & np.isfinite(p)
        lo, hi = 0.38, 0.82
        ax.plot([lo, hi], [lo, hi], color="k", lw=0.7)
        ax.fill_between([lo, hi], [lo - .01, hi - .01], [lo + .01, hi + .01],
                        color="k", alpha=0.10, lw=0, label="$\\pm$10 mV")
        ax.scatter(m[ok], p[ok], s=7, c=c, alpha=0.55, lw=0,
                   label=f"scored ({ok.sum()} of {cen.size};"
                         f" {cen.size - ok.sum()} censored or off-grid)")
        assert ok.sum() == r["vmin_conditions_scored"], "legend count ≠ reported n"
        ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
        ax.set_xlabel("reference $V_{min}$ (V)")
        ax.set_ylabel("surrogate $V_{min}$ (V)")
        ax.set_title(mode)
        ax.text(0.04, 0.96, f"RMSE {r['vmin_rmse_mV_holdout']:.2f} mV\n"
                            f"$n$ = {r['vmin_conditions_scored']}",
                transform=ax.transAxes, va="top", fontsize=7)
        ax.legend(loc="lower right", frameon=False)
    save(fig, 3, "forward")

# =============================================================================
# Fig. 4 -- fixed-corner validation
# =============================================================================
if want(4):
    print("Fig. 4  corner validation")
    fig, axes = plt.subplots(1, 2, figsize=(DCOL, 2.9))
    for ax, j, ttl, c in ((axes[0], "corner.json", "read @ 125 $^\\circ$C", C_READ),
                          (axes[1], "corner_write.json",
                           "write @ $-40$ $^\\circ$C", C_WRITE)):
        r = load(j)
        cs = r["corners"]
        names = [q["corner"] for q in cs]
        x = np.arange(len(cs))
        meas = np.array([q["vmin_meas"] for q in cs])
        pred = np.array([q["vmin_pred"] for q in cs])
        cen = np.array([q["censored_meas"] or q["censored_pred"] for q in cs])
        ax.bar(x - 0.19, meas, 0.36, color=c, alpha=0.85, label="independent reference run")
        ax.bar(x + 0.19, pred, 0.36, color=c, alpha=0.35, label="surrogate")
        ax.axhline(V_T0, color="k", ls="--", lw=0.8)
        ax.text(len(cs) - 0.45, V_T0 + 0.004, "$V_{T0}$ = 0.625 V", fontsize=6.6,
                ha="right", va="bottom")
        for xi, q, cc in zip(x, cs, cen):
            if cc:
                ax.text(xi, 0.362, "censored\n($<$0.4 V)", ha="center",
                        fontsize=6.2, color="0.35")
            else:
                # keep the error label clear of the V_T0 rule: a corner sitting
                # just under spec would otherwise print its number on the line.
                top = max(q["vmin_meas"], q["vmin_pred"]) + 0.008
                if V_T0 - 0.012 < top < V_T0 + 0.010:
                    top = V_T0 + 0.013
                ax.text(xi, top, f"{sgn(q['err_mV'])} mV", ha="center", fontsize=6.6)
        ax.set_xticks(x); ax.set_xticklabels(names)
        ax.set_ylim(0.35, 0.70)
        ax.set_ylabel("$V_{min}$ (V)")
        ax.set_title(ttl)
        ax.legend(loc="upper left", frameon=False, ncol=1)
    save(fig, 4, "corner")

# =============================================================================
# Fig. 5 -- inverse: T0 boundary in the (cn, pu) plane
# =============================================================================
if want(5):
    print("Fig. 5  inverse boundary")
    z = np.load(RESULTS / "inverse_boundary.npz")
    inv = load("inverse.json")
    cn, pu, vmin = z["cn"], z["pu"], z["vmin"]
    pu_axis, cn_star = z["pu_axis"], z["cn_star"]
    fig, ax = plt.subplots(figsize=(COL, 2.9))
    CN, PU = np.meshgrid(cn, pu)          # 'xy' -- matches how v_e_inverse built VM
    lv = np.arange(0.40, 0.76, 0.025)
    cf = ax.contourf(CN, PU, vmin, levels=lv, cmap="viridis", extend="both")
    ax.contour(CN, PU, vmin, levels=[V_T0], colors="w", linewidths=3.0)
    good = np.isfinite(cn_star)
    ax.plot(cn_star[good], pu_axis[good], color="#c1121f", lw=1.1, ls="--",
            label="$V_{T0}$ contour / axis-wise exact solution")
    ms = inv["multistart"]
    ax.scatter([m["cn_solution"] for m in ms], [m["pu"] for m in ms], s=16,
               marker="o", facecolor="none", edgecolor="w", lw=0.9,
               label="multistart converged (12/12)")
    ax.set_xlabel("$c_n$: NMOS $V_{th}$ shift (mV)")
    ax.set_ylabel("$p_u$: PMOS $V_{th}$ shift (mV)")
    ax.set_title("read $V_{min}$ over the two design knobs")
    ax.legend(loc="lower left", frameon=True, framealpha=0.85, fontsize=6.4)
    cb = fig.colorbar(cf, ax=ax, pad=0.02)
    cb.set_label("$V_{min}$ (V)", fontsize=7.5)
    cb.ax.tick_params(labelsize=6.5)
    save(fig, 5, "inverse")

# =============================================================================
# Fig. 6 -- lobe correlation and the correction it forces
# =============================================================================
if want(6):
    print("Fig. 6  lobe correction")
    lob = load("lobe.json")
    cs = lob["conditions"]
    fig, axes = plt.subplots(1, 2, figsize=(DCOL, 2.75))

    a = axes[0]
    order = np.argsort([q["rho_skew"] for q in cs])
    y = np.arange(len(cs))
    rs = np.array([cs[i]["rho_skew"] for i in order])
    se = np.array([cs[i]["se_rho"] for i in order])
    rq = np.array([cs[i]["rho_qq"] for i in order])
    labs = [f"deck {cs[i]['deck']} @ {cs[i]['vop']:.1f} V" for i in order]
    a.errorbar(rs, y, xerr=se, fmt="o", ms=3.4, color=C_READ, lw=0.9,
               capsize=1.8, label="skewness inversion")
    a.scatter(rq, y, s=16, marker="s", facecolor="none", edgecolor=C_ACC,
              lw=0.9, label="quantile-ladder $\\chi^2$")
    a.axvline(lob["rho_pooled"], color=C_WRITE, lw=1.0, ls="--",
              label=f"pooled $\\rho_{{LR}}$ = {sgn(lob['rho_pooled'], '.3f')}")
    a.axvline(0, color="k", lw=0.7)
    a.set_yticks(y); a.set_yticklabels(labs, fontsize=6.2)
    a.set_xlabel("lobe correlation $\\rho_{LR}$")
    a.set_title("(a) two independent estimators agree")
    a.legend(loc="center right", frameon=True, framealpha=0.9, fontsize=6.2)

    b = axes[1]
    cor = lob["corners"]
    names = [c["corner"] for c in cor]
    x = np.arange(len(cor))
    v0 = np.array([c["vmin_meas"] for c in cor])
    v1 = np.array([c["vmin_corrected"] for c in cor])
    FLOOR = 0.35                      # grid floor: SFG's naive Vmin sits on it
    b.bar(x - 0.19, v0, 0.36, color="0.72", label="naive $z$ ($Z_t$ = 6.398)")
    b.bar(x + 0.19, v1, 0.36, color=C_WRITE, alpha=0.85,
          label="lobe-corrected ($Z_{eff}$ = 7.453)")
    b.axhline(V_T0, color="k", ls="--", lw=0.8)
    b.text(-0.45, V_T0 + 0.005, "$V_{T0}$", fontsize=6.6)
    for xi, (a0, a1) in enumerate(zip(v0, v1)):
        b.annotate("", xy=(xi + 0.19, a1), xytext=(xi - 0.19, a0),
                   arrowprops=dict(arrowstyle="->", lw=0.7, color="0.25"))
        b.text(xi, max(a0, a1) + 0.006, f"+{1e3*(a1-a0):.0f} mV", ha="center",
               fontsize=6.4)
        if a0 <= FLOOR + 1e-9:      # a bar drawn at the axis floor reads as absent
            b.text(xi - 0.19, FLOOR + 0.004, "$\\leq$0.35\nclamp", ha="center",
                   va="bottom", fontsize=5.8, color="0.30")
    b.set_xticks(x); b.set_xticklabels(names)
    b.set_ylim(0.33, 0.78)
    b.set_ylabel("read $V_{min}$ (V)")
    b.set_title("(b) correction moves the limiting corner past spec")
    b.legend(loc="upper left", frameon=False, fontsize=6.2)
    save(fig, 6, "lobe")

# =============================================================================
# Fig. 7 -- simulation budget
# =============================================================================
if want(7):
    print("Fig. 7  cost")
    cond, mc = load("cost_conditions.json"), load("cost_mc.json")
    volt, comb = load("cost_voltage.json"), load("cost_combined.json")
    base = cond["baseline"]["vmin_rmse_mV"]
    fig, axes = plt.subplots(1, 3, figsize=(DCOL, 2.55))

    a = axes[0]
    n = [p["n_conditions"] for p in cond["pareto"]]
    v = [p["vmin_rmse_mV"] for p in cond["pareto"]]
    a.plot(n, v, "o-", color=C_READ, ms=3.4)
    a.axhline(base, color="k", ls="--", lw=0.7)
    a.axvline(400, color=C_ACC, lw=0.8, ls=":")
    a.text(430, 16, "knee\n400", fontsize=6.4, color=C_ACC)
    a.set_xscale("log")
    a.set_xlabel("training conditions")
    a.set_ylabel("hold-out $V_{min}$ RMSE (mV)")
    a.set_title("(a) conditions")

    b = axes[1]
    n2 = [p["n_mc"] for p in mc["pareto"]]
    v2 = [p["vmin_rmse_mV"] for p in mc["pareto"]]
    b.plot(n2, v2, "s-", color=C_READ, ms=3.4)
    b.axhline(base, color="k", ls="--", lw=0.7)
    b.set_xscale("log")
    b.set_ylim(6.5, 9.5)
    b.set_xticks(n2); b.set_xticklabels([f"{v:,}" for v in n2], fontsize=6.2)
    b.minorticks_off()
    b.set_xlabel("MC samples per condition")
    b.set_title("(b) MC depth")

    c = axes[2]
    labels = ["base", "$-$1\nlevel", "400\ncond.", "500\nMC", "all\nthree"]
    vals = [base, volt["reduced_on_full"]["vmin_rmse_mV"],
            cond["pareto"][2]["vmin_rmse_mV"],
            [p for p in mc["pareto"] if p["n_mc"] == 500][0]["vmin_rmse_mV"],
            comb["combined_on_full"]["vmin_rmse_mV"]]
    cols = ["0.6", C_READ, C_READ, C_READ, C_WRITE]
    c.bar(np.arange(5), vals, 0.62, color=cols, alpha=0.85)
    c.axhline(base, color="k", ls="--", lw=0.7)
    for i, v3 in enumerate(vals):
        c.text(i, v3 + 0.18, f"{v3:.1f}", ha="center", fontsize=6.4)
    c.set_xticks(np.arange(5))
    c.set_xticklabels(labels, fontsize=6.2)
    c.set_ylim(0, 14)
    c.set_title("(c) one factor vs. all three")
    c.text(4, 12.4, f"{comb['speedup']:.0f}$\\times$\ncheaper", ha="center",
           fontsize=6.6, color=C_WRITE, linespacing=1.1)
    save(fig, 7, "cost")

# =============================================================================
# Fig. 8 -- sensitivity
# =============================================================================
if want(8):
    print("Fig. 8  sensitivity")
    s, sw = load("sensitivity.json"), load("sensitivity_write.json")
    LAB = {"cn": "$c_n$", "sk": "$s_k$", "pu": "$p_u$", "lpu": "$l_{pu}$",
           "l_com": "$l_{com}$", "l_sk": "$l_{sk}$", "mpu": "$m_{pu}$",
           "m_com": "$m_{com}$", "m_sk": "$m_{sk}$"}
    fig, axes = plt.subplots(1, 3, figsize=(DCOL, 2.85))

    def st_panel(ax, key, title, xlab):
        st, stw = s["sobol"]["ST"][key], sw["sobol"]["ST"][key]
        ci, ciw = s["sobol"]["ST_ci"][key], sw["sobol"]["ST_ci"][key]
        order = sorted(DEVICE_COLS, key=lambda c: -st[c])
        y = np.arange(len(order))[::-1]
        for off, src, cis, col, lab in ((+0.20, st, ci, C_READ, "read"),
                                        (-0.20, stw, ciw, C_WRITE, "write")):
            v = np.array([src[c] for c in order])
            e = np.array([[v[i] - cis[c][0], cis[c][1] - v[i]]
                          for i, c in enumerate(order)]).T
            ax.barh(y + off, v, 0.38, color=col, alpha=0.85, label=lab,
                    xerr=np.clip(e, 0, None),
                    error_kw=dict(lw=0.6, capsize=1.3, ecolor="0.25"))
        ax.set_yticks(y); ax.set_yticklabels([LAB[c] for c in order])
        ax.set_xlim(0, 1.0)
        ax.set_xlabel(xlab)
        ax.set_title(title)
        return order

    st_panel(axes[0], "z(0.625V)", "(a) what moves the margin",
             "$S_T$ share of $z(V_{T0})$ variance")
    axes[0].legend(loc="lower right", frameon=False)
    st_panel(axes[1], "sigma(0.625V)", "(b) what moves $\\sigma$",
             "$S_T$ share of $\\sigma(V_{T0})$ variance")

    # (c) the same axes ranked by the free ARD proxy -- the point is that it is flat
    c_ax = axes[2]
    rel, relw = s["ard"]["relevance_mu"], sw["ard"]["relevance_mu"]
    order = sorted(DEVICE_COLS, key=lambda c: -s["sobol"]["ST"]["z(0.625V)"][c])
    y = np.arange(len(order))[::-1]
    c_ax.barh(y + 0.20, [rel[c] for c in order], 0.38, color=C_READ, alpha=0.55)
    c_ax.barh(y - 0.20, [relw[c] for c in order], 0.38, color=C_WRITE, alpha=0.55)
    c_ax.axvline(1 / len(DEVICE_COLS), color="k", lw=0.8, ls="--")
    c_ax.text(1 / len(DEVICE_COLS) + 0.003, -0.35, "equal\nrelevance",
              fontsize=6.0, va="bottom")
    c_ax.set_yticks(y); c_ax.set_yticklabels([LAB[c] for c in order])
    c_ax.set_xlim(0, 0.16)
    c_ax.set_xticks([0, 0.05, 0.10, 0.15])
    c_ax.set_xlabel("ARD relevance $\\lambda^{-1}/\\sum\\lambda^{-1}$")
    c_ax.set_title("(c) the free proxy is flat")
    save(fig, 8, "sensitivity")

# =============================================================================
# Fig. 9 -- where the skew tolerance closes
# =============================================================================
if want(9):
    print("Fig. 9  skew tolerance")
    s = load("sensitivity.json")
    fig, axes = plt.subplots(1, 2, figsize=(DCOL, 2.7))
    for ax, key, ttl in ((axes[0], "z_target", "(a) naive $Z_t$ = 6.398"),
                         (axes[1], "z_eff", "(b) lobe-corrected $Z_{eff}$ = 7.453")):
        t = s["skew_tolerance"][key]
        w = np.array(t["width_map_mV"])                 # (cn, pu)
        cn_a, pu_a = np.array(t["cn_axis"]), np.array(t["pu_axis"])
        im = ax.pcolormesh(cn_a, pu_a, w.T, cmap="RdYlBu", vmin=0,
                           vmax=t["sk_axis_range_mV"], shading="auto")
        ax.contour(cn_a, pu_a, w.T, levels=[t["sk_axis_range_mV"] - 1e-6],
                   colors="k", linewidths=0.8)
        ax.set_xlabel("$c_n$: NMOS $V_{th}$ shift (mV)")
        ax.set_title(ttl)
        ax.text(0.03, 0.03, f"{t['full_range_pct']:.0f} % of the plane\n"
                            f"tolerates every skew", transform=ax.transAxes,
                fontsize=6.4, va="bottom",
                bbox=dict(fc="w", ec="0.6", lw=0.5, alpha=0.9, pad=2))
    axes[0].set_ylabel("$p_u$: PMOS $V_{th}$ shift (mV)")
    cb = fig.colorbar(im, ax=axes, pad=0.015, fraction=0.045)
    cb.set_label("passing $s_k$ width (mV of 40)", fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    for ext in ("png", "pdf"):
        fig.savefig(FIGURES / f"fig9_skew.{ext}", bbox_inches="tight")
    plt.close(fig)
    print("  wrote figures/fig9_skew.png|pdf")

print(f"\nfigures in {FIGURES}")
