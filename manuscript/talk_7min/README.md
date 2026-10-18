# talk_7min — 7분 사내 발표회 자료 (2026-10-18)

**최신 논문 기준은 `../SRAM_Vmin_IEEE_KR.docx`(= `../results/*.json`)다.** `paper_*.md`는 D-16 이전
수치라 쓰지 않는다. 이 폴더만 보면 발표 준비가 끝나도록 모았다. 5분 판(`../presentation/`)은 그대로 둔다.

## 무엇이 들어 있나

| 파일 | 내용 |
|---|---|
| `SRAM_Vmin_7min_KR.pptx` / `.pdf` | 발표 자료 14장. 흰 배경, 강조색은 navy 하나만 쓴다. 노트에는 7분 맞춤판 대본이 들어 있다 |
| `SCRIPT_7min_KR_trim.md` | **발표용 대본 (7분 맞춤판, 약 2,500자, 7.7분)**. 고친 뒤 `make_deck.py`를 다시 돌리면 노트에도 반영된다 |
| `SCRIPT_7min_KR.md` | 전체판 대본 (약 3,300자, 10분). 설명이 더 필요할 때 참고 |
| `lab/scenario_lab.py` | 시나리오 test GUI (아래) |
| `figs/` | 장표에 들어가는 그림. `lab_*.png`와 `lab_summary.json`은 Lab이 만든다 |
| `make_figs.py` · `make_deck.py` | 그림과 PPT 생성. 시나리오 수치는 `lab_summary.json`에서 읽는다 (손으로 옮겨 적지 않음) |

## 흐름 (사용자와 한 장씩 합의, 2026-10-18)

| 장 | 제목 (명사형 — 결론 문장은 각 장 아래 강조 줄에) |
|---|---|
| 1 | 표지: 논문 제목 |
| 2 | 배경: FinFET Low power VOC와 SRAM cell 검토 수요 |
| 3 | 문제: Monte Carlo 기반 Vmin 검토의 비용 한계 |
| 4 | 제안: 순·역방향 Vmin 추정 model |
| 5 | 방법: 중심치·산포 기반 Vmin 추정 구조 |
| 6 | physics-guided 요소: 학습하지 않는 Vmin 계산과 단조성 (최종 model에 실제로 쓴 네 가지만) |
| 7 | 입력 축: NMOS 공통 · PD–PG skew · PMOS 구성과 범위 (+ 표본 선정: random, 사분면 가중 45 %) |
| 8 | model 구성: GP와 ARD (아파트 시세 비유는 말로만) |
| 9 | 검증: 기존 Monte Carlo 대비 Vmin 추정 정확도 (silicon 비교 아님) |
| 10 | 적용 사례: Low Vmin VOC (0.625 → 0.575 V, 논문 시나리오) |
| 11 | knob별 Vmin 개선 효과 비교 |
| 12 | 목표 Vmin 달성에 필요한 개선량 (read·write 합친 contour) |
| 13 | 장점: 조건 변경 검토의 유연성과 학습 비용 |
| 14 | 정리: model 기반 Vmin 검토의 의의 |

6장 주의: 논문 D판 §II-C의 "단조성 패널티 · 코너 앵커링 · 선형 σ 정규화"는 최종 학습 코드(`code/v_b_forward.py`)와
최종 원고(`make_docx.js`)에 없다. 장표에는 넣지 않았다.

SNMR 분포 꼬리, corner 밖에서 생기는 분산, censoring 이야기는 넣지 않는다.

## Scenario Lab — 이것저것 돌려 보고 장표에 넣을지 고르기

```bash
.venv/bin/python manuscript/talk_7min/lab/scenario_lab.py     # 브라우저가 열린다 (127.0.0.1만)
```

- **기준 조건**: 목표 Vmin, read/write 중 무엇을 볼지, 각각의 corner(FFG/FSG/SFG/SSG/nominal),
  나머지 축의 고정값.
- **lever**: 축 하나, `l_com+lpu`처럼 묶은 축, `corner`(global Vth corner 폭 축소).
- **① lever 순위**: 목표를 통과하려면 knob마다 얼마나 움직여야 하는지 보여 준다. **② knob별 Vmin 곡선**:
  read와 write 선을 함께 그려 줄다리기 관계를 보여 준다. **③ 두 knob map**: 통과 영역과 가장 가까운 통과점을 보여 준다.
  **④ window**: 고른 knob을 목표까지 개선하기 전후의 read·write 합친 contour를 보여 준다 (10장 그림).
- 실행할 때마다 `lab/exports/<시각>_<종류>/`에 `figure.png`, `data.csv`, `params.json`이 쌓인다(gitignore).
  장표에 넣을 그림은 `figs/`로 복사한 뒤 `make_deck.py`에서 파일 이름을 바꾼다.
- 발표 그림(`lab_rank.png`, `lab_window.png`)과 장표 수치(`lab_summary.json`)는 `--defaults`로 다시 만든다. 목표는 `--target`으로 바꿀 수 있고, 기본값은 논문 시나리오의 0.575 V다.
- 모델은 `../gui/demo_bundle/`을 쓴다. 기밀 bundle이니 외부로 내보내지 않는다.

`lab/test_scenario_lab.py`는 Lab이 논문 §IV-B 수치(σN −10.89 %, σN+σP −7.79 %, corner −46.9 %,
σP 단독 불가)를 그대로 재현하는지 확인한다.

## 다시 만들기

```bash
.venv/bin/python manuscript/talk_7min/lab/scenario_lab.py --defaults   # 먼저 (make_figs가 lab_summary.json을 읽음)
.venv/bin/python manuscript/talk_7min/make_figs.py
.venv/bin/python manuscript/talk_7min/make_deck.py
```

PDF는 Windows PowerPoint로 내보낸다(LibreOffice 없음).

## 질문이 나오면

- **분포가 Gaussian이 아니면?** 발표에서는 다루지 않는다. 논문 §V-F에 측정과 보정이 있다고만 답한다.
- **leakage도 보나?** 이 model은 Vmin(read · write)만 다룬다. 같은 방식으로 leakage를 출력에 추가하는 게 다음 단계다.
- **역산 결과를 그대로 공정 사양으로 써도 되나?** 안 된다. 나머지 축을 고정한 조건부 경계이고, 기준값은 HSPICE MC다.
- **read와 write 온도가 다르다(125 °C / −40 °C).** 각 mode의 sign-off 온도에서 따로 학습했다.
  binding Vmin은 두 조건 중 나쁜 쪽을 뜻한다.
