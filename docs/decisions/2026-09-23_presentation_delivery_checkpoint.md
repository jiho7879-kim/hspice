# 발표 해설·로컬 inverse 도구 delivery checkpoint

작성: 2026-09-23
관련 결정: `2026-09-22_manuscript_explanation_and_demo.md`, `2026-09-22_windows_inverse_gui_design.md`

## 목표와 이번 delivery 범위

사용자 목표는 제출된 SRAM Vmin 논문을 바탕으로 다음 네 메시지를 정확하면서 쉽게 발표하고,
Windows 발표용 PC에서 inverse를 시연하는 것이다.

1. 직접 회로 simulation 대비 학습된 surrogate의 효용
2. `9개 축 + VDD → μ GP / log σ GP → yield relation → Vmin` 구현 방식
3. Sobol 우선순위와 conditional inverse를 결합한 DTCO candidate 탐색
4. 초기 simulation budget과 accuracy 사이의 cost trade-off

이번 delivery는 **원고/결과/checkpoint를 수정하지 않고** 발표 해설·편집 가능한 PPTX·로컬 GUI·Windows 패키징 스크립트를 만든다. 제출한 원고의 전체 교정 또는 Windows EXE의 실기기 검증은 이 checkpoint의 완료 주장에 포함하지 않는다.

## 산출물

| 산출물 | 경로 | 역할 |
|---|---|---|
| 그림별 해설, 대본, Q&A | `manuscript/presentation/PRESENTATION_GUIDE_KR.md` | Fig. 1–10을 각각 ‘무엇/어떻게 읽나/무엇을 말하지 않나’로 설명. ARD, GP, Sobol, MC, inverse, RMSE/R², censoring도 보강. |
| 편집 가능한 15-slide deck | `manuscript/presentation/SRAM_Vmin_Surrogate_Presentation_KR.pptx` | 12개 본문 + 3개 backup; 각 slide의 발표자 노트 포함. |
| PPTX 생성기 | `manuscript/presentation/make_presentation.js` | 현재 figure PNG와 검증된 수치를 다시 활용해 deck을 재생성. |
| local browser GUI | `manuscript/gui/demo_server.py`, `demo_engine.py`, `static/` | loopback-only forward/inverse/plane UI. |
| trusted inference bundle creator | `manuscript/gui/prepare_bundle.py` | protected source data를 읽을 수 있는 안전한 준비 환경에서만 self-contained inference bundle 생성. |
| Windows 배포 자료 | `manuscript/gui/README_KR.md`, `build_windows.bat`, `launch_windows.bat`, `requirements-windows.txt` | PyInstaller `--onedir` standalone folder build/run 절차. |

## 핵심 해석 결정

### 반드시 유지할 표현

- 3.98 mV(read) / 5.65 mV(write)는 **Gaussian-reference simulation에 대한 scored hold-out surrogate Vmin RMSE**다.
- `Vmin`은 `g(p,V)=μ−Ztarget σ`가 0이 되는 공급전압 교차점이다. `Vmin=μ−kσ`가 아니다.
- Sobol 대상은 독립 uniform training box에서 `z=μ/σ` at 0.625 V의 total-order `ST`다.
- inverse는 나머지 8축을 고정한 **조건부 설계 boundary**다.
- 53.125×/42.5×는 sample-count budget ratio이지 HSPICE wall-clock 측정값이 아니다.

### 발표에서 피할 표현

- surrogate가 PDK/compact model/HSPICE를 대체한다.
- inverse가 9개 공정 원인을 유일하게 진단한다.
- `l_com=0.272`가 실제 불량의 27.2%를 뜻한다.
- PMOS local-σ floor miss 0.58 mV가 ‘물리적으로 불가능’을 증명한다.
- lobe correction 추정과 baseline Gaussian RMSE를 더해 실제 silicon Vmin error라고 한다.

## GUI 안전 동작

