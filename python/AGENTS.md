# AGENTS.md — Python ML Pipeline

**Primary codebase** for SRAM Vmin estimation via GP surrogate + differentiable physics layer.

**CWD requirement**: All scripts must be run from `python/` directory.

---

## Structure

```
python/
├── src/           # Core modules (13 files, 4241 LOC)
├── scripts/       # Entrypoints (28 files, ~7000 LOC)
├── tests/         # Unit tests (10 files, 1760 LOC)
├── data/          # .npz datasets + .xlsx (gitignore real data)
├── templates/     # HSPICE netlists + PDK model cards + manual-entry CSVs
├── results/       # Output figures, ablation results, checkpoints
├── docs/          # Python-side documentation
├── pyproject.toml # Project metadata + deps
└── requirements.txt # Runtime deps (includes openpyxl)
```

---

## Where to look

| Task | Location | Notes |
|------|----------|-------|
| Add new constants | `src/utils.py` | Central hub — 8/12 modules import from here |
| GP model changes | `src/models.py` | ExactGPModel, AdditiveGPModel |
| GP training loop | `src/surrogate.py` | Surrogate class |
| Physics constraints | `src/physics.py` | PhysicsConstrainedSurrogate |
| Vmin computation | `src/physics_layer.py` | Differentiable Vmin layer |
| Data loading/saving | `src/data.py` | .npz format, stratified splits |
| HSPICE I/O | `src/hspice_io.py` | Deck gen, .mt0 parsing, manual entry |
| PrimeSim I/O | `src/primesim_io.py` | Wrap-safe parser, Vtrip split |
| Condition generation | `src/condition_gen.py` | FROZEN CORE — portable |
| Workflow state | `src/harness.py` | CLI for workflow_state.json |

---

## Dependency graph (4-tier DAG, no cycles)

```
Tier 0 (leaf): utils.py, primesim_io.py, condition_gen.py, inhouse_deck_gen.py, harness.py
Tier 1: models.py, data.py, physics_layer.py
Tier 2: surrogate.py, contour.py, hspice_io.py
Tier 3: physics.py
```

---

## Conventions

- All 12 `src/` modules use `from __future__ import annotations` (strict typing)
- Lazy scipy imports (inside functions, not at module level)
- No `__all__` or `__version__` defined anywhere
- `_to_tensor()` duplicated in surrogate.py and physics.py (refactoring candidate)

---

## Anti-patterns

- **Do NOT run scripts from wrong directory** — CWD must be `python/`
- **Do NOT skip the `sys.path.insert(0, ...)` boilerplate**
- **Do NOT rename** `VOPS`, `Z_FIXED`, `VOP_COL`, `CN_COL`, `SK_COL` — imported everywhere
- **Do NOT change the data shape convention** (X: N×d, y: N×2)
