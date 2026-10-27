"""Paper-style figures.

rcParams, colours and window conventions are copied from manuscript/code/gen_figures.py
(Fig. 5 / 10 / 11): RdYlBu_r filled cell Vmin pinned at the target, solid black =
read limit, dash-dot = write limit, grey dash = reference spec, dotted box =
training range, stars = binding corners (filled when they pass). Keep in sync by hand
-- gen_figures.py draws at import time, so it cannot be imported.
"""
from __future__ import annotations

import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402

from .config import AXIS  # noqa: E402

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
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
COL, DCOL = 3.5, 7.16
C_READ, C_WRITE, C_ACC = "#1f4e79", "#a63603", "#2a7f62"
MODE_COLOR = {"read": C_READ, "write": C_WRITE}
SERIES = [C_READ, C_ACC, C_WRITE, "0.45", "#6a4c93", "#b08900"]
# FSG solid / SFG dash-dot echoes the window figures (read limit solid, write limit dash-dot)
CORNER_LS = {"FSG": "-", "SFG": "-.", "FFG": "--", "SSG": ":", "nominal": (0, (1, 1)), None: (0, (1, 1))}
CORNER_MK = {"FSG": "o", "SFG": "^", "FFG": "s", "SSG": "D", "nominal": "x", None: "x"}
NAN_FILL = 0.85        # above the supply grid -> fails, drawn as deep red (paper: nan_to_num 0.85)


def sgn(x: float, fmt: str = "+.1f") -> str:
    return format(x, fmt).replace("-", "−")


def axis_label(key: str) -> str:
    a = AXIS[key]
    return f"${a['symbol']}$" + ("" if a["unit"] == "×" else f" ({a['unit']})")


def levels(target: float) -> np.ndarray:
    lo, hi = min(0.40, target - 0.05), max(0.75, target + 0.05)
    return np.arange(lo, hi + 0.0125, 0.025)


def _norm(lv: np.ndarray, target: float) -> TwoSlopeNorm:
    return TwoSlopeNorm(vmin=lv[0], vcenter=target, vmax=lv[-1])


def _crosses(a: np.ndarray, v: float) -> bool:
    a = a[np.isfinite(a)]
    return a.size > 0 and a.min() < v < a.max()


def cell(vr: np.ndarray | None, vw: np.ndarray | None) -> np.ndarray:
    parts = [np.nan_to_num(v, nan=NAN_FILL) for v in (vr, vw) if v is not None]
    return np.maximum.reduce(parts)


