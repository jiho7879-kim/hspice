# SRAM Vmin Inverse Estimation: Physics-Constrained Adaptive Surrogate Modeling

> 작성일: 2026-06-30
> 목적: SRAM Vmin target (0.6V)이 주어졌을 때, 역으로 설계 자유도(Mb, σL, σG, PVTA, mobility, fin, W, L 등)의 feasible region을 최소한의 BSIM simulation으로 추정하는 방법론 정리 및 논문 가능성 검토

---

## 1. Problem Definition

### Forward (현재 flow)

```
[Design/Memory params] ─→ HSPICE MC 10k ─→ SNMR_μ,σ / Vtrip_μ,σ ─→ Zscore=μ/σ
    ─→ Poisson yield model ─→ Vmin
```

- 각 condition에서 HSPICE MC 10k 필요
- 고차원 parameter space에서 full factorial 불가능
- **Vmin이 나온 후에야** "어느 파라미터가 문제인지" 파악 가능

### Inverse (원하는 것)

```
Vmin_target = 0.6V 가 주어졌을 때, 다음을 역으로推定:
  ├─ Mb_max  = ?    (메모리 크기 제한)
  ├─ σL_max  = ?    (local variation tolerance — Pelgrom Avt 배수)
  ├─ σG_max  = ?    (global variation tolerance — Vth 3σ)
  ├─ ΔN, ΔP contour = ?  (PVTA design margin)
  ├─ μ_mobility 범위 = ?
  ├─ Nfin, W, L 범위 = ?
  └─ 모든 설계 자유도의 trade-off曲面 (Pareto front)
```

### 핵심 제약

1. **BSIM simulation은 비싸다** — MC 10k × 1 condition ≈ 5-10분
2. **Parameter space는 고차원** (10+ physical parameters)
3. **물리 법칙 위반 extrapolation은 안 됨** — monotonicity, Pelgrom scaling 등
4. **결과를 industry에서 바로 써야 함** — PVTA spec, Mb spec, σ spec으로 변환 가능해야 함

---

## 2. 핵심 결정: 어떤 출력 파라미터를 학습할 것인가?

### 비교 검토

| 후보 | 차원 | Vmin과의 관계 | 학습 난이도 | 판정 |
|------|------|--------------|-----------|------|
| **SNMR_μ/σ, Vtrip_μ/σ** | **4** | 직접 결정 (Vmin = max(Vmin_SNMR, Vmin_Vtrip)) | 낮음 (4출력) | ✅ **선택** |
| Full I-V/C-V curves | ~1000 | 간접 (→ SNMR 재계산 필요) | 매우 높음 (1000출력) | ❌ |
| Cell current (Iread, Iwrite) | 2-4 | 부분적, 단독 Vmin 결정 불가 | 중간 | ❌ |
| Zscore directly | 2 | 직접적, but Vop 의존성 혼재 | 중간 | ❌ |
| Vmin directly | 1 | 가장 직접적 | 낮음, but gradient 정보 손실 | △ 보조용 |

### 선택 근거

- **SNMR** = Read stability의 직접적 물리 척도
- **Vtrip** = Write ability의 직접적 물리 척도
- `Vmin = max(Vmin_SNMR, Vmin_Vtrip)` 관계는 대수적으로 명확 → 미분가능한 layer로 encode
- 출력 4개 스칼라 → **1000차원 I-V/C-V 학습 대비 sample efficiency 250배 우수**
- I-V/C-V 학습 시 오차 전파 2중 (I-V reconstruction error → SNMR extraction error)

---

## 3. Input Space 정의

### 학습 입력 벡터 (10차원)

| # | 파라미터 | 범위 | 단위 | 비고 |
|---|---------|------|------|------|
| 1 | `log2(Mb)` | [0, 8] | log2(Mb) → Mb=1~256Mb | 메모리 용량 |
| 2 | `σL_mult` | [0.5, 3.0] | 배율 | Pelgrom Avt의 배수 (1x=nominal) |
| 3 | `σG` | [0, 60] | mV (3σ) | Global Vth variation |
| 4 | `ΔN_Vtsat` | [-60, +60] | mV | NMOS PVTA shift |
| 5 | `ΔP_Vtsat` | [-60, +60] | mV | PMOS PVTA shift |
| 6 | `Temp` | [-40, 125] | °C | 온도 |
| 7 | `Vop` | [0.5, 1.0] | V | Operating voltage |
| 8 | `Nfin` | [1, 8] | 개수 | FinFET fin count |
| 9 | `W` | [0.1, 1.0] | μm | Device width (ratio) |
| 10 | `μ_mobility_mult` | [0.7, 1.3] | 배율 | Mobility multiplier |

> **Note**: Sobol sensitivity analysis로 Phase 0에서 top-5로 축소 가능.
> 실제로는 10개 중 3-4개가 Vmin variance의 90%+를 설명할 가능성 높음 (Singhee & Rutenbar 2010).

### 출력 벡터 (4차원)

`[μ_SNMR, σ_SNMR, μ_Vtrip, σ_Vtrip]` — 모두 Softplus activation으로 양수 제약

---

## 4. Sampling Method: LHS vs 더 나은 대안

### LHS의 한계

1. **고차원(10D+)에서 space-filling property 급감**
   - Stein (1987): LHS는 1D marginal uniformity만 보장
   - 고차원 correlation 구조는 최적화되지 않음
2. **Adaptive sampling 불가**
   - 한 번 sample size 결정 → 나중에 추가 불가
   - "이 영역을 더 보고 싶다"가 안 됨
3. **Vmin estimation에 특화되지 않음**
   - General-purpose DOE → Vmin 결정 boundary에서 oversampling 안 됨

### 대안 비교

| 방법 | Space-filling | Adaptive | Vmin-specific | 구현난이도 |
|------|:---:|:--------:|:-------------:|:--------:|
| Random MC | ✗ | △ | ✗ | ★ |
| **LHS** | △ (∼10D 한계) | ✗ | ✗ | ★★ |
| **Sobol QMC** | ○ (이론적 보장) | ✗ | ✗ | ★ |
| **Space-filling LHD** (Kinoshita 2025) | ○ | ✗ | ✗ | ★★★ |
| **Bayesian OED** (Active Learning) | ○ | **○** | **○** | ★★★★ |
| **Multi-fidelity + Active** | ○ | **○** | **○** | ★★★★★ |

### 최종 판단: Multi-fidelity Active Learning + Sobol Initialization

**Phase 0 (Initialization — Sobol 또는 Space-filling LHD):**
- 50-100 points로 cold start
- Sobol sequence가 LHS보다 space-filling 우수 (Singhee & Rutenbar, TCAD 2010)
- 2x-8x speedup over MC in circuit problems

**Phase 1-N (Active Learning Loop):**
- 각 iteration마다 Vmin prediction uncertainty가 가장 높은 영역에 5-10 points 추가
- Acquisition function = `Vmin_uncertainty(x) = Var(Vmin_SNMR) + Var(Vmin_Vtrip)`
- Batch acquisition으로 parallel HSPICE simulation 활용

