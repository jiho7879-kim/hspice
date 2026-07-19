# Physics-Constrained Gaussian Process Surrogates for Inverse SRAM Vmin Estimation

> Version v0.5 (2026-07-14). Restructured around the final 9-D real-data
> batch; the progressive (3D→4D→9D) narrative is retired in favor of a
> contribution-driven structure (audit decision D6). `[TBD]` marks numbers
> pending transcription of the final batch; `[Fig N]` blocks are placeholders.

---

## Abstract

The minimum operating voltage (Vmin) of SRAM governs the yield of large
arrays, yet estimating it under process variation requires thousands of
Monte-Carlo (MC) circuit simulations per condition — and the question
designers actually ask, *which variation combinations violate a target
Vmin*, is an inverse problem that forward MC does not answer. We combine a
Gaussian-process (GP) surrogate from process-variation parameters to
read static-noise-margin (SNM) statistics with a differentiable physics
layer that converts those statistics into a yield-referenced Vmin, so that
one fixed simulation budget serves both forward prediction and
gradient-based inverse estimation. A lobe-resolved effective z-score removes
the optimistic bias of min-statistics (up to +1.9σ at Z≈6) in closed form,
and a noise-aware GP absorbs heterogeneous MC budgets through per-condition
standard errors. On production-calibrated MC data from an advanced FinFET
node — 2,000 conditions × 5 supply voltages — the method reaches a hold-out
μ coefficient of determination of [TBD] and a Vmin-contour Hausdorff
distance of [TBD] mV, and gradient inversion agrees with bisection
cross-checks to within [TBD] mV.

---

## 1. Introduction

SRAM occupies the largest area in modern SoCs and dominates chip yield.
Vmin — the lowest voltage at which a cell reads and writes reliably —
depends strongly on process variation, and verifying the ~6σ tail yield
demanded by 256 Mb-class arrays with direct MC is computationally
impractical. The deeper problem is the direction of the question. A
simulation flow reports the Vmin of a given variation condition; what
design and process engineers want is the reverse — the boundary in
variation space where a target Vmin is violated, and the minimum assist
required to move an operating point back across it.

We train the surrogate once and answer both forward and inverse queries
with no further simulation. A GP learns the map from variation parameters
to SNM statistics (μ, σ); a differentiable physics layer converts (μ, σ)
into Vmin through a z-score yield model — exactly, as an analytic
constraint rather than a learned approximation. Because the entire pipeline
is differentiable in its inputs, points on a target-Vmin contour can be
reached directly by gradient descent.

Our contributions:

1. **Inverse Vmin estimation through a differentiable physics layer.**
   End-to-end autograd from design variables through the GP posterior mean
   and the Vmin transform; accuracy is cross-checked against 1-D bisection
   and the method extends to multivariable inverse problems where grid
   search is infeasible.
2. **A metric-definition framework for inverse accuracy.** Design-range
   feasibility, left-censoring of Vmin below the sampled voltage range, and
   assist-active scoring. A naive metric over-reports the error of
   identical predictions by roughly 60× (0.16 V vs 2.6 mV).
