# 논문 기술 해설·발표 메시지·시연 도구 방향

작성: 2026-09-22. 대상: `manuscript/SRAM_Vmin_IEEE.docx`와 생성기 `manuscript/code/make_docx.js`, 현재 `manuscript/results/`.
사용자가 이 DOCX를 바탕으로 수정해 제출했다고 확인했다. 제출 후 수정본 자체는 아직 없으므로 제출본 전체의 오타 검토 완료를 뜻하지 않는다. 원고·모델·결과 파일은 변경하지 않는다.

> **상태 갱신 (2026-09-23):** 아래 §12의 GUI 방향은 당시의 설계 기록이다. 구현된 발표 해설·PPTX·GUI·Windows build 경로와 검증 기록은 `2026-09-23_presentation_delivery_checkpoint.md`를 기준으로 한다.

## 1. 가장 먼저 이해할 한 문장

**이미 수행한 비싼 회로 시뮬레이션을 학습해, 새로운 공정 조건의 SRAM 동작 한계를 빠르게 예측하고, 목표를 만족시키려면 무엇을 얼마나 바꿔야 하는지 역으로 탐색하는 도구다.**

Surrogate도 model이다. 따라서 발표 제목에서 “model 대 surrogate”보다는 “직접 회로 시뮬레이션 대 학습된 surrogate”라고 비교해야 한다. compact model/PDK를 부정하거나 교체하는 연구가 아니다. 물리·회로 모델에서 얻은 결과를 반복해서 활용하는 상위 설계 탐색 계층이다.

## 2. SRAM, 마진, Vmin

SRAM 셀의 PU(pull-up)는 저장 노드를 위로 당기는 PMOS, PD(pull-down)는 아래로 당기는 NMOS, PG(pass-gate)는 비트라인과 연결하는 접근 NMOS다. 읽을 때는 저장값을 유지해야 하고, 쓸 때는 기존 저장값을 바꿀 수 있어야 한다. 양쪽 요구가 같지 않으므로 읽기와 쓰기의 불리한 조건도 다를 수 있다.

마진은 동작을 얼마나 여유 있게 할 수 있는지 나타내는 양이다. 이 연구는 읽기 SNMR과 쓰기 Vtrip 지표의 평균·표준편차를 모드별로 다룬다. 지표 정의와 실패 방향을 고정한 상태에서 높은 평균, 작은 산포가 통계적 여유를 늘린다. 모든 Vtrip 정의에 이 방향을 일반화하면 안 된다.

같은 공정 조건에서도 셀마다 특성이 다르다. Monte Carlo(MC)는 이 mismatch를 무작위로 바꾸어 회로를 반복 실행한다. 그 결과에서 평균 μ와 표준편차 σ를 구한다. 평균만 안전해도 분포의 불리한 꼬리에 있는 셀은 실패할 수 있다. 큰 메모리는 셀이 많으므로 꼬리까지 고려해야 한다.

Vmin은 이 통계적 요구를 만족시키는 **가장 낮은 공급전압**이다. 전압을 낮추면 전력 측면의 이익을 기대할 수 있지만 동작 여유를 잃는다. 본 논문은 전력 절감량 자체를 실측한 연구는 아니다.

## 3. 식 (1)과 (2): 같은 V 단위라도 서로 다른 물리량

마진 M이 정규분포 N(μ, σ²)이고 M≥0을 성공으로 정의하면:

- 셀 성공확률: `Y_cell = Φ(μ/σ)`.
- 셀 실패확률: `p_fail = Φ(−μ/σ)`.
- 독립이고 동일한 셀 N개가 모두 통과할 확률: `Y_array = (1−p_fail)^N`.
- 희귀실패 Poisson 근사: `Y_array ≈ exp(−N·p_fail)`.

논문의 Φ 식은 **셀** 성공확률이다. array yield로 직접 부르면 안 된다. array target에서 허용 셀 실패확률을 구하고, 이를 정규분포 z 값으로 바꾼 것이 k다. 현재 논문 코드는 128 Mb, 99%, `k=6.3984`를 사용한다(`manuscript/code/_paths.py`). 루트 문서의 256 Mb/6.50와 섞지 않는다.

`g(p,V)=μ(p,V)−kσ(p,V)`는 전압 V에서의 통계적 마진이다.

`Vmin(p)=min{V:g(p,V)≥0}`이며 단조 교차 구간에서는 `g(p,Vmin)=0`을 푼다.

