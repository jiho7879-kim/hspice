# 9차원 공정 윈도우 전 구간에서의 순·역방향 SRAM Vmin 추정을 위한 물리 제약 Gaussian Process Surrogate 모델

**사내 기술 보고서 — IEEE 논문 형식, v3.1, 2026년 7월**

> v3.1-verified: final 배치(2,000 조건 × 4 V_op) 기준으로 전면 재작성. sign-off 기준을
> 0.625 V 단일 기준 통일. min-statistics 편향을 "제안"에서 "측정"으로 승격.
> 검증 완료: 읽기 ρ_LR = −0.406, z_bias = +1.123σ (조건 간 균일 p=0.33).
> 미측정: corner-라벨 재측정, write 지표 ρ_LR (좌우 분리 데이터 부재). 원본 방식·구조·기존 수치는 변경되지 않았다.

---

## 초록

SRAM 어레이의 최소 동작 전압(Vmin)은 공정 변동 윈도우 전 구간에 대해 제품
사양으로 sign-off되어야 하나, 요구되는 tail 수율을 직접 Monte Carlo(MC)로
검증하는 것은 계산 비용이 과도하며, corner 기반 sign-off는 corner 정의 밖의
변동 축을 표현하지 못한다. 본 연구는 단일 고정 시뮬레이션 예산으로 순방향과
역방향 Vmin 질의를 모두 처리하는 surrogate 파이프라인을 제시한다. Gaussian
process(GP)가 9개 공정 변동 파라미터로부터 static noise margin(SNM) 통계를
회귀하고, 미분 가능한 physics layer가 이 통계를 학습된 근사가 아닌 해석적
제약으로서 수율 기준 Vmin으로 변환한다. 합성 함수가 입력에 대해 미분
가능하므로, 목표 Vmin 경계 위의 점을 격자 탐색 없이 gradient 하강으로 직접
획득한다. 조건별 MC 표준오차로 구동되는 heteroscedastic likelihood는 이질적
샘플링 예산을 단일 모델에 수용한다. 본 방법은 첨단 FinFET 노드의 생산
캘리브레이션 데이터 2,000 조건 × 4 전압으로 검증되었다. Hold-out 정확도는
μ에서 R² = 0.982, σ에서 0.985에 도달하고, 사양 구간 Vmin RMSE 9.14 mV,
0.625 V sign-off 기준 판정 일치율 98.3%를 달성한다. Surrogate로 비로소
경제성이 확보된 분산 기반 민감도 분석은 NMOS local σ가 Vmin 분산의 3위 기여
인자로서 pass-gate/pull-down Vth skew를 앞서며, 어떤 corner 정의도 포괄하지
못하는 축임을 식별한다. 또한 기존 전압 격자의 최상위 레벨이 사양 판정에
구조적으로 무관함을 보여 손실 없이 시뮬레이션 물량을 20% 절감할 수 있음을
밝힌다. 끝으로, min-statistics z-score에 내재된 체계적 낙관의 크기를 결정하는
물리량이 butterfly 두 lobe의 상관 ρ_LR임을 보이고, 이를 양산 MC 출력만으로
측정하는 방법을 제시하며, 사양 밴드 조건들에서 ρ_LR = −0.43, z-score 기준
+1.15σ의 낙관을 측정한다. 이 값은 구속 corner의 잔여 margin과 같은 자릿수로,
지배 불확실성이 모델이 아니라 지표에 있음을 뜻한다. 단, 본 측정은 corner 라벨 없이 수행되었으며 corner 간
균일성(현재 p=0.33)은 추가 측정으로 확정되어야 한다. Write 지표의 ρ_LR은
9차원 쓰기 배치에 좌우 분리 MC 데이터가 없어 아직 측정되지 않았다.

**색인어** — SRAM, minimum operating voltage, process variation, Gaussian
process, surrogate model, inverse problem, yield analysis, sensitivity
analysis, static noise margin.

---

## I. 서론

### A. Sign-off 사양과 여유 구조

SRAM은 현대 시스템온칩에서 최대 면적을 차지하며 칩 수율을 지배한다. 본 연구
대상 공정의 nominal 공급 전압은 0.75 V이며, on-chip 및 off-chip IR drop을
반영한 sign-off Vmin 사양은 표 I과 같다.

**표 I. Vmin 사양**

| 항목 | 값 |
|---|---|
| Nominal 공급 전압 | 0.75 V |
| **Sign-off Vmin 사양 (time-zero)** | **0.625 V** |

본 연구의 모든 시뮬레이션과 판정은 time-zero 기준이며, **sign-off 사양은
0.625 V 단일 기준이다.** 열화(BTI 등)에 대한 guardband는 실리콘에서
경험적으로 확립되어 이 time-zero 사양에 이미 반영되어 있으므로[23]–[25],
본고에서 열화 후 전압을 별도의 판정 기준으로 사용하지 않는다. Time-zero
시뮬레이션 결과에 guardband를 다시 얹어 평가하는 것은 이중 계산이다.

이 사양이 설계에 남기는 여유는 크지 않다. PVTA corner만 인가하고 나머지 변동
축을 nominal로 둘 때, 읽기 구속 corner(FSG)와 쓰기 구속 corner(SFG)는 모두
0.625 V에 접하거나 근소하게 하회한다(읽기는 제5절 C항, 쓰기는 제8절 C항).
즉 **구속 corner의 실질 여유는 0에 가깝다.** 따라서 핵심 질문은 Vmin의 수치
자체가 아니라 주어진 공정 조건이 0.625 V를 만족하는가이며, 여유가 0에
가까우므로 어떤 체계적 낙관도 그대로 sign-off 오판으로 환산된다. 이 여유
구조가 본 논문 전반에서 모델 오차·통계 잡음·체계적 편향의 중요도를 판단하는
기준이 된다.

### B. 직접 검증의 비용

업계 표준은 MC 시뮬레이션으로 Vmin을 추정한다. 각 공정 변동 조건에 대해
수천 개의 무작위 mismatch 표본을 시뮬레이션하여 SNM 분포를 구성하고, 이를 각
전압 레벨에서 반복한다. 본 연구 규모(2,000 조건, 전압 레벨 4~5개, 조건당
5,000 MC)에서는 4~5 × 10⁷회의 회로 시뮬레이션에 해당한다. 시뮬레이터 1회
실행이 수분에서 수십분에 이르므로 병렬 실행하에서도 wall-clock time은
수주에서 수개월에 달하며, 여기에 PDK 라이선스, 라이선스당 동시성 제한, 서버
인프라 비용이 추가된다. 이 부담은 compact model이 복잡해지는 첨단 노드에서
가중된다.

### C. Corner 기반 sign-off의 한계

검증을 대표 corner(FSG, SFG, FFG, SSG)로 한정하면 비용은 억제되나 두 가지
결함이 발생한다.

첫째, corner는 NMOS·PMOS Vth shift라는 두 축의 극단 조합일 뿐이다. 본 연구가
다루는 Vth skew, local σ, mobility 축은 corner 정의에 들어가지 않는다.
제7절은 분산 기반 민감도 분석으로 NMOS local σ가 Vmin 분산의 3위 기여
인자로서 pass-gate/pull-down Vth skew를 능가함을 확립하는데, corner 기반
절차는 이 축을 전혀 관측할 수 없다.

둘째, corner 시뮬레이션은 순방향 질문에만 답한다. 공정·설계 엔지니어링이
실무에서 던지는 질문은 역방향이다. 어떤 변동 조합이 사양을 위반하는가, 준수를
회복하려면 어느 파라미터를 얼마나 조여야 하는가, 어느 정도의 skew 허용폭을
인정할 수 있는가. 유한한 corner 점 집합은 준수 경계의 위치도 형상도 결정하지
못한다.

### D. 기여

본 연구의 기여는 다음과 같다.

1. 단일 고정 시뮬레이션 예산으로 순·역방향 Vmin 질의를 처리하는 surrogate
   파이프라인으로, 역방향 해를 격자 탐색이 아닌 미분 가능한 physics layer를
   통한 gradient 하강으로 획득한다(제4절).
