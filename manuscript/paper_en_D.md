# Forward and Inverse SRAM Vmin Estimation with an Analytic Physics Layer: Where the Margin Actually Comes From

**[Authors TBD — O-01]**
**[Affiliation TBD — O-01]**

> Internal technical report · IEEE manuscript format · draft v5.0-**D** (2026-09-06)
> **Device/process-reader edition.** The structure is that of `paper_en_C.md` (condensed,
> ~9 pages); two things differ. (1) Every tool borrowed from outside circuit design —
> Gaussian process, Sobol indices, the bootstrap, censoring — is introduced by saying what
> it was built for and why it fits this problem, assuming no statistics or machine-learning
> background (Table II). (2) The variation-axis symbols now read as device names
> (Table III); the old symbols were internal code names and the mapping is given below that
> table. No number differs from the other versions.
> Every number traces to an evidence ID in `manuscript/LEDGER.md`.
> Open before submission: title/authors/affiliation (O-01), target venue (O-05).
>
> Figures reuse the v4.0 files, with axis labels following the new symbols of Table III:
> Fig. 1 = `fig1_pipeline`, Fig. 2 = `fig3_forward`,
> Fig. 3 = `fig4_corner`, Fig. 4 = `fig5_inverse`, Fig. 5 = `fig8_sensitivity`,
> Fig. 6 = `fig6_lobe`, Fig. 7 = `fig7_cost`.

---

## Abstract

Verifying the minimum operating voltage (Vmin) of an SRAM across process variation is
expensive by Monte Carlo (MC) and structurally incomplete by corners. We present a
surrogate answering both forward and inverse Vmin queries from one fixed simulation budget:
a Gaussian process regresses the margin statistics (μ, σ) over nine process axes and the
supply, and an analytic physics layer with no trainable parameters converts them into the
yield-referenced Vmin. Keeping that layer unlearned is what makes the map invertible —
fixing eight coordinates leaves a monotone one-dimensional function, so the inverse is
solved exactly by bisection and a Vmin boundary is traced directly rather than by grid
search: 858 evaluations against 4,900 for a grid over the same plane, returning boundary
points rather than interpolants. On production calibration data from an advanced FinFET node
the hold-out Vmin RMSE is 8.35 mV for read and 14.45 mV for write, and 9.3 mV on PDK corners
absent from training with each mode's limiting corner identified correctly; inverse queries
recover a process coordinate to 2.60–3.20 mV. Beyond the numbers, three readings: the
read/write gap is not a modeling artifact but the identity δVmin ≈ Z_t (δσ/σ)/(dz/dV_op),
which reproduces the read figure to 3%; corners are incomplete in a specific way, since
their two axes move the *mean* margin while a 6.4σ target is set by the *spread*, so the
NMOS common local-σ axis outranks the PMOS threshold shift and at least 39% of the margin
variance lies off-corner; and the lobe correlation ρ_LR = −0.371, measured from MC shape
statistics alone, says local mismatch carries 2.2× the global variance in the lobe
difference — worth 70 mV of Vmin, enough to put the read-limiting corner past spec, and
closable only by about 2.9× the pass-gate/pull-down area or 37 mV more supply.

**Index Terms** — Gaussian process, inverse problem, minimum operating voltage, process
variation, sensitivity analysis, SRAM, static noise margin, surrogate model, yield
analysis.

---

## I. Introduction

SRAM dominates SoC area and yield, and its Vmin must be signed off across the whole
process-variation window. Two methods are in use, each unsatisfactory for a different
reason.

Direct MC is unaffordable: at the scale used here — 2,000 conditions per mode × 4–5 supply
levels × 5,000 MC samples — a campaign is 4–5 × 10⁷ circuit simulations, weeks to months of
wall-clock even parallelized, and the cost grows as compact models get heavier at advanced
nodes.

Corner sign-off is affordable but **structurally** incomplete, and the reason matters for
what follows. A corner is an extreme combination of exactly two axes, the NMOS and PMOS
threshold shifts, and those two axes move the *mean* of the margin distribution. But Vmin
is defined by extrapolating that distribution to a 6.4σ quantile, where the margin is set
at least as much by its *spread* — and no corner definition contains a spread axis.
Section V measures the consequence; the point here is that it follows from the corner
construction, not from how many corners one runs.

A surrogate replacing either method must be accurate at the decision over the whole window,
must take all nine variation axes as inputs so the axes no corner contains become
observable, and must be **invertible** — because the question design asks is "which process
condition meets this Vmin", not "what is the Vmin of this condition". The third requirement
dictates the architecture. Learning the map end to end would make inversion an optimization
through a black box; instead the Gaussian process (GP) learns only (μ, σ) and the
conversion to Vmin is imposed as an analytic constraint with no trainable parameters. That
constraint is monotone in the supply, so along any single axis the inverse collapses to a
one-dimensional root-find solved exactly — no optimizer, no learning rate, no tolerance
(Fig. 1).

**Fig. 1.** Pipeline overview.

Sections III and IV establish the pipeline's forward and inverse accuracy at three
increasing distances from the training distribution. Sections V and VI then use it for what
a corner flow cannot do: locate the margin variance across all nine axes, and measure the
bias of the metric itself.

**Related work.** Surrogates for SRAM yield are established — multi-fidelity networks [4],
active learning and shrinkage features [5], [6], optimal-manifold search [7], quasi-MC [8]
and space-filling designs [9] on the sampling side, and Gupta and Calhoun [10] on Vmin
itself — as are rare-event methods, statistical blockade [11] and mixture importance
sampling [12]. All estimate a failure probability accurately **at one design point**. We
instead obtain the Vmin *contour* over the window and invert it, so the requirement is
smooth nine-dimensional regression plus an exact inverse rather than importance sampling in
the tail. The two are complementary: a blockade campaign is what would produce trustworthy
labels where this surrogate flags a condition as marginal. On the metric, the non-normality
of SNM is known [13], [14]; new here is identifying the quantity that sets the size of the
bias, measuring it from production output, and converting it into a spec's Vmin units.

---

## II. Method

### A. Vmin, and why the physics layer is not learned

Read stability is the static noise margin (SNM), the **minimum** of the two lobes of the
butterfly characteristic [15]; write stability is the write trip point (V_trip). MC gives a
distribution for each, of which μ and σ are recorded. For a condition **x** the margin
ratio

    z(V_op) = μ(x, V_op) / σ(x, V_op)                                     (1)

