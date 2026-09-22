# SRAM Vmin surrogate 발표 해설집

> 기준일: 2026-09-23
>
> **발표 수치의 기준:** `manuscript/SRAM_Vmin_IEEE.docx`를 생성하는 `manuscript/code/make_docx.js`와 `manuscript/results/*.json`.
> `manuscript/paper_*.md`는 D-16 이후 수치가 낡았으므로 발표 숫자의 출처로 사용하지 않는다.

이 문서는 “슬라이드에 무엇을 적을지”보다 **발표자가 왜 그런 말을 할 수 있는지**를 이해하는 데 목적이 있다. 결과 수치는 원시 회로 시뮬레이션·모델 및 그 정의에 조건부이며, 실리콘 yield 보장으로 바꾸어 말하면 안 된다.

---

## 0. 30초 핵심 메시지

> **직접 회로 시뮬레이션을 대체하는 것이 아니라, 이미 수행한 비싼 회로 시뮬레이션에서 얻은 정보를 재사용해 더 많은 설계 질문에 답하는 surrogate 계층이다.**
> 9개 공정 축과 공급전압에서 margin의 평균과 산포를 학습하고, 물리적으로 해석 가능한 yield 관계로 Vmin을 계산한다. 그 결과 “이 조건의 Vmin은?”이라는 순방향 질문뿐 아니라 “목표 Vmin을 만족하려면 이 공정 축을 어디까지 바꿔야 하나?”라는 조건부 역방향 질문도 빠르게 할 수 있다.

### 네 개의 발표 펀치라인

1. **왜 surrogate인가:** HSPICE/PDK/compact model을 버리는 AI가 아니라, 그 결과를 반복 질의 가능한 설계 탐색 모델로 바꾼다.
2. **어떻게 구현했나:** `9개 공정 축 + VDD → μ GP, log σ GP → z=μ/σ → Vmin`의 명시적 파이프라인이다.
3. **DTCO에 어떻게 쓰나:** Sobol로 “어느 축이 중요할까”를 우선순위화하고, one-axis inverse로 “그 축을 얼마나 움직여야 하나”를 조건부로 계산한다.
4. **비용은 얼마나 줄이나:** 초기 학습 캠페인은 필요하지만, 모델을 만든 뒤 수많은 what-if/inverse 질의에 추가 MC가 필요 없다. 저장된 예산 실험은 정확도 대가를 동반한 **sample-count** 감소 후보를 보여준다.

### 가장 중요한 안전 문장

- “Surrogate 정확도”와 “실제 array yield 정확도”는 다르다.
- “inverse”는 9개 원인의 유일한 진단이 아니라 **나머지 축을 고정한 설계 경계 탐색**이다.
- “Sobol 영향도”는 그 분석 범위·분포·출력에 조건부다.
- “53배”는 HSPICE wall-clock을 직접 재서 측정한 속도 향상이 아니라, 조건·전압·MC 표본 수로 계산한 예산 비율이며 MC-depth 부분은 noise-emulation이다.

---

## 1. 먼저 맞춰야 할 배경: SRAM과 Vmin

### 1.1 SRAM 셀을 아주 간단히 보면

6T SRAM의 한 저장 노드는 세 역할의 transistor strength 균형으로 유지된다.

| 역할 | 소자 | 읽기/쓰기에서 직관 |
|---|---|---|
| PU (pull-up) | PMOS | 저장 노드를 ‘1’ 방향으로 끌어올린다. |
| PD (pull-down) | NMOS | 저장 노드를 ‘0’ 방향으로 끌어내린다. |
| PG (pass-gate) | NMOS | bitline과 저장 노드를 연결하여 읽고 쓴다. |

- **읽기:** bitline을 연결했을 때 기존 저장값이 뒤집히지 않아야 한다. 보통 SNMR 계열 마진으로 본다.
- **쓰기:** 새 값을 충분히 강하게 넣어 기존 저장값을 뒤집을 수 있어야 한다. 여기서는 Vtrip 기반 지표를 쓴다.
- 같은 공정 corner라도 read와 write에 불리한 방향은 달라질 수 있다. 이 데이터에서도 read 제한 corner는 FSG, write 제한 corner는 SFG다.

### 1.2 Vmin은 왜 어려운가

공급전압을 내리면 성능/안정성 여유가 작아진다. 셀들은 완전히 같지 않으므로 어떤 셀은 평균 셀보다 먼저 실패한다. 따라서 Vmin은 “평균 셀의 동작전압”이 아니라 **큰 array에서 충분히 낮은 실패확률을 만족하는 통계적 경계 전압**이다.

MC를 직접 한다면 다음 조합이 필요하다.

```text
공정 조건 수 × 공급전압 level 수 × 조건·전압별 mismatch MC 표본 수
```

새 공정 질문이 생길 때마다 이 과정을 재실행하면 비용이 급격히 커진다.

---

## 2. 논문의 metric과 식: 단위를 섞지 말기

### 2.1 margin distribution

한 공정 조건 `p`, 공급전압 `V`에서 margin을 `M`이라 하자. 논문의 기본 근사는 다음이다.

```text
M(p, V) ~ Normal( μ(p, V), σ(p, V)^2 )
```

- `μ`: 그 조건에서의 평균 margin. 전압/공정 shift가 평균 동작 여유를 어떻게 옮기는지.
- `σ`: 그 조건에서 cell-to-cell mismatch로 margin이 얼마나 퍼지는지.
- 이것은 **물리적 셀 산포**다. GP가 예측값에 대해 갖는 불확실성과 다르다.

### 2.2 z-score

```text
z(p, V) = μ(p, V) / σ(p, V)
```

직관은 “평균이 0 margin에서 표준편차 몇 개만큼 떨어져 있는가”다. 양의 z가 크면 실패 꼬리에서 멀다.

