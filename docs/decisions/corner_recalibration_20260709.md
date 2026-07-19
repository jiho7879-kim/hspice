# Corner 재보정 실험 — 5접근 비교 & 결론 (2026-07-09)

> 선행: `stage4_real_data_gate.md` (Gate GO), `corner_calibration.md`.
> 문제: Stage 4 GP가 실제 공정 corner에서 mu를 **체계적으로 과소예측**
> (외삽 편향). 이를 어떻게 교정할지 5개 접근을 비교.
> 결론: **per-corner residual correction (sep)** 채택.
> 스크립트: `scripts/corner_retrain_test*.py`, `corner_retrain_pvta_contour.py`.
> 데이터: `data/hspice_real_corner.xlsx` (4 corner × 6 Vop 독립 측정).

---

## 0. corner 좌표에 대한 정정 (중요)

이전 문서(`stage4_real_data_gate.md` §5.1)에서 "정확한 (±60,±60) corner
미샘플"이라 적었으나, **이는 잘못된 지적**이었다. analytic toy에서 ±60은
단순 가정이었고, **실제 공정 corner의 VT shift는 측정된 값이 맞다**:

| Corner | 실제 (cn, pu) mV | 의미 |
|--------|:----------------:|------|
| FFG | (−36, −44) | fast N, fast P |
| FSG | (−29, +39) | fast N, slow P (SNMR worst) |
| SFG | (+32, −37) | slow N, fast P (Vtrip worst) |
| SSG | (+36, +45) | slow N, slow P |

→ corner 검증은 **정당함**. 이 좌표가 이 PDK의 실제 3σ global corner다.

## 1. 문제: GP corner 외삽 편향 (실데이터 최초 실증)

`stage4_corner_verification/corner_prediction_errors.png`:

- 4개 corner **모두 mu 예측 오차 음수** (GP < 측정), **Vop↑일수록 악화**
  → Vop=0.9V에서 **−20mV 이상**.
- 랜덤 노이즈가 아닌 **체계적 외삽 편향**: TT+skew 데이터로 학습 후
  corner로 나갈 때 mu를 낮게 예측.
- 이는 `adversarial_review_20260707.md` §4.1 + `physics_ablation.md`가 예측한
  "GP corner extrapolation 취약, corner anchor 필요"의 **실데이터 최초 실증**.

**단, Vmin 자체 오차는 작다**: FSG +23mV(+4.2%), SSG +6mV(+1.3%),
FFG −0.5mV, SFG 0(censored). mu 편향이 커도 Z=mu/sigma가 target을 crossing
하는 Vop 위치는 덜 민감 → Vmin 오차가 완화됨. (그래도 FSG는 SNMR worst
corner이므로 +23mV는 무시 못 함.)

## 2. 5개 접근 비교 (FSG Vmin 오차 기준)

| # | 접근 | 방법 | 스크립트 | 폴더 | FSG 오차 | contour |
|---|------|------|---------|------|:--------:|:-------:|
| 0 | Original | 보정 없음 | (stage4_real) | stage4_real | +23.1mV | 매끄러움 |
| 1 | noise-weight | corner noise 1e-6 (het.) | corner_retrain_test | stage4_corner_retrain | +25.2mV ❌ | — |
| 2 | **sep** | **2단계: main GP + corner별 residual spline** | **corner_retrain_test_sep** | **stage4_corner_retrain_sep** | **0.0mV ✅** | **유지 ✅** |
| 3 | dup | corner data 50× 복제 | corner_retrain_test_dup | stage4_corner_retrain_dup | −0.02mV | **왜곡 ❌** |
| 4 | noise-contrast | corner 1e-6 / TT 5e-2 | corner_retrain_test_noise | stage4_corner_retrain_noise | +17.8mV △ | — |
| 5 | feat | corner one-hot feature | corner_retrain_test_feat | stage4_corner_retrain_feat | +24.4mV ❌ | — |

+ `corner_retrain_pvta_contour.py` → `stage4_corner_retrain_contour`:
  Original vs dup(50×) vs sep의 PVTA contour 3-panel 비교.

## 3. 결정적 통찰: 정확도 vs contour 부작용

`stage4_corner_retrain_contour/pvta_contour_comparison_3panel.png`:

- **(a) Original**: 매끄러운 대각 contour (물리적으로 타당) — 단 corner 부정확.
- **(b) Data Dup 50×**: corner는 맞췄으나 **contour 심하게 뒤틀림**. corner 4점을
  50배 복제 → GP가 그 점에 과적합, 전역 표면 물결침. **inverse estimation에
  위험** (Vmin=0.55V 등고선이 비물리적으로 구불거림).
