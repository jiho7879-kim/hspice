# Deck Scenarios — Stage D Full 9D Pilot + Reduced Models

> 전제: full까지 무조건 간다. 시간 절약이 목표.
> 변경: σG(global) 제거 — PVTA .lib에 포함됨.
> 변경: device별(L/PG/PD) local(σL) + mobility(mom) 각각 독립 차원.
> 변경: Vop {0.4~0.8} 5레벨 (0.9 제거, Vmin crossing에 영향 없음 확인 완료)
> Device 影響度 (실측 기준): SNMR = PG > PD > PU, Vtrip = PG > PU > PD

---

## 0. Stage D 차원 구성 (최종)

### Vth shift (global, VTMSKEW)
| 차원 | 기호 | 범위 | Template 파라미터 |
|------|------|------|-------------------|
| common_N shift | **cn** | −60 ~ +60 mV | VTMSKEW_PG1/2, VTMSKEW_PD1/2 |
| PG-PD skew | **sk** | −20 ~ +20 mV | PG = cn+sk, PD = cn−sk |
| PU shift | **pu** | −60 ~ +60 mV | VTMSKEW_PU1/2 |

### Local mismatch (VTSL — σL, device별)
| 차원 | 기호 | 범위 | Template 파라미터 |
|------|------|------|-------------------|
| PU local σ | **lpu** | 0.7 ~ 1.3 (±30%, ×nominal) | VTSLSKEW_PU1/2 |
| PG local σ | **lpg** | 0.7 ~ 1.3 (±30%, ×nominal) | VTSLSKEW_PG1/2 |
| PD local σ | **lpd** | 0.7 ~ 1.3 (±30%, ×nominal) | VTSLSKEW_PD1/2 |

### Mobility (MOM, device별)
| 차원 | 기호 | 범위 | Template 파라미터 |
|------|------|------|-------------------|
| PU mobility | **mpu** | 0.7 ~ 1.3 (×nominal) | MOMSKEW_PU1/2 |
| PG mobility | **mpg** | 0.7 ~ 1.3 (×nominal) | MOMSKEW_PG1/2 |
| PD mobility | **mpd** | 0.7 ~ 1.3 (×nominal) | MOMSKEW_PD1/2 |

### Grid
| 차원 | 값 |
|------|-----|
| **Vop** | 5 levels {0.4, 0.5, ..., 0.8} |
| **Temp (SNMR)** | 125°C 고정 |
| **Temp (Vtrip)** | −40°C 고정 |

**총 연속 차원: 9D** (cn, sk, pu, lpu, lpg, lpd, mpu, mpg, mpd)

### Vop 0.9 제거 근거

Stage 4 real HSPICE data(201 conditions × 6 Vop) 검증 결과:

- Vmin(Z=4) crossing: **81.7%** Vop 0.4–0.5, **16.7%** Vop 0.5–0.6, **1.7%** Vop 0.6–0.7
- Vop 0.9에서 crossing하는 조건: **0개** (전체 조건 중 0%)
- Z=4~6 모든 target에서 Vop 0.9 제거 시 **Vmin error = 0.000 mV**
- Vop 0.9는 mu_SNMR plateau 영역 → Vmin interpolation에 전혀 관여하지 않음

→ Vop 레벨 6→5, **decks 16.7% 절감**.

---

## 0.5. Overlap 제거 전략 — Stage 간 중복 sim 방지

### 원칙
각 stage의 Sobol 조건을 생성할 때, **이전 stage에서 이미 sim한 점과 겹치는 조건은 제외**하고,
겹친 위치의 data는 이전 stage 결과를 재사용한다. 목표 cond 수(target)는 유지.

```
신규 sim 수 = target cond 수 − overlap (기존 stage에서 재사용)
```

### Stage A → Stage B 예시