is evaluated on a supply grid, and Vmin is the voltage where z crosses the target Z_t,
by linear interpolation. Z_t follows from the array yield requirement — for a 128 Mb array
at 99% Poisson yield,

    p_fail = −ln(0.99) / (128 × 10⁶) ≈ 7.85 × 10⁻¹¹                        (2)
    Z_t = Φ⁻¹(1 − p_fail) = 6.398                                          (3)

The failing unit is the **cell**, not the transistor; the array size is consistent with the
14 nm 128 Mb SRAM of [16]. The sign-off spec, after IR drop from a 0.75 V nominal supply,
is **0.625 V** (Table I). All results here are time-zero: guardbands for degradation such as
BTI were established empirically in silicon and are already folded into this spec [1]–[3],
so no post-degradation voltage is applied as a second criterion. Z_t enters the *definition*
of Vmin; the spec decides whether the
result *passes*. The two are set independently, and that Z_t is analytic rather than
silicon-calibrated is what makes Section VI possible to state and impossible to catch
inside the flow.

Equations (1)–(3) are the entire physics layer. Nothing in them is fitted, which buys three
things: in sparsely sampled regions the GP extrapolates only (μ, σ) while the definition of
Vmin never moves; the threshold is a constant that can be corrected in post-processing
without retraining (Section VI); and the map is invertible in closed form along any axis
(Section IV).

**TABLE I. Sign-off reference quantities**

| Item | Value |
|---|---|
| Nominal supply | 0.75 V |
| **Sign-off Vmin spec (time-zero)** | **0.625 V** |
| Target z-score Z_t (128 Mb, 99% Poisson) | 6.398 |
| Read / write grid | 0.4–0.8 V / 0.4–0.7 V |

Accuracy is needed only where it changes a decision, so conditions crossing below the grid
floor (wide pass) or above the ceiling (wide fail) are censored and excluded from continuous
error metrics with their share reported. The grids are set by the spec, not by data
availability: they contain the minimal bracket around 0.625 V.


### B. What this paper borrows from outside circuit design

Every conclusion below is a device or process statement, but several of the computational
tools that produce them come from outside circuit design. So that the tools do not become
the obstacle in review, Table II summarizes each in one line, and the section that first
uses a tool restates why it has to be that tool. None of them was invented for this paper;
each is a standard instrument of its field used in its standard way.

**TABLE II. Non-circuit tools and what they do here**

| Tool | What it was built for | What it replaces here |
|---|---|---|
| Gaussian process (GP) | Kriging in geostatistics — interpolating an ore body from a handful of boreholes while reporting where the evidence is thin | Filling in between 2,000 conditions scattered through a nine-dimensional process box, instead of re-running MC for every new condition |
| Matérn-5/2 kernel + ARD | Deciding how close two conditions must be before their outputs are treated as similar, separately per axis | Stating the physical smoothness of μ(V_op) as an explicit assumption while letting the data set its strength |
| Fixed-noise likelihood | Weighted least squares for instrument data — trusting a point with a large error bar less | Weighting each label in proportion to the MC sample count behind it |
| Censoring | Reliability testing: specimens that have not failed by the end of the test | Counting conditions that cross outside the voltage grid separately rather than filling them with an arbitrary value |
| Bisection | Root-finding for a monotone function — one iteration halves the interval exactly | The inverse query: solving "which process coordinate meets this Vmin" exactly |
| Sobol indices | Apportioning output spread among inputs in simulators with dozens of inputs (aerospace, climate) | Answering "what share of the margin spread do the two corner axes carry" |
| Bootstrap | Resampling to measure an estimate's error bar directly | Error bars on the Sobol indices — here the bars, not the indices, decide the conclusion |
| Owen's T | The standard evaluation of the bivariate normal CDF | The closed form for the union probability, failure being either lobe collapsing |
| Random-effects pooling | Meta-analysis, where the true value differs slightly between studies | Pooling ρ_LR when it differs slightly between conditions |

### C. The surrogate

**Why a GP.** The GP began life in geostatistics as a way to map an ore body from a handful
of boreholes (kriging): interpolate smoothly between the observations while reporting where
the evidence is thin. Three things make it the right fit here. First, our data is that
situation exactly — 2,000 conditions scattered through a nine-dimensional process box, with
the space between them to be filled. Second, μ(V_op) is physically smooth: raising the
supply by 1 mV does not make the margin jump, and the GP states that smoothness as an
**explicit assumption** while letting the data set its strength, so nobody has to fix the
degree of a regression formula in advance. Third, the MC sample count differs between
conditions, so labels differ in reliability, and the GP takes a per-point measurement error
as a first-class input. None of the conclusions rest on this choice, however — Section III-C
shows a quadratic response surface does about as well on the same data.

A GP [18] maps the nine variation axes and the supply to (μ, σ), with a Matérn-5/2 ARD
kernel for μ and an additive kernel for σ separating the supply group from the device
group. A **kernel** is the function that decides how close two conditions must be before
their outputs are treated as similar; Matérn-5/2 sits between the infinitely smooth
assumption (RBF) and no smoothness at all, at twice differentiable. Imposing too much
smoothness on measured curves washes out local structure, which is why it is the default in
the regression literature and why it is used here. **ARD** lets each axis learn its own
lengthscale — how far that axis must move before the output visibly changes. With axes
carrying units of mV and dimensionless multipliers, one shared lengthscale would make no
physical sense. One warning is due in advance: **a lengthscale is not a sensitivity.**
Section V takes that distinction head on.

Per-condition bootstrap standard errors enter a fixed-noise likelihood, so
conditions backed by larger MC batches carry proportionally more weight. This is the same
idea as weighted least squares on instrument data — trusting a σ from 5,000 samples and a σ
from 500 equally is something no measurement engineer would do. It is why a
fixed budget is better spent on breadth of conditions than depth per condition
(Section VII), and why the discrepancy term of a multi-fidelity formulation [20] is
unnecessary when lower fidelity is nothing but fewer samples from the same simulator.
Inputs are standardized, without which the marginal likelihood converges to a markedly
worse optimum with no diagnostic warning. Three physics constraints inject device
knowledge: corner anchoring against extrapolation drift, a monotonicity penalty
ReLU(−∂μ/∂V_op)² suppressing the unphysical prediction that raising the supply degrades
mean stability, and weak regularization toward a linear σ(V_op) consistent with mismatch
scaling [19].

### D. Data

