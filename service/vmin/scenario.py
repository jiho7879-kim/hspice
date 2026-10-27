"""Spec -> evaluation context: Z, base point, binding checks, levers.

A spec never names code paths. It names a base point per mode, a list of binding
checks (mode + corner or explicit point; all must clear the target at once) and
optional levers. A lever moves axes by u x max_change with usage u in [0, 1]:

    scale   value  <- value x (1 + a)                 local-sigma / mobility multipliers
    pull    offset <- offset x (1 + a), offset = point - base   global-distribution tightening
    shift   value  <- value + a  (axis units)          Vth target move (moves every check)

so max_change = -0.10 on a scale lever is "up to 10 % smaller", -0.20 on a pull
lever is "corner offsets up to 20 % closer to the base point".
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np

from .config import AXIS, AXIS_KEYS, CORNERS, DEFAULTS, LIMITING, MODES
from .engine import ABOVE, Engine, resolve_z, vmin_from_z

LEVER_TYPES = ("scale", "pull", "shift")
COMMON_DEFAULTS = {
    "target": DEFAULTS["target"],
    "reference_vmin": DEFAULTS["reference_vmin"],
    "z": {"array_mb": DEFAULTS["array_mb"], "yield": DEFAULTS["yield"], "lobe": False, "value": None},
    "base": {"reference": "mode_nominal", "overrides": {}},
    "checks": "limiting",
    "modes": list(MODES),
    "levers": [],
}


class SpecError(ValueError):
    """A problem in the user's spec, phrased for the user."""


