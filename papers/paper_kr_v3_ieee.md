# 9차원 공정 윈도우 전 구간에서의 순·역방향 SRAM Vmin 추정을 위한 물리 제약 가우시안 프로세스 대리모델

**사내 기술 보고서 — IEEE 논문 형식, v3.0, 2026년 7월**

---

## 초록

SRAM 어레이의 최소 동작 전압(Vmin)은 공정 변동 윈도우 전 구간에 대해 제품
사양으로 sign-off되어야 하나, 요구되는 tail 수율을 직접 Monte Carlo(MC)로
검증하는 것은 계산 비용이 과도하며, 코너 기반 sign-off는 코너 정의 밖의 변동
축을 표현하지 못한다. 본 연구는 단일 고정 시뮬레이션 예산으로 순방향과 역방향
Vmin 질의를 모두 처리하는 대리모델 파이프라인을 제시한다. 가우시안 프로세스
(GP)가 9개 공정 변동 파라미터로부터 정적 잡음 여유(SNM) 통계를 회귀하고,
미분 가능한 물리 계층이 이 통계를 학습된 근사가 아닌 해석적 제약으로서
수율 기준 Vmin으로 변환한다. 합성 함수가 입력에 대해 미분 가능하므로, 목표
Vmin 경계 위의 점을 격자 탐색 없이 gradient 하강으로 직접 획득한다.
조건별 MC 표준오차로 구동되는 heteroscedastic 우도는 이질적 샘플링 예산을
단일 모델에 수용한다. 본 방법은 첨단 FinFET 노드의 생산 캘리브레이션 데이터
2,000 조건 × 4 전압으로 검증되었다. Hold-out 정확도는 평균에서 R²=0.982,
표준편차에서 0.985에 도달하고, 사양 관련 구간에서 Vmin RMSE 9.14 mV,
end-of-life 기준에서 사양 판정 일치율 99.3%를 달성한다. 대리모델로 비로소
경제성이 확보된 분산 기반 민감도 분석은 NMOS local-sigma가 Vmin 분산의 3위
기여 인자로서 pass-gate/pull-down 문턱 skew를 앞서며 어떤 코너 정의도 포괄하지
못하는 축임을 식별한다. 또한 기존 전압 격자의 최상위 레벨이 사양 판정에
구조적으로 무관함을 보여 손실 없이 시뮬레이션 물량을 20% 절감할 수 있음을
밝힌다. 끝으로, 기존 최소값 통계 z-score에 내재된 체계적 낙관을 Vmin 기준
53~144 mV로 정량화하는데, 이는 time-zero부터 end-of-life까지의 마진 예산
전체에 비견되며, 이를 해소할 저비용 진단 프로토콜을 제시한다.

**색인어** — SRAM, 최소 동작 전압, 공정 변동, 가우시안 프로세스, 대리모델,
역문제, 수율 해석, 민감도 분석, 정적 잡음 여유.

---

## I. 서론

### A. 사양 맥락

SRAM은 현대 시스템온칩에서 최대 면적을 차지하며 칩 수율을 지배한다. 본
연구 대상 공정의 nominal 공급 전압은 0.75 V이다. On-chip 및 off-chip IR
drop을 반영하면 셀에 실제 인가되는 전압이 표 I의 Vmin 사양을 규정한다.

**표 I. Vmin 사양**

| 기준 | Vmin 사양 | 근거 |
|---|---|---|
| Time-zero (T0) | 0.625 V | 초기 특성 |
| End-of-life (EOL) | 0.675 V | 열화 반영, 구속 기준 |

두 기준을 가르는 50 mV는 BTI(bias-temperature instability)에 대한 가드밴드로,
BTI가 SRAM의 static noise margin과 Vmin에 미치는 영향은 실험적으로
확립되어 있으며[24], [25] 본 노드급의 신뢰성 고려 안정성 설계에 반영되어
있다[23]. EOL 시험을 매 로트마다 반복할 수 없으므로 이 가드밴드는 실리콘에서
경험적으로 고정되어 time-zero 사양에 적용되며, 본 연구의 모든 평가도 그에
따라 time-zero 기준이다.

이 50 mV가 설계가 사용할 수 있는 마진 예산 전부이다. 이 값은 본 논문
전반에서 모델 오차·통계 잡음·체계적 편향을 비교하는 기준자로 반복
사용된다. 따라서 핵심 질문은 Vmin의 수치 자체가 아니라, 주어진 공정
조건이 0.675 V를 만족하는가, 그렇지 못하다면 어느 정도 미달하는가이다.

### B. 직접 검증의 비용

업계 표준은 MC 시뮬레이션으로 Vmin을 추정한다. 각 공정 변동 조건에 대해
수천 개의 무작위 트랜지스터를 시뮬레이션하여 SNM 분포를 구성하고 이를 각
전압 레벨에서 반복한다. 본 연구 규모(2,000 조건, 5 전압, 조건당 5,000 MC)
에서는 5×10⁷회의 회로 시뮬레이션에 해당한다. PrimeSim 1회가 수분에서
수십분에 이르므로, 병렬 실행하에서도 wall-clock time은 수주에서 수개월에
달하며, 여기에 PDK 라이선스, 라이선스당 동시성 제한, 서버 인프라 비용이
추가된다. 이 부담은 compact model이 복잡해지는 첨단 노드에서 가중된다.

### C. 코너 기반 sign-off의 한계

검증을 대표 코너(FSG, SFG, FFG, SSG)로 한정하면 비용은 억제되나 두 가지
결함이 발생한다.

첫째, 코너는 NMOS 및 PMOS 문턱 시프트라는 두 축의 극단 조합일 뿐이다.
본 연구가 다루는 문턱 skew, local-sigma, 이동도 축은 코너 정의에 들어가지
않는다. 제7절은 분산 기반 민감도 분석으로 NMOS local-sigma가 Vmin 분산의
3위 기여 인자로서 pass-gate/pull-down 문턱 skew를 능가함을 확립하는데,
코너 기반 절차는 이 축을 전혀 관측할 수 없다.