정규 근사 및 margin `M≥0` 통과 정의하에서는:

```text
P_cell,pass = Φ(z)
P_cell,fail = Φ(−z)
```

`Φ(z)`는 **한 셀의 통과확률**이다. array yield 자체를 바로 뜻하지 않는다.

### 2.3 array target과 `Z_target`

독립·동일한 셀 `N`개라는 단순화 아래:

```text
Y_array = (1 − P_cell,fail)^N ≈ exp(−N · P_cell,fail)
```

현재 manuscript 경로의 설정은 128 Mb, array yield 99%, `Z_target=6.3984`다 (`manuscript/code/_paths.py`). 이 값은 root AGENTS의 예전 256 Mb/6.50와 혼동하지 않는다.

### 2.4 Vmin의 올바른 정의

특정 전압에서의 lower-tail margin은

```text
g(p, V) = μ(p, V) − Z_target · σ(p, V)
```

이고, Vmin은 이 margin이 처음 0 이상이 되는 **공급전압**이다.

```text
Vmin(p) = min { V : g(p, V) ≥ 0 }
```

**절대 말하면 안 되는 식:** `Vmin = μ − kσ`.

두 식 모두 단위가 V라서 혼동하기 쉽지만, 오른쪽은 margin이고 Vmin은 그 margin의 전압축 교차점이다.

#### 15초 비유

> μ−kσ는 “현재 고도에서 물보다 얼마나 위에 있는가”이고, Vmin은 “고도를 어디까지 올려야 수면을 넘는가”입니다. 둘 다 길이 단위라도 같은 양은 아닙니다.

### 2.5 `Z_eff` / lobe correction의 위치

저장소의 lobe 분석에는 `Z_eff = Z_target + z_bias`라는 보정 후보가 존재한다. 하지만 현재 DOCX의 기본 surrogate 정확도 3.98/5.65 mV는 Gaussian `Z_target` 정의로 계산된 기준값에 대한 것이다. 제출 원고가 tail correction을 future work로 남겼다면, 본 발표의 기본 pipeline도 `Z_target`으로 두고 lobe correction은 **backup: metric-risk analysis**로 분리한다.

- 9개 조건에서 Gaussian 형태 이탈을 본 기록과 약 70 mV급 보정 추정은 중요하다.
- 그러나 그 보정도 lobe/min-of-two 모형·상관 추정·기울기에 의존하는 추정이며, silicon에서 측정된 Vmin 오차가 아니다.
- “모델 오차는 4–6 mV지만 metric 가정의 영향은 훨씬 클 수 있다”가 올바른 교훈이다.

---

## 3. 데이터와 9개 공정 축

### 3.1 실제 GP 입력은 10차원

`9개 device/process 축 + Vop`이다. direct gate-length(nm) 또는 oxide thickness 축이 직접 들어가지는 않는다.

| 코드 | 발표용 이름 | 소자 수준 의미 | 단위 |
|---|---|---|---|
| `cn` | NMOS 공통 Vth shift | PG·PD NMOS에 공통 Vth shift | mV |
| `sk` | PG–PD NMOS Vth skew | PG에 `cn+sk`, PD에 `cn−sk` | mV |
| `pu` | PMOS Vth shift | pull-up PMOS의 Vth shift | mV |
| `l_com` | NMOS 공통 local-σ | PG·PD NMOS mismatch 산포 배율 | × |
| `l_sk` | PG–PD local-σ skew | 두 NMOS 역할의 mismatch 배율 차이 | × |
| `lpu` | PMOS local-σ | PMOS mismatch 산포 배율 | × |
| `m_com` | NMOS 공통 mobility | PG·PD mobility 배율 | × |
| `m_sk` | PG–PD mobility skew | 두 NMOS mobility 배율 차이 | × |
| `mpu` | PMOS mobility | PMOS mobility 배율 | × |

### 3.2 두 가지 흔한 오해

1. `sk`는 **N/P threshold skew가 아니라 PG/PD NMOS skew**다.
2. `l_*`의 l을 “gate length”라고 부르면 안 된다. 이 구현에서 해당 좌표는 local mismatch `σ` 배율이다. 실제 layout, area, implant, geometry의 어느 knob가 이 축을 움직이는지는 별도 process mapping이 필요하다.

### 3.3 입력 표준화

mV shift와 0.7–1.3 배율을 그대로 GP 거리 계산에 넣으면 숫자 크기가 큰 열이 거리를 지배할 수 있다. 그래서 학습 전에 각 입력을 평균 0, 표준편차 1에 가깝게 표준화한다. 이 덕분에 ARD lengthscale을 축끼리 비교할 수 있다.

---

## 4. GP surrogate를 쉬운 말로 설명하기

### 4.1 GP는 무엇인가

GP는 “모르는 함수 전체”에 대한 분포를 두고, 관측한 입력 주변에서는 관측값을 따르며 멀어질수록 불확실해지는 보간기다.

이 논문에서 학습할 함수는 직접 `Vmin(p)` 하나가 아니라:

```text
μ(p, Vop)와 log σ(p, Vop)
```

이다. read와 write에 각각 별도 모델이 있고, μ와 log σ에도 각각 하나씩 있어 총 네 개의 GP가 있다.

### 4.2 왜 Vmin을 직접 회귀하지 않았나

Vmin을 직접 맞히면 최종 숫자는 나올 수 있지만, 그 변화가:

- 평균 margin `μ`가 악화됐는지,
- cell mismatch 산포 `σ`가 커졌는지,
- 아니면 둘 다인지

분해하기 어렵다. μ/σ를 별도로 모델링하면 sensitivity와 DTCO 이야기를 물리적 언어로 할 수 있다.

### 4.3 kernel과 Matérn 5/2

현재 구현은 μ와 log σ 모두 **full-ARD Matérn 5/2** kernel을 사용한다. 아주 쉽게 말하면:

