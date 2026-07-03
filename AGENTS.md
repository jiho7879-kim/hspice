# AGENTS.md — HSPICE SRAM Vmin Estimation

**Domain**: SRAM Vmin estimation via GP surrogate + differentiable physics layer.
Two parallel stacks: **HSPICE circuit simulation** (real PDK) and **Python toy project** (PyTorch/GPyTorch surrogate modeling).

---

## Session continuation rules (MANDATORY)

These rules ensure continuity across session resets. Follow them in every session:

1. **Document discussions in `.md` files** — Any architectural discussion, design decision, tradeoff analysis, or rationale behind a choice must be recorded in a dedicated `.md` file. The decision process itself should be visible (options considered, why chosen/rejected).

2. **Record trial & error** — Failed approaches, bugs encountered, root cause analysis, and their fixes must be logged. This prevents repeating the same mistakes in future sessions.

3. **Write phase/checkpoint summaries** — After each major phase or checkpoint, produce a consolidated summary `.md` file that connects back to the project's goal. This creates a chain of reasoning from project objective → what was done → what was learned.

These rules exist because the project involves two parallel domains (HSPICE + Python ML), and session context does not persist across resets. The `.md` files are the only permanent record.

---

## Ambiguity Gate (MANDATORY — 모든 Action의 전제 조건)

> **원칙**: 어떤 action(토론, 결정, 설계, 코딩)이든 **ambiguity score가 threshold 이하로 검증되기 전까지 실행하지 않는다.**
> 모호한 상태에서 시작한 작업은 방향을 잘못 잡아 재작업 비용이 2-3배 발생할 수 있다.

**Ambiguity Score = S + I + O + M + C (0-10)**

| Domain | 항목 | 0점 (명확) | 1점 (일부 모호) | 2점 (완전 모호) |
|--------|------|-----------|----------------|----------------|
| **S**cope | "무엇을 할지" | 구체적 목표 명시 | 방향은 있으나 세부 미정 | 무슨 작업인지 모름 |
| **I**nput | 입력 데이터/파라미터 | 정확히 명시 | 일부만 명시 | 전혀 명시 안 됨 |
| **O**utput | 기대 결과물 | 형태 + 기준 명확 | 형태만 알겠음 | 무엇이 나와야 할지 모름 |
| **M**ethod | 접근 방법 | 방법 결정됨 | 방향만 있음 | 방법을 모름 |
| **C**onstraint | 제약 조건/범위 밖 | 명확히 문서화 | 일부만 파악 | 전혀 모름 |

**Threshold**: Score > 5 → **Action 금지**. 질문을 던져서 score ≤ 5가 될 때까지 반복.

**Loop 규칙**:
1. Score 계산 → 0-5면 proceed, 6-10이면 질문
2. 모호한 dimension 위주로 1-3개 질문 → user 응답 대기
3. 재평가 → score ≤ 5 또는 user가 "그냥 진행" 명시적으로 허용할 때까지 반복
4. 동일 질문 3회 이상 반복 시 best guess로 proceed (assumptions 문서화)

**절대 하지 말 것**:
- Score > 5인데 "네, 알겠습니다. 진행하겠습니다."
- 질문 없이 모호한 요청을 자기 멋대로 해석해서 action
- Ambiguity 체크를 건너뛰고 바로 구현

**참조**: `AGENT.md §2 Ambiguity Gate` — full scoring detail, 질문 템플릿, agent별 적용 방식

---

## Agent orchestration

Refer to **`AGENT.md`** (project root) for agent switching guide — which agent (Sisyphus, Atlas, Prometheus, Hephaestus, Oracle, etc.) handles which task type, and how to invoke them.

Quick reference:
- **Atlas**: Python ML implementation (GP, physics layer, contour, ablation)
- **Prometheus**: Planning & architecture (DOE, sampling, paper outline)
- **Hephaestus**: HSPICE simulation (deck gen, PDK, parsing)
- **Oracle**: Hard debugging & architecture consultation (read-only)

---

## Repository layout

```
root/
├── python/                  # Python GP surrogate + physics pipeline (primary)
│   ├── src/                 # Core: utils, models, data, surrogate, physics, physics_layer, contour, hspice_io
│   ├── scripts/             # Entrypoints: demo, ablation, diagnostics, train, gen_hspice
│   ├── tests/               # Unit tests: test_models, test_physics, test_pipeline
│   ├── data/                # .npz datasets (demo_analytic, dataset_synth)
│   ├── templates/           # HSPICE netlist template (sram_cell_pvta.sp)
│   ├── results/             # Output figures, diagnostic plots, ablation results
│   │   └── ablation/        # Physics-constrained ablation study results
│   ├── pyproject.toml
│   └── requirements.txt
├── hspice/                  # HSPICE domain
│   ├── docs/                # Reference guides (convergence, PDK, naming, etc.)
│   ├── templates/           # HSPICE template files
│   └── decks/               # Generated simulation decks
├── pdk/                     # Process design kit data
│   └── sky130/              # SKY130 PDK-calibrated contour analysis
├── docs/                    # Project documentation
│   └── decisions/           # Architecture decision records
├── papers/                  # Research papers and references
├── array_params_template.inc # HSPICE SRAM mini-array parameter template
└── tail_extraction_demo.sp  # HSPICE 6-sigma tail extraction demo
```

**No sub-AGENTS.md needed** — the project is small and flat.

---

## Python toy project

### Entrypoints (run from `python/`)