def window(panels: list[dict], xk: str, yk: str, target: float, reference: float,
           box: tuple[tuple[float, float], tuple[float, float]] | None,
           what: str = "cell") -> plt.Figure:
    """Process-window panels. panel = dict(title, x, y, vr, vw, markers)."""
    n = len(panels)
    ncol = 1 if n == 1 else 2
    nrow = math.ceil(n / ncol)
    size = (COL + 0.75, 3.15) if n == 1 else (DCOL, 2.85 * nrow)
    fig, axes = plt.subplots(nrow, ncol, figsize=size, squeeze=False, sharex=True, sharey=True)
    lv = levels(target)
    cf = None
    for ax, p in zip(axes.ravel(), panels):
        X, Y = np.meshgrid(p["x"], p["y"])
        vr, vw = p.get("vr"), p.get("vw")
        fill = cell(vr if what in ("cell", "read") else None, vw if what in ("cell", "write") else None)
        cf = ax.contourf(X, Y, fill, levels=lv, cmap="RdYlBu_r", norm=_norm(lv, target), extend="both")
        if _crosses(fill, reference):
            ax.contour(X, Y, fill, levels=[reference], colors="0.25", linewidths=1.0, linestyles="dashed")
        for v, ls in ((vr, "solid"), (vw, "dashdot")):
            if v is not None:
                f = np.nan_to_num(v, nan=NAN_FILL)
                if _crosses(f, target):
                    ax.contour(X, Y, f, levels=[target], colors="k", linewidths=1.8, linestyles=ls)
        if box is not None:
            (bx0, bx1), (by0, by1) = box
            if X.min() < bx0 - 1e-9 or X.max() > bx1 + 1e-9 or Y.min() < by0 - 1e-9 or Y.max() > by1 + 1e-9:
                ax.add_patch(plt.Rectangle((bx0, by0), bx1 - bx0, by1 - by0, fill=False,
                                           ec="0.15", lw=0.9, ls=":", zorder=4))
        for mk in p.get("markers", []):
            moved = abs(mk["x1"] - mk["x0"]) + abs(mk["y1"] - mk["y0"]) > 1e-6 * (1 + abs(mk["x0"]) + abs(mk["y0"]))
            if moved:
                ax.scatter([mk["x0"]], [mk["y0"]], s=30, marker="*", facecolor="none",
                           edgecolor="0.35", lw=0.8, zorder=5)
                ax.annotate("", (mk["x1"], mk["y1"]), (mk["x0"], mk["y0"]), zorder=5,
                            arrowprops=dict(arrowstyle="->", color="0.15", lw=0.8))
            ax.scatter([mk["x1"]], [mk["y1"]], s=46, marker="*", zorder=6,
                       facecolor="#111111" if mk["ok"] else "none", edgecolor="#111111", lw=1.0)
            ax.annotate(mk["label"], (mk["x1"], mk["y1"]), textcoords="offset points",
                        xytext=(5, 3), fontsize=6.4, color="#111111", fontweight="bold")
        ax.set_xlim(X.min(), X.max())
        ax.set_ylim(Y.min(), Y.max())
        ax.set_title(p["title"], fontsize=7.4, linespacing=1.35)
    for ax in axes[-1, :]:
        ax.set_xlabel(axis_label(xk))
    for ax in axes[:, 0]:
        ax.set_ylabel(axis_label(yk))
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    title_lines = max(p["title"].count("\n") + 1 for p in panels)
    if nrow > 1 and title_lines > 2:      # keep the paper's spacing for 2-line titles
        fig.subplots_adjust(hspace=0.2 + 0.11 * (title_lines - 2))
    lines = [f"process window at target $V_{{min}} \\leq$ {target:.3f} V — blue passes, red fails.",
             f"Solid black = read limit, long-dash = write limit, grey dash = reference {reference:.3f} V."]
    if any(p.get("markers") for p in panels):
        lines.append("Stars = binding corners (filled = pass); hollow grey star = before the lever moved it.")
    text = "\n".join(lines) if n == 1 else " ".join(lines[:2]) + "".join("\n" + x for x in lines[2:])
    fig.suptitle(text, fontsize=6.6 if n == 1 else 7.4, y=1.08 if n == 1 else 1.0 + 0.04 / nrow)
    cb = fig.colorbar(cf, ax=axes, pad=0.015 if n > 1 else 0.03, fraction=0.04 if n > 1 else 0.06)
    label = {"cell": "cell $V_{min}=\\max$(read, write)  (V)", "read": "read $V_{min}$ (V)",
             "write": "write $V_{min}$ (V)"}[what]
    cb.set_label(label, fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    return fig


def curves(series: list[dict], xlabel: str, target: float, reference: float,
           roots: list[float] = (), title: str | None = None) -> plt.Figure:
    """Vmin along one axis. series = dict(x, y, label, mode, corner); y NaN where not finite."""
    fig, ax = plt.subplots(figsize=(COL + 0.35, 2.7))
    for s in series:
        ax.plot(s["x"], s["y"], color=MODE_COLOR.get(s["mode"], "0.3"),
                ls=CORNER_LS.get(s.get("corner"), "-"), label=s["label"])
    ax.axhline(target, color="k", lw=0.9, label=f"target {target:.3f} V")
    ax.axhline(reference, color="0.45", lw=0.8, ls="--", label=f"reference {reference:.3f} V")
    for r in roots:
        ax.axvline(r, color="k", lw=0.6, ls=":")
        ax.scatter([r], [target], s=22, facecolor="white", edgecolor="k", lw=0.9, zorder=5)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("$V_{min}$ (V)")
    if title:
        ax.set_title(title, fontsize=7.6)
    ax.legend(frameon=False, fontsize=6.2, ncol=2, loc="best")
    return fig


def zcurves(items: list[dict], z: float, z_text: str) -> plt.Figure:
    """The physics layer: z(Vop) per check against the Z threshold."""
    fig, ax = plt.subplots(figsize=(COL + 0.35, 2.7))
    for it in items:
        c = MODE_COLOR.get(it["mode"], "0.3")
        ax.plot(it["vops"], it["z"], color=c, ls=CORNER_LS.get(it.get("corner"), "-"),
                marker=CORNER_MK.get(it.get("corner"), "o"), ms=2.6, label=it["label"])
        if it["status"] == 0:
            ax.plot([it["vmin"]] * 2, [0, z], color=c, lw=0.6, ls=":")
    ax.axhline(z, color="k", lw=0.9)
    ax.text(0.01, z, f"  Z = {z:.3f}  ({z_text})", transform=ax.get_yaxis_transform(),
            va="bottom", fontsize=6.2)
    ax.set_ylim(bottom=0)
    ax.set_xlabel("$V_{op}$ (V)")
    ax.set_ylabel("$z = \\mu / \\sigma$")
    ax.legend(frameon=False, fontsize=5.8, ncol=4, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    return fig


def lever_usage(rows: list[tuple[str, np.ndarray, bool, list[str]]], levers: list) -> plt.Figure:
    """How much of each lever's ceiling every solution spends. row = (name, u, reached, texts)."""
    k, n = len(levers), len(rows)
    fig, ax = plt.subplots(figsize=(COL + 0.9, 0.16 * n * k + 0.35 * n + 0.9))
    h = 0.8 / k
    for i, (_, u, ok, texts) in enumerate(rows):
        for j in range(k):
            y = i + (j - (k - 1) / 2) * h
            ax.barh(y, u[j] * 100, height=h * 0.86, color=SERIES[j % len(SERIES)],
                    hatch=None if ok else "////", edgecolor="white" if ok else "0.2", lw=0.4)
            if u[j] > 1e-9:
                ax.text(u[j] * 100 + 1.5, y, texts[j], va="center", fontsize=5.8)
    ax.set_yticks(range(n))
    ax.set_yticklabels([r[0] + ("" if r[2] else "\n(not reached)") for r in rows], fontsize=6.4)
    ax.invert_yaxis()
    ax.set_xlim(0, 125)
    ax.axvline(100, color="0.3", lw=0.7, ls="--")
    ax.set_xlabel("lever usage (% of its ceiling); hatched = target not reached")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=SERIES[j % len(SERIES)]) for j in range(k)],
              labels=[f"{lv.label} ({lv.limit_text()})" for lv in levers],
              frameon=False, fontsize=6.0, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=min(k, 3))
    ax.grid(axis="y", visible=False)
    return fig