```
Stage A: 200 cond (cn, pu)   ← 이미 sim 완료, sk=0
Stage B 목표: 400 cond (cn, sk, pu)

1. Sobol 400개를 3D(cn,sk,pu)에서 생성
2. 각 점에 대해:
   - |sk| < ε(=2mV) AND (cn,pu)가 Stage A의 어떤 점과 근접 → 제거
   - 나머지 → keep
3. 예: 50개 제거, 350개 keep
4. 신규 sim: 350개 (MC=5K)
5. 학습 data: Stage A에서 겹친 50개 (MC=2K) + 신규 350개 (MC=5K) = 400 cond
   → 단, MC가 다를 경우(Stage A=2K, B=5K), 재사용 data의 MC 통일 필요.
```

> ⚠ MC 불일치 주의: Stage A(2K) data를 Stage B(5K)와 합칠 때 noise level이 다름.
> 해결책:
>   a) Stage A를 2K로 사용, Stage B GP 학습 시 heteroscedastic likelihood
>   b) 또는 Stage A도 5K로 재sim (overlap 제거 의미 없어짐)
>   c) GP는 MC 차이를 학습하지 않으므로, MC가 다르면 SNMR mu/sigma 추정치의
>      신뢰도만 다를 뿐. GP는 입력 X에 대한 y만 학습하므로 MC 불일치는 허용됨.
>      단, sigma_SNMR의 noise level이 MC에 따라 달라지는 점은 고려.

### Stage A = 순수 PVTA Global Corner Baseline

Stage A(lpu=lpg=lpd=mpu=mpg=mpd=1.0)의 핵심 의미:

```
Stage A 조건 = (cn, sk, pu, l*=1.0, m*=1.0)
            = device local/mobility는 전부 nominal
            = Vmin = f(cn, sk, pu) = 순수 PVTA global corner에서의 Vmin
```

즉 Stage A는 **"이 PDK의 TT/FSG/SFG corner에서 Vmin이 몇 V인가"**라는
가장 근본적인 질문에 대한 baseline이다.

- 고차원(9D) GP에서 (cn,sk,pu) submanifold를 정의하는 기준점 역할
- lpu/lpg/lpd/mpu/mpg/mpd가 nominal에서 벗어날수록 Stage A의 Vmin에서
  국소적으로 편향되는 구조 → Stage A가 정확해야 고차원 extrapolation도 신뢰 가능
- 이것이 overlap을 제거하면서도 Stage A data를 재사용하는 이유:
  Stage A는 local/mobility dim이 0인 "pure global corner" 조건에서 sim된
  유일한 dataset이며, 이후 모든 stage의 submanifold anchor가 됨.

### Stage D pilot에 확장

```
Stage D pilot 목표: 500 cond (9D) 
이전 stage: A(200) + B(400) = 600 cond in (cn,sk,pu) space

1. Sobol 500개를 9D에서 생성
2. 각 점에 대해:
   - (cn,sk,pu)가 A+B의 어떤 점과 근접 AND
     (lpu,lpg,lpd,mpu,mpg,mpd) 모두 nominal(≈1.0) → 제거
   - 나머지 → keep
3. 예: 80개 제거, 420개 keep
4. 신규 sim: 420개 (MC=2K)
5. 학습 data: A+B에서 겸친 80개 + 신규 420개 = 500 cond
```

### Cumulative 효과

| Stage | Target cond | Overlap (재사용) | 신규 sim | 누적 data |
|-------|:----------:|:----------------:|:--------:|:---------:|
| A | 200 | 0 | **200** | 200 |
| B | 400 | ~50 (from A) | **~350** | 550 |
| D pilot | 500 | ~80 (from A+B) | **~420** | 970 |
| D full | 2,000 | ~200 (from A+B+Dp) | **~1,800** | 2,770 |
| **Total** | | | **~2,770** | 2,770 |

vs naive (no overlap removal): 200+400+500+2,000 = 3,100 → **~10% sim 절약**.

## 1. Full 9D Sobol Sensitivity Pilot (BASE)

> 결정: LOC/MOM 분할 없이 **9D single pilot**으로 진행.
> 근거: loc/mom 모두 단조함수 → Matern 5/2 + ARD + L_mono로 효율적 학습 가능.
> 500 Sobol points의 1D stratification 우수(차원당 max gap ~1.4%) → GP interpolation에 충분.
> 분할 시(256+256=512 cond) cost는 유사하나, loc×mom interaction(lpg×mpg 등)을
> sensitivity 분석에서 볼 수 없는 단점이 더 큼.

