# Session 2026-07-06 — Stage 3 NO-GO 근본원인 수정 + 지표 정정

> **한 줄 요약**: Stage 3 NO-GO(Vmin RMSE 0.16-0.26V)는 모델 실패가 아니라
> **(1) PhysicsConstrainedSurrogate의 입력 스케일링 누락 버그 + (2) 지표 정의
> 아티팩트 3종**이었다. 수정 후 inverse assist 정확도는 **2.6-4.9 mV** → **Stage 3 GO**.

---

## 1. 이 세션에서 한 일 (요약)

| # | 항목 | 결과 |
|---|------|------|
| 1 | ngspice 트랙 검증 (SNM 추출 + 모델카드) | 결함 2건 수치 확정 후 **user 결정으로 트랙 보류** — `ngspice_integration.md` 상단 참조 |
| 2 | `physics.py` 입력 스케일링 버그 수정 | 4D mu RMSE **0.049 → 0.0023** (21x) |
| 3 | `physics.py` L_pelgrom no-op 버그 수정 | gradient 흐름 복구 + 단위테스트 추가 |
| 4 | Stage 3 지표 아티팩트 3종 수정 | Vmin RMSE 0.16-0.26V → **2.6-4.9mV**, GO |
| 5 | 3D ablation 재실행 (정직한 수치) | Baseline 6.52→1.26mV, L_boundary 효과 -27% 유지 |
| 6 | PG≫PU lengthscale 계층 실험 | 스케일링 후 GP가 계층을 방향까지 학습함을 확인 |
| 7 | Z_target 유도 정정 | `derive_z_target()` 추가, 64Mb@99.9% = **6.64** (Z_FIXED=6.0은 optimistic) |

---

## 2. Bug 1: PhysicsConstrainedSurrogate 입력 스케일링 누락

### 증상 (2026-07-02 세션)
- 4D physics-constrained fit: mu RMSE 0.039 (plain Surrogate 대비 15x 악화) → Stage 3 NO-GO
- all-constraints 설정에서 CG non-convergence

### 근본 원인
- `surrogate.Surrogate.fit()`은 `StandardScaler`로 입력을 표준화하지만
  `physics.PhysicsConstrainedSurrogate.fit()`은 **raw 입력을 그대로 사용**했다.
- raw 스케일: cn/pu 범위 120(mV) vs Vop 0.5(V) vs WLUD 0.1(ratio).
  GPyTorch 기본 lengthscale 초기값 ~0.69에서 cn/pu가 유효 lengthscale(~30-60)에
  도달하려면 수백 iteration 필요 → n_iter=120-150으로는 수렴 불가.
- **3D ablation(2040pt 조밀 데이터)에서는 짧은 lengthscale로도 보간이 되어 버그가
  가려졌고**, 4D(30개 (cn,pu) 지점, 희소)에서 폭발했다.

### 증거 (A/B 벤치마크, 동일 데이터/iteration)
| 구성 | mu RMSE |
|------|---------|
| plain Surrogate (참조) | 0.00243 |
| Physics **수정판** (boundary) | 0.00235 |
| Physics **구버전 재현** (identity scaler) | **0.04925** ← NO-GO 재현 |
| Physics 수정판 all-on (mono+boundary+pelgrom) | 0.00232 |

### 수정 내용 (`src/physics.py`)
- `fit()`: `self._x_scaler.fit_transform(X_aug)` (augmented set 기준으로 fit)
- probe points, `predict()` 입력 모두 동일 scaler로 transform
- **체크포인트 v2 명명** (`gp_{tag}_v2.pth`): v1 체크포인트는 unscaled 기준이라
  로드 시 조용히 오염됨 → 파일명 버전으로 차단

---

## 3. Bug 2: L_pelgrom이 사실상 no-op

### 원인 (구현 2중 결함)
```python
with torch.no_grad():          # ← gradient 차단: loss에 더해도 학습 효과 0
    output = gp(xt)            # ← train 모드에서는 PRIOR 반환 (posterior 아님)
```
- 기존 ablation의 "Pelgrom +0.25mV 개선"은 제약 효과가 아니라 co-training 노이즈였다.

### 수정
- L_mono와 동일 패턴: eval 모드 + `prediction_strategy = None` + gradient 흐름 유지
- pelgrom target은 **raw Vop 컬럼**에서 사전 계산해 전달 (스케일된 Vop로 계산하면 무의미)
- warmup 30 / interval 3 (Cholesky 비용 관리, L_mono와 동일)
- `tests/test_physics.py`에 gradient-flow 검증 추가 (`penalty.requires_grad` + backward 확인)

---

## 4. Stage 3 지표 아티팩트 3종 (validate_assist_sweep.py)

