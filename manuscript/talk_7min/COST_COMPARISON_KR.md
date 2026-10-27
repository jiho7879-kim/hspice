# Simulation deck 수 비교 — 9D crossed DOE vs 논문 GP

작성 2026-10-26. GP 쪽 수치는 `manuscript/results/forward.json`, `forward_write.json`에서 가져왔다.

## 1. 기존 방식: 9D crossed DOE (3D CCD × 7D 3-level grid)

**inner — 2D contour 기본 set (N Vt, P Vt 축)**

| 항목 | 값 |
|---|---|
| CCD (3인자) | 15점 |
| 지표 | 2 (SNMR, BWRM) |
| V_op | 5 |
| **기본 set** | 15 × 2 × 5 = **150 deck** |

**outer — 나머지 7D 인자에 대한 3-level grid**

7인자 3-level full grid = 3⁷ = **2,187점**

crossed DOE 점 수 = inner 15 × outer 2,187 = **32,805점**

7D의 각 점마다 기본 set 150 deck을 돌려야 7D 전체에서 2D contour가 설명된다.

**총 deck = 32,805점 × 2지표 × V_op 5 = 328,050 deck** (= 기본 set 150 × 2,187)

## 2. 논문 방식: GP

| | SNMR | BWRM |
|---|---|---|
| 조건 | 2,000 | 2,000 |
| V_op | 5 | 5 |
| deck | 10,000 | 10,000 |

**총 deck = 20,000 deck** (이 중 학습 17,000, hold-out 검증 3,000)

## 3. 비교

| 방식 | deck |
|---|---|
| 9D crossed DOE | **328,050** |
| 논문 GP | **20,000** |
| 비율 (crossed ÷ GP) | 16.4 |

같은 조건당 MC 표본 수를 가정했다.
