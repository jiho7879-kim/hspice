# Forward and Inverse SRAM Vmin Estimation Across a Nine-Dimensional Process Window: A Physics-Constrained Gaussian Process Surrogate

**[Authors TBD — O-01]**
**[Affiliation TBD — O-01]**

> Internal technical report · IEEE manuscript format · draft v4.0 (2026-09-05)
> Every number in this manuscript traces to an evidence ID in `manuscript/LEDGER.md`.
> Open before submission: title/authors/affiliation (O-01), target venue (O-05),
> re-confirmation of the Stage-B pilot defect conditions with the fab (O-06).

---

## Abstract

Signing off the minimum operating voltage (Vmin) of an SRAM across the whole
process-variation window is unaffordable by direct Monte Carlo, and corner-based sign-off
cannot observe variation axes that no corner definition contains. We present a surrogate
pipeline that answers forward and inverse Vmin queries from one fixed simulation budget: a
Gaussian process regresses the margin statistics over nine process axes and the supply
voltage, a physics layer with no trainable parameters converts them into the
yield-referenced Vmin, and inverse queries are solved exactly by axis-wise bisection. On
production calibration data from an advanced FinFET node, the condition-level hold-out
Vmin RMSE is 8.35 mV for read and 14.45 mV for write; on PDK corners absent from training
it is 9.3 and 16.7 mV, with the limiting corner of each mode identified correctly. Inverse
queries recover a process coordinate from a Vmin value to within 2.6–3.2 mV. Cutting the
simulation budget 53x costs 2.6 mV of Vmin RMSE although the three single-factor
experiments predict no loss at all: a reduction is a Pareto point with a price. A variance
decomposition places at least 39% of the read margin variance on axes no corner contains.
Finally we identify the lobe correlation as the quantity that sets the systematic optimism
of the min-statistics z-score, measure it from production Monte Carlo output alone
(-0.371, or 1.054 sigma), and show that correcting for it puts the read-limiting corner 37
mV past spec: the dominant uncertainty lies in the metric, not the model.

**Index Terms** — Gaussian process, inverse problem, minimum operating voltage, process
variation, sensitivity analysis, SRAM, static noise margin, surrogate model, yield
analysis.

---

## I. Introduction

### A. The sign-off spec and the margin it leaves

SRAM occupies the largest area in a modern SoC and dominates chip yield. The process
studied here has a nominal supply of 0.75 V; after on-chip and off-chip IR drop, the
sign-off Vmin spec is **0.625 V** (Table I). All simulations and decisions here are
time-zero. Guardbands for degradation such as BTI were established empirically in
silicon and are already folded into this time-zero spec [1]–[3], so we do not apply a
post-degradation voltage as a second criterion.

**TABLE I. Vmin specification**

| Item | Value |
|---|---|
| Nominal supply | 0.75 V |
| **Sign-off Vmin spec (time-zero)** | **0.625 V** |

The margin this leaves is thin. With only the corners applied and every other axis at
nominal, the read-limiting corner (FSG) and the write-limiting corner (SFG) reach
0.5903 V and 0.5924 V, within 35 mV of spec (Section V-D). At that margin, **any systematic
optimism converts directly into a sign-off misjudgment.** This margin structure is what
sets the relative importance of model error, statistical noise, and metric bias
throughout the paper.

### B. The cost of direct verification

The industry standard estimates Vmin by MC. For each process condition, thousands of
random mismatch samples build a margin distribution, repeated at every voltage level.
At the scale used here — 2,000 conditions per mode × 4–5 voltages × 5,000 MC per
condition — that is 4–5 × 10⁷ circuit simulations. With a simulator run of minutes to
tens of minutes, the wall-clock time is weeks to months even under parallel execution,
plus PDK licences, concurrency limits, and server cost. The burden grows at advanced
nodes as compact models get heavier.

### C. Two limitations of corner-based sign-off

Restricting verification to the representative corners (FFG/FSG/SFG/SSG) contains the
cost but loses two things.

First, a corner is only an extreme combination of two axes, the NMOS and PMOS Vth
shifts. The Vth skew, local σ, and mobility axes studied here do not enter the corner
definition at all. Section VII quantifies their contribution; a corner-based procedure
cannot observe those axes even in principle.

Second, corners answer only the forward question. The questions asked in practice are
inverse ones — which combination of variations violates the spec, how far must a
parameter be tightened to restore compliance, how much skew can be tolerated. A finite
set of points fixes neither the location nor the shape of the compliance boundary.

### D. Related work

Surrogates for SRAM yield are an established line of work. Guo *et al.* [4] use a
multi-fidelity neural network; Yin *et al.* [5], [6] use active learning and shrinkage
features; Liu *et al.* [7] search an optimal manifold — all to reduce **the cost of
estimating the extremely low failure rate at a given design point**. On the sampling
side, quasi-MC [8] and space-filling Latin hypercube designs [9] are established.
Gupta and Calhoun [10] address Vmin itself, estimating dynamic read Vmin jointly with
yield.

The rare-event side of the problem has its own literature. Statistical blockade [11]
filters samples through a classifier and fits a generalised Pareto tail to what survives;
mixture importance sampling [12] shifts the sampling distribution towards the failure
region and reweights. Both attack the same difficulty — a 6σ quantile is unreachable by
plain Monte Carlo — and both do it at one design point.

What differs here is the **direction of the question**. Those works estimate the failure
probability of one point accurately; we obtain the Vmin **contour** over the whole
process window and then invert it to recover conditions. The requirement is therefore
different — not importance sampling in the extreme tail, but smooth regression across
nine dimensions plus an inverse query that is solved exactly on top of it. The two are
complementary rather than competing: a blockade or importance-sampling campaign is what
would produce trustworthy labels at the conditions this surrogate flags as marginal.

On the metric itself, the non-normality of SNM is established [13], [14]. What has not
been done is to identify the physical quantity that sets the size of the resulting bias,
measure it from production MC output alone, and convert it into the Vmin units of a
product spec — which in our data exceeds the model error by an order of magnitude
(Section V-F).

### E. Contributions

1. A surrogate pipeline that serves forward and inverse Vmin queries from one fixed
   budget. The inverse is solved as an **axis-wise one-dimensional exact solution**,
   accurate to machine precision with no optimizer, learning rate, or tolerance
   (Sections IV-F, V-E).
2. Validation at three levels of distance from the training distribution — in-batch
   hold-out, PDK corners absent from training, and an independently designed pilot batch
   — for both read and write modes (Sections V-B, V-D, V-G).
3. Evidence for budget reduction along voltage levels, condition count, and MC depth,
   plus the direct measurement that **the losses do not multiply when the three are cut
   together** (Section VI).
4. A quantitative sensitivity ranking, including axes no corner can observe, and the
   resulting skew tolerance (Section VII).
5. Identification of ρ_LR as the physical quantity that sets the systematic optimism of
   the min-statistics z-score, its measurement from production MC output alone, and its
   conversion into the Vmin units of a specific product spec (Sections II-D, V-F).

Fig. 1 shows the pipeline these five contributions assemble: one GP fit per mode, a
physics layer with no trainable parameters, and both query directions off the same fit.

**Fig. 1.** Pipeline overview.

---

## II. Problem Formulation

### A. Stability metrics

The read stability of a 6T cell is quantified by the static noise margin (SNM), defined
as the **minimum** of the two lobes of the butterfly characteristic [15]. Write stability
is measured by the write trip point (V_trip). MC produces a distribution for each
metric, of which the mean μ and standard deviation σ are conventionally recorded. The
method is metric-agnostic and is applied identically to both.

### B. Definition of Vmin and the yield target

For a condition **x**, the margin ratio

    z(V_op) = μ(x, V_op) / σ(x, V_op)                                     (1)

is evaluated on a voltage grid, and Vmin(**x**) is the voltage where z crosses the target
z-score Z_t, obtained by linear interpolation.

Z_t follows analytically from the array yield requirement. For a 128 Mb array at 99%
Poisson yield,

    p_fail = −ln(0.99) / (128 × 10⁶) ≈ 7.85 × 10⁻¹¹                        (2)
    Z_t = Φ⁻¹(1 − p_fail) = 6.398                                          (3)

where Φ is the standard normal CDF. The failing unit is the **cell**; multiplying by the
transistor count is wrong. The 128 Mb array size is consistent with the 14 nm 128 Mb
SRAM of [16].

Two reference quantities must be kept apart. Z_t is a yield criterion that enters the
*definition* of Vmin; the spec voltage of Table I decides whether the resulting Vmin
*passes*. They are set independently. That Z_t is an analytic derivation rather than a
silicon calibration is decisive for Section II-D.

### C. Region of interest and two-sided censoring

Vmin accuracy is needed only where it changes a decision. Conditions whose Vmin lies
below the lowest simulated voltage pass with ample margin and are left-censored;
conditions above the grid violate the spec by a wide margin and are right-censored.
The interval between the two contains the spec point at 0.625 V and is the only region
where numerical accuracy is required.

The voltage grids are {0.4, 0.5, 0.6, 0.7, 0.8} V for read and {0.4, 0.5, 0.6, 0.7} V
for write. This choice is dictated by the spec, not by data availability: it contains
the minimal bracket around the spec point. Section VI-A gives the quantitative
justification. Censored conditions are excluded from continuous error metrics and their
share is reported alongside.

One caveat: **the censoring share depends on the decision threshold.** Correcting the
bias of Section II-D raises the effective threshold, which increases the right-censored
share on the same grid. The adequacy of the grid ceiling must therefore be judged at the
corrected threshold, not the naive one (Section VI-A).

### D. The systematic bias of the min-statistics z-score

SNM is the minimum of two lobe margins, and the minimum of two Gaussian variates is not
Gaussian: its lower tail is heavier than a moment-matched normal. Equation (1)
nevertheless fits a Gaussian to the minimum and extrapolates to Z_t = 6.398, so it
systematically underestimates the failure probability. A failure occurs if *either* lobe
collapses, so the true failure probability is a union probability.

The non-normality of the SNM distribution is itself established. Saeidi *et al.* [13]
showed that the one-sided read SNM follows a weighted sum of normals rather than a single
Gaussian; Zheng and Mazumder [14] modeled within-die SNM variation as a combination of
folded-normal and non-central chi-squared distributions with agreement beyond 6σ. The
contribution here is not that observation but **identifying the physical quantity that
sets the size of the bias, measuring it from production MC output alone, and converting
it into the Vmin units of a specific product spec.**

Given the per-lobe statistics (μ_L, σ_L, μ_R, σ_R, ρ_LR), the failure probability is
closed-form:

    p_fail  = P(L<0) + P(R<0) − P(L<0, R<0)                               (4)
    Z_union = Φ⁻¹(1 − p_fail)                                             (5)

The joint term is a bivariate normal CDF, computed with Owen's T function [17]. Z_union is
the z that a correct union calculation assigns to a condition; the naive z of Eq. (1)
returns a smaller value, and the gap between them is the bias this section is about.

#### 1) The physical meaning of ρ_LR

The size of the bias is set entirely by ρ_LR, and this is not an arbitrary fitting
constant but **a physical quantity that directly reflects the local/global split of the
variation**.

In two cross-coupled inverters, local mismatch that strengthens one side widens the lobe
in that direction while cutting the opposite lobe. The local component therefore
anti-correlates the two lobes. A device-type-level global shift moves both sides the same
way and co-correlates them.

- ρ_LR → +1 : global dominates; the minimum converges to a single Gaussian and the bias
  vanishes.
- ρ_LR = 0 : the lobes are independent.
- ρ_LR → −1 : local mismatch dominates; the union failure probability, and the bias, are
  maximal.

An important consequence follows. **The experiment design of Section III cannot mitigate
this bias.** All nine design axes are device-type-level global quantities that preserve
the left–right symmetry of the cell, so under the design axes alone the two lobes are
exchangeable at every condition. What makes the lobes asymmetric arises only from local
mismatch *inside* an MC sample. There is therefore no subset of conditions that is
naturally exempt, and the bias applies across the entire process window.

#### 2) Structure of the correction

The bias affects **only the threshold** of the (μ, σ) → Vmin conversion. Since Vmin is
the crossing of z(V_op) = Z_t, what is needed is not the whole z axis but the bias at
the single point z = Z_t. The correction is therefore the post-processing step

    z_bias = Z_union(ρ_LR, Z_t) − Z_t                                     (6)
    Z_eff  = Z_t + z_bias                                                  (7)

where z_bias is evaluated at the target quantile: it is the amount by which the union
calculation exceeds the naive threshold there. The corrected threshold Z_eff is what the
crossing must reach, and the correction requires no re-simulation. Consequently the **ordering** conclusions of Sections V–VII —
the sensitivity ranking and the corner ordering — are unaffected. Anything referenced to
the threshold does move: pass fractions, tolerance widths and the location of the
compliance boundary all contain Z_t, so both thresholds are reported wherever they occur
(Tables XIV and XIX, Section VII-D).

