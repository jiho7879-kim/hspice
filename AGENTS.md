# AGENTS.md — HSPICE SRAM Vmin Estimation

**Domain**: SRAM Vmin estimation via GP surrogate + differentiable physics layer.
Two stacks: **HSPICE circuit simulation** (real PDK, ngspice/PrimeSim) and **Python surrogate modeling** (PyTorch/GPyTorch).

**Current phase**: Phase 2 Stage A GO (real HSPICE data gate passed 2026-07-09).
**Active plan**: `docs/plans/phase2_to_paper_plan.md`
**Workflow state**: `docs/workflow_state.json` (managed by `src/harness.py`)

---

## Session continuation rules (MANDATORY)

1. **Document discussions in `.md` files** — architectural discussions, decisions, tradeoffs, rationale → dedicated `.md` file in `docs/decisions/`. Show options considered and why chosen/rejected.
2. **Record trial & error** — failed approaches, bugs, root cause analysis, fixes → log to prevent repeating.
3. **Write phase/checkpoint summaries** — consolidated `.md` linking back to project goal after each major phase.

The `.md` files are the only permanent record. Session context does not persist across resets.

---

## Agent orchestration

See **`AGENT.md`** (project root) for full orchestration guide (ambiguity gate, agent roles, switching patterns). Quick map:

| Task | Agent |
|------|-------|
| Python ML code | Atlas |
| Experiment planning | Prometheus |
| HSPICE / PDK | Hephaestus |
| Hard debugging | Oracle |
| Ambiguous request | Metis |
| Plan review | Momus |

---

## Repository layout

```
root/
├── python/                  # GP surrogate + physics pipeline (PRIMARY codebase)
│   ├── src/                 # Core modules (13 files)
│   ├── scripts/             # Entrypoints (20 files — see entrypoints table)
│   ├── tests/               # Unit tests (10 files)
│   ├── data/                # .npz datasets + .xlsx (gitignore real data)
│   ├── templates/           # HSPICE netlists + PDK model cards + manual-entry CSVs
│   ├── results/             # Output figures, ablation results, checkpoints
│   └── docs/                # Python-side documentation
├── hspice/                  # HSPICE domain
│   ├── docs/                # 14 reference guides (convergence, PDK, naming, etc.)
│   └── raw/                 # Raw HSPICE output metadata
├── bin/                     # ngspice executables (Windows)
├── pdk/sky130/              # SKY130 PDK-calibrated contour analysis
├── docs/                    # Project documentation
│   ├── decisions/           # Architecture decision records (CRITICAL — read first)
│   └── plans/               # Active phase plans
├── papers/                  # paper_en.md, paper_kr.md
├── AGENT.md                 # Agent orchestration guide (ambiguity gate, roles)
├── array_params_template.inc # HSPICE SRAM mini-array parameter template
└── tail_extraction_demo.sp  # HSPICE 6-sigma tail extraction demo
```

---

## Critical conventions (an agent WILL get these wrong without help)

### Run directory

**All Python scripts expect CWD = `python/`.** Run from there:
```bash
cd python && python scripts/demo.py
```

### Import pattern (ubiquitous)

Every script uses this before any `src.` import:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```
Do NOT assume `PYTHONPATH`. Each script is self-contained.

### Data shape (hard requirement — every module depends on it)

```
X: (N, d) where d ≥ 3
   Core 3D:   [common_N_shift (mV), PU_shift (mV), Vop (V)]
   Extended:  [..., W (norm), σL_mult, σG, μ_mobility_mult, Temp (°C)]
