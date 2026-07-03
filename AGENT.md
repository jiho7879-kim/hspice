# AGENT.md — SRAM Vmin Agent Orchestration Guide

> **목적**: Project 목적(planning → implementation → review)에 따라 agent를 전환하는 가이드.
> **적용 대상**: Sisyphus (orchestrator)가 subagent를 선택할 때 참조.
> **관련 파일**: `~/.config/opencode/oh-my-openagent.json` (agent 정의)

---

## 1. Agent Inventory

| Agent | Model | Role | Mode |
|-------|-------|------|------|
| **Sisyphus** | `opencode/big-pickle` | **Orchestrator** — task decomposition, delegation, verification | primary |
| **Sisyphus-Junior** | `opencode/big-pickle` | **Task Executor** — focused implementation, no delegation | subagent |
| **Atlas** | `opencode/big-pickle` | **Python ML Implementation** — GP surrogate, physics layer, contour | subagent |
| **Prometheus** | `opencode/qwen3.6-plus-free` | **Planning & Architecture** — DOE, ablation, paper outline | subagent |
| **Hephaestus** | `opencode/big-pickle` | **HSPICE & PDK Simulation** — deck gen, parsing, validation | subagent |
| **Oracle** | `opencode/qwen3.6-plus-free` | **High-IQ Consultation** — debugging, architecture, review | subagent |
| **Metis** | `opencode/big-pickle` | **Pre-Planning Analysis** — ambiguity resolution, scope clarification | subagent |
| **Momus** | `ollama.qwen3.5:4b` | **Plan Critic** — evaluate plans for clarity & completeness | subagent |
| **Explore** | `ollama.qwen3.5:4b` | **Codebase Search** — contextual grep, pattern discovery | subagent |
| **Librarian** | `ollama.qwen3.5:4b` | **External Reference** — docs, OSS examples, web search | subagent |

---

## 2. Ambiguity Gate — 모든 Action의 전제 조건

> **원칙**: 토론, 결정, 코딩 등 **어떤 action이든 ambiguity score가 threshold 이하로 떨어질 때까지 실행하지 않는다.**
> 모호한 상태에서 action을 시작하면 방향을 잘못 잡아 재작업 비용이 더 크다.

### 2.1 Ambiguity Scoring System

요청이 들어오면 **5개 dimension** 각각을 0-2점으로 평가한다:

| Dim | 항목 | 0점 | 1점 | 2점 |
|-----|------|-----|-----|-----|
| **S** | **Scope (범위)** | "무엇을 할지"가 구체적임 | 대략적인 방향은 알겠음 | "뭘 원하는지"를 모르겠음 |
| **I** | **Input (입력)** | 입력 데이터/파라미터가 명시됨 | 일부는 명시, 일부는 추정 필요 | 입력이 전혀 명시되지 않음 |
| **O** | **Output (출력)** | 기대 결과물이 명확함 | 결과물의 형태는 알겠으나 기준이 모호 | "뭐가 나와야 하는지" 모름 |
| **M** | **Method (방법)** | 사용할 방법/알고리즘이 정해짐 | 방법의 방향은 있으나 세부는 미정 | 어떻게 할지 전혀 감이 안 옴 |
| **C** | **Constraint (제약)** | 하지 말아야 할 것, 범위 밖이 명확 | 일부 제약은 알겠으나 누락 있음 | 제약 조건을 전혀 모름 |

**Total Score = S + I + O + M + C (0-10)**

| Score | 상태 | Action |
|:-----:|------|--------|
| **0-3** | ✅ **Clear** | 바로 진행. assumptions 명시만 하고 proceed |
| **4-5** | ⚠️ **Low ambiguity** | 가정(assumptions)을 명시하고 user 확인 후 proceed |
| **6-7** | 🔶 **Moderate** | **질문 필요**. 모호한 dimension 위주로 1-3개 질문 |
| **8-10** | 🔴 **High ambiguity** | **Action 금지**. Iterative Q&A로 score를 낮출 때까지 대기 |