- `127.0.0.1`, `localhost`, `::1` 외 bind는 거부한다.
- CDN/telemetry/upload가 없고 UI API는 상대 local path만 사용한다.
- Vmin이 voltage grid 밖일 때 숫자를 꾸며내지 않는다 (`below_grid`, `above_grid`).
- selected-axis scan 후 bracket을 확인하고, `no_root_in_box`·`multiple_roots`를 정상 결과로 표시한다.
- 2D plane은 다른 7축을 고정한 `cn × pu` slice로 표시한다.
- exact GP checkpoint 복원에 필요한 training state가 포함될 수 있으므로 `demo_bundle/`와 build/dist 폴더를 Git ignore하고 confidential asset로 취급한다.

## 검증 증거 (Linux 개발 환경)

| 검증 | 결과 |
|---|---|
| `node manuscript/presentation/make_presentation.js` | 15-slide PPTX 생성 성공 |
| `pptx/scripts/office/validate.py` | `All validations PASSED!` |
| PPTX zip integrity | `No errors detected in compressed data` |
| OOXML slide text extraction | 15개 slide 제목·수치·caption·backup 순서 확인 |
| GUI/engine `py_compile` | 통과 |
| `node --check` (presentation generator, GUI JS) | 통과 |
| GUI pure safety tests | 4 passed + intentional integration skip |
| local trusted-bundle integration smoke | 1 passed; read inverse root and range guard 확인 |
| prior server HTTP smoke | health, metadata, predict, inverse endpoint가 loopback에서 응답 |
| non-loopback rejection | `--host 0.0.0.0`가 exit 1로 거부됨 |

GPyTorch가 저장 checkpoint의 매우 작은 likelihood noise를 `0.0001`로 반올림한다는 기존 `NumericalWarning`은 integration run에서 관찰되었다. test failure는 아니며, 이 delivery에서 likelihood/모델 수치를 바꾸지 않았다.

### 기존 test suite 실행 기록

이 환경에는 `pytest`가 설치되어 있지 않아 test 함수 64개를 직접 수집·실행했다. 61개는 통과했다.
`python/tests/test_noise_aware.py`의 3개는 synthetic data가 noise를 더한 뒤 음수 `sigma` label을 만들며 실패했다. 현재 `Surrogate.fit()`의 기존 `_positive_sigma()` guard는 log-σ GP에 음수 sigma를 넣지 않도록 이를 거부한다. 이 실패는 이번 변경 범위인 `Surrogate.load()` 진입 전 `fit()`에서 발생하며, `git diff`상 해당 guard/fit 경로는 수정하지 않았다. 유효한 MC standard deviation은 원래 양수여야 하므로, noise-aware synthetic fixture를 log-space 또는 양수 support로 고치는 작업은 논문 GUI delivery와 분리해 수행한다. 이 checkpoint에서는 test를 억지로 약화하거나 core sigma guard를 완화하지 않았다.

## 아직 남은 외부 환경 검증

1. **Windows build:** PyInstaller는 cross-compile하지 않으므로 Windows PC에서 `build_windows.bat`을 실행해야 한다.
2. **Windows presentation smoke:** 생성된 `dist/SRAM-Vmin-Inverse-Studio/` 폴더를 인터넷 없이 발표 PC에서 실행해야 한다.
3. **PPTX visual render:** 이 Linux 환경에는 `soffice`가 없어 PDF/thumbnail 렌더 시각검증은 불가했다. PPTX 구조 검증은 통과했으며, 실제 PowerPoint에서 15개 slide와 speaker notes를 한 번 확인한다.
4. **원고 정정:** 보고된 원고 문장/그림의 잘못된 해석은 발표 자료에서 회피했지만 제출본 DOCX 자체는 이번 작업에서 수정하지 않았다.

## 완료 판단

발표자가 사용할 **설명 자료, deck, local inference GUI source, and Windows build path**는 준비되었다. Windows binary/run 및 PowerPoint renderer QA는 target environment에서만 완료 판단할 수 있는 별도 gate로 남긴다.
