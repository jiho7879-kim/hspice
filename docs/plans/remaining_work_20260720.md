# 잔여 작업 목록 — 2026-07-20 기준

> 논문 v3.0(IEEE 형식) 확정 시점의 미완 사항 정리.
> 정본: `papers/paper_en_v3_ieee.md`, `papers/paper_kr_v3_ieee.md`
> 이전 버전은 `papers/archive/`로 이동.

---

## A. 사내 진단 대기 (최우선 — 논문 결론에 영향)

**tail 형상 진단** — `docs/plans/infab_tail_diagnostic_request.md`

| 항목 | 내용 |
|---|---|
| 목적 | 최소값 통계 z-score의 체계적 낙관(§2.4) 크기 확정 |
| 규모 | 9개 조건(최소 3개: **981, 435, 147**) × MC 100,000 |
| 비용 | 전체 배치의 약 1.8% |
| 스크립트 | `python/scripts/infab_snmr_tail_diag.py` (numpy만 필요, 합성 3케이스 검증 완료) |
| 회신 | 조건당 `=== TAILDIAG v1 ... ===` 블록 (텍스트) |

**결과에 따른 처리 (재시뮬레이션 불필요, 전부 후처리):**

| 결과 | 조치 |
|---|---|
| `best=GAUSS`, zbias≈0 | 현재 수치 전부 유효. §2.4를 "검증 완료"로 축소, 방어선 확보 |
| zbias +0.1~0.3σ | `Z_t → 6.50 + zbias` 적용 후 스크립트 재실행 (~15분) |
| zbias ≈ +0.7σ | 동일 보정. EOL 통과율 88.5% → 약 80.5%. **논문 헤드라인화** |
| zbias 조건 의존 | zbias를 입력(특히 l_com)의 함수로 피팅 후 적용. 진단 조건 추가 필요 가능 |

영향 범위: **절대 Vmin·사양 통과율만** 변경. 상대 결론(민감도 순위, 등고선
형상, skew 허용폭, 코너 서열)은 불변.

---

## B. Vtrip 전사 진행 중

**현황**: 2026-07-20 기준 0.5V 진행 중. 시트
`python/data/sheet_final_vtrip_seed2028.xlsx` (10,000행, 조건 기입 완료).

**전사 정밀도 (확정)**: avg, std 모두 **소수점 1자리**.
- 근거: std 민감도가 avg의 z배(=6.5배). 1자리 반올림 → Vmin 오차 0.44mV.
  MC 자체 노이즈 바닥이 약 1.8mV이므로 그 1/4 수준으로 무시 가능.
- 정수는 부족(4.40mV, 노이즈 바닥의 2.4배), 2자리는 낭비.

**주의 사항 2건:**
1. **QC 임계값이 SNMR 전용** — 현재 하드코딩된 `avg ∈ [-50,300]mV`,
   `std ∈ [3,30]mV`는 Vtrip에 부적합. Stage C 실측 기준 Vtrip은
   avg 154~415mV, std 14.4~27.7mV. **Vtrip용 QC 미구현 — 전사 완료 전 필요.**
   권장: robust 통계(median ± MAD) + Vop 추세 이탈 검사로 지표 무관하게.
2. **컬럼명이 `snmr_avg`/`snmr_std`** — Vtrip 시트인데 SNMR 이름. 스크립트는
   그대로 동작하나 두 배치 혼용 시 혼동 주의.

**제안(미실행)**: Vop 레벨 하나 끝날 때마다 QC 돌리는 점진 검사. SNMR에서
22건이 나왔으므로 Vtrip도 유사 예상. 끝나고 한꺼번에보다 그때그때가 유리.

---

## C. 미완 분석 — 실데이터 보유, 계산만 하면 됨

**추가 시뮬레이션 불필요.** Vtrip 완료 후 그림이 읽기·쓰기 통합본으로 바뀔
가능성이 있어 의도적으로 보류 중(두 번 작업 방지).

| 항목 | 논문 위치 | 필요 데이터 | 상태 |
|---|---|---|---|
| 등고선 Hausdorff | §V-D, Fig.4 | 보유 | **정의 결정 필요** (아래) |
| 실데이터 역추정 재현 | §V-E, Fig.5 | 보유(대리모델 측 연산) | 미실행 |
| 4D 외부검증 (nominal slice) | §V-F | `260713_stageB_snmr.xlsx` 1,745행 보유 | 미실행 |

