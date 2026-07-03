# SRAM Vmin 추정을 위한 물리 기반 GP 대리 모델

> **버전**: 2026-07-02 (v0.3)
> **상태**: Toy project 완료, HSPICE 실데이터 추출 준비 완료

---

## 1. 서론

### 1.1 연구 배경

SRAM (Static Random Access Memory)은 시스템 반도체에서 가장 큰 면적을 차지하는 블록으로, 전체 칩의 수율(yield)에 지배적인 영향을 미친다. SRAM의 동작을 결정하는 가장 중요한 지표 중 하나가 **Vmin (최소 동작 전압)** 이다. Vmin은 셀이 읽기/쓰기 동작을 안정적으로 수행할 수 있는 최저 전압으로, 공정 변동(process variation)에 크게 의존한다.

전통적인 SRAM Vmin 추정은 Monte Carlo (MC) HSPICE 시뮬레이션에 의존한다. 수천 회의 MC 시뮬레이션을 각 PVTA 조건(process, voltage, temperature, aging)에 대해 반복하므로 계산 비용이 매우 크다. 특히 6-sigma 수율 분석(tail estimation)을 위해서는 수백만 회의 MC가 필요해 실질적으로 불가능에 가깝다.

### 1.2 제안 방법: GP 대리 모델 + 미분 가능 물리 레이어

본 연구는 Gaussian Process (GP) 대리 모델(surrogate model)과 미분 가능한 물리 레이어(differentiable physics layer)를 결합하여 SRAM Vmin을 효율적으로 추정하는 방법을 제안한다.

**핵심 아이디어**:
1. **GP 대리 모델**: PVTA 파라미터 → SNMR(mu, sigma) 매핑 학습
2. **미분 가능 물리 레이어**: SNMR(mu, sigma) → Vmin 변환 (Z-score 기반 선형 보간)
3. **물리 기반 손실 함수**: monotonicity (L_mono), corner anchor (L_boundary), Pelgrom scaling (L_pelgrom) 제약 조건

### 1.3 논문 기여도 (예상)

| 기여 항목 | 중요도 | 설명 |
|----------|--------|------|
| 미분 가능 Vmin 변환 | ⭐⭐⭐ | GP 출력 → Vmin의 end-to-end 미분 가능 파이프라인 |
| 가산 커널 델타 sigma GP | ⭐⭐⭐ | Vop(전압) + (cn, pu) 주소성 분리로 sigma 예측 정확도 향상 |
| 역 Vmin 등고선 추출 | ⭐⭐⭐⭐ | Vmin=0.6V contour 기준 Hausdorff 거리 기반 검증 |
| 예측-실측 격차 진단 | ⭐⭐ | lengthscale, gradient 방향, corner bias 분석 체계 |
| 물리 기반 GP 제약 | ⭐⭐⭐ | L_boundary → 20.9% Vmin RMSE 개선 (실험 검증 완료) |

---

## 2. 방법론

### 2.1 입력 공간

**Core 3D** (항상 포함):
| 변수 | 기호 | 범위 | 단위 |
|------|------|------|------|
| NMOS 공통 시프트 | common_N | [-60, 60] | mV |
| PMOS 시프트 | PU | [-60, 60] | mV |
| 동작 전압 | Vop | [0.4, 0.9] | V |

**확장 차원** (indices 3+, 선택적):
| 변수 | 기호 | 범위 | 설명 |
|------|------|------|------|
| NMOS 폭 | W | nominal ±10% | PG/PU 트랜지스터 폭 변동 |
| 게이트 길이 변동 | σL_mult | [0.8, 1.2] | 공정 변동에 따른 L variation |
| 임계 전압 변동 | σG | [0.8, 1.2] | Global Vth variation |
| 이동도 변동 | μ_mobility_mult | [0.8, 1.2] | Carrier mobility variation |
| 온도 | Temp | {-40, 25, 85, 125, 150} | °C (이산 값, continuous kernel) |

**출력**: y = [mu_SNMR (V), sigma_SNMR (V)] — (N, 2), 고정 불변.

### 2.2 GP 모델 구조

**mu GP** (`ExactGPModel`):
- 커널: Matern 5/2 + ARD (d 차원 자동 적응)
- 모든 입력 차원에 대해 독립 lengthscale 학습

**sigma GP** (`AdditiveGPModel`):
- 가산 커널: k_Vop(Vop) + k_cnpu(cn, pu)
- Vop 의존성과 (common_N, PU) 의존성을 분리하여 sigma의 Pelgrom scaling 학습

