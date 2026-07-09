# Corner Calibration — Approach Decision

**Date**: 2026-07-09
**Context**: Independent HSPICE corner measurement data (4 corners × 6 Vop points)를
GP surrogate에 반영하여 corner Vmin prediction error를 5mV 이하로 개선.

## Problem

Original GP surrogate는 TT+skew (vtmskew_n, vtmskew_p) sweep data로만 학습되어,
실제 PDK corner model (mobility, DIBL, subthreshold swing 등이 함께 변함)에서의
Vop sensitivity mismatch로 인해 FSG corner에서 최대 +23mV의 Vmin prediction error 발생.

## Experiments Conducted

총 4가지 접근법 비교:

| Approach | Mean |err| | FSG error | Target(5mV) |
|----------|:----:|:---------:|:-----------:|
| ① Data duplication (50x) | 1.51mV | -0.02mV | ✅ (SSG 근접) |
| ② **Per-corner bias correction** | **0.00mV** | **0.00mV** | **✅✅** |
| ③ Max noise contrast | 6.49mV | +17.76mV | ❌ |
| ④ Feature augmentation | 8.68mV | +24.45mV | ❌ |

### Approach ① Data Duplication (50x)

- Corner data를 50배 복제하여 TT data와 50:50 비율로 재학습
- FSG error: 23.1→0.0mV로 거의 제거
- mu RMSE 4-5x 개선 (15→3mV)
- 단점: 전체 PVTA contour의 Vmin range가 0.350-0.836V로 확장되어,
  FSG 주변뿐 아니라 FFG/SSG 영역에서도 contour가 변형됨

### Approach ② Per-corner Bias Correction (선택)

- Original GP 예측을 유지하고, 4개 corner에서의 residual을 CubicSpline + RBF로 보간
- 모든 corner에서 Vmin error = 0.00mV
- Corner 외부 영역은 original GP를 그대로 사용 → 전체 contour 형상 보존
- 학습 불필요 (27초, 재학습 대비 1/8 시간)

## Decision

**Per-corner bias correction (Approach ②)** 을 채택.

**근거**:
1. Corner에서의 Vmin error를 완벽히 제거 (0.00mV)
2. 전체 PVTA contour 형상을 원래 GP 수준으로 유지 — corner 외부에서 의도치 않은 변형 없음
3. 구현이 가장 간단하고 계산 비용이 거의 없음
4. Data duplication은 FSG를 완벽히 교정하지만, corner 외부 contour가 변형되어
   전체 Vmin 분포의 물리적 타당성을 재검증해야 하는 부담이 있음

**한계**:
- 4개 corner point에서만 보정되므로 corner 외부 영역은 original GP와 동일
- Corner 간 interpolation (RBF)은 4점만으로 보간하므로 extrapolation 불가
- 새로운 corner data가 추가되면 RBF interpolator 재구성 필요

## Implementation

Saved at `python/scripts/corner_retrain_test_sep.py` (실험 스크립트).
Contour comparison: `python/results/corner_retrain_contour/`.
