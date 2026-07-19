# Revised Simulation Plan — PG/PD Skew 확장, Assist 제외

> 작성일: 2026-07-09
> 선행: `hspice_sim_scope.md`, `phase2_to_paper_plan.md`, `execution_guide.md`
> 변경:
>   - ~~WLUD(Vwl) 4D~~ → **PG/PD skew**로 대체 (assist 불필요 cell)
>   - common_N 유지, 거기에 skew 추가
>   - Stage D (논문 확장)의 500-조건 파일럿 구체적 명세
> 목적: sim 대기시간 + 손전사 병목 고려, **미리 큐에 올릴 job을 stage별로 구체 지정**

---

## 0. Parameterization 변경

### 기존 (hspice_sim_scope)
```
VTMSKEW_PG1/2 = common_N_shift   (PG = PD, 동일)
VTMSKEW_PD1/2 = common_N_shift
VTMSKEW_PU1/2 = PU_shift
```

### 변경
```
common_N = baseline NMOS shift (mV),  range [-60, +60]
skew_pgpd = PG − PD differential (mV), range [-20, +20]
   → PG_shift = common_N + skew_pgpd
   → PD_shift = common_N − skew_pgpd
PU_shift (mV), unchanged, range [-60, +60]
Vop (V), unchanged, 6 levels {0.4, 0.5, ..., 0.9}
```

skew=0일 때 기존 common_N(=PG=PD)와 동일. skew≠0이면 PG와 PD가
서로 다른 Vth shift를 가짐 (예: skew=+20 → PG가 PD보다 40mV 느림).

### 스키마 변화 — GP 입력 차원

| 차원 | 기호 | 범위 | Stage | 비고 |
|------|------|------|-------|------|
| common_N shift | cn | −60 ~ +60 mV | A~D | PG+PD baseline |
| PG-PD skew | sk | −20 ~ +20 mV | **B~D** (신규) | PG=cn+sk, PD=cn−sk |
| PU shift | pu | −60 ~ +60 mV | A~D | PMOS Vth shift |
| Vop | Vop | 0.4, 0.5, …, 0.9 V (6) | A~D | grid |
| PU local σ | lpu | 0.5 ~ 2.0 (×nom) | **D** | VTSLSKEW_PU |
| PG local σ | lpg | 0.5 ~ 2.0 (×nom) | **D** | VTSLSKEW_PG |
| PD local σ | lpd | 0.5 ~ 2.0 (×nom) | **D** | VTSLSKEW_PD |
| PU mobility | mpu | 0.7 ~ 1.3 (×nom) | **D** | MOMSKEW_PU |
| PG mobility | mpg | 0.7 ~ 1.3 (×nom) | **D** | MOMSKEW_PG |
| PD mobility | mpd | 0.7 ~ 1.3 (×nom) | **D** | MOMSKEW_PD |

> ~~σG~~: PVTA .lib에 이미 포함. GP 입력에서 제거하고 physics layer에서
> **cn/pu amplitude scaling**(α)으로 global variation 처리. 자세한 내용은
> `docs/plans/deck_scenarios.md §6` 참조.

**Stage 구분**: A(3D) → B(4D+skew) → C(+Vtrip) → D(full Sobol)

---

## 1. Stage A — 3D Baseline (기존과 동일)

### 조건
| 항목 | 값 |
|------|-----|
| 차원 | cn, pu, Vop (3D) — PG=PD=cn, skew=0 |
| 조건 수 | 200쌍 (stratified Sobol: FSG 35%, SFG 25%, 나머지 40%) |
| Vop | 6레벨 (0.4~0.9) |
| 온도 | 125°C (단일) |
| MC | 2,000 |
| Sim 수 | 200 × 6 = **1,200 decks** |
| 출력 | 조건당 SNMR (mu, sigma) |

