# Physics-Constrained Gaussian Process Surrogates for Forward and Inverse SRAM Vmin Estimation Across a Nine-Dimensional Process Window

**Internal Technical Report — IEEE manuscript format, v3.0, July 2026**

---

## Abstract

The minimum operating voltage (Vmin) of an SRAM array must be signed off against
a product specification across the full process-variation window, yet direct
Monte Carlo (MC) verification of the required tail yield is computationally
prohibitive, and corner-based sign-off cannot represent variation axes outside
the corner definition. This work presents a surrogate pipeline that answers both
forward and inverse Vmin queries from a single fixed simulation budget. A
Gaussian process (GP) regresses static-noise-margin statistics from nine
process-variation parameters, and a differentiable physics layer converts those
statistics into a yield-referenced Vmin as an analytic constraint rather than a
learned approximation. Because the composition is differentiable in its inputs,
points on a target-Vmin boundary are obtained directly by gradient descent
without grid search. A heteroscedastic likelihood driven by per-condition MC
standard errors admits heterogeneous sampling budgets into a single model. The
method is validated on production-calibrated data from an advanced FinFET node
comprising 2000 conditions at four supply voltages. Hold-out accuracy reaches
R² = 0.982 for the mean and 0.985 for the standard deviation, with a Vmin RMSE
of 9.14 mV inside the specification-relevant region, and the specification
verdict is reproduced with 99.3% agreement at the end-of-life criterion.
Variance-based sensitivity analysis, made affordable by the surrogate, identifies
NMOS local-sigma as the third-ranked contributor to Vmin variance, ahead of
pass-gate/pull-down threshold skew and outside the axes any corner definition
spans. The analysis further shows that the highest supply level of the
conventional grid is structurally irrelevant to the specification verdict,
permitting a 20% reduction in simulation volume without loss. Finally, a
systematic optimism inherent in the conventional minimum-statistics z-score is
quantified at 53 to 144 mV of Vmin, comparable to the entire time-zero to
end-of-life margin budget, and a low-cost diagnostic protocol to resolve it is
specified.

**Index Terms** — SRAM, minimum operating voltage, process variation, Gaussian
process, surrogate model, inverse problem, yield analysis, sensitivity analysis,
static noise margin.

---

## I. INTRODUCTION

### A. Specification Context

SRAM occupies the largest die area in modern systems-on-chip and dominates chip
yield. The process considered here has a nominal supply of 0.75 V. After
accounting for on-chip and off-chip IR drop, the voltage available at the cell
establishes the Vmin specification given in Table I.

**TABLE I. Vmin SPECIFICATION**

| Criterion | Vmin specification | Basis |
|---|---|---|
| Time-zero (T0) | 0.625 V | Initial characteristics |
| End-of-life (EOL) | 0.675 V | Degradation included; binding criterion |

The 50 mV separating the two criteria constitutes the entire margin budget
available to the design. This quantity recurs throughout the paper as a
reference scale against which model error, statistical noise, and systematic
bias are compared. The operative question is therefore not the numerical value
of Vmin in isolation, but whether a given process condition satisfies 0.675 V
and, if not, by what margin it fails.

### B. Cost of Direct Verification

The industry-standard approach estimates Vmin by MC simulation: for each
process-variation condition, thousands of randomized transistor instantiations
are simulated to construct a static-noise-margin (SNM) distribution, repeated at
each supply level. For a batch of the size considered here — 2000 conditions,
five supply levels, 5000 MC samples per condition — this amounts to 5 × 10⁷
circuit simulations. At minutes to tens of minutes per PrimeSim invocation, the
resulting wall-clock time extends to weeks or months even under parallel
execution, before accounting for process design kit licensing, per-license
concurrency limits, and server infrastructure. The burden increases at advanced
nodes as compact models grow more complex.

### C. Limitations of Corner-Based Sign-off

Restricting verification to representative corners (FSG, SFG, FFG, SSG) bounds
the cost but introduces two deficiencies.

First, corners are extreme combinations of two axes only, namely the NMOS and
PMOS threshold shifts. The threshold skew, local-sigma, and mobility axes
treated in this work do not enter the corner definition. Section VII establishes
by variance-based sensitivity analysis that NMOS local-sigma is the third-largest
contributor to Vmin variance, exceeding pass-gate/pull-down threshold skew; a
corner-based procedure cannot observe this axis at all.

Second, corner simulation answers only the forward question. The questions posed
in practice by process and design engineering are inverse: which variation
combinations violate the specification, which parameter must be tightened and by
how much to restore compliance, and what skew tolerance may be admitted. A finite
set of corner points determines neither the location nor the geometry of the
compliance boundary.

### D. Contributions

This work makes the following contributions.

1. A surrogate pipeline that answers forward and inverse Vmin queries from a
   single fixed simulation budget, with the inverse solution obtained by
   gradient descent through a differentiable physics layer rather than by grid
   search (Section IV).
2. Validation on production-calibrated data from an advanced FinFET node,
   including reproduction of the specification verdict at 99.3% agreement and
   confirmation of the pass-gate dominance hierarchy across three independent
   batches (Section V).
