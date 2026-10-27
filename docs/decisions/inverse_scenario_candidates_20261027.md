# Inverse query 활용 시나리오 후보 (2026-10-27)

Fig. 11(`manuscript/code/v_e_scenario_process.py`, lever별 상한을 둔 50 mV 시나리오)을 만든 뒤 나온 논의다.
"inverse query를 더 잘 쓰는 방법이 뭔가?"
아래 수치는 **탐색용으로 한 번 돌려 본 값이고 LEDGER에 올라간 결과가 아니다**. 논문에 쓰려면
`manuscript/code/`에 스크립트를 따로 두고 다시 유도해야 한다.
모두 post-D-16 체크포인트(`surrogate_vb[_write].pth`)로 계산했고 재학습은 하지 않았다.

## 후보와 1차 탐색 결과

| # | 시나리오 | 답하는 질문 | 추가 sim | 1차 탐색 결과 |
|---|---|---|---|---|
| 1 | **Robust inverse** | "몇 % 개선해야 **95 % 확신**으로 통과하나" | 없음 | inverse 해는 정의상 target 위에 놓이므로 P(pass)가 약 0.5다. 우선순위 해는 0.46, 균형 해는 0.48, local N만 10 %는 0.22. binding Vmin의 5–95 % 폭은 약 ±6 mV |
| 2 | **Product retarget (Z inversion)** | "같은 cell로 1 Mb L1과 512 Mb LLC를 만들면 Vmin과 binding mode가 어떻게 바뀌나" | 없음 (Z는 physics layer 입력) | 1 Mb 0.567 V(write) → 128 Mb 0.596(read) → 2 Gb 0.624(read). **binding mode가 32–128 Mb 사이에서 write에서 read로 넘어간다.** 공정 변경 없이 0.575 V를 맞추려면 Z = 5.855, 즉 약 4 Mb 규모 |
| 3 | **Vth targeting + leakage 제약** | "σ를 줄이기 전에 Vth target만 옮기면 얼마나 버나" | Vmin 쪽은 없음. leakage 모델은 필요 | 전체 분포를 N −9 mV, P −15~16 mV 옮기면 6.5–7.7 mV를 번다. local N −10 %와 합치면 global tightening 없이 0.570 V. **대가는 leakage 증가**이고, 최적점이 학습 box 경계(FFG pu ≈ −61 mV)에 닿아 있어 일부 외삽이다 |
| 4 | Vmin fail 진단 (관측값 → 원인) | "silicon read/write Vmin이 나빠졌을 때 원인이 global shift인가 local σ인가" | 없음 (MCMC on surrogate) | 기반은 §V-E 좌표 복원(2.6/3.2 mV). 실측 데이터가 없으면 synthetic demo에 그친다(D-13) |
| 5 | WAT/ET spec window | "N·P Vth 관리 한계를 각각 몇 mV로 잡으면 Vmin이 보장되나" | 없음 | Fig. 5 pass 영역에 내접하는 최대 직사각형을 구하면 된다. 아직 계산하지 않음 |
| 6 | 개선 roadmap | "−10…−60 mV 목표마다 필요한 lever 조합" | 없음 | Fig. 11을 target sweep으로 확장한 것. 상한 때문에 도달할 수 없게 되는 지점이 나온다 |

> **정정 (2026-10-28)**: #1의 P(pass)·분포 폭은 gpytorch 기본 CG 경로로 계산한 값이라 σ posterior가 ~34 % 넓었다.
> exact posterior로는 priority 0.45 · balanced 0.50 · local N 단독 0.20이다. 상세와 95 % 기준 해는
> `2026-10-28_vmin_service_design.md`. 이 후보들은 `service/`(SRAM Vmin Studio)의 분석으로 구현됐다.

범위 밖: assist(WLUD/NBL)는 manuscript의 9D surrogate에 축이 없어 데이터가 새로 필요하다. EOL·aging guardband는 D-05와 충돌한다.

## 계산 방법 (재현용 메모)

- #1: 5개 Vop에 걸친 joint posterior(μ GP, log σ GP)에서 4,000회 sampling해 Vmin 분포를 얻었다. epistemic만 넣었고 μ와 σ는 독립으로 취급했다.
- #2: `derive_z_target(mb, 0.99)`로 Z를 바꾸고, 4개 코너 × 2개 모드의 worst를 취했다.
- #3: 4개 코너 전체에 (δcn, δpu)를 더하고 4개 코너 × 2개 모드의 max를 최소화했다. 1.5 mV 격자로 찾은 뒤 0.25 mV로 좁혔다.

## 권고

- 논문: **#1 + #2**. 둘 다 sim 비용이 0이다. #2는 "physics layer를 학습하지 않아서 Z로 거꾸로 풀 수 있다"(README의 3요건 중 가역성)를 바로 보여 준다. #1은 Fig. 11의 "경계 판정" 한계를 확률로 바꿔 준다.
- 신뢰도: inverse 해 1–2개를 in-house HSPICE로 확인하는 것이 가장 강한 근거다.
- 실무·발표: #3. 다만 leakage 모델을 정해야 한다.
- 결정은 사용자 몫이다(미정).