### 실행
```bash
cd python

# deck 생성 (stage 1 = 3D)
python scripts/gen_hspice.py --stage 1 --n_cond 200 --out_dir ../decks/stageA

# HSPICE 실행 (farm)
#   hspice64 -i decks/stageA/cond_000001.sp -o decks/stageA/cond_000001
#   ...
# 결과: 각 cond_xxxxxx 디렉토리에 .mt0 파일

# CSV 전사 (손으로 옮겨적거나, .mt0 파서 사용)
#   CSV 형식: common_N_shift, PU_shift, Vop, mu_SNMR, sigma_SNMR, n_mc

# → 학습 pipeline
parse_csv.py -> dataset_stageA.npz -> scripts/train.py
```

### 미리 큐에 올리기
✅ **지금 바로 가능.** 기존 gen_hspice.py가 --stage 1 지원.
skew=0이므로 PG=PD=common_N, 기존과 완전 동일.

---

## 2. Stage B — 4D with PG/PD Skew (신규)

### 조건
| 항목 | 값 |
|------|-----|
| 차원 | **cn, sk, pu**, Vop (4D) |
| 공통 | PG=cn+sk, PD=cn−sk |
| 조건 수 | **400쌍** Sobol (4D이므로 200→400으로 증가 권장) |
| Vop | 6레벨 |
| 온도 | 125°C |
| MC | 2,000 |
| Sim 수 | 400 × 6 = **2,400 decks** |

### Sampling 전략 (skew 포함)
Sobol sequence over 3D (cn, sk, pu), independent uniform:

```python
from scipy.stats.qmc import Sobol
sobol = Sobol(d=3, scramble=True)
samples = sobol.random(n=400)    # (400, 3) in [0,1]^3
cn = -60 + 120 * samples[:, 0]   # [-60, +60]
sk = -20 + 40 * samples[:, 1]   # [-20, +20]
pu = -60 + 120 * samples[:, 2]   # [-60, +60]
```

skew=0 근방에 더 밀도를 주고 싶으면 truncated normal이나
beta(2,2) 변환 가능하나, 첫 배치는 uniform Sobol로 충분.

### 주의: Template 렌더링 변경
`_render_vth_skew()`가 PG와 PD에 **다른 값**을 넣도록 수정 필요:

```python
# 현재 (render_deck 인자)
def render_deck(..., common_n_shift, ...):
    # PG=PD=common_n_shift

# 변경
def render_deck(..., common_n_shift, skew_pgpd=None, ...):
    pg_shift = common_n_shift + skew_pgpd/2  if skew_pgpd else common_n_shift
    pd_shift = common_n_shift - skew_pgpd/2  if skew_pgpd else common_n_shift
    # _render_vth_skew에 pg/pd 별도 전달
```

**또는**: 별도의 `--pg_shift` / `--pd_shift` 인자를 gen_hspice.py에 추가.
단, 조건 파일(csv)에 PG_shift, PD_shift 컬럼을 명시하는 방식이 더 안전.

### 미리 큐에 올리기
⚠ **약간의 코드 수정 필요** (render_deck에 skew 인자 추가).
수정 후 Stage A와 함께 제출 가능.

---

## 3. Stage C — +Vtrip Write Margin (read-write 통합)

### 조건
| 항목 | 값 |
|------|-----|
| 차원 | **cn, sk, pu**, Vop (4D, Stage B와 동일 조건) |
| 측정 | SNMR(read) @125°C (Stage B 재사용) + **Vtrip(write) @−40°C (신규)** |
| 조건 수 | 400쌍 (B와 동일) |
| Vop | 6레벨 |
| MC | 2,000 |
| Sim 수 | 400 × 6 = **2,400 decks** (Vtrip @−40°C 신규; SNMR은 Stage B 결과 재사용) |

SNMR과 Vtrip은 최적 온도가 다르므로 별도 deck 생성 필요.
Stage B deck의 SNMR(125°C) 데이터를 재사용하고, 동일 조건으로 Vtrip(−40°C) deck을 추가 생성.

### Write margin pilot (선택)
20 조건 × 6 Vop × **1온도(−40°C)** = **120 decks**로
cold write margin 사전 검증 권장.

### 미리 큐에 올리기
❌ **Vtrip .MEASURE 추가 + deck template 수정 필요.**
deck template에 Vtrip MEASURE 라인이 없는 경우 먼저 추가.
pilot 120 decks만 먼저 테스트 → full 2,400은 결과 보고 결정.