두 GP 모두 GPyTorch 기반의 `ExactMarginalLogLikelihood` + Adam optimizer로 학습.

### 2.3 미분 가능 물리 레이어

Vmin은 다음과 같이 계산된다:
1. 각 (common_N, PU) 조건에서 GP가 mu(Vop), sigma(Vop) 예측 (Vop ∈ {0.4, 0.5, ..., 0.9})
2. Zscore(Vop) = mu(Vop) / sigma(Vop)
3. Vmin = linear_interpolate({Vop | Zscore(Vop) = Z_target}), Z_target = 6.0 (64Mb @ 99.9% yield 대응)

이 과정은 mu, sigma를 통해 **완전 미분 가능**하며, GP → Vmin의 end-to-end gradient 흐름이 보장된다.

### 2.4 물리 기반 제약 조건

**L_mono (단조성)**:
- ∂μ/∂Vop > 0 (Vop 증가 → mu_SNMR 증가)
- Probe point collocation (PINN 스타일)으로 전체 입력 공간에서 평가
- 패널티: ReLU(-∂μ/∂Vop)²

**L_boundary (코너 앵커)**:
- 4개 글로벌 코너 (FSG, SFG, FFG, SSG) × 6 Vop = 24개 가상 관측
- 학습 데이터에 직접 추가 (data augmentation)
- Ground truth: `analytic_snmr()` 함수

**L_pelgrom (Sigma 스케일링)**:
- σ(Vop) = SIGMA₀ + SIGMA_VOP_SLOPE × (0.9 − Vop)
- sigma GP 학습 시 약한 정규화(regularization)

**통합 손실 함수**:
```
L_total = -log p(y|X,θ) + λ_mono·L_mono + λ_pelgrom·L_pelgrom
```

### 2.5 입력 정규화 (StandardScaler)

각 입력 차원의 스케일 차이(mV, V, °C, 무차원 비율)로 인한 GP 학습 불안정을 방지하기 위해 **StandardScaler**를 도입:
- 각 차원별 평균 0, 분산 1로 정규화
- 학습 데이터 통계(fit) → 동일 통계로 변환(transform)
- 역변환(inverse_transform)으로 원래 스케일 복원
- numpy-only 구현 (sklearn 의존성 없음)

### 2.6 GP → NN 전환 조건

GP로 충분하지 않을 때 Neural Network + PINN으로 전환:

| 조건 | 기준 | 현재 상태 |
|------|------|-----------|
| Hausdorff 거리 | > 3-5mV | ✅ 1.2-1.8mV (촉발 안 됨) |
| ℓ_pu / ℓ_cn 비율 | > 2.0 | ✅ ~1.0 (toy data 한계) |
| 코너 Vmin 오차 | > 3σ | ✅ 통과 |

---

## 3. 실험 결과

### 3.1 Ablation Study (5 Configs)

| Config | mu R² | σ R² | Vmin RMSE | Hausdorff | 설명 |
|--------|-------|------|-----------|-----------|------|
| Baseline | 0.9973 | 0.6301 | 6.52mV | 1.8mV | 참조 |
| +L_mono | 0.9973 | 0.6292 | 6.46mV | 2.1mV | 단독 효과 미미 |
| +L_boundary | 0.9978 | 0.6340 | **5.16mV** | 1.3mV | **20.9% 개선** |
| +Mono+Boundary | 0.9978 | 0.6313 | 5.10mV | 1.2mV | 복합 효과 |
| +Mono+Boundary+Pelgrom | 0.9978 | 0.6365 | **4.91mV** | 1.3mV | **전체: 24.7% 개선** |

**핵심 발견**:
- **L_boundary가 개선의 95% 설명** (6.52→5.16mV, 나머지 0.25mV는 L_mono+L_pelgrom)
- L_mono 효과 없음 (penalty = 0): toy data가 이미 단조 함수이므로
- σ R² < 0.64: sigma 예측이 mu보다 어려움 (향후 개선 필요)

### 3.2 물리적 일관성 검증

**Gradient 방향 검증** (중앙점 (0,0)에서 finite difference):
- ∂Vmin/∂common_N < 0: NMOS 느려짐 → PG leakage 감소 → Vmin 감소 ✅
- ∂Vmin/∂PU > 0: PMOS 느려짐 → PU strength 감소 → Vmin 증가 ✅
- Cos similarity ≈ 1.0: GP가 true gradient 방향 정확히 포착 ✅