**Vmin=μ−kσ는 틀린 식이다.** 오른쪽은 공급전압이 아니라 마진이다. 양쪽 단위가 V라서 단위 검사만으로 잡히지 않는 오류다.

설명용 예: μ=100 mV, σ=10 mV, k=6.4면 통계적 마진은 36 mV다. 이것은 Vmin이 36 mV라는 뜻이 아니다. 공급전압을 바꾸면서 이 마진이 0이 되는 지점을 찾아야 Vmin이다. 이 예는 논문 결과가 아닌 교육용 가상 수치다.

## 4. 구현: 실제 학습하는 것과 학습하지 않는 것

실제 경로: `v_b_forward.py` → `python/src/surrogate.py` → `python/src/physics_layer.py`.

1. 여러 공정 조건·전압에서 MC를 수행해 μ, σ를 만든다.
2. 전사 오류·이상값을 점검한다. 수정된 라벨의 영향도 별도 검토가 필요하다.
3. 입력은 **9개 공정 축 + 공급전압 = 10차원**이다.
4. 입력을 표준화한다. mV와 무차원 배율이 섞여 있어 원래 숫자 크기만으로 거리를 비교하면 안 된다.
5. μ를 예측하는 GP와 log σ를 예측하는 GP를 각각 학습한다. 읽기와 쓰기는 별도 모델이다.
6. 예측한 log σ를 되돌려 양수 σ를 얻는다.
7. μ/σ와 목표 k를 비교하고 전압 격자 사이의 교차를 계산해 Vmin을 얻는다.
8. 같은 모델에 입력을 반복 질의하여 공정 축의 경계나 개선 시나리오를 찾는다.

현재는 μ와 log σ 모두 full-ARD Matérn 5/2 계열 GP다. 예전 additive σ 모델을 현재 구현으로 소개하면 안 된다. log 변환은 σ의 양수 성질을 유지하고 상대적 관측오차를 다루기 쉽게 한다. MC로 추정한 σ의 표준오차 `σ/√(2N_MC)`는 정규·큰 표본 조건의 근사이며 log σ의 오차는 대략 `1/√(2N_MC)`가 된다.

GP는 “가까운 입력에서는 출력도 관련될 것”이라는 커널을 이용해 관측점 사이의 함수를 학습한다. ARD는 축마다 상관거리(lengthscale)를 따로 둔다. 이를 **물리 법칙을 자동으로 보장하는 모델**이라고 부르면 과장이다. 현재 physics-guided의 핵심은 μ·σ 분리와 해석적 yield 변환이지, PDE나 물리 제약 손실을 푼다는 뜻이 아니다.

세 가지 불확실성을 구별한다:

- 셀 사이의 σ: 실제 mismatch에 의한 산포.
- MC 추정량의 표준오차: 유한 개 표본으로 μ·σ를 추정한 오차.
- GP 예측 불확실성: 학습 데이터가 충분하지 않아 함수를 모르는 정도.

GP가 출력하는 불확실성과 셀 σ는 같지 않다. RMSE 역시 개별 예측점의 보장 구간이 아니다.

## 5. 9개의 축은 무엇인가

| 코드 | 발표용 의미 | 직관 |
|---|---|---|
| cn | NMOS 공통 Vth shift | PG·PD를 함께 느리게/빠르게 |
| sk | PG–PD 사이 NMOS Vth skew | 접근 소자와 pull-down의 상대 균형 |
| pu | PMOS Vth shift | pull-up의 세기 변화 |
| l_com | NMOS local mismatch 공통 배율 | NMOS끼리의 개별 산포 크기 |
| l_sk | PG–PD local mismatch 배율 차이 | 두 NMOS 역할의 산포 불균형 |
| lpu | PMOS local mismatch 배율 | PMOS 개별 산포 크기 |
| m_com | NMOS mobility 공통 배율 | NMOS 구동 특성을 공통 조정 |
| m_sk | PG–PD mobility 배율 차이 | NMOS 역할별 구동 특성 불균형 |
| mpu | PMOS mobility 배율 | PMOS 구동 특성 조정 |

양의 Vth shift는 NMOS·PMOS 모두 느려지는 convention이다. PMOS는 부호 있는 Vth 자체보다 |Vth| 증가로 이해하면 된다. `l`이라는 내부 이름을 보고 곧바로 물리적 gate length(nm)라고 설명하면 안 된다. 현재 모델에서 사용하는 좌표는 local-σ 배율이며, 실제 공정 knob로의 변환에는 별도 보정이 필요하다. oxide thickness는 이 9축에 없다.