3. Evidence supporting reduction of the simulation budget along three axes —
   supply levels, condition count, and MC samples per condition — with the
   supply-level reduction shown to be structurally lossless with respect to the
   specification verdict (Section VI).
4. A quantitative sensitivity ranking obtained at negligible marginal cost,
   which identifies NMOS local-sigma as a first-order contributor invisible to
   corner-based methods, and which demonstrates that automatic relevance
   determination lengthscales are inadequate as a sensitivity measure on this
   problem (Section VII).
5. Quantification of a systematic optimism inherent in the conventional
   minimum-statistics z-score, of magnitude comparable to the entire margin
   budget, together with a low-cost diagnostic protocol to resolve it
   (Section II-D).

**Fig. 1.** Pipeline overview: variation parameters to GP posterior (μ, σ), to
differentiable physics layer, to Vmin, with forward and inverse paths indicated.

---

## II. PROBLEM FORMULATION

### A. Read Stability Metric

Read stability of a six-transistor cell is quantified by the static noise
margin, defined as the minimum of the two lobes of the butterfly characteristic
[15]. MC simulation yields an SNM distribution over randomized samples, from
which the mean μ and standard deviation σ are conventionally recorded. The write
metric is treated in Section VIII-C; the methodology is metric-agnostic.

### B. Vmin Definition and Yield Target

For a condition **x**, the margin ratio

    z(V_op) = μ(x, V_op) / σ(x, V_op)                                    (1)

is evaluated on the supply grid, and Vmin(**x**) is obtained by linear
interpolation of the supply voltage at which z crosses a target z-score Z_t.

Z_t is derived analytically from the array yield requirement. For a 256 Mb array
at 99% Poisson yield,

    p_fail = −ln(0.99) / (256 × 10⁶) ≈ 3.9 × 10⁻¹⁰                       (2)
    Z_t = Φ⁻¹(1 − p_fail) ≈ 6.50                                          (3)

where Φ denotes the standard normal cumulative distribution function. The unit
of failure is the cell; multiplication by the transistor count is incorrect.

Two distinct reference quantities must be kept separate. Z_t enters the
*definition* of Vmin as a yield criterion, whereas the specification voltages of
Table I determine whether the resulting Vmin *passes*. The two are established
independently. That Z_t is an analytically derived rather than
silicon-calibrated quantity is material to the discussion of Section II-D.

### C. Region of Interest and Two-Sided Censoring

Accuracy in Vmin is required only where it alters a decision. Three regimes
follow from Table I.

Conditions with Vmin below the lowest sampled supply pass with substantial
margin; their exact value is immaterial and they are treated as left-censored.
Conditions with Vmin above 0.7 V already violate the EOL criterion by a wide
margin; they require classification as failing but no numerical resolution, and
are treated as right-censored. The interval between these bounds contains both
specification voltages and is the sole region in which numerical accuracy is
required.

The supply grid is accordingly set to {0.4, 0.5, 0.6, 0.7} V. This choice is
determined by the specification rather than by data availability: it is the
minimal interval bracketing both specification points. The 0.7 V ceiling is
simultaneously the largest admissible reduction and the smallest value the
specification permits, since bracketing the EOL criterion at 0.675 V by
interpolation requires a sample above it. Quantitative justification appears in
Section VI-A. Censored conditions are excluded from continuous error metrics and
enter only through their classification.

### D. Systematic Bias of the Minimum-Statistics z-Score

The SNM is the minimum of two lobe margins, and the minimum of two Gaussian
variates is not Gaussian; its lower tail is heavier than that of a
moment-matched normal distribution. Equation (1) nevertheless fits a Gaussian to
the minimum and extrapolates to Z_t = 6.50, and therefore underestimates the
failure probability systematically. Since failure requires only one lobe to
collapse, the true failure probability is the union probability, which is
bounded below by that of either lobe individually.

Given per-lobe statistics (μ_L, σ_L, μ_R, σ_R, ρ_LR), the exact failure
probability admits a closed form,

    p_fail = P(L<0) + P(R<0) − P(L<0, R<0)                               (4)
    Z_eff = Φ⁻¹(1 − p_fail)                                              (5)

in which the joint term is the bivariate normal cumulative distribution function,
computable via Owen's T function [9] and differentiable in all arguments, so
that (4)–(5) may be substituted into the pipeline without loss of gradient flow.

The magnitude of the bias depends on the lobe correlation ρ_LR, ranging from
+0.7σ for independent lobes to +1.9σ under anticorrelation. Table II converts
these to Vmin using the measured slope dz/dV_op ≈ 13.2 V⁻¹ in the
specification band.

**TABLE II. IMPACT OF THE MINIMUM-STATISTICS BIAS**

| Assumption | z bias | Vmin optimism | EOL pass rate |
|---|---|---|---|
| No bias | 0 | — | 88.5% |
| Independent lobes | +0.7σ | 53 mV | 80.5% |
| Anticorrelated lobes | +1.9σ | 144 mV | 63.0% |