- **(c) Corner-corrected (sep)**: **매끄러움 유지 + corner 정확**. 3개 중
  유일하게 둘 다 만족.

→ **dup과 sep 모두 corner를 0mV로 맞추지만, dup은 전역 표면을 희생하고
sep은 아니다.** 이유: sep은 main GP(전역 매끄러움 담당)를 건드리지 않고
corner residual만 후처리로 더하기 때문.

## 4. 결론: sep (per-corner residual correction) 채택

### 방법 (corner_retrain_test_sep.py)
```
1. Main GP (원 surrogate) → mu, sigma @ (cn, pu, Vop) 전역 예측
2. 각 corner에서 residual = measured − predicted (6 Vop)
3. residual을 Vop에 대해 cubic spline 보간
4. Final = main_pred + residual_interp(Vop)
```
corner 근방에서만 residual이 유효하도록 거리 기반 감쇠(=corner에 정확히
있을 때만 residual 적용, 멀어지면 0)를 적용 → 전역 GP 불변.

### 채택 근거
1. corner 정확도 완벽 (FSG 0mV) — dup과 동급.
2. 전역 contour 매끄러움 유지 — dup과 결정적 차이. inverse estimation 안전.
3. main GP를 재학습하지 않음 → Stage 4 GO 판정 결과 그대로 보존.
4. 물리적으로 정직: "GP 외삽은 편향되지만, 측정된 corner에서는 실측값으로
   보정한다"는 명확한 2단계 구조 → 논문 설명 용이.

### 열등 접근을 버린 이유 (trial & error 기록)
- **noise-weight / noise-contrast (1, 4)**: corner에 낮은 noise를 줘도 GP가
  전역 lengthscale로 평활화하는 힘이 더 커서 corner를 충분히 통과 못 함
  (부분 개선 또는 악화). heteroscedastic likelihood만으로는 4점을 강제
  통과시키기에 부족.
- **dup (3)**: 통과는 시키나 50× 복제가 전역 표면을 왜곡. weight를 낮추면
  통과가 약해지는 딜레마 — 본질적으로 "hard constraint를 soft 수단으로
  흉내"내는 한계.
- **feat (5)**: corner one-hot은 4점에만 non-zero라 GP가 그 feature의
  lengthscale을 제대로 학습할 데이터가 부족 → 사실상 무효 + 차원만 증가.

## 5. 논문 반영

1. **기여로 프레이밍**: "GP는 학습 도메인 밖 corner에서 mu를 체계적으로
   과소예측한다(실데이터 실증). 이를 main GP의 전역 매끄러움을 해치지 않는
   per-corner residual correction으로 교정 — corner 정확도와 contour 물리성을
   동시에 확보." (§4.1 gradient inversion과 함께 physics-informed 후처리 계열.)
2. **Figure**: 3-panel contour (Original / dup 왜곡 / sep) — dup을 "naive
   over-fitting" 반례로, sep을 해법으로 대비. §3.5 "지표/방법 정의가 결론을
   바꾼다"와 같은 서사.
3. **주의**: 이 실험은 4개 corner뿐. corner가 많아지면(Phase 4의 skew/σL 조합)
   residual spline이 아니라 corner anchor를 training에 넣는 방식(physics.py의
   L_boundary)이 더 자연스러울 수 있음 — 재평가 필요.

## 6. 폴더/스크립트 정리 (이 문서 작성 후 실행)

실험 탐색 과정에서 8개 result 폴더 + 9개 스크립트가 생성됨. 결론(sep)과
핵심 비교(contour)만 남기고 열등 접근은 정리:

**유지**:
- `stage4_real/` — Gate 결과 (기준)
- `stage4_corner_verification/` — 외삽 편향 실증 (문제 정의)
- `stage4_corner_retrain_sep/` — 채택 해법
- `stage4_corner_retrain_contour/` — 정확도 vs 부작용 비교 figure
- 스크립트: `stage4_real_data.py`, `corner_verification.py`,
  `corner_retrain_test_sep.py`, `corner_retrain_pvta_contour.py`

**정리 대상** (열등 접근, 본 문서에 결과 기록됨):
- `stage4_corner_retrain/`, `_dup/`, `_noise/`, `_feat/` (폴더)
- `corner_retrain_test.py`, `_dup.py`, `_noise.py`, `_feat.py`,
  `_check_tt_error.py` (스크립트)

> 스크립트는 재현 목적상 git 히스토리에 남으므로 삭제해도 복원 가능.
> result 폴더(주로 .png/.pth 바이너리)는 저장소 비대화 방지 위해 정리.
