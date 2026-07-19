# 개정 계획 리뷰 — deck_scenarios + revised_sim_plan (2026-07-09)

> 대상: `docs/plans/deck_scenarios.md`, `docs/plans/revised_sim_plan_20260709.md`.
> 목적: 두 개정 계획의 논리 검증 + 위험/개선점 도출. 실데이터로 검증 가능한
> 주장은 직접 확인.

---

## 1. 개정의 핵심 변경 (요약)

| 항목 | 기존 (hspice_sim_scope) | 개정 | 판정 |
|------|------------------------|------|------|
| Assist 차원 | WLUD(Vwl) 4D | **PG/PD skew**로 대체 | ✅ 타당 (아래 §2.1) |
| Global σ | GP 입력 차원 | **physics layer cn/pu scaling** | ✅ 우수 (§2.2) |
| Vop 레벨 | 6 (0.4~0.9) | **5 (0.4~0.8)** | ✅ 실데이터 확증 (§2.3) |
| Local/mobility | Phase 4 언급만 | **device별 6차원 명세** (lpu/lpg/lpd/mpu/mpg/mpd) | ✅ 구체화 |
| Vmin 통합 | max(read,write) | **smooth_max** (softplus) | ✅ (단 §3.1 주의) |
| Overlap | 없음 | **stage 간 재사용** (~10% 절감) | ✅ (단 §3.2 주의) |

전반적으로 **매우 잘 발전된 계획**. 특히 global-scaling과 Vop 축소는 sim
비용을 크게 줄이면서 물리적으로 정당하다. 아래는 검증 결과 + 위험점.

## 2. 검증된 주장 (실데이터/수치로 확인)

### 2.1 WLUD → PG/PD skew 대체 — 타당
현 셀은 assist 불필요(WLUD 미사용)이므로 4번째 차원을 skew로 돌린 것은
합리적. skew=0에서 기존 common_N과 완전 하위호환(PG=PD=cn). 다만 **skew는
Stage 4 inverse assist 데모(§4.1 gradient inversion)의 "assist 축"을
대체**하므로, 논문의 inverse 시나리오를 "required WLUD" → "허용 가능한
PG-PD skew tolerance"로 바꿔야 함. 방법론은 동일(미분 가능 inversion),
해석만 변경. **이 변경을 phase2_to_paper_plan §4.1에 반영 필요.**

### 2.2 Global σ = cn/pu amplitude scaling — 우수하고 물리적으로 정당
`Vmin(α) = GP(cn·α, pu·α, ...)`. 검증: α가 **TT(원점) 기준으로 cn,pu를
스케일**하므로, "corner VT shift = k·σ_global"(Pelgrom형 선형)이 성립하면
정확하다 — 이는 표준 가정. 이점:
- GP 차원 10D→9D, full run 2,500→2,000 cond.
- σG sweep sim 0개 (미분으로 해결).
- `dVmin/dα = ∂GP/∂cn·cn_nom + ∂GP/∂pu·pu_nom` — GP 미분가능하므로 closed form.

**단 한계 (문서에 명시 권장)**: 이 스케일링은 **global variation이 cn/pu와
같은 방향(VT shift)으로만 작용**한다고 가정. mobility/local σ의 global
성분은 못 잡음. 하지만 PVTA corner가 이미 그것들을 포함하므로 실용상 OK.
논문에서는 "global VT variation을 physics layer에서 처리"로 정확히 한정.

### 2.3 Vop 0.9 제거 — 실데이터로 확증 (오히려 더 줄일 수 있음)
`hspice_real.xlsx` 201조건으로 Vmin crossing 구간 직접 집계:

| Z_target | 0.4-0.5 | 0.5-0.6 | 0.6-0.7 | 0.7-0.8 | 0.8-0.9 |
|:--------:|:-------:|:-------:|:-------:|:-------:|:-------:|
| 4 | 49 | 10 | 0 | 0 | **0** |
| 5 | 92 | 22 | 6 | 0 | **0** |
| 6 | 112 | 37 | 16 | 1 | **0** |