**Multi-Fidelity 옵션:**
- Low-fi: MC=100 (빠름, noisy, 30초)
- High-fi: MC=10k (정확, 5분)
- GP bias correction으로 low-fi + few high-fi 조합

---

## 5. Surrogate Neural Network Architecture

### 권장: Residual MLP with Physics-Informed Constraints

```
Input(10) 
  → LayerNorm
  → Linear(10→128) + SiLU
  → ResBlock: [Linear(128→128) + SiLU + Linear(128→128)] × 4 (skip-connection)
  → ResBlock: [Linear(128→64) + SiLU + Linear(64→64)] × 2 (skip-connection)
  → Linear(64→4)
  → Softplus()  ← μ, σ는 항상 양수
```

### Loss Function (3항)

```
L_total = L_data + λ₁·L_mono + λ₂·L_pelgrom
```

| Term | 내용 | 역할 |
|------|------|------|
| `L_data (MSE)` | `(μ̂_SNMR − μ_SNMR)² + ...` | 기본 예측 오차 |
| `L_mono (Monotonicity)` | `ReLU(∂μ_SNMR/∂Vop < 0)²` | Vop↑→SNMR↑ 물리 법칙 |
| `L_pelgrom` | `ReLU(|σ_SNMR − Avt/√(WL)| − tol)²` | Pelgrom scaling 일관성 |

> **L_mono + L_pelgrom이 physical constraint 역할** — 데이터가 없는 extrapolation 영역에서도 물리적으로 타당한 예측 보장.

---

## 6. Differentiable Physics Layer (Fixed, No Training)

Surrogate 뒤에 붙어서 analytic computation을 미분가능하게 연결.

```
Step 1: Zscore 계산
  Z_SNMR(Vop) = μ_SNMR(Vop) / σ_SNMR(Vop)
  Z_Vtrip(Vop) = μ_Vtrip(Vop) / σ_Vtrip(Vop)

Step 2: Target Zscore from Poisson yield
  Nbits = Mb × 10^6 × 6         ← 6T SRAM bit 수
  P_fail_per_bit = 1 − Y_target^(1/Nbits)
  Z_target = −Φ⁻¹(P_fail_per_bit)  ← norm.ppf

Step 3: Vmin interpolation
  Vmin = Vop_low + (Z_target − Z_low) × (Vop_high − Vop_low) / (Z_high − Z_low)
  → 미분가능한 linear interpolation
  → ∂Vmin/∂μ, ∂Vmin/∂σ available via autograd
```

**왜 PINN이 아니라 Differentiable Physics Layer인가?**

| 구분 | PINN | Differentiable Physics Layer |
|------|------|---------------------------|
| 대상 | PDE residual을 NN loss에 추가 | Closed-form analytic model을 미분가능한 연산으로 구현 |
| Vmin 문제 적합도 | ❌ Vmin = max(...)는 PDE가 아님 | ✅ 정확히 Vmin 구조를 표현 |
| 구현 | 복잡 (PDE collocation points) | 간단 (PyTorch tensor 연산) |
| 정확도 | Soft constraint (근사) | **Hard constraint (정확)** |

---

## 7. Inverse Estimation: 4가지 시나리오

### Scenario A: Max Memory Size at Vmin=0.6V

```
Fix: σL=1x, σG=0, ΔN=0, ΔP=0, Temp=25, Nfin=nom, W=nom
Variable: log2(Mb) ∈ [0, 8]
Target: Vmin = 0.6V

방법: Adam optimizer가 Mb를 조정하며 loss = (Vmin_pred − 0.6)² 최소화
```

### Scenario B: Local Variation Tolerance

```
Fix: Mb=target, σG=0, ΔN=0, ΔP=0, Temp=25
Variable: σL_mult ∈ [0.5, 3.0]
Target: Vmin = 0.6V
Output: "Avt가 nominal의 1.8배까지 허용 가능"

→ 공정팀과의 negotiation에서 직접 사용 가능한 수치
```

### Scenario C: Global Variation Tolerance

```
Fix: Mb=target, σL=1x, ΔN=0, ΔP=0, Temp=25
Variable: σG ∈ [0, 60] mV
Target: Vmin = 0.6V
Output: "3σ global Vth variation 42mV까지 허용 가능"
```

### Scenario D: PVTA Contour (ΔN vs ΔP)

```
Fix: Mb=target, σL=1x, σG=0, Temp=25
Variables: ΔN ∈ [−60, +60], ΔP ∈ [−60, +60]
Target: Vmin = 0.6V

Output 2D contour:
         ΔP
      +60 ┌─────────────────┐
          │   Vmin > 0.6V   │
          │     (FAIL)      │
          │    ┌───────┐    │
      ΔN=0────┤Vmin≤0.6V├────  ← feasible
          │    └───────┘    │
          │   Vmin > 0.6V   │
      -60 └─────────────────┘
         -60     ΔN=0     +60

→ PVTA design spec으로 직접 변환
```

---

## 8. Multi-Objective Pareto Front (Extension)

**최종 목표**: 단일 숫자가 아니라 **설계 자유도의 trade-off surface**

```
목표: Vmin ≤ 0.6V
변수: Mb, σL, σG, ΔN, ΔP, Nfin, W (7개)
Pareto: 어느 하나를 개선하면 다른 하나가 나빠지는 경계면

방법:
  - NSGA-II (pymoo) 또는 Bayesian Optimization
  - Surrogate NN으로 Vmin 평가 (1 evaluation ≈ 1ms)
  - SPICE simulation zero 추가

예시 Pareto front:
  - 64MB, σL=1.0x, σG=15mV  → Vmin=0.58V (달성)
  - 32MB, σL=1.5x, σG=15mV  → Vmin=0.59V (달성)
  - 64MB, σL=1.5x, σG=15mV  → Vmin=0.63V (실패)
```

---

## 9. Simulation Budget vs Accuracy Pareto (논문의 핵심 contribution)

```
목적: "N개의 BSIM simulation으로 어느 정도의 inverse estimation accuracy를 얻을 수 있는가?"
       → Simulation budget decision guide for industry

방법:
  1. Total 2000 points dataset 생성 (LHS + Sobol 혼합)
  2. N=50, 100, 200, 500, 1000, 2000 으로 각각 surrogate 학습
  3. 각 budget에서 inverse estimation error 측정
  4. Budget vs RMSE curve 제시

기대 결과:
  - N=200에서 saturation 시작
  - N=500에서 full accuracy의 90% 달성
  - 즉, 2000 → 500으로 75% simulation reduction 가능
```

---

## 10. 실험 검증 계획

| 검증 항목 | 방법 | 목표 |
|----------|------|------|
| Surrogate accuracy | Hold-out test (N=200) | RMSE < 10mV, max error < 25mV |
| Inverse accuracy | True HSPICE Vmin vs predicted Vmin (20 points) | Error < 20mV |
| Active learning 효과 | Random acquisition vs OED acquisition 비교 | 동일 budget에서 2x lower error |
| Sampling 전략 비교 | LHS vs Sobol vs OED initialization | Sobol/OED 우세 확인 |
| Physics constraint 효과 | w/ vs w/o L_mono, L_pelgrom | Extrapolation quality 비교 |
| Multi-fidelity 효과 | Low-fi only vs high-fi only vs MFGP | 동일 budget에서 accuracy 비교 |