Table III lists the nine axes. Pass-gate and pull-down share the NMOS flavor and therefore
the dominant variation sources, so sampling them independently would place design points in
states silicon does not realize; a common/skew split is used instead, inducing
corr(σ_PG, σ_PD) ≈ 0.88 with the components sampled independently, which the variance
analysis of Section V requires. **Two of the nine axes — ΔVth,N and ΔVth,P — are the corner axes;
the other seven are outside any corner definition.**

**TABLE III. Variation parameters**

| Symbol | Description | Range | Unit |
|---|---|---|---|
| ΔVth,N | NMOS (pass-gate, pull-down) common Vth shift | ±60 | mV |
| ΔVth,skew | Pass-gate versus pull-down Vth mismatch | ±20 | mV |
| ΔVth,P | PMOS (pull-up) Vth shift | ±60 | mV |
| k_σN | NMOS local-mismatch σ multiplier, common | [0.7, 1.3] | — |
| Δk_σN | NMOS local-mismatch σ multiplier, skew | ±0.075 | — |
| k_σP | Pull-up local-mismatch σ multiplier | [0.7, 1.3] | — |
| k_μN | NMOS mobility multiplier, common | [0.7, 1.3] | — |
| Δk_μN | NMOS mobility multiplier, skew | ±0.075 | — |
| k_μP | Pull-up mobility multiplier | [0.7, 1.3] | — |

The notation is two letters. **Δ** is an absolute shift in mV, **k** a dimensionless
multiplier, and a multiplier prefixed by Δ (Δk) is the mismatch between pass-gate and
pull-down. The internal code names remain `cn`, `sk`, `pu`, `l_com`, `l_sk`, `lpu`,
`m_com`, `m_sk`, `mpu` respectively, and the result files still use them; the text, tables
and figures use only the symbols above.

Each mode is characterized only at its own worst temperature — read hot (125 °C), where the
lower threshold weakens the pull-down against the pass-gate; write cold (−40 °C), where the
higher threshold leaves the pass-gate unable to overpower the pull-up. This is a cost
decision and it splits the data into two batches of 2,000 conditions each, SNMR at 125 °C
over five levels and V_trip at −40 °C over four. Their nine-dimensional coordinates
intersect in **0/2000** conditions and the input has no temperature axis, so the two cannot
be merged into one GP; there are two models and only the argument runs jointly. Conditions
are deterministic PCG64 draws on **independent per-quadrant** streams, weighted toward each
metric's worst quadrant (read 45% FSG, write 45% SFG). Independence matters: an early pilot
reused one stream across quadrants and flipped only the signs of ΔVth,N and ΔVth,P, giving 75% of
conditions a mirror twin and silently inflating hold-out accuracy. The batches here have no
twins by construction and the training script asserts it.

A μ(V_op) monotonicity audit — μ must rise with supply, so a violation beyond three MC
standard errors is a transcription error — corrected 31 cells in the read batch and 12 in
the write batch, improving the read Vmin RMSE from 14.74 to **8.35 mV**. Thirteen read
conditions were repaired by a quadratic-in-V_op fit, which borrows the smoothness a GP also
assumes; dropping every audited condition from the hold-out moves the headline to
**8.44 mV**, so it does not rest on the repairs. Two duplicated conditions in an
independent batch bound the reference's own resolution at **1.09 mV**, and no error claim
below that is meaningful. The Appendix gives the audit procedure.

---

## III. How Accurate, and Why Write Is Harder

The split is at condition level, 1,700 training and 300 hold-out per batch, with all supply
levels of a condition in the same partition. Splitting by condition is the point: a random
split by row would put a condition's 0.5 V row in training and its 0.6 V row in the
hold-out, which amounts to grading against an answer already seen. Validation is stacked at three increasing
distances from the training distribution: the in-batch hold-out, the four PDK global corner
decks, which appear in neither partition and were run separately at each mode's own
temperature and sample count, and the Stage-B pilot batch, designed earlier and
independently, evaluated from the same checkpoints with no retraining (coincidence with the
training coordinates is 0/348 and 0/399). Table IV collects all three.

**TABLE IV. Forward accuracy at three distances from training**

| | Read (SNM, 125 °C) | Write (V_trip, −40 °C) |
|---|---|---|
| μ RMSE / R², hold-out | 2.50 mV / 0.9965 | 2.17 mV / 0.9989 |
| σ RMSE / R², hold-out | 0.256 mV / 0.9798 | **2.04 mV / 0.7318** |
| **Vmin RMSE, hold-out** | **8.35 mV** (243 scored) | **14.45 mV** (228 scored) |
| \|error\| median / P90 | 3.36 / 10.69 mV | 9.81 / 21.47 mV |
| **Vmin RMSE, PDK corners** | **9.3 mV** | **16.7 mV** |
| **Vmin RMSE, independent batch** | **4.26 mV** (283 clean) | **13.63 mV** (305 clean) |
| Vmin RMSE, spec band (±25 mV) | **7.67 mV** | **10.44 mV** |

Three levels return the same order of magnitude for read, and the error does not grow on
data generated outside the training design — the model learned behavior over the (ΔVth,N, ΔVth,P)
plane rather than a structure of the design. The independent batch is *better* (4.26 mV)
for a reason worth stating rather than celebrating: that batch freezes the six length and
multiplier axes at nominal, so its σ is nearly constant at 13.4 ± 0.27 mV, the denominator
of z is effectively fixed, and the problem is genuinely easier. The representative figure
for the full nine-dimensional window is the 8.35 mV. Fig. 2 plots predicted against
reference Vmin.

**Fig. 2.** Reference-simulation versus predicted Vmin on the hold-out conditions.

### A. The read/write gap is an identity, not an artifact

Write has the *better* mean prediction (R² 0.9989) and a 1.7× worse Vmin error. That
inversion is the most informative number in the table, because it localizes where accuracy
is actually lost.

Vmin is the crossing of z = μ/σ with Z_t, so a small error in the statistics moves the
crossing by δVmin ≈ δz/(dz/dV_op). At the crossing σ = μ/Z_t by definition, and the
relative μ error is several times smaller than the relative σ error in both modes, so

    δVmin ≈ Z_t · (δσ/σ) / (dz/dV_op)                                     (4)

With the read σ ≈ 13.4 mV, δσ = 0.256 mV and a population median slope of 15.1 V⁻¹,
Eq. (4) predicts **8.1 mV** against the measured 8.35 mV — within 3%, from four quantities
none of which is the Vmin error itself. Applied to write it says the observed 14.45 mV
implies σ ≈ 25 mV, consistent with μ(0.6 V) = 187 mV divided by Z_t.

