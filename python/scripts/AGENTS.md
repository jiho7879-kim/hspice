# AGENTS.md — Python scripts/

Entrypoints for every pipeline stage. 28 scripts total.

---

## Entry point pattern

All 26 non-`__init__` scripts include:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```
**CWD must be `python/`** for all scripts.

### Guarded scripts (14 with `if __name__ == "__main__"` + `def main()`)
- ablation.py, budget_pareto.py, demo_gradient_inversion.py, diagnostics.py
- gen_condition_sheet.py, gen_hspice.py, gen_inhouse_condition_sheet.py, gen_ngspice_data.py
- gen_paper_figures.py, legacy_sobol_regen.py, stage1_ngspice.py
- stageB_leakage_check.py, test_ngspice.py, train.py

### Unguarded scripts (12 — run on import)
- demo.py, demo_4d.py, demo_assist.py, debug_assist.py
- corner_verification.py, corner_retrain_test_sep.py, corner_retrain_pvta_contour.py
- validate_assist_sweep.py, stage4_real_data.py
- stageB_real_data.py, stageB_snmr_analysis.py
- stageC_readwrite.py, stageC_skew_cooptimization.py

---

## Script inventory by stage

### Core pipeline
| Script | Lines | Purpose |
|--------|-------|---------|
| demo.py | 253 | Full GP demo: analytic data → train → contour |
| train.py | 66 | Train GP surrogate from .npz |
| ablation.py | 494 | Physics-constrained ablation (5 configs) |
| diagnostics.py | 373 | Multi-panel error diagnostics |
| budget_pareto.py | 461 | Budget vs accuracy Pareto |

### Deck generation
| Script | Lines | Purpose |
|--------|-------|---------|
| gen_hspice.py | 68 | Generate HSPICE decks |
| gen_condition_sheet.py | 105 | Generate pre-filled condition sheet |
| gen_inhouse_condition_sheet.py | 142 | Generate in-house condition sheet |
| gen_ngspice_data.py | 243 | Generate ngspice simulation data |

### Real data & validation
| Script | Lines | Purpose |
|--------|-------|---------|
| stage4_real_data.py | 269 | Real HSPICE data GP (Stage A) |
| stageB_real_data.py | ~300 | Stage B 4D GP |
| stageC_readwrite.py | ~400 | Stage C read+write Vmin |
| stageC_skew_cooptimization.py | ~300 | Skew co-optimization |
| corner_verification.py | 478 | Corner accuracy verification |
| corner_retrain_pvta_contour.py | ~300 | Per-corner residual correction |

### Specialized
| Script | Lines | Purpose |
|--------|-------|---------|
| demo_4d.py | ~200 | 4D GP demo (+WLUD) |
| demo_assist.py | 396 | Stage 3 assist demo |
| demo_gradient_inversion.py | 333 | Autograd inversion |
| stage1_ngspice.py | 369 | GP on ngspice data |
| test_ngspice.py | 354 | ngspice integration test |
| gen_paper_figures.py | 664 | 8 paper figures |

---

## Conventions

- Scripts with `__main__` guard follow: `def main()` → `if __name__ == "__main__": main()`
- Unguarded scripts run entire pipeline at module load time
- No `console_scripts` in pyproject.toml — nothing is pip-installable
- `python -m python.scripts.<name>` will NOT work (no `__main__.py`)

---

## Anti-patterns

- **Do NOT run scripts from wrong directory** — CWD must be `python/`
- **Do NOT skip the `sys.path.insert(0, ...)` boilerplate**
- **Do NOT use `matplotlib.use("Agg")` for interactive sessions**