## 6. 순방향과 역방향: 무엇이 검증됐나

순방향은 “공정 조건 p를 주면 Vmin이 얼마인가?”다.
역방향은 “목표 Vmin을 주고 나머지 조건을 고정하면 특정 축을 어디까지 허용할 수 있는가?”다.

현재 검증의 중심은 **한 축의 구간을 이분 탐색**하는 것이다. 양 끝에서 목표를 사이에 두고 함수가 연속이면 근을 찾을 수 있다. 단조성까지 확인되면 그 구간의 유일한 경계로 해석하기 쉽다. 단조성은 GP이므로 자동 보장되지 않으며, 공급전압 단조성도 공정 축 단조성을 뜻하지 않는다. 여러 번 교차하면 모든 교차 후보를 표시하거나 구간 선택이 필요하다.

9개의 미지수를 Vmin 숫자 하나로 유일하게 복원할 수는 없다. 예를 들어 같은 Vmin 악화는 Vth 변화로도 mismatch 증가로도 생길 수 있다. 따라서 역추정은 **조건부 설계 경계**이지 단독으로 원인 소자를 확정하는 진단기가 아니다.

현재 수치(`forward*.json`, `corner*.json`, `inverse.json`):

| 항목 | 읽기 | 쓰기 |
|---|---:|---:|
| hold-out Vmin RMSE | 3.98 mV | 5.65 mV |
| 채점 가능한 미학습 코너 RMSE | 8.5 mV | 5.8 mV |
| 읽기 기반 cn 좌표 복원 RMSE | 1.46 mV | 해당 수치 아님 |
| 읽기 기반 pu 좌표 복원 RMSE | 1.94 mV | 해당 수치 아님 |

코너 4개를 평가했지만 각 모드에서 1개는 전압 하한 아래로 censored되어 수치 RMSE는 3개 코너 기준이다. censoring은 정확한 값을 모른다는 뜻이다. “<0.4 V”를 정확한 “0.4 V” 라벨처럼 채점하면 안 된다. hold-out도 유효 교차가 있는 조건을 채점한다.

전압의 Vmin 오차(mV)와 공정 Vth 좌표의 복원 오차(mV)는 단위가 같아도 다른 결과다. 이분 탐색의 수치 잔차를 아주 작게 만들어도 모델 자체의 오차까지 없어지지는 않는다.

## 7. 영향도 분석: inverse와는 별개로 결합하는 도구

역추정이 자동으로 영향도 순위를 주는 것은 아니다. **Sobol 분석으로 어느 축이 중요한지 찾고, inverse로 얼마를 바꿔야 하는지 구한다.** 이것이 발표의 세 번째 펀치라인이다.

현재 Table V의 대상은 Vmin 자체도 raw SNMR도 아닌 **읽기 `z=μ/σ` at 0.625 V**다. 학습 상자 안에서 각 축을 독립 균일분포로 움직여 평가한다. 실제 생산 lot 분포를 추정한 결과가 아니다.

| 축 | total-order S_T |
|---|---:|
| NMOS 공통 Vth cn | 0.413 |
| NMOS 공통 local-σ l_com | 0.272 |
| PMOS Vth pu | 0.200 |
| NMOS Vth skew sk | 0.065 |
| PMOS local-σ lpu | 0.045 |
| NMOS mobility m_com | 0.015 |
| NMOS mobility skew m_sk | 0.015 |
| PMOS mobility mpu | 0.008 |
| NMOS local-σ skew l_sk | 0.001 |

S1은 해당 축의 단독 효과, ST는 해당 축이 참여하는 상호작용까지 포함한다. 예: mismatch가 커질수록 Vth shift의 불리함이 증폭된다면 그 결합 효과가 양쪽 ST에 들어간다. 그러므로 ST를 더해 100% 원형차트로 그리면 안 된다.

**정확한 메시지:** NMOS local mismatch는 PMOS Vth보다 큰 total-order 영향도를 보이며 무시할 수 없다.
**틀린 메시지:** local mismatch가 모든 global corner 축보다 중요하다. 실제 1위는 cn이다.

