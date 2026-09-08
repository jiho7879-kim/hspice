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
from matplotlib.colors import TwoSlopeNorm

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

    # No table number here: the axis table is II in v4.0/B/C and III in D, and one
    # shared figure cannot cite both. The box is self-explanatory without it.
    box(1, 14, 17, 12, "9 process axes\n$+\\;V_{op}$")
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
    a.set_xlabel("$\\Delta V_{th,N}$: NMOS $V_{th}$ shift (mV)")
    a.set_ylabel("$\\Delta V_{th,P}$: PMOS $V_{th}$ shift (mV)")
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
    # One axes for both modes: the point of the figure is that each mode is
    # limited by a *different* corner (read FSG, write SFG), and side-by-side
    # panels make the reader hold two y-axes in their head to see it.
    print("Fig. 4  corner validation (read + write merged)")
    fig, ax = plt.subplots(figsize=(DCOL, 3.1))
    read, write = load("corner.json"), load("corner_write.json")
    names = [q["corner"] for q in read["corners"]]
    assert [q["corner"] for q in write["corners"]] == names, "corner order differs"
    x = np.arange(len(names))

    W = 0.19
    for cs, c, off, lbl in ((read["corners"], C_READ, -W, "read"),
                            (write["corners"], C_WRITE, +W, "write")):
        # the limiting corner gets a heavy outline instead of an arrow: with four
        # bars per group an annotation collides with the error labels and legend
        live = [(i, q) for i, q in enumerate(cs) if not q["censored_meas"]]
        i_lim = max(live, key=lambda t: t[1]["vmin_meas"])[0]
        edges = [1.1 if i == i_lim else 0.0 for i in range(len(cs))]
        meas = np.array([q["vmin_meas"] for q in cs])
        pred = np.array([q["vmin_pred"] for q in cs])
        ax.bar(x + off - W / 2, meas, W, color=c, alpha=0.85,
               edgecolor="k", linewidth=edges, label=f"{lbl} — reference")
        ax.bar(x + off + W / 2, pred, W, color=c, alpha=0.32,
               edgecolor="k", linewidth=edges, label=f"{lbl} — surrogate")
        for xi, q in zip(x, cs):
            if q["censored_meas"] or q["censored_pred"]:
                ax.text(xi + off, 0.359, "censored\n($<$0.4 V)", ha="center",
                        va="bottom", fontsize=5.6, color="0.4", rotation=90)
            else:
                top = max(q["vmin_meas"], q["vmin_pred"]) + 0.006
                if V_T0 - 0.012 < top < V_T0 + 0.010:   # keep clear of the V_T0 rule
                    top = V_T0 + 0.013
                lab = f"{sgn(q['err_mV'])}"
                if xi == i_lim:
                    lab += "\nlimiting"
                ax.text(xi + off, top, lab, ha="center", va="bottom",
                        fontsize=6.2, color=c, linespacing=1.25)

    ax.axhline(V_T0, color="k", ls="--", lw=0.8)
    ax.text(len(names) - 0.5, V_T0 + 0.004, "$V_{T0}$ = 0.625 V", fontsize=6.6,
            ha="right", va="bottom")
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_xlim(-0.55, len(names) - 0.45)
    ax.set_ylim(0.35, 0.70)
    ax.set_ylabel("$V_{min}$ (V)")
    ax.set_xlabel("PDK corner (labels above bars are surrogate $-$ reference, mV)")
    ax.legend(loc="upper left", frameon=False, ncol=2, columnspacing=1.2,
              handlelength=1.2, borderaxespad=0.2)
    save(fig, 4, "corner")