둘째, 코너 시뮬레이션은 순방향 질문에만 답한다. 공정·설계 엔지니어링이
실무에서 던지는 질문은 역방향이다. 어떤 변동 조합이 사양을 위반하는가,
준수를 회복하려면 어느 파라미터를 얼마나 조여야 하는가, 어느 정도의 skew
허용폭을 인정할 수 있는가. 유한한 코너 점 집합은 준수 경계의 위치도
형상도 결정하지 못한다.

### D. 기여

본 연구의 기여는 다음과 같다.

1. 단일 고정 시뮬레이션 예산으로 순·역방향 Vmin 질의를 처리하는 대리모델
   파이프라인으로, 역방향 해를 격자 탐색이 아닌 미분 가능 물리 계층을 통한
   gradient 하강으로 획득한다(제4절).
2. 첨단 FinFET 노드의 생산 캘리브레이션 데이터에 대한 검증으로, 사양 판정
   99.3% 일치 및 세 개 독립 배치에 걸친 pass-gate 지배 계층의 재현을
   포함한다(제5절).
3. 전압 레벨, 조건 수, 조건당 MC 표본의 세 축에 걸친 시뮬레이션 예산 절감의
   근거로, 전압 레벨 절감이 사양 판정에 대해 구조적으로 무손실임을
   보인다(제6절).
4. 무시할 수 있는 한계 비용으로 획득한 정량적 민감도 순위로, NMOS
   local-sigma를 코너 기반 방법이 관측하지 못하는 1차 기여 인자로 식별하며,
   ARD lengthscale이 본 문제에서 민감도 척도로 부적합함을 입증한다(제7절).
5. 기존 최소값 통계 z-score에 내재된, 마진 예산 전체에 비견되는 체계적
   낙관의 정량화와, 이를 해소할 저비용 진단 프로토콜(제2절 D항).

**그림 1.** 파이프라인 개요: 변동 파라미터 → GP 사후 (μ, σ) → 미분 가능
물리 계층 → Vmin, 순방향·역방향 경로 표시.

---

## II. 문제 정식화

### A. 읽기 안정성 지표

6T 셀의 읽기 안정성은 정적 잡음 여유로 정량화되며, 이는 버터플라이 특성의
두 lobe 중 최소값으로 정의된다[1]. MC 시뮬레이션은 무작위 표본에 대한 SNM
분포를 산출하고, 관례적으로 평균 μ와 표준편차 σ를 기록한다. 쓰기 지표는
제8절 C항에서 다루며, 본 방법론은 지표에 무관하다.

### B. Vmin 정의와 수율 목표

조건 **x**에 대해 마진비

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
결정한다. 둘은 독립적으로 설정된다. Z_t가 실리콘 캘리브레이션이 아닌
해석적 유도값이라는 점이 제2절 D항의 논의에 결정적이다.

### C. 관심 구간과 양측 censoring

Vmin의 정확도는 의사결정을 바꾸는 곳에서만 요구된다. 표 I로부터 세 영역이
따라온다.

Vmin이 최저 샘플 전압 아래인 조건은 충분한 여유로 통과하며, 정확한 값이
무의미하므로 좌측 censoring으로 처리한다. Vmin이 0.7 V를 초과하는 조건은
EOL 기준을 큰 폭으로 위반하며, fail로 분류될 뿐 수치 해석은 불필요하므로
우측 censoring으로 처리한다. 두 경계 사이 구간이 두 사양 전압을 모두
포함하며, 수치 정확도가 요구되는 유일한 영역이다.

이에 따라 전압 격자를 {0.4, 0.5, 0.6, 0.7} V로 설정한다. 이 선택은 데이터
가용성이 아니라 사양이 규정한 것으로, 두 사양 점을 모두 bracket하는 최소
구간이다. 0.7 V 상한은 최대 허용 절감치이자 사양이 허용하는 최소치이니,
0.675 V의 EOL 기준을 보간으로 bracket하려면 그 위의 표본이 필요하기
때문이다. 정량적 근거는 제6절 A항에 있다. Censoring 조건은 연속 오차
지표에서 제외되며 분류 결과로만 반영된다.

### D. 최소값 통계 z-score의 체계적 편향

SNM은 두 lobe 여유의 최소값이며, 두 가우시안 변량의 최소값은 가우시안이
아니다. 그 하측 tail은 모멘트를 맞춘 정규분포보다 무겁다. 그런데 식 (1)은
최소값에 가우시안을 맞춰 Z_t=6.50까지 외삽하므로 실패 확률을 체계적으로
과소평가한다. 실패는 두 lobe 중 하나만 무너져도 성립하므로, 실제 실패
확률은 union 확률이며 이는 각 lobe 개별 확률로 하한이 결정된다.

SNM 분포의 비정규성은 문헌에 이미 확립되어 있으며 본 데이터에 국한된
현상이 아니다. Saeidi 등[20]은 단측 읽기 SNM이 단일 가우시안이 아니라
정규분포의 가중합을 따름을 보였고, Zheng과 Mazumder[21]는 다이 내 SNM
변동을 folded-normal 분포와 non-central chi-squared 분포의 조합으로
모델링하여 6-sigma를 넘는 영역까지 일치함을 보고하였다. 본 절의 기여는
이 관찰 자체가 아니라, 그것을 특정 제품 사양에 대한 **Vmin 단위로
정량화**하고 양산 데이터에서 판정할 저비용 프로토콜을 함께 제시하는
데 있다.

lobe별 통계 (μ_L, σ_L, μ_R, σ_R, ρ_LR)가 주어지면 정확한 실패 확률은
폐형식을 갖는다.

    p_fail = P(L<0) + P(R<0) − P(L<0, R<0)                               (4)
    Z_eff = Φ⁻¹(1 − p_fail)                                              (5)

