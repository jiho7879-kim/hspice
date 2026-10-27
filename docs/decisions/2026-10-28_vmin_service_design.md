# SRAM Vmin Studio (`service/`) — 설계 결정과 시행착오 (2026-10-28)

## 요청

"시나리오들을 포함해 forward까지 쉽게 재현할 수 있는 prototype web service를 다시 만들어 달라.
하드코딩하지 말고 여러 가지를 유연하게 재현할 수 있게. hspice 폴더 안에 service용 폴더를 따로."
추가 질문에는 "뭔가 부족해서 토탈 솔루션 느낌으로"라고만 답했다. 그래서 범위는 아래처럼 직접 정했다.

- 기존 도구 두 개(Inverse Studio, Scenario Lab)의 기능 + 2026-10-27 후보 시나리오
  (`inverse_scenario_candidates_20261027.md`)를 한 서비스에 담는다.
- 모든 분석을 데이터(JSON spec)로 정의한다. 논문 수치는 preset의 `expect`로 대조한다.
- 그림은 논문 형식으로 맞춘다 (Fig. 11 작업 때 받은 요구).

## 선택지와 결정

| 쟁점 | 선택지 | 결정 | 이유 |
|---|---|---|---|
| 어디에 | (a) `manuscript/gui` 확장 (b) Scenario Lab 확장 (c) 새 `service/` | **c** | 둘 다 시나리오가 코드에 박혀 있다 (gui는 저장된 결과 표시, Lab은 lever 문자열 파서). 요청이 폴더를 따로 원했다. 기존 도구는 발표용으로 그대로 둔다 |
| 서버 | stdlib `http.server` / FastAPI(.venv에 있으나 requirements에 없음) | **stdlib** | 저장소의 다른 두 도구와 같고 새 의존성이 없다. 검증은 spec 해석 단계(`scenario.py`)에서 한 번 한다 |
| 긴 계산 | 동기 요청 / 작업 큐 + polling | **큐** | 81×81 window 4장이 60 s 넘게 걸린다. worker thread 하나가 GP를 독점하므로 torch 동시 접근 문제도 없다 |
| 그림 | 브라우저 차트 / 서버 matplotlib | **서버 matplotlib** | 논문 그림과 같아야 한다. PDF가 바로 논문용이 된다 |
| 시나리오 정의 | 코드 preset / JSON spec | **JSON spec** | 화면·CLI·저장·재현이 같은 객체를 쓴다. 실행마다 기본값까지 채운 spec을 저장하므로 `main.py run runs/<id>/spec.json`이 똑같이 재현한다 |
| 폼 | 분석마다 손으로 / 카탈로그에서 생성 | **생성** | `analyses.py`의 `fields`만 바꾸면 화면이 따라온다 |
| lever | 축 이름 문자열(Lab) / 타입 있는 lever | **scale · pull · shift** | Fig. 10(배율·corner 당김)과 Fig. 11(축별 당김), Vth target 이동을 한 문법으로 표현한다. 모든 solver는 usage u ∈ [0, 1](상한 대비 사용률) 위에서 돈다 |
| 기준 좌표 | 공통 nominal / mode별 학습 중앙값 | **mode별 (기본) + 선택** | 논문 시나리오가 mode별 중앙값을 썼다(`v_e_scenario.py`). 화면에서 read·write 공통으로 바꿀 수 있다 |

## lever solver

- **single**: lever 하나만, 이분법. 상한에서 못 넘으면 "도달 불가".
- **priority**: 목록 순서대로 상한까지 쓰고 마지막 것만 이분법.
- **balanced**: 모든 lever를 상한의 같은 비율 t만큼 — "한 lever를 끝까지 밀지 않는" minimax 해 (D-17과 같은 정의).
- **min-cost**: Σ weight·u 최소. k−1개 lever 격자 + 남은 하나 이분법, 모든 lever가 한 번씩 이분법 쪽이 된다.
- **robust**: 같은 solver를 posterior 분위수 함수 위에서 돌린다. 공통 난수(고정 seed)를 써서 분위수가 u에 대해 매끄럽게 움직이게 했다.