def lever_sweeps(sweeps: list[dict], target: float, reference: float) -> plt.Figure:
    """Binding Vmin vs usage, one lever at a time. sweep = dict(label, usage, binding, solution)."""
    fig, ax = plt.subplots(figsize=(COL + 0.35, 2.7))
    for j, s in enumerate(sweeps):
        y = np.where(np.isfinite(s["binding"]), s["binding"], np.nan)
        ax.plot(np.asarray(s["usage"]) * 100, y, color=SERIES[j % len(SERIES)], label=s["label"],
                marker="o", ms=2.2)
        if s.get("solution") is not None:
            ax.scatter([s["solution"] * 100], [target], s=24, marker="D", zorder=5,
                       facecolor=SERIES[j % len(SERIES)], edgecolor="k", lw=0.5)
    ax.axhline(target, color="k", lw=0.9, label=f"target {target:.3f} V")
    finite = np.concatenate([np.asarray(s["binding"])[np.isfinite(s["binding"])] for s in sweeps])
    if finite.size and finite.min() - 0.01 <= reference <= finite.max() + 0.01:
        ax.axhline(reference, color="0.45", lw=0.8, ls="--", label=f"reference {reference:.3f} V")
    ax.set_xlabel("lever usage alone (% of its ceiling)")
    ax.set_ylabel("binding $V_{min}$ (V)")
    ax.legend(frameon=False, fontsize=6.0)
    return fig


def _mag(lv, u) -> float:
    """Lever change as a positive magnitude (scale/pull in %, shift in its own units)."""
    a = lv.change(u)
    return abs(a) if lv.type == "shift" else abs(a) * 100


def _mag_label(lv) -> str:
    if lv.type == "shift":
        return f"{lv.label}: |shift| ({AXIS[lv.axes[0]]['unit']})"
    return f"{lv.label}: {'reduction' if lv.max_change < 0 else 'increase'} (%)"


