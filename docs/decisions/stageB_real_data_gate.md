# Stage B Real-Data Gate — 4D with PG/PD Skew (GO)

> Date: 2026-07-13
> Script: `python/scripts/stageB_real_data.py`
> Data: `python/data/260713_stageB_snmr.xlsx` (sheet `stageB_snmr`)
> Output: `python/results/stageB_real/` (metrics.txt, go_decision.txt, contour PNG, surrogate_stageB.pth)
> Predecessor: Stage A gate `stage4_real_data.md` (2026-07-09, GO)

## Verdict: **GO** (2/2 hard criteria PASS, FSG-worst qualitatively confirmed)

Second real-data gate, first on the **4D input `[cn, sk, pu, Vop]`** where
`sk` = PG-PD Vth skew (PG = cn+sk, PD = cn−sk). Hand-transcribed in-house
PrimeSim SNMR results, **348 conditions × 5 Vop (0.4–0.8) = 1745 samples**.

| Criterion | Result | Verdict |
|-----------|--------|---------|
| hold-out mu R² ≥ 0.95 | **0.9785** (RMSE 6.47 mV) | PASS |
| Vmin gradient direction | dVmin/dcn=−0.00152 (<0), dVmin/dpu=+0.00138 (>0) | PASS |
| FSG worst corner | auto-check SKIP (see below) — qualitatively CONFIRMED | PASS* |

## Key results

- **Fit**: mu R²=0.9785 / RMSE 6.47 mV; sigma R²=0.5304 / RMSE 0.18 mV.
  Low sigma R² is expected — σ_SNMR is near-constant (12.8–15.5 mV across the
  whole design), so there is almost no variance to explain; 0.18 mV RMSE is
  excellent in absolute terms. (Stage A saw the same pattern.)
  Split = condition-grouped 15% hold-out (296 train / 52 hold-out conditions).
- **Lengthscale hierarchy** (standardized-input ARD, mu GP):
  `ell_cn=6.28 < ell_pu=7.13 ≈ ell_sk=7.21`, `ell_Vop=5.06`.
  → **cn (PG baseline) is the most sensitive process dim** (ell_pu/ell_cn=1.14),
  reproducing the Stage A first-real-data PG≫PU signal (weak but correct
  direction). **Skew sensitivity ≈ PU** (ell_pu/ell_sk=0.99) — the new skew dim
  is real but comparatively gentle, consistent with the raw `mu vs sk` scatter
  (slight positive slope).
- **Corner Vmin** (nearest sampled condition to each ideal corner, sk≈0):
  FSG **>0.8 V** (Z tops out at 6.10 < 6.5 within 0.4–0.8) > SSG 0.487 V >
  FFG 0.478 V > SFG **<0.4 V** (censored). Ordering FSG→SFG is exactly physical
  (fast-N/slow-P worst for read stability, fast-P best). The contour surface
  (fig a) shows the same: FSG corner reddest, SFG bluest, clean 0.48 V median
  diagonal.

### *FSG worst-corner auto-check = SKIP (why it is still a PASS)

The automated check compares finite Vmin values with `max()`. FSG's Vmin is
**not finite within the sampled Vop range** — its Z-curve never reaches Z=6.5
by Vop=0.8, i.e. Vmin(FSG) > 0.8 V. Because FSG is the *only* corner that fails
to cross while all others cross at ≤0.49 V, FSG being the worst corner is
**confirmed**, not indeterminate; the code just cannot put a number on it.
Two consequences worth carrying forward:

1. The gate logic should treat "FSG censored-high (>max Vop) while others finite"
   as an explicit worst-corner PASS rather than SKIP. (Minor script polish, not
   a re-run — the Z-curves already settle it.)
2. **The worst skew-augmented corner's Vmin exceeds the 0.8 V ceiling.** Stage A
   concluded "real-data crossing 100% within 0.4–0.8" — that held for the Stage A
   distribution, but Stage B's extreme skew corners (e.g. nearest-FSG
   (cn=−60, sk=−14, pu=+58): PG=−74, PD=−46, very fast pass-gate) push worst-case
   Vmin above 0.8 V. Inverse estimation / contour near the FSG corner is therefore
   extrapolation above the sampled Vop ceiling. Not a gate failure (surrogate
   quality + gradients are sound), but flagged for the assist / Vmin-target work.

## Prerequisite fixes made this session