#### 3) How ρ_LR can be measured

Read SNM flows normally report only the μ and σ of the minimum. But the **skewness of
min(L, R) is a closed-form function of ρ_LR**, so ρ_LR can be inverted from the minimum
samples alone. Since min(L,R) = (S − |D|)/2 with S = L+R and D = L−R independent,

    a² = 2(1 − ρ),  c = √(2/π)
    m₂ = 1 − a²/(2π),  m₃ = −a³(2c³ − c)/8
    g₁(ρ) = m₃ / m₂^{3/2}                                                 (8)

where m₂ and m₃ are the second and third central moments of the standardized minimum —
written m, not μ, because μ denotes the margin mean throughout.

and g₁ is monotone in ρ. Skewness uses the whole sample and is therefore statistically
more efficient than a tail fit that depends on a handful of lower quantiles. The
measurement is reported in Section V-F.

---

## III. Experiment Design

### A. Input space and two batches

**A word on vocabulary.** No silicon data enters this study. Every value the surrogate is
scored against is HSPICE Monte Carlo output, and we call it the **reference simulation**
throughout. "Measure" is reserved for quantities this work estimates from that output —
ρ_LR, the repeatability floor, the budget-reduction price — and "silicon measurement" is
used only where the paper says such a measurement is missing.

The nine device-variation axes of Table II are sampled jointly with the supply voltage.

**TABLE II. Variation parameters**

| Symbol | Description | Range | Unit |
|---|---|---|---|
| cn | NMOS common Vth shift | ±60 | mV |
| sk | Pass-gate / pull-down Vth skew | ±20 | mV |
| pu | PMOS Vth shift | ±60 | mV |
| lpu | Pull-up local σ multiplier | [0.7, 1.3] | — |
| l_com | NMOS local σ, common | [0.7, 1.3] | — |
| l_sk | NMOS local σ, skew | ±0.075 | — |
| mpu | Pull-up mobility multiplier | [0.7, 1.3] | — |
| m_com | NMOS mobility, common | [0.7, 1.3] | — |
| m_sk | NMOS mobility, skew | ±0.075 | — |

Deck parameters follow as Vth_PG = cn + sk and Vth_PD = cn − sk; the local σ and mobility
multipliers decompose the same way.

**Read and write are each characterized only at their own worst-case temperature.**
Read is worst hot (125 °C), write worst cold (−40 °C). Running each mode only at its own
worst temperature, instead of every mode at every temperature, is a deliberate **cost
decision**, and it splits the data into two batches: SNMR (read static noise margin, the
retention-side minimum) at 125 °C, 2,000 conditions ×
5 levels, and V_trip at −40 °C, 2,000 conditions × 4 levels. The intersection of their
nine-dimensional coordinates is **0/2000**, and the input has no temperature axis, so
**the two cannot be merged into one GP.** There are two models; only the argument of the
paper runs jointly.

Both the price and the benefit of this choice surface in Section V-D. The price is that the
per-condition combined Vmin = max(read, write) cannot be verified against the reference
simulation in the 2,000-condition batches. The benefit is that the **complementarity** of the two modes
— each filling the other's censored corner — is confirmed by the reference simulation.

### B. Common/skew parameterization

The pass-gate and pull-down devices share the NMOS flavor, hence share the dominant
variation sources — gate stack, channel doping, anneal, lithographic critical dimension
— with imperfect tracking from device geometry and layout environment. Sampling them
independently assigns design points to states never realized in silicon, where two
devices of the same flavor diverge in opposite directions at the mismatch level.

The adopted common/skew split induces corr(l_PG, l_PD) ≈ 0.88, inside the plausible
0.85–0.95 range for same-flavor tracking and consistent with the ρ ≈ 0.80 structure of
the Vth axes. The common and skew components are sampled independently, a property the
variance-based analysis of Section VII requires. Fig. 2 shows both halves of the design:
the quadrant weighting in (a) and the tracking band it induces in (b).

**Fig. 2.** (a) Quadrant weighting in the (cn, pu) plane; (b) the diagonal
(l_PG, l_PD) tracking band induced by independent (l_com, l_sk) sampling.

### C. Quadrant weighting

Read and write margins degrade in different quadrants — FSG for the former, SFG for the
latter. A separate deck set per metric carries the weights of Table III, raising the
resolution of the worst region by 2–4× at a fixed condition count. Conditions are
generated from deterministic PCG64 draws on independent per-quadrant streams.

**TABLE III. Quadrant weighting per metric**

| Metric | FSG | FN | SN | SFG |
|---|---|---|---|---|
| Read (SNM) | 45% | 20% | 15% | 20% |
| Write (V_trip) | 10% | 15% | 30% | 45% |

An initial design hypothesis was that stratified low-discrepancy sampling would beat
pseudo-random draws. Internal validation supported this on neither the domain-uniform nor
the corner-restricted metric, so the claim is withdrawn. The benefit of this design comes
from quadrant weighting alone.

### D. Mirror-twin leakage — an early design failure and its fix

An early pilot design reused a single quasi-random stream across the four quadrants,
flipping only the signs of cn and pu. As a result, 75% of conditions had a mirror twin
sharing the remaining seven coordinates, and in a random hold-out about 74% of test
conditions had a twin in training — **inflating the accuracy metrics with no
implementation defect anywhere.**

The cause was identified by comparing the executed condition coordinates against a
reconstruction of the generator, and fixed by assigning independent streams per quadrant.
The two batches used in this paper have no mirror twins by construction: all 2,000
conditions differ in the seven coordinates other than (cn, pu), and the training script
asserts this. Design-induced leakage of this kind inflates metrics silently, so surrogate
validation studies should report the design generation procedure together with the split
rule.

### E. Data quality audit

In an internal characterization flow with heavy manual transcription, the spreadsheet
itself is an error source. We applied a **μ(V_op) monotonicity audit** to both batches:
μ must increase monotonically with supply, so a violation exceeding three MC standard
errors is a transcription error.

We corrected 31 cells in the read batch (3 typos plus 19 conditions of monotonicity
violation, 19 μ and 9 σ cells) and 12 in the write batch. Six missing-decade errors were
restored by ×10; the rest were replaced by a quadratic fit through the other voltage
points of the same condition (residual RSS 0.001–0.5 mV²). No cell was quarantined and
all 10,000 cells are used. The script asserts that zero violations remain.

The effect is large: for read, μ RMSE improved from 5.44 to **2.50 mV** and Vmin RMSE
from 14.74 to **8.35 mV**. Section V-B describes what triggered the audit — **the model
pointed at defects in its own training data.**

**A repaired label is no longer a measurement, so it must not quietly grade the model.**
Thirteen read conditions were repaired by the quadratic-in-V_op route, and that route
borrows exactly the smoothness a GP also assumes; a repaired cell sitting in the hold-out
would be a label the model is nearly guaranteed to match. Four of the thirteen do sit in
the hold-out. Scoring without them gives **8.39 mV over 240 conditions** against 8.35 mV
over 243, and dropping every condition touched by the audit — decade restorations and
typos included, seven in total — gives **8.44 mV over 237**. The headline number does not
depend on the repairs. For write the question does not arise: no write condition was
repaired by the quadratic route, and excluding all six touched conditions moves 14.45 mV
to 14.48 mV.

---

## IV. Surrogate Model

### A. Gaussian process regression

A GP [18] provides non-parametric Bayesian regression that returns a calibrated predictive
variance alongside the predictive mean. The model maps the nine variation axes and the
supply voltage to the margin statistics (μ, σ). Three properties justify the choice:
behavior under limited data, quantified predictive uncertainty, and a likelihood that
accepts per-condition noise directly (Section IV-E). Appendix A gives the background.

The μ process uses a Matérn-5/2 kernel with ARD, assigning an independently learned
lengthscale λ to each input dimension. The σ process uses an additive kernel that
separates the supply-voltage group from the device-variation group. Kernel lengthscales
are written λ throughout, to keep them distinct from the local-σ length axes l_com, lpu
and l_sk of Table II.

### B. Input standardization

The input vector mixes mV-scale shifts, V-scale supply levels, and dimensionless
multipliers. Without standardization, marginal likelihood optimization converges to a
markedly worse optimum **with no diagnostic warning**. Most of an improvement initially
attributed to the physics constraints was later traced to this factor. All inputs are
standardized with training statistics.

### C. Physics layer

The conversion from (μ, σ) to Vmin is imposed as an **analytic constraint with no
trainable parameters**. For each condition the posterior mean is evaluated at every
supply level, the margin ratio is formed by (1), and the crossing with Z_t is
interpolated linearly. That this layer is not learned matters: in sparsely sampled
regions the GP extrapolates only (μ, σ), while the definition of Vmin never moves.
Censored conditions are flagged and excluded.

### D. Physics constraints

Three constraints inject prior device knowledge. **Corner anchoring** augments the
training set with virtual observations at the four global corners, preventing
extrapolation drift at the domain extremes. A **monotonicity penalty** ReLU(−∂μ/∂V_op)²
evaluated at probe points through the posterior suppresses the unphysical prediction that
raising the supply degrades mean stability. Weak regularization induces a linear σ(V_op)
trend consistent with established mismatch scaling [19].

### E. Noise-aware likelihood

Per-condition bootstrap standard errors enter a fixed-noise Gaussian likelihood, so
conditions backed by larger MC batches receive proportionally larger weight. Bootstrap
rather than analytic standard errors are used because the standard error of σ is
sensitive to kurtosis.

This mechanism absorbs heterogeneous sample budgets into one model. When lower fidelity
consists of **nothing but fewer samples from the same simulator**, a heteroscedastic
single-fidelity GP is the correct model and the discrepancy term of a multi-fidelity
formulation [20] is unnecessary. Because the posterior borrows strength from neighbouring
conditions, an individual condition does not need a large MC batch to be informative —
which is the basis for spending a fixed budget on **breadth of condition coverage**
rather than depth per condition (Section VI-C).

### F. Inverse queries: axis-wise exact solution

For a target spec voltage V*, the set {**x** : Vmin(**x**) = V*} is a hypersurface in
the nine-dimensional variation space and forms the boundary of the admissible process
window. In practice the question put to this boundary is usually about a single axis —
"given the rest of the conditions, how far can I turn this knob and still meet spec?"

That form of query is solved **exactly**. Fixing the other eight coordinates makes Vmin a
one-dimensional function of the chosen axis, and that function is monotone: Vmin
decreases in cn (a faster pass-gate needs a lower supply) and increases in pu. We
evaluate Vmin at both ends of the design range, check that the target is bracketed, and
narrow the crossing by bisection. Twenty-four iterations shrink a ±60 mV span below
10⁻⁵ mV, so the solution is exact to machine precision with respect to the surrogate.
**There is no optimizer, no learning rate, and no convergence tolerance.**

The direction of monotonicity is not assumed but read from the two endpoints. A slice
where the target is not attained anywhere in the design range — for example when pu is
fast enough that any cn meets spec — has no boundary, and is reported as "no boundary"
rather than clipped to a range end. That distinction is part of the result (Section V-E).

**A planar boundary is traced by the axis-wise solution.** The boundary curve of a
two-dimensional section such as (cn, pu) is obtained by solving cn* one-dimensionally at
each row of the pu grid. This is both cheaper and more accurate than sweeping the same
plane on a grid. In our setting, solving the 33 pu rows where a boundary exists took
26 evaluations each, **858 condition evaluations** in total, against **4,900** for a
70 × 70 grid over the same plane — a 5.7× difference; and where the grid can only place
boundary points by interpolating between cells, the axis-wise solution returns the
boundary points themselves.

Without the surrogate the query does not exist. One bisection requires Vmin at 26
distinct process conditions, each a MC batch at five supply levels: 130 MC runs per
boundary point in HSPICE, 4,290 for the 33 rows. On a trained surrogate the same
computation takes seconds.

> **Scope.** The procedure above solves exactly the query with one unknown axis.
> Obtaining the full nine-dimensional hypersurface with several axes free at once is
> outside the scope of this paper. Gradient descent through the differentiable composite
> function is the natural extension there, but **we claim only what we validated**
> (Section VIII-E).

---

## V. Validation

### A. Split and evaluation procedure

The split is at condition level. Of each batch's 2,000 conditions, 1,700 go to training
and 300 to hold-out, and all supply levels of a condition always stay in the same
partition. As established in Section III-D neither batch has mirror twins, so the
condition-level split leaks nothing, and the training script asserts this. Vmin errors are
reported on the non-censored subset with the censoring share alongside.

Validation is stacked at three levels: **in-batch hold-out** (Section V-B) → **PDK corners
absent from training** (Section V-D) → **an independently designed pilot batch**
(Section V-G). Each step is further from the training distribution.

