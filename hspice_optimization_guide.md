---
title: 'HSPICE Optimization Guide for SRAM Characterization'
subtitle: 'Goal-Seeking, Parameter Optimization, Sensitivity Analysis, and Condition-Finding'
version: '1.0'
date: '2026-06-30'
description: 'Complete HSPICE guide for optimization-based condition finding. Covers .OPTIMIZE, goal-seeking .MEASURE, bisection method, sensitivity analysis (.SENS), parametric condition sweeps, and practical SRAM use cases for finding Vmin, critical transistor sizes, and failure boundaries.'
tags: [HSPICE, optimization, goal-seeking, sensitivity, bisection, condition finding, SRAM]
language: 'HSPICE'
keywords: [OPTIMIZE, GOAL, sensitivity, .SENS, bisection, condition finding, optimization, parameter sweep, SRAM optimization]
---

# HSPICE Optimization Guide for SRAM Characterization

> **Purpose**: Guide for using HSPICE optimization features to find conditions, failure boundaries, and optimal design parameters.
> **Scope**: TR-level SRAM bitcell/UT characterization ? Vmin finding, critical condition search, design space exploration.
> **Basis**: HSPICE .OPTIMIZE engine, .SENS sensitivity, .MEASURE GOAL, .PARAM sweeps.

---

## Table of Contents

