# SRAM Vmin Sign-off Across the Full Process Window — A Physics-Constrained GP Surrogate with Differentiable Inversion

> **Internal review draft v2.0 (2026-07-19)** — Restructured for a
> process/device engineering audience. Readers are assumed fluent in device
> physics but not in machine learning, so device fundamentals are compressed
> and ML concepts are explained qualitatively. Carries over all technical
> content from `paper_enhanced_en.md` (v1.1) but reframes the narrative from
> "list of metrics" to "solving the sign-off problem."
>
> `[TBD]` pending in-fab results. In particular, the tail diagnostic of §2.4
> (`docs/plans/infab_tail_diagnostic_request.md`) may trigger a uniform
> correction to all absolute Vmin figures.

---

## 1. The Problem: Vmin Sign-off Must Cover the Whole Process Window

### 1.1 What Must Be Met — the Spec

The nominal operating voltage of this process is **0.75 V**. Once on-chip and
off-chip IR drop are accounted for, the voltage actually seen by an SRAM cell
is lower, and the resulting **Vmin spec** the cell must satisfy is:

| Criterion | Vmin spec | Meaning |
|---|---|---|
| **T0** (time-zero) | **0.625 V** | Initial characteristics |
| **EOL** (end-of-life) | **0.675 V** | With degradation — the binding criterion |

So under any process-variation condition, cell Vmin must be **at or below
0.675 V** for operation to be guaranteed through end of life. The **50 mV**
between T0 and EOL is the entire margin budget this design has to work with.
Keep that number in mind — it recurs throughout this paper as a yardstick.

This spec anchors every judgement in the paper. More important than "what is
Vmin" is **"does this condition meet 0.675 V, and if not, by how much does it
miss?"**

### 1.2 Why It Is Hard — a 9-Dimensional Space and the Cost of MC

Vmin depends strongly on process variation, and that variation is not a single
axis. This study alone spans nine: NMOS/PMOS Vth shifts, PG-PD skew, local-σ
(local mismatch strength), mobility, and the PG-PD asymmetric component of each.

Sweeping that space with the standard Monte Carlo (MC) approach multiplies:

- thousands of MC runs per condition (to build the SNM distribution)
- repeated at every voltage level
- across thousands of conditions

For a batch of this size (2,000 conditions × 5 voltages × 5,000 MC) that is
**50 million runs**. With PrimeSim taking minutes to tens of minutes per run,
even heavily parallelized this is weeks to months — before counting PDK
licenses, per-license concurrency limits, and server cost. The bottleneck
worsens at advanced nodes as models grow more complex.

### 1.3 Why Corners Alone Are Not Enough

The traditional alternative is to sign off at a few representative corners
(FSG/SFG/FFG/SSG). That solves cost but misses two things.

**First, missing axes.** Corners are extreme combinations of just two axes
(cn, pu). The skew, local-σ, and mobility axes this study covers do not appear
in the corner definition at all. Yet the variance-based sensitivity analysis of
§7 finds that **NMOS local-σ is the third-largest contributor to Vmin variation
(Sobol ST = 0.199), ahead of PG−PD Vth skew (0.108)** — an axis corner sign-off
never looks at. PG-PD skew itself moves Vmin by roughly **2.8 mV per mV**, a
swing of about **114 mV** across a ±20 mV range: more than twice the entire
50 mV margin budget, moving outside the corner definition.

**Second, direction.** Corner simulation answers only the forward question,
"what is Vmin here?" What process and design actually ask runs the other way:

> "Which variation combinations violate the spec?"
> "To get back inside, which parameter must be tightened, and by how much?"
> "How much PG-PD skew can we tolerate?"

These are **inverse** questions, and a handful of corner points reveals neither
the location nor the shape of the boundary.

### 1.4 What This Paper Does

We build a **surrogate pipeline that answers both forward and inverse queries
from a single fixed simulation budget**, and validate it on
production-calibrated data from an advanced FinFET node. In process terms:

1. **Train once, then no further simulation.** Vmin at any condition is
   predicted instantly, and the spec boundary — the allowable process window —
   is traced directly by gradient descent.
2. **A quantitative ranking of which parameters to tighten**, at no additional
   simulation cost (§7) — which reveals that **NMOS local-σ ranks third, ahead
   of PG−PD Vth skew, despite being an axis corner sign-off never examines.**
3. **Evidence for shrinking the simulation budget itself**, along all three
   axes: voltage levels, condition count, and MC per condition (§6).
4. **Quantification of a systematic optimism inherent in the current sign-off
   metric** (§2.4). Its magnitude is comparable to the entire 50 mV margin
   budget, which means it — not surrogate accuracy — may be the dominant error.

`[Fig 1 — Pipeline overview: variation parameters → GP(μ,σ) → physics layer →
Vmin, with forward and inverse arrows]`

---

## 2. The Target and the Metric

### 2.1 Read Stability (SNMR)

Read stability of a 6T cell is evaluated by the SNM, the minimum of the two
butterfly-curve lobes; the primary metric here is read SNM (SNMR). MC produces
an SNMR distribution from thousands of samples per condition, and conventionally
records its **mean μ and standard deviation σ**.

