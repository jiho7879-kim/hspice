# Legacy 조건 설계 감사 및 final 재실행 결정 (2026-07-14)

> 대상: 사내에서 이미 실행된 StageD(500 조건)·final(2000 조건) 배치의 조건 설계.
> 원본 생성 스크립트는 유실. 사용자 손 전사 시트(64 조건)로부터 레시피를
> 포렌식 복원 → 설계 결함 발견 → **final 재실행 결정** 및 v2.1 설계 확정.

---

## 1. 레시피 복원 (재현성 검증)

사용자가 전사한 64개 조건과 재구성 코드를 대조하여 legacy 생성기를 복원했다.
**60/64 완전 일치**, 불일치 4건은 전부 전사 오류로 규명 (아래 §1.2).

### 1.1 복원된 legacy 레시피

| 항목 | 값 |
|---|---|
| sampler | `scipy.stats.qmc.Sobol(d=9, scramble=True, seed=2026).random(n)` |
| seed | 2026 |
| n_quad | `int(n_cond * w)` — 500: 100/225/75/100, 2000: 400/900/300/400 |
| weights | `{(+1,+1):0.20, (-1,+1):0.45, (-1,-1):0.15, (+1,-1):0.20}` ※ 스펙 v1.0과 (+,+)/(−,−) 스왑 |
| 축 순서 | `[pu, cn, sk, lpu, l_com, l_sk, mpu, m_com, m_sk]` |
| sign flip | 전 범위에서 뽑은 뒤 cn, pu 부호를 quadrant에 맞게 반전 |
| clamp | `\|skew\| <= \|common − 1.0\|` — **l_sk와 m_sk 둘 다** 적용 |
| vop | 0.4 / 0.5 / 0.6 / 0.7 / 0.8 |
| 정렬(시트) | cn 오름차순(반올림 전 float). 동점 순서는 유실된 shuffle에 의존 → 복원 불가, 값 매칭으로 대체 |
| deck 표기 | `f"{x:4f}"` = 소수 6자리 (시트의 2자리는 전사 시 반올림) |

재생성 스크립트: `python/scripts/legacy_sobol_regen.py`
골든 조건표: `python/data/stageD_500_seed2026.xlsx`, `python/data/final_2000_seed2026.xlsx`
(entry / conditions_full(6자리) / meta 3시트. **매칭은 num이 아니라 cond_id 또는 조건값**.)

> scipy 종속성 주의: scramble Sobol 스트림은 scipy 버전에 민감. scipy 1.18에서
> 재현 확인. 골든 xlsx가 버전 독립적 기준.

### 1.2 규명된 전사 오류 (1차 시트 64행 기준)

| 행 | 시트 값 | 실제 값 |
|---|---|---|
| 11 | cn=−60 | **−59** (raw −59.47) |
| 91 | l_comp=1.305 | **1.05** |
| 141↔146 | l/m 블록 교차 뒤바뀜 | 2차 시트에서 확인·정정 |
| 261, 266 | m_comp=0.83 | **0.82** (raw 0.820390) |

64행 중 4~6행 오류 = **행 오류율 ~9%** → 조건 손 전사 폐지의 실증 근거.

---

## 2. 발견된 설계 결함 (legacy 배치)

### F1. quadrant마다 같은 seed 재사용 → mirror 중복 (치명)
4개 quadrant가 **동일한 Sobol 스트림**을 재사용, cn/pu 부호만 반전.
- final 2000: **실질 설계점 900개** (4중 mirror 300그룹 + 3중 100그룹 + 단독 500)
- 조건의 75%가 쌍둥이 보유 (9좌표 중 7개 완전 동일)
- **무작위/조건 단위 hold-out 시 test의 ~74%가 train에 쌍둥이 존재** → R², Hausdorff 등 전 지표 낙관 편향
- StageB(348 조건)도 동일 생성기: pu-mirror 114쌍 → StageB 게이트 수치도 동일 오염

### F2. clamp가 nominal에서 mismatch를 0으로 강제
`|sk| ≤ |com−1|` → l_com≈1.0 근처(final의 330개 조건)에서 skew≈0.
**nominal local-sigma/mobility에서의 PG-PD mismatch 정보가 데이터에 없음.**
또한 com·sk 간 인공 상관 발생 → Saltelli 민감도의 독립성 전제 위반.

