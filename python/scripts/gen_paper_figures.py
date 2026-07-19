"""
gen_paper_figures.py — 논문용 설명 그림 일괄 생성 (non-experimental)

paper_en.md / paper_kr.md (enhanced) 본문에 `[Fig: ...]`로 명시된 그림과,
본문 이해를 돕는 예비(spare) 그림을 논문 톤(muted, grayscale 위주)으로
생성한다. 실험 결과 그림(§5 hold-out scatter / Vmin contour / inversion
trajectory)은 실측 데이터가 필요하므로 이 스크립트에서 다루지 않는다.

출력 (python/results/):
  본문 태그 대응
    fig_sram_cell_6t.png          — 6T SRAM 셀 회로도 (§2.1)
    fig_butterfly_snm.png         — 버터플라이 곡선과 SNM (§2.1)
    fig2_design_visualization.png — quadrant weighting + common/skew box→band (§3.2)
  개요/예비 (본문 태그 없음, 삽입 후보)
    fig1_pipeline_overview.png    — 전체 파이프라인 (forward + inverse)
    fig_gp_1d.png                 — 1-D GP 회귀 개념도 (§4.1, 비-ML 독자용)
    fig_lobe_zscore.png           — min-통계 z 편향 vs lobe 상관 (§2.2–2.3)
    fig_physics_layer.png         — z(Vop) → Vmin 보간 (§4.3)
    fig_mirror_twin.png           — mirror-twin leakage 개념도 (§3.4)

사용법:
    python scripts/gen_paper_figures.py
    python scripts/gen_paper_figures.py --dpi 600
    python scripts/gen_paper_figures.py --format pdf
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Polygon, Circle, Rectangle
from matplotlib.lines import Line2D

# ── Publication style ──────────────────────────────────────────────────────
# Muted, near-grayscale palette. Color only where it disambiguates.

COLORS = {
    "ink":       "#232323",
    "gray":      "#6b6b6b",
    "lightgray": "#c7c7c7",
    "paper":     "#f4f3ef",
    "steel":     "#3d5a73",   # muted steel blue (primary accent)
    "brick":     "#8a4f3d",   # muted brick red (secondary accent)
    "fsg": "#4C6680",
    "sfg": "#8B4C42",
    "fn":  "#5B7A5B",
    "sn":  "#7A6A8B",
}

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "serif"],
    "font.size": 9,
    "text.color": COLORS["ink"],
    "axes.edgecolor": COLORS["ink"],
    "axes.labelcolor": COLORS["ink"],
    "xtick.color": COLORS["ink"],
    "ytick.color": COLORS["ink"],
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "axes.linewidth": 0.7,
    "lines.linewidth": 1.2,
    "axes.grid": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

OUT_DIR = Path(__file__).resolve().parent.parent / "results"


# ════════════════════════════════════════════════════════════════════════════
# Fig 1: Pipeline Overview
# ════════════════════════════════════════════════════════════════════════════

def fig1_pipeline_overview(save_path: Path) -> None:
    """x -> GP(mu,sigma) -> z-score -> Vmin forward chain, MC training input,
    and the gradient-inversion return path."""

    fig, ax = plt.subplots(figsize=(7.0, 2.6))
    ax.set_xlim(-0.3, 7.5)
    ax.set_ylim(-1.05, 1.55)
    ax.axis("off")

    box_style = "round,pad=0.08"

    def draw_box(x, y, w, h, text, fontsize=7.5, face=COLORS["paper"],
                 edge=COLORS["ink"], ls="-"):
        fb = FancyBboxPatch((x, y), w, h, boxstyle=box_style,
                             facecolor=face, edgecolor=edge,
                             linewidth=0.9, linestyle=ls, zorder=3)
        ax.add_patch(fb)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fontsize, zorder=4, linespacing=1.4)
        return (x, y, w, h)

    def draw_arrow(x1, y1, x2, y2, color=COLORS["ink"], lw=1.1, ls="-"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                    linestyle=ls),
                    zorder=2)

    y0, h = -0.42, 0.84
    yc = y0 + h / 2

    b_input = draw_box(-0.1, y0, 1.35, h, "Input $x$\n9-D variation\n+ $V_{\\mathrm{op}}$")
    b_gp    = draw_box(1.7,  y0, 1.55, h, "GP surrogate\n$\\mu$: Matérn 5/2\n$\\sigma$: additive")
    b_z     = draw_box(3.85, y0, 1.3, h, "$z(V_{\\mathrm{op}})$\n$= \\mu/\\sigma$")
    b_vmin  = draw_box(5.75, y0, 1.5, h, "Physics layer\ninterp. $z=Z_t$\n$\\rightarrow V_{\\min}$")

    # training-data input (one-time, dashed)
    xg = b_gp[0] + b_gp[2] / 2
    b_train = draw_box(1.45, 0.82, 2.05, 0.62,
                       "HSPICE MC data: $(\\mu,\\sigma)\\pm$SEM\n2,000 cond $\\times$ 5 $V_{\\mathrm{op}}$",
                       fontsize=6.8, face="white", edge=COLORS["gray"], ls="--")
    draw_arrow(xg, 0.82, xg, y0 + h + 0.03, color=COLORS["gray"], ls="--")
    ax.text(xg - 0.12, 0.58, "train (one-time, FixedNoise)", fontsize=6.2,
            color=COLORS["gray"], ha="right", va="center")

    # forward arrows + label
    draw_arrow(b_input[0] + b_input[2], yc, b_gp[0], yc)
    draw_arrow(b_gp[0] + b_gp[2], yc, b_z[0], yc)
    draw_arrow(b_z[0] + b_z[2], yc, b_vmin[0], yc)
    ax.text(5.9, 1.1, "forward: instant prediction (no simulation)", ha="center",
            va="center", fontsize=6.8, color=COLORS["ink"])

    # inverse return path: polyline below the boxes
    y_bus = y0 - 0.26
    x_vmin_c = b_vmin[0] + b_vmin[2] / 2
    x_input_c = b_input[0] + b_input[2] / 2
    inv_kw = dict(color=COLORS["brick"], lw=1.1, linestyle="--",
                  solid_capstyle="round", zorder=2)
    ax.plot([x_vmin_c, x_vmin_c], [y0, y_bus], **inv_kw)
    ax.plot([x_vmin_c, x_input_c], [y_bus, y_bus], **inv_kw)
    draw_arrow(x_input_c, y_bus, x_input_c, y0 - 0.02, color=COLORS["brick"], ls="--")

    ax.text((x_input_c + x_vmin_c) / 2, y_bus - 0.2,
            "inverse: minimize $(V_{\\min}(x) - V^{*})^2$ by gradient descent"
            " on $x$  (target $V^{*}$, multi-start, no grid search)",
            ha="center", va="center", fontsize=6.8, color=COLORS["brick"])

    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Fig: 6T SRAM Cell — proper transistor symbols
# ════════════════════════════════════════════════════════════════════════════

def fig_sram_cell_6t(save_path: Path) -> None:
    """Textbook-style 6T SRAM schematic: cross-coupled inverters + pass gates,
    drawn with simplified MOSFET symbols (PMOS bubble on gate)."""

    fig, ax = plt.subplots(figsize=(3.9, 3.9))
    ax.set_xlim(-0.35, 6.15)
    ax.set_ylim(0.0, 6.15)
    ax.set_aspect("equal")
    ax.axis("off")

    ink = COLORS["ink"]

    def wire(x1, y1, x2, y2, **kw):
        d = dict(color=ink, lw=0.9, solid_capstyle="round", zorder=1)
        d.update(kw)
        ax.plot([x1, x2], [y1, y2], **d)

    def dot(x, y):
        ax.plot(x, y, "o", color=ink, markersize=3.2, zorder=5)

    def mos_v(cx, cy, gs, pmos=False):
        """Vertical MOSFET: channel at x=cx, gate lead entering from side gs
        (+1 = right). Returns (gate_lead_x_end, top_y, bot_y)."""
        ch = 0.26          # channel half-length
        wire(cx, cy - ch, cx, cy + ch, lw=1.7)               # channel
        px = cx + gs * 0.15                                    # gate plate
        wire(px, cy - 0.16, px, cy + 0.16, lw=1.7)
        if pmos:
            ax.add_patch(Circle((cx + gs * 0.22, cy), 0.055, facecolor="white",
                                edgecolor=ink, lw=0.9, zorder=3))
            lead_x0 = cx + gs * 0.275
        else:
            lead_x0 = px
        lead_x1 = cx + gs * 0.55
        wire(lead_x0, cy, lead_x1, cy)
        return lead_x1, cy + ch, cy - ch

    def mos_h(cx, cy):
        """Horizontal NMOS (pass gate): channel at y=cy, gate lead upward.
        Returns (gate_lead_y_end, left_x, right_x)."""
        ch = 0.26
        wire(cx - ch, cy, cx + ch, cy, lw=1.7)                # channel
        wire(cx - 0.16, cy + 0.15, cx + 0.16, cy + 0.15, lw=1.7)  # plate
        lead_y1 = cy + 0.55
        wire(cx, cy + 0.15, cx, lead_y1)
        return lead_y1, cx - ch, cx + ch

    # geometry
    xL, xR = 1.5, 4.3            # storage-node columns
    x_inL, x_inR = 2.05, 3.75    # inverter-input buses (gate side)
    y_pu, y_pd = 4.5, 1.3        # transistor row centers
    y_q = 2.9                    # storage-node tap height (PG row)
    y_x1, y_x2 = 3.35, 2.45      # cross-coupling wire heights
    y_vdd, y_vss = 5.35, 0.5
    y_wl = 5.75
    x_pg1, x_pg2 = 0.55, 5.25    # pass-gate channel centers
    x_bl, x_blb = -0.05, 5.85

    # rails
    wire(xL, y_vdd, xR, y_vdd, lw=1.1)
    ax.text((xL + xR) / 2, y_vdd - 0.14, "$V_{\\mathrm{DD}}$", ha="center",
            va="top", fontsize=9, fontweight="bold")
    wire(xL, y_vss, xR, y_vss, lw=1.1)
    ax.text((xL + xR) / 2, y_vss - 0.14, "$V_{\\mathrm{SS}}$", ha="center",
            va="top", fontsize=9, fontweight="bold")

    # left inverter (gates face right)
    g1, pu1_top, pu1_bot = mos_v(xL, y_pu, +1, pmos=True)
    g2, pd1_top, pd1_bot = mos_v(xL, y_pd, +1, pmos=False)
    wire(xL, pu1_top, xL, y_vdd)
    wire(xL, pd1_bot, xL, y_vss)
    wire(xL, pu1_bot, xL, pd1_top)                      # storage column (node Q)
    ax.text(xL - 0.28, y_pu, "PU$_1$", ha="right", va="center", fontsize=8, fontweight="bold")
    ax.text(xL - 0.28, y_pd, "PD$_1$", ha="right", va="center", fontsize=8, fontweight="bold")

    # right inverter (gates face left)
    g3, pu2_top, pu2_bot = mos_v(xR, y_pu, -1, pmos=True)
    g4, pd2_top, pd2_bot = mos_v(xR, y_pd, -1, pmos=False)
    wire(xR, pu2_top, xR, y_vdd)
    wire(xR, pd2_bot, xR, y_vss)
    wire(xR, pu2_bot, xR, pd2_top)                      # storage column (node Qbar)
    ax.text(xR + 0.28, y_pu, "PU$_2$", ha="left", va="center", fontsize=8, fontweight="bold")
    ax.text(xR + 0.28, y_pd, "PD$_2$", ha="left", va="center", fontsize=8, fontweight="bold")

    # inverter input buses (join PU/PD gates)
    wire(g1, y_pu, x_inL, y_pu); wire(g2, y_pd, x_inL, y_pd)
    wire(x_inL, y_pd, x_inL, y_pu)
    wire(g3, y_pu, x_inR, y_pu); wire(g4, y_pd, x_inR, y_pd)
    wire(x_inR, y_pd, x_inR, y_pu)

    # cross-coupling (no dot where wires merely cross)
    wire(x_inL, y_x1, xR, y_x1)      # left input <- Qbar
    dot(x_inL, y_x1); dot(xR, y_x1)
    wire(x_inR, y_x2, xL, y_x2)      # right input <- Q
    dot(x_inR, y_x2); dot(xL, y_x2)

    # storage-node labels (on the storage columns themselves)
    ax.text(xL - 0.15, 3.28, "$Q$", ha="right", va="center", fontsize=9)
    ax.text(xR + 0.15, 3.28, "$\\bar{Q}$", ha="left", va="center", fontsize=9)

    # pass gates
    wl1, pg1_l, pg1_r = mos_h(x_pg1, y_q)
    wl2, pg2_l, pg2_r = mos_h(x_pg2, y_q)
    ax.text(x_pg1, y_q - 0.22, "PG$_1$", ha="center", va="top", fontsize=8, fontweight="bold")
    ax.text(x_pg2, y_q - 0.22, "PG$_2$", ha="center", va="top", fontsize=8, fontweight="bold")

    wire(pg1_r, y_q, xL, y_q); dot(xL, y_q)             # PG1 -> Q
    wire(pg2_l, y_q, xR, y_q); dot(xR, y_q)             # PG2 -> Qbar

    # bit lines
    wire(pg1_l, y_q, x_bl, y_q); wire(x_bl, y_q, x_bl, 1.7)
    ax.text(x_bl, 1.52, "BL", ha="center", va="top", fontsize=8, fontweight="bold")
    wire(pg2_r, y_q, x_blb, y_q); wire(x_blb, y_q, x_blb, 1.7)
    ax.text(x_blb, 1.52, "$\\overline{\\mathrm{BL}}$", ha="center", va="top",
            fontsize=8, fontweight="bold")

    # word line across the top
    wire(x_pg1, wl1, x_pg1, y_wl); wire(x_pg2, wl2, x_pg2, y_wl)
    wire(x_pg1, y_wl, x_pg2, y_wl)
    ax.text((x_pg1 + x_pg2) / 2, y_wl + 0.12, "WL", ha="center", va="bottom",
            fontsize=8, fontweight="bold")

    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Fig: Butterfly Curve / SNM — exact 45°-rotated square extraction
# ════════════════════════════════════════════════════════════════════════════

def _vtc(vin, vlow=0.04, vhigh=0.96, vm=0.5, k=11.0):
    """Monotone decreasing inverter VTC (sigmoid)."""
    return vlow + (vhigh - vlow) / (1.0 + np.exp(k * (vin - vm)))


def _snm_square(x1, y1, x2, y2, u_lo, u_hi):
    """Largest axis-aligned square inscribed between two curves, standard SNM
    construction: rotate 45° (u=(x-y)/sqrt2 along the lobe, w=(x+y)/sqrt2
    across it); max gap g* across the lobe gives square side s = g*/sqrt2,
    with opposite corners on the two curves.

    Returns (side, corner_xy) with corner_xy the lower-left corner.
    """
    s2 = np.sqrt(2.0)
    u1, w1 = (x1 - y1) / s2, (x1 + y1) / s2
    u2, w2 = (x2 - y2) / s2, (x2 + y2) / s2
    o1, o2 = np.argsort(u1), np.argsort(u2)
    ug = np.linspace(u_lo + 1e-4, u_hi - 1e-4, 600)
    w1g = np.interp(ug, u1[o1], w1[o1])
    w2g = np.interp(ug, u2[o2], w2[o2])
    gap = np.abs(w1g - w2g)
    i = int(np.argmax(gap))
    side = gap[i] / s2
    u_c = ug[i]
    w_lo = min(w1g[i], w2g[i])
    x_ll = (u_c + w_lo) / s2      # lower corner (on one curve)
    y_ll = (w_lo - u_c) / s2
    return side, (x_ll, y_ll)


def fig_butterfly_snm(save_path: Path) -> None:
    """Butterfly curve with two eye-shaped lobes and correctly inscribed
    SNM squares (corners on the VTCs)."""

    fig, ax = plt.subplots(figsize=(3.6, 3.6))

    v = np.linspace(0, 1, 2000)
    vout1 = _vtc(v, vm=0.44)          # inverter I:  y = f1(x)
    vout2 = _vtc(v, vm=0.56)          # inverter II: x = f2(y)  (mirrored)

    xI, yI = v, vout1
    xII, yII = vout2, v

    ax.plot(xI, yI, color=COLORS["ink"], lw=1.4, label="Inverter I", zorder=3)
    ax.plot(xII, yII, color=COLORS["gray"], lw=1.4, ls="--",
            label="Inverter II (mirrored)", zorder=3)

    # crossings on the x-grid
    order = np.argsort(xII)
    yII_on_x = np.interp(v, xII[order], yII[order])
    diff = yI - yII_on_x
    sc = np.where(np.diff(np.sign(diff)))[0]
    i_lo, i_mid, i_hi = sc[0], sc[1], sc[-1]

    # shade the two lobes (middle segments between the 3 crossings)
    m_l = (v >= v[i_lo]) & (v <= v[i_mid])
    m_r = (v >= v[i_mid]) & (v <= v[i_hi])
    ax.fill_between(v[m_l], yI[m_l], yII_on_x[m_l],
                     color=COLORS["lightgray"], alpha=0.6, zorder=1)
    ax.fill_between(v[m_r], yI[m_r], yII_on_x[m_r],
                     color=COLORS["lightgray"], alpha=0.6, zorder=1)

    # crossing points in rotated coordinate u = (x-y)/sqrt2
    s2 = np.sqrt(2.0)
    u_cross = [(v[i] - yI[i]) / s2 for i in (i_lo, i_mid, i_hi)]

    snm_l, ll_l = _snm_square(xI, yI, xII, yII, u_cross[0], u_cross[1])
    snm_r, ll_r = _snm_square(xI, yI, xII, yII, u_cross[1], u_cross[2])

    ax.add_patch(Rectangle(ll_l, snm_l, snm_l, fill=False,
                            edgecolor=COLORS["steel"], lw=1.1, ls=":", zorder=4))
    ax.add_patch(Rectangle(ll_r, snm_r, snm_r, fill=False,
                            edgecolor=COLORS["brick"], lw=1.1, ls=":", zorder=4))

    ax.text(ll_l[0] + snm_l / 2, ll_l[1] + snm_l / 2, "SNM$_L$", ha="center",
            va="center", fontsize=6.2, color=COLORS["steel"], fontweight="bold")
    ax.text(ll_r[0] + snm_r / 2, ll_r[1] + snm_r / 2, "SNM$_R$", ha="center",
            va="center", fontsize=7.5, color=COLORS["brick"], fontweight="bold")

    ax.text(0.03, 0.06, "SNM = min(SNM$_L$, SNM$_R$)", ha="left", va="bottom",
            fontsize=7.5,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      edgecolor=COLORS["ink"], linewidth=0.6))

    ax.set_xlabel("$V_{\\mathrm{in,1}}$ / $V_{\\mathrm{out,2}}$ (V)")
    ax.set_ylabel("$V_{\\mathrm{out,1}}$ / $V_{\\mathrm{in,2}}$ (V)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.legend(frameon=False, fontsize=6.8, loc="upper right")
    ax.tick_params(length=3)

    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Fig 2: Design Visualization (3 panels, matches §3.2 caption)
# ════════════════════════════════════════════════════════════════════════════

def fig2_design_visualization(save_path: Path) -> None:
    """(a) Quadrant weighting in (cn, pu);
       (b) independent (l_com, l_sk) sampling box;
       (c) derived (l_PD, l_PG) diagonal band."""

    from src.condition_gen import generate_conditions

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(7.2, 2.6))

    # ── (a) quadrant weighting ─────────────────────────────────────────
    n_show = 500
    cols, cond = generate_conditions("D", n_show, seed=2027, metric="snmr")
    cn, pu = cond[:, 0], cond[:, 2]

    colors_a = np.where(
        (cn < 0) & (pu > 0), COLORS["fsg"],
        np.where((cn > 0) & (pu < 0), COLORS["sfg"],
                 np.where((cn < 0) & (pu < 0), COLORS["fn"], COLORS["sn"])))
    ax1.scatter(cn, pu, c=colors_a, s=7, alpha=0.5, edgecolors="none", zorder=2)
    ax1.axhline(0, color=COLORS["gray"], lw=0.5, ls="--", zorder=1)
    ax1.axvline(0, color=COLORS["gray"], lw=0.5, ls="--", zorder=1)

    for label, (x, y, c) in {
        "FSG 45%": (-31, 36, COLORS["fsg"]),
        "SFG 20%": (31, -36, COLORS["sfg"]),
        "FN 20%":  (-31, -36, COLORS["fn"]),
        "SN 15%":  (31, 36, COLORS["sn"]),
    }.items():
        ax1.text(x, y, label, ha="center", va="center", fontsize=6.5,
                  color=c, fontweight="bold",
                  bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                            edgecolor=c, linewidth=0.5, alpha=0.9))

    ax1.set_xlabel("$c_n$ (mV)")
    ax1.set_ylabel("$p_u$ (mV)")
    ax1.set_title("(a) SNMR quadrant weighting", fontsize=8.5, pad=7)
    ax1.set_xlim(-65, 65); ax1.set_ylim(-65, 65)
    ax1.set_aspect("equal"); ax1.tick_params(length=3)

    # ── shared sample for (b)->(c) ─────────────────────────────────────
    rng = np.random.default_rng(42)
    n_pts = 700
    l_com = rng.uniform(0.7, 1.3, n_pts)
    l_sk = rng.uniform(-0.075, 0.075, n_pts)
    l_pg, l_pd = l_com + l_sk, l_com - l_sk

    # ── (b) independent sampling box ───────────────────────────────────
    ax2.scatter(l_com, l_sk, s=5, alpha=0.4, color=COLORS["steel"],
                edgecolors="none", zorder=2)
    ax2.add_patch(Rectangle((0.7, -0.075), 0.6, 0.15, fill=False,
                             edgecolor=COLORS["steel"], lw=0.9, ls="--", zorder=3))
    ax2.axhline(0, color=COLORS["gray"], lw=0.5, ls=":", zorder=1)
    ax2.set_xlabel("$l_{\\mathrm{com}}$")
    ax2.set_ylabel("$l_{\\mathrm{sk}}$")
    ax2.set_title("(b) sampled: independent box", fontsize=8.5, pad=7)
    ax2.set_xlim(0.62, 1.38); ax2.set_ylim(-0.12, 0.12)
    ax2.set_box_aspect(1)
    ax2.tick_params(length=3)

    # ── (c) derived diagonal band ──────────────────────────────────────
    ax3.scatter(l_pd, l_pg, s=5, alpha=0.4, color=COLORS["steel"],
                edgecolors="none", zorder=2)
    corners = [(0.625, 0.775), (0.775, 0.625), (1.375, 1.225), (1.225, 1.375)]
    ax3.add_patch(Polygon(corners, closed=True, facecolor=COLORS["steel"],
                           alpha=0.08, edgecolor=COLORS["steel"], lw=0.8,
                           ls="--", zorder=1))
    ax3.plot([0.55, 1.45], [0.55, 1.45], color=COLORS["gray"], lw=0.5, ls=":", zorder=1)
    ax3.plot(1.0, 1.0, "+", color=COLORS["ink"], markersize=8, markeredgewidth=1.2, zorder=3)
    ax3.text(1.04, 0.96, "nominal", fontsize=6, color=COLORS["gray"], ha="left", va="top")

    ax3.set_xlabel("$l_{\\mathrm{PD}} = l_{\\mathrm{com}} - l_{\\mathrm{sk}}$", fontsize=8)
    ax3.set_ylabel("$l_{\\mathrm{PG}} = l_{\\mathrm{com}} + l_{\\mathrm{sk}}$", fontsize=8)
    ax3.set_title("(c) derived: device band", fontsize=8.5, pad=7)
    ax3.set_xlim(0.58, 1.42); ax3.set_ylim(0.58, 1.42)
    ax3.set_aspect("equal"); ax3.tick_params(length=3)
    ax3.text(0.63, 1.36, "$\\rho \\approx 0.88$", fontsize=7,
              color=COLORS["steel"], fontstyle="italic",
              bbox=dict(boxstyle="round,pad=0.12", facecolor="white",
                        edgecolor=COLORS["steel"], linewidth=0.5))

    fig.tight_layout(w_pad=1.8)
    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Spare Fig: 1-D GP regression illustration (§4.1)
# ════════════════════════════════════════════════════════════════════════════

def fig_gp_1d(save_path: Path) -> None:
    """Toy 1-D GP: posterior mean + 95% band through noisy points; uncertainty
    grows away from data. For readers without an ML background."""

    def k_rbf(a, b, ls=0.55, sf=1.0):
        return sf ** 2 * np.exp(-0.5 * (a[:, None] - b[None, :]) ** 2 / ls ** 2)

    rng = np.random.default_rng(7)
    f = lambda x: np.sin(2.2 * x) + 0.35 * x
    X = np.array([-1.8, -1.35, -0.7, -0.35, 0.4, 0.55, 1.5])
    sn = 0.08
    y = f(X) + rng.normal(0, sn, X.shape)

    Xs = np.linspace(-2.8, 2.8, 400)
    K = k_rbf(X, X) + sn ** 2 * np.eye(len(X))
    L = np.linalg.cholesky(K)
    alpha = np.linalg.solve(L.T, np.linalg.solve(L, y))
    Ks = k_rbf(Xs, X)
    mean = Ks @ alpha
    v_ = np.linalg.solve(L, Ks.T)
    var = np.clip(1.0 - np.sum(v_ ** 2, axis=0), 0, None)
    sd = np.sqrt(var)

    fig, ax = plt.subplots(figsize=(4.2, 2.7))

    ax.fill_between(Xs, mean - 1.96 * sd, mean + 1.96 * sd,
                     color=COLORS["steel"], alpha=0.14, zorder=1,
                     label="95% confidence band")
    ax.plot(Xs, mean, color=COLORS["steel"], lw=1.4, zorder=3,
            label="GP posterior mean")
    ax.plot(Xs, f(Xs), color=COLORS["gray"], lw=0.9, ls="--", zorder=2,
            label="true function (unknown)")
    ax.plot(X, y, "o", color=COLORS["ink"], markersize=4, zorder=4,
            label="simulation samples")

    # annotate uncertainty growth away from data
    x_far = 2.45
    i_far = np.argmin(np.abs(Xs - x_far))
    ax.annotate("uncertainty grows\naway from data",
                xy=(x_far, mean[i_far] + 1.96 * sd[i_far]),
                xytext=(1.15, 2.35), fontsize=6.8, color=COLORS["gray"],
                ha="left", linespacing=1.3,
                arrowprops=dict(arrowstyle="->", color=COLORS["gray"], lw=0.7))

    ax.set_xlabel("input (1-D slice of variation space)")
    ax.set_ylabel("output (e.g. $\\mu_{\\mathrm{SNMR}}$)")
    ax.set_xlim(-2.8, 2.8)
    ax.set_ylim(-2.4, 2.9)
    ax.legend(frameon=False, fontsize=6.6, loc="lower left", handlelength=1.6)
    ax.tick_params(length=3)
    ax.set_yticks([])
    ax.set_xticks([])

    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Spare Fig: min-statistics z bias vs lobe correlation (§2.2–2.3)
# ════════════════════════════════════════════════════════════════════════════

def _min_stats(z, rho):
    """Exact mean/std of min(L,R) for L,R ~ N(mu,sig^2) with corr rho,
    expressed in per-lobe sigma units (mu = z, sig = 1).
    min = A - |B|, A=(L+R)/2 ~ N(z,(1+rho)/2), B=(L-R)/2 ~ N(0,(1-rho)/2), A⊥B.
    """
    mu_min = z - np.sqrt((1.0 - rho) / np.pi)
    var_min = 1.0 - (1.0 - rho) / np.pi
    return mu_min, np.sqrt(var_min)


def _p_fail_exact(z, rho):
    """P(min(L,R) < 0) = 2*Phi(-z) - Phi2(-z,-z; rho)."""
    from scipy.stats import norm, multivariate_normal
    p1 = norm.cdf(-z)
    p2 = multivariate_normal(mean=[0.0, 0.0],
                             cov=[[1.0, rho], [rho, 1.0]]).cdf([-z, -z])
    return 2.0 * p1 - p2


def fig_lobe_zscore(save_path: Path) -> None:
    """(a) optimism of the naive min-Gaussian z vs lobe correlation;
       (b) left-tail CDF of min(L,R): exact vs moment-matched Gaussian."""

    from scipy.stats import norm

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.8))

    # ── (a) bias vs rho, for per-lobe z levels ────────────────────────
    rhos = np.linspace(-0.9, 0.9, 61)
    styles = {5.0: (COLORS["lightgray"], "-"), 6.0: (COLORS["steel"], "-"),
              7.0: (COLORS["gray"], "--")}
    for z_lobe, (c, ls) in styles.items():
        bias = []
        for r in rhos:
            mu_m, sd_m = _min_stats(z_lobe, r)
            z_naive = mu_m / sd_m
            z_eff = -norm.ppf(_p_fail_exact(z_lobe, r))
            bias.append(z_naive - z_eff)
        ax1.plot(rhos, bias, color=c, lw=1.3, ls=ls,
                 label=f"per-lobe $z = {z_lobe:.0f}$")

    # mark the independent-lobe reference
    mu_m, sd_m = _min_stats(6.0, 0.0)
    b0 = mu_m / sd_m + norm.ppf(_p_fail_exact(6.0, 0.0))
    ax1.plot(0.0, b0, "o", color=COLORS["steel"], markersize=4, zorder=4)
    ax1.annotate(f"$\\rho=0$: +{b0:.2f}$\\sigma$", xy=(0.0, b0),
                 xytext=(0.13, b0 + 0.42), fontsize=7, color=COLORS["steel"],
                 arrowprops=dict(arrowstyle="->", color=COLORS["steel"], lw=0.7))

    ax1.axhline(0, color=COLORS["gray"], lw=0.5, ls=":")
    ax1.set_xlabel("lobe correlation $\\rho_{LR}$")
    ax1.set_ylabel("optimism  $z_{\\mathrm{naive}} - z_{\\mathrm{eff}}$  ($\\sigma$)")
    ax1.set_title("(a) bias of naive min-Gaussian $z$", fontsize=9, pad=7)
    ax1.legend(frameon=False, fontsize=6.8, loc="upper right")
    ax1.tick_params(length=3)

    # ── (b) left tail: exact vs moment-matched Gaussian ───────────────
    z_lobe, rho = 6.0, 0.0
    mu_m, sd_m = _min_stats(z_lobe, rho)
    t_std = np.linspace(-8.5, 0.0, 200)          # threshold in sigma_min units
    t_raw = mu_m + t_std * sd_m                  # back to per-lobe sigma units

    p_gauss = norm.cdf(t_std)
    p_exact = np.array([_p_fail_exact(z_lobe - t, rho) for t in t_raw])
    # note: P(min < t) with lobes shifted so threshold at t == P(min-t < 0)

    ax2.semilogy(t_std, p_gauss, color=COLORS["gray"], lw=1.3, ls="--",
                 label="moment-matched Gaussian")
    ax2.semilogy(t_std, p_exact, color=COLORS["steel"], lw=1.3,
                 label="exact (lobe-resolved)")
    ax2.fill_between(t_std, p_gauss, p_exact,
                      where=p_exact > p_gauss, color=COLORS["steel"],
                      alpha=0.12, zorder=1)

    ax2.annotate("heavier left tail:\nGaussian is optimistic",
                 xy=(-6.3, p_exact[np.argmin(np.abs(t_std + 6.3))]),
                 xytext=(-5.4, 3e-11), fontsize=6.8, color=COLORS["steel"],
                 linespacing=1.3,
                 arrowprops=dict(arrowstyle="->", color=COLORS["steel"], lw=0.7))

    ax2.set_xlabel("threshold  $(t - \\mu_{\\min})/\\sigma_{\\min}$")
    ax2.set_ylabel("$P(\\mathrm{SNM} < t)$")
    ax2.set_title("(b) left tail of min(L, R),  $\\rho_{LR}=0$", fontsize=9, pad=7)
    ax2.set_ylim(1e-16, 1)
    ax2.set_xlim(-8.5, 0)
    ax2.legend(frameon=False, fontsize=6.8, loc="upper left")
    ax2.tick_params(length=3)

    fig.tight_layout(w_pad=2.5)
    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Spare Fig: Physics layer — z(Vop) → Vmin (§4.3)
# ════════════════════════════════════════════════════════════════════════════

def fig_physics_layer(save_path: Path) -> None:
    """z(Vop) curves crossing Z_t; Vmin by linear interpolation on the Vop
    grid; one left-censored condition."""

    fig, ax = plt.subplots(figsize=(4.2, 3.0))

    z_target = 6.50
    vgrid = np.array([0.4, 0.5, 0.6, 0.7, 0.8])
    vop = np.linspace(0.38, 0.82, 300)

    z_of = {
        "A": lambda v: 1.0 + 12.0 * (1.0 - np.exp(-5.0 * (v - 0.35))),
        "B": lambda v: 0.8 + 10.0 * (1.0 - np.exp(-3.5 * (v - 0.35))),
        "C": lambda v: 2.0 + 15.0 * (1.0 - np.exp(-9.0 * (v - 0.30))),
    }
    style = {"A": (COLORS["steel"], "-", "o"), "B": (COLORS["brick"], "-", "s"),
             "C": (COLORS["gray"], "-.", "^")}

    for name, zf in z_of.items():
        c, ls, mk = style[name]
        ax.plot(vop, zf(vop), color=c, lw=1.3, ls=ls, zorder=2)
        ax.plot(vgrid, zf(vgrid), mk, color=c, markersize=3.5, zorder=3,
                markerfacecolor="white", markeredgewidth=0.9,
                label=f"condition {name}")

    ax.axhline(z_target, color=COLORS["ink"], lw=0.8, ls="--", zorder=1)
    ax.text(0.815, z_target + 0.25, f"$Z_t = {z_target}$", fontsize=7.5,
            ha="right", va="bottom")

    # Vmin crossings for A and B (linear interp on the 5-point grid)
    for name in ("A", "B"):
        c = style[name][0]
        zg = z_of[name](vgrid)
        i = np.searchsorted(zg, z_target)
        v_lo, v_hi = vgrid[i - 1], vgrid[i]
        z_lo, z_hi = zg[i - 1], zg[i]
        vmin = v_lo + (z_target - z_lo) * (v_hi - v_lo) / (z_hi - z_lo)
        ax.plot(vmin, z_target, "o", color=c, markersize=4.5, zorder=4)
        ax.plot([vmin, vmin], [0, z_target], color=c, lw=0.6, ls=":", zorder=1)
        ax.text(vmin, 0.35, f"$V_{{\\min}}^{{{name}}}$", ha="center", fontsize=7.5,
                color=c, fontweight="bold")

    # censored: z(0.4) > Z_t
    ax.text(0.465, 13.4, "condition C censored:\n$z(0.4\\,\\mathrm{V}) > Z_t"
            "\\;\\Rightarrow\\; V_{\\min} < 0.4\\,\\mathrm{V}$",
            fontsize=6.5, color=COLORS["gray"], ha="left", va="top",
            linespacing=1.3)

    ax.set_xlabel("$V_{\\mathrm{op}}$ (V)")
    ax.set_ylabel("$z = \\mu / \\sigma$")
    ax.set_xlim(0.38, 0.82)
    ax.set_ylim(0, 14)
    ax.legend(frameon=False, fontsize=7, loc="lower right")
    ax.tick_params(length=3)

    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Spare Fig: Mirror-twin leakage (§3.4)
# ════════════════════════════════════════════════════════════════════════════

def fig_mirror_twin(save_path: Path) -> None:
    """(a) pilot: one stream sign-flipped into 4 quadrants -> mirror twins,
    random split leaks twins across train/test;
    (b) fix: independent stream per quadrant, no twins."""

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.6, 3.1))

    rng = np.random.default_rng(11)
    n = 28
    quads = [(1, 1), (-1, 1), (-1, -1), (1, -1)]   # ring order for the polygon

    # (a) mirrored pilot design: one QMC stream sign-flipped into 4 quadrants
    base = rng.uniform(5, 55, size=(n, 2))
    for i in range(n):
        for sx, sy in quads:
            ax1.plot(base[i, 0] * sx, base[i, 1] * sy, "o", markersize=2.8,
                     color=COLORS["lightgray"], markeredgewidth=0, zorder=2)

    # highlighted mirror group: one test condition + its 3 twins in training
    gx, gy = 38.0, 27.0
    ring = [(gx * sx, gy * sy) for sx, sy in quads]
    ax1.plot([p[0] for p in ring] + [ring[0][0]],
             [p[1] for p in ring] + [ring[0][1]],
             color=COLORS["brick"], lw=0.7, ls=":", zorder=3)
    for j, (px, py) in enumerate(ring):
        if j == 0:   # test point (open marker)
            ax1.plot(px, py, "o", markersize=5, color=COLORS["brick"],
                     markerfacecolor="white", markeredgewidth=1.1, zorder=4)
        else:        # its mirror twins, sitting in the training set
            ax1.plot(px, py, "o", markersize=5, color=COLORS["brick"],
                     markeredgewidth=0, zorder=4)
    ax1.annotate("held-out test point", xy=ring[0], xytext=(8, 52),
                 fontsize=6.3, color=COLORS["brick"], ha="left",
                 arrowprops=dict(arrowstyle="->", color=COLORS["brick"], lw=0.7))
    ax1.annotate("its mirror twins\n(in training)", xy=ring[2], xytext=(-24, -48),
                 fontsize=6.3, color=COLORS["brick"], ha="center", va="center",
                 linespacing=1.25,
                 arrowprops=dict(arrowstyle="->", color=COLORS["brick"], lw=0.7))

    ax1.axhline(0, color=COLORS["gray"], lw=0.5, ls="--")
    ax1.axvline(0, color=COLORS["gray"], lw=0.5, ls="--")
    ax1.set_title("(a) pilot: sign-flipped stream\n$\\rightarrow$ mirror twins leak", fontsize=8.5, pad=6)
    ax1.set_xlabel("$c_n$ (mV)")
    ax1.set_ylabel("$p_u$ (mV)")
    ax1.set_xlim(-68, 68); ax1.set_ylim(-68, 68)
    ax1.set_aspect("equal"); ax1.tick_params(length=3)

    # (b) independent streams per quadrant
    from src.condition_gen import generate_conditions
    cols, cond = generate_conditions("D", 4 * n, seed=2027, metric="snmr")
    ax2.plot(cond[:, 0], cond[:, 2], "o", markersize=2.8, color=COLORS["steel"],
             alpha=0.55, markeredgewidth=0, zorder=3, linestyle="none")
    ax2.axhline(0, color=COLORS["gray"], lw=0.5, ls="--")
    ax2.axvline(0, color=COLORS["gray"], lw=0.5, ls="--")
    ax2.set_title("(b) v2: independent stream\nper quadrant (no twins)", fontsize=8.5, pad=6)
    ax2.set_xlabel("$c_n$ (mV)")
    ax2.set_ylabel("$p_u$ (mV)")
    ax2.set_xlim(-68, 68); ax2.set_ylim(-68, 68)
    ax2.set_aspect("equal"); ax2.tick_params(length=3)

    fig.tight_layout(w_pad=2.2)
    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    ap = argparse.ArgumentParser(description="Generate paper explanatory figures")
    ap.add_argument("--dpi", type=int, default=300, help="Output DPI (default: 300)")
    ap.add_argument("--format", choices=["png", "pdf", "svg"], default="png")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ext = args.format

    print(f"Generating paper explanatory figures -> {OUT_DIR}/  (format={ext}, dpi={args.dpi})")

    fig_sram_cell_6t(OUT_DIR / f"fig_sram_cell_6t.{ext}")
    fig_butterfly_snm(OUT_DIR / f"fig_butterfly_snm.{ext}")
    fig2_design_visualization(OUT_DIR / f"fig2_design_visualization.{ext}")
    fig1_pipeline_overview(OUT_DIR / f"fig1_pipeline_overview.{ext}")
    fig_gp_1d(OUT_DIR / f"fig_gp_1d.{ext}")
    fig_lobe_zscore(OUT_DIR / f"fig_lobe_zscore.{ext}")
    fig_physics_layer(OUT_DIR / f"fig_physics_layer.{ext}")
    fig_mirror_twin(OUT_DIR / f"fig_mirror_twin.{ext}")

    print(f"\nDone. 8 figures saved to {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
