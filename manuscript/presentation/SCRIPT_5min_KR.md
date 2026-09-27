# SRAM Vmin surrogate — 5분 발표 대본

슬라이드 `SRAM_Vmin_5min_KR.pptx`의 노트에도 같은 대본이 들어 있다. 수치 출처는 `SRAM_Vmin_IEEE_KR.docx`.

## 1. (0:00–0:10)

SRAM Vmin을 순방향과 역방향으로 함께 추정하는 physics-guided surrogate를 소개하겠습니다.

## 2. (0:10–0:45)

출발점은 고객 VOC였습니다. Vmin은 더 낮추고, 성능도 같이 올려 달라는 요구였습니다. 목표를 0.575 V로 잡으면 지금은 read가 21 mV, write가 18 mV 모자랍니다. 공정 쪽에서 움직일 수 있는 knob은 셀의 PU, PD, PG마다 Vth, local mismatch, mobility가 있습니다. 그런데 이 중 어느 knob이 Vmin에 가장 잘 듣는지, 얼마나 움직여야 하는지 빨리 비교할 방법이 없었습니다.

## 3. (0:45–1:15)

기존 방법은 둘입니다. 왼쪽 그림처럼 MC는 학습 조건 하나에 수천 번을 돌려야 하고, corner는 별 네 개, 네 점만 봅니다. 오른쪽은 margin 분포입니다. 평균이 같아도 local mismatch로 σ가 커지면 tail이 0을 넘어가고, 그만큼 Vmin이 올라갑니다. corner로는 이게 안 보여서 Vmin을 낙관적으로 잡기 쉽습니다.

## 4. (1:15–1:40)

그래서 simulation은 한 번만 돌리고, 그 결과에 여러 번 묻기로 했습니다. 이 조건의 Vmin은 얼마인지, 어느 축이 Vmin을 흔드는지, 목표를 맞추려면 얼마나 바꿔야 하는지, simulation은 얼마나 줄일 수 있는지. 뒤에서 이 네 가지를 같은 색으로 짚겠습니다.

## 5. (1:40–2:20)

구현은 단순합니다. 입력은 오른쪽 표처럼 Vth shift, local-σ, mobility를 NMOS 공통, pass-gate와 pull-down 사이 skew, PMOS로 나눈 9개 축과 공급 전압입니다. HSPICE MC 결과로 GP 두 개를 학습합니다. 하나는 margin 평균 μ, 하나는 산포 log σ입니다. Vmin은 따로 배우지 않습니다. 그림처럼 μ에서 kσ를 뺀 선이 0이 되는 가장 낮은 전압이 Vmin입니다. 이렇게 나눠 두면 Vmin이 밀린 원인이 중심인지 산포인지 보이고, 역산도 1차원 이분 탐색으로 끝납니다.

## 6. (2:20–2:50)

정확도부터 보겠습니다. 학습에 안 쓴 조건에서 Vmin 오차는 read 3.98 mV, write 5.65 mV RMSE입니다. 학습에서 뺀 PDK corner 네 곳에서도 8.5 mV와 5.8 mV이고, read는 FSG, write는 SFG로 최악 corner를 제대로 짚었습니다. 기준값은 따로 돌린 HSPICE MC입니다.

## 7. (2:50–3:25)

다음은 어느 축이 Vmin을 흔드는지입니다. total-order Sobol 지수로 read margin 분산을 나눠 보면, NMOS local mismatch가 0.272로 corner 축인 PMOS Vth shift 0.200보다 큽니다. corner 두 축을 합쳐도 0.61이 상한이라, 적어도 38 %는 corner 밖에서 나옵니다. 성능 쪽 knob인 mobility 축은 0.015 이하로 작았습니다. VOC 대응 action을 어떤 순서로 볼지 이 결과로 정했습니다.

## 8. (3:25–4:05)

이제 VOC로 돌아가겠습니다. 앞에서 본 read 21 mV, write 18 mV 차이를 없애려면 무엇을 얼마나 바꿔야 할까요. 나머지 축을 고정하고 knob 하나씩 거꾸로 풀면, NMOS local-σ를 10.9 % 줄이는 게 가장 작은 변화였습니다. NMOS와 PMOS에 나누면 각각 7.8 %면 되고, PMOS local-σ만으로는 30 %를 줄여도 닿지 않습니다. 공정 action 후보를 simulation을 더 돌리지 않고 이렇게 바로 비교할 수 있었던 게 가장 쓸모 있었습니다.

## 9. (4:05–4:30)

비용입니다. 기준 학습은 1,700개 조건, 전압 5개, 조건당 MC 5,000개였습니다. 400개 조건, 전압 4개, MC 500개로 줄이면 budget은 53배 줄고 read 오차는 3.5 mV 늡니다. 한 번 학습해 두면 이후 질의에는 MC가 더 들지 않습니다.

## 10. (4:30–4:55)

정리하면, simulation을 한 번 돌려 정확도, 민감도, 역산, 비용 네 가지에 답했고, 실제 VOC에서 어떤 공정 action이 효과적인지 고르는 데 썼습니다. 다만 margin을 Gaussian으로 가정했고, 역산은 나머지 축을 고정한 결과라는 한계가 있습니다. 감사합니다.

---

공백 제외 1574자 · 분당 약 330자 기준 약 4.8분.