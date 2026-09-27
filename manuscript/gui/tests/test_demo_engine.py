"""Focused, dependency-light tests for presentation-tool safety boundaries."""
from __future__ import annotations

import os
import json
from unittest.mock import Mock
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
from demo_engine import DemoEngine, DemoInputError, ModeModel
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


class JointQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = {"read": [], "write": []}
        self.engine = DemoEngine({name: ModeModel(
            name, Mock(), np.array([0.4 if name == "read" else 0.45, 0.6, 0.8]),
            {axis: ((0., 2.) if name == "read" else (0.5, 1.5)) for axis in DEVICE_COLS},
            {axis: (1. if name == "read" else 1.4) for axis in DEVICE_COLS}, "synthetic",
        ) for name in ("read", "write")})
        self.engine._predict_rows = self.predict_rows

    def predict_rows(self, mode, rows):
        self.rows[mode].append(rows.copy())
        n = len(rows)
        values = 0.5 + 0.1 * (rows[:, 0] if mode == "read" else rows[:, 2])
        grid = np.tile([4., 6., 8.], (n, 1))
        return grid, np.ones_like(grid), grid, values, ["in_range"] * n, values.tolist(), np.ones(n, dtype=bool)

    def test_plane_shares_rows_intersection_and_fixed_coordinates(self) -> None:
        result = self.engine.joint_plane({"sk": 0.2}, target_vmin=0.6, points=15)
        read, write = (np.concatenate(self.rows[mode]) for mode in ("read", "write"))
        np.testing.assert_array_equal(read, write)
        self.assertEqual(result["bounds"]["cn"], (0.5, 1.5))
        self.assertEqual(result["x_values"][0], 0.5)
        self.assertEqual(result["x_values"][-1], 1.5)
        np.testing.assert_array_equal(read[:, 1], np.full(225, 0.2))
        np.testing.assert_array_equal(read[:, 3:], np.ones((225, 6)))
        self.assertEqual(result["modes"]["write"]["extrapolated_axes"], ["sk"])
        expected = (read[:, 0] <= 1.) & (read[:, 2] <= 1.)
        np.testing.assert_array_equal(result["joint_feasible"], expected)
        json.dumps(result, allow_nan=False)

    def test_combinations_bounded_deterministic_and_fixed(self) -> None:
        for axes in (["cn", "pu"], ["cn", "pu", "sk"], list(DEVICE_COLS)):
            with self.subTest(axes=axes):
                first = self.engine.solve_combination(None, axes, 0.65, budget=125)
                second = self.engine.solve_combination(None, axes, 0.65, budget=125)
                self.assertEqual(first, second)
                self.assertLessEqual(first["sampled_count"], 125)
                self.assertLessEqual(len(first["candidates"]), 12)
                distances = [row["normalized_distance"] for row in first["candidates"]]
                self.assertEqual(distances, sorted(distances))
                self.assertTrue(first["provenance"]["baseline_in_shared_bounds"])
                self.assertTrue(first["provenance"]["baseline_included"])
                self.assertEqual(distances[0], 0.0)
                for row in first["candidates"]:
                    for axis in DEVICE_COLS:
                        if axis not in axes:
                            self.assertEqual(row["coordinates"][axis], 1.)
                json.dumps(first, allow_nan=False)

    def test_near_grid_baseline_is_evaluated_exactly(self) -> None:
        result = self.engine.solve_combination(
            {"cn": 0.999999, "pu": 1.0}, ["cn", "pu"], 0.65, budget=9,
        )
        first = result["candidates"][0]
        self.assertTrue(result["provenance"]["baseline_included"])
        self.assertEqual(first["normalized_distance"], 0.0)
        self.assertEqual(first["coordinates"]["cn"], 0.999999)
        self.assertEqual(first["coordinates"]["pu"], 1.0)

    def test_censored_invalid_and_nonmonotone_never_certified(self) -> None:
        def predict(mode, rows):
            n = len(rows)
            grid = np.tile([4., 6., 8.], (n, 1))
            grid[3, 1] = np.nan
            statuses = ["below_grid", "above_grid"] + ["in_range"] * (n - 2)
            values = [None, None] + [0.55] * (n - 2)
            monotone = np.ones(n, dtype=bool)
            monotone[2] = False
            return grid, np.ones_like(grid), grid, np.full(n, -999.), statuses, values, monotone
        self.engine._predict_rows = predict
        result = self.engine.solve_combination(None, ["cn", "pu"], 0.6, budget=9)
        self.assertEqual(result["feasible_count"], 6)
        self.assertEqual(result["unknown_count"], 3)
        self.assertNotIn("-999", json.dumps(result, allow_nan=False))
        self.assertTrue(any(row["modes"]["read"]["status"] == "below_grid" for row in result["candidates"]))

    def test_maximum_budget_uses_bounded_prediction_chunks(self) -> None:
        result = self.engine.solve_combination(None, list(DEVICE_COLS), 0.6, budget=4096)
        self.assertEqual(result["sampled_count"], 4096)
        for mode in ("read", "write"):
            self.assertEqual(sum(len(rows) for rows in self.rows[mode]), 4096)
            self.assertTrue(all(len(rows) <= 128 for rows in self.rows[mode]))
        np.testing.assert_array_equal(np.concatenate(self.rows["read"]), np.concatenate(self.rows["write"]))

    def test_invalid_arguments_rejected_before_prediction(self) -> None:
        for axes in (None, [], ["cn"], ["cn", "cn"], ["cn", "bad"], ["cn", []]):
            with self.assertRaises(DemoInputError):
                self.engine.solve_combination(None, axes, 0.6)
        for target in (None, float("nan"), 0.4, 0.9):
            with self.assertRaises(DemoInputError):
                self.engine.joint_plane(None, target_vmin=target)
        for budget in (7, 4097, 12.5, True, "125"):
            with self.assertRaises(DemoInputError):
                self.engine.solve_combination(None, ["cn", "pu"], 0.6, budget)
        for points in (14, 62, 15.5, True):
            with self.assertRaises(DemoInputError):
                self.engine.joint_plane(None, target_vmin=0.6, points=points)
        self.engine._modes["write"].bounds["cn"] = (3., 4.)
        with self.assertRaises(DemoInputError):
            self.engine.solve_combination(None, ["cn", "pu"], 0.6)
        self.assertEqual(self.rows, {"read": [], "write": []})


if __name__ == "__main__":
    unittest.main()
