# AGENTS.md — Python src/ modules

Core modules implementing GP surrogate + differentiable physics layer.

---

## Module inventory (13 files, 4241 LOC)

| Module | Lines | Purpose |
|--------|-------|---------|
| `utils.py` | 409 | Constants, StandardScaler, sampling, lobe-resolved Z |
| `models.py` | 107 | ExactGPModel, AdditiveGPModel |
| `surrogate.py` | 318 | Surrogate class (train/predict/save/load) |
| `data.py` | 145 | Dataset build/save/load, stratified splits |
| `physics_layer.py` | 409 | Differentiable Vmin computation |
| `physics.py` | 532 | PhysicsConstrainedSurrogate |
| `contour.py` | 270 | PVTA contour extraction |
| `hspice_io.py` | 991 | Deck gen, .mt0 parsing, manual entry QC |
| `primesim_io.py` | 485 | PrimeSim wrapped .mt0 parser |
| `condition_gen.py` | 254 | FROZEN CORE portable condition generator |
| `harness.py` | 233 | Workflow state management |
| `inhouse_deck_gen.py` | 359 | In-house deck gen adapter |
| `__init__.py` | 1 | Empty init |

---

## Complexity hotspots

1. **hspice_io.py (991 lines)** — 5 concerns in 1 file: deck gen, .mt0 parsing, MC statistics, manual entry ingestion, transcription QC. **Prime refactoring candidate.**
2. **physics.py (532 lines)** — Core innovation module. Custom training loop with 3 constraint terms. `_train_gp()` is 99 lines with scheduling, checkpointing, NaN-guarding.
3. **primesim_io.py (485 lines)** — Wrap-safe parser + Vtrip left/right join. Approaching refactoring threshold.

---

## Key patterns

### GP posterior gradient (L_mono trick)
```python
gp.eval()
gp.prediction_strategy = None  # force recompute Cholesky
output = gp(probe_points)       # posterior, not prior
```
**`gp.forward()` returns the prior** — never use for posterior gradients.

### Data shape convention
```
X: (N, d) where d ≥ 3
   Core 3D: [cn, pu, Vop]
   Extended: [..., W, σL_mult, σG, μ_mobility_mult, Temp]
y: (N, 2) = [mu_SNMR, sigma_SNMR]
```

### Column layout
- `VOP_COL` = 2 (Stage A), 3 (Stage B)
- PU is LAST device column: `pu_col_for(vop_col)`
- Device-first: `[cn, (sk...), pu, Vop, (operating dims)]`

---

## Anti-patterns

- **Do NOT rename** constants in utils.py — imported by 8/12 modules
- **Do NOT change data shape** — every module depends on it
- **Do NOT hardcode Vop column** — use `VOP_COL` or `vop_col_for()`
- **Do NOT use `gp.forward()`** for posterior gradients
