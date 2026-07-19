# Toy Validation Results — Stages 1-3

**Date**: 2026-07-02 (updated)
**Session**: VWL → WLUD ratio refactoring + physics-constrained Stage 3

---

## Changes Made (2026-07-02)

### VWL → WLUD Ratio Refactoring
- **Problem**: Absolute Vwl voltage causes non-physical GP behavior (Vwl can exceed Vop, no bounded range)
- **Solution**: 4th input dimension changed from absolute Vwl (V) to **WLUD ratio (Vwl/Vop)**, always bounded in [0, 1]
- **Files affected**: 11 files — `src/utils.py`, `src/physics.py`, `src/physics_layer.py`, `src/contour.py`, `src/hspice_io.py`, `scripts/demo_4d.py`, `scripts/demo_assist.py`, `scripts/debug_assist.py`, `scripts/gen_hspice.py`, `tests/test_physics.py`
- **Backward compat**: `VWL_COL = WLUD_COL`, `N_VWL = N_WLUD` aliases retained

### WLUD Range Narrowing (user feedback)
- **Problem**: WLUD ratio below 0.9 (i.e. >10% underdrive) never used in practice
- **Solution**: `WLUD_FACTORS` changed from `[0.50, 0.60, 0.70, 0.80, 0.90, 1.00]` to `[0.90, 0.92, 0.94, 0.96, 0.98, 1.00]`
- All `wlud_lo` param values updated accordingly

### Physics-Constrained Stage 3
- **Problem**: Stage 3 used plain `Surrogate` from `src/surrogate.py`, ignoring physics constraints
- **Fix**: `PhysicsConstrainedSurrogate.fit()` now derives `n_extra` from `X_train.shape` and passes it to `generate_corner_anchor_data()` and `generate_probe_points()`
- `_format_lengthscales()` and `get_lengthscales()` fixed for 4D+ AdditiveGPModel (kernel group split)
- `demo_assist.py` switched to `PhysicsConstrainedSurrogate(use_mono=False, use_boundary=True, use_pelgrom=False)`

### Stage 3 Crashes Fixed
1. **CG non-convergence** (1000 iter warnings): Resolved by only using boundary augmentation (no mono/pelgrom). CG warnings still appear for mu GP but training completes.
2. **`_format_lengthscales` crash**: `ls_vop.item()` failed because 4D AdditiveGPModel `kernels[0]` has 2D lengthscale (Vop + WLUD), not 1D. Rewrote to handle variable-dim kernel groups.

---

## Results (2026-07-02, WLUD ratio [0.90, 1.00])

### Stage 1 — 3D Baseline ✅
| Metric | Value |
|--------|-------|
| mu RMSE | 0.00206 |
| sigma RMSE | 0.00053 |
| True Vmin range | [0.350, 0.896] |
| Pred Vmin range | [0.350, 0.900] |
| Contour pts (Vmin=0.6V) | 99 / 99 |

### Stage 2 — 4D + WLUD ratio ✅
| Metric | Value | Threshold | Verdict |
|--------|-------|-----------|---------|
| mu RMSE | 0.00237 | ≤ 0.015 | ✅ |
| WLUD monotonicity | 100.0% | ≥ 95% | ✅ |
| Max assist benefit | 0.104 V | ≥ 0.02 V | ✅ (narrowed range) |

Plots: `results/toy/stage2_4d_vwl/contour_wlud_sweep.png`, `assist_benefit.png`

### Stage 3 — Inverse Assist (physics-constrained, boundary only) ❌ NO-GO
| Metric | Value | Threshold | Verdict |
|--------|-------|-----------|---------|
| mu RMSE | 0.03989 | — | ⚠️ elevated (4D boundary aug) |
| WLUD RMSE | 0.0277 | ≤ 0.05 | ✅ |
| Feasibility agreement | 75.7% | ≥ 90% | ❌ |
| Vmin achieved RMSE | 0.1560 V | ≤ 0.02 V | ❌ |

**Root cause**: mu RMSE 0.03989 is too high (plain Surrogate gave ~0.002). Boundary augmentation with `generate_corner_anchor_data(n_extra=1)` adds 144 points but the corner anchor grid at the 4 extreme corners may not provide useful augmentation for the interior WLUD prediction task. The physics-constrained GP is over-constrained for this small-data regime.

**Trial & Error Log**:
1. `use_mono=True, use_boundary=True, use_pelgrom=True` → CG failed to converge, training extremely slow → killed
2. `use_mono=False, use_boundary=True, use_pelgrom=False` → training succeeds but `_format_lengthscales` crashes on 4D AdditiveGPModel → fixed
3. After fix → mu RMSE 0.03989, Vmin RMSE 0.156 V → NO-GO

---

## Open Issues
- PhysicsConstrainedSurrogate with 4D boundary augmentation degrades mu accuracy vs plain Surrogate. Need investigation: is the corner anchor grid (only 4 extreme corners) actually harmful for interpolation problems?
- Possible fix: use only 3D corner anchors with WLUD=0.0 filling, or disable boundary augmentation for 4D

Plots: `results/toy/stage3_inverse_assist/assist_map.png`, `assist_accuracy.png`, `achieved_vmin_hist.png`
