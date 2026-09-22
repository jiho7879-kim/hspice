"""Model-safe inference core for the local SRAM Vmin presentation GUI.

The GUI never imports manuscript analysis scripts because those scripts execute
experiments and write results at import time.  This module only restores trusted
saved models, predicts them, and reports the limits of each query explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import sys
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch

from demo_config import (
    APP_VERSION,
    AXES,
    AXIS_BY_KEY,
    BUNDLE_SCHEMA,
    DEFAULT_BUNDLE_DIR,
    DEVICE_COLS,
    MODE_CONFIG,
    PYTHON_ROOT,
    RESULTS_DIR,
    SEED,
    TRAIN_TEST_FRACTION,
    V_T0,
    Z_TARGET,
    public_axes,
)

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from src.data import grouped_train_test_split
from src.final_data import load_final_snmr, load_final_vtrip
from src.physics_layer import compute_vmin_from_z
from src.surrogate import Surrogate

ModeName = Literal["read", "write"]
VminStatus = Literal["in_range", "below_grid", "above_grid"]


@dataclass(frozen=True)
class CanonicalTrainingData:
    """The exact training data needed to reconstruct one saved ExactGP."""

    mode: ModeName
    x_train: np.ndarray
    y_train: np.ndarray
    vops: np.ndarray
    bounds: dict[str, tuple[float, float]]
    nominal: dict[str, float]


@dataclass
class ModeModel:
    """A restored surrogate plus its query bounds and reference coordinates."""

    mode: ModeName
    surrogate: Surrogate
    vops: np.ndarray
    bounds: dict[str, tuple[float, float]]
    nominal: dict[str, float]
    source: str


class DemoInputError(ValueError):
    """A safe, user-facing invalid query error."""


def _assert_mode(mode: str) -> ModeName:
    if mode not in MODE_CONFIG:
        raise DemoInputError(f"unknown mode {mode!r}; choose read or write")
    return mode  # type: ignore[return-value]


def canonical_training_data(mode: str) -> CanonicalTrainingData:
    """Rebuild the canonical train split used by ``v_b_forward.py``.

    This is intentionally the sole route that reads the protected XLSX inputs.
    Windows demonstration bundles are created from this function once, then run
    without these XLSX files.
    """
    name = _assert_mode(mode)
    cfg = MODE_CONFIG[name]
    loader = load_final_snmr if name == "read" else load_final_vtrip
    frame = loader()
    avg = str(cfg["avg_col"])
    std = str(cfg["std_col"])
    frame = frame[frame[avg].notna() & frame[std].notna() & frame["n_mc"].notna()].copy()
    x_all = frame[list(DEVICE_COLS) + ["vop"]].to_numpy(dtype=float)
    y_all = frame[[avg, std]].to_numpy(dtype=float) * 1e-3
    _, groups = np.unique(x_all[:, :len(DEVICE_COLS)], axis=0, return_inverse=True)
    x_train, _, y_train, _ = grouped_train_test_split(
        x_all, y_all, groups, TRAIN_TEST_FRACTION, SEED,
    )
    bounds = {
        axis: (float(x_all[:, i].min()), float(x_all[:, i].max()))
        for i, axis in enumerate(DEVICE_COLS)
    }
    nominal = {axis: float(np.median(frame[axis])) for axis in DEVICE_COLS}
    vops = np.asarray(sorted(frame["vop"].unique()), dtype=float)
    return CanonicalTrainingData(name, x_train, y_train, vops, bounds, nominal)


def _to_json_number(value: float | np.floating[Any] | None) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return float(value)


def _vmin_label(status: VminStatus, value: float | None, vops: np.ndarray) -> str:
    if status == "below_grid":
        return f"< {vops[0]:.3f} V (censored)"
    if status == "above_grid":
        return f"> {vops[-1]:.3f} V (outside voltage grid)"
    assert value is not None
    return f"{value:.4f} V"


class DemoEngine:
    """Read/write model service used by the GUI and its deterministic tests."""

    def __init__(self, modes: dict[ModeName, ModeModel]) -> None:
        if set(modes) != {"read", "write"}:
            raise ValueError("the presentation engine requires one read and one write model")
        self._modes = modes

    @classmethod
    def from_source(cls, results_dir: Path = RESULTS_DIR) -> "DemoEngine":
        """Development-only loader that reconstructs models from local source data."""
        modes: dict[ModeName, ModeModel] = {}
        for mode in ("read", "write"):
            data = canonical_training_data(mode)
            checkpoint = results_dir / str(MODE_CONFIG[mode]["checkpoint_file"])
            if not checkpoint.is_file():
                raise FileNotFoundError(f"missing checkpoint: {checkpoint}")
            modes[mode] = ModeModel(
                mode=mode,
                surrogate=Surrogate.load(
                    checkpoint, data.x_train, data.y_train, n_device=len(DEVICE_COLS),
                ),
                vops=data.vops,
                bounds=data.bounds,
                nominal=data.nominal,
                source="source data + saved checkpoint",
            )
        return cls(modes)

    @classmethod
    def from_bundle(cls, bundle_dir: Path = DEFAULT_BUNDLE_DIR) -> "DemoEngine":
        """Restore a local trusted bundle without reading the original XLSX files."""
        modes: dict[ModeName, ModeModel] = {}
        for mode in ("read", "write"):
            path = bundle_dir / str(MODE_CONFIG[mode]["bundle_file"])
            if not path.is_file():
                raise FileNotFoundError(
                    f"missing {path.name}. Create a trusted local bundle with "
                    "prepare_bundle.py before launching the Windows demo.")
            state = torch.load(path, map_location="cpu", weights_only=False)
            meta = state.get("demo_bundle")
            if not isinstance(meta, dict) or meta.get("schema") != BUNDLE_SCHEMA:
                raise ValueError(f"{path} is not a supported SRAM Vmin inference bundle")
            if meta.get("mode") != mode:
                raise ValueError(f"bundle mode mismatch: expected {mode}, found {meta.get('mode')!r}")
            if tuple(meta.get("device_cols", ())) != DEVICE_COLS:
                raise ValueError(f"bundle axis order mismatch in {path}")
            raw_bounds = meta.get("bounds")
            raw_nominal = meta.get("nominal")
            raw_vops = meta.get("vops")
            if not isinstance(raw_bounds, dict) or not isinstance(raw_nominal, dict) or raw_vops is None:
                raise ValueError(f"bundle metadata is incomplete in {path}")
            bounds = {
                axis: (float(raw_bounds[axis][0]), float(raw_bounds[axis][1]))
                for axis in DEVICE_COLS
            }
            nominal = {axis: float(raw_nominal[axis]) for axis in DEVICE_COLS}
            modes[mode] = ModeModel(
                mode=mode,
                surrogate=Surrogate.load(path, n_device=len(DEVICE_COLS)),
                vops=np.asarray(raw_vops, dtype=float),
                bounds=bounds,
                nominal=nominal,
                source="trusted local inference bundle",
            )
        return cls(modes)

    def metadata(self) -> dict[str, Any]:
        """JSON-safe UI metadata; it intentionally contains no training labels."""
        modes: dict[str, Any] = {}
        for name, model in self._modes.items():
            cfg = MODE_CONFIG[name]
            modes[name] = {
                "label_kr": cfg["label_kr"],
                "temperature": cfg["temperature"],
                "metric_kr": cfg["metric_kr"],
                "metric_short_kr": cfg["metric_short_kr"],
                "vops": model.vops.tolist(),
                "bounds": {key: list(pair) for key, pair in model.bounds.items()},
                "reference_coordinates": model.nominal,
                "reference_label": "이 mode 학습 배치의 중앙값 좌표 (공통 물리 nominal 아님)",
                "source": model.source,
            }
        return {
            "app_name": "SRAM Vmin Inverse Studio",
            "app_version": APP_VERSION,
            "z_target": Z_TARGET,
            "v_t0": V_T0,
            "axes": public_axes(),
            "modes": modes,
            "limitations": [
                "표시 Vmin은 Gaussian μ/σ 정의와 이 모델의 전압 격자에서 계산한 surrogate 점예측입니다.",
                "inverse는 다른 여덟 축을 고정한 한 축 조건부 경계를 찾습니다. 9개 원인의 유일한 진단이 아닙니다.",
                "학습 범위 밖의 입력은 외삽 경고가 붙습니다. 최종 sign-off와 실리콘 yield 보장을 대체하지 않습니다.",
                "read와 write는 서로 다른 온도·배치에서 학습됐습니다. combined 비교는 설계 탐색용 예측입니다.",
            ],
        }

    def reference_coordinates(self, mode: str) -> dict[str, float]:
        return dict(self._model(mode).nominal)

    def _model(self, mode: str) -> ModeModel:
        return self._modes[_assert_mode(mode)]

    def _coerce_coordinates(
        self, mode: str, supplied: dict[str, Any] | None,
    ) -> tuple[np.ndarray, dict[str, float], list[str]]:
        """Merge valid optional coordinates with one mode's reference point."""
        model = self._model(mode)
        supplied = supplied or {}
        unknown = set(supplied).difference(DEVICE_COLS)
        if unknown:
            raise DemoInputError(f"unknown process axes: {', '.join(sorted(unknown))}")
        values = dict(model.nominal)
        for axis, raw in supplied.items():
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise DemoInputError(f"{axis} must be a finite number") from exc
            if not math.isfinite(value):
                raise DemoInputError(f"{axis} must be a finite number")
            values[axis] = value
        extrapolated = [
            axis for axis, value in values.items()
            if value < model.bounds[axis][0] or value > model.bounds[axis][1]
        ]
        return np.asarray([values[axis] for axis in DEVICE_COLS], dtype=float), values, extrapolated

    @staticmethod
    def _status_and_value(
        raw_vmin: float, censored: bool, vops: np.ndarray,
    ) -> tuple[VminStatus, float | None]:
        if bool(censored):
            return "below_grid", None
        if not math.isfinite(float(raw_vmin)):
            return "above_grid", None
        value = float(raw_vmin)
        if value < float(vops[0]) or value > float(vops[-1]):
            raise RuntimeError("in-range Vmin interpolation returned an invalid voltage")
        return "in_range", value

    def _predict_rows(
        self, mode: str, rows: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[VminStatus], list[float | None], np.ndarray]:
        """Predict μ, σ, z and Vmin for N device-coordinate rows in one batch."""
        model = self._model(mode)
        rows = np.asarray(rows, dtype=float)
        if rows.ndim != 2 or rows.shape[1] != len(DEVICE_COLS):
            raise ValueError(f"rows must have shape (N, {len(DEVICE_COLS)}), got {rows.shape}")
        n = len(rows)
        query = np.repeat(rows, len(model.vops), axis=0)
        query = np.column_stack((query, np.tile(model.vops, n)))
        mu, sigma = model.surrogate.predict_mean(query)
        mu_grid = mu.reshape(n, len(model.vops))
        sigma_grid = sigma.reshape(n, len(model.vops))
        z_grid = mu_grid / (sigma_grid + 1e-12)
        raw, censored = compute_vmin_from_z(
            z_grid, Z_TARGET, vops=model.vops, return_censored=True,
        )
        statuses: list[VminStatus] = []
        values: list[float | None] = []
        for item, cens in zip(raw, censored):
            status, value = self._status_and_value(float(item), bool(cens), model.vops)
            statuses.append(status)
            values.append(value)
        supply_monotone = np.all(np.diff(z_grid, axis=1) >= -1e-7, axis=1)
        return mu_grid, sigma_grid, z_grid, raw, statuses, values, supply_monotone

    @staticmethod
    def _solver_value(raw: float, status: VminStatus, vops: np.ndarray) -> float:
        """Bounded numeric surrogate for scan/bracket tests only, never displayed."""
        if status == "below_grid":
            return float(vops[0] - 0.1)
        if status == "above_grid":
            return float(vops[-1] + 0.1)
        return float(raw)

    def predict(self, mode: str, supplied: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return one transparent forward query, including grid/censoring status."""
        name = _assert_mode(mode)
        model = self._model(name)
        row, values, extrapolated = self._coerce_coordinates(name, supplied)
        mu, sigma, z, raw, statuses, vmins, supply_monotone = self._predict_rows(name, row.reshape(1, -1))
        status = statuses[0]
        value = vmins[0]
        return {
            "mode": name,
            "coordinates": values,
            "extrapolated_axes": extrapolated,
            "in_training_box": not extrapolated,
            "vops": model.vops.tolist(),
            "mu_mV": (mu[0] * 1e3).tolist(),
            "sigma_mV": (sigma[0] * 1e3).tolist(),
            "z": z[0].tolist(),
            "supply_monotone_on_grid": bool(supply_monotone[0]),
            "vmin": {
                "status": status,
                "value_V": _to_json_number(value),
                "label": _vmin_label(status, value, model.vops),
                "scored_on_voltage_grid": status == "in_range",
            },
        }

    def solve_axis(
        self,
        mode: str,
        supplied: dict[str, Any] | None,
        axis: str,
        target_vmin: float,
        scan_points: int = 81,
        iterations: int = 32,
    ) -> dict[str, Any]:
        """Find every scan-detected one-axis Vmin boundary in the training box.

        Unlike the paper's narrowly validated vectorised bisection, this GUI
        scans before solving.  It can therefore warn about multiple crossings
        or non-monotonic axis behaviour rather than silently claiming one root.
        A scan cannot mathematically rule out roots between its samples.
        """
        name = _assert_mode(mode)
        model = self._model(name)
        if axis not in AXIS_BY_KEY:
            raise DemoInputError(f"unknown inverse axis {axis!r}")
        try:
            target = float(target_vmin)
        except (TypeError, ValueError) as exc:
            raise DemoInputError("target Vmin must be a finite voltage") from exc
        if not math.isfinite(target):
            raise DemoInputError("target Vmin must be a finite voltage")
        if target < model.vops[0] or target > model.vops[-1]:
            raise DemoInputError(
                f"target Vmin must be within the modeled voltage grid "
                f"[{model.vops[0]:.3f}, {model.vops[-1]:.3f}] V")
        if not 21 <= int(scan_points) <= 401:
            raise DemoInputError("scan_points must be between 21 and 401")
        point, coordinates, extrapolated = self._coerce_coordinates(name, supplied)
        index = DEVICE_COLS.index(axis)
        lo, hi = model.bounds[axis]
        x_values = np.linspace(lo, hi, int(scan_points), dtype=float)
        rows = np.repeat(point.reshape(1, -1), len(x_values), axis=0)
        rows[:, index] = x_values
        _, _, _, raw, statuses, values, supply_monotone = self._predict_rows(name, rows)
        effective = np.asarray(
            [self._solver_value(item, status, model.vops) for item, status in zip(raw, statuses)],
            dtype=float,
        )
        f_values = effective - target
        tol = 1e-8
        candidates: list[tuple[float, float]] = []
        for i in range(len(x_values) - 1):
            left, right = f_values[i], f_values[i + 1]
            if abs(left) <= tol:
                candidates.append((x_values[i], x_values[i]))
            if left * right < 0:
                candidates.append((x_values[i], x_values[i + 1]))
        if abs(f_values[-1]) <= tol:
            candidates.append((x_values[-1], x_values[-1]))

        # Deduplicate a root shared by two adjacent scan intervals.
        unique: list[tuple[float, float]] = []
        for candidate in candidates:
            center = (candidate[0] + candidate[1]) / 2
            if not any(abs(center - (seen[0] + seen[1]) / 2) < 1e-9 for seen in unique):
                unique.append(candidate)

        def evaluate_value(x: float) -> tuple[float, VminStatus, float | None]:
            one = point.copy()
            one[index] = x
            _, _, _, one_raw, one_status, one_values, _ = self._predict_rows(name, one.reshape(1, -1))
            status = one_status[0]
            return self._solver_value(float(one_raw[0]), status, model.vops), status, one_values[0]

        solutions: list[dict[str, Any]] = []
        for left, right in unique:
            if left == right:
                root = left
            else:
                low, high = left, right
                flow, _, _ = evaluate_value(low)
                flow -= target
                for _ in range(iterations):
                    mid = (low + high) / 2
                    fmid, _, _ = evaluate_value(mid)
                    fmid -= target
                    if abs(fmid) <= tol:
                        low = high = mid
                        break
                    if flow * fmid <= 0:
                        high = mid
                    else:
                        low, flow = mid, fmid
                root = (low + high) / 2
            solved, status, shown_value = evaluate_value(root)
            solutions.append({
                "axis_value": float(root),
                "status": status,
                "vmin_V": _to_json_number(shown_value),
                "vmin_label": _vmin_label(status, shown_value, model.vops),
                "residual_mV": _to_json_number((solved - target) * 1e3),
            })

        direction: str
        diffs = np.diff(effective)
        if np.all(diffs >= -1e-8):
            direction = "nondecreasing_on_scan"
        elif np.all(diffs <= 1e-8):
            direction = "nonincreasing_on_scan"
        else:
            direction = "nonmonotonic_on_scan"
        status = "root_found" if len(solutions) == 1 else (
            "multiple_roots" if len(solutions) > 1 else "no_root_in_box"
        )
        return {
            "mode": name,
            "axis": axis,
            "axis_label": AXIS_BY_KEY[axis].label_kr,
            "target_vmin_V": target,
            "coordinates_fixed": coordinates,
            "extrapolated_axes": extrapolated,
            "axis_bounds": [lo, hi],
            "scan": {
                "axis_values": x_values.tolist(),
                "vmin_values_V": [_to_json_number(item) for item in values],
                "vmin_statuses": statuses,
                "supply_monotone": supply_monotone.tolist(),
                "axis_direction": direction,
                "points": int(scan_points),
            },
            "status": status,
            "solutions": solutions,
            "caveats": [
                "해는 다른 8개 축을 고정한 조건부 설계 경계입니다. 원인을 유일하게 복원한 결과가 아닙니다.",
                "scan은 여러 교차를 찾기 위한 검사입니다. scan 간격 사이의 매우 좁은 교차까지 보장하지는 않습니다.",
                "이분 탐색의 작은 수치 잔차는 surrogate 자체의 검증 오차와 다릅니다.",
            ],
        }

    def plane(
        self,
        mode: str,
        supplied: dict[str, Any] | None,
        x_axis: str = "cn",
        y_axis: str = "pu",
        points: int = 31,
    ) -> dict[str, Any]:
        """Return a bounded two-axis Vmin plane for a presentation heat map."""
        name = _assert_mode(mode)
        model = self._model(name)
        if x_axis not in AXIS_BY_KEY or y_axis not in AXIS_BY_KEY or x_axis == y_axis:
            raise DemoInputError("choose two different valid process axes for the plane")
        if not 15 <= int(points) <= 61:
            raise DemoInputError("plane points must be between 15 and 61")
        point, coordinates, extrapolated = self._coerce_coordinates(name, supplied)
        xs = np.linspace(*model.bounds[x_axis], int(points))
        ys = np.linspace(*model.bounds[y_axis], int(points))
        xx, yy = np.meshgrid(xs, ys)
        rows = np.repeat(point.reshape(1, -1), xx.size, axis=0)
        rows[:, DEVICE_COLS.index(x_axis)] = xx.ravel()
        rows[:, DEVICE_COLS.index(y_axis)] = yy.ravel()
        _, _, _, _, statuses, values, supply_monotone = self._predict_rows(name, rows)
        return {
            "mode": name,
            "x_axis": x_axis,
            "y_axis": y_axis,
            "x_values": xs.tolist(),
            "y_values": ys.tolist(),
            "vmin_values_V": [_to_json_number(item) for item in values],
            "vmin_statuses": statuses,
            "supply_monotone_count": int(np.sum(supply_monotone)),
            "points_per_axis": int(points),
            "coordinates_fixed": coordinates,
            "extrapolated_axes": extrapolated,
            "caveat": "이 평면은 선택한 두 축만 움직이고 나머지 7축은 표시된 reference 좌표에 고정한 단면입니다.",
        }

    def paper_scenario(self) -> dict[str, Any]:
        """Expose the stored paper scenario without recomputing or re-labelling it."""
        path = RESULTS_DIR / "scenario.json"
        with path.open(encoding="utf-8") as handle:
            result = json.load(handle)
        return {
            "scenario": result,
            "caveats": [
                "0.575 V는 0.625 V 사양보다 50 mV 낮은 목표이지 baseline 예측 Vmin보다 50 mV 낮은 값이 아닙니다.",
                "PMOS local-σ 단독 case는 floor에서 목표보다 약 0.58 mV 높습니다. 모델 오차보다 작은 차이라 물리적 불가능으로 단정하면 안 됩니다.",
                "개선 비율은 surrogate 좌표의 변화량입니다. 공정 비용·면적·지연의 최소 비용 해가 아닙니다.",
            ],
        }

    def sensitivity(self) -> dict[str, Any]:
        """Return stored Sobol results with their actual analysis scope attached."""
        path = RESULTS_DIR / "sensitivity.json"
        with path.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        key = "z(0.625V)"
        total = raw["sobol"]["ST"][key]
        first = raw["sobol"]["S1"][key]
        rows = [
            {
                "axis": axis,
                "label_kr": AXIS_BY_KEY[axis].label_kr,
                "S1": float(first[axis]),
                "ST": float(total[axis]),
            }
            for axis in DEVICE_COLS
        ]
        rows.sort(key=lambda row: row["ST"], reverse=True)
        return {
            "mode": "read",
            "output": key,
            "temperature": raw.get("temp_C"),
            "rows": rows,
            "scope": [
                "분석 출력은 raw margin이나 Vmin이 아니라 0.625 V에서의 z=μ/σ입니다.",
                "각 입력축은 학습 상자 안에서 독립 균등분포로 샘플했습니다. foundry 생산분포의 측정값이 아닙니다.",
                "ST는 그 축이 참여하는 상호작용까지 포함하므로 ST 막대를 합쳐 100% pie chart로 만들면 안 됩니다.",
            ],
        }
