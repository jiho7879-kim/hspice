# SRAM Vmin — 7분 사내 발표 대본

슬라이드 `SRAM_Vmin_7min_KR.pptx`의 노트에 같은 대본이 들어간다(`make_deck.py`가 이 파일을 읽는다).
사용자와 한 장씩 합의하며 만든다. 합의한 뼈대(12장)는 `README.md`에 있다.

## 1. (0:00–0:22) 표지

안녕하십니까. 오늘 말씀드릴 내용은 공정 변동 하의 SRAM Vmin 순·역방향 추정을 위한 physics-guided framework입니다. 공정 조건이 바뀌었을 때의 Vmin을 추정하고, 거꾸로 목표 Vmin을 맞추는 공정 조건도 추정할 수 있는 model입니다.

## 2. (0:22–0:47) 배경

제가 맡고 있는 FinFET 공정은 node를 가리지 않고 Low VDD, Low Vmin, Low leakage를 요구하는 VOC가 계속 들어오고 있습니다. 이에 대응하려면 기존 cell을 개선하거나 신규 cell을 개발해야 하고, 그만큼 simulation 단계에서 검토해야 할 조건도 많아졌습니다.

## 3. (0:47–1:36) 문제

예를 들어 SRAM cell에서는 pull-up, pull-down, pass-gate마다 Vth, local mismatch, mobility를 조정할 수 있어서, 무엇을 얼마나 바꿀지 여러 경우를 비교해 봐야 합니다. 그런데 조건 하나의 Vmin을 확인하려면 VDD를 5개 바꿔 가며 VDD마다 Monte Carlo simulation을 5,000번씩, 모두 2만 5천 번을 수행해야 합니다. 이 연구에서 학습에 쓴 조건만 1,700개입니다. 검토할 조건이 늘어날수록 비용도 그대로 늘어나서, 실제로 시도해 볼 수 있는 조건은 몇 개로 제한됩니다. 이 연구는 그중 Vmin 검토를 빠르게 하는 데 집중했습니다.

## 4. (1:36–2:29) 제안

그래서 Monte Carlo simulation을 한 번 수행하고, 그 결과로 Vmin model을 만들었습니다. 이 model은 두 방향의 추정이 모두 가능합니다. 순방향 추정은 공정 조건이 주어지면 그 조건에서의 Vmin을 찾는 것입니다. 예를 들어 NMOS local mismatch를 10 % 줄이면 Vmin이 얼마가 되는지 바로 알 수 있습니다. 역방향 추정은 반대로 목표 Vmin이 주어지면 그 목표를 맞추는 공정 조건을 찾는 것입니다. Vmin을 0.575 V로 맞추려면 NMOS local mismatch를 얼마나 줄여야 하는지 구할 수 있습니다. 두 방향 모두 Monte Carlo simulation을 다시 수행하지 않고 model 안에서 계산합니다.

## 5. (2:29–3:23) 방법

기존에 Vmin을 추정할 때는 Vop를 sweep하면서, SNMR과 Vtrip의 중심치를 산포로 나눈 Z-score를 구합니다. 그리고 memory density 등에 따라 정해지는 target Z를 처음으로 만족하는 전압을 Vmin으로 찾습니다.

그래서 model도 Vmin 자체를 학습하지 않고, Vmin을 추정하는 데 쓰는 중심치와 산포를 학습했습니다. Vmin은 기존과 같은 방식으로 계산합니다. 이렇게 하면 세 가지가 좋아집니다. 첫째, target Z가 바뀌어도 model을 다시 만들 필요가 없습니다. 둘째, 중심치와 산포는 조건에 따라 부드럽게 변해서 더 정확하게 학습됩니다. 셋째, Vmin이 움직인 원인이 중심치 쪽인지 산포 쪽인지 보입니다.

## 6. (3:23–4:26) physics-guided 요소

이 framework를 physics-guided라고 부르는 이유는, 물리로 정해진 부분은 학습시키지 않았기 때문입니다. 먼저 Vmin 계산식입니다. 중심치를 산포로 나눈 z가 target Z를 처음 넘는 전압이 Vmin인데, target Z는 array 크기와 yield 목표로 계산한 값이고, 이 식에는 학습하는 값이 하나도 없습니다. 둘째, 이 계산은 공급 전압에 대해 단조라서, 목표 Vmin에서 공정 조건을 거꾸로 찾는 역방향 추정이 이분 탐색으로 안정적으로 풀립니다. 셋째, 데이터도 물리로 점검했습니다. 공급 전압을 올리면 margin 중심치는 커져야 하므로, 이를 어기는 값은 전사 오류로 보고 바로잡았습니다. 마지막으로 GP는 공정 조건이 조금 바뀌면 margin도 조금 바뀐다는 연속성을 전제로 하고, 산포는 Monte Carlo 오차가 일정해지는 log 축에서 학습했습니다.

## 7. (4:26–5:27) 입력 축

