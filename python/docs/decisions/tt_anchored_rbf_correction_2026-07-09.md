# TT-anchored RBF Correction (2026-07-09)

## Problem

Per-corner bias correction via RBF interpolation used 4 corner points
(FFG, FSG, SFG, SSG) to interpolate residual(mu) and residual(sigma)
across the (common_N, PU) space.  This caused the TT region to be
distorted because all 4 corner residuals have the **same sign**
(original GP systematically under-predicts mu at every corner).

**Quantified impact (84 TT-area training points):**
- mu RMSE: 0.47 mV (original GP) → 12.87 mV (4-corner RBF) = **27× worse**
- TT Vmin shift: −4.6 mV (artifact)
- Mean mu bias injected: +10.9 mV

**Root cause:** Linear RBF with 4 points of the same sign creates a
smooth plane that assigns positive residuals everywhere inside the
convex hull, including the origin where the GP is already accurate.

## Solution

Add TT (cn=0, pu=0) as a 5th anchor point with residual = 0 for both
mu and sigma.  The RBF interpolator now trains on 5 points:

```
rbf_points = [(FFG_cn, FFG_pu), (FSG_cn, FSG_pu),
              (SFG_cn, SFG_pu), (SSG_cn, SSG_pu),
              (0.0, 0.0)]                        # ← TT anchor
```

## Verification

| Metric | Original GP | RBF4 (4-corner) | RBF5 (TT-anchored) |
|--------|:-----------:|:----------------:|:------------------:|
| TT-area mu RMSE | 0.47 mV | 12.87 mV | **0.47 mV** |
| TT-area sigma RMSE | 0.15 mV | 0.41 mV | **0.15 mV** |
| TT Vmin shift | — | −4.6 mV | **0.0 mV** |
| FFG Vmin err | −0.5 mV | — | **0.0 mV** |
| FSG Vmin err | +23.1 mV | — | **0.0 mV** |
| SSG Vmin err | +6.0 mV | — | **0.0 mV** |

RBF5 passes through all corner residuals exactly (it is an
interpolator), so corner correction quality is identical to RBF4
at the 4 corner points.  The TT anchor only changes the surface shape
**between** the corners — it forces the correction to decay to zero
at the origin.

## Files Changed

- `python/scripts/corner_retrain_pvta_contour.py` — RBF points extended
  from 4 to 5; residual arrays extended with `+ [0.0]`.
