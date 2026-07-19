# Execution Guide — Stage-by-Stage

## Overview

Two parallel stacks, three execution phases:

```
Toy Stack (Python analytic)          Real Stack (HSPICE + PDK)
┌─────────────────────┐             ┌─────────────────────────┐
│ Stage 1: 3D baseline│ ───Go──▶   │ Stage 4: 3D HSPICE val. │
│ Stage 2: 4D+Vwl     │ ───Go──▶   │ Stage 5: 4D+Vwl HSPICE  │
│ Stage 3: Inv. assist│             │ Stage 6: Full PDK (8D)  │
└─────────────────────┘             └─────────────────────────┘
```

**Principle**: Toy stage N must pass Go criteria BEFORE real stage N starts.
Toy is fast (<5 min), real is slow (>8 hours). Fail fast on toy.

---

## Stage 1 — 3D Toy Baseline (cn, pu, Vop)

**목적**: GP surrogate + contour extraction pipeline 검증.
**상태**: ✅ DONE (demo.py로 검증 완료)

### 실행
```bash
cd python
python scripts/demo.py
# → results/demo_pvta_contour.png 생성
# → mu RMSE ~0.003, sigma RMSE ~0.0005
```

### 사용 데이터
| 항목 | 내용 |
|------|------|
| Raw data | Analytic model (synthetic) |
| 생성 코드 | `demo.py` 내 analytic_snmr() |
| X shape | (N, 3) = [cn, pu, Vop] |
| y shape | (N, 2) = [mu_SNMR, sigma_SNMR] |

### Go / No-Go Criteria

| 항목 | Go 조건 | 측정 방법 |
|------|---------|----------|
| mu RMSE | < 0.01 | `demo.py` 출력 |
| sigma RMSE | < 0.001 | `demo.py` 출력 |
| Contour 추출 | Vmin=0.6V contour ≥ 20 pts | `extract_contour()` 결과 |
| Hausdorff | < 10 mV | `contour.compute_full_pipeline()` |
| Vmin (0,0) | 0.5 ~ 0.8 V | `gradient_check()` |

> **FAIL 시**: GP kernel 변경 (Matern 3/2, RBF) 또는 n_iter/train set 증가 후 재시도.

---

## Stage 2 — 4D+Vwl Toy (cn, pu, Vop, Vwl)

**목적**: Vwl 차원 확장시 GP 학습 + inverse assist estimation 동작 검증.

### 실행

```bash
cd python
python scripts/demo_4d.py
# → results/demo_4d_contour.png
# → results/demo_4d_assist.png
```

`scripts/demo_4d.py` (신규, 필요시 작성):
```python
# 1. 4D analytic data 생성 (cn, pu, Vop, Vwl)
#    mu = A*Vop + B*cn + C*pu + E*(Vop-Vwl) + D
#    sigma = SIGMA0 + SIGMA_VOP*(0.9 - Vop) + SIGMA_VWL*(Vop-Vwl)
# 2. GP surrogate train (4D)
# 3. compute_vmin_on_grid(vwl_fixed=each_level)
# 4. estimate_required_assist(target_vmin=0.6)
# 5. Plot: Vmin contour @ 각 Vwl + Assist map
```

### 사용 데이터

| 항목 | 내용 |
|------|------|
| Raw data | Analytic model + Vwl term (`src/physics.py`에 이미 구현) |
| 샘플링 | `build_dataset(N_COND=400)` → Vwl은 각 (cn,pu,Vop)에 WLUD_FACTORS 5레벨 |
| X shape | (N, 4) = [cn, pu, Vop, Vwl] |
| y shape | (N, 2) = [mu_SNMR, sigma_SNMR] |

### Go / No-Go Criteria

