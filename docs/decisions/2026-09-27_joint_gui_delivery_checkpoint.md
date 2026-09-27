# Joint read/write GUI delivery checkpoint

작성: 2026-09-27  
관련 결정: `2026-09-27_joint_read_write_multiaxis_gui.md`  
프로젝트 목표 연결: HSPICE/MC로 학습한 SRAM Vmin surrogate를 이용해 DTCO 후보를 빠르게 좁히되, HSPICE·PDK·silicon sign-off를 대체하지 않는다.

## 이번 checkpoint의 결과

Windows 발표용 local GUI가 기존 one-axis inverse를 보존한 채 다음 질문을 처리할 수 있게 되었다.

1. “같은 공정 좌표에서 read와 write target 경계가 각각 어디인가?”
2. “두 축·세 축·그 이상의 축을 함께 바꿨을 때 양쪽 target을 만족하는 **표본 후보**가 있는가?”

## 산출물

| 범위 | 변경 |
|---|---|
| inference core | `manuscript/gui/demo_engine.py`: shared-row joint plane, bounded 2–9-axis candidate sampler, censoring/nonmonotonic safety |
| local API | `manuscript/gui/demo_server.py`: `/api/joint-plane`, `/api/combination` |
| presentation UI | `manuscript/gui/static/index.html`, `app.js`, `app.css`: overlaid read/write contours, joint-pass shading, 2–9-axis selector, candidate table/apply action, result-staleness export |
| regression | `manuscript/gui/tests/test_demo_engine.py`, `test_ui_contours.js` |
| operator docs | `manuscript/gui/README_KR.md` |

## scientific interpretation locked in

- A joint query uses one shared 9D vector, and sweep axes use the intersection of read/write training boxes.
- A pass means `Vmin_read ≤ target` **and** `Vmin_write ≤ target` under the current surrogate/grid policy.
- 2D/3D results are bounded grid samples; 4–9D results are deterministic Latin-hypercube samples. “No feasible sample” is not a proof that no continuous solution exists.
- Candidate ranking is normalized coordinate distance only, not manufacturing cost or a global optimum. When the current selected-axis point is inside the shared domain, it is retained as a sampled baseline within the hard budget.
- Combined predictions span read 125 °C and write −40 °C model/batch conditions; they remain design exploration, not joint experimental validation.

## validation evidence

- Python GUI tests with trusted bundle: 11 passed (incl. near-grid baseline regression).
- Browser-independent contour topology test: 3 passed.
- Local loopback HTTP smoke: both new endpoints returned HTTP 200 with real bundle data.
- JS syntax, Python byte compilation, and diff whitespace checks: passed.
- No model checkpoint, raw HSPICE data, condition generator, or manuscript result file was changed.

## outstanding gate

The target Windows PyInstaller build and real browser/presentation-PC interaction still require Windows evidence. The existing small-likelihood GPyTorch warning remains a pre-existing model-load warning and was not masked or changed.
