# 적대적 학술 검토 (Adversarial Review) — 방법론 + Phase 2 계획

> 작성일: 2026-07-07
> 대상: `docs/plans/phase2_to_paper_plan.md` + 기저 방법론 전체 (GP surrogate →
> z-score → Vmin → inverse)
> 방식: TCAD Reviewer #2 관점. 각 지적은 **정량 근거**(이 세션에서 수치 검증) +
> 처방 포함. 검증 결과 "문제없음"으로 판명된 항목도 §D에 기록 (균형 유지).
>
> **총평**: 방법론 골격(GP+physics layer+교정 지표)은 건전하다. 그러나 논문
> 생사를 좌우할 Critical 4건이 있고, 그중 A1은 현재 계획된 y-정의에 **주장
> 정확도(2.6mV)의 수십 배에 달하는 구조적 낙관 편향**을 만들 수 있다. 모두
> Phase 2 착수 전 설계 변경으로 해결 가능 — 지금이 잡을 수 있는 마지막 시점.

---

## A. Critical — 논문 승패/타당성 좌우

### A1. min-of-lobes에 Gaussian z-score 적용 시 구조적 낙관 편향 (+0.7~1.9σ)

**문제**: Read SNM의 관례적 정의는 두 로브(eye)의 min: `SNM = min(L, R)`.
현 계획은 MC 샘플별 SNM(=min)의 (μ, σ)를 취해 `Z = μ/σ → Φ(−Z)`로 tail을
외삽한다. 그러나 **min의 분포는 좌측 꼬리가 moment-matched Gaussian보다
무겁다** — 로브가 각각 Gaussian이어도 min은 아니다.

**정량 검증** (이 세션, bivariate normal 닫힌형 + MC 200만 샘플 교차확인):

| 로브 상관 ρ | Z_gauss(min) | Z_true | 편향 | Vmin 영향 (dZ/dVop≈10/V) | p_fail 과소평가 |
|:-----------:|:------------:|:------:|:----:|:-----------------------:|:---------------:|
| −0.7 | 7.77 | 5.89 | **+1.89σ** | ~+189 mV 낙관 | 500,000× |
| −0.3 | 7.00 | 5.89 | **+1.11σ** | ~+111 mV | 1,500× |
| 0.0 | 6.58 | 5.89 | **+0.70σ** | ~+70 mV | 83× |
| +0.5 | 6.11 | 5.89 | +0.22σ | ~+22 mV | 3.8× |
| +0.9 | 5.92 | 5.90 | +0.02σ | ~+2 mV | 1.1× |

(조건: 로브별 Z=6, 대칭. Z_true = Φ⁻¹[P(L<0)+P(R<0)−P(both<0)])

**왜 치명적인가**: SRAM 문헌(Bhavnagarwala 2001 등)에서 두 로브는 비대칭
mismatch에 대해 **반대 방향으로 반응(음의 상관 성분)** — 한쪽 눈이 줄면
반대쪽이 커진다. ρ가 0 이하라면 편향은 주장 정확도(2.6mV)의 **30~70배**.
Toy에서는 analytic (μ,σ)를 직접 생성하므로 이 문제가 **구조적으로 보이지
않는다** — 실데이터 y-생성 단계에서만 나타난다. IS 계열 리뷰어(Liu 2023
저자군)가 정확히 노리는 지점이기도 하다.

**처방** (Phase 2 파서 설계에 반영, 비용 미미):
1. MC 샘플마다 **로브별 SNM(L, R)을 따로 기록** — HSPICE `.MEASURE` 2줄
   (ngspice 템플릿의 snmr1/snmr2와 동형). 
2. (μ_L, σ_L, μ_R, σ_R, ρ_LR)에서 **lobe-resolved 유효 z**:
   `p_fail = P(L<0) + P(R<0) − P(L<0, R<0)` (bivariate Φ, 닫힌형·미분가능)
   → `Z_eff = Φ⁻¹(1−p_fail)` → 기존 physics layer 무수정 사용.
3. Step A 파일럿에서 **ρ_LR을 실측**해 편향 크기를 확정 — ρ > 0.9로 나오면
   기존 min 방식과 병기, 아니면 lobe-resolved가 기본.
4. 논문 재료로 역이용: "표준 margin 관행의 tail 편향을 정량화·교정" —
   방어가 아니라 기여가 된다.