### 2.2 Ambiguity Resolution Loop

```
[User Request]
     │
     ▼
┌─────────────────────────────────┐
│ Ambiguity Scoring               │
│ S + I + O + M + C = Score (0-10)│
└──────────┬──────────────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
  Score ≤ 5   Score > 5
     │           │
     │           ▼
     │    ┌──────────────────┐
     │    │ 질문 생성 & 전송   │
     │    │ (모호한 dim 위주) │
     │    └────────┬─────────┘
     │             │
     │      [User 응답 대기]
     │             │
     │             ▼
     │      ← 재평가 (loop) →
     │
     ▼
[Action 허용]
  ├─ 토론/결정: 진행
  ├─ Planning: Prometheus 위임
  └─ Implementation: Atlas/Hephaestus 위임
```

**Loop 종료 조건** (셋 중 하나):
1. Score ≤ 5 도달
2. User가 "그냥 진행해" 또는 "네가 알아서 해" (→ 명시적 권한 위임)
3. 동일 질문을 3회 이상 반복해도 답변이 더 이상 오지 않음 (→ best guess로 proceed, assumptions 문서화)

### 2.3 질문 원칙 (Scoring 체계에 따른 질문)

| 상황 | 질문 템플릿 |
|------|------------|
| **Scope 모호** (S ≥ 1) | "목표가 XX인 것으로 이해했는데, YY도 포함인가요?" |
| **Input 모호** (I ≥ 1) | "어떤 파라미터 범위/파일을 기준으로 할까요?" |
| **Output 모호** (O ≥ 1) | "결과물 포맷은 XX, YY 중 어떤 걸 원하시나요?" |
| **Method 모호** (M ≥ 1) | "접근법은 Z를 생각 중인데, 다른 방법을 고려할까요?" |
| **Constraint 모호** (C ≥ 1) | "하지 말아야 할 것, 범위 밖이 있나요?" |

> **절대**: "네, 알겠습니다. 진행하겠습니다." 라고만 답하지 않는다.
> threshold(≤5)를 통과하지 못했으면 반드시 질문을 던진다.

### 2.4 Agent별 적용

| Agent | Ambiguity Gate 적용 방식 |
|-------|--------------------------|
| **Sisyphus** (orchestrator) | **Direct** — 모든 user request에 대해 scoring 후 action |
| **Atlas / Hephaestus** (implementers) | **위임 시 이미 clear** — Sisyphus가 ambiguity를 해결한 후 전달 |
| **Prometheus** (planner) | Plan output에 ambiguity section 포함 — plan 자체의 모호성 self-check |
| **Oracle** (consultant) | **부분 적용** — 문제 정의가 모호하면 clarification 요청 가능 |
| **Sisyphus-Junior** (executor) | Prompt에 모든 정보가 명시되어야 함 — ambiguity는 orchestration layer에서 해결 |

---

## 3. Agent Switching Flow

### 3.1 Task Lifecycle

```
[User Request]
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  Sisyphus (Orchestrator)                            │
│  ├─ 1. Intent classification                        │
│  ├─ 2. Ambiguity Gate (Score ≤ 5 확인)              │
│  │     └─ Score > 5 → 질문 → 반복 → 해결            │
│  ├─ 3. Decomposition into work units                │
│  └─ 4. Delegate to appropriate agent               │
└──────────────────┬──────────────────────────────────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   ┌────────┐ ┌────────┐ ┌────────┐
   │Atlas   │ │Prometheus│ │Hephaestus│
   │(ML impl)│ │(planning)│ │(HSPICE)  │
   └───┬────┘ └───┬────┘ └────┬────┘
       │          │           │
       ▼          ▼           ▼
   ┌───────────────────────────────────────────────┐
   │  Oracle / Momus (Review & Quality Gate)       │
   └───────────────────────────────────────────────┘
                   │
                   ▼
            [Verified Result → User]
```