여기서 결합항은 이변량 정규 누적분포함수로 Owen's T 함수[3]로 계산되며 모든
인수에 대해 미분 가능하므로, (4)–(5)를 gradient 흐름 손실 없이 파이프라인에
대입할 수 있다.

편향의 크기는 lobe 상관 ρ_LR에 의존하여, 독립 lobe에서 +0.7σ, 역상관에서
+1.9σ에 이른다. 표 II는 사양 밴드의 실측 기울기 dz/dV_op ≈ 13.2 V⁻¹로
이를 Vmin으로 환산한다.

**표 II. 최소값 통계 편향의 영향**

| 가정 | z 편향 | Vmin 낙관량 | EOL 통과율 |
|---|---|---|---|
| 편향 없음 | 0 | — | 88.5% |
| 독립 lobe | +0.7σ | 53 mV | 80.5% |
| 역상관 lobe | +1.9σ | 144 mV | 63.0% |

가장 유리한 가정에서도 유발 오차 53 mV가 표 I의 마진 예산 50 mV 전체를
초과한다. 제5절 B항에서 확립되는 대리모델 Vmin 정확도 9.14 mV와 비교하면,
지배 오차는 모델이 아니라 지표에 존재할 수 있다.

제3절의 설계는 이를 완화하지 못한다. 9개 파라미터가 모두 소자 타입 레벨의
전역량이며 셀의 좌우 대칭을 깨지 않으니, 좌·우 pass-gate가 동일하게
시프트되기 때문이다. 따라서 두 lobe는 모든 조건에서 교환 가능하며, 이는
최소값 통계 편향이 최대가 되는 구성이다. 자연적으로 비대칭이어서 면제되는
조건 부분집합은 존재하지 않는다.

본 배치의 MC 출력은 최소값의 μ와 σ만 포함하므로 (4)–(5)를 적용할 수 없었다.
본고의 모든 결과는 관행에 따라 식 (1)을 사용한다. 편향의 크기를 실증적으로
해소하기 위해, 사양 경계 근방 조건에 대한 tail 형상 진단을 규정하였다. 이는
10⁵ MC 표본에서 분포 형상을 측정하여 가우시안과 최소값-2가우시안 모델을
판별한다. 편향은 (μ, σ)→Vmin 변환의 임계값에만 영향을 주므로, 그 보정은
Z_t → Z_t + z_bias의 후처리로 기존 데이터에 적용되며 추가 시뮬레이션이
불필요하다. 따라서 제5~7절의 상대적 결론 — 민감도 순위, 경계 기하, skew
허용폭, 코너 서열 — 은 영향을 받지 않으며, 절대 Vmin 값과 사양 통과율만
일괄 보정 대상이다.

---

## III. 실험 설계

### A. 입력 공간

표 III에 나열된 9개 소자 변동 차원을 공급 전압과 함께 샘플링한다.

**표 III. 변동 파라미터**

| 기호 | 설명 | 범위 | 단위 |
|---|---|---|---|
| cn | NMOS 공통 문턱 시프트 | ±60 | mV |
| sk | Pass-gate/pull-down 문턱 skew | ±20 | mV |
| pu | PMOS 문턱 시프트 | ±60 | mV |
| lpu | Pull-up local-sigma 배율 | [0.7, 1.3] | — |
| l_com | NMOS local-sigma, 공통 | [0.7, 1.3] | — |
| l_sk | NMOS local-sigma, skew | ±0.075 | — |
| mpu | Pull-up 이동도 배율 | [0.7, 1.3] | — |
| m_com | NMOS 이동도, 공통 | [0.7, 1.3] | — |
| m_sk | NMOS 이동도, skew | ±0.075 | — |

Deck 파라미터는 문턱 PG = cn + sk, PD = cn − sk로 따라오며, local-sigma와
이동도 배율도 동일하게 분해된다.

### B. 공통-skew 파라미터화

Pass-gate와 pull-down 소자는 NMOS 플레이버를 공유하므로, 게이트 스택, 채널
도핑, 애닐, 리소그래피 임계 치수를 포함하는 지배적 변동 원인을 공유하며,
소자 기하와 레이아웃 환경에서 불완전 추적이 발생한다. 소자별 독립 샘플링은
공통 플레이버의 소자가 mismatch 수준에서 반대 방향으로 갈라지는, 실리콘에서
실현되지 않는 상태에 설계점을 할당한다.

채택한 분해는 corr(l_PG, l_PD) ≈ 0.88을 유도하는데, 이는 동일 플레이버
추적의 타당 범위 0.85~0.95에 있으며 ρ ≈ 0.80의 문턱 구조와 일관된다. 공통과
skew 성분은 독립적으로 샘플링되며, 이 성질은 제7절의 분산 기반 분석이
요구한다.

**그림 2.** 설계 시각화: (a) (cn, pu) 평면의 사분면 가중, (b) 독립적인
(l_com, l_sk) 샘플링 박스와 그것이 유도하는 대각 (l_PG, l_PD) 띠.

### C. 사분면 가중 실험계획

읽기와 쓰기 여유는 서로 다른 최악 사분면에서 열화하며, 전자는 FSG에서,
후자는 SFG에서 그러하다. 이에 따라 지표별로 표 IV의 사분면 가중을 갖는 별도
deck 세트를 구성하여, 고정 조건 수에서 최악 영역의 해상도를 2~4배 높인다.
조건은 사분면별 독립 스트림의 결정적 PCG64 draw로 생성한다.

**표 IV. 지표별 사분면 가중**

| 지표 | FSG | FN | SN | SFG |
|---|---|---|---|---|
| 읽기(SNM) | 45% | 20% | 15% | 20% |
| 쓰기(Vtrip) | 10% | 15% | 30% | 45% |