> The write metric (Vtrip) is treated separately in §9.3. The methodology is
> metric-agnostic, and Vtrip is in fact better behaved — its monotonicity in
> voltage is cleaner than SNMR's.

### 2.2 Vmin Definition and Yield Target

For condition x we compute **z(Vop) = μ/σ** over the voltage grid and linearly
interpolate the voltage at which it crosses the target z-score **Z_t**; that
voltage is Vmin(x).

Z_t is derived **by calculation** from array yield. For 256 Mb at 99% Poisson
yield:

```
p_fail = −ln(0.99) / (256 × 10⁶) ≈ 3.9 × 10⁻¹⁰
Z_t    = Φ⁻¹(1 − p_fail) ≈ 6.50
```

The failure unit is the cell (bit); multiplying by six transistors is incorrect.

> **Caution — two distinct reference lines.** Z_t = 6.50 is the yield criterion
> that enters the *definition* of Vmin; the 0.625/0.675 V of §1.1 is the spec
> that decides whether the resulting Vmin *passes*. They are set independently
> and must not be conflated. **That Z_t is a calculated value rather than a
> silicon-calibrated one is decisive for the discussion in §2.4.**

### 2.3 The Region of Interest — the Spec Sets the Voltage Range

We do not need Vmin everywhere. Only the neighbourhood of the spec actually
contributes to a decision, and that fact governs the entire experimental design.

- **Vmin < 0.4 V** (left-censored): passes with comfortable margin; the exact
  value changes no decision.
- **0.4 V ≤ Vmin ≤ 0.7 V**: **where the verdict is decided.** Both spec points
  (0.625/0.675 V) live here. This is the only region needing accuracy.
- **Vmin > 0.7 V** (right-censored): already far outside EOL spec. It only
  needs to be classified as "fail"; the exact value is unnecessary.

We therefore use the voltage grid **{0.4, 0.5, 0.6, 0.7} V** — not because data
is unavailable above it, but because **this is the minimal interval that
brackets the spec**. The 0.7 V ceiling is simultaneously the most we can cut
and the least the spec permits: bracketing the EOL spec at 0.675 V by
interpolation requires 0.7 V, and a 0.6 V ceiling would make 0.675 V an
extrapolation. Quantitative justification is in §6.1.

Conditions censored on either side are excluded from continuous error metrics;
only their classification is used.

### 2.4 A Systematic Optimism in the Current Metric — Size and Handling

**One issue must be stated plainly here.** SNMR is the **minimum** of two lobes,
and the minimum of two Gaussians is not Gaussian — its left tail is fatter. Yet
z = μ/σ fits a Gaussian to that minimum and extrapolates to 6.5σ, and therefore
**systematically underestimates the failure probability**.

Intuitively: imagine two students sitting the same exam, where failure means
**either one** of them fails. Even if each individually has a low chance of
failing, the chance that at least one does is higher. A read failure works the
same way — only one lobe has to collapse — so the true failure rate is always at
least as large as what a Gaussian fitted to the minimum suggests.

The size depends on the lobe correlation ρ_LR: **+0.7σ** if independent, up to
**+1.9σ** if anticorrelated. Converted through the measured spec-band slope
**dz/dVop ≈ 13.2 /V**:

| Assumption | z bias | **Vmin optimism** | EOL pass rate |
|---|---|---:|---|
| No bias | 0 | — | 88.5% |
| Independent lobes | +0.7σ | **≈ 53 mV** | 80.5% (−8.0 pp) |
| Anticorrelated lobes | +1.9σ | **≈ 144 mV** | 63.0% (−25.6 pp) |

**Even under the most optimistic assumption, 53 mV exceeds the entire 50 mV
T0→EOL margin budget.** Set against a surrogate Vmin accuracy of 9–13 mV
(§5.2), the dominant error may lie in the metric rather than the model.

**The structure of this DOE offers no relief.** All nine parameters are
device-type-level (PG/PD/PU) global knobs and **do not break the cell's
left-right symmetry** (PG-left and PG-right move together). The two lobes are
therefore statistically identical in every condition — precisely the
configuration in which the minimum-statistics bias is **maximal**. There is no
subset of conditions that is naturally asymmetric and therefore safe.

**How this paper handles it.** Given per-lobe statistics (μ_L, σ_L, μ_R, σ_R,
ρ_LR) the exact failure probability is available in closed form:

```
p_fail = P(L<0) + P(R<0) − P(L<0, R<0),   Z_eff = Φ⁻¹(1 − p_fail)
```