### F3. StageD 500 ⊂ final 2000 (완전 포함)
같은 seed로 n만 확대 → Sobol 스트림 앞부분 재사용. 500을 독립 검증셋으로
사용 불가 (완전 누수).

### F4. 파생 lpg/lpd가 선언 범위 밖 + 표시정밀도 join 모호
- lpg/lpd/mpg/mpd 실범위 0.63~1.37 (선언 [0.7,1.3] 위반 121~130개/2000)
- 2자리 반올림 값으로는 final 2000 중 **22개 조건이 join 모호** → cond_id 매칭 필수

### F5. quadrant 가중치가 스펙과 스왑
실행본: (+,+) 20% / (−,−) 15%. 스펙 v1.0: (+,+) 15% / (−,−) 20%. (경미)

---

## 3. 논문 영향 판정

| 판정 | 항목 |
|---|---|
| 🔴 무효화 | 무작위 hold-out 기반 headline 수치 전부 (mu R², Hausdorff, Vmin RMSE) — F1 |
| 🟠 재설계 | Sobol/Saltelli 민감도(F12 figure) — F1+F2로 계산 불가 |
| 🟠 명시 필요 | 입력공간 기술(§2.1), nominal-mismatch 외삽 한계 — F2, F4 |
| 🟢 무관 | differentiable physics layer, gradient inversion, corner anchor, noise-aware GP, censored 지표, z_eff — 방법론 기여는 설계와 독립 |

---

## 4. 결정 (2026-07-14, 사용자 확정)

**D1. final만 재실행한다.** 논문 headline은 final에서만 나옴. 동일 비용(10,000 sim)으로
실질 설계점 900 → 2000 회복. legacy StageD·legacy final 결과는 전사하지 않는다.

**D2. StageB는 유지한다 (폐기 아님).**
- 파이프라인 게이트 역할은 이미 수행 완료 (전사 워크플로·파서·물리 방향성 검증)
- 수치를 인용할 경우 mirror-grouped split (`src/data.py::grouped_train_test_split`)로 재평가
- 9D 모델의 **nominal-slice 외부 검증**으로 재활용: StageB 조건은 9D 공간의
  (l=m=1, l_sk=m_sk=0) 평면 위 실측 348점

**D3. legacy StageD 500은 폐기.** legacy final의 부분집합 + 결함 설계 + 결과 미전사.
새 final의 초기 QC가 필요하면 별도 파일럿 없이 새 final의 앞 N개 조건만 먼저 전사.

**D4. 재실행 설계 (condition_gen v2.1) — frozen:**

| 항목 | legacy (버그) | v2.1 (확정) |
|---|---|---|
| quadrant 샘플러 | 4개 모두 같은 seed | **quadrant별 독립 스트림** (`seed+1+i`) |
| method | scipy Sobol scramble (버전 종속) | **numpy PCG64 rng** (버전 안정 — 사내 이식 계약) |
| ratio 파라미터화 | com+skew (유지 — 물리적으로 옳음, §5) | com+skew 동일 |
| clamp | `\|sk\| ≤ \|com−1\|` | **no-clamp: com ⊥ sk 완전 독립.** 파생 lpg/lpd는 [0.625, 1.375]까지 스필 허용 |
| weights (SNMR deck) | 45/15/20/20 (스왑본) | **FSG 45 / FFG 20 / SSG 15 / SFG 20** (스펙 v1.0) |
| weights (Vtrip deck) | — | **SFG 45 / SSG 30 / FFG 15 / FSG 10** — vtrip은 **별도 deck** (사용자 확인) |
| vop | 0.4~0.8 5레벨 | 동일 |
| 범위 | cn/pu ±60mV, sk ±20mV, com [0.7,1.3], skew ±0.075 | 동일 (§5 검토로 유지 확정) |

no-clamp 선택 근거: (i) com⊥sk 독립 → Saltelli 민감도 유효, (ii) nominal과
극단 common 양쪽에서 mismatch 정보 확보, (iii) 스필 구간 [0.625,0.7)∪(1.3,1.375]의
model card 유효성은 사내 확인 사항.

**D5. 평가 프로토콜.** legacy 데이터(StageB 포함)를 쓰는 모든 평가는
mirror-grouped split 필수. 새 final은 mirror가 없으므로 조건 단위 split로 충분
(조건의 5개 Vop 행은 같은 쪽에 묶는 기존 규칙 유지).