- 가까운 공정 조건은 비슷한 결과를 낼 것이라는 smoothness 가정,
- 다만 완전히 직선/무한히 매끄러운 함수가 아니라 현실적인 굴곡은 허용,
- 축마다 별도의 변화 거리(ARD lengthscale)를 학습

을 뜻한다.

“physics-consistent GP”보다 **“회로 시뮬레이션 결과의 smooth local interpolation을 가정한 GP”**라고 설명하는 편이 정확하다. 물리성의 핵심은 이후 μ·σ→yield 변환에 있다.

### 4.4 왜 `log σ`인가

σ는 항상 양수라서 log σ를 학습하면 음수 σ 예측을 피한다. 그리고 MC에서 표준편차 추정량의 표준오차는 큰 표본·정규 근사에서 대략:

```text
SEM(σ̂) ≈ σ / √(2N_MC)
SEM(log σ̂) ≈ 1 / √(2N_MC)
```

가 되어, N_MC가 같다면 log scale에서 관측 잡음이 더 균질해진다. “완전히 등분산”이라고 단정하지 말고 **근사적으로**라고 말한다.

### 4.5 GP uncertainty와 σ를 구별하는 비유

- `σ`: 같은 시험을 받은 많은 학생의 성적 편차.
- GP predictive uncertainty: 그 학생 집단의 성적 분포를 추정한 선생님이 아직 얼마나 확신하지 못하는가.

둘은 모두 ‘불확실성’처럼 들리지만 대상이 다르다.

---

## 5. ARD와 Sobol: 둘 다 “중요도”가 아니다

### 5.1 ARD relevance / lengthscale

ARD가 답하는 질문:

> 모델이 이 축을 따라 얼마나 빨리 굽어야 데이터를 설명했는가?

짧은 lengthscale은 작은 입력 변화에도 출력이 빠르게 달라질 수 있음을 뜻한다. 그러나 축 범위가 아주 좁으면 출력 분산 기여는 작을 수 있다. 그래서 ARD는 **local curvature proxy**이지 global influence 순위가 아니다.

### 5.2 Sobol index

Sobol은 지정한 입력 분포에서 출력 분산을 축별로 분해한다.

- `S1_i`: i축만 변할 때 생기는 단독 효과.
- `ST_i`: i축이 관여하는 단독 + 모든 interaction 효과.

이번 결과의 정확한 출력은:

```text
read mode, 125 °C, z(VT0=0.625 V) = μ/σ
```

이고 입력은 **학습 box 안 독립 균등분포**다.

따라서 “실제 생산 lot에서 불량의 38%가 non-corner axis 때문이다”는 해석은 틀리다. 올바른 문장은:

> 이 연구가 정한 design box와 independent uniform prior 아래, corner 정의에 포함되지 않는 축이 read z(0.625 V) 변동에 무시할 수 없는 영향을 준다.

### 5.3 현재 total-order ST 순위 (read z at 0.625 V)

| 순위 | 축 | ST | 발표 해석 |
|---:|---|---:|---|
| 1 | `cn`, NMOS 공통 Vth | 0.413 | 가장 큰 global driver |
| 2 | `l_com`, NMOS 공통 local-σ | 0.272 | PMOS Vth보다 큰 non-corner mismatch driver |
| 3 | `pu`, PMOS Vth | 0.200 | 중요한 global driver |
| 4 | `sk`, PG–PD Vth skew | 0.065 | 상대 strength 균형도 영향 |
| 5 | `lpu`, PMOS local-σ | 0.045 | PMOS mismatch 영향 |
| 나머지 | mobility/skew 축 | ≤0.015 | 이 범위·출력에서는 작음 |

**정확한 punchline:** `l_com`은 `pu`보다 큰 total-order 영향도를 가진다.

**틀린 punchline:** local mismatch가 모든 global Vth corner보다 가장 중요하다. `cn=0.413`이 1위이므로 틀리다.

### 5.4 왜 ST를 합치면 100%를 넘을 수 있나

interaction은 여러 축이 공유한다. 예를 들어 `cn`과 `l_com`이 함께 작동하는 효과는 두 ST에 모두 들어갈 수 있다. ST 막대를 pie chart로 만들지 말고 **순위 막대**로 제시한다.

---

## 6. inverse: 무엇을 풀고 무엇을 풀지 않는가

### 6.1 순방향 질문

```text
입력: 9축 좌표 p
출력: Vmin(p)
```

### 6.2 역방향 질문

```text
입력: 목표 V*, 나머지 8축 고정, 한 축 xj 선택
출력: Vmin(p with xj)=V*가 되는 xj
```

이 논문에서 검증한 것은 축별 1차원 bisection이다. 목표가 양 끝의 Vmin 사이에 있고, 해당 구간에서 연속/단조적이라면 root를 안정적으로 좁힐 수 있다.

### 6.3 발표에서 꼭 붙일 조건

- 전압 VDD에 대해 z가 단조인 것과 공정 축에 대해 Vmin이 단조인 것은 다르다.
- GUI는 먼저 scan하여 bracket과 여러 교차를 찾는다. 여러 해가 보이면 한 개만 고르지 않는다.
- `solver residual`이 µV 수준이어도 이것은 root-finding 수치 오차다. surrogate의 3.98/5.65 mV 일반화 오차가 사라진 것은 아니다.
- 9개 축 미지수를 Vmin 하나로 유일하게 회복하는 것은 불가능하다. 원인 규명에는 추가 측정·prior·공정 제약이 필요하다.

### 6.4 inverse 결과 수치

현재 결과에서 coordinate recovery는:

| 축 | Read RMSE | Write RMSE | 의미 |
|---|---:|---:|---|
| `cn` | 1.46 mV | 2.50 mV | 다른 축을 실제 좌표로 고정한 synthetic recovery 조건 |
| `pu` | 1.94 mV | 5.10 mV | 같은 조건부 recovery |