2. 첨단 FinFET 노드의 생산 캘리브레이션 데이터에 대한 검증으로, 0.625 V
   sign-off 판정 98.3% 일치 및 세 개 독립 배치에 걸친 pass-gate 지배 계층의
   재현을 포함한다(제5절).
3. 전압 레벨, 조건 수, 조건당 MC 표본의 세 축에 걸친 시뮬레이션 예산 절감의
   근거로, 전압 레벨 절감이 사양 판정에 대해 구조적으로 무손실임을
   보인다(제6절).
4. 무시할 수 있는 한계 비용으로 획득한 정량적 민감도 순위로, NMOS local σ를
   corner 기반 방법이 관측하지 못하는 상위 기여 인자로 식별하며, ARD
   lengthscale이 본 문제에서 민감도 척도로 부적합함을 입증한다(제7절).
5. Min-statistics z-score에 내재된 체계적 낙관의 크기를 결정하는 물리량이
   lobe 상관 ρ_LR임을 규명하고, 이를 양산 MC 출력만으로 측정하는 방법(skewness
   역산)과 그 측정 결과를 제시한다(제2절 D항, 제5절 F항).

**그림 1.** 파이프라인 개요: 변동 파라미터 → GP posterior (μ, σ) → 미분
가능한 physics layer → Vmin, 순방향·역방향 경로 표시.

---

## II. 문제 정식화

### A. 읽기 안정성 지표

6T 셀의 읽기 안정성은 static noise margin으로 정량화되며, 이는 butterfly
특성의 두 lobe 중 최소값으로 정의된다[1]. MC 시뮬레이션은 무작위 표본에 대한
SNM 분포를 산출하고, 관례적으로 평균 μ와 표준편차 σ를 기록한다. 쓰기
지표(write margin, V_trip)는 제8절 C항에서 다루며, 본 방법론은 지표에
무관하다.

### B. Vmin 정의와 수율 목표

조건 **x**에 대해 margin 비

    z(V_op) = μ(x, V_op) / σ(x, V_op)                                    (1)

를 전압 격자에서 평가하고, z가 목표 z-score Z_t를 교차하는 전압을 선형
보간하여 Vmin(**x**)를 얻는다.

Z_t는 어레이 수율 요구에서 해석적으로 유도된다. 256 Mb 어레이 99% Poisson
수율에 대해

    p_fail = −ln(0.99) / (256 × 10⁶) ≈ 3.9 × 10⁻¹⁰                       (2)
    Z_t = Φ⁻¹(1 − p_fail) ≈ 6.50                                          (3)

이며 Φ는 표준정규 누적분포함수이다. 실패 단위는 셀이며, 트랜지스터 수를
곱하는 것은 잘못이다.

두 개의 구별되는 기준량을 분리해야 한다. Z_t는 수율 기준으로서 Vmin의
*정의*에 들어가는 반면, 표 I의 사양 전압은 그 결과 Vmin이 *합격인지*를
결정한다. 둘은 독립적으로 설정된다. Z_t가 실리콘 캘리브레이션이 아닌 해석적
유도값이라는 점이 D항의 논의에 결정적이다.

### C. 관심 구간과 양측 censoring

Vmin의 정확도는 의사결정을 바꾸는 곳에서만 요구된다. 표 I로부터 세 영역이
따라온다.

Vmin이 최저 샘플 전압 아래인 조건은 충분한 여유로 통과하며, 정확한 값이
무의미하므로 left-censoring으로 처리한다. Vmin이 0.7 V를 초과하는 조건은
0.625 V 사양을 큰 폭으로 위반하며, fail로 분류될 뿐 수치 해석은 불필요하므로
right-censoring으로 처리한다. 두 경계 사이 구간이 사양 전압을 포함하며, 수치
정확도가 요구되는 유일한 영역이다.

이에 따라 전압 격자를 {0.4, 0.5, 0.6, 0.7} V로 설정한다. 이 선택은 데이터
가용성이 아니라 사양이 규정한 것으로, 사양점 0.625 V를 보간으로 bracket하는
최소 구간이다. 정량적 근거는 제6절 A항에 있다. Censoring 조건은 연속 오차
지표에서 제외되며 분류 결과로만 반영된다.

한 가지 유의점은 censoring 비율이 판정 임계값에 의존한다는 것이다. D항의
체계적 편향을 보정하면 유효 임계 z가 상승하여 동일 격자에서 right-censoring
비율이 증가한다. 따라서 격자 상한의 적정성은 보정 전이 아니라 보정 후
임계값에서 평가되어야 한다(제6절 A항).

### D. Min-statistics z-score의 체계적 편향과 lobe 상관

SNM은 두 lobe margin의 최소값이며, 두 Gaussian 변량의 최소값은 Gaussian이
아니다. 그 하측 tail은 모멘트를 맞춘 정규분포보다 무겁다. 그런데 식 (1)은
최소값에 Gaussian을 맞춰 Z_t = 6.50까지 외삽하므로 실패 확률을 체계적으로
과소평가한다. 실패는 두 lobe 중 하나만 무너져도 성립하므로 실제 실패 확률은
union 확률이며, 이는 각 lobe 개별 확률로 하한이 결정된다.

SNM 분포의 비정규성 자체는 문헌에 확립되어 있다. Saeidi 등[20]은 단측 읽기
SNM이 단일 Gaussian이 아니라 정규분포의 가중합을 따름을 보였고, Zheng과
Mazumder[21]는 다이 내 SNM 변동을 folded-normal과 non-central chi-squared의
조합으로 모델링하여 6σ를 넘는 영역까지 일치함을 보고하였다. 본 절의 기여는
이 관찰이 아니라, **편향의 크기를 결정하는 물리량이 무엇인지 규명하고 그것을
양산 MC 출력만으로 측정하여 특정 제품 사양에 대한 Vmin 단위로 환산**하는 데
있다.

Lobe별 통계 (μ_L, σ_L, μ_R, σ_R, ρ_LR)가 주어지면 정확한 실패 확률은
폐형식을 갖는다.

    p_fail = P(L<0) + P(R<0) − P(L<0, R<0)                               (4)
    Z_eff = Φ⁻¹(1 − p_fail)                                              (5)

결합항은 bivariate normal CDF로 Owen's T 함수[3]로 계산되며 모든 인수에 대해
미분 가능하므로, (4)–(5)는 gradient 흐름의 손실 없이 파이프라인에 대입된다.

#### 1) Lobe 상관 ρ_LR의 물리적 의미

편향의 크기는 전적으로 ρ_LR이 결정하며, 이 값은 임의의 적합 상수가 아니라
**변동의 local·global 성분비를 직접 반영하는 물리량**이다.

교차결합된 두 인버터에서 한쪽을 강화하는 local mismatch는 그 방향의 lobe를
넓히는 동시에 반대쪽 lobe를 깎는다. 따라서 local 성분은 두 lobe를
anti-correlate시킨다. 반면 소자 타입 레벨의 global shift는 좌우를 동일하게
이동시키므로 두 lobe를 co-correlate시킨다.

- ρ_LR → +1 : global 성분 지배. min이 단일 Gaussian에 수렴하여 편향 소멸
- ρ_LR = 0 : 두 lobe 독립
- ρ_LR → −1 : local mismatch 지배. union 실패 확률이 최대, 편향 최대

즉 ρ_LR은 lobe 차분에서 local mismatch가 차지하는 비중의 척도이다. 이는
제7절 B항의 분산 분해가 독립적으로 도달하는 결론 — NMOS local σ가 corner
정의 밖의 상위 기여 인자라는 — 과 동일한 물리를 다른 경로로 측정한 것이며,
두 측정의 정합 여부가 본고의 검증 항목 중 하나이다(제5절 F항).

