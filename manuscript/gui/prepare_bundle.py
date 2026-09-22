"""Create a self-contained, local-only Windows inference bundle.

The original GP checkpoint carries model weights, input training coordinates and
scalers but intentionally not the training targets required by GPyTorch's
ExactGP reconstruction.  This script adds only the canonical *training split*
targets and presentation metadata to a copy of each checkpoint.  It never
changes the source checkpoints or XLSX files.

Run from the repository root:
    .venv/bin/python manuscript/gui/prepare_bundle.py --output manuscript/gui/demo_bundle

The output includes proprietary model/training assets and is ignored by git.
Do not upload it or include it in a public release without approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

import numpy as np
import torch

from demo_config import (
    APP_NAME,
    APP_VERSION,
    BUNDLE_SCHEMA,
    DEFAULT_BUNDLE_DIR,
    DEVICE_COLS,
    MODE_CONFIG,
    RESULTS_DIR,
    V_T0,
    Z_TARGET,
)
from demo_engine import canonical_training_data


def sha256(path: Path) -> str:
    """Return a file digest without exposing its contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bundle_metadata(mode: str, data: Any, source_digest: str) -> dict[str, Any]:
    """Build small, non-label metadata that the UI needs at runtime."""
    return {
        "schema": BUNDLE_SCHEMA,
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "mode": mode,
        "device_cols": list(DEVICE_COLS),
        "vops": data.vops.tolist(),
        "bounds": {axis: list(pair) for axis, pair in data.bounds.items()},
        "nominal": data.nominal,
        "z_target": Z_TARGET,
        "v_t0": V_T0,
        "source_checkpoint_sha256": source_digest,
        "contains_training_targets": True,
        "disclosure": (
            "Trusted local inference bundle. Contains proprietary model weights, "
            "training coordinates and training targets needed to reconstruct an ExactGP."
        ),
    }


def prepare_one(mode: str, output_dir: Path, overwrite: bool) -> dict[str, Any]:
    """Create one atomically written bundle and return public metadata."""
    data = canonical_training_data(mode)
    checkpoint = RESULTS_DIR / str(MODE_CONFIG[mode]["checkpoint_file"])
    if not checkpoint.is_file():
        raise FileNotFoundError(f"missing source checkpoint: {checkpoint}")
    destination = output_dir / str(MODE_CONFIG[mode]["bundle_file"])
    if destination.exists() and not overwrite:
        raise FileExistsError(f"{destination} exists; pass --overwrite to replace it")

    state = torch.load(checkpoint, map_location="cpu", weights_only=False)
    saved_x = state.get("x_train")
    if saved_x is None:
        raise ValueError(f"{checkpoint} does not contain the saved training inputs")
    saved_x = np.asarray(saved_x, dtype=np.float64)
    if saved_x.shape != data.x_train.shape or not np.allclose(saved_x, data.x_train):
        raise ValueError(
            f"canonical {mode} training split does not match {checkpoint}; "
            "refuse to make an ambiguous inference bundle")
    state["y_train"] = data.y_train
    state["demo_bundle"] = bundle_metadata(mode, data, sha256(checkpoint))

    with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        torch.save(state, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return state["demo_bundle"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_BUNDLE_DIR,
                        help="local output folder; it is ignored by git")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace existing local bundle files")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    metadata = [prepare_one(mode, output, args.overwrite) for mode in ("read", "write")]
    (output / "bundle_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(f"Created trusted local bundles in {output}")
    for item in metadata:
        print(f"  {item['mode']}: {item['source_checkpoint_sha256'][:12]}…")
    print("No source checkpoint or XLSX file was modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
