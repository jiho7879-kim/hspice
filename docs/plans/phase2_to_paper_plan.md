# Phase 2 → 논문 상세 계획: HSPICE 실데이터 검증부터 IEEE TCAD 투고까지

> 작성일: 2026-07-07
> 선행 문서: `sram_vmin_inverse_estimation_plan.md` (원 계획, Gate 0 정의),
> `docs/decisions/session_20260706_root_cause_fixes.md` (Gate 0 통과 근거),
> `docs/plans/deck_generation_plan.md` + `execution_guide.md` (HSPICE 실행 절차),
> `papers/paper_en.md` v0.3 (논문 초안 — 수치 stale, §7.8에서 갱신 목록 관리)
> 목적: **Gate 0(toy) 통과 이후 논문 제출까지의 전 구간**을 Phase 단위로 상세 기술.
> 각 Phase는 착수 조건(entry), 산출물(exit), Go/No-Go, 기술 디테일을 포함한다.

---

## 1. 현재 위치: Gate 0 통과 판정 (2026-07-06 기준)

### 1.1 Toy 3단계 최종 수치 (교정된 지표)

| Stage | 내용 | 핵심 수치 | 판정 |
|-------|------|-----------|------|
| 1 (3D) | PVTA contour | mu RMSE 0.00206, Vmin RMSE 3.5mV | ✅ GO |
| 2 (4D+WLUD) | Assist 차원 추가 | mu RMSE 0.00238, WLUD monotonicity 100% | ✅ GO |
| 3 (inverse) | Required-assist 역추정 | **Vmin RMSE 2.55mV (physics) / 3.14mV (plain), p95 3.87/6.15mV, feasibility 일치 100%** | ✅ GO |

Physics-constrained ablation (재실행, 정직한 수치): baseline 1.26mV → +L_boundary
0.92mV(−27%) → all-on 0.90mV. **개선의 1차 요인은 input standardization이며 corner
anchor는 잔여 오차의 ~27%를 추가 개선, 특히 tail(p95 −37%)에서 효과가 크다.**

### 1.2 검증 완료된 방법론 스택 (논문의 "재료")

| 구성요소 | 위치 | 상태 |
|----------|------|------|
| GP surrogate (Matern 5/2+ARD, 표준화 입력) | `src/surrogate.py`, `src/models.py` | ✅ |
| Additive sigma kernel (k_op ⊕ k_cnpu) | `src/models.py` | ✅ |
| Physics-constrained fit (L_mono/L_boundary/L_pelgrom) | `src/physics.py` | ✅ (v2, 스케일링+pelgrom 수정) |
| Differentiable physics layer (Z→Vmin 보간) | `src/physics_layer.py` | ✅ (forward), gradient 시연은 §4.1 |
| Censored/assist-active 지표 정의 | `physics_layer.py`, `validate_assist_sweep.py` | ✅ — 논문 §Exp Setup에 그대로 기술 |
| 정확 Z_target 유도 `derive_z_target()` | `src/utils.py` | ✅ (64Mb@99.9% → 6.64) |
| HSPICE deck 템플릿/렌더러 | `templates/sram_cell_pvta.sp`, `gen_hspice.py`, `hspice_io.py` | ✅ (미실행) |

### 1.3 논문 Accept 조건 대비 Gap 분석 (원 계획 §11 기준)

| # | Accept 조건 | 현재 상태 | 담당 Phase |
|---|------------|-----------|-----------|
| 1 | Inverse estimation formulation이 main novelty | △ feasible-region + assist bisection까지. **gradient 기반 inversion 미시연** — "differentiable" 주장의 근거 필요 | Phase 3 (§4.1) |
| 2 | Physical parameter space (mobility, W, σL…) 입력 포함 | ❌ 현 4D (cn, pu, Vop, WLUD)까지만 | Phase 4 |
| 3 | Simulation budget vs accuracy Pareto 정량 제시 | △ 단발 N_train sweep만 존재 (seed 1개, 전략 비교 없음) | Phase 3 (§4.2) |
| 4 | Active learning + physics constraint + multi-fidelity 통합 | △ physics constraint만 완료 | Phase 3 (§4.3, §4.4) |
| 5 | Real industry PDK validation | ❌ deck 파이프라인만 준비 | **Phase 2 (최우선)** |

> **전략적 판단**: 조건 5(실데이터)가 최장 리드타임(farm 큐, 사내 승인)이므로 최우선.
> 조건 1·3·4는 toy/실데이터 어느 쪽으로도 개발 가능하므로 farm 대기 시간에 병렬 진행.

---

## 2. 전체 로드맵 (Phase 구조)

```
Phase 1  Toy Gate 0                          ✅ 완료 (2026-07-06)
Phase 2  HSPICE 3D/4D 실데이터 검증           ← 최우선, farm 리드타임 지배
Phase 3  방법론 novelty 완성                  ← Phase 2와 병렬 (toy에서 개발 → 실데이터 재실행)
  3.1 Gradient-based inversion
  3.2 Budget vs accuracy Pareto
  3.3 Active learning (contour-targeted)
  3.4 Multi-fidelity (noise-aware GP 통합)
  3.5 Tail/normality 방어
Phase 4  차원 확장 (skew → σL/σG → 8D Sobol) ← Phase 2 GO 이후
Phase 5  논문 작성/투고                        ← Phase 2+3 결과로 초고, Phase 4는 확장 섹션
```