이 값은 Vmin RMSE와 다른 축의 물리량(mV Vth coordinate)이다. “Vmin을 1.46 mV로 맞힌다”는 의미가 아니다.

---

## 7. 검증 metric을 읽는 법

### 7.1 hold-out Vmin RMSE

| 항목 | Read | Write |
|---|---:|---:|
| hold-out Vmin RMSE | 3.98 mV | 5.65 mV |
| 채점 가능 조건 수 | 245 / 300 | 228 / 300 |
| censored 또는 off-grid | 55 / 300 | 72 / 300 |
| 최대 절대오차 | 약 20.50 mV | 약 43.29 mV |

- RMSE는 큰 오차에 더 큰 벌점을 주는 평균적 규모다.
- 245/228이라는 denominator를 함께 말해야 한다.
- “모든 Vmin을 4–6 mV 이내로 맞힌다”는 과장이다.

### 7.2 unseen corner

네 corner를 질의했지만 각 mode에서 하나는 `Vmin < 0.4 V` censored이다. 그래서 RMSE 수치는 각 mode의 **3개 비검열 corner** 기준이다.

| 항목 | Read | Write |
|---|---:|---:|
| corner RMSE (scorable) | 8.48 mV | 5.79 mV |
| 제한 corner | FSG | SFG |

제한 corner 자체는 맞게 식별했지만, RMSE보다 작은 차이의 corner 순서를 확정했다고 말하면 안 된다.

### 7.3 σ R²

현재 σ fit R²는 read 0.9971, write 0.9880이다. 이는 σ label variation에 대한 fit 지표다. Vmin R²도, array yield R²도 아니다. σ가 잘 맞아도 tail model이 맞는지는 별도 문제다.

### 7.4 censoring

- `Vmin < 0.4 V`: grid 하한보다 낮다는 뜻이며 정확한 숫자가 아니다.
- `Vmin > grid max`: grid 안에서 target crossing이 없다는 뜻이다.
- 표나 산점도에서 제외된 점이 “실패” 또는 “오차 0”이 아니라 score 정의상 수치화할 수 없는 점임을 말한다.

---

## 8. simulation cost 절감: 좋은 주장과 나쁜 주장

### 8.1 저장된 combined budget 결과

| | Read | Write |
|---|---:|---:|
| train conditions | 1,700 → 400 | 1,700 → 400 |
| Vop levels | 5 → 4 | 4 → 4 |
| MC depth | 5,000 → 500 | 5,000 → 500 |
| sample-count 비율 | 53.125× | 42.5× |
| baseline Vmin RMSE | 3.98 mV | 5.65 mV |
| reduced Vmin RMSE | 7.51 mV | 8.46 mV |
| RMSE 증가 | +3.53 mV | +2.81 mV |

### 8.2 올바른 메시지

> “같은 정답 정확도를 공짜로 얻었다”가 아니라, 질문 목적과 허용 오차에 따라 선택할 수 있는 **Pareto point**를 정량화했다.

### 8.3 피해야 할 메시지

- “53배 빠른 HSPICE runtime을 실측했다.” → 아니다.
- “write도 전압 level을 줄였다.” → 저장된 write combined run은 4→4다.
- “MC depth를 500으로 줄여도 무손실이다.” → D-16 이후 그 결론은 폐기됐다.
- “surrogate training은 무료다.” → exact GP training 비용도 있고, checkpoint 복원과 별도 validation도 필요하다.

---

## 9. 그림별 상세 해설

각 그림은 아래 순서로 발표한다.

1. **무엇이 input/출력인가?**
2. **어떤 색·선·점이 무엇인가?**
3. **청중이 봐야 할 한 부분은 어디인가?**
4. **이 그림만으로 말할 수 없는 것은 무엇인가?**

### Fig. 1 — pipeline (`fig1_pipeline.png`)

| 항목 | 해설 |
|---|---|
| 무엇을 그리나 | 9개 공정 축과 Vop을 넣어 μ·σ를 GP로 예측하고, z=μ/σ 및 threshold crossing으로 forward/inverse를 만드는 전체 흐름이다. |
| 왼쪽 상자 | “공정 조건을 하나 찍는다”가 아니라 9개의 서로 다른 physical/mismatch/mobility knob와 Vop을 동시에 입력한다. |
| 가운데 GP | μ와 σ가 따로다. σ는 GUI/발표에서 `log σ`로 학습된다는 보충을 할 수 있다. |
| physics layer | trainable neural layer가 아니라 명시적인 계산식이다. 여기서 “평균 변화냐 산포 변화냐”라는 해석성이 생긴다. |
| 오른쪽 forward | 임의 공정 좌표에서 Vmin을 예측한다. |
| 오른쪽 inverse | 다른 축을 고정하고 하나의 축을 target Vmin 경계까지 bisection한다. |
| 말할 문장 | “GP는 μ와 σ만 예측합니다. yield 정의와 Vmin conversion은 학습시키지 않고 식으로 고정해 두었습니다.” |
| 주의 | 현재 그림의 `Z_eff/lobe correction`은 현재 기본 RMSE 정의와 섞이면 안 된다. 기본 발표는 `Z_target` pipeline으로 보이고 lobe branch는 backup/metric-risk로 분리하거나 그림을 고친다. |

### Fig. 2 — DOE design (`fig2_design.png`, backup 권장)