`1−ST_cn−ST_pu≈0.387`은 이 분포·함수에 대한 점추정 기반 보수적 분산 몫이다. “코너 밖 최소 38%”는 실제 제조 불량 38%, Vmin 오차 38%, 또는 통계적 95% 하한을 뜻하지 않는다. 유한 표본 추정오차가 있고, 축 범위·분포·전압·모드를 바꾸면 순위도 달라진다. corner+MC가 local mismatch 자체를 전혀 다루지 못한다는 주장도 잘못이다. 여기서 지적할 것은 **local mismatch 강도를 독립적으로 변화시키는 축 탐색이 global corner 좌표만으로 대체되지 않는다**는 점이다.

ARD lengthscale의 역수는 Sobol의 대체물이 아니다. 국소 변화율, 전 구간 분산 영향도, 실제 개선 비용도 서로 다르다.

## 8. DTCO 시나리오: 가장 설득력 있는 시연

기존 사양 0.625 V를 0.575 V로 낮추는 상황을 보여준다. 사양이 50 mV 낮아졌다는 뜻이지, 모든 셀의 Vmin을 정확히 50 mV 개선해야 한다는 뜻은 아니다. 현재 surrogate의 두 제한 조건은 읽기 FSG 0.5961 V, 쓰기 SFG 0.5933 V여서 필요한 개선은 약 21.1/18.3 mV다.

`scenario.json`의 예측:

- NMOS local-σ만 개선: 약 10.9% 감소로 목표 교차.
- NMOS·PMOS local-σ를 함께 개선: 각각 약 7.8% 감소로 교차.
- global corner를 기준 nominal 쪽으로 이동: 기준 nominal에서의 offset 약 47% 축소로 교차.
- PMOS local-σ만 개선: 설정한 하한(30% 감소)에서 0.57558 V로 목표에 약 0.58 mV 부족.

마지막 0.58 mV는 보고된 수 mV 모델 RMSE보다 작다. “물리적으로 불가능”이 아니라 **surrogate 점예측상 상자 안 교차 없음, 추가 회로 검증 필요**라고 말해야 한다. RMSE로 이 점의 확률적 pass/fail을 계산할 수는 없지만, 이처럼 작은 차이를 확정판정할 근거도 없다.

두 제한 조건을 통과했다는 것이 9차원 전체 최악조건을 보장하지는 않는다. knob 변경 후 제한 코너가 바뀔 수 있고, 전체 공정 창·다른 코너·읽기/쓰기 공통 좌표 검증이 필요하다. 현재 read/write 모델은 서로 다른 온도와 배치에서 학습됐다. combined contour는 설계 탐색 예측이며 모든 점에서 공동 실측 검증됐다는 뜻이 아니다.

“10.9%가 47%보다 싸다”라고 말할 수 없다. 서로 다른 공정 knob의 상대 이동량일 뿐, 제조 비용·면적·지연·전력·공정 가능성을 같은 척도로 측정하지 않았다.

활용 순서: 중요 축 선별 → 축별 요구 변화량 산출 → 복수 knob 분담 후보 비교 → 공정팀이 feasibility/cost 검토 → 선택 후보를 원 회로 시뮬레이션으로 재확인. topology 변경, 레이아웃 변경, assist 추가는 현재 학습 입력에 없으면 곧바로 모델을 적용할 수 없다.

## 9. simulation cost 절감은 어떻게 설명할까

총 MC 실행량은 대략 `공정 조건 수 × 공급전압 수 × 조건·전압별 MC 표본 수`다. surrogate는 초기 학습용 MC를 없애는 것이 아니라 학습 후 많은 질문에 추가 MC 없이 답한다. 초기 학습 비용·GP 학습 시간·추가 검증 비용도 고려해야 한다.

현재 저장된 budget 결과:

| | 읽기 | 쓰기 |
|---|---:|---:|
| 학습 조건 | 1,700→400 | 1,700→400 |
| 전압 수 | 5→4 | 4→4 |
| MC depth | 5,000→500 | 5,000→500 |
| 실행량 비율 | 53.125× | 42.5× |
| baseline RMSE | 3.98 mV | 5.65 mV |
| reduced RMSE | 7.51 mV | 8.46 mV |

이 비율은 실제 wall-clock speedup 측정값이 아니다. MC 깊이 감소는 통계적 잡음 주입으로 모사한 budget 실험이다. “새 HSPICE 캠페인을 돌려 실행시간 53배를 측정했다”라고 설명하면 안 된다. 쓰기는 전압 수를 줄이지 않았다. 적정 표현은 **잡음 모사 기반 예산 실험에서, 정확도 저하를 감수하는 수십 배 MC 실행량 감소 후보를 제시했다**다.

## 10. 현재 DOCX에서 수정/완화할 항목