def lever_map(ua: np.ndarray, ub: np.ndarray, B: np.ndarray, la, lb, target: float,
              points: list[dict]) -> plt.Figure:
    """Binding Vmin over two levers' changes; the black line is every combination that just passes."""
    fig, ax = plt.subplots(figsize=(COL + 0.6, 2.9))
    XA, XB = np.meshgrid([_mag(la, u) for u in ua], [_mag(lb, u) for u in ub])
    lv = levels(target)
    f = np.nan_to_num(np.where(np.isfinite(B), B, np.nan), nan=NAN_FILL)
    cf = ax.contourf(XA, XB, f, levels=lv, cmap="RdYlBu_r", norm=_norm(lv, target), extend="both")
    if _crosses(f, target):
        ax.contour(XA, XB, f, levels=[target], colors="k", linewidths=1.8)
    for p, mk in zip(points, ("D", "o", "s", "^", "v")):
        ax.scatter([_mag(la, p["ua"])], [_mag(lb, p["ub"])], s=34, marker=mk, facecolor="white",
                   edgecolor="k", lw=0.9, zorder=5, label=p["name"], clip_on=False)
    ax.set_xlabel(_mag_label(la))
    ax.set_ylabel(_mag_label(lb))
    ax.set_title("binding $V_{min}$ over two levers (others at 0); black = just passes", fontsize=7.2)
    if points:
        ax.legend(frameon=True, framealpha=0.85, fontsize=6.0, loc="upper right")
    cb = fig.colorbar(cf, ax=ax, pad=0.02)
    cb.set_label("binding $V_{min}$ (V)", fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    return fig


def robust(draws: dict[str, np.ndarray], target: float) -> plt.Figure:
    """Posterior spread of the binding Vmin at each solution."""
    fig, ax = plt.subplots(figsize=(COL + 0.35, 2.9))
    finite = np.concatenate([d[np.isfinite(d)] for d in draws.values()] or [np.array([target])])
    bins = np.linspace(min(finite.min(), target - 0.005), max(finite.max(), target + 0.005), 70)
    for j, (name, d) in enumerate(draws.items()):
        p = float(np.mean(d <= target))
        ax.hist(d[np.isfinite(d)], bins=bins, histtype="step", lw=1.1,
                color=SERIES[j % len(SERIES)], label=f"{name}  P(pass) = {p:.2f}")
    ax.axvline(target, color="k", lw=0.9)
    ax.set_xlabel("binding $V_{min}$ (V) — GP posterior draws")
    ax.set_ylabel("count")
    ax.legend(frameon=False, fontsize=5.8, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2)
    return fig


def retarget(mb: np.ndarray, series: list[dict], target: float, reference: float,
             current_mb: float, marks: list[tuple[float, str]]) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(COL + 0.35, 2.7))
    for s in series:
        ax.plot(mb, s["y"], color=MODE_COLOR.get(s["mode"], "0.3"),
                ls=CORNER_LS.get(s.get("corner"), "-"), label=s["label"])
    ax.set_xscale("log", base=2)
    ax.axhline(target, color="k", lw=0.9, label=f"target {target:.3f} V")
    ax.axhline(reference, color="0.45", lw=0.8, ls="--", label=f"reference {reference:.3f} V")
    ax.axvline(current_mb, color="0.3", lw=0.7, ls=":")
    ax.text(current_mb, 1.0, " current", transform=ax.get_xaxis_transform(), fontsize=6, va="top")
    for x, text in marks:
        ax.axvline(x, color=C_ACC, lw=0.8, ls="--")
        ax.text(x, 0.02, f" {text}", transform=ax.get_xaxis_transform(), fontsize=6, color=C_ACC,
                rotation=90, va="bottom")
    ax.set_xlabel("array size (Mb)")
    ax.set_ylabel("$V_{min}$ (V)")
    ax.legend(frameon=False, fontsize=6.0, loc="lower right")
    return fig


def recenter(dx: np.ndarray, dy: np.ndarray, W: np.ndarray, feasible: np.ndarray, target: float,
             best: tuple[float, float], xk: str, yk: str) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(COL + 0.6, 2.9))
    X, Y = np.meshgrid(dx, dy)
    lv = levels(target)
    f = np.nan_to_num(np.where(np.isfinite(W), W, np.nan), nan=NAN_FILL)
    cf = ax.contourf(X, Y, f, levels=lv, cmap="RdYlBu_r", norm=_norm(lv, target), extend="both")
    if _crosses(f, target):
        ax.contour(X, Y, f, levels=[target], colors="k", linewidths=1.8)
    if not feasible.all():
        ax.contourf(X, Y, (~feasible).astype(float), levels=[0.5, 1.5], colors="none",
                    hatches=["////"], zorder=3)
        ax.contour(X, Y, feasible.astype(float), levels=[0.5], colors="0.2", linewidths=0.7)
    ax.scatter([0], [0], s=40, marker="*", facecolor="none", edgecolor="k", lw=0.9, zorder=5)
    ax.annotate("today", (0, 0), textcoords="offset points", xytext=(4, -9), fontsize=6.2)
    ax.scatter([best[0]], [best[1]], s=52, marker="*", facecolor="#111111", edgecolor="k", zorder=6)
    ax.annotate("optimum", best, textcoords="offset points", xytext=(5, 3), fontsize=6.4,
                fontweight="bold")
    ax.set_xlabel("target move  " + axis_label(xk))
    ax.set_ylabel("target move  " + axis_label(yk))
    ax.set_title("worst binding $V_{min}$ when the whole distribution moves\n"
                 "black = target; hatched = some check leaves the training range", fontsize=7.0)
    cb = fig.colorbar(cf, ax=ax, pad=0.02)
    cb.set_label("worst $V_{min}$ over checks (V)", fontsize=7)
    cb.ax.tick_params(labelsize=6.5)
    return fig