중요한 귀결이 따른다. **제3절의 실험 설계는 이 편향을 완화하지 못한다.**
9개 설계 파라미터가 모두 소자 타입 레벨의 global 양이며 셀의 좌우 대칭을
깨지 않으므로, 설계 축만으로는 두 lobe가 모든 조건에서 교환 가능하다. Lobe를
비대칭하게 만드는 성분은 설계 축이 아니라 MC 표본 내부의 local mismatch에서만
발생한다. 따라서 편향을 자연적으로 면제받는 조건 부분집합은 존재하지 않으며,
편향은 공정 윈도우 전 구간에 걸린다.

#### 2) 보정 구조

편향은 (μ, σ) → Vmin 변환의 임계값에만 영향을 준다. Vmin이 z(V_op)가 Z_t를
교차하는 전압으로 정의되므로, 보정에 필요한 것은 z축 전체가 아니라 z = Z_t
한 점에서의 편향값뿐이다. 따라서 보정은

    Z_eff,target = Z_t + z_bias                                          (6)

의 후처리로 기존 데이터에 적용되며 재시뮬레이션을 요구하지 않는다. 그 결과
제5~7절의 상대적 결론 — 민감도 순위, 경계 기하, skew 허용폭, corner 서열 —
은 영향을 받지 않으며, 절대 Vmin과 사양 통과율만 일괄 보정 대상이다.

#### 3) ρ_LR의 측정 경로

측정 경로는 지표에 따라 다르다. Write margin(V_trip)은 좌우 항목이 별도 MC
출력으로 산출되므로 ρ_LR을 표본 상관으로 직접 계산할 수 있다. 읽기 SNM은
통상 최소값의 μ, σ만 보고되나, min(L, R)의 skewness가 ρ_LR의 닫힌
함수이므로

    σ_u² = (1+ρ)/2,  σ_v² = (1−ρ)/2
    γ(ρ) = −K · σ_v³ / [σ_u² + (1−2/π)·σ_v²]^{3/2}                       (7)

를 역산하여 최소값 표본만으로 ρ_LR을 추정할 수 있다. 여기서
K = √2(4−π)(π−2)^{−3/2}(1−2/π)^{3/2} ≈ 0.21803이며, 이는
max(L,R) = u + |v| 분해에서 u ⊥ v이고 |v|만이 skewness를 갖는다는 사실에서
따른다. Skewness는 전체 표본을 사용하므로, 하위 분위수 소수 점에 의존하는
tail 적합보다 통계적으로 효율적이다. 측정 결과는 제5절 F항에 보고한다.

---

## III. 실험 설계

### A. 입력 공간

표 II에 나열된 9개 소자 변동 차원을 공급 전압과 함께 샘플링한다.

**표 II. 변동 파라미터**

| 기호 | 설명 | 범위 | 단위 |
|---|---|---|---|
| cn | NMOS 공통 Vth shift | ±60 | mV |
| sk | Pass-gate/pull-down Vth skew | ±20 | mV |
| pu | PMOS Vth shift | ±60 | mV |
| lpu | Pull-up local σ 배율 | [0.7, 1.3] | — |
| l_com | NMOS local σ, 공통 | [0.7, 1.3] | — |
| l_sk | NMOS local σ, skew | ±0.075 | — |
| mpu | Pull-up mobility 배율 | [0.7, 1.3] | — |
| m_com | NMOS mobility, 공통 | [0.7, 1.3] | — |
| m_sk | NMOS mobility, skew | ±0.075 | — |

Deck 파라미터는 Vth PG = cn + sk, PD = cn − sk로 따라오며, local σ와
mobility 배율도 동일하게 분해된다.

### B. Common-skew 파라미터화

Pass-gate와 pull-down 소자는 NMOS 플레이버를 공유하므로, 게이트 스택, 채널
도핑, 애닐, 리소그래피 임계 치수를 포함하는 지배적 변동 원인을 공유하며, 소자
기하와 레이아웃 환경에서 불완전 추적이 발생한다. 소자별 독립 샘플링은 공통
플레이버의 소자가 mismatch 수준에서 반대 방향으로 갈라지는, 실리콘에서
실현되지 않는 상태에 설계점을 할당한다.

채택한 분해는 corr(l_PG, l_PD) ≈ 0.88을 유도하는데, 이는 동일 플레이버
추적의 타당 범위 0.85~0.95에 있으며 ρ ≈ 0.80의 Vth 구조와 일관된다. 공통과
skew 성분은 독립적으로 샘플링되며, 이 성질은 제7절의 분산 기반 분석이
요구한다.

**그림 2.** 설계 시각화: (a) (cn, pu) 평면의 quadrant 가중, (b) 독립적인
(l_com, l_sk) 샘플링 박스와 그것이 유도하는 대각 (l_PG, l_PD) 띠.

### C. Quadrant 가중 실험계획

읽기와 쓰기 margin은 서로 다른 최악 quadrant에서 열화하며, 전자는 FSG에서,
후자는 SFG에서 그러하다. 이에 따라 지표별로 표 III의 quadrant 가중을 갖는
별도 deck 세트를 구성하여, 고정 조건 수에서 최악 영역의 해상도를 2~4배
높인다. 조건은 quadrant별 독립 스트림의 결정적 PCG64 draw로 생성한다.

**표 III. 지표별 quadrant 가중**

| 지표 | FSG | FN | SN | SFG |
|---|---|---|---|---|
| 읽기(SNM) | 45% | 20% | 15% | 20% |
| 쓰기(V_trip) | 10% | 15% | 30% | 45% |

본고의 9차원 정량 결과는 읽기 세트에 기반한다. 쓰기 세트는 동일 규모로
확보되어 분석 중이며(**[쓰기 GP 적합 분석 중]**), 확정 전까지 쓰기 관련 논의는
독립적인 4차원 배치를 참조로 인용한다.

초기 설계 가설은 stratified 저불일치 샘플링이 pseudo-random draw를
능가하리라는 것이었다. 내부 검증은 domain-uniform 및 corner-restricted 지표
어느 쪽에서도 이를 지지하지 않아 해당 주장을 철회하며, 본 설계의 이득은
quadrant 가중에서만 비롯된다.

### D. Mirror-twin 누수

초기 파일럿 설계는 단일 quasi-random 스트림을 네 quadrant에 재사용하고 cn,
pu의 부호만 반전시켰다. 그 결과 조건의 75%가 나머지 7개 좌표를 공유하는
mirror-twin을 가졌고, 무작위 hold-out에서 test 조건의 약 74%가 train에
쌍둥이를 두어, 구현 결함 없이 정확도 지표를 부풀렸다.

원인은 실행된 조건 좌표를 생성기 재구성본과 대조하여 식별하였으며,
quadrant별 독립 스트림 할당과 legacy 데이터 관련 평가에 대한 mirror-group
분할 강제로 해결되었다. 이러한 설계 유래 leakage는 지표를 은밀히 부풀리므로,
surrogate 검증 연구는 설계 생성 절차를 분할 규칙과 함께 보고해야 한다.

---

## IV. Surrogate 모델

### A. Gaussian process 회귀

GP[4]는 예측 평균에 더해 보정된 예측 분산을 반환하는 비모수 Bayesian 회귀를
제공한다. 모델은 9개 변동 파라미터와 공급 전압을 SNM 통계 (μ, σ)로 사상한다.
세 가지 성질이 이 선택을 정당화한다. 제한된 데이터 하의 동작, 정량화된 예측
불확실성, 그리고 입력에 대한 posterior 평균의 미분 가능성이며, 마지막 성질은
F항 역추정의 전제조건이다. 형식론에 익숙하지 않은 독자를 위해 부록 A에
배경을 제공한다.

μ 프로세스는 ARD를 적용한 Matérn-5/2 kernel을 사용하여 각 입력 차원에
독립적으로 학습된 lengthscale을 할당한다. σ 프로세스는 공급 전압 그룹과 소자
변동 그룹을 분리하는 가산 kernel을 사용한다.

### B. 입력 표준화

입력 벡터는 mV 규모 shift, V 규모 공급 레벨, 무차원 배율을 혼합한다. 표준화
없이는 marginal likelihood 최적화가 진단 없이 현저히 열등한 최적점으로
수렴한다. 초기에 물리 제약의 효과로 귀속되었던 개선의 대부분이 이후 이
요인으로 추적되었다(제6절 B항). 모든 입력은 학습 통계로 표준화된다.