| 항목 | Go 조건 | 비고 |
|------|---------|------|
| mu RMSE (4D) | < 0.015 | Vwl 추가로 3D보다 약간 높을 수 있음 |
| sigma RMSE (4D) | < 0.0015 | |
| Vwl monotonicity | 모든 (cn,pu)에서 Vwl↓ → Vmin↓ 성립 | `compute_vmin_vs_vwl()`로 확인 |
| Assist feasible ratio | 전체 grid의 ≥ 30%에서 추정 가능 | `estimate_required_assist()` |
| Assist 오차 | Vmin(vwl_required) - target < 20 mV | 검증 |

> **No-Go**: Vwl sensitivity가 너무 작아서(E_MU=0.05로도 Vmin 변화 < 50mV) → E_MU 증대 또는 WLUD 범위 확장
> **No-Go**: monotonicity 깨짐 → Vwl 범위 축소 (WLUD 0.7~1.0 → 0.8~1.0)

---

## Stage 3 — Inverse Assist Estimation Validation (Toy)

**목적**: Target Vmin 달성에 필요한 Vwl 추정 정확도 검증.

### 실행

```python
from src.physics_layer import estimate_required_assist, compute_vmin_vs_vwl

# 4D surrogate (Stage 2에서 학습된 모델)
surrogate_fn = lambda X: surr.predict(X)  # (mu, sigma)

# Required assist map
CN, PU, vwl_req, vmin_ach = estimate_required_assist(
    surrogate_fn, target_vmin=0.55, vop_fixed=0.7,
    n_grid=40, vwl_lo=0.35, n_vwl_eval=15,
)

# 검증: ground truth와 비교
vwl_test = vwl_req[~np.isnan(vwl_req)]
# 각 (cn,pu)에서 analytic_snmr(cn,pu,Vop=0.7,Vwl=vwl_test) → Vmin 계산
# Vmin이 target_vmin ± 10mV 이내인지 확인
```

### Go / No-Go Criteria

| 항목 | Go 조건 |
|------|---------|
| Assist 추정 RMSE | < 15 mV (Vmin 기준) |
| Infeasible flag 정확도 | 100% (실제 infeasible 영역을 정확히 탐지) |
| Binary search 수렴 | 모든 feasible point에서 20 iteration 내 수렴 |

> **No-Go**: 추정 오차 큼 → `n_vwl_eval` 증가 (15→25) 또는 interpolation 방식 개선
> **참고**: 이 단계는 HSPICE 돌리기 전에 inverse estimation 알고리즘 자체를 검증하는 것이 목적.

---

## Stage 4 — 3D HSPICE Validation (Real Data)

**목적**: 실제 HSPICE simulation data로 3D GP surrogate 학습 + contour 검증.

### 사전 준비

1. **Template 확인** (`templates/sram_cell_pvta.sp`)
   - `_render_vth_skew()`의 정규식이 사내 .in template 형식과 일치하는지 확인
   - template에 `{{ VWL }}`, `{{ TEMP }}` 등 필요한 변수가 정의되어 있는지 확인

2. **Validation deck 생성** → HSPICE 실행 → CSV 수집
```bash
cd python

# (a) Validation deck (TT, 6 Vop)
python scripts/gen_hspice.py --validation --out_dir ../decks/val

# (b) Full deck (200 cond, 6 Vop)
python scripts/gen_hspice.py --stage 1 --n_cond 200 --out_dir ../decks/stage1

# (c) HSPICE 실행 (farm or local)
# hspice64 -i decks/stage1/cond_000001.sp -o decks/stage1/cond_000001
# ...

# (d) 결과 CSV 생성 (예: mt0 → CSV 변환은 사내 pipeline에 맞게)
# CSV columns: common_N_shift, PU_shift, Vop, mu_SNMR, sigma_SNMR
```

### 실행
```bash
cd python

# CSV → dataset.npz 변환
python -c "
from src.hspice_io import parse_csv_to_dataset
X, y = parse_csv_to_dataset('../results/stage1_raw.csv')
np.savez('../data/dataset_stage1.npz', X=X, y=y)
"

# GP 학습
python scripts/train.py --data ../data/dataset_stage1.npz --out ../results/stage1

# Contour plot
python scripts/diagnostics.py --data ../data/dataset_stage1.npz --out ../results/stage1
```

