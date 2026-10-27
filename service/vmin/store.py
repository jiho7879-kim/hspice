"""Run directories: runs/<id>/ = spec.json + result.json + figures (png, pdf) + tables (csv).

spec.json is the complete, defaults-filled spec, so `main.py run runs/<id>/spec.json`
reproduces the run exactly.
"""
from __future__ import annotations

import csv
import json
import math
import re
import secrets
import time
from pathlib import Path
from typing import Any

import numpy as np

from .config import RUNS

PNG_DPI = 220
ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-z_]+-[0-9a-f]{4}$")


def clean(x: Any) -> Any:
    """JSON-safe copy: numpy -> python, NaN/inf -> None (browsers reject bare NaN)."""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, np.ndarray):
        return clean(x.tolist())
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(float(x)) else None
    return x


def new_id(kind: str) -> str:
    return time.strftime("%Y%m%d-%H%M%S") + f"-{kind}-{secrets.token_hex(2)}"


def run_dir(run_id: str) -> Path:
    if not ID_RE.match(run_id):
        raise FileNotFoundError(run_id)
    return RUNS / run_id


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(clean(obj), ensure_ascii=False, indent=2), encoding="utf-8")


def save(run_id: str, spec: dict, res, header: dict) -> dict:
    import matplotlib.pyplot as plt

    d = run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    write_json(d / "spec.json", spec)
    figs = []
    for name, title, fig in res.figures:
        fig.savefig(d / f"{name}.png", dpi=PNG_DPI, bbox_inches="tight")
        fig.savefig(d / f"{name}.pdf", bbox_inches="tight")
        plt.close(fig)
        figs.append(dict(name=name, title=title, png=f"{name}.png", pdf=f"{name}.pdf"))
    tables = []
    for t in res.tables:
        with open(d / f"{t['name']}.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(t["columns"])
            w.writerows(clean(t["rows"]))
        tables.append(dict(name=t["name"], title=t["title"], columns=t["columns"], csv=f"{t['name']}.csv",
                           rows=t["rows"] if t["inline"] else None, n_rows=len(t["rows"])))
    result = dict(header, status="done", summary=res.summary, tables=tables, figures=figs,
                  notes=res.notes, data=res.data, verification=res.verification)
    write_json(d / "result.json", result)
    return clean(result)


def save_error(run_id: str, spec: dict, header: dict, message: str) -> dict:
    d = run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    write_json(d / "spec.json", spec)
    result = dict(header, status="error", error=message)
    write_json(d / "result.json", result)
    return clean(result)


def load(run_id: str) -> dict:
    return json.loads((run_dir(run_id) / "result.json").read_text(encoding="utf-8"))


def listing(limit: int = 300) -> list[dict]:
    out = []
    if not RUNS.is_dir():
        return out
    for d in sorted(RUNS.iterdir(), reverse=True)[:limit]:
        f = d / "result.json"
        if not f.is_file():
            continue
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        ver = r.get("verification") or []
        out.append(dict(id=r.get("id"), kind=r.get("kind"), title=r.get("title"), created=r.get("created"),
                        status=r.get("status"), elapsed_s=r.get("elapsed_s"),
                        headline=(r.get("summary") or [{}])[0].get("value", r.get("error", "")),
                        verified=f"{sum(v['ok'] for v in ver)}/{len(ver)}" if ver else ""))
    return out


def file_path(run_id: str, name: str) -> Path:
    if "/" in name or "\\" in name or name.startswith("."):
        raise FileNotFoundError(name)
    p = run_dir(run_id) / name
    if not p.is_file():
        raise FileNotFoundError(name)
    return p