의존성: P2 → P4 → P5(full), P3는 P2와 독립 병렬, P5 초고는 P2+P3만으로 착수 가능.

---

## 3. Phase 2 — HSPICE 실데이터 검증 (Stage 4/5 of execution_guide)

### 3.1 Entry 조건 및 사전 결정사항

- [ ] 사내 PDK 접근 + farm 계정 확인, 데이터 반출 규정 확인 (§7.7 익명화 전략과 연동)
- [ ] **MC_RUNS 결정** — 아래 noise-floor 분석 기반:

**Vmin 추정의 MC 노이즈 플로어 (조건당)**

Z = μ/σ에서 σ 추정 오차가 지배적: δσ/σ ≈ 1/√(2(N−1)), δμ/μ = 1/(Z√N) (Z≈6.6에서 무시 가능).
따라서 δZ ≈ Z/√(2N), Vmin 전파: **δVmin ≈ δZ / (dZ/dVop)**.
Toy 기준 dZ/dVop ≈ 8.8/V (실데이터에서는 §3.4 QC에서 실측):

| MC_RUNS | δZ (Z=6.6) | δVmin (1σ, 조건당) |
|---------|-----------|--------------------|
| 1,000 | 0.148 | ~17 mV |
| 2,000 | 0.104 | ~12 mV |
| 5,000 | 0.066 | ~7.5 mV |
| 10,000 | 0.047 | ~5.3 mV |

**권장**: 훈련용 surface는 MC=2,000 (GP가 조건 간 평활화로 노이즈 흡수 — noise-aware GP
전제), **검증 기준점(4 corner + TT + hold-out 20점)은 MC=10,000**. 검증 지표의 판정
임계값은 이 노이즈 플로어와 같은 자릿수이므로, **동일 조건 seed 반복(TT 2회)으로 empirical
repeatability를 먼저 측정**하고 Go/No-Go 임계값을 `max(15mV, 2×repeatability)`로 설정.

### 3.2 실행 순서 (execution_guide Stage 4 → 5)

```
Step A  Validation deck: 1 corner(TT) × 6 Vop, MC=10K 수동 실행
        └─ 히스토그램 QC (§3.4) 통과 → deck correctness 확정
        └─ **로브별 (SNM_L, SNM_R) 동시 측정 + ρ_LR 실측** (§3.2.1 — 적대적
           리뷰 A1의 선행 조건. ρ ≤ 0.9면 lobe-resolved Z_eff가 기본 정의)
Step B  TT seed-반복 5회 → Vmin repeatability 실측 (n=2는 χ²(1) 수준으로 무의미)
Step C  본 실행: 200 (cn,pu) × 6 Vop = 1,200 decks (Stage 4, 3D)
        └─ farm 병렬, ~1.5-5h (MC 수에 따라)
Step D  검증 세트 (MC=10K, 검증 전용):
        └─ corner 4점 + **corner-ring 8점**(각 corner ±10mV 오프셋) + 내부 20점
        └─ **anchor/검증 분리 규칙**: L_boundary anchor로 쓴 corner 측정은
           anchored GP의 검증점으로 사용 금지 (이중사용 = 자명한 저오차).
           anchored GP는 ring+내부점으로, corner 자체 성능은 boundary-off
           config로만 평가
Step E  파싱 → npz (§3.3 스키마) → GP 학습 → Stage 4 Go/No-Go
Step F  GO 시 Stage 5 (4D+Vwl): 200 × 6 × 5 = 6,000 decks (~8h overnight)
Step F' **Write-margin 파일럿** (20 cond × 2 temp, deck plan Stage 3 전용분 조기
        편입): WLUD의 read/write 상충을 dual-metric으로 1개 데모 확보 —
        inverse assist 주장을 "read-limited" 반쪽 최적화로 남기지 않기 위함
        (적대적 리뷰 A2, 선택지 (b) 채택)
Step G  TT full-variation MC 1회 → local-only 대비 bias 정량화 (원 계획 14.5 Step 5)
```

### 3.2.1 y-정의 변경: lobe-resolved Z_eff (적대적 리뷰 A1 처방)

Read SNM = min(L, R)의 (μ,σ)에 Gaussian z를 적용하면 **min 분포의 좌측 꼬리가
moment-matched Gaussian보다 무거워** Z≈6에서 +0.7σ(ρ=0)~+1.9σ(ρ=−0.7)의
**낙관 편향** 발생 — Vmin ~70-190mV 과소평가 가능 (2026-07-07 닫힌형+MC 검증,
`adversarial_review_20260707.md` A1 표). 처방:

```
MC 샘플별 로브 SNM_L, SNM_R 기록 (.MEASURE 2줄, ngspice snmr1/snmr2와 동형)
→ (μ_L, σ_L, μ_R, σ_R, ρ_LR) 추출
→ p_fail = P(L<0) + P(R<0) − P(L<0, R<0)   # bivariate Φ, 닫힌형·미분가능
→ Z_eff = Φ⁻¹(1 − p_fail)                   # physics layer는 무수정
```

GP y는 (μ, σ)를 로브별 2쌍으로 확장하거나, Z_eff를 재구성 가능한 최소 통계량
(μ_worst, σ_worst, ρ)을 저장 — Step A 파일럿의 ρ 실측 후 최종 결정.
논문 기여로 역이용: "표준 margin 관행의 tail 편향 정량화 및 교정".