두 deck 세트 모두 설계·생성되었다. 본고 작성 시점에 결과 전사가 완료된 것은
읽기 세트뿐이며, 쓰기 세트 결과는 전사가 진행 중으로 제7절 D항과 제8절 C항에서
독립적인 4차원 배치를 참조로만 인용한다.

초기 설계 가설은 stratified 저불일치 샘플링이 유사난수 draw를 능가하리라는
것이었다. 내부 검증은 domain-uniform 및 corner-restricted 지표 어느 쪽에서도
이를 지지하지 않아 해당 주장을 철회하며, 본 설계의 이득은 사분면 가중에서만
비롯된다.

### D. 전사 없는 프로토콜

시뮬레이션은 netlist도 raw 결과도 반출할 수 없는 시설 내에서 실행된다. 조건
생성이 결정적이므로, (stage, 조건 수, seed, metric, method) 튜플의 전송만으로
시설 측 deck 루프와 모델 측 조건표가 비트 단위로 동일해진다. 결과는 전압
레벨과 deck 인덱스로만 라벨링되어 반환되며, 조건 좌표는 수기로 전사되지
않는다. 조건을 수기 전사한 파일럿에서 행 오류율은 약 9%였다. 이 프로토콜은
편의가 아니라 데이터 무결성 요구사항이다.

결과값의 전사는 그럼에도 남는다. 자동 범위 기반 품질 관리가 본 배치에서
자릿수 오류 22건을 검출했으며, 그중 3건은 파싱 불가, 19건은 크기가 물리적으로
비현실적이었다. 이러한 값은 대리모델을 파국적으로 열화시켜 보정 전 hold-out
R²를 −0.41로 떨어뜨리므로, 물리 기반 범위 검사를 파서에 상시 유지할 것을
권고한다.

### E. Mirror-twin 누수

초기 파일럿 설계는 단일 준난수 스트림을 네 사분면에 재사용하고 cn, pu의
부호만 반전시켰다. 그 결과 조건의 75%가 나머지 7개 좌표를 공유하는
mirror-twin을 가졌고, 무작위 hold-out에서 test 조건의 약 74%가 train에
쌍둥이를 두어, 구현 결함 없이 정확도 지표를 부풀렸다.

원인은 전사된 조건과 재구성된 생성기의 포렌식 대조로 식별되었으며, 사분면별
독립 스트림 할당과 legacy 데이터 관련 평가에 대한 mirror-group 분할 강제로
해결되었다. 이러한 설계 유래 누수는 지표를 은밀히 부풀리므로, 대리모델 검증
연구는 설계 생성 절차를 분할 규칙과 함께 보고해야 한다.

---

## IV. 대리모델

### A. 가우시안 프로세스 회귀

가우시안 프로세스[4]는 예측 평균에 더해 보정된 예측 분산을 반환하는
비모수 Bayesian 회귀를 제공한다. 모델은 9개 변동 파라미터와 공급 전압을 SNM
통계 (μ, σ)로 사상한다. 세 가지 성질이 이 선택을 정당화한다. 제한된 데이터
하의 동작, 정량화된 예측 불확실성, 그리고 입력에 대한 사후 평균의 미분
가능성이며, 마지막 성질은 제4절 F항의 역추정의 전제조건이다. 형식론에
익숙하지 않은 독자를 위해 부록 A에 배경을 제공한다.

평균 프로세스는 자동 관련성 결정(ARD)을 적용한 Matérn-5/2 커널을 사용하여,
각 입력 차원에 독립적으로 학습된 lengthscale을 할당한다. 표준편차 프로세스는
공급 전압 그룹과 소자 변동 그룹을 분리하는 가산 커널을 사용한다.

### B. 입력 표준화

입력 벡터는 mV 규모 시프트, V 규모 공급 레벨, 무차원 배율을 혼합한다.
표준화 없이는 주변 우도 최적화가 진단 없이 현저히 열등한 최적점으로
수렴한다. 초기에 물리 제약의 효과로 귀속되었던 개선의 대부분이 이후 이
요인으로 추적되었으며, 제6절 B항에 보고한다. 모든 입력은 학습 통계로
표준화된다.

### C. 미분 가능 물리 계층

(μ, σ)에서 Vmin으로의 변환은 학습 가능 파라미터가 없는 해석적 제약으로
부과된다. 각 조건에 대해 사후 평균을 4개 공급 레벨에서 평가하고, 식 (1)로
마진비를 형성하며, Z_t와의 교차를 선형 보간한다. Bracket 구간의 선택은
이산이나 각 구간 내부에서 1차 미분이 잘 정의되므로, GP와 물리 계층의 합성은
입력에 대해 미분 가능하다. Censoring 조건은 플래그되어 제외된다.

### D. 물리 제약

세 제약이 사전 소자 지식을 주입한다. Corner anchoring은 4개 전역 코너의 가상
관측으로 학습 세트를 증강하며, exact GP 하에서 하드 제약으로 작용하여 도메인
극단에서의 외삽 이탈을 방지한다. ReLU(−∂μ/∂V_op)² 형태의 단조성 패널티는
사후를 통해 probe 점에서 평가되어, 공급 증가가 평균 안정성을 열화시킨다는
비물리적 예측을 억제한다. 약한 정규화가 확립된 mismatch 스케일링[2]과 일관된
선형 σ(V_op) 경향을 유도한다. 기여도는 제6절 B항에서 분리된다.

### E. 잡음 인지 우도

조건별 부트스트랩 표준오차가 고정 잡음 가우시안 우도에 들어가, 더 큰 MC
배치로 뒷받침되는 조건이 비례적으로 큰 가중을 받는다. σ의 표준오차가 첨도에
민감하므로 해석적 표준오차가 아닌 부트스트랩을 사용한다.

