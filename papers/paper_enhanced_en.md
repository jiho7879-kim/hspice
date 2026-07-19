# Physics-Constrained Gaussian Process Surrogates for Inverse SRAM Vmin Estimation

> **Internal Review Draft (v1.0)** — Enhanced background for device/process
> engineers without ML background. Retains all technical content from
> paper_en.md (v0.5) while adding accessible explanations and emphasizing
> resource/lithography motivation.
> `[TBD]` — pending final batch data transcription.

---

## 1. Introduction: Why This Research Matters

### 1.1 SRAM and the Critical Role of Vmin

SRAM (Static Random-Access Memory) occupies the largest die area in modern
SoCs (System-on-Chip). In a typical mobile application processor, SRAM accounts
for 30–60% of total chip area, forming the bulk of CPU caches, GPU register
files, and other performance-critical blocks.

The **minimum operating voltage (Vmin)** is the lowest supply voltage at which
a memory cell can reliably read and write. Higher Vmin forces the entire chip
to operate at elevated voltages, directly increasing power consumption and
reducing battery life. For modern mobile and IoT applications, every 50 mV
reduction in Vmin translates to meaningful improvements in energy efficiency.

However, Vmin is strongly dependent on **process variation** — the unavoidable
fluctuations in transistor characteristics (threshold voltage, mobility, gate
length, etc.) that occur during semiconductor manufacturing. These variations
cause identical designs to exhibit different Vmin values across a wafer and
between wafers.

### 1.2 The Resource Bottleneck: Why Standard MC Simulation Is Expensive

The industry standard for Vmin estimation is **Monte Carlo (MC) simulation**.
For each process-variation condition, thousands of random transistor
instantiations are generated, and HSPICE (or PrimeSim) circuit simulation is
run for each to build an SNM (Static Noise Margin) distribution. Typically
1,000–2,000 conditions are evaluated across the design space.

The computational cost is staggering:

- **MC per condition**: 1,000–5,000 runs (to collect SNM distribution)
- **Total simulations**: 1,000 conditions × 3,000 MC × 5 voltages = **15 million runs**
- **Time per HSPICE run**: minutes to tens of minutes (depending on model complexity)
- **Total wall-clock time**: **weeks to months** (even with parallelization)

This is not merely a time problem. **PDK (Process Design Kit) licenses, concurrent
execution limits per license, server infrastructure costs** — all add to the
total expense. As technology nodes advance (FinFET, GAA, CFET), PDK models become
more complex and individual simulation time increases, making this bottleneck
even more severe.

### 1.3 The Practical Value of Resource Reduction

Our method serves **both forward and inverse queries from a single simulation
budget**. Under the traditional approach:

- **Forward**: "What is Vmin for this condition?" → MC simulation required
- **Inverse**: "What is the boundary of conditions violating Vmin = 0.6V?" →
  Grid search requiring hundreds to thousands of additional MC runs

With our approach:

- **Forward**: Instant prediction via trained GP surrogate (no simulation needed)
- **Inverse**: Direct boundary exploration via gradient descent on the
  differentiable pipeline (no additional simulation needed)

This enables **10–100× more conditions to be analyzed with the same simulation
budget**, providing particular value in fab environments where computational
resources are tightly constrained.

### 1.4 Paper Organization

The paper is organized as follows:

1. **Problem Setup** (§2): SRAM read stability, Vmin definition, inverse problem formulation
2. **Data Design** (§3): Condition generation, resource-saving protocol, design pitfalls
3. **Method** (§4): GP surrogate, differentiable physics layer, physics constraints
4. **Experiments** (§5): Accuracy validation, Vmin contours, gradient inversion
5. **Limitations and Conclusion** (§6–8)

---

## 2. Problem Setup

### 2.1 The 6T SRAM Cell and Read Stability

`[Fig: 6T SRAM cell schematic]`

A 6T SRAM cell consists of six transistors:

- **PU (Pull-Up)**: 2 PMOS transistors that hold data as '1'
- **PD (Pull-Down)**: 2 NMOS transistors that hold data as '0'
- **PG (Pass-Gate)**: 2 NMOS access transistors controlled by the word line (WL)

During a read operation, cell stability is evaluated using the **butterfly
curve** — the overlay of left/right inverter Voltage Transfer Characteristics
(VTC). The minimum size of the two "lobes" (eye-shaped regions) gives the
SNM. Smaller SNM indicates higher risk of data corruption during read.