---

## 11. 논문 가능성 평가 (Publication Feasibility)

### 유사 연구 대비 차별점

| 기존 연구 | 접근법 | 당신의 차별점 |
|---------|--------|-------------|
| MFNN+IS (Guo 2024) | Multi-fidelity NN + IS, **forward** only, variation space | **Inverse**, physical parameter space |
| BYA (Yin 2022) | Bayesian active learning, **forward** only | **Inverse** formulation |
| ASDK (Yin 2023) | Deep kernel + feature selection, 1152D→48D | Physical parameter에서의 **inverse Pareto** |
| TabPFN YMCA (Xing 2026) | Foundation model, zero-hyperparameter | **Simulation budget vs accuracy Pareto** |
| OPTIMIS (Liu 2023) | Optimal manifold IS, forward only | **Differentiable physics layer**로 inverse 가능 |
| Gupta (2021) | Analytical Vmin model, 6% error | **Physical parameter 확장 + ML flexibility** |

### 목표 학회/저널

| 우선순위 | 학회/저널 | 이유 |
|:-------:|----------|------|
| **1순위** | **IEEE TCAD** (Trans. CAD) | Inverse estimation + surrogate 방법론, impact factor 높음 |
| **2순위** | **IEEE TVLSI** | SRAM + variation에 특화 |
| **3순위** | **DAC / ICCAD** | Fast turnaround, industry 관심 높음 |
| 4순위 | SISPAD | Simulation methodology |
| 5순위 | IEEE TED | Device 쪽에 치우칠 경우 |

### Accept 조건

**Publishable if:**
1. Inverse estimation formulation이 main novelty
2. Physical parameter space (mobility, fin, W, L)를 입력으로 포함
3. Simulation budget vs accuracy Pareto를 정량적으로 제시
4. Active learning + physics constraint + multi-fidelity 통합
5. Real industry PDK로 validation (TSMC/Samsung/etc.)

**Not publishable if:**
1. LHS + NN + forward Vmin estimation만 — Guo 2024, Yin 2022/2023이 이미 해결
2. σL, σG만 variation space — Gupta 2021이 analytical model으로 faster
3. Inverse estimation이 grid search 수준 — method novelty 부족

---

## 12. 실행 로드맵 (Timeline)

```
Week 1-2: PoC (2D toy: Vop + Mb만)
  ├─ LHS 50pt + GP surrogate
  ├─ Differentiable physics layer
  ├─ Vmin=0.6V inversion → Mb_max 추정
  └─ PoC 검증 → 논문 방향 확정

Week 3-4: Data generation
  ├─ Sobol sensitivity (10 physical params → top-5)
  ├─ Full dataset 2000pt (HSPICE farm, 100 cores → 1-2일)
  └─ Active learning emulation

Week 5-6: Model development
  ├─ Residual MLP + physics constraints
  ├─ Active learning loop
  ├─ Multi-fidelity GP extension
  └─ 4가지 inverse scenario 구현

Week 7-8: Validation + Paper writing
  ├─ Budget vs accuracy Pareto
  ├─ Baseline comparison (LHS, Sobol, random, OED)
  ├─ Paper draft (IEEE TCAD or DAC format)
  └─ Review iteration
```

---

## 13. 실무적 조언

### 1. PINN naming은 피할 것
Vmin 문제는 PDE가 아니라 closed-form analytic model이 존재. "Physics-informed surrogate" 또는 "Differentiable physics layer"가 더 정확하고 reviewer 반응도 좋음.

### 2. 첫 PoC는 2D (Vop + Mb)로
첫 주에는 Vop + Mb 2D sweep만으로 surrogate → differentiable layer → inversion pipeline이 동작하는지 검증. 이후 확장.

### 3. Sobol sensitivity부터 먼저
10개 파라미터 중 실제로 Vmin에 significant한 것은 3-4개일 가능성 높음. 먼저 sensitivity analysis로 effective dimension을 낮추고 시작.

### 4. Inverse scenario 중 가장 임팩트 큰 순서
```
PVTA contour (D) > σL tolerance (B) > Mb limit (A) > σG tolerance (C)
```
PVTA 결과가 공정-설계 협의에서 가장 강력한 negotiation card.

### 5. Simulation budget decision guide가 가장 실용적 value
"200회 MC로 90% 정확도 달성 가능" 같은 quantitative guide는 industry에서 바로 adoption 가능. 논문의 citation을 높이는 핵심 figure.

---

## 14. Toy Project: Feasibility Verification (실현 가능성 검증)

> **목적**: Inverse estimation의 핵심 아이디어 — surrogate → differentiable physics layer → inversion — 이 실제로 동작하는지 **실제 HSPICE MC 10K 데이터**로 검증
> **핵심**: Model 구축 후에는 HSPICE run이 0이 되는 구조. 초기 데이터 투자는 **1회성 고정비용(fixed cost)**이며, 이후 모든 Vmin 예측은 inference만으로 해결 → 투자 대비 ROI가 매우 높음
> **검증 인자**: **PVTA contour (common_N_shift vs PU_shift)** — industry standard, MHC 교차 검증 직접 활용
> **투자**: 1인, 2주, HSPICE MC 10K × **~1200 conditions (≈5시간, parallel farm)** + Python prototyping
> 
> > **핵심 마인드**: "최소한의 simulation"이 목표가 아니다. Model quality를 보장할 수 있을 만큼 충분히 투자하고, 그 결과로 HSPICE-free prediction을 얻는다. 700 runs에서 아꼈다가 interaction 놓쳐서 실패하는 것이 가장 큰 손실.

---

### 14.1 설계 결정: 왜 PVTA Contour인가?

#### NMOS Device: PG와 PD는 같은 Shift를 받는다

6T SRAM cell에서 PG(pass gate)와 PD(pull-down)는 모두 **NMOS**이므로, PVTA variation에 대해 기본적으로 **같은 방향, 같은 크기**로 shift된다.

```
PG_shift = PD_shift = common_N_shift  (nominal 가정)
```

즉 ΔN_Vtsat 하나로 두 NMOS device의 shift가 동시에 결정된다. 이는 현업 PVTA 분석에서도 일반적인 가정이며, PG-PD 간 skew는 별도의 mismatch parameter로 다룬다.

| 검증 인자 | 물리적 nonlinearity | GP 학습 난이도 | Industry value | MHC 연계 |
|-----------|:-------------------:|:--------------:|:--------------:|:--------:|
| ~~Mb~~ | ❌ Poisson yield 공식으로 analytic 결정 | GP 불필요 | △ Mb spec은 trivial | ❌ |
| ~~σL_mult~~ | ⭕ Partial | 중간 | ⭕ | ⭕ |
| **common_N_shift vs PU_shift (PVTA)** | **✅✅ Asymmetric device interaction (NMOS vs PMOS)** | **⭐ GP 진짜 성능 검증** | **✅✅✅ PVTA spec, MHC 교차 검증** | **✅✅✅** |
| PG-PD skew (extension) | ✅✅ Finer-grained asymmetry | ⭐⭐ 추가 검증 | **✅✅✅✅ PG-PD mismatch spec** | ✅✅✅✅ |