### B. Forward accuracy

This section answers one question — **within how many mV does the surrogate reproduce
the worst-case Vmin that HSPICE MC would have produced at an arbitrary process
condition?** The criterion is the per-condition Vmin; the accuracy of μ and σ is reported
alongside as the intermediate product that makes it.

**TABLE IV. Hold-out prediction accuracy (300 conditions per mode)**

| Item | Read (SNM, 125 °C) | Write (V_trip, −40 °C) |
|---|---|---|
| μ RMSE / R² | 2.50 mV / 0.9965 | 2.17 mV / 0.9989 |
| σ RMSE / R² | 0.256 mV / 0.9798 | **2.04 mV / 0.7318** |
| **Vmin RMSE (per condition)** | **8.35 mV** | **14.45 mV** |
| \|error\| median / P90 / max (percentiles of \|error\|) | 3.36 / 10.69 / 53.78 mV | 9.81 / 21.47 / 53.06 mV |
| Censored: crossing below the grid floor | 49 / 300 | 69 / 300 |
| Excluded: crossing above the top level | 8 / 300 | 3 / 300 |
| **Scored conditions** | **243** | **228** |
| Training / hold-out rows | 8,500 / 1,500 | 6,777 / 1,195 |

The write batch has only four supply levels (0.4–0.7 V), a narrower grid and hence more
censored conditions.

The two exclusions are not the same thing. A censored condition has its crossing below
0.4 V, so both reference and prediction are clamped to the floor and the difference
between them is not an error. A condition excluded at the top has no crossing inside the
grid at all, so no Vmin exists to compare. Both are outside the RMSE, which leaves 243
scored read conditions and 228 write.

RMSE alone does not reveal the error structure, so we look at the distribution. The
53.78 mV maximum for read occurs at **three conditions only**, whose reference Vmin is
0.401–0.404 V — right at the grid floor — where the surrogate predicts a crossing below
0.4 V and is clamped to the floor. The magnitude is set by the clamp width, not by
prediction quality, and these conditions sit more than 200 mV below the spec voltage.
Excluding those three, the Vmin RMSE is **6.02 mV** with a maximum error of **19.3 mV**.
Table V breaks the error down by Vmin band.

**TABLE V. Read Vmin error by band (hold-out, 243 non-censored conditions)**

| Reference Vmin band | Conditions | RMSE (mV) | \|error\| median | \|error\| max |
|---|---|---|---|---|
| 0.40 – 0.45 V | 48 | 14.03 | 3.49 | 53.8 † |
| 0.45 – 0.55 V | 97 | 5.04 | 2.83 | 17.8 |
| 0.55 – 0.65 V | 72 | 6.32 | 3.55 | 19.1 |
| 0.65 – 0.75 V | 23 | 8.07 | 4.78 | 15.5 |
| 0.75 – 0.80 V | 3 | 14.73 | 16.24 | 19.3 |

† Includes the three grid-floor clamps.

Across 0.45–0.75 V, where decisions are actually made, the RMSE is 5–8 mV — **an order of
magnitude below** the metric bias measured in Section V-F (+1.054 σ in z, 70 mV in Vmin).
The term that dominates the sign-off decision is not the regression error of the
surrogate but the bias of the metric itself. Fig. 3 plots predicted against reference
Vmin for both modes.

**Fig. 3.** Reference-simulation versus predicted Vmin on the hold-out conditions.

#### 1) The write bottleneck is the variance, not the mean

In Table IV the write μ prediction is more accurate than the read one (R² 0.9989). Its
Vmin error is nevertheless 1.7× larger, and the reason is σ. Since z = μ/σ, the relative
error of σ propagates straight into z and then into the crossing. The write σ reaches
only R² = 0.732.

Two effects overlap. First, the σ of V_trip has a wide condition-to-condition spread
(SD 3.96 mV against 1.79 mV for read). Second, **69% of the transcribed σ values are
rounded to integers** (1% in the read batch). Rounding alone contributes an RMS of
1/√12 ≈ 0.29 mV, which does not account for the observed 2.04 mV. Section V-G tests this
diagnosis directly against an independent batch with almost no rounding, and the result
changes how the cause is apportioned.

#### 2) A by-product: the surrogate as a transcription-error detector

In early training two hold-out conditions had Vmin errors above 100 mV. Tracing them led
not to the model but to the transcription sheet. In both, only the 0.6 V SNM mean was
recorded at one tenth of its neighbors (e.g. 10.9 mV between 83.8 and 127.0 mV), and the
surrogate was predicting 109.9 mV for the same cell. This triggered the full audit of
Section III-E. Using **a trained surrogate to point at defects in the data that trained it**
is a secondary but practical by-product in any internal flow with heavy transcription.

#### 3) How much of this is the Gaussian process?

A surrogate paper should say what its choice of regressor buys, so we scored the simplest
alternative that could plausibly work: a full quadratic response surface in the same ten
inputs (66 terms), least squares on the same training rows, through the same physics
layer, on the same hold-out. Table VI puts the two side by side.

**TABLE VI. Gaussian process against a quadratic response surface**

| | GP, read | Quadratic, read | GP, write | Quadratic, write |
|---|---|---|---|---|
| μ RMSE | 2.502 mV | **2.386 mV** | **2.171 mV** | 3.455 mV |
| σ RMSE | 0.256 mV | **0.137 mV** | 2.041 mV | **1.622 mV** |
| Vmin RMSE, hold-out | 8.35 mV | **7.69 mV** | 14.45 mV | **13.97 mV** |
| Vmin RMSE, PDK corners | 9.34 mV | **6.11 mV** | **16.70 mV** | 18.86 mV |

**The quadratic is not worse, and for read it is better** — including at the four PDK
corners, which the fit never saw, so this is not an in-batch artifact. For write the two
trade places: the GP has the better μ and the better corners, the quadratic the better σ
and a marginally better hold-out Vmin.

We report this rather than bury it, and it bounds the claim this paper makes. **Nothing
in the rest of the paper turns on the regressor.** The physics layer, the censoring
treatment, the axis-wise inverse, the budget curves and the ρ_LR correction all take μ and
σ as inputs and would accept either model. What this comparison says is that over a
process box this smooth, a quadratic surface is sufficient for the mean and the spread —
which is useful news for a fab flow, since it removes GP training from the deployment
path entirely.

What the GP supplies that the quadratic does not is a per-point predictive variance and a
likelihood that weights conditions by their MC standard error. Neither is exercised as a
deliverable here: no result in this paper consumes the predictive variance, and every
condition in this dataset carries the same 5,000 samples (Section VI-C). We therefore do
not claim them as demonstrated advantages. Two caveats on the comparison itself: the GP
was fitted with 150 Adam iterations and was not tuned further, and the condition-count
knee of Section VI-B is a property of the GP — a 66-coefficient surface would be expected
to need far fewer conditions, which we did not measure.

### C. Physical consistency

A model can fit the numbers and still be wrong about the device. Table VII lists the
properties the physics requires and what the fitted model does with them.

**TABLE VII. Physical consistency checks (read model)**

| Property | Expected | Fitted model | Result |
|---|---|---|---|
| Pass-gate dominance | λ_cn < λ_pu | λ_pu/λ_cn = **1.093** | pass |
| Vth direction | ∂Vmin/∂cn < 0 | negative | pass |
| Pull-up direction | ∂Vmin/∂pu > 0 | positive | pass |
| Worst read corner | FSG | FSG | pass |
| Supply sensitivity | shortest lengthscale | λ_Vop = **4.64**, shortest | pass |

The pass-gate dominance hierarchy — a shorter lengthscale on cn than on pu — also
reproduced in the same direction on earlier pilot design batches; we report only the
direction here, because the per-batch values were not re-derived into this manuscript's
evidence ledger. These are qualitative checks; the quantitative sensitivity ranking is read from the variance-based
indices of Section VII.

### D. Fixed-corner validation

The hold-out of Section V-B comes from the same batch, so a bias in the design itself would
go undetected. This section asks the same question with data generated **independently of
the training batch**: separate runs of the four global corner decks provided by the PDK,
which appear in neither training nor hold-out.

A corner is a (Vth shift_n, Vth shift_pu) pair, corresponding in the nine-dimensional
input to placing those shifts in (cn, pu) with the other seven coordinates at nominal.
All four corners lie **inside** the training box — this is not extrapolation, and the
script verifies it coordinate by coordinate. The corner decks were simulated under the
same conditions as each mode's batch — 125 °C for read, −40 °C for write, the same MC
sample count — so neither temperature nor sample size enters as a confound.

**TABLE VIII. Vmin per corner — independent simulation versus surrogate (Z_t = 6.398)**

| Corner | (cn, pu) mV | Read reference → GP (error) | Write reference → GP (error) |
|---|---|---|---|
| **FSG** | (−29.16, +38.64) | **0.5903 → 0.5908 (+0.6 mV)** ← read worst | < 0.4 V, both clamped |
| **SFG** | (+31.63, −36.76) | < 0.4 V, both clamped | **0.5924 → 0.6070 (+14.6 mV)** ← write worst |
| FFG | (−36.42, −44.32) | 0.4731 → 0.4604 (−12.7) | 0.4923 → 0.4939 (+1.6) |
| SSG | (+36.30, +44.80) | 0.4672 → 0.4772 (+10.0) | 0.5335 → 0.5086 (−24.9) |
| **RMSE / max** (3 scored corners) | | **9.3 / 12.7 mV** | **16.7 / 24.9 mV** |

On the three scorable corners the read Vmin RMSE is 9.3 mV, the same magnitude as the
8.35 mV hold-out error. That the error does not grow on data generated outside the
training design indicates that the model learned the behavior over the (cn, pu) plane
rather than a particular structure of the design.

**What matters for design is the ordering.** For read, both reference and prediction
name **FSG** as the worst corner, and the error there is 0.6 mV, the smallest of the four.
The second and third places (FFG 0.4731 V, SSG 0.4672 V) do swap in the prediction.
Their reference gap of **5.9 mV** is smaller than the model's corner RMSE (9.3 mV), which
means this accuracy cannot separate them. The claim that can be supported is therefore
"the read-limiting corner is identified", not the ordering of mid-table corners 5 mV
apart. For sign-off this is not a problem — the decision uses the worst corner. On the
write side the corners are more than 40 mV apart and the **ordering reproduces 4/4**.

At the spec voltage of 0.625 V, the sign of the z margin (pass/fail) agrees between
reference and prediction at all four corners for both modes (4/4, 4/4). This is a
sanity check that the model is operating correctly, not a claim about population yield.
**This paper does not estimate yield.**

#### 1) The two modes fill each other's gaps

In Table VIII, SFG is clamped below 0.4 V in both reference and prediction for read.
This is a physical fact, not a data defect — **read does not set Vmin at that corner.**
SFG combines a fast pull-up with a slow pass-gate, which favors read stability while
making the cell hard to flip, so **write** becomes the constraint. Symmetrically, FSG is
censored for write.

Beyond that symmetry, the read worst (FSG, 0.5903 V) and the write worst (SFG, 0.5924 V)
differ by only **2 mV**. This cell design sits near the balance point between read and
write, with no room left to optimize one side alone; equally, it shows that **reasoning
about Vmin from a single mode misses the decision at the opposite corner**.

The combined per-condition Vmin is max(read, write). At the four corners both
reference runs exist and Table VIII gives that value directly. In the 2,000-condition
batches the coordinates do not overlap, so the same comparison cannot be made against
the reference simulation; each surrogate would have to be evaluated at the other's
coordinates, and
that would be a prediction built on a prediction (Section VIII-C). Fig. 4 compares the
per-corner values for both modes.

**Fig. 4.** Reference-simulation versus predicted Vmin per corner, read and write.

### E. Inverse validation

The forward surrogate answers "what is the Vmin of this condition". The use this paper
targets is the reverse — **"which process condition meets a target Vmin?"** This section
validates that direction against the reference simulation.

So that the validation is not a self-consistency check of the model against its own
output, the target is always **the Vmin taken from the reference z curve**. The procedure:
pick a hold-out condition, fix eight of the nine coordinates at the deck's actual values,
leave the ninth unknown, and find the value at which the surrogate's Vmin equals that
condition's reference Vmin. Then compare it with the coordinate the deck actually had.
**Because the answer to be recovered is already in the data**, the inverse error can be
measured directly in mV.

The unknowns are the two knobs design actually turns, cn and pu. A condition whose target
is not attained for any value inside the design box [−60, +60] mV is left unrecovered
rather than clipped. Table IX gives the recovery error for each axis.

**TABLE IX. Coordinate recovery error (245 hold-out conditions, target = reference Vmin)**