### 3.3 파서/데이터 스키마 변경 (코드 작업)

`src/hspice_io.py` 파서에 **이번에 확립한 지표 정의를 이식**:

1. npz에 추가 배열 저장: `n_mc` (조건별 MC 수), `sem_mu = σ̂/√N`,
   `sem_sigma` — noise-aware GP 입력. `load_intermediate`는 X, y만
   반환하므로 하위호환 유지, 새 로더 `load_with_noise()` 추가.
   `sem_sigma`는 Gaussian 공식(σ̂/√(2N))이 kurtosis에 민감하므로 **bootstrap
   SEM을 기본**으로, 공식값은 참고 병기. 로브별 통계(§3.2.1) 컬럼 포함:
   `mu_L, sigma_L, mu_R, sigma_R, rho_LR`.
2. **Censored 처리**: z(Vop_min) > Z_target인 조건은 Vmin left-censored로 플래그
   (`compute_vmin_from_z(..., return_censored=True)` 활용). z(Vop_max) < Z_target은
   fail-point (NaN). 파서 단계에서 마스크 저장.
3. QC 리포트 자동 생성 (§3.4 항목별 pass/fail, `results/hspice_stage4/qc_report.md`).

### 3.4 MC 히스토그램 QC (조건별, 자동화)

| 체크 | 기준 | Fail 시 조치 |
|------|------|-------------|
| 정규성 (Anderson-Darling) | p > 0.01 (Vop ≥ 0.5V 구간) | robust 통계(median/IQR→σ 환산) fallback + 플래그 |
| Bimodality (dip test 또는 GMM BIC) | 단봉 | 저전압 fail 혼입 의심 → 해당 Vop censored 처리 |
| SNM > 0 비율 | > 99.9% (Vop ≥ 0.6V) | 셀/모델 설정 재점검 |
| dZ/dVop 실측 | 조건별 회귀 기울기 분포 리포트 | noise-floor 표(§3.1) 갱신 |

> **주의 (toy에서 얻은 교훈)**: 저전압(0.4V)에서 분포 왜곡·bimodality는 정상적 물리
> (fail 혼입)일 수 있다. 이를 "데이터 오류"로 버리지 말고 censored로 분류하는 것이
> 통계적으로 옳다 — Gaussian 가정은 z-crossing 근방 Vop에서만 필요.

### 3.5 Noise-aware GP (방법론 개선 + 논문 셀링 포인트)

현행 `GaussianLikelihood`(등분산 학습)를 **`FixedNoiseGaussianLikelihood`**로 확장:

```python
# mu GP:    noise = sem_mu**2      (조건별 상이 — heteroscedastic)
# sigma GP: noise = sem_sigma**2
likelihood = FixedNoiseGaussianLikelihood(
    noise=torch.tensor(sem**2), learn_additional_noise=True)
```

- 효과 1: MC 수가 적은 조건의 영향 자동 감쇠 → 훈련 MC=2,000의 노이즈를 원리적으로 처리
- 효과 2: **multi-fidelity의 자연 통합** (§4.4) — low-fi(MC 200)와 high-fi(MC 10K)를
  같은 GP에 넣고 SEM 차이로 가중 → 별도 co-kriging 없이 "noise-aware GP unifies
  multi-fidelity MC"라는 명확한 스토리
- 구현: `Surrogate.fit(..., y_noise=None)` 옵션 인자. 기존 호출부 무변경.

### 3.6 Stage 4/5 Go/No-Go (실데이터 특화 기준)

execution_guide 기준 + 이번 세션 교훈 반영:

| 기준 | Go | 비고 |
|------|----|----|
| mu R² (hold-out, MC=10K 기준점) | > 0.95 | |
| Contour Hausdorff vs hold-out | < 15mV (고정) | 임계는 응용 요구에 고정. **repeatability > 7.5mV면 기준 완화가 아니라 검증 MC를 4×로 증량** (임계 순환성 방지 — 리뷰 B6) |
| Corner 4점 \|Vmin_pred − Vmin_MC\| | < 15mV | local-only MC가 정답 (이중계산 금지). **boundary-off config로만 평가** (anchor 이중사용 금지 — 리뷰 A3) |
| Gradient 방향 | dVmin/dcn < 0, dVmin/dpu > 0 | |
| **ℓ_cn < ℓ_pu (PG≫PU 계층)** | 성립 여부 **기록** | toy에서 불가했던 검증 — 실데이터에서 처음 유효. 불성립 시 원인 분석(§7.5) 후 진행 (hard gate 아님) |
| L_mono 재평가 | penalty > 0 발생 여부 기록 | 실데이터 비단조 구간에서만 의미 — toy에선 노이즈만 추가했음 |
| sigma의 (cn,pu) 의존성 | additive kernel 잔차 분석 | 의존성 크면 kernel 재설계 (§7.4) |

---

## 4. Phase 3 — 방법론 Novelty 완성 (farm 대기와 병렬, toy에서 개발)

### 4.1 Gradient-based Inversion (Accept 조건 1의 완결)

**현황**: inversion이 grid 평가 + bisection뿐 — "differentiable physics layer"의
미분 가능성을 실제로 쓰는 데모가 없다. 리뷰어가 가장 먼저 지적할 지점.

