"""Solver semantics on closed-form binding functions -- no GP needed.

    .venv/bin/python service/tests/test_solve.py      (pytest also collects it)
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vmin.solve import balanced, bisect, min_cost, priority, single  # noqa: E402

# Vmin = 0.60 - 0.03 u0 - 0.01 u1 - 0.02 u2 : linear, decreasing in every lever
W = np.array([0.03, 0.01, 0.02])


def g(U):
    return 0.60 - np.atleast_2d(U) @ W


def test_bisect_hits_target():
    x = bisect(lambda x: 0.6 - 0.1 * x, 0.55, [0.0], [1.0])
    assert abs(x[0] - 0.5) < 1e-8


def test_single_reachable_and_not():
    u, ok = single(g, 3, 0, 0.58)          # 0.02 / 0.03
    assert ok and abs(u[0] - 2 / 3) < 1e-8 and u[1] == u[2] == 0
    u, ok = single(g, 3, 1, 0.58)          # lever 1 tops out at -0.01
    assert not ok and u[1] == 1.0


def test_single_already_passing():
    u, ok = single(g, 3, 0, 0.61)
    assert ok and not u.any()


def test_priority_fills_in_order():
    u, ok, steps = priority(g, 3, [1, 0, 2], 0.57)   # 0.01 from lever 1, 0.02 from lever 0
    assert ok and u[1] == 1.0 and abs(u[0] - 2 / 3) < 1e-8 and u[2] == 0
    assert len(steps) == 2


def test_priority_unreachable_uses_everything():
    u, ok, _ = priority(g, 3, [0, 1, 2], 0.53)       # needs 0.07 > 0.06 available
    assert not ok and np.all(u == 1.0)


def test_balanced_common_fraction():
    u, ok = balanced(g, 3, 0.57)                     # 0.03 / 0.06
    assert ok and np.allclose(u, 0.5, atol=1e-8)


def test_min_cost_prefers_cheap_effective_lever():
    # equal weights: lever 0 buys the most per unit of usage
    # (min_cost bisects 14 steps, so 2^-14 ~ 6e-5 is its resolution)
    u, ok, res = min_cost(g, 3, np.ones(3), 0.58)
    assert ok and abs(u[0] - 2 / 3) < 1e-4 and u[1] < 1e-9 and u[2] < 1e-9
    # make lever 0 expensive: lever 2 alone (0.02 at full use) is the cheapest way
    u, ok, _ = min_cost(g, 3, np.array([10.0, 1.0, 1.0]), 0.58)
    assert ok and u[0] < 1e-9 and abs(u[2] - 1.0) < 1e-4


if __name__ == "__main__":
    tests = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for f in tests:
        f()
    print(f"{len(tests)} solver tests passed")