사용자 선택: **A를 base**로 full 9D sensitivity pilot 실행.

### 조건

SNMR과 Vtrip은 별도 Sobol set. 상세 quadrant weight는 §1.5 참조.

| 항목 | SNMR pilot | Vtrip pilot |
|------|:----------:|:-----------:|
| 차원 | 9D | 9D |
| Condition | **500 Sobol** (weighted: Q2 45%) | **500 Sobol** (weighted: Q4 45%) |
| Vop | 5레벨 grid | 5레벨 grid |
| 온도 | 125°C | −40°C |
| MC | 2,000 | 2,000 |
| **Deck 수** | **500 × 5 = 2,500** | **500 × 5 = 2,500** |
| 출력 | SNMR (mu, sigma) | Vtrip (mu, sigma) |

### Sampling

SNMR pilot (Q2=45% weighted):
```python
from scipy.stats.qmc import Sobol
import numpy as np

# Quadrant weights (SNMR: Q2 집중)
quadrant_weights = {
    (-1, +1): 0.45,  # Q2 (FSG)
    (-1, -1): 0.20,  # Q1 (FFG)
    (+1, +1): 0.15,  # Q3 (SSG)
    (+1, -1): 0.20,  # Q4 (SFG)
}
names = ['cn','sk','pu','lpu','lpg','lpd','mpu','mpg','mpd']
bounds = {
    'cn':  (-60, 60), 'sk':  (-20, 20), 'pu':  (-60, 60),
    'lpu': (0.7, 1.3), 'lpg': (0.7, 1.3), 'lpd': (0.7, 1.3),
    'mpu': (0.7, 1.3), 'mpg': (0.7, 1.3), 'mpd': (0.7, 1.3),
}

n_total = 500
points = []
for (cn_sign, pu_sign), w in quadrant_weights.items():
    n = int(n_total * w)
    if n == 0: continue
    sobol = Sobol(d=9, scramble=True)
    s = sobol.random(n)                          # (n, 9) uniform in [0,1]^9
    # quadrant마다 cn과 pu의 부호를 제한
    for i, name in enumerate(names):
        lo, hi = bounds[name]
        if name == 'cn':
            lo_s = 0.0 if cn_sign > 0 else -60.0
            hi_s = 60.0 if cn_sign > 0 else 0.0
        elif name == 'pu':
            lo_s = 0.0 if pu_sign > 0 else -60.0
            hi_s = 60.0 if pu_sign > 0 else 0.0
        else:
            lo_s, hi_s = lo, hi
        s[:, i] = lo_s + (hi_s - lo_s) * s[:, i]
    points.append(s)
samples = np.vstack(points)  # (500, 9)
```

Vtrip pilot (Q4=45% weighted):

```python
# Quadrant weights (Vtrip: Q4 집중)
quadrant_weights_vtrip = {
    (-1, +1): 0.10,  # Q2
    (-1, -1): 0.15,  # Q1
    (+1, +1): 0.30,  # Q3
    (+1, -1): 0.45,  # Q4 (SFG) — Vtrip worst
}
# 동일한 구조로 500점 생성
```
(SNMR/Vtrip 각각 500점, 소계 1,000점. 서로 다른 온도에서 sim되므로 overlap 허용.)

### Template 변수 매핑 (deck 1개당)
```
.param VTMSKEW_PU1 = '(pu) + (0)'          # mu
.param VTMSKEW_PG1 = '(cn + sk) + (0)'     # PG = cn + sk
.param VTMSKEW_PD1 = '(cn - sk) + (0)'     # PD = cn - sk
.param VTMSKEW_PU2 = '(pu) + (0)'
.param VTMSKEW_PG2 = '(cn + sk) + (0)'
.param VTMSKEW_PD2 = '(cn - sk) + (0)'

.param VTSLSKEW_PU1 = '(lpu) + (0)'        # local σ PU
.param VTSLSKEW_PG1 = '(lpg) + (0)'        # local σ PG
.param VTSLSKEW_PD1 = '(lpd) + (0)'        # local σ PD
( same for _PU2, _PG2, _PD2 )

.param MOMSKEW_PU1 = '(mpu) + (0)'         # mobility PU
.param MOMSKEW_PG1 = '(mpg) + (0)'         # mobility PG
.param MOMSKEW_PD1 = '(mpd) + (0)'         # mobility PD
( same for _PU2, _PG2, _PD2 )
```