| Unknown | Recovered | RMSE | Median | P90 | Max | Bias | \|∂Vmin/∂x\| | Implied by forward 8.35 mV |
|---|---|---|---|---|---|---|---|---|
| cn | 244 / 245 | **2.60 mV** | 1.63 | 4.31 | 10.72 | −0.38 | 2.081 | 4.01 mV |
| pu | 235 / 245 | **3.20 mV** | 2.08 | 5.32 | 9.81 | +0.46 | 1.633 | 5.11 mV |

The Vth coordinates are recovered to within 2–3 mV. Two reference points make this
readable.

First, the recovery error is **smaller than the forward error implies**. Converted
through the local sensitivity at the target, the forward Vmin RMSE of 8.35 mV corresponds
to 4.01 mV in cn and 5.11 mV in pu; the actual recovery errors are 60–65% of that. The
inverse constrains the coordinate through the whole z(V) curve of the condition rather
than through a single Vmin point, so errors at one voltage partly cancel against errors
at another. Second, the **bias is within ±0.5 mV**, so there is no systematic offset.

In practical terms this accuracy is finer than the usual tolerance of Vth targeting. The
question "where must Vth sit to meet this Vmin" can be answered at a resolution the
design can act on.

#### 1) Multistart convergence

With the target set to Vmin = 0.625 V, the inverse was run from twelve random starts
inside the design box. **All twelve converged onto the target manifold with a maximum
residual of 4.7 × 10⁻⁴ mV.** Each start is a one-dimensional slice at fixed pu, so the
solution is unique, and this residual confirms that the axis-wise solver of Section IV-F is
exact to machine precision.

#### 2) The design boundary

The end product of the inverse is not an individual solution but a **boundary**. Holding
the other seven coordinates at nominal and extracting the iso-Vmin = 0.625 V contour over
the (cn, pu) plane yields the compliant design region directly.

**92.8%** of this plane meets spec. More informative is the geometry of the boundary.
It exists only where **pu ≥ 4.3 mV** (33 of 70 pu rows); if pu is faster than that, any
cn in ±60 mV meets spec and there is no boundary at all. On the boundary, cn* ranges from
−59.3 to −25.1 mV.

Read this as follows. **The read process window of this cell closes only along pu.**
Once PU slows by more than about 4 mV, a lower bound appears on cn, and that bound rises
quickly as pu slows further. Where PU is fast enough, cn is a free design variable.
**Corner sign-off, seeing only four points, cannot see this structure.** Fig. 5 shows the
plane, the spec boundary, and the multistart solutions on it.

**Fig. 5.** Vmin contours over the (cn, pu) plane with the spec boundary and the
multistart convergence points.

### F. Lobe correlation and the min-statistics bias

The problem raised in Section II-D is closed here by measuring ρ_LR.

#### 1) The fab tail table

Inside the fab, **shape statistics only** were computed for nine conditions
(V_op 0.6/0.7 V, 10⁵ MC samples each) and exported; the raw samples never leave the fab.
The exported items are a five-point standardized quantile ladder, skewness, excess
kurtosis, and the observed minimum.

#### 2) Rejecting the Gaussian hypothesis

Three statistics reject normality independently, and Table X collects them.

**TABLE X. Three independent pieces of evidence against normality (9 conditions)**

| Evidence | Result | If Gaussian |
|---|---|---|
| Quantile-ladder χ² | 582–821 (5 degrees of freedom) in 9/9 conditions | ≈ 5 |
| Sign of skewness | negative in 9/9, mean **−0.292** | 0 |
| Observed min / E[min] | mean **1.18**, > 1.09 in 9/9 | 1.00 |

The third indicator is independent of the quantile fit. Against the expected minimum of
an n = 10⁵ Gaussian sample (Blom position −4.265 σ), the observed minima are 18% deeper
on average.

#### 3) Estimating ρ_LR — two paths that converge

**(a) Skewness inversion (primary estimator).** Invert Eq. (8). No MC reference table is
needed, and the closed form reproduces the fab table's `skew_ref` column to within 0.5%
(ρ = −0.25 → −0.2306 vs −0.2317; ρ = −0.50 → −0.3750 vs −0.3741). This checks the
implementation against the fab's implementation of the same model, not the model itself. The standard error of
g₁ is taken not as the Gaussian null √(6/n) = 0.00775 but as **0.00816**, simulated
directly from the min-of-two distribution (400 repetitions). By the delta method,
SE(ρ̂) = 0.013–0.016.

**(b) Quantile-ladder χ² (cross-check).** A ρ grid from −0.70 to 0 in steps of 0.025 is
fitted to the five-point ladder, with the minimum located by parabolic interpolation.

The two paths converge independently on **ρ_LR ≈ −0.34 … −0.37**. Pooling the nine
per-condition skewness estimates gives

    **ρ_LR = −0.371**,  between-condition SD 0.039,  random-effects SE **0.013**

from which **z_bias = +1.054 σ** and **Z_eff = 7.453**.

We quote the random-effects standard error, not the inverse-variance one. Fixed-effect
pooling of the nine per-condition SEs would give ±0.005, but that presumes the nine
conditions estimate a common ρ, and the next subsection rejects exactly that presumption
(χ² = 53.6, p = 8 × 10⁻⁹). The wider interval is also the one consistent with the two
estimation paths themselves, which differ by 0.027. In Vmin terms ±0.013 in ρ is about
±1 mV, so the conclusions below are unchanged by the substitution.

> **The fab table's `correction_sigma` column (0.94 / 1.23) must not be used as is.**
> Those values are (i) referenced to Z = 6.50 and (ii) **labels on a four-point ρ grid**
> {−0.50, −0.25, 0, +0.25} rather than estimates. That eight conditions landed on −0.25
> and one on −0.50 is an artifact of the grid spacing; a continuous fit places all nine
> between −0.30 and −0.41.

#### 4) Between-condition uniformity — the test is rejected, yet one scalar suffices

The uniformity test is **rejected**: χ² = 53.6 on 8 degrees of freedom, p = 8.1 × 10⁻⁹. ρ_LR does vary
significantly across conditions.

The **effective size of that variation is negligible**, however. Converting each
condition's ρ̂ into a z_bias spans +0.981 … +1.095 σ, which in the spec band is ±4 mV of
Vmin — less than half the forward model error of 8.35 mV. **A single scalar z_bias is
therefore sufficient**, but the justification is not "the uniformity test passed"; it is
**"the variation is smaller than the model error"**. At n = 10⁵ even practically
meaningless differences become significant, and this is such a case.

#### 5) Conversion to Vmin

The factor converting σ into mV is dz/dV_op in the spec band. The post-QC data give a
population median of **15.1 V⁻¹** for read (interquartile range 12.6–18.2) and
36.4 V⁻¹ for write
(IQR 31.9–42.3); the local slope at the read-limiting corner FSG is 14.2 V⁻¹.

A z_bias of +1.054 σ therefore converts to **70 mV** at the population median and
**74 mV** at the FSG local slope (tracing the z curve directly gives 71.7 mV — slightly
less than the linear conversion because of curvature). Table XI applies that shift to the
four corners.

**TABLE XI. Read Vmin per corner before and after correction (125 °C)**

| Corner | Naive | Corrected (Z_eff = 7.453) | Shift |
|---|---|---|---|
| FFG | 0.4731 V | 0.5279 V | +54.7 mV |
| SSG | 0.4672 | 0.5126 | +45.5 |
| SFG | < 0.4 † | 0.4230 | — |
| **FSG** | **0.5903** | **0.6619** | **+71.7** |

† Clamped at the 0.4 V floor.

#### 6) After correction, the read-limiting corner exceeds spec

At the read-limiting corner FSG, z(0.625 V) = **6.927**. For the spec decision to survive,
the corrected effective threshold must not exceed that value, so the admissible z_bias is
bounded by

    z_bias ≤ 6.927 − 6.398 = **+0.529 σ**   (equivalently ρ_LR ≥ +0.145)

The measured **+1.054 σ is twice that headroom**. The corrected FSG Vmin is therefore
0.662 V, **37 mV past spec**.

Two conditions attach to that number. The nine tail conditions carry no corner labels and
between-condition uniformity is rejected (Section V-F.4), so applying the pooled z_bias at
FSG is an **extrapolation into an unsampled quadrant**; a corner-labeled re-measurement
is what would close it, and it is item 3 of Section VIII-G. And 0.662 V is the worst value in
**corner space**, where the other seven axes are held at nominal — Section VII-B puts at
least 39% of the margin variance on those axes, so the nine-dimensional worst case is
worse than this, and 37 mV is a lower bound on the shortfall rather than the shortfall.

**This is a result, not a failure of the method.** It means three things.

1. **Corner sign-off passed only thanks to min-statistics optimism.** The naive FSG value
   of 0.590 V leaves 35 mV of margin, but that margin comes from an assumption about the
   tail shape.
2. At the 128 Mb / 99% target this design is closed on the read side, and what is needed
   is **either a 37 mV increase in V_op or a design change that brings ρ_LR above
   +0.145** — the latter meaning a smaller local-mismatch share in the lobe difference,
   i.e. more pass-gate/pull-down area.
3. **The earlier "silicon upper-bound consistency" argument is withdrawn.** It used
   z(0.625 V) = 8.06 at FSG to set a bound z_bias ≤ +1.56 σ and claimed the measurement
   sat at 74% of it; after QC the value is 6.927. More fundamentally the
   argument was **circular**: corner simulation is the very source of the naive z being
   corrected, so it cannot bound the correction. An independent check requires actual
   silicon Vmin measurement, which this study does not have (Section VIII-A).

Fig. 6 shows the two estimates side by side and the shift the correction imposes on the
corners.

**Fig. 6.** (a) ρ_LR from the two estimation paths; (b) the shift the correction imposes
on the corner Vmin values.

#### 7) What was not measured

- **Write ρ_LR.** The left and right terms are separate MC outputs, so a direct
  correlation measurement is possible in principle, but the nine-dimensional write batch
  contains only `vtrip_avg`/`vtrip_std`. The write-limiting corner SFG already sits at
  0.5924 V, touching spec, so **the value of the write ρ_LR decides pass or fail
  directly. This is the highest-priority additional measurement.**
- **A corner-labeled re-measurement.** The nine conditions were run without corner
  labels, so between-corner uniformity is untested.
- **Direct per-lobe statistics.** ρ_LR is inverted from the distribution shape and
  therefore presumes the min-of-two model. Recording (μ_L, σ_L, μ_R, σ_R, ρ_LR) directly
  for a few conditions would turn that premise into a verification.

### G. External validation on an independent batch

The hold-out of Section V-B came from the **same batch** as training — same generation, same
deck template, same MC settings — so it shows an upper bound on generalization. The
stronger question is what survives a move to an **independently designed batch**.

#### 1) The external batch

The Stage-B pilot batch was designed earlier and independently of the nine-dimensional
batches, and contains both metrics: 348 read conditions and 399 write conditions. It
sweeps only (cn, sk, pu) and fixes the six length/multiplier axes exactly at nominal, so
every condition lies on a three-dimensional subspace of the nine-dimensional space. The
script asserts three things: **inside the training box** (not extrapolation), **no
leakage** (coincidence with the 1,700 training coordinates is 0/348 for read and 0/399
for write), and **no retraining** (the Section V-B checkpoints are evaluated as they are).

Whether the two batches measure the same physical quantity is checked separately. The
coefficients of μ(V_op) regressed on (cn, sk, pu) agree to within 0.7% — at 0.6 V for
write, (187.04, −1.095, −1.746, +0.638) in 9-D against (187.59, −1.088, −1.744, +0.637)
in the pilot. **The pilot calls the metric BWRM and the 9-D batch calls it V_trip, but it
is the same quantity.**

#### 2) Self-consistency audit of the pilot batch

Stage-B is a **working file, not final raw data**. Compared with its backup, nine cells
have already been corrected by hand — six decimal-point errors, and three values of one
condition **shifted by one row**. We audit on the assumption that defects remain.

The criterion **must be independent of the surrogate**, otherwise it becomes circular —
blaming the data wherever the model is wrong. At each voltage we fit a quadratic surface
to the pilot batch's **own** μ(cn, sk, pu) and flag conditions whose mean residual exceeds
five times the robust SD. This flags **13/348 (3.7%)** for read and **8/399 (2.0%)** for
write (robust SD 1.00 / 0.93 mV; worst mean residual −54.4 / −35.4 mV).

Two independent confirmations follow. First, both sheets accidentally contain a duplicated
condition; the difference between the two repeats is max |Δμ| = 0.34 mV / ΔVmin = 1.09 mV
for read and 0.70 / 0.64 mV for write — the flagged deviations are tens to hundreds of
times this **repeatability floor**. Second, the 13 read conditions flagged this way
contain **all five** of the largest Vmin errors: two independent criteria point at the
same conditions. No correction was applied — that requires the original decks (O-06).