def roadmap(gains_mV: np.ndarray, plan: dict[str, np.ndarray], levers: list,
            max_gain: dict[str, float]) -> plt.Figure:
    """Lever usage needed per improvement target. plan[strategy] = (n_targets, k), NaN = unreachable."""
    fig, ax = plt.subplots(figsize=(COL + 0.6, 2.8))
    styles = {"priority": "-", "balanced": "--", "min_cost": ":"}
    for sname, U in plan.items():
        if sname == "balanced":     # every lever at the same fraction: one line says it
            ax.plot(gains_mV, U[:, 0] * 100, color="0.25", ls="--", marker="o", ms=2.0,
                    label="balanced · every lever")
            continue
        for j, lv in enumerate(levers):
            ax.plot(gains_mV, U[:, j] * 100, color=SERIES[j % len(SERIES)], ls=styles.get(sname, "-"),
                    marker="o", ms=2.0, label=f"{lv.label} · {sname}")
    g = min(max_gain.values()) if max_gain else np.inf
    if np.isfinite(g) and g < gains_mV[-1]:
        ax.axvspan(max(g, gains_mV[0]), gains_mV[-1], color="0.9", zorder=0)
        ax.axvline(g, color="0.3", lw=0.7)
        ax.text(g, 0.5, " unreachable with these ceilings", transform=ax.get_xaxis_transform(),
                fontsize=6, rotation=90, va="center", color="0.3")
    ax.set_xlim(gains_mV[0], gains_mV[-1])
    ax.set_xlabel("required $V_{min}$ improvement vs reference (mV)")
    ax.set_ylabel("lever usage (% of ceiling)")
    ax.set_ylim(-3, 108)
    ax.legend(frameon=False, fontsize=5.8, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    return fig


def sensitivity(axes_keys: list[str], slopes: list[dict], sobol: dict[str, dict] | None) -> plt.Figure:
    """Left: local slope per 10 % of the training range. Right: saved global Sobol S_T of z(0.625 V)."""
    ncol = 2 if sobol else 1
    fig, axs = plt.subplots(1, ncol, figsize=(DCOL if sobol else COL + 0.6, 2.9), squeeze=False)
    ax = axs[0, 0]
    y = np.arange(len(axes_keys))
    h = 0.8 / max(1, len(slopes))
    for j, s in enumerate(slopes):
        ax.barh(y + (j - (len(slopes) - 1) / 2) * h, s["values"], height=h * 0.9,
                color=MODE_COLOR.get(s["mode"], SERIES[j % len(SERIES)]),
                alpha=1.0 if j < 2 else 0.6, label=s["label"])
    ax.set_yticks(y)
    ax.set_yticklabels([f"${AXIS[k]['symbol']}$" for k in axes_keys])
    ax.invert_yaxis()
    ax.axvline(0, color="0.2", lw=0.6)
    ax.set_xlabel("Δ$V_{min}$ per +10 % of training range (mV)")
    ax.set_title("local slope at each check", fontsize=7.4)
    ax.legend(frameon=False, fontsize=6.0)
    if sobol:
        ax2 = axs[0, 1]
        for j, (mode, d) in enumerate(sobol.items()):
            vals = [d.get(k, np.nan) for k in axes_keys]
            ax2.barh(y + (j - 0.5) * 0.38, vals, height=0.36, color=MODE_COLOR.get(mode, "0.4"), label=mode)
        ax2.set_yticks(y)
        ax2.set_yticklabels([f"${AXIS[k]['symbol']}$" for k in axes_keys])
        ax2.invert_yaxis()
        ax2.set_xlabel("total-order Sobol $S_T$ of z(0.625 V)  (saved, §VII)")
        ax2.set_title("global ranking over the whole training box", fontsize=7.4)
        ax2.legend(frameon=False, fontsize=6.0)
    return fig