| 위치(생성기 검색어) | 문제 | 권장 수정 |
|---|---|---|
| §V-B `Vmin = μ − kσ` | Vmin과 마진 혼동 | Vmin은 μ−kσ=0의 전압 교차 |
| §IV-A `±15 mV (3σ)` | 허용 shift 5 mV에서 3σ=15 mV 도출 불가 | 5 mV가 허용 3σ 한계라면 단순 조건에서 σ≤5/3 mV; 실제 편향/분포 고려 |
| AXIS `N/P threshold skew` | sk는 PG/PD NMOS skew | PG–PD NMOS threshold skew |
| §II-A gate length/oxide thickness | 실제 9축과 불일치 | 구현된 shift, mismatch/mobility 배율 열거 |
| §III-B/결론 `on four unseen ... RMSE` | RMSE 분모 3개/모드 | four evaluated, three uncensored scored per mode |
| §VI `local mismatch, not the global corners, ... primary` | cn이 1위 | local mismatch exceeds PMOS shift, alongside strongest NMOS shift |
| §II 식(1) yield Y | cell/array 구별 누락 | Y_cell, array 변환 별도 제시 |
| Table III `+-0.97 mV` | 부호 오타 | −0.97 mV |
| §II-C·§V-A `V_{min}`, `k_{σN}` 등 | 일부 raw 수식 마크업 잔존 | 정상 subscript 표시 |
| §III-A `Sub-5.65-mV accuracy` | RMSE를 전체 오차 상한처럼 읽을 위험 | RMSE 3.98/5.65 mV on scored hold-out |
| §II-C yield debugging | 한 Vmin으로 실제 원인 유일 규명 불가 | 조건부 원인 후보·개선 후보 탐색 |
| §VI 53× | wall-clock 실측·무손실로 오해 | 실행량 기준·noise-emulated·오차 증가 명시 |

가장 큰 해석 한계: 3.98/5.65 mV는 **동일한 Gaussian μ/σ 정의로 계산한 회로 시뮬레이션 기준 Vmin에 대한 오차**다. 실리콘 array yield를 그 오차로 보증하지 않는다. 현재 DOCX는 tail correction을 future work로 두었지만 저장된 `lobe.json`에는 Gaussian 형태 이탈과 약 70 mV 수준의 모형 의존 보정 추정이 있다. 이 값도 실리콘 검증값은 아니며, 보정을 적용한 결과를 현재 기본 결과와 섞어 제시하지 않는다. 발표 backup에 Gaussian tail 가정·실리콘 미검증을 명확히 남긴다. 수천 MC 표본으로 6σ대 희귀 꼬리를 직접 관측했다는 주장은 피한다.

## 11. 네 가지 펀치라인에 맞춘 발표 순서

1. 문제: MC를 매번 돌리면 느리고, 제한된 corner만 보면 창 전체가 안 보인다.
2. 제안: 회로 시뮬레이션을 재사용하는 μ/σ surrogate + 해석적 yield 계층.
3. 구현: 9축+VDD → μ/logσ GP → z → Vmin. physical σ와 모델 uncertainty 구분.
4. 신뢰성: hold-out 3.98/5.65 mV, 별도 코너 검사. 같은 정의의 reference임을 명시.
5. 핵심 전환: “Vmin이 얼마인가”에서 “무엇을 얼마나 바꿔야 하는가”로.
6. 영향도: cn, NMOS local-σ, pu 순위. Sobol 대상은 z at 0.625 V.
7. GUI 시연: 0.575 V target → 단일 knob → 두 knob 분담 → 읽기/쓰기 동시 검토.
8. 비용: 53.1×/42.5× 실행량 후보와 RMSE penalty를 함께 제시.
9. 결론: 최종 sign-off 대체가 아니라, 검증할 후보를 빠르게 좁히는 DTCO 도구.

발표 마지막 문장: **“시뮬레이션을 적게 하는 데서 끝나지 않고, 같은 시뮬레이션으로 설계자가 물을 수 있는 질문을 늘립니다.”**

## 12. GUI 요청: 초기 설계 방향과 선택지 (2026-09-22 기록)

사용자가 추가로 현재 모델 기반 inverse 시연 GUI, 시나리오 화면/영상 자료 제작을 요청했다. 실행 대상 OS는 확인 중이다.