**D6. 논문 구조 변경.** 점진(3D→4D→9D 게이트) 서사 폐기 → 기여 중심 구조.
StageA/B는 차원 확장 보조 실험 + nominal-slice 외부 검증으로만 등장.
`papers/paper_kr.md`, `papers/paper_en.md` v0.5에 반영.

**D7. 조건 무전사 프로토콜 유지.** 사내와 (stage, n_cond, seed, metric, method,
vops, prefix, start) 공유 → `inhouse_deck_gen.py` (FROZEN CORE v2.1) 전달.
사용자는 결과값(snmr_avg, snmr_std, n_mc)만 기입. 이식 검증은 self-test 기준값.

**D8. 데이터 요구사항 (재실행 시트).** lobe-resolved z_eff(적대적 리뷰 A1)를
쓰려면 가능하면 per-lobe 통계(snmr_L_avg/std, snmr_R_avg/std, rho)를 함께 수집.
불가 시 min-lobe (avg, std)로 진행하되 논문에서 z_eff 보정 한계 명시.

---

## 5. com+skew 파라미터화 검토 (질문 4에 대한 결론)

**물리적으로 타당하다.** PD·PG는 같은 NMOS flavor — 지배적 변동 원인(게이트 스택,
채널 도핑, 애닐, 리소 CD)은 공유(common), 잔여는 W/L·레이아웃 환경(STI/LOD)·
flavor 차이에 의한 불완전 추적(skew). Vth의 cn/sk 구조와 동일 철학으로 9D 전체가
내적 일관.

정량 근거: uniform 가정에서 암묵적 corr(lpg,lpd) = (Var(com)−Var(sk))/(Var(com)+Var(sk))
= (0.03−0.0019)/(0.0319) ≈ **0.88** — 같은 flavor 추적 상관의 통상 범위(0.85~0.95) 내.
Vth 쪽(±60/±20)은 ρ≈0.80으로 같은 급.

범위 판정:
- com ±30%: corner(통상 ±10~15%) 대비 넉넉 — contour를 도메인 내부에 두는 여유로 유지.
  단 MOMSKEW=0.7의 model card 유효성 사내 확인 권장.
- skew ±0.075 (PG-PD 최대 벌어짐 0.15): 적정. skew/common 비 0.25로 Vth(0.33)와 같은 급.
- 유의: l_sk 효과는 PG/PD 대칭 성분에서 2차항 — 조건당 MC 노이즈(SEM ~1.6%@MC2000)에
  근접할 수 있음. ARD가 둔감 판정하면 그 자체가 발견("PG-PD ratio mismatch는 SNMR에 2차적").

---

## 6. 코드 변경 이력 (이 감사에서)

| 파일 | 변경 |
|---|---|
| `src/condition_gen.py` | v2.1: Stage-D 레이아웃 com/skew, no-clamp, `in_design_domain()` 추가 |
| `src/inhouse_deck_gen.py` | FROZEN CORE v2.1 동기화, `condition_to_deck_params` ratio 분해 반영 |
| `src/utils.py` | `STAGE_DEVICE_COLS["D"]` 갱신, LOC/MOM/LSK/MSK·VOPS_REAL 상수 추가 |
| `src/data.py` | `grouped_train_test_split()` 추가 (mirror-group 단위 분할) |
| `scripts/legacy_sobol_regen.py` | legacy 재생성기 (provenance 보존용 — 신규 사용 금지) |
| `scripts/stageB_leakage_check.py` | StageB 조건분할 vs mirror-grouped 열화 측정 (실행 대기) |
| `tests/test_condition_gen.py` | v2.1 계약 고정: 도메인·레이아웃·grouped split 누수 테스트 |

## 7. 남은 액션

- [ ] v2.1로 final 2000×2 (SNMR deck / Vtrip deck) 조건 생성 + 사내 전달 패키지
- [ ] 재실행 시트에 per-lobe 컬럼 포함 여부 사내 확인 (D8)
- [ ] MOMSKEW/VTSLSKEW 0.625~1.375 model card 유효성 사내 확인 (D4)
- [ ] StageB grouped 재평가 실행 (`stageB_leakage_check.py`) — 논문 인용 시
- [ ] `docs/plans/phase2_to_paper_plan.md` §5(차원 확장)·§6(논문) 갱신 — D6 반영