**선택 근거:**
1. **Asymmetric nonlinearity** — NMOS(common_N_shift)와 PMOS(PU_shift)의 Vtsat shift가 SNMR에 미치는 영향이 qualitatively 다름 → **GP surrogate의 진짜 학습 능력 검증**.
2. **Industry standard** — PVTA contour (ΔN vs ΔP)는 현업에서 spec 협의, Si 벤더 negotiation, **MHC (Measurement-Hardware Correlation)** 검증에 이미 사용 중.
3. **Full paper Scenario D (Sec.7, 1순위)** 로의 확장 경로 명확.
4. **PG-PD skew**로의 자연스러운 확장 — toy project에서 검증한 pipeline에 skew 차원 하나만 추가하면 됨.

#### Ultimate Goal: N/P Split Full Parameter Space

Toy project (PVTA contour 3D) → PG-PD skew (4D) → 최종적으로는 **N와 P 각각의 variation/mobility**에 대한 Vmin 역추정:

| 단계 | Input space | 검증 대상 | 비고 |
|------|------------|-----------|------|
| **Toy project** (지금) | [common_N_shift, PU_shift, Vop] 3D | PVTA contour feasibility | PG=PD 동일 shift, Temp=125°C 고정 |
| **Step 2** | [+ PG-PD skew] 4D | Skew tolerance | PG≠PD, mismatch 영향 |
| **Step 3** | [+ σL_N, σL_P] 6D | Local variation tolerance | N/P 각각 Pelgrom |
| **Step 4** | [+ σG_N, σG_P] 8D | Global variation tolerance | N/P 각각 Vth 3σ |
| **Step 5** | [+ μ_N, μ_P] 10D | Mobility sensitivity | N/P 각각 mobility |
| **+ Temp** | Temp discrete 5 level | PVTA×Temp coupling | -40/25/85/125/150°C, 연속 추정 아님 |
| **Full paper** | 위 + Mb, Nfin, W | Sec.3 input space 확장 | 설계 자유도 전반 |

> **Toy project는 이 전체 로드맵의 Gate 0** — "surrogate + physics layer + inversion pipeline이 실제로 동작하는가?"를 가장 단순한 PVTA 3D에서 먼저 검증한다. 이후 각 step에서 차원을 하나씩 추가하며 점진적 확장.

### 14.2 핵심 이해: Vmin Estimation의 구조 (Vop는 고정 변수가 아니다)

Vmin 추정 절차:

```
For a given (PG_shift, PU_shift) pair:
  Step 1: Sweep Vop = 0.4, 0.5, 0.6, 0.7, 0.8, 0.9 V
  Step 2: At each Vop, compute SNMR μ, σ from MC 10K
  Step 3: Zscore(Vop) = μ_SNMR(Vop) / σ_SNMR(Vop)
  Step 4: Z_target from Poisson yield (given Mb, Y_target)
  Step 5: Vmin = interpolate {Vop | Zscore(Vop) = Z_target}
```

즉 **Vop는 고정 변수가 아니라 Zscore 커브의 x축**이며, 그 커브 위에서 Vmin이 정의됩니다.
따라서 surrogate는 **Vop를 입력으로 포함**해야 하며, 실제로는 **3D 입력 → 2D 출력** 문제입니다.

### 14.3 Toy Project Scope

| 항목 | 범위 | 비고 |
|------|------|------|
| **입력 파라미터** | `common_N_shift` (=PG_shift=PD_shift), `PU_shift`, `Vop` (3D) | PG와 PD는 동일 NMOS shift. 10D→3D 축소 |
| **출력** | SNMR_μ, σ (2개) | Vtrip 제외, read-centric |
| **고정 변수** | Mb=64MB, **Temp=125°C (hot, SNMR worst-case)** | Full project에서 5 level(-40/25/85/125/150°C)로 확장 |
| **Data source** | HSPICE MC 10K × **1200 runs** (200×6) | ≈5hr on parallel farm, overnight OK |
| **Surrogate** | GP (Gaussian Process), 3D→2D | Matern 5/2 + ARD kernel, ample data |
| **Physics layer** | Zscore → Poisson yield → Vmin interpolation | Sec.6 그대로 |
| **Inversion (= Feasible Region Identification)** | "PG-PU 공간에서 Vmin ≤ 0.6V를 만족하는 영역의 경계(contour line) 추정" | 2D boundary tracing, scalar optimization이 아님 |
| **검증** | True HSPICE contour line vs predicted contour line distance | Hausdorff distance 또는 max error < 20mV |

**Out-of-scope (toy project):**
- Vtrip, global variation, mobility, Nfin, W, L
- Active learning loop, multi-fidelity
- Sobol sensitivity analysis (→ full project)
- Pareto front (NSGA-II)
- **PG-PD skew** → 별도 extension으로 계획 (Sec.14.11)

### 14.4 Data Generation: HSPICE MC 10K

#### Investment Philosophy

Model 구축 후 모든 Vmin 예측은 **inference 전용**이 된다. 즉 초기 데이터 생성은 **1회성 고정비용(fixed cost)**이며, 이후 HSPICE run은 zero. 따라서:

> **"Model quality를 보장할 수 있는 데이터"에 투자하는 것이 가장 효율적인 전략이다.**
> 적게 샘플링해서 interaction을 놓치고 재시도하는 비용이, 처음부터 충분히 샘플링하는 비용보다 항상 크다.

#### Domain Knowledge: 관심 영역은 Worst-Case Corner 주변

SRAM Vmin 분석에서 실제로 중요한 영역은 **global corner 이내**다.

| 항목 | 값 | 비고 |
|------|------|------|
| Global 1σ (Vth) | 20-30mV | 공정/PDK 의존적 |
| Global corner (3σ) | ±60-90mV from TT | FFG/SSG/FSG/SFG |
| **관심 영역** | **±60mV 이내 (TT ± 3σ)** | Corner 바깥은 Vmin이 inherently 나쁨 → priority low |
| SNMR worst corner | **Hot + FSG** (common_N < 0, PU > 0) | NMOS fast, PMOS slow, 고온 |
| Vtrip worst corner | **Cold + SFG** (common_N > 0, PU < 0) | NMOS slow, PMOS fast, 저온 |
| Temperature | **Discrete**: -40, 25, 85, 125, 150°C | 연속 추정 불필요, 5 level |

**Toy project에의 적용:**
- SNMR만 다루므로 **Hot + FSG 영역**이 primary 관심사
- (common_N, PU) ∈ [-60, +60]mV² 범위는 global corner를 커버하므로 적절
- 단, **uniform sampling보다는 FSG/SFG quadrant에 weighted sampling**이 효율적
- Temperature: **125°C (hot, SNMR worst)** 로 고정. Full project에서 5 level 확장