`[Fig: Butterfly curve and SNM illustration]`

### 2.2 Lobe Statistics of Read SNM

MC simulation collects the distribution of SNM across thousands of random
samples. Conventionally, the reported statistics are the mean and standard
deviation of the minimum: (μ_SNMR, σ_SNMR).

However, there is a critical issue: **the left tail of the minimum distribution
is heavier than a moment-matched Gaussian**. Naively applying z = μ/σ
systematically underestimates failure probability. At Z ≈ 6, this bias reaches
+0.7σ (independent lobes) to +1.9σ (anti-correlated lobes) — a fatal error for
6σ-tail yield estimation in 256 Mb arrays.

### 2.3 Lobe-Resolved Effective Z-Score

We compute the exact failure probability from individual lobe statistics
(μ_L, σ_L, μ_R, σ_R, ρ_LR):

```
p_fail = P(L < 0) + P(R < 0) − P(L < 0, R < 0)
Z_eff = Φ⁻¹(1 − p_fail)
```

The joint term uses the **bivariate normal CDF (Owen's T)**, which is
closed-form, smooth, and differentiable in all inputs. This removes the
min-statistics bias while preserving gradient flow through the GP surrogate.

### 2.4 Vmin Definition and Yield Target

For a condition x, Vmin(x) is obtained by linearly interpolating the voltage
at which z(Vop) = μ/σ crosses the target Z_t over the grid Vop ∈ {0.4, …, 0.8} V.

Z_t is derived from the array yield model. For 256 Mb at 99% Poisson yield:

```
p_fail = −ln(0.99) / (256 × 10⁶) ≈ 3.9 × 10⁻¹⁰
Z_t = Φ⁻¹(1 − p_fail) ≈ 6.50
```

Conditions with z(0.4 V) > Z_t have Vmin below the sampled voltage range and
are flagged as **left-censored**, excluded from continuous error metrics.

### 2.5 The Inverse Problem: Why Forward-Only Is Insufficient

For a target voltage V*, the set {x : Vmin(x) = V*} is a **hypersurface**
(contour) in 9-dimensional variation space. What designers and process engineers
actually ask:

> "Which variation combinations violate the target Vmin?"
> "What is the minimum assist (e.g., wordline underdrive) to bring an operating
> point back across the boundary?"

This is an **inverse problem**. The traditional approach requires grid search
with MC simulation at many points. Even in 2D (cn, pu), a 50×50 grid needs
2,500 MC runs; in 9D, the search space grows exponentially.

Our method solves this via **gradient descent** on the differentiable Vmin(x).
Instead of evaluating a grid, we directly walk toward points on the target contour,
achieving 100× or greater efficiency over grid search.

---

## 3. Data Design

### 3.1 Input Space: 9-Dimensional Variation Parameters

Cell transistor variation is described in 9 dimensions. Since PG and PD are the
same NMOS flavor, their variation is decomposed into a **common component** and
a **PG-PD skew**.

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

**Deck parameter derivation**:
- Vth: PG = cn + sk, PD = cn − sk
- Local-σ: PG = l_com + l_sk, PD = l_com − l_sk
- Mobility: PG = m_com + m_sk, PD = m_com − m_sk

### 3.2 Rationale for the Common+Skew Parameterization

PG and PD are the same NMOS flavor — their dominant variation sources (gate
stack, channel doping, anneal, lithography CD) are **shared**, with W/L,
layout environment, and flavor differences producing imperfect tracking.

Independent per-device sampling wastes design points on states that **do not
occur in silicon** — the same flavor diverging by ±30% in opposite directions
at the mismatch level. The common+skew decomposition produces an implicit
correlation:

```
corr(l_PG, l_PD) ≈ 0.88
```

This falls within the plausible tracking band (0.85–0.95) and is consistent
with the Vth structure (ρ ≈ 0.80). Common and skew are sampled **independently** —
a property required by the variance-based sensitivity analysis (§5.6).

`[Fig: (a) Quadrant weighting in (cn, pu) plane; (b) (l_com, l_sk) box → (l_PG, l_PD) band]`

### 3.3 Design of Experiments: Strategy for Resource Efficiency

Read (SNMR) and write (Vtrip) degrade in different worst-case quadrants:

- **SNMR**: Worst at FSG (cn < 0, pu > 0) — fast NMOS, slow PMOS destabilize read
- **Vtrip**: Worst at SFG (cn > 0, pu < 0) — slow NMOS, fast PMOS cause write failure

Separate deck sets are used per metric with different quadrant weights:

| Metric | FSG | FN | SN | SFG |
|---|---|---|---|---|
| SNMR | 45% | 20% | 15% | 20% |
| Vtrip | 10% | 15% | 30% | 45% |

This **doubles to quadruples the resolution** in worst-case regions with the
same 2,000 conditions. Conditions use deterministic PCG64 random draws with
independent streams per quadrant.

Each deck set: 2,000 conditions × 5 Vop = **10,000 simulations**.
Total across 2 metrics = 20,000 simulations — approximately **100× reduction**
vs. grid search.

### 3.4 Design Pitfall: Mirror-Twin Leakage

An early pilot design re-used one QMC stream across all four quadrants,
flipping only cn and pu signs. The consequences:

- **75% of conditions** had a mirror twin sharing the remaining 7 coordinates
- Under random hold-out, **~74% of test conditions** had a twin in training
- Accuracy metrics were **silently inflated**

We discovered this through forensic comparison of transcribed conditions
against the reconstructed generator, then (i) gave each quadrant an
**independent stream** and (ii) enforced **mirror-group splits** for any
evaluation touching legacy data. We recommend that surrogate-validation
studies **report their design-generation code and split rule together**.

---

## 4. Method

### 4.1 GP Surrogate: An Accessible Explanation

A **Gaussian Process (GP)** is a non-parametric Bayesian method that estimates
the *distribution of functions* from finite data points. In our problem:

- **Input**: 9-D variation parameters + voltage
- **Output**: SNM statistics (μ_SNMR, σ_SNMR)
- **What the GP learns**: The *distribution* of functions mapping inputs to (μ, σ)

GP advantages:
1. **Uncertainty quantification**: Provides variance (uncertainty) alongside predictions
2. **Works with limited data**: 2,000 conditions suffice for 9-D space learning
3. **Differentiable**: Directly usable for gradient-based optimization (inversion)

**μ GP**: Matern 5/2 kernel with ARD (Auto-Relevance Determination). Automatically
learns per-dimension lengthscales, identifying which parameters matter most.

**σ GP**: Additive kernel separating the operating-voltage group from the
device-variation group, incorporating structural knowledge.

### 4.2 Input Standardization: The Hidden Critical Step

When inputs span **mixed units** (mV, V, dimensionless ratios), omitting
standardization causes **silent under-convergence** that lengthscale
initialization cannot compensate. Most improvements we initially attributed
to physics constraints were actually due to standardization (§5.5). All inputs
are therefore standardized with training statistics.

### 4.3 Differentiable Physics Layer

The layer converting GP output (μ, σ) to Vmin operates as an **analytic
constraint** (not a learned approximation):

```
1. For each condition: predict (μ, σ) at 5 voltages
2. Compute z(Vop) = μ(Vop) / σ(Vop)
3. Linearly interpolate the voltage where z(Vop) crosses Z_t = 6.50
4. → Vmin(x)
```

This layer has **no learnable parameters** — it depends only on GP posterior
mean and variance. The first derivative is well-defined within each interpolation
interval; censored conditions are flagged separately.

### 4.4 Physics Constraints

Three constraints inject physical knowledge into the GP:

1. **Corner Anchoring**: Virtual observations at 4 global corners × 5 Vop are
   added to training data. Under an exact GP, this acts as a hard constraint.

2. **Monotonicity Penalty**: ReLU(−∂μ/∂Vop)² penalizes non-monotone behavior
   in the z-score vs. voltage relationship, evaluated on probe points through
   the posterior.

3. **Pelgrom Linear Trend**: Weak regularization encouraging σ(Vop) to increase
   linearly with voltage, consistent with Pelgrom's law.

### 4.5 Noise-Aware GP

Per-condition bootstrap standard errors (sem_μ, sem_σ) enter a **FixedNoise
likelihood**. This:

- **Automatically down-weights** low-budget conditions
- **Unifies heterogeneous budgets** in a single model: when low fidelity is
  simply fewer samples from the same simulator, a heteroscedastic single GP
  is the correct model — no Kennedy–O'Hagan bias term needed.

### 4.6 Gradient Inversion

The inverse problem is solved by optimization:

1. Input x set as a **leaf tensor** with sigmoid reparameterization (box constraints)
2. **(Vmin(x) − V\*)²** minimized via Adam optimizer
3. Convergence verified from **multiple starting points**
4. Each converged point cross-checked against **1-D bisection** on its slice

This directly finds points on the target contour without grid search,
remaining efficient even in high dimensions.

---

## 5. Experiments

### 5.1 Protocol

- **Hold-out**: Condition-level split (all 5 Vop rows of a condition stay together), 15%
- **Current batch**: No mirror twins by construction (§3.4) → condition-level split sufficient
- **Legacy pilot references**: Mirror-group splits enforced
- **Vmin errors**: Reported on non-censored set with censoring rate noted

### 5.2 Forward Accuracy

`[Table: hold-out μ R², μ RMSE, σ R², σ RMSE — TBD]`

`[Fig: Predicted vs measured scatter (μ, σ), hold-out]`

### 5.3 Vmin Contours (Inverse Problem i)

Hausdorff distance between GP and hold-out MC contours: **[TBD] mV**.
|Vmin_pred − Vmin_MC| at corner-near conditions: **[TBD] mV**.

`[Fig: Vmin contours in (cn, pu) plane: GP vs MC overlay + 4 corner points]`

### 5.4 Gradient Inversion (Inverse Problem ii)

On the analytic testbed, all 8 starting points converge (max |Vmin − target| =
2.41 mV), each matching 1-D bisection to **4 decimal places**.

`[Fig: Inversion trajectories: multi-start gradient paths with target contour]`

### 5.5 Constraint Ablation and Budget Curves

**Analytic testbed** (standardization controlled):

| Configuration | Vmin RMSE | p95 Error |
|---|---|---|
| Baseline | 1.26 mV | — |
| + Corner Anchoring | 0.92 mV (−27%) | −37% |

**Key finding**: To accurately assess physics constraint contributions,
**input standardization must be controlled**. Without it, most apparent
improvement comes from standardization, not constraints.

### 5.6 Sensitivity Analysis

ARD lengthscales reported by group alongside Sobol indices. Key questions:
1. Does ℓ_cn < ℓ_pu (PG-dominance hierarchy) hold?
2. Are l_sk/m_sk second-order effects only?

### 5.7 External Validation: Nominal-Slice and Dimension Scaling

Independent 4D batch (348 conditions, nominal multipliers) provides measured
points on the (l=m=1, skew=0) plane of the 9D space, testing generalization
outside the training distribution.

### 5.8 MC QC

Anderson–Darling normality tests and Q-Q inspection at voltages near the
z-crossing.

---

## 6. Limitations and Threats

1. **Gaussian extrapolation in z = μ/σ**: Industry-standard margin metric, not
   absolute fail-rate predictor. Defended by normality QC and lobe-resolved z_eff.
2. **Single node, single cell topology**: Limited generalization scope.
3. **Multiplier spill band** [0.625, 0.7) ∪ (1.3, 1.375]: Edge of compact-model
   calibration — read conservatively.
4. **Proprietary PDK**: Absolute values not reproducible → analytic testbed and
   normalized-axis results released for relative comparison.

## 7. Related Work

- MFNN+IS (Guo et al., ISEDA'24): Forward yield estimation
- Bayesian active learning (Yin et al., DAC'22, ASPDAC'23): Forward yield estimation
- Tail-accurate IS (Liu et al., DAC'23, OPTIMIS): Complementary tail-precision method
- Analytic Vmin models (Gupta & Calhoun, TCAS-I'21): Analytical approach — GP offers flexibility
- QMC yield analysis (Singhee & Rutenbar, TCAD'10): Design foundation

## 8. Conclusion

We proposed a pipeline serving both forward and inverse SRAM Vmin queries from
a **single simulation budget**, combining a GP surrogate with a differentiable
physics layer, and validated it on advanced-node data.

Key contributions:
1. **Resource reduction**: 10–100× more conditions analyzed with the same budget
2. **Differentiable inversion**: Direct contour exploration via gradient descent
3. **Lobe-resolved z-score**: Closed-form bias correction for min-statistics
4. **Noise-aware GP**: Unified heterogeneous MC budgets in a single model

---

## Appendix A. Metric Definitions

Formal definitions of design-range feasibility, left-censoring handling, and
assist-active scoring.

## Appendix B. Reproducibility Contract

Condition-generator version, seed, quadrant weights, ranges, and deck numbering convention.