### Vtrip pilot (Vtrip template 준비되면 실행)
SNMR과 **별도 Sobol set**으로 실행 (quadrant 가중치 상이).
단 −40°C, Vtrip .MEASURE. 상세는 §1.5 참조.

---

## 1.5. SNMR / Vtrip 분리 구조 — Vmin = smooth_max(SNMR, Vtrip)

### 구조적 분리 이유

SNMR(125°C)과 Vtrip(−40°C)은 **온도가 달라 하나의 deck에서 동시 측정 불가**.
따라서 두 metric은 별도 deck, 별도 Sobol set으로 GP를 각각 학습한다.
Sim cost는 전혀 늘지 않는다 — 오히려 각 metric에 최적인 data를 독립적으로
선택할 수 있어 더 효율적이다.

```
┌─ Sobol set A (quadrant-weighted for SNMR) → SNMR deck @125°C → GP_SNMR(cn, sk, pu, l*, m*) → mu_SNMR, sigma_SNMR
└─ Sobol set B (quadrant-weighted for Vtrip) → Vtrip deck @-40°C → GP_Vtrip(cn, sk, pu, l*, m*) → mu_Vtrip, sigma_Vtrip
```

### Vmin = smooth_max(Vmin_SNMR, Vmin_Vtrip)

Vmin은 두 metric 중 **큰 쪽**으로 결정된다:

```
Vmin(p) = max( Vmin_SNMR(p),  Vmin_Vtrip(p) )
```

이 max()는 비볼록(non-convex) 함수이므로 GP surrogate에 그대로 쓰면
미분 기반 최적화에 문제가 생길 수 있다. 대신 **부드러운 근사**를 사용한다:

```
Vmin(p) ≈ smooth_max(Vmin_SNMR, Vmin_Vtrip, α)
         = softplus( Vmin_SNMR - Vmin_Vtrip, α ) + Vmin_Vtrip
         = α · log(1 + exp((Vmin_SNMR - Vtrip_Vmin) / α)) + Vmin_Vtrip
```

α → 0: max()에 수렴. α > 0: 항상 미분 가능.

### Worst-corner priority — 비볼록 문제는 없음

SNMR과 Vtrip의 worst corner는 다르므로, **실제 Vmin이 관심 있는 영역에서는
비볼록 문제가 발생하지 않는다:**

| Quadrant | Corner | SNMR Vmin | Vtrip Vmin | Vmin 결정 | 비고 |
|----------|--------|:---------:|:----------:|:---------:|------|
| **Q2** (cn−, pu+) | FSG | **높음** | 낮음 | **SNMR** | SNMR worst, Vtrip min에 가까움 |
| **Q4** (cn+, pu−) | SFG | 낮음 | **높음** | **Vtrip** | Vtrip worst, SNMR min에 가까움 |
| Q1 (cn−, pu−) | FFG | 중간~높음 | 중간~높음 | **crossover 가능** |
| Q3 (cn+, pu+) | SSG | 낮음~중간 | 낮음~중간 | **crossover 가능** |

FSG(→SNMR dominant)와 SFG(→Vtrip dominant)에서는 두 값이 명확히 갈리므로
smooth_max의 smoothing factor α 영향이 거의 없다. Crossover 가능성이 있는
Q1/Q3은 Vmin이 낮아 최종 Vmin(Vmin_goal = Vmin @ Z=5)에 영향이 미미하다.

→ **worst Vmin 관점에서는 비볼록 문제가 사실상 없음.**
α는 수치 안정성(numerical stability)을 위해 작은 값으로 설정.

> **[리뷰 2026-07-09 정정]** α=0.01V는 교차점에서 α·ln2 = **6.93mV 편향**
> (수치 검증 완료, `revised_plan_review_20260709.md` §3.1). 목표 정확도
> 대비 큼. Q1/Q3 crossover 영역에서 Vmin을 systematic하게 높게 만듦.
> **α ≤ 0.002V 권장** (편향 <1.4mV). 평가는 exact max, gradient inversion
> 최적화에서만 smooth_max 사용. FSG/SFG worst corner는 gap≫20mV라 무관.