**Lengthscale 분석**:
- ℓ_cn ≈ ℓ_pu ≈ 1.0 (모든 config): toy data에서 cn/pu coefficient 유사 → **실 data에서 재검증 필요**
- ℓ_Vop ≈ 0.65 (작음): Vop sensitivity를 GP가 정확히 포착

### 3.3 StandardScaler + 8D 확장 검증

- StandardScaler 3D/8D 정규화: mean=0, std=1, inverse_transform 정확 ✅
- `ExactGPModel` 8D: `ard_num_dims=8` 자동 설정, loss 감소 확인 ✅
- `AdditiveGPModel` 8D: extra dims unmodeled, loss 감소 확인 ✅
- `generate_probe_points(n_extra=5)`: 8D probe 생성, extra dims=0 ✅
- `generate_corner_anchor_data(n_extra=5)`: 8D anchor 생성 ✅
- Full pipeline (GP train → contour): 오류 없음 ✅

---

## 4. 논의

### 4.1 L_boundary가 효과적인 이유

GP의 extrapolation 취약점: 학습 데이터는 common_N, PU ∈ [-60, 60]에 분포하지만 코너(FSG: cn=-60, pu=+60)는 domain 극단. 24개 가상 관측만으로 큰 보정 효과. 실 HSPICE data에서도 적은 수의 코너 시뮬레이션으로 큰 효과를 볼 가능성 높음.

### 4.2 L_mono가 toy data에서 효과 없는 이유

Toy data의 `analytic_snmr()`는 ∂μ/∂Vop = A_MU = 0.15 > 0이 항상 만족. 실 data에서는 non-monotonic 영역이 존재할 가능성 (Vop saturation, 저전압 extreme) → L_mono 효과 기대.

### 4.3 PG >> PU 미반영

Toy data 자체가 common_N과 PU의 계수를 유사하게 설정 (B_MU=0.001, C_MU=-0.0015). 실 data에서는 PG(Pass Gate) variation이 PU(Pull-Up)보다 Vmin에 2-3배 더 큰 영향을 미치므로, ℓ_cn < ℓ_pu가 관측되어야 함.

### 4.4 GP → NN 전환 시점

세 가지 transition trigger 모두 아직 만족되지 않음:
1. Hausdorff > 5mV: ❌ (현재 1.2-1.8mV)
2. ℓ_pu/ℓ_cn > 2.0: ❌ (현재 ~1.0, toy data 한계)
3. Corner Vmin error > 3σ: ❌

실 HSPICE data 도착 후 재평가 필요.

---

## 5. 결론 및 향후 계획

### 5.1 현재까지 달성

- ✅ GP + 미분 가능 물리 레이어 기반 Vmin 추정 파이프라인 구축
- ✅ 물리 기반 제약 조건 (L_mono, L_boundary, L_pelgrom) 구현
- ✅ Ablation study: L_boundary 20.9% Vmin RMSE 개선 확인
- ✅ 3D → 8D 입력 공간 확장 인터페이스 준비
- ✅ 입력 정규화 (StandardScaler) 도입
- ✅ 검증 파이프라인 구축 (test_pipeline.py, demo_pvta_contour.py)

### 5.2 남은 과제

| 우선순위 | 과제 | 설명 |
|----------|------|------|
| 🔴 1순위 | **HSPICE 실데이터 수집** | Option A (486 conditions × 800 MC) or Option B (1200 cond × 240 MC) |
| 🟡 2순위 | **실데이터 기반 Lengthscale 재분석** | ℓ_cn < ℓ_pu 검증 |
| 🟡 2순위 | **GP→NN 전환 평가** | 실데이터에서 Hausdorff, lengthscale 재측정 |
| 🟢 3순위 | **PINN 구현** | NN + PDE residual (L_boundary contour loss) |
| 🟢 3순위 | **논문 초안 작성** | DAC/ISCAS 타겟 |

---

## 6. 참조

| 문서 | 위치 | 설명 |
|------|------|------|
| Master Plan | `sram_vmin_inverse_estimation_plan.md` | 전체 프로젝트 계획 |
| Ablation Log | `toy_project/physics_ablation/DECISIONS.md` | Ablation trial & error |
| Orchesration Guide | `AGENT.md` | Agent 전환 가이드 |
| 데이터 추출 Spec | `toy_project/HSPICE_DATA_EXTRACTION_DETAILS.md` | PDK 엔지니어용 매뉴얼 |
| Agent 정의 | `~/.config/opencode/oh-my-openagent.json` | Atlas/Prometheus/Hephaestus 설정 |

---

*이 문서는 프로젝트 진행에 따라 지속적으로 업데이트됩니다.*