입력 축은 Vth, local mismatch, mobility 세 종류를 NMOS와 PMOS에 나눠 잡았습니다. NMOS는 pull-down과 pass-gate 두 개가 있는데, 같은 NMOS라 대부분 함께 움직입니다. 그래서 기본은 둘을 함께 움직이는 공통 축으로 두고, 완전히 같지는 않으니 둘의 차이를 skew 축 하나로 허용했습니다. 범위는 Vth가 ±60 mV로 PDK corner를 모두 안에 포함하고, local mismatch와 mobility는 ±30 %로 개선 목표의 경계가 범위 안에 들어오도록 넉넉하게 잡았습니다. skew는 공통 범위의 1/4에서 1/3 정도로 작게 두었습니다. 표본은 read와 write 각각 2,000개 조건이고, 각 축은 범위 안에서 random으로 뽑되 Vmin이 나빠지는 사분면에 45 %를 모았습니다.

## 8. (5:27–6:13) model 구성

model은 GP와 ARD라는 방법으로 만들었는데, 아파트 시세에 비유하면 쉽습니다. 우리 집 시세가 궁금할 때 단지의 모든 집이 거래되기를 기다리지는 않습니다. 근처에서 비슷한 평수와 층의 집이 얼마에 팔렸는지 보고 짐작하죠. 비슷한 거래가 없으면 잘 모르겠다고 하고요. GP가 바로 이렇게, Monte Carlo simulation을 수행한 조건으로 수행하지 않은 조건을 추정하고 그 추정이 얼마나 확실한지도 알려 줍니다. 또 역까지 거리는 500 m만 달라도 시세가 크게 바뀌지만, 층수는 몇 층 달라도 비슷합니다. ARD는 이렇게 knob마다 값을 흔드는 정도를 따로 배웁니다.

## 9. (6:13–6:57) 검증

그럼 이 model을 믿을 수 있을까요. 비교 기준은 silicon이 아니라, 같은 조건에서 수행한 기존 Monte Carlo simulation입니다. 학습에 쓰지 않은 조건에서 기존 Monte Carlo simulation으로 구한 Vmin과 model이 추정한 Vmin을 비교했습니다. 오차는 read 3.98 mV, write 5.65 mV였고, 점이 거의 대각선 위에 있습니다. 학습에서 일부러 뺀 PDK corner에서도 오차는 8.5 mV, 5.8 mV였고, Read worst와 Write worst도 맞게 찾았습니다.

## 10. (6:57–7:25) 적용 사례

이제 이 model을 실제 VOC에 적용해 보겠습니다. 앞에서 말씀드린 Low Vmin VOC 중 하나로, Vmin을 0.625 V에서 0.575 V로 50 mV 낮춰 달라는 요청이었습니다. 현재 공정으로는 read가 21 mV, write가 18 mV 모자랍니다. 둘 다 맞춰야 하니 cell Vmin은 read와 write 중 나쁜 쪽으로 봤습니다.

## 11. (7:25–8:11) 어떤 knob이 효과적인가

먼저 어떤 knob이 효과적인지 봤습니다. 나머지 조건은 그대로 두고, knob을 하나씩 바꿔 가며 목표에 닿으려면 얼마나 바꿔야 하는지 역방향으로 추정했습니다. 막대가 짧을수록 조금만 바꿔도 되는 knob입니다.

NMOS local mismatch는 10.9 % 줄이면 목표에 닿았고, NMOS와 PMOS를 함께 줄이면 각각 7.8 %면 됩니다. 반면 Vth와 mobility는 어느 것을 움직여도 목표에 닿지 못했습니다. read가 좋아지는 방향으로 움직이면 write가 나빠지기 때문입니다. read와 write를 함께 낮추는 건 local mismatch뿐이었습니다.

## 12. (8:11–8:52) 얼마나 바꿔야 하나

NMOS local mismatch를 10.9 % 줄이면 실제로 어떻게 달라지는지 보겠습니다. 가로축은 NMOS Vth, 세로축은 PMOS Vth이고, 파란 영역이 read와 write 모두 0.575 V를 만족하는 영역입니다. 현재는 Read worst와 Write worst가 이 영역 밖에 있습니다. NMOS local mismatch를 줄이면 영역이 넓어지면서 두 조건이 모두 경계까지 들어옵니다. 이 그림을 얻는 데 Monte Carlo simulation은 한 번도 더 수행하지 않았습니다.

## 13. (8:52–9:28) 장점

이런 검토는 조건을 바꿔 가며 얼마든지 반복할 수 있습니다. 목표 Vmin을 바꿔 보면, 0.590 V는 NMOS local mismatch를 2.6 %, 0.560 V는 20 %, 0.550 V는 26 % 줄여야 합니다. 이런 비교를 할 때마다 Monte Carlo simulation을 새로 수행하지 않아도 됩니다. 처음 학습에 드는 비용도 줄일 수 있습니다. 학습 조건을 줄이면 비용은 53분의 1이 되고, read 오차는 3.5 mV 늘어나는 데 그칩니다.

## 14. (9:28–10:03) 정리

정리하겠습니다. Monte Carlo simulation 결과로 순방향과 역방향 추정이 모두 가능한 Vmin model을 만들었습니다. 이 model로 효과적인 개선 knob과 필요한 양을 먼저 좁히고, Monte Carlo simulation은 마지막 확인에만 쓰면 됩니다. Low Vmin VOC가 계속 들어오는 지금, 더 많은 조건을 더 빠르게 검토할 수 있습니다. 다만 이 결과는 나머지 조건을 고정했을 때의 값입니다. 감사합니다.

---