#### PVTA Contour의 실제 구조: TT → Shift → Response Surface

PVTA contour 분석의 실제 workflow:

```
TT (common_N=0, PU=0) → 여기에 ΔVtsat shift를 가함
  ├─ common_N ∈ [-60, +60] mV
  └─ PU ∈ [-60, +60] mV

각 (common_N, PU)에서 Vmin = f(Vop sweep)

Global corner들은 이 2D response surface 위의 known reference points:
  └─ FSG = (common_N ≈ -σ×3, PU ≈ +σ×3)   → SNMR worst
  └─ SFG = (common_N ≈ +σ×3, PU ≈ -σ×3)   → Vtrip worst
  └─ FFG = (common_N ≈ -σ×3, PU ≈ -σ×3)
  └─ SSG = (common_N ≈ +σ×3, PU ≈ +σ×3)
```

여기서 중요한 점:
1. **Surrogate가 학습하는 것은 Vmin = f(common_N, PU, Vop)라는 연속 함수**
2. TT에서 모든 방향으로 shift한 결과를 response surface로 모델링
3. Global corner 4개는 이 표면 위의 **validation points** — 이미 HSPICE 결과가 있거나 쉽게 구할 수 있음
4. **Corner 간 interpolation이 아니라 TT→corner까지의 전체 shift를 학습하는 것**

이 구조는 Surrogate → Differentiable Physics Layer → Inversion pipeline과 정확히 일치한다:
- Surrogate는 연속 함수 Vmin(shift)를 학습
- Physics layer는 Vop sweep을 통해 Vmin 계산
- Inversion은 "어떤 shift에서 Vmin=0.6V가 되는가?"를 추정

#### Sampling Strategy

```
Feature space는 3D: [common_N_shift, PU_shift, Vop]

PG_shift = PD_shift = common_N_shift  (NMOS device 일괄 shift)
PU_shift: PMOS device shift (독립 변수)

Vop ∈ {0.4, 0.5, 0.6, 0.7, 0.8, 0.9} V (6 level, step 0.1V)
Temperature: 125°C 고정 (SNMR worst-case hot)

Sampling: Stratified 2D Sobol — 200 points in (common_N, PU)
  └─ 전체 범위: common_N ∈ [-60, +60] mV, PU ∈ [-60, +60] mV
  └─ 하지만 uniform이 아닌, **worst-case corner 중심 weighted sampling**

  Region breakdown (200pt 기준):
    FSG quadrant (common_N < 0, PU > 0):    100pt (50%) ← SNMR worst, 집중
    SFG quadrant (common_N > 0, PU < 0):     50pt (25%) ← Vtrip worst, future-proof
    나머지 2 quadrant (++, --):               50pt (25%) ← baseline coverage

  각 quadrant 내에서는 Sobol sequence로 space-filling 유지

Rationale:
  - Global corner(±3σ) 바깥은 Vmin이 inherently 불량 → dense sampling 불필요
  - FSG region에서의 SNMR curvature가 가장 중요 → 여기에 절반 투자
  - 나머지 region은 GP가 interpolation으로 처리 가능할 정도의 sparse coverage
  - 이 stratification으로 200pt의 effective resolution이 worst region에서 2배 향상
```

**왜 200pt + weighted인가:**

| 전략 | 장점 | 단점 |
|------|------|------|
| Uniform Sobol 200pt | 바이어스 없음 | FSG region에서 density 부족 가능 |
| **Stratified weighted 200pt** | **Worst region 해상도 2배** | Quadrant 경계에서 GP interpolation 부담 |
| Uniform 400pt | Worst region 해상도 충분 | 2배 budget, 10hr run (overnight 초과) |

> **선택: Stratified weighted 200pt.** GP의 ARD kernel이 quadrant 경계에서의 interpolation을 자연스럽게 처리하므로, uniform의 장점은 유지하면서 worst region 해상도를 높이는 trade-off가 가장 효율적.

#### 핵심 DOE 과제: Skew × PVTA Interaction

이전에 실패했던 지점이 여기다. PVTA contour 자체는 skew=0에서 잘 맞출 수 있었지만, **skew가 추가되면 문제가 발생한다**:

**문제의 구조:**
```
Vmin = f(common_N, PU, skew, Vop)

∂Vmin/∂skew = g(common_N, PU)  ← skew의 영향이 PVTA 위치에 따라 변함
```

즉 아래 그림처럼 skew sensitivity가 PVTA 공간에서 일정하지 않다:

```
     Skew = -30mV          Skew = 0           Skew = +30mV
  PU↑                    PU↑                 PU↑
    |  Vmin=0.6V          |  Vmin=0.6V         |  Vmin=0.6V
    |    ╲                |    ──              |  ╱
    |     ╲               |                    | ╱
    |      ╲              |                    |╱
    └───────→ common_N    └────────→ common_N  └────────→ common_N

  ∂Vmin/∂skew ∈ [−0.3, +0.8]  (PVTA 위치에 따라 부호와 magnitude가 바뀜)
```

**왜 기존 방식으로 왜곡이 생겼는가 (그리고 200pt로 어떻게 해결하는가):**

| 원인 | 120pt에서의 결과 | 200pt에서의 개선 |
|------|-----------------|-----------------|
| 4D interaction 포착 밀도 부족 | Contour skew 방향 extrapolation error | (common_N, PU) 밀도 67%↑ → GP가 interaction lengthscale을 더 정확히 추정 |
| GP lengthscale 평균화 | 급격한 gradient 변화가 smooth over | 밀도 증가로 국소적 lengthscale variation 포착 가능 |
| Skew 극단 contour curvature 소실 | 체계적 bias(distortion) | Dense PVTA baseline이 skew extension의 adaptive sampling guide 제공 |

**해결 전략: Nested Adaptive Grid**

Toy project(skew=0) → skew extension에서 이 문제를 피하기 위한 DOE:

```
Phase A — PVTA Baseline (Toy project, skew=0): 1200 runs
  └─ 2D Sobol 200 × Vop 6
  └─ GP surrogate로 ∂Vmin/∂common_N, ∂Vmin/∂PU gradient map 확보 (고해상도)
  └─ 이 gradient map이 skew extension의 "어디를 집중 sampling할지" 결정

Phase B — Skew Augmentation (Toy project 이후, ~600-800 runs 추가):
  └─ 3D space: [common_N, PU, skew] + Vop
  └─ Strategy: "Adaptive skew grid"
     1. Skew ∈ {−30, −15, 0, +15, +30} mV (5 levels)
     2. 각 skew level에서 (common_N, PU) sampling 밀도를 Phase A gradient에 따라 차별화
     3. Gradient가 가파른 region → skew에 민감 → 3x density
     4. Gradient가 평탄한 region → skew 영향 미미 → 0.5x density
  └─ 이 adaptive 전략은 120pt baseline으로는 불가능 (gradient map 자체가 불안정)

Phase C — GP with Composite Kernel:
  └─ Kernel = k_PVTA(common_N, PU, Vop) × k_skew(skew) + k_noise
  └─ f(x) = f_PVTA(common_N, PU, Vop) + f_skew(skew) + f_int(common_N, PU, skew)
      └─ f_int가 "skew sensitivity가 PVTA에 따라 달라지는" 부분을 명시적 모델링
```