### Go / No-Go Criteria

| 항목 | Go 조건 | 비고 |
|------|---------|------|
| Simulation 수렴률 | ≥ 95% | .mt0 파일이 정상 생성된 비율 |
| CSV NaN 비율 | < 5% | MC 수렴 실패 조건 제외 |
| mu_SNMR range | [0.05, 0.35] V | TT @ FSG corner 포함 |
| sigma_SNMR range | [0.005, 0.05] V | |
| GP mu RMSE (hold-out) | < 0.02 V | 학습된 GP의 hold-out 오차 |
| GP sigma RMSE (hold-out) | < 0.005 V | |
| Vmin range | [0.4, 0.9] V | 0.4V 밖이면 Vop 범위 재설정 |
| FSG corner Vmin | < SFG corner Vmin | FSG(SNMR worst)가 가장 높은 Vmin |
| Hausdorff distance | < 20 mV (hold-out) |

> **No-Go 예시**:
> - 수렴률 < 95% → MC_RUNS 증가 또는 simulation option 조정
> - FSG Vmin < SFG Vmin → shift convention 확인 (positive=slower)
> - GP RMSE 큼 → n_cond 증가 (200 → 400)
> - CSV NaN > 5% → MC_RUNS=2000으로는 부족, 5000으로 증가

---

## Stage 5 — 4D+Vwl HSPICE Validation

**목적**: Vwl assist 포함 실제 simulation으로 4D GP 학습 + inverse assist estimation.

### 실행

```bash
cd python

# (a) Vwl 포함 deck 생성
python scripts/gen_hspice.py --stage 2 --n_cond 200 --out_dir ../decks/stage2

# (b) HSPICE 실행 (Vwl per condition)
# → 200 cond × 6 Vop × 5 Vwl = 6,000 decks
# → ~8 hours 예상

# (c) CSV → dataset
# CSV columns: common_N_shift, PU_shift, Vop, Vwl, mu_SNMR, sigma_SNMR

# (d) GP 학습 + contour
python scripts/train.py --data ../data/dataset_stage2.npz --out ../results/stage2

# (e) Inverse assist estimation
python -c "
from src.physics_layer import estimate_required_assist
import joblib
surr = joblib.load('../results/stage2/surrogate.pkl')
CN, PU, vwl_req, vmin_ach = estimate_required_assist(
    lambda X: surr.predict(X), target_vmin=0.55, vop_fixed=0.7, n_grid=50,
)
np.savez('../results/stage2/assist_map.npz', CN=CN, PU=PU, vwl_req=vwl_req, vmin_ach=vmin_ach)
"
```

### Go / No-Go Criteria (Stage 4 모든 조건 + 아래 추가 조건)

| 항목 | Go 조건 | 비고 |
|------|---------|------|
| Vwl sensitivity | Vwl=Vop*0.8에서 Vmin ≥ 20mV 감소 | Vwl 효과가 측정 가능한 크기인지 |
| GP ARD lengthscale(Vwl) | 유한값 (발산하지 않음) | Vwl 차원이 GP에 의해 중요하게 학습되는지 |
| Vwl monotonicity (data) | 90% 이상의 조건에서 성립 | 실제 data에서도 Vwl↓→Vmin↓인지 |
| Assist feasible ratio | ≥ 20% | Target Vmin 달성 가능한 (cn,pu) 비율 |
| Assist map smoothness | 급격한 변화 없음 | (cn,pu) 공간에서 연속적인 assist 분포 |

> **No-Go**: Vwl sensitivity < 20mV → WLUD 범위 확대 (0.6~1.0)
> **No-Go**: ARD lengthscale(Vwl) 발산 → Vwl effect가 noise 수준, data quality 확인
> **No-Go**: Monotonicity < 90% → simulation noise 의심, MC_RUNS 증가