기존 "Vmin RMSE 0.16-0.26V"는 아래 3개 아티팩트의 합성이었다:

| 아티팩트 | 내용 | 수정 |
|----------|------|------|
| **범위 불일치** | GP는 WLUD∈[0.90,1.0]만 탐색하는데 truth는 [0.50,1.0]에서 feasibility 판정 → >10% underdrive가 필요한 지점이 전부 "GP 실패"로 계산 (74-90% 일치) | truth도 design range [0.90,1.0]로 통일. **일치율 99.2-99.9%**. 범위 밖 지점은 `OoR` 진단 컬럼으로 분리 |
| **포화 floor** | true Vmin < 0.4V인 지점의 heuristic floor(0.35V)를 실측값처럼 RMSE에 산입 | `compute_vmin_from_z(..., return_censored=True)` 추가 — censored 지점은 "target met with margin"으로 별도 집계 |
| **무어시스트 셀** | `wlud_required=1.0`(자연 Vmin이 이미 target 이하) 셀에서 "달성Vmin−target"을 오차로 계산 — 마진을 오차로 둔갑 | assist-active(0.9<WLUD<1.0) 셀만 정확도 평가. `NoAst` 컬럼 분리 |

### 수정 후 결과 (plain Surrogate, N_COND=30)
| Target | Agree% | NoAst | VminRMSE_int | VminRMSE_leg(구정의) | p95 |
|--------|--------|-------|--------------|----------------------|-----|
| 0.55V | 99.9% | 373 | **2.6 mV** | 159 mV | 5.1 mV |
| 0.60V | 99.9% | 414 | **2.8 mV** | 193 mV | 5.2 mV |
| 0.65V | 99.4% | 461 | **3.5 mV** | 225 mV | 6.6 mV |
| 0.70V | 99.2% | 502 | **4.9 mV** | 258 mV | 12.8 mV |

**판정: Stage 3 (inverse assist) GO.** "Target 0.55V가 너무 낮다"는 결론도 아티팩트였다
— 모든 target에서 동등하게 동작. `demo_assist.py`는 계획서 정본 target 0.60V로 설정.

---

## 5. 3D Ablation 재실행 (수정된 코드, 정직한 수치)

| Config | Vmin RMSE (신) | Vmin RMSE (구, 버그) | Hausdorff (신) |
|--------|---------------:|---------------------:|---------------:|
| Baseline | 1.263 mV | 6.52 mV | 0.50 mV |
| +L_mono | 1.586 mV | 6.46 mV | 0.59 mV |
| +L_boundary | 0.918 mV | 5.16 mV | 0.40 mV |
| +Mono+Boundary | 1.315 mV | 5.10 mV | 0.46 mV |
| +All | **0.897 mV** | 4.91 mV | 0.35 mV |

**해석 (기존 결론 정정):**
1. **입력 스케일링이 최대 효과** — baseline 자체가 5x 개선 (6.52→1.26mV).
   기존 ablation은 "under-converged GP를 corner anchor가 부분 보상"하는 구도였다.
2. **L_boundary 효과는 생존** — 1.26→0.92mV (-27%), 기존 -21%와 유사한 상대 개선.
   "corner anchor가 저비용 고효율"이라는 논문 주장은 유지 가능하되 **절대 수치는 이 표로 교체**.
3. L_mono는 단조 analytic 데이터에서 여전히 무효(오히려 소폭 악화 — penalty=0인데
   3-iteration 간격 스케줄이 학습 노이즈만 추가). 실 데이터(비단조 구간)에서 재평가.
4. mu RMSE는 전 구성 ~0.00206 (관측 노이즈 0.002 바닥에 도달).

## 6. PG≫PU Lengthscale 계층 실험 (physics_ablation.md §6.3 후속)

PG 민감도를 2x/3x로 키운 asymmetric 데이터에서 plain Surrogate(표준화 입력)의 ARD:

| 데이터 | \|B/C\| | l_pu/l_cn |
|--------|--------:|----------:|
| 현행 (B=+0.001, C=-0.0015) | 0.67 | 0.86 |
| PG 2x (B=+0.002, C=-0.001) | 2.0 | 1.16 |
| PG 3x (B=+0.003, C=-0.001) | 3.0 | 1.31 |

- **표준화 후 GP는 민감도 계층을 방향까지 정확히 학습한다** (민감한 축 → 짧은 lengthscale).
- 기존 "l_pu/l_cn ≈ 1.0 항상" 관찰 역시 unscaled GP(lengthscale이 초기값 부근에 정체)의
  아티팩트였다.
