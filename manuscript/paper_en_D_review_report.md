# Manuscript Review Report — paper_en_D

## Overall assessment

The manuscript has a strong device/process-facing core: **a physics-constrained surrogate predicts the margin statistics, keeps the Vmin definition analytic, and therefore supports an axis-wise inverse query and direct Vmin-boundary extraction.** The numerical results are substantial and the manuscript contains unusually good reviewer-facing validation and limitations.

However, the current draft is **not yet optimal for an IEEE/VLSI device/process audience**. The main issue is not that GP/Sobol/censoring/bootstrap are insufficiently explained; it is that the manuscript sometimes explains them at textbook length while the central device result is diluted by the long Section VI on non-Gaussian SNM tails. Several statements also overclaim mathematical guarantees. These are fixable without changing the underlying results.

## Priority 1 — Core thesis / scope

### 1. The paper currently has two competing stories

The title and Sections I–V establish:
- fixed-budget SRAM Vmin surrogate;
- forward prediction;
- inverse process-coordinate recovery;
- direct Vmin boundary extraction;
- corner incompleteness through global sensitivity.

Section VI then introduces a second, very large story:
- SNM is a minimum of two lobes;
- Gaussian-tail approximation is biased;
- lobe correlation is inferred;
- the resulting correction is ~70 mV and changes the sign-off decision.

For a device/process reviewer, Section VI is scientifically interesting, but its scale makes it look like the **real contribution**. This risks the reviewer asking whether the paper is actually about surrogate modeling or about the validity of the Gaussian SNM tail approximation.

### Recommended fix

Keep Section VI, but explicitly demote it to a **secondary diagnostic finding**. The paper's primary contribution should remain:

> A physics-constrained surrogate of margin statistics enables both forward and inverse Vmin analysis from a fixed MC budget, while exposing variation axes that corner analysis cannot observe.

The revised abstract and conclusion should mention the tail result as an important limitation/diagnostic, not as an equal third contribution.

## Priority 2 — Mathematical claims that should be softened

### 2. “Guaranteed monotonicity” is too strong

The current text says the analytic layer “guarantees” monotonicity. The actual model constrains μ(Vop), while z = μ/σ also depends on σ(Vop). Therefore, μ monotonicity alone does not mathematically guarantee z or Vmin monotonicity.

**Required wording:** monotonicity is an explicit validation/audit condition over the inverse-query range, followed by bisection only where the condition holds.

I changed the manuscript accordingly.

### 3. “Exact inverse” is too strong

Bisection produces a numerically converged solution of the surrogate. It is not an exact physical solution, and the paper itself uses a finite number of iterations.

Use:
- “numerically converged inverse,”
- “inverse solved to numerical tolerance,” or
- “inverse of the surrogate.”

Avoid “exact,” “closed-form inverse,” and “machine-precision exact” in the main narrative.

I changed these claims.

### 4. Endpoint checks do not prove monotonicity

The manuscript says the direction is read from the two endpoints. Endpoint direction is useful, but it is not a proof that an entire interval is monotone.

The revised text now states that the direction is inferred from endpoints **and monotonicity is checked over the full axis range before bisection**.

## Priority 3 — GP background is currently slightly over-explained

The intent of the “device/process-reader edition” is correct, but the ore-body/kriging analogy is too long for an IEEE device paper. A device reviewer needs only three facts:

1. GP = smooth regression over sparse multidimensional samples.
2. The kernel encodes the assumed smoothness.
3. ARD gives an axis-specific length scale, but it is **not** a physical sensitivity metric.

That is enough.

I shortened the explanation and removed the extended “ore body” analogy.

### What should remain

The following sentence-level idea is valuable and should stay:

> “A lengthscale is not a sensitivity.”

This anticipates a likely reviewer misunderstanding and directly supports Section V.

## Priority 4 — Sobol explanation is good in concept but too long

The device-facing distinction between local derivative and global variance contribution is excellent. Keep that.

Remove the historical explanation that Sobol indices were developed for aircraft/climate simulators. It does not help the technical argument.

The revised manuscript defines total-order Sobol indices in device language and retains the distinction from local sensitivity.

## Priority 5 — IEEE abstract requirements

The original abstract was approximately **321 words** and contained equations/symbolic expressions. IEEE guidance recommends a single self-contained paragraph of up to 250 words, without equations, references, or footnotes. It also recommends 3–5 index terms.

The revised abstract is approximately **217 words**, removes equations and symbolic expressions, and uses five index terms. citeturn0search1turn0search3

## Priority 6 — VLSI Symposium format is substantially different

If the intended target is the **IEEE/JSAP Symposium on VLSI Technology & Circuits**, the current manuscript is not a submission-format match.

The 2026 symposium requires a **maximum of three pages including illustrations**, with an approximately two-column format and strict figure/table sizing requirements. Papers exceeding three pages are not accepted. citeturn0search0turn0search2

Therefore:

- The current ~9-page technical manuscript should be treated as a **full technical manuscript / extended paper**.
- A VLSI submission would require a separate 3-page compression, not merely formatting changes.
- The VLSI symposium explicitly favors originality, innovation, and advancing the field, so the 3-page version should foreground the device/process result rather than the GP background. citeturn0search2

