# Read/write 공동 contour 및 다축 후보 탐색 GUI 결정

작성: 2026-09-27  
대상: `manuscript/gui/`의 Windows 발표용 로컬 SRAM Vmin 도구

## 요청과 성공 기준

사용자는 기존 GUI가 한 mode의 조건부 2D 단면과 한 축 inverse만 푸는 상태에서 다음을 요청했다.

1. **동일한 물리 좌표에서** read/SNMR와 write/Vtrip의 target-Vmin contour를 함께 계산·표시한다.
2. 하나의 축만 움직이는 root가 아니라, 두 축·세 축 이상을 함께 바꿔 read와 write가 모두 target Vmin을 만족하는 조합을 찾는다.

성공 기준은 read/write에 서로 다른 mode별 median을 몰래 채우지 않고 같은 9D row를 평가하는 것, censoring을 가짜 숫자로 바꾸지 않는 것, 기존 one-axis API/UI를 보존하는 것, 그리고 다축 결과를 전역 최적해·원인 진단·sign-off로 과장하지 않는 것이다.

## 확인한 기존 상태

- `/api/predict`는 이미 UI에서 같은 좌표로 read/write를 함께 질의한다.
- `/api/plane`와 `/api/inverse`는 선택한 한 mode만 처리한다.
- 각 mode는 training bounds, reference median, voltage grid가 다르다. 그러므로 각각의 `plane()`에 partial coordinate를 넘겨 결합하면 서로 다른 9D 점을 비교하게 된다.
- 기존 2D 표시는 정확한 isoline이 아니라 target을 가로지를 수 있는 grid cell을 점선으로 표시한다.

## 선택지와 결정

### 1. 공동 contour의 좌표 기준

1. mode별 `plane()` 결과 두 개를 UI에서 겹친다. **기각:** 누락 축이 read/write별 median으로 채워지고 axis bounds도 달라 비교 좌표가 달라진다.
2. 하나의 full 9D coordinate를 먼저 결정하고, 두 모델 training-box의 교집합에서 두 축만 sweep한다. **채택:** 같은 row를 두 surrogate에 넣을 수 있고, sweep 축은 양쪽에서 in-domain이다.
3. 한 mode의 bounds를 그대로 쓴다. **기각:** 다른 mode에서 불필요한 외삽을 만든다.

공동 contour API는 fixed coordinate가 어느 mode의 box 밖인지 별도로 보고한다. 이 경고는 숨기지 않지만, 사용자가 현재 조건을 탐색하는 것은 허용한다.

### 2. 공동 만족의 의미

채택 기준은 같은 target `T`에 대해

```text
Vmin_read(p) <= T  AND  Vmin_write(p) <= T
```

이다. target은 양쪽 voltage grid 안에 있어야 한다. `below_grid`는 실제 Vmin이 하한보다 낮다는 뜻이므로 이 조건에서는 pass로 분류할 수 있지만, 화면에는 계속 `< lower-grid V`로만 표시한다. `above_grid`, non-finite 예측, 또는 supply grid가 비단조인 row는 pass로 인증하지 않는다.

별도 read/write target은 이번 변경의 범위를 넓히지 않기 위해 추가하지 않는다. API 구조는 이후 mode별 target map으로 확장할 수 있게 유지한다.

### 3. 다축 해를 찾는 방법

1. 고차원 연속 최적화로 단일 해를 반환한다. **기각:** GP의 비단조성, 비유일성 및 제조 비용 모델 부재 때문에 “최적해”라는 잘못된 인상을 준다.
2. 모든 선택 축의 Cartesian grid를 무제한 탐색한다. **기각:** 4축 이상에서 비용이 지수적으로 커진다.
3. 2–3축은 제한된 Cartesian grid, 4–9축은 결정론적 space-filling 표본으로 **feasible sample set**을 반환한다. **채택:** 조합을 실제로 보여주면서 요청 크기를 제한하고 재현 가능하다.

결과는 연속 방정식의 유일 root가 아니라 **표본 격자/설계 안에서 발견한 공동 만족 후보**다. 반환 후보는 선택 축의 shared-span으로 정규화한 baseline 이동 거리로 정렬하며, 제조 비용 최소 또는 전역 최소라고 부르지 않는다. 선택하지 않은 축은 정확히 고정한다.

## API/UI 계약

- `POST /api/joint-plane`: full shared coordinate, `x_axis`, `y_axis`, `target_vmin`, points를 받아 공통 grid, mode별 Vmin/status, joint feasibility, bounds·외삽 상태를 반환한다.
- `POST /api/combination`: full shared coordinate, distinct axes 2–9개, target, bounded budget을 받아 sample/feasible/unknown 수와 소수의 대표 후보를 반환한다.
- UI는 파란 read와 주황 write contour를 같은 plot에 겹치고 joint-pass 영역을 별도로 표시한다. finite/in-range vertex가 없는 구간은 contour처럼 이어 그리지 않는다.
- UI의 다축 후보표에는 각 후보의 read/write status, 선택 축 변화량, sample method/budget을 표시하며 후보 적용은 사용자가 명시적으로 누르게 한다.
- 기존 `/api/plane`, `/api/inverse`, one-axis 화면은 유지한다.