Under the most favorable assumption the induced error of 53 mV exceeds the
entire 50 mV margin budget of Table I. Compared against the surrogate Vmin
accuracy of 9.14 mV established in Section V-B, the dominant error may therefore
reside in the metric rather than in the model.

The design of Section III affords no mitigation. All nine parameters are
device-type-level global quantities and do not break the left-right symmetry of
the cell, since the left and right pass gates are shifted identically. The two
lobes are consequently exchangeable in every condition, which is precisely the
configuration maximizing the minimum-statistics bias; no subset of conditions is
naturally asymmetric and therefore exempt.

The MC output available for the present batch contains only μ and σ of the
minimum, so (4)–(5) could not be applied. All results reported here use (1),
consistent with prevailing practice. A tail-shape diagnostic on conditions near
the specification boundary has been specified to resolve the magnitude
empirically, measuring the distribution shape at 10⁵ MC samples and
discriminating between a Gaussian and a minimum-of-two-Gaussians model. Because
the bias affects only the threshold of the (μ, σ) to Vmin transform, its
correction is applied to existing data by post-processing under
Z_t → Z_t + z_bias, requiring no additional simulation. The relative conclusions
of Sections V through VII — sensitivity ranking, boundary geometry, skew
tolerance, and corner ordering — are therefore unaffected; absolute Vmin values
and specification pass rates are subject to uniform correction.

---

## III. EXPERIMENTAL DESIGN

### A. Input Space

Nine device-variation dimensions are sampled, listed in Table III, together with
the supply voltage.

**TABLE III. VARIATION PARAMETERS**

| Symbol | Description | Range | Unit |
|---|---|---|---|
| cn | NMOS common threshold shift | ±60 | mV |
| sk | Pass-gate/pull-down threshold skew | ±20 | mV |
| pu | PMOS threshold shift | ±60 | mV |
| lpu | Pull-up local-sigma multiplier | [0.7, 1.3] | — |
| l_com | NMOS local-sigma, common | [0.7, 1.3] | — |
| l_sk | NMOS local-sigma, skew | ±0.075 | — |
| mpu | Pull-up mobility multiplier | [0.7, 1.3] | — |
| m_com | NMOS mobility, common | [0.7, 1.3] | — |
| m_sk | NMOS mobility, skew | ±0.075 | — |

Deck parameters follow as threshold PG = cn + sk and PD = cn − sk, with the
local-sigma and mobility multipliers decomposed identically.

### B. Common-Skew Parameterization

The pass-gate and pull-down devices share an NMOS flavor and therefore share
their dominant variation sources, including gate stack, channel doping, anneal,
and lithographic critical dimension, with imperfect tracking arising from device
geometry and layout environment. Independent per-device sampling would allocate
design points to states not realized in silicon, in which devices of a common
flavor diverge in opposite directions at the mismatch level.

The adopted decomposition induces corr(l_PG, l_PD) ≈ 0.88, within the plausible
same-flavor tracking band of 0.85 to 0.95 and consistent with the threshold
structure at ρ ≈ 0.80. Common and skew components are sampled independently, a
property required by the variance-based analysis of Section VII.

**Fig. 2.** Design visualization: (a) quadrant weighting in the (cn, pu) plane;
(b) the independent (l_com, l_sk) sampling box and the induced diagonal
(l_PG, l_PD) band.

### C. Quadrant-Weighted Design of Experiments

Read and write margins degrade in different worst-case quadrants, the former at
FSG and the latter at SFG. Separate deck sets are therefore constructed per
metric with the quadrant weights of Table IV, raising resolution in the
worst-case region by a factor of two to four at fixed condition count.
Conditions are generated by deterministic PCG64 draws with an independent stream
per quadrant.

**TABLE IV. QUADRANT WEIGHTS BY METRIC**

| Metric | FSG | FN | SN | SFG |
|---|---|---|---|---|
| Read (SNM) | 45% | 20% | 15% | 20% |
| Write (Vtrip) | 10% | 15% | 30% | 45% |

Both deck sets were designed and generated. At the time of writing, result
transcription is complete for the read set only; write-set results are in
progress and are cited in Sections VII-D and VIII-C from an independent
four-dimensional batch for reference.

An earlier design hypothesis held that stratified low-discrepancy sampling would
outperform pseudorandom draws. Internal validation supported this on neither the
domain-uniform nor the corner-restricted metric, and the claim is withdrawn; the
benefit of the present design derives from quadrant weighting alone.

### D. Transcription-Free Protocol

Simulations execute within a facility from which neither netlists nor raw results
may be exported. Because condition generation is deterministic, transmission of
the tuple (stage, condition count, seed, metric, method) renders the
facility-side deck loop and the model-side condition table bit-identical.
Results return labeled solely by supply level and deck index, and no condition
coordinate is transcribed manually. In a pilot in which conditions were manually
transcribed, the row error rate was approximately 9%; the protocol constitutes a
data-integrity requirement rather than a convenience.

Transcription of result values nonetheless remains. Automated range-based
quality control detected 22 digit-placement errors in the present batch, of
which three were unparseable and nineteen were physically implausible in
magnitude. Such values degrade the surrogate catastrophically, reducing the
hold-out R² to −0.41 prior to correction, and permanent retention of
physically-motivated range checks in the parser is recommended.