**구현 설계**:
```
x = (cn, pu[, wlud]) ∈ R^d  (leaf tensor, requires_grad)
  → X_vop = [x ⊗ 1_6 ; VOPS]           # 6개 Vop 행 복제 (미분가능 concat)
  → mu(X), sigma(X)                     # GP posterior mean (eval mode,
                                        #   prediction_strategy=None, torch 유지)
  → PhysicsLayer(mu, sigma) → Vmin(x)   # 기존 torch 모듈
  → loss = (Vmin − target)²  → Adam으로 x 갱신
```

- **미분가능성 논거** (논문 §method에 명시): Matern 5/2 posterior mean은 입력에 대해
  C² — 1차 미분 well-defined. Physics layer는 crossing 구간 선택이 이산이지만 구간
  내부에서 선형보간은 미분가능 → **piecewise-differentiable**; 구간 경계에서
  subgradient. 실무적으로 Adam에 문제없음 + bisection 교차검증으로 정합성 입증.
- 박스 제약: `x = lo + (hi−lo)·sigmoid(θ)` 재매개변수화 (projected step보다 안정).
- **검증**: 동일 target에서 gradient 결과 vs bisection 결과 — WLUD 차이 < 0.005 요구.
- **시연 시나리오** (리뷰 B2 반영 — 데모는 gradient가 진짜 이기는 문제여야 함):
  주 데모 = **다변수 동시 역추정** (예: (WLUD, σL_mult) 2-자유도에서 Vmin=0.6
  제약 하 최소-assist 해; Phase 4 이후엔 Scenario B σL tolerance). 2D 경계 추적
  (Scenario D)은 grid/bisection이 우월한 케이스이므로 **교차검증용으로만** 사용.
- **Censored 영역 함정** (리뷰 C8): censored 셀은 상수(0.35V)를 반환해 기울기가
  소실됨 → barrier 페널티(z(V_min_op) − Z_target에 비례) 또는 마스킹으로 처리 명세.
- 산출물: `scripts/demo_gradient_inversion.py`, contour 위 수렴 궤적 figure (논문 Fig).
- 공수: 2-3일 (toy에서 개발, 실데이터 GP에 그대로 적용 가능).

### 4.2 Simulation Budget vs Accuracy Pareto (Accept 조건 3, "산업 가치" 핵심 figure)

**설계** (기존 `run_ablation` 확장):
```
N_train ∈ {50, 100, 200, 400, 800, 1200}   # 조건 수 기준 (×6 Vop)
전략 ∈ {random, Sobol-uniform, stratified-Sobol(35/25/20/20)}
seeds = 5   (오차 막대 필수 — 기존 단일 seed의 약점)
지표: contour Hausdorff, Vmin RMSE(assist-active), feasibility 일치율
+ 각 N에서 physics-constrained vs plain 병기 → "제약이 저예산 구간에서 더 유효" 가설 검증
```
- 기대 결과(가설): N≈200에서 포화 시작, 제약 효과는 N<200에서 최대 —
  "**corner anchor 24점 = 훈련 몇백 점의 가치**"를 정량화하면 강력한 문장이 된다.
- 실데이터 버전: Phase 2 완료 후 1,200 조건 풀에서 subsampling으로 동일 실험 재실행.
- 공수: 1-2일 (CPU 배치, 밤샘 실행).

### 4.3 Active Learning — Contour-Targeted Acquisition (Accept 조건 4의 절반)

**핵심 아이디어**: Vmin=0.6V **경계 근방**의 불확실성만 줄이면 된다 (전역 정확도 불필요)
→ level-set estimation 문제 (Gotovos et al. 2013, Bryan et al. straddle).

**Acquisition 설계** (physics layer 통과형 — 이 조합이 차별점):
```
1. (cn,pu) 후보 grid에서 GP posterior를 M=50회 샘플링
   → physics layer 통과 → Vmin 샘플 분포 → s_Vmin(x) = std
   ★ 반드시 (cn,pu)별 Vop-slice 6점의 JOINT posterior 샘플 (6×6 공분산)
     — marginal 독립 샘플링은 인위적 crossing으로 Vmin 분산을 과대평가해
     acquisition을 왜곡함 (리뷰 B3). μ-GP/σ-GP 간 독립 가정은 한계로 명시.
2. straddle(x) = 1.96·s_Vmin(x) − |Vmin_med(x) − 0.6|
3. Batch 선정: straddle 상위에서 greedy-distance (farm 병렬 활용, batch=10)
```
- 비교 실험: 초기 Sobol 50pt + {random, Sobol 추가, straddle} × 5 rounds × 10pt
  → round별 contour Hausdorff. 목표: **동일 budget에서 2× 오차 감소** (원 계획 §10).
- 주의: GP 샘플링 → Vmin 전파는 mu/sigma GP 독립 가정 — 상관 무시의 한계를 논문에 명시.
- Toy로 알고리즘 검증 → 실데이터에서는 "AL 에뮬레이션" (1,200점 풀에서 꺼내는 방식,
  원 계획 Week 3-4 항목과 동일) — farm 재제출 없이 AL 커브 생성 가능.
- 공수: 3-4일.

### 4.4 Noise-aware MC Budget Allocation (구 "multi-fidelity" — 리뷰 B1로 재명명)

