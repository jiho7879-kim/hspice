# HSPICE SRAM Vmin — Workflow Harness

> **목적**: 이 문서는 Sisyphus(본 에이전트)의 행동을 제어하는 하네스입니다.
> 모든 세션 시작 시 **반드시** 이 문서를 읽고 `session_start` 체크리스트를 수행해야 합니다.
> 하네스 규칙 위반은 버그로 간주되어 즉시 수정되어야 합니다.

---

## 1. Session Init Protocol (MANDATORY — 세션 시작 시)

모든 세션은 아래 순서로 시작합니다:

```yaml
step_1: "Read docs/harness.md → session_start checklist 수행"
step_2: "Read docs/workflow_state.json → 현재 Phase/Queue 확인"
step_3: "Read AGENTS.md → Domain knowledge refresh"
step_4: "Read docs/decisions/*.md → Latest findings 확인"
step_5: "workflow_state.json.bg_queue 비어있는지 확인. Pending 있으면 먼저 처리"
```

체크리스트를 완료하기 전에는 **어떤 action도 금지**합니다.

---

## 2. Agent Routing Decision Tree (MANDATORY)

작업 유형별로 반드시 지정된 agent를 사용합니다:

```
Task Type                          → Agent              
─────────────────────────────────────────────────────────
Python ML (GP, physics, contour,                        
  ablation, surrogate, data)       → Atlas (subagent)
HSPICE (deck gen, PDK, parsing,                         
  simulation run)                  → Hephaestus (subagent)
Planning, architecture, DOE,                            
  paper outline, sampling          → Prometheus (consult)
Hard debugging / architecture                           
  consultation (read-only)         → Oracle (consult)
Documentation, .md files           → Sisyphus (직접)
Investigation / exploration                             
  (codebase search)                → explore (background)
Library research / OSS reference                        
  fetch                           → librarian (background)
Trivial single-file fix                               
  (typo, config)                  → 직접 또는 quick category
```

**규칙**:
- Atlas/Hephaestus/Prometheus 작업은 반드시 `task(subagent_type="...")` 또는 `task(category="...")`로 위임
- 절대 Sisyphus(본인)가 직접 Python ML/HSPICE 구현하지 않음
- 단, **문서 작업(.md)** 과 **오케스트레이션 결정**은 Sisyphus가 직접 수행

---

## 3. Phase State Machine

프로젝트의 공식 Phase들입니다. `workflow_state.json`의 `phase` 필드를 업데이트하며 진행합니다.

```
Stage 1: 3D Baseline ✅ (DONE)
Stage 2: 4D + WLUD ratio ✅ (DONE)
Stage 3: Inverse Assist ❓ (IN PROGRESS — 아래 sub-phase로 세분화)
├── 3a: Validation at correct target Vmin ⬜
├── 3b: PhysicsConstrainedSurrogate 4D root cause ⬜
├── 3c: Fix or alternative approach ⬜
└── 3d: Final verification ⬜
Stage 4+: Future phases
```

**Phase 전환 규칙**:
1. Phase 진입 시 → `workflow_state.json` 업데이트 + `docs/decisions/`에 checkpoint summary 생성
2. Phase 내 sub-phase 완료 시 → `workflow_state.json` 업데이트 (상태 변경)
3. Phase 완료 시 → **phase summary .md 파일** 필수 생성 (AGENTS.md §Session continuation rules)
4. Trial/error 발생 시 → **즉시** `docs/decisions/`에 로그 (나중에 몰아쓰지 않음)

---

## 4. Background Task Protocol

Background task는 반드시 다음 프로토콜을 따릅니다:

### 실행
```yaml
1. task(subagent_type="explore|librarian", run_in_background=true, ...) 호출
2. 반환된 `bg_...` ID를 즉시 workflow_state.json.bg_queue에 등록
3. **같은 검색을 수동으로 중복 수행 금지** (Anti-Duplication Rule)
4. Non-overlapping 작업만 계속 수행
5. 더 이상 독립적으로 할 일이 없으면 → **응답 종료** (기다리지 않음)
```

### 수집
```yaml
1. <system-reminder> 수신 → background_output(task_id="bg_...") 호출
2. 결과 수집 → workflow_state.json.bg_queue에서 제거
3. 결과 기반으로 다음 action 결정
```

### 금지
- ❌ `background_output`을 system-reminder 없이 호출 (blocking anti-pattern)
- ❌ 동일 검색을 explore/librarian에 위임하고 직접 다시 수행
- ❌ background task 완료를 기다리지 않고 "일단 구현"

---

## 5. Ambiguity Gate (AGENTS.md §2)

모든 action 전에 S+I+O+M+C score를 계산합니다:

> **Score = 0-5**: Proceed
> **Score = 6-10**: 반드시 질문. Threshold 이하로 떨어질 때까지 반복.

Ambiguity 체크를 건너뛰고 action을 시작한 경우:
1. 즉시 중단
2. Score 계산
3. 필요한 질문
4. 재평가 후 진행

---

## 6. Documentation Triggers (MANDATORY)

다음 이벤트 발생 시 **즉시** 문서화합니다:

| Event | Location | Format |
|-------|----------|--------|
| Phase transition | `docs/decisions/phase_<name>.md` | What was done, metrics, verdict |
| Trial & error | `docs/decisions/` (파일명에 내용 반영) | What was tried, what failed, root cause, fix |
| Design decision | `docs/decisions/` | Options considered, why chosen/rejected |
| Bug 발견 | `docs/decisions/trial_log.md` (append) | Symptoms, diagnosis, fix |
| User feedback/지적 | `docs/decisions/trial_log.md` (append) | What was wrong, correction |

**지연 금지**: "나중에 정리" → 절대 안 합니다. 발견 즉시 3줄이라도 씁니다.

---

## 7. 대화 규칙

1. **User의 질문/지적을 받으면**: 먼저 틀린 점을 인정하고 수정. 변명/방어 금지.
2. **"queue" 관련 지적**: 즉시 workflow_state.json.bg_queue 확인. Pending task 처리.
3. **Background task 완료 전** 구현 결정 금지 (특히 Oracle 결과 필요 시).
4. **Todo list**: Multi-step 작업은 todowrite로 즉시 생성. 진행 상황 투명하게.
5. **Evidence**: 작업 완료 = diagnostics clean + build pass + test pass (해당 시).

---

## 8. 현재 상태 요약 (session start용)

```
Phase: Stage 3a (Validation at correct target Vmin)
Previous findings:
- PhysicsConstrainedSurrogate with 4D boundary aug → mu RMSE 0.039 (bad)
- physics_ablation.md: L_boundary alone gives 95% of Vmin RMSE improvement
- demo_assist.py currently uses plain Surrogate (not PhysicsConstrained)
- Target Vmin=0.55V → too low for WLUD∈[0.90, 1.0] practical range

Open questions:
1. What target Vmin makes sense? (0.60? 0.65? 0.70?)
2. Does plain Surrogate give good WLUD prediction at correct target Vmin?
3. Should PhysicsConstrainedSurrogate be fixed or plain Surrogate accepted for Stage 3?
```