### E. Mirror-Twin Leakage

An early pilot design reused a single quasi-random stream across all four
quadrants, inverting only the signs of cn and pu. As a consequence 75% of
conditions possessed a mirror twin sharing the remaining seven coordinates, and
under a random hold-out approximately 74% of test conditions had a twin present
in training, inflating accuracy metrics without any implementation defect.

The cause was identified by forensic comparison of transcribed conditions against
the reconstructed generator, and was addressed by assigning an independent stream
per quadrant and by enforcing mirror-group splits for any evaluation involving
legacy data. Because design-induced leakage of this kind inflates metrics
silently, surrogate-validation studies should report the design generation
procedure together with the split rule.

---

## IV. SURROGATE MODEL

### A. Gaussian Process Regression

A Gaussian process [10] provides a nonparametric Bayesian regression that
returns, in addition to a predictive mean, a calibrated predictive variance. The
model maps the nine variation parameters and the supply voltage to the SNM
statistics (μ, σ). Three properties motivate this choice: operation under
limited data, quantified predictive uncertainty, and differentiability of the
posterior mean with respect to the inputs, the last being a prerequisite for the
inversion of Section IV-F. Appendix A provides additional background for readers
unfamiliar with the formalism.

The mean process employs a Matérn-5/2 kernel with automatic relevance
determination (ARD), assigning an independently learned lengthscale to each
input dimension. The standard-deviation process employs an additive kernel
separating the supply-voltage group from the device-variation group.

### B. Input Standardization

The input vector mixes millivolt-scale shifts, volt-scale supply levels, and
dimensionless multipliers. Without standardization the marginal likelihood
optimization converges to a substantially inferior optimum without diagnostic
indication. A majority of the improvement initially attributed to physics
constraints was subsequently traced to this factor, as reported in Section VI-B.
All inputs are standardized using training statistics.

### C. Differentiable Physics Layer

The transformation from (μ, σ) to Vmin is imposed as an analytic constraint
containing no trainable parameters. For each condition, the posterior mean is
evaluated at the four supply levels, the margin ratio is formed by (1), and the
crossing with Z_t is interpolated linearly. Selection of the bracketing interval
is discrete, but the first derivative is well defined within each interval, so
the composition of GP and physics layer is differentiable in the inputs.
Censored conditions are flagged and excluded.

### D. Physics Constraints

Three constraints inject prior device knowledge. Corner anchoring augments the
training set with virtual observations at the four global corners, which under
an exact GP acts as a hard constraint and prevents extrapolation drift at the
domain extremes. A monotonicity penalty of the form ReLU(−∂μ/∂V_op)², evaluated
at probe points through the posterior, suppresses the non-physical prediction
that increasing supply degrades mean stability. A weak regularizer encourages a
linear σ(V_op) trend consistent with established mismatch scaling [8].
Contributions are isolated in Section VI-B.

### E. Noise-Aware Likelihood

Per-condition bootstrap standard errors enter a fixed-noise Gaussian likelihood,
so that conditions supported by larger MC batches receive proportionally greater
weight. Bootstrap rather than analytic standard errors are used because the
standard error of σ is sensitive to kurtosis.

This mechanism admits heterogeneous sampling budgets into a single model. When
reduced fidelity consists solely of fewer samples drawn from the same simulator,
a heteroscedastic single-fidelity GP is the correct model and the discrepancy
term of a multi-fidelity formulation [11] is unnecessary. Because the posterior
borrows strength across neighboring conditions in the input space, no individual
condition requires a large MC batch to be informative, which supports allocating
a fixed budget toward breadth in condition coverage rather than depth per
condition, as quantified in Section VI-C.

### F. Gradient-Based Inversion

For a target specification voltage V*, the set {**x** : Vmin(**x**) = V*} is a
hypersurface in the nine-dimensional variation space, constituting the boundary
of the allowable process window. It is located directly by minimizing
(Vmin(**x**) − V*)² with respect to **x** using Adam [14], with **x** treated as
a leaf tensor under a sigmoid box reparameterization that confines iterates to
physically admissible ranges. Convergence is verified from multiple
initializations, and each converged point is cross-checked against a
one-dimensional bisection on its own slice.

The cost of this procedure does not grow combinatorially with dimension. A
50 × 50 grid over the two threshold axes alone would require 2500 MC evaluations,
and exhaustive search in nine dimensions is infeasible.

---

## V. VALIDATION

### A. Protocol

Splitting is performed at condition level, with all supply rows of a condition
assigned to the same partition, at a hold-out fraction of 15%. The present batch
contains no mirror twins by construction, so condition-level splitting is
sufficient; evaluations referencing legacy pilot data enforce mirror-group
splits. Vmin errors are reported on the non-censored subset with the censoring
rate stated alongside.

### B. Forward Accuracy

Table V reports hold-out accuracy for 2000 conditions at four supply levels
under the noise-aware likelihood.

**TABLE V. HOLD-OUT ACCURACY**