## 시행착오

1. **50k행 GP 한 번 호출 → OOM kill.** `v_e_scenario_process.py` 때와 같은 문제. `engine.predict`가
   4,000행씩 나눠 부른다 (100×100×5 Vop = 50k행).
2. **posterior 공분산이 부정확했다.** gpytorch 기본 경로(학습점 8,500 > `max_cholesky_size`)는 CG를 쓰는데,
   FSG read 지점에서 log σ의 posterior sd가 exact 대비 **+34 %**였다 (0.00540 vs 0.00404). LOVE(rank 100)는
   **+80 %**, rank 2,000이어야 +2 %였지만 GP당 60–80 s가 걸렸다. exact Cholesky 경로는 맞지만 호출마다
   다시 분해해 3 s씩 걸렸다. 해결: 학습 공분산 Cholesky를 GP마다 한 번 분해해 캐시하고(GP당 ~5 s, 0.6 GB),
   `K** − V'V`를 직접 계산한다. 값은 gpytorch exact 경로와 4자리까지 같고(0.0040413 vs 0.0040412) 호출당 0.04 s다.
   → 10-27 후보 기록의 robust 수치(CG 기반)는 아래처럼 정정된다.
3. **min-cost가 45 s.** 이분법 한 단계마다 격자 전체를 GP에 넣는다. 30단계 → 14단계(2⁻¹⁴ ≈ 6e-5),
   격자 예산 600 → 400으로 낮췄다. 단위 시험의 허용오차를 이 해상도에 맞췄다.
4. **window 제목이 colorbar를 덮었다.** lever 세 개 이름이 한 줄에 안 들어간다. 44자에서 줄을 바꾸고,
   3줄짜리 제목이 있을 때만 행 간격을 넓힌다 (2줄이면 논문과 같은 간격).
5. **빈 mode 목록이 "전부"로 해석됐다.** `[] or MODES`. 화면에서 둘 다 끄면 오류가 나도록 고쳤다.

## 검증 (2026-10-28)

- `main.py verify` — 논문 preset 4개, LEDGER 대조 19/19 통과 (bundle·원본 두 경로 모두).
- 시작할 때 §V-D corner 예측 8/8 재현.
- `tests/test_solve.py` — solver 7개 시험 (닫힌 형식 함수).
- API: 잘못된 축 이름, x = y 평면, 빈 mode, 경로 조작(`..`), 외부 bind가 모두 사용자 메시지로 막힌다.

## 정정 — `inverse_scenario_candidates_20261027.md`의 robust 수치

| 해 | 10-27 (CG 근사) | exact posterior |
|---|---|---|
| priority (local N −10 %, global N −8.0 %) | P(pass) 0.46 | **0.45** |
| balanced (t = 0.754) | 0.48 | **0.50** |
| local N −10 % 단독 | 0.22 | **0.20** |

새로 얻은 것: 95 % 기준 priority 해는 **local N −10 %, global N −20 %, global P −11.2 %**, balanced 해는
t = 0.93(**−9.3 % / −18.6 % / −18.6 %**)이다. 상한 안에서 95 % 확신은 가능하지만 global N을 상한까지 써야 한다.

## 열린 문제

- leakage 모델이 없어 `recenter` 결과는 Vmin 쪽 상한일 뿐이다 (사내 Ioff–Vth 데이터 필요).
- Windows exe 패키징은 하지 않았다 (`manuscript/gui`의 PyInstaller 경로가 있음).
- loopback 밖 공유(사내망)는 막아 두었다. 필요하면 인증과 함께 따로 결정한다.
- `manuscript/gui/demo_bundle/*.pt`(학습 target 포함)는 README와 달리 git에 커밋되어 있다 — 정리 여부는 사용자 결정.