### Quadrant weighting rationale

Stage 4 real data(201 conditions)의 quadrant별 Vmin 분석 결과:

| Quadrant | cond 수 | SNMR Vmin @Z=5 | Vtrip Vmin @Z=5 | 비고 |
|----------|:-------:|:--------------:|:---------------:|------|
| Q1 (FFG) | 58 | 0.53V | 0.46V | Both medium |
| Q2 (FSG) | 55 | **0.57V** (worst) | 0.37V | **SNMR만 worst** |
| Q3 (SSG) | 46 | 0.46V | 0.45V | Both low |
| Q4 (SFG) | 42 | 0.35V | **0.54V** (worst) | **Vtrip만 worst** |

**SNMR**: Q2(FSG)가 Vmin variation의 대부분을 설명 (std=0.058V).
→ Q2에 높은 가중치를 두어 FSG 영역의 GP 정밀도 확보.

**Vtrip**: Q4(SFG)만이 유일하게 Vtrip worst. 나머지 quadrant는 Vtrip Vmin이
항상 SNMR보다 낮아 Vmin 결정에 관여하지 않음.
→ Q4에 집중. Q1~Q3은 Vtrip Vmin이 최종 Vmin에 영향이 없으므로 sampling 밀도 낮춤.

### Quadrant weight table

| Stage | Metric | Q1 (FFG) | Q2 (FSG) | Q3 (SSG) | Q4 (SFG) | 비고 |
|-------|--------|:--------:|:--------:|:--------:|:--------:|------|
| B | SNMR | 20% | **45%** | 15% | 20% | SNMR FSG 집중 |
| C | Vtrip | 15% | 10% | 30% | **45%** | Vtrip SFG 집중 |
| D-pilot | SNMR | 20% | **45%** | 15% | 20% | B와 동일 |
| D-pilot | Vtrip | 15% | 10% | 30% | **45%** | C와 동일 |
| D-full | SNMR | 20% | **45%** | 15% | 20% | |
| D-full | Vtrip | 15% | 10% | 30% | **45%** | |

총계는 각 stage별로 100%.

### Weighted Sobol generation 방식

Sobol은 균등 분포이므로, quadrant weight를 반영하려면 **rejection sampling**
또는 **CDF warping**을 사용한다.

```python
def weighted_sobol_sample(n_total, bounds, quadrant_weights, seed=42):
    """
    n_total: 목표 condition 수
    bounds: {name: (lo, hi)}  # cn, sk, pu, l*, m*
    quadrant_weights: {(cn_sign, pu_sign): weight}  
                      예: {(-1, +1): 0.45, ...}  # Q2에 45%
    """
    n_per_quadrant = {q: int(n_total * w) for q, w in quadrant_weights.items()}
    samples = []
    for (cn_sign, pu_sign), n in n_per_quadrant.items():
        sobol = Sobol(d=9, scramble=True, seed=seed)
        s = sobol.random(n)
        # 각 quadrant의 bounds로 scaling
        for name, (lo, hi) in bounds.items():
            s[:, idx] = lo + (hi - lo) * s[:, idx]
        # cn, pu 방향 보정 (cn_sign, pu_sign로 quadrant 한정)
        ...
    return np.vstack(samples)
```

SNMR과 Vtrip은 **별도 Sobol set을 각자의 quadrant weight로 생성**한다.
두 set의 overlap은 의도적으로 허용 (다른 온도에서 sim되므로 간섭 없음).

### GP 학습 구조

```
GP_SNMR:  X_SNMR → y_SNMR  (Matern 5/2 + ARD, 9D)
GP_Vtrip: X_Vtrip → y_Vtrip (Matern 5/2 + ARD, 9D)

Vmin(p) = smooth_max(GP_SNMR(p), GP_Vtrip(p), α=0.01)
```

두 GP는 완전히 독립적. Sobol set, 학습, prediction 모두 별도.
Weight 공유나 multi-task 학습 없음 — 간섭을 피하는 것이 더 중요.