#### 3) Results

Table XII gives the read batch and Table XIII the write batch, each with and without the
conditions the batch's own consistency audit flags.

**TABLE XII. External validation — read (all five levels inside the training range)**

| Metric | All (348) | 13 defects excluded (335) | In-batch hold-out |
|---|---|---|---|
| μ RMSE / R² | 5.043 mV / 0.9855 | **1.756 / 0.9982** | 2.502 / 0.9965 |
| σ RMSE / R² | 0.148 mV / 0.695 | **0.146 / 0.707** | 0.256 / 0.9798 |
| z RMSE | 0.373 | **0.137** | — |
| Vmin RMSE | 21.39 mV (296) | **4.26 mV** (283) | 8.35 mV (243) |
| \|error\| P50/P90/max | 3.33 / 6.54 / 250.6 | **3.21 / 6.12 / 17.56** | 3.36 / 10.69 / 53.78 |

**TABLE XIII. External validation — write (scored on the trained range 0.4–0.7 V)**

| Metric | All (399) | 8 defects excluded (391) | In-batch hold-out |
|---|---|---|---|
| μ RMSE / R² | 4.304 mV / 0.9961 | **2.077 / 0.9991** | 2.171 / 0.9989 |
| σ RMSE / R² | 1.786 mV / 0.564 | **1.783 / 0.564** | 2.041 / 0.7318 |
| z RMSE | 0.674 | **0.644** | — |
| Vmin RMSE | 14.42 mV (312) | **13.63 mV** (305) | 14.45 mV (228) |
| \|error\| P50/P90/max | 9.32 / 23.81 / 54.40 | **9.28 / 22.71 / 43.67** | 9.81 / 21.47 / 53.06 |

On censoring, read shows a floor clamp of 50 reference against 49 predicted — **one
disagreement** — and 2/2 agreement above the ceiling. Write shows 75 reference against
66 predicted, with **33 disagreements (8.3%)**.

#### 4) The two modes say different things

**Read — with defects excluded, the external batch beats the in-batch hold-out**
(4.26 vs 8.35 mV). This is not only an absence of overfitting; **the plane is easier**.
The pilot plane fixes the six length/multiplier axes at nominal, and those axes are
precisely what creates the condition-to-condition spread of σ (the pilot's σ is nearly
constant at 13.4 ± 0.27 mV across all conditions). With the denominator of z = μ/σ
effectively fixed, σ RMSE falls from 0.256 to 0.146 mV, z RMSE from 0.373 to 0.137, and
the Vmin error follows. The representative figure for the full nine-dimensional window
remains the **8.35 mV** of Section V-B. **This is also an independent prediction that the
variance decomposition of Section VII-B will name the length/multiplier axes as the main
contributors to σ — the two sections cross-check each other.**

**Write — external and in-batch are nearly identical** (13.63 vs 14.45 mV). The plane does
not get easier, because the write bottleneck is σ and the write σ does not shrink when
the length/multiplier axes are fixed.

This yields **an independent answer to the σ transcription question raised in
Section V-B**. The nine-dimensional write batch has 69.3% of its σ values rounded to
integers; the pilot has **0.9%** — effectively no rounding, hence a much cleaner
reference. Against that clean reference the σ RMSE is still 1.78 mV, so **rounding is
part of the cause of the write σ error but not all of it.** The remainder is a genuine
limitation of the model. The 33 write censoring disagreements (against one for read) are
the most direct evidence of the same root cause: near the 0.4 V floor the z curve is not
steep, so a σ error flips the clamp decision outright.

#### 5) Voltage extrapolation — write at 0.8 V

The nine-dimensional write batch has 0/2000 entries at 0.8 V, so the model was trained
only over 0.4–0.7 V. The pilot batch has 400 rows at 0.8 V, giving a direct check of
extrapolation **one level outside the training range**.

μ RMSE **7.55 mV**, μ bias **−6.45 mV**, R² 0.969, σ RMSE 1.19 mV, z RMSE 0.854. Most of
the error is **systematic bias**: the model consistently underestimates the write margin
at 0.8 V. Against the interpolation-range μ RMSE of 2.08 mV this is 3.6×. Voltage-axis
extrapolation produces bias even one level out, and that fact constrains the grid
reduction argument of Section VI-A.

---

## VI. Simulation Budget Reduction

The campaign cost is a product of three factors.

    cost = (number of voltage levels) × (number of conditions) × (MC samples per condition)

We cut each factor in turn and measure what is lost. All three experiments are scored on
**the same 300-condition hold-out as Section V-B**, so the curves are mutually comparable,
and no experiment touches the hold-out — only the training budget is reduced.

### A. Voltage levels

#### 1) The spec decision cannot see the top level, by construction

Since the spec voltage 0.625 V lies inside [0.6, 0.7] V, z(0.625 V) is a linear
interpolation of those two points. The 0.8 V sample **cannot participate** in the
decision — this is the structure of the interpolation formula, not an empirical
approximation. Comparing z(0.625 V) from the full five-level grid against the same value
from the 0.6/0.7 pair alone over all 2,000 conditions gives max |Δz| = **1.78 × 10⁻¹⁵**,
machine epsilon. **If the decision is the only deliverable, two levels suffice and 60%
can be removed.** That is the upper bound; the rest of this section asks whether it can
actually be taken.

#### 2) But Vmin contours do use the top level — and the correction increases that use

Vmin is the crossing z(V) = Z_t, so each condition needs a **bracket** around its own
crossing. We examine both before (Z_t = 6.398) and after (Z_eff = 7.453) correction, and
Table XIV gives the resulting distribution.

**TABLE XIV. Distribution of crossing brackets.** The write Z_eff column applies the
read-measured z_bias; write ρ_LR is unmeasured (Section V-F.7).

| Read (2,000 conditions, 0.4–0.8) | Z_t = 6.398 | Z_eff = 7.453 |
|---|---|---|
| Floor clamp | 16.4% | 6.8% |
| [0.4,0.5] / [0.5,0.6] / [0.6,0.7] | 32.0 / 29.9 / 14.4% | 25.8 / 29.0 / 20.2% |
| **[0.7,0.8]** ← conditions that use 0.8 V | **3.8%** | **7.5%** |
| Above ceiling (> 0.8 V) | 3.5% | **10.8%** |

| Write (1,972 conditions, 0.4–0.7) | Z_t = 6.398 | Z_eff = 7.453 |
|---|---|---|
| Floor clamp | 22.4% | 14.8% |
| **[0.4,0.5]** ← conditions that use 0.4 V | **8.8%** | **4.9%** |
| [0.5,0.6] / [0.6,0.7] | 46.2 / 21.5% | 40.6 / 36.3% |
| Above ceiling (> 0.7 V) | 1.1% | **3.5%** |

> **The lobe correction changes the voltage-budget argument.** A higher effective
> threshold pushes crossings up the voltage axis. The read conditions that need 0.8 V grow
> from 3.8% to 7.5%, and those beyond the ceiling from 3.5% to 10.8%: after correction
> **18.3%** of the population sits near or above 0.8 V. "Removing 0.8 V is lossless" is
> true **only for the decision**; it is false when the contour is the deliverable.

#### 3) Which level can be removed differs by mode

The 0.6/0.7 bracket supports the spec decision and cannot be removed in either mode (the
script asserts this). That leaves exactly one candidate per mode: **0.8 V** (top) for read
and **0.4 V** (bottom) for write, since the write grid already ends at 0.7 V.

Removing a level shrinks not only the scoring grid but **the training data**. We therefore
retrained on the reduced grid and compared three things: the reduced model on the reduced
grid (what a four-level campaign would actually deliver), the original model on the
reduced grid (isolating the grid effect), and the reduced model at the removed level
(extrapolation bias).

Two cautions when reading the numbers. First, **μ RMSE cannot be compared across different
scoring grids** — the 0.8 V row has the largest μ and is the hardest, so dropping it moves
μ RMSE from 2.502 to 1.182 mV because the problem got easier, not because the model got
better. Second, each fit here is a single run, so **differences of a few mV are not
distinguishable from fit-to-fit noise**. Only conclusions that survive both cautions are
stated:

1. **For read, the 0.8 V level contributes almost nothing to training.** On the same
   reduced grid the reduced model gives μ = 1.218 mV against 1.182 mV for the original —
   1,700 simulations at 0.8 V buy **0.04 mV**.
2. **The contour nevertheless survives.** Scoring the reduced model on the full grid gives
   a Vmin RMSE of **6.99 mV** over 244 conditions, equal to or better than the baseline
   (8.35 mV over 243). Without simulating 0.8 V at all, the surrogate fills that level in
   with a **bias of −0.18 mV**. For read, **the 20% reduction is effectively lossless.**
3. **Write is different: removing 0.4 V causes a structural loss** — hold-out censored
   conditions grow from 69 to **90** (+21 of 297, 7%), and for those Vmin cannot be
   produced at all. This matches the population prediction (floor clamp 14.8 → 19.7%),
   and it is grid geometry, not fit noise.
4. **The write σ error is concentrated at 0.4 V.** The same original model has σ RMSE
   2.041 mV over all four levels but 1.336 mV over 0.5–0.7 alone.

**Voltage extrapolation bends with opposite signs at the two ends.** Three observations
form one picture: write 0.7 → 0.8 V, **−6.45 mV** (margin underestimated); write
0.5 → 0.4 V, **+5.66 mV** (overestimated); read 0.7 → 0.8 V, −0.18 mV (no bias). This is
the textbook behavior of a GP reverting to the mean outside its training range and
**compressing the slope of μ(V_op)**. The read bias is essentially zero because the read
dz/dV_op of 15 V⁻¹ is gentler than the write 36 V⁻¹, so the absolute compression is smaller.
**The decision to trim a grid end is conditional on that mode's slope.**

### B. Number of conditions

Training conditions are reduced along nested subsets and scored on the same hold-out.
Simulation cost is **linear** in the condition count while exact GP training is roughly
cubic — the fit times show it. Table XV gives the result.

**TABLE XV. Effect of the training condition count (read)**

| Conditions | Training rows | GP fit | μ RMSE | σ RMSE | **Vmin RMSE** | P90 |
|---|---|---|---|---|---|---|
| 100 | 500 | 22 s | 3.623 mV | 0.640 mV | 17.32 mV | 27.75 |
| 200 | 1,000 | 55 s | 2.941 | 0.421 | 12.34 | 18.74 |
| **400** | 2,000 | 152 s | 2.715 | 0.337 | **8.78** | 13.26 |
| 800 | 4,000 | 645 s | 2.556 | 0.286 | 7.87 | 11.41 |
| 1,200 | 6,000 | 1,455 s | 2.528 | 0.259 | 9.08 | 12.50 |
| 1,700 | 8,500 | (baseline) | 2.502 | 0.256 | 8.35 | 10.69 |

**μ and σ improve monotonically, but Vmin alone breaks monotonicity above 400**
(7.87 → 9.08 → 8.35). Since model quality itself is monotone, this fluctuation is noise in
the Vmin metric — a few conditions whose crossing sits near a grid boundary flip.
**One draw cannot support "800 is better than 1,700."** The replication over further
draws was not run, so every row here carries the fit-to-fit spread of a single draw and
differences of a few mV are unresolved.

Subject to that, the knee is at **400 conditions**. Going from 1,700 to 400 removes
**76%** of the simulation volume and moves the Vmin RMSE from 8.35 to 8.78 mV. That
0.4 mV is below what a single draw can resolve, and below the 1.09 mV batch repeatability
floor of Section V-G — though that floor is a per-condition repeatability and not a bound on
the sampling error of an RMSE over 243 conditions, so it is an indication, not a proof.
At 100–200 conditions the error clearly collapses to 12–17 mV, so **the reduction has a
floor.**

### C. MC samples per condition

The actual campaign ran 5,000 samples per condition and no shallower data exists. Instead
we **reproduce the situation by adding the extra sampling noise that a label would have
carried at n′ < 5,000**. Since Var(μ̂) = σ²/n, we add independent noise of
σ²(1/n′ − 1/5000) to the μ labels and σ²(1/2n′ − 1/10000) to σ̂, and re-supply y_noise at
n′ to the noise-aware GP. The hold-out labels are untouched. Table XVI gives the result.

**TABLE XVI. Effect of MC depth (read)**

| n′ | μ RMSE | μ R² | σ RMSE | **Vmin RMSE** | P90 |
|---|---|---|---|---|---|
| **500** | 2.489 mV | 0.9965 | 0.265 mV | 7.63 mV | 10.97 |
| 1,000 | 2.482 | 0.9965 | 0.252 | 8.59 | 11.65 |
| 2,500 | 2.486 | 0.9965 | 0.253 | 8.71 | 11.64 |
| 5,000 (as run) | 2.502 | 0.9965 | 0.256 | 8.35 | 10.69 |