The two modes then differ by two competing factors. Write σ is relatively about four times
worse, because V_trip is a *switching* threshold set by the pass-gate/pull-up contention
at the instant regeneration is lost — a ratio of two varying drive currents, whose spread
compounds — whereas read SNM is a *static* geometric margin dominated by a single additive
threshold-mismatch term. Its condition-to-condition σ spread is correspondingly wider
(SD 3.96 mV against 1.79 mV). Against that, the write z curve is 2.4× steeper
(36.4 against 15.1 V⁻¹), which divides the same z error down. Net ≈ 1.7×, which is what
Table IV shows.

**First practical consequence — accuracy is bought on σ, not on μ.** A campaign adding
conditions to improve the mean is spending in the wrong place, and Section V says which axes
carry σ.

**Second — the write σ error is not transcription noise.** The measured sheets were
transcribed by hand and **69% of the write batch lost its decimals** against 1% for read, but
that contributes 1/√12 ≈ **0.29 mV** on a 1 mV grid — the variance is the same whether the
decimals were rounded or discarded — which does not account for the observed 2.04 mV. Against
the independent batch, 0.9% decimal loss and a far cleaner ruler, the σ RMSE is still
1.78 mV, and excluding the grid floor drops it from 2.041 to 1.336 mV, **yet 0.4 V is
precisely the level whose decimals survived**. The error is concentrated where the
transcription is cleanest, so the cause is a real model limitation. Its signature is 33 write
censoring disagreements against one for read: near the floor the z curve is shallow, so a σ
error flips the clamp decision outright.

### B. The corners, and what their spacing says about the cell

**TABLE V. Vmin per corner — independent simulation versus surrogate (Z_t = 6.398)**

| Corner | (ΔVth,N, ΔVth,P) mV | Read reference → GP | Write reference → GP |
|---|---|---|---|
| **FSG** | (−29.16, +38.64) | **0.5903 → 0.5908** ← read worst | < 0.4 V, both clamped |
| **SFG** | (+31.63, −36.76) | < 0.4 V, both clamped | **0.5924 → 0.6070** ← write worst |
| FFG | (−36.42, −44.32) | 0.4731 → 0.4604 | 0.4923 → 0.4939 |
| SSG | (+36.30, +44.80) | 0.4672 → 0.4772 | 0.5335 → 0.5086 |

The limiting corner of each mode is identified correctly, with a 0.6 mV error at FSG. The
mid-table read corners swap in the prediction, but their reference gap of 5.9 mV is smaller
than the corner RMSE of 9.3 mV, so the honest claim is "the limiting corner is identified",
not the ordering of corners 5 mV apart — which is what sign-off uses anyway. On the write
side the corners are more than 40 mV apart and the ordering reproduces 4/4.

The corner identification is physically right, not merely numerically right. FSG combines a
fast NMOS with a slow PMOS: a strong pass-gate lifts the storage '0' during read while a
weak pull-up cannot restore it, so read SNM collapses. SFG is the mirror — a weak pass-gate
cannot overpower a strong pull-up, so the cell resists flipping and write becomes the
constraint. This is why each mode's worst corner is the other mode's censored corner in
Table V: read genuinely does not set Vmin at SFG, and that is a fact about the cell, not a
data defect.

**The spacing is the result.** The read worst (0.5903 V) and the write worst (0.5924 V) lie
**2 mV apart**. A 6T cell has essentially one sizing degree of freedom against these two
constraints — strengthen the pass-gate and writability improves while read stability
degrades. Finding both limiting corners within 2 mV is what a cell sitting *at* its
constrained sizing optimum looks like. The practical implication is sharp: **there is no
read/write trade left to harvest, so any further Vmin improvement must come from area or
supply, not from ratio.** Section VI returns to this with a number. Fig. 3 compares the
per-corner values.

**Fig. 3.** Reference-simulation versus predicted Vmin per corner, read and write.

### C. What the Gaussian process contributes

A quadratic response surface in the same ten inputs (66 terms, least squares, same physics
layer, same hold-out) is **not worse** — for read it gives 7.69 mV on the hold-out and
6.11 mV on the corners against the GP's 8.35 and 9.34 mV, and the corners were never
fitted, so this is not an in-batch artifact. We report it because it bounds the claim: over
a process box this smooth the regressor is not the difficulty, and **nothing downstream
depends on it** — the physics layer, the censoring, the inverse, the sensitivity indices
and the ρ_LR correction all consume only μ and σ. The contribution is the pipeline, not the
regressor, and a fab flow may drop GP training from the deployment path entirely. What the
GP adds — a per-point predictive variance and a noise-aware likelihood — is not exercised
on a dataset where no result consumes the variance and every condition carries the same
5,000 samples, so we do not claim it.

---

## IV. Inverting the Surrogate

The forward direction answers "what is the Vmin of this condition". The question design
asks is the reverse, and the analytic physics layer makes it exact. Fixing eight of the
nine coordinates leaves Vmin a monotone one-dimensional function of the ninth — decreasing
in ΔVth,N, since a faster pass-gate needs a lower supply, and increasing in ΔVth,P. The direction is
read from the two endpoints rather than assumed.

**Why bisection.** Bisection is the oldest root-finding method there is: provided the
function is monotone, one iteration halves the candidate interval exactly. That it is
available here is what dictates the architecture of the whole paper — because the physics
layer is not learned, the map is *guaranteed* monotone in the supply, and no optimizer is
needed. Twenty-four bisection steps shrink a
±60 mV span below 10⁻⁵ mV, so the solution is exact to machine precision with respect to
the surrogate. A slice where the target is unattainable anywhere in the design range is
reported as "no boundary" rather than clipped, and that distinction turns out to be the
result.

### A. Accuracy, and why it beats the forward error

To keep this from being a self-consistency check, the target is always the Vmin taken from
the *reference* z curve: fix eight coordinates at a hold-out deck's actual values, solve
the ninth, and compare against the coordinate the deck had. Because the answer is already
in the data the inverse error is measured directly in mV, and Table VI gives it per axis.

**TABLE VI. Coordinate recovery (245 hold-out conditions, target = reference Vmin)**

| Unknown | Recovered | RMSE | Bias | \|∂Vmin/∂x\| | Implied by forward 8.35 mV |
|---|---|---|---|---|---|
| ΔVth,N | 244 / 245 | **2.60 mV** | −0.38 | 2.081 | 4.01 mV |
| ΔVth,P | 235 / 245 | **3.20 mV** | +0.46 | 1.633 | 5.11 mV |