> **명칭 주의**: MC 표본수 차이는 문헌의 multi-fidelity(모델 충실도 차이,
> bias 있는 low-fi)가 아니라 heteroscedastic noise다. 논문에서 'multi-fidelity'
> 주장은 하지 않는다 — "noise-aware MC budget allocation"으로 정직하게
> 포지셔닝하고, 진짜 이질-fidelity(co-kriging)는 Discussion의 future work.

**결정: co-kriging(AR1) 대신 noise-aware GP 단일화 (§3.5)로 간다.**

| 접근 | 장점 | 단점 | 판정 |
|------|------|------|------|
| AR(1) co-kriging (Kennedy-O'Hagan) | 문헌 정합성 | 구현·튜닝 비용, low-fi bias 모델 필요 | 보류 |
| **SEM 기반 heteroscedastic 단일 GP** | 구현 1일, MC 통계와 정확히 일치하는 원리, deck 수 무관 동일 파이프라인 | fidelity 간 systematic bias는 못 잡음 | **채택** |

- MC의 low-fi는 bias가 아니라 **분산**이 크다 (동일 시뮬레이터, 표본수만 차이) →
  Kennedy-O'Hagan의 bias 항이 원리적으로 불필요. 이 논거 자체가 논문 한 단락.
- **Budget allocation 실험**: 총 MC 예산 B 고정, (많은 조건 × MC 200) vs (적은 조건 ×
  MC 10K) vs 혼합 → 어느 배분이 contour 정확도 최적인지. 산업 독자에게 §4.2와 함께
  "시뮬레이션 예산 설계 가이드" 챕터를 구성.
- 공수: noise-aware GP(§3.5) 완료 후 +2일.

### 4.5 Tail/Normality 방어 (최대 리뷰어 리스크 선제 대응)

Z=μ/σ의 Gaussian 외삽(Z≈6.6, P~1e-11)은 IS 문헌(Liu 2023 등)이 정확히 공격하는 지점.
3중 방어:

1. **Framing (필수)**: 본 방법의 목표는 절대 fail-rate 예측이 아니라 **산업 표준
   margin metric(μ/σ z-score)의 surrogate**임을 명시. Vmin spec 결정은 z-score 기반이
   현업 관행 — 인용: Gupta & Calhoun 2021 (dynamic Vmin), margin-based 방법론 계열.
2. **QC 근거 (필수)**: §3.4의 정규성 검정 + Q-Q plot을 z-crossing 근방 Vop에서 제시 —
   "보간에 사용되는 구간에서 Gaussian 가정이 데이터로 지지됨"을 figure 하나로.
3. **IS 스팟체크 (여력 시)**: 3-5개 조건에서 mean-shift IS로 tail quantile 직접 추정
   → z-score 기반 Vmin과 비교. 차이가 나면 그것대로 "z-score 한계의 정량화"로 보고
   (defensive contribution). HSPICE에서 shifted-sampling deck 필요 — Phase 4와 병행.

### 4.6 (선택) Repair/ECC-aware Z_target

`derive_z_target(mb, y_target, n_repair)` 확장 — repair r개 허용 시
`P(fail_bits > r) ≤ 1−Y`의 binomial tail(Poisson 근사: `Q(r, λ)=1−Y`, λ=Nbits·p).
scipy `gammainccinv`로 닫힌형. Physics layer는 Z_target 스칼라만 바뀌므로 무수정.
→ "repair 8개 = Vmin 30mV 완화" 류의 산업 임팩트 문장 생성 가능. 공수: 1일. 우선순위 하.

---

## 5. Phase 4 — 차원 확장 (Phase 2 GO 이후)

원 계획 §14.11 단계별 확장을 따르되, 이번 세션 교훈을 반영:

### 5.1 +PG-PD skew (4D→5D 실데이터 기준으로는 첫 확장)

- 원 계획 Phase B (nested adaptive grid): **toy가 아닌 Phase 2 실데이터 GP의 gradient
  map**을 sampling guide로 사용 (toy analytic gradient는 PG≫PU 미반영이므로 부적합 —
  §1.2 lengthscale 실험의 교훈).
- Skew ∈ {−30, −15, 0, +15, +30} mV, gradient 상위 사분위 영역 3× 밀도.
- 예산: ~600-800 decks 추가.

### 5.2 σL/σG/mobility/W/Temp → Full 8D (deck plan Stage 4)

- 3,000 Sobol 조건 × 6 Vop = 18,000 decks, MC 5,000 (~30h farm).
- **Vop만 grid 유지** (Vmin 보간 필요 — deck plan §Stage 4 논거 그대로).
- **Sobol sensitivity (Saltelli)** 를 full run 전 파일럿(500 decks)으로 먼저:
  10D 중 Vmin 분산 90%를 설명하는 top-k 식별 → full run 차원 축소 근거 + 논문 Table.

### 5.3 GP 확장성 결정 기준

| 훈련 포인트 | 모델 | 근거 |
|------------|------|------|
| ≤ 5K | ExactGP (현행) | Cholesky 수 초 수준 |
| 5K–20K | ExactGP + CG/LOVE (gpytorch 기본 최적화) | 15K는 경험상 가능, 메모리 배치 필수 |
| > 20K 또는 반복 재학습(AL) | SVGP (inducing 1-2K) | ELBO 학습, physics 제약은 anchor 방식 유지 |

- Additive kernel을 **그룹 구조로 확장**: k_device(cn,pu,skew) + k_process(σL,σG,μ_mob,W)
  + k_operating(Vop,WLUD) + k_temp(T) — deck plan의 그룹 정의와 일치. 그룹별 ARD로
  해석성(민감도 순위) 유지 — 논문 Discussion 재료.

### 5.4 Write margin (Vtrip) 방향 정의 — **미결 사항, Phase 4 착수 전 결정 필요**

deck plan Stage 3의 open question. 제안:
- Read SNM과 동형이 되도록 **WSNM(write static noise margin)** 정의 채택: write 조건
  butterfly에서 "닫힌 눈"의 여유 → μ_WSNM/σ_WSNM z-score → Vmin_write = z-crossing.
  (로브 통계는 read와 동일하게 §3.2.1 lobe-resolved 처리)
- `Vmin_cell = max(Vmin_read, Vmin_write)` — **주의 (리뷰 B5)**: smooth-max(LSE_β)는
  교차점에서 ln2/β 편향 (β=50 → 13.9mV, 목표 정확도의 5배). 따라서
  (i) **평가는 exact max**, (ii) gradient 최적화는 constraint 정식화
  (`Vmin_read ≤ t ∧ Vmin_write ≤ t`)를 우선 — assist 문제에 더 자연스럽고
  편향 無. smooth-max를 쓸 경우 β ≥ 500 (편향 < 1.4mV).
- 파일럿은 **Phase 2 Step F'로 조기 편입** (리뷰 A2): 20 cond × 2 temp로
  WLUD의 read/write 상충 dual-metric 데모 확보. hot-read/cold-write 지배
  가정 검증 후 full run.

---

## 6. Phase 5 — 논문 작성

### 6.1 타깃/포맷 결정

| 순위 | 벤ュー | 판단 기준 |
|------|--------|-----------|
| 1 | **IEEE TCAD** | 방법론+실험 full story(10-12p). Phase 2+3 완료 시점에 초고 착수 |
| 2 | DAC/ICCAD (6p) | TCAD 리뷰가 늦거나 Phase 4까지 기다릴 수 없을 때 압축판 |
| 3 | TVLSI | TCAD reject 시 재타깃 (SRAM 특화 어필) |

**결정 규칙**: Phase 2 GO + Phase 3의 §4.1-4.3 완료 시점에 TCAD 초고 착수.
Phase 4(8D)는 TCAD면 본문, DAC면 future work로 강등 가능한 모듈형 구성.

### 6.2 논문 뼈대 (섹션 → 근거 자료 매핑)

```
1. Introduction
   - Vmin이 SRAM yield 지배 + MC 비용 문제 (paper_en.md §1.1 재사용)
   - 기여 4개: (a) inverse formulation via differentiable physics layer,
     (b) physics-constrained GP (corner anchor 중심), (c) noise-aware GP로
     MC 통계/multi-fidelity 통합, (d) budget-accuracy 설계 가이드
2. Background & Related Work
   - §6.5 포지셔닝 표. z-score margin 관행 + tail 한계 명시 (§4.5 framing)
3. Method
   3.1 문제 정식화: X → (μ,σ) → Z(Vop) → Vmin, censored 정의 포함
   3.2 GP 구조 (표준화, ARD, additive sigma kernel) — "표준화가 1차 요인"
       교훈을 ablation으로 정직하게 보고 (session_20260706 §5)
   3.3 Physics constraints (anchor=data augmentation, mono/pelgrom=penalty)
   3.4 Differentiable inversion (§4.1) + piecewise-differentiability 논거
   3.5 Noise-aware/multi-fidelity (§3.5, §4.4)
   3.6 Contour-targeted active learning (§4.3)
4. Experimental Setup
   - Analytic testbed (통제 실험) + HSPICE 14nm-class PDK (실검증)
   - 지표 정의: design-range feasibility, assist-active Vmin RMSE, censored
     처리 — 정의 자체가 기여임을 명시 (naive 지표는 60×를 과대평가:
     0.16V vs 2.6mV — 이 대비를 표로)
5. Results
   5.1 Forward 정확도 (Stage 4/5 실데이터)
   5.2 Inverse 정확도 (assist map + gradient inversion 수렴)
   5.3 Ablation (physics 제약, 재실행 수치)
   5.4 Budget Pareto + AL 커브 + fidelity allocation
   5.5 (Phase 4 완료 시) 8D 민감도 + σL tolerance 시나리오
6. Discussion: lengthscale 해석(PG≫PU), tail 한계, GP→NN 전환 조건
7. Conclusion
```

### 6.3 Figure 리스트 (12개, 소스 스크립트 명기)

| # | Figure | 소스 |
|---|--------|------|
| F1 | 파이프라인 다이어그램 (X→GP→Z→Vmin→inverse) | 신규 작도 |
| F2 | Butterfly/z-curve/censoring 개념도 | 신규 작도 |
| F3 | HSPICE Vmin contour: GP vs MC hold-out overlay + corner 4점 | `demo.py` 실데이터판 |
| F4 | 지표 아티팩트 대비 (naive vs corrected inverse RMSE) | `validate_assist_sweep.py` |
| F5 | Required-assist map (물리 정합 주석) | `demo_assist.py` (완성) |
| F6 | Gradient inversion 수렴 궤적 on contour | §4.1 신규 |
| F7 | Ablation bar (baseline/±constraints, 오차막대) | `ablation.py` (seeds 추가) |
| F8 | Budget vs accuracy Pareto (전략 3종 × physics on/off) | §4.2 신규 |
| F9 | AL 커브 (straddle vs random vs Sobol) | §4.3 신규 |
| F10 | Fidelity allocation (동일 예산 배분 비교) | §4.4 신규 |
| F11 | MC 히스토그램 QC + Q-Q (z-crossing 근방) | §3.4 파서 |
| F12 | (P4) Sobol sensitivity + 8D lengthscale 그룹 | §5.2 |

### 6.4 Claim–Evidence 매핑 (리뷰 대비 체크리스트)

| Claim | Evidence | 상태 |
|-------|----------|------|
| Inverse accuracy few-mV | Stage 3 교정 지표 (2.6-4.9mV) + 실데이터 재현 | toy ✅ / 실데이터 ⬜ |
| Corner anchor 저비용 고효율 | ablation −27% + budget 저예산 구간 분석 | 부분 ✅ (§4.2로 강화) |
| Differentiable → gradient inversion 동작 | §4.1 데모 + bisection 교차검증 | ⬜ |
| Noise-aware GP가 MC 예산 흡수 | §4.4 allocation 실험 | ⬜ |
| AL 2× budget 효율 | §4.3 에뮬레이션 | ⬜ |
| 지표 정의의 중요성 (60× 왜곡) | 0.16-0.26V vs 2.6-4.9mV 대비표 | ✅ |

### 6.5 Related Work 포지셔닝 (갱신판)

| 기존 연구 | 그들 | 우리 차별점 |
|-----------|------|------------|
| Guo 2024 (MFNN+IS) | forward yield, variation space | **inverse**, physical space, GP-native fidelity 통합 |
| Yin 2022 (BYA) / 2023 (ASDK) | forward AL | **contour-targeted** AL (physics layer 통과 acquisition) |
| Liu 2023 (OPTIMIS) | tail 정밀 (IS) | margin-metric surrogate + censored 지표 체계 (상보적 — 인용으로 방어) |
| Gupta 2021 | analytic Vmin 모델 | ML 유연성 + physical param 확장 + 제약 학습 |
| Xing 2026 (TabPFN) | zero-hyperparameter | physics 제약 주입 + budget 설계 가이드 |

### 6.6 예상 리뷰어 공격 → 방어 (Threats to Validity)

| 공격 | 방어 |
|------|------|
| "Z=μ/σ Gaussian 외삽은 tail에서 무효" | §4.5 3중 방어 (framing + QC figure + IS 스팟체크) |
| "toy analytic 검증은 자기충족적" | analytic은 통제 실험으로만 사용, 모든 headline은 HSPICE 수치 |
| "physics 제약 효과가 작다 (0.9 vs 1.26mV)" | 저예산 구간(§4.2)과 tail(p95 −37%)에서 효과 집중을 명시 — 절대치가 아닌 조건부 가치 |
| "bisection이면 되는데 왜 differentiable?" | 고차원 시나리오(σL, Pareto)에서 grid 불가 — gradient만 확장 가능 + F6 시연 |
| "PDK 비공개로 재현 불가" | analytic testbed 코드 공개 + 정규화 축 실데이터 (§6.7) |

### 6.7 사내 데이터 반출 전략 (리드타임 주의 — Phase 2 시작과 동시 착수)

- 축 정규화: ΔVth를 σ_G 단위로, Vmin을 ΔVmin(TT 대비 mV)로, 절대 전류/치수 비공개
- 공정명 → "advanced FinFET node"로 익명화, 상대 개선율 중심 보고
- **사내 승인 프로세스를 Phase 2 Step C 제출과 동시에 시작** (통상 수 주 소요 가정)

### 6.8 paper_en.md v0.3 → v0.4 갱신 목록 (즉시 실행 가능)

- [ ] §3.1 ablation 표 전면 교체 (세션 20260706 §5 수치) — "20.9%" 문장 폐기
- [ ] §1.3 기여표 재평가: censored/assist-active 지표 정의 + noise-aware GP 추가
- [ ] §2.5 표준화 섹션을 "1차 요인" 교훈으로 격상, §4.3(PG≫PU) lengthscale 실험 반영
- [ ] Stage 3 inverse 결과 (2.55mV, feasibility 100%) 추가
- [ ] Z_target 유도(6.64) 및 censoring 정의 수식화

---

## 7. 리스크 매트릭스

| # | 리스크 | 조기 신호 | 완화 |
|---|--------|-----------|------|
| 1 | Farm 큐 지연 | Step C 제출 후 24h 미착수 | MC 2,000으로 감축 + noise-aware GP로 흡수; 검증점만 10K 유지 |
| 2 | 실데이터 히스토그램 비정규/bimodal | §3.4 QC fail 다수 | censored 분류 원칙 적용; z-crossing 근방만 Gaussian 요구 |
| 3 | 실데이터에서 additive sigma kernel 부적합 | sigma 잔차의 (cn,pu) 구조 | full ARD kernel fallback (모델 스위치는 1줄) + 논문에 kernel 선택 근거로 역이용 |
| 4 | ExactGP 확장성 — Stage 5는 6,000 rows로 **문제없음** (초판의 "36K rows"는 산술 오류였음, 리뷰 C1). 실제 리스크는 Stage 4 8D의 18,000 rows | Stage 4 학습 > 30min/OOM | §5.3 기준따라 SVGP 전환 |
| 5 | PG≫PU 계층 불성립 (실데이터) | Stage 4 lengthscale 표 | 원인 분석(입력 상관, 범위 비대칭). Go 게이트 아님 — Discussion 재료. **headline 민감도는 derivative/Sobol 기반으로, lengthscale은 정성 근거로만** (리뷰 C4) |
| 6 | Write margin 미편입 시 inverse assist가 반쪽 최적화로 공격받음 (리뷰 A2) | — | Step F' 파일럿 조기 편입 (§5.4). 지연 시 fallback = "read-limited" 명시 스코핑 + 주장 강도 하향 |
| 7 | 데이터 반출 승인 지연/거부 | 승인 > 3주 | 정규화 축 선반영 (§6.7) + **ASAP7 공개 PDK 병렬 트랙** (아래 #9) |
| 8 | Tail 가정 공격 | — | §4.5 선제 방어 + **lobe-resolved Z_eff (§3.2.1)가 1차 방어선** — min-통계 편향(+0.7~1.9σ)을 정량 교정했음을 명시 |
| 9 | 사내 PDK 단일 의존 = 논문 좌초 리스크 + 재현성 공격 (리뷰 A4) | 승인 프로세스 정체 | **ASAP7 (공개 FinFET, HSPICE 호환) Stage 4 축소 재현** (50 cond × 6 Vop, MC 2K, ~3-4일) 을 Phase 2 병렬 트랙으로. 사내 데이터 확보 시 보조 검증으로 강등, 실패 시 주 실험으로 승격 |

---

## 8. 일정 (2026-07-07 기준, 1인)

```
W1 (7/07-7/11)  P2 Step A-C: validation deck + QC + 본실행 제출 (farm 대기 시작)
                P3 병렬: noise-aware GP 구현(§3.5), budget Pareto 스크립트(§4.2)
                §6.7 데이터 반출 승인 프로세스 개시
W2 (7/14-7/18)  P2 Step D-E: 파싱/QC/GP/Go-No-Go → Stage 4 판정
                P3: gradient inversion 데모(§4.1) — toy 완성
W3 (7/21-7/25)  P2 Step F-G: Stage 5 (4D+Vwl) farm + TT bias
                P3: AL 에뮬레이션(§4.3), fidelity allocation(§4.4)
W4 (7/28-8/01)  P2/P3 실데이터 재실행 (Pareto/AL/inversion을 HSPICE GP로)
                paper_en.md v0.4 (§6.8)
W5-6            P4: skew 파일럿 + Sobol sensitivity 파일럿 + Vtrip 파일럿(§5.4)
W7-8            TCAD 초고 (§6.2 뼈대, F1-F11)
W9-10           내부 리뷰 → 수정 → 8D full run 착수 여부 결정 (TCAD 본문 vs 후속)
W11+            제출. 8D full은 리뷰 기간 중 병행 → major revision 대비 탄약
```

**주간 체크포인트 규칙** (AGENTS.md 세션 규칙 연동): 매주 금요일
`docs/decisions/`에 주간 요약 md 생성 + `workflow_state.json` phase 갱신.

---

## 9. 즉시 착수 가능한 작업 (우선순위순)

### 9.1 완료 (2026-07-07 구현 세션)

1. ✅ **lobe-resolved Z_eff** — `src/utils.py`: `bvn_cdf()` (Owen's T 기반
   bivariate normal CDF, scipy 대비 max err 4e-15), `z_eff_from_lobes()`,
   `effective_mu_sigma()` (y=(N,2) 규약 보존, mu_eff/sigma_eff == Z_eff).
   `tests/test_zeff.py` 8개 (scipy 대조, MC 검증, A1 편향 회귀고정 +0.697σ).
2. ✅ **noise-aware GP** — `models.py` likelihood 주입 인자, `surrogate.py`
   `fit(y_noise=)` + `FixedNoiseGaussianLikelihood(learn_additional_noise)`,
   save/load에 noise 배열 포함 (하위호환 유지). `tests/test_noise_aware.py`:
   오염 데이터에서 mu RMSE 0.00587→0.00204, roundtrip, 무노이즈 하위호환.
   부수 수정: `Surrogate.load`의 `weights_only=True` 잠재버그(numpy 메타데이터
   언피클 실패) → `weights_only=False` (자체생성 신뢰 파일).
3. ✅ **파서 QC 확장** — `hspice_io.py`: `bootstrap_sem()`, `condition_qc()`
   (AD 정규성/skew/kurtosis/fail-mix), `lobe_mc_summary()`, `write_qc_report()`.
   `data.py`: `save_with_noise()`/`load_with_noise()` (n_mc/sem/censored/extras,
   하위호환). `tests/test_parser_qc.py` 5개 (실 .mt0은 Step A에서 연결).

### 9.2 다음 착수 (남은 병렬 작업)

4. **budget Pareto 스크립트** — `scripts/budget_pareto.py` (§4.2, 10 seeds×전략, 밤샘 CPU)
5. **gradient inversion 데모** — `scripts/demo_gradient_inversion.py` (§4.1,
   다변수 시나리오 + censored barrier)
6. **ASAP7 병렬 트랙 착수** — deck 템플릿 이식 (리뷰 A4; 사내 farm과 독립)
7. **paper_en.md v0.4** — stale 수치 교체 (§6.8)
8. (farm 접근 가능해지는 즉시) **Step A validation deck 실행** (로브별 측정 포함)
```