The joint term is the bivariate-normal CDF (Owen's T), smooth and
differentiable in all inputs, so it passes through the pipeline unchanged.
**However, the MC output of this batch contains only the μ and σ of the
minimum, so this correction has not been applied to the real data.** Every
figure in this paper uses z = μ/σ, consistent with current practice.

To pin down the actual magnitude, a **tail-shape diagnostic on conditions near
the spec boundary** is underway
(`docs/plans/infab_tail_diagnostic_request.md`): 100,000 MC runs measure the
distribution's tail directly and determine whether it matches a Gaussian or a
minimum-of-two-Gaussians. Result: `[TBD]`.

**Crucially, this correction requires no re-simulation.** The bias affects only
the threshold in the (μ, σ) → Vmin transform, so once measured it is applied to
existing data by post-processing with Z_t → Z_t + z_bias. Consequently the
*relative* conclusions of §5–§7 (sensitivity ranking, contour shape, skew
tolerance, corner ordering) hold regardless; what shifts is absolute Vmin and
the spec pass rates.

---

## 3. Experimental Design

### 3.1 Input Space

| Variable | Meaning | Range | Unit |
|---|---|---|---|
| cn | NMOS common Vth shift (PG=PD baseline) | ±60 | mV |
| sk | PG−PD Vth skew | ±20 | mV |
| pu | PMOS Vth shift | ±60 | mV |
| lpu | PU local-σ multiplier | [0.7, 1.3] | ratio |
| l_com | NMOS local-σ common | [0.7, 1.3] | ratio |
| l_sk | NMOS local-σ PG-PD skew | ±0.075 | ratio |
| mpu | PU mobility multiplier | [0.7, 1.3] | ratio |
| m_com | NMOS mobility common | [0.7, 1.3] | ratio |
| m_sk | NMOS mobility PG-PD skew | ±0.075 | ratio |

Deck parameters derive as: Vth PG = cn+sk, PD = cn−sk; local-σ PG = l_com+l_sk,
PD = l_com−l_sk; mobility likewise.

### 3.2 Rationale for the Common+Skew Parameterization

PG and PD are the same NMOS flavor, so they **share** their dominant variation
sources (gate stack, channel doping, anneal, litho CD), with W/L and layout
environment producing imperfect tracking. Sampling the two devices independently
would spend design points on states **that do not occur in silicon** — the same
flavor diverging by ±30% in opposite directions at the mismatch level.

The common+skew decomposition implies `corr(l_PG, l_PD) ≈ 0.88`, inside the
plausible same-flavor tracking band (0.85–0.95) and consistent with the Vth
structure (ρ ≈ 0.80). Common and skew are sampled **independently**, a property
required by the variance-based sensitivity analysis of §7.

`[Fig 2 — (a) quadrant weighting in the (cn, pu) plane; (b) independent
(l_com, l_sk) box and the induced diagonal (l_PG, l_PD) band]`

### 3.3 Quadrant-Weighted Design of Experiments

Read and write degrade in different worst-case quadrants — SNMR at FSG
(cn<0, pu>0), Vtrip at SFG (cn>0, pu<0). We therefore use separate deck sets
per metric with different quadrant weights:

| Metric | FSG | FN | SN | SFG |
|---|---|---|---|---|
| SNMR | 45% | 20% | 15% | 20% |
| Vtrip | 10% | 15% | 30% | 45% |

This raises resolution in the worst-case region by 2–4× at the same 2,000
conditions. Conditions are generated by deterministic PCG64 draws with an
independent stream per quadrant.

> **Scope of results in this paper.** Both deck sets were designed and
> generated, but at the time of writing only the **SNMR set** has completed
> result transcription. The Vtrip set is being transcribed now; related figures
> are cited in §7.4 and §9.3 from the 4-D Stage-C batch as reference only. The
> integrated read/write verdict will be produced through the same pipeline once
> Vtrip transcription completes.

> An earlier plan assumed stratified Sobol sampling would outperform random
> draws. Our own validation did not support this on either the uniform or the
> corner metric, and **the claim is retracted** (§6.2). The gain in this design
> comes from quadrant weighting, not from the sampling sequence.

### 3.4 Voltage Grid

Following §2.3 we use **four levels, {0.4, 0.5, 0.6, 0.7} V**; quantitative
justification is in §6.1. MC per condition is 5,000, and per-condition standard
errors are recorded alongside for the noise-aware GP of §4.5.

### 3.5 A Transcription-Free Protocol

Simulations run inside a fab from which neither decks nor raw results can be
exported. Because condition generation is deterministic, sharing only
**(stage, n_cond, seed, metric, method)** makes the fab-side deck loop and the
model-side condition table byte-identical. Results return labelled only by
(Vop, deck number), and **no condition coordinate is ever transcribed by hand.**

In a pilot where conditions *were* hand-transcribed, the row error rate was
about 9%. This protocol is a data-integrity requirement, not a convenience.

> Transcription of result values nevertheless remains. In this batch automatic
> QC caught 22 digit-slip errors (3 unparseable, 19 out-of-range). We recommend
> keeping physically-motivated range QC permanently in the parser.

### 3.6 A Design Pitfall: Mirror-Twin Leakage

An early pilot reused one QMC stream across all four quadrants, flipping only
the signs of cn and pu. As a result **75% of conditions** had a mirror twin
sharing the remaining seven coordinates, and under a random hold-out about
**74% of test conditions** had a twin in training — silently inflating accuracy.

We found this by forensic comparison of transcribed conditions against the
reconstructed generator, then (i) removed the cause with an independent stream
per quadrant and (ii) enforced mirror-group splits for any evaluation touching
legacy data. Because design-induced leakage inflates metrics without any
implementation bug, **surrogate-validation studies should report their design
generation code and split rule together.**

---

## 4. Method

### 4.1 GP Surrogate

A **Gaussian Process (GP)** estimates a function from finite data while also
reporting **how much it trusts each prediction**. It is a regression that fits a
surface, but unlike ordinary fitting it expresses "I have no data near here, so
I am unsure."

- Input: 9-D variation parameters + voltage
- Output: SNMR statistics (μ, σ)
- Why it suits us: works with limited data, quantifies uncertainty, and is
  **differentiable** — which is what makes inversion possible.

The **μ GP** uses a Matern-5/2 kernel with ARD. A *lengthscale* answers "how far
must I move this input before the output changes appreciably?" — short means
sensitive, long means insensitive. ARD learns one per axis from data, so the
fitted lengthscales are themselves a **coarse sensitivity ranking** (§7).

The **σ GP** uses an additive kernel separating the voltage group from the
device-variation group.

### 4.2 Input Standardization

With mV, V, and dimensionless multipliers in one input vector, omitting
standardization causes **silent under-convergence**. Most of what our early
experiments attributed to physics constraints turned out to be this fix (§5.6).
All inputs are standardized with training statistics. This is not cosmetic
preprocessing — it changed conclusions.

### 4.3 Differentiable Physics Layer

The layer converting (μ, σ) into Vmin is an **analytic constraint with no
learnable parameters**:

```
1. predict (μ, σ) at the four voltages for each condition
2. compute z(Vop) = μ/σ
3. linearly interpolate the voltage where z crosses Z_t  →  Vmin(x)
```

Interval selection is discrete, but the first derivative is well defined inside
each interval, so the whole pipeline is differentiable in its inputs — the
premise for §4.6. Censored conditions are flagged out.

### 4.4 Physics Constraints

1. **Corner anchoring** — virtual observations at the four global corners are
   added to training. This tells the GP "you already know the answer at these
   extremes; do not drift away because the fit elsewhere pulls you," the way a
   cartographer pins a map to surveyed landmarks. Under an exact GP it acts as
   a hard constraint.
2. **Monotonicity penalty** — discourages the fitted surface from predicting
   that raising the supply makes the cell less stable on average, a behaviour
   real cells do not show. Inert on monotone data.
3. **Pelgrom linear trend** — weak regularization toward a linear σ(Vop) trend,
   using decades of established mismatch-measurement behaviour instead of asking
   2,000 conditions to rediscover it.

Contributions are isolated in §6.2.

### 4.5 Noise-Aware GP — Why MC per Condition Can Be Reduced

Per-condition bootstrap standard errors enter a FixedNoise likelihood. It is
like combining opinion polls of different sizes: a condition backed by many
samples is automatically trusted more, one backed by few is trusted less, and no
separate correction term is needed for the small ones.

This connects directly to budget allocation. Because the GP **borrows
statistical strength from neighbouring conditions** in the 9-D space, no single
condition needs an expensive high-MC batch to be trustworthy on its own — the
surrounding design space effectively vouches for it. A fixed budget can
therefore be spent covering **more distinct conditions** rather than
over-sampling a few (§6.3).

### 4.6 Gradient Inversion — Finding the Allowable Process Window

For a target spec voltage V*, the set {x : Vmin(x) = V*} is a boundary surface
in the 9-D variation space — **the edge of the allowable process window**. We
locate it directly by gradient descent.

It is like descending a foggy hillside toward a target elevation by feel: the
gradient indicates the steepest direction, Adam converts that into a stable step
size, and a sigmoid reparameterization fences every step inside physically
realistic variation ranges.

1. treat x as a leaf tensor under a sigmoid box reparameterization
2. minimize (Vmin(x) − V*)² with Adam
3. verify convergence from multiple starting points
4. cross-check each converged point against a 1-D bisection on its slice

Unlike grid search, cost does not explode with dimension. Even in 2-D (cn, pu) a
50×50 grid needs 2,500 MC runs; in 9-D it is simply infeasible.

---

## 5. Validation: Can This Model Be Trusted?

From a process standpoint the first question about a surrogate is not its error
figure but **whether it reproduces the physics**. We present it in that order.

### 5.1 Protocol

Condition-level splitting (all voltage rows of a condition stay on one side),
15% hold-out. This batch contains no mirror twins by construction, so
condition-level splitting suffices; every evaluation referencing legacy pilot
data uses mirror-group splits. Vmin errors are reported on the non-censored set
with the censoring rate alongside.

### 5.2 Forward Accuracy

2,000 conditions × 4 voltages, noise-aware GP, condition-level hold-out:

| Metric | Value |
|---|---|
| μ coefficient of determination R² | **0.9817** (RMSE 5.35 mV) |
| σ coefficient of determination R² | **0.9845** (RMSE 0.22 mV) |
| Vmin RMSE (hold-out) | **13.50 mV** |
| Vmin RMSE (**spec region**, Vmin ≤ 0.7 V) | **9.14 mV** |

In the spec region — where the verdict is actually decided — the error is
**9.14 mV**, about one fifth of the 50 mV margin budget. Surrogate error does
not drive the sign-off decision. (Note that the systematic bias of §2.4 is a
separate and larger quantity.)

`[Fig 3 — predicted vs measured scatter (μ, σ), hold-out]`

### 5.3 Physical Consistency

| Check | Expected | Measured | Verdict |
|---|---|---|---|
| PG dominance | ℓ_cn < ℓ_pu | ℓ_pu/ℓ_cn = **1.083** | ✅ |
| Vth direction | ∂Vmin/∂cn < 0 | negative | ✅ |
| PMOS direction | ∂Vmin/∂pu > 0 | positive | ✅ |
| Worst read corner | FSG | FSG confirmed | ✅ |
| Voltage sensitivity | shortest Vop lengthscale | shortest (5.17) | ✅ |

The PG-dominance hierarchy reproduces across Stage A (1.08), the 4-D Stage B
batch (1.14), and now 9-D — consistent across three independent batches. That is
evidence the model captured device physics rather than memorizing data.

### 5.4 Reproducing the Spec Verdict

The real sign-off query is not "what exactly is Vmin" but "does it pass?" On 300
hold-out conditions:

| Spec | pass/fail agreement | Misclassification | z-margin RMSE |
|---|---|---|---|
| T0 (0.625 V) | **295/300 (98.3%)** | FP 4, FN 1 | 0.573 |
| EOL (0.675 V) | **298/300 (99.3%)** | FP 1, FN 1 | 0.322 |

FP denotes predicted-pass but actually-fails (the optimistic error). At the
binding EOL criterion there is a single FP (0.3%), which supports using the
surrogate for sign-off screening.

**Population (2,000 conditions):** T0 pass 81.2%, EOL pass 88.5%, EOL fail
11.4%. (These are subject to uniform correction once §2.4 is settled.)

### 5.5 Vmin Contours and the Process Window

`[Fig 4 — Vmin contours in the (cn, pu) plane: GP vs hold-out MC overlay with
the four corner points]`
Hausdorff distance at the target level: `[TBD]` mV.

### 5.6 Gradient Inversion Verification

On the analytic testbed all eight starting points converged to the target
manifold (max |Vmin − target| = 2.41 mV), and every converged point matched a
1-D bisection on its slice to four decimal places. Real-data reproduction:
`[TBD]`.

`[Fig 5 — inversion trajectories: multi-start gradient paths with the target
contour]`

### 5.7 External Validation

A 4-D batch (348 conditions, nominal multipliers) designed and executed
independently of this one provides measured points on the (l=m=1, skew=0) plane
of the 9-D space. Agreement between the 9-D model projected onto that plane and
the 4-D measurements directly tests generalization on a plane outside the
training draw: `[TBD]`. Because the 4-D batch is a pilot-generation design, its
own metrics are recomputed under mirror-group splits.

---

## 6. Cost: What Can Be Reduced, and by How Much

The simulation budget factors into three axes — **voltage levels × condition
count × MC per condition**. We give evidence for each.

### 6.1 Voltage Levels: 0.8 V Is Unnecessary (20% Saving)

Both spec voltages, 0.625 V and 0.675 V, lie **inside the [0.6, 0.7] interval**,
so z(V_spec) is linearly interpolated from the 0.6 V and 0.7 V points alone.
**The 0.8 V level cannot structurally participate in the verdict.** Measured
confirmation:

| Spec | verdict agreement, 0.4–0.7 V vs 0.4–0.8 V grid | max\|Δz\| |
|---|---|---|
| T0 (0.625 V) | **2000/2000 (100%)** | **0.00e+00** |
| EOL (0.675 V) | **2000/2000 (100%)** | **0.00e+00** |

Δz is exactly zero — this is structural necessity, not empirical approximation.

A GP trained only on 0.4–0.7 V also reproduces the spec verdict (§5.4) and
matches on spec-region Vmin RMSE at 9.14 mV; adding 0.8 V moves μ R² only from
0.9817 to 0.9834. The 90 conditions that 0.8 V newly resolves all have
Vmin > 0.7 V — **already outside EOL spec and therefore out of interest**.

**Conclusion: five voltage levels → four, a 20% budget saving for this metric.**
Note that 0.7 V is a floor, not a target for further cutting (§2.3).

### 6.2 Condition Count: the Budget–Accuracy Knee

Subsampling the training set to size N and refitting traces a budget–accuracy
curve (analytic testbed, 10 redraws per size):

| N | Vmin RMSE (mV) | Contour Hausdorff (mV) |
|---|---|---|
| 50 | 5.13 ± 1.84 | 1.62 ± 0.64 |
| 100 | 3.90 ± 0.50 | 1.30 ± 0.29 |
| 200 | 3.21 ± 0.77 | 1.00 ± 0.42 |
| 400 | 2.01 ± 0.26 | 0.76 ± 0.14 |
| 800 | 1.40 ± 0.15 | 0.54 ± 0.15 |

Gains are steep at first, then pass a **knee around N ≈ 400** beyond which
returns diminish. That point turns "how many MC batches should we run" from a
guess into a defensible decision.

**The physics constraints likewise concentrate at low budget.** Corner anchoring
significantly improves corner-neighbourhood Vmin RMSE at low N (≤100)
(pooled −1.29 mV, p < 1e-6), with the effect vanishing as N grows. On the
**domain-average metric the effect is small and unstable**, so the claim must be
stated with its metric attached. On the analytic testbed, baseline 1.26 mV →
corner anchoring 0.92 mV (−27%), with p95 −37%.

> Methodological lesson: the hold-out design itself determines the conclusion.
> A uniform hold-out measures "a model that is good on average"; a corner
> hold-out measures "a model that is good where safety margin matters." These
> are different questions. Report both.

`[Fig 6 — budget–accuracy Pareto: condition count × (Vmin RMSE, Hausdorff)]`

### 6.3 MC per Condition

The noise-aware GP of §4.5 takes per-condition standard errors explicitly and
down-weights low-budget conditions automatically. Because strength is borrowed
from neighbouring conditions, no individual condition needs high confidence on
its own, which justifies allocating budget to **breadth over depth**. The same
mechanism unifies heterogeneous MC budgets in one model: when low fidelity is
merely fewer samples from the same simulator, a heteroscedastic single GP is the
correct model and no separate bias term is required.

### 6.4 Summary

| Axis | Conventional | This work | Basis |
|---|---|---|---|
| Voltage levels | 5 | **4** | §6.1 (spec-driven, lossless) |
| Condition count | chosen by feel | **chosen at the knee** | §6.2 |
| MC per condition | uniform | **heterogeneous allowed** | §6.3 |
| Inverse queries | extra grid-search MC | **zero additional runs** | §4.6 |

The largest saving is the last row: once trained, both forward and inverse
queries are served without any further simulation.

---

## 7. Sensitivity: Which Parameters Should Be Tightened

This is the most directly actionable output for a process owner — **of the nine
variation sources, which actually move Vmin and which can be controlled more
loosely.**

We use two tools together.

**ARD lengthscales (essentially free).** The GP already learns one per dimension
while fitting, so reading them off costs nothing. Their limitation is that they
are a property of *the fitted model*, not of *the data*: they distort when
inputs are correlated (which is exactly why common and skew are sampled
independently, §3.2), and they do not separate a standalone effect from an
interaction effect.

**Sobol indices (rigorous, but normally expensive).** These answer "if every
input but one were held fixed, how much of the Vmin spread would disappear?"
Computing them exactly typically needs tens of thousands of function
evaluations, which is why variance-based sensitivity analysis is rarely applied
to circuit-level yield studies. **With a surrogate the situation changes** —
evaluating the trained GP takes milliseconds rather than minutes of circuit
simulation, so tens of thousands of queries ride essentially free on top of the
budget that trained it. The cost of the forward/inverse pipeline **also buys a
statistically rigorous sensitivity study.**

We report both side by side because their agreement is itself informative: where
they agree the ranking is trustworthy from two independent angles; where they
disagree, they point to an input pair whose correlation or interaction deserves
a closer look.

### 7.1 Results — Final Batch (2,000 conditions, 0.4–0.7 V)

**ARD lengthscales** (standardized-input scale; shorter = more sensitive):

| Rank | Axis | ℓ | | Rank | Axis | ℓ |
|---|---|---|---|---|---|---|
| 1 | Vop | 5.185 | | 6 | l_com | 8.173 |
| 2 | **cn** | 7.405 | | 7 | m_sk | 8.177 |
| 3 | **pu** | 7.945 | | 8 | mpu | 8.186 |
| 4 | sk | 8.056 | | 9 | l_sk | 8.196 |
| 5 | m_com | 8.114 | | 10 | lpu | 8.213 |

ℓ_pu/ℓ_cn = **1.073**, reconfirming the PG-dominance hierarchy (consistent with
1.083 from the hold-out-trained model of §5.3).

**Sobol indices** (GP-based, N=1024 base → 11,264 surrogate evaluations):

| Axis | S1 (first) | ST (total) | Reading |
|---|---:|---:|---|
| **cn** | 0.388 | **0.464** | dominant — NMOS common Vth |
| **pu** | 0.212 | **0.298** | second — PMOS Vth |
| **l_com** | 0.157 | **0.199** | **third — NMOS local-σ** |
| sk | 0.121 | 0.108 | PG−PD Vth skew |
| lpu | 0.032 | 0.039 | PU local-σ |
| m_sk | 0.007 | 0.024 | interaction-driven (ST/S1 ≈ 3.3) |
| m_com | 0.021 | 0.021 | negligible |
| mpu | 0.008 | 0.014 | negligible |
| l_sk | 0.004 | 0.001 | **negligible** |

Var[Vmin] = 8.94×10⁻³ V² (sd **94.5 mV**); ΣS1 = 0.948 → **near-additive**
(interactions are weak).

### 7.2 Where the Two Metrics Disagree — and What That Tells Us

**The top two (cn > pu) agree between the metrics.** They part company at rank
three: ARD ranks sk (8.056) as more sensitive than l_com (8.173), whereas
**Sobol places l_com (ST 0.199) roughly twice as high as sk (0.108).**

A more fundamental problem is visible. **ARD lengthscales have almost no
discriminating power on this problem.** Sobol ST spans 0.001–0.464, a range of
about 400×, while the ARD lengthscales are compressed into 7.41–8.21, a range of
only 1.1×. Even allowing that sensitivity enters the kernel roughly as 1/ℓ²,
that is a factor of 1.23 — nowhere near expressing a 400× difference in actual
variance contribution.

The cause is not certain, but with 2,000 conditions spread over nine dimensions
the individual per-axis lengthscales appear not to be sharply identifiable (a
known difficulty for multi-dimensional Matern ARD). Whatever the mechanism, the
practical implication is unambiguous:

> **On this problem the sensitivity ranking must be read from Sobol indices, not
> from ARD lengthscales.** ARD remains useful as a qualitative check on large
> hierarchies such as PG≫PU, but it is unfit for quantitatively deciding which
> parameter to tighten.

This also **re-confirms the value of the surrogate** stated at the top of §7: the
free signal (ARD) failed to answer the question, and the signal that did answer
it (Sobol) would have required tens of thousands of circuit simulations without
a surrogate. The surrogate is the only reason this analysis was possible.

### 7.3 Conclusions in Process Terms

1. **Vth dominates** — cn (0.464) plus pu (0.298) account for most of the
   total-order budget, with NMOS common Vth the single largest factor.
2. **local-σ ranks third, above PG−PD Vth skew** (l_com 0.199 vs sk 0.108).
   **This is an axis corner-based sign-off misses entirely** — corners are
   extreme combinations of (cn, pu) and never touch local-σ. Controlling local
   mismatch is a higher priority than controlling skew, which is one of the
   practically useful findings of this work.
3. **All mobility axes are minor** (mpu/m_com/m_sk all ST < 0.025). For read
   Vmin, mobility-variation control is lower priority than Vth and local-σ.
4. **l_sk is negligible** (ST 0.001): PG−PD asymmetry in local-σ makes no
   material contribution to read Vmin, which is evidence that its control
   specification could be relaxed. m_sk is small in absolute terms but operates
   **only through interaction** (ST/S1 ≈ 3.3) — answering the second question
   posed at the head of §7.
5. **Behaviour is near-additive** (ΣS1 = 0.948). Weak interaction means
   axis-by-axis control is broadly valid — provided local-σ is on the list of
   axes being controlled.

### 7.4 PG-PD Skew Tolerance (Final Batch)

Skew sweeps at nominal multipliers (l = m = 1) for representative operating
points:

| Operating point | Vmin(sk=0) | Swing (±20 mV) | dVmin/dsk |
|---|---:|---:|---:|
| TT (0, 0) | 470.3 mV | 114.2 mV | −2.80 mV/mV |
| mild-FSG (−30, +30) | 586.3 mV | 120.8 mV | −2.76 mV/mV |
| mild-SFG (+30, −30) | 350.0 mV | 104.8 mV | **−7.13 mV/mV** |
| FFG-ish (−30, −30) | 475.2 mV | 119.1 mV | −2.84 mV/mV |
| SSG-ish (+30, +30) | 470.5 mV | 112.1 mV | −2.81 mV/mV |

Positive skew (slower PG) stabilizes the read, with a slope near −2.8 mV/mV at
most operating points. **Near SFG the slope steepens to −7.13 mV/mV**, over 2.5×,
so the same skew excursion produces a much larger Vmin movement there.

**Allowable skew window against the spec:**

| Spec | TT | mild-FSG | mild-SFG | FFG | SSG |
|---|---|---|---|---|---|
| T0 (0.625 V) | full | **[−11, +20]** | full | full | full |
| EOL (0.675 V) | full | full | full | full | full |

**At the EOL spec every representative operating point tolerates the full
±20 mV range.** Only under the tighter T0 criterion does mild-FSG become
constrained, requiring sk ≥ −11 mV. The current ±20 mV skew control
specification is therefore adequate at nominal multipliers.

> **Caveat.** These sweeps hold multipliers at nominal. Since §7.1 identifies
> l_com as the third-ranked factor, the allowable skew window may narrow at high
> local-σ. A joint (sk, l_com) sweep is required before finalizing a skew spec.

`[Fig 7 — grouped sensitivity: ARD-based vs Sobol indices side by side, plus the
allowable skew window]`

---

## 8. Limitations

1. **Systematic optimism of the min-statistics z (§2.4).** The largest open
   uncertainty in this work. Estimated at +0.7σ (≈53 mV) to +1.9σ (≈144 mV),
   comparable to the entire 50 mV margin budget. A diagnostic is underway and
   the correction is applicable by post-processing. **Absolute Vmin values and
   spec pass rates in this paper are pre-correction.**
2. **The Gaussian extrapolation itself.** z = μ/σ is an industry-standard margin
   metric, not an absolute fail-rate predictor. That each lobe is Gaussian out
   to 6σ is a separate assumption; the tail diagnostic of §2.4 tests both at
   once.
3. **Scope.** One node, one cell topology, primarily the read metric. Write
   integration is discussed in §9.3.
4. **Multiplier spill band** [0.625, 0.7) ∪ (1.3, 1.375] sits at the edge of
   compact-model calibration; predictions there should be read conservatively.
5. **Spec dependence.** The voltage-reduction conclusion of §6.1 is contingent on
   the 0.625/0.675 V spec. If the IR-drop budget changes such that the spec
   exceeds 0.7 V, it must be revisited.
6. **Reproducibility.** The PDK is proprietary, so absolute values are not
   reproducible. We release the analytic testbed in full and report
   normalized-axis results alongside.

---

## 9. Recommendations

### 9.1 Simulation Planning
- **Let the spec set the voltage levels.** Simulate only the minimal interval
  that brackets the spec — currently four levels, 0.4–0.7 V, which is both the
  maximum cut and the minimum requirement.
- **Choose condition count at the budget–accuracy knee.** Past it, additional
  HSPICE hours are better spent on depth near the boundary or on a different
  design corner than on more breadth.
- **MC per condition need not be uniform.** Recording standard errors lets
  heterogeneous budgets coexist in one model.

### 9.2 Data Collection (Important)
- **Make tail-shape diagnostics routine on a few near-spec conditions.** Fewer
  than ten conditions, under 2% of the budget, closes the largest open
  uncertainty in §2.4.
- **Record per-lobe statistics, or at least skewness and low quantiles, where
  possible.** The μ and σ of a minimum contain no information about tail shape,
  as a matter of principle.
- **Keep physically-motivated range QC on result transcription permanently.**
  This batch alone contained 22 digit-slip errors, and such values destroy the
  surrogate outright (μ R² = −0.41 before correction).

### 9.3 Next Steps
- **Extend to Vtrip.** The methodology is metric-agnostic, and Vtrip's
  monotonicity in voltage is cleaner than SNMR's, making interpolation more
  stable. The spec voltages sit inside [0.6, 0.7] identically, so the
  voltage-reduction argument of §6.1 carries over — though confirmation with the
  same scripts after transcription is recommended.
- **Integrated read/write verdict.** Combining the two metrics by smooth-max
  yields a saddle-shaped surface high at both FSG (read) and SFG (write).
  **Read alone favours positive skew (§7.4), but write moves the opposite way** —
  on the Stage-C 4-D batch the combined worst case was minimized near
  sk* ≈ −2 mV, essentially symmetric. That figure has not been reproduced on the
  final batch (the Vtrip sheet is not yet transcribed) and should be recomputed
  in 9-D with the same scripts once it is. The directional conclusion —
  **do not set a skew specification from the read metric alone** — is firm.
- **Joint (sk, l_com) sweep.** The skew windows of §7.4 hold multipliers at
  nominal. With local-σ identified as the third-ranked factor, the joint effect
  must be checked before a skew specification is finalized.
- **Silicon correlation.** Since Z_t is a calculated value, the §2.4 bias is
  ultimately best closed by correlating against measured silicon Vmin
  distributions.

---

## 10. Conclusion

We built a pipeline that serves both forward and inverse SRAM Vmin queries from
a single fixed simulation budget, and validated it on production-calibrated data
from an advanced node (2,000 conditions × 4 voltages).

Conclusions in process terms:

1. **The surrogate is usable for sign-off screening.** Spec-region Vmin RMSE of
   9.14 mV (one fifth of the margin budget), 99.3% agreement on the EOL spec
   verdict, and physical consistency — PG≫PU hierarchy, gradient directions,
   worst-corner identity — reproduced across three independent batches.
2. **The simulation budget can be cut, and the justification comes from the
   spec.** A 20% voltage-level reduction is available at no loss; this is not
   "truncating for lack of data" but actively simulating only the interval that
   informs a decision.
3. **Inverse queries open up at no additional simulation cost.** The allowable
   process-window boundary, skew tolerance, and parameter priorities all come
   directly out of the trained model. This established that **NMOS local-σ is
   the third-largest contributor to Vmin variation, ahead of PG−PD Vth skew** —
   an axis corner-based sign-off structurally cannot see, and an analysis that
   would have required tens of thousands of circuit simulations without a
   surrogate.
4. **The largest uncertainty lies in the metric, not the model.** The systematic
   optimism of the min-statistics z is estimated at 50–144 mV, comparable to the
   entire margin budget. However precisely the model is built — 9 mV here — this
   bias dominates if left standing. **That finding is as important as the
   methodological contributions, and it can be closed for under 2% of the total
   budget.**

---

## Appendix A. Metric Definitions
Formal definitions of design-range feasibility agreement, two-sided censoring
handling, and assist-active scoring, including the reproduction table for the
~60× gap a naive metric reports on identical predictions (0.16 V vs 2.6 mV).

## Appendix B. Reproducibility Contract
Condition-generator version, seed, quadrant weights, ranges, and deck numbering
convention. Full analytic-testbed code released.

## Appendix C. Derivation of the Lobe-Resolved Effective z-Score
Closed-form derivation of Z_eff summarized in §2.4, the Owen's T computation,
verification of differentiability, and synthetic-data validation results.

## Appendix D. Plain-Language Glossary

| Term | Plain-language meaning |
|---|---|
| Gaussian Process (GP) | A way of fitting a surface that also reports how confident it is in each prediction |
| Kernel / lengthscale | The GP's internal notion of how far apart two inputs must be before their outputs are unrelated |
| ARD | Learning a separate lengthscale per input dimension, so the model can tell which inputs matter |
| Noise-aware likelihood | Telling the model how reliable each individual data point is |
| Corner anchoring | Adding known reference points to training so the model cannot drift away from them |
| Gradient inversion | Walking straight toward a target using slope information instead of trial and error |
| Hausdorff distance | The **worst-case** gap between two curves, not the average |
| Sobol index | The share of an output's variability attributable to each input |
| Left/right censoring | A condition whose value lies outside the observed range, so only "below/above X" is known |
| Owen's T | Closed-form probability that two correlated Gaussians are simultaneously below a threshold |