| Quantity | Value |
|---|---|
| μ coefficient of determination | 0.9817 (RMSE 5.35 mV) |
| σ coefficient of determination | 0.9845 (RMSE 0.22 mV) |
| Vmin RMSE, all non-censored | 13.50 mV |
| Vmin RMSE, specification region (Vmin ≤ 0.7 V) | 9.14 mV |

Within the specification region, where the verdict is determined, the error of
9.14 mV is approximately one fifth of the 50 mV margin budget, so surrogate
error does not govern the sign-off decision. The systematic bias of
Section II-D is a separate and larger quantity.

**Fig. 3.** Predicted versus measured statistics (μ, σ) on the hold-out
partition.

### C. Physical Consistency

Table VI summarizes agreement with expected device behavior.

**TABLE VI. PHYSICAL CONSISTENCY CHECKS**

| Property | Expectation | Measurement | Result |
|---|---|---|---|
| Pass-gate dominance | ℓ_cn < ℓ_pu | ℓ_pu/ℓ_cn = 1.083 | Satisfied |
| Threshold direction | ∂Vmin/∂cn < 0 | Negative | Satisfied |
| Pull-up direction | ∂Vmin/∂pu > 0 | Positive | Satisfied |
| Worst read corner | FSG | FSG | Satisfied |
| Supply sensitivity | shortest lengthscale | 5.17, shortest | Satisfied |

The pass-gate dominance hierarchy reproduces across three independently designed
batches, at ratios of 1.08, 1.14, and 1.083 respectively, indicating that the
model has captured device physics rather than memorized the training
distribution.

### D. Specification Verdict Reproduction

The operative sign-off query is binary. Table VII reports agreement between
surrogate and measurement on 300 hold-out conditions.

**TABLE VII. SPECIFICATION VERDICT AGREEMENT**

| Criterion | Agreement | False positive | False negative | z-margin RMSE |
|---|---|---|---|---|
| T0 (0.625 V) | 295/300 (98.3%) | 4 | 1 | 0.573 |
| EOL (0.675 V) | 298/300 (99.3%) | 1 | 1 | 0.322 |

A false positive denotes a condition predicted to pass that in fact fails. At
the binding EOL criterion a single such case occurs, supporting use of the
surrogate for sign-off screening. Over the full population of 2000 conditions,
81.2% pass T0 and 88.5% pass EOL, with 11.4% failing EOL. These proportions are
subject to the uniform correction discussed in Section II-D.

**Fig. 4.** Vmin contours in the (cn, pu) plane: surrogate prediction overlaid
on hold-out measurement, with the four global corners indicated.

### E. Gradient-Based Inversion

On an analytic testbed for which ground truth is available, all eight
initializations converged to the target manifold with a maximum absolute
deviation of 2.41 mV, and every converged point agreed with a one-dimensional
bisection on its slice to four decimal places.

**Fig. 5.** Multi-start inversion trajectories over the (cn, pu) plane with the
target contour indicated.

### F. External Validation

An independently designed four-dimensional batch of 348 conditions at nominal
multipliers provides measured points on the (l = m = 1, skew = 0) plane of the
nine-dimensional space. Agreement between the projected nine-dimensional model
and these measurements tests generalization on a plane outside the training
draw. As the four-dimensional batch is of pilot generation, its own metrics are
recomputed under mirror-group splits.

---

## VI. SIMULATION COST REDUCTION

The simulation budget factors as the product of supply levels, condition count,
and MC samples per condition. Evidence is presented for each factor.

### A. Supply Levels

Both specification voltages lie within the interval [0.6, 0.7] V, so z at either
specification point is interpolated from the 0.6 V and 0.7 V samples alone. The
0.8 V level cannot participate structurally in the verdict. Table VIII confirms
this on the full population.

**TABLE VIII. VERDICT INVARIANCE TO REMOVAL OF THE 0.8 V LEVEL**

| Criterion | Verdict agreement | max abs Δz |
|---|---|---|
| T0 (0.625 V) | 2000/2000 (100%) | 0.00 × 10⁰ |
| EOL (0.675 V) | 2000/2000 (100%) | 0.00 × 10⁰ |

The deviation is identically zero, reflecting structural necessity rather than
empirical approximation. A surrogate trained on the reduced grid reproduces the
specification verdict as reported in Section V-D and attains the same
specification-region Vmin RMSE of 9.14 mV; inclusion of the 0.8 V level moves
the mean coefficient of determination only from 0.9817 to 0.9834. The 90
conditions newly resolved by that level all possess Vmin above 0.7 V and are
therefore already outside the EOL criterion.

Reduction from five supply levels to four accordingly yields a 20% saving in
simulation volume for this metric without loss. The 0.7 V ceiling is a lower
bound on the reduction, not a target for further compression.

### B. Condition Count

Subsampling the training set to size N and refitting traces the budget-accuracy
relationship of Table IX, obtained on the analytic testbed with ten independent
redraws per size.

**TABLE IX. BUDGET-ACCURACY RELATIONSHIP**