y: (N, 2) = [mu_SNMR (V), sigma_SNMR (V)]
```

- Vop column = `VOP_COL` (defined in `src/utils.py`, currently 2). **Never hardcode `2`** — use `VOP_COL` or `vop_col_for(n_device)`.
- PU is the LAST device column: use `pu_col_for(vop_col)`.
- Column layout is device-first: `[cn, (sk...), pu, Vop, (operating dims)]`.
- Stages: A=3D(cn,pu), B=4D(cn,sk,pu), D=9D(cn,sk,pu,lpu,lpg,lpd,mpu,mpg,mpd).

### Shift convention (CRITICAL)

**Positive shift = slower device** for both NMOS and PMOS.
- common_N > 0 → NMOS Vth higher → NMOS slower
- PU > 0 → PMOS |Vth| larger → PMOS slower
- FSG = (cn < 0, pu > 0) = fast N, slow P — SNMR worst corner
- SFG = (cn > 0, pu < 0) = slow N, fast P — Vtrip worst corner

### Z_TARGET

**Z_FIXED = 6.50** (256 Mb @ 99% Poisson yield). Changed from legacy 6.0.
Use `derive_z_target(mb=..., y_target=...)` for different array specs. Absolute Vmin shifts ~+25 mV vs old Z=6.0; contour shapes unchanged.

### matplotlib backend

All figure-generating scripts: `matplotlib.use("Agg")` BEFORE `import matplotlib.pyplot`. Remove or swap to `TkAgg` for interactive use.

---

## Python src/ modules

| Module | Purpose |
|--------|---------|
| `utils.py` | Constants (`VOPS`, `Z_FIXED`, `VOP_COL`, bounds), `StandardScaler`, stratified sampling, `bvn_cdf`/`z_eff_from_lobes` (lobe-resolved Z) |
| `models.py` | `ExactGPModel` (mu: Matern 5/2 + ARD), `AdditiveGPModel` (sigma: additive kernel). Auto-adapts to d ≥ 3. |
| `surrogate.py` | `Surrogate` class — train/predict/save/load with auto-standardization |
| `data.py` | `build_dataset`, `save_intermediate`, `load_intermediate`, `stratified_train_test_split`, noise-aware save/load |
| `physics_layer.py` | `compute_vmin_from_z`, `compute_vmin_on_grid`, `gradient_check`, `estimate_required_assist` |
| `physics.py` | `PhysicsConstrainedSurrogate` — L_mono, L_boundary, L_pelgrom constraints |
| `contour.py` | `extract_contour` — PVTA contour extraction + Hausdorff distance |
| `hspice_io.py` | Deck generation (Mustache), .mt0 parsing, histogram QC, manual XLSX/CSV parsing |
| `primesim_io.py` | PrimeSim .mt0 parsing — handles auto-wrapped rows and Vtrip left/right split |
| `condition_gen.py` | **Portable** condition generator (zero project imports). Frozen core contract for in-house use. |
| `harness.py` | Workflow state management via `docs/workflow_state.json` |
| `inhouse_deck_gen.py` | In-house deck generation adapter |

### GP posterior gradient (L_mono trick)

```python
gp.eval()
gp.prediction_strategy = None  # force recompute Cholesky with current params
output = gp(probe_points)       # posterior, not prior
```
**`gp.forward()` returns the prior** (ConstantMean, no input dependence). Never use it for posterior gradients.

---

## Python scripts (run from `python/`)

### Core pipeline
| Command | What it does |
|---------|-------------|
| `python scripts/demo.py` | Full GP demo: analytic data → train → contour plot |
| `python scripts/train.py --data ./data/dataset.npz` | Train GP surrogate |
| `python scripts/ablation.py` | Physics-constrained GP ablation study (5 configs) |
| `python scripts/diagnostics.py` | Multi-panel error diagnostics |
| `python scripts/budget_pareto.py --smoke` | Budget vs accuracy Pareto (~1 min) |
| `python scripts/budget_pareto.py --full` | Paper-quality Pareto run |

### Deck generation & HSPICE integration
| Command | What it does |
|---------|-------------|
| `python scripts/gen_hspice.py --n_cond 200` | Generate HSPICE decks (Stage 1, 3D) |
| `python scripts/gen_hspice.py --validation` | Generate 6 validation decks (TT only) |
| `python scripts/gen_condition_sheet.py` | Generate pre-filled condition sheet for in-house transcription |
| `python scripts/gen_ngspice_data.py` | Generate ngspice simulation data |

### Real data & validation
| Command | What it does |
|---------|-------------|
| `python scripts/stage4_real_data.py` | Real HSPICE data GP training + validation |
| `python scripts/corner_retrain_pvta_contour.py` | Per-corner residual recalibration |
| `python scripts/corner_retrain_test_sep.py` | Separated corner retrain test |
| `python scripts/corner_verification.py` | Corner accuracy verification |
| `python scripts/validate_assist_sweep.py` | Assist-active inverse validation |
| `python scripts/demo_gradient_inversion.py` | x=(cn,pu,WLUD) autograd inversion demo |

### Specialized
| Command | What it does |
|---------|-------------|
| `python scripts/demo_4d.py` | 4D GP demo (+WLUD) |
| `python scripts/stage1_ngspice.py` | GP on ngspice butterfly data |
| `python scripts/test_ngspice.py` | ngspice integration test |
| `python scripts/debug_assist.py` | Debug assist-active pipeline |
| `python scripts/demo_assist.py` | Stage 3 assist demo |

### Tests (run from `python/`)
```bash
python -m pytest tests/ -v          # all tests
python -m pytest tests/test_models.py -v  # single file
```
10 test files: test_pipeline, test_models, test_physics, test_condition_gen, test_manual_entry, test_noise_aware, test_parser_qc, test_primesim_io, test_zeff, test_ngspice.

---

## HSPICE domain

### Running simulations
```bash
hspice64 -i deck.sp -o output_prefix     # Synopsys HSPICE
ngspice.exe deck.sp                       # ngspice (bin/ngspice.exe on Windows)
```

### .mt0 parsing
- **Standard HSPICE**: `hspice_io.parse_mt0_file()` — histogram QC, bootstrap SEM
- **PrimeSim (in-house, auto-wrapped rows)**: `primesim_io.py` — reads all numeric tokens flat, reshapes by column count. Handles Vtrip left/right split across `*a0.mt0` / `*a1.mt0`.

### Template system
`sram_cell_pvta.sp` uses `{{ MUSTACHE_VARS }}` rendered by `hspice_io.render_deck()` or `gen_hspice.py`.
Key variables: `COMMON_N_SHIFT`, `PU_SHIFT`, `VOP`, `TEMP`, `MC_RUNS`.

### condition_gen.py (PORTABLE — FROZEN CORE)

This file has **zero project imports** (only numpy). It is the single source of truth for condition generation shared between our local environment and the in-house fab.

**FROZEN CORE** (DO NOT MODIFY): `generate_conditions`, `_unit_samples`, `_quadrant_cnpu`, `deck_number`, `iter_decks`.
**SITE ADAPTER** (modifiable): deck template/paths/sim call.

Contract: `method="rng"` (numpy PCG64, version-stable) ensures identical conditions from `(stage, n_cond, seed, metric, method)` on both sides. Tests: `test_condition_gen.py`.

### Mini-array parameters
`array_params_template.inc`: copy → `array_params.inc` → fill `<<< USER:` values → `.INCLUDE` in main deck.

---

## Dependencies

Python ≥ 3.11. Install: `pip install -r requirements.txt` (includes `openpyxl` not in pyproject.toml).

Core: numpy, scipy, matplotlib, torch≥2.1, gpytorch≥1.11, pandas, seaborn, openpyxl

---

## What NOT to do

- **Do NOT suppress Python type errors** — all `src/` files use `from __future__ import annotations` with strict typing
- **Do NOT rename** `VOPS`, `Z_FIXED`, `COMMON_N_MIN`, `COMMON_N_MAX`, `VOP_COL`, `CN_COL`, `SK_COL` — imported everywhere from `src.utils`
- **Do NOT change the data shape convention** (X: N×d, y: N×2)
- **Do NOT hardcode Vop column index as `2`** — use `VOP_COL` or `vop_col_for()`
- **Do NOT assume 3D input** — physics code accepts variable-dim X via `n_extra` parameter
- **Do NOT use `gp.forward()` for posterior gradients** — returns the prior, not the posterior
- **Do NOT run scripts from wrong directory** — CWD must be `python/`
- **Do NOT skip the `sys.path.insert(0, ...)` boilerplate**
- **Do NOT modify condition_gen.py FROZEN CORE** — breaks in-house reproducibility contract
- **Do NOT use `matplotlib.use("Agg")` for interactive sessions** — swap to `TkAgg` or remove
- **Do NOT commit** `python/data/hspice_real*.xlsx`, `*.tr0`, `*.mt0`, `*.lis`, `*.log` — all gitignored