---

## 4. Stage D — Sobol Sensitivity Pilot + Full (논문 확장)

### 4.1 Stage D 개요

Stage D = 9개 GP 입력 차원(cn, sk, pu, **lpu, lpg, lpd, mpu, mpg, mpd**)에 대해
**어느 device**의 local mismatch와 mobility가 Vmin 분산을 지배하는지
Saltelli Sobol sensitivity 분석으로 파악하는 단계.

> 제외: σG(global) — PVTA .lib에 포함. Temp — SNMR 125°C 고정, Vtrip −40°C 고정.
> global variation은 physics layer에서 cn/pu amplitude scaling(α)으로 처리
> (자세한 내용은 `docs/plans/deck_scenarios.md §6` 참조)

**Device 影響度 (경험적 순서):**
| Metric | 1st | 2nd | 3rd |
|--------|-----|-----|-----|
| SNMR (read) | **PG** | **PD** | PU |
| Vtrip (write) | **PG** | **PU** | PD |

PG가 read/write 모두 지배적. Pilot으로 정량적 기여도 측정.

### 4.2 Pilot (500 조건) — 구체적 명세

| 항목 | 값 |
|------|-----|
| 차원 | **cn, sk, pu, lpu, lpg, lpd, mpu, mpg, mpd** (9D) |
| Vop | 6레벨 grid (고정) |
| 온도 | 125°C (SNMR pilot); −40°C (Vtrip pilot, 별도) |
| 조건 | 500 Sobol points over **9D** |
| **Deck 수** | 500 × 6 = **3,000 decks** (SNMR) + 3,000 (Vtrip 선택) |
| MC | **2,000** (파일럿이므로 고MC 불필요) |

#### Sampling
```python
from scipy.stats.qmc import Sobol
sobol = Sobol(d=9, scramble=True)
s = sobol.random(500)            # (500, 9) in [0,1]^9

cn  = -60  + 120 * s[:, 0]      # [-60, +60]
sk  = -20  +  40 * s[:, 1]      # [-20, +20]
pu  = -60  + 120 * s[:, 2]      # [-60, +60]
lpu = 0.5  + 1.5 * s[:, 3]     # [0.5, 2.0]  VTSLSKEW_PU
lpg = 0.5  + 1.5 * s[:, 4]     # [0.5, 2.0]  VTSLSKEW_PG
lpd = 0.5  + 1.5 * s[:, 5]     # [0.5, 2.0]  VTSLSKEW_PD
mpu = 0.7  + 0.6 * s[:, 6]     # [0.7, 1.3]  MOMSKEW_PU
mpg = 0.7  + 0.6 * s[:, 7]     # [0.7, 1.3]  MOMSKEW_PG
mpd = 0.7  + 0.6 * s[:, 8]     # [0.7, 1.3]  MOMSKEW_PD
```

### 4.3 Sensitivity 분석

```python
from SALib.analyze import sobol as sobol_analyze

problem = {
    'num_vars': 9,
    'names': ['cn','sk','pu','lpu','lpg','lpd','mpu','mpg','mpd'],
    'bounds': [[-60,60],[-20,20],[-60,60],
               [0.5,2.0],[0.5,2.0],[0.5,2.0],
               [0.7,1.3],[0.7,1.3],[0.7,1.3]]
}
Si = sobol_analyze.analyze(problem, Y_vmin, calc_second_order=False)
# Si['S1'] = 1차 민감도, Si['ST'] = 전효과
```

### 4.4 Pilot → Full Run 시나리오

| 시나리오 | 조건 | 차원 | Cond × Vop | Decks | MC |
|----------|------|:----:|:----------:|------:|:--:|
| R1 (top-5~7) | lpu/mpu 등 기여도 < 1% 제거 | 5~7D | 1,000×6 | **6,000** | 5K |
| R2 (full 9D) | 모든 dim 유지 | 9D | 2,000×6 | **12,000** | 5K |
| W1 (Vtrip reduced) | snmr pilot 결과 기반으로 유사 적용 | 5~7D | 1,000×6 | **6,000** | 5K |
| W2 (Vtrip full) | 모든 dim 유지 | 9D | 2,000×6 | **12,000** | 5K |