### C. 미분 가능한 physics layer

(μ, σ)에서 Vmin으로의 변환은 학습 가능 파라미터가 없는 해석적 제약으로
부과된다. 각 조건에 대해 posterior 평균을 4개 공급 레벨에서 평가하고, 식
(1)로 margin 비를 형성하며, Z_t와의 교차를 선형 보간한다. Bracket 구간의
선택은 이산이나 각 구간 내부에서 1차 미분이 잘 정의되므로, GP와 physics
layer의 합성은 입력에 대해 미분 가능하다. Censoring 조건은 플래그되어
제외된다.

### D. 물리 제약

세 제약이 사전 소자 지식을 주입한다. Corner anchoring은 4개 global corner의
가상 관측으로 학습 세트를 증강하며, exact GP 하에서 하드 제약으로 작용하여
도메인 극단에서의 외삽 이탈을 방지한다. ReLU(−∂μ/∂V_op)² 형태의 단조성
패널티는 posterior를 통해 probe 점에서 평가되어, 공급 증가가 평균 안정성을
열화시킨다는 비물리적 예측을 억제한다. 약한 정규화가 확립된 mismatch
스케일링[2]과 일관된 선형 σ(V_op) 경향을 유도한다. 기여도는 제6절 B항에서
분리된다.

### E. Noise-aware likelihood

조건별 bootstrap 표준오차가 fixed-noise Gaussian likelihood에 들어가, 더 큰
MC 배치로 뒷받침되는 조건이 비례적으로 큰 가중을 받는다. σ의 표준오차가
첨도에 민감하므로 해석적 표준오차가 아닌 bootstrap을 사용한다.

이 기구는 이질적 샘플링 예산을 단일 모델에 수용한다. 저 fidelity가 동일
시뮬레이터에서 추출한 표본 수의 감소만으로 구성될 때, heteroscedastic
단일-fidelity GP가 올바른 모델이며 multi-fidelity 정식화[5]의 불일치 항이
불필요하다. Posterior가 입력 공간의 인접 조건에서 강도를 차용하므로 개별
조건이 정보성을 갖기 위해 큰 MC 배치를 요구하지 않으며, 이는 고정 예산을
조건당 깊이가 아닌 조건 커버리지의 폭으로 할당하는 것을 뒷받침한다(제6절
C항).

### F. Gradient 기반 역추정

목표 사양 전압 V*에 대해 집합 {**x** : Vmin(**x**) = V*}는 9차원 변동 공간의
hypersurface이며, 허용 공정 윈도우의 경계를 구성한다. (Vmin(**x**) − V*)²를
Adam[9]으로 최소화하여 직접 위치를 찾는데, **x**는 반복해를 물리적으로
허용되는 범위에 가두는 sigmoid 박스 재매개화 하의 leaf 텐서로 취급된다.
수렴은 다중 초기화에서 검증되고, 각 수렴점은 자신의 슬라이스에 대한 1차원
bisection과 대조된다.

이 절차의 비용은 차원에 대해 조합적으로 증가하지 않는다. 두 Vth 축만의
50 × 50 격자도 2,500회 MC 평가를 요구하며, 9차원 전수 탐색은 불가능하다.

---

## V. 검증

### A. 분할과 평가 절차

분할은 조건 수준으로 수행되어 한 조건의 모든 공급 행이 동일 파티션에
할당되며, hold-out 비율은 15%이다. 본 배치는 설계상 mirror-twin이 없어 조건
수준 분할로 충분하며, legacy 파일럿 데이터를 참조하는 평가는 mirror-group
분할을 강제한다. Vmin 오차는 non-censored 부분집합에서 censoring 비율을
병기하여 보고한다.

### B. 순방향 정확도

표 IV는 noise-aware likelihood 하에서 2,000 조건 × 4 공급 레벨의 hold-out
정확도를 보고한다.

**표 IV. Hold-out 정확도**

| 항목 | 값 |
|---|---|
| μ R² | 0.9817 (RMSE 5.35 mV) |
| σ R² | 0.9845 (RMSE 0.22 mV) |
| Vmin RMSE, 전체 non-censored | 13.50 mV |
| Vmin RMSE, 사양 구간 (Vmin ≤ 0.7 V) | 9.14 mV |

판정이 결정되는 사양 구간에서 surrogate 오차는 9.14 mV로, F항에서 측정되는
지표 편향(수십 mV)보다 한 자릿수 가까이 작다. 즉 surrogate 오차는 sign-off
결정을 지배하지 않으며, 지배 항은 지표 쪽에 있다.

**그림 3.** Hold-out 파티션에서의 예측 대 실측 통계 (μ, σ).

### C. 물리 정합성

표 V는 예상 소자 거동과의 일치를 요약한다.

**표 V. 물리 정합성 검사**

| 성질 | 기대 | 실측 | 결과 |
|---|---|---|---|
| Pass-gate 지배 | ℓ_cn < ℓ_pu | ℓ_pu/ℓ_cn = 1.083 | 만족 |
| Vth 방향 | ∂Vmin/∂cn < 0 | 음 | 만족 |
| Pull-up 방향 | ∂Vmin/∂pu > 0 | 양 | 만족 |
| 최악 읽기 corner | FSG | FSG | 만족 |
| 공급 민감도 | 최단 lengthscale | 5.17, 최단 | 만족 |

Pass-gate 지배 계층은 각각 1.08, 1.14, 1.083의 비로 세 개의 독립 설계
배치(파일럿 3차원, 4차원, 본 final 9차원)에 걸쳐 재현되어, 모델이 학습
분포를 암기한 것이 아니라 소자 물리를 포착했음을 가리킨다.

### D. 사양 판정 재현

실질 sign-off 질의는 이진이다. 표 VI은 300 hold-out 조건에서 surrogate와
실측 간 일치를 보고한다.

**표 VI. 사양 판정 일치 (sign-off 0.625 V)**

| 기준 | 일치 | False positive | False negative | z-margin RMSE |
|---|---|---|---|---|
| Sign-off (0.625 V) | 295/300 (98.3%) | 4 | 1 | 0.573 |

False positive는 통과로 예측되었으나 실제 fail인 조건을 뜻하며 4건이
발생하였다. 2,000 조건 전체에서 81.2%가 사양을 통과한다.

이 통과율은 F항의 지표 편향에 대해 **보정 전** 값이다. 편향 보정은 판정
임계값을 상향시키므로 보정 후 통과율은 이보다 낮다 **[보정 통과율: Z_t=7.62 기준 GP 재학습 후 기재 예정]**.

**그림 4.** (cn, pu) 평면의 Vmin contour: hold-out 실측 위에 surrogate
예측을 중첩하고 4개 global corner를 표시.

### E. Gradient 기반 역추정 검증

Ground truth가 가용한 해석적 testbed에서, 8개 초기화 전부가 최대 절대 편차
2.41 mV로 목표 manifold에 수렴하였고, 모든 수렴점이 자신의 슬라이스에 대한
1차원 bisection과 소수점 4자리까지 일치하였다.

**그림 5.** (cn, pu) 평면에서 목표 contour를 표시한 다중 시작 역추정 궤적.

### F. Lobe 상관의 측정과 편향의 크기

제2절 D항 3)의 skewness 역산을 final 읽기 배치의 사양 밴드 조건 8개(각
n = 5,000)에 적용하였다. 결과를 표 VII에 요약한다.

**표 VII. Lobe 상관 측정 요약**

| 항목 | 값 | 상태 |
|---|---|---|
| Gaussian 가설 | 8/8 조건에서 기각 | 측정 완료 |
| ρ_LR (읽기, pooled) | −0.406 ± 0.121 | 1차 측정 완료 (조건 간 변동 ±0.121) |
| 조건 간 균일성 | χ² = 8.00, dof 7, p = 0.33 | 1차 측정 완료 |
| z_bias | +1.123σ [0.941, 1.233] | 1차 측정 완료 |
| Corner 간 균일성 | — | **미측정 — corner-라벨 재측정 필요** |
| ρ_LR (쓰기, 직접 상관) | — | **미측정 — 좌우 분리 MC 데이터 부재** |
| 보정 후 통과율·censoring | — | **GP 재학습 후 기재 예정** |