- 권장: 로컬 Python 계산 엔진 + 브라우저 UI. 원 데이터와 모델은 로컬에 유지. 기존 GP 및 physics layer 재사용. 설치 의존성은 기존 환경을 우선하며 추가 패키지는 별도 판단.
- 대안: 데스크톱 GUI. 브라우저 서버가 필요 없지만 디자인·배포·영상 레이아웃 작업이 늘어남.
- 대안: 사전 계산 시나리오 재생. 발표 안정성은 높지만 임의 inverse를 실시간으로 계산할 수 없음.

초기 범위: 9축 입력, read/write/combined 조건 표시, 목표 Vmin, 한 축 inverse, scan/bracket 검사, 시나리오 비교, 논문 프리셋, 그림·조건/결과 내보내기. 자동 영상 인코딩은 의존성·실행환경 확인 후 결정하고 실시간 계산과 사전 재생을 혼동하지 않는다.

필수 안전 표기: Gaussian target(k=6.3984), 모드별 온도, training bounds, 해 없음/다중 교차, censoring, point estimate, combined 미검증, 계산 진행/실패. 임의 9축 전역 최적화나 제조비용 최적화는 초기 범위 밖이다. 저장 체크포인트가 학습 입력을 추가 요구하는지 확인하며, 배포용 번들에 raw 자료를 무심코 포함하지 않는다.

성공 기준: 기존 baseline·scenario 숫자 재현, 합성 함수 inverse 단위검증, 잘못된 입력·범위 밖·censored 결과 검사, 원고와 모델 파일 미변경, 발표 화면 export 검증. 설계·실행환경 확정 후 구현한다.

## 13. 조사 기록과 한계

- `paper_en*.md`를 최신 원고로 읽으려다 README D-16 경고를 확인하여 DOCX/생성기/JSON으로 기준을 전환했다. Markdown 수치 혼용 금지.
- 셸 `python` 실행파일은 없어서 `python3` 또는 `.venv/bin/python`을 사용했다.
- 현재 작업은 저장된 결과·코드·DOCX의 정합성 검토다. HSPICE 재실행, GP 전체 재학습, 실리콘 검증을 수행하지 않았다.
- 기존 untracked `.agents/`, `.claude/skills/`, `skills-lock.json`은 사용자 환경으로 보고 건드리지 않았다.

### 추가 확인

- 사용자가 실행 환경을 **Windows 발표용 PC 독립 실행**으로 지정했다. WSL·Linux 서버에 연결하는 배포는 기본안에서 제외한다.
- 현 체크포인트에는 GP 추론을 복원하는 데 필요한 training y가 들어 있지 않다. Windows 배포 번들을 만들 때 현재 로더/동일 split으로 훈련 상태를 재구성하고 검증해야 한다. 재구성 후 raw XLSX가 없는 상태에서도 실행 가능한지 테스트한다. 이 번들도 학습 정보를 담으므로 사내 모델 자산으로 취급하며 외부 공개하지 않는다.
- 시나리오 코드의 nominal은 물리적 공통 nominal이 아니라 배치별 중앙값이다(read cn/pu=−13/+11 mV; write +21/−11 mV). GUI의 논문 재현 모드와 공통 좌표 비교 모드를 구별해야 한다.
- `v_e_scenario.py`는 단조성 bool을 기록하지만 false일 때 탐색을 중단하지 않는다. GUI에 해당 동작을 그대로 복사하지 않는다.
- hold-out 300조건 중 유효 Vmin 채점은 읽기 245, 쓰기 228. 최대 절대오차는 각각 약 20.50/43.29 mV다. 읽기 inverse는 cn 245/245, pu 239/245 복원 성공 조건 기준이다.

### 공개 원리 참고자료 (2026-09-22 확인)

미공개 원고나 수치를 외부 질의에 보내지 않고 일반 개념만 확인했다.

- [GP 예측 평균·불확실성 — scikit-learn 공식 문서](https://scikit-learn.org/stable/modules/gaussian_process.html)
- [Sobol S1/ST 정의 — SALib 공식 문서](https://salib.readthedocs.io/en/latest/user_guide/basics.html)
- [입력 분포 설정 — SALib 공식 문서](https://salib.readthedocs.io/en/latest/user_guide/advanced.html)
- [이분 탐색 연속성·bracket 조건 — SciPy 공식 문서](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.bisect.html)
- [분포 꼬리 외삽 주의 — NIST](https://www.itl.nist.gov/div898/handbook/apr/section4/apr43.htm): 신뢰성 수명분석의 일반 주의사항이며 SRAM 검증 자료는 아님.