**The curve is flat.** The full span of μ RMSE is **0.02 mV** and the four R² values agree
to four decimals. The 7.63–8.71 mV fluctuation in Vmin is the same size as the
fit-to-fit noise band identified in Section VI-B. **Cutting the MC depth tenfold, from 5,000
to 500 samples per condition, produces no measurable loss.**

The reason: label noise degrades the precision of one condition's μ and σ, but what the GP
uses is the **spatial structure across 1,700 conditions**. Neighbouring conditions average
one another, and the noise-aware likelihood automatically downweights noisy points. At
n′ = 500 the standard error of μ̂ is σ/√500 ≈ 0.6 mV, far below the 2.5 mV μ RMSE — label
noise was never the dominant term in the error budget.

**Three limitations.** (i) n′ > 5,000 cannot be emulated, so this section answers only
"how far can it be cut". (ii) The emulation **reproduces noise but not the estimator** —
the sample bias of σ̂, tail-shape distortion, and convergence failures are absent.
(iii) The hold-out labels carry their own 5,000-sample noise, which floors every curve.

### D. Putting them together — multiplication is an assumption, not a result

Each of the three sections cut **one factor** and left the other two at full budget.
Whether the losses multiply, add, or explode when all three are cut at once is not
answered by those experiments. One worsening mechanism is clearly present: **with only
400 conditions, each label has fewer neighbors to average against, so the n′ = 500 noise
bites harder than it did at 1,700 conditions.** The flatness of Section VI-C is a result
obtained with 1,700 neighbors. So we ran the combined experiment directly, and Table XVII
reports it.

**TABLE XVII. Combined reduction (400 conditions × reduced levels × 500 MC, same hold-out)**

| | Read | Write |
|---|---|---|
| Voltage levels | 5 → 4 (0.8 V removed) | 4 kept (removing 0.4 V is a structural loss) |
| Training rows / budget ratio | 1,600 / 0.0188 (**53×**) | 1,596 / 0.0235 (**42.5×**) |
| GP fit | 114 s | 127 s |
| μ RMSE (full grid) | 3.425 mV | 2.822 mV |
| **Vmin RMSE (full grid)** | **10.95 mV** (245 cond.) | **15.83 mV** (228 cond.) |
| Baseline | 8.35 mV (243) | 14.45 mV (228) |
| **Degradation** | **+2.6 mV** | **+1.4 mV** |

Placing the read result next to what the single-factor experiments predict makes the
mismatch plain.

| What was cut | Vmin RMSE | vs. baseline |
|---|---|---|
| Voltage only (0.8 V removed) | 6.99 mV | −1.4 |
| Conditions only (400) | 8.78 | +0.4 |
| MC only (500) | 7.63 | −0.7 |
| **Naive sum of the three deltas** | **≈ 6.7 mV** | **−1.7** |
| **All three together (run directly)** | **10.95 mV** | **+2.6** |

**The single-factor experiments predict no degradation at all.** Their deltas sum to
−1.7 mV, and each one on its own lies inside the ±1 mV fit-noise band of Section VI-B. The
combined cut degrades the error by **+2.6 mV**, which is outside that band. We report the
**4.3 mV gap** between the naive prediction and the combined run rather than a ratio,
because the denominator is indistinguishable from zero. μ moves the same way (2.489–2.715
for single factors, 3.425 mV combined), and μ and Vmin move together, so coincidence is
unlikely. **The mechanism is the one predicted.**

The smaller write degradation (+1.4 vs +2.6 mV) follows from not removing a voltage level
there, and is consistent with the write error budget being dominated by σ and therefore
less sensitive to training-budget cuts.

> **Each subsection here is a Pareto curve, not an assembly part.** The inference "20%
> off the voltage axis, 76% off conditions and 90% off MC, each lossless, therefore 53×
> for free" is **refuted** by this data. The 53× remains achievable, but its price is
> **Vmin RMSE 8.35 → 10.95 mV**. We report it as a Pareto point with a stated price, not
> as lossless.

Fig. 7 collects the three single-factor curves and the combined point.

**Fig. 7.** Budget-reduction Pareto — (a) conditions, (b) MC depth, (c) single factor
versus all three.

### E. What must be excluded from the reduction

**The tail-diagnosis budget is not in the calculation above and is not a candidate for
reduction.** The ρ_LR measurement of Section V-F required **10⁵** samples per condition
(nine conditions). Five hundred samples suffice to estimate z but not to see the
**shape** of the distribution — a tail fit needs the observed minimum near −4.3 σ, whereas
500 samples reach only about −3.2 σ. A campaign must be designed as a **two-tier
structure: shallow sampling for most conditions plus very deep sampling for a few.**

As a side effect, **the training cost falls too.** Simulation cost is linear in the
condition count but exact GP training is roughly cubic — 1,455 s at 1,200 conditions
against 152 s at 400, i.e. a 3× reduction in conditions makes training **9.6×** faster.
Reducing the condition count is the only factor that cuts both costs at once.

---

## VII. Sensitivity

Three questions are asked here, in order of how much they cost. Which axes did the GP
have to bend to fit? Which axes actually move the sign-off margin? And how far can the
NMOS/PMOS threshold skew — an axis no corner contains — drift before the margin is lost?
The first answer is free and turns out to be nearly useless; the second costs 45,056
surrogate evaluations and no new simulation; the third is what a designer asks for.

Nothing in this section refits. Both trained models are loaded from the checkpoints of
Section V-B.

### A. Fitted lengthscales

ARD gives one lengthscale per input, learned from the data, so it is tempting to read the
fitted values as a sensitivity ranking. Since inputs are standardized over the training
box, the values are comparable across axes, and relevance can be defined as the
normalized inverse lengthscale λ⁻¹/Σλ⁻¹.

For the read μ kernel the nine device lengthscales span 7.41 (cn, the shortest) to 8.41
(l_sk), which is a relevance spread of 0.108–0.123 against the 0.111 an axis would get if
all nine were equal. The supply axis is the one clear signal: λ_Vop = **4.64**, far
shorter than any device axis, which is the physical-consistency check already reported in
Section V-C. The write model behaves the same way (device axes 6.71–8.82, λ_Vop = 4.00).

The σ kernel is flatter still: **all nine device lengthscales fall inside 7.83–7.92**, a
spread of about 1%. Read literally, the fit says no process axis matters more than any
other for σ. Section VII-C shows that this reading is wrong.

### B. Variance decomposition

**What is decomposed, and why it is not Vmin.** Sobol indices [21] partition the variance
of a scalar output under a stated input distribution — here a uniform prior over the
training box. The output is z at the spec voltage, not Vmin. Vmin is undefined wherever
z never reaches the threshold inside the voltage grid, and discarding those samples would
break the pairing that the Saltelli estimator depends on. Writing V_T0 = 0.625 V for the
time-zero spec voltage of Table I, z(V_T0) is finite everywhere,
is monotone in the sign-off margin, and is the quantity the T0 decision actually reads.
μ(V_T0) and σ(V_T0) are decomposed as well, because σ is the write bottleneck of
Section V-B and the subject of an open prediction from Section V-G.

**Estimation.** S1 uses the Saltelli 2010 estimator [22] and S_T the Jansen estimator [23],
on a base sample of N = 4,096 (45,056 surrogate evaluations per mode). Both are sample
means, so their sampling error is what separates a small index from zero; we resample the
Saltelli rows 500 times and report 95% bootstrap intervals. Resampling costs no further
GP evaluations.

The uniform prior is a stated choice, not the process distribution. It weights every point
of the qualification box equally, while the shipped population concentrates near nominal.
The shares below therefore answer "across the window we are signing off", not "in the
population we will ship"; a population-weighted decomposition would need the fab's joint
distribution over the nine axes, which this study does not have.

**TABLE XVIII. Total-order Sobol indices over the training box (N = 4,096; 95% bootstrap
interval on the read z column)**

| Axis | ARD rel. (read) | S_T of z, read | S_T of z, write | S_T of σ, read | S_T of σ, write |
|---|---|---|---|---|---|
| cn (NMOS Vth) | 0.123 | **0.419** [0.397, 0.441] | **0.421** | 0.001 | 0.006 |
| l_com (common local σ) | 0.109 | **0.276** [0.259, 0.293] | 0.170 | **0.847** | **0.722** |
| pu (PMOS Vth) | 0.112 | 0.188 [0.178, 0.199] | 0.168 | 0.007 | 0.017 |
| sk (Vth skew) | 0.111 | 0.067 [0.064, 0.071] | 0.097 | 0.001 | 0.011 |
| lpu (pull-up local σ) | 0.109 | 0.043 [0.040, 0.046] | 0.060 | 0.137 | 0.193 |
| m_com (common multiplier) | 0.110 | 0.015 [0.014, 0.017] | 0.032 | 0.001 | 0.013 |
| m_sk (multiplier skew) | 0.109 | 0.014 [0.014, 0.015] | 0.005 | 0.002 | 0.000 |
| mpu (pull-up multiplier) | 0.109 | 0.008 [0.008, 0.009] | 0.026 | 0.000 | 0.016 |
| l_sk (local σ skew) | 0.108 | 0.001 [0.001, 0.001] | 0.008 | 0.004 | 0.031 |
| **Σ** | 1.000 | **1.031** | 0.987 | 1.000 | 1.007 |

Three results follow.

**1) Two fifths of the margin variance is invisible to corners.** A corner moves only the
two threshold axes. Their total-order indices sum to 0.61 for read (0.419 + 0.188) and
0.59 for write. Total-order indices overlap through interactions and do not partition the
variance, so those sums are an **upper bound** on the joint share of the two corner axes;
the remaining seven axes therefore carry **at least 39% (read) and 41% (write)** of the
margin variance. The overlap is small here — ΣS_T exceeds 1 by only 0.031 for read — so the
bound is close to tight. The largest single non-corner axis, l_com, carries more of the
read margin variance than pu does. This is the quantitative form of the limitation stated
in Section I-C: the gap is not a rounding effect, it is two fifths of the problem.

**2) σ is a length story, and only a length story.** The three local-σ length axes carry
**98.8% (read) and 93.8% (write)** of the σ variance, and l_com alone carries 85% and
72%. The three multiplier axes together carry 0.3% and 2.9%. Section V-G predicted, from
the pilot batch alone, that the length and multiplier axes would be named here as the
main contributors to σ. That pilot observation froze the length and multiplier axes
**together**, so on its own it established only that the six frozen axes carry the σ
spread; the decomposition resolves that lumped set, putting 98.8% on the three length
axes and 0.3% on the multipliers.

Two cautions on how far this cross-check reaches. The pilot observation is empirical and
the decomposition is not: these indices describe the **fitted surrogate** and inherit its
error, so the confirmation runs one way, from data to model, and not back. And a variance
share is not an error budget — freezing 98.8% of the read σ variance moved the read σ
RMSE only from 0.256 to 0.146 mV, so the axes that carry the variance are not
proportionally the axes that carry the model's error.

**3) The first-order indices are too noisy to interpret, and we do not.** S_T is the
better-determined of the two: no total-order interval exceeds 0.05 in the z columns or
0.07 in the σ columns, in either mode. S1 is not. The
read z column gives S1(cn) = 0.302 with an interval of [0.199, 0.416], and the nine S1
estimates sum to 0.790 while the nine S_T sum to 1.031. For a purely additive response
both sums would be 1. The S_T excess of 0.031 says interactions are small; the S1 deficit
of 0.21 is within the combined noise of nine estimates each carrying a ±0.1 interval. The
two statements cannot both be sharp, so we rank on S_T and quote no interaction fraction.

The write z column carries its own warning: its S_T sum is **0.987**, below the arithmetic
floor of 1 that holds for independent inputs. The shortfall of 0.013 is the scale of the
estimator noise in that column, and it is the same order as the interval widths above.

> The σ column shows the same problem in its clearest form: S1(l_com) = 1.020 exceeds its
> own S_T of 0.847, which exact arithmetic forbids. The bootstrap interval [0.706, 1.365]
> explains it — when one axis carries nearly all of the variance, the S1 estimator's noise
> is the size of the index itself. Without the interval, that 1.020 would have been
> reported as a result. It is not one.

**Fig. 8.** Total-order Sobol indices with bootstrap intervals for (a) z(V_T0) and
(b) σ(V_T0), read and write; (c) the ARD relevance of the same axes, in the same order.

### C. A fitted lengthscale is not a sensitivity

Panels (a) and (c) of Fig. 8 rank the same nine axes with the same model. They disagree.

ARD relevance spans a factor of 1.13 across the nine axes; S_T spans a factor of 400. The
order disagrees too: by ARD relevance l_com is indistinguishable from three other axes
(all 0.109 at the precision of Table XVIII), yet it ranks **second of nine** by variance
share. The σ kernel is the extreme case — nine lengthscales within about 1% of each
other, while one of those axes carries 85% of the σ variance.