### 3.2 Decision Matrix

| Task Type | Primary Agent | When | Secondary |
|-----------|--------------|------|-----------|
| **Python ML coding** (GP, PyTorch, numpy, data pipeline) | **Atlas** | Implementation phase | Sisyphus-Junior for trivial fixes |
| **Experiment design** (DOE, sampling, ablation configs) | **Prometheus** | Planning phase | Metis for ambiguity resolution |
| **HSPICE simulation** (deck gen, PDK mapping, .mt0 parsing) | **Hephaestus** | Data generation phase | Atlas for parser scripting |
| **Paper outline / contribution analysis** | **Prometheus** | Paper writing phase | Oracle for novelty assessment |
| **Hard debugging** (2+ failed attempts, OOM, gradient issues) | **Oracle** | Any phase | — |
| **Plan review / quality check** | **Momus** | Before execution | — |
| **Architecture decision** (GP→NN transition, kernel design) | **Oracle** | When uncertainty > threshold | Prometheus for background planning |
| **Codebase exploration** (find existing patterns) | **Explore** | Any phase (background) | — |
| **External research** (docs, literature, OSS examples) | **Librarian** | When unfamiliar library/topic | — |
| **Ambiguous request** (unclear scope, multiple interpretations) | **Metis** | Before planning | — |
| **Frontend/visualization** (contour plots, diagnostic figures) | **visual-engineering** category | Implementation phase | Atlas for plot data preparation |

---

## 4. Agent Roles & Responsibilities

### 4.1 Atlas — Python ML Implementation Specialist

**Invocation**: `task(subagent_type="atlas", load_skills=["/shared/programming"], run_in_background=BOOL, prompt="...")`

**Responsibilities**:
- GP surrogate training (`ExactGPModel`, `AdditiveGPModel`)
- Physics-constrained surrogate (`L_mono`, `L_boundary`, `L_pelgrom`)
- Differentiable physics layer (`compute_vmin_from_z`)
- Contour extraction (`extract_contour`, Hausdorff distance)
- Data loading, parsing, and preprocessing (`parse_snm.py` style)
- Ablation study implementation and metrics computation
- Diagnostic plots and visualization (matplotlib, seaborn)
- All `toy_project/src/` and `physics_ablation/` code

**Project-specific rules** (from AGENTS.md):
- Data shape: X(N,d) [common_N, PU, Vop, ...], y(N,2) [mu, sigma] — d ≥ 3
- Shift convention: positive = slower for both NMOS and PMOS
- Import pattern: `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`
- Never hardcode Vop column index as `2` — use `VOP_COL` from `src.utils`
- Physics constraint code must accept variable-dim X via `n_extra` parameter
- All input dimensions must be **StandardScaler-normalized** before GP training for numerical stability
- Never use `gp.forward()` for L_mono — use eval-mode `__call__()` with `prediction_strategy = None`
- Never suppress Python type errors (strict typing with `from __future__ import annotations`)
- Use `matplotlib.use("Agg")` when generating saved figures

**Model**: `opencode/big-pickle` — capable model for complex ML code.

---

### 4.2 Prometheus — Planning & Architecture Consultant

**Invocation**: `task(subagent_type="prometheus", load_skills=["/shared/ulw-plan"], prompt="...")`

**Responsibilities**:
- Experiment design (DOE, sampling strategy, stratified weighted sampling)
- Ablation study configuration (5 configs, metric definition)
- Paper outline and contribution analysis
- Go/No-Go criteria evaluation
- Simulation budget vs accuracy analysis
- Research methodology design
- Literature survey direction

**When to use**:
- **Before Atlas**: "Plan the DOE for real PDK data validation" → Prometheus → then Atlas implements
- **Before paper writing**: "Design the paper outline and key figures" → Prometheus → then writing
- **For architecture**: "Should we use GP or NN+PINN?" → Prometheus researches → Oracle decides