Converted through the local sensitivity, the forward error of 8.35 mV should have produced
4.01 mV in ΔVth,N and 5.11 mV in ΔVth,P. The actual recovery is 60–65% of that, with bias inside
±0.5 mV. **This is structural, not luck.** The GP's error field is smooth, so at a given
condition much of the model error is a near-rigid offset of the whole z(V) curve rather
than an independent error at each supply level. The forward query reads a single crossing
and absorbs that offset in full. The inverse constrains the coordinate against all five
levels at once, and shifting the unknown axis also moves the whole curve — so the shared
component of the error cancels between the two and only the voltage-dependent residual
survives. An inverse built on a *learned* Vmin map would have no such structure to exploit.

In practical terms 2–3 mV is finer than the usual tolerance of threshold targeting, so
"where must Vth sit to meet this Vmin" is answerable at a resolution design can act on.
Twelve random starts at a target of 0.625 V all converged onto the target manifold with a
maximum residual of **4.7 × 10⁻⁴ mV**, confirming exactness — an optimizer would have had
to be stopped at a tolerance instead.

### B. The window closes along one axis only

The deliverable is a boundary, not an individual solution. Holding the other seven
coordinates at nominal and extracting the iso-Vmin = 0.625 V contour over the (ΔVth,N, ΔVth,P)
plane gives the compliant region directly: **92.8%** of the plane passes, but the geometry
is the informative part. The boundary **exists only where ΔVth,P ≥ 4.3 mV** — 33 of 70 ΔVth,P rows;
if the pull-up is faster than that, any ΔVth,N in ±60 mV meets spec and there is no boundary at
all. **This cell's read window closes along ΔVth,P and only along ΔVth,P.** Once the pull-up slows
past about 4 mV a lower bound appears on ΔVth,N and rises quickly; where it is fast enough, ΔVth,N
is a free design variable. Corner sign-off cannot represent this — not because four points
are too few to interpolate, but because over half the plane the boundary is *absent*, and a
set of points has no way to report absence.

Boundary error is quoted where the decision reads it: over hold-out conditions within
±25 mV of spec the read Vmin RMSE is 7.67 mV, which divided by the measured |∂Vmin/∂x|
places the boundary within **3.7 mV of ΔVth,N** or **4.7 mV of ΔVth,P**. We give an in-plane
displacement rather than a Hausdorff distance because the two axes move Vmin at different
rates, so a Euclidean distance in (ΔVth,N, ΔVth,P) would mix non-interchangeable quantities.

Because the boundary is *solved* rather than searched, its cost scales with the number of
rows, not with grid resolution: **858** condition evaluations against **4,900** for a
70 × 70 grid, and the products are not equivalent, since the grid can only place boundary
points by interpolating between cells. In HSPICE a boundary point costs 130 MC runs, so the
33 rows would need 4,290;
on the trained surrogate it takes seconds. Fig. 4 shows the plane, the boundary and the
multistart solutions.

**Fig. 4.** Vmin contours over the (ΔVth,N, ΔVth,P) plane with the spec boundary and the
multistart convergence points.

---

## V. The Corner Axes Move the Mean; the Margin Is Set by the Spread

**Why Sobol indices.** They were built for simulators with dozens of inputs — aircraft
design, climate models — to apportion "what share of the output spread is due to this
input". One difference from the local sensitivity ∂y/∂x familiar on the device side is
decisive here. A derivative is **the slope at one point**; a Sobol index is **the
contribution of shaking that axis over its whole allowed range**. Corner sign-off asks
exactly the latter question — a corner is not a slope at a point but the extremes of an
entire axis — which is why the indices are used here. A total-order index S_T reads as "what
share of the output spread disappears if that axis is pinned perfectly", interactions with
other axes included.

Sobol indices [21] partition the variance of a scalar output under a stated input
distribution — here a uniform prior over the training box, which weights the qualification
window evenly rather than describing the shipped population. The output is z at the spec
voltage, written V_T0 = 0.625 V, not Vmin: Vmin is undefined wherever z never reaches the
threshold inside the grid, and discarding those samples would break the pairing the
Saltelli estimator depends on, whereas z(V_T0) is finite everywhere and monotone in the
margin. Total-order indices use the Jansen estimator [23] on a base sample of N = 4,096 —
45,056 surrogate evaluations per mode, no new simulation — with 500-fold bootstrap
intervals. The **bootstrap** resamples the data one already has, with replacement, to
measure directly how much an estimate wobbles; it is indispensable here because it is the
error bars, not the indices, that decide the conclusion. Indeed, first-order indices from
the Saltelli estimator [22] appear nowhere in this
paper: their noise is the size of the index itself, most visibly where S1(k_σN) = 1.020
exceeds its own S_T of 0.847, which exact arithmetic forbids and the interval
[0.706, 1.365] explains. Table VII gives the total-order indices.

**TABLE VII. Total-order Sobol indices over the training box (N = 4,096)**

| Axis | In a corner? | S_T of z, read | S_T of z, write | S_T of σ, read | S_T of σ, write |
|---|---|---|---|---|---|
| ΔVth,N (NMOS Vth) | yes | **0.419** | **0.421** | 0.001 | 0.006 |
| k_σN (common local σ) | **no** | **0.276** | 0.170 | **0.847** | **0.722** |
| ΔVth,P (PMOS Vth) | yes | 0.188 | 0.168 | 0.007 | 0.017 |
| ΔVth,skew (Vth skew) | no | 0.067 | 0.097 | 0.001 | 0.011 |
| k_σP (pull-up local σ) | no | 0.043 | 0.060 | 0.137 | 0.193 |
| k_μN, Δk_μN, k_μP, Δk_σN | no | ≤ 0.015 each | ≤ 0.032 each | ≤ 0.004 each | ≤ 0.031 each |
| **Σ** | | **1.031** | 0.987 | 1.000 | 1.007 |

**A spread axis outranks a corner axis.** For read, S_T(k_σN) = 0.276 against
S_T(ΔVth,P) = 0.188, with non-overlapping bootstrap intervals ([0.259, 0.293] and
[0.178, 0.199]). The device reason is the one anticipated in Section I. A global PMOS
threshold shift moves both pull-ups together; SNM is a *difference* measure between the two
inverters, so a symmetric shift is largely common-mode and cancels to first order. The
k_σN axis scales the *local* mismatch σ of the NMOS devices, and z = μ/σ depends on it
through the denominator, with no cancellation available. At a 6.4σ target the denominator
is simply worth more than the numerator. **Corner definitions were built to bracket mean
shifts; a tail-quantile metric is spread-dominated, and the mismatch is structural.**