| 항목 | 해설 |
|---|---|
| (a) 점 | 각 점은 하나의 공정 조건이다. x=NMOS common Vth shift, y=PMOS Vth shift다. |
| 사분면 | FSG 45%, SSG/FFG 20%, SFG 15%로 read에 위험한 사분면을 더 많이 표본화했다. 균등한 foundry lot 분포를 그린 것이 아니라 DOE allocation이다. |
| (b) 대각선 | PG/PD local-σ multiplier가 같으면 점선 `y=x`에 놓인다. 주변의 band는 common component와 skew를 분리해 생성한 설계가 두 소자의 산포를 tracking시키는 모습을 보인다. |
| `corr=0.88` | PG/PD multiplier의 상관이며 성능 상관이나 GP accuracy가 아니다. |
| 말할 문장 | “corner만 네 개 찍지 않고, 위험 사분면과 PG–PD relative mismatch를 포함한 공간을 의도적으로 채웠습니다.” |
| 주의 | 이 그림은 데이터 설계를 보여줄 뿐, surrogate가 잘 맞는다는 증거는 아니다. |

### Fig. 3 — hold-out forward accuracy (`fig3_forward.png`)

| 항목 | 해설 |
|---|---|
| x/y축 | x=학습에 쓰지 않은 기준 회로 simulation Vmin, y=surrogate Vmin. 이상적이면 검은 45° 선 위다. |
| 점 | 채점 가능한 hold-out 조건 하나씩이다. 색은 read/write를 구분한다. |
| 회색 ±10 mV band | 완전한 정답선 주변의 읽기 쉬운 기준 band다. confidence interval이 아니다. |
| RMSE/n | read 3.98 mV over 245, write 5.65 mV over 228. 300개 전체가 아니다. |
| 봐야 할 것 | 대부분 대각선 근처 → 데이터 사이 보간에서 average accuracy가 mV 단위. |
| 말할 문장 | “동일한 Gaussian reference 정의로 계산된, 채점 가능한 hold-out 조건에서의 평균적 Vmin 오차입니다.” |
| 주의 | 그림 밖/censored 조건은 성능이 0이라는 뜻이 아니고 Vmin value가 grid에 없어서 점수에서 제외됐다. 큰 outlier가 전혀 없다는 뜻도 아니다. |

### Fig. 4 — unseen PDK corner (`fig4_corner.png`)

| 항목 | 해설 |
|---|---|
| 막대 | 진한 막대=reference simulation, 연한 막대=surrogate. 파랑=read, 갈색=write. |
| x축 | FFG, FSG, SFG, SSG 네 PDK corner. 학습에서 제외했다. |
| 점선 | T0 spec 0.625 V. 높을수록 더 높은 공급전압이 필요하므로 나쁘다. |
| 두꺼운 테두리 | mode별 limiting corner: read FSG, write SFG. |
| 막대 위 +/−mV | `surrogate − reference` 오차다. +면 surrogate가 Vmin을 높게 예측, −면 낮게 예측한다. |
| `censored <0.4 V` | 정확한 Vmin이 0.4 V 미만이라는 뜻. 0.4 V 값으로 비교한 것이 아니다. |
| 말할 문장 | “학습에서 빼 둔 industry corner에서도 각 mode의 worst corner를 맞췄고, scorable 세 corner의 RMSE는 read 8.48, write 5.79 mV입니다.” |
| 주의 | 네 corner 모두에 대해 RMSE를 낸 것이 아니다. 서로 몇 mV 차이의 corner 전체 순위를 신뢰성 있게 매겼다는 주장도 하지 않는다. |

### Fig. 5 — inverse boundary (`fig5_inverse.png`)

| 항목 | 해설 |
|---|---|
| 배경색 | `cell Vmin=max(read, write)`. 파란색은 T0=0.625 V보다 낮아 pass 쪽, 붉은색은 높은 Vmin이 필요한 fail 쪽이다. |
| x/y축 | NMOS/PMOS global Vth shift 2D slice. 다른 7축은 reference 좌표에 고정됐다. |
| 빨간 dashed | read가 T0를 통과하는 경계. |
| 노란 solid | write가 T0를 통과하는 경계. |
| 읽는 법 | 한 mode만 pass여도 충분하지 않다. 셀이 통과하려면 read·write 둘 다 pass라야 하고, combined Vmin은 둘 중 더 큰 값이다. |
| 핵심 결론 | process window에는 read-limited 부분과 write-limited 부분이 다르게 존재한다. corner 네 점만으로는 이 경계의 모양/위치를 주지 못한다. |
| 말할 문장 | “이것이 inverse의 산출물입니다. 특정 목표선 위에서 어떤 Vth 조합까지 허용되는지를 좌표로 줍니다.” |
| 주의 | 9D 전체 window가 아니라 2D conditional slice다. read/write batch의 temperature와 reference coordinate가 다르므로 전체 combined surface의 실측 검증 주장은 하지 않는다. |

### Fig. 6 — lobe correction (`fig6_lobe.png`, backup/metric-risk)

| 항목 | 해설 |
|---|---|
| (a) | 서로 다른 두 estimator가 lobe correlation `ρLR`에 대해 대체로 음의 값을 가리킨다는 관찰이다. dashed가 pooled estimate다. |
| (b) 회색/갈색 | naive Gaussian z vs lobe-corrected z를 Vmin으로 바꾼 차이다. 화살표 위 +mV가 보정 이동량이다. |
| 핵심 메시지 | surrogate가 μ/σ reference를 잘 근사해도, `min-of-two` tail metric 자체의 형태 가정이 틀리면 sign-off 결론이 수십 mV 달라질 수 있다. |
| 말할 문장 | “이 그림은 GP가 틀렸다는 그림이 아니라 reference metric의 가정이 더 큰 risk일 수 있다는 진단입니다.” |
| 주의 | baseline 3.98/5.65 mV와 이 보정량을 합산해 ‘실제 오차’라고 말하지 않는다. 이 보정도 model-based estimate이며 silicon validation이 아니다. |

### Fig. 7 — budget trade-off (`fig7_cost.png`)