1. [Optimization Overview](#1-optimization-overview)
2. [Goal-Seeking Optimization (.OPTIMIZE)](#2-goal-seeking-optimization-optimize)
3. [Optimization Methods: GRADIENT, BISECTION, PASSFAIL](#3-optimization-methods-gradient-bisection-passfail)
4. [Bisection Optimization for Condition Finding](#4-bisection-optimization-for-condition-finding)
5. [Sensitivity Analysis (.SENS)](#5-sensitivity-analysis-sens)
6. [Parametric Sweep with Conditional Logic](#6-parametric-sweep-with-conditional-logic)
7. [SRAM Use Case 1: Finding Vmin (Minimum Operating Voltage)](#7-sram-use-case-1-finding-vmin-minimum-operating-voltage)
8. [SRAM Use Case 2: Finding Critical Write Conditions](#8-sram-use-case-2-finding-critical-write-conditions)
9. [SRAM Use Case 3: Finding Maximum Cell Ratio for Stability](#9-sram-use-case-3-finding-maximum-cell-ratio-for-stability)
10. [SRAM Use Case 4: Read Current vs Wordline Voltage Sweep](#10-sram-use-case-4-read-current-vs-wordline-voltage-sweep)
11. [SRAM Use Case 5: Temperature Cross-Condition Finding](#11-sram-use-case-5-temperature-cross-condition-finding)
12. [Multi-Objective Optimization Trade-Off](#12-multi-objective-optimization-trade-off)
13. [Optimization Tips and Pitfalls](#13-optimization-tips-and-pitfalls)
14. [Complete Optimization Workbench Template](#14-complete-optimization-workbench-template)
15. [References](#15-references)

---

## 1. Optimization Overview

### 1.1 What HSPICE Optimization Solves
HSPICE optimization automatically finds parameter values that make measured circuit performance meet a specified goal. This is fundamentally different from brute-force sweep:

| Method | Approach | Use Case |
|--------|----------|----------|
| .DC Sweep | Sweep parameter across range, measure at each point | When you need full response curve |
| .OPTIMIZE | Adaptive search toward a goal | When you only care about a specific target value |
| .SENS | Sensitivity of output to each parameter | When you need to know which parameter dominates |

### 1.2 When to Use Optimization for Condition Finding
- Finding **Vmin**: what VDD gives exactly RSNM = 0.1*VDD?
- Finding **critical write voltage**: what BL voltage makes write fail?
- Finding **minimum transistor size**: smallest W that meets Ireq?
- Finding **failure boundary**: what temperature + voltage causes hold failure?
- Finding **margin**: how much margin exists before SNM = 0?

### 1.3 Optimization Workflow
1. Define variable parameters with .PARAM OPTxxx(init, min, max)
2. Define optimization model with .MODEL mname OPT METHOD=xxx
3. Define target with .MEASURE ... GOAL(=,<,>) value
4. Run analysis with OPTIMIZE=xxx RESULTS=xxx MODEL=xxx
5. HSPICE iterates until goal met or iteration limit reached

---

## 2. Goal-Seeking Optimization (.OPTIMIZE)

### 2.1 Core Components
Three mandatory components and one analysis command:

| Component | Statement | Purpose |
|-----------|-----------|---------|
| Variable | .PARAM x=OPTxxx(init, min, max) | What to vary |
| Target | .MEASURE ... GOAL(=,<,>) val | What to achieve |
| Model | .MODEL mname OPT METHOD=xxx | How to search |
| Analysis | .TRAN/.DC OPTIMIZE=OPTxxx RESULTS=mname MODEL=mname | When to run |

### 2.2 Optimization Parameter Functions (.PARAM OPTxxx)
| Function | Syntax | Description |
|----------|--------|-------------|
| OPT1 | OPT1(init, min, max) | Single variable, continuous |
| OPT2 | OPT2(init, min, max) | Second optimization variable group |
| OPTW | OPTW(init, min, max, delta) | Width optimization with quantization step |
| OPTL | OPTL(init, min, max, delta) | Length optimization with quantization step |

### 2.3 Basic Optimization Example
* Find resistor R value for exactly 1mA with VDD=1.8V
.OPTIONS POST=2

.PARAM R_VAL=OPT1(1K, 100, 100K)

R1 VDD VOUT {R_VAL}
VDD_SRC VDD 0 DC=1.8
I1 VOUT 0 DC=1M

.MODEL OPT1_MOD OPT METHOD=GRADIENT

.MEASURE DC VOUT_MEAS FIND V(VOUT)
.MEASURE DC IMEAS FIND I(I1)
.MEASURE DC IGOAL PARAM='IMEAS - 1M' GOAL=0

.DC VDD_SRC 1.8 1.8 1
+ OPTIMIZE=OPT1 RESULTS=IGOAL MODEL=OPT1_MOD

### 2.4 Optimization Variable Types
* Continuous (analog): OPT1, OPT2
* Discrete (quantized): OPTW for transistor widths, OPTL for lengths
* Multiple variables: Declare multiple .PARAM with same OPT group name

* Multiple variable optimization
.PARAM W_PU=OPT1(120N, 60N, 300N)
.PARAM W_PD=OPT1(200N, 100N, 400N)
.PARAM W_PG=OPT1(160N, 80N, 300N)

.MODEL SRAM_OPT OPT METHOD=GRADIENT ITROPT=50
.MEASURE DC RSNM_GOAL PARAM='RSNM - 0.15*VDD' GOAL=0

.DC VDD_SRC VDD_NOM VDD_NOM 1
+ OPTIMIZE=OPT1 RESULTS=RSNM_GOAL MODEL=SRAM_OPT

---

## 3. Optimization Methods: GRADIENT, BISECTION, PASSFAIL

### 3.1 Method Selection
| Method | Algorithm | Best For | When to Use |
|--------|-----------|----------|-------------|
| GRADIENT | Gradient descent with line search | Continuous multi-parameter | Multiple variables, smooth response |
| BISECTION | Binary search on one parameter | Single-variable condition-finding | Finding exact boundary/threshold |
| PASSFAIL | Binary pass/fail search | Pass/fail condition detection | Margin analysis, Vmin |
| GENETIC | Genetic algorithm | Multi-objective, rough landscape | Complex trade-offs |

### 3.2 .MODEL OPT Syntax for Each Method
* Gradient-based (default)
.MODEL OPT_GRAD OPT METHOD=GRADIENT
+ RELIN=1E-5 RELOUT=1E-5 ITROPT=30 GRAD=DERIVSTEP

* Bisection (binary search)
.MODEL OPT_BISECT OPT METHOD=BISECTION
+ RELIN=1E-3 RELOUT=1E-3 ITROPT=30

* Pass/fail (binary pass/fail)
.MODEL OPT_PF OPT METHOD=PASSFAIL
+ RELIN=1E-3 RELOUT=1E-3 ITROPT=30

### 3.3 Optimization Model Parameters
| Parameter | Description | Default |
|-----------|-------------|---------|
| RELIN | Relative convergence tolerance for input | 1e-3 |
| RELOUT | Relative convergence tolerance for output | 1e-3 |
| ITROPT | Maximum optimization iterations | 30 |
| GRAD | Derivative method (DERIVSTEP, RATIO) | DERIVSTEP |
| GRADSTEP | Step size for derivative calculation | 1e-3 |

### 3.4 GRADIENT Method
For continuous, smooth optimization. Calculates gradient (sensitivity) at each step,
then moves parameters in the direction that reduces the error.

.MODEL OPT_GRAD OPT METHOD=GRADIENT ITROPT=40 RELIN=1E-6
* Best when: Multiple parameters, response is smooth and continuous
* Worst when: Noisy response, binary pass/fail criteria

### 3.5 BISECTION Method
Binary search: narrows parameter range by half each iteration.
Checks if goal is met at midpoint, then searches upper or lower half.

.MODEL OPT_BISECT OPT METHOD=BISECTION ITROPT=30 RELIN=1E-3
* Best when: Single parameter, monotonic response, finding exact threshold
* Ideal for: Vmin finding, critical voltage finding
* Requires: GOAL must be a crossing condition (e.g., target - GOAL = 0)

### 3.6 PASSFAIL Method
Simpler binary search for pass/fail conditions.
Stops when consecutive iterations bracket the pass/fail boundary.

.MODEL OPT_PF OPT METHOD=PASSFAIL ITROPT=30
* Best when: Only pass/fail information available (digital yes/no)
* Use for: Yield boundary, margin testing, failure condition finding

---

## 4. Bisection Optimization for Condition Finding

### 4.1 Why Bisection for SRAM Condition Finding
Bisection is the most practical method for SRAM characterization because:
- Most SRAM metrics (RSNM, IREAD, WNM) are monotonic with respect to VDD, W, T
- Binary search finds the crossing point efficiently (N iterations = log2(range/step))
- Only 30-40 simulations needed vs 1000+ for full sweep
- Exactly finds the boundary condition

### 4.2 Generic Bisection Setup for Condition Finding
* Goal: find parameter value P where measure M = target_value T
* .MEASURE M_PARAM PARAM='M_MEAS - TARGET' GOAL=0
* .MODEL ... METHOD=BISECTION

### 4.3 Bisection Limit and Convergence
.MODEL BISECT_OPT OPT METHOD=BISECTION
+ RELIN=1E-4   * Stop when |P_new - P_old| / P_old < 1E-4
+ RELOUT=1E-4  * Stop when |M - T| / T < 1E-4
+ ITROPT=50    * Maximum 50 iterations

### 4.4 Practical Bisection Example: Find VDD at RSNM=0.1V
* Optimize VDD so that RSNM = exactly 0.1*VDD
* Note: RSNM decreases as VDD decreases (monotonic)

.PARAM VDD_OPT=OPT1(0.8, 0.4, 1.0)

VDD_SRC VDD 0 DC='VDD_OPT'

* SRAM cell with RSNM measurement
.MEASURE DC RSNM_TARGET PARAM='RSNM - 0.1*VDD_OPT' GOAL=0

.MODEL VMIN_OPT OPT METHOD=BISECTION ITROPT=30

.DC VDD_SRC 'VDD_OPT' 'VDD_OPT' 1
+ OPTIMIZE=OPT1 RESULTS=RSNM_TARGET MODEL=VMIN_OPT

* After convergence, VDD_OPT holds the VDD where RSNM = 0.1*VDD

---

## 5. Sensitivity Analysis (.SENS)

### 5.1 What .SENS Provides
.SENS calculates the DC small-signal sensitivity of an output variable with respect to ALL circuit parameters (device dimensions, model parameters, temperature, etc).

.SENS V(OUT)
* Output lists dV(OUT)/dP for every parameter P in the circuit

### 5.2 .SENS for SRAM Optimization
Use .SENS to identify which device parameters most strongly affect each metric:

.SENS V(VVDD) V(VVDD2)
* Output shows sensitivity of storage node voltages to:
  - WPU, WPD, WPG (device widths)
  - VTH0_PU, VTH0_PD, VTH0_PG (threshold voltages)
  - VDD, TEMP (environment)

### 5.3 Interpreting .SENS Output
* Example output from .SENS:
  SENSITIVITY OF V(VVDD)
  ELEMENT       PARAMETER       SENSITIVITY (V/V)
  MPU1          WPU             0.423
  MPD1          WPD            -0.287
  MPG1          WPG            -0.134
  MPU1          VTH0_PU         0.812
  MPD1          VTH0_PD        -0.621
  TEMP          TEMP           -0.003

Interpretation:
- V(VVDD) is most sensitive to MPU1 VTH0 (0.812 V/V)
- V(VVDD) is least sensitive to temperature (-0.003 V/V)
- Use these to prioritize optimization variables

### 5.4 Sensitivity-Guided Optimization Workflow
1. Run .SENS on the metric of interest (e.g., RSNM, IREAD)
2. Identify top-3 most sensitive parameters
3. Declare only those as OPTxxx variables
4. Run .OPTIMIZE with focused variable set
5. Result: faster convergence, fewer iterations

### 5.5 .SENS Example for SRAM RSNM Sensitivity
.OPTIONS POST=2
VDD_SRC VDD 0 DC=0.8
* SRAM subcircuit instance
XCELL BL BLB WL VDD VSS VVDD VVDD2 SRAM6T
.SENS V(VVDD) V(VVDD2)
.DC VVDD_INJ 0 0.8 0.01

* Output sensitivity of RSNM-relevant node voltages
* High sensitivity to MPD VTH0 -> mismatch in PD dominates RSNM variation

---

## 6. Parametric Sweep with Conditional Logic

### 6.1 Sweep + .MEASURE GOAL (without Optimization)
Use .DC sweep with conditional .MEASURE to find crossing points.

.DC VDD_SRC 0.4 1.0 0.01
.MEASURE DC RSNM_MEAS ...
.MEASURE DC VDD_CROSS FIND V(VDD) WHEN RSNM=0.1*V(VDD) CROSS=1

* Alternative: Find where WNM crosses threshold
.MEASURE DC WNM_CROSS FIND V(BL) WHEN V(VVDD)=V(VVDD2) CROSS=1

### 6.2 Using .MEASURE WHEN with Logical Conditions
.MEASURE DC VMIN_FOUND FIND V(VDD)
+ WHEN RSNM=0.1*V(VDD) CROSS=1
.MEASURE DC VMIN_CHECK PARAM='VMIN_FOUND > 0.6'

* Multiple condition AND
.MEASURE DC VMIN_ALL PARAM='VMIN_FOUND < 0.75'
.MEASURE DC PASS_ALL PARAM='RSNM_MIN > 0.1*VDD_NOM'

### 6.3 Data-Driven Parameter Sweep (.DATA)
Use .DATA to sweep any set of parameter combinations:
.PARAM WPU=0 WPD=0 WPG=0
.DATA SWEEP_DATA
+ WPU    WPD    WPG
+ 120N   200N   160N
+ 140N   220N   180N
+ 100N   180N   140N
+ 160N   240N   200N
.ENDDATA

.DC VDD_SRC 0.4 1.0 0.1 SWEEP DATA=SWEEP_DATA

.MEASURE DC RSNM ...
.MEASURE DC IREAD ...

### 6.4 Optimization via .ALTER + Manual Iteration
For complex multi-step conditions, chain .ALTER cases:

.ALTER case=try_small
    .PARAM WPU=80N
.ALTER case=try_medium
    .PARAM WPU=120N
.ALTER case=try_large
    .PARAM WPU=200N

* Each run independently. Post-process to find best result.

---

## 7. SRAM Use Case 1: Finding Vmin (Minimum Operating Voltage)

### 7.1 Problem
Find the minimum VDD where the SRAM cell still meets all read, write, and hold criteria simultaneously. The limiting mechanism can be read stability (RSNM), write margin (WNM), or retention (HSNM).

### 7.2 Approach: Bisection Optimization on VDD
* Variable: VDD (0.4V to 1.0V range)
* Goals: RSNM >= 0.1*VDD, IREAD >= 1uA, WNM >= 0.15*VDD
* Composite goal: min(all margins) = 0

### 7.3 Vmin Optimization Netlist
* File: sram_vmin_opt.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* Optimization variable: VDD
.PARAM VDD_OPT=OPT1(0.7, 0.4, 1.0)

* Sources
VDD_SRC VDD 0 DC='VDD_OPT'
VSS_SRC VSS 0 DC=0
WL_SRC WL 0 DC='VDD_OPT'
BL_SRC BL 0 DC='VDD_OPT'
BLB_SRC BLB 0 DC='VDD_OPT'

* SRAM 6T
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W=120N L=30N
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W=120N L=30N
MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W=200N L=30N
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W=200N L=30N
MPG1 BL WL VVDD VSS NMOS_SRAM W=160N L=30N
MPG2 BLB WL VVDD2 VSS NMOS_SRAM W=160N L=30N

* Sweep source
VVDD_INJ VVDD VSS DC 0
.DC VVDD_INJ 0 'VDD_OPT' 0.005

* Measurements
.MEASURE DC RSNM_VAL MIN V(VVDD,VVDD2)
.MEASURE DC IREAD_VAL FIND I(MPG1) WHEN V(VVDD)=0 CROSS=1
.MEASURE DC WNM_VAL FIND V(BL) WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE DC WNM_PARAM PARAM='VDD_OPT - WNM_VAL'

* Margin calculations (how far from failure)
.MEASURE DC RSNM_MARGIN PARAM='RSNM_VAL - 0.1*VDD_OPT'
.MEASURE DC IREAD_MARGIN PARAM='IREAD_VAL - 1E-6'
.MEASURE DC WNM_MARGIN PARAM='WNM_PARAM - 0.15*VDD_OPT'

* Composite: minimum of all margins must be >= 0
.MEASURE DC VMIN_COMPOSITE
+ PARAM='MIN(RSNM_MARGIN, IREAD_MARGIN, WNM_MARGIN)'
+ GOAL=0

* Optimization model
.MODEL VMIN_OPT OPT METHOD=BISECTION ITROPT=50

* Optimize
.DC VVDD_INJ 0 'VDD_OPT' 0.005
+ OPTIMIZE=OPT1 RESULTS=VMIN_COMPOSITE MODEL=VMIN_OPT

* Final Vmin is in VDD_OPT after convergence

### 7.4 Vmin Result Interpretation
* After optimization, VDD_OPT holds the Vmin value
* Example: VDD_OPT = 0.62V means cell fails below 0.62V
* The limiting mechanism is the one with smallest margin
* For production: Vmin_6sigma = mu_Vmin + 6*sigma_Vmin

---

## 8. SRAM Use Case 2: Finding Critical Write Conditions

### 8.1 Problem
Find the minimum bitline voltage (BL) required to successfully write the cell.
Or find the wordline pulse width that just barely writes.

### 8.2 Optimization: Find BL Trip Point
* Variable: BL voltage at write condition
* Goal: V(VVDD) crosses V(VVDD2) exactly at end of WL pulse

.PARAM BL_WRITE=OPT1(0.6, 0, 0.8)

BL_SRC BL 0 DC='BL_WRITE'
BLB_SRC BLB 0 DC=0        * Complement: writing '0'
WL_SRC WL 0 PULSE(0 'VDD_NOM' 0 10P 10P 'WIDTH' 'PERIOD')

.MEASURE TRAN WRITE_TRIP
+ TRIG V(WL) VAL='VDD_NOM*0.5' RISE=1
+ TARG V(VVDD) VAL=V(VVDD2) CROSS=1
.MEASURE TRAN WRITE_MARGIN PARAM='WIDTH - WRITE_TRIP' GOAL=0

.MODEL WRITE_OPT OPT METHOD=BISECTION
.TRAN 1P 'PERIOD' SWEEP OPTIMIZE=OPT1
+ RESULTS=WRITE_MARGIN MODEL=WRITE_OPT

### 8.3 Optimization: Minimum Wordline Pulse Width
* Variable: WL pulse width
* Goal: cell state flips exactly at end of WL pulse

.PARAM WL_PW=OPT1(100P, 10P, 500P)
WL_SRC WL 0 PULSE(0 'VDD_NOM' 0 10P 10P 'WL_PW' 'PERIOD')

.MEASURE TRAN TWRITE_END WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE TRAN TWRITE_MARGIN PARAM='WL_PW - TWRITE_END' GOAL=0
* Positive margin: write completes within pulse

.MODEL TWRITE_OPT OPT METHOD=BISECTION ITROPT=30

### 8.4 Write Failure Boundary: Temperature + VDD Cross
Use two-parameter sweep to find the (VDD, TEMP) boundary:
.DC VDD_SRC 0.4 1.0 0.05 TEMP_SRC -40 125 10
.MEASURE DC WRITE_FAIL FIND V(BL) WHEN V(VVDD)=V(VVDD2) CROSS=1
* Post-process: find (VDD, TEMP) combinations where write fails

---

## 9. SRAM Use Case 3: Finding Maximum Cell Ratio for Stability

### 9.1 Problem
Find the maximum PU:PD:PG ratio where the cell remains stable.
This helps find the beta and gamma ratio limits before the cell fails.

### 9.2 Optimization: Find Max Beta Ratio (WPD/WPG) for Read Stability
* Variable: WPD (pull-down width), WPG fixed
* Goal: RSNM >= 0.1*VDD (boundary condition)

.PARAM WPD_OPT=OPT1(200N, 100N, 500N)
.PARAM WPG_FIX=160N

MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W={WPD_OPT} L=30N
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W={WPD_OPT} L=30N
MPG1 BL WL VVDD VSS NMOS_SRAM W={WPG_FIX} L=30N
MPG2 BLB WL VVDD2 VSS NMOS_SRAM W={WPG_FIX} L=30N

.MEASURE DC RSNM_MIN MIN V(VVDD,VVDD2)
.MEASURE DC RSNM_COND PARAM='RSNM_MIN - 0.1*VDD_NOM' GOAL=0

.MODEL BETA_OPT OPT METHOD=BISECTION ITROPT=30

* After convergence: beta_max = WPD_OPT / WPG_FIX

### 9.3 Optimization: Find Min Gamma Ratio (WPG/WPU) for Writeability
* Variable: WPU, WPG fixed
* Goal: WNM >= 0.15*VDD

.PARAM WPU_OPT=OPT1(120N, 50N, 300N)

MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W={WPU_OPT} L=30N
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W={WPU_OPT} L=30N

.MEASURE DC WNM_TRIP FIND V(BL) WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE DC WNM_VALUE PARAM='VDD_NOM - WNM_TRIP'
.MEASURE DC WNM_COND PARAM='WNM_VALUE - 0.15*VDD_NOM' GOAL=0

.MODEL GAMMA_OPT OPT METHOD=BISECTION ITROPT=30

* After convergence: gamma_min = WPG / WPU_OPT

### 9.4 Design Window: Beta vs Gamma Trade-off
The beta/gamma ratio defines the SRAM cell operating window:
- High beta = stable read, hard write
- High gamma = easy write, unstable read
- Optimization finds the Pareto-optimal ratio

---

## 10. SRAM Use Case 4: Read Current vs Wordline Voltage Sweep

### 10.1 Problem
Find the wordline voltage at which Iread drops below target.
Used to determine min WL undervoltage margin.

### 10.2 Optimization: Find WL Undervoltage Limit
.PARAM WL_V_OPT=OPT1(0.7, 0.3, 0.8)

WL_SRC WL 0 DC='WL_V_OPT'

.MEASURE DC IREAD_FIND FIND I(MPG1) WHEN V(VVDD)=0 CROSS=1
.MEASURE DC IREAD_COND PARAM='IREAD_FIND - 1E-6' GOAL=0
* Find WL voltage where Iread drops to 1uA

.MODEL WL_OPT OPT METHOD=BISECTION ITROPT=40
.DC VVDD_INJ 0 'VDD_NOM' 0.005
+ OPTIMIZE=OPT1 RESULTS=IREAD_COND MODEL=WL_OPT

* Results: WL_V_OPT = wordline voltage where Iread = 1uA
* Wordline margin = VDD_NOM - WL_V_OPT

---

## 11. SRAM Use Case 5: Temperature Cross-Condition Finding

### 11.1 Problem
Find the temperature where cell transitions from read-stable to read-fail.
Used for worst-case corner identification.

### 11.2 Optimization: Find Temperature Limit
.PARAM TEMP_OPT=OPT1(85, -40, 150)

.TEMP {TEMP_OPT}

.MEASURE DC RSNM_HOT MIN V(VVDD,VVDD2)
.MEASURE DC RSNM_HOT_COND PARAM='RSNM_HOT - 0.1*VDD_NOM' GOAL=0

.MODEL TEMP_OPT_MOD OPT METHOD=BISECTION ITROPT=20
.DC VVDD_INJ 0 'VDD_NOM' 0.005
+ OPTIMIZE=OPT1 RESULTS=RSNM_HOT_COND MODEL=TEMP_OPT_MOD

* Result: TEMP_OPT holds the maximum temperature for stable read
* Use: identify temperature above which RSNM fails

### 11.3 Combined VDD + Temperature Optimization
Two-variable optimization with .ALTER for corner conditions:
.ALTER case=SS_125C
    VDD_SRC VDD 0 DC='VDD_SS'
    .TEMP 125
    .PARAM VDD_SS=OPT1(0.7, 0.4, 1.0)
    .MODEL SS_OPT OPT METHOD=BISECTION
    .DC ... OPTIMIZE=OPT1 ...

---

## 12. Multi-Objective Optimization Trade-Off

### 12.1 Problem
SRAM optimization requires balancing competing metrics:
- Read stability (RSNM) vs Writeability (WNM)
- Speed (IREAD) vs Leakage (ISTBY)
- Area (W) vs Performance (Iread, RSNM)

### 12.2 Weighted Sum Approach
Combine multiple goals into a single cost function:

.MEASURE DC RSNM_ERR PARAM='(RSNM_TARGET - RSNM_VAL) / RSNM_TARGET'
.MEASURE DC WNM_ERR PARAM='(WNM_TARGET - WNM_VAL) / WNM_TARGET'
.MEASURE DC IREAD_ERR PARAM='(IREAD_TARGET - IREAD_FOUND) / IREAD_TARGET'

* Weighted composite (alpha + beta + gamma = 1.0)
.MEASURE DC COST PARAM='0.4*RSNM_ERR + 0.4*WNM_ERR + 0.2*IREAD_ERR'
+ GOAL=0

* Optimization minimizes this weighted cost function

### 12.3 Constraint-Based Optimization
Enforce hard constraints as .MEASURE limits:
.MEASURE DC RSNM_CONSTRAINT PARAM='RSNM_VAL - RSNM_MIN' GOAL=0
.MEASURE DC WNM_CONSTRAINT PARAM='WNM_VAL - WNM_MIN' GOAL=0
.MEASURE DC IREAD_CONSTRAINT PARAM='IREAD_VAL - IREAD_MIN' GOAL=0

* All goals must be >= 0 simultaneously
* Optimization finds any solution within feasible region

### 12.4 Pareto Front via Multiple Optimization Runs
Run optimization at each weighting factor:

* Run 1: alpha=0.8, beta=0.1, gamma=0.1 (prioritize read stability)
* Run 2: alpha=0.1, beta=0.8, gamma=0.1 (prioritize write)
* Run 3: alpha=0.1, beta=0.1, gamma=0.8 (prioritize speed)

Each run produces one Pareto-optimal point. Collect all for design space.

---

## 13. Optimization Tips and Pitfalls

### 13.1 Convergence Tips
| Issue | Fix |
|-------|-----|
| Optimization oscillates | Reduce ITROPT or tighten RELOUT |
| Optimization stuck at boundary | Widen min/max range, adjust initial guess |
| Non-monotonic response | Use GRADIENT instead of BISECTION |
| Too many variables | Run .SENS first, select top 2-3 variables |
| No convergence | Increase ITROPT, reduce RELOUT tolerance |
| Goal never reached | Check that goal is physically achievable |

### 13.2 Important Notes on BISECTION
- BISECTION requires **monotonic** relationship between variable and output
- If output is non-monotonic, BISECTION may converge to wrong boundary
- Always verify: measure at both ends of range to confirm direction
- For Vmin: RSNM is always monotonic with VDD (lower VDD = lower RSNM)
- For WNM: WNM is monotonic with BL voltage (lower BL = easier write)

### 13.3 Initial Guess Strategy
- Start from known good value (e.g., VDD_NOM for Vmin search)
- Set min/max to physically plausible range
- For width optimization: start from nominal sizing

### 13.4 Variable Range Guidelines
| Variable | Min | Max | Reason |
|----------|-----|-----|--------|
| VDD | 0.4*VDD_NOM | 1.2*VDD_NOM | Below Vret, above overvoltage |
| WPU | 0.5*W_NOM | 3*W_NOM | Below causes write fail, above area |
| WPD | 0.5*W_NOM | 3*W_NOM | Below causes read fail |
| WPG | 0.5*W_NOM | 3*W_NOM | Below stops write, above read fail |
| TEMP | -40 | 150 | Standard IC range |

### 13.5 Pitfalls to Avoid
| ? Pitfall | Why | ? Fix |
|-----------|-----|-------|
| Initial guess at boundary | Optimizer may step out of range | Set guess at middle of range |
| Too many OPT variables | Convergence time grows exponentially | Limit to 3-4 per run |
| Ignoring .SENS first | Wasting iterations on insensitive params | Always run .SENS first |
| BISECTION on non-monotonic | Incorrect crossing point found | Verify monotonicity first |
| GOAL with wrong sign | Optimizer goes the wrong direction | Check goal = measured - target |

---

## 14. Complete Optimization Workbench Template

### 14.1 Vmin Optimization Workbench
* File: sram_vmin_optimizer.sp
* Purpose: Find VDD where cell just meets all criteria
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* === OPTIMIZATION VARIABLE ===
.PARAM VDD_OPT=OPT1(0.75, 0.4, 1.0)

* === SUPPLIES ===
VDD_SRC VDD 0 DC='VDD_OPT'
VSS_SRC VSS 0 DC=0
WL_SRC WL 0 DC='VDD_OPT'
BL_SRC BL 0 DC='VDD_OPT'
BLB_SRC BLB 0 DC='VDD_OPT'

* === SRAM BITCELL (6T) ===
.PARAM WPU=120N WPD=200N WPG=160N LCELL=30N

MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W={WPU} L={LCELL}
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W={WPU} L={LCELL}
MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W={WPD} L={LCELL}
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W={WPD} L={LCELL}
MPG1 BL WL VVDD VSS NMOS_SRAM W={WPG} L={LCELL}
MPG2 BLB WL VVDD2 VSS NMOS_SRAM W={WPG} L={LCELL}

* === SWEEP SOURCE FOR DC ANALYSIS ===
VVDD_INJ VVDD VSS DC 0

* === MEASUREMENTS ===
.MEASURE DC RSNM_V MIN V(VVDD,VVDD2)
.MEASURE DC IREAD_V FIND I(MPG1) WHEN V(VVDD)=0 CROSS=1
.MEASURE DC WNM_V FIND V(BL) WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE DC WNM COMP PARAM='VDD_OPT - WNM_V'

* === MARGIN CHECK ===
.MEASURE DC MARGIN_RSNM PARAM='RSNM_V - 0.1*VDD_OPT'
.MEASURE DC MARGIN_IREAD PARAM='IREAD_V - 1E-6'
.MEASURE DC MARGIN_WNM PARAM='WNM_COMP - 0.15*VDD_OPT'

* === COMPOSITE GOAL (optimization target) ===
.MEASURE DC MARGIN_COMPOSITE
+ PARAM='MIN(MARGIN_RSNM, MARGIN_IREAD, MARGIN_WNM)'
+ GOAL=0

* === OPTIMIZATION MODEL ===
.MODEL VMIN_OPT_MOD OPT METHOD=BISECTION
+ RELIN=1E-4 RELOUT=1E-4 ITROPT=40

* === ANALYSIS ===
.DC VVDD_INJ 0 'VDD_OPT' 0.005
+ OPTIMIZE=OPT1 RESULTS=MARGIN_COMPOSITE MODEL=VMIN_OPT_MOD

* === REVIEW RUN (final result) ===
.ALTER case=review
    .DC VVDD_INJ 0 'VDD_OPT' 0.005

.END

### 14.2 Design Optimization Workbench
* File: sram_design_optimizer.sp
* Purpose: Find optimal WPU, WPD, WPG for target performance
.OPTIONS POST=2

.PARAM WPU_OPT=OPT1(120N, 60N, 300N)
.PARAM WPD_OPT=OPT1(200N, 100N, 400N)
.PARAM WPG_OPT=OPT1(160N, 80N, 300N)
.PARAM VDD_FIX=0.8

* Cell with optimization variables
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W={WPU_OPT} L=30N
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W={WPU_OPT} L=30N
MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W={WPD_OPT} L=30N
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W={WPD_OPT} L=30N
MPG1 BL WL VVDD VSS NMOS_SRAM W={WPG_OPT} L=30N
MPG2 BLB WL VVDD2 VSS NMOS_SRAM W={WPG_OPT} L=30N

.MODEL DES_OPT OPT METHOD=GRADIENT ITROPT=60

* Multi-objective optimization
.MEASURE DC RSNM_T PARAM='RSNM - 0.15*VDD_FIX'
.MEASURE DC WNM_T PARAM='WNM - 0.2*VDD_FIX'
.MEASURE DC IREAD_T PARAM='IREAD - 2E-6'

* Weighted goal (prioritize RSNM slightly)
.MEASURE DC COST PARAM='0.5*RSNM_T + 0.3*WNM_T + 0.2*IREAD_T' GOAL=0

.DC VVDD_INJ 0 'VDD_FIX' 0.005
+ OPTIMIZE=OPT1 RESULTS=COST MODEL=DES_OPT

.END

---

## 15. Quick-Reference: Optimization by Condition Type

### 15.1 Condition-Finding Decision Matrix
| What to Find | Method | Variable | Goal Definition | Recommended Options |
|-------------|--------|----------|----------------|-------------------|
| Vmin (read-limited) | BISECTION | VDD | RSNM - 0.1*VDD = 0 | ITROPT=30, RELIN=1E-4 |
| Vmin (write-limited) | BISECTION | VDD | WNM - 0.15*VDD = 0 | ITROPT=30, RELIN=1E-4 |
| Min Iread | BISECTION | VDD or WL | Iread - 1E-6 = 0 | ITROPT=40 |
| Max temp for stability | BISECTION | TEMP | RSNM - 0.1*VDD = 0 | ITROPT=20 |
| Min WL pulse | BISECTION | WL_PW | WL_PW - Twrite = 0 | ITROPT=30 |
| Optimize cell ratio | GRADIENT | WPU,WPD,WPG | Weighted cost = 0 | ITROPT=60 |
| Width for target current | BISECTION | W | Iread - I_TARGET = 0 | ITROPT=30 |

### 15.2 Common .MEASURE GOAL Patterns
* Goal = 0 (crossing / boundary)
.MEASURE DC MARGIN PARAM='MEASURED - TARGET' GOAL=0

* Goal = maximum (minimize error)
.MEASURE DC ERROR PARAM='ABS(MEASURED - TARGET)'
.MEASURE DC ERROR_MIN MIN ERROR GOAL=0

* Goal < target (constraint satisfaction)
.MEASURE DC CHECK PARAM='MEASURED' GOAL < 1E-6

### 15.3 Post-Optimization Verification Checklist
[ ] Did the optimization converge? Check iteration count in output
[ ] Is the final goal value close to 0? (.mt0 output)
[ ] Are all variables within their defined min/max bounds?
[ ] Run a review simulation at the optimized point
[ ] Compare against brute-force sweep at same point
[ ] Vary initial guess to verify solution is not a local minimum
[ ] For Vmin: verify at least 3 other nearby VDD points

---

> **Revision History**
> - 2026-06-30: Initial version. Covers .OPTIMIZE, .SENS, BISECTION, PASSFAIL, SRAM use cases.
