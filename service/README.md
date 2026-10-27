# SRAM Vmin Studio — `service/`

논문의 read·write GP surrogate와 physics layer를 그대로 써서 **forward(조건 → Vmin)와
inverse(목표 Vmin → 공정 조건)**를 한곳에서 돌리는 로컬 웹 서비스다. 분석 하나는 JSON
spec 하나다. 실행할 때마다 spec·결과·그림(PNG·PDF)·CSV가 `service/runs/<id>/`에 남고,
그 spec을 CLI에 넣으면 같은 결과가 다시 나온다. 그림은 논문 Fig. 5/10/11과 같은 형식이다.

## 실행

저장소 루트에서:

```bash
.venv/bin/python service/main.py serve            # http://127.0.0.1:8765/
.venv/bin/python service/main.py verify           # 논문 수치가 박힌 preset 전부 재현 (~3분)
.venv/bin/python service/main.py run SPEC.json    # spec 하나 (화면에서 만든 runs/<id>/spec.json도 됨)
.venv/bin/python service/main.py list             # preset 목록
.venv/bin/python service/tests/test_solve.py      # solver 단위 시험 (GP 없이 1초)
```

- WSL에서 띄우면 Windows 브라우저에서 위 주소를 열면 된다 (`--no-browser`로 자동 열기를 끌 수 있다).
- 모델 로드는 원본 데이터 경로가 ~25 s, bundle이 ~1 s다. robust 분석(P(pass), 95 % 기준)은
  서버를 띄운 뒤 처음 한 번 posterior 준비에 20–30 s가 더 든다.
- 서버는 127.0.0.1에만 열린다. 다른 주소를 주면 거부한다 — 모델과 학습 데이터가 기밀이다.

## 폴더

```
service/
├── main.py           CLI — serve · run · verify · list
├── config.toml       모델 위치, 축 목록, PDK corner, 기본값 (시나리오와 무관한 것만)
├── vmin/
│   ├── engine.py     모델 로드 · 배치 Vmin · exact posterior 표본 — GP를 만지는 유일한 곳
│   ├── scenario.py   spec → 기준 좌표 · binding 조건 · lever
│   ├── solve.py      lever solver (single · priority · balanced · min-cost) — GP와 무관
│   ├── analyses.py   분석 카탈로그. 화면의 폼도 여기서 정의된다
│   ├── figures.py    논문 그림 형식 (gen_figures.py와 같은 rcParams·색·선 규약)
│   ├── store.py      runs/<id>/ 저장 · 목록
│   └── server.py     loopback HTTP + 작업 큐 (GP는 worker thread 하나만 씀)
├── web/              화면 — vanilla JS, 외부 CDN 없음
├── scenarios/        preset spec: paper/(LEDGER 대조) · explore/ · user/(화면에서 저장)
├── runs/             실행 결과 (gitignore)
└── tests/test_solve.py
```

새 분석을 넣으려면 `analyses.py`에 `@analysis(...)` 함수 하나를 추가하면 된다. 화면은
카탈로그(`/api/meta`)를 읽어 폼을 만들기 때문에 web/ 쪽은 바꿀 필요가 없다.

## 분석

| kind | 화면 이름 | 묻는 것 | 대표 출력 |
|---|---|---|---|
| `point` | 조건별 Vmin · physics layer | 이 조건들의 Vmin은? | 조건별 Vmin, z(Vop) 곡선, §V-D HSPICE 대조 |
| `sweep` | 1축 sweep · 1축 inverse | 한 축만 움직이면 어디서 목표를 넘나? | 근, 통과 구간, Vmin 곡선 |
| `plane` | 2D process window | 두 축 평면 어디까지 통과하나? | Fig. 5 형식 window, 통과 면적 |
| `levers` | 공정 lever 조합 | 상한이 있는 lever로 목표를 맞추려면? | single·priority·balanced·min-cost 해, P(pass), robust 해, Fig. 10/11 형식 window |
| `retarget` | 제품 retarget | array 크기·yield를 바꾸면? | Mb별 Vmin, 목표를 지키는 최대 array, binding 전환점 |
| `recenter` | Vth target 재조정 | σ 대신 분포 중심을 옮기면? | 최적 이동, 최악 Vmin 변화, 이동 map |
| `roadmap` | 개선 roadmap | 목표를 낮춰 가면 lever가 얼마나 필요한가? | 목표별 필요량, 도달 불가 지점 |
| `sensitivity` | 민감도 · exchange rate | 어느 축이 가장 민감하고 lever끼리 교환비는? | 국소 기울기, 저장된 Sobol S_T |

## spec

모든 분석이 공유하는 키 (없으면 `config.toml`의 기본값):

