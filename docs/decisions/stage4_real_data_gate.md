# Stage 4 — 첫 실데이터 Gate 통과 (2026-07-09)

> **판정: GO** (3/3 PASS). Toy(analytic)에서 검증한 GP + physics-layer 파이프라인이
> 손으로 전사한 실제 HSPICE 결과에서도 그대로 작동함을 확인.
> 스크립트: `scripts/stage4_real_data.py`. 산출물: `results/stage4_real/`.

---

## 1. 데이터

`data/hspice_real.xlsx` — 사내 PrimeSim MC 결과를 손으로 전사(반출 제약으로
자동 파일 반출 불가). 컬럼: `snmr_avg, snmr_med, snmr_std, vop, vtmskew_n,
vtmskew_pu`.

- **201개 (common_N, PU) 조건 × 6 Vop = 1206 samples** — 계획한 Stage A
  규모(200조건)와 거의 정확히 일치.
- Vop: 0.4~0.9V 6레벨, 계획대로.
- 샘플링 분포: FSG 68 / SFG 47 / FFG 43 / SSG 35 / on-axis 8 — FSG 집중
  전략이 실제로 반영됨 (68/201=34%, 계획한 35% weighting과 일치).
- 단위: mu/sigma는 mV로 기록됨 (예: snmr_avg=142.12 → 0.14212V), cn/pu는
  이미 mV. `parse_manual_xlsx(mu_sigma_unit="mV")`가 변환 처리.

### 1.1 전사 오류 발견 → 사용자가 실시간으로 자체 수정

작업 중 두 종류의 명백한 전사 오타를 발견:
1. **`snmr_med` 자릿수 밀림** (5건): median이 avg의 정확히 10배/100배
   (예: avg=111.95인데 median=1112.79). 소수점 위치 오류로 추정.
2. **`snmr_avg` 단일 이상치** (1건, 최초 발견 시 row 897):
   `avg=9.83`인데 같은 (cn,pu) 조건의 이웃 Vop 값(0.5V→65.89, 0.7V→111.65)
   으로 보간하면 ~88.8이 예상되고, 실제로 그 행의 `median=92.53`이 그
   범위에 있어 **원래 값은 98.3이었을 것**으로 강하게 추정.

**두 문제 모두 median은 학습에 쓰지 않으므로(y=[mu,sigma]만 사용) 학습
결과에 직접 영향은 없었으나**, avg 이상치 1건은 실제 mu 값이라 영향권.
파일을 재확인한 시점(작업 중간)에 **사용자가 이미 두 문제를 전부 직접
수정**한 것을 확인 — 재실행한 QC(`_median_digit_shift_qc`,
`_vop_interpolation_outlier_qc`)에서 flag 0건.

**교훈**: 전사 데이터는 자동 보정하지 않고 항상 플래그만 하는 원칙
(`hspice_io.py` 설계 원칙)이 유효했음 — 실제로 원본 확인 권한이 있는
사용자가 직접 고치는 것이 안전했다.

## 2. QC 인프라: xlsx 로더 신설

`src/hspice_io.py`에 `parse_manual_xlsx()` 추가 (기존 `parse_manual_csv`와
`_parse_manual_df` 공통 바디 공유하도록 리팩터링):
- 컬럼 별칭 확장: `vtmskew_n/pu`, `snmr_avg/std/med` 등 사내 명명 규칙 추가.
- `mu_sigma_unit="mV"|"V"` — mV 시트를 자동으로 V로 변환 (cn/pu/Vop는
  변환 안 함, 이미 project 단위).
- `_median_digit_shift_qc`, `_vop_interpolation_outlier_qc` — 두 가지
  전사 오류 패턴을 자동 감지, **자동 수정은 하지 않고 플래그만** 출력.

## 3. 결과

### 3.1 Hold-out 정확도 (15% stratified split)

| 지표 | 값 |
|------|-----|
| mu RMSE | 0.00112 V |
| mu R² | **0.9992** |
| sigma RMSE | 0.00022 V |
| sigma R² | 0.5138 |

sigma R²가 낮아 보이지만 **RMSE는 0.22mV로 매우 작음** — sigma_std 자체가
12.6~14.4mV 좁은 범위에 몰려 있어(변동폭이 원래 작음) R² = 1 −
SS_res/SS_tot 공식상 분모(SS_tot)가 작아 자연스럽게 낮게 나오는 통계
현상. 문제가 아니라 **실데이터 sigma의 실제 특성**(toy 모델보다 Vop
의존성이 약함, session_20260708 논의와 일치하는 방향).

### 3.2 물리 정합성 체크 (Go/No-Go 기준, 전부 PASS)