| N | Vmin RMSE (mV) | Contour Hausdorff distance (mV) |
|---|---|---|
| 50 | 5.13 ± 1.84 | 1.62 ± 0.64 |
| 100 | 3.90 ± 0.50 | 1.30 ± 0.29 |
| 200 | 3.21 ± 0.77 | 1.00 ± 0.42 |
| 400 | 2.01 ± 0.26 | 0.76 ± 0.14 |
| 800 | 1.40 ± 0.15 | 0.54 ± 0.15 |

Accuracy improves steeply at small N and passes a knee near N = 400, beyond
which returns diminish. This transition converts the choice of condition count
from an unquantified judgement into a defensible decision.

The physics constraints of Section IV-D concentrate their benefit in the same
low-budget regime. Corner anchoring improves corner-neighborhood Vmin RMSE
significantly at N ≤ 100, with a pooled paired difference of −1.29 mV at
p < 10⁻⁶ under a Wilcoxon signed-rank test, the effect vanishing as N increases.
On the domain-uniform metric the effect is small and unstable, and the claim
must therefore be stated together with the metric on which it is measured. On
the analytic testbed the baseline Vmin RMSE of 1.26 mV improves to 0.92 mV with
corner anchoring, a reduction of 27%, with the 95th percentile improving by 37%.

This observation carries a methodological implication: the hold-out design
itself determines the conclusion. A domain-uniform hold-out measures average
accuracy, whereas a corner-restricted hold-out measures accuracy where safety
margin is critical. These are distinct questions and both should be reported.

**Fig. 6.** Budget-accuracy relationship: condition count against Vmin RMSE and
contour Hausdorff distance, with and without physics constraints.

### C. MC Samples per Condition

The noise-aware likelihood of Section IV-E accepts per-condition standard errors
explicitly and down-weights sparsely sampled conditions automatically. Because
the posterior borrows strength across neighboring conditions, individual
conditions need not attain high confidence in isolation, which justifies
allocating budget toward breadth. The same mechanism permits heterogeneous
budgets to coexist within a single model without a discrepancy term.

---

## VII. SENSITIVITY ANALYSIS

The practically actionable output for process ownership is a ranking of which
variation sources govern Vmin. Two measures are computed and compared.

### A. ARD Lengthscales

The GP learns a lengthscale per input dimension during fitting, so this measure
carries no marginal cost. It is, however, a property of the fitted model rather
than of the data: it is distorted under input correlation, which motivates the
independent sampling of Section III-B, and it does not separate standalone from
interaction effects. Table X reports the fitted values.

**TABLE X. ARD LENGTHSCALES (STANDARDIZED SCALE; SHORTER IS MORE SENSITIVE)**

| Rank | Axis | ℓ | Rank | Axis | ℓ |
|---|---|---|---|---|---|
| 1 | V_op | 5.185 | 6 | l_com | 8.173 |
| 2 | cn | 7.405 | 7 | m_sk | 8.177 |
| 3 | pu | 7.945 | 8 | mpu | 8.186 |
| 4 | sk | 8.056 | 9 | l_sk | 8.196 |
| 5 | m_com | 8.114 | 10 | lpu | 8.213 |

### B. Variance-Based Sobol Indices

Variance-based sensitivity analysis apportions output variance among inputs and
their interactions. Exact evaluation typically requires tens of thousands of
function evaluations, which precludes its application to circuit-level yield
studies conducted by direct simulation. The surrogate removes this obstacle:
evaluation requires milliseconds rather than minutes, so the required queries
impose negligible marginal cost beyond the budget that trained the model. First-
order indices are estimated by the Saltelli estimator [12] and total-order
indices by the Jansen estimator [13], using 1024 base samples corresponding to
11 264 surrogate evaluations. Results appear in Table XI.

**TABLE XI. SOBOL SENSITIVITY INDICES OF Vmin**

| Axis | S₁ (first order) | S_T (total order) |
|---|---|---|
| cn | 0.388 | 0.464 |
| pu | 0.212 | 0.298 |
| l_com | 0.157 | 0.199 |
| sk | 0.121 | 0.108 |
| lpu | 0.032 | 0.039 |
| m_sk | 0.007 | 0.024 |
| m_com | 0.021 | 0.021 |
| mpu | 0.008 | 0.014 |
| l_sk | 0.004 | 0.001 |

The output variance corresponds to a standard deviation of 94.5 mV, and
ΣS₁ = 0.948 indicates near-additive behavior with weak interaction.

### C. Discrepancy Between the Two Measures

The two measures agree on the leading pair, cn followed by pu, but diverge at
third rank: the lengthscale ordering places sk ahead of l_com, whereas the Sobol
ordering places l_com at approximately twice the total-order index of sk.

A more fundamental limitation is apparent. The total-order indices span 0.001 to
0.464, a range exceeding two orders of magnitude, whereas the fitted lengthscales
span 7.41 to 8.21, a range of 1.1. Even under the approximate scaling of
sensitivity as ℓ⁻², this corresponds to a factor of 1.23 and cannot represent
the observed variation in contribution. The most plausible explanation is weak
identifiability of individual lengthscales at this sample density in nine
dimensions.

