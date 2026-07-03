# Session Summary — 2026-07-02

## 진행 내용

### 1. VWL → WLUD Ratio 전면 refactoring

**동기**: 기존 4D GP input의 Vwl(절대전압)은 Vop와 독립적이라 물리적 의미가 불명확하고 range가 unbounded됨. WLUD ratio(=Vwl/Vop)로 변경하여 [0,1] bounded + Vop-independent + 물리적 해석 가능.

**변경 내역** (11개 파일):
- `VWL_COL` → `WLUD_COL`, `N_VWL` → `N_WLUD` (하위호환 alias 유지)
- CSV parser(`hspice_io.py`)에서 절대 Vwl 자동 변환
- Probe points, corner anchors 모두 WLUD ratio 기반

**결정 근거 기록**: `docs/decisions/toy_validation_results.md`에 반영

### 2. WLUD Range [0.90, 1.00] 축소

**동기** (user feedback): 현업에서 WLUD ratio가 0.9 아래(>10% underdrive)로 내려갈 일이 없음.
- `WLUD_FACTORS`: `[0.50,0.60,0.70,0.80,0.90,1.00]` → `np.linspace(0.90, 1.00, 6)`
- `wlud_lo` values: 0.50 → 0.90

### 3. Physics-Constrained Stage 3

**문제**: `demo_assist.py`가 plain `Surrogate`를 사용 — ablation 결과 무시
**수정**: `PhysicsConstrainedSurrogate.fit()` 4D 대응 (n_extra 전달), `_format_lengthscales` 버그픽스, `demo_assist.py` 전환

### 4. Trial & Error

| 시도 | 결과 |
|------|------|
| `use_mono+pelgrom+boundary` all-on | CG non-convergence (1000 iter), killed |
| boundary only → training OK | `_format_lengthscales` crash (4D kernel group) |
| fix lengthscale formatting → result | mu RMSE 0.039 (too high), Vmin RMSE 0.156V → **NO-GO** |

### 5. 실행 결과 요약

| Stage | 결과 | 주요 메트릭 |
|-------|------|-----------|
| Stage 1 (3D baseline) | ✅ GO | mu RMSE 0.00206 |
| Stage 2 (4D+WLUD) | ✅ GO | mu RMSE 0.00237, monotonicity 100% |
| Stage 3 (inverse assist) | ❌ NO-GO | mu RMSE 0.039, Vmin RMSE 0.156V |

### 6. Ablation Study 확인 (재실행, WLUD range 변경 후)

기존 3D ablation은 WLUD range와 무관하므로 결과 동일:
| Config | Vmin RMSE | vs Baseline |
|--------|-----------|-------------|
| Baseline | 6.52 mV | — |
| +L_boundary | 5.16 mV | -20.9% |
| +Mono+Boundary | 5.10 mV | -21.8% |
| +Mono+Boundary+Pelgrom | 4.91 mV | -24.7% |

핵심 finding 재확인: **L_boundary alone gives 95% of improvement**

### 7. 기록 점검 (AGENTS.md 준수)

| 규칙 | 상태 | 비고 |
|------|------|------|
| 설계 결정 .md 기록 | ⚠️ Partial | `toy_validation_results.md` 업데이트 완료 |
| Trial & error 기록 | ✅ | 위 trial table 참조 |
| Phase/checkpoint summary | ⚠️ Partial | 본 문서 생성 중 |

## Open Issues / 다음 스텝
1. PhysicsConstrainedSurrogate 4D 성능: 왜 mu RMSE가 10× 이상 나빠졌는지 원인 분석 필요
2. 대안: Stage 3에서는 plain Surrogate 사용 + ablation constraint는 별도로 검증
3. Xyce + ASAP7 open-source 검증 파이프라인 feasibility 검토