**공정한 유보**: 사내 flow의 SNMR 측정이 이미 per-side/worst-side 정의라면
편향 크기는 달라진다 — 그래서 처방 3(실측)이 선행 조건이다. 또한 GP surrogate
자체는 무엇을 y로 주든 학습하므로, 이것은 **surrogate의 결함이 아니라
y-정의(라벨) 설계의 결함**이다.

### A2. WLUD assist 역추정이 write margin 상충을 무시 (read-only의 논리 공백)

**문제**: WL underdrive는 read 안정성을 **올리고 write 능력을 내린다** — 고전적
트레이드오프. 현 inverse assist("Vmin_read=0.6V를 위한 WLUD 추천")는 write
제약 없는 단방향 최적화다. 추천된 WLUD가 write-Vmin을 위반하면 산업적으로
무의미하며, 심사자(산업계)가 반드시 지적한다. `Vmin_cell = max(read, write)`는
원 계획에도 있으나(§6) Phase 4로 밀려 있다.

**처방** (양자택일, 착수 전 결정):
- (a) **명시적 스코핑**: 논문 전체를 "read-limited Vmin regime"으로 한정하고
  Intro/Limitations에 WLUD-write 상충을 명시 + write 확장은 future work.
  Phase 2 일정 유지. 단, "inverse assist 추천" 주장의 강도를 낮춰야 함.
- (b) **조기 편입**: deck plan Stage 3의 write margin 파일럿(20 cond)을 Phase 2
  Step F 직후로 당겨 dual-metric 데모 1개(assist 추천에 write 제약 추가)를
  확보. 논문 주장 온전, 일정 +1주.
- 권고: **(b)** — inverse가 main novelty(accept 조건 1)이므로 반쪽 제약 최적화는
  novelty 자체를 깎는다.

### A3. Corner anchor의 학습/검증 이중사용 (실험 설계 결함)

**문제**: Phase 2에서 L_boundary anchor 값은 corner MC 측정에서 와야 하는데,
같은 corner 4점이 Step D의 검증점이기도 하다. anchor로 넣은 점의 검증 오차는
자명하게 작아져 corner validation이 무의미해진다 (toy에서는 anchor가 analytic
truth에서 왔으므로 문제가 없었다 — 실데이터에서 처음 발생하는 결함).

**처방**: 검증 지점을 이원화 — (i) physics-constrained GP의 corner 성능은
**anchor 미포함 config**(plain 또는 boundary-off)로만 평가, (ii) anchored GP의
검증은 corner가 아닌 **hold-out ring**(코너 인접 ±10mV 오프셋 4×2점 + 내부
20점)으로. deck 8개 추가면 충분.

### A4. Public-PDK fallback 부재 (단일 실패점 + 재현성 공격)

**문제**: 논문의 headline 수치는 전부 사내 PDK 의존(§6.6 방어 논리 자체가
"headline은 HSPICE"라고 못박음). 반출 승인이 거부/지연되면 좌초. 동시에
"analytic testbed 코드 공개"만으로는 재현성 요구(최근 TCAD/DAC 추세)에 약하다.
ngspice 트랙은 보류 중이고 그 카드도 수리된 비공인 카드라 publication-grade가
아니다.

**처방**: **ASAP7**(공개 FinFET PDK, HSPICE 호환) 기반 Stage 4 축소 재현
(50 cond × 6 Vop, MC 2K). 이중 목적: (i) 승인 실패 보험, (ii) 논문의 재현
가능 실험 섹션.

**UPDATE 2026-07-07 (user 결정): ASAP7 트랙 DEFERRED (기본 미실행).**
판단 근거: (a) TCAD/DAC 다수 산업 논문이 비공개 PDK + 상대 수치로 통과하며,
재현성은 **analytic testbed 코드 + 지표 정의/파이프라인 공개**로 방어 가능
(§6.6 방어 논리를 "analytic 공개 + 정규화 실데이터"로 조정). (b) ASAP7은
novelty에 기여하지 않는 보조 검증. **잔여 리스크(명시)**: ngspice 트랙이 OSDI
미지원으로 막혀 있어 ASAP7까지 빼면 로컬 실리콘-급 검증 경로가 0 → 논문
실데이터가 100% 사내 farm 의존. **조건부 재활성화 트리거**: 사내 반출 승인이
거부되거나 3주 이상 정체되면 ASAP7을 주 실험으로 승격 (deck 이식 3-4일).