The reason is that the two quantities answer different questions. A lengthscale measures
how quickly the function *wiggles* along an axis: it responds to curvature. A Sobol index
measures how far the output *moves* when the axis is varied over its range. A dependence
that is strong, smooth and nearly linear — which is what l_com does to σ — earns a long
lengthscale and a large variance share at the same time. The two rankings coincide only
when the axes have comparable curvature, and here they do not.

What survives from Section VII-A is narrower than a ranking. λ_Vop = 4.64 is genuinely the
shortest lengthscale in the model, and the supply axis is genuinely the most curved one.
The direction of the pass-gate check in Section V-C also holds up: ARD puts λ_cn below λ_pu,
and Sobol puts S_T(cn) above S_T(pu). Directions can be read off a fitted kernel;
rankings and magnitudes cannot. This is the caution referred to in Appendix A, and it
applies to any GP surrogate whose lengthscales are reported as a sensitivity result.

### D. Skew tolerance

Section VII-B measured how much the threshold skew sk contributes on average. A designer
asks the sharper question: with the rest of the process fixed, how far can sk drift
before the T0 margin is gone?

We sweep sk across its full training range (±20 mV) at each of 625 cells of the (cn, pu)
plane, holding the other six axes at nominal, and record the fraction of that range which
keeps z(V_T0) at or above the threshold. Both thresholds are reported, because the lobe
correction of Section V-F raises the bar the margin must clear. Table XIX summarizes the
result and Fig. 9 maps it.

**TABLE XIX. Skew tolerance over the (cn, pu) plane (625 cells, sk swept ±20 mV).**
**The write Z_eff columns apply the read-measured z_bias, which is an assumption: write
ρ_LR has not been measured (Section V-F.7).**

| | Read, Z_t | Read, Z_eff | Write, Z_t | Write, Z_eff |
|---|---|---|---|---|
| Cells with some passing skew | 97.3% | 90.9% | 100% | 97.0% |
| Cells passing at **every** skew | **82.7%** | **67.0%** | **77.6%** | **62.9%** |
| Passing width, median | 40.0 mV | 40.0 mV | 40.0 mV | 40.0 mV |
| Passing width, IQR | 40.0–40.0 | 38.5–40.0 | 40.0–40.0 | 30.6–40.0 |

**Tolerance is close to binary.** The median passing width is the full 40 mV in every
column: a cell that has any margin at all almost always tolerates the entire skew range.
What the correction removes is whole cells, not slices of the axis — the fully tolerant
fraction falls from 82.7% to 67.0% for read and from 77.6% to 62.9% for write, while
the median width does not move. About one sixth of the plane's skew freedom is the price
of the correction for read. The write figure is what the same correction would cost if
z_bias transfers between modes; since write ρ_LR is unmeasured (Section V-F.7), that column
is a projection, not a measurement.

**Where it closes is where the paper has been pointing all along.** Fig. 9 shows the
tolerance collapsing in the fast-NMOS / slow-PMOS region — the FSG quadrant that Section V-D
identifies as the read-limiting corner and Section V-F pushes past spec. The write mode keeps
more cells (97.0% retain some margin at Z_eff) but loses more inside them: its IQR falls
to 30.6–40.0 mV, consistent with the larger sk variance share in Table XVIII (0.097 versus
0.067).

**Fig. 9.** Passing skew width over the (cn, pu) plane, read mode, (a) at Z_t = 6.398 and
(b) at Z_eff = 7.453. The contour marks the boundary of full tolerance.

Two limits on this number. It is a one-axis tolerance with the other six non-threshold
axes at nominal, and Table XVIII says l_com moves the read margin more than sk does, so a
joint tolerance region over several axes would be tighter than this one. And the map is a
surrogate prediction: cells within roughly one model error (8.35 mV in Vmin, Section V-B) of
the boundary should be read as boundary cells, not as decided ones.


---

## VIII. Discussion and Limitations

### A. The dominant uncertainty is in the metric, not the model

Placing this paper's numbers side by side makes the priority clear.

| Error source | Size (in Vmin) |
|---|---|
| Batch repeatability floor (same condition twice) | 1.1 mV |
| Surrogate regression error (read hold-out) | 8.4 mV |
| Surrogate regression error (read, independent corners) | 9.3 mV |
| Price of a 53× budget reduction | +2.6 mV |
| **Min-statistics metric bias** | **70 mV** |

**The metric bias exceeds every other error source by an order of magnitude** — and is
three times all of them combined. Effort
spent making the model more accurate ranks below it. That is why a paper about surrogate
methodology places Section V-F where it does — as the evidence that underwrites the accuracy
of the method.

The status of the bias is as follows. It is **estimated from data rather than assumed**:
two estimators built on different moments of the same exported statistics converge on
ρ_LR ≈ −0.34 … −0.37, and normality is rejected by three independent lines of evidence.
Their agreement tests the estimator, not the min-of-two-Gaussians premise that both share
(Section V-F.7). The **correction is post-processing**, Eqs. (6)–(7), requiring no re-simulation. But
it is **not verified against silicon.** The earlier claim that inverted an upper bound
from corner simulation and reported the measurement as "inside the bound" was circular and
has been withdrawn: corner simulation is the very source of the naive z being corrected,
so it cannot serve as independent evidence for the size of the correction. An independent
check requires an actual silicon Vmin measurement, which this study does not have.

### B. The limit of write σ prediction — the diagnosis is only half confirmed

Section V-B attributed the write σ error (RMSE 2.04 mV, R² 0.732) to a wide
condition-to-condition spread plus the 69% integer rounding of transcribed σ values.
Section V-G tested that diagnosis **independently**: the pilot batch, with only 0.9%
rounding, is a clean reference, and even against it the σ RMSE remains 1.78 mV.

**Rounding is therefore part of the cause but not all of it**; the remainder is a genuine
limitation of the model. The practical consequence is the 33 write censoring
disagreements (one for read), and Section VI-A localized much of the write σ error to the
lowest voltage (0.4 V). Three observations point the same way — the write σ varies
strongly across conditions at low supply and the current model does not track it.
**There are two improvement paths:** ask the fab to transcribe σ at full decimal
resolution (immediately available, partial effect), and increase the condition density in
the low-voltage region.

Section VII-B supplies the axis-level detail that was missing from both: the σ **variance**
is carried almost entirely by the local-σ length axes — 85% by l_com alone for read, 72%
for write — while the three multiplier axes together account for under 3%.

That is a statement about where σ varies, not about where the model's σ **error** lives,
and the two are not the same. Section V-G.4 is the direct test: the pilot batch freezes all
six length and multiplier axes at nominal, removing most of the σ variance, and the write
σ RMSE still only moves from 2.04 to 1.78 mV. So placing added conditions along the
local-σ length axes is a **hypothesis** worth testing for read, where the same freeze cut
σ RMSE from 0.256 to 0.146 mV, and one the pilot batch has already answered negatively for
write. For write the σ error behaves like a floor. Locating it needs a different
measurement — regressing the hold-out σ residual on the nine coordinates, which costs no
simulation — and that is the next step this section points to.

### C. Combined decisions across the two modes — a prediction on top of a prediction

Characterizing read and write only at their own worst temperature is a deliberate cost
decision (Section III-A), and its price appears here. Because the nine-dimensional
coordinates of the two batches do not intersect, the per-condition combined
Vmin = max(read, write) **cannot be verified against the reference simulation in the
2,000-condition batches.**

The distinction must be kept. **What is possible**: at the four PDK corners both
reference runs exist, so the combined decision can be checked directly, and Table VIII gives
those values. The result that the two worst corners are each other's censored corner and
lie 2 mV apart is a reference-simulation result. **What is not possible**: a combined contour over the full
2,000-condition window. Each surrogate could be evaluated at the other's coordinates to
*propose* a combined decision, but that is a prediction built on an unvalidated
prediction, and this paper does not report that surface as a result.

There is exactly one way to remove the limitation — **acquire even a small set of
condition coordinates shared by both modes.** A few tens of conditions where the combined
decision matters would suffice, and this is a design item for the next campaign.

### D. What the Gaussian process is and is not doing here

Section V-B.3 scored a 66-term quadratic response surface against the GP and found it at
least as accurate — better for read on both the hold-out and the independent corners. The
honest reading is that **this window is smooth enough that the regressor is not the
difficulty**; the difficulty is the metric (Section VIII-A), the censoring, and the labels.
Three consequences follow.

First, the paper's results are portable: every downstream step consumes only μ and σ, so
a flow that prefers least squares to a GP keeps the physics layer, the inverse, the budget
curves and the ρ_LR correction unchanged.

Second, the case for the GP here rests on two properties this study never puts to work —
a per-point predictive variance, which no result in the paper consumes, and a noise-aware
likelihood, which cannot show its value on a dataset where every condition carries the
same 5,000 samples. A campaign with genuinely heterogeneous depth, which Section VI-E
argues for on other grounds, is also what would make that likelihood earn its place.

Third, the budget conclusions of Section VI are GP-specific. A 66-coefficient surface
should saturate at far fewer than 400 conditions, so the knee reported there is a property
of the model as much as of the problem. We did not measure the quadratic's knee.

### E. Scope

The results concern a single technology node and a single cell topology. The multiplier
spill band that appears when the common component approaches the range edge sits at the
margin of compact-model calibration, and predictions there should be read conservatively.
The voltage-level reduction of Section VI-A is conditional on the spec of Table I; if the
IR-drop budget changes so that the spec leaves the grid, it must be revisited.

The scope of the inverse must also be stated. What is validated is the **axis-wise
one-dimensional solution** — it solves the query "fix the rest, solve one axis" to machine
precision and traces the boundary curve of a two-dimensional plane exactly. The ability to
obtain the full nine-dimensional hypersurface with several axes free at once **is not
claimed.** Gradient descent through the differentiable composite function is the natural
extension, but it was not validated in this study, and we did not leave an unvalidated
method in the methodology section.

The PDK is proprietary, so absolute values are not externally reproducible. What is
reproducible is the procedure and the relative conclusions; Appendix C specifies both.

### F. Recommendations

Only items that a campaign design can act on directly.

1. **The spec sets the voltage levels.** The bracket around the spec point cannot be
   removed in either mode. Trimming a grid end is conditional on that mode's dz/dV_op
   (Section VI-A); in a steep mode, one level of extrapolation produces 5–6 mV of systematic
   bias.
2. **Spend the budget on breadth of condition coverage.** Cutting MC depth tenfold
   produces no measurable loss, while cutting the condition count to 100–200 clearly
   collapses. Only reducing the condition count cuts both the simulation cost (linear) and
   the training cost (cubic). Where breadth is added, Section VII-B says where it pays: the
   local-σ length axes for σ accuracy, the threshold axes for the margin itself.
3. **Re-measure the price when cutting all three factors together.** The product of
   single-factor curves is optimistic relative to the combined run (Section VI-D).
4. **Record tail-shape information in the MC flow as standard.** The μ and σ of the
   minimum discard the shape information, and that loss makes sign-off tens of mV
   optimistic. Record at least the skewness and the lower quantiles, and preferably the
   per-lobe statistics (μ_L, σ_L, μ_R, σ_R, ρ_LR).
5. **Transcribe σ at full decimal resolution.** It costs nothing and directly improves
   write accuracy.
6. **Make the monotonicity audit a standing gate.** This single check caught 31
   transcription errors in the read batch and 12 in the write batch, and after correction
   the Vmin RMSE improved from 14.74 to 8.35 mV.

### G. Next measurements, in priority order

1. **Write ρ_LR.** The write-limiting corner SFG already touches spec, so this value
   decides pass or fail directly. The left and right terms are separate MC outputs, so
   adding the record makes it a direct correlation measurement.
2. **Silicon Vmin measurement.** The only independent check on the size of the correction.
3. **Corner-labeled tail re-measurement.** The present nine conditions carry no corner
   labels, so between-corner uniformity is untested.
4. **Conditions shared by both modes.** Required to validate the combined decision
   (Section VIII-C).
5. **Re-confirmation of the 13 flagged Stage-B pilot conditions** against the original
   decks. They look like coordinate-label misalignment, but confirming that requires the
   decks (O-06).

---

## IX. Conclusion

We built a surrogate pipeline that serves forward and inverse SRAM Vmin queries from one
fixed simulation budget, and validated it for both read and write modes on production
calibration data from an advanced FinFET node.

**Forward.** On a condition-level hold-out the Vmin RMSE is 8.35 mV for read and 14.45 mV
for write. The error does not grow on the three scorable of four PDK corners absent from
training (9.3 / 16.7 mV), and the limiting corner of each mode is identified correctly. Applied without
retraining to an independently designed pilot batch, the read Vmin RMSE is 21.4 mV over
all 348 conditions and 4.26 mV over the 283 that pass that batch's own consistency audit.
Three levels of validation return the same order of magnitude.