**등고선 Hausdorff 정의 이슈**: 9차원에 조건이 흩어져 있어 기하학적 실측
등고선 추출이 곤란(2D 평면 위에 조건이 놓여있지 않음). 대안:
- (a) 4D Stage B(skew=0 평면, 밀도 충분)에서 실측 등고선 추출 → 원 의미 충실
- (b) Hausdorff 제외, **목표 등고선 근방 조건의 Vmin 오차**로 대체 → §V-D의
  사양 판정 일치율(98.3%/99.3%)과 자연 연결
- **권장: (b) 주 + (a) 를 §V-F 외부검증에 병기**

---

## D. Vtrip 완료 후 재산출 필요

| 항목 | 현재 상태 | 조치 |
|---|---|---|
| sk* (읽기·쓰기 통합 최적 skew) | Stage C 4D 참조값 −2mV | 9D 기준 재산출 |
| 읽기·쓰기 통합 Vmin (smooth-max) | 미산출 | 신규 |
| Vtrip 자체 민감도/Sobol | 미산출 | `final_snmr_seed2027_sensitivity.py` 재사용 |
| Vtrip Vop 충분성 | 구조적 논거는 동일(사양 전압이 [0.6,0.7] 내부) | 실측 확인 권장 |

**방향적 결론은 이미 확정**: 읽기만으로 skew 사양을 정하면 안 됨(읽기는 양의
skew 유리, 쓰기는 반대 방향).

---

## E. 논문 마무리

| 항목 | 상태 |
|---|---|
| 참고문헌 서지정보 | **placeholder** — 15편, 제출 전 확정 필요 |
| 제목·저자·소속 | 미확정 (현 제목은 임시) |
| Fig. 1–7 | **미생성** — `gen_paper_figures.py`는 구 구조용 8종. v3 구조에 맞춰 재작성 필요 |
| (sk, l_com) 결합 스윕 | 미실행. §VII-D에서 skew 사양 확정 전 필요하다고 명시함 |

---

## F. 코드 부채

| 항목 | 위치 | 심각도 |
|---|---|---|
| `stratified_train_test_split`이 `X[:,:2]`로만 그룹화 — 누수 인접 | `python/src/data.py` | 중 (Stage B는 로컬 분할로 우회함) |
| FSG 최악코너 자동검사가 Vmin>maxVop일 때 SKIP 반환 | `stageB_real_data.py` | 하 |
| Vtrip용 QC 임계값 미구현 | 신규 필요 | **중 (B항 참조)** |
| 물리범위 QC를 파서에 상시 내장 | `python/src/hspice_io.py` | 중 (논문 §III-D 권고사항) |

---

## G. 데이터 반출 주의 (신규 — 2026-07-20)

**`.gitignore`가 사내 실측 데이터를 충분히 배제하지 못함.**

현재 패턴 `python/data/hspice_real*.xlsx`는 11개 데이터 파일 중 **2개만**
잡는다. 배제되지 않는 파일:

- `sheet_final_snmr_seed2027.xlsx` ← **최종 배치 실측 데이터 (745KB)**
- `sheet_final_vtrip_seed2028.xlsx`
- `260713_stageB_snmr.xlsx`, `_pre_fix_backup.xlsx`
- `final_2000_seed2026.xlsx`, `stageD_500_seed2026.xlsx`
- `inhouse_condition_snmr.xlsx`, `inhouse_condition_vtrip.xlsx`
- `fixed_corner.xlsx`

추가로 `python/results/final_snmr_seed2027/*.pth`(실측 데이터로 학습된
대리모델 가중치)와 `*.json`(파생 지표)도 반출 시 주의 대상.

**버전 관리 도입 전 `.gitignore` 보강 필수.** 논문 자체가 "PDK 비공개,
팹에서 덱·결과 반출 불가"를 명시하고 있으므로 일관성 필요.

---

## 우선순위 요약

1. **Vtrip QC 스크립트** (전사 완료 전에 있어야 함) — F항
2. **tail 진단 회신** 대기 → 회신 시 즉시 후처리 — A항
3. Vtrip 전사 완료 → C·D항 일괄 실행
4. 그림 생성 + 참고문헌 확정 — E항
5. `.gitignore` 보강 (버전 관리 도입 시) — G항
