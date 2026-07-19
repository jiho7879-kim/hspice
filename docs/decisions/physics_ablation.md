# Physics-Constrained GP Ablation — Decisions & Trial Log

> **목적**: 다음 의사결정 참고 및 시행착오/결과 해석 지원  
> **생성일**: 2026-07-01  
> **관련**: toy_project/ → physics_ablation/ 전환

> **⚠️ CORRECTION 2026-07-06** — 본 문서의 수치는 입력 스케일링이 누락된 GP +
> no-op L_pelgrom으로 얻은 것이다. 수정된 코드의 재실행 결과(baseline 1.26mV,
> +boundary 0.92mV, all 0.90mV)와 결론 정정("스케일링이 1차 요인, corner anchor는
> 잔여 -27%", "ℓ_pu/ℓ_cn≈1.0은 unscaled 아티팩트")은
> `session_20260706_root_cause_fixes.md` §5-6 참조. 이하 수치는 역사 기록.

---

## 1. 핵심 논의 (3 Topics)

### Topic 1: Toy Project → Full Paper Transition Criteria

| 단계 | 접근법 | 손실함수 | 데이터 |
|------|--------|----------|--------|
| **Toy (현재)** | GP + physics-constrained loss | L_mono + L_boundary + L_pelgrom | Analytic SNMR model |
| **Full Paper** | NN + PINN | PDE residual + L_mono + L_boundary + L_pelgrom | HSPICE simulation or silicon |

**Transition Trigger** (셋 중 하나라도 만족):
- GP의 Hausdorff distance > HSPICE noise floor (≈3-5mV)
- GP lengthscale 해석에서 PG>>PU ratio > 2.0 (GP가 물리적 sensitivity를 제대로 포착 못함)
- 특정 corner (FSG/SFG)에서 Vmin error가 다른 corner보다 3σ 이상 벗어남

**Decision**: Toy 단계에서는 "PINN"이라는 용어를 사용하지 않음. PINN은 NN + PDE loss 조합을 지칭하므로, GP 기반에서는 "physics-constrained GP" 또는 "physics-informed loss"라고 부름.

### Topic 2: L_boundary — Corner Anchor vs Contour Boundary Loss

| 항목 | Corner Anchor (채택) | Contour Boundary Loss (보류) |
|------|---------------------|-----------------------------|
| 구현 | 4 global corners × 6 Vop = 24개 virtual observation을 training data에 추가 | Vmin=0.6V contour에서 GP posterior의 contour error를 loss로 |
| 장점 | ExactGP에 자연스럽게 통합, gradient flow不需 | PINN에서 자연스러움 |
| 단점 | corner에만 강제, interior는 간접 영향 | 구현 복잡, toy에서는 overkill |
| 적용 | **Toy에서 사용** | Full paper NN+PINN에서 사용 예정 |

**Decision**:  
- Toy: Corner anchor (boundary data augmentation)  
- Full paper: Corner anchor + Contour boundary PINN loss  

**Corner 선정** (4 global corners, SRAM industry standard):

| Corner | common_N | PU | 의미 |
|--------|----------|-----|------|
| FSG | -60 mV | +60 mV | Fast NMOS, Slow PMOS (hot, SNMR worst) |
| SFG | +60 mV | -60 mV | Slow NMOS, Fast PMOS (cold, Vtrip worst) |
| FFG | -60 mV | -60 mV | Fast NMOS, Fast PMOS |
| SSG | +60 mV | +60 mV | Slow NMOS, Slow PMOS |

### Topic 3: Multi-Fidelity Loss Function Design

- **L_mono (Monotonicity)**: ∂μ/∂Vop > 0 — probe point collocation (PINN-style)
- **L_boundary (Corner Anchor)**: data augmentation — exact constraint  
- **L_pelgrom (Sigma Scaling)**: σ(Vop) = SIGMA₀ + SIGMA_VOP_SLOPE × (0.9 − Vop) — weak regularization

**Loss 조합**:

```
L_total = -log p(y|X,θ) + λ_mono·L_mono + λ_pelgrom·L_pelgrom
```

λ_mono = 100, λ_pelgrom = 1.0으로 설정 (L_mono는 gradient scale이 작으므로 큰 weight)

---

## 2. SRAM Industry Constraints (6가지)

User 공유:

1. **Vmin > 0**: SNMR 모델이 양의 Vmin을 가져야 함 (0.3V–0.9V range)
2. **SNMR–Vtrip Tradeoff**: common_N ↑ (NMOS slower) → PG leakage ↓ → Vmin ↓. PU ↑ (PMOS slower) → PU strength ↓ → Vmin ↑
3. **PG >> PU**: PG (pass gate) variation이 PU보다 Vmin에 큰 영향. Lengthscale에서 ℓ_cn < ℓ_pu 로 나타나야 함
4. **Corner Dependence**: FSG에서 SNMR minimum (Vmin max), SFG에서 Vtrip critical
5. **σ(Vop) Scaling**: Vop ↓ → σ ↑ (Pelgrom scaling). 근사: σ(Vop) = SIGMA₀ + slope × (0.9 − Vop)
6. **Global Mismatch Dominance**: toy data는 global variation만 고려 (local random mismatch는 향후)

---

## 3. Implementation Decisions

### 3.1 L_mono: Eval-Mode Posterior Gradient

**Problem**: GPyTorch `ExactGP.__call__()` in `train=True` returns **prior** only. The posterior mean's gradient w.r.t. input (∂μ/∂Vop) requires **posterior**, which is only available in eval mode.

**Solution**: Switch to `eval()`, compute posterior at probe points, then switch back.

```python
was_training = gp.training
gp.eval()
gp.prediction_strategy = None  # force recompute with current kernel params
output = gp(probe_grad)        # posterior at probe points
grad = torch.autograd.grad(output.mean.sum(), probe_grad, create_graph=True)
gp.train() if was_training else None
```

**Key Insight**: Setting `prediction_strategy = None` forces GPyTorch to recompute the cached Cholesky decomposition with CURRENT kernel parameters, preserving gradient flow to lengthscales. Using `del` removes the attribute entirely, causing `AttributeError` in `__call__()`.

**Limitation**: This requires 2 Cholesky decompositions per training iteration (one for MLL, one for L_mono posterior), making it O(n³) per iteration with n=2040 training points.

### 3.2 L_boundary: Data Augmentation

- 24 virtual observations (4 corners × 6 Vop levels)
- True values from analytic_snmr() — matches demo_pvta_contour.py exactly
- Concatenated to training data before GP construction
- No loss term needed — works naturally with ExactGP's exact inference

### 3.3 L_pelgrom: Weak Regularization

- Target: σ(Vop) = 0.015 + 0.004 × (0.9 − Vop)
- Applied only to sigma GP (not mu)
- `torch.no_grad()` for target computation, `create_graph=False`
- Weaker effect on toy data since sigma already well-modeled by Vop-only additive kernel

### 3.4 Checkpoint System (v2)

각 config별로 훈련된 GP weight를 `.pth` 파일로 저장:

```
results/gp_{config_name}_{mu|sigma}.pth
```

재실행 시 체크포인트가 있으면 로드하고 스킵. 같은 데이터를 쓰는 config(baseline↔mono, mono_boundary↔all)는 weight 재사용 가능.

---

## 4. Trial & Error Log

### Bug 1: `forward()` vs `__call__()` for Probe Gradient

- **Attempt 1**: `gp.forward(probe_grad)` — prior mean from ConstantMean()는 input에 무관한 constant 반환
- **Error**: `RuntimeError: One of the differentiated Tensors appears to not have been used in the graph`
- **Root Cause**: `ConstantMean`의 output은 input `probe_grad`에 의존하지 않음 → autograd graph 끊김
- **Fix**: posterior mean (`K(probe, X_train) · α`)는 input에 의존 → eval mode에서 `__call__()` 사용

### Bug 2: `del prediction_strategy → AttributeError`

- **Attempt 2**: `del gp.prediction_strategy` 후 eval-mode `gp(probe_grad)` 호출
- **Error**: `AttributeError: 'ExactGPModel' object has no attribute 'prediction_strategy'`
- **Root Cause**: `hasattr()`가 True 반환 (초기값 None) → `del`로 삭제 → `__call__()` line 305에서 `if self.prediction_strategy is None`가 AttributeError 발생
- **Fix**: `gp.prediction_strategy = None` (재설정, 삭제하지 않음)

### Bug 3: OOM on Large Grid

- **Error**: `RuntimeError: not enough memory: you tried to allocate 1866240000 bytes`
- **Root Cause**: 3600 test points(60×60 grid) × 2064 train points → GPyTorch가 생성하는 joint covariance matrix가 1.74GB
- **Fix 1**: grid 60→40 (1600 points)  
- **Fix 2**: `predict()`에 batch_size=1000 추가

### Performance Issue: L_mono Cholesky Overhead

- 2040 training points × 2 Choleskys/iteration (MLL + L_mono posterior) = 매우 느림
- Toy data 기준 예상: ~2-3분/config (L_mono 있는 경우), ~30초/config (없는 경우)
- **Optimizations**:
  - Warmup: 30회 이후 L_mono 적용
  - Skip: 3회마다 L_mono 적용 (interval=3)
  - Probe: n_probe=6→4 (216→64 points)
  - Max iter: 150→120

---

## 5. Ablation Configs

| Config | L_mono | L_boundary | L_pelgrom | 기대 효과 |
|--------|--------|------------|-----------|-----------|
| baseline | ✗ | ✗ | ✗ | Reference |
| +L_mono | ✓ | ✗ | ✗ | Interior gradient 개선, contour smoothness |
| +L_boundary | ✗ | ✓ | ✗ | Corner accuracy 개선, extrapolation |
| +Mono+Boundary | ✓ | ✓ | ✗ | Combined effect |
| +Mono+Boundary+Pelgrom | ✓ | ✓ | ✓ | Full physics |

**실제 결과 (2026-07-01)**:

| Config | mu R² | σ R² | Vmin RMSE | Hausdorff | Cos Sim | ℓ_pu/ℓ_cn |
|--------|-------|------|-----------|-----------|---------|-----------|
| Baseline | 0.9973 | 0.6301 | 6.52mV | 1.8mV | 0.9999 | 1.00 |
| +L_mono | 0.9973 | 0.6292 | 6.46mV | 2.1mV | 1.0000 | 1.00 |
| +L_boundary | 0.9978 | 0.6340 | **5.16mV** | 1.3mV | 0.9989 | 0.98 |
| +Mono+Boundary | 0.9978 | 0.6313 | 5.10mV | 1.2mV | 0.9999 | 1.00 |
| +Mono+Boundary+Pelgrom | 0.9978 | 0.6365 | **4.91mV** | 1.3mV | 0.9995 | 0.99 |

**Key Findings**:
- L_boundary alone: **20.9% Vmin RMSE reduction** (6.52→5.16mV)
- Full physics (All): **24.7% Vmin RMSE reduction** (6.52→4.91mV) — best config
- L_mono alone: negligible effect (6.52→6.46mV) — analytic data already monotonic
- All configs pass gradient direction check (dVmin/dcn < 0, dVmin/dpu > 0)
- **ℓ_pu/ℓ_cn ≈ 1.0 across ALL configs** — PG>>PU hierarchy NOT captured

**해석**:
- L_mono penalty = 0.000000 in all iterations → analytic model mu already satisfies ∂μ/∂Vop > 0. 실 HSPICE data에서는 non-monotonic region 존재 가능 → L_mono 효과 있을 것
- ℓ_pu/ℓ_cn ≈ 1.0인 이유: analytic model의 B_MU=0.001, C_MU=-0.0015로 cn과 PU sensitivity가 유사. 실 data에서는 PG >> PU이므로 ℓ_cn < ℓ_pu 나타나야 함
- L_pelgrom은 sigma GP training에서 pelgrom loss가 0.000298→0.000007로 감소, sigma R² 0.6301→0.6365 소폭 개선

---

## 6. Deep Result Analysis — Discussion 정리

### 6.1 L_boundary 효과가 이렇게 큰 이유?

24개 corner point만 추가로 Vmin RMSE가 20.9% 개선된 것은 **GP의 extrapolation 취약점**을 보여줌.

- Training data는 `common_N ∈ [-60, 60], PU ∈ [-60, 60]`에 분포
- Corner (예: FSG의 `cn=-60, pu=+60`)는 domain 극단 → GP가 true function과 다른 extrapolation
- 24개 virtual observation만으로 큰 보정 효과

**실 data 시사점**: Corner HSPICE simulation은 비용이 크지만, 적은 수의 corner anchor만으로 큰 효과를 볼 가능성 높음. 다만 toy data가 linear해서 효과가 과장되었을 수 있음 — real silicon은 더 nonlinear → anchor 영향 범위가 제한적일 수 있음.

### 6.2 L_mono = 0 — 진짜 문제일까?

Toy data에서 `∂μ/∂Vop = A_MU = 0.15 > 0`이 항상 만족 → penalty = 0.

**실 data도 마찬가지?** → SRAM SNMR-Vop는 일반적으로 monotonic. 하지만:
- Vop가 saturation 영역에서 derivative ≈ 0에 근접
- Low voltage extreme에서는 급격한 SNMR degradation으로 derivative 감소

**더 근본적 문제**: GP의 Vop lengthscale = 0.64-0.65로 매우 작음. Vop range [0.5, 1.0]에서 ℓ=0.65면 약 2-3개 point만으로 correlation 소멸. GP가 Vop sharp change를 이미 잘 포착 → L_mono의 추가 benefit 의문.

**L_mono가 필요한 조건**: GP의 Vop lengthscale이 크게 학습된 경우 (ℓ_Vop > 2-3), 즉 GP가 Vop sensitivity를 underestimation할 때.

### 6.3 ℓ_pu/ℓ_cn ≈ 1.0 — PG>>PU 미반영 원인

SRAM 물리의 가장 기본인 PG >> PU가 lengthscale에 전혀 반영되지 않음.

**원인 분석**:
1. **Model 자체의 문제**: `mu = 0.15·Vop + 0.001·cn - 0.0015·pu` — cn과 PU 계수 크기가 거의 같음. **Toy data 자체가 PG>>PU를 반영하지 않음**
2. **Input scaling**: cn ∈ [-60, 60], PU ∈ [-60, 60] — range 동일, scaling bias 없음
3. **GP의 한계**: Lengthscale 해석은 input isotropy 가정 → 실제 cn과 PU는 물리적 의미가 완전히 다름

**Toy data 수정 제안**:
```
mu = 0.15·Vop + 0.002·cn - 0.001·pu   (PG sensitivity 2x)
mu = 0.15·Vop + 0.003·cn - 0.001·pu   (PG sensitivity 3x)
```
이렇게 변경 시 GP가 PG>>PU를 학습하는지, physics constraint가 이를 강제하는지 테스트 가능.

### 6.4 L_pelgrom 효과가 미미한 이유

| Config | sigma R² | Vmin RMSE |
|--------|----------|-----------|
| Mono+Boundary | 0.6313 | 5.10mV |
| +Pelgrom (All) | 0.6365 | 4.91mV |

sigma R² +0.005, Vmin RMSE -0.19mV. Marginal.

**이유**: sigma GP가 이미 additive Vop kernel 사용 (`Vop_kernel(cn,pu) + cn_pu_kernel(vop)`) — 이 구조 자체가 analytic sigma = SIGMA₀ + SIGMA_VOP_SLOPE × (0.9-Vop)와 유사. Kernel 구조가 이미 물리를 반영 → L_pelgrom 추가 정규화 효과 제한적.

**실 data에서는?** sigma modeling이 더 복잡할수록 (local mismatch, random variation) L_pelgrom 효과 커질 수 있음.

### 6.5 Full Physics (4.91mV) — 의미 있는 개선인가?

Baseline (6.52mV) 대비 **24.7% 개선**. 수치상 인상적이지만:

- **절대 차이**: 4.91mV vs 6.52mV = 1.6mV
- **SRAM Vmin 관점**: Spec range 0.5-0.7V, 측정 noise ~2-3mV → 1.6mV는 유의미
- **Hausdorff 개선**: 1.8mV → 1.3mV (contour accuracy 확인)
- **그러나**: 개선의 95%는 L_boundary 하나로 설명 (6.52→5.16). L_mono+L_pelgrom 추가분 = 0.25mV (4.8%)

**결론**: Toy data 한정 **L_boundary가 95%의 개선을 설명**. Full physics 추가 benefit은 marginal.

### 6.6 Full Paper (NN+PINN) 전환 시사점

| 결정 | Toy 결과 | 실 data 예상 |
|------|---------|-------------|
| L_boundary 포함 | ✅ 무조건 (20.9% 개선) | Corner measurement 비용 대비 효과 큼 |
| L_mono 포함 | ❌ 효과 없음 (penalty=0) | 재평가 필요 — non-monotonic region에서 효과 |
| L_pelgrom 포함 | ⚠️ Marginal (0.25mV) | Sigma model 복잡도에 따라 효과 달라짐 |
| PG>>PU 검증 | ❌ Toy data 자체가 미반영 | 실 data에서 재검증 필수 |
| GP→NN+PINN 전환 | Transition trigger 未달성 | Hausdorff > 5mV or ℓ_pu/ℓ_cn > 2.0 or corner bias > 3σ |

### 6.7 Metric 신뢰성 — Area Overlap 문제

| Config | Hausdorff | Area Overlap |
|--------|-----------|-------------|
| Baseline | 1.8mV | 0.0000 |
| Mono+Boundary | 1.2mV | 1.0000 |
| All | 1.3mV | 1.0000 |

Hausdorff는 1.2-1.8mV로 비슷한데 Area Overlap이 0.0과 1.0으로 극단 분리.

**원인**: `extract_contour()`가 grid boundary에서 contour 폐곡선 형성 여부에 따라 area 계산 실패. Baseline의 contour가 grid 밖에서 닫혀 area=0이 된 것. **Area Overlap metric은 40×40 grid에서 신뢰하기 어려움.** Hausdorff를 primary contour metric으로 사용할 것.

---

## 7. Result Interpretation Guide

### Vmin Contour (Vmin=0.6V)
| 관찰 | 의미 | 조치 |
|------|------|------|
| L_mono config의 contour가 baseline보다 True에 가까움 | L_mono gradient 제약이 Vmin 예측 개선 | λ_mono 증가 or probe density 증가 |
| L_boundary config의 corner 근접도 우수 | Corner anchor가 extrapolation 도움 | 유지 |
| Hausdorff < 1mV | Toy data에서는 충분히 좋음 | Full paper 전환 고려 |
| Hausdorff > 5mV | GP로는 부족 | NN+PINN 전환 검토 |

### Lengthscale 분석
| ℓ_cn vs ℓ_pu | 의미 |
|-------------|------|
| ℓ_cn < ℓ_pu | PG가 PU보다 Vmin에 영향 큼 (물리적) |
| ℓ_cn ≈ ℓ_pu | GP가 두 변수를 유사하게 중요도 평가 |
| ℓ_cn > ℓ_pu | 비물리적 — constraint가 필요 |

### Gradient Check (중앙점 (0,0)에서 finite difference)
| ∂Vmin/∂cn | ∂Vmin/∂pu | 물리적 |
|-----------|-----------|--------|
| 음수 | 양수 | common_N ↑ → Vmin ↓, PU ↑ → Vmin ↑ |
| cos_sim ≈ 1.0 | | GP가 true gradient 방향을 잘 포착 |

---

## 8. 코드 구조

```
toy_project/
├── physics_ablation/
│   ├── __init__.py
│   ├── DECISIONS.md                  ← 이 문서
│   ├── src/
│   │   └── physics_constrained_surrogate.py
│   ├── run_physics_ablation.py
│   └── results/
│       ├── gp_{config}_{mu|sigma}.pth  ← checkpoint
│       ├── contour_comparison.png
│       ├── metrics_comparison.png
│       ├── error_maps.png
│       ├── gradient_table.txt
│       ├── lengthscale_table.txt
│       └── ablation_results.json
├── data/
│   └── demo_analytic.npz
└── src/
    ├── utils.py
    ├── toy_surrogate.py
    ├── toy_physics_layer.py
    └── toy_contour.py
```

---

## 9. Known Limitations

1. **L_mono computational cost**: Eval-mode Cholesky recomputation makes training ~5x slower
2. **Toy data fidelity**: Analytic SNMR은 real silicon보다 linear, GP가 쉽게 fitting
3. **σ prediction**: Vop-only additive kernel과 analytic $\sigma$가 유사 → L_pelgrom 효과 미미할 가능성
4. **No local mismatch**: Toy data는 global variation만 포함
5. **Grid resolution**: 40×40 contour grid (1600 points) — corner 근처 resolution 부족 가능성
6. **L_mono penalty = 0**: Analytic model의 mu가 Vop에 대해 strictly monotonic (A_MU=0.15)이므로 penalty가 항상 0. 실 data에서 non-monotonic region 있을 때 효과 기대
7. **Area Overlap = 1.0000 의문**: mono_boundary/all config에서 Jaccard index=1.0. Hausdorff 1.2-1.3mV이므로 contour가 거의 일치하는 것은 사실이나, 다른 config이 0.0인 것은 contour가 grid 밖에서 닫히지 않았기 때문일 수 있음. Area overlap metric의 grid 의존성 주의
8. **ℓ_pu/ℓ_cn ≈ 1.0**: Analytic model coefficients가 B_MU=0.001 vs C_MU=-0.0015로 유사 → PG>>PU hierarchy 학습 불가. 실 data에서는 ℓ_cn < ℓ_pu 예상
