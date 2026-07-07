# Physics-Constrained GP Surrogate for Inverse SRAM Vmin Estimation

> **Version**: 2026-07-07 (v0.4)
> **Status**: Toy (Gate 0) complete and audited; Phase-2 (real-data) infrastructure implemented; HSPICE farm data pending.
> **Change log v0.3 → v0.4**: ablation numbers replaced after fixing a GP
> input-scaling bug and an L_pelgrom no-op (all v0.3 physics-constraint
> figures were confounded); added lobe-resolved effective z-score, the
> noise-aware GP, gradient-based inversion, and the metric-definition
> framework; corrected the Z_target derivation. See
> `docs/decisions/session_20260706_root_cause_fixes.md` and
> `docs/decisions/adversarial_review_20260707.md`.

---

## 1. Introduction

### 1.1 Motivation

SRAM occupies the largest area in modern SoCs and dominates chip yield. The
**Vmin** — the lowest voltage at which a cell operates reliably — is the
single most critical yield metric, yet it is strongly affected by process,
voltage, temperature, and aging (PVTA) variation. Conventional Vmin
estimation runs Monte-Carlo (MC) HSPICE per PVTA condition across corners;
this is prohibitive for the ~6-sigma tails that large arrays require, and it
only tells the designer the Vmin *after* the fact — not which parameters to
tighten to *reach* a target Vmin.

### 1.2 Proposed Approach

We learn a surrogate once (fixed one-time simulation cost) and then answer
both forward and **inverse** Vmin questions with zero further simulation:

1. **GP surrogate** maps PVTA parameters → read-SNM statistics (μ, σ).
2. **Differentiable physics layer** converts (μ, σ) → Vmin through a
   z-score / yield model, exactly (a hard analytic constraint, not a
   learned approximation).
3. **Inverse estimation** back-propagates through the whole pipeline to
   recover the feasible design region (and the minimum assist) for a target
   Vmin.

The inverse formulation is the core novelty: prior surrogate/active-learning
work (Guo 2024, Yin 2022/2023) addresses *forward* yield only.

### 1.3 Contributions

| # | Contribution | Description |
|---|--------------|-------------|
| C1 | **Inverse Vmin estimation via a differentiable physics layer** | End-to-end autograd from design variables through GP posterior mean and the Vmin transform; recovers the minimum-assist design on the Vmin=target manifold. Demonstrated to match a 1-D bisection to <5×10⁻³ WLUD while scaling to multiple free variables where grid search does not. |
| C2 | **A metric-definition framework for inverse accuracy** | Design-range feasibility, left-censoring of Vmin below the sampled Vop range, and assist-active scoring. Without these, a naive metric over-reports error by ~60× (0.16 V vs 2.6 mV on identical predictions). |
| C3 | **Lobe-resolved effective z-score** | Read SNM = min(left, right lobe); a Gaussian z on the min's (μ,σ) is optimistically biased by +0.7σ (independent) to +1.9σ (anticorrelated lobes) at Z≈6 — 70–190 mV of Vmin. We compute the exact union-fail z, closed-form and differentiable. |
| C4 | **Noise-aware GP unifying MC budgets** | Per-condition MC standard errors enter a FixedNoiseGaussianLikelihood, so low-budget and high-budget conditions coexist in one model (a principled alternative to co-kriging when the only difference is sample count, not model fidelity). |
| C5 | **Physics-constrained GP, honestly ablated** | With input standardization fixed, corner-anchor augmentation gives a real ~27% Vmin-RMSE reduction, concentrated in the tail (p95 −37%); L_mono/L_pelgrom are marginal on monotone analytic data. |

---

## 2. Methodology

### 2.1 Input Space

**Core 3D** (always present, Vop at column `VOP_COL = 2`):

| Variable | Symbol | Range | Unit |
|----------|--------|-------|------|
| NMOS common shift (PG=PD) | common_N | [−60, 60] | mV |
| PMOS shift | PU | [−60, 60] | mV |
| Operating voltage | Vop | [0.4, 0.9] | V |

**Extended dims** (added stage by stage): WLUD ratio (Vwl/Vop assist),
Temp, then W, σL, σG, μ_mobility for the full 8-D DOE.

**Output**: y = [μ_SNMR, σ_SNMR] ∈ (N, 2), fixed. The optional lobe-resolved
path (§2.7) preserves this shape.

All inputs are **StandardScaler-normalized before GP training** — this is
not cosmetic (§2.5).

### 2.2 GP Model Architecture