3. **Lobe-resolved effective z-score.** Read SNM is the minimum of two
   butterfly lobes; a Gaussian z on the min's (μ, σ) is optimistic by
   +0.7σ (independent lobes) to +1.9σ (anticorrelated) at Z≈6. We compute
   the exact union-fail z in closed form (Owen's T), preserving
   differentiability.
4. **A noise-aware GP that unifies heterogeneous MC budgets.**
   Per-condition MC standard errors enter a heteroscedastic likelihood, so
   low- and high-budget conditions coexist in one model — a principled
   replacement for co-kriging when fidelities differ only in sample count.
5. **Honestly ablated physics constraints, validated on real data.** With
   input standardization controlled for, corner-anchor augmentation
   contributes mainly at low budgets and in the tail (Vmin RMSE −27%, p95
   −37% on the analytic testbed; real data [TBD]).

In addition, §3.5 reports a **transcription-free experiment protocol** for
fab environments from which decks and results cannot be exported (a shared
seed for deterministic condition generation eliminates hand-transcription
of conditions), and the **mirror-twin leakage** we discovered in a pilot
design together with the group-split evaluation discipline it necessitates.
Both are practically reusable lessons for validating surrogates on
industrial data.

`[Fig 1 — Pipeline overview: variation parameters → GP(μ,σ) → physics
layer → Vmin, forward and inverse arrows. Placeholder.]`

---

## 2. Problem Setup

### 2.1 Read stability and lobe statistics

The read SNM of a 6T cell is the minimum of the two butterfly-curve lobes.
MC flows conventionally record the min's (μ, σ), but the min's left tail is
heavier than a moment-matched Gaussian, so z = μ/σ systematically
underestimates the failure probability. From per-lobe statistics
(μ_L, σ_L, μ_R, σ_R, ρ_LR),

p_fail = P(L<0) + P(R<0) − P(L<0, R<0),  Z_eff = Φ⁻¹(1 − p_fail),

which removes the bias; the joint term is the bivariate-normal CDF via
Owen's T — closed-form and smooth in all inputs. Mapping Z_eff back to an
effective (μ, σ) pair (μ_eff/σ_eff ≡ Z_eff, σ_eff = √(σ_Lσ_R)) leaves the
downstream pipeline untouched.

### 2.2 Vmin definition and yield target

For a condition x, Vmin(x) linearly interpolates the voltage at which
z(Vop) = μ/σ over the grid Vop ∈ {0.4, …, 0.8} V crosses a target Z_t.
Z_t derives from the array yield model: for 256 Mb at 99% Poisson yield,
p_fail = −ln(0.99)/(256·10⁶) and Z_t = Φ⁻¹(1 − p_fail) ≈ 6.50. The failure
unit is the cell (bit); multiplying by six transistors is incorrect.
Conditions with z(0.4 V) > Z_t have Vmin below the sampled range and are
flagged as left-censored, excluded from continuous error metrics.

### 2.3 The inverse problem

For a target V*, the set {x : Vmin(x) = V*} is a hypersurface (contour) in
variation space. We formalize inversion as (i) extracting the geometry of
this contour and (ii) finding the minimum assist (e.g., wordline
underdrive) that returns a given operating point to it. Both are solved by
gradient descent on the differentiable Vmin(x).

---

## 3. Data Design

### 3.1 Input space

The cell transistors are PU (PMOS pull-up), PD (NMOS pull-down), and PG
(NMOS pass-gate). Inputs are nine device-variation dimensions plus the
supply voltage.

| Variable | Meaning | Range |
|---|---|---|
| cn | NMOS common Vth shift (PG=PD baseline) | ±60 mV |
| sk | PG−PD Vth skew | ±20 mV |
| pu | PMOS Vth shift | ±60 mV |
| lpu | PU local-σ multiplier | [0.7, 1.3] |
| l_com, l_sk | NMOS local-σ common / PG−PD skew | [0.7, 1.3] / ±0.075 |
| mpu | PU mobility multiplier | [0.7, 1.3] |
| m_com, m_sk | NMOS mobility common / PG−PD skew | [0.7, 1.3] / ±0.075 |
| Vop | supply voltage | {0.4, 0.5, 0.6, 0.7, 0.8} V |

Deck parameters are derived: Vth PG = cn+sk, PD = cn−sk; local-σ
PG = l_com+l_sk, PD = l_com−l_sk; mobility likewise.

### 3.2 Rationale for the common+skew parameterization

PG and PD are the same NMOS flavor: their dominant variation sources (gate
stack, channel doping, anneal, litho CD) are shared, and W/L, layout
environment, and flavor differences produce imperfect tracking. Sampling
the two devices independently would spend design points on states that do
not occur in silicon — the same flavor diverging by ±30% in opposite
directions at the mismatch level. The common+skew decomposition implies
corr(l_PG, l_PD) ≈ 0.88, inside the plausible 0.85–0.95 tracking band and
consistent with the Vth treatment (ρ ≈ 0.80). Common and skew are sampled
independently — a property required by the variance-based sensitivity
analysis of §5.6 — and the derived per-device multipliers may extend to
[0.625, 1.375] when the common sits near a range edge, confirmed to be
within the compact model's validity.

`[Fig 2 — Design visualization: (a) quadrant weighting in the (cn, pu)
plane; (b) independent (l_com, l_sk) box and the induced diagonal
(l_PG, l_PD) band. Placeholder.]`

### 3.3 Design of experiments

Read (SNMR) and write (Vtrip) degrade in different worst-case quadrants, so
they use separate deck sets with different (cn, pu) quadrant weights: the
SNMR set allocates 45% to FSG (cn<0, pu>0), the write set 45% to SFG
(cn>0, pu<0). Each set is 2,000 conditions × 5 Vop = 10,000 simulations;
conditions are generated by deterministic pseudo-random draws (PCG64) with
an independent stream per quadrant. Per-condition MC is N_MC = [TBD], with
per-lobe statistics and ρ_LR collected [availability TBD].

### 3.4 A transcription-free protocol

Simulations run inside a fab from which neither netlists nor raw results
can be exported. Because condition generation is deterministic, sharing
only (stage, n_cond, seed, metric, method) makes the fab-side deck loop and
the model-side condition table byte-identical; results come back labeled
only by (Vop, deck number), and no condition is ever hand-transcribed. In a
pilot where conditions *were* transcribed by hand, the row error rate was
about 9% (§3.5) — the protocol is a data-integrity requirement, not a
convenience.

### 3.5 Design pitfalls and evaluation discipline

An early pilot design re-used one QMC stream across all four quadrants,
flipping only the signs of cn and pu. As a result, 75% of conditions had a
mirror twin sharing the remaining seven coordinates, and under a random
hold-out about 74% of test conditions had a twin in training — silently
inflating accuracy metrics. We discovered this by forensic comparison of
transcribed conditions against the reconstructed generator, then (i)
removed the cause in the present design by giving each quadrant an
independent stream and (ii) enforced mirror-group splits for any evaluation
that touches the legacy data. Because design-induced leakage of this kind
inflates metrics without any implementation bug, we recommend that
surrogate-validation studies report their design-generation code and split
rule together.

### 3.6 Measurement and QC

Per condition × voltage, MC histograms are checked with Anderson–Darling
normality tests and Q-Q inspection at voltages near the z-crossing
[summary TBD]. Transcribed results re-attach to the condition table by the
(Vop, deck number) key; derived statistics (z, censoring flags) are
recomputed by the parser.

---

## 4. Method

### 4.1 GP surrogate

The μ GP uses Matern-5/2 with ARD; the σ GP uses an additive kernel
separating the operating-voltage group from the device-variation group.
All inputs are standardized with training statistics. This is not
cosmetic: with mV, V, and dimensionless multipliers in one input,
unstandardized training under-converges silently, and most of what our
early experiments attributed to physics constraints was in fact this fix
(§5.5).

### 4.2 Differentiable physics layer

Per condition, (μ, σ) predictions on the five voltages give z(Vop), whose
crossing with Z_t is linearly interpolated into Vmin. Interval selection is
discrete, but the first derivative is well-defined inside each interval;
censored conditions are flagged out. Every path that needs posterior
gradients (monotonicity penalty, gradient inversion) evaluates the
eval-mode posterior so gradients flow to the inputs.

### 4.3 Physics constraints

Corner anchoring augments training with virtual observations at the four
global corners × 5 Vop (a hard constraint under an exact GP). The
monotonicity penalty ReLU(−∂μ/∂Vop)² is evaluated on probe points through
the posterior; a Pelgrom-style linear σ(Vop) trend enters as weak
regularization. Contributions are isolated in §5.5.

### 4.4 Noise-aware GP

Per-condition bootstrap standard errors (sem_μ, sem_σ) feed a fixed-noise
likelihood; bootstrap rather than the analytic σ/√(2N) because the σ-SEM is
kurtosis-sensitive. Low-budget conditions are automatically down-weighted,
and this same mechanism unifies mixed budgets: when low fidelity is merely
fewer samples from the same simulator, a heteroscedastic single GP is the
correct model and the Kennedy–O'Hagan bias term is unnecessary.

### 4.5 Gradient inversion

With x as a leaf tensor under a sigmoid box reparameterization and
feasibility barriers, Adam minimizes (Vmin(x) − V*)². Convergence to the
contour is checked from multiple starts, and each converged point is
compared against a 1-D bisection on its own slice.

---

## 5. Experiments

### 5.1 Protocol

Hold-out splits are condition-level (all five Vop rows of a condition stay
on one side), at 15%. The present batch contains no mirror twins by
construction (§3.5), so condition-level splitting suffices; every
experiment that references legacy pilot data uses mirror-group splits.
Vmin errors are reported on the non-censored set with the censoring rate
alongside.

### 5.2 Forward accuracy

`[Table: hold-out μ R², μ RMSE, σ R², σ RMSE — TBD]`
`[Fig 3 — Predicted vs measured scatter (μ, σ), hold-out. Placeholder.]`

### 5.3 Vmin contours (inverse problem i)

Hausdorff distance between GP and hold-out MC contours at the target level
Vmin = [TBD] V: [TBD] mV. At measured conditions nearest the four corners,
|Vmin_pred − Vmin_MC| = [TBD] mV, evaluated with the boundary-off
configuration to avoid double-use of anchors.

`[Fig 4 — Vmin contours in the (cn, pu) plane: GP vs hold-out MC overlay
with the four corner points, at sk=0 and nominal multipliers.
Placeholder.]`

### 5.4 Gradient inversion (inverse problem ii)

On the analytic testbed, all eight starting points converge to the
minimum-assist design on the Vmin = 0.6 V manifold (max |Vmin − target| =
2.41 mV), and every converged point matches a 1-D bisection on its slice to
four decimal places. Real-data reproduction: [TBD].

`[Fig 5 — Inversion trajectories: multi-start gradient paths over the
(cn, pu) plane with the target contour. Placeholder.]`

### 5.5 Constraint ablation and budget curves

On the analytic testbed (standardization controlled): baseline Vmin RMSE
1.26 mV; corner anchoring 0.92 mV (−27%), with the gain concentrated at
p95 (−37%). The monotonicity penalty is inert on monotone data. Real-data
ablation: [TBD]. Budget-accuracy curves obtained by subsampling training
conditions test whether the anchor gain concentrates at low budgets:
[TBD].

`[Fig 6 — Budget–accuracy Pareto: number of conditions × (Vmin RMSE,
Hausdorff), constraints on/off. Placeholder.]`

### 5.6 Sensitivity

Inverse ARD lengthscales are reported by group (Vth, local-σ, mobility ×
common/skew/PU), alongside variance-based Sobol indices — valid here
because common ⊥ skew by design: [TBD]. Of particular interest are
(i) whether ℓ_cn < ℓ_pu (the PG-dominance hierarchy) holds, and
(ii) whether l_sk/m_sk act at second order. If PG−PD multiplier mismatch
proves second-order for read SNM, that is itself a finding about design
parameter prioritization.

`[Fig 7 — Grouped sensitivity: ARD-based vs Sobol indices, side-by-side
bars. Placeholder.]`

### 5.7 External validation: the nominal slice and dimension scaling

A 4-D batch (cn, sk, pu, Vop; 348 conditions, multipliers nominal),
designed and executed independently of the present batch, provides
measured points on the (l=m=1, skew=0) plane of the 9-D space. Agreement
between the 9-D model projected onto this plane and the 4-D measurements
([TBD]) directly tests generalization on a plane outside the training
draw. We additionally report hold-out accuracy across the 3D/4D/9D batches
to show degradation with dimensionality at fixed budget [TBD]. The 4-D
batch is a pilot-generation design, so its own metrics are recomputed
under mirror-group splits [TBD].

`[Fig 8 — Nominal-slice external validation: projected 9-D predictions vs
4-D measurements. Placeholder.]`

### 5.8 MC QC

`[Fig 9 — MC histograms + Q-Q near the z-crossing voltage, with an example
of censored classification. Placeholder.]`

---

## 6. Limitations and Threats

The Gaussian extrapolation in z = μ/σ is used as an industry-standard
margin metric, not an absolute fail-rate predictor; we defend it with
normality QC at the z-crossing voltages and optional importance-sampling
spot checks, and the lobe-resolved z_eff removes the largest systematic
component. Results concern one node, one cell topology, and primarily the
read metric; the write-margin deck set is [TBD]. The multiplier spill band
[0.625, 0.7) ∪ (1.3, 1.375] sits at the edge of compact-model calibration,
so predictions there should be read conservatively. The PDK is
proprietary; absolute values are not reproducible, so we release the
analytic testbed in full and report normalized-axis results for relative
comparison.

## 7. Related Work

MFNN+IS (Guo et al., ISEDA'24) and Bayesian active learning (Yin et al.,
DAC'22, ASPDAC'23) target forward yield estimation; we differ in the
inverse formulation over physical parameters and the differentiable
pipeline. Tail-accurate importance sampling (Liu et al., DAC'23, OPTIMIS)
is complementary to a margin-metric surrogate. Against analytic Vmin
models (Gupta & Calhoun, TCAS-I'21), the GP offers flexibility in physical
parameter extension and constraint injection. Standard QMC yield analysis
(Singhee & Rutenbar, TCAD'10) and space-filling designs (Kinoshita,
TSM'25) underpin our DOE.

## 8. Conclusion

We proposed a pipeline that serves forward and inverse SRAM Vmin queries
from a single simulation budget, combining a GP surrogate with a
differentiable physics layer, and validated it on production-calibrated
data from an advanced node ([TBD] conditions). The lobe-resolved effective
z, noise-aware budget unification, the censoring-aware metric framework,
and the transcription-free protocol with leakage-free evaluation
discipline are reusable components for carrying surrogate-based yield
methodology onto real industrial data.

---

## Appendix A. Metric definitions

Formal definitions of design-range feasibility agreement, left-censoring
handling, and assist-active scoring; the reproduction table for the ~60×
gap of the naive metric on identical predictions.

## Appendix B. Reproducibility contract

Condition-generator version, seed, quadrant weights, ranges, and the deck
numbering convention. Full analytic-testbed code released [repository TBD].

## Internal references (remove before submission)

| Document | Location |
|---|---|
| Design audit and rerun decision | `docs/decisions/legacy_design_audit_20260714.md` |
| Phase-2 → paper plan | `docs/plans/phase2_to_paper_plan.md` |
| Root-cause fixes | `docs/decisions/session_20260706_root_cause_fixes.md` |
| Adversarial review | `docs/decisions/adversarial_review_20260707.md` |