---

## 2. Pilot 결과 → Sensitivity 분석

### 분석 방법

SNMR과 Vtrip은 별도 GP이므로 **각각 독립적으로 sensitivity 분석** 수행.

```python
from SALib.analyze import sobol as sobol_analyze

problem = {
    'num_vars': 9,
    'names': ['cn','sk','pu','lpu','lpg','lpd','mpu','mpg','mpd'],
    'bounds': [[-60,60],[-20,20],[-60,60],
               [0.7,1.3],[0.7,1.3],[0.7,1.3],
               [0.7,1.3],[0.7,1.3],[0.7,1.3]]
}

# SNMR sensitivity
Si_snmr = sobol_analyze.analyze(problem, Y_snmr_vmin, calc_second_order=False)

# Vtrip sensitivity
Si_vtrip = sobol_analyze.analyze(problem, Y_vtrip_vmin, calc_second_order=False)
```

출력: 각 metric별 각 차원의 **S1 (1차 민감도)** 와 **ST (전효과)**, Vmin 분산 기여도(%).

### Device 影響度 사전 정보 (참고)
| Metric | 1st | 2nd | 3rd |
|--------|-----|-----|-----|
| SNMR | PG | PD | PU |
| Vtrip | PG | PU | PD |

PG가 양쪽에서 지배적 → pilot에서 `lpg` (PG local σ)와 `mpg` (PG mobility)의
기여도가 높을 것으로 예상.

---

## 3. Pilot 결과 기반 시나리오 (Full Run)

### 시나리오 R1: SNMR reduced model (PG + PD 중심)

PG 위주 + PD 보조. device 影響度 PG>PD>PU 반영.

**dim if lpu, mpu 기여도 < 1% (PU 생략 가능):**
| 차원 | 기호 | 범위 | 비고 |
|------|------|------|------|
| common_N | cn | −60~+60 | PG+PD 공통 |
| PG-PD skew | sk | −20~+20 | PG/PD 분리 |
| PU shift | pu | −60~+60 | keep (SNMR 3순위지만 영향 있음) |
| PU local σ | lpu | 0.7~1.3 | 생략 가능 |
| PG local σ | lpg | 0.7~1.3 | **필수** |
| PD local σ | lpd | 0.7~1.3 | **필수** |
| PU mobility | mpu | 0.7~1.3 | 생략 가능 |
| PG mobility | mpg | 0.7~1.3 | **필수** |
| PD mobility | mpd | 0.7~1.3 | keep |

→ **7D model** (생략 시 5D): 1,000 cond × 5 Vop = **5,000 decks**

### 시나리오 R2: SNMR full 9D (보수적)

모든 차원 유지 → 9D GP.
**2,000 cond × 5 Vop = 10,000 decks** (MC=5K)

### 시나리오 W1: Vtrip reduced model (PG + PU 중심)

device 影響度 PG>PU>PD 반영.

| 차원 | 생략 가능? |
|------|-----------|
| lpd (PD local σ) | 생략 가능 (3순위) |
| mpd (PD mobility) | 생략 가능 |
| lpu, mpu | **유지** (2순위) |
| lpg, mpg | **필수** (1순위) |

→ **7D model**: 1,000 cond × 5 Vop = **5,000 decks**

### 시나리오 W2: Vtrip full 9D

모든 차원 유지 → 9D GP.
**2,000 cond × 5 Vop = 10,000 decks** (MC=5K)

### 시나리오 F (Full): SNMR + Vtrip 독립 GP → smooth_max

SNMR GP와 Vtrip GP를 각각 독립적으로 학습 후 smooth_max로 결합.
두 GP는 다른 Sobol set, 다른 온도, 다른 quadrant weight를 사용 ( §1.5 ).

| Metric | Cond | Vop | MC | 온도 | Decks |
|--------|:----:|:---:|:--:|:----:|:-----:|
| SNMR | 2,000 | 5 | 5K | 125°C | 10,000 |
| Vtrip | 2,000 | 5 | 5K | −40°C | 10,000 |
| **Total** | | | | | **20,000** |

---