**Decision rule**: ST < 0.01인 device의 lpu/lpg/lpd 또는 mpu/mpg/mpd → nominal 고정 후 제거.

---

## 5. 종합: 미리 큐에 올릴 Job Manifest

### 지금 올릴 것

| # | Job | 조건 | Sim 수 | MC | Deck 생성 | 선행조건 |
|---|-----|------|-------:|----|----------|---------|
| **A** | 3D baseline (cn, pu, Vop) | 200 × 6 | **1,200** | 2,000 | ✅ 지금 가능 | 없음 |
| **B** | 4D+skew (cn, sk, pu, Vop) | 400 × 6 | **2,400** | 2,000 | 🔧 `render_deck` 수정 필요 | A와 병렬 가능 |
| **Bv** | 검증 기준점 (corner 4 + hold-out 20) | 24 × 6 | **144** | 10,000 | ✅ (validation 모드) | A/B와 병렬 |
| **Cp** | Vtrip pilot (write 검증 @−40°C) | 20 × 6 | **120** | 2,000 | 🔧 Vtrip template 필요 | B와 병렬 가능 |

**총계: ~3,864 decks** (3,900 안팎)

### 나중에 결정

| # | Job | Sim 수 | Deck 생성 | 결정 시점 |
|---|-----|-------:|----------|----------|
| **C** | Vtrip full (Stage B 조건 + Vtrip) | 2,400 | 🔧 Vtrip | Cp pilot → hot-read/cold-write 지배 확인 후 |
| **Dp** | Sobol sensitivity pilot (9D) | 3,000 | 🔧 gen_hspice 확장 | A+B 결과로 GP 동작 확인 후 |
| **D** | Full run (pilot 결과에 따라) | 6K~12K | 🔧 전면 확장 | Dp 완료 후 |

---

## 6. 코드 변경 요약

### 필수 (Stage B 이전)

| 파일 | 변경 |
|------|------|
| `src/hspice_io.py:_render_vth_skew()` | PG/PD 별도 skew 인자 지원: `render_deck(..., pg_shift, pd_shift)` |
| `src/hspice_io.py:render_deck()` | skew_pgpd 인자 → PG, PD 각각 계산 |
| `scripts/gen_hspice.py` | CLI `--skew` 인자 또는 조건 csv에서 skew 읽기 |

### 선택 (Stage C)

| 파일 | 변경 |
|------|------|
| `templates/sram_cell_pvta.sp` | Vtrip .MEASURE 추가 (write margin) |
| `src/hspice_io.py` | .mt0 파서에 Vtrip 통계 추가 |

### Stage D — 9D template 확장

| 파일 | 변경 |
|------|------|
| `templates/sram_cell_pvta.sp` | VTSL(PU/PG/PD) + MOM(PU/PG/PD) `.param` 6개 추가 (현재는 모두 '(1)+(0)' 고정) |
| `scripts/gen_hspice.py` | `--stage 3` (9D Sobol) 모드 추가 |
| `src/utils.py` | Sobol 9D sampling 함수 |
| `src/models.py` | 9D grouped kernel (device별 ARD) |
| 분석 | `SALib` sensitivity 분석 스크립트 (신규) |
| `src/physics.py` | Global variation scaling (α → cn,pu amplitude) 추가 |

---

## 7. Stage D Pilot FAQ (모호한 점 정리)

### Q1: "500 조건"이 뭘 의미하나?
500 = 9차원 Sobol point 개수. 각 point는 (cn, sk, pu,
lpu, lpg, lpd, mpu, mpg, mpd)의 조합 1개.
각 point를 6개 Vop에서 sim = 500×6 = 3,000 decks.
σG(global)은 PVTA에 포함되어 있어 제외.
Temp는 SNMR 125°C 고정, Vtrip −40°C 고정.