# =============================================================================
# Fig. 5 -- inverse: T0 boundary in the (cn, pu) plane
# =============================================================================
if want(5):
    print("Fig. 5  inverse boundary")
    # Read and write share one plane. A cell has to pass BOTH at the same supply,
    # so the usable window is the intersection of the two T0 boundaries -- and the
    # two modes are limited from opposite directions in (cn, pu), which a
    # read-only plane cannot show.
    z = np.load(RESULTS / "inverse_boundary.npz")
    zw = np.load(RESULTS / "inverse_boundary_write.npz")
    inv = load("inverse.json")
    cn, pu, vmin = z["cn"], z["pu"], z["vmin"]
    pu_axis, cn_star = z["pu_axis"], z["cn_star"]
    assert np.allclose(cn, zw["cn"]) and np.allclose(pu, zw["pu"]), \
        "read/write boundary grids differ -- cannot overlay"
    vmin_w = zw["vmin"]

    fig, ax = plt.subplots(figsize=(COL, 3.0))
    CN, PU = np.meshgrid(cn, pu)          # 'xy' -- matches how v_e_inverse built VM
    lv = np.arange(0.40, 0.76, 0.025)
    # The cell has to work in BOTH modes at one supply, so what it costs is
    # max(read, write) -- not read alone. Filling with read makes the region past
    # SFG look best-in-plane when write is in fact driving Vmin up there.
    # NaN = no crossing below the top supply, i.e. worse than the grid can show.
    vcell = np.maximum(np.nan_to_num(vmin, nan=0.85),
                       np.nan_to_num(vmin_w, nan=0.85))
    # Colour is pinned to the spec: everything at or under V_T0 reads cool/blue
    # (passes), everything above reads warm/red (fails). A sequential map makes
    # the reader hunt for the threshold in the colourbar instead of seeing it.
    cf = ax.contourf(CN, PU, vcell, levels=lv, cmap="RdYlBu_r",
                     norm=TwoSlopeNorm(vmin=lv[0], vcenter=V_T0, vmax=lv[-1]),
                     extend="both")

    # the true spec boundary is the T0 contour of the cell, not of either mode.
    # It is kept thin: it lies on top of the read boundary in the upper left and
    # on the write boundary in the lower right, and a heavy line hides both.
    ax.contour(CN, PU, vcell, levels=[V_T0], colors="k", linewidths=1.3)
    ax.plot([], [], color="k", lw=1.3, label="cell $V_{T0}$ boundary")
    good = np.isfinite(cn_star)
    ax.plot(cn_star[good], pu_axis[good], color="#c1121f", lw=1.2, ls="--",
            label="read $V_{T0}$ boundary (axis-wise exact)")
    ax.contour(CN, PU, vmin_w, levels=[V_T0], colors="#ffd166", linewidths=1.6,
               linestyles="-")
    ax.plot([], [], color="#ffd166", lw=1.6, label="write $V_{T0}$ boundary")

    # No "both pass" hatch here: with the cell-Vmin fill the black T0 contour
    # already separates pass from fail, and at T0 the passing region is most of
    # the plane, so hatching it buries the colormap.

    # which mode owns the boundary, said once instead of left to the line colours
    ax.text(-46, 46, "read-limited", fontsize=6.4, ha="center", va="center",
            rotation=41, color="0.15")
    # the write boundary is near-vertical at cn ~ 50 mV, so its label runs up it
    ax.text(55.5, -38, "write-limited", fontsize=6.4, ha="center", va="center",
            rotation=90, color="0.15")

    ms = inv["multistart"]
    # filled white with a dark rim: the solutions sit ON the red boundary line,
    # and an unfilled white ring disappears into both the line and the dark fill
    ax.scatter([m["cn_solution"] for m in ms], [m["pu"] for m in ms], s=20,
               marker="o", facecolor="w", edgecolor="k", lw=0.7, zorder=7,
               label=f"multistart converged ({len(ms)}/{len(ms)})")
    ax.set_xlabel("$\\Delta V_{th,N}$: NMOS $V_{th}$ shift (mV)")
    ax.set_ylabel("$\\Delta V_{th,P}$: PMOS $V_{th}$ shift (mV)")
    ax.set_title("cell $V_{min}=\\max$(read, write) with each mode's boundary")
    ax.legend(loc="lower left", frameon=True, framealpha=0.85, fontsize=6.2)
    cb = fig.colorbar(cf, ax=ax, pad=0.02)
    cb.set_label("cell $V_{min}$ (V)", fontsize=7.5)
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
    volt, comb = load("cost_voltage.json"), load("cost_combined_c400_mc500.json")
    base = cond["baseline"]["vmin_rmse_mV"]
    fig, axes = plt.subplots(1, 3, figsize=(DCOL, 2.55))

    a = axes[0]
    # One curve per random draw of the nested subsets. A single curve invites the
    # reader to trust its wiggles; three show how much of the wiggle is the draw.
    draws = [cond] + [load(f"cost_conditions_s{k}.json") for k in (1, 2)
                      if (RESULTS / f"cost_conditions_s{k}.json").exists()]
    n = [p["n_conditions"] for p in cond["pareto"]]
    for i, d in enumerate(draws):
        a.plot([p["n_conditions"] for p in d["pareto"]],
               [p["vmin_rmse_mV"] for p in d["pareto"]], "o-", color=C_READ, ms=3.0,
               alpha=1.0 if i == 0 else 0.45, lw=1.1 if i == 0 else 0.8,
               label=f"draw {i + 1}")
    if len(draws) > 1:
        band = np.array([[p["vmin_rmse_mV"] for p in d["pareto"]] for d in draws])
        a.fill_between(n, band.min(axis=0), band.max(axis=0), color=C_READ, alpha=0.12, lw=0)
        a.legend(loc="upper right", frameon=False, fontsize=6.0)
    a.axhline(base, color="k", ls="--", lw=0.7)
    a.axvline(400, color=C_ACC, lw=0.8, ls=":")
    # axes fraction, not data: the y range moves whenever the baseline moves
    a.text(0.42, 0.90, "knee\n400", transform=a.transAxes, fontsize=6.4,
           color=C_ACC, va="top")
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
    c.set_ylim(0, max(vals) * 1.45)     # headroom for the value labels + the caption
    c.set_title("(c) one factor vs. all three")
    c.text(4, max(vals) * 1.28, f"{comb['speedup']:.0f}$\\times$\ncheaper", ha="center",
           fontsize=6.6, color=C_WRITE, linespacing=1.1)
    save(fig, 7, "cost")