**Toy project의 결정적 역할:**

Toy project(skew=0)의 dense GP는 단순히 PVTA contour만 제공하는 것이 아니라, **skew extension의 DOE quality 자체를 결정**한다:

```
Toy project GP quality → gradient map reliability → Phase B adaptive sampling quality
  → skew×PVTA interaction 포착 정확도 → skew extension 성공/실패
```

즉 toy project에서 **1200pt 투자는 skew extension의 성공 확률을 높이는 investment**다. 200pt의 dense baseline은 gradient map을 신뢰할 수준으로 만들어 주며, 이 gradient map이 없으면 Phase B adaptive sampling이 불가능하다.

#### HSPICE Deck Structure

```
* sram_cell_pvta.sp — PG=PD common NMOS shift + PU PMOS shift + Vop sweep
.param common_n_shift = {N_SHIFT}    * PG와 PD 동시 적용
.param pu_shift = {P_SHIFT}
.param vdd = {VOP}

* PG device (NMOS): .model ... Vtsat0={VT0_NOM + common_n_shift}
* PD device (NMOS): .model ... Vtsat0={VT0_NOM + common_n_shift}  * PG와 동일
* PU device (PMOS): .model ... Vtsat0={VT0_P_NOM + pu_shift}

.temp 25

.dc vdd {VOP} {VOP} 0.01   ← DC sweep for SNM (hold/noise source)
.mc run=10000 ...
.measure dc snm_meas ...

.alter case=2: vdd=0.5
.alter case=3: vdd=0.6
... (Vop sweep을 .alter 또는 별도 deck으로)
```

> **중요: MC 10K × 6 Vop level = 60K MC run total이 아니라, 각각 10K MC를 병렬로 돌리면 1개 condition의 6개 Vop job을 farm에 6개 job으로 submit. Total job 수 = 200(common_N,PU) × 6(Vop) = 1200 jobs. 5시간 (overnight).**

#### Post-Processing

```
Raw HSPICE output (1200 × .mt0)
  → Python parser: histogram check, μ/σ 추출
  → Save as .npz: X(1200×3), y(1200×2)

Data shape:
  X[i] = [common_N_shift_i, PU_shift_i, Vop_i]
  y[i] = [μ_SNMR_i, σ_SNMR_i]
```

#### Simulation Budget Breakdown

| 항목 | 예상 시간 | 비고 |
|------|----------|------|
| Deck gen script (200 (common_N,PU) × 6 Vop) | 2hr | Python template engine |
| Deck validation (1 corner × 6 Vop) | 30min | 수동 run + histogram check |
| Batch submit 1200 jobs | 30min | 100 cores면 12 batch |
| **HSPICE run** | **≈5hr** | 1200 parallel jobs |
| Post-processing + QC | 2hr | Parsing + histogram QC |
| **Total** | **≈10hr (1일+)** | Deck gen(오전) → submit(점심) → overnight → post-proc(다음날) |

### 14.5 Toy Project Pipeline

```
Step 0: HSPICE data gen (Day 1-2)
  └─ 200 (common_N, PU) × 6 Vop = 1200 conditions, MC 10K each
  └─ → 1200 × [μ_SNMR, σ_SNMR]
  └─ 5hr farm run (overnight, 무인)

Step 1: Train/Test split (Day 2)
  └─ Train 1000 / Test 200 (또는 stratified split by quadrant)
  └─ Stratified split: FSG/SFG/rest 각각 80/20 비율 유지

Step 2: GP Surrogate (Day 2-3)
  └─ Input: [common_N_shift, PU_shift, Vop] (3D)
  └─ Output: [μ_SNMR, σ_SNMR] (2 independent GP or multi-output GP)
  └─ Kernel: Matern 5/2 + ARD (Automatic Relevance Determination)
  └─ Train: log marginal likelihood

Step 3: Differentiable Physics Layer (Day 3-5)
  └─ For a given (common_N, PU), predict μ(Vop), σ(Vop) → Zscore(Vop)
  └─ Z_target from Poisson yield (Mb=64MB, Y_target=99.9%)
  └─ Linear interpolation → Vmin(common_N, PU)
  └─ Unit test: ∂Vmin/∂common_N, ∂Vmin/∂PU gradient check

Step 4: Feasible Region Identification — PVTA Contour (Day 5-7)
  └─ 여기서의 "inversion"은 scalar optimization이 아니라, forward prediction을 grid로 평가하여 Vmin ≤ 0.6V 조건을 만족하는 (common_N, PU) 영역의 경계를 식별하는 과정
  └─ Grid over common_N ∈ [-60,60], PU ∈ [-60,60] (50×50 = 2500 eval, ≈2.5초)
  └─ For each (common_N, PU), predict Vmin via pipeline
      └─ Surrogate → μ(Vop), σ(Vop) → Zscore(Vop) → interpolate → Vmin
  └─ Contour line: { (common_N, PU) | Vmin_pred = 0.6V }
  └─ Compare with true HSPICE contour (hold-out 100pt):  
      └─ Hausdorff distance, max error, area overlap ratio

Step 5: Validation & Ablation (Day 7-10)
  └─ **Surrogate accuracy (local-only hold-out)**:
      └─ Hold-out 200pt (stratified): predicted vs local-only MC
      └─ RMSE: μ_SNMR, σ_SNMR 각각
  └─ **Corner validation** (4 global corners—FSG, SFG, FFG, SSG):
      └─ 각 corner: predicted Vmin vs local-only MC (별도 4회, 각 10K)
      └─ Corner error: max|Vmin_pred - Vmin_local| ≤ 15mV 목표
      └─ **여기서는 local-only MC가 정답** — corner는 이미 global shift가 PVTA로 반영되었으므로 full-variation MC와 비교하는 것은 이중계산
  └─ **TT full-variation bias 측정** (TT 1회, full-variation MC 10K):
      └─ Model Vmin (local-only 기반) vs TT full-variation MC Vmin
      └─ 이 차이가 "global variation을 MC에서 제외함으로써 발생하는 TT에서의 optimistic bias"
      └─ (TT는 fail point가 아니므로 문제되지 않지만, bias 크기를 정량화)
  └─ Contour boundary Hausdorff distance
  └─ Ablation: N_train = 50, 100, 200, 400, 800, 1000 → contour accuracy
```

### 14.6 성공/실패 기준 (Go/No-Go Decision)

| 기준 | Go (계속 진행) | No-Go (재설계) |
|------|---------------|----------------|
| **Contour boundary error** | Predicted Vmin=0.6V line vs true, Hausdorff dist < 15mV | > 30mV |
| **Surrogate fit (R²)** | μ_SNMR R² > 0.95, σ_SNMR R² > 0.90 | < 0.80 |
| **Gradient flow** | ∂Vmin/∂PG, ∂Vmin/∂PU가 물리적 방향 (PG↑→Vmin↑, PU asymmetry) | Zero / sign mismatch |
| **PVTA asymmetry 포착** | PG shift와 PU shift의 영향 차이를 surrogate가 재현 | Symmetric prediction (not physical) |
| **Contour smoothness** | Vmin=0.6V contour line이 물리적으로 smooth | 골짜기/불연속 급변 |
| **Ablation trend** | N_train ↑ → contour error ↓ (수렴 방향) | Flat / non-monotonic |

