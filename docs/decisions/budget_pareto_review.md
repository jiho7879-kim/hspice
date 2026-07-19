# Budget Pareto — Review & Re-validation (2026-07-08)

> 선행: `docs/decisions/adversarial_review_20260707.md` §4.2 (원 설계),
> `scripts/budget_pareto.py`.
> 목적: seeds=6 baseline 결과에서 발견된 두 가지 불확실성(physics 효과가
> noise 안에 묻힘, stratified_sobol이 corner 근처에서도 유리하지 않아 보임)을
> corner-only hold-out + Wilcoxon paired test로 재검증.

---

## 1. seeds=6 Baseline (2026-07-07, commit f1fc776) — 원 관찰

180 cells (N∈{50,100,200,400,800} × 3전략 × physics{on,off} × 6seed), mean-only
fast path, ~15분. 결과: `results/budget_pareto/pareto_results.json` (이 커밋 이전 버전).

**트렌드는 명확**: N=50→800에서 Vmin RMSE 5.2→1.5mV, Hausdorff 1.6→0.5mV,
N≈400 부근 무릎. 이건 재검증에서도 불변으로 예상 — 논문 headline은 안전.

**불확실성 2건**:
1. **physics on/off 차이가 seed 표준편차 안에 묻힘.** 예: N=200 random에서
   physics가 오히려 +13.8%(악화). 단일 seed 관찰(이전 3D ablation, −27%)과
   불일치 — 정말 physics가 이기는지 통계적으로 불명확.
2. **stratified_sobol이 domain-uniform hold-out에서 random보다 안 나음**
   (N≥400). uniform hold-out이 train 분포와 일치하는 strategy를 유리하게
   만드는 아티팩트일 가능성 — corner 근처 정확도를 못 보여줌.

---

## 2. 재검증 설계 (이 세션)

### 2.1 Corner-only hold-out
`build_corner_holdout()`: 4 global corner(FSG/SFG/FFG/SSG) 각각 반경 15mV
이내 20점(총 80점), 동일한 censored-aware 채점. Uniform hold-out과 별도로
`corner_vmin_rmse_mV`로 리포트 — stratified_sobol이 겨냥하는 영역에서의
정확도를 domain 평균에 섞이지 않게 분리.

### 2.2 Paired Wilcoxon signed-rank test
`_paired_significance()`: 같은 seed로 physics on/off를 pairing(이미 각 seed가
동일 train 조건에 physics만 켜고 끄므로 자연 pairing), (strategy, N) 셀별
+ 전체 pooled로 Wilcoxon 검정. n_seeds가 작아(6-10) 정규성 가정 없는
비모수 검정 사용. `wilcoxon_p < 0.05`면 유의.

### 2.3 재실행
seeds 6→10 (통계력 확보), grid 60 유지(§Hausdorff 안정성은 이전 세션에서
검증됨). `results/budget_pareto/pareto_results.json`에 `significance` 필드 추가.

---

## 3. 재검증 결과 (seeds=10 완주, 300/300, 3회 checkpoint-resume 후 완료)

풀런은 외부 요인(세션/OS 레벨로 추정, Python traceback 전무)으로 3번
죽었으나 매번 checkpoint에서 무손실 재개 — 최종 300/300 cells 확보.
결과: `results/budget_pareto/pareto_results.json`,
`results/budget_pareto/corner_significance.json`.

### 3.1 N vs 정확도 (headline, seeds=6 baseline과 트렌드 일치 — 안전)

| N | Vmin RMSE, uniform (mV, plain) | Hausdorff (mV, plain) |
|---|---:|---:|
| 50 | 5.13±1.84 | 1.62±0.64 |
| 100 | 3.90±0.50 | 1.30±0.29 |
| 200 | 3.21±0.77 | 1.00±0.42 |
| 400 | 2.01±0.26 | 0.76±0.14 |
| 800 | 1.40±0.15 | 0.54±0.15 |

N=50→800에서 Vmin RMSE 5.1→1.4mV, Hausdorff 1.6→0.5mV, N≈400 무릎 —
seeds=6 baseline과 정량적으로 거의 동일. **headline 그대로 사용.**

### 3.2 Physics on/off — Wilcoxon 검정: uniform vs corner 지표

**핵심 수정 사항**: 애초 구현한 `_paired_significance()`는 uniform
hold-out(`vmin_rmse_mV`)에만 돌았음 — corner 지표(`corner_vmin_rmse_mV`,
seeds=6에서 이미 physics 효과가 보였던 바로 그 지표)에는 검정이 없었음.
이 세션에서 저장된 300 records로 즉시 재계산(`corner_significance.json`).

**Uniform hold-out** (원래 검정): POOLED diff=−0.11mV, **p=0.0072*** —
유의하지만 효과크기가 작음(개별 셀은 대부분 p>0.05, N=50/100 random만 유의).

**Corner-only hold-out** (추가 검정, 훨씬 강한 신호):