The bound this puts on corner methods is quantitative. The two corner axes sum to 0.61 for
read and 0.59 for write, and since total-order indices overlap through interactions those
sums are an *upper* bound on their joint share: the remaining seven axes carry **at least
39% (read) and 41% (write)** of the margin variance, and the bound is nearly tight because
ΣS_T exceeds 1 by only 0.031 for read. A corollary Section VI needs: **any Vmin quoted at a
corner is a worst case in corner space, hence a lower bound on the nine-dimensional worst
case.**

The σ columns make the point in its purest form: the three local-σ length axes carry
**98.8% (read) and 93.8% (write)** of the σ variance, k_σN alone 85% and 72%, while the
three mobility multipliers together carry 0.3% and 2.9%. That axes named "σ" carry σ
variance is unsurprising; what it establishes is that the σ error identified in
Section III-A as the accuracy bottleneck lives on axes a corner flow never varies. One
caution: a variance share is not an error budget — freezing 98.8% of the read σ variance,
as the independent batch does, moved the read σ RMSE only from 0.256 to 0.146 mV.

**The fitted lengthscales say none of this**, which matters because ARD relevance is the
free proxy everyone reaches for. It spans a factor of 1.13 across the nine axes while S_T
spans a factor of 400, and by relevance k_σN is indistinguishable from three other axes
(all 0.109) despite ranking second by variance. The σ kernel is the extreme case: nine
device lengthscales inside 7.83–7.92, about 1% apart, while one of them carries 85% of the
σ variance. The two quantities answer different questions — a lengthscale responds to
*curvature*, a Sobol index to how far the output *moves* over the axis range — and a
strong, smooth, nearly linear dependence, which is exactly what k_σN does to σ, earns a
long lengthscale and a large variance share at once. What survives from the fitted kernel
is direction, not ranking: λ(V_op) = **4.64** is genuinely the shortest lengthscale and the
supply genuinely the most curved axis, and ARD puts λ(ΔVth,N) below λ(ΔVth,P) just as Sobol puts
S_T(ΔVth,N) above S_T(ΔVth,P). **Reporting ARD lengthscales as a sensitivity result is a cheap
mistake to make.** Fig. 5 shows both rankings side by side.

**Fig. 5.** Total-order Sobol indices with bootstrap intervals for (a) z(V_T0) and
(b) σ(V_T0), read and write; (c) the ARD relevance of the same axes, in the same order.

As a corollary for the designer, sweeping the off-corner threshold-mismatch axis ΔVth,skew
over its full ±20 mV range at each of 625 cells of the (ΔVth,N, ΔVth,P) plane leaves
**82.7%** of cells passing at every mismatch, with a median passing width of the full range.
The tolerance is close to binary, so what disappears as the threshold tightens is not part
of an axis but the cell itself.

---

## VI. The Metric's Own Bias, and What It Says About the Cell

Everything above takes Eq. (1) at face value. It is biased, and the bias is larger than any
error measured so far.

SNM is the minimum of two lobe margins, and the minimum of two Gaussians is not Gaussian —
its lower tail is heavier than a moment-matched normal. Equation (1) nevertheless fits a
Gaussian to that minimum and extrapolates to 6.398σ, so it underestimates the failure
probability. Failure occurs if *either* lobe collapses, so the truth is a union probability;
given the per-lobe statistics it is closed-form, with the joint term a bivariate normal CDF
computed by Owen's T [17]. **Owen's T** is the standard function for evaluating bivariate
normal probabilities numerically, available straight from statistical tables. The gap between
the union z and the naive z of Eq. (1) is the
bias, and its size is set entirely by the lobe correlation ρ_LR.

### A. Measuring ρ_LR without new simulation

Read SNM flows report only the μ and σ of the minimum, which is why this bias is normally
invisible. But the **skewness of min(L, R) is a closed-form function of ρ_LR**: with
min(L,R) = (S − |D|)/2 where S = L+R and D = L−R are independent,

    a² = 2(1 − ρ),  c = √(2/π),  m₂ = 1 − a²/(2π),  m₃ = −a³(2c³ − c)/8
    g₁(ρ) = m₃ / m₂^{3/2}                                                 (5)

with m₂, m₃ the second and third central moments of the standardized minimum, and g₁
monotone in ρ. Skewness uses the whole sample and is therefore more efficient than a tail
fit resting on a few lower quantiles. **This is what makes the diagnostic cheap: it needs
four extra exported columns from a run the fab is doing anyway, not a new deck.** Here nine
conditions at 10⁵ samples were exported as shape statistics only — a five-point quantile
ladder, skewness, excess kurtosis and the observed minimum — with raw samples never leaving
the fab.

Normality is rejected three independent ways: the quantile-ladder χ² is 582–821 on five
degrees of freedom in 9/9 conditions, skewness is negative in 9/9 with mean **−0.292**, and
the observed minimum runs **1.18×** deeper than the expected minimum of an n = 10⁵ Gaussian
sample (Blom position −4.265 σ), the last being independent of any quantile fit. Inverting
Eq. (5) and cross-checking against a χ² fit on the ladder, the two paths converge on
ρ_LR ≈ −0.34 … −0.37; pooling the nine per-condition estimates gives

    **ρ_LR = −0.371**,  random-effects SE **0.013**,  **z_bias = +1.054 σ**,  **Z_eff = 7.453**

**Why random-effects pooling.** It comes from meta-analysis, where several studies are
combined: unlike a fixed-effects pooling, which assumes every study shares one true value,
it allows the true value itself to differ slightly between studies and widens the error bar
accordingly. We quote the random-effects rather than the inverse-variance SE (which would give ±0.005)
because the latter presumes a common ρ, and a uniformity test rejects that presumption
(χ² = 53.6, p = 8.1 × 10⁻⁹). The rejection does not force a per-condition correction: the
per-condition z_bias values span +0.981 … +1.095 σ, which is ±4 mV of Vmin, less than half
the model error — at n = 10⁵ even practically meaningless differences become significant.
A single scalar suffices, and the reason is that the variation is smaller than the model
error, not that the test passed.

### B. ρ_LR is a readout of the cell's local/global variance split