## 4. 시간 절약 실행 전략

### 권장: Simultaneous Pilot + Early Reduced Full

```
Stage A (완료): 4D baseline, MC=2K, 125°C — 200 cond × 5 Vop = 1,000 decks ✅

Round 1 (동시 제출):
  ├─ Stage B: 4D baseline (신규 350 cond × 5 Vop = 1,750 decks, MC=5K, 125°C)
  │            + Stage A overlap 50 cond 재사용 → 학습용 400 cond
  ├─ Stage C: Vtrip @-40°C (400 cond × 5 Vop = 2,000 decks, MC=5K)
  │            (Stage A 조건과 동일, 온도만 변경 — 전체 신규)
  ├─ Stage D-pilot-SNMR: 9D Sobol (신규 420 cond × 5 Vop = 2,100 decks, MC=2K, 125°C)
  │            + A/B overlap 80 cond 재사용 → 학습용 500 cond
  │            (quadrant weight: Q2 45% — §1.5 참조)
  └─ Stage D-pilot-Vtrip: 9D Sobol (신규 420 cond × 5 Vop = 2,100 decks, MC=2K, -40°C)
             + A/B overlap 80 cond 재사용 → 학습용 500 cond
             (quadrant weight: Q4 45% — §1.5 참조)
  Total 신규 sim: 1,750 + 2,000 + 2,100 + 2,100 = 7,950 decks
  Total 학습 cond: Stage-A(200) + B(400) + C(400) + D-SNMR(500) + D-Vtrip(500)

Pilot 결과 분석 → Reduced model 결정:
  - dim 제거: 각 device의 lpu/lpg/lpd, mpu/mpg/mpd → ST < 0.01이면 생략

Round 2 (필요시):
  └─ Stage D-full: reduced model, 신규 ~1,800 cond × 5 Vop (MC=5K)
     + A/B/Dp overlap ~200 cond 재사용 → 학습용 2,000 cond
```

### Pilot + Full 분리 이유

| 전략 | 총 신규 sim | RTT | 설명 |
|------|-----------:|:---:|------|
| Pilot만 먼저 | 1,000(A) + 7,950(1R) = 8,950 | 1x | A 완료, B+C+Dp 동시. 빠름 |
| Full 동시 | 8,950 + 9,000(Df) = 17,950 | 1x | over-sim 위험 |
| **권장: Pilot → Reduced** | **8,950 + ~9,000** | **2x** | **최적. pilot으로 dim 줄이면 Df가 절반** |

pilot MC=2K는 full MC=5K보다 2.5배 빠르므로, pilot round가 크지 않음.
pilot 완료 후 불필요한 dim을 제거하면 full sim 수가 절반으로 줄어듦.

---

## 5. 종합 Job Manifest (최종) — Overlap 반영

> 신규 sim: 새로 submit할 deck 수.
> 학습 cond: 이전 stage 재사용 포함, GP 학습에 실제 사용되는 조건 수.

| # | Job | Dim | 학습 cond | 신규 sim (cond×Vop) | Decks | MC | Temp | 측정 | 비고 |
|---|-----|:---:|:---------:|:-------------------:|------:|:--:|:----:|------|------|
| **A** | 4D baseline SNMR | 4D | 200 | 200×5 | **1,000** | 2K | 125°C | SNMR | ✅ 완료 |
| **B** | 4D SNMR (ext) | 4D | 400 | 350×5 | **1,750** | 5K | 125°C | SNMR | A overlap ~50 재사용 |
| **C** | Vtrip @-40°C | 4D | 400 | 400×5 | **2,000** | 5K | −40°C | Vtrip | 전체 신규 |
| **Dp** | 9D pilot SNMR | 9D | 500 | 420×5 | **2,100** | 2K | 125°C | SNMR | A+B overlap ~80, Q2=45% weight (§1.5) |
| **Dp** | 9D pilot Vtrip | 9D | 500 | 420×5 | **2,100** | 2K | −40°C | Vtrip | A+B overlap ~80, Q4=45% weight (§1.5) |
| | *Subtotal R1* | | | | ***8,950*** | | | | |
| **Df** | Full reduced | 5~9D | 2,000 | 1,800×5 | **~9,000** | 5K | 각각 | SNMR/Vtrip | A+B+Dp overlap ~200 재사용 |
| | **Total 신규 sim** | | | | **~17,950** | | | | |
| | Total 학습 cond | | | | (200+400+400+500+500+2,000) = **4,000** | | | | |