---

## B. Major — 주장/설계의 약점

### B1. "Multi-fidelity" 리브랜딩 리스크
SEM 기반 heteroscedastic noise는 기술적으로 옳지만, 문헌의 multi-fidelity(모델
충실도 차이, bias 있는 low-fi)와 다르다. 심사자: "이건 MF가 아니라 표본수
가중이다." **처방**: 명칭을 "noise-aware MC budget allocation"으로 정직하게
포지셔닝하고, accept 조건 4의 'multi-fidelity' 충족 주장은 (i) 이 재명명으로
낮추거나 (ii) 진짜 이질 fidelity(예: MC vs analytic 모델을 low-fi로 하는
co-kriging) 1개 실험을 추가해 지지. 권고: (i) + Discussion에서 (ii)를 future로.

### B2. Gradient inversion 데모 시나리오 선택 모순
계획된 데모(Scenario D, 2D 경계 추적)는 **grid/bisection이 더 잘하는 문제** —
"왜 gradient인가"의 §6.6 방어("고차원에서만 gradient가 확장")와 정면 모순.
**처방**: 데모를 다변수 동시 역추정(예: (WLUD, σL_mult) 2-자유도에서 Vmin=0.6
등고면 위 최소-assist 해 탐색, 또는 Phase 4의 σL tolerance)으로 교체. 2D 경계
추적은 bisection 교차검증용으로만 사용.

### B3. AL acquisition의 posterior 샘플링 — joint 필수
Vmin(x)는 같은 (cn,pu)의 **Vop 6점에서의 μ,σ에 동시 의존** — 6점을 marginal로
독립 샘플링하면 인위적 crossing이 생겨 Vmin 분산 과대평가 → acquisition 왜곡.
**처방**: (cn,pu)별 Vop-slice 6점의 **joint posterior 샘플**(6×6 공분산, 비용
무시 가능)을 명세에 못박기. μ-GP/σ-GP 간 독립 가정은 한계로 명시.

### B4. "60× 지표 아티팩트" 기여 framing
"naive 0.16V vs corrected 2.6mV"의 naive는 **우리 자신의 이전 버그** — 이를
기여로 팔면 "자기 오류 수정이 기여인가"라는 역공을 부른다. **처방**: 교정된
지표 **정의 체계**(censoring/design-range/assist-active)를 기여로 제시하고,
아티팩트 대비는 "이 정의가 없을 때 생기는 왜곡의 예시"로 한 문장만. F4 figure
캡션 톤 조정.

### B5. smooth-max(β=50)의 정량 편향
`Vmin = smoothmax(read, write)`에서 LSE_β 편향은 교차점에서 ln2/β = **13.9mV**
(β=50) — 목표 정확도의 5배. **처방**: 평가는 exact max, 최적화 중에만 smooth
사용(β≥500, ln2/β<1.4mV) 또는 constraint 형태(`Vmin_read≤t ∧ Vmin_write≤t`)로
재정식화 — 후자가 assist 문제에는 더 자연스럽다.

### B6. Go/No-Go 임계의 순환성
`max(15mV, 2×repeatability)`는 데이터가 나쁠수록 기준이 풀려 GO가 보장되는
구조. **처방**: 임계는 응용 요구(스펙 해상도, 예: 10-15mV)에 고정하고,
repeatability가 임계의 절반을 넘으면 **기준 완화가 아니라 검증 MC 증량**(N을
4×)으로 대응한다는 규칙으로 교체.

---

## C. Minor / 기대치 관리