- **[0.8,0.9] crossing = 0** (전 Z_target) → Vop 0.9 제거 정당 (계획 주장 확증).
- **추가 발견**: [0.7,0.8]도 최대 1개(Z=6)뿐. **Vop 0.4~0.7 4레벨로 더 축소
  가능** (Z≤5 기준 crossing 100%가 0.4~0.7 안). deck 추가 20% 절감 여지.
  → **권고**: Z_target 확정(§3.3) 후 Vop 레벨 재결정. Z=5면 4레벨(0.4~0.7)로
  충분, Z=6이면 5레벨(0.4~0.8) 유지.

## 3. 위험/개선점 (착수 전 결정 필요)

### 3.1 smooth_max α=0.01V — 편향 6.9mV, 계획값 과대 (수치 검증 완료)
수식 `α·log(1+exp((V_S−V_T)/α))+V_T`에서 α는 **볼트 단위**. 교차점(V_S=V_T)
편향 = α·ln2. 직접 계산:

| α (V) | 교차점 편향 | gap=20mV 편향 | gap=50mV |
|:-----:|:-----------:|:-------------:|:--------:|
| **0.01** (계획값) | **6.93mV** | 1.27mV | 0.07mV |
| 0.002 | 1.39mV | 0.05mV | ~0 |
| 0.001 | 0.69mV | ~0 | ~0 |

- **계획의 α=0.01V는 교차점에서 6.9mV 편향** — 목표 정확도(few-mV) 대비 큼.
  Q1/Q3 crossover 영역(두 metric이 가까운 곳)에서 Vmin을 systematic하게
  높게 만듦.
- **권고**: (i) 평가는 exact max, (ii) gradient inversion에서만 smooth_max
  쓰되 **α ≤ 0.002V** (편향 <1.4mV). §1.5 주장대로 FSG/SFG worst corner는
  두 값이 명확히 갈려(gap≫20mV) 편향 <0.1mV로 무관하지만, **Q1/Q3
  crossover와 최종 Vmin 결정 영역에서는 α=0.01이 위험** — 계획서 §1.5의
  "α=0.01로 설정" 문장을 α≤0.002로 수정 권장.

### 3.2 Overlap 재사용 시 MC 불일치 — noise-aware GP 필수
Stage A(MC=2K) 데이터를 Stage B/D(MC=5K)와 합칠 때 sigma_SNMR의 noise
level이 다름. 계획 §0.5도 인지하고 있음(옵션 a/b/c 제시). **명확한 권고**:
- 옵션 (a) heteroscedastic likelihood 채택 = 이미 구현된 **noise-aware GP**
  (`surrogate.fit(y_noise=)`)를 그대로 사용. 조건당 n_mc를 기록하면 SEM
  자동 유도 → MC 불일치가 원리적으로 처리됨.
- **필수 조건**: Stage A 재전사 시 **n_mc 컬럼 추가** (현 xlsx엔 없음).
  안 하면 MC 불일치를 GP가 모른 채 합쳐 sigma 예측이 왜곡.

### 3.3 Z_target — **확정됨 (2026-07-09, 사용자 결정)**
**Z_target = 6.50** = `derive_z_target(mb=256, y_target=0.99, model="poisson")`
= **256 Mb 어레이, Poisson yield 99%**. 사내 관행(128/256Mb Poisson 99%)
기준. `Z_FIXED`를 6.0 → 6.50으로 교체 (`src/utils.py`), 전 테스트 통과.

- Poisson = Binomial (이 스케일에서 4자리 일치) → 코드 공식 무변경, `model`
  인자만 추가.
- **Vop 레벨 확정**: Z=6.5에서 실데이터 crossing이 0.4~0.8 안에서 100%
  종료([0.8,0.9]=0개, [0.7,0.8]=6개 존재). → **Vop 5레벨(0.4~0.8)이
  필요·충분**. 계획서의 5레벨 결정이 Z=6.5에 정확히 부합. (4레벨 0.4~0.7은
  0.7~0.8 crossing 6조건을 놓치므로 불가.)
- **절대 Vmin 영향**: Z 6.0→6.5로 median Vmin +~25mV 상향. contour 모양/GP
  품질지표(RMSE/R²)는 불변 (mu/sigma 기반이라 Z 무관).
- 128Mb(Z=6.40)와 256Mb(Z=6.50)는 `derive_z_target(mb=)`로 언제든 병기
  가능 — 지금은 256 단일 표준.