1. **Parser sk support was half-implemented** — `hspice_io._parse_manual_df`
   already built the 4D X with sk, but `_vop_interpolation_outlier_qc` still
   unpacked the condition key as a 2-tuple `(c, p)` while building it as the
   3-tuple `(cn, sk, pu)` when sk is present → `ValueError: too many values to
   unpack`. Fixed to unpack sk-agnostically (and carry sk into the flag dict).
   This closes the workflow_state OPEN item "add sk to parse_manual_xlsx".
2. **Transcription QC on the raw sheet** (before the gate) — the now-working
   vop-trend QC plus grid-integrity/std-range checks caught, over three user
   iterations: 3 pu-sign / coordinate-collision condition errors (fixed by user),
   then 9 avg cells (5 gross decimal slips 8079→80.79 etc. + a 3-cell shifted
   condition) and 2 std decimal slips (1284→12.84, 135→13.5). All 11 residual
   cells fixed in-place (backup: `260713_stageB_snmr_pre_fix_backup.xlsx`);
   final QC clean (0 flags, 348 conditions, all mu monotonic in Vop except the
   one intentional benign duplicate condition (16,0,14)).

## SNMR-only downstream analyses (2026-07-13, script `stageB_snmr_analysis.py`)

Run on the surrogate retrained on all 1745 samples (Vtrip/write-margin data not
yet available — `stageB_bwrm` sheet has 1 row, `stageD_*` empty). Outputs in
`results/stageB_real/` (skew_tolerance / sensitivity / skew_contour_shift PNGs,
`snmr_analysis_summary.txt`).

**A. PG-PD skew tolerance.** `dVmin/dsk ≈ −2.6 mV/mV` across operating points
(−6.9 near the SFG floor). **Positive skew (PG slower than PD → less read
disturb) lowers Vmin**, i.e. improves read stability — sign matches the gate's
dVmin/dsk. Over the full sk∈[−20,+20] range Vmin swings **~110 mV**, so skew is
a materially strong knob, not a nuisance dim. Allowable-skew window (keep Vmin ≤
budget): benign corners (TT/SFG/FFG/SSG) tolerate the **entire** ±20 mV range at
a 0.55 V budget; the **FSG worst corner is skew-constrained** — needs sk ≥ +15
(0.55 V budget) or sk ≥ −6 (0.60 V). → positive skew is a genuine design lever
at the worst corner. (This is the concrete form of the plan's "required WLUD →
allowable PG-PD skew tolerance" reframing.)

**B. GP-based Sobol sensitivity of Vmin** (Saltelli S1 / Jansen ST, N=2048 base,
physical ranges cn/pu ±60, sk ±20):

| dim | S1 (first) | ST (total) |
|-----|-----------|-----------|
| cn  | 0.484 | 0.507 |
| pu  | 0.364 | 0.400 |
| sk  | 0.138 | 0.145 |

Near-**additive** (ΣS1≈0.99, ST≈S1 → weak interactions). cn dominates (~48%),
pu second (~36%), **skew ~14%**. Note skew's smaller share is partly its
narrower ±20 mV range vs ±60 for cn/pu — its *per-mV* sensitivity is comparable
to pu (consistent with ARD ell_sk≈ell_pu). This is the GP-based sensitivity the
plan called for (not weighted-Sobol → no Saltelli bias).

**C. Skew-shifted Vmin=0.6 V boundary** moves ~monotonically up-left in the
(cn,pu) plane by ~20–30 mV per +20 mV skew; positive skew enlarges the pass
region. Clean, near-parallel offset of the pass/fail contour.

**Takeaway**: PG-PD skew is a real secondary Vmin driver (~14% of variance,
~2.6 mV/mV), and positive skew is an actionable lever specifically at the FSG
worst corner where the baseline (cn,pu) margin is thinnest.

## Follow-ups

- Adopt the FSG-censored-high → worst-corner PASS rule in the gate script.
- Carry the ">0.8 V worst-corner" note into the assist / Vmin-target analysis and
  the Vop-range sufficiency claim (Stage A's "0.4–0.8 sufficient" is
  distribution-dependent; skew corners breach it).
- Fix `src.data.stratified_train_test_split` (groups by `X[:,:2]`, which is
  (cn,sk) not the full condition in Stage B) — the gate used a local
  device-column-grouped split to avoid this; the shared helper should take a
  `vop_col`/`n_device` and group by all device dims.
- Stage C (+Vtrip write margin) and Stage D (9D Sobol) per `revised_sim_plan_20260709.md`.
