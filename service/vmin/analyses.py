"""Analysis catalogue. Each entry turns a full spec into a Result.

Adding an analysis = one function under @analysis(...). The web form is built from
`fields`, so the UI needs no change. Spec keys shared by every analysis (target,
z, base, checks, modes, levers) are resolved by scenario.Context.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from . import figures as F
from . import solve
from .config import AXIS, AXIS_KEYS, DEFAULTS, MODES, RESULTS
from .engine import ABOVE, BELOW, OK, derive_z_target, lobe_bias, vmin_from_z
from .scenario import COMMON_DEFAULTS, Check, Context, SpecError, axis_index, merged

Progress = Callable[[str], None]


# ----------------------------------------------------------------- result type
@dataclass
class Result:
    summary: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    figures: list[tuple[str, str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    verification: list[dict] = field(default_factory=list)

    def card(self, label: str, value: str, hint: str = "") -> None:
        self.summary.append(dict(label=label, value=value, hint=hint))

    def table(self, name: str, title: str, columns: list[str], rows: list[list], inline: bool = True) -> None:
        self.tables.append(dict(name=name, title=title, columns=columns, rows=rows, inline=inline))

    def figure(self, name: str, title: str, fig: Any) -> None:
        self.figures.append((name, title, fig))

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)


REGISTRY: dict[str, dict] = {}


def field_(key: str, type_: str, label: str, **kw) -> dict:
    return dict(key=key, type=type_, label=label, **kw)


def analysis(kind: str, group: str, title: str, description: str, uses: list[str],
             fields: list[dict], defaults: dict):
    def deco(fn):
        REGISTRY[kind] = dict(kind=kind, group=group, title=title, description=description,
                              uses=uses, fields=fields, defaults=defaults, run=fn)
        return fn
    return deco


def catalogue() -> list[dict]:
    return [{k: v for k, v in e.items() if k != "run"} | {"defaults": full_defaults(e["kind"])}
            for e in REGISTRY.values()]


def full_defaults(kind: str) -> dict:
    return merged(merged(COMMON_DEFAULTS, REGISTRY[kind]["defaults"]), {"kind": kind})


def run(spec: dict, engine, progress: Progress = lambda _m: None) -> tuple[dict, Result]:
    kind = spec.get("kind")
    if kind not in REGISTRY:
        raise SpecError(f"알 수 없는 분석 '{kind}' — {', '.join(REGISTRY)}")
    full = merged(full_defaults(kind), spec)
    ctx = Context(full, engine)
    res = Result()
    REGISTRY[kind]["run"](full, ctx, res, progress)
    for c in ctx.checks:
        out = ctx.outside(c, ctx.rows(c, fixed_usage(ctx))[0])
        if out:
            res.note(f"{c.label}: {', '.join(out)} 축이 학습 범위 밖입니다 — GP 외삽 값입니다.")
    for exp in full.get("expect") or []:
        res.verification.append(_verify(res.data, exp))
    res.data["context"] = dict(
        checks=[c.label for c in ctx.checks], z=ctx.z, z_text=ctx.z_text, target=ctx.target,
        reference=ctx.reference, base=full["base"].get("reference", "mode_nominal"),
        overrides={k: v for k, v in (full["base"].get("overrides") or {}).items() if v not in (None, "")},
        levers=[dict(id=lv.id, label=lv.label, type=lv.type, axes=lv.axes, limit=lv.limit_text(),
                     applied=lv.text(lv.usage) if lv.usage else None) for lv in ctx.levers])
    return full, res


def _lookup(data: Any, path: str) -> Any:
    for part in path.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def _verify(data: dict, exp: dict) -> dict:
    out = dict(path=exp["path"], expected=exp["value"], tol=exp.get("tol", 0.0),
               ledger=exp.get("ledger", ""), note=exp.get("note", ""))
    try:
        got = _lookup(data, exp["path"])
    except (KeyError, IndexError, TypeError, ValueError):
        return out | dict(actual=None, ok=False)
    if isinstance(exp["value"], (bool, str)) or exp["value"] is None:
        ok = got == exp["value"]
    else:
        ok = got is not None and abs(float(got) - float(exp["value"])) <= float(exp.get("tol", 0.0))
    return out | dict(actual=got, ok=bool(ok))


# ----------------------------------------------------------------- helpers
def fixed_usage(ctx: Context) -> np.ndarray:
    return np.array([[lv.usage for lv in ctx.levers]], float)


def vtext(v: float, st: int, vops: np.ndarray) -> str:
    if st == ABOVE:
        return f"> {vops[-1]:.2f} V"
    if st == BELOW:
        return f"< {vops[0]:.2f} V"
    return f"{v:.4f} V"


def wrap(parts: list[str], width: int = 44) -> str:
    """Join with ' · ', breaking lines so a panel title never runs into the colour bar."""
    lines: list[str] = []
    for p in parts:
        if lines and len(lines[-1]) + 3 + len(p) <= width:
            lines[-1] += " · " + p
        else:
            lines.append(p)
    return "\n".join(lines)


def mv(x: float) -> str:
    return F.sgn(x * 1e3) + " mV" if np.isfinite(x) else "—"


def eff(v: np.ndarray, st: np.ndarray) -> np.ndarray:
    """Value used for pass/fail and max: above the supply grid counts as +inf."""
    return np.where(st == ABOVE, np.inf, v)


def num(v: float) -> float | None:
    return float(v) if v is not None and np.isfinite(v) else None


def binding_text(ctx: Context, V: np.ndarray, S: np.ndarray) -> tuple[float, str]:
    E = eff(V, S)
    i = int(np.argmax(E))
    c = ctx.checks[i]
    return float(E[i]), f"{vtext(V[i], S[i], ctx.e.modes[c.mode].vops)}  ({c.label})"


def paper_setting(spec: dict, ctx: Context) -> bool:
    """True when the saved §V-D HSPICE values are comparable: paper base, Z and no lever moved."""
    b = spec["base"]
    return (b.get("reference", "mode_nominal") == "mode_nominal"
            and not any(v not in (None, "") for v in (b.get("overrides") or {}).values())
            and abs(ctx.z - 6.3984) < 1e-3 and not any(lv.usage for lv in ctx.levers))


def root_bisect(f: Callable[[float], float], a: float, b: float, iters: int = 40) -> float:
    """Sign-change root of f on [a, b] (f(a) and f(b) differ in sign)."""
    fa = f(a)
    for _ in range(iters):
        m = 0.5 * (a + b)
        fm = f(m)
        if (fm > 0) == (fa > 0):
            a, fa = m, fm
        else:
            b = m
    return 0.5 * (a + b)


def sign_roots(xs: np.ndarray, ys: np.ndarray, target: float, f: Callable[[float], float]) -> list[float]:
    d = np.where(np.isinf(ys), 1.0, ys - target)
    roots = []
    for i in range(len(xs) - 1):
        if d[i] == 0:
            roots.append(float(xs[i]))
        elif (d[i] > 0) != (d[i + 1] > 0) and d[i + 1] != 0:
            roots.append(root_bisect(lambda x: f(x) - target, xs[i], xs[i + 1]))
    return roots


def intervals_text(xs_lo: float, xs_hi: float, roots: list[float], passes: Callable[[float], bool],
                   fmt: str) -> tuple[str, list[list[float]]]:
    pts = [xs_lo] + sorted(roots) + [xs_hi]
    ivs = []
    for a, b in zip(pts[:-1], pts[1:]):
        if b > a and passes(0.5 * (a + b)):
            if ivs and abs(ivs[-1][1] - a) < 1e-12:
                ivs[-1][1] = b
            else:
                ivs.append([a, b])
    if not ivs:
        return "없음 (범위 안에서 통과하는 값 없음)", ivs
    return ", ".join(f"[{format(a, fmt)}, {format(b, fmt)}]" for a, b in ivs).replace("-", "−"), ivs


LEVER_FIELD = field_("levers", "levers", "공정 lever (위에서부터 priority 순서)",
                     columns=["id", "label", "type", "axes", "max_change", "weight"])
FIXED_LEVERS = field_("levers", "levers", "적용할 공정 변화 (선택)", fixed=True,
                      columns=["id", "label", "type", "axes", "max_change"],
                      hint="적은 변화를 그대로 적용한 상태에서 계산합니다. 비워 두면 오늘 공정.")


# ======================================================================= FORWARD
@analysis("point", "Forward", "조건별 Vmin · physics layer",
          "binding 조건(corner 또는 좌표)마다 μ·σ → z(Vop) → Vmin을 계산합니다. "
          "논문 설정이면 PDK corner 옆에 §V-D HSPICE 값을 같이 보여 줍니다.",
          uses=["target", "z", "base", "checks"], fields=[FIXED_LEVERS],
          defaults={"checks": "all_corners", "target": DEFAULTS["reference_vmin"]})
def _point(spec, ctx, res, progress):
    U = fixed_usage(ctx)
    zg = ctx.zgrids(U)
    ref = ctx.e.reference if paper_setting(spec, ctx) else {}
    items, rows, data = [], [], {}
    V = np.empty(len(ctx.checks))
    S = np.empty(len(ctx.checks), int)
    for i, (c, g) in enumerate(zip(ctx.checks, zg)):
        vops = ctx.e.modes[c.mode].vops
        v, st = vmin_from_z(g, ctx.z, vops)
        V[i], S[i] = v[0], st[0]
        row = ctx.rows(c, U)[0]
        h = ref.get((c.mode, c.corner))
        htxt = ("< 0.40 V" if h and h["hspice_censored"] else f"{h['hspice']:.4f} V") if h else "—"
        diff = mv(v[0] - h["hspice"]) if h and st[0] == OK and not h["hspice_censored"] else "—"
        margin = mv(ctx.target - eff(v, st)[0]) if st[0] != BELOW else "> " + mv(ctx.target - vops[0])
        rows.append([c.label, *[round(float(x), 4) for x in row], vtext(v[0], st[0], vops), margin, htxt, diff])
        items.append(dict(label=c.label, mode=c.mode, corner=c.corner, vops=vops, z=g[0],
                          vmin=v[0], status=int(st[0])))
        data[c.label] = dict(vmin=num(v[0]), status=int(st[0]), z=[float(x) for x in g[0]],
                             vops=vops.tolist(), hspice=h["hspice"] if h else None)
    bv, btxt = binding_text(ctx, V, S)
    res.card("binding Vmin", btxt, "모든 조건 중 최댓값")
    res.card("목표 대비 margin", mv(ctx.target - bv), f"target {ctx.target:.3f} V")
    res.card("Z 기준", f"{ctx.z:.4f}", ctx.z_text)
    res.table("checks", "조건별 Vmin", ["조건", *AXIS_KEYS, "Vmin", "target margin", "HSPICE §V-D", "GP − HSPICE"], rows)
    res.figure("zcurves", "physics layer — z(Vop)가 Z를 넘는 전압이 Vmin", F.zcurves(items, ctx.z, ctx.z_text))
    res.data.update(checks=data, binding=bv, z=ctx.z)
    if not paper_setting(spec, ctx):
        res.note("HSPICE 비교값은 논문 설정(학습 중앙값 기준, Z = 6.398, lever 없음)에서만 표시합니다.")


@analysis("sweep", "Forward", "1축 sweep · 1축 inverse",
          "한 축만 움직이며 조건별 Vmin을 그리고, 목표를 만나는 값(1축 inverse)과 통과 구간을 찾습니다. "
          "나머지 축은 고정 — 논문 §V-E의 축별 역해와 같습니다.",
          uses=["target", "z", "base", "checks"],
          fields=[field_("axis", "axis", "sweep 축"),
                  field_("lo", "number", "시작값", optional=True, hint="빈칸 = 학습 범위"),
                  field_("hi", "number", "끝값", optional=True, hint="빈칸 = 학습 범위"),
                  field_("n", "int", "격자 점 수", min=11, max=401), FIXED_LEVERS],
          defaults={"axis": "l_com", "lo": None, "hi": None, "n": 81})
def _sweep(spec, ctx, res, progress):
    key = spec["axis"]
    i = axis_index(key)
    boxes = [ctx.e.modes[m].box[i] for m in ctx.modes]
    lo = float(spec["lo"]) if spec.get("lo") not in (None, "") else min(b[0] for b in boxes)
    hi = float(spec["hi"]) if spec.get("hi") not in (None, "") else max(b[1] for b in boxes)
    if not hi > lo:
        raise SpecError("끝값이 시작값보다 커야 합니다")
    xs = np.linspace(lo, hi, int(spec["n"]))
    U = fixed_usage(ctx)
    base_rows = [ctx.rows(c, U)[0] for c in ctx.checks]

    def eval_at(cidx: list[int], x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        V = np.empty((len(cidx), len(x)))
        S = np.empty((len(cidx), len(x)), int)
        for mode in ctx.modes:
            sel = [k for k, ci in enumerate(cidx) if ctx.checks[ci].mode == mode]
            if not sel:
                continue
            R = np.concatenate([np.repeat(base_rows[cidx[k]][None], len(x), 0) for k in sel])
            R[:, i] = np.tile(x, len(sel))
            v, st = ctx.e.vmin(mode, R, ctx.z)
            V[sel], S[sel] = v.reshape(len(sel), -1), st.reshape(len(sel), -1)
        return V, S

    allc = list(range(len(ctx.checks)))
    V, S = eval_at(allc, xs)
    E = eff(V, S)
    B = E.max(axis=0)

    def bind_at(x: float) -> float:
        v, s = eval_at(allc, np.array([x]))
        return float(eff(v, s).max())

    broots = sign_roots(xs, B, ctx.target, bind_at)
    unit = AXIS[key]["unit"]
    fmt = ".2f" if unit == "mV" else ".4f"
    text, ivs = intervals_text(lo, hi, broots, lambda x: bind_at(x) <= ctx.target, fmt)
    rows, series, data = [], [], {}
    for ci, c in enumerate(ctx.checks):
        r = sign_roots(xs, E[ci], ctx.target, lambda x, ci=ci: float(eff(*eval_at([ci], np.array([x])))[0, 0]))
        mono = solve.monotone(E[ci]) or solve.monotone(E[ci][::-1])
        rows.append([c.label, ", ".join(F.sgn(x, fmt) for x in r) or "없음",
                     vtext(V[ci, 0], S[ci, 0], ctx.e.modes[c.mode].vops),
                     vtext(V[ci, -1], S[ci, -1], ctx.e.modes[c.mode].vops), "예" if mono else "아니오"])
        series.append(dict(x=xs, y=np.where(S[ci] == OK, V[ci], np.nan), label=c.label,
                           mode=c.mode, corner=c.corner))
        data[c.label] = dict(roots=r, monotone=mono)
        if not mono:
            res.note(f"{c.label}: Vmin이 {key}에 대해 단조가 아닙니다 — 근이 여러 개일 수 있습니다.")
    res.card("통과 구간 (모든 조건 동시)", f"{key} ∈ {text}", f"target {ctx.target:.3f} V")
    res.card("binding 근", ", ".join(F.sgn(x, fmt) for x in broots) or "없음", unit)
    res.table("roots", "조건별 근 (Vmin = target)", ["조건", f"근 ({unit})", f"Vmin @ {lo:g}", f"Vmin @ {hi:g}", "단조"], rows)
    res.table("sweep", "sweep 값", [key] + [c.label for c in ctx.checks],
              [[float(x)] + [num(E[ci, k]) for ci in allc] for k, x in enumerate(xs)], inline=False)
    res.figure("sweep", f"{key} sweep", F.curves(series, F.axis_label(key), ctx.target, ctx.reference, broots))
    res.data.update(binding_roots=broots, intervals=ivs, checks=data)


def plane_grid(ctx: Context, mode: str, xk: str, yk: str, xs: np.ndarray, ys: np.ndarray,
               u: np.ndarray, levers=None) -> np.ndarray:
    """Vmin over an (x, y) slice for one mode; levers on the slice's own axes are skipped
    (they move the markers instead). NaN = above the supply grid."""
    base = ctx.base[mode]
    pseudo = Check(mode, "plane", base.copy(), base.copy(), None)
    row = ctx.rows(pseudo, u[None], levers, skip_axes=(xk, yk))[0]
    R = np.tile(row, (len(xs) * len(ys), 1))
    R[:, axis_index(xk)] = np.tile(xs, len(ys))
    R[:, axis_index(yk)] = np.repeat(ys, len(xs))
    v, st = ctx.e.vmin(mode, R, ctx.z)
    return np.where(st == ABOVE, np.nan, v).reshape(len(ys), len(xs))


def markers(ctx: Context, u: np.ndarray, xk: str, yk: str) -> list[dict]:
    """Binding checks on the slice; checks sharing a position merge (pass = all pass)."""
    ix, iy = axis_index(xk), axis_index(yk)
    V, S = ctx.evaluate(u[None])
    E = eff(V, S)[0]
    out: dict[tuple, dict] = {}
    for ci, c in enumerate(ctx.checks):
        p0 = ctx.rows(c, np.zeros_like(u)[None])[0]
        p1 = ctx.rows(c, u[None])[0]
        key = (round(p1[ix], 6), round(p1[iy], 6), c.corner or c.label)
        mk = out.setdefault(key, dict(x0=p0[ix], y0=p0[iy], x1=p1[ix], y1=p1[iy],
                                      label=c.corner or c.label, ok=True))
        mk["ok"] = mk["ok"] and bool(E[ci] <= ctx.target + 1e-6)
    return list(out.values())


def plane_axes(spec: dict, ctx: Context, prefix: str = "") -> tuple[str, str, np.ndarray, np.ndarray, tuple]:
    xk, yk = spec[prefix + "x"], spec[prefix + "y"]
    if xk == yk:
        raise SpecError("x축과 y축이 같습니다")
    ix, iy = axis_index(xk), axis_index(yk)
    box_x = (min(ctx.e.modes[m].box[ix][0] for m in ctx.modes), max(ctx.e.modes[m].box[ix][1] for m in ctx.modes))
    box_y = (min(ctx.e.modes[m].box[iy][0] for m in ctx.modes), max(ctx.e.modes[m].box[iy][1] for m in ctx.modes))

    def rng(key, box):
        lo = spec.get(prefix + key + "_lo")
        hi = spec.get(prefix + key + "_hi")
        return (float(lo) if lo not in (None, "") else box[0], float(hi) if hi not in (None, "") else box[1])

    (x0, x1), (y0, y1) = rng("x", box_x), rng("y", box_y)
    n = int(spec[prefix + "n"])
    return xk, yk, np.linspace(x0, x1, n), np.linspace(y0, y1, n), (box_x, box_y)


PLANE_FIELDS = [field_("x", "axis", "x축"), field_("y", "axis", "y축"),
                field_("x_lo", "number", "x 시작", optional=True, hint="빈칸 = 학습 범위"),
                field_("x_hi", "number", "x 끝", optional=True),
                field_("y_lo", "number", "y 시작", optional=True),
                field_("y_hi", "number", "y 끝", optional=True),
                field_("n", "int", "격자 (한 변)", min=11, max=151, hint="61 ≈ 2 mV · 81 이상은 느림")]


@analysis("plane", "Forward", "2D process window",
          "두 축 평면에서 cell Vmin = max(read, write)를 칠하고 read·write 목표 경계와 기준 spec을 겹쳐 그립니다 "
          "(논문 Fig. 5 형식). 나머지 축은 고정입니다.",
          uses=["target", "z", "base", "checks"],
          fields=PLANE_FIELDS + [field_("fill", "select", "색으로 칠할 값",
                                        options=[["cell", "cell = max(read, write)"], ["read", "read"], ["write", "write"]]),
                                 FIXED_LEVERS],
          defaults={"x": "cn", "y": "pu", "x_lo": None, "x_hi": None, "y_lo": None, "y_hi": None,
                    "n": 61, "fill": "cell", "target": DEFAULTS["reference_vmin"]})
def _plane(spec, ctx, res, progress):
    xk, yk, xs, ys, box = plane_axes(spec, ctx)
    u = fixed_usage(ctx)[0]
    planes = {}
    for m in ctx.modes:
        progress(f"{m} 평면 계산 ({len(xs)}×{len(ys)})")
        planes[m] = plane_grid(ctx, m, xk, yk, xs, ys, u)
    vr, vw = planes.get("read"), planes.get("write")
    fill = spec["fill"] if spec["fill"] in planes or spec["fill"] == "cell" else "cell"
    title = "today" if not any(lv.usage for lv in ctx.levers) else \
        " · ".join(f"{lv.label} {lv.text(lv.usage)}" for lv in ctx.levers if lv.usage)
    mks = markers(ctx, u, xk, yk)
    res.figure("window", "process window", F.window(
        [dict(title=title, x=xs, y=ys, vr=vr, vw=vw, markers=mks)], xk, yk, ctx.target, ctx.reference, box, fill))
    c = F.cell(vr, vw)
    X, Y = np.meshgrid(xs, ys)
    inside = (X >= box[0][0]) & (X <= box[0][1]) & (Y >= box[1][0]) & (Y <= box[1][1])
    frac = float(np.mean(c[inside] <= ctx.target)) if inside.any() else float("nan")
    res.card("통과 면적 (학습 범위 안)", f"{frac * 100:.1f} %", f"cell Vmin ≤ {ctx.target:.3f} V")
    for mk in mks:
        res.card(f"{mk['label']}", "통과" if mk["ok"] else "실패", "해당 corner의 정확한 Vmin 기준")
    res.table("grid", "평면 값", [xk, yk] + [f"vmin_{m}" for m in planes] + ["cell"],
              [[float(X.flat[k]), float(Y.flat[k])] + [num(planes[m].flat[k]) for m in planes] + [num(c.flat[k])]
               for k in range(X.size)], inline=False)
    res.data.update(pass_fraction=frac, markers=[{k: (float(v) if isinstance(v, (float, np.floating)) else v)
                                                  for k, v in mk.items()} for mk in mks])


# ======================================================================= INVERSE
@analysis("levers", "Inverse", "공정 lever 조합 (single · priority · balanced · min-cost)",
          "lever마다 상한(max_change)을 두고, 목표 Vmin을 모든 binding 조건에서 동시에 만족하는 조합을 찾습니다. "
          "priority는 목록 순서대로 상한까지 쓰고, balanced는 모든 lever를 상한의 같은 비율만큼 씁니다. "
          "confidence를 고르면 GP posterior 분위수 기준의 robust 해도 같이 냅니다.",
          uses=["target", "z", "base", "checks"],
          fields=[LEVER_FIELD,
                  field_("strategies", "multi", "풀이 방식",
                         options=[["single", "single (lever 하나씩)"], ["priority", "priority (목록 순서)"],
                                  ["balanced", "balanced (같은 비율)"], ["min_cost", "min-cost (weight 합 최소)"]]),
                  field_("confidence", "select", "robust 기준",
                         options=[[None, "없음 (posterior mean)"], [0.9, "90 %"], [0.95, "95 %"], [0.99, "99 %"]]),
                  field_("draws", "int", "posterior 표본 수", min=0, max=20000, hint="0 = P(pass) 생략"),
                  field_("panels", "text", "window 패널", hint="auto 또는 baseline, priority, single:id … (쉼표)"),
                  field_("plane_n", "int", "window 격자", min=21, max=151),
                  field_("map", "bool", "두 lever map 그리기")],
          defaults={"levers": [
              {"id": "local_N", "label": "local N σ", "type": "scale", "axes": ["l_com"], "max_change": -0.10, "weight": 1},
              {"id": "global_N", "label": "global N", "type": "pull", "axes": ["cn"], "max_change": -0.20, "weight": 1},
              {"id": "global_P", "label": "global P", "type": "pull", "axes": ["pu"], "max_change": -0.20, "weight": 1}],
              "strategies": ["single", "priority", "balanced"], "confidence": None, "draws": 2000,
              "panels": "auto", "plane_n": 61, "plane_x": "cn", "plane_y": "pu", "map": True})
def _levers(spec, ctx, res, progress):
    k = len(ctx.levers)
    if not k:
        raise SpecError("lever를 하나 이상 정의해 주세요")
    T = ctx.target
    g = ctx.binding
    V0, S0 = ctx.evaluate(np.zeros((1, k)))
    b0 = float(eff(V0, S0).max())
    labels = [c.label for c in ctx.checks]
    res.data["baseline"] = {lab: num(eff(V0, S0)[0, i]) for i, lab in enumerate(labels)}
    res.data["baseline_binding"] = b0

    progress("lever별 sweep")
    grid = np.linspace(0, 1, 11)
    sweeps, slope = [], {}
    for j, lv in enumerate(ctx.levers):
        U = np.zeros((len(grid), k))
        U[:, j] = grid
        B = g(U)
        if not solve.monotone(B):
            res.note(f"{lv.label}: binding Vmin이 usage에 대해 단조 감소가 아닙니다 — 이분법 해가 최소가 아닐 수 있습니다.")
        sweeps.append(dict(label=f"{lv.label} ({lv.limit_text()})", usage=grid, binding=B, id=lv.id))
        d = 0.05
        step = abs(lv.max_change) * d * (1 if lv.type == "shift" else 100)
        slope[lv.id] = float((B[0] - g(np.eye(k)[j][None] * d)[0]) * 1e3 / step)
    res.data["slope_mV_per_unit"] = slope

    sols: dict[str, dict] = {}

    def record(name: str, u: np.ndarray, ok: bool, basis: str) -> None:
        V, S = ctx.evaluate(u[None])
        E = eff(V, S)[0]
        sols[name] = dict(u=u.copy(), reached=bool(ok), basis=basis, binding=float(E.max()),
                          checks={lab: num(E[i]) for i, lab in enumerate(labels)})

    strategies = spec.get("strategies") or []
    progress("해 찾기 (posterior mean)")
    if "single" in strategies:
        for j, lv in enumerate(ctx.levers):
            u, ok = solve.single(g, k, j, T)
            record(f"single:{lv.id}", u, ok, "mean")
    if "priority" in strategies:
        u, ok, _ = solve.priority(g, k, list(range(k)), T)
        record("priority", u, ok, "mean")
    if "balanced" in strategies:
        u, ok = solve.balanced(g, k, T)
        record("balanced", u, ok, "mean")
    if "min_cost" in strategies:
        progress("min-cost 격자 탐색")
        u, ok, resn = solve.min_cost(g, k, np.array([lv.weight for lv in ctx.levers]), T)
        record("min_cost", u, ok, "mean")
        if k > 1:
            res.note(f"min-cost는 lever {k - 1}개를 {resn}칸 격자로 훑고 나머지 하나를 이분법으로 풉니다 "
                     f"(격자 간격 = 상한의 {100 / (resn - 1):.1f} %).")

    draws = int(spec.get("draws") or 0)
    conf = spec.get("confidence")
    seed = int(spec.get("seed", 7))
    if conf:
        conf = float(conf)
        progress(f"robust 해 ({conf * 100:g} % 분위) — 첫 실행은 posterior 준비로 20–30 s")
        nd = max(draws, 1000)

        def gq(U: np.ndarray) -> np.ndarray:
            return np.array([np.quantile(ctx.binding_draws(u, nd, seed), conf) for u in np.atleast_2d(U)])

        tag = f"@{conf * 100:g}%"
        for name in list(sols):
            if name.startswith("single:"):
                j = [lv.id for lv in ctx.levers].index(name.split(":", 1)[1])
                u, ok = solve.single(gq, k, j, T, iters=20)
            elif name == "priority":
                u, ok, _ = solve.priority(gq, k, list(range(k)), T, iters=20)
            elif name == "balanced":
                u, ok = solve.balanced(gq, k, T, iters=20)
            else:
                continue
            record(name + tag, u, ok, f"{conf * 100:g} % quantile")
        if "min_cost" in sols:
            res.note("min-cost는 robust 기준을 지원하지 않습니다 (격자 × posterior 계산량). mean 기준 해의 P(pass)만 보고합니다.")

    rob: dict[str, np.ndarray] = {}
    if draws:
        progress("P(pass) 계산 — 첫 실행은 posterior 준비로 20–30 s")
        for name, s in sols.items():
            d = ctx.binding_draws(s["u"], draws, seed)
            rob[name] = d
            s.update(p_pass=float(np.mean(d <= T)), q05=float(np.quantile(d, 0.05)),
                     q50=float(np.quantile(d, 0.5)), q95=float(np.quantile(d, 0.95)))

    # ---- tables / data ------------------------------------------------------
    lev_cols = [f"{lv.label}" for lv in ctx.levers]
    rows = []
    for name, s in sols.items():
        rows.append([name, s["basis"], "도달" if s["reached"] else "도달 불가",
                     *[lv.text(s["u"][j]) for j, lv in enumerate(ctx.levers)],
                     f"{s['binding']:.4f}" if np.isfinite(s["binding"]) else "∞",
                     *[f"{s['checks'][lab]:.4f}" if s["checks"][lab] is not None else "∞" for lab in labels],
                     f"{s['p_pass']:.2f}" if "p_pass" in s else "—",
                     f"{s['q05']:.4f} – {s['q95']:.4f}" if "q05" in s else "—"])
    res.table("solutions", "해", ["해", "기준", "결과", *lev_cols, "binding Vmin", *labels, "P(pass)", "5–95 %"], rows)
    res.table("levers", "lever 정의와 기울기", ["lever", "type", "axes", "상한", "기울기 @baseline"],
              [[lv.label, lv.type, "+".join(lv.axes), lv.limit_text(),
                f"{slope[lv.id]:.3f} mV per {'mV' if lv.type == 'shift' else '1 %'}"] for lv in ctx.levers])
    res.table("sweeps", "lever sweep", ["lever", "usage", "change", "binding"],
              [[s["id"], float(u), ctx.levers[j].change(u), num(b)] for j, s in enumerate(sweeps)
               for u, b in zip(s["usage"], s["binding"])], inline=False)
    res.data["solutions"] = {
        name: dict(reached=s["reached"], basis=s["basis"], binding=num(s["binding"]), checks=s["checks"],
                   usage={lv.id: float(s["u"][j]) for j, lv in enumerate(ctx.levers)},
                   change={lv.id: float(lv.change(s["u"][j])) for j, lv in enumerate(ctx.levers)},
                   **{q: s[q] for q in ("p_pass", "q05", "q50", "q95") if q in s})
        for name, s in sols.items()}

    res.card("현재 binding Vmin", f"{b0:.4f} V", f"target 대비 {mv(b0 - T)}")
    for name in ("priority", "balanced", "min_cost"):
        if name in sols:
            s = sols[name]
            txt = " · ".join(f"{lv.label} {lv.text(s['u'][j])}" for j, lv in enumerate(ctx.levers)
                             if s["u"][j] > 1e-9) or "변경 없음"
            hint = ("도달" if s["reached"] else "상한을 다 써도 도달 불가") + \
                (f" · P(pass) {s['p_pass']:.2f}" if "p_pass" in s else "")
            res.card(name, txt, hint)
    if conf:
        for name in ("priority", "balanced"):
            if name + tag in sols:
                s = sols[name + tag]
                txt = " · ".join(f"{lv.label} {lv.text(s['u'][j])}" for j, lv in enumerate(ctx.levers)
                                 if s["u"][j] > 1e-9) or "변경 없음"
                res.card(name + tag, txt, "도달" if s["reached"] else "도달 불가")

    # ---- figures -------------------------------------------------------------
    for sw in sweeps:
        name = f"single:{sw['id']}"
        sw["solution"] = float(sols[name]["u"][[lv.id for lv in ctx.levers].index(sw["id"])]) \
            if name in sols and sols[name]["reached"] else None
    res.figure("sweeps", "lever 하나씩 — binding Vmin vs usage", F.lever_sweeps(sweeps, T, ctx.reference))
    res.figure("usage", "해마다 lever 상한을 얼마나 쓰는가", F.lever_usage(
        [(n, s["u"], s["reached"], [lv.text(s["u"][j]) for j, lv in enumerate(ctx.levers)]) for n, s in sols.items()],
        ctx.levers))
    if rob:
        res.figure("robust", "GP posterior로 본 binding Vmin 분포", F.robust(rob, T))

    xk, yk = spec.get("plane_x", "cn"), spec.get("plane_y", "pu")
    panels = spec.get("panels") or "auto"
    if isinstance(panels, str):
        panels = [p.strip() for p in panels.split(",") if p.strip()] if panels != "auto" else []
    if not panels:
        panels = ["baseline"] + [p for p in ("priority", "balanced", "min_cost") if p in sols]
        if len(panels) == 1:
            panels += [n for n in sols if n.startswith("single:")][:5]
    panels = [p for p in panels if p == "baseline" or p in sols][:6]
    if panels:
        _, _, xs, ys, box = plane_axes(dict(x=xk, y=yk, n=spec["plane_n"]), ctx)
        cache: dict[tuple, dict] = {}
        out = []
        for p in panels:
            u = np.zeros(k) if p == "baseline" else sols[p]["u"]
            key = tuple(round(float(u[j]), 9) if any(a not in (xk, yk) for a in lv.axes) else 0.0
                        for j, lv in enumerate(ctx.levers))
            if key not in cache:
                progress(f"window 패널 '{p}'")
                cache[key] = {m: plane_grid(ctx, m, xk, yk, xs, ys, u) for m in ctx.modes}
            pl = cache[key]
            if p == "baseline":
                title = "baseline (today)"
            elif p.startswith("single:"):
                lv = ctx.levers[[x.id for x in ctx.levers].index(p.split(":", 1)[1].split("@")[0])]
                title = lv.label + ("" if sols[p]["reached"] else " (ceiling)")
            else:
                title = {"priority": "priority path", "balanced": "balanced (minimax burden)",
                         "min_cost": "min cost"}.get(p.split("@")[0], p) + \
                        (" " + p.split("@")[1] if "@" in p else "")
            changes = wrap([f"{lv.label} {lv.text(u[j])}" for j, lv in enumerate(ctx.levers) if u[j] > 1e-9])
            out.append(dict(title=title + ("\n" + changes if changes else ""), x=xs, y=ys,
                            vr=pl.get("read"), vw=pl.get("write"), markers=markers(ctx, u, xk, yk)))
        res.figure("window", "process window — 해마다", F.window(out, xk, yk, T, ctx.reference, box))

    if spec.get("map") and k >= 2:
        progress("두 lever map")
        n = 21
        ua = np.linspace(0, 1, n)
        A, Bm = np.meshgrid(ua, ua)
        U = np.zeros((n * n, k))
        U[:, 0], U[:, 1] = A.ravel(), Bm.ravel()
        Bv = g(U).reshape(n, n)
        pts = [dict(name=nm, ua=s["u"][0], ub=s["u"][1]) for nm, s in sols.items()
               if not nm.startswith("single:") and np.all(s["u"][2:] < 1e-9)]
        pts += [dict(name=nm, ua=s["u"][0], ub=s["u"][1]) for nm, s in sols.items()
                if nm.startswith("single:") and s["reached"] and np.all(s["u"][2:] < 1e-9)][:2]
        res.figure("map", "두 lever 조합 map", F.lever_map(ua, ua, Bv, ctx.levers[0], ctx.levers[1], T, pts))
        if k > 2:
            res.note(f"lever map은 앞의 두 lever({ctx.levers[0].label}, {ctx.levers[1].label})만 움직이고 나머지는 0입니다. "
                     "나머지 lever를 쓰는 해는 map에 표시하지 않습니다.")
    order = ["window", "usage", "robust", "map", "sweeps"]       # the paper-style window first
    res.figures.sort(key=lambda f: order.index(f[0]) if f[0] in order else len(order))


@analysis("retarget", "Inverse", "제품 retarget (array size · yield → Vmin)",
          "같은 cell을 다른 array 크기·yield 사양에 쓸 때 Vmin과 binding mode가 어떻게 바뀌는지 봅니다. "
          "Z는 학습하지 않는 physics layer 입력이라 재학습 없이 거꾸로 풀립니다 — 목표를 지키는 최대 array 크기를 찾습니다.",
          uses=["target", "z", "base", "checks"],
          fields=[field_("array_mb_list", "numbers", "array 크기 (Mb, 쉼표)", hint="Z 칸의 array 크기 = 현재 제품"),
                  FIXED_LEVERS],
          defaults={"array_mb_list": [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]})
def _retarget(spec, ctx, res, progress):
    U = fixed_usage(ctx)
    zg = ctx.zgrids(U)
    yt = float(spec["z"]["yield"])
    lobe = bool(spec["z"].get("lobe"))
    labels = [c.label for c in ctx.checks]

    def zfor(mb: float) -> float:
        z = derive_z_target(mb=mb, y_target=yt)
        return z + lobe_bias(round(z, 4)) if lobe else z

    def vm(mb: float) -> tuple[np.ndarray, np.ndarray]:
        z = zfor(mb)
        cols = [vmin_from_z(gz, z, ctx.e.modes[c.mode].vops) for gz, c in zip(zg, ctx.checks)]
        return np.array([c[0][0] for c in cols]), np.array([c[1][0] for c in cols])

    def bind(log2mb: float) -> float:
        v, s = vm(2.0 ** log2mb)
        return float(eff(v, s).max())

    mbs = sorted(float(x) for x in spec["array_mb_list"])
    rows = []
    for mb in mbs:
        v, s = vm(mb)
        e = eff(v, s)
        i = int(np.argmax(e))
        rows.append([mb, round(zfor(mb), 4), *[vtext(v[ci], s[ci], ctx.e.modes[c.mode].vops) for ci, c in enumerate(ctx.checks)],
                     labels[i]])

    def max_mb(level: float) -> float | None:
        lo, hi = -10.0, 20.0
        if bind(lo) > level:
            return None
        if bind(hi) <= level:
            return 2.0 ** hi
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if bind(mid) <= level else (lo, mid)
        return 2.0 ** lo

    mt, mr = max_mb(ctx.target), max_mb(ctx.reference)
    fine = np.linspace(math.log2(mbs[0]), math.log2(mbs[-1]), 241)
    Vf = np.array([eff(*vm(2.0 ** x)) for x in fine])        # (n, checks)
    arg = np.argmax(Vf, axis=1)
    switches = []
    for i in range(len(fine) - 1):
        if arg[i] != arg[i + 1]:
            a, b = fine[i], fine[i + 1]
            for _ in range(40):
                m = 0.5 * (a + b)
                a, b = (m, b) if np.argmax(eff(*vm(2.0 ** m))) == arg[i] else (a, m)
            switches.append(dict(mb=2.0 ** (0.5 * (a + b)), from_=labels[arg[i]], to=labels[arg[i + 1]]))
    cur = float(spec["z"]["array_mb"])
    vc, sc = vm(cur)
    res.card("현재 array", f"{cur:g} Mb → {float(eff(vc, sc).max()):.4f} V", f"Z = {zfor(cur):.3f}")
    res.card(f"target {ctx.target:.3f} V를 지키는 최대 array", f"{mt:.3g} Mb" if mt else "없음", f"yield {yt * 100:g} %")
    res.card(f"reference {ctx.reference:.3f} V를 지키는 최대 array", f"{mr:.3g} Mb" if mr else "없음", "")
    for sw in switches:
        res.card("binding 전환", f"{sw['mb']:.3g} Mb", f"{sw['from_']} → {sw['to']}")
    res.table("arrays", "array 크기별 Vmin", ["Mb", "Z", *labels, "binding"], rows)
    marks = ([(mt, f"max for target ({mt:.3g} Mb)")] if mt and mbs[0] <= mt <= mbs[-1] else []) + \
            [(sw["mb"], f"binding → {sw['to']}") for sw in switches]
    series = [dict(y=np.where(np.isfinite(Vf[:, ci]), Vf[:, ci], np.nan), label=lab, mode=c.mode, corner=c.corner)
              for ci, (lab, c) in enumerate(zip(labels, ctx.checks))]
    res.figure("retarget", "array 크기에 따른 Vmin", F.retarget(2.0 ** fine, series, ctx.target, ctx.reference, cur, marks))
    res.data.update(max_mb_target=mt, max_mb_reference=mr, switches=switches,
                    rows={str(r[0]): r for r in rows})


@analysis("recenter", "Inverse", "Vth target 재조정 (분포 중심 이동)",
          "σ를 줄이는 대신 global Vth 분포의 중심(implant target)을 옮겨 모든 조건의 최악 Vmin을 최소로 만드는 위치를 찾습니다. "
          "leakage·speed 비용은 이 모델에 없으니 결과는 Vmin 쪽 상한입니다.",
          uses=["target", "z", "base", "checks"],
          fields=[field_("x", "axis", "이동할 축 1"), field_("y", "axis", "이동할 축 2"),
                  field_("range", "number", "탐색 범위 ± (축 단위)"), field_("n", "int", "격자 (한 변)", min=11, max=101),
                  field_("in_box", "bool", "모든 조건이 학습 범위 안에 있을 때만 허용"), FIXED_LEVERS],
          defaults={"x": "cn", "y": "pu", "range": 20.0, "n": 41, "in_box": True, "checks": "all_corners"})
def _recenter(spec, ctx, res, progress):
    xk, yk = spec["x"], spec["y"]
    ix, iy = axis_index(xk), axis_index(yk)
    r, n = float(spec["range"]), int(spec["n"])
    U = fixed_usage(ctx)
    base_rows = [ctx.rows(c, U)[0] for c in ctx.checks]

    def worst(shifts: np.ndarray):
        m = len(shifts)
        V = np.empty((m, len(ctx.checks)))
        S = np.empty((m, len(ctx.checks)), int)
        inside = np.ones(m, bool)
        for mode in ctx.modes:
            idx = [i for i, c in enumerate(ctx.checks) if c.mode == mode]
            if not idx:
                continue
            R = np.concatenate([np.repeat(base_rows[i][None], m, 0) for i in idx])
            R[:, ix] += np.tile(shifts[:, 0], len(idx))
            R[:, iy] += np.tile(shifts[:, 1], len(idx))
            v, st = ctx.e.vmin(mode, R, ctx.z)
            V[:, idx], S[:, idx] = v.reshape(len(idx), m).T, st.reshape(len(idx), m).T
            box = ctx.e.modes[mode].box
            ok = np.all((R >= box[:, 0] - 1e-9) & (R <= box[:, 1] + 1e-9), axis=1)
            inside &= ok.reshape(len(idx), m).all(axis=0)
        E = eff(V, S)
        return E.max(axis=1), E, inside

    progress(f"이동 격자 {n}×{n}")
    d = np.linspace(-r, r, n)
    DX, DY = np.meshgrid(d, d)
    W, _, inside = worst(np.column_stack([DX.ravel(), DY.ravel()]))
    feas = inside if spec.get("in_box") else np.ones_like(inside)
    if not feas.any():
        raise SpecError("학습 범위 안에 머무는 이동이 없습니다 — 범위를 줄이거나 in_box를 끄세요")
    i = int(np.argmin(np.where(feas, W, np.inf)))
    step = d[1] - d[0]
    fine = np.linspace(-step, step, 11)
    FX, FY = np.meshgrid(DX.flat[i] + fine, DY.flat[i] + fine)
    fs = np.column_stack([FX.ravel(), FY.ravel()])
    Wf, _, insf = worst(fs)
    j = int(np.argmin(np.where(insf if spec.get("in_box") else True, Wf, np.inf)))
    best = (float(fs[j, 0]), float(fs[j, 1]))
    w0, E0, _ = worst(np.zeros((1, 2)))
    w1, E1, ins1 = worst(np.array([best]))
    labels = [c.label for c in ctx.checks]
    res.card("최적 이동", f"{xk} {F.sgn(best[0])} · {yk} {F.sgn(best[1])} ({AXIS[xk]['unit']})",
             "분포 전체(모든 corner)를 같이 이동")
    res.card("최악 Vmin", f"{w0[0]:.4f} → {w1[0]:.4f} V", f"{mv(w1[0] - w0[0])}")
    res.card("binding 조건 (이동 후)", labels[int(np.argmax(E1[0]))],
             "target 통과" if w1[0] <= ctx.target else f"target까지 {mv(w1[0] - ctx.target)} 부족")
    res.table("checks", "조건별 Vmin (이동 전 → 후)", ["조건", "현재", "이동 후", "변화"],
              [[lab, num(E0[0, k]), num(E1[0, k]), mv(E1[0, k] - E0[0, k])] for k, lab in enumerate(labels)])
    res.figure("recenter", "분포 중심 이동 map", F.recenter(d, d, W.reshape(n, n), feas.reshape(n, n),
                                                       ctx.target, best, xk, yk))
    res.note("Vth target 이동은 leakage·speed와 trade-off입니다. 이 모델은 Vmin만 보므로, 실제 target은 leakage 사양과 같이 정해야 합니다.")
    if abs(abs(best[0]) - r) < step or abs(abs(best[1]) - r) < step:
        res.note("최적점이 탐색 범위 경계에 붙어 있습니다 — 범위를 넓혀 다시 확인하세요.")
    ii, jj = np.unravel_index(i, (n, n))
    near = feas.reshape(n, n)[max(ii - 1, 0):ii + 2, max(jj - 1, 0):jj + 2]
    if spec.get("in_box") and not near.all():
        res.note("최적점이 학습 범위 경계(빗금) 바로 옆입니다 — 더 나은 점이 범위 밖에 있을 수 있지만 그쪽은 GP 외삽이라 고르지 않았습니다.")
    res.data.update(best_shift=list(best), worst_before=float(w0[0]), worst_after=float(w1[0]),
                    gain_mV=float((w0[0] - w1[0]) * 1e3), inside=bool(ins1[0]))


@analysis("roadmap", "Inverse", "개선 roadmap (목표별 필요 lever)",
          "Vmin 개선 목표를 단계적으로 바꿔 가며 priority·balanced 해를 구합니다. 상한 때문에 더는 도달할 수 없는 지점이 같이 나옵니다.",
          uses=["reference", "z", "base", "checks"],
          fields=[LEVER_FIELD,
                  field_("strategies", "multi", "풀이 방식",
                         options=[["priority", "priority"], ["balanced", "balanced"], ["min_cost", "min-cost (느림)"]]),
                  field_("gain_from", "number", "개선 목표 시작 (mV, reference 대비)"),
                  field_("gain_to", "number", "개선 목표 끝 (mV)"),
                  field_("gain_step", "number", "간격 (mV)")],
          defaults={"levers": [
              {"id": "local_N", "label": "local N σ", "type": "scale", "axes": ["l_com"], "max_change": -0.10, "weight": 1},
              {"id": "global_N", "label": "global N", "type": "pull", "axes": ["cn"], "max_change": -0.20, "weight": 1},
              {"id": "global_P", "label": "global P", "type": "pull", "axes": ["pu"], "max_change": -0.20, "weight": 1}],
              "strategies": ["priority", "balanced"], "gain_from": 30, "gain_to": 70, "gain_step": 5})
def _roadmap(spec, ctx, res, progress):
    k = len(ctx.levers)
    if not k:
        raise SpecError("lever를 하나 이상 정의해 주세요")
    g = ctx.binding
    a, b, st = float(spec["gain_from"]), float(spec["gain_to"]), abs(float(spec["gain_step"]))
    if st <= 0:
        raise SpecError("간격은 0보다 커야 합니다")
    gains = np.arange(a, b + st * 0.5, st)
    floor = float(g(np.ones((1, k)))[0])
    b0 = float(g(np.zeros((1, k)))[0])
    plan, maxg = {}, {}
    rows = [[f"{x:g}", f"{ctx.reference - x / 1e3:.3f}"] for x in gains]
    for sname in spec.get("strategies") or []:
        U = np.full((len(gains), k), np.nan)
        for i, x in enumerate(gains):
            progress(f"{sname}: −{x:g} mV")
            T = ctx.reference - x / 1e3
            if sname == "priority":
                u, ok, _ = solve.priority(g, k, list(range(k)), T)
            elif sname == "balanced":
                u, ok = solve.balanced(g, k, T)
            else:
                u, ok, _ = solve.min_cost(g, k, np.array([lv.weight for lv in ctx.levers]), T)
            if ok:
                U[i] = u
            rows[i].append(" · ".join(f"{lv.label} {lv.text(u[j])}" for j, lv in enumerate(ctx.levers)
                                      if u[j] > 1e-9) or "변경 없음" if ok else "도달 불가")
        plan[sname] = U
        maxg[sname] = (ctx.reference - floor) * 1e3
    res.card("현재 binding Vmin", f"{b0:.4f} V", f"reference 대비 {mv(b0 - ctx.reference)}")
    res.card("모든 lever 상한일 때", f"{floor:.4f} V", f"최대 개선 {mv(ctx.reference - floor)} (reference 대비)")
    res.table("roadmap", "개선 목표별 필요 lever", ["개선 (mV)", "target (V)", *plan.keys()], rows)
    res.figure("roadmap", "개선 목표별 lever usage", F.roadmap(gains, plan, ctx.levers, maxg))
    res.data.update(floor=floor, baseline=b0, max_gain_mV=(ctx.reference - floor) * 1e3,
                    plan={s: [[None if not np.isfinite(x) else float(x) for x in r] for r in U] for s, U in plan.items()},
                    gains=gains.tolist())


# ======================================================================= SENSITIVITY
@analysis("sensitivity", "Sensitivity", "민감도 · exchange rate",
          "조건마다 축별 국소 기울기(학습 범위 10 %당 mV)를 계산하고, lever가 있으면 lever 사이의 교환비를 냅니다. "
          "§VII의 저장된 global Sobol S_T도 나란히 보여 줍니다 (재계산 아님).",
          uses=["z", "base", "checks"],
          fields=[field_("step", "number", "미분 간격 (학습 범위 비율)", hint="0.02 = 범위의 2 %"),
                  field_("show_sobol", "bool", "저장된 Sobol S_T 같이 보기"),
                  field_("levers", "levers", "교환비를 볼 lever (선택)", columns=["id", "label", "type", "axes", "max_change"])],
          defaults={"step": 0.02, "show_sobol": True, "levers": []})
def _sensitivity(spec, ctx, res, progress):
    h = float(spec["step"])
    U = fixed_usage(ctx)
    slopes, rows, data = [], [], {}
    for c in ctx.checks:
        m = ctx.e.modes[c.mode]
        base = ctx.rows(c, U)[0]
        R = np.repeat(base[None], 2 * len(AXIS_KEYS), 0)
        for i in range(len(AXIS_KEYS)):
            span = m.box[i, 1] - m.box[i, 0]
            R[2 * i, i] += h * span
            R[2 * i + 1, i] -= h * span
        v, st = ctx.e.vmin(c.mode, R, ctx.z)
        vals = []
        for i in range(len(AXIS_KEYS)):
            ok = st[2 * i] == OK and st[2 * i + 1] == OK
            vals.append((v[2 * i] - v[2 * i + 1]) / (2 * h) * 0.1 * 1e3 if ok else np.nan)
        if any(np.isnan(vals)):
            res.note(f"{c.label}: 일부 축에서 Vmin이 전압 격자 밖이라 기울기를 계산하지 않았습니다.")
        slopes.append(dict(label=c.label, mode=c.mode, values=np.array(vals)))
        data[c.label] = {k: num(x) for k, x in zip(AXIS_KEYS, vals)}
    for i, key in enumerate(AXIS_KEYS):
        rows.append([key, AXIS[key]["name"], *[f"{s['values'][i]:+.2f}" if np.isfinite(s["values"][i]) else "—"
                                               for s in slopes]])
    res.table("slopes", "축별 국소 기울기 (학습 범위 +10 %당 mV)", ["축", "의미", *[s["label"] for s in slopes]], rows)
    if ctx.levers:
        k = len(ctx.levers)
        g = ctx.binding
        b0 = float(g(np.zeros((1, k)))[0])
        ex = {}
        for j, lv in enumerate(ctx.levers):
            d = 0.05
            unit = abs(lv.max_change) * d * (1 if lv.type == "shift" else 100)
            ex[lv.id] = (b0 - float(g(np.eye(k)[j][None] * d)[0])) * 1e3 / unit
        ref = ctx.levers[0]
        res.table("exchange", "lever 교환비 (binding Vmin 기준)", ["lever", "기울기", f"{ref.label} 1단위와 같은 양"],
                  [[lv.label, f"{ex[lv.id]:.3f} mV per {'mV' if lv.type == 'shift' else '1 %'}",
                    f"{ex[ref.id] / ex[lv.id]:.2f} {'mV' if lv.type == 'shift' else '%'}" if ex[lv.id] else "—"]
                   for lv in ctx.levers])
        res.data["exchange_mV_per_unit"] = ex
    sob = None
    if spec.get("show_sobol"):
        sob = {}
        for mode in ctx.modes:
            p = RESULTS / MODES[mode]["sobol"]
            if p.is_file():
                st = json.loads(p.read_text())["sobol"]["ST"].get("z(0.625V)")
                if st:
                    sob[mode] = st
        if sob:
            res.table("sobol", "저장된 Sobol S_T — z(0.625 V), 학습 범위 전체 (§VII)", ["축", *sob.keys()],
                      [[k, *[f"{sob[m].get(k, float('nan')):.3f}" for m in sob]] for k in AXIS_KEYS])
        else:
            sob = None
    top = {s["label"]: AXIS_KEYS[int(np.nanargmax(np.abs(s["values"])))] for s in slopes if np.isfinite(s["values"]).any()}
    for lab, key in top.items():
        res.card(f"가장 민감한 축 · {lab}", f"{key} ({AXIS[key]['name']})", "국소 기울기 절댓값 기준")
    res.figure("sensitivity", "국소 기울기와 global Sobol", F.sensitivity(AXIS_KEYS, slopes, sob))
    res.data.update(slopes=data, sobol=sob)