**Model**: `opencode/qwen3.6-plus-free` — strong reasoning for planning and analysis.

---

### 4.3 Hephaestus — HSPICE & PDK Simulation Specialist

**Invocation**: `task(subagent_type="hephaestus", prompt="...")`

**Responsibilities**:
- HSPICE netlist template creation and validation (`sram_cell_pvta.sp`)
- PDK parameter mapping (common_N shift, PU shift implementation)
- Simulation matrix generation (`gen_decks_pvta.py`)
- MC output parsing (`.mt0` → `.npz`)
- Convergence troubleshooting
- Farm job submission and monitoring
- Data extraction specification (Excel)

**Model**: `opencode/big-pickle` — HSPICE domain knowledge + scripting.

---

### 4.4 Oracle — High-IQ Read-Only Consultant

**Invocation**: `task(subagent_type="oracle", prompt="...")` [always blocking, never background]

**When to consult**:
1. **After 2+ failed fix attempts** — debugging escalation
2. **Architecture decisions** — GP→NN transition, kernel selection, loss design
3. **Paper novelty assessment** — "Is this contribution publishable?"
4. **Complex math verification** — gradient flow, Cholesky decomposition, kernel properties
5. **Post-implementation review** — verify against constraints

**Model**: `opencode/qwen3.6-plus-free` — most expensive, highest reasoning quality.

---

### 4.5 Metis — Pre-Planning Ambiguity Resolution

**Invocation**: `task(subagent_type="metis", prompt="...")`

**Use when**: Request is ambiguous, multiple interpretations exist, or scope is unclear.
**Output**: Clarified scope, hidden intention discovery, AI failure point identification.

---

### 4.6 Momus — Plan & Quality Critic

**Invocation**: `task(subagent_type="momus", prompt="...")`

**Use when**: Work plan needs evaluation before execution.
**Output**: Gaps, ambiguities, missing contexts, verifiability assessment.

---

## 5. Switching Patterns (Common Scenarios)

### Pattern 1: New Feature Implementation

```
User: "Add L_boundary constraint to the surrogate"
  │
  ▼
Sisyphus intent: Implementation
  │
  ├─ [Ambiguity Gate] Score ≤ 5 확인 → Clear
  │
  ├─ [Planning] task(subagent_type="prometheus", ...)
  │   → "Design the L_boundary corner anchor approach"
  │
  ├─ [Implementation] task(subagent_type="atlas", ...)
  │   → Based on Prometheus plan, implement in physics_constrained_surrogate.py
  │
  └─ [Review] task(subagent_type="oracle", ...)
      → "Verify gradient flow and physical correctness"
```

### Pattern 2: Hard Bug

```
User: "L_mono gradient is not flowing"
  │
  ▼
Sisyphus intent: Fix needed
  │
  ├─ [Ambiguity Gate] "어떤 L_mono? 어떤 gradient? 어떤 gp model?"
  │   → Score > 5 → 질문 → 해결 → Clear
  │
  ├─ [Diagnose] task(subagent_type="explore", run_in_background=true, ...)
  │   → "Find all places where gp() is called in physics_constrained_surrogate.py"
  │
  ├─ [Escalate] task(subagent_type="oracle", ...)
  │   → "L_mono gradient not flowing — eval-mode posterior gradient issue"
  │   → Returns: prediction_strategy = None fix
  │
  └─ [Implement] task(subagent_type="atlas", ...)
      → Apply Oracle's fix
```

### Pattern 3: Paper Writing

```
User: "Let's write the DAC paper"
  │
  ▼
Sisyphus intent: Writing
  │
  ├─ [Plan] task(subagent_type="prometheus", ...)
  │   → "Paper outline: contributions, figures, target venue"
  │
  ├─ [Assess] task(subagent_type="oracle", ...)
  │   → "Novelty check against existing literature"
  │
  ├─ [Figures] task(category="visual-engineering", ...)
  │   → "Generate paper-quality contour plots"
  │
  └─ [Write] task(category="writing", ...)
      → "Draft the paper sections"
```