The practical consequence is that on this problem the sensitivity ranking must be
read from the variance-based indices rather than from the lengthscales. The
lengthscales remain serviceable as a qualitative check on large hierarchies such
as pass-gate dominance, but are unsuited to quantitative prioritization. This
also reinforces the value of the surrogate: the cost-free measure did not answer
the question, and the measure that did would have been unaffordable by direct
simulation.

### D. Process Implications and Skew Tolerance

Threshold variation dominates, with cn and pu jointly accounting for the majority
of total-order variance. NMOS local-sigma ranks third and exceeds
pass-gate/pull-down threshold skew, an axis that corner-based sign-off cannot
represent, indicating that local mismatch control warrants higher priority than
skew control. All mobility axes are minor, with total-order indices below 0.025.
The local-sigma skew term is negligible at 0.001, providing evidence that its
control specification may be relaxed, whereas the mobility skew term, although
small in absolute magnitude, operates predominantly through interaction with a
total-to-first-order ratio of approximately 3.3.

Table XII reports the skew response at nominal multipliers.

**TABLE XII. PG-PD SKEW RESPONSE**

| Operating point | Vmin at sk = 0 | Swing over ±20 mV | dVmin/dsk |
|---|---|---|---|
| TT (0, 0) | 470.3 mV | 114.2 mV | −2.80 mV/mV |
| mild FSG (−30, +30) | 586.3 mV | 120.8 mV | −2.76 mV/mV |
| mild SFG (+30, −30) | 350.0 mV | 104.8 mV | −7.13 mV/mV |
| FFG (−30, −30) | 475.2 mV | 119.1 mV | −2.84 mV/mV |
| SSG (+30, +30) | 470.5 mV | 112.1 mV | −2.81 mV/mV |

Positive skew, corresponding to a slower pass gate, stabilizes the read
operation, with a slope near −2.8 mV/mV at most operating points and steepening
to −7.13 mV/mV near SFG. Against the specification, every representative
operating point tolerates the full ±20 mV range at the EOL criterion; only under
the tighter T0 criterion does the mild-FSG point become constrained, requiring
sk ≥ −11 mV. The present ±20 mV control specification is therefore adequate at
nominal multipliers. Since local-sigma is identified above as a first-order
contributor, a joint sweep over skew and local-sigma is required before a skew
specification is finalized.

**Fig. 7.** Grouped sensitivity: ARD-derived measure against Sobol indices, with
the allowable skew window.

---

## VIII. DISCUSSION AND LIMITATIONS

### A. Principal Limitation

The systematic optimism of Section II-D constitutes the largest open uncertainty
in this work. Its estimated magnitude of 53 to 144 mV of Vmin is comparable to
the entire margin budget and exceeds the surrogate error by a factor of six to
sixteen. Absolute Vmin values and specification pass rates reported here are
therefore pre-correction quantities. The diagnostic specified in Section II-D
resolves this at under 2% of the total simulation budget, and the correction
requires no re-simulation.

A related assumption is that each lobe margin is itself Gaussian into the far
tail. The relation (1) is an industry-standard margin metric rather than an
absolute failure-rate predictor, and the proposed diagnostic examines both
assumptions simultaneously.

### B. Scope

Results concern a single technology node, a single cell topology, and
principally the read metric. The multiplier spill band arising when a common
component approaches a range boundary lies at the edge of compact-model
calibration, and predictions there should be interpreted conservatively. The
supply-level reduction of Section VI-A is contingent upon the specification of
Table I and requires revisiting should the IR-drop budget change such that the
specification exceeds 0.7 V. The process design kit is proprietary, so absolute
values are not externally reproducible; the analytic testbed is released in full
and normalized-axis results are reported to permit relative comparison.

### C. Write Margin and Integrated Verdict

Read alone favors positive skew, whereas the write metric responds in the
opposite direction. On the independent four-dimensional batch, the combined
worst case under a smooth-maximum composition was minimized near sk ≈ −2 mV,
essentially symmetric, and the resulting surface is saddle-shaped with maxima at
both FSG and SFG. This value has not been reproduced on the present batch, as
write-set transcription remains in progress, and should be recomputed in nine
dimensions once available. The directional conclusion, that a skew specification
must not be derived from the read metric alone, is nonetheless firm.

### D. Recommendations

Supply levels should be determined by the specification, simulating only the
minimal bracketing interval. Condition count should be selected at the
budget-accuracy knee, beyond which marginal effort is better directed toward
depth near the boundary or toward an additional design corner. MC counts need
not be uniform across conditions provided standard errors are recorded.
Tail-shape diagnostics on a small number of near-specification conditions should
be made routine, and per-lobe statistics or, at minimum, skewness and low
quantiles should be recorded where the flow permits, since the mean and standard
deviation of a minimum contain no information regarding tail shape.

---

## IX. CONCLUSION

A surrogate pipeline was constructed that answers forward and inverse SRAM Vmin
queries from a single fixed simulation budget, and was validated on
production-calibrated data from an advanced node comprising 2000 conditions at
four supply levels.

