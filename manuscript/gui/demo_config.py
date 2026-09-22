"""Shared configuration for the local SRAM Vmin presentation tool.

This module intentionally contains no model loading or data I/O.  It is safe to
use from the Windows launcher, the inference-bundle creator, and unit tests.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

APP_NAME = "SRAM Vmin Inverse Studio"
APP_VERSION = "0.1.0"
BUNDLE_SCHEMA = 1
SEED = 42
TRAIN_TEST_FRACTION = 0.15
Z_TARGET = 6.3984
V_T0 = 0.625

THIS_DIR = Path(__file__).resolve().parent
MANUSCRIPT_ROOT = THIS_DIR.parent
REPO_ROOT = MANUSCRIPT_ROOT.parent
PYTHON_ROOT = REPO_ROOT / "python"
DEFAULT_BUNDLE_DIR = THIS_DIR / "demo_bundle"
STATIC_DIR = THIS_DIR / "static"
RESULTS_DIR = MANUSCRIPT_ROOT / "results"

DEVICE_COLS = (
    "cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk",
)


@dataclass(frozen=True)
class AxisDefinition:
    """Human-facing definition of one model input axis."""

    key: str
    label_kr: str
    symbol: str
    unit: str
    short_kr: str
    detailed_kr: str
    kind: str

    def public(self) -> dict[str, str]:
        return asdict(self)


AXES = (
    AxisDefinition(
        "cn", "NMOS 공통 Vth shift", "ΔVth,N", "mV",
        "PG·PD NMOS를 함께 빠르게/느리게 만드는 전역 shift",
        "양의 값은 NMOS Vth를 높여 두 NMOS를 느리게 하는 convention이다.",
        "threshold",
    ),
    AxisDefinition(
        "sk", "PG–PD NMOS Vth skew", "ΔVth,skew", "mV",
        "pass-gate와 pull-down 사이의 상대 Vth 불균형",
        "N/P skew가 아니다. PG에는 cn+sk, PD에는 cn−sk가 적용된다.",
        "threshold",
    ),
    AxisDefinition(
        "pu", "PMOS Vth shift", "ΔVth,P", "mV",
        "pull-up PMOS의 전역 속도 변화",
        "양의 값은 |Vth,P|를 키워 PMOS를 느리게 하는 convention이다.",
        "threshold",
    ),
    AxisDefinition(
        "lpu", "PMOS local-σ multiplier", "kσP", "×",
        "PMOS cell-to-cell mismatch 산포의 배율",
        "이름의 l은 이 도구에서 직접적인 gate length(nm)를 뜻하지 않는다.",
        "mismatch",
    ),
    AxisDefinition(
        "l_com", "NMOS 공통 local-σ multiplier", "kσN", "×",
        "PG·PD NMOS의 cell-to-cell mismatch 산포 공통 배율",
        "값이 커지면 local mismatch 산포가 커지는 모델 좌표다.",
        "mismatch",
    ),
    AxisDefinition(
        "l_sk", "PG–PD NMOS local-σ skew", "ΔkσN", "×",
        "PG와 PD의 mismatch 산포 차이",
        "두 NMOS 역할 간 local mismatch 배율의 불균형을 뜻한다.",
        "mismatch",
    ),
    AxisDefinition(
        "mpu", "PMOS mobility multiplier", "kμP", "×",
        "PMOS mobility/drive 배율",
        "PDK compact-model 파라미터의 추상화된 공정 좌표다.",
        "mobility",
    ),
    AxisDefinition(
        "m_com", "NMOS 공통 mobility multiplier", "kμN", "×",
        "PG·PD NMOS mobility/drive 공통 배율",
        "값의 실제 제조 비용이나 geometry 변환은 이 모델이 제공하지 않는다.",
        "mobility",
    ),
    AxisDefinition(
        "m_sk", "PG–PD NMOS mobility skew", "ΔkμN", "×",
        "PG와 PD mobility 배율 차이",
        "두 NMOS 역할의 상대 구동 능력 불균형을 표현한다.",
        "mobility",
    ),
)
AXIS_BY_KEY = {axis.key: axis for axis in AXES}

MODE_CONFIG: dict[str, dict[str, Any]] = {
    "read": {
        "label_kr": "읽기 / SNMR",
        "temperature": "125 °C",
        "avg_col": "snmr_avg",
        "std_col": "snmr_std",
        "bundle_file": "read_inference_bundle.pt",
        "checkpoint_file": "surrogate_vb.pth",
        "metric_kr": "SNMR (static noise margin)",
        "metric_short_kr": "읽기 안정성 마진",
    },
    "write": {
        "label_kr": "쓰기 / Vtrip",
        "temperature": "−40 °C",
        "avg_col": "vtrip_avg",
        "std_col": "vtrip_std",
        "bundle_file": "write_inference_bundle.pt",
        "checkpoint_file": "surrogate_vb_write.pth",
        "metric_kr": "Vtrip",
        "metric_short_kr": "쓰기 전환 마진 지표",
    },
}

# Exactly the corners and mode limits used by the paper scenario.  They are not
# a claim of a global nine-dimensional worst case.
CORNER_SHIFTS = {
    "FFG": (-36.42, -44.32),
    "FSG": (-29.16, 38.64),
    "SFG": (31.63, -36.76),
    "SSG": (36.30, 44.80),
}
LIMITING_CORNERS = {"read": "FSG", "write": "SFG"}


def public_axes() -> list[dict[str, str]]:
    """Return JSON-safe axis descriptions in model-column order."""
    return [axis.public() for axis in AXES]