| 항목 | 해설 |
|---|---|
| (a) x/y축 | training condition 수를 줄일 때 hold-out Vmin RMSE가 어떻게 변하는지. x축은 log scale이다. draw 1/2는 subset 선택에 따른 흔들림을 보여준다. |
| knee 400 | 약 400 부근이 실용적 후보라는 observation이다. 보편적인 자연 법칙/엄밀 optimum이 아니다. |
| (b) | MC samples per condition을 바꾼 결과. D-16 후 MC depth는 실제로 accuracy에 영향을 준다. |
| (c) | 하나만 줄인 경우와 여러 요소를 동시에 줄인 경우가 다름을 보여준다. 오른쪽 7.5 mV bar가 53× sample-count cut의 대가다. |
| 말할 문장 | “이 그림의 목적은 무손실 절감 주장보다, 어떤 cost/accuracy trade-off를 선택할지 수치로 만드는 것입니다.” |
| 주의 | HSPICE wall-clock 측정 그래프가 아니다. write의 계산은 42.5×이며 voltage levels를 줄인 것이 아니다. |

### Fig. 8 — sensitivity (`fig8_sensitivity.png`)

| 항목 | 해설 |
|---|---|
| (a) | read/write에서 `z(VT0)` variance의 ST share. `cn`이 1위, `l_com`이 2위, `pu`가 3위다. local NMOS σ가 PMOS Vth를 앞서는 것이 핵심이다. |
| error bar | Saltelli sample row bootstrap CI다. 제조 lot의 variation bar가 아니다. |
| (b) | σ 자체의 variance가 어떤 축에서 오는지. local-σ 축이 대부분을 차지한다. μ 영향도와 σ 영향도는 다를 수 있다는 것을 보여준다. |
| (c) | ARD relevance가 거의 평평하다. ‘변화가 빠른 축’이라는 free proxy가 output variance influence를 제대로 대체하지 못한다는 반례다. |
| 말할 문장 | “어느 축이 model을 빨리 굽게 했는지와, 실제 design box에서 z variance를 얼마나 움직이는지는 다릅니다. 그래서 Sobol을 따로 했습니다.” |
| 주의 | ST가 0.272라서 “실제 불량의 27.2%”라는 뜻이 아니다. ST 합은 interaction 때문에 중복된다. |

### Fig. 9 — skew tolerance (`fig9_skew.png`, backup)

| 항목 | 해설 |
|---|---|
| 색 | 각 `cn, pu` 지점에서 허용되는 PG–PD skew 폭이다. 빨강은 허용 폭이 거의 없고, 파랑은 ±40 mV 전체 sweep을 허용한다. |
| 검은 선 | 어떤 Vth 조합에서는 어느 정도 skew도 모두 허용되는 ‘every skew’ 경계다. |
| (a)/(b) | naive `Ztarget`와 lobe-corrected `Zeff`를 비교한다. 보정을 넣으면 모든 skew를 허용하는 평면 비율이 82%→67%로 줄어든다. |
| 말할 문장 | “tail 가정의 보정은 단순히 Vmin 숫자를 이동하는 데서 끝나지 않고, 허용 공정 window의 모양을 줄일 수 있습니다.” |
| 주의 | Fig. 6과 마찬가지로 metric-risk backup이며 기본 Gaussian RMSE와 혼용하지 않는다. |

### Fig. 10 — 0.575 V DTCO scenario (`fig10_scenario.png`)

| 항목 | 해설 |
|---|---|
| 네 panel | baseline, NMOS local-σ 개선, PMOS local-σ 최대 개선, 양쪽 local-σ 분담 개선이다. |
| 색 | combined cell Vmin=max(read,write): 파랑 pass, 빨강 fail. |
| black solid / long dash | read limit과 write limit. 두 line의 동시 pass 영역만 쓸 수 있다. |
| thin grey dash | 기존 0.625 V spec reference. 새 target은 0.575 V다. |
| 별 | read FSG와 write SFG limiting corner. filled star는 해당 corner가 새 target을 통과함을 뜻한다. |
| 핵심 숫자 | NMOS local-σ 약 10.9% 감소, 양쪽 분담 시 각 7.8% 감소가 surrogate point estimate에서 target을 맞춘다. |
| 말할 문장 | “민감도는 무엇을 먼저 볼지 알려주고, inverse는 target을 위해 각 knob를 얼마나 움직여야 할지를 계산합니다. 이 두 단계를 합쳐 DTCO candidate를 만듭니다.” |
| 주의 | PMOS-only의 floor miss는 0.58 mV로 model RMSE보다 작다. ‘절대 불가능’이 아니라 추가 circuit verification이 필요한 near-boundary point다. 개선 비율은 제조비용 최소해가 아니다. |

---

## 10. 15분 발표 권장 구조와 대본

### Slide 1 (0:00–0:40) — 제목과 한 문장

**화면:** `Forward and inverse SRAM Vmin estimation across a 9D process window` + “one calibration campaign → many design questions.”

**말할 문장:**

> 오늘의 핵심은 AI가 HSPICE를 대체한다는 것이 아닙니다. 한 번 수행한 회로 simulation을 재사용해 Vmin을 예측하고, 목표 Vmin을 만족하는 공정 경계까지 역으로 찾는 설계 도구를 만들었다는 것입니다.

### Slide 2 (0:40–1:40) — 문제: MC 비용과 corner의 빈칸

**화면:** `conditions × voltage levels × MC samples` 식 + four corners가 9D 공간의 일부만 본다는 그림.

**말할 문장:**

> direct MC는 한 조건의 통계를 신뢰성 있게 보는 좋은 방법이지만, 공정 window 전체에 반복하면 비용이 큽니다. 그리고 corner는 global Vth 조합을 대표하지만 local mismatch strength 같은 축을 독립적으로 sweep하지 않습니다.

### Slide 3 (1:40–2:40) — metric/Vmin primer

**화면:** μ, σ 분포와 `g=μ−kσ`, `g=0 → Vmin` 도식.