- **μ GP** (`ExactGPModel`): Matern-5/2 + ARD over all dims.
- **σ GP** (`AdditiveGPModel`): k_op(Vop, [WLUD…]) + k_dev(common_N, PU),
  separating voltage from corner dependence.
- Both trained by `ExactMarginalLogLikelihood` + Adam, independently.

For any posterior-gradient use (L_mono, gradient inversion) we evaluate in
eval mode with `prediction_strategy = None` so the Cholesky is rebuilt with
current parameters and gradients flow to the inputs — `gp.forward()` returns
the constant-mean prior and must not be used.

### 2.3 Differentiable Physics Layer (Vmin)

Per condition: predict μ(Vop), σ(Vop) on the 6 Vop levels →
Z(Vop) = μ/σ → Vmin = interpolate{Vop | Z(Vop) = Z_target}.

**Z_target derivation** (corrected in v0.4). For an array of N_bits cells at
per-block yield Y:

  p_fail_per_bit = 1 − Y^(1/N_bits),  N_bits = Mb·10⁶,
  Z_target = Φ⁻¹(1 − p_fail_per_bit) = norm.isf(p_fail_per_bit).

For 64 Mb @ 99.9%, **Z_target ≈ 6.64** (`derive_z_target()`). The toy runs
keep a fixed Z=6.0 for cross-session comparability; note this is slightly
*optimistic* (lower Vmin), not "conservative" as v0.3 stated — switching to
6.64 shifts all Vmin uniformly and leaves contour shapes and GP-quality
metrics unchanged. The "×6 transistors" factor sometimes applied to N_bits
is wrong: the failure unit is the cell.

**Left-censoring.** When Z(Vop_min) already exceeds Z_target, the true Vmin
lies below the sampled range; the transform returns a floor placeholder that
must be flagged (`compute_vmin_from_z(return_censored=True)`) and excluded
from continuous error metrics (§3.5).

### 2.4 Physics-Informed Losses

- **L_boundary** (corner anchoring): 4 global corners × 6 Vop virtual
  observations augmented into the training set (exact-GP hard constraint).
- **L_mono**: ReLU(−∂μ/∂Vop)² on probe collocation points (posterior
  gradient).
- **L_pelgrom**: posterior σ(Vop) pulled toward SIGMA₀ + slope·(0.9−Vop).
  (v0.4 fix: the historical implementation computed this under
  `torch.no_grad()` on the train-mode prior — a zero-gradient no-op; it is
  now an eval-mode posterior penalty with a data-fixed target.)

### 2.5 Input Standardization — a first-order effect, not a detail

Raw inputs span mV (cn, pu ≈ ±60) to volts (Vop) to dimensionless ratios
(WLUD ≈ 0.1 wide). GPyTorch's default lengthscale init cannot bridge this in
a normal iteration budget, so unstandardized training silently
under-converges. This was the root cause of the earlier "Stage-3 NO-GO"
(4-D μ RMSE 0.049 vs 0.0023). With standardization the plain GP already
reaches the observation-noise floor; **most of what v0.3 attributed to
physics constraints was really this fix** (§3.1). All inputs, probe points,
and prediction inputs share one fitted scaler.

### 2.6 GP → NN/PINN Transition Criteria

Switch to NN+PINN only when GP is demonstrably insufficient:

| Criterion | Threshold | Toy status |
|-----------|-----------|------------|
| Contour Hausdorff | > HSPICE noise floor (3–5 mV) | 0.35–0.5 mV — not triggered |
| ℓ_pu/ℓ_cn (PG≫PU) | > 2.0 in the *wrong* direction | see §4.3 |
| Corner Vmin bias | > 3σ vs other corners | not triggered |

### 2.7 Lobe-Resolved Effective Z-score (optional y-definition)

Read SNM is the **minimum** of the two butterfly lobes. Applying a Gaussian
z to the min's (μ, σ) is optimistically biased because the min's left tail
is heavier than a moment-matched Gaussian. From per-lobe statistics
(μ_L, σ_L, μ_R, σ_R, ρ_LR):

  p_fail = P(L<0) + P(R<0) − P(L<0, R<0),   Z_eff = Φ⁻¹(1 − p_fail),

with the joint term from the bivariate-normal CDF (Owen's T; matches SciPy
to 4×10⁻¹⁵). `effective_mu_sigma()` maps this back to the (μ, σ) convention
(μ_eff/σ_eff ≡ Z_eff, σ_eff = √(σ_L σ_R)) so the downstream pipeline is
untouched. The bias, verified in closed form and by MC:

| ρ_LR | Z_gauss(min) | Z_true | bias | ≈ Vmin |
|:----:|:------------:|:------:|:----:|:------:|
| −0.7 | 7.77 | 5.89 | +1.89σ | +189 mV |
| 0.0 | 6.58 | 5.89 | +0.70σ | +70 mV |
| +0.9 | 5.92 | 5.90 | +0.02σ | +2 mV |

Since real lobes respond oppositely to asymmetric mismatch (ρ ≤ 0 is
plausible), this is a first-order correction, not a nicety. ρ_LR is measured
in the Phase-2 pilot; the per-lobe `.MEASURE` requirement is fixed before
the farm run.

### 2.8 Noise-Aware GP

Per condition we record N_MC and bootstrap standard errors (sem_μ, sem_σ;
bootstrap rather than σ/√(2N) because the σ-SEM is kurtosis-sensitive).
These variances feed a `FixedNoiseGaussianLikelihood` (with
`learn_additional_noise`), so the GP down-weights noisy/low-budget
conditions automatically. This is also the mechanism that unifies mixed MC
budgets in one model: because MC low-fidelity differs only in *variance*
(same simulator, fewer samples), a heteroscedastic single GP is the correct
model — the Kennedy–O'Hagan bias term is unnecessary. (On corrupted
synthetic data: μ RMSE 0.0059 → 0.0020 vs a homoscedastic GP.)

---

## 3. Experimental Results

> Headline numbers below are on the controlled **analytic testbed**; real
> HSPICE numbers replace them in Phase 2. Analytic results are used only to
> validate the machinery and metric definitions, never as the paper's final
> accuracy claims.

### 3.1 Ablation (re-run after the v0.4 fixes)

| Config | μ R² | Vmin RMSE | Hausdorff | Note |
|--------|:----:|:---------:|:---------:|------|
| Baseline | 0.999 | **1.26 mV** | 0.50 mV | standardized GP at noise floor |
| +L_mono | 0.999 | 1.59 mV | 0.59 mV | adds only training noise on monotone data |
| +L_boundary | 0.999 | **0.92 mV** | 0.40 mV | −27% vs baseline |
| +Mono+Boundary | 0.999 | 1.32 mV | 0.46 mV | — |
| +All (··+Pelgrom) | 0.999 | **0.90 mV** | 0.35 mV | best |

**Corrected findings** (contrast the retracted v0.3 "L_boundary = 20.9%"):
input standardization is the primary factor (baseline alone 6.52 → 1.26 mV);
on top of that, corner anchoring gives a genuine ~27% reduction, largest in
the tail. L_mono is inert on strictly monotone analytic data (re-evaluate on
real data). μ RMSE sits at the 0.002 observation-noise floor throughout.

### 3.2 Physical Consistency

- ∂Vmin/∂common_N < 0 and ∂Vmin/∂PU > 0 (both physical), cosine similarity
  ≈ 1.0 vs the analytic gradient.
- After standardization the GP recovers a sensitivity **hierarchy**: on
  asymmetric synthetic data (PG 2×/3×), ℓ_pu/ℓ_cn tracks the imposed ratio
  (0.86 → 1.31), where the unstandardized GP had frozen it at ≈1.0. The
  current toy coefficients make PU slightly *more* sensitive, so the
  PG≫PU lengthscale test is deferred to real data (§4.3) rather than used as
  a gate.

### 3.3 Inverse Assist Estimation (Stage 3)

Target Vmin = 0.60 V, WLUD design range [0.90, 1.00], corrected metrics:

| Surrogate | Feasibility agree | WLUD RMSE | Vmin RMSE (assist-active) | p95 |
|-----------|:-----------------:|:---------:|:-------------------------:|:---:|
| plain GP | 99.9% | 0.0016 | 3.14 mV | 6.15 mV |
| physics-constrained | **100.0%** | 0.0013 | **2.55 mV** | **3.87 mV** |

Physics constraints help most in the tail (p95 −37%), consistent with
corner anchoring correcting extrapolation.

### 3.4 Gradient-Based Inversion (C1 demonstration)

Three free variables x = (common_N, PU, WLUD), Adam through the
differentiable pipeline with a sigmoid box reparameterization and
feasibility barriers for the flat (censored / read-fail) regions. From 8
starts across the plane, all converge to the minimum-assist design on the
Vmin = 0.6 V manifold: **max |Vmin − target| = 2.41 mV**, and every
converged design matches a 1-D WLUD bisection at its own (cn,pu) slice to
**0.0000**. Gradient and grid agree, but the gradient walk is O(iters) per
start vs O(K³) for a 3-D grid — the basis for scaling inversion to higher-
dimensional design spaces.