**2주 후 판정:**
- **5-6 Go** → Full project 진행 (8주, Sec.12)
- **3-4 Go** → Scope 추가 축소 후 재시도 (예: Vop만, 또는 Mb만)
- **≤2 Go** → 방법론 재검토 필요

### 14.7 실행 일정 (2주, 1인)

```
Day 1 (Mon):
  오전 ─ Python env setup + deck generator 스크립트 완성
          (PyTorch, GPyTorch, scipy, matplotlib, numpy)
  오후 ─ SRAM cell netlist: PG=PD common_N_shift + PU_shift .param 추가
          Temp=125°C 설정 (SNMR worst-case hot)
          Stratified sampling 구현: FSG 50%, SFG 25%, 나머지 25%
          deck validation 1 corner × 6 Vop 수동 run (30min)
          histogram 확인 → deck correctness 확보

Day 2 (Tue):
  오전 ─ 200 (common_N,PU) × 6 Vop = 1200 jobs batch submit (점심 전)
  오전~오후 ─ (Sim run 5hr 중) GP surrogate 코드 작성
                └─ Data loader, 3D→2D GP with ARD Matern 5/2
  오후 ─ Post-processing script 완성
  저녁 ─ Simulation 완료 → Post-processing → .npz 저장
          (5hr run이므로 늦은오후~저녁 사이 완료)

Day 3 (Wed):
  오전 ─ GP tuning (kernel, lengthscale initialization)
          └─ μ, σ 각각 independent GP vs multi-output GP 비교
          └─ Visualize: predicted vs true scatter, confidence band
  오후 ─ Differentiable physics layer 구현
          └─ Zscore(Vop) → Poisson yield → Vmin interpolation

Day 4 (Thu):
  오전 ─ Physics layer unit tests (gradient check)
          └─ ∂Vmin/∂common_N, ∂Vmin/∂PU analytical vs autograd 비교
  오후 ─ Full pipeline 연결: 3D Input → GP → Physics → Vmin
          └─ Sanity check: Nominal (common_N=0, PU=0)에서 Vmin ≈ 0.5-0.7V?

Day 5 (Fri):
  오전 ─ PVTA grid inference: 50×50 = 2500 point eval (≈2.5초)
  오후 ─ Vmin contour line 추출 + true HSPICE contour와 비교
          └─ Hausdorff distance, max error 계산
          └─ **4 global corner validation** (FSG/SFG/FFG/SSG local-only MC 각각)
          └─ **TT bias 측정용** full-variation MC 1회 submit (overnight run)

Day 6 (Mon):
  오전 ─ Ablation: N_train = 50, 100, 200, 400, 800, 1000
          └─ 각각 surrogate 학습 → contour error 측정
          └─ Budget vs accuracy curve 생성 (paper의 핵심 preview)
  오후 ─ Error breakdown: surrogate MSE vs Vmin propagation error
          └─ TT full-variation bias 결과 정리 (실행 완료되었다고 가정)

Day 7 (Tue):
  오전 ─ Contour visualization: true vs predicted overlay color map
          └─ 4 global corner 위치 marking + 각각 error 표기
  오후 ─ Asymmetry 분석: common_N_shift 민감도 vs PU_shift 민감도
          └─ "TT에서 local-only vs full-variation bias" figure 추가

Day 8 (Wed):
  오전 ─ Ablation figure 정리 + convergence 분석
  오후 ─ Go/No-Go matrix 작성 + 결과 종합

Day 9 (Thu):
  오전─오후 ─ Toy report 작성 (2-page)
                ├─ Method: 3D GP + physics layer + inversion
                ├─ Key figures: contour overlay, ablation curve, scatter, error breakdown
                ├─ Go/No-Go 판정
                └─ Full project impact assessment

Day 10 (Fri):
  오전 ─ Report review + 보완
  오후 ─ Decision meeting
```

### 14.8 Phase Timeline (Gantt-style)

```
              | Day1 | Day2 | Day3 | Day4 | Day5 | Day6 | Day7 | Day8 | Day9 | Day10 |
--------------|------|------|------|------|------|------|------|------|------|------|
Deck gen      | ████ |      |      |      |      |      |      |      |      |      |
Sim run       |      | ██   |      |      |      |      |      |      |      |      |
Post-proc     |      | ██   |      |      |      |      |      |      |      |      |
GP surrogate  |      | ██   | ████ |      |      |      |      |      |      |      |
Physics layer |      |      | ██   | ████ |      |      |      |      |      |      |
PVTA contour  |      |      |      |      | ████ | ██   |      |      |      |      |
Validation    |      |      |      |      |      | ██   | ████ | ██   |      |      |
Ablation      |      |      |      |      |      | ██   | ██   |      |      |      |
Report        |      |      |      |      |      |      |      | ██   | ████ | ████ |
              |      |      |      |      |      |      |      |      |      |      |
Key milestones|DeckOK|SimOK |GPfit |PhysOK|ContOK|AblOK |Asym  |GoNoGo|Report|Meeting|
```

### 14.9 Deliverables

| 산출물 | 설명 | 마감 |
|-------|------|------|
| `gen_decks_pvta.py` | HSPICE deck generator (stratified 200 (common_N,PU) × 6 Vop, FSG/SFG weighted) | Day 1 |
| `parse_snm.py` | SNMR μ/σ post-processor (HSPICE .mt0 → .npz) | Day 2 |
| `toy_surrogate.py` | 3D→2D GP surrogate training + evaluation + ablation | Day 3 |
| `toy_physics_layer.py` | Differentiable Vmin computation (PyTorch) + gradient unit tests | Day 4 |
| `toy_contour.py` | PVTA contour inference + Hausdorff distance computation | Day 5 |
| `toy_report.md` | 2-page summary with all figures + Go/No-Go | Day 10 |
| Figures (8장) | GP fit scatter, contour overlay, ablation curve, Hausdorff, gradient check, asymmetry, error breakdown, **TT bias (local vs full)** | Day 9 |

### 14.10 Risk & Mitigation

| 위험 | 영향 | 완화 |
|------|------|------|
| Farm queue busy → 5hr → 10hr+ | 일정 1일 슬립 | Day 1 submit, overnight run. Queue time 포함해도 Day 3 오전까지 OK |
| MC 10K에서 SNMR histogram 비정규 (bimodal) | μ,σ 통계 불안정 | Post-processing histogram QC. Robust statistics (median, IQR) fallback |
| GP 3D (1200pt) training O(n³) 부담 | 학습 느림 | GPyTorch CIQ (Contour Integral Quadrature) or SGPR. 1200pt는 GPyTorch에서 충분히 처리 가능 |
| ∂Vmin/∂common_N gradient vanishing | Contour boundary 불안정 | Gradient clipping + Vop grid fine-tuning |
| common_N/PU shift가 너무 좁은 범위에서만 Vmin=0.6V crossing | Contour 불완전 | [-60,60]mV 범위가 충분하지 않으면 [-80,80]으로 확장 (budget 내) |
| True contour와 predicted contour의 비교 metric 모호 | 판정 불명확 | Hausdorff distance + max error + area overlap ratio 3종 metric |