| # | 지적 | 처방 |
|---|------|------|
| C1 | 계획 §7.4의 "Stage 5 = 6,000×6=36K rows"는 **산술 오류** — 6,000 deck 자체가 (cn,pu,Vop,Vwl) 행이므로 GP rows=6,000. ExactGP로 충분 | 계획 수정 (확장성 리스크는 Stage 4의 18K rows로 이동) |
| C2 | TT repeatability를 n=2 반복으로 추정 — χ²(1) 수준으로 무의미 | n≥5 반복 |
| C3 | SEM_σ = σ/√(2N)은 Gaussian 전제(kurtosis 민감) | 파서에서 bootstrap SEM 병행, QC에 kurtosis 추가 |
| C4 | ARD lengthscale ≠ sensitivity (선형 함수의 ls는 range/noise 반영) | headline 민감도는 derivative/Sobol 기반, ls는 정성 근거로만 |
| C5 | Vop 100mV grid 선형보간 편향 | **검증 완료: toy에서 −0.6mV, steep-σ 가정에서도 −0.3mV → 무시 가능**. 실데이터 Step A에서 1회 재확인 + 필요시 PCHIP(단조 C¹, 미분가능) 옵션 |
| C6 | Hausdorff sub-mV 차이는 contour 추출 grid 분해능(40×40) 노이즈 수준 | config 간 0.1-0.2mV 차이 해석 금지, Vmin RMSE를 주지표로 |
| C7 | "feasibility 100%", "2.6mV"는 toy(저노이즈) 수치 — 실데이터 목표치로 전이 금지 | 실데이터 목표는 노이즈 플로어에서 유도해 별도 설정 (계획 §3.1) |
| C8 | gradient inversion에서 censored 영역(상수 0.35V) 진입 시 기울기 소실로 조용히 정지 | censored 영역에 barrier 페널티 또는 마스킹 처리 명세 |
| C9 | Budget Pareto 5 seeds는 CI가 넓음 | headline figure는 10 seeds (analytic은 비용 무시 가능) |
| C10 | Related work 누락 영역: SRAM variability 고전(Bhavnagarwala, Calhoun), GP 기반 yield 선행연구, conformal/calibrated surrogate | W2에 체계적 문헌 탐색 태스크, novelty 문장 사전 검증 |

## D. 검토 결과 "문제없음"으로 판명된 항목 (검증 근거 포함)

1. **Vop 보간 편향**: 수치 검증 결과 sub-mV (C5) — 우려 기각.
2. **Stratified split 누수**: (cn,pu) 조건 단위 그룹 분할이 Vop/WLUD 전체를
   묶음 — 누수 없음 (코드 확인).
3. **MC 표본수 fidelity의 무편향성**: μ̂는 무편향, σ̂의 c4 편향은 N=200에서
   0.13% — noise-aware 접근의 전제 성립 (단, B1의 명칭 문제는 별개).
4. **μ̂, σ̂ 추정 노이즈의 독립성**: Gaussian 표본에서 x̄⊥s² — 독립 GP 노이즈
   모델과 정합 (비정규성은 C3에서 처리).
5. **derive_z_target의 bit 독립 가정**: local mismatch 조건부 독립은 이
   framework(global shift = 입력)에서 정합적 — 단, 논문에 "조건부 Vmin" 정의를
   명시할 것.

## E. 계획 문서에 즉시 반영한 수정 (이 리뷰와 동시 적용)

1. §3.2-3.4: 로브별 (L,R,ρ) 측정 + lobe-resolved Z_eff 파이프라인 (A1),
   Step B 반복 5회 (C2), anchor/검증 분리 규칙 (A3)
2. §4.1: 데모 시나리오 교체 (B2) + censored barrier (C8)
3. §4.3: joint Vop-slice 샘플링 명세 (B3)
4. §4.4: "noise-aware budget allocation"으로 재명명 (B1)
5. §5.4: smooth-max → constraint 정식화 우선 (B5)
6. §7: C1 산술 오류 수정, ASAP7 fallback 트랙 추가 (A4), write-margin 스코핑
   결정 항목 추가 (A2), Go/No-Go 규칙 교체 (B6)

## F. 종합 판정

- **방법론 코어(GP + physics layer + 교정 지표)**: 건전. Gate 0 결론 유지.
- **단, 실데이터 y-정의(A1)와 assist 스코핑(A2)을 고치지 않고 Phase 2를 돌리면**
  1,200-deck 데이터셋을 재생성해야 할 위험이 크다 — 두 항목은 **Step A 파일럿
  전 필수 반영**.
- A4(ASAP7)는 보험이자 재현성 자산으로 병렬 착수 권고.
- 논문 novelty 주장 중 'multi-fidelity'(B1)는 하향 조정이 정직하고 안전하다.
  나머지 기여(inverse+differentiable, 제약 GP, 지표 체계, budget 가이드)는
  A1 교정(lobe-resolved z)이 더해지면 오히려 강화된다.