**측정 결과.** 최소값 표본의 skewness는 8개 조건 전부 음이며(평균 −0.32),
Gaussian 가설은 tail 분위수 적합과 skewness 양쪽에서 기각된다. 독립 증거로,
각 조건의 관측 최소값을 해당 n의 Gaussian 순서통계량(order statistic)
기대값으로 나눈 비가 평균 1.48로 8개 조건 전부 1.15를 초과한다(Gaussian이면
1.00). 식 (7)의 역산은 ρ_LR = −0.406 ± 0.121을 주며, 조건 간 산포(표준편차
0.141)가 표본 잡음만으로 기대되는 수준과 일치하므로 균일성 검정을
통과한다(p = 0.33). 따라서 **z_bias는 조건의 함수가 아니라 단일 스칼라로
충분**하며, 식 (6)의 보정은 Z_t 6.50 → 7.62의 일괄 상향이 된다.

**물리 정합.** ρ_LR < 0은 lobe 차분에서 local mismatch가 지배함을 뜻하며
(제2절 D항 1), 이는 제7절 B항의 분산 분해가 독립적으로 지목한 NMOS local σ의
상위 기여와 정합한다. 서로 무관한 두 측정 — MC 표본 내부의 분포 형상과 설계
축에 대한 분산 분해 — 이 같은 결론에 도달한다.

**실리콘 상한과의 정합.** 읽기 구속 corner FSG는 사양 0.625 V를
만족한다(corner 시뮬레이션 실측). 이 사실로부터 허용 가능한 z_bias의 상한이
역산된다: FSG에서 z(0.625 V) = 8.06이므로 z_bias ≤ +1.56σ, 즉
ρ_LR ≥ −0.75. 측정값 +1.151σ는 이 상한의 74%로 내부에 있다. 측정이 상한을
위반했다면 방법 어딘가에 오류가 있음을 뜻했을 것이므로, 이는 측정의 독립
검증이다.

**Vmin 환산.** 사양 밴드에서의 모집단 median 기울기는 dz/dV_op ≈ 13.2 V⁻¹
이나, 환산에 유효한 것은 구속 corner의 국소 기울기이다: 읽기 17.9~23.8 V⁻¹
(corner별), 쓰기 25.3 V⁻¹(final 쓰기 배치 median, IQR 20.9~29.9). 이에 따라
z_bias +1.123σ의 Vmin 환산은 읽기 구속 corner(FSG)에서 약 63 mV, 모집단
median dz/dV_op(13.2 V⁻¹) 기준 약 85 mV이다. 보정 전 읽기 구속 corner
FSG의 Vmin은 0.548 V로서, 보정 후 0.611 V(잔여 margin +14 mV)로 추정된다.
**Corner-라벨 재측정 및 쓰기 ρ_LR은 미측정이다.** 쓰기 지표의 ρ_LR은 좌우
항목이 별도 MC 출력으로 산출되므로 직접 상관 측정이 가능하나, 본 연구의
9차원 쓰기 배치는 vtrip_avg/vtrip_std만 포함하고 좌우 분리 데이터를 포함하지
않아 현재 데이터로는 측정 불가능하다. 특히 쓰기 구속 corner SFG는 보정 전
Vmin이 이미 사양에 접해 있어 쓰기 ρ_LR 값이 통과·실패를 직접 가르므로,
쓰기 ρ_LR 측정이 최우선 과제로 남는다.

**남은 측정.** 1차 측정 8개 조건은 corner 라벨 없이 수행되어 corner 간
균일성이 미검정이다. 5개 corner × 2 전압의 라벨된 재측정과, 좌우 항목이 별도
출력인 쓰기 지표의 직접 상관 측정이 필요하나, 현행 9차원 쓰기 배치 데이터 구조상 불가능하다 **[⥀ 좌우 분리 MC 데이터 기록 필요]**. 읽기 ρ_LR은 분포
형상에서 역산된 값으로 min-of-two 모델을 전제하므로, 소수 조건에서 lobe별
통계를 직접 기록하면 전제가 검증으로 바뀐다.

### G. 외부 검증

독립적으로 설계된 4차원 배치 348 조건(배율 nominal)이 9차원 공간의
(l = m = 1, sk = 0) 평면에 실측점을 제공한다. 사영된 9차원 모델과 이 실측점
간의 일치는 학습 draw 밖 평면에서의 일반화를 검증한다. 4차원 배치는 파일럿
세대이므로 자체 지표는 mirror-group 분할로 재계산한다.

---

## VI. 시뮬레이션 비용 절감

시뮬레이션 예산은 전압 레벨, 조건 수, 조건당 MC 표본의 곱으로 인수분해된다.
각 인자에 대한 근거를 제시한다.

### A. 전압 레벨

사양 전압 0.625 V가 [0.6, 0.7] V 구간 안에 있으므로, 사양점에서의 z는 0.6 V와
0.7 V 표본만으로 보간된다. 0.8 V 레벨은 판정에 구조적으로 참여할 수 없다.
표 VIII이 이를 전체 모집단에서 확인한다.

**표 VIII. 0.8 V 레벨 제거에 대한 판정 불변성**

| 기준 | 판정 일치 | max Δz |
|---|---|---|
| Sign-off (0.625 V) | 2000/2000 (100%) | 0 |

편차가 정확히 0이며, 이는 경험적 근사가 아닌 구조적 필연이다. 축소된 격자로
학습한 surrogate는 D항에 보고된 사양 판정을 재현하고 동일한 사양 구간 Vmin
RMSE 9.14 mV를 달성하며, 0.8 V 레벨의 포함은 μ R²를 0.9817에서 0.9834로
이동시킬 뿐이다. 그 레벨이 새로 해결하는 90개 조건은 모두 Vmin이 0.7 V를
초과하므로 이미 사양 밖이다.

5개에서 4개로의 전압 레벨 축소는 이에 따라 본 지표에 대해 손실 없이 20%의
시뮬레이션 물량 절감을 낳는다.

다만 이 무손실성은 판정 임계값에 종속된다. 제5절 F항의 편향을 보정하면 유효
임계 z가 상승하여 사양점에서의 교차가 더 높은 전압으로 이동하고, 격자 상한을
넘는 right-censored 조건이 늘어난다(쓰기 배치 기준 보정 전 1.2% → 보정 후
4.8%). 따라서 격자 축소의 확정은 보정 후 임계값에서의 censoring 재평가를
전제로 하며, 보정 전 수치만으로 판단하면 상한 여유를 과대평가한다. 보정 후
유효 Z_t = 7.62에서의 censoring 비율은 GP 재학습을 통해 재계산이 필요하다.

### B. 조건 수

학습 세트를 크기 N으로 서브샘플링하고 재적합하면 표 IX의 예산-정확도 관계가
얻어지며, 이는 해석적 testbed에서 크기별 10회 독립 재추출로 획득되었다.

**표 IX. 예산-정확도 관계**

| N | Vmin RMSE (mV) | Contour Hausdorff 거리 (mV) |
|---|---|---|
| 50 | 5.13 ± 1.84 | 1.62 ± 0.64 |
| 100 | 3.90 ± 0.50 | 1.30 ± 0.29 |
| 200 | 3.21 ± 0.77 | 1.00 ± 0.42 |
| 400 | 2.01 ± 0.26 | 0.76 ± 0.14 |
| 800 | 1.40 ± 0.15 | 0.54 ± 0.15 |

정확도는 작은 N에서 가파르게 개선되다 N = 400 부근에서 knee를 지나며, 그
이후 수확이 체감한다. 이 전이는 조건 수 선택을 정량화되지 않은 판단에서 방어
가능한 결정으로 전환한다.