### 14.11 PG-PD Skew: Known Significant, Next Step

#### PG-PD Skew는 이미 영향이 큰 것으로 알려져 있다

PG-PD skew는 SRAM read stability에 직접적인 영향을 미치는 주요 mismatch 요인이다. 이미 알려진 사실이므로, **"영향이 있는가?"를 검증하는 것이 아니라** toy project 이후 이 파라미터를 어떻게 추가할지 계획하는 것이 필요하다.

```
PG_shift = common_N_shift + skew/2
PD_shift = common_N_shift - skew/2

skew = PG_shift - PD_shift  (nominal: 0, 범위: 예를 들어 ±30mV)
```

#### Skew Extension 이후의 Path

PG-PD skew 추가 → **N/P 각각의 variation/mobility로의 확장 (ultimate goal)**

| Step | 추가 파라미터 | Input 차원 | 의미 |
|------|-------------|-----------|------|
| **Toy project** | — | [common_N, PU, Vop] 3D | PVTA contour baseline |
| **+ skew** (Step 2) | `skew = PG - PD` | +1 = 4D | PG-PD mismatch 영향 |
| **+ N/P local** (Step 3) | `σL_N`, `σL_P` | +2 = 6D | Pelgrom scaling per device |
| **+ N/P global** (Step 4) | `σG_N`, `σG_P` | +2 = 8D | Global Vth variation per device |
| **+ N/P mobility** (Step 5) | `μ_N`, `μ_P` | +2 = 10D | Mobility sensitivity per device |
| **Full paper** | + Mb, Temp, Nfin, W | 10D+ (Sec.3) | 전체 설계 자유도 |

각 step에서의 핵심 질문:
- Step 2: skew가 주어졌을 때 PVTA feasible region이 얼마나 축소되는가?
  - 특히 **∂Vmin/∂skew가 PVTA 위치에 따라 어떻게 변하는가?** (Sec.14.4.1의 interaction 문제)
- Step 3: N/P local variation이 Vmin에 asymmetric하게 기여하는가?
- Step 4: global variation이 PVTA shift와 어떻게 coupling되는가?
- Step 5: mobility variation이 Vmin에 유의미한가?

#### Skew 추가를 위한 DOE 접근 (이전 실패로부터의 교훈)

이전에 skew 추가 시도가 잘 안 되었던 근본 원인: **skew sensitivity가 PVTA 위치에 따라 달라지는 interaction**을 DOE가 제대로 포착하지 못했다.

제안하는 접근법 (Sec.14.4.1 상세):

```
Phase B — Skew Augmentation (Toy project 이후, ~600-800 runs 추가):
  ├─ Skew ∈ {−30, −15, 0, +15, +30} mV (5 levels, 계층적)
  ├─ 각 skew level에서 (common_N, PU) sampling 밀도 차별화
  │    └─ Toy project의 dense GP(200pt) gradient map이
  │       "어느 PVTA region에서 skew 영향이 클지" 정밀 가이드
  ├─ Composite kernel GP: k_PVTA(common_N, PU, Vop) × k_skew(skew)
  └─ f_int(common_N, PU, skew) term으로 interaction 명시적 모델링

핵심 통찰:
  Toy project(skew=0)의 gradient map = skew extension의 adaptive sampling guide
  즉 "skew=0에서 기울기가 가파른 region = skew에 민감한 region = oversampling 필요"
```

#### Toy Project에서의 역할

Toy project는 skew=0만 다루지만, **그 결과가 skew extension의 DOE quality를 결정**한다:

| Toy project output | Skew extension에서의 용도 |
|-------------------|--------------------------|
| `∂Vmin/∂common_N` gradient map | 어느 PVTA region이 skew에 민감한지 식별 |
| ∂Vmin/∂PU gradient map | PMOS skew sensitivity의 baseline |
| GP lengthscale (ARD) | (common_N, PU) space에서의 특성 길이 → skew grid 간격 결정 |
| Hold-out error | Surrogate quality → skew 추가 시 신뢰할 수 있는 baseline인지 확인 |

#### Toy Report에 포함

```
Toy report:
  ├─ ∂Vmin/∂common_N, ∂Vmin/∂PU gradient map (2D contour)
  ├─ GP lengthscale: common_N, PU, Vop 각 방향
  ├─ Skew sensitivity 근사 (from GP gradient)
  ├─ "Toy project GP quality → skew extension에서의 신뢰도" 평가
  └─ Phase B (skew augmentation)를 위한 adaptive sampling 가이드
```

### 14.12 이 결정이 전체 프로젝트에 주는 의미

```
Toy project 성공:
  └─ Full project 8주 확정
  └─ Sec. 12 timeline full execution
  └─ Target: IEEE TCAD or DAC

Toy project 실패 (No-Go):
  └─ 방법론 재검토
  └─ 대안 1: Forward-only surrogate로 축소 (inverse 제외)
  └─ 대안 2: Direct Vmin network (physics layer 제거)
  └─ 대안 3: Closed-form Vmin model + analytical inversion (ML 없이)
  └─ Target: SISPAD 또는 workshop paper로 축소
```

---

## References

1. Singhee & Rutenbar, "Why Quasi-Monte Carlo is Better Than MC or LHS for Statistical Circuit Analysis," *IEEE TCAD*, 2010.
2. Guo et al., "An Efficient SRAM Yield Analysis Method using Multi-Fidelity Neural Network," *ISEDA*, 2024.
3. Yin et al., "Efficient Bayesian Yield Analysis and Optimization with Active Learning," *DAC*, 2022.
4. Yin et al., "High-Dimensional Yield Estimation Using Shrinkage Deep Features," *ASPDAC*, 2023.
5. Xing et al., "Breaking the Tuning Barrier: Zero-Hyperparameters Yield Multi-Corner Analysis Via Learned Priors," *arXiv*, 2026.
6. Liu et al., "Seeking the Yield Barrier: High-Dimensional SRAM Evaluation Through Optimal Manifold," *DAC*, 2023.
7. Gupta & Calhoun, "Dynamic Read VMIN and Yield Estimation for Nanoscale SRAMs," *IEEE TCAS-I*, 2021.
8. Kinoshita et al., "Space-Filling Latin Hypercube Design for Efficient Bayesian Optimization with Application to Semiconductor Development," *IEEE TSM*, 2025.
9. Kobayashi et al., "Physics-informed Bayesian optimization suitable for extrapolation of materials growth," *npj Computational Materials*, 2025.
10. Stein, "Large Sample Properties of Simulations Using Latin Hypercube Sampling," *Technometrics*, 1987.