### 3.5 Why the Metric Definition Is a Contribution (C2)

The same predictions score 0.16–0.26 V RMSE under a naive definition and
2.6–4.9 mV under the corrected one — a ~60× difference — because the naive
version (i) compared a GP that searches WLUD∈[0.9,1] against ground truth
over [0.5,1], (ii) treated the censored 0.35 V floor as a measurement, and
(iii) counted no-assist-needed cells (natural margin) as error. Reporting
inverse accuracy therefore *requires* specifying design-range feasibility,
censoring, and assist-active scoring.

### 3.6 Variable-Dimensionality

StandardScaler, both GP kernels, probe/anchor generators, and the full
train→contour pipeline are verified 3-D through 8-D (auto ARD, additive
kernel group growth). Six test suites pass.

---

## 4. Discussion

### 4.1 Corner anchoring: cheap and tail-focused
24 virtual corner points buy a ~27% Vmin-RMSE reduction concentrated at
p95. For real PDKs this argues that a handful of corner simulations are
worth their cost — but the effect is now correctly separated from the
standardization fix that dominates the baseline.

### 4.2 L_mono on monotone data
Zero penalty throughout on the analytic model; on real data with
near-threshold non-monotonicity it may matter. Kept, but not claimed.

### 4.3 PG ≫ PU hierarchy — deferred, not failed
The toy generator lacks the hierarchy, so its lengthscales cannot show it
(and the standardized GP *does* recover imposed asymmetry, §3.2). This is a
real-data measurement, reported in Discussion rather than used as a Go gate.

### 4.4 Tail validity of the z-score
The z=μ/σ Gaussian extrapolation is a **margin metric** (industry-standard
for Vmin spec setting), not an absolute fail-rate predictor. We defend it by
(i) framing, (ii) Anderson–Darling/Q-Q QC in the z-crossing Vop band, and
(iii) optional importance-sampling spot checks. The lobe-resolved z (§2.7)
removes the largest *systematic* component of the error.

---

## 5. Status & Roadmap

### 5.1 Done
- GP + differentiable physics layer; corrected Z_target; censoring-aware
  Vmin.
- Root-cause fixes (input scaling, L_pelgrom) and honest ablation.
- Metric-definition framework; inverse assist GO (2.55 mV).
- Lobe-resolved Z_eff, noise-aware GP, MC-stats parser/QC (all tested).
- Budget-vs-accuracy sweep and gradient-inversion demos.

### 5.2 Next (see `docs/plans/phase2_to_paper_plan.md`)
| Priority | Task |
|----------|------|
| 🔴 | HSPICE Step A validation deck **with per-lobe measures + ρ_LR** |
| 🔴 | Stage-4/5 real-data forward + inverse validation (noise-aware GP) |
| 🟡 | Active-learning (contour-targeted) and budget-allocation experiments |
| 🟡 | Write-margin (WSNM) pilot → Vmin = max(read, write) |
| 🟢 | 8-D Sobol DOE + sensitivity; PINN only if a transition trigger fires |

### 5.3 Venue
IEEE TCAD (primary, full method+experiments); DAC/ICCAD as a compressed
alternative. Draft starts once Phase-2 forward/inverse and the §3.4/§3.5
methodology results are in on real data.

---

## 6. References (internal)

| Document | Location |
|----------|----------|
| Master plan | `sram_vmin_inverse_estimation_plan.md` |
| Phase-2 → paper plan | `docs/plans/phase2_to_paper_plan.md` |
| Root-cause fixes | `docs/decisions/session_20260706_root_cause_fixes.md` |
| Adversarial review | `docs/decisions/adversarial_review_20260707.md` |
| Ablation log | `docs/decisions/physics_ablation.md` |
| Deck generation | `docs/plans/deck_generation_plan.md` |

External: Singhee & Rutenbar TCAD'10 (QMC); Guo ISEDA'24 (MFNN+IS); Yin
DAC'22 / ASPDAC'23 (Bayesian AL); Liu DAC'23 (OPTIMIS/IS); Gupta & Calhoun
TCAS-I'21 (dynamic Vmin); Kinoshita TSM'25 (space-filling LHD).

---

*Living document; revised each major phase. v0.4 supersedes v0.3's
physics-constraint numbers in full.*