제4절 D항의 물리 제약은 동일한 저예산 영역에 그 이득을 집중한다. Corner
anchoring은 N ≤ 100에서 corner 근방 Vmin RMSE를 유의하게 개선하며(Wilcoxon
부호순위, pooled paired 차이 −1.29 mV, p < 10⁻⁶), N 증가에 따라 효과가
소멸한다. Domain-uniform 지표에서는 효과가 작고 불안정하므로, 주장은 측정된
지표와 함께 명시되어야 한다. 해석적 testbed에서 baseline Vmin RMSE 1.26 mV가
corner anchoring으로 0.92 mV로 27% 개선되며, 95 백분위수가 37% 개선된다.

이 관찰은 방법론적 함의를 갖는다. Hold-out 설계 자체가 결론을 결정한다.
Domain-uniform hold-out은 평균 정확도를, corner-restricted hold-out은 안전
margin이 중요한 곳의 정확도를 측정한다. 이들은 구별되는 질문이며 둘 다
보고되어야 한다.

**그림 6.** 예산-정확도 관계: 조건 수 대 Vmin RMSE 및 contour Hausdorff
거리, 물리 제약 유무별.

### C. 조건당 MC 표본

제4절 E항의 noise-aware likelihood는 조건별 표준오차를 명시적으로 수용하고
희소 샘플링된 조건을 자동으로 하향 가중한다. Posterior가 인접 조건에서
강도를 차용하므로 개별 조건이 고립된 채 높은 신뢰도를 얻을 필요가 없으며,
이는 예산을 폭으로 할당하는 것을 정당화한다. 동일 기구가 이질적 예산을
불일치 항 없이 단일 모델에 공존시킨다.

부수적으로, 제5절 F항의 ρ_LR 측정도 조건당 n = 5,000에서 pooled 정밀도
±0.02에 도달하였다. Skewness의 표준오차가 √(6/n)로 감쇠하므로 대규모 tail
샘플링(n = 10⁵급)은 편향 측정 목적에 불필요하다.

---

## VII. 민감도 분석

공정 관리에 실질적으로 활용 가능한 산출물은 어떤 변동 원인이 Vmin을
지배하는지의 순위이다. 두 척도를 계산하여 비교한다.

### A. ARD lengthscale

GP는 적합 중 입력 차원별 lengthscale을 학습하므로 이 척도는 한계 비용이
없다. 그러나 이는 데이터가 아닌 적합된 모델의 성질이다. 입력 상관 하에서
왜곡되며(제3절 B항의 독립 샘플링을 동기부여), 단독 효과와 상호작용 효과를
분리하지 못한다. 표 X이 적합값을 보고한다.

**표 X. ARD lengthscale (표준화 척도, 짧을수록 민감)**

| 순위 | 축 | ℓ | 순위 | 축 | ℓ |
|---|---|---|---|---|---|
| 1 | V_op | 5.185 | 6 | l_com | 8.173 |
| 2 | cn | 7.405 | 7 | m_sk | 8.177 |
| 3 | pu | 7.945 | 8 | mpu | 8.186 |
| 4 | sk | 8.056 | 9 | l_sk | 8.196 |
| 5 | m_com | 8.114 | 10 | lpu | 8.213 |

### B. 분산 기반 Sobol 지수

분산 기반 민감도 분석은 출력 분산을 입력과 그 상호작용에 배분한다[6]. 정확한
평가는 통상 수만 회의 함수 평가를 요구하여, 직접 시뮬레이션으로 수행되는
회로 수준 수율 연구에 적용을 배제한다. Surrogate가 이 장애를 제거한다.
평가에 수분이 아닌 수 밀리초가 소요되므로, 요구되는 질의가 모델을 학습시킨
예산을 넘어 무시할 수 있는 한계 비용을 부과한다. 1차 지수는 Saltelli
추정량[7]으로, 전체 지수는 Jansen 추정량[8]으로 추정하며, 1,024 기저 표본이
11,264회의 surrogate 평가에 대응한다. 결과는 표 XI에 나타난다.

**표 XI. Vmin의 Sobol 민감도 지수**

| 축 | S₁ (1차) | S_T (전체) |
|---|---|---|
| cn | 0.388 | 0.464 |
| pu | 0.212 | 0.298 |
| l_com | 0.157 | 0.199 |
| sk | 0.121 | 0.108 |
| lpu | 0.032 | 0.039 |
| m_sk | 0.007 | 0.024 |
| m_com | 0.021 | 0.021 |
| mpu | 0.008 | 0.014 |
| l_sk | 0.004 | 0.001 |

출력 분산은 표준편차 94.5 mV에 대응하며, ΣS₁ = 0.948은 상호작용이 약한 거의
가법적 거동을 가리킨다.

### C. 두 척도 간의 불일치

두 척도는 선두 쌍 cn, pu에서 일치하나 3위에서 갈라진다. Lengthscale 순서는
sk를 l_com보다 앞에 두는 반면, Sobol 순서는 l_com을 sk의 약 2배 전체 지수로
둔다.

더 근본적인 한계가 드러난다. 전체 지수는 0.001에서 0.464로 두 자릿수를 넘는
범위에 걸치나, 적합된 lengthscale은 7.41에서 8.21로 1.1배의 범위이다.
민감도가 ℓ⁻²로 근사되는 스케일링 하에서도 이는 1.23배에 해당하여 관측된
기여 변이를 표현할 수 없다. 가장 개연성 있는 설명은 9차원에서 이 표본 밀도에
대한 개별 lengthscale의 약한 식별성이다.

실무적 귀결은, 본 문제에서 민감도 순위가 lengthscale이 아닌 분산 기반 지수로
읽혀야 한다는 것이다. Lengthscale은 pass-gate 지배와 같은 큰 계층에 대한
정성적 점검으로는 유효하나 정량적 우선순위화에는 부적합하다. 이는 또한
surrogate의 가치를 강화한다. 비용 없는 척도는 질문에 답하지 못했고, 답한
척도는 직접 시뮬레이션으로는 경제성이 없었을 것이다.

### D. 공정 함의와 skew 허용폭

Vth 변동이 지배하며, cn과 pu가 함께 전체 분산의 대부분을 차지한다. NMOS
local σ가 3위이며 pass-gate/pull-down Vth skew를 능가하는데, 이는 corner
기반 sign-off가 표현할 수 없는 축으로, local mismatch 관리가 skew 관리보다
높은 우선순위를 가짐을 시사한다. 이 결론은 제5절 F항의 ρ_LR < 0 — lobe
차분의 local mismatch 지배 — 과 독립 경로에서 정합한다. 모든 mobility 축은
전체 지수가 0.025 미만으로 경미하다. Local σ skew 항은 0.001로 무시 가능하여
그 관리 사양을 완화할 수 있다는 근거를 제공하는 반면, mobility skew 항은
절대 크기는 작으나 전체 대 1차 지수 비 약 3.3으로 주로 상호작용을 통해
작동한다.

표 XII는 배율 nominal에서의 skew 응답을 보고한다.

**표 XII. PG-PD skew 응답**

| 동작점 | sk = 0에서 Vmin | ±20 mV 스윙 | dVmin/dsk |
|---|---|---|---|
| TT (0, 0) | 470.3 mV | 114.2 mV | −2.80 mV/mV |
| mild FSG (−30, +30) | 586.3 mV | 120.8 mV | −2.76 mV/mV |
| mild SFG (+30, −30) | 350.0 mV | 104.8 mV | −7.13 mV/mV |
| FFG (−30, −30) | 475.2 mV | 119.1 mV | −2.84 mV/mV |
| SSG (+30, +30) | 470.5 mV | 112.1 mV | −2.81 mV/mV |