**말할 문장:**

> 평균이 좋아도 산포가 크면 tail cell이 실패합니다. 그래서 μ와 σ를 따로 보고, 특정 전압에서의 lower-tail margin이 0이 되는 지점을 Vmin으로 정의합니다.

### Slide 4 (2:40–4:00) — 9 axes + GP implementation

**화면:** Fig. 1의 정정판(기본 `Ztarget`) 또는 pipeline 재도식; 9축 3×3 grouping.

**말할 문장:**

> 입력은 threshold shift 3개, local mismatch 배율 3개, mobility 배율 3개, 그리고 VDD입니다. read와 write에서 각각 μ GP와 log σ GP를 별도로 학습하고, Vmin conversion은 학습시키지 않은 식으로 수행합니다.

### Slide 5 (4:00–5:20) — forward validation

**화면:** Fig. 3.

**말할 문장:**

> 학습에 쓰지 않은, grid 안에서 Vmin을 채점할 수 있는 조건에서 read RMSE는 3.98 mV, write 5.65 mV입니다. 이는 Gaussian reference definition에 대한 surrogate error입니다.

### Slide 6 (5:20–6:15) — held-out PDK corners

**화면:** Fig. 4.

**말할 문장:**

> 더 어려운 test로 네 PDK corner를 학습에서 빼고 물었습니다. read는 FSG, write는 SFG가 제한 corner라는 것을 맞췄습니다. 단, 각 mode의 한 corner는 하한 아래 censoring되어 RMSE는 세 corner 기준입니다.

### Slide 7 (6:15–7:50) — inverse is the new query

**화면:** Fig. 5.

**말할 문장:**

> forward가 “이 조건에서 Vmin은 얼마인가”라면, inverse는 “0.625 V boundary를 이루는 Vth 조합이 무엇인가”를 줍니다. read와 write의 boundary가 서로 다르므로 usable window는 교집합입니다.

### Slide 8 (7:50–9:10) — Sobol: which axis matters

**화면:** Fig. 8(a)만 크게, (b)(c)는 small inset 또는 backup.

**말할 문장:**

> `cn`이 가장 크지만 NMOS local mismatch `l_com`이 PMOS Vth shift `pu`보다 큰 total-order 영향을 가집니다. 이 순위는 이 design box와 uniform prior에서의 z(0.625 V) variance에 대한 것입니다.

### Slide 9 (9:10–10:50) — scenario/DTCO

**화면:** Fig. 10의 baseline + joint-N/P panel만 크게.

**말할 문장:**

> 사양을 0.575 V로 낮추는 scenario에서 sensitivity가 주목할 축을 알려주고, inverse가 필요 개선량을 정량화합니다. local σ 두 축을 분담하면 각 7.8%의 surrogate-coordinate 변화로 target에 도달하는 후보가 나옵니다. 이것은 곧바로 제조비용 최적화 결과는 아니고, circuit simulation으로 재검증할 후보입니다.

### Slide 10 (10:50–11:50) — budget trade-off

**화면:** Fig. 7(c) 크게, (a)(b) 작게.

**말할 문장:**

> 53× sample-count 감축은 +3.53 mV RMSE라는 price를 가집니다. 결론은 lossless saving이 아니라, accuracy와 budget 사이 Pareto point를 수치로 관리할 수 있다는 것입니다.

### Slide 11 (11:50–12:40) — GUI demonstration

**화면:** Inverse Studio. `cn` 또는 `l_com` 선택 → target change → scan/root → plane.

**말할 문장:**

> 이 화면은 논문 모델을 그대로 쓴 local-only demonstration입니다. slider로 좌표를 바꾸고, scan이 bracket을 확인한 다음 one-axis boundary만 풉니다. 해가 없거나 여러 개면 그 상태를 숨기지 않습니다.

### Slide 12 (12:40–14:00) — conclusion + limitations

**화면:** 네 펀치라인 + 작은 `surrogate error ≠ tail/metric error ≠ silicon proof` 도식.

**말할 문장:**

> 우리의 contribution은 빠른 Vmin 숫자 하나가 아니라, 한 simulation budget에서 forward prediction, process boundary, sensitivity, scenario screening을 연결한 것입니다. 최종 sign-off는 여전히 high-fidelity simulation과 silicon validation이 필요합니다.

### Backup

- Fig. 6: lobe/metric risk
- Fig. 9: skew tolerance
- full 9-axis table
- accuracy denominator/censoring table
- inverse recovery table
- detailed cost caveat

---

## 11. GUI 시연 runbook

### 준비

1. Windows PC에서 bundle을 포함한 도구를 실행한다.
2. 화면에서 `read / SNMR`을 선택하고 target `0.625 V`, axis `cn`을 둔다.
3. `Vmin 예측`으로 read/write 결과를 먼저 보여준다.
4. `선택 축 inverse`를 눌러 scan curve, target line, root marker를 보여준다.
5. `2D 단면 계산`을 눌러 `cn × pu` 단면이 9D 전체가 아니라 조건부 slice임을 말한다.
6. 지식 패널에서 Sobol 순위와 scenario를 한 번씩 보여준다.

### 화면별 말할 문장

| 화면 | 말할 문장 |
|---|---|
| Read/Write Vmin cards | “같은 좌표를 두 mode model에 질의합니다. read/write는 학습 온도와 reference batch가 다름을 유지합니다.” |
| inverse sweep | “먼저 scan해서 실제 bracket이 있는지 확인합니다. 곧바로 bisection을 믿고 하나의 해를 강요하지 않습니다.” |
| root result | “이 값은 다른 8축을 고정한 경계입니다. 9개 실제 원인을 추정했다는 뜻은 아닙니다.” |
| 2D heatmap | “다른 7축을 고정한 단면입니다. 색은 Vmin point estimate이고 target crossing cell을 표시했습니다.” |
| sensitivity tab | “ST는 interaction 포함이라 합쳐서 100%가 아닙니다.” |
| scenario tab | “이 비율은 DTCO candidate의 surrogate point estimate이지 process cost 최적화가 아닙니다.” |