이 기구는 이질적 샘플링 예산을 단일 모델에 수용한다. 저 fidelity가 동일
시뮬레이터에서 추출한 표본 수의 감소만으로 구성될 때, heteroscedastic
단일-fidelity GP가 올바른 모델이며 다중-fidelity 정식화[5]의 불일치 항이
불필요하다. 사후가 입력 공간의 인접 조건에서 강도를 차용하므로 개별 조건이
정보성을 갖기 위해 큰 MC 배치를 요구하지 않으며, 이는 고정 예산을 조건당
깊이가 아닌 조건 커버리지의 폭으로 할당하는 것을 뒷받침한다. 제6절 C항에서
정량화한다.

### F. Gradient 기반 역추정

목표 사양 전압 V*에 대해 집합 {**x** : Vmin(**x**) = V*}는 9차원 변동
공간의 초곡면이며, 허용 공정 윈도우의 경계를 구성한다. 이는 **x**에 대해
(Vmin(**x**) − V*)²를 Adam[9]으로 최소화하여 직접 위치를 찾는데, **x**는
반복해를 물리적으로 허용되는 범위에 가두는 sigmoid 박스 재매개화 하의 leaf
텐서로 취급된다. 수렴은 다중 초기화에서 검증되고, 각 수렴점은 자신의
슬라이스에 대한 1차원 bisection과 대조된다.

이 절차의 비용은 차원에 대해 조합적으로 증가하지 않는다. 두 문턱 축만의
50 × 50 격자도 2,500회 MC 평가를 요구하며, 9차원 전수 탐색은 불가능하다.

---

## V. 검증

### A. 프로토콜

분할은 조건 수준으로 수행되어 한 조건의 모든 공급 행이 동일 파티션에 할당되며,
hold-out 비율은 15%이다. 본 배치는 설계상 mirror-twin이 없어 조건 수준 분할로
충분하며, legacy 파일럿 데이터를 참조하는 평가는 mirror-group 분할을 강제한다.
Vmin 오차는 non-censored 부분집합에서 censoring 비율을 병기하여 보고한다.

### B. 순방향 정확도

표 V는 잡음 인지 우도 하에서 2,000 조건 4 공급 레벨의 hold-out 정확도를
보고한다.

**표 V. HOLD-OUT 정확도**

| 항목 | 값 |
|---|---|
| μ 결정계수 | 0.9817 (RMSE 5.35 mV) |
| σ 결정계수 | 0.9845 (RMSE 0.22 mV) |
| Vmin RMSE, 전체 non-censored | 13.50 mV |
| Vmin RMSE, 사양 구간 (Vmin ≤ 0.7 V) | 9.14 mV |

판정이 결정되는 사양 구간에서 오차 9.14 mV는 마진 예산 50 mV의 약 1/5로,
대리모델 오차가 sign-off 결정을 지배하지 않는다. 제2절 D항의 체계적 편향은
별개의 더 큰 양이다.

**그림 3.** Hold-out 파티션에서의 예측 대 실측 통계 (μ, σ).

### C. 물리 정합성

표 VI은 예상 소자 거동과의 일치를 요약한다.

**표 VI. 물리 정합성 검사**

| 성질 | 기대 | 실측 | 결과 |
|---|---|---|---|
| Pass-gate 지배 | ℓ_cn < ℓ_pu | ℓ_pu/ℓ_cn = 1.083 | 만족 |
| 문턱 방향 | ∂Vmin/∂cn < 0 | 음 | 만족 |
| Pull-up 방향 | ∂Vmin/∂pu > 0 | 양 | 만족 |
| 최악 읽기 코너 | FSG | FSG | 만족 |
| 공급 민감도 | 최단 lengthscale | 5.17, 최단 | 만족 |

Pass-gate 지배 계층은 각각 1.08, 1.14, 1.083의 비로 세 개의 독립 설계 배치에
걸쳐 재현되어, 모델이 학습 분포를 암기한 것이 아니라 소자 물리를 포착했음을
가리킨다.

### D. 사양 판정 재현

실질 sign-off 질의는 이진이다. 표 VII은 300 hold-out 조건에서 대리모델과
실측 간 일치를 보고한다.

**표 VII. 사양 판정 일치**

| 기준 | 일치 | False positive | False negative | z-마진 RMSE |
|---|---|---|---|---|
| T0 (0.625 V) | 295/300 (98.3%) | 4 | 1 | 0.573 |
| EOL (0.675 V) | 298/300 (99.3%) | 1 | 1 | 0.322 |

False positive는 통과로 예측되었으나 실제 fail인 조건을 뜻한다. 구속 기준인
EOL에서 그러한 경우가 1건 발생하여, 대리모델을 sign-off 스크리닝에 사용하는
것을 뒷받침한다. 2,000 조건 전체에서 81.2%가 T0를, 88.5%가 EOL을 통과하며
11.4%가 EOL에 실패한다. 이 비율은 제2절 D항에서 논의한 일괄 보정 대상이다.

**그림 4.** (cn, pu) 평면의 Vmin 등고선: hold-out 실측 위에 대리모델 예측을
중첩하고 4개 전역 코너를 표시.

### E. Gradient 기반 역추정

ground truth가 가용한 해석적 testbed에서, 8개 초기화 전부가 최대 절대 편차
2.41 mV로 목표 manifold에 수렴하였고, 모든 수렴점이 자신의 슬라이스에 대한
1차원 bisection과 소수점 4자리까지 일치하였다.

**그림 5.** (cn, pu) 평면에서 목표 등고선을 표시한 다중 시작 역추정 궤적.

### F. 외부 검증

독립적으로 설계된 4차원 배치 348 조건(배율 nominal)이 9차원 공간의
(l = m = 1, skew = 0) 평면에 실측점을 제공한다. 사영된 9차원 모델과 이
실측점 간의 일치는 학습 draw 밖 평면에서의 일반화를 검증한다. 4차원 배치는
파일럿 세대이므로 자체 지표는 mirror-group 분할로 재계산한다.