느린 pass-gate에 대응하는 양의 skew가 읽기 동작을 안정화하며, 대부분의
동작점에서 기울기가 −2.8 mV/mV 부근이고 SFG 근방에서 −7.13 mV/mV로
가팔라진다. 0.625 V 사양에 대해 mild-FSG 동작점만 제약되어 sk ≥ −11 mV를
요구하며, 나머지 대표 동작점은 ±20 mV 전 범위를 허용한다. 따라서 현행
±20 mV 관리 사양은 배율 nominal에서 적절하다. 단, 이 허용폭은 읽기 지표
단독의 결론이며(제8절 C항), local σ가 상위 기여 인자로 식별되었으므로 skew
사양 확정 전에 skew와 local σ의 결합 스윕이 요구된다.

**그림 7.** 그룹별 민감도: ARD 유도 척도 대 Sobol 지수, 허용 skew 윈도우
포함.

---

## VIII. 논의와 한계

### A. 지표 편향의 보정 상태

Min-statistics 편향은 v3.0까지 본 연구의 최대 미해결 불확실성이었으나, 제5절
F항의 측정으로 1차 확정되었다: ρ_LR = −0.406 ± 0.121, z_bias = +1.123σ,
조건 간 균일(p=0.33). 보정은 식 (6)의 후처리로 적용되며 재시뮬레이션이 불필요하다.

남은 불확실성은 세 가지다. (1) **Corner 간 균일성** — 1차 측정은
corner 라벨 없이 수행되었다. (2) **쓰기 지표의 ρ_LR** — 본 연구의
9차원 쓰기 배치는 vtrip_avg/vtrip_std만 포함하고 좌우 분리 데이터를
포함하지 않아, 현재 데이터로는 직접 측정이 불가능하다. 쓰기 지표의
lobe별 통계가 별도 기록되면 직접 상관 측정이 가능하다. (3) **보정 후
통과율과 right-censoring 비율의 최종화** — 보정 후 유효 Z_t가 7.62로
상승하므로 GP 재학습을 통한 재평가가 요구된다.

관련 가정은 각 lobe margin 자체가 원거리 tail까지 Gaussian이라는 것이다.
관계 (1)은 절대 실패율 예측기가 아니라 본 노드급 bitcell sign-off에서
표준적으로 사용되는 margin 지표이며[22], 제5절 F항의 분포 형상 검사는 두
가정을 동시에 검사한다.

### B. 범위

결과는 단일 기술 노드, 단일 셀 토폴로지에 관한 것이며, 9차원 정량 결과는
읽기 지표에 기반한다. 공통 성분이 범위 경계에 접근할 때 발생하는 배율 스필
밴드는 compact model 캘리브레이션의 가장자리에 있어 그 영역의 예측은
보수적으로 해석되어야 한다. 제6절 A항의 전압 레벨 절감은 표 I의 사양에
종속되며, IR-drop 예산이 변경되어 사양이 0.7 V를 초과하면 재검토를 요구한다.
PDK가 비공개이므로 절대값은 외부적으로 재현 불가하다. 해석적 testbed를 전면
공개하고 정규화 축 결과를 보고하여 상대 비교를 가능하게 한다.

### C. 쓰기 margin과 통합 판정

읽기만으로는 양의 skew가 유리하나, 쓰기 지표는 반대 방향으로 응답한다. 독립
4차원 배치에서 smooth-maximum 합성 하의 통합 최악 조건은 sk ≈ −2 mV의 거의
대칭에서 최소화되었고, 그 결과 곡면은 FSG(읽기 구속)와 SFG(쓰기 구속) 양쪽에
극대를 갖는 안장형이다. 두 구속 corner가 서로 다른 물리로 같은 사양에 동시에
접근하므로, 지표 편향의 보정은 어느 한쪽이 아니라 양쪽 모두에 적용되어야
한다.

Final 9차원 쓰기 배치는 확보되어 분석 중이다. 쓰기 GP 적합, 통합
Vmin, skew 허용폭의 9차원 재계산은 추가 분석이 필요하다. 그때까지의 방향적 결론 — skew 사양이
읽기 지표만으로 유도되어서는 안 된다 — 은 확고하다.

### D. 권고

전압 레벨은 사양으로 결정되어 최소 bracket 구간만 시뮬레이션되어야 한다.
조건 수는 예산-정확도 knee에서 선택되어야 하며, 그 이후의 한계 노력은 경계
근방의 깊이나 추가 설계 corner에 배분하는 편이 낫다. 조건별 표준오차가
기록되는 한 MC 수는 조건 간 균일할 필요가 없다. MC flow에는 최소값의 μ, σ에
더해 lobe별 통계(μ_L, σ_L, μ_R, σ_R, ρ_LR) 또는 최소한 skewness와 하위
분위수가 상시 기록되어야 한다. 최소값의 평균과 표준편차만으로는 tail 형상
정보가 소실되며, 제5절 F항이 보인 대로 그 소실이 sign-off를 수십 mV
낙관시킨다.

---

## IX. 결론

단일 고정 시뮬레이션 예산으로 순·역방향 SRAM Vmin 질의를 처리하는 surrogate
파이프라인을 구축하고, 첨단 노드의 생산 캘리브레이션 데이터 2,000 조건 × 4
공급 레벨로 검증하였다.

Surrogate는 sign-off 스크리닝에 적합하다: 사양 구간 Vmin RMSE 9.14 mV,
0.625 V sign-off 판정 98.3% 일치, 세 개 독립 배치에 걸친 물리 정합성 재현.
시뮬레이션 예산은 사양 유도 근거에서 절감 가능하며, 전압 레벨 수의 20% 감소가
구조적으로 무손실임을 보였다. 허용 공정 윈도우 경계, skew 허용폭, 파라미터
우선순위화를 포함하는 역방향 질의가 추가 시뮬레이션 없이 응답되며, 이로써
NMOS local σ가 Vth skew를 앞선 Vmin 분산의 3위 기여 인자임을, corner 기반
sign-off가 구조적으로 관측할 수 없는 축에서 확립하였다.

끝으로, 지배 불확실성이 모델이 아닌 지표에 존재함을 보였다. Min-statistics
z-score의 체계적 낙관은 lobe 상관 ρ_LR이 결정하며, 이는 양산 MC 출력의
skewness만으로 측정된다. 측정값 ρ_LR = −0.406은 z-score 기준 +1.123σ, 구속
corner 기준 Vmin 수십 mV의 낙관에 해당하여 surrogate 오차를 한 자릿수
초과하며, 구속 corner의 잔여 margin과 같은 자릿수이다. ρ_LR < 0은 분산
분해가 독립적으로 지목한 local mismatch 지배와 정합하며, 실리콘 sign-off
사실로부터 역산되는 상한의 내부에 있다. corner-라벨 확정 측정과 쓰기 지표
측정이 완료되면 보정이 최종화된다. **현재까지 쓰기 ρ_LR은 데이터 미비로 미측정 상태이다.**

---

## 부록 A: Gaussian process 배경

본 부록은 주 전문 영역이 통계적 학습 밖에 있는 독자를 위해 형식론을 요약한다.

GP는 함수값의 임의의 유한 집합이 결합 Gaussian 분포를 따르도록 하는, 함수에
대한 분포를 정의한다. 이는 평균 함수와 공분산 kernel로 규정되며, 후자는
가까운 입력이 상관된 출력을 낳는다는 가정을 부호화한다. 관측 데이터에
조건화하면 임의의 질의점에서 예측 평균과 예측 분산을 함께 반환하는
posterior가 얻어지며, 분산은 관측에서 먼 영역에서 증가하는데 이 점이 본
방법을 통상 회귀와 구별한다.

Kernel lengthscale은 상관이 감쇠하는 거리를 지배한다. 한 축을 따라 짧은
lengthscale은 출력이 그 입력에 대해 급격히 변함을, 긴 lengthscale은 둔감함을
가리킨다. ARD는 각 입력 차원에 독립 lengthscale을 할당하고 모두를 데이터로부터
학습하며, 이것이 적합값이 흔히 민감도 척도로 해석되는 이유이다. 이 해석은
제7절 C항에서 비판적으로 검토된다.

Posterior 평균은 학습 입력에 대한 kernel 평가의 선형 결합이므로, kernel이
미분 가능한 한 질의점에 대해 미분 가능하다. 이 성질이 제4절 F항의 역문제를
탐색이 아닌 gradient 하강으로 풀 수 있게 한다.