### Pattern 4: Real PDK Data Arrives

```
User: "I have the HSPICE data from foundry"
  │
  ▼
Sisyphus intent: Implementation
  │
  ├─ [Parse] task(subagent_type="atlas", ...)
  │   → "Create loading script for the new CSV data format"
  │
  ├─ [Validate] task(subagent_type="hephaestus", ...)
  │   → "Verify MC histogram quality, convergence status"
  │
  ├─ [Train] task(subagent_type="atlas", ...)
  │   → "Train GP surrogate on real data, evaluate hold-out"
  │
  └─ [Assess] task(subagent_type="oracle", ...)
      → "Compare real-data results with toy: GP→NN transition needed?"
```

---

## 6. Invocation Reference

```python
# Planning/Design → Prometheus
task(subagent_type="prometheus", load_skills=["/shared/ulw-plan"],
     prompt="Design experiment matrix for PVTA contour validation...")

# Python ML Implementation → Atlas
task(subagent_type="atlas", load_skills=["/shared/programming"],
     run_in_background=True,
     prompt="TASK: Implement L_boundary in physics_constrained_surrogate.py...")

# HSPICE Work → Hephaestus
task(subagent_type="hephaestus",
     prompt="Generate HSPICE decks for 486 conditions...")

# Hard Problem → Oracle (read-only, always blocking)
task(subagent_type="oracle",
     prompt="L_mono gradient not flowing through eval-mode posterior...")

# Codebase Search → Explore (always background)
task(subagent_type="explore", run_in_background=True,
     prompt="Find all GP training loops in toy_project/src/...")

# External Research → Librarian (always background)
task(subagent_type="librarian", run_in_background=True,
     prompt="Find GPyTorch examples of L_mono posterior gradient...")
```

---

## 7. Anti-Patterns

| Anti-Pattern | Why | Correct |
|-------------|-----|---------|
| Ambiguity bypass | 모호한 상태에서 action → 방향 틀어짐, 재작업 비용 2-3배 | Ambiguity Gate에서 Score ≤ 5 확인 후 action |
| Atlas doing planning | ML coder가 DOE 설계까지 하면 scope creep + suboptimal design | Prometheus plan first → Atlas implement |
| Oracle doing implementation | Read-only agent, cannot edit files | Oracle advises → Atlas/Hephaestus implements |
| Prometheus doing detailed coding | Planning model이 Python 세부 구현에 약함 | Prometheus spec → Atlas codes |
| Sisyphus implementing directly | Orchestrator가 직접 구현하면 quality低下 | Decompose → delegate → verify |
| Hephaestus doing ML | HSPICE specialist가 GP surrogate coding | Hephaestus data → Atlas ML |

---

## 8. Quick Reference Card

```
┌─────────────────────────────────────────────────────────────────────┐
│                      TASK → AGENT QUICK MAP                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Python ML Code  ─────→ Atlas                                       │
│  Experiment Plan ─────→ Prometheus                                   │
│  HSPICE/PDK      ─────→ Hephaestus                                  │
│  Hard Debug      ─────→ Oracle                                      │
│  Ambiguous Req   ─────→ Metis                                       │
│  Plan Review     ─────→ Momus                                       │
│  Code Search     ─────→ Explore (background)                        │
│  External Ref    ─────→ Librarian (background)                      │
│  Paper Writing   ─────→ writing category                            │
│  Visualization   ─────→ visual-engineering category                 │
│  Simple Fix      ─────→ Sisyphus-Junior / quick category            │
│  Complex Task    ─────→ deep category                               │
│                                                                     │
│  Sisyphus (Orchestrator): Decompose → Delegate → Verify → Ship     │
└─────────────────────────────────────────────────────────────────────┘
```