# =============================================================================
# Fig. 8 -- sensitivity
# =============================================================================
if want(8):
    print("Fig. 8  sensitivity")
    s, sw = load("sensitivity.json"), load("sensitivity_write.json")
    # Display symbols follow Table III of paper_*_D.md: Delta = absolute shift (mV),
    # k = dimensionless multiplier, Delta-k = pass-gate/pull-down mismatch. The dict keys
    # stay the internal code names, which is what results/*.json is keyed by.
    LAB = {"cn": "$\\Delta V_{th,N}$", "sk": "$\\Delta V_{th,skew}$",
           "pu": "$\\Delta V_{th,P}$", "lpu": "$k_{\\sigma P}$",
           "l_com": "$k_{\\sigma N}$", "l_sk": "$\\Delta k_{\\sigma N}$",
           "mpu": "$k_{\\mu P}$", "m_com": "$k_{\\mu N}$", "m_sk": "$\\Delta k_{\\mu N}$"}
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
        ax.set_xlabel("$\\Delta V_{th,N}$: NMOS $V_{th}$ shift (mV)")
        ax.set_title(ttl)
        ax.text(0.03, 0.03, f"{t['full_range_pct']:.0f} % of the plane\n"
                            f"tolerates every skew", transform=ax.transAxes,
                fontsize=6.4, va="bottom",
                bbox=dict(fc="w", ec="0.6", lw=0.5, alpha=0.9, pad=2))
    axes[0].set_ylabel("$\\Delta V_{th,P}$: PMOS $V_{th}$ shift (mV)")
    cb = fig.colorbar(im, ax=axes, pad=0.015, fraction=0.045)
    cb.set_label("passing $s_k$ width (mV of 40)", fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    for ext in ("png", "pdf"):
        fig.savefig(FIGURES / f"fig9_skew.{ext}", bbox_inches="tight")
    plt.close(fig)
    print("  wrote figures/fig9_skew.png|pdf")

# =============================================================================
# Fig. 10 -- §IV-B scenario: what has to improve to reach V_min = 0.575 V
# =============================================================================
if want(10):
    print("Fig. 10  50 mV scenario")
    sc = load("scenario.json")
    z = np.load(RESULTS / "scenario_contours.npz", allow_pickle=False)
    keys = [str(k) for k in z["panel_keys"]]
    labels = [str(k) for k in z["panel_labels"]]
    cn_a, pu_a = z["cn"], z["pu"]
    VT = float(z["v_target"])
    CN, PU = np.meshgrid(cn_a, pu_a)
    s_of = {c["case"]: c for c in sc["cases"]}
    pan_of = {p["key"]: p for p in sc["panels"]}
    shifts = sc["corner_shifts"]

    ncol = 2
    nrow = int(np.ceil(len(keys) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(DCOL, 2.85 * nrow),
                             squeeze=False, sharex=True, sharey=True)
    lv = np.arange(0.40, 0.76, 0.025)
    cf = None
    for ax, key, lab in zip(axes.ravel(), keys, labels):
        vr, vw = z[f"{key}_read"], z[f"{key}_write"]
        # fill with the cell Vmin = max(read, write); see Fig. 5
        vcell = np.maximum(np.nan_to_num(vr, nan=0.85), np.nan_to_num(vw, nan=0.85))
        # colour pinned to the NEW target: cool/blue passes, warm/red fails, so
        # the fill itself is the verdict and no grey mask is needed on top
        cf = ax.contourf(CN, PU, vcell, levels=lv, cmap="RdYlBu_r",
                         norm=TwoSlopeNorm(vmin=lv[0], vcenter=VT, vmax=lv[-1]),
                         extend="both")
        # today's spec drawn too: FSG/SFG clear V_T0 but not the new target, and
        # without both lines the reader cannot see that the corner sits between them
        ax.contour(CN, PU, vcell, levels=[V_T0], colors="0.25", linewidths=1.0,
                   linestyles="dashed")
        # everything outside this box is GP extrapolation, not fitted behaviour
        th = float(z["train_half"])
        ax.add_patch(plt.Rectangle((-th, -th), 2 * th, 2 * th, fill=False,
                                   ec="0.15", lw=0.9, ls=":", zorder=4))
        ax.contour(CN, PU, vr, levels=[VT], colors="k", linewidths=1.8)
        ax.contour(CN, PU, vw, levels=[VT], colors="k", linewidths=1.8,
                   linestyles="dashdot")
        # pass/fail comes from the solved corner Vmin in scenario.json, not from
        # the ~2 mV contour grid, which would snap the corner to a neighbour
        cv = pan_of[key]["corner_vmin"]
        for cname, mode in (("FSG", "read"), ("SFG", "write")):
            x0, y0 = shifts[cname]
            ok = float(cv[f"{cname}_{mode}"]) <= VT + 1e-4
            ax.scatter([x0], [y0], s=46, marker="*", zorder=5,
                       facecolor=("#111111" if ok else "none"),
                       edgecolor="#111111", lw=1.0)
            ax.annotate(cname, (x0, y0), textcoords="offset points",
                        xytext=(5, 3), fontsize=6.4, color="#111111",
                        fontweight="bold")
        sub = ""
        if key in s_of and s_of[key].get("sigma_reduction_pct") is not None:
            sub = f"\n$\\sigma$ reduced {s_of[key]['sigma_reduction_pct']:.1f}%"
        ax.set_title(f"{lab}{sub}", fontsize=7.4, linespacing=1.35)
    for ax in axes[-1, :]:
        ax.set_xlabel("$\\Delta V_{th,N}$ (mV)")
    for ax in axes[:, 0]:
        ax.set_ylabel("$\\Delta V_{th,P}$ (mV)")
    for ax in axes.ravel()[len(keys):]:
        ax.axis("off")
    fig.suptitle(f"process window at the NEW target $V_{{min}} \\leq$ {VT} V — "
                 f"blue passes, red fails. Solid black = read limit, "
                 f"long-dash = write limit, grey dash = today's spec {V_T0} V. "
                 f"Dotted box = training range; outside it the GP extrapolates.",
                 fontsize=7.4, y=1.004)
    cb = fig.colorbar(cf, ax=axes, pad=0.015, fraction=0.04)
    cb.set_label("cell $V_{min}=\\max$(read, write)  (V)", fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    for ext in ("png", "pdf"):
        fig.savefig(FIGURES / f"fig10_scenario.{ext}", bbox_inches="tight")
    plt.close(fig)
    print("  wrote figures/fig10_scenario.png|pdf")

print(f"\nfigures in {FIGURES}")
