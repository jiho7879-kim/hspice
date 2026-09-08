# Physics-Constrained Forward and Inverse SRAM Vmin Estimation Under Process Variation

**Abstract—** SRAM minimum operating voltage (Vmin) verification under process variation is costly with Monte Carlo (MC) and incomplete with predefined process corners. We present a physics-constrained surrogate that supports both forward and inverse Vmin queries from one fixed simulation budget. A Gaussian process (GP) predicts the mean and standard deviation of the SRAM margin over nine process axes and supply voltage, while an explicit yield relation converts these statistics to Vmin. After validating monotonicity over the queried range, inverse process-axis queries are solved by one-dimensional bisection. On production calibration data from an advanced FinFET node, hold-out Vmin RMSE is 8.35 mV for read and 14.45 mV for write. Four PDK corners excluded from training are predicted with 9.3 and 16.7 mV RMSE, respectively, and the limiting corner is correctly identified for both modes. Axis-wise inverse queries recover threshold-voltage shifts with 2.60–3.20 mV RMSE. Global sensitivity analysis shows that a local mismatch axis contributes more read-margin variance than a PMOS threshold-shift corner axis, indicating that corner-only analysis can miss variance-dominant directions.

**Index Terms—** SRAM, Vmin, process variation, Gaussian process, yield analysis.

## I. INTRODUCTION

SRAM Vmin is set by the low-margin tail of a process distribution, making exhaustive MC verification expensive. Conventional PDK corners reduce the simulation burden but sample only predefined global directions. They can therefore miss local mismatch or other variance-dominant process axes.

This work addresses the problem with a **single fixed-budget, physics-constrained surrogate** that is usable in both directions. Rather than learning Vmin as a black-box output, the surrogate predicts the mean μ and standard deviation σ of the SRAM margin. An explicit yield relation then maps these statistics to Vmin. This separation preserves the yield definition and enables inverse queries without training a second inverse model.

The main results are: (1) millivolt-level hold-out Vmin prediction, (2) correct identification of unseen limiting PDK corners, (3) direct recovery of process-axis values from a target Vmin, and (4) a global-sensitivity result showing that local mismatch can dominate a conventional corner axis.

## II. PROPOSED VMIN SURROGATE

### A. Margin-Statistics Model

For each circuit simulation, the read or write margin is evaluated at a specified process condition and supply voltage. Two GP regressors predict the corresponding margin mean μ and standard deviation σ over nine process axes and supply voltage.

The yield criterion is retained analytically rather than embedded in the regression target. In this form, the surrogate represents the process-dependent electrical margin, while the required yield remains an explicit engineering constraint. Consequently, a forward query evaluates Vmin from μ and σ, whereas an inverse query fixes the remaining process coordinates and solves for the process-axis value that reaches a target Vmin.

### B. Inverse Query and Numerical Solution

For a selected process axis, the inverse problem is one-dimensional after the other coordinates are fixed. The supply-voltage dependence is first checked for monotonicity over the queried range. Bisection is then applied only on a validated monotone interval.

The resulting solution is a numerical inverse of the surrogate, not an exact inverse of the physical circuit. The same simulation campaign therefore supports forward prediction, corner checking, sensitivity analysis, and inverse process interpretation.

## III. FORWARD VMIN RESULTS

The surrogate was evaluated on hold-out production calibration data from an advanced FinFET node. The predicted Vmin agrees with the circuit results to within millivolt-level error.

**TABLE I. VMIN PREDICTION ACCURACY**

| Test | Read | Write |
|---|---:|---:|
| Hold-out Vmin RMSE | **8.35 mV** | **14.45 mV** |
| Unseen PDK-corner RMSE | **9.3 mV** | **16.7 mV** |
| Limiting PDK corner | Correct | Correct |

The larger write-mode error indicates that accurate Vmin prediction depends not only on the mean margin but also on the predicted margin spread and the local slope of the yield relation. This distinction is important when comparing read and write verification accuracy.

Four PDK corners were excluded from training and used as an independent corner-oriented test. The limiting corner is correctly identified for both read and write, showing that the surrogate can reproduce the relevant corner ranking without having been trained directly on those four corner points.

## IV. INVERSE PROCESS-AXIS RECOVERY

The same surrogate was queried in reverse by specifying a target Vmin and recovering the corresponding value of a selected process axis while holding the other axes fixed.

**TABLE II. INVERSE RECOVERY**

| Recovered quantity | RMSE |
|---|---:|
| Threshold-voltage shift | **2.60–3.20 mV** |

The inverse result provides a process-oriented interpretation that direct Vmin regression cannot readily provide: given a Vmin target, the engineer can estimate the process-axis shift associated with that electrical limit. Because the inverse is performed on the validated surrogate relation, no additional circuit-simulation campaign is required for each inverse query.

## V. GLOBAL SENSITIVITY: WHY CORNERS ARE NOT SUFFICIENT

Total-order Sobol analysis was applied to the surrogate output to quantify variance contribution over the allowed process range, including interactions. This analysis is complementary to GP ARD lengthscales: a lengthscale describes function smoothness, whereas the Sobol index measures contribution to output variance.

The key device/process observation is that the **local NMOS common-mismatch/local-σ axis contributes more read-margin variance than the PMOS threshold-shift corner axis**. At least approximately **39% of the variance lies away from the conventional corner directions** in the evaluated condition.

Thus, a corner analysis can capture important mean shifts while still underrepresenting the margin spread that determines the yield-referenced Vmin. This result directly motivates the use of the fixed-budget surrogate over a broader process space.

## VI. SECONDARY MC DIAGNOSTIC: NON-GAUSSIAN TAIL

The μ–σ yield mapping is intentionally compact, so the underlying MC distribution was separately examined for shape effects. The read-margin lobes exhibit a correlation of ρ_LR = −0.371. The local mismatch contribution to lobe-difference variance is approximately 2.2× the global contribution, and the analyzed tail-shape effect corresponds to an estimated Vmin shift of about 70 mV.

This result is treated as a **post-processing diagnostic**, not as a learned correction, and it is not silicon-validated. It therefore does not change the primary surrogate accuracy claims.

## VII. CONCLUSION

A physics-constrained surrogate has been demonstrated for forward and inverse SRAM Vmin estimation under process variation. Predicting margin mean and standard deviation while retaining the yield relation explicitly enables multiple analyses from one fixed simulation budget. Hold-out Vmin RMSE is 8.35 mV for read and 14.45 mV for write; four unseen PDK corners are predicted with 9.3 and 16.7 mV RMSE and the limiting corner is correctly identified. Inverse threshold-voltage recovery achieves 2.60–3.20 mV RMSE.

Global sensitivity analysis further shows that local mismatch can contribute more read-margin variance than a conventional threshold-shift corner axis, demonstrating a concrete limitation of corner-only verification. The framework therefore connects device/process variation, yield-referenced Vmin, and inverse process interpretation without requiring a separate surrogate for each query type.