| 체크 | 결과 |
|------|------|
| Gradient 방향 | dVmin/dcn=−0.00141 (<0 ✓), dVmin/dpu=+0.00134 (>0 ✓) |
| FSG worst corner | **PASS** — FSG(nearest, dist 11.4mV) Vmin=0.675V, 4개 corner 중 최고 |
| mu R² ≥ 0.95 | PASS (0.9992) |

**Corner 상세** (실측 조건 중 최근접점 사용, 정확한 corner는 미샘플):

| Corner | 최근접 조건 | 거리 | Vmin | Z(Vop=0.4→0.9) |
|--------|------------|------|------|------------------|
| FSG | (−51,+53)mV | 11.4mV | **0.675V (worst)** | 1.47→7.63 |
| SFG | (+46,−56)mV | 14.6mV | censored (<0.4V, 최선) | 8.15→16.38 |
| FFG | (−50,−50)mV | 14.1mV | 0.456V | 4.90→10.01 |
| SSG | (+56,+59)mV | 4.1mV | 0.442V | 4.94→14.36 |

FSG=SNMR worst, SFG=SNMR 최선(반대로 Vtrip worst일 것으로 예상, 미검증)
— 계획 문서(`sram_vmin_inverse_estimation_plan.md` §14.1)의 예측과
**정확히 일치**.

### 3.3 PG≫PU lengthscale 계층 — 실데이터 최초 검증

```
ell_cn = 7.467, ell_pu = 8.086   (표준화 입력 스케일)
ell_pu / ell_cn = 1.083
```

**방향은 물리적으로 옳음** (ℓ_cn < ℓ_pu → PG가 더 민감 → GP가 그 방향으로
더 빨리 변화를 학습). 다만 비율이 1.08로 약함 — `physics_ablation.md`가
기대한 "뚜렷한 계층"(비율 1.5~3.0)에는 못 미침. 세션 20260706의 asymmetric
합성실험(PG 2×/3× 민감도 주입 시 비율 1.16~1.31 관찰)과 비교하면, 실데이터의
실제 PG:PU 민감도 비는 그 실험의 "PG 2배" 케이스보다 약간 낮은 수준으로
보임. **Go 게이트로 쓰지 않고 참고 지표로만 사용** (원 설계대로).

## 4. Go/No-Go 판정

| 기준 | 결과 |
|------|------|
| mu R² ≥ 0.95 | ✅ PASS (0.9992) |
| Gradient 방향 물리적 | ✅ PASS |
| FSG worst corner | ✅ PASS |

**>>> GO <<<** — Stage 5(4D+Vwl assist) 진행 가능. 상세 기준은
`docs/plans/hspice_sim_scope.md` Stage A / `phase2_to_paper_plan.md` §3.6.

## 5. 남은 이슈 / 다음 스�텝

1. **정확한 4-corner 미샘플** — 최근접점(4~15mV 오차)으로 대체 판정. 정밀
   corner 검증(계획 §3.6 "corner-ring" 요구사항)을 위해서는 정확히
   (±60,±60) 근방 소수 조건을 추가 시뮬해야 함.
2. **Vmin=0.6V 표준 타깃과의 정합** — 이번 스크립트는 임시로 domain
   median(≈0.45V)을 contour level로 사용. Z_FIXED(6.0) 또는
   `derive_z_target()`(6.64) 중 어느 것을 실데이터 표준으로 쓸지 결정
   필요 — 결정 후 contour를 표준 target으로 재추출.
3. **n_mc 정보 없음** — 이번 xlsx에는 조건당 MC 샘플 수가 없어 noise-aware
   GP(SEM 기반)를 못 씀. 향후 손 전사 시 `n_mc` 컬럼 추가를 권장(표준
   템플릿에는 이미 있음, `manual_entry_standard.csv` 참고).
4. **σL/σG/mobility 없음** — nominal 고정(계획대로, Stage A 범위).
   Vtrip/write margin도 이번 데이터엔 없음(계획대로 Stage C 이후).
5. **Lengthscale 비율 1.08** — 약한 신호. σL/σG 확장(Phase 4) 또는 추가
   FSG-heavy 샘플링으로 재검증 여지.

## 6. 세션 코드 변경 요약

- `src/hspice_io.py`: `parse_manual_xlsx`, `_parse_manual_df`(공통화),
  `_median_digit_shift_qc`, `_vop_interpolation_outlier_qc`,
  `_manual_data_qc`. 별칭 확장(`vtmskew_n/pu`, `snmr_avg/std/med`).
- `requirements.txt`: `openpyxl>=3.1` 추가.
- `scripts/stage4_real_data.py` 신설 — 실데이터 전용 Gate 스크립트
  (ground truth 없는 환경에 맞춘 Go/No-Go: hold-out R², gradient 방향,
  corner 상대비교, lengthscale 참고지표).