---

## VI. 시뮬레이션 비용 절감

시뮬레이션 예산은 전압 레벨, 조건 수, 조건당 MC 표본의 곱으로 인수분해된다.
각 인자에 대한 근거를 제시한다.

### A. 전압 레벨

두 사양 전압이 모두 [0.6, 0.7] V 구간 안에 있으므로, 각 사양 점에서의 z는
0.6 V와 0.7 V 표본만으로 보간된다. 0.8 V 레벨은 판정에 구조적으로 참여할 수
없다. 표 VIII이 이를 전체 모집단에서 확인한다.

**표 VIII. 0.8 V 레벨 제거에 대한 판정 불변성**

| 기준 | 판정 일치 | max |Δz| |
|---|---|---|
| T0 (0.625 V) | 2000/2000 (100%) | 0.00 × 10⁰ |
| EOL (0.675 V) | 2000/2000 (100%) | 0.00 × 10⁰ |

편차가 정확히 0이며, 이는 경험적 근사가 아닌 구조적 필연을 반영한다. 축소된
격자로 학습한 대리모델은 제5절 D항에 보고된 사양 판정을 재현하고 동일한
사양 구간 Vmin RMSE 9.14 mV를 달성하며, 0.8 V 레벨의 포함은 평균 결정계수를
0.9817에서 0.9834로 이동시킬 뿐이다. 그 레벨이 새로 해결하는 90개 조건은
모두 Vmin이 0.7 V를 초과하므로 이미 EOL 기준 밖이다.

5개에서 4개로의 전압 레벨 축소는 이에 따라 본 지표에 대해 손실 없이 20%의
시뮬레이션 물량 절감을 낳는다. 0.7 V 상한은 절감의 하한이며 추가 압축의
목표가 아니다.

### B. 조건 수

학습 세트를 크기 N으로 서브샘플링하고 재적합하면 표 IX의 예산-정확도 관계가
얻어지며, 이는 해석적 testbed에서 크기별 10회 독립 재추출로 획득되었다.

**표 IX. 예산-정확도 관계**

| N | Vmin RMSE (mV) | 등고선 Hausdorff 거리 (mV) |
|---|---|---|
| 50 | 5.13 ± 1.84 | 1.62 ± 0.64 |
| 100 | 3.90 ± 0.50 | 1.30 ± 0.29 |
| 200 | 3.21 ± 0.77 | 1.00 ± 0.42 |
| 400 | 2.01 ± 0.26 | 0.76 ± 0.14 |
| 800 | 1.40 ± 0.15 | 0.54 ± 0.15 |

정확도는 작은 N에서 가파르게 개선되다 N = 400 부근에서 무릎을 지나며, 그
이후 수확이 체감한다. 이 전이는 조건 수 선택을 정량화되지 않은 판단에서
방어 가능한 결정으로 전환한다.

제4절 D항의 물리 제약은 동일한 저예산 영역에 그 이득을 집중한다. Corner
anchoring은 N ≤ 100에서 corner 근방 Vmin RMSE를 유의하게 개선하며, Wilcoxon
부호순위 검정에서 pooled paired 차이 −1.29 mV, p < 10⁻⁶이고, N 증가에 따라
효과가 소멸한다. Domain-uniform 지표에서는 효과가 작고 불안정하므로, 주장은
측정된 지표와 함께 명시되어야 한다. 해석적 testbed에서 baseline Vmin RMSE
1.26 mV가 corner anchoring으로 0.92 mV로 27% 개선되며, 95 백분위수가 37%
개선된다.

이 관찰은 방법론적 함의를 갖는다. Hold-out 설계 자체가 결론을 결정한다.
Domain-uniform hold-out은 평균 정확도를, corner-restricted hold-out은 안전
마진이 중요한 곳의 정확도를 측정한다. 이들은 구별되는 질문이며 둘 다
보고되어야 한다.

**그림 6.** 예산-정확도 관계: 조건 수 대 Vmin RMSE 및 등고선 Hausdorff 거리,
물리 제약 유무별.

### C. 조건당 MC 표본

제4절 E항의 잡음 인지 우도는 조건별 표준오차를 명시적으로 수용하고 희소
샘플링된 조건을 자동으로 하향 가중한다. 사후가 인접 조건에서 강도를
차용하므로 개별 조건이 고립된 채 높은 신뢰도를 얻을 필요가 없으며, 이는
예산을 폭으로 할당하는 것을 정당화한다. 동일 기구가 이질적 예산을 불일치 항
없이 단일 모델에 공존시킨다.

---

## VII. 민감도 분석

공정 관리에 실질적으로 활용 가능한 산출물은 어떤 변동 원인이 Vmin을 지배하는지의
순위이다. 두 척도를 계산하여 비교한다.

### A. ARD Lengthscale

GP는 적합 중 입력 차원별 lengthscale을 학습하므로 이 척도는 한계 비용이 없다.
그러나 이는 데이터가 아닌 적합된 모델의 성질이다. 입력 상관 하에서 왜곡되며,
이는 제3절 B항의 독립 샘플링을 동기부여하고, 단독 효과와 상호작용 효과를
분리하지 못한다. 표 X이 적합값을 보고한다.

**표 X. ARD LENGTHSCALE (표준화 척도, 짧을수록 민감)**

| 순위 | 축 | ℓ | 순위 | 축 | ℓ |
|---|---|---|---|---|---|
| 1 | V_op | 5.185 | 6 | l_com | 8.173 |
| 2 | cn | 7.405 | 7 | m_sk | 8.177 |
| 3 | pu | 7.945 | 8 | mpu | 8.186 |
| 4 | sk | 8.056 | 9 | l_sk | 8.196 |
| 5 | m_com | 8.114 | 10 | lpu | 8.213 |