## 안전성과 제외 범위

- read 125 °C와 write −40 °C의 서로 다른 batch/model 비교는 설계 탐색용이며 공동 실측 검증 또는 final sign-off가 아니다.
- 모델, raw data, bundle, Z target(`manuscript/gui`의 `6.3984`)은 변경하지 않는다.
- 네트워크·외부 bind·새 의존성·전역 9D 최적화·제조 비용 모델은 추가하지 않는다.
- 2D/3D 이상의 결과는 fixed-axis 조건부 slice 또는 sampled feasible set이라고 명시한다.

## 검증 계획 및 기록

변경 전 `python -m unittest manuscript.gui.tests.test_demo_engine -v`는 4 passed, 1 intentional integration skip이었다. 이 환경에는 `pytest`가 설치되어 있지 않아 `python -m pytest`는 실행할 수 없었다.

변경 후에는 synthetic model/monkeypatch 기반으로 common-row, bounds 교집합, censoring·비단조 exclusion, fixed-axis 보존, 입력 오류, deterministic sampling을 검증한다. 실제 trusted bundle smoke와 Windows standalone smoke는 bundle/Windows 환경이 있을 때의 별도 gate로 남긴다.

## 구현 결과와 검토 기록

구현은 다음과 같이 결정 계약을 그대로 반영했다.

- `DemoEngine.joint_plane()`은 한 번 merge한 9D coordinate와 selected-axis shared bounds를 사용해 두 model에 같은 rows를 보낸다. API는 mode별 value/status/finite/monotone/feasible mask와 joint mask를 함께 돌려준다.
- `DemoEngine.solve_combination()`은 2–3축에서 bounded Cartesian grid, 4–9축에서 seed 고정 Latin-hypercube 표본을 쓴다. 현재 입력점이 selected shared interval 안이면 hard budget 안에서 반드시 한 표본으로 포함한다. 최대 4,096개 row를 128-row prediction chunk로 처리하고, 최대 12개의 낮은 normalized-distance 후보만 반환한다.
- `below_grid`는 target grid-valid 조건에서만 feasible로 세되 표시 값은 `null`로 유지한다. `above_grid`, non-finite μ/σ/z, 양수가 아닌 σ, supply-grid 비단조 sample은 unknown이며 feasible로 인증하지 않는다.
- frontend는 blue/read·orange/write의 bilinear-interpolated target contour를 finite+monotone node 사이에서만 그리고, green은 joint-feasible sample node 영역만 표시한다. bilinear saddle cell은 asymptotic decider로 연결하여 가짜 diagonal crossing을 피한다.
- 입력이 바뀌면 forward, inverse, plane, combination 결과를 각각 stale로 추적해 JSON export가 새 forward prediction만 보고 오래된 inverse/plane/candidate를 fresh로 표시하지 않게 했다.

### 시도와 수정

1. managed sandbox에서 loopback HTTP smoke를 처음 실행했을 때 socket bind가 `PermissionError: [Errno 1] Operation not permitted`로 차단되었다. 제품 오류가 아니라 sandbox network boundary였고, 로컬 `127.0.0.1`만 사용하는 승인된 smoke에서 `/api/joint-plane`과 `/api/combination`이 모두 HTTP 200을 반환함을 확인했다.
2. post-implementation review에서 (a) busy 중 candidate apply, (b) joint shading의 node/cell geometry, (c) finite/monotone mask 없이 contour를 그리는 문제, (d) aggregate stale export, (e) saddle cell contour pairing을 지적했다. 모두 수정했고 saddle 양 방향은 dependency-free Node regression test로 고정했다.

### 검증 증거

- `RUN_SRAM_VMIN_DEMO_INTEGRATION=1 python -m unittest manuscript.gui.tests.test_demo_engine -v`: 11 passed. synthetic joint-query tests와 trusted local bundle one-axis smoke를 포함한다.
- `node manuscript/gui/tests/test_ui_contours.js`: 3 passed (two bilinear saddle orientations + ordinary cell).
- `node --check manuscript/gui/static/app.js`, `python -m compileall -q manuscript/gui`, `git diff --check`: 모두 통과.
- trusted local bundle benchmark: 31×31 joint plane은 961 node를 계산했고 656 joint-feasible/269 unknown node를 보고했다. 3-axis 1,331-row Cartesian query와 4-axis 2,048-row seeded-LHS query도 완료했다. 이 시간 측정은 현재 Linux 개발 환경의 warm-up/CPU 상태에 한정되며 Windows 발표 PC latency 보장은 아니다.
- read/write checkpoint load에서 기존의 very-small GP likelihood noise rounding warning은 관찰되었지만 test failure는 아니며 model 수치 변경은 하지 않았다.

### 남은 검증 경계

브라우저 DOM/canvas의 실제 상호작용과 Windows PyInstaller/발표 PC smoke는 이 Linux 환경에서 실행하지 않았다. target Windows에서 bundle 포함 build와 오프라인 UI 상호작용을 별도 확인해야 한다.
