# AGENTS.md — Python tests/

Unit tests for the GP surrogate + physics pipeline.

---

## Test inventory (10 files, 1760 LOC)

| Test file | LOC | Modules tested |
|-----------|-----|----------------|
| test_pipeline.py | ~200 | End-to-end: Surrogate → physics_layer → contour |
| test_models.py | ~100 | ExactGPModel, AdditiveGPModel shapes & training |
| test_physics.py | ~300 | PhysicsConstrainedSurrogate + all 3 penalties |
| test_condition_gen.py | ~250 | Frozen core cross-validation + deck numbering |
| test_noise_aware.py | ~100 | Noise-aware GP + save/load |
| test_manual_entry.py | ~150 | Hand-entry CSV parsing |
| test_parser_qc.py | ~200 | MC QC + npz roundtrip |
| test_primesim_io.py | ~300 | Wrapped .mt0 + Vtrip min-join |
| test_zeff.py | ~200 | Lobe-resolved effective Z |
| test_ngspice.py | ~350 | ngspice integration test |

---

## Testing patterns

### Dual-runner (every test file)
```bash
python -m pytest tests/test_foo.py -v      # pytest
python tests/test_foo.py                    # direct execution
```
Each file has `if __name__ == "__main__":` block that calls all test functions.

### Self-bootstrapping imports
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

### No pytest infrastructure
- No `conftest.py`, no fixtures, no parametrize
- All parameterization is manual (loops, for-over-cases)
- Plain `assert` statements throughout

### Analytic ground truth only
No real HSPICE data in tests. All use synthetic/analytic models:
- `analytic_snmr()` for physics tests
- `rng.normal()` samples for QC tests
- `tempfile.TemporaryDirectory` for I/O tests

### Deterministic seeds
Each test function creates `rng = np.random.default_rng(SEED)` with unique seed.

---

## Coverage gaps

| Module | Coverage | Gap |
|--------|----------|-----|
| utils.py | Partial | StandardScaler, sample_common_n_pu not directly tested |
| surrogate.py | Partial | evaluate(), run_ablation() not tested |
| physics_layer.py | Partial | PhysicsLayer (torch Module) not tested |
| contour.py | Partial | hausdorff_distance, area_overlap not tested |
| hspice_io.py | ~40% | parse_mt0_file, render_deck, generate_decks not tested |
| harness.py | None | Zero tests for workflow state management |

---

## Anti-patterns

- **Do NOT delete failing tests** to make suite pass
- **Do NOT add real HSPICE data dependencies** to test suite
- **Do NOT mock** — use synthetic data instead
