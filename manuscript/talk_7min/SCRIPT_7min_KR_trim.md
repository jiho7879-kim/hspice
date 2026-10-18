# SRAM Vmin — 7분 사내 발표 대본 (7분 맞춤판)

`SCRIPT_7min_KR.md`(전체판)를 7분에 맞춰 줄인 판이다. 슬라이드 노트에는 이 판이 들어간다.
내용과 수치는 전체판과 같고, 겹치는 설명과 예시만 덜어냈다.

## 1. (0:00–0:11) 표지

안녕하십니까. 공정 변동 하의 SRAM Vmin 순·역방향 추정을 위한 physics-guided framework를 소개하겠습니다.

## 2. (0:11–0:35) 배경

제가 맡고 있는 FinFET 공정은 node를 가리지 않고 Low VDD, Low Vmin, Low leakage를 요구하는 VOC가 계속 들어오고 있습니다. 그래서 기존 cell을 개선하거나 신규 cell을 개발해야 하고, simulation 단계에서 검토할 조건도 그만큼 늘었습니다.

## 3. (0:35–1:07) 문제

SRAM cell은 pull-up, pull-down, pass-gate마다 Vth, local mismatch, mobility를 바꿀 수 있습니다. 그런데 조건 하나의 Vmin을 보려면 VDD 5개에서 Monte Carlo simulation을 5,000번씩, 모두 2만 5천 번 수행해야 합니다. 조건이 늘수록 비용도 그대로 늘어서, 실제로 시도해 볼 수 있는 조건은 몇 개뿐입니다.

## 4. (1:07–1:35) 제안

그래서 Monte Carlo simulation 결과로 Vmin model을 만들었습니다. 이 model은 두 방향으로 추정할 수 있습니다. 순방향은 공정 조건을 넣으면 그 조건의 Vmin을 찾습니다. 역방향은 목표 Vmin을 넣으면 그 목표를 맞추는 공정 조건을 찾습니다. 두 방향 모두 Monte Carlo simulation을 다시 수행하지 않습니다.

## 5. (1:35–2:12) 방법

기존에는 Vop를 sweep하면서 SNMR과 Vtrip의 중심치를 산포로 나눈 Z-score를 구하고, memory density 등으로 정해지는 target Z를 처음 만족하는 전압을 Vmin으로 찾습니다. 그래서 model도 Vmin을 직접 학습하지 않고 중심치와 산포를 학습했습니다. Vmin은 기존과 같은 방식으로 계산합니다. 이렇게 하면 target Z가 바뀌어도 다시 학습할 필요가 없고, 부드럽게 변하는 값을 학습하니 더 정확합니다.

## 6. (2:12–3:15) physics-guided 요소

이 framework를 physics-guided라고 부르는 이유는, 물리로 정해진 부분은 학습시키지 않았기 때문입니다. 먼저 Vmin 계산식입니다. 중심치를 산포로 나눈 z가 target Z를 처음 넘는 전압이 Vmin인데, target Z는 array 크기와 yield 목표로 계산한 값이고, 이 식에는 학습하는 값이 하나도 없습니다. 둘째, 이 계산은 공급 전압에 대해 단조라서, 목표 Vmin에서 공정 조건을 거꾸로 찾는 역방향 추정이 이분 탐색으로 안정적으로 풀립니다. 셋째, 데이터도 물리로 점검했습니다. 공급 전압을 올리면 margin 중심치는 커져야 하므로, 이를 어기는 값은 전사 오류로 보고 바로잡았습니다. 마지막으로 GP는 공정 조건이 조금 바뀌면 margin도 조금 바뀐다는 연속성을 전제로 하고, 산포는 Monte Carlo 오차가 일정해지는 log 축에서 학습했습니다.

## 7. (3:15–4:16) 입력 축