### B. 분산 기반 Sobol 지수

분산 기반 민감도 분석은 출력 분산을 입력과 그 상호작용에 배분한다. 정확한
평가는 통상 수만 회의 함수 평가를 요구하여, 직접 시뮬레이션으로 수행되는
회로 수준 수율 연구에 적용을 배제한다. 대리모델이 이 장애를 제거한다. 평가에
수분이 아닌 수 밀리초가 소요되므로, 요구되는 질의가 모델을 학습시킨 예산을
넘어 무시할 수 있는 한계 비용을 부과한다. 1차 지수는 Saltelli 추정량[7]으로,
전체 지수는 Jansen 추정량[8]으로 추정하며, 1,024 기저 표본이 11,264회의
대리모델 평가에 대응한다. 결과는 표 XI에 나타난다.

**표 XI. Vmin의 SOBOL 민감도 지수**

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
범위에 걸치나, 적합된 lengthscale은 7.41에서 8.21로 1.1의 범위이다. 민감도가
ℓ⁻²로 근사되는 스케일링 하에서도 이는 1.23배에 해당하여 관측된 기여 변이를
표현할 수 없다. 가장 개연성 있는 설명은 9차원에서 이 표본 밀도에 대한 개별
lengthscale의 약한 식별성이다.

실무적 귀결은, 본 문제에서 민감도 순위가 lengthscale이 아닌 분산 기반 지수로
읽혀야 한다는 것이다. Lengthscale은 pass-gate 지배와 같은 큰 계층에 대한
정성적 점검으로는 유효하나 정량적 우선순위화에는 부적합하다. 이는 또한
대리모델의 가치를 강화한다. 비용 없는 척도는 질문에 답하지 못했고, 답한
척도는 직접 시뮬레이션으로는 경제성이 없었을 것이다.

### D. 공정 함의와 skew 허용폭

문턱 변동이 지배하며, cn과 pu가 함께 전체 분산의 대부분을 차지한다. NMOS
local-sigma가 3위이며 pass-gate/pull-down 문턱 skew를 능가하는데, 이는 코너
기반 sign-off가 표현할 수 없는 축으로, 국소 mismatch 관리가 skew 관리보다
높은 우선순위를 가짐을 시사한다. 모든 이동도 축은 전체 지수가 0.025 미만으로
경미하다. Local-sigma skew 항은 0.001로 무시 가능하여 그 관리 사양을 완화할
수 있다는 근거를 제공하는 반면, 이동도 skew 항은 절대 크기는 작으나 전체 대
1차 지수 비 약 3.3으로 주로 상호작용을 통해 작동한다.

표 XII는 배율 nominal에서의 skew 응답을 보고한다.

**표 XII. PG-PD SKEW 응답**

| 동작점 | sk = 0에서 Vmin | ±20 mV 스윙 | dVmin/dsk |
|---|---|---|---|
| TT (0, 0) | 470.3 mV | 114.2 mV | −2.80 mV/mV |
| mild FSG (−30, +30) | 586.3 mV | 120.8 mV | −2.76 mV/mV |
| mild SFG (+30, −30) | 350.0 mV | 104.8 mV | −7.13 mV/mV |
| FFG (−30, −30) | 475.2 mV | 119.1 mV | −2.84 mV/mV |
| SSG (+30, +30) | 470.5 mV | 112.1 mV | −2.81 mV/mV |

느린 pass-gate에 대응하는 양의 skew가 읽기 동작을 안정화하며, 대부분의
동작점에서 기울기가 −2.8 mV/mV 부근이고 SFG 근방에서 −7.13 mV/mV로 가팔라진다.
사양에 대해, 모든 대표 동작점이 EOL 기준에서 ±20 mV 전 범위를 허용하며,
더 엄격한 T0 기준에서만 mild-FSG 점이 제약되어 sk ≥ −11 mV를 요구한다. 따라서
현행 ±20 mV 관리 사양은 배율 nominal에서 적절하다. Local-sigma가 위에서 1차
기여 인자로 식별되었으므로, skew 사양 확정 전에 skew와 local-sigma의 결합
스윕이 요구된다.

**그림 7.** 그룹별 민감도: ARD 유도 척도 대 Sobol 지수, 허용 skew 윈도우
포함.

---

## VIII. 논의와 한계

### A. 주요 한계

제2절 D항의 체계적 낙관이 본 연구의 최대 미해결 불확실성을 구성한다. Vmin
기준 53~144 mV의 추정 크기는 마진 예산 전체에 비견되며 대리모델 오차를 6~16배
초과한다. 따라서 본고에 보고된 절대 Vmin 값과 사양 통과율은 보정 전 양이다.
제2절 D항에 규정된 진단은 이를 전체 시뮬레이션 예산의 2% 미만으로 해소하며,
보정은 재시뮬레이션을 요구하지 않는다.

관련 가정은 각 lobe 여유 자체가 원거리 tail까지 가우시안이라는 것이다. 관계
(1)은 절대 실패율 예측기가 아니라 본 노드급 bitcell sign-off에서 표준적으로
사용되는 마진 지표이며[22], 제안된 진단은 두 가정을 동시에 검사한다.

### B. 범위

본 연구의 모든 값은 time-zero 기준이다. 이는 의도된 사용 방식과 일치한다.
EOL 시험을 매 로트마다 반복할 수 없으므로, 실리콘에서 경험적으로 확립된 표 I의
50 mV 가드밴드를 time-zero Vmin 사양에 적용하고 그 가드된 값으로 준수 여부를
평가한다. 따라서 열화 모델링은 본 연구의 범위 밖이다.