The surrogate is suitable for sign-off screening, attaining a
specification-region Vmin RMSE of 9.14 mV, one fifth of the margin budget, with
99.3% agreement on the end-of-life specification verdict and physical
consistency reproduced across three independent batches. The simulation budget
admits reduction on specification-derived grounds, with a 20% decrease in
supply-level count shown to be structurally lossless. Inverse queries, including
the allowable process-window boundary, skew tolerance, and parameter
prioritization, are answered without additional simulation; this established
that NMOS local-sigma is the third-largest contributor to Vmin variance, ahead
of threshold skew, on an axis that corner-based sign-off structurally cannot
observe.

Finally, the dominant uncertainty was found to reside in the metric rather than
in the model. The systematic optimism of the minimum-statistics z-score is
estimated at 53 to 144 mV, comparable to the entire margin budget, and would
govern the total error irrespective of surrogate precision. Quantifying and
resolving this effect is of comparable importance to the methodological
contributions, and is achievable at under 2% of the total simulation budget.

---

## APPENDIX A: GAUSSIAN PROCESS BACKGROUND

This appendix summarizes the formalism for readers whose primary expertise lies
outside statistical learning.

A Gaussian process defines a distribution over functions such that any finite
collection of function values follows a joint Gaussian distribution. It is
specified by a mean function and a covariance kernel, the latter encoding the
assumption that inputs which are close produce outputs which are correlated.
Conditioning on observed data yields a posterior that returns, at any query
point, both a predictive mean and a predictive variance; the variance grows in
regions distant from observations, which distinguishes the method from
conventional regression.

The kernel lengthscale governs the distance over which the correlation decays.
A short lengthscale along an axis indicates that the output varies rapidly with
that input, and a long lengthscale indicates insensitivity. Automatic relevance
determination assigns an independent lengthscale to each input dimension and
learns all of them from data, which is why the fitted values are frequently
interpreted as a sensitivity measure — an interpretation examined critically in
Section VII-C.

The posterior mean is a linear combination of kernel evaluations against the
training inputs, and is therefore differentiable with respect to the query point
whenever the kernel is. This property is what permits the inverse problem of
Section IV-F to be solved by gradient descent rather than by search.

A heteroscedastic likelihood generalizes the standard formulation by permitting
the observation noise to differ per data point. Supplying per-condition Monte
Carlo standard errors in this role causes the posterior to weight conditions in
proportion to their statistical reliability, without an auxiliary correction
term.

## APPENDIX B: METRIC DEFINITIONS

Formal definitions of design-range feasibility agreement, two-sided censoring,
and assist-active scoring are provided, together with the reproduction table
demonstrating that a naive metric overstates the error of identical predictions
by approximately a factor of sixty.

## APPENDIX C: REPRODUCIBILITY

Condition-generator version, seed, quadrant weights, parameter ranges, and deck
numbering convention are specified. The analytic testbed is released in full.

---

## REFERENCES

Full bibliographic details to be completed prior to submission.

[1] E. Seevinck, F. J. List, and J. Lohstroh, "Static-noise margin analysis of
    MOS SRAM cells," *IEEE J. Solid-State Circuits*, 1987.

[2] M. J. M. Pelgrom, A. C. J. Duinmaijer, and A. P. G. Welbers, "Matching
    properties of MOS transistors," *IEEE J. Solid-State Circuits*, 1989.

[3] D. B. Owen, "Tables for computing bivariate normal probabilities," *Ann.
    Math. Statist.*, 1956.

[4] C. E. Rasmussen and C. K. I. Williams, *Gaussian Processes for Machine
    Learning*. MIT Press, 2006.

[5] M. C. Kennedy and A. O'Hagan, "Predicting the output from a complex computer
    code when fast approximations are available," *Biometrika*, 2000.

[6] A. Saltelli et al., "Variance based sensitivity analysis of model output,"
    *Comput. Phys. Commun.*, 2010.

[7] M. J. W. Jansen, "Analysis of variance designs for model output," *Comput.
    Phys. Commun.*, 1999.

[8] D. P. Kingma and J. Ba, "Adam: A method for stochastic optimization," in
    *Proc. ICLR*, 2015.

[9] A. Singhee and R. A. Rutenbar, "Why quasi-Monte Carlo is better than Monte
    Carlo or Latin hypercube sampling for statistical circuit analysis," *IEEE
    Trans. Comput.-Aided Design*, 2010.

[10] Guo et al., "Multi-fidelity neural network with importance sampling for
     SRAM yield estimation," in *Proc. ISEDA*, 2024.

[11] Yin et al., "Bayesian active learning for yield estimation," in *Proc.
     DAC*, 2022.

[12] Yin et al., "Efficient yield estimation via active learning," in *Proc.
     ASP-DAC*, 2023.

[13] Liu et al., "OPTIMIS: Tail-accurate importance sampling for memory yield,"
     in *Proc. DAC*, 2023.

[14] V. Gupta and B. H. Calhoun, "Analytical modeling of SRAM Vmin," *IEEE
     Trans. Circuits Syst. I*, 2021.

[15] Kinoshita, "Space-filling designs for semiconductor process
     characterization," *IEEE Trans. Semicond. Manuf.*, 2025.