**Inverse.** Recovering one of nine coordinates from a reference Vmin gives an RMSE of
2.60 mV for the NMOS Vth shift and 3.20 mV for the PMOS Vth shift — smaller than the
forward error implies, with a systematic bias inside ±0.5 mV. The axis-wise solution is
exact to machine precision without an optimizer (12/12 starts, maximum residual
4.7 × 10⁻⁴ mV) and traces a planar boundary 5.7× more cheaply than a grid, returning exact
boundary points rather than interpolants. Its output shows a structure corner sign-off
cannot see: the read process window of this cell closes only along pu, and a lower bound
on cn appears once PU slows by more than 4.3 mV.

**Cost.** If the spec decision is the only deliverable, two voltage levels suffice by
construction; the training condition count can drop from 1,700 to 400 and the MC depth
from 5,000 to 500, each without measurable loss. But the losses do not multiply when the
three are combined — a 53× reduction costs +2.6 mV of Vmin RMSE, where the single-factor
deltas sum to −1.7 mV and predict no degradation at all. Reductions must be reported as Pareto points with a stated price,
not as lossless.

**Sensitivity.** A variance decomposition of the same surrogate, taken under a uniform
prior over the design ranges of Table II, puts at least 39% of the read margin variance
and 41% of the write on axes that no corner definition contains, with a single local-σ
length axis outranking the PMOS threshold shift for read. The same
decomposition resolves the σ variance — 98.8% of it sits on the three local-σ length
axes and 0.3% on the multipliers — which sharpens an observation Section V-G could only make
about the six axes as a block. The fitted ARD lengthscales, the free proxy for the same
question, rank the nine axes almost flat: a lengthscale measures curvature, not influence,
and should not be reported as a sensitivity result.

**The metric.** The last point matters most. The dominant uncertainty is in the metric,
not the model. The systematic optimism of the min-statistics z-score is set by the lobe
correlation ρ_LR, which can be measured from the shape statistics of production MC output
alone. The pooled value on which two independent paths converge,
ρ_LR = −0.371 (random-effects SE 0.013), corresponds to +1.054 σ in z and 70 mV in
Vmin — an order of
magnitude above the surrogate regression error. Correcting for it puts the read-limiting
corner FSG 37 mV past spec. Corner sign-off passed not because margin existed but because
of an assumption about the shape of the tail.

---

## Appendix A: Gaussian Process Background

A summary of the formalism for readers whose main expertise lies outside statistical
learning.

A GP defines **a distribution over functions** such that any finite set of function values
is jointly Gaussian [18]. It is specified by a mean function and a covariance kernel, the
latter encoding the assumption that nearby inputs produce correlated outputs.
Conditioning on observed data yields a posterior that returns both a predictive mean and a
predictive variance at any query point, and the variance grows away from the observations
— the property that distinguishes a GP from ordinary regression [24], [25].

The kernel lengthscale governs the distance over which correlation decays. A short
lengthscale along an axis indicates that the output changes rapidly with that input; a
long one indicates insensitivity. ARD assigns an independent lengthscale to each input
dimension and learns them all from data, which is why fitted values are often read as a
sensitivity measure. Section VII-C examines that reading critically.

A heteroscedastic likelihood generalizes the standard formulation by letting the
observation noise differ per data point. Supplying per-condition MC standard errors in
that role makes the posterior weight each condition in proportion to its statistical
reliability, with no auxiliary correction term.

## Appendix B: Reference Data QC Audit

The audit procedure applied to both batches, and its record.

**Procedure.** (1) Parse-stage typo detection — double decimal points such as `93..1`,
and merged mean/standard-deviation cells such as `182.9612.14`. (2) μ(V_op) monotonicity
check — μ must increase with supply, so violations exceeding three MC standard errors are
flagged. (3) Recovery — if a missing decade (×10, ÷10, ÷100) matches the neighbouring
voltage trend, the decade is restored; otherwise the value is replaced by a quadratic fit
through the remaining voltage points of the same condition. (4) Re-check — the script
asserts zero remaining violations.

**Record.** 31 corrections in the read batch (3 typos, 6 decade restorations, 22 quadratic
replacements) and 12 in the write batch. No cell quarantined; 10,000 of 10,000 cells used.
Before and after, for read: μ RMSE 5.44 → 2.50 mV, Vmin RMSE 14.74 → 8.35 mV.

**The independent batch.** For the Stage-B pilot, the batch's own quadratic-surface
residual criterion was used instead (Section V-G.2). The criteria differ because the pilot's
original decks are unavailable, so recovery is impossible and only **flag and exclude**
is available.

## Appendix C: Reproducibility

Condition generation is a deterministic PCG64 stream, so the tuple (stage, condition
count, seed, metric, method) reproduces the entire condition set bit for bit. Training
uses GPyTorch [26] with seed 42, 150 iterations, and a fixed-noise noise-aware
likelihood. Each result corresponds to one script and one output file, and every number in
the text traces through that correspondence table (the evidence ledger) from script to
data to output.

The PDK and the reference data are internal assets and are not released. What can be
released is the procedural specification and the relative metrics.

---

## References

[1] C. Bae, S. Pae, C.-S. Yu, K. Kim, Y. Kim, and J. Park, "SRAM stability
     design comprehending 14nm FinFET reliability," in *Proc. IEEE Int. Rel.
     Phys. Symp. (IRPS)*, 2015, pp. MY.13.1–MY.13.5,
     doi: 10.1109/IRPS.2015.7112815.

[2] A. T. Krishnan *et al.*, "SRAM cell static noise margin and V_MIN
     sensitivity to transistor degradation," in *Proc. IEEE Int. Electron
     Devices Meeting (IEDM)*, 2006, pp. 1–4, doi: 10.1109/IEDM.2006.346778.

[3] S.-M. Lim, H. Hong, S. Yu, Z. Ming, J. Park, and Y. Kim, "Effects of BTI
     during AHTOL on SRAM V_MIN," in *Proc. IEEE Int. Rel. Phys. Symp. (IRPS)*,
     2011, pp. 2D.4.1–2D.4.6, doi: 10.1109/IRPS.2011.5784460.

[4] Z. Guo, W. Sun, Z. Wang, Y. Cai, and L. Shi, "An efficient SRAM yield
     analysis method using multi-fidelity neural network," in *Proc. 2nd Int.
     Symp. Electron. Design Autom. (ISEDA)*, 2024, pp. 547–551,
     doi: 10.1109/ISEDA62518.2024.10617638.

[5] S. Yin, X. Jin, L. Shi, K. Wang, and W. W. Xing, "Efficient Bayesian yield
     analysis and optimization with active learning," in *Proc. 59th ACM/IEEE
     Design Autom. Conf. (DAC)*, 2022, pp. 1195–1200,
     doi: 10.1145/3489517.3530607.

[6] S. Yin, G. Dai, and W. W. Xing, "High-dimensional yield estimation using
     shrinkage deep features and maximization of integral entropy reduction,"
     in *Proc. 28th Asia South Pacific Design Autom. Conf. (ASP-DAC)*, 2023,
     pp. 283–289, doi: 10.1145/3566097.3567907.

[7] Y. Liu, G. Dai, and W. W. Xing, "Seeking the yield barrier:
     High-dimensional SRAM evaluation through optimal manifold," in *Proc.
     60th ACM/IEEE Design Autom. Conf. (DAC)*, 2023, pp. 1–6,
     doi: 10.1109/DAC56929.2023.10247952.

[8] A. Singhee and R. A. Rutenbar, "Why quasi-Monte Carlo is better than Monte
    Carlo or Latin hypercube sampling for statistical circuit analysis,"
    *IEEE Trans. Comput.-Aided Design Integr. Circuits Syst.*, vol. 29,
    no. 11, pp. 1763–1776, Nov. 2010.

[9] S. Kinoshita, Y. Inoue, T. Watanabe, K. Ikeda, S. Nishio, A. Teruya,
     N. Sakai, and T. Goda, "Space-filling Latin hypercube design for efficient
     Bayesian optimization with application to semiconductor development,"
     *IEEE Trans. Semicond. Manuf.*, vol. 38, no. 3, pp. 446–452, 2025,
     doi: 10.1109/TSM.2025.3574791.

[10] S. Gupta and B. H. Calhoun, "Dynamic read Vmin and yield estimation for
     nanoscale SRAMs," *IEEE Trans. Circuits Syst. I, Reg. Papers*, vol. 68,
     no. 3, pp. 1171–1182, Mar. 2021, doi: 10.1109/TCSI.2020.3044836.

[11] A. Singhee and R. A. Rutenbar, "Statistical blockade: Very fast statistical
     simulation and modeling of rare circuit events and its application to memory
     design," *IEEE Trans. Comput.-Aided Design Integr. Circuits Syst.*, vol. 28,
     no. 8, pp. 1176–1189, Aug. 2009, doi: 10.1109/TCAD.2009.2020721.

[12] R. Kanj, R. Joshi, and S. Nassif, "Mixture importance sampling and its application
     to the analysis of SRAM designs in the presence of rare failure events," in
     *Proc. 43rd Design Automation Conf. (DAC)*, 2006, pp. 69–72,
     doi: 10.1145/1146909.1146930.

[13] R. Saeidi, M. Sharifkhani, and K. Hajsadeghi, "Statistical analysis of
     read static noise margin for near/sub-threshold SRAM cell," *IEEE Trans.
     Circuits Syst. I, Reg. Papers*, vol. 61, no. 12, pp. 3386–3393, Dec. 2014,
     doi: 10.1109/TCSI.2014.2327334.

[14] N. Zheng and P. Mazumder, "Modeling and mitigation of static noise margin
     variation in subthreshold SRAM cells," *IEEE Trans. Circuits Syst. I, Reg.
     Papers*, vol. 64, no. 10, pp. 2726–2736, Oct. 2017,
     doi: 10.1109/TCSI.2017.2700818.

[15] E. Seevinck, F. J. List, and J. Lohstroh, "Static-noise margin analysis of
    MOS SRAM cells," *IEEE J. Solid-State Circuits*, vol. SC-22, no. 5,
    pp. 748–754, Oct. 1987.

[16] T. Song et al., "A 14 nm FinFET 128 Mb SRAM with V_MIN enhancement
     techniques for low-power applications," *IEEE J. Solid-State Circuits*,
     vol. 50, no. 1, pp. 158–169, Jan. 2015, doi: 10.1109/JSSC.2014.2362842.

[17] D. B. Owen, "Tables for computing bivariate normal probabilities," *Ann.
    Math. Statist.*, vol. 27, no. 4, pp. 1075–1090, Dec. 1956.

[18] C. E. Rasmussen and C. K. I. Williams, *Gaussian Processes for Machine
    Learning*. Cambridge, MA, USA: MIT Press, 2006.

[19] M. J. M. Pelgrom, A. C. J. Duinmaijer, and A. P. G. Welbers, "Matching
    properties of MOS transistors," *IEEE J. Solid-State Circuits*, vol. 24,
    no. 5, pp. 1433–1439, Oct. 1989.

[20] M. C. Kennedy and A. O'Hagan, "Predicting the output from a complex
    computer code when fast approximations are available," *Biometrika*,
    vol. 87, no. 1, pp. 1–13, Mar. 2000.

[21] I. M. Sobol', "Global sensitivity indices for nonlinear mathematical models
    and their Monte Carlo estimates," *Math. Comput. Simul.*, vol. 55,
    no. 1–3, pp. 271–280, Feb. 2001.

[22] A. Saltelli, P. Annoni, I. Azzini, F. Campolongo, M. Ratto, and
    S. Tarantola, "Variance based sensitivity analysis of model output. Design
    and estimator for the total sensitivity index," *Comput. Phys. Commun.*,
    vol. 181, no. 2, pp. 259–270, Feb. 2010.

[23] M. J. W. Jansen, "Analysis of variance designs for model output," *Comput.
    Phys. Commun.*, vol. 117, no. 1–2, pp. 35–43, Mar. 1999.

[24] R. M. Neal, *Bayesian Learning for Neural Networks*. New York, NY, USA:
     Springer, 1996.

[25] M. L. Stein, *Interpolation of Spatial Data: Some Theory for Kriging*.
     New York, NY, USA: Springer, 1999.

[26] J. R. Gardner, G. Pleiss, D. Bindel, K. Q. Weinberger, and A. G. Wilson,
     "GPyTorch: Blackbox matrix-matrix Gaussian process inference with GPU
     acceleration," in *Proc. Adv. Neural Inf. Process. Syst. (NeurIPS)*, vol. 31,
     2018, pp. 7576–7586.
