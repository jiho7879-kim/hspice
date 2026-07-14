"""
gen_paper_figures.py — 논문용 설명 그림 일괄 생성 (non-experimental)

논문 paper_en.md / paper_kr.md 의 [Fig N] placeholder와 구조 설명을 위해
실험 결과가 아닌 개념·구조 그림을 논문 톤(publication-quality)으로 생성한다.

출력 (python/results/):
  fig1_pipeline_overview.png      — 전체 파이프라인 개요 (Fig 1)
  fig2_design_visualization.png   — 설계 공간 시각화 (Fig 2)
  fig_sram_cell_6t.png            — 6T SRAM 셀 구조 (보조)
  fig_butterfly_snm.png           — 버터플라이 곡선과 SNM (보조)
  fig_lobe_zscore.png             — Lobe 분해 z-score 보정 (보조)
  fig_physics_layer.png           — 물리 계층 z(Vop) → Vmin (보조)

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
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Arc
from matplotlib.lines import Line2D

# ── Publication style ──────────────────────────────────────────────────────
# Unified style for all figures: clean, minimal, IEEE/Journal-ready.

COLORS = {
    "primary":   "#2563EB",   # blue-600
    "secondary": "#DC2626",   # red-600
    "accent":    "#059669",   # emerald-600
    "orange":    "#D97706",   # amber-600
    "purple":    "#7C3AED",   # violet-600
    "gray":      "#6B7280",   # gray-500
    "lightgray": "#E5E7EB",   # gray-200
    "dark":      "#1F2937",   # gray-800
    "bg":        "#F9FAFB",   # gray-50
    "fsg":       "#2563EB",   # blue (FSG quadrant)
    "sfg":       "#DC2626",   # red (SFG quadrant)
    "fn":        "#059669",   # green (fast-N quadrant)
    "sn":        "#7C3AED",   # purple (slow-N quadrant)
}

FONT = {
    "family": "serif",
    "size": 9,
}
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "serif"],
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "axes.linewidth": 0.6,
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
    """Block diagram: x → GP(μ,σ) → Physics Layer → Vmin, + inverse path."""

    fig, ax = plt.subplots(figsize=(7.0, 2.8))
    ax.set_xlim(-0.3, 7.3)
    ax.set_ylim(-1.8, 1.8)
    ax.axis("off")

    # ── Boxes ──────────────────────────────────────────────────────────
    box_style = "round,pad=0.08"
    box_kwargs = dict(
        boxstyle=box_style,
        facecolor="white",
        edgecolor=COLORS["dark"],
        linewidth=1.0,
    )

    def draw_box(x, y, w, h, text, color=COLORS["lightgray"], fontsize=8.5, ec=COLORS["dark"]):
        fb = FancyBboxPatch((x, y), w, h, boxstyle=box_style,
                            facecolor=color, edgecolor=ec, linewidth=0.9,
                            zorder=2, transform=ax.transData)
        ax.add_patch(fb)
        ax.text(x + w/2, y + h/2, text, ha="center", va="center",
                fontsize=fontsize, fontweight="medium", zorder=3)
        return fb

    def draw_arrow(x1, y1, x2, y2, color=COLORS["dark"], lw=1.0, style="-|>", zorder=1):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                                    connectionstyle="arc3,rad=0"),
                    zorder=zorder)

    # Input
    draw_box(-0.1, -0.55, 1.4, 1.1,
             "Input\n$x$\n[cn, sk, pu,\nloc, mom]",
             color="#EFF6FF", fontsize=7.5)

    # GP model
    draw_box(1.9, -0.55, 1.6, 1.1,
             "GP Surrogate\n$\\mu$: Matern 5/2\n$\\sigma$: Additive",
             color="#F0FDF4", fontsize=7.5)

    # (μ, σ)
    ax.text(3.95, 0.0, "($\\mu$, $\\sigma$)", ha="center", va="center",
            fontsize=9, fontstyle="italic", color=COLORS["dark"])

    # z-score
    draw_box(4.35, -0.55, 1.2, 1.1,
             "z-score\n$z = \\mu / \\sigma$\nper $V_{\\mathrm{op}}$",
             color="#FEF3C7", fontsize=7.5)

    # Physics layer / Vmin
    draw_box(5.95, -0.55, 1.3, 1.1,
             "Physics Layer\n$V_{\\min}$\ninterp. $z = Z_t$",
             color="#FEE2E2", fontsize=7.5)

    # Forward arrows (top row)
    draw_arrow(1.45, 0.0, 1.85, 0.0, color=COLORS["primary"], lw=1.3)
    draw_arrow(3.6, 0.0, 4.30, 0.0, color=COLORS["primary"], lw=1.3)
    draw_arrow(5.6, 0.0, 5.90, 0.0, color=COLORS["primary"], lw=1.3)

    # Forward label
    ax.text(3.65, 0.45, "Forward", ha="center", va="center", fontsize=8,
            color=COLORS["primary"], fontweight="bold")

    # Inverse path (bottom arc)
    # Draw from Vmin back to Input via gradient
    inv_y = -1.15
    ax.annotate("", xy=(0.65, -0.6), xytext=(6.6, -0.6),
                arrowprops=dict(
                    arrowstyle="-|>",
                    color=COLORS["secondary"],
                    lw=1.3,
                    connectionstyle="arc3,rad=0.35",
                ), zorder=1)

    ax.text(3.65, inv_y + 0.0, "Gradient Inversion:  $\\nabla_x (V_{\\min}(x) - V^*)^2$",
            ha="center", va="center", fontsize=7.5,
            color=COLORS["secondary"], fontstyle="italic")

    # Output label
    ax.text(6.6, 0.75, "$V_{\\min}$", ha="center", va="center",
            fontsize=11, fontweight="bold", color=COLORS["secondary"])

    # Vmin target annotation
    ax.text(6.6, 1.15, "target $V^*$", ha="center", va="center",
            fontsize=7.5, color=COLORS["secondary"], fontstyle="italic",
            bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                      edgecolor=COLORS["secondary"], linewidth=0.6))

    # ── Legend ─────────────────────────────────────────────────────────
    legend_elements = [
        Line2D([0], [0], color=COLORS["primary"], lw=1.5, label="Forward path"),
        Line2D([0], [0], color=COLORS["secondary"], lw=1.5, label="Inverse path (gradient)"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", frameon=False,
              fontsize=7.5, ncol=2, bbox_to_anchor=(0.0, 1.12))

    fig.tight_layout()
    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Fig 2: Design Visualization
# ════════════════════════════════════════════════════════════════════════════

def fig2_design_visualization(save_path: Path) -> None:
    """(a) Quadrant weighting in (cn, pu) plane.
       (b) (l_com, l_sk) independent box → derived (l_PG, l_PD) band."""

    from src.condition_gen import generate_conditions

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 3.0))

    # ── Panel (a): (cn, pu) quadrant weighting ────────────────────────
    n_show = 500
    cols, cond = generate_conditions("D", n_show, seed=2027, metric="snmr")
    cn = cond[:, 0]
    pu = cond[:, 2]

    # Quadrant coloring
    colors_a = np.where(
        (cn < 0) & (pu > 0), COLORS["fsg"],
        np.where(
            (cn > 0) & (pu < 0), COLORS["sfg"],
            np.where(
                (cn < 0) & (pu < 0), COLORS["fn"],
                COLORS["sn"]
            )
        )
    )
    ax1.scatter(cn, pu, c=colors_a, s=8, alpha=0.45, edgecolors="none", zorder=2)

    # Quadrant lines
    ax1.axhline(0, color=COLORS["gray"], lw=0.5, ls="--", zorder=1)
    ax1.axvline(0, color=COLORS["gray"], lw=0.5, ls="--", zorder=1)

    # Quadrant labels with weights
    q_labels = {
        "FSG 45%": (-30, 35, COLORS["fsg"]),
        "SFG 20%": (30, -35, COLORS["sfg"]),
        "FN 20%": (-30, -35, COLORS["fn"]),
        "SN 15%": (30, 35, COLORS["sn"]),
    }
    for label, (x, y, c) in q_labels.items():
        ax1.text(x, y, label, ha="center", va="center", fontsize=7,
                 color=c, fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                           edgecolor=c, linewidth=0.5, alpha=0.85))

    ax1.set_xlabel("$c_n$ (mV)")
    ax1.set_ylabel("$p_u$ (mV)")
    ax1.set_title("(a) SNMR quadrant weighting", fontsize=9, pad=8)
    ax1.set_xlim(-65, 65)
    ax1.set_ylim(-65, 65)
    ax1.set_aspect("equal")
    ax1.tick_params(length=3)

    # ── Panel (b): Common+skew decomposition ──────────────────────────
    # Show the independent (l_com, l_sk) box and derived (l_PG, l_PD) band

    # Independent box in (l_com, l_sk) → mapped to (l_PG, l_PD)
    # l_PG = l_com + l_sk, l_PD = l_com - l_sk
    # l_com ∈ [0.7, 1.3], l_sk ∈ [-0.075, 0.075]
    # Transform: (l_com, l_sk) → (l_PG, l_PD)

    # Generate points in the independent box
    rng = np.random.default_rng(42)
    n_pts = 800
    l_com = rng.uniform(0.7, 1.3, n_pts)
    l_sk = rng.uniform(-0.075, 0.075, n_pts)
    l_pg = l_com + l_sk
    l_pd = l_com - l_sk

    ax2.scatter(l_pd, l_pg, s=6, alpha=0.35, color=COLORS["accent"], edgecolors="none", zorder=2)

    # Draw the derived band boundary
    # Corners of (l_com, l_sk) box mapped to (l_PD, l_PG):
    #   (0.7, -0.075) → (0.775, 0.625)
    #   (0.7, +0.075) → (0.625, 0.775)
    #   (1.3, -0.075) → (1.375, 1.225)
    #   (1.3, +0.075) → (1.225, 1.375)
    corners_lpd = [0.775, 0.625, 1.225, 1.375]
    corners_lpg = [0.625, 0.775, 1.375, 1.225]
    # Order: BL→TL→TR→BR for polygon
    order = [1, 0, 3, 2]
    band_x = [corners_lpd[i] for i in order]
    band_y = [corners_lpg[i] for i in order]
    from matplotlib.patches import Polygon
    band_patch = Polygon(list(zip(band_x, band_y)), closed=True,
                         facecolor=COLORS["accent"], alpha=0.08,
                         edgecolor=COLORS["accent"], linewidth=0.8,
                         linestyle="--", zorder=1)
    ax2.add_patch(band_patch)

    # Diagonal reference line (l_PG = l_PD)
    ax2.plot([0.55, 1.45], [0.55, 1.45], color=COLORS["gray"], lw=0.5,
             ls=":", zorder=1)

    # Nominal point
    ax2.plot(1.0, 1.0, "k+", markersize=8, markeredgewidth=1.2, zorder=3)
    ax2.text(1.02, 0.97, "nominal", fontsize=6.5, color=COLORS["gray"],
             ha="left", va="top")

    # Axis labels
    ax2.set_xlabel("$l_{\\mathrm{PD}}$")
    ax2.set_ylabel("$l_{\\mathrm{PG}}$")
    ax2.set_title("(b) Common+skew → device band", fontsize=9, pad=8)
    ax2.set_xlim(0.58, 1.42)
    ax2.set_ylim(0.58, 1.42)
    ax2.set_aspect("equal")
    ax2.tick_params(length=3)

    # Correlation annotation
    ax2.text(0.62, 1.38, "$\\rho(l_{PG}, l_{PD}) \\approx 0.88$",
             fontsize=7, color=COLORS["accent"], fontstyle="italic",
             bbox=dict(boxstyle="round,pad=0.12", facecolor="white",
                       edgecolor=COLORS["accent"], linewidth=0.5))

    fig.tight_layout(w_pad=2.5)
    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Fig S1: 6T SRAM Cell Structure
# ════════════════════════════════════════════════════════════════════════════

def fig_sram_cell_6t(save_path: Path) -> None:
    """Simplified 6T SRAM cell schematic highlighting PU, PG, PD."""

    fig, ax = plt.subplots(figsize=(3.2, 3.8))
    ax.set_xlim(-1.5, 4.5)
    ax.set_ylim(-0.5, 5.5)
    ax.axis("off")

    # ── Transistor positions ──────────────────────────────────────────
    # Cross-coupled inverters + access transistors
    # Simplified: show as boxes with labels

    def draw_transistor(ax, cx, cy, label, color, w=0.8, h=0.45):
        rect = FancyBboxPatch((cx - w/2, cy - h/2), w, h,
                              boxstyle="round,pad=0.04",
                              facecolor=color, edgecolor=COLORS["dark"],
                              linewidth=0.8, zorder=2)
        ax.add_patch(rect)
        ax.text(cx, cy, label, ha="center", va="center", fontsize=8,
                fontweight="bold", zorder=3)

    def draw_wire(ax, x1, y1, x2, y2, **kwargs):
        defaults = dict(color=COLORS["dark"], lw=0.8, solid_capstyle="round")
        defaults.update(kwargs)
        ax.plot([x1, x2], [y1, y2], **defaults, zorder=1)

    def draw_node(ax, x, y, label="", size=3.5):
        ax.plot(x, y, "o", color=COLORS["dark"], markersize=size, zorder=4)
        if label:
            ax.text(x + 0.12, y, label, fontsize=7, va="center", ha="left",
                    color=COLORS["dark"])

    # VDD
    ax.text(0.7, 5.1, "$V_{\\mathrm{DD}}$", ha="center", fontsize=9,
            fontweight="bold", color=COLORS["secondary"])
    draw_wire(ax, 0.7, 4.9, 0.7, 4.5)

    # VSS
    ax.text(2.5, -0.2, "$V_{\\mathrm{SS}}$", ha="center", fontsize=9,
            fontweight="bold", color=COLORS["primary"])
    draw_wire(ax, 2.5, 0.1, 2.5, 0.5)

    # PU (pull-up) - PMOS - left and right
    draw_transistor(ax, 0.7, 4.25, "PU₁", "#FECACA", w=0.7, h=0.4)  # light red
    draw_transistor(ax, 2.5, 4.25, "PU₂", "#FECACA", w=0.7, h=0.4)
    draw_wire(ax, 0.7, 4.05, 0.7, 3.6)
    draw_wire(ax, 2.5, 4.05, 2.5, 3.6)

    # PD (pull-down) - NMOS - left and right
    draw_transistor(ax, 0.7, 0.75, "PD₁", "#DBEAFE", w=0.7, h=0.4)  # light blue
    draw_transistor(ax, 2.5, 0.75, "PD₂", "#DBEAFE", w=0.7, h=0.4)
    draw_wire(ax, 0.7, 0.55, 0.7, 0.35)
    draw_wire(ax, 2.5, 0.55, 2.5, 0.35)

    # Internal nodes Q and Q̄
    draw_node(ax, 0.7, 3.6, "$Q$")
    draw_node(ax, 2.5, 3.6, "$\\bar{Q}$")
    draw_wire(ax, 0.7, 3.6, 0.7, 1.0)
    draw_wire(ax, 2.5, 3.6, 2.5, 1.0)

    # Cross-coupling wires
    draw_wire(ax, 0.7, 3.0, -0.3, 3.0, color=COLORS["gray"], lw=0.6, ls="--")
    draw_wire(ax, -0.3, 3.0, -0.3, 2.4, color=COLORS["gray"], lw=0.6, ls="--")
    draw_wire(ax, -0.3, 2.4, 2.5, 2.4, color=COLORS["gray"], lw=0.6, ls="--")
    draw_wire(ax, 2.5, 2.4, 2.5, 2.6, color=COLORS["gray"], lw=0.6, ls="--")

    draw_wire(ax, 2.5, 3.0, 3.5, 3.0, color=COLORS["gray"], lw=0.6, ls="--")
    draw_wire(ax, 3.5, 3.0, 3.5, 2.4, color=COLORS["gray"], lw=0.6, ls="--")
    draw_wire(ax, 3.5, 2.4, 0.7, 2.4, color=COLORS["gray"], lw=0.6, ls="--")
    draw_wire(ax, 0.7, 2.4, 0.7, 2.6, color=COLORS["gray"], lw=0.6, ls="--")

    # PG (pass-gate) - NMOS - access transistors
    # PG₁ bridges between BL (x≈-0.7) and Q (x=0.7); PG₂ bridges Q̄ (x=2.5) and BL̄ (x≈3.9)
    pg1_x, pg1_y = 0.0, 3.0
    pg2_x, pg2_y = 3.2, 3.0
    draw_transistor(ax, pg1_x, pg1_y, "PG₁", "#FEF3C7", w=0.65, h=0.38)  # light yellow
    draw_transistor(ax, pg2_x, pg2_y, "PG₂", "#FEF3C7", w=0.65, h=0.38)

    # BL → PG₁: vertical up from BL (x=-0.7, y=2.0) to y=3.0, horizontal to PG₁
    draw_wire(ax, -0.7, 2.0, -0.7, 3.0)
    draw_wire(ax, -0.7, 3.0, pg1_x, 3.0)
    ax.text(-0.7, 1.8, "BL", ha="center", fontsize=8, fontweight="bold",
            color=COLORS["accent"])

    # PG₁ → Q: horizontal to Q column, then up to Q node
    draw_wire(ax, pg1_x, 3.0, 0.7, 3.0)

    # BL̄ → PG₂: vertical up from BL̄ (x=3.9, y=2.0) to y=3.0, horizontal to PG₂
    draw_wire(ax, 3.9, 2.0, 3.9, 3.0)
    draw_wire(ax, 3.9, 3.0, pg2_x, 3.0)
    ax.text(3.9, 1.8, "$\\overline{\\mathrm{BL}}$", ha="center", fontsize=8,
            fontweight="bold", color=COLORS["accent"])

    # PG₂ → Q̄: horizontal to Q̄ column
    draw_wire(ax, pg2_x, 3.0, 2.5, 3.0)

    # Word line — shared by both PGs
    draw_wire(ax, pg1_x, 3.0, pg1_x, 3.5)
    draw_wire(ax, pg1_x, 3.5, pg2_x, 3.5)
    draw_wire(ax, pg2_x, 3.5, pg2_x, 3.0)
    ax.text(1.6, 3.75, "WL", ha="center", fontsize=8, fontweight="bold",
            color=COLORS["orange"])

    # ── Legend ─────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(facecolor="#FECACA", edgecolor=COLORS["dark"], label="PU (PMOS)", linewidth=0.6),
        mpatches.Patch(facecolor="#DBEAFE", edgecolor=COLORS["dark"], label="PD (NMOS)", linewidth=0.6),
        mpatches.Patch(facecolor="#FEF3C7", edgecolor=COLORS["dark"], label="PG (NMOS)", linewidth=0.6),
    ]
    ax.legend(handles=legend_items, loc="lower center", frameon=False,
              fontsize=7, ncol=3, bbox_to_anchor=(0.5, -0.08))

    fig.tight_layout()
    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Fig S2: Butterfly Curve / SNM
# ════════════════════════════════════════════════════════════════════════════

def fig_butterfly_snm(save_path: Path) -> None:
    """Butterfly curve with two lobes and SNM annotation."""

    fig, ax = plt.subplots(figsize=(3.8, 3.2))

    # Generate synthetic butterfly curves
    v = np.linspace(0, 1, 200)
    # Left inverter VTC
    vtc_l = 1.0 / (1.0 + np.exp(-8 * (v - 0.48)))
    # Right inverter VTC (mirrored)
    vtc_r = 1.0 / (1.0 + np.exp(-8 * (v - 0.52)))
    vtc_r_inv = 1.0 - vtc_r  # flipped for overlay

    # Plot VTCs
    ax.plot(v, vtc_l, color=COLORS["primary"], lw=1.5, label="Inverter I (left)", zorder=3)
    ax.plot(v, vtc_r_inv, color=COLORS["secondary"], lw=1.5, label="Inverter II (right)", zorder=3)

    diff = vtc_l - vtc_r_inv
    cross_idx = np.where(np.diff(np.sign(diff)))[0][0]
    v_cross = v[cross_idx]

    v_left = v[:cross_idx + 1]
    fill_bot_l = np.minimum(vtc_l[:cross_idx + 1], vtc_r_inv[:cross_idx + 1])
    fill_top_l = np.maximum(vtc_l[:cross_idx + 1], vtc_r_inv[:cross_idx + 1])
    ax.fill_between(v_left, fill_bot_l, fill_top_l,
                    alpha=0.15, color=COLORS["primary"], zorder=1)

    v_right = v[cross_idx:]
    fill_bot_r = np.minimum(vtc_l[cross_idx:], vtc_r_inv[cross_idx:])
    fill_top_r = np.maximum(vtc_l[cross_idx:], vtc_r_inv[cross_idx:])
    ax.fill_between(v_right, fill_bot_r, fill_top_r,
                    alpha=0.15, color=COLORS["secondary"], zorder=1)

    # Approximate max inscribed square in left lobe: place at ~40% of lobe width from crossing
    v_mid_l = v_cross - 0.4 * (v_cross - v_left[0])
    idx_ml = np.argmin(np.abs(v - v_mid_l))
    gap_l = abs(vtc_l[idx_ml] - vtc_r_inv[idx_ml])
    snm_l_size = 0.6 * gap_l
    snm_l_cx = v_mid_l
    snm_l_cy = 0.5 * (vtc_l[idx_ml] + vtc_r_inv[idx_ml])
    sq_l = plt.Rectangle((snm_l_cx - snm_l_size / 2, snm_l_cy - snm_l_size / 2),
                          snm_l_size, snm_l_size, fill=False,
                          edgecolor=COLORS["primary"], lw=1.2, ls="--", zorder=4)
    ax.add_patch(sq_l)
    ax.annotate("", xy=(snm_l_cx + snm_l_size / 2, snm_l_cy - snm_l_size / 2),
                xytext=(snm_l_cx - snm_l_size / 2, snm_l_cy - snm_l_size / 2),
                arrowprops=dict(arrowstyle="<->", color=COLORS["primary"], lw=1.0))
    ax.text(snm_l_cx, snm_l_cy - snm_l_size / 2 - 0.04, "$\\mathrm{SNM}_L$",
            ha="center", fontsize=7.5, color=COLORS["primary"], fontweight="bold")

    # Right lobe: same approach, ~40% from crossing into right lobe
    v_mid_r = v_cross + 0.4 * (v_right[-1] - v_cross)
    idx_mr = np.argmin(np.abs(v - v_mid_r))
    gap_r = abs(vtc_l[idx_mr] - vtc_r_inv[idx_mr])
    snm_r_size = 0.6 * gap_r
    snm_r_cx = v_mid_r
    snm_r_cy = 0.5 * (vtc_l[idx_mr] + vtc_r_inv[idx_mr])
    sq_r = plt.Rectangle((snm_r_cx - snm_r_size / 2, snm_r_cy - snm_r_size / 2),
                          snm_r_size, snm_r_size, fill=False,
                          edgecolor=COLORS["secondary"], lw=1.2, ls="--", zorder=4)
    ax.add_patch(sq_r)
    ax.annotate("", xy=(snm_r_cx + snm_r_size / 2, snm_r_cy - snm_r_size / 2),
                xytext=(snm_r_cx - snm_r_size / 2, snm_r_cy - snm_r_size / 2),
                arrowprops=dict(arrowstyle="<->", color=COLORS["secondary"], lw=1.0))
    ax.text(snm_r_cx, snm_r_cy - snm_r_size / 2 - 0.04, "$\\mathrm{SNM}_R$",
            ha="center", fontsize=7.5, color=COLORS["secondary"], fontweight="bold")

    ax.text(v_mid_l, fill_top_l[idx_ml] + 0.04, "Left lobe", ha="center", fontsize=7,
            color=COLORS["primary"], fontstyle="italic")
    ax.text(v_mid_r, fill_top_r[idx_mr - cross_idx] + 0.04, "Right lobe", ha="center",
            fontsize=7, color=COLORS["secondary"], fontstyle="italic")

    # SNM = min annotation
    ax.text(0.50, 0.95, "$\\mathrm{SNM} = \\min(\\mathrm{SNM}_L,\\; \\mathrm{SNM}_R)$",
            ha="center", fontsize=8.5, fontstyle="italic",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      edgecolor=COLORS["dark"], linewidth=0.6))

    ax.set_xlabel("$V_{\\mathrm{out}}$ (V)")
    ax.set_ylabel("$V_{\\mathrm{in}}$ (V)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.legend(frameon=False, fontsize=7, loc="upper left")
    ax.tick_params(length=3)

    fig.tight_layout()
    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Fig S3: Lobe-resolved Z-score Bias Correction
# ════════════════════════════════════════════════════════════════════════════

def fig_lobe_zscore(save_path: Path) -> None:
    """Illustrate the bias of min-statistics z and lobe-resolved correction."""

    from scipy.stats import norm, multivariate_normal

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.0))

    # ── Panel (a): Z_bias vs correlation ρ_LR ────────────────────────
    ax = axes[0]
    z_target = 6.5
    rho_vals = np.linspace(-0.5, 0.95, 200)
    z_biases = []

    for rho in rho_vals:
        mu_L, sigma_L = 0.15, 0.023  # typical values giving z ≈ 6.5
        mu_R, sigma_R = 0.15, 0.023
        mean = np.array([mu_L, mu_R])
        cov = np.array([[sigma_L**2, rho * sigma_L * sigma_R],
                        [rho * sigma_L * sigma_R, sigma_R**2]])
        # p_fail for independent
        p_L = norm.cdf(0, mu_L, sigma_L)
        p_R = norm.cdf(0, mu_R, sigma_R)
        # joint via multivariate_normal
        lower = np.array([-np.inf, -np.inf])
        mvn_dist = multivariate_normal(mean=mean, cov=cov)
        p_joint = mvn_dist.cdf(lower)
        p_fail = p_L + p_R - p_joint
        p_fail = max(p_fail, 1e-20)
        z_eff = norm.isf(p_fail)
        # E[min(X,Y)] for i.i.d. X~N(mu,σ²): mu - σ/√π,  std: σ√(1 - 1/π)
        mu_min = mu_L - sigma_L / np.sqrt(np.pi)
        sigma_min = sigma_L * np.sqrt(1.0 - 1.0 / np.pi)
        z_naive = mu_min / sigma_min
        z_biases.append(z_eff - z_naive)

    ax.plot(rho_vals, z_biases, color=COLORS["primary"], lw=1.5)
    ax.axhline(0, color=COLORS["gray"], lw=0.5, ls=":")

    # Mark key regions
    ax.axvspan(-0.5, 0, alpha=0.05, color=COLORS["accent"])
    ax.axvspan(0, 0.5, alpha=0.05, color=COLORS["orange"])
    ax.axvspan(0.5, 0.95, alpha=0.05, color=COLORS["secondary"])

    ax.text(-0.25, max(z_biases) * 0.85, "Independent\n(+0.7$\\sigma$)", fontsize=6.5,
            ha="center", color=COLORS["accent"], fontstyle="italic")
    ax.text(0.75, max(z_biases) * 0.85, "Anticorrelated\n(+1.9$\\sigma$)", fontsize=6.5,
            ha="center", color=COLORS["secondary"], fontstyle="italic")

    ax.set_xlabel("Lobe correlation $\\rho_{LR}$")
    ax.set_ylabel("$z_{\\mathrm{eff}} - z_{\\mathrm{naive}}$  ($\\sigma$)")
    ax.set_title("(a) Bias of naive z vs correlation", fontsize=9, pad=8)
    ax.set_xlim(-0.5, 0.95)
    ax.tick_params(length=3)

    # ── Panel (b): CDF comparison — min vs true ──────────────────────
    ax = axes[1]

    mu, sigma = 0.15, 0.023
    z_grid = np.linspace(0, 8, 300)

    z_naive_val = (mu - sigma / np.sqrt(np.pi)) / (sigma * np.sqrt(1.0 - 1.0 / np.pi))
    p_gaussian = norm.cdf(-z_grid, loc=z_naive_val, scale=1)
    rho_ex = 0.3
    z_eff_shift = 0.4
    p_true = norm.cdf(-z_grid, loc=(z_naive_val + z_eff_shift), scale=1.05)

    ax.plot(z_grid, p_gaussian, color=COLORS["primary"], lw=1.5, label="Naive (min-Gaussian)")
    ax.plot(z_grid, p_true, color=COLORS["secondary"], lw=1.5, label="Lobe-resolved (exact)")

    ax.axvline(z_target, color=COLORS["dark"], lw=0.8, ls="--", label=f"$Z_t = {z_target}$")

    # Shade the difference region
    mask = z_grid > 5.5
    ax.fill_between(z_grid[mask], p_gaussian[mask], p_true[mask],
                    alpha=0.2, color=COLORS["secondary"])

    ax.set_xlabel("z-score")
    ax.set_ylabel("$P(\\mathrm{SNM} < 0)$")
    ax.set_title("(b) Tail probability: naive vs exact", fontsize=9, pad=8)
    ax.set_yscale("log")
    ax.set_ylim(1e-12, 1e-1)
    ax.set_xlim(0, 8)
    ax.legend(frameon=False, fontsize=6.5, loc="lower left")
    ax.tick_params(length=3)

    # Annotation
    ax.annotate("Optimistic bias\nregion", xy=(6.8, 1e-9), fontsize=6.5,
                color=COLORS["secondary"], fontstyle="italic", ha="center")

    fig.tight_layout(w_pad=2.5)
    fig.savefig(save_path, dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  saved: {save_path}")


# ════════════════════════════════════════════════════════════════════════════
# Fig S4: Physics Layer — z(Vop) → Vmin
# ════════════════════════════════════════════════════════════════════════════

def fig_physics_layer(save_path: Path) -> None:
    """z(Vop) curve crossing Z_t, with Vmin interpolation."""

    fig, ax = plt.subplots(figsize=(4.2, 3.2))

    vop = np.linspace(0.35, 0.85, 200)
    z_target = 6.50

    # Condition A: crosses Z_t ≈ 6.5 near vop ≈ 0.55V (fast cell)
    z_a = 1.0 + 12.0 * (1.0 - np.exp(-5.0 * (vop - 0.35)))
    # Condition B: crosses Z_t ≈ 6.5 near vop ≈ 0.70V (harder cell)
    z_b = 0.8 + 10.0 * (1.0 - np.exp(-3.5 * (vop - 0.35)))
    # Condition C (censored): z(0.4) > Z_t — very fast corner
    z_c = 0.5 + 15.0 * (1.0 - np.exp(-12.0 * (vop - 0.35)))

    ax.plot(vop, z_a, color=COLORS["primary"], lw=1.5, label="Condition A", zorder=3)
    ax.plot(vop, z_b, color=COLORS["secondary"], lw=1.5, label="Condition B", zorder=3)
    ax.plot(vop, z_c, color=COLORS["accent"], lw=1.2, ls="-.", label="Condition C", zorder=3)

    ax.axhline(z_target, color=COLORS["dark"], lw=0.8, ls="--", zorder=2)
    ax.text(0.83, z_target + 0.15, "$Z_t = 6.50$", fontsize=7.5,
            color=COLORS["dark"], ha="right", va="bottom")

    # Condition A crossing
    idx_a = np.searchsorted(z_a, z_target)
    vmin_a = vop[min(idx_a, len(vop) - 1)]
    ax.plot(vmin_a, z_target, "o", color=COLORS["primary"], markersize=5, zorder=4)
    ax.plot([vmin_a, vmin_a], [0, z_target], color=COLORS["primary"], lw=0.6, ls=":", zorder=1)
    ax.text(vmin_a, 0.3, f"$V_{{\\min}}^A = {vmin_a:.2f}$ V",
            ha="center", fontsize=7, color=COLORS["primary"], fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.1", facecolor="white",
                      edgecolor=COLORS["primary"], linewidth=0.5))

    # Condition B crossing
    idx_b = np.searchsorted(z_b, z_target)
    vmin_b = vop[min(idx_b, len(vop) - 1)]
    ax.plot(vmin_b, z_target, "s", color=COLORS["secondary"], markersize=5, zorder=4)
    ax.plot([vmin_b, vmin_b], [0, z_target], color=COLORS["secondary"], lw=0.6, ls=":", zorder=1)
    ax.text(vmin_b, 0.3, f"$V_{{\\min}}^B = {vmin_b:.2f}$ V",
            ha="center", fontsize=7, color=COLORS["secondary"], fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.1", facecolor="white",
                      edgecolor=COLORS["secondary"], linewidth=0.5))

    # Interpolation arrow between the two crossings
    mid_interp = 0.5 * (vmin_a + vmin_b)
    ax.annotate("linear interp.", xy=(mid_interp, z_target), xytext=(mid_interp, z_target + 1.0),
                fontsize=6.5, color=COLORS["gray"], ha="center", fontstyle="italic",
                arrowprops=dict(arrowstyle="->", color=COLORS["gray"], lw=0.6))

    # Censored region: Condition C already above Z_t before 0.4V
    ax.axvspan(0.35, 0.40, alpha=0.08, color=COLORS["gray"])
    ax.text(0.55, 11.5, "Censored: $z(0.4\\,\\mathrm{V}) > Z_t \\rightarrow V_{\\min} < 0.4\\,\\mathrm{V}$",
            ha="center", fontsize=6, color=COLORS["gray"], fontstyle="italic")

    ax.set_xlabel("$V_{\\mathrm{op}}$ (V)")
    ax.set_ylabel("$z = \\mu / \\sigma$")
    ax.set_xlim(0.35, 0.85)
    ax.set_ylim(0, 14)
    ax.legend(frameon=False, fontsize=7.5, loc="upper right")
    ax.tick_params(length=3)

    fig.tight_layout()
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

    print(f"Generating paper explanatory figures → {OUT_DIR}/  (format={ext}, dpi={args.dpi})")

    fig1_pipeline_overview(OUT_DIR / f"fig1_pipeline_overview.{ext}")
    fig2_design_visualization(OUT_DIR / f"fig2_design_visualization.{ext}")
    fig_sram_cell_6t(OUT_DIR / f"fig_sram_cell_6t.{ext}")
    fig_butterfly_snm(OUT_DIR / f"fig_butterfly_snm.{ext}")
    fig_lobe_zscore(OUT_DIR / f"fig_lobe_zscore.{ext}")
    fig_physics_layer(OUT_DIR / f"fig_physics_layer.{ext}")

    print(f"\nDone. {6} figures saved to {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