This is why ρ_LR is worth measuring rather than fitting: it is not a nuisance parameter but
a **direct statement about where the cell's variance comes from**. Local mismatch that
strengthens one side widens one lobe and cuts the other, so it anti-correlates them; a
device-type-level global shift moves both the same way and co-correlates them. Writing the
lobes as L = G + M and R = G − M with G global, M local and independent — the same
exchangeability the min-of-two model already assumes — gives ρ_LR = (g − m)/(g + m) with g
and m the two variances. The measured value inverts to

    m / g = (1 − ρ_LR)/(1 + ρ_LR) = **2.2**

**Local mismatch carries about 2.2 times the global variance in the lobe difference.** For a
minimum-geometry FinFET 6T bitcell that is the expected regime — σ_Vth ∝ 1/√(WL) [19] — but
it is now measured rather than assumed, from production output, on this cell.

An immediate consequence is that the experiment design of Section II-D **cannot** mitigate
this bias. All nine axes are device-type-level global quantities that preserve the cell's
left–right symmetry, so under the design axes alone the lobes are exchangeable at every
condition; what makes them asymmetric arises only from local mismatch *inside* an MC
sample. No subset of conditions is naturally exempt, and the bias applies across the whole
window.

### C. What it costs, and the design choice it forces

The bias moves **only the threshold** of the (μ, σ) → Vmin conversion, so the correction is
the post-processing step z_bias = Z_union(ρ_LR, Z_t) − Z_t, Z_eff = Z_t + z_bias, needing no
re-simulation — one constant in the physics layer. Ordering conclusions are therefore
untouched; anything referenced to the threshold moves.

Converting σ to millivolts uses dz/dV_op in the spec band: a population median of
**15.1 V⁻¹** for read, and 14.2 V⁻¹ locally at FSG. A z_bias of +1.054 σ is therefore
**70 mV** of Vmin at the population median, and tracing the FSG z curve directly gives
**+71.7 mV** there.

That is decisive at FSG, where z(0.625 V) = **6.927**. For the spec decision to survive the
corrected threshold must not exceed that value, so the admissible bias is
z_bias ≤ 6.927 − 6.398 = **+0.529 σ**, equivalently ρ_LR ≥ +0.145. The measured +1.054 σ is
**twice that headroom**, and the corrected FSG Vmin is 0.662 V — **37 mV past spec**. Two
conditions attach: the nine tail conditions carry no corner labels, so applying the pooled
z_bias at FSG extrapolates into an unsampled quadrant; and 0.662 V is a corner-space worst
case, which Section V established is a *lower* bound on the nine-dimensional one, so the
shortfall is at least 37 mV.

**Table VIII places this next to everything else the paper measured.**

**TABLE VIII. Error sources in Vmin units, and the corner shift the correction imposes**

| Error source | Size | | Corner | Naive | Corrected |
|---|---|---|---|---|---|
| Reference repeatability (same condition twice) | 1.1 mV | | FFG | 0.4731 V | 0.5279 V |
| Surrogate regression error (read hold-out) | 8.4 mV | | SSG | 0.4672 | 0.5126 |
| Surrogate regression error (read, PDK corners) | 9.3 mV | | SFG | < 0.4 | 0.4230 |
| Price of a 53× budget reduction (Section VII) | +2.6 mV | | **FSG** | **0.5903** | **0.6619** |
| **Min-statistics metric bias** | **70 mV** | | | | |

The metric bias exceeds every other term by an order of magnitude and is three times all of
them combined, which is the practical ranking this paper argues for: **record tail shape
before improving the regressor.** The 1 mV separating the GP from a quadratic surface
(Section III-C) is not where the uncertainty is.

Section III-B found the cell at its constrained sizing optimum, with no ratio trade left;
Section VI-B says what the remaining levers cost. Reaching ρ_LR ≥ +0.145 means m/g ≤ 0.75,
a **2.9× reduction in local mismatch variance**, which by σ_Vth ∝ 1/√(WL) [19] is about
**2.9× the pass-gate/pull-down area**. The alternative is **+37 mV of supply**. Those are
the two options, and the surrogate's contribution is that both are now numbers rather than
directions. Fig. 6 shows the two ρ_LR estimates and the shift the correction imposes.

**Fig. 6.** (a) ρ_LR from the two estimation paths; (b) the shift the correction imposes
on the corner Vmin values.

**This is a result, not a failure of the method** — corner sign-off passed this design not
because margin existed but because of an assumption about the shape of a tail. What is not
established matters equally: the two estimation paths share the min-of-two premise, so their
agreement tests the estimator and not the premise, and nothing here is checked against
silicon. Write ρ_LR is unmeasured, and since the write-limiting corner already sits at
0.5924 V it decides pass or fail directly.

---

## VII. What the Campaign Must and Must Not Spend

Campaign cost is (voltage levels) × (conditions) × (MC samples per condition). Cutting each
factor alone and scoring on the same hold-out, none shows a measurable loss: dropping the
0.8 V read level gives 6.99 mV (the surrogate fills that level back in with a bias of
−0.18 mV), cutting training conditions from 1,700 to 400 removes 76% of the simulation
volume for 8.78 mV, and cutting MC depth tenfold to 500 samples gives 7.63 mV. The three
deltas sum to **−1.7 mV** — they predict no degradation at all.

**Run together, the same cuts cost +2.6 mV** (Table IX). The 4.3 mV gap is not noise: μ
moves the same way (2.489–2.715 mV single-factor against 3.425 mV combined), and μ and Vmin
move together.

**TABLE IX. Combined reduction (400 conditions × reduced levels × 500 MC, same hold-out)**

| | Read | Write |
|---|---|---|
| Training rows / budget ratio | 1,600 / 0.0188 (**53×**) | 1,596 / 0.0235 (**42.5×**) |
| **Vmin RMSE (full grid)** | **10.95 mV** vs 8.35 baseline | **15.83 mV** vs 14.45 |
| **Degradation** | **+2.6 mV** | **+1.4 mV** |

The mechanism is worth stating because the mistake is easy to make. **Condition count and
MC depth are not independent axes: they enter the error through the same term.** The GP's
error at a condition is label noise divided by the number of neighbours effectively
averaging it. At 1,700 conditions the n′ = 500 label noise (σ/√500 ≈ 0.6 mV) sat far below
the 2.5 mV model error and was invisible; at 400 conditions each label has roughly four
times fewer neighbours, so the same noise contributes about twice as much and stops being
negligible. A reduction is a **Pareto point with a stated price**, not a product of lossless
factors.