### 3.4 skew 범위 ±20mV 근거 부재
cn/pu는 ±60(3σ corner)인데 skew ±20의 물리적 근거가 문서에 없음. PG-PD
mismatch의 실제 3σ 크기(Pelgrom Avt/√WL 기반)를 명시 권장. 과대설정 시
비현실적 영역 sim 낭비, 과소설정 시 tolerance 추정 범위 부족.

### 3.5 Stage D 9D pilot 500점 — Sobol 균등성 vs quadrant weighting 충돌
§1.5는 quadrant별로 Sobol을 **나눠 생성**(Q2 45% 등)하는데, 이러면 각
quadrant 내부에서만 Sobol 균등성이 보장되고 **9D 전역 low-discrepancy가
깨짐**. Saltelli sensitivity는 전역 균등 샘플을 전제하므로, **weighted
Sobol로는 Sobol indices가 편향될 수 있음**.
- **권고**: sensitivity 분석용 pilot은 **균등 Sobol**(weight 없음)로,
  GP 학습 정밀도용 추가 샘플만 quadrant-weighted로 분리. 또는 SALib 대신
  GP 기반 sensitivity(학습된 GP에서 Sobol 재샘플)를 쓰면 pilot 샘플 분포와
  무관하게 정확 — **후자를 권고**(이미 GP가 있으므로 추가 sim 0).

## 4. 종합 판정 & 착수 순서

**계획은 건전하고 잘 발전됨.** 착수 전 결정 — **전부 확정 (2026-07-09)**:

1. ✅ **[상류] Z_target = 6.50** (256Mb@99% Poisson). Vop 5레벨(0.4~0.8)
   확정. `Z_FIXED=6.50` 반영 완료.
2. ✅ **skew ±20mV 유지** (사용자 결정). Pelgrom 대략치로는 ~30mV일 수 있어
   다소 보수적이나 첫 배치로 무난. 실측 mismatch 나오면 재조정.
3. ✅ **n_mc 전사 필수화**. 비용 ~0(조건별 MC 같으면 헤더 상수 1개), overlap
   재사용 시 MC 불일치를 noise-aware GP가 처리.
4. ✅ **sensitivity는 GP-based Sobol로**. weighted Sobol(quadrant 45%)은
   Saltelli 균등 전제 위반 → 학습된 GP에서 균등 Sobol 재샘플로 S1/ST 계산,
   추가 sim 0.
5. ⬜ **[코드] render_deck에 skew 인자** (계획 §6 필수) → Stage B 선행.

### 전사 정밀도 & 워크플로우 (2026-07-09 확정, §3.6 신설)

**핵심 결정**: deck(.in)도 반출 불가 → 조건도 손 전사 대상. 그러나 **Sobol
설계는 우리가 만들므로** 조건값을 우리가 이미 안다. → **우리가 조건이 미리
채워진 표(row_id + cn/pu/sk/loc/mom)를 생성 → 사용자는 각 행에 결과
(snmr_avg, std [, n_mc])만 채움.** 전사량 9D pilot 기준 27,500 → 7,500 숫자
(**3.7배↓**), loc/mom 정밀도 고민 제거(우리가 full precision 지정).

**전사 정밀도 (조건표를 못 만드는 예외 상황의 안전장치)**:
| 입력 | 정밀도 | 근거 |
|------|--------|------|
| cn, pu, skew | **정수 mV** | 반올림 Vmin 오차 ≤0.7mV ≪ GP RMSE·MC노이즈 |
| loc, mom (ratio) | **소수 2자리 0.01** | 0.1은 7값뿐(Sobol 해상도 파괴), 0.001은 과잉 |
| snmr_avg, std | 측정 그대로 (mV) | 결과값, 반올림 금지 |
| n_mc | 정수 | noise-aware GP SEM 유도용 |

**즉시 반영할 문서 수정**:
- phase2_to_paper_plan §4.1: inverse "WLUD" → "PG-PD skew tolerance".
- hspice_sim_scope: 개정 계획(skew/global-scaling/Vop5)으로 supersede 표시.
- smooth_max α 단위/편향 재확인 후 §1.5 수치 확정.