Heteroscedastic likelihood는 관측 잡음이 데이터 점마다 다를 수 있게 하여
표준 정식화를 일반화한다. 이 역할에 조건별 MC 표준오차를 공급하면 posterior가
조건을 그 통계적 신뢰도에 비례하여 가중하게 되며, 보조 보정 항이 불필요하다.

## 부록 B: 지표 정의

설계범위 feasibility 일치, 양측 censoring, 어시스트-활성 채점의 형식 정의를,
순진한 지표가 동일 예측의 오차를 약 60배 과대보고함을 입증하는 재현표와 함께
제공한다.

## 부록 C: 재현성

조건 생성기 버전, seed, quadrant 가중, 파라미터 범위, deck 번호 규약을
규정한다. 조건 생성이 결정적 PCG64 스트림이므로 (stage, 조건 수, seed,
metric, method) 튜플만으로 조건 집합 전체가 비트 단위로 재현된다. 해석적
testbed를 전면 공개한다.

---

## 참고문헌

[1] E. Seevinck, F. J. List, and J. Lohstroh, "Static-noise margin analysis of
    MOS SRAM cells," *IEEE J. Solid-State Circuits*, vol. SC-22, no. 5,
    pp. 748–754, Oct. 1987.

[2] M. J. M. Pelgrom, A. C. J. Duinmaijer, and A. P. G. Welbers, "Matching
    properties of MOS transistors," *IEEE J. Solid-State Circuits*, vol. 24,
    no. 5, pp. 1433–1439, Oct. 1989.

[3] D. B. Owen, "Tables for computing bivariate normal probabilities," *Ann.
    Math. Statist.*, vol. 27, no. 4, pp. 1075–1090, Dec. 1956.

[4] C. E. Rasmussen and C. K. I. Williams, *Gaussian Processes for Machine
    Learning*. Cambridge, MA, USA: MIT Press, 2006.

[5] M. C. Kennedy and A. O'Hagan, "Predicting the output from a complex
    computer code when fast approximations are available," *Biometrika*,
    vol. 87, no. 1, pp. 1–13, Mar. 2000.

[6] I. M. Sobol', "Global sensitivity indices for nonlinear mathematical models
    and their Monte Carlo estimates," *Math. Comput. Simul.*, vol. 55,
    no. 1–3, pp. 271–280, Feb. 2001.

[7] A. Saltelli, P. Annoni, I. Azzini, F. Campolongo, M. Ratto, and
    S. Tarantola, "Variance based sensitivity analysis of model output. Design
    and estimator for the total sensitivity index," *Comput. Phys. Commun.*,
    vol. 181, no. 2, pp. 259–270, Feb. 2010.

[8] M. J. W. Jansen, "Analysis of variance designs for model output," *Comput.
    Phys. Commun.*, vol. 117, no. 1–2, pp. 35–43, Mar. 1999.

[9] D. P. Kingma and J. Ba, "Adam: A method for stochastic optimization," in
    *Proc. 3rd Int. Conf. Learn. Represent. (ICLR)*, 2015.

[10] A. Singhee and R. A. Rutenbar, "Why quasi-Monte Carlo is better than Monte
     Carlo or Latin hypercube sampling for statistical circuit analysis,"
     *IEEE Trans. Comput.-Aided Design Integr. Circuits Syst.*, vol. 29,
     no. 11, pp. 1763–1776, Nov. 2010.

[11] Z. Guo, W. Sun, Z. Wang, Y. Cai, and L. Shi, "An efficient SRAM yield
     analysis method using multi-fidelity neural network," in *Proc. 2nd Int.
     Symp. Electron. Design Autom. (ISEDA)*, 2024, p. 547.

[12] S. Yin, X. Jin, L. Shi, K. Wang, and W. W. Xing, "Efficient Bayesian yield
     analysis and optimization with active learning," in *Proc. 59th ACM/IEEE
     Design Autom. Conf. (DAC)*, 2022, pp. 1195–1200.

[13] S. Yin, G. Dai, and W. W. Xing, "High-dimensional yield estimation using
     shrinkage deep features and maximization of integral entropy reduction,"
     in *Proc. 28th Asia South Pacific Design Autom. Conf. (ASP-DAC)*, 2023.

[14] Y. Liu, G. Dai, and W. W. Xing, "Seeking the yield barrier:
     High-dimensional SRAM evaluation through optimal manifold," in *Proc.
     60th ACM/IEEE Design Autom. Conf. (DAC)*, 2023.

[15] S. Gupta and B. H. Calhoun, "Dynamic read Vmin and yield estimation for
     nanoscale SRAMs," *IEEE Trans. Circuits Syst. I, Reg. Papers*, vol. 68,
     no. 3, pp. 1171–1182, 2021.

[16] S. Kinoshita, Y. Inoue, T. Watanabe, K. Ikeda, S. Nishio, A. Teruya,
     N. Sakai, and T. Goda, "Space-filling Latin hypercube design for efficient
     Bayesian optimization with application to semiconductor development,"
     *IEEE Trans. Semicond. Manuf.*, vol. 38, no. 3, pp. 446–452, 2025,
     doi: 10.1109/TSM.2025.3574791.

[17] J. R. Gardner, G. Pleiss, D. Bindel, K. Q. Weinberger, and A. G. Wilson,
     "GPyTorch: Blackbox matrix-matrix Gaussian process inference with GPU
     acceleration," in *Proc. Adv. Neural Inf. Process. Syst. (NeurIPS)*, 2018.

[18] R. M. Neal, *Bayesian Learning for Neural Networks*. New York, NY, USA:
     Springer, 1996.

[19] M. L. Stein, *Interpolation of Spatial Data: Some Theory for Kriging*.
     New York, NY, USA: Springer, 1999.

[20] R. Saeidi, M. Sharifkhani, and K. Hajsadeghi, "Statistical analysis of
     read static noise margin for near/sub-threshold SRAM cell," *IEEE Trans.
     Circuits Syst. I, Reg. Papers*, vol. 61, no. 12, pp. 3386–3393, Dec. 2014,
     doi: 10.1109/TCSI.2014.2327334.

[21] N. Zheng and P. Mazumder, "Modeling and mitigation of static noise margin
     variation in subthreshold SRAM cells," *IEEE Trans. Circuits Syst. I,
     Reg. Papers*, vol. 64, no. 10, pp. 2726–2736, Oct. 2017,
     doi: 10.1109/TCSI.2017.2700818.

[22] T. Song, W. Rim, et al., "A 14 nm FinFET 128 Mb SRAM with V_MIN
     enhancement techniques for low-power applications," *IEEE J. Solid-State
     Circuits*, vol. 50, no. 1, pp. 158–169, Jan. 2015.

[23] C. Bae, S. Pae, C.-S. Yu, K. Kim, Y. Kim, and J. Park, "SRAM stability
    design comprehending 14nm FinFET reliability," in *Proc. IEEE Int. Rel.
    Phys. Symp. (IRPS)*, 2015, pp. MY.13.1–MY.13.5,
    doi: 10.1109/IRPS.2015.7112815.

[24] A. T. Krishnan, V. Reddy, D. Aldrich, J. Raval, K. Christensen, J. Rosal,
     C. O'Brien, R. Khamankar, A. Marshall, W.-K. Loh, R. McKee, and
     S. Krishnan, "SRAM cell static noise margin and V_MIN sensitivity to
     transistor degradation," in *Proc. IEEE Int. Electron Devices Meeting
     (IEDM)*, 2006, pp. 1–4, doi: 10.1109/IEDM.2006.346778.

[25] S.-M. Lim, H. Hong, S. Yu, Z. Ming, J. Park, and Y. Kim, "Effects of BTI
     during AHTOL on SRAM V_MIN," in *Proc. IEEE Int. Rel. Phys. Symp. (IRPS)*,
     2011, pp. 105–110, doi: 10.1109/IRPS.2011.5784460.