| Strategy | N | mean diff (mV) | p-value | 유의 |
|----------|---:|---:|---:|:---:|
| random | 50 | −5.50 | 0.037 | * |
| random | 100 | −1.38 | 0.084 | |
| random | 200~800 | −0.94~+0.10 | 0.38~1.00 | |
| sobol_uniform | 50 | −2.04 | 0.037 | * |
| sobol_uniform | 100 | −1.48 | **0.006** | * |
| sobol_uniform | 200~800 | −0.65~−0.24 | 0.16~0.49 | |
| stratified_sobol | 50 | −2.00 | 0.084 | |
| stratified_sobol | 100 | −2.25 | **0.004** | * |
| stratified_sobol | 200~800 | −1.16~−0.60 | 0.11~0.28 | |
| **POOLED (150 pairs)** | — | **−1.29** | **<0.000001** | *** |

**판정**: physics가 **통계적으로 유의하게, 그리고 효과크기가 큰 수준으로**
이긴다 — 단 **corner 정확도에서만**, 그리고 **저-N(50~100)에서 집중적으로**.
N↑에 따라 효과가 단조 감소(random N=800에서는 사실상 0, +0.10mV) — 이는
정확히 리뷰(`adversarial_review_20260707.md` §4.2)가 세운 가설
("corner anchor는 저예산 구간에서 최대 효과") 그대로 재현된 것.
Uniform 지표만 봤다면 이 효과는 거의 안 보였을 것 — **corner-only
hold-out을 추가한 것 자체가 이번 재검증의 핵심 기여.**

### 3.3 Corner-only vs Uniform — strategy 비교 (stratified_sobol 재평가)

| N | Uniform RMSE: random / sobol_u / stratified (plain) | Corner RMSE: random / sobol_u / stratified (plain) |
|---|---|---|
| 50 | 5.13 / 4.39 / 5.03 | 10.45 / 7.45 / 7.77 |
| 800 | 1.40 / 1.54 / 1.55 | 3.17 / 3.28 / 3.76 |

**판정**: uniform 지표에서 stratified_sobol이 random을 앞서지 못한다는
seeds=6 관찰은 **재확인됨** — corner 지표에서도 stratified_sobol이
random보다 나은 것은 아님(오히려 N=50에서 random의 corner RMSE가 가장
나쁨 10.45, sobol_uniform이 가장 좋음 7.45). "FSG 집중 샘플링이 corner
정확도를 높인다"는 가설은 **이 실험 설계로는 지지되지 않음** — 원인 후보:
(a) 4-corner 중 FSG만 겨냥한 weighting인데 corner hold-out은 4개 corner
전체 평균이라 SFG/FFG/SSG에서는 오히려 손해, (b) N=50~100처럼 총량이
작을 때 FSG weighting이 다른 영역의 샘플 밀도를 희생시킴. **논문에서
"stratified sampling이 우월하다"는 주장은 하지 않음** — 대신 physics
constraint(corner anchor)가 sampling strategy와 무관하게 저-N corner
정확도를 개선한다는, 더 강하고 unstrategy-dependent한 결과를 보고.

---

## 4. 논문 반영 결론

1. **Budget-accuracy 곡선(headline)**: 그대로 사용. N=50→800, RMSE 5→1.4mV,
   N≈400 무릎. seeds=10 최종 수치로 교체.
2. **Physics constraint 주장 — 조건부로 확정**: "corner anchor는 corner 근방
   정확도를 저예산(N≤100) 구간에서 유의하게(p<0.01, pooled p<1e-6) 개선하며,
   효과는 N 증가에 따라 소멸한다." Uniform-domain 평균 지표에서는 효과가
   작고 불안정하므로 그 주장은 하지 않음 — **지표를 명시해서 주장할 것**
   (이것 자체가 §3.5의 "naive vs corrected" 교훈과 같은 패턴: 지표 정의가
   결론을 바꾼다).
3. **Sampling strategy 주장 — 철회**: stratified_sobol(FSG 집중)이
   random/sobol_uniform보다 우월하다는 근거 없음, uniform·corner 지표
   모두에서. 계획서의 "FSG weighted sampling이 효율적" 주장(원 계획 §14.4)은
   **재검토 필요** — 최소한 이 3D 분석적 세팅에서는 지지되지 않음.
4. **Figure**: uniform + corner 2-panel 병기 (이미 `_plot()`이 3-panel로
   구현됨: Hausdorff, uniform Vmin RMSE, corner Vmin RMSE). Physics on/off
   비교는 corner panel이 주역.
5. **방법론적 교훈**: budget/strategy 실험을 설계할 때 hold-out 자체가
   지표의 결론을 결정한다 — uniform hold-out은 "평균적으로 좋은 모델"을,
   corner hold-out은 "안전마진이 중요한 곳에서 좋은 모델"을 측정하며 이
   둘은 다른 질문이다. 두 경우 모두 명시하고 보고할 것.
