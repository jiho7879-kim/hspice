# Physics-Constrained GP Surrogate for SRAM Vmin Estimation

> **Version**: 2026-07-02 (v0.3)
> **Status**: Toy project complete, HSPICE real-data extraction pipeline ready

---

## 1. Introduction

### 1.1 Motivation

SRAM (Static Random Access Memory) occupies the largest area in modern system-on-chip (SoC) designs and dominates overall chip yield. The **Vmin (minimum operating voltage)** — the lowest voltage at which a cell can operate reliably — is the single most critical metric for SRAM yield, yet it is strongly affected by process, voltage, temperature, and aging (PVTA) variations.

Traditional Vmin estimation relies on Monte Carlo (MC) HSPICE simulations: thousands of runs per PVTA condition, repeated across process corners. This approach is computationally prohibitive, especially for 6-sigma tail estimation requiring millions of MC samples.

### 1.2 Proposed Approach: GP Surrogate + Differentiable Physics Layer

We propose a hybrid framework combining a **Gaussian Process (GP) surrogate model** with a **differentiable physics layer** for efficient SRAM Vmin estimation:

1. **GP Surrogate**: Maps PVTA parameters → SNMR statistics (mu, sigma)
2. **Differentiable Physics Layer**: Converts (mu, sigma) → Vmin via Z-score-based linear interpolation
3. **Physics-Informed Losses**: Monotonicity (L_mono), corner anchoring (L_boundary), Pelgrom scaling (L_pelgrom)

### 1.3 Contributions (Estimated)

| Contribution | Rating | Description |
|-------------|--------|-------------|
| Differentiable Vmin transform | ⭐⭐⭐ | End-to-end differentiable pipeline from GP outputs to Vmin |
| Additive-kernel delta sigma GP | ⭐⭐⭐ | Separates Vop and (cn, pu) dependencies for accurate sigma prediction |
| Inverse Vmin contour extraction | ⭐⭐⭐⭐ | Hausdorff-distance-based validation at Vmin=0.6V isocontour |
| Prediction-truth gap diagnostics | ⭐⭐ | Lengthscale, gradient direction, corner bias analysis framework |
| Physics-constrained GP | ⭐⭐⭐ | L_boundary achieves 20.9% Vmin RMSE reduction (verified) |

---

## 2. Methodology

### 2.1 Input Space

**Core 3D** (always required, Vop at index `VOP_COL = 2`):

| Variable | Symbol | Range | Unit |
|----------|--------|-------|------|
| NMOS common shift | common_N | [-60, 60] | mV |
| PMOS shift | PU | [-60, 60] | mV |
| Operating voltage | Vop | [0.4, 0.9] | V |

**Extended dimensions** (indices 3+, optional):

| Variable | Symbol | Range | Notes |
|----------|--------|-------|-------|
| NMOS width | W | nominal ±10% | PG/PU transistor width variation |
| Gate length variation | σL_mult | [0.8, 1.2] | Process-induced L variation |
| Threshold voltage variation | σG | [0.8, 1.2] | Global Vth variation |
| Mobility variation | μ_mobility_mult | [0.8, 1.2] | Carrier mobility variation |
| Temperature | Temp | {-40, 25, 85, 125, 150} | °C (discrete sampling, continuous GP kernel) |

**Output**: y = [mu_SNMR (V), sigma_SNMR (V)] — (N, 2), fixed. Non-negotiable.

All dimensions are **StandardScaler-normalized** (zero mean, unit variance) before GP training to ensure numerical stability across heterogeneous scales (mV, V, °C, dimensionless ratios).

### 2.2 GP Model Architecture

**mu GP** (`ExactGPModel`):
- Kernel: Matern 5/2 + ARD (dimensionality inferred from input: d ≥ 3)
- Independent lengthscale per dimension via automatic relevance determination (ARD)

**sigma GP** (`AdditiveGPModel`):
- Additive kernel: k_Vop(Vop) + k_cnpu(common_N, PU)
- Explicitly separates voltage dependence from corner dependence
- Captures Pelgrom scaling naturally through Vop-only kernel

Both models trained independently via `ExactMarginalLogLikelihood` + Adam optimizer.

**Key implementation detail**: For L_mono posterior gradient, we use `gp.__call__()` in eval mode with `prediction_strategy = None`, **not** `gp.forward()` (which returns the prior with constant mean).

### 2.3 Differentiable Physics Layer (Vmin Computation)

For each (common_N, PU) condition:

1. Predict mu(Vop), sigma(Vop) across 6 Vop levels {0.4, 0.5, ..., 0.9}
2. Compute Zscore(Vop) = mu(Vop) / sigma(Vop)
3. Vmin = linear_interpolate({Vop | Zscore(Vop) = Z_target})

where Z_target = 6.0 (conservative target for 64Mb @ 99.9% yield).

The entire pipeline is **fully differentiable** w.r.t. mu and sigma, enabling end-to-end gradient flow from GP hyperparameters to Vmin.

### 2.4 Physics-Informed Loss Functions

**L_mono (Monotonicity)**:
- ∂μ/∂Vop > 0 (increasing Vop → higher hold SNM)
- Evaluated via PINN-style collocation across probe points
- Penalty: ReLU(-∂μ/∂Vop)²

**L_boundary (Corner Anchoring)**:
- 4 global corners (FSG, SFG, FFG, SSG) × 6 Vop = 24 virtual observations
- Augmented directly into training data (hard constraint via exact GP inference)
- Ground truth from analytic SNMR model matching the data generator

**L_pelgrom (Sigma Scaling)**:
- σ(Vop) = SIGMA₀ + SIGMA_VOP_SLOPE × (0.9 − Vop)
- Weak regularization on sigma GP only

**Composite loss**:
```
L_total = -log p(y|X,θ) + λ_mono·L_mono + λ_pelgrom·L_pelgrom
```

### 2.5 Input Standardization (StandardScaler)

A numpy-only StandardScaler (no sklearn dependency) ensures GP training stability:

- **fit**: Compute per-dimension mean and std from training data
- **transform**: (X − mean) / std (zero mean, unit variance)
- **inverse_transform**: X * std + mean (restore original scale)
- Zero-variance dimensions protected by clamping std to 1.0

This is critical when mixing dimensions with different physical units and ranges.

### 2.6 GP-to-NN Transition Criteria

The switch to Neural Network + PINN architecture is gated by:

| Criterion | Threshold | Current Status |
|-----------|-----------|----------------|
| Hausdorff distance | > 3-5mV | ✅ 1.2-1.8mV (not triggered) |
| ℓ_pu / ℓ_cn ratio | > 2.0 | ✅ ~1.0 (toy data limitation) |
| Corner Vmin error | > 3σ | ✅ Pass |
| (GP→NN considered when ANY trigger fires) | | |

---

## 3. Experimental Results

### 3.1 Ablation Study (5 Configurations)

Physics-constrained ablation over 5 configurations:

| Config | mu R² | σ R² | Vmin RMSE | Hausdorff | Description |
|--------|-------|------|-----------|-----------|-------------|
| Baseline | 0.9973 | 0.6301 | 6.52mV | 1.8mV | Reference (no physics) |
| +L_mono | 0.9973 | 0.6292 | 6.46mV | 2.1mV | Negligible alone |
| +L_boundary | 0.9978 | 0.6340 | **5.16mV** | 1.3mV | **20.9% improvement** |
| +Mono+Boundary | 0.9978 | 0.6313 | 5.10mV | 1.2mV | Combined |
| +Mono+Boundary+Pelgrom | 0.9978 | 0.6365 | **4.91mV** | 1.3mV | **Full: 24.7% improvement** |

**Key findings**:
- **L_boundary accounts for ~95% of total improvement** (6.52→5.16mV)
- L_mono penalty is effectively zero on toy data (analytic model is already monotonic)
- Sigma R² < 0.64 indicates sigma prediction remains challenging (target for improvement)

### 3.2 Physical Consistency Verification

**Gradient direction check** (central point (0,0) via finite difference):
- ∂Vmin/∂common_N < 0: Slower NMOS → less PG leakage → lower Vmin ✅
- ∂Vmin/∂PU > 0: Slower PMOS → weaker PU → higher Vmin ✅
- Cosine similarity ≈ 1.0: GP captures true gradient direction ✅

**Lengthscale analysis**:
- ℓ_cn ≈ ℓ_pu ≈ 1.0 (all configs): Toy data has equal cn/pu coefficients — **not physically realistic**
- ℓ_Vop ≈ 0.65: GP accurately captures Vop sensitivity (sharp Vmin roll-off)
- Real data expected to show ℓ_cn < ℓ_pu (PG >> PU hierarchy)

### 3.3 Variable-Dimensionality Validation (8D Extension)

All components verified with 8D input:

| Component | Test Result |
|-----------|-------------|
| StandardScaler (3D) | mean=0, std=1, exact inverse ✅ |
| StandardScaler (8D) | mean=0, std=1, exact inverse ✅ |
| `ExactGPModel` (8D) | ard_num_dims=8 auto, loss 1.22→-0.16 ✅ |
| `AdditiveGPModel` (8D) | loss 0.95→-0.45 (extra dims unmodeled) ✅ |
| `generate_probe_points(n_extra=5)` | (96, 8), extra dims=0.0 ✅ |
| `generate_corner_anchor_data(n_extra=5)` | (24, 8), extra dims=0.0 ✅ |
| Full pipeline (train → contour) | ALL CHECKS PASSED ✅ |

---

## 4. Discussion

### 4.1 Why L_boundary Dominates Improvement

GP extrapolation is notoriously weak at domain boundaries. Training data covers common_N, PU ∈ [-60, 60], but corners like FSG (cn=-60, pu=+60) lie at the extremum. Adding just 24 virtual corner observations dramatically improves prediction quality. This suggests that even a handful of corner HSPICE simulations can provide substantial benefit for real PDK data.

### 4.2 L_mono Ineffectiveness on Toy Data

The analytic SNMR model has ∂μ/∂Vop = A_MU = 0.15 > 0 throughout the domain, so the monotonicity penalty is always zero. Real data may contain non-monotonic regions (Vop saturation, low-voltage extreme), where L_mono could be beneficial.

### 4.3 PG >> PU Hierarchy Not Captured

The toy data generator uses B_MU=0.001, C_MU=-0.0015, so cn and PU have nearly equal sensitivity. In real SRAM, Pass Gate (PG, NMOS) variation affects Vmin 2-3× more than Pull-Up (PU, PMOS) variation, yielding ℓ_cn < ℓ_pu. **This must be verified with real PDK data.**

### 4.4 GP-to-NN Transition Outlook

None of the three transition triggers are currently met on toy data. Real HSPICE data is expected to increase all three metrics:
1. Hausdorff: from ~1.5mV to 3-10mV (realistic device mismatch)
2. ℓ_pu/ℓ_cn: from ~1.0 to 1.5-3.0 (PG >> PU in real devices)
3. Corner Vmin error: systematic bias at extreme corners

The transition decision will be made after real data evaluation.

---

## 5. Conclusions & Future Work

### 5.1 Completed ✅

- Full GP + differentiable physics layer pipeline for SRAM Vmin estimation
- Three physics-informed loss functions (L_mono, L_boundary, L_pelgrom)
- Ablation study: L_boundary provides 20.9% Vmin RMSE improvement
- 3D-to-8D variable input dimension interface (StandardScaler, dynamic kernel)
- Comprehensive validation suite (test_pipeline, demo, 8D verification)

### 5.2 Remaining Work

| Priority | Task | Details |
|----------|------|---------|
| 🔴 P0 | **HSPICE real-data extraction** | Option A (486 cond × 800 MC) or B (1200 cond × 240 MC) |
| 🟡 P1 | **Lengthscale analysis on real data** | Verify ℓ_cn < ℓ_pu (PG >> PU hierarchy) |
| 🟡 P1 | **GP→NN transition assessment** | Re-measure Hausdorff, lengthscale, corner bias |
| 🟢 P2 | **PINN implementation** | Neural network + PDE residual + contour boundary loss |
| 🟢 P2 | **Paper draft** | DAC or ISCAS target venue |

### 5.3 Paper Contributions Roadmap

```
Phase 1: Toy (current)          → GP + physics loss + contour
Phase 2: Real-data validation   → HSPICE verification + lengthscale analysis
Phase 3: NN+PINN (if needed)    → Full differentiable physics via PINN
Phase 4: Paper                  → Synthesis into target venue
```

---

## 6. References

| Document | Location | Description |
|----------|----------|-------------|
| Master Plan | `sram_vmin_inverse_estimation_plan.md` | Full project roadmap |
| Ablation Log | `toy_project/physics_ablation/DECISIONS.md` | Trial & error log |
| Agent Guide | `AGENT.md` | Agent orchestration reference |
| Data Extraction Spec | `toy_project/HSPICE_DATA_EXTRACTION_DETAILS.md` | PDK engineer manual |
| Phase 2 Checkpoint | `toy_project/CHECKPOINT_PHASE2.md` | Phase 2 summary (Korean) |
| Agent Config | `~/.config/opencode/oh-my-openagent.json` | Atlas/Prometheus/Hephaestus setup |

---

*This paper draft is a living document. It will be continuously updated as the project progresses, with each major phase trigger a revision bump.*