IEEE also provides official conference and journal templates; the Markdown draft itself should not be regarded as the final IEEE layout. citeturn0search4turn0search8

## Priority 7 — Title should be more IEEE-like

Current:

> Forward and Inverse SRAM Vmin Estimation with an Analytic Physics Layer: Where the Margin Actually Comes From

“Where the Margin Actually Comes From” is readable, but it is more editorial than IEEE technical-paper style.

Recommended title:

> **Physics-Constrained Forward and Inverse SRAM Vmin Estimation Under Process Variation**

Alternative if the inverse contribution is the main novelty:

> **Physics-Constrained Surrogate Modeling for Forward and Inverse SRAM Vmin Estimation**

I recommend the first one.

## Priority 8 — Several phrases sound argumentative rather than technical

Examples include:
- “The spacing is the result.”
- “This is a result, not a failure of the method.”
- “The contribution is the pipeline, not the regressor.”
- “The point here is...”
- “what follows.”

These are not wrong, but they make the paper sound like it is anticipating an argument with the reviewer. IEEE reviewers generally respond better to direct technical statements.

I converted the most prominent instances to neutral technical prose.

## Priority 9 — Important technical caveat: the inverse claim should be framed as axis-wise

The manuscript correctly limits the inverse validation to one unknown axis, but some early statements sound like the entire nine-dimensional map is invertible.

The defensible claim is:

> **For a fixed set of eight coordinates, the validated one-dimensional axis-wise inverse can be solved by bisection.**

Do not imply that the full nine-dimensional inverse is uniquely determined. The Limitations section already says this; the abstract/introduction should match that precision.

## Priority 10 — Section VII is useful but should not compete with the main result

The simulation-budget study is valuable to a process engineer because it gives an actionable campaign-design rule. However, it currently occupies a full section after the paper has already established the surrogate and sensitivity results.

For an IEEE journal/long paper, retain it.

For a VLSI 3-page version, reduce it to **one figure/table plus two sentences**:
- 53× lower budget costs only +2.6 mV read error;
- combined reduction is not separable because condition count and MC depth interact.

## GP / statistics background: final judgment

### Keep
- one-sentence definition of GP;
- one-sentence explanation of kernel;
- one-sentence explanation of ARD;
- fixed-noise likelihood intuition;
- one-sentence explanation of censoring;
- one-sentence definition of bisection;
- local derivative vs total-order Sobol distinction;
- one-sentence bootstrap explanation;
- one-sentence explanation of random-effects pooling.

### Remove or shorten
- historical origin stories;
- “oldest root-finding method”;
- repeated statements that these are standard tools;
- long analogies to other disciplines;
- repeated explanations of why the reviewer should not be intimidated by statistics.

For this audience, **background should explain what the quantity means physically, not teach the entire statistical method.**

## Device/process reviewer questions the manuscript should answer explicitly

The revised structure should make these answers easy to find:

1. **What does the surrogate predict?**
   - μ and σ of the margin, not Vmin directly.

2. **Why is Vmin not learned directly?**
   - To preserve the explicit yield definition and enable the inverse query.

3. **What makes the inverse possible?**
   - A fixed eight-dimensional coordinate set plus a validated monotone one-dimensional relation.

4. **Why are corners insufficient?**
   - Corner axes mainly shift the mean, while the yield target depends strongly on the distribution spread.

5. **Why is write worse than read despite better μ prediction?**
   - σ prediction error and the slope of z(Vop) dominate Vmin error.

6. **What is genuinely new to device/process understanding?**
   - The local-mismatch axis can dominate a corner threshold axis in margin variance, and the lobe-shape diagnostic exposes a potentially much larger systematic error than surrogate regression.

7. **What remains unverified?**
   - Silicon validation of the tail correction and shared read/write conditions.

These are already present in the manuscript; the main improvement is making their hierarchy unmistakable.

## Changes made in the reviewed manuscript

- Rewrote the abstract to IEEE-style length/content.
- Softened “guaranteed monotonicity” and “exact inverse” claims.
- Added explicit monotonicity audit language before bisection.
- Reduced GP background to device-relevant concepts.
- Reduced Sobol background to the local-vs-global sensitivity distinction.
- Reframed Section VI as a non-Gaussian-tail diagnostic rather than a co-equal main contribution.
- Reworked the conclusion to emphasize the surrogate/inverse contribution first and the tail correction as an important but not silicon-validated finding.
- Replaced several argumentative/editorial phrases with neutral technical prose.
- Kept the numerical results and the manuscript's existing evidence hierarchy unchanged.

## Bottom line

**Technical substance: strong.**  
**Device/process relevance: strong.**  
**Statistical background for non-ML reviewers: now appropriate after shortening.**  
**IEEE manuscript structure: broadly appropriate after the abstract/style corrections.**  
**IEEE/VLSI final formatting: not yet complete because the source is Markdown; it needs the official IEEE/VLSI template.**  
**VLSI Symposium submission: requires a separate 3-page compression, not just formatting.**

The most important remaining editorial decision is whether the target is **(A) an IEEE journal/full paper**, where the current depth is defensible, or **(B) VLSI Symposium**, where the paper must be rebuilt around a very small number of device-level messages.