Which grid end can be trimmed is **predictable from that mode's slope**, so it can be
decided before the campaign runs: extrapolating one level out costs −6.45 mV of bias for
write at 0.8 V and +5.66 mV at 0.4 V, but only −0.18 mV for read at 0.8 V, because the GP
reverts to its prior mean outside
the training range and compresses μ(V_op) in proportion to how steep that slope already is —
read's 15.1 V⁻¹ against write's 36.4 V⁻¹. For write, dropping 0.4 V is not a loss of accuracy
but a structural loss: hold-out censoring rises from 69 to 90 conditions, and for those
there is no Vmin to report at all.

**The tail-diagnosis budget is not in this calculation and is not a candidate for
reduction.** Measuring ρ_LR needed **10⁵** samples per condition; 500 estimate z perfectly
well but cannot see the *shape*, since a tail fit needs the observed minimum near −4.3σ and
500 samples reach only about −3.2σ. **A campaign should therefore be two-tier — shallow
sampling for most conditions plus very deep sampling for a few** — since otherwise the
deepest cut lands on the cheapest term while the term dominating the error budget goes
unmeasured. Reducing conditions is meanwhile the only factor that cuts both simulation cost
(linear) and exact GP training cost (roughly cubic: 1,455 s at 1,200 conditions against
152 s at 400). Fig. 7 collects the curves.

**Fig. 7.** Budget-reduction Pareto — (a) conditions, (b) MC depth, (c) single factor
versus all three.

---

## VIII. Limitations

**Not verified against silicon.** The ρ_LR correction is estimated from data and applied as
post-processing, but no silicon Vmin measurement exists to check its size, and corner
simulation cannot serve that role because it is the very source of the naive z being
corrected. This is the single largest open item.

**Write σ is a floor, not a knob.** Section III-A left most of the write σ error unexplained
even after the decimal loss is accounted for. Section V places the σ *variance* on the local-σ
axes, but that is where σ varies, not where the model's σ *error* lives: the independent
batch freezes those axes and the write σ RMSE still moves only from 2.04 to 1.78 mV. Adding
conditions along them is worth testing for read and already answered negatively for write.
Locating the write floor needs a different measurement — regressing the hold-out σ residual
on the nine coordinates, which costs no simulation.

**Combined read/write decisions are not validated.** The two batches share no coordinates,
so Vmin = max(read, write) can be checked against the reference only at the four PDK corners
(Table V); over the full 2,000 conditions it would require evaluating each surrogate at the
other's coordinates, which is a prediction on top of an unvalidated prediction, and
we do not report that surface. A few tens of shared conditions would remove the limitation.

**Scope.** One node, one cell topology, one proprietary PDK — absolute values are not
externally reproducible, though the procedure and relative conclusions are. Only the
**axis-wise** inverse is validated; the full nine-dimensional hypersurface with several axes
free at once is not claimed, and gradient descent through the differentiable composite,
though the natural extension, was not validated here. The voltage-level reduction is
conditional on the spec of Table I, and the Sobol shares assume a uniform prior over the
qualification box, answering "across the window we sign off" rather than "in the population
we ship".

**Next measurements, in priority order.** (1) Write ρ_LR — it decides pass or fail, and since
the two lobe terms are separate MC outputs, adding the record makes it a direct correlation
measurement. (2) Silicon Vmin. (3) A corner-labeled tail re-measurement. (4) Conditions
shared by both modes.

---

## IX. Conclusion

One surrogate, built from a fixed simulation budget, answers Vmin queries in both
directions on production FinFET calibration data: 8.35 mV hold-out RMSE for read and
14.45 mV for write, 9.3 mV on PDK corners it never saw with each mode's limiting corner
identified correctly, and 2.60–3.20 mV recovering a process coordinate. Keeping the
(μ, σ) → Vmin conversion analytic rather than learned is what makes the last number
possible, and it lets a boundary be traced exactly at 858 evaluations against 4,900 for a
grid.

The numbers that matter, though, are the ones that say something about the cell. The forward
error is not generic regression error but Z_t(δσ/σ)/(dz/dV_op), so accuracy is bought on the
spread, not the mean. The read and write limiting corners lie 2 mV apart — a cell at its
constrained sizing optimum, with no ratio trade left. The variance decomposition shows why
corner sign-off is structurally rather than merely practically incomplete: corner axes move
the mean, a 6.4σ target is set by the spread, and an NMOS local-σ axis outranks the PMOS
threshold shift with at least 39% of the margin variance off-corner. And ρ_LR = −0.371,
obtainable from four extra columns of a run the fab already performs, says local mismatch
carries 2.2× the global variance in the lobe difference — worth 70 mV of Vmin, enough to put
the read-limiting corner 37 mV past spec, and closable only by about 2.9× the
pass-gate/pull-down area or 37 mV more supply. Corner sign-off passed this design on an
assumption about the shape of a tail, and the same simulation output that hid the problem
also contains its measurement.

---

## Appendix: Reproducibility

Condition generation is a deterministic PCG64 stream, so the tuple (stage, condition count,
seed, metric, method) reproduces the entire condition set bit for bit. Training uses
GPyTorch [24] with seed 42, 150 iterations and a fixed-noise noise-aware likelihood. Each
result corresponds to one script and one output file, and every number in the text traces
through that correspondence table from script to data to output. The PDK and reference data
are internal assets and are not released; the procedural specification and the relative
metrics are.

The QC audit of Section II-D in full: parse-stage typo detection (double decimal points such
as `93..1`, merged mean/σ cells such as `182.9612.14`); the μ(V_op) monotonicity check;
recovery by decade restoration where a missing ×10 matches the neighbouring voltage trend,
otherwise by a quadratic fit through the same condition's other voltage points; and a
re-check asserting zero remaining violations. For the independent pilot batch, whose original
decks are unavailable, only flag-and-exclude is possible, so its own quadratic-surface
residual criterion is used instead — flagging 13/348 read and 8/399 write conditions, whose
deviations run tens to hundreds of times the 1.09 mV repeatability floor.

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

[24] J. R. Gardner, G. Pleiss, D. Bindel, K. Q. Weinberger, and A. G. Wilson,
     "GPyTorch: Blackbox matrix-matrix Gaussian process inference with GPU
     acceleration," in *Proc. Adv. Neural Inf. Process. Syst. (NeurIPS)*, vol. 31,
     2018, pp. 7576–7586.
