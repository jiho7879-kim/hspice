# 7분 사내 발표회 자료 + Scenario Lab 결정 기록

작성: 2026-10-18 · 산출물: `manuscript/talk_7min/` (README가 진입점)

## 요구

- 최신 논문(`SRAM_Vmin_IEEE_KR.docx` = `results/*.json`) 기준 7분 사내 발표.
- SNMR 분포 꼬리, corner 밖 분산, censoring 이야기는 넣지 않는다.
- 시나리오 test GUI를 고도화한다. 시연용이 아니라, 발표자가 여러 조건을 돌려 보고 장표에 넣을지 고르는 용도다.

## 진행 방식 (시행착오)

처음에 11장을 한 번에 만들었더니 "한국어가 어색하고 흐름이 없다"는 피드백을 받았다. 그래서 뼈대부터 합의한 뒤
한두 장씩 렌더링해서 보여 주며 진행하는 방식으로 바꿨다. 그 과정에서 바뀐 것:

| 항목 | 처음 | 최종 |
|---|---|---|
| 서사 | Vmin 검증·sign-off | **DTCO**: FinFET node마다 Low VDD·Vmin·leakage VOC → cell 개선·신규 개발 → simulation 검토 비용 |
| 표지 | 별도 문구 | 논문 제목 그대로. 배경은 제목의 단어를 순서대로 풀어 간다 |
| 순·역방향 | "묻는다" | "추정"으로 정의: 공정 조건 → Vmin / 목표 Vmin → 공정 조건 |
| GP·ARD | 화면에 비유 표 | 화면에는 한 줄씩만. 아파트 시세 비유는 말로만 설명 |
| 검증 | "오차 4~6 mV" | 비교 대상이 silicon이 아닌 **기존 Monte Carlo**라는 점을 제목·축·각주에 명시 |
| 적용 사례 | 0.575 V → 0.559 V(IR drop 13 %) 시도 | **논문 숫자(0.625 → 0.575 V)로 복귀** |
| read·write | read(SNMR) 위주 | 모든 시나리오를 cell Vmin = max(read, write)로, contour도 두 경계를 합쳐서 |
| 표현 | "read 최악 조건" | **Read worst / Write worst** |
| 제목 | 결론 문장(동사형) | **명사형**. 결론 문장은 각 장 아래 강조 줄에 |
| 스타일 | navy 띠, 색 상자, 초록·주황 | 흰 배경, 강조색 navy 하나, 얇은 선 |

## 결정

- **폴더**: `manuscript/talk_7min/`을 새로 만들었다. 5분 판(`presentation/`)은 그대로 두고, layout helper만 import해서 쓴다.
- **수치는 손으로 옮기지 않는다**: `lab/scenario_lab.py --defaults`가 `figs/lab_summary.json`을 쓰고, `make_deck.py`·`make_figs.py`가 그 파일을 읽는다.
- **대본 두 판**: `SCRIPT_7min_KR_trim.md`(발표용, 슬라이드 노트), `SCRIPT_7min_KR.md`(전체판).
- **physics-guided 장표(6장)**: 최종 model에 실제로 있는 것만 넣었다. 학습하지 않는 Vmin 계산식(Z_t = 6.398), VDD에 대한 단조성(역방향 이분 탐색), μ(V_op) 단조성 데이터 감사(read 31 · write 12셀), GP 연속성과 log σ.
  논문 D판 §II-C의 "단조성 패널티 · 코너 앵커링 · 선형 σ 정규화"는 `code/v_b_forward.py`와 최종 docx에 없으므로 **제외했다**.
- **입력 축 장표(7장)**: common + skew 파라미터화(PG = 공통 + skew, PD = 공통 − skew), 범위는 논문 표 II 그대로(skew ±0.075). 범위 근거는 `legacy_design_audit_20260714.md` §5에서 가져왔다.
- **표본 선정**: Sobol이 아니다. 논문 §II-C에 따르면 사분면별 독립 스트림의 PCG64 pseudo-random이고, 지표별 최악 사분면에 45 %를 둔다. 초기의 저불일치(quasi-random) 가설은 검증에서 지지되지 않아 철회됐다.

## Scenario Lab

`lab/scenario_lab.py` (127.0.0.1 전용). 기능은 lever 순위 · knob별 곡선 · 두 knob map · read/write 합친 window contour이고,
실행마다 그림 · CSV · 조건이 `lab/exports/`(gitignore)에 남는다. `lab/test_scenario_lab.py`가 논문 §IV-B 수치를 재현하는지 확인한다.

## 새로 확인한 것 (논문에 없음)

- Vth와 mobility 7축은 단독으로는 0.575 V에 닿지 않는다. read와 write를 반대 방향으로 움직이기 때문이다. 둘을 함께 낮추는 축은 local-σ뿐이다.
- 목표 Vmin을 바꾸면 필요한 NMOS local-σ 감소량은 0.590 V −2.6 %, 0.560 V −20.0 %, 0.550 V −26.3 %다.

## 남은 일

- 6장 범위 근거 중 "보통 corner 폭 ±10~15 %"와 "PD·PG 상관 0.8~0.9"는 설계 검토 기준값이지 측정값이 아니다. 사용자 확인이 필요하다.
- 논문 표 II의 skew ±0.075와 실제 데이터 ±0.07(반올림)이 어긋난다.
- 맞춤판 대본은 7.7분이라 7분에 맞추려면 더 줄여야 한다.