- 현행 toy 계수는 PU가 더 민감(0.86 < 1) — 실리콘 상식(PG≫PU)과 반대이므로, **HSPICE
  데이터 투입 전까지는 lengthscale 계층을 Go/No-Go 기준으로 쓰지 말 것** (데이터 자체가
  계층을 안 가짐). HSPICE 데이터에서는 유효한 진단이 된다.

## 7. Z_target 정정 (`src/utils.py`)

- `derive_z_target(mb, y_target)` 추가: 정확 유도 `norm.isf(1 - y^(1/Nbits))`.
  64Mb@99.9% → **6.64**, 256Mb → 6.84, 64Mb@99% → 6.29.
- 기존 주석의 "Z_FIXED=6.0 conservative"는 **반대** — 6.0 < 6.64이므로 optimistic
  (Vmin을 낮게 추정). toy 재현성 위해 Z_FIXED=6.0은 유지하되 주석 정정.
- 계획서 §6의 `Nbits = Mb × 10^6 × 6` 오류 수정 — 6T의 6은 transistor 수이므로
  bit 수에 곱하면 안 됨 (failure 단위는 cell).
- **논문/HSPICE 배포 시**: `derive_z_target()` 사용. 모든 Vmin이 고정 +shift되나
  contour 모양/GP 품질 지표는 불변.

---

## 8. Trial & Error 로그 (이 세션)

| 시도 | 결과 |
|------|------|
| ngspice `.osdi` dot 명령 | ngspice-46 현재 빌드에 미구현 |
| `.spiceinit` + `pre_osdi` | "no such command" — **OSDI 미컴파일 빌드 확정** |
| Seevinck max를 ±V_BND 창으로만 제한 | wing 오염 (394mV 오답) → **(pseudo-)crossing 사이 eye 구간 제한 필수** |
| 모델카드 vth0만 낮춤 (0.32/-0.30) | READ gain 0.99로 악화 — 원인은 vth가 아니라 `xl=-9n` (Leff 7nm) |
| `xl=0` + PMOS u0 0.028 + nfactor 1.25 | 인버터 gain 7.4-11.2 정상화, butterfly 3-crossing 복구 |
| pelgrom fix 후 test_physics 구 시그니처 | 테스트를 새 계약(사전계산 target + grad 검증)으로 갱신 |

## 9. 논문 관점 시사점

1. **지표 정의가 곧 결론이다** — censoring, 범위 정합, boundary 셀 처리를 명시한
   "inverse accuracy" 정의를 논문 §experimental setup에 그대로 기술할 것 (이번 수정이 초안).
2. ablation 표의 절대 수치는 §5 표로 전면 교체. "L_boundary 95% of improvement" 표현은
   "input standardization이 1차 요인, corner anchor가 잔여 오차의 ~27% 추가 개선"으로 수정.
3. Vmin RMSE 1-5mV 수준은 HSPICE 노이즈 플로어(2-3mV)와 같은 자릿수 — full project 전환
   트리거(physics_ablation.md §1) 관점에서 GP로 충분, NN+PINN 전환 근거 아직 없음.
4. Z_target을 유도식으로 쓰면 Mb(용량)별 Vmin 차이가 자동으로 나온다 —
   Scenario A(Mb_max 역추정)가 additional simulation 없이 physics layer만으로 가능해짐.

## 10. 다음 스텝 (우선순위)

1. ~~**Stage 3a 마무리** + **PhysicsConstrainedSurrogate로 Stage 3 재실행**~~ → **완료 (같은 날)**:
   `demo_assist.py` 재작성 (target 0.60V, 교정 지표, plain vs physics 비교,
   출력 `results/stage3_assist/`). 결과:

   | 지표 (target 0.60V) | plain | physics (boundary+pelgrom) |
   |---|---|---|
   | Feasibility agreement | 99.9% | **100.0%** |
   | WLUD RMSE | 0.0016 | **0.0013** |
   | Vmin RMSE (assist-active) | 3.14 mV | **2.55 mV** (−19%) |
   | \|err\| p95 | 6.15 mV | **3.87 mV** (−37%) |
   | 판정 | — | **GO** (3/3 PASS) |

   Physics 제약의 이득은 평균보다 **tail(p95 −37%)에서 큼** — corner anchor가
   extrapolation 영역을 보정한다는 해석과 일치. assist map은 물리적으로 정합
   (SFG 방향 무어시스트 / FSG 방향 설계범위 내 불가, 경계 기울기 = gradient 부호와 일치).

2. **HSPICE 실데이터 준비** (main track): `docs/plans/deck_generation_plan.md` 기준
   1200 job 팜 실행 — 이 세션의 지표 정의(censored/assist-active)를 파서에 반영할 것
3. (보류 중) ngspice 재개 시 `ngspice_integration.md` 상단 checklist 순서로