---

## Stage 6 — Full PDK (8D)

**목적**: Final paper-grade GP surrogate with process variation + temperature.

### 실행

```bash
cd python

# Sobol DOE (나머지 7D Sobol, Vop만 6 level grid)
python -c "
from src.utils import sample_common_n_pu
import numpy as np
# 3,000 cond × 6 Vop = 18,000 condition points
conditions = sample_common_n_pu(3000, seed=42)
np.save('../decks/stage6/conditions.npy', conditions)
print(f'Generated {len(conditions)} conditions')
"

# deck generation: Sobol over W, sigmaL, sigmaG, mu, Temp at each condition
# → gen_hspice.py --stage 3 --n_cond 3000 (requires CLI update)

# HSPICE farm run
# → 18,000 decks × MC_RUNS 5,000 = 90M simulations
# → ~30 hours on farm

# CSV: common_N_shift, PU_shift, Vop, Vwl, W, sigmaL, sigmaG, mu_mobility, Temp, mu_SNMR, sigma_SNMR

# GP 학습
python scripts/train.py --data ../data/dataset_stage6.npz --ablation --out ../results/stage6
```

### Go / No-Go Criteria

| 항목 | Go 조건 |
|------|---------|
| 모든 GP lengthscale | 수렴, 발산하는 차원 없음 |
| Ablation: L_mono 효과 | monotonicity violation < 5% |
| Ablation: L_boundary 효과 | corner Vmin 오차 < 30 mV |
| Vmin RMSE (hold-out) | < 25 mV |
| 물리적 일관성 | FSG > SSG > FFG/SFG 순서 유지 |
| Assist 추정 | 8D GP 위에서도 stable |

---

## 요약: 실행 순서

```
Step 0: Template 설정
  └─ _render_vth_skew() 정규식을 사내 .in 파일 형식에 맞게 조정
  └─ template에 {{ VWL }}, {{ TEMP }} 변수 확인

Step 1: Stage 1 (Toy 3D) ← DONE
  └─ python scripts/demo.py
  └─ Go check → 통과

Step 2: Stage 2 (Toy 4D+Vwl) 
  └─ python scripts/demo_4d.py (작성 필요)
  └─ Go check → Vwl monotonic + assist feasible

Step 3: Stage 3 (Toy Inverse Assist)
  └─ estimate_required_assist() 검증
  └─ Go check → 추정 오차 < 15 mV

  ──── Toy 완료, Real 시작 ────

Step 4: Stage 4 (HSPICE 3D)
  └─ gen_hspice.py --stage 1 → HSPICE → CSV → train
  └─ Go check → 수렴률, RMSE, FSG>SFG

Step 5: Stage 5 (HSPICE 4D+Vwl)
  └─ gen_hspice.py --stage 2 → HSPICE → CSV → train
  └─ Go check → Vwl sensitivity, ARD lengthscale

Step 6: Stage 6 (Full 8D PDK)
  └─ Sobol DOE → HSPICE farm → GP + ablation
  └─ Final verification
```

## Quick Reference: 커맨드 요약

| 작업 | 명령어 |
|------|--------|
| 3D deck 생성 | `python scripts/gen_hspice.py --stage 1 --n_cond 200` |
| 4D+Vwl deck 생성 | `python scripts/gen_hspice.py --stage 2 --n_cond 200` |
| Validation deck | `python scripts/gen_hspice.py --validation` |
| CSV → dataset | `parse_csv_to_dataset()` in python |
| GP 학습 | `python scripts/train.py --data <path>` |
| Contour validation | `compute_full_pipeline()` in python |
| Inverse assist | `estimate_required_assist()` in python |
| Demo (3D) | `python scripts/demo.py` |
| Demo (4D) | `python scripts/demo_4d.py` (작성 필요) |