결과는 단일 기술 노드, 단일 셀 토폴로지, 주로 읽기 지표에 관한 것이다. 공통
성분이 범위 경계에 접근할 때 발생하는 배율 스필 밴드는 compact model 캘리브레이션의
가장자리에 있어 그 영역의 예측은 보수적으로 해석되어야 한다. 제6절 A항의
전압 레벨 절감은 표 I의 사양에 종속되며, IR-drop 예산이 변경되어 사양이
0.7 V를 초과하면 재검토를 요구한다. PDK가 비공개이므로 절대값은 외부적으로
재현 불가하다. 해석적 testbed를 전면 공개하고 정규화 축 결과를 보고하여 상대
비교를 가능하게 한다.

### C. 쓰기 여유와 통합 판정

읽기만으로는 양의 skew가 유리하나, 쓰기 지표는 반대 방향으로 응답한다. 독립
4차원 배치에서 smooth-maximum 합성 하의 통합 최악 조건은 sk ≈ −2 mV의 거의
대칭에서 최소화되었고, 그 결과 곡면은 FSG와 SFG 양쪽에 극대를 갖는 안장형이다.
이 값은 쓰기 세트 전사가 진행 중이므로 본 배치에서 재현되지 않았으며, 가용해지면
9차원에서 재계산되어야 한다. 그럼에도 skew 사양이 읽기 지표만으로 유도되어서는
안 된다는 방향적 결론은 확고하다.

### D. 권고

전압 레벨은 사양으로 결정되어 최소 bracket 구간만 시뮬레이션되어야 한다. 조건
수는 예산-정확도 무릎에서 선택되어야 하며, 그 이후의 한계 노력은 경계 근방의
깊이나 추가 설계 코너에 배분하는 편이 낫다. 표준오차가 기록되는 한 MC 수는
조건 간 균일할 필요가 없다. 소수의 사양 근방 조건에 대한 tail 형상 진단이
상시화되어야 하며, 흐름이 허용하는 경우 lobe별 통계 또는 최소한 왜도와 하위
분위수가 기록되어야 하니, 최소값의 평균과 표준편차는 tail 형상에 관한 정보를
담지 않기 때문이다.

---

## IX. 결론

단일 고정 시뮬레이션 예산으로 순·역방향 SRAM Vmin 질의를 처리하는 대리모델
파이프라인을 구축하고, 첨단 노드의 생산 캘리브레이션 데이터 2,000 조건 4 공급
레벨로 검증하였다.

대리모델은 sign-off 스크리닝에 적합하며, 마진 예산의 1/5인 사양 구간 Vmin
RMSE 9.14 mV, end-of-life 사양 판정 99.3% 일치, 세 개 독립 배치에 걸친 물리
정합성 재현을 달성한다. 시뮬레이션 예산은 사양 유도 근거에서 절감 가능하며,
전압 레벨 수의 20% 감소가 구조적으로 무손실임을 보인다. 허용 공정 윈도우
경계, skew 허용폭, 파라미터 우선순위화를 포함하는 역방향 질의가 추가
시뮬레이션 없이 응답되며, 이로써 NMOS local-sigma가 문턱 skew를 앞선 Vmin
분산의 3위 기여 인자임을, 코너 기반 sign-off가 구조적으로 관측할 수 없는
축에서 확립하였다.

끝으로, 지배 불확실성이 모델이 아닌 지표에 존재함을 발견하였다. 최소값 통계
z-score의 체계적 낙관은 53~144 mV로 추정되어 마진 예산 전체에 비견되며,
대리모델 정밀도와 무관하게 전체 오차를 지배할 것이다. 이 효과의 정량화와
해소는 방법론적 기여에 비견되는 중요성을 가지며, 전체 시뮬레이션 예산의
2% 미만으로 달성 가능하다.

---

## 부록 A: 가우시안 프로세스 배경

본 부록은 주 전문 영역이 통계적 학습 밖에 있는 독자를 위해 형식론을 요약한다.

가우시안 프로세스는 함수값의 임의의 유한 집합이 결합 가우시안 분포를 따르도록
하는, 함수에 대한 분포를 정의한다. 이는 평균 함수와 공분산 커널로 규정되며,
후자는 가까운 입력이 상관된 출력을 낳는다는 가정을 부호화한다. 관측 데이터에
조건화하면 임의의 질의점에서 예측 평균과 예측 분산을 함께 반환하는 사후가
얻어지며, 분산은 관측에서 먼 영역에서 증가하는데 이 점이 본 방법을 통상
회귀와 구별한다.

커널 lengthscale은 상관이 감쇠하는 거리를 지배한다. 한 축을 따라 짧은
lengthscale은 출력이 그 입력에 대해 급격히 변함을, 긴 lengthscale은 둔감함을
가리킨다. 자동 관련성 결정은 각 입력 차원에 독립 lengthscale을 할당하고 모두를
데이터로부터 학습하며, 이것이 적합값이 흔히 민감도 척도로 해석되는 이유이다.
이 해석은 제7절 C항에서 비판적으로 검토된다.

사후 평균은 학습 입력에 대한 커널 평가의 선형 결합이므로, 커널이 미분 가능한
한 질의점에 대해 미분 가능하다. 이 성질이 제4절 F항의 역문제를 탐색이 아닌
gradient 하강으로 풀 수 있게 한다.

Heteroscedastic 우도는 관측 잡음이 데이터 점마다 다를 수 있게 하여 표준
정식화를 일반화한다. 이 역할에 조건별 MC 표준오차를 공급하면 사후가 조건을
그 통계적 신뢰도에 비례하여 가중하게 되며, 보조 보정 항이 불필요하다.

## 부록 B: 지표 정의

설계범위 feasibility 일치, 양측 censoring, 어시스트-활성 채점의 형식 정의를,
순진한 지표가 동일 예측의 오차를 약 60배 과대보고함을 입증하는 재현표와 함께
제공한다.

## 부록 C: 재현성

조건 생성기 버전, seed, 사분면 가중, 파라미터 범위, deck 번호 규약을 규정한다.
해석적 testbed를 전면 공개한다.

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
