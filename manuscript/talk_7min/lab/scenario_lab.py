"""Scenario Lab — "목표 Vmin을 낮추려면 어느 knob을 얼마나?"를 직접 돌려 보는 개인 test GUI.

논문 §IV-B 시나리오(code/v_e_scenario.py)를 일반화했다.
  - 기준 조건: mode별 한계 corner(read=FSG, write=SFG) + 나머지 축은 mode 학습 중앙값
  - lever: 축 하나 또는 같은 종류 축 묶음("l_com+lpu"), 또는 "corner"(global Vth 폭 축소)
  - binding Vmin = 선택한 mode들의 Vmin 최댓값. 모두 목표 이하여야 통과
배율 축(local-σ, mobility 공통)은 중앙값 × s, shift/skew 축은 + Δ, corner는 offset × s.
논문 값 재현: k_σN −10.89 %, k_σN+k_σP −7.79 %, corner −46.9 %, k_σP 단독 불가.

결과는 실행할 때마다 exports/<시각>_<종류>/ 에 figure.png · data.csv · params.json으로 남는다.
마음에 드는 그림만 ../figs/ 로 복사하면 발표 자료(make_deck.py)가 그 파일을 쓴다.

    .venv/bin/python manuscript/talk_7min/lab/scenario_lab.py            # 브라우저 GUI
    .venv/bin/python manuscript/talk_7min/lab/scenario_lab.py --defaults # 발표 그림 + lab_summary.json → ../figs/
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "gui"))
from demo_config import AXIS_BY_KEY, CORNER_SHIFTS, DEVICE_COLS, LIMITING_CORNERS  # noqa: E402
from demo_engine import DemoEngine, DemoInputError  # noqa: E402

EXPORTS = HERE / "exports"
FIGS = HERE.parent / "figs"
MODES = ("read", "write")
I = {c: i for i, c in enumerate(DEVICE_COLS)}
MULT = {"l_com", "lpu", "m_com", "mpu"}           # 중앙값 ≈ 1인 배율 축; 나머지는 덧셈 축
CORNER = "corner"
NAMES = {"cn": "NMOS Vth", "sk": "PG–PD Vth 차이", "pu": "PMOS Vth", "lpu": "PMOS local mismatch",
         "l_com": "NMOS local mismatch", "l_sk": "PG–PD local mismatch 차이", "mpu": "PMOS mobility",
         "m_com": "NMOS mobility", "m_sk": "PG–PD mobility 차이"}
SHOW_TITLE = True                                 # 발표 장표용(--defaults)은 장표 제목과 겹치므로 끈다
DEFAULT_LEVERS = ["l_com", "lpu", "l_com+lpu", CORNER, "cn", "pu", "sk", "l_sk", "m_com", "mpu", "m_sk"]

NAVY, BLUE, STEEL, GRAY, WRITE, RED = "#1428A0", "#3E7EDE", "#5B728D", "#A6A6A6", "#8C8C8C", "#C0392B"
FILL = "#EDEDED"                                  # 통과 영역 (window)
PALETTE = [NAVY, WRITE, "#2E9E6A", "#8E44AD", BLUE, "#B8860B", STEEL, "#E05A8A", "#555555"]
for f in ("/mnt/c/Windows/Fonts/malgun.ttf", "/mnt/c/Windows/Fonts/malgunbd.ttf"):
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
plt.rcParams.update({"font.family": ["Malgun Gothic", "DejaVu Sans"], "axes.unicode_minus": False,
                     "font.size": 11, "axes.spines.top": False, "axes.spines.right": False})


# ------------------------------------------------------------------ lever model
def parse_lever(spec: str) -> list[str]:
    axes = [a.strip() for a in str(spec).split("+") if a.strip()]
    if axes == [CORNER]:
        return axes
    if not axes or any(a not in I for a in axes) or len(set(axes)) != len(axes):
        raise DemoInputError(f"lever {spec!r}: 축 이름은 {', '.join(DEVICE_COLS)} 또는 'corner'")
    if len({a in MULT for a in axes}) > 1:
        raise DemoInputError(f"lever {spec!r}: 배율 축과 덧셈 축은 한 lever로 묶을 수 없다")
    return axes


def lever_kind(axes: list[str]) -> str:
    return CORNER if axes == [CORNER] else ("mult" if axes[0] in MULT else "add")


def lever_label(spec: str) -> str:
    axes = parse_lever(spec)
    if axes == [CORNER]:
        return "global Vth corner 폭"
    if len(axes) == 2 and {"l_com", "lpu"} == set(axes):
        return "NMOS + PMOS local mismatch"
    return " + ".join(NAMES[a] for a in axes)


def change_text(axes: list[str], s: float) -> str:
    kind = lever_kind(axes)
    if kind == CORNER:
        out = f"corner 폭 {-(1 - s) * 100:+.1f} %"
    elif kind == "mult":
        out = f"{(s - 1) * 100:+.1f} %"
    else:
        out = f"{s:+.1f} mV" if AXIS_BY_KEY[axes[0]].unit == "mV" else f"{s:+.3f}"
    return out.replace("-", "−")                  # 장표와 같은 minus 기호


def x_value(axes: list[str], s: float) -> float:
    """plot/CSV용 변화량: 배율·corner는 %, 덧셈 축은 원 단위."""
    kind = lever_kind(axes)
    return (s - 1) * 100 if kind in ("mult", CORNER) else s


def x_unit(axes: list[str]) -> str:
    kind = lever_kind(axes)
    if kind == CORNER:
        return "corner 폭 변화 (%)"
    if kind == "mult":
        return "배율 변화 (%)"
    return "shift (mV)" if AXIS_BY_KEY[axes[0]].unit == "mV" else "skew 변화 (Δk)"


class Lab:
    def __init__(self, engine: DemoEngine) -> None:
        self.e = engine
        self.nominal = {m: np.array([engine.reference_coordinates(m)[c] for c in DEVICE_COLS]) for m in MODES}
        self.box = {m: engine._model(m).bounds for m in MODES}
        self.vops = {m: engine._model(m).vops for m in MODES}

    # -- config ------------------------------------------------------------
    def config(self, raw: dict[str, Any]) -> dict[str, Any]:
        modes = [m for m in raw.get("modes", list(MODES)) if m in MODES]
        if not modes:
            raise DemoInputError("read/write 중 하나 이상을 고른다")
        corners = {m: raw.get("corners", {}).get(m, LIMITING_CORNERS[m]) for m in MODES}
        for c in corners.values():
            if c != "nominal" and c not in CORNER_SHIFTS:
                raise DemoInputError(f"corner {c!r}: FFG/FSG/SFG/SSG/nominal 중 하나")
        overrides = {}
        for ax, v in (raw.get("overrides") or {}).items():
            if v in (None, ""):
                continue
            if ax not in I:
                raise DemoInputError(f"unknown axis {ax!r}")
            overrides[ax] = float(v)
        target = float(raw.get("target", 0.575))
        lo = max(self.vops[m][0] for m in modes)
        hi = min(self.vops[m][-1] for m in modes)
        if not lo <= target <= hi:
            raise DemoInputError(f"목표 Vmin은 [{lo:.2f}, {hi:.2f}] V 안")
        return {"modes": modes, "corners": corners, "overrides": overrides, "target": target}

    def _base(self, cfg: dict[str, Any], mode: str, corner_scale: float) -> np.ndarray:
        nom = self.nominal[mode]
        row = nom.copy()
        c = cfg["corners"][mode]
        if c != "nominal":
            for ax, val in zip(("cn", "pu"), CORNER_SHIFTS[c]):
                row[I[ax]] = nom[I[ax]] + corner_scale * (val - nom[I[ax]])
        for ax, v in cfg["overrides"].items():
            row[I[ax]] = v
        return row

    def rows(self, cfg: dict[str, Any], levers: list[tuple[list[str], np.ndarray]]) -> dict[str, np.ndarray]:
        """levers: [(axes, s 배열)] — 모든 lever의 s 배열은 같은 길이 N. mode별 (N, 9)."""
        n = len(levers[0][1]) if levers else 1
        out = {}
        for mode in cfg["modes"]:
            scale = np.ones(n)
            for axes, s in levers:
                if axes == [CORNER]:
                    scale = s
            rows = np.stack([self._base(cfg, mode, float(k)) for k in scale]) if np.any(scale != 1) \
                else np.repeat(self._base(cfg, mode, 1.0)[None], n, axis=0)
            for axes, s in levers:
                if axes == [CORNER]:
                    continue
                for ax in axes:
                    rows[:, I[ax]] = rows[:, I[ax]] * s if ax in MULT else rows[:, I[ax]] + s
            out[mode] = rows
        return out

    def lever_range(self, cfg: dict[str, Any], axes: list[str]) -> tuple[float, float, float]:
        """(lo, hi, s0): 모든 mode에서 학습 상자 안에 머무는 lever 범위. s0 = 지금."""
        if axes == [CORNER]:
            return 0.0, 1.0, 1.0
        lo, hi = -np.inf, np.inf
        for mode in cfg["modes"]:
            base = self._base(cfg, mode, 1.0)
            for ax in axes:
                b0, b1 = self.box[mode][ax]
                v = base[I[ax]]
                if ax in MULT:
                    lo, hi = max(lo, b0 / v), min(hi, b1 / v)
                else:
                    lo, hi = max(lo, b0 - v), min(hi, b1 - v)
        s0 = 1.0 if axes[0] in MULT else 0.0
        if not lo <= s0 <= hi:
            raise DemoInputError(f"{'+'.join(axes)}: 기준점이 학습 상자 밖이다 (override 확인)")
        return float(lo), float(hi), s0

    # -- prediction ----------------------------------------------------------
    def vmin(self, cfg: dict[str, Any], levers: list[tuple[list[str], np.ndarray]]) -> dict[str, np.ndarray]:
        """mode별 Vmin (censored 아래는 vops[0]−0.1, 위는 vops[-1]+0.1로 표시용 아님) + binding."""
        out: dict[str, np.ndarray] = {}
        for mode, rows in self.rows(cfg, levers).items():
            vals = []
            for k in range(0, len(rows), 256):
                _, _, _, raw, status, _, _ = self.e._predict_rows(mode, rows[k:k + 256])
                vals += [self.e._solver_value(float(r), st, self.vops[mode]) for r, st in zip(raw, status)]
            out[mode] = np.asarray(vals)
        out["binding"] = np.max([out[m] for m in cfg["modes"]], axis=0)
        return out

    def solve(self, cfg: dict[str, Any], spec: str, n: int = 41) -> dict[str, Any]:
        """지금(s0)에서 가장 가까운 '목표 통과' 지점을 scan + 이분 탐색으로 찾는다."""
        axes = parse_lever(spec)
        lo, hi, s0 = self.lever_range(cfg, axes)
        target = cfg["target"]
        grid = np.unique(np.r_[np.linspace(lo, hi, n), s0])
        v = self.vmin(cfg, [(axes, grid)])
        f = lambda s: float(self.vmin(cfg, [(axes, np.array([s]))])["binding"][0])
        i0 = int(np.flatnonzero(grid == s0)[0])
        base = float(v["binding"][i0])
        found = []
        if base <= target:
            found.append((s0, base))
        else:
            for step in (-1, 1):
                prev = i0
                for j in range(i0 + step, -1 if step < 0 else len(grid), step):
                    if v["binding"][j] <= target:
                        a, b = grid[prev], grid[j]          # a: 실패, b: 통과
                        for _ in range(30):
                            mid = 0.5 * (a + b)
                            a, b = (a, mid) if f(mid) <= target else (mid, b)
                        found.append((float(b), f(b)))
                        break
                    prev = j
        best_i = int(np.argmin(v["binding"]))
        rec: dict[str, Any] = {
            "lever": spec, "label": lever_label(spec), "axes": axes, "kind": lever_kind(axes),
            "range": [lo, hi], "s0": s0, "baseline_vmin": base,
            "baseline_by_mode": {m: float(v[m][i0]) for m in cfg["modes"]},
            "scan_s": grid.tolist(), "scan_binding": v["binding"].tolist(),
            "scan_by_mode": {m: v[m].tolist() for m in cfg["modes"]},
            "best_s": float(grid[best_i]), "best_vmin": float(v["binding"][best_i]),
        }
        if base <= target:
            rec.update(status="already", s_required=s0, need=0.0, change="이미 통과")
        elif found:
            s_req, v_req = min(found, key=lambda t: abs(t[0] - s0))
            rec.update(status="reachable", s_required=s_req, vmin_at_s=v_req,
                       need=abs(s_req - s0) / (hi - lo), change=change_text(axes, s_req),
                       both_sides=len(found) == 2)
            side = grid <= s0 if s_req < s0 else grid >= s0
            d = np.diff(v["binding"][side])
            rec["monotone"] = bool(np.all(d >= -1e-6) or np.all(d <= 1e-6))
        else:
            rec.update(status="unreachable", need=None,
                       change=f"학습 범위 안에서 닿지 않음 · 최선 {change_text(axes, grid[best_i])} → {v['binding'][best_i]:.4f} V")
        return rec

    def map2(self, cfg: dict[str, Any], spec_a: str, spec_b: str, n: int = 25) -> dict[str, Any]:
        a, b = parse_lever(spec_a), parse_lever(spec_b)
        if set(a) & set(b):
            raise DemoInputError("두 lever가 같은 축을 공유한다")
        (alo, ahi, a0), (blo, bhi, b0) = self.lever_range(cfg, a), self.lever_range(cfg, b)
        sa, sb = np.linspace(alo, ahi, n), np.linspace(blo, bhi, n)
        A, B = np.meshgrid(sa, sb)
        v = self.vmin(cfg, [(a, A.ravel()), (b, B.ravel())])
        grid = v["binding"].reshape(n, n)
        ok = grid <= cfg["target"]
        dist = np.hypot((A - a0) / (ahi - alo), (B - b0) / (bhi - blo))
        best = None
        if ok.any():
            k = np.unravel_index(np.argmin(np.where(ok, dist, np.inf)), ok.shape)
            best = {"s_a": float(A[k]), "s_b": float(B[k]), "vmin": float(grid[k]),
                    "change_a": change_text(a, A[k]), "change_b": change_text(b, B[k])}
        return {"lever_a": spec_a, "lever_b": spec_b, "label_a": lever_label(spec_a), "label_b": lever_label(spec_b),
                "s_a": sa.tolist(), "s_b": sb.tolist(), "s0": [a0, b0], "binding": grid.tolist(),
                "by_mode": {m: v[m].reshape(n, n).tolist() for m in cfg["modes"]}, "closest": best}

    def window(self, cfg: dict[str, Any], spec: str, s: float | None = None, n: int = 61) -> dict[str, Any]:
        """NMOS Vth × PMOS Vth 평면에서 read·write Vmin — 현재와 lever 적용 후. s 생략 시 목표를 맞추는 값."""
        axes = parse_lever(spec)
        if axes == [CORNER]:
            raise DemoInputError("window는 cell knob lever만 받는다 (corner 불가)")
        rec = self.solve(cfg, spec)
        if s is None:
            if rec["status"] == "unreachable":
                raise DemoInputError(f"{lever_label(spec)}: 학습 범위 안에서 목표에 닿지 않아 개선 후 평면을 그릴 수 없다")
            s = rec["s_required"]
        lo = max(self.box[m]["cn"][0] for m in MODES), max(self.box[m]["pu"][0] for m in MODES)
        hi = min(self.box[m]["cn"][1] for m in MODES), min(self.box[m]["pu"][1] for m in MODES)
        cn, pu = np.linspace(lo[0], hi[0], n), np.linspace(lo[1], hi[1], n)
        CN, PU = np.meshgrid(cn, pu)
        out: dict[str, Any] = {"lever": spec, "label": lever_label(spec), "s": float(s), "change": change_text(axes, s),
                               "cn": cn.tolist(), "pu": pu.tolist(), "corners": {}}
        for tag, sv in (("before", None), ("after", s)):
            for mode in cfg["modes"]:
                rows = np.repeat(self.nominal[mode][None], CN.size, axis=0)
                rows[:, I["cn"]], rows[:, I["pu"]] = CN.ravel(), PU.ravel()
                if sv is not None:
                    for ax in axes:
                        rows[:, I[ax]] = rows[:, I[ax]] * sv if ax in MULT else rows[:, I[ax]] + sv
                vals = []
                for k in range(0, len(rows), 256):
                    _, _, _, raw, st, _, _ = self.e._predict_rows(mode, rows[k:k + 256])
                    vals += [self.e._solver_value(float(r), t, self.vops[mode]) for r, t in zip(raw, st)]
                out[f"{tag}_{mode}"] = np.asarray(vals).reshape(n, n).tolist()
            lv = [] if sv is None else [(axes, np.array([sv]))]
            v = self.vmin(cfg, lv) if lv else self.vmin(cfg, [([axes[0]], np.array([1.0 if axes[0] in MULT else 0.0]))])
            out["corners"][tag] = {m: {"corner": cfg["corners"][m], "vmin": float(v[m][0])} for m in cfg["modes"]}
        return out


# ------------------------------------------------------------------ figures
def _mode_note(cfg: dict[str, Any]) -> str:
    return " & ".join(f"{m} @ {cfg['corners'][m]}" for m in cfg["modes"])


def fig_rank(cfg: dict[str, Any], recs: list[dict[str, Any]]):
    order = sorted(recs, key=lambda r: (r["status"] != "already", r["need"] is None, r["need"] or 0))
    fig, ax = plt.subplots(figsize=(8.2, 0.52 * len(order) + 1.4))
    for i, r in enumerate(reversed(order)):
        if r["status"] == "unreachable":
            ax.barh(i, 100, color="#EEEEEE", hatch="//", edgecolor="#CCCCCC")
            ax.text(2, i, r["change"], va="center", fontsize=10, color="#666666")
        else:
            val = r["need"] * 100
            ax.barh(i, val, color=NAVY)
            ax.text(val + 1.2, i, r["change"], va="center", fontsize=11, weight="bold", color="#202020")
    ax.set_yticks(range(len(order)), [r["label"] for r in reversed(order)])
    ax.set_xlim(0, 112)
    ax.set_xlabel("움직여야 하는 양 (학습 범위 대비 %)  — 짧을수록 효과적인 knob")
    if SHOW_TITLE:
        ax.set_title(f"목표 Vmin {cfg['target']:.3f} V 통과에 필요한 변화  ({_mode_note(cfg)})", fontsize=12, loc="left")
    fig.tight_layout()
    return fig


def fig_sweep(cfg: dict[str, Any], recs: list[dict[str, Any]], per_mode: bool):
    units = list(dict.fromkeys(x_unit(r["axes"]) for r in recs))
    fig, axs = plt.subplots(1, len(units), figsize=(6.4 * len(units), 4.4), squeeze=False)
    for ax, unit in zip(axs[0], units):
        for k, r in enumerate(recs):
            if x_unit(r["axes"]) != unit:
                continue
            c = PALETTE[k % len(PALETTE)]
            xs = [x_value(r["axes"], s) for s in r["scan_s"]]
            ax.plot(xs, r["scan_binding"], color=c, lw=2.4, label=r["label"])
            if per_mode:
                for m, ls in (("read", "--"), ("write", ":")):
                    if m in r["scan_by_mode"]:
                        ax.plot(xs, r["scan_by_mode"][m], color=c, lw=1.1, ls=ls, alpha=0.8)
            if r["status"] == "reachable":
                ax.plot(x_value(r["axes"], r["s_required"]), cfg["target"], "o", color=c, ms=7)
        ax.axhline(cfg["target"], color=RED, lw=1.4)
        ax.text(ax.get_xlim()[0], cfg["target"], f" 목표 {cfg['target']:.3f} V", color=RED, va="bottom", fontsize=10)
        ax.set_xlabel(unit)
        ax.set_ylabel("binding Vmin (V)")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=9, frameon=False)
    if per_mode:
        fig.text(0.01, 0.01, "굵은 선 = binding(max), 점선 = read, 점점선 = write", fontsize=9, color="#666666")
    if SHOW_TITLE:
        fig.suptitle(f"knob을 움직일 때 Vmin  ({_mode_note(cfg)})", fontsize=12, x=0.01, ha="left")
    fig.tight_layout()
    return fig


def fig_map(cfg: dict[str, Any], res: dict[str, Any]):
    a, b = parse_lever(res["lever_a"]), parse_lever(res["lever_b"])
    xa = [x_value(a, s) for s in res["s_a"]]
    xb = [x_value(b, s) for s in res["s_b"]]
    g = np.asarray(res["binding"])
    fig, ax = plt.subplots(figsize=(6.6, 5.2))
    cf = ax.contourf(xa, xb, g, levels=14, cmap="Blues_r")
    fig.colorbar(cf, ax=ax, label="binding Vmin (V)")
    ax.contourf(xa, xb, g <= cfg["target"], levels=[0.5, 1.5], colors="none", hatches=["..."])
    cs = ax.contour(xa, xb, g, levels=[cfg["target"]], colors=RED, linewidths=2.2)
    ax.clabel(cs, fmt=f"{cfg['target']:.3f} V", fontsize=9)
    ax.plot(x_value(a, res["s0"][0]), x_value(b, res["s0"][1]), "k*", ms=13, label="지금")
    if res["closest"]:
        cl = res["closest"]
        ax.plot(x_value(a, cl["s_a"]), x_value(b, cl["s_b"]), "o", color=RED, ms=8,
                label=f"가장 가까운 통과점: {cl['change_a']}, {cl['change_b']}")
    ax.set_xlabel(f"{res['label_a']}  {x_unit(a)}")
    ax.set_ylabel(f"{res['label_b']}  {x_unit(b)}")
    ax.legend(fontsize=9, loc="upper right", framealpha=0.9)
    if SHOW_TITLE:
        ax.set_title(f"두 knob 나눠 부담하기 — 점무늬 = 목표 통과  ({_mode_note(cfg)})", fontsize=11, loc="left")
    fig.tight_layout()
    return fig


def fig_window(cfg: dict[str, Any], res: dict[str, Any]):
    """현재 vs lever 적용 후. 칠한 영역 = read·write 모두 목표 이하, 별 = Read worst · Write worst corner (빈 별 = 미달)."""
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from demo_config import CORNER_SHIFTS as CS
    t = cfg["target"]
    cn, pu = np.asarray(res["cn"]), np.asarray(res["pu"])
    fig, axs = plt.subplots(1, 2, figsize=(10.4, 4.6), sharey=True)
    for ax, (tag, title, tc) in zip(axs, (("before", "현재", "#404040"), ("after", f"{res['label']} {res['change']}", NAVY))):
        r = np.asarray(res.get(f"{tag}_read", np.full((len(pu), len(cn)), -np.inf)))
        w = np.asarray(res.get(f"{tag}_write", np.full((len(pu), len(cn)), -np.inf)))
        ax.contourf(cn, pu, np.maximum(r, w) <= t, levels=[0.5, 1.5], colors=[FILL])
        if "read" in cfg["modes"]:
            ax.contour(cn, pu, r, levels=[t], colors=[NAVY], linewidths=2.6)
        if "write" in cfg["modes"]:
            ax.contour(cn, pu, w, levels=[t], colors=[WRITE], linewidths=2.6, linestyles="--")
        for mode, col in (("read", NAVY), ("write", WRITE)):
            c = res["corners"][tag].get(mode)
            if not c or c["corner"] == "nominal":
                continue
            x, y = CS[c["corner"]]
            ok = c["vmin"] <= t + 1e-4
            ax.plot(x, y, "*", ms=17, color=col if ok else "white", mec=col, mew=1.8, zorder=4)
            ax.annotate(f"{mode.capitalize()} worst\n({c['corner']})", (x, y), xytext=(10, -30), textcoords="offset points",
                        fontsize=10, color=col, weight="bold")
        ax.set_title(title, fontsize=14, weight="bold", color=tc)
        ax.set_xlabel("NMOS Vth shift (mV)")
    axs[0].set_ylabel("PMOS Vth shift (mV)")
    fig.legend(handles=[Patch(color=FILL, label=f"read·write 모두 {t:.3f} V 이하"),
                        Line2D([], [], color=NAVY, lw=2.6, label="read 경계"),
                        Line2D([], [], color=WRITE, lw=2.6, ls="--", label="write 경계"),
                        Line2D([], [], marker="*", color="gray", ls="", ms=12, mfc="white", label="빈 별 = 목표 미달")],
               loc="lower center", ncol=4, frameon=False, fontsize=10.5, bbox_to_anchor=(0.5, -0.04))
    if SHOW_TITLE:
        fig.suptitle(f"목표 {t:.3f} V · 나머지 knob은 mode별 중앙값", fontsize=11, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.06, 1, 0.97 if SHOW_TITLE else 1))
    return fig


# ------------------------------------------------------------------ export
def export(kind: str, cfg: dict[str, Any], fig, header: list[str], rows: list[list[Any]], extra: dict[str, Any]) -> Path:
    d = EXPORTS / f"{datetime.now():%Y%m%d-%H%M%S}_{kind}"
    d.mkdir(parents=True, exist_ok=True)
    fig.savefig(d / "figure.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    with (d / "data.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    (d / "params.json").write_text(json.dumps({"kind": kind, "config": cfg, **extra}, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    return d


def run(lab: Lab, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    cfg = lab.config(payload)
    if kind == "rank":
        recs = [lab.solve(cfg, s) for s in payload.get("levers") or DEFAULT_LEVERS]
        rows = [[r["label"], r["lever"], r["status"], r["change"], r.get("s_required"),
                 None if r["need"] is None else round(r["need"] * 100, 2), r["baseline_vmin"], r.get("vmin_at_s")]
                for r in recs]
        d = export(kind, cfg, fig_rank(cfg, recs),
                   ["label", "lever", "status", "change", "s_required", "need_pct_of_range", "baseline_V", "vmin_at_s_V"],
                   rows, {"results": recs})
        table = [{"label": r["label"], "status": r["status"], "change": r["change"],
                  "baseline": round(r["baseline_vmin"], 4)} for r in recs]
    elif kind == "sweep":
        recs = [lab.solve(cfg, s) for s in payload.get("levers") or ["l_com", "lpu", "l_com+lpu"]]
        rows = [[r["lever"], x_value(r["axes"], s), *(r["scan_by_mode"].get(m, [None] * len(r["scan_s"]))[i] for m in MODES),
                 r["scan_binding"][i]] for r in recs for i, s in enumerate(r["scan_s"])]
        d = export(kind, cfg, fig_sweep(cfg, recs, bool(payload.get("per_mode", True))),
                   ["lever", "change", "vmin_read_V", "vmin_write_V", "binding_V"], rows, {"results": recs})
        table = [{"label": r["label"], "status": r["status"], "change": r["change"],
                  "baseline": round(r["baseline_vmin"], 4)} for r in recs]
    elif kind == "map":
        res = lab.map2(cfg, payload.get("lever_a", "l_com"), payload.get("lever_b", "lpu"), int(payload.get("n", 25)))
        a, b = parse_lever(res["lever_a"]), parse_lever(res["lever_b"])
        rows = [[x_value(a, sa), x_value(b, sb), res["binding"][j][i]]
                for j, sb in enumerate(res["s_b"]) for i, sa in enumerate(res["s_a"])]
        d = export(kind, cfg, fig_map(cfg, res), [f"{res['lever_a']}_change", f"{res['lever_b']}_change", "binding_V"],
                   rows, {"result": res})
        cl = res["closest"]
        table = [{"label": "가장 가까운 통과점", "status": "reachable" if cl else "unreachable",
                  "change": f"{res['label_a']} {cl['change_a']} / {res['label_b']} {cl['change_b']}" if cl else "격자 안 통과점 없음",
                  "baseline": round(cl["vmin"], 4) if cl else None}]
    elif kind == "window":
        sv = payload.get("s")
        res = lab.window(cfg, payload.get("lever_a", "l_com"), None if sv in (None, "") else float(sv))
        rows = [[x, y, res["before_read"][j][i] if "before_read" in res else None,
                 res["before_write"][j][i] if "before_write" in res else None,
                 res["after_read"][j][i] if "after_read" in res else None,
                 res["after_write"][j][i] if "after_write" in res else None]
                for j, y in enumerate(res["pu"]) for i, x in enumerate(res["cn"])]
        d = export(kind, cfg, fig_window(cfg, res),
                   ["cn_mV", "pu_mV", "before_read_V", "before_write_V", "after_read_V", "after_write_V"], rows, {"result": res})
        table = [{"label": f"{res['label']} {res['change']}", "status": tag, "change": mode,
                  "baseline": round(c["vmin"], 4)} for tag in ("before", "after") for mode, c in res["corners"][tag].items()]
    else:
        raise DemoInputError(f"unknown kind {kind!r}")
    return {"dir": str(d), "image": f"/exports/{d.name}/figure.png", "table": table, "config": cfg}


# ------------------------------------------------------------------ server
class Handler(BaseHTTPRequestHandler):
    lab: Lab
    lock = threading.Lock()

    def log_message(self, fmt: str, *args: object) -> None:
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: Any) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/meta":
            lab = self.lab
            return self._json(200, {
                "axes": [{"key": c, "symbol": AXIS_BY_KEY[c].symbol, "label": AXIS_BY_KEY[c].label_kr,
                          "nominal": {m: float(lab.nominal[m][I[c]]) for m in MODES},
                          "box": [max(lab.box[m][c][0] for m in MODES), min(lab.box[m][c][1] for m in MODES)]}
                         for c in DEVICE_COLS],
                "corners": list(CORNER_SHIFTS) + ["nominal"], "limiting": LIMITING_CORNERS,
                "levers": DEFAULT_LEVERS, "lever_labels": {s: lever_label(s) for s in DEFAULT_LEVERS}})
        if path.startswith("/exports/"):
            f = (EXPORTS / path[len("/exports/"):]).resolve()
            if f.is_file() and f.is_relative_to(EXPORTS.resolve()):
                return self._send(200, f.read_bytes(), "image/png")
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            with self.lock:
                self._json(200, {"ok": True, **run(self.lab, self.path.rsplit("/", 1)[-1], payload)})
        except (DemoInputError, ValueError, TypeError, KeyError) as exc:
            self._json(400, {"ok": False, "error": str(exc)})


def defaults(lab: Lab, target: float) -> None:
    """발표 그림 + 장표 수치(lab_summary.json). 조건: 목표 Vmin, read @ FSG · write @ SFG, 나머지 knob은 mode별 중앙값."""
    global SHOW_TITLE
    SHOW_TITLE = False
    FIGS.mkdir(exist_ok=True)
    knobs = [lv for lv in DEFAULT_LEVERS if lv != CORNER]   # 발표는 cell knob만 비교한다
    for kind, extra, name in (("rank", {"levers": knobs}, "lab_rank.png"),
                              ("window", {"lever_a": "l_com"}, "lab_window.png")):
        out = run(lab, kind, {"target": target, **extra})
        (FIGS / name).write_bytes((Path(out["dir"]) / "figure.png").read_bytes())
        print(f"{name:15s} <- {out['dir']}")
    cfg = lab.config({"target": target})
    recs = {sp: lab.solve(cfg, sp) for sp in knobs}
    sweep = []
    for t in sorted({0.590, 0.575, 0.560, 0.550, round(target, 3)}, reverse=True):
        c = lab.config({"target": t})
        sweep.append({"target": t, **{sp: lab.solve(c, sp)["change"] for sp in ("l_com", "l_com+lpu")}})
    summary = {"target": target, "baseline": recs["l_com"]["baseline_by_mode"],
               "gap_mV": {m: (v - target) * 1e3 for m, v in recs["l_com"]["baseline_by_mode"].items()},
               "levers": {sp: {"label": r["label"], "status": r["status"], "change": r["change"]} for sp, r in recs.items()},
               "target_sweep": sweep}
    (FIGS / "lab_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--defaults", action="store_true", help="발표 그림과 lab_summary.json을 ../figs/에 만들고 끝낸다")
    ap.add_argument("--target", type=float, default=0.575,
                    help="--defaults의 목표 Vmin. 기본 = 논문 시나리오 (0.625 V → 0.575 V)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    lab = Lab(DemoEngine.from_bundle())
    if args.defaults:
        defaults(lab, args.target)
        return 0
    Handler.lab = lab
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\nScenario Lab: {url}  (Ctrl+C 종료, 결과는 {EXPORTS})\n")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