입력 축은 Vth, local mismatch, mobility 세 종류를 NMOS와 PMOS에 나눠 잡았습니다. NMOS는 pull-down과 pass-gate 두 개가 있는데, 같은 NMOS라 대부분 함께 움직입니다. 그래서 기본은 둘을 함께 움직이는 공통 축으로 두고, 완전히 같지는 않으니 둘의 차이를 skew 축 하나로 허용했습니다. 범위는 Vth가 ±60 mV로 PDK corner를 모두 안에 포함하고, local mismatch와 mobility는 ±30 %로 개선 목표의 경계가 범위 안에 들어오도록 넉넉하게 잡았습니다. skew는 공통 범위의 1/4에서 1/3 정도로 작게 두었습니다. 표본은 read와 write 각각 2,000개 조건이고, 각 축은 범위 안에서 random으로 뽑되 Vmin이 나빠지는 사분면에 45 %를 모았습니다.

## 8. (4:16–4:48) model 구성

model은 GP와 ARD로 만들었습니다. 아파트 시세에 비유하면, 우리 집 시세는 근처에서 비슷한 집이 얼마에 팔렸는지 보고 짐작합니다. GP도 Monte Carlo simulation을 수행한 조건으로, 수행하지 않은 조건을 추정합니다. 또 역까지 거리는 조금만 달라도 시세가 크게 바뀌지만 층수는 몇 층 달라도 비슷합니다. ARD는 이렇게 knob마다 영향을 주는 정도를 따로 배웁니다.

## 9. (4:48–5:15) 검증

비교 기준은 silicon이 아니라, 같은 조건에서 수행한 기존 Monte Carlo simulation입니다. 학습에 쓰지 않은 조건에서 두 결과를 비교하니 Vmin 오차는 read 3.98 mV, write 5.65 mV였습니다. 학습에서 뺀 PDK corner에서도 Read worst와 Write worst를 맞게 찾았습니다.

## 10. (5:15–5:35) 적용 사례

실제 VOC에 적용해 보겠습니다. Vmin을 0.625 V에서 0.575 V로 50 mV 낮춰 달라는 요청이었고, 현재 공정으로는 read가 21 mV, write가 18 mV 모자랍니다. 둘 다 맞춰야 하니 cell Vmin은 둘 중 나쁜 쪽으로 봤습니다.

## 11. (5:35–6:15) 어떤 knob이 효과적인가

나머지 조건은 그대로 두고, knob을 하나씩 바꿀 때 목표에 닿으려면 얼마나 바꿔야 하는지 역방향으로 추정했습니다. 막대가 짧을수록 효과적인 knob입니다. NMOS local mismatch는 10.9 %를 줄이면 되고, NMOS와 PMOS를 함께 줄이면 각각 7.8 %면 됩니다. 반면 Vth와 mobility는 어느 것도 목표에 닿지 못했습니다. read가 좋아지면 write가 나빠지기 때문입니다. read와 write를 함께 낮추는 건 local mismatch뿐이었습니다.

## 12. (6:15–6:47) 얼마나 바꿔야 하나

가로축은 NMOS Vth, 세로축은 PMOS Vth이고, 색칠한 영역이 read와 write 모두 0.575 V를 만족하는 곳입니다. 지금은 Read worst와 Write worst가 영역 밖에 있지만, NMOS local mismatch를 10.9 % 줄이면 영역이 넓어져 둘 다 경계 안으로 들어옵니다. 이 결과를 얻는 데 Monte Carlo simulation은 한 번도 더 하지 않았습니다.

## 13. (6:47–7:13) 장점

이런 검토는 조건을 바꿔 가며 얼마든지 반복할 수 있습니다. 목표를 0.560 V로 낮추면 NMOS local mismatch를 20 %, 0.550 V면 26 % 줄여야 한다는 것도 바로 나옵니다. 처음 학습 비용도 줄일 수 있어서, 학습 조건을 줄이면 비용은 53분의 1이 되고 read 오차는 3.5 mV 늘어나는 데 그칩니다.

## 14. (7:13–7:40) 정리

정리하겠습니다. Monte Carlo simulation 결과로 순방향과 역방향 추정이 모두 가능한 Vmin model을 만들었습니다. 이 model로 효과적인 knob과 필요한 양을 먼저 좁히고, Monte Carlo simulation은 마지막 확인에만 쓰면 됩니다. 다만 이 결과는 나머지 조건을 고정했을 때의 값입니다. 감사합니다.

---