### Q2: 그래서 뭘 측정하나?
각 sim에서 SNMR (mu, sigma) → Vmin 계산.
500개의 Vmin 값으로 Saltelli Sobol sensitivity 분석.
출력: **device별** local(σL)과 mobility의 "Vmin 분산 기여도 (%)".

### Q3: device별로 다 independent여야 하나?
네. SRAM에서 PU/PG/PD의 local mismatch와 mobility는
물리적으로 독립적이므로 각각 별도 차원으로 설정.
다만 pilot 결과에서 ST < 0.01인 device dim은 제거 가능.

### Q4: 파일럿 결과로 무엇을 결정하나?
PG의 local(σL)과 mobility 기여도가 가장 높을 것으로 예상.
- `lpg`, `mpg` 기여도 60%+ → PG variation = Vmin 지배 요인
- `lpu`, `mpu` 기여도 < 1% → PU device dim 제거, 7D로 축소
- `lpd`, `mpd` 기여도 < 1% → PD device dim 제거
- sk 기여도 < 1% → skew 차원 제거

Device 影響度 사전 정보 (참고):
| Metric | 1st | 2nd | 3rd |
|--------|-----|-----|-----|
| SNMR | PG | PD | PU |
| Vtrip | PG | PU | PD |

### Q5: full run은 얼마나 큰가?
보수적(full 9D): 2,000 cond × 6 Vop = **12,000 decks** (MC=5K)
축소 성공(5~7D): 1,000 cond × 6 Vop = **6,000 decks** (MC=5K)

---

## 8. 권고: 실행 순서

```
Step 1 — Template 준비 (선행 필수)
  ├─ sram_cell_pvta.sp에 .param VTSLSKEW_* 6개, MOMSKEW_* 6개 추가
  ├─ Vtrip .MEASURE 추가 (write margin)
  └─ Vtrip template QA: TT×6Vop @-40°C → 6 decks

Step 2 — Batch 1 제출 (동시)
  ├─ Stage A: 3D baseline (1,200 decks, MC=5K, 125°C)
  ├─ Stage B: 4D+skew (2,400 decks, MC=5K, 125°C)
  ├─ Stage C: Vtrip @-40°C (2,400 decks, MC=5K)
  └─ Stage Dp: 9D Sobol pilot SNMR (3,000 decks, MC=2K, 125°C)
  Total: 9,000 decks

Step 3 — Batch 1 대기 중 병렬 작업
  ├─ SALib sensitivity 분석 스크립트 작성
  ├─ 9D sampling + deck 생성 스크립트 준비 (Stage D full)
  └─ Physics layer에 global variation scaling 구현

Step 4 — Pilot 결과 → Full run 결정
  ├─ 각 device dim의 ST 기여도 확인
  ├─ 불필요한 dim 제거한 reduced model 설계
  └─ Batch 2 제출: 6K~12K decks (MC=5K)

Step 5 — 모든 data 도착
  ├─ CSV → dataset.npz 변환
  ├─ GP 학습 (3D baseline, 4D+skew, 9D/reduced)
  ├─ GP 사후 Sobol sensitivity (차원 중요도)
  └─ Vtrip write margin contour
```

---

## 9. 부록: skew 도입 시 template 렌더링 상세

### Template 현재 구조
```
.param VTMSKEW_PG1 = '({cn}) + (0)'
.param VTMSKEW_PD1 = '({cn}) + (0)'    ← PG와 PD가 같은 값
.param VTMSKEW_PG2 = '({cn}) + (0)'
.param VTMSKEW_PD2 = '({cn}) + (0)' 
```

### skew 도입 후
```
.param VTMSKEW_PG1 = '({cn} + {skew}/2) + (0)'   ← PG = cn + sk/2
.param VTMSKEW_PD1 = '({cn} - {skew}/2) + (0)'   ← PD = cn − sk/2
.param VTMSKEW_PG2 = '({cn} + {skew}/2) + (0)'
.param VTMSKEW_PD2 = '({cn} - {skew}/2) + (0)'
```

skew=0 → PG=PD=cn (기존과 완전 동일, 하위호환).
`render_deck(common_n_shift, pu_shift, vop, skew_pgpd=0.0)` 기본값=0.