**~17,950 decks** = realistic total (신규 sim 기준, Vop 5레벨).
At ~30 sec per deck (MC=2K) to ~120 sec per deck (MC=5K), this is
**~150~600 CPU-hours** depending on MC and farm parallelization.

---

## 6. Global Variation in Physics Layer

> 결정: σG를 GP 입력 차원에서 제거. 대신 physical layer에서
> **cn/pu amplitude scaling**으로 global variation을 처리.

### 논리

PDK의 PVTA corner(FSG, SFG, TT 등)는 이미 global variation을 포함.
예를 들어 FSG corner의 VT shift가 (cn=−40, pu=+40)이라면:
- global variation amplitude α = 1.0 (기준 FSG)
- α = 0.9 (10% 개선) → cn = −36, pu = +36
- α = 1.1 (10% 열화) → cn = −44, pu = +44

GP는 (cn, pu) 입력에 대해 Vmin을 예측하므로, global variation α에 대한
Vmin은 **GP(cn·α, pu·α, ...)** 로 직접 계산 가능 — 추가 sim 불필요.

### 수식

```
Vmin(α) = GP( cn_nominal × α,  pu_nominal × α,  sk,  lpu, lpg, lpd, mpu, mpg, mpd )

dVmin/dα = ∂GP/∂cn × cn_nominal + ∂GP/∂pu × pu_nominal
         (chain rule — GP 미분 가능하므로 closed form)
```

### Physical layer 구현

기존 `src/physics.py`의 `PhysicsConstrainedSurrogate`에 추가:

```python
class PhysicsConstrainedSurrogate:
    def __init__(self, gp_mu, gp_sigma):
        self.gp_mu = gp_mu    # 9D GP
        self.gp_sigma = gp_sigma

    def predict_with_global_scale(self, X, alpha=1.0):
        """X: (N, 9) = [cn, sk, pu, lpu, lpg, lpd, mpu, mpg, mpd]
           alpha: global variation scaling factor (1.0 = nominal corner)
        """
        X_scaled = X.copy()
        X_scaled[:, 0] *= alpha   # cn ← cn × α
        X_scaled[:, 2] *= alpha   # pu ← pu × α
        return self.gp_mu(X_scaled), self.gp_sigma(X_scaled)

    def dVmin_dalpha(self, X_nominal):
        """Gradient of Vmin w.r.t. global variation α at α=1."""
        # ∂GP/∂cn × cn_nominal + ∂GP/∂pu × pu_nominal
        ...
```

### 이점

| 항목 | σG를 GP 입력으로 할 때 | Physical layer에서 처리 |
|------|----------------------|----------------------|
| GP 차원 | 10D (cn,sk,pu,lpu,lpg,lpd,mpu,mpg,mpd,**σG**) | **9D** |
| Sobol pilot | 500 cond × 5 Vop (10D) | 500 cond × 5 Vop (9D) |
| Full run cond | 2,500 (10D) | **2,000 (9D)** |
| σG sweep 필요 | 전용 sweep sim 필요 | **0 sim — 미분으로 해결** |
| 물리 해석 | black-box | **cn/pu scaling = 직관적** |
| 논문 설명 | "10D GP learned σG" | "global = cn/pu amplitude → physics layer에서 미분" |

### Corner interpolation 예시

```
TT:          cn= 0, pu= 0  → GP( 0,  0, ...)
FSG:         cn=-40, pu=+40 → GP(-40, +40, ...)    (α=1.0)
FSG × 0.9:  cn=-36, pu=+36 → GP(-36, +36, ...)    (α=0.9)
FSG × 1.1:  cn=-44, pu=+44 → GP(-44, +44, ...)    (α=1.1)
```

GP가 연속 함수이므로 α에 대한 Vmin 변화는 자동으로 부드러움.
추가 sim, 추가 GP 차원, 추가 학습 불필요.