| Command | What it does |
|---------|-------------|
| `python scripts/demo.py` | Full GP demo (generate data → train → contour plot) |
| `python scripts/ablation.py` | Physics-constrained GP ablation study |
| `python scripts/diagnostics.py` | Multi-panel error diagnostics |
| `python scripts/train.py --data ./data/dataset.npz` | Train GP surrogate |
| `python scripts/train.py --data ./data/dataset.npz --ablation` | Train + ablation sweep |
| `python scripts/gen_hspice.py --validation` | Generate 6 validation HSPICE decks |
| `python scripts/gen_hspice.py --n_cond 200` | Generate 1200 HSPICE decks for farm |
| `python tests/test_pipeline.py` | End-to-end test with synthetic data |
| `python tests/test_models.py` | Unit tests for GP model definitions |
| `python tests/test_physics.py` | Unit tests for physics-constrained surrogate |

### Data shape convention (hard requirement)

```
X: (N, d) where d ≥ 3
   Core 3D:   [common_N_shift (mV), PU_shift (mV), Vop (V)]
   Extended:  [..., W (norm), σL_mult, σG, μ_mobility_mult, Temp (°C)]

y: (N, 2) = [mu_SNMR (V), sigma_SNMR (V)] — non-negotiable.
```

- **Core 3D** (Vop at index 2 = `VOP_COL`) is always required.
- **Extended dims** (indices 3+): add as needed. When absent, code defaults to core 3D.
- **Vop column** is canonically referred to as `VOP_COL` (defined in `src/utils.py`).
  Never hardcode `2` in physics constraint code — always use `VOP_COL`.
- One row per (common_N, PU, Vop, ...) combination. Saved as `.npz` with keys `X`, `y`.

### Shift convention (CRITICAL)

- **positive shift = slower device** for BOTH NMOS and PMOS
- common_N > 0 → NMOS Vth higher → NMOS slower
- PU > 0 → PMOS |Vth| larger → PMOS slower
- FSG corner: (common_N < 0, PU > 0) = fast N, slow P
- SFG corner: (common_N > 0, PU < 0) = slow N, fast P

### Import pattern (ubiquitous)

Every script that imports from `src/` does this before any local import:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```
**Always use this pattern when writing a new script.** Do not assume `PYTHONPATH`.

Note: `physics.py` (formerly `physics_ablation/src/physics_constrained_surrogate.py`) now lives in `src/` and uses the same `.parent.parent` pattern as other scripts.

### GP model structure

- **mu GP**: `ExactGPModel` — Matern 5/2 + ARD (3D: cn, pu, Vop; auto-adapts to d≥3)
- **sigma GP**: `AdditiveGPModel` — k_Vop(Vop) + k_cnpu(cn, pu) (additive kernel)
- Both independent, trained via `ExactMarginalLogLikelihood` + Adam

Key trick for L_mono (posterior gradient):
```python
gp.eval()
gp.prediction_strategy = None  # force recompute Cholesky with current params
output = gp(probe_points)       # posterior, not prior
```
**Do NOT use `gp.forward()` for posterior gradients** — that returns the prior (ConstantMean, no input dependence).

### Dependencies

Python ≥3.11. Install: `pip install -r requirements.txt`
Core: numpy, scipy, matplotlib, torch≥2.1, gpytorch≥1.11, pandas, seaborn

### Diagnostics & plotting

All scripts use `matplotlib.use("Agg")` before `import matplotlib.pyplot` — **always do this when generating saved figures** (no display backend).

### Physics-constrained ablation

Code lives in `src/physics.py` (class `PhysicsConstrainedSurrogate`).
Entrypoint: `scripts/ablation.py`.
5 configs: baseline → +L_mono → +L_boundary → +Mono+Boundary → All.
Checkpoints saved as `results/ablation/gp_{config}_{mu|sigma}.pth`.
**Key finding (from `docs/decisions/physics_ablation.md`):** L_boundary (corner anchor data augmentation) alone gives 95% of Vmin RMSE improvement.

---

## HSPICE domain

### Running simulations

```bash
hspice64 -i deck.sp -o output_prefix
```

`.mt0` files contain MC measurement results. Parse via `python/src/hspice_io.py` (`parse_mt0_file` function).

### Template system

`sram_cell_pvta.sp` uses `{{ MUSTACHE_VARS }}` rendered by `python/src/hspice_io.py` (`render_deck` function) or `python/scripts/gen_hspice.py`.
Key variables: `COMMON_N_SHIFT`, `PU_SHIFT`, `VOP`, `TEMP`, `MC_RUNS`.

### Mini-array parameters

`array_params_template.inc` is a comprehensive parameter template for SRAM mini-array peripheral simulation.
Usage: copy → `array_params.inc` → fill `<<< USER:` values → `.INCLUDE` in main deck.

### Output files to .gitignore

All `.tr0`, `.sw0`, `.st0`, `.mt0`, `.lis`, `.log`, `.ic0`, `.fsdb`, `.psf`, `.csv`, `.dat` files are gitignored.

---

## What NOT to do

- **Do NOT suppress Python type errors** — all `src/` files use strict typing (`from __future__ import annotations`)
- **Do NOT rename VOPS, Z_FIXED, COMMON_N_MIN, COMMON_N_MAX, VOP_COL** — these are imported by every module from `src.utils`
- **Do NOT change the data shape convention** (X: N×d, y: N×2) — every module depends on it
- **Do NOT hardcode Vop column index as `2`** — use `VOP_COL` from `src.utils` instead
- **Do NOT assume 3D input** — physics constraint code (`generate_probe_points`, `generate_corner_anchor_data`, `_compute_mono_penalty`) must accept variable-dim X via `n_extra` parameter
- **Do NOT use `gp.forward()` for L_mono** — see GP model section above
- **Do NOT run scripts from wrong directory** — all scripts expect CWD = `python/`
- **Do NOT skip the `sys.path.insert(0, ...)` import boilerplate** — each script is self-contained
- **Do NOT use `matplotlib.use("Agg")` if running interactively** — swap to `TkAgg` or remove for notebooks