def merged(defaults: dict, spec: dict) -> dict:
    """defaults <- spec, recursively for dicts; lists and scalars are replaced."""
    out = copy.deepcopy(defaults)
    for k, v in (spec or {}).items():
        out[k] = merged(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def axis_index(key: str) -> int:
    if key not in AXIS:
        raise SpecError(f"알 수 없는 축 '{key}' — 사용 가능: {', '.join(AXIS_KEYS)}")
    return AXIS_KEYS.index(key)


@dataclass
class Check:
    mode: str
    label: str
    point: np.ndarray     # absolute coordinates before any lever
    center: np.ndarray    # what pull levers pull toward (the mode's base point)
    corner: str | None


@dataclass
class Lever:
    id: str
    label: str
    type: str
    axes: list[str]
    max_change: float
    weight: float = 1.0
    usage: float = 0.0    # fixed usage, for analyses that hold levers still

    def change(self, u: float) -> float:
        return float(u) * self.max_change

    def text(self, u: float) -> str:
        a = self.change(u)
        if abs(a) < 5e-7:
            return "0"
        if self.type == "shift":
            s = f"{a:+.1f} {AXIS[self.axes[0]]['unit']}"
        else:
            s = f"{a * 100:+.1f} %"
        return s.replace("-", "−")

    def limit_text(self) -> str:
        return "max " + self.text(1.0)


def parse_lever(raw: dict, i: int) -> Lever:
    lid = str(raw.get("id") or f"lever{i + 1}")
    if "." in lid or ":" in lid:
        raise SpecError(f"lever id '{lid}'에는 '.'과 ':'을 쓸 수 없습니다")
    typ = raw.get("type", "scale")
    if typ not in LEVER_TYPES:
        raise SpecError(f"lever '{lid}': type은 {', '.join(LEVER_TYPES)} 중 하나")
    axes = raw.get("axes") or []
    axes = [axes] if isinstance(axes, str) else list(axes)
    if not axes:
        raise SpecError(f"lever '{lid}': axes가 비어 있습니다")
    for a in axes:
        axis_index(a)
    try:
        mc = float(raw.get("max_change"))
    except (TypeError, ValueError):
        raise SpecError(f"lever '{lid}': max_change가 숫자가 아닙니다") from None
    if mc == 0:
        raise SpecError(f"lever '{lid}': max_change가 0이면 움직일 수 없습니다")
    return Lever(lid, str(raw.get("label") or lid), typ, axes, mc,
                 float(raw.get("weight", 1.0) or 1.0), float(raw.get("usage", 0.0) or 0.0))


class Context:
    """Everything an analysis needs, resolved from one spec."""

    def __init__(self, spec: dict, engine: Engine):
        self.e = engine
        self.spec = spec
        self.z, self.z_text = resolve_z(spec["z"])
        self.target = float(spec["target"])
        self.reference = float(spec["reference_vmin"])
        modes = spec.get("modes")
        self.modes = [m for m in (MODES if modes is None else modes) if m in engine.modes]
        if not self.modes:
            raise SpecError("read/write 중 하나 이상을 골라 주세요")
        self.base = self._base(spec["base"])
        self.checks = self._checks(spec["checks"])
        self.levers = [parse_lever(r, i) for i, r in enumerate(spec.get("levers") or [])]
        if len({lv.id for lv in self.levers}) != len(self.levers):
            raise SpecError("lever id가 겹칩니다")

    # -- resolution -----------------------------------------------------------
    def _base(self, b: dict) -> dict[str, np.ndarray]:
        ref = b.get("reference", "mode_nominal")
        out = {}
        for m in self.e.modes:
            src = m if ref == "mode_nominal" else str(ref).removesuffix("_nominal")
            if src not in self.e.modes:
                raise SpecError(f"base.reference '{ref}' — mode_nominal / read_nominal / write_nominal")
            p = self.e.modes[src].nominal.copy()
            for k, v in (b.get("overrides") or {}).items():
                if v not in (None, ""):
                    p[axis_index(k)] = float(v)
            out[m] = p
        return out

    def _checks(self, raw) -> list[Check]:
        if raw in (None, "limiting"):
            items = [{"mode": m, "corner": LIMITING[m]} for m in self.modes]
        elif raw == "all_corners":
            items = [{"mode": m, "corner": c} for m in self.modes for c in CORNERS]
        elif raw == "nominal":
            items = [{"mode": m, "corner": "nominal"} for m in self.modes]
        elif isinstance(raw, list):
            items = [c for c in raw if c.get("mode") in self.modes]
        else:
            raise SpecError("checks는 limiting / all_corners / nominal 또는 목록이어야 합니다")
        out = []
        for c in items:
            m, corner = c["mode"], c.get("corner")
            p = self.base[m].copy()
            if corner and corner != "nominal":
                if corner not in CORNERS:
                    raise SpecError(f"corner '{corner}' — {', '.join(CORNERS)} 또는 nominal")
                for k, v in CORNERS[corner].items():
                    p[axis_index(k)] = float(v)
            for k, v in (c.get("point") or {}).items():
                p[axis_index(k)] = float(v)
            label = c.get("label") or f"{corner or 'point'}·{m}"
            out.append(Check(m, label, p, self.base[m].copy(), corner))
        if not out:
            raise SpecError("binding 조건이 하나도 없습니다")
        return out

    # -- evaluation -----------------------------------------------------------
    def rows(self, check: Check, U: np.ndarray, levers: list[Lever] | None = None,
             skip_axes: tuple[str, ...] = ()) -> np.ndarray:
        """Coordinates of one check under usage matrix U (n, k)."""
        levers = self.levers if levers is None else levers
        U = np.atleast_2d(np.asarray(U, float))
        R = np.repeat(check.point[None], len(U), axis=0)
        for j, lv in enumerate(levers):
            a = U[:, j] * lv.max_change
            for ax in lv.axes:
                if ax in skip_axes:
                    continue
                i = AXIS_KEYS.index(ax)
                if lv.type == "scale":
                    R[:, i] = R[:, i] * (1.0 + a)
                elif lv.type == "pull":
                    R[:, i] = check.center[i] + (1.0 + a) * (R[:, i] - check.center[i])
                else:
                    R[:, i] = R[:, i] + a
        return R

    def zgrids(self, U: np.ndarray, levers: list[Lever] | None = None) -> list[np.ndarray]:
        """z(Vop) per check, (n, n_vop) each -- one GP call per mode."""
        U = np.atleast_2d(np.asarray(U, float))
        out: list[np.ndarray | None] = [None] * len(self.checks)
        for mode in self.modes:
            idx = [i for i, c in enumerate(self.checks) if c.mode == mode]
            if not idx:
                continue
            R = np.concatenate([self.rows(self.checks[i], U, levers) for i in idx])
            zg = self.e.zgrid(mode, R).reshape(len(idx), len(U), -1)
            for k, i in enumerate(idx):
                out[i] = zg[k]
        return out  # type: ignore[return-value]

    def evaluate(self, U: np.ndarray, levers: list[Lever] | None = None,
                 z: float | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Vmin and status, (n, n_checks) each."""
        z = self.z if z is None else z
        zg = self.zgrids(U, levers)
        cols = [vmin_from_z(g, z, self.e.modes[c.mode].vops) for g, c in zip(zg, self.checks)]
        return np.column_stack([c[0] for c in cols]), np.column_stack([c[1] for c in cols])

    def binding(self, U: np.ndarray, levers: list[Lever] | None = None) -> np.ndarray:
        """max over checks; a check above the supply grid counts as +inf (fails)."""
        V, S = self.evaluate(U, levers)
        return np.where(S == ABOVE, np.inf, V).max(axis=1)

    def binding_draws(self, u: np.ndarray, n: int, seed: int,
                      levers: list[Lever] | None = None) -> np.ndarray:
        """(n,) posterior draws of the binding Vmin at one usage vector."""
        cols = []
        for k, mode in enumerate(self.modes):
            idx = [i for i, c in enumerate(self.checks) if c.mode == mode]
            if idx:
                R = np.concatenate([self.rows(self.checks[i], u[None], levers) for i in idx])
                cols.append(self.e.posterior_vmin(mode, R, self.z, n, seed + 1000 * k))
        return np.concatenate(cols, axis=1).max(axis=1)

    def outside(self, check: Check, row: np.ndarray) -> list[str]:
        box = self.e.modes[check.mode].box
        tol = 1e-9 * (box[:, 1] - box[:, 0] + 1)
        return [k for i, k in enumerate(AXIS_KEYS)
                if row[i] < box[i, 0] - tol[i] or row[i] > box[i, 1] + tol[i]]
