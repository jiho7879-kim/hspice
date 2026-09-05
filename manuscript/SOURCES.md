# 논문에 실제로 쓰이는 파일 — 그리고 안 쓰이는 파일

`python/`에 스크립트 43개, `src` 모듈 14개, 데이터 15개가 있다.
**v3 논문(9D 최종 배치, 읽기)에 실제로 기여하는 것은 그중 일부다.**
아래 목록 밖의 것은 건드리지 않는다.

---

## ✅ 데이터 — 논문이 쓰는 것

| 파일 | 내용 | 논문 위치 |
|---|---|---|
| `python/data/sheet_final_snmr_seed2027.xlsx` | **최종 읽기 배치**. 2,000조건 × 5 Vop = 10,000행, 전사 완료 | §V 전체, §VI, §VII |
| `python/data/infab_snmr_tail.xlsx` | **팹 tail 진단 회신**. 9조건 × MC 100,000, 분위수 사다리 5점 | §II-D, §V-F |
| `python/data/260713_stageB_snmr.xlsx` | 4D 파일럿 배치 (skew=0 평면) | §V-G 외부검증 |
| `python/data/sheet_final_vtrip_seed2028.xlsx` | 쓰기 배치. **8,000/10,000행** (0.8 V 미완) | §VII-D 예비, §VIII-C |
| `python/data/hspice_real_corner.xlsx` | 고정 코너 5종 실측 | §V-D 코너 서열, §V-F 실리콘 상한 |
| `python/data/hspice_real.xlsx` | stage4 실측 (→ `results/stage4_real/dataset_real.npz`) | §V-F 직교성 도해 |

## ❌ 데이터 — 안 쓰는 것

`dataset_synth.npz` `demo_analytic.npz` `ngspice_test.npz` (전부 토이/합성) ·
`final_2000_seed2026.xlsx` `stageD_500_seed2026.xlsx` (구세대 파일럿) ·
`260713_stageB_snmr_pre_fix_backup.xlsx` (백업) · `fixed_corner.xlsx` ·
`inhouse_condition_snmr.xlsx` `inhouse_condition_vtrip.xlsx` (전사용 빈 시트 — §III 방법 근거일 뿐 결과 아님)

---

## ✅ 라이브러리 — `python/src` 중 살아있는 8개

```
utils.py         derive_z_target, 표준화, 공통 상수      ← 모두가 의존
models.py        GP 커널/평균 정의                       ← surrogate가 의존
surrogate.py     ExactGP + AdditiveGP 래퍼               ← 본체
data.py          그룹 분할(mirror-group), 로더            ← §III-D 누수 방지
physics_layer.py 미분가능 Vmin 산출 (z → Vmin)            ← §IV-C
contour.py       등고선 추출                              ← §V-D, Fig.4
hspice_io.py     xlsx 파서 + 물리범위 QC                  ← stageB/C
final_data.py    최종 배치 canonical QC 로더 (07-21 신규)  ← §V 전체의 단일 입구
```

## ❌ 라이브러리 — 논문 결과를 만들지 않는 것

`physics.py` (해석적 토이 모델) · `condition_gen.py` `inhouse_deck_gen.py`
(덱 생성 — §III 방법 서술의 근거지만 수치를 만들지 않음) ·
`primesim_io.py` `harness.py` (미사용)

---

## ✅ 스크립트 — 재유도의 출발점 (그대로 쓰지 말고 `code/`로 다시 쓸 것)

| 기존 스크립트 | 담당 | 재유도 후 이름 |
|---|---|---|
| `forward_model_clean.py` | §V-B 순방향 정확도 | `code/v_b_forward.py` |
| `final_snmr_seed2027_spec_review.py` | §V-D 사양 판정 | `code/v_d_spec.py` |
| `tail_correction_passrate.py` | §V-D 보정 후 통과율 | 위에 통합 |
| `result3_inverse.py` | §V-E 역추정 | `code/v_e_inverse.py` |
| `infab_snmr_tail_diag.py` + `redo_lobe_judgment.py` | §V-F lobe 측정 | `code/v_f_lobe.py` |
| `stageB_snmr_analysis.py` + `stageB_leakage_check.py` | §V-G 외부검증, §III-D 누수 | `code/v_g_external.py` |
| `final_snmr_seed2027_extrap_test.py` | §VI-A 전압 레벨 | `code/vi_a_vop.py` |
| `budget_pareto.py` | §VI-B 조건 수 | `code/vi_b_budget.py` |
| `final_snmr_seed2027_sensitivity.py` + `result34_clean.py` | §VII 민감도 | `code/vii_sensitivity.py` |
| `stageC_skew_cooptimization.py` | §VII-D skew | `code/vii_d_skew.py` |
| `corner_verification.py` | 코너 서열 | `code/corner_check.py` |
| `zeff_vs_z_contour.py` | §V-F 직교성 도해 | 그림으로 흡수 |

**주의**: `infab_snmr_tail_diag.py`는 팹에 보낸 원본이라 **수정 금지**.
`bias_at_target()`만 임포트해서 쓴다.

## ❌ 스크립트 — 논문과 무관 (31개)

- **토이/합성**: `demo.py` `demo_4d.py` `demo_assist.py` `demo_gradient_inversion.py`
  `debug_assist.py` `validate_assist_sweep.py` `ablation.py` `diagnostics.py` `train.py`
- **ngspice 트랙**: `stage1_ngspice.py` `gen_ngspice_data.py` `test_ngspice.py`
  — 사용자 지시로 2026-07-06 중단
- **구세대**: `legacy_sobol_regen.py` `stage4_real_data.py` `corner_retrain_*.py`
  `final_snmr_seed2027_analysis.py` (→ `forward_model_clean`으로 대체됨)
- **덱 생성**: `gen_condition_sheet.py` `gen_hspice.py` `gen_inhouse_condition_sheet.py`
  — 시뮬 이전 단계, 결과 없음
- **학습 실험**: `train_sparse_gp.py` `train_float32.py` `train_threaded.py`
  — **Sparse GP는 채택 불가**: Vmin RMSE 33.95 mV vs exact 14.77 mV
- **폐기**: `gen_paper_figures.py` (구 8종 구조) `gen_verified_paper.py`
  `stageB_real_data.py` `stageC_readwrite.py` (stageB/C 분석본으로 대체)