### 발표 실패 방지

- 2D grid 버튼은 발표 시작 전에 한 번 눌러 warm-up한다.
- 예상치 못한 `no_root`는 오류가 아니라 결과다. “현재 bounds에서는 이 축 하나만으로 target을 가로지르지 않습니다”라고 말한다.
- `below grid`/`above grid`는 숨기지 않는다. “정확한 Vmin값이 아니라 censoring 상태”라고 말한다.
- 네트워크가 없어도 GUI는 localhost만 사용한다.

---

## 12. 예상 질문과 답변

### Q1. “이건 HSPICE를 대체합니까?”

**답:** 아닙니다. HSPICE/PDK MC가 label을 만들고, surrogate는 그 expensive label을 반복 질의 가능한 함수로 바꿉니다. final sign-off와 변경된 process 후보의 검증에는 원 회로 simulation이 필요합니다.

### Q2. “왜 neural network가 아니라 GP인가요?”

**답:** 이 데이터 규모와 smooth process window에서는 GP가 자연스러운 interpolation baseline입니다. 다만 이 연구의 일부 결과는 μ·σ를 주는 다른 regressor에도 적용됩니다. 실제로 quadratic response surface 비교에서는 GP가 압도적이지 않았습니다. GP의 pointwise uncertainty/noise-aware likelihood 장점은 이 dataset에서 완전히 활용되었다고 과장하지 않습니다.

### Q3. “왜 Vmin을 바로 학습하지 않나요?”

**답:** Vmin 하나로 학습하면 평균 margin 변화와 mismatch spread 변화를 분해하기 어렵습니다. μ·σ를 따로 예측하면 influence와 mitigation hypothesis를 더 해석 가능하게 만듭니다.

### Q4. “3.98 mV면 silicon Vmin도 4 mV 정확한가요?”

**답:** 아닙니다. 동일한 Gaussian μ/σ definition으로 만든 reference simulation Vmin에 대한 hold-out RMSE입니다. tail distribution, PDK/model discrepancy, aging, silicon systematic variation은 별도다.

### Q5. “Sobol 0.272는 local mismatch가 27.2% 책임이라는 뜻인가요?”

**답:** 아닙니다. 이 design box와 independent uniform input에서 z(0.625 V) variance에 대한 total-order index입니다. interaction이 포함되어 다른 ST와 중복될 수 있고, 생산 lot 불량률의 비율이 아닙니다.

### Q6. “inverse가 실제 불량의 원인을 찾아주나요?”

**답:** 다른 변수들이 알려져 있고 고정됐다는 조건에서 설계 boundary를 찾습니다. Vmin 하나만으로 9개 원인의 실제 조합을 유일하게 진단하지는 못합니다.

### Q7. “10.9% local-σ 개선이 cheapest solution인가요?”

**답:** surrogate 좌표에서 요구 변화량이 작은 single-axis candidate일 뿐입니다. 제조 비용·area·delay·feasibility를 이 모델이 계산하지 않았으므로 cheapest라고 주장할 수 없습니다.

### Q8. “53배 절감이 실제 runtime 53배입니까?”

**답:** sample-count budget 비율입니다. 실행시간·license queue·parallelism을 포함한 wall-clock measurement은 아니며 MC depth 부분은 noise-emulation이다.

---

## 13. 발표 전에 수정/숨김 처리할 원고 표현

| 발견 위치 | 문제 | 발표에서는 이렇게 말하기 |
|---|---|---|
| `make_docx.js` Vmin 설명 | `Vmin=μ−kσ` 혼동 | “Vmin은 μ−kσ=0의 VDD crossing” |
| `make_docx.js` 3σ 예시 | 5 mV 경계 → ±15 mV 규격으로 잘못 확장 | distribution σ와 deterministic boundary를 분리; 근거 없는 3σ 숫자 삭제 |
| sk label | N/P skew로 표기 | PG–PD NMOS Vth skew |
| input 예 | gate length/tox 직접 input처럼 보임 | 이 구현의 9축 이름을 그대로 표시 |
| sensitivity 결론 | local mismatch가 global axis보다 모두 중요 | local NMOS mismatch가 **PMOS Vth**보다 큼; cn은 가장 큼 |
| four-corner RMSE | 네 corner를 모두 scoring한 것처럼 보임 | four evaluated, three uncensored scored per mode |
| cost | 53× faster simulation | sample-count reduction candidate with RMSE price |
| `+-0.97 mV` | 부호 오타 | `−0.97 mV` 또는 bias signless notation |

---

## 14. 참고자료 (일반 원리)

- [GP 예측 평균·uncertainty — scikit-learn 공식 문서](https://scikit-learn.org/stable/modules/gaussian_process.html)
- [Sobol S1/ST 정의 — SALib 공식 문서](https://salib.readthedocs.io/en/latest/user_guide/basics.html)
- [Sobol 입력 분포 설정 — SALib 공식 문서](https://salib.readthedocs.io/en/latest/user_guide/advanced.html)
- [bisection bracket 조건 — SciPy 공식 문서](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.bisect.html)
- [tail extrapolation 일반 주의 — NIST](https://www.itl.nist.gov/div898/handbook/apr/section4/apr43.htm) — SRAM-specific evidence가 아니라 일반 통계 주의사항이다.

## 15. 이 해설집의 검증 범위

이 문서는 current result JSON, figure generation code, current DOCX와 model implementation을 대조하여 작성했다. HSPICE 재실행, 새 silicon measurement, full retraining은 수행하지 않았다. 발표에서 결과를 새 실험처럼 말하지 않고, source file과 definition을 보존한다.