```jsonc
{
  "kind": "levers",
  "title": "실행 이름 (선택)",
  "target": 0.575,                    // V — 모든 binding 조건이 이 값 이하여야 통과
  "reference_vmin": 0.625,            // V — 오늘 spec (회색 점선, roadmap 기준)
  "z": {"array_mb": 128, "yield": 0.99, "lobe": false, "value": null},   // value를 주면 Z 직접
  "base": {"reference": "mode_nominal", "overrides": {"l_com": 1.05}},   // 나머지 축 고정값
  "checks": "limiting",               // limiting | all_corners | nominal | [{mode, corner, point, label}]
  "modes": ["read", "write"],
  "levers": [
    {"id": "local_N", "label": "local N σ", "type": "scale", "axes": ["l_com"], "max_change": -0.10, "weight": 1}
  ]
}
```

lever 세 종류 — `max_change`는 부호가 있는 상한이다 (scale·pull은 비율, shift는 mV):

| type | 의미 | 예 |
|---|---|---|
| `scale` | 축 값 × (1 + 변화) | local σ −10 %: `l_com`, `-0.10` |
| `pull` | corner와 기준 좌표 사이 거리 × (1 + 변화) — global 분포 폭 축소 | global N −20 %: `cn`, `-0.20` |
| `shift` | 축 값 + 변화 (mV) — 분포 전체 이동 | P Vth target −10 mV: `pu`, `-10` |

`levers` 분석에서 lever 목록 순서가 priority 순서다. forward 분석(point·sweep·plane·retarget·
recenter)에 lever를 적으면 그 변화를 다 적용한 상태(`usage: 1`)에서 계산한다. 분석별 키는
화면의 "spec JSON"을 열거나 `scenarios/`의 예를 보면 된다.

## 논문 재현

`scenarios/paper/`의 preset은 `expect` 블록에 LEDGER 값을 갖고 있다. `verify`가 다시
돌려 허용오차 안에 드는지 본다 (2026-10-28: 4개 preset, 19/19 통과).

| preset | 대조 항목 |
|---|---|
| `v_d_corners` | §V-D corner 예측 8개 중 6개 (N035 포함) |
| `fig10_single_levers` | N035–N039 — kσN −10.89 %, kσP 도달 불가, corner −46.9 %, kσN+kσP −7.79 % |
| `fig11_bounded_levers` | N099–N101 — local N 단독 불가, priority (−10 %, −8.0 %), balanced t = 0.754 |
| `sweep_kSigmaN_inverse` | N036 — 1축 inverse가 lever 해와 같은 kσN = 0.8911 |

서버를 띄우면 저장된 §V-D corner 예측 8개를 다시 계산해 상단에 `self-check 8/8`로 보여 준다.
어긋나면 checkpoint나 config가 바뀐 것이다.

## 모델 소스

`config.toml`의 `model.source`:

- `auto` (기본) — `python/data/final*.xlsx`가 있으면 원본 경로, 없으면 bundle
- `source` — `manuscript/results/surrogate_vb[_write].pth` + 같은 grouped split 재구성.
  checkpoint에 저장된 학습 좌표와 다르면 로드를 거부한다
- `bundle` — `manuscript/gui/demo_bundle/` (xlsx 없는 PC용). `manuscript/gui/prepare_bundle.py`로 만든다

## 한계

- Vmin은 posterior mean 기준 점예측이다. P(pass)는 GP의 epistemic 불확실성만 담는다 —
  학습 데이터 밖의 물리, compact model 오차는 들어 있지 않다.
- 학습 범위 밖 좌표는 외삽이다. 결과에 경고가 붙고, `recenter`는 기본적으로 범위 안 이동만 고른다.
- lever의 공정 비용, leakage·speed trade-off, area 환산은 모델에 없다. `min-cost`의 weight는
  사용자가 정하는 상대 비용일 뿐이다.
- read(125 °C)와 write(−40 °C)는 각자의 sign-off 온도에서 학습됐다. binding은 둘 중 나쁜 쪽이다.
- 고른 해는 HSPICE MC로 확인해야 한다. sign-off를 대신하지 않는다.

## 기존 도구와의 관계

`manuscript/gui/`(Inverse Studio, Windows 발표용 exe)와 `manuscript/talk_7min/lab/`(Scenario Lab)은
그대로 둔다. 이 서비스는 두 도구의 기능(1축 inverse, 공동 contour, lever 순위·window)을 spec 기반으로
다시 묶고 retarget·recenter·roadmap·robust inverse를 더했다. 설계 근거는
`docs/decisions/2026-10-28_vmin_service_design.md`.
