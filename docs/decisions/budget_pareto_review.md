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

## 3. 재검증 결과

<!-- FILL AFTER RUN -->

### 3.1 N vs 정확도 (headline, 변함없음 확인)

| N | Vmin RMSE (mV) | Hausdorff (mV) |
|---|---|---|
| 50 | | |
| 800 | | |

### 3.2 Physics on/off — Wilcoxon 검정 결과

| Strategy | N | mean diff (mV) | p-value | 유의? |
|----------|---|-----------------|---------|:-----:|
| ... | | | | |
| **POOLED** | — | | | |

**판정**: <!-- physics가 통계적으로 유의하게 이기는가? -->

### 3.3 Corner-only vs Uniform hold-out — strategy 비교

| N | Uniform: random / sobol / stratified | Corner: random / sobol / stratified |
|---|---|---|
| 50 | | |
| 800 | | |

**판정**: <!-- stratified_sobol이 corner에서는 실제로 유리한가? -->

---

## 4. 논문 반영 결론

<!-- FILL AFTER RUN -->

1. Budget-accuracy 곡선(headline): 그대로 사용 가능 / 조정 필요
2. Physics constraint 주장: <!-- 유지 / 조건부(N<X에서만) / 철회 -->
3. Sampling strategy 주장: <!-- stratified_sobol 권고 유지 / corner-only 지표로 대체 -->
4. Figure: uniform + corner 2-panel 병기 권고 (domain-avg와 corner accuracy는
   다른 이야기이므로 하나로 뭉개면 오해 소지)
