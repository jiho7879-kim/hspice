"""config.toml, resolved once. Paths in the file are relative to service/."""
from __future__ import annotations

import tomllib
from pathlib import Path

SERVICE = Path(__file__).resolve().parent.parent
ROOT = SERVICE.parent
CFG = tomllib.loads((SERVICE / "config.toml").read_text(encoding="utf-8"))


def path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (SERVICE / p).resolve()


AXES: list[dict] = CFG["axes"]
AXIS_KEYS = [a["key"] for a in AXES]
AXIS = {a["key"]: a for a in AXES}
CORNERS: dict[str, dict[str, float]] = CFG["corners"]
LIMITING: dict[str, str] = CFG["limiting"]
MODES: dict[str, dict] = CFG["model"]["modes"]
DEFAULTS: dict = CFG["defaults"]
RESULTS = path(CFG["model"]["results_dir"])
RUNS = path(CFG["service"]["runs_dir"])
SCENARIOS = path(CFG["service"]["scenarios_dir"])
