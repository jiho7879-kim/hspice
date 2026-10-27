"""Lever solvers on a black-box binding function g(U) -> Vmin.

U is (n, k): per-lever usage in [0, 1] (1 = the lever's full max_change). Every
solver assumes g is non-increasing in each usage. Callers check that on a sweep
and report it, because bisection on a non-monotone curve returns *a* root, not
necessarily the smallest one. The same functions run on posterior quantiles for
robust answers -- they only ever see g.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

G = Callable[[np.ndarray], np.ndarray]
ITERS = 30          # 2^-30 of the lever range -- far below anything the GP resolves


def bisect(g1: Callable[[np.ndarray], np.ndarray], target: float,
           lo: np.ndarray, hi: np.ndarray, iters: int = ITERS) -> np.ndarray:
    """Smallest x in [lo, hi] with g1(x) <= target, vectorised over rows.
    The caller guarantees g1(hi) <= target."""
    lo, hi = np.array(lo, float), np.array(hi, float)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        ok = g1(mid) <= target
        hi, lo = np.where(ok, mid, hi), np.where(ok, lo, mid)
    return hi


def _along(g: G, base: np.ndarray, j: int) -> Callable[[np.ndarray], np.ndarray]:
    def g1(x: np.ndarray) -> np.ndarray:
        U = np.repeat(base[None], np.size(x), axis=0)
        U[:, j] = x
        return g(U)
    return g1


def single(g: G, k: int, j: int, target: float, iters: int = ITERS) -> tuple[np.ndarray, bool]:
    """Lever j alone."""
    return path(g, np.eye(k)[j], target, iters)


def path(g: G, direction: np.ndarray, target: float, iters: int = ITERS) -> tuple[np.ndarray, bool]:
    """Smallest t in [0, 1] with g(t * direction) <= target."""
    d = np.asarray(direction, float)

    def g1(t: np.ndarray) -> np.ndarray:
        return g(np.atleast_1d(t)[:, None] * d[None])

    if g1(np.array([0.0]))[0] <= target:
        return np.zeros_like(d), True
    if g1(np.array([1.0]))[0] > target:
        return d.copy(), False
    return float(bisect(g1, target, [0.0], [1.0], iters)[0]) * d, True


def balanced(g: G, k: int, target: float, iters: int = ITERS) -> tuple[np.ndarray, bool]:
    """Every lever at the same fraction of its own ceiling (minimax burden)."""
    return path(g, np.ones(k), target, iters)


def priority(g: G, k: int, order: list[int], target: float,
             iters: int = ITERS) -> tuple[np.ndarray, bool, list[np.ndarray]]:
    """Spend levers in order: each one up to its ceiling, the last only as far as needed."""
    u, steps = np.zeros(k), []
    for j in order:
        if g(u[None])[0] <= target:
            break
        full = u.copy()
        full[j] = 1.0
        if g(full[None])[0] <= target:
            u[j] = float(bisect(_along(g, u, j), target, [0.0], [1.0], iters)[0])
        else:
            u[j] = 1.0
        steps.append(u.copy())
    return u, bool(g(u[None])[0] <= target), steps


def min_cost(g: G, k: int, weights: np.ndarray, target: float,
             budget: int = 400, iters: int = 14) -> tuple[np.ndarray, bool, int]:
    """Cheapest usage (sum of w_j u_j) that meets target.

    Grid over k-1 levers, bisect the remaining one; every lever takes a turn as
    the bisected one. Resolution is the grid step, returned so callers can say it.
    14 bisection steps (2^-14 of the range) because every step is a batched GP call
    over the whole grid -- 30 steps made a 3-lever run take ~45 s.
    """
    w = np.asarray(weights, float)
    if k == 1:
        u, ok = single(g, 1, 0, target)
        return u, ok, 0
    res = int(max(3, min(41, round(budget ** (1.0 / (k - 1))))))
    axis = np.linspace(0.0, 1.0, res)
    best: tuple[np.ndarray, float] | None = None
    for j in range(k):
        others = [i for i in range(k) if i != j]
        grid = np.array(np.meshgrid(*[axis] * (k - 1), indexing="ij")).reshape(k - 1, -1).T
        U = np.zeros((len(grid), k))
        U[:, others] = grid
        top = U.copy()
        top[:, j] = 1.0
        U = U[g(top) <= target]
        if not len(U):
            continue
        done = g(U) <= target                       # already passes with u_j = 0

        def g1(x: np.ndarray, U=U, j=j) -> np.ndarray:
            V = U.copy()
            V[:, j] = x
            return g(V)

        x = bisect(g1, target, np.zeros(len(U)), np.ones(len(U)), iters)
        U[:, j] = np.where(done, 0.0, x)
        cost = U @ w
        i = int(np.argmin(cost))
        if best is None or cost[i] < best[1]:
            best = (U[i].copy(), float(cost[i]))
    if best is None:
        return np.ones(k), False, res
    return best[0], True, res


def monotone(values: np.ndarray, tol: float = 1e-6) -> bool:
    """Non-increasing within tol (V); inf counts as larger than everything."""
    v = np.where(np.isinf(values), 1e9, values)
    return bool(np.all(np.diff(v) <= tol))
