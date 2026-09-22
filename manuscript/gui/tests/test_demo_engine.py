"""Focused, dependency-light tests for presentation-tool safety boundaries."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import torch

GUI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = GUI_ROOT.parents[1]
sys.path.insert(0, str(GUI_ROOT))
sys.path.insert(0, str(REPO_ROOT / "python"))

from demo_config import AXES, DEVICE_COLS
from demo_engine import DemoEngine, DemoInputError
from src.surrogate import Surrogate


class DemoEnginePureTests(unittest.TestCase):
    def test_axis_metadata_matches_model_column_order(self) -> None:
        self.assertEqual(tuple(axis.key for axis in AXES), DEVICE_COLS)
        self.assertEqual(AXES[1].key, "sk")
        self.assertIn("PG", AXES[1].detailed_kr)

    def test_censoring_is_not_reported_as_a_numeric_vmin(self) -> None:
        vops = np.array([0.4, 0.5, 0.6])
        status, value = DemoEngine._status_and_value(0.35, True, vops)
        self.assertEqual(status, "below_grid")
        self.assertIsNone(value)
        status, value = DemoEngine._status_and_value(float("nan"), False, vops)
        self.assertEqual(status, "above_grid")
        self.assertIsNone(value)

    def test_out_of_grid_solver_values_are_internal_only(self) -> None:
        vops = np.array([0.4, 0.5, 0.6])
        self.assertLess(DemoEngine._solver_value(0.35, "below_grid", vops), vops[0])
        self.assertGreater(DemoEngine._solver_value(float("nan"), "above_grid", vops), vops[-1])

    def test_regular_checkpoint_without_targets_fails_with_a_clear_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "regular_checkpoint.pt"
            torch.save({
                "sigma_model": Surrogate.SIGMA_MODEL,
                "x_train": np.zeros((1, 2)),
            }, path)
            with self.assertRaisesRegex(ValueError, "does not contain y_train"):
                Surrogate.load(path)

    @unittest.skipUnless(
        os.environ.get("RUN_SRAM_VMIN_DEMO_INTEGRATION") == "1",
        "set RUN_SRAM_VMIN_DEMO_INTEGRATION=1 after creating a local inference bundle",
    )
    def test_local_bundle_smoke(self) -> None:
        engine = DemoEngine.from_bundle()
        report = engine.predict("read")
        self.assertEqual(report["vmin"]["status"], "in_range")
        inverse = engine.solve_axis("read", None, "cn", 0.625, scan_points=41)
        self.assertEqual(inverse["status"], "root_found")
        with self.assertRaises(DemoInputError):
            engine.solve_axis("read", None, "cn", 0.9)


if __name__ == "__main__":
    unittest.main()
