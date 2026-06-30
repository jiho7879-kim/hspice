---
title: 'HSPICE Yield Modeling and SRAM VMIN Workbench Guide'
subtitle: 'Monte Carlo, Corner Analysis, and Statistical Methodology for SRAM Yield'
version: '1.0'
date: '2026-06-30'
description: 'Complete HSPICE guide for yield modeling, Monte Carlo analysis, corner analysis, and Vmin distribution extraction for SRAM bitcells and mini-arrays.'
tags: [HSPICE, yield, Monte Carlo, Vmin, SRAM, corner, statistical, mismatch, workbench]
language: 'HSPICE'
keywords: [Monte Carlo, Vmin, yield, SRAM, mismatch, corner, agauss, statistical, workbench]
---

# HSPICE Yield Modeling and SRAM VMIN Workbench Guide

> **Purpose**: Statistical yield modeling methodology for SRAM bitcells and mini-arrays.
> **Coverage**: Monte Carlo simulation, corner analysis, Vmin distribution extraction, mismatch modeling, failure-rate prediction.
> **Target**: SRAM yield analysis for 6T bitcell, mini-array, and memory compiler characterization.

---

## Table of Contents

1. [Yield Modeling Overview](#1-yield-modeling-overview)
2. [Statistical Model Parameters](#2-statistical-model-parameters)
3. [Monte Carlo Analysis (.MC)](#3-monte-carlo-analysis-mc)
4. [SRAM VMIN Distribution Extraction](#4-sram-vmin-distribution-extraction)
5. [Corner Analysis (PVT)](#5-corner-analysis-pvt)
6. [Mismatch Modeling](#6-mismatch-modeling)
7. [Failure Probability Estimation](#7-failure-probability-estimation)
8. [Importance Sampling for Rare Events](#8-importance-sampling-for-rare-events)
9. [Mini-Array Statistical Simulation](#9-mini-array-statistical-simulation)
10. [Complete Yield Workbench Template](#10-complete-yield-workbench-template)
11. [References](#11-references)

---

## 1. Yield Modeling Overview

### 1.1 SRAM Yield Challenge
SRAM occupies 50-90% of modern SoC area. A single bitcell failure can kill the entire chip.
Yield modeling predicts the probability of failure for:
- **Read failure**: Cell flips during read (RSNM too low)
- **Write failure**: Unable to write new data (write margin too low)
- **Hold failure**: Data lost during standby (retention failure)
- **Access failure**: Read current too slow (timing failure)

### 1.2 Sources of Variation
| Variation | Type | Distribution | Impact |
|-----------|------|--------------|--------|
| Global process (die-to-die) | Systematic | Gaussian | Shifts all cells equally |
| Local mismatch (within-die) | Random | Gaussian | Varies per cell independently |
| Temperature | Environmental | Uniform | Shifts all cells (corner-based) |
| Voltage (IR drop) | Environmental | Bounded | Supply variation across array |

### 1.3 Statistical Methodology Flow
1. Define failure criteria (e.g., RSNM < 0.1*VDD)
2. Model global + local variation on device parameters
3. Run Monte Carlo simulation (N trials at each VDD)
4. Extract VMIN for each MC trial (minimum VDD passing all criteria)
5. Fit VMIN distribution to Gaussian
6. Compute sigma level (e.g., mu - 6*sigma = VMIN_6sigma)
7. Report yield at target VDD

### 1.4 Terminology
| Term | Definition |
|------|------------|
| VMIN | Minimum VDD at which all cells meet all criteria |
| mu_VMIN | Mean of VMIN distribution |
| sigma_VMIN | Standard deviation of VMIN distribution |
| N_sigma | Number of sigma for target yield (e.g., 6-sigma) |
| Sigma level | Quality metric (higher = better yield) |

---

## 2. Statistical Model Parameters

### 2.1 BSIM4 Statistical Parameters for SRAM
The following BSIM4 parameters are randomized for SRAM Monte Carlo:

| Parameter | Symbol | Distribution | Global Sigma | Mismatch Sigma | Description |
|-----------|--------|--------------|-------------|----------------|-------------|
| VTH0 | Vth | Gaussian | 30 mV | 20 mV | Threshold voltage |
| U0 | Mobility | Gaussian | 5% | 3% | Carrier mobility |
| TOX | Tox | Gaussian | 2% | 1% | Oxide thickness |
| RSH | Rsheet | Gaussian | 5% | ? | Sheet resistance |
| XL | L_int | Gaussian | 3 nm | ? | Length offset |
| XW | W_int | Gaussian | 3 nm | ? | Width offset |

### 2.2 Global Variation (.PARAM + .GAUSS)
* Global variation shifts affect ALL devices equally
.PARAM VTH0_NOM=0.35
.PARAM VTH0_GLB='AGUSS(0, 0.03, 1)'  * Global: mean=0, sigma=30mV
.PARAM VTH0_EFF='VTH0_NOM + VTH0_GLB'

### 2.3 Local Mismatch (.PARAM + .AGAUSS)
* Local mismatch affects each device independently
* agauss(sigma, sigma_ratio, aname) for mismatch modeling
.PARAM VTH0_MIS='AGAUSS(0, 0.02, 1)'  * Mismatch: sigma=20mV
.PARAM VTH0_DEV='VTH0_NOM + VTH0_GLB + VTH0_MIS'

### 2.4 Pelgrom Mismatch Model
* Mismatch standard deviation scales with 1/sqrt(W*L)
* Avth = Pelgrom coefficient (typical ~3 mV-um for 65nm)
.PARAM AVTH=3M  * Pelgrom coefficient (Vth mismatch)
.PARAM VTH_MIS_SIGMA='AVTH / SQRT(W*L)'
.PARAM VTH_MIS_DEV='AGAUSS(0, VTH_MIS_SIGMA, 1)'

### 2.5 Per-Device Mismatch Instantiation
* Each device gets its own mismatch variable
.PARAM MIS_PU1='AGAUSS(0, 0.02, 1)'
.PARAM MIS_PU2='AGAUSS(0, 0.02, 2)'
.PARAM MIS_PD1='AGAUSS(0, 0.02, 3)'
.PARAM MIS_PD2='AGAUSS(0, 0.02, 4)'
.PARAM MIS_PG1='AGAUSS(0, 0.02, 5)'
.PARAM MIS_PG2='AGAUSS(0, 0.02, 6)'

* Apply to devices
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W=WPU L=LCELL
+ VTH0='VTH0_NOM + MIS_PU1'
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W=WPU L=LCELL
+ VTH0='VTH0_NOM + MIS_PU2'

---

## 3. Monte Carlo Analysis (.MC)

### 3.1 Monte Carlo Syntax
.MC [RUNS] [ANALYSIS] [MEASURE_LIST] [OUTPUT=ALL/SUMMARY/DATA]
+ [SEED=value] [STATS=value]

| Parameter | Description |
|-----------|-------------|
| RUNS | Number of Monte Carlo iterations |
| ANALYSIS | Analysis type (DC, TRAN) |
| MEASURE_LIST | Measures to collect statistics on |
| OUTPUT | Output control: ALL, SUMMARY, DATA |
| SEED | Random seed for reproducibility |
| STATS | Statistical distribution type (GAUSS/UNIF) |

### 3.2 Basic Monte Carlo Setup
.OPTIONS POST=2 RUNLVL=5 MEASOUT=1

* Statistical parameter definitions
.PARAM VTH0_PU='AGAUSS(0, 0.02, 11)'
.PARAM VTH0_PD='AGAUSS(0, 0.02, 12)'
.PARAM VTH0_PG='AGAUSS(0, 0.02, 13)'

* Device with mismatch
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W=WPU L=LCELL
+ VTH0='0.35 + VTH0_PU'

* Measurements
.MEASURE DC RSNM TRIG...
.MEASURE DC IREAD VAL...
.MEASURE DC WNM VAL...

* Monte Carlo run
.MC 1000 DC RSNM IREAD WNM OUTPUT=ALL
+ SEED=12345

### 3.3 Monte Carlo Output Files
| File | Content |
|------|---------|
| output.mc0 | Monte Carlo statistical summary |
| output.mt0 | Measurement results (last run) |
| output.mt# | Per-run measurements (RUN# = mt#) |

### 3.4 Statistical Output Summary (.mc0)
The .mc0 file contains:
 STANDARD_MC
RSNM: MU=0.185 SIGMA=0.012 MIN=0.142 MAX=0.212
IREAD: MU=3.21E-05 SIGMA=2.1E-06 MIN=2.5E-05 MAX=3.8E-05
WNM: MU=0.245 SIGMA=0.015 MIN=0.192 MAX=0.278

### 3.5 MC Control Options
* Output all runs to individual .mt# files
.MC 1000 DC RSNM OUTPUT=ALL

* Output only statistical summary (faster)
.MC 1000 DC RSNM OUTPUT=SUMMARY

* Output as .gr# data file for external processing
.MC 1000 DC RSNM OUTPUT=DATA

* Multi-measurement Monte Carlo
.MC 500 DC RSNM IREAD WNM VTRIP SVNM SINM
+ OUTPUT=ALL

### 3.6 IMPORTANT: .MC SEED for Repeatability
* Use SEED to reproduce exact random sequence
.MC 1000 DC RSNM OUTPUT=ALL SEED=12345
* Same SEED + same parameters = identical results

### 3.7 MC with .ALTER for multi-condition
* Combine .ALTER and .MC for PVT + statistical
.ALTER case=TT_25C
.MC 100 DC RSNM OUTPUT=ALL

.ALTER case=SS_125C
.MC 100 DC RSNM OUTPUT=ALL

.ALTER case=FF_m40C
.MC 100 DC RSNM OUTPUT=ALL

### 3.8 Nonlinear Tail Extraction via Model-Based ΔVth Sweep

#### 3.8.1 The Problem: Linearity Assumption in 6σ Tail
* Standard yield estimation: `Iread@6σ = MEAN(Iread) - 6 * STD(Iread)`
* This assumes Iread is linearly related to Vth shift — **WRONG for HVT devices**
* Reality: Iread follows an exponential function in subthreshold → log-linear at best
* Deeper tail: GIDL and junction leakage dominate → **flattening/saturation**
* Result: linear extrapolation overestimates tail current by 2× or more for HVT

```
Iread(Vth) = Isub(Vth) + IGIDL + IJUNC
            ↘ exp(-Vth/nVt)   ↘ const     ↘ const
            → deep tail에서는 GIDL이 Isub보다 커짐 → flatten
```

#### 3.8.2 Solution: Model-Based Sigma + ΔVth Sweep (Fully HSPICE Internal)

**원칙**: sigma를 "사용자가 입력한 값"이 아니라, model parameter(AVTH0)로 HSPICE가 직접 계산하게 한다. 그 sigma로 ΔVth를 sweep하여 model이 실제로 계산하는 Iread를 6σ 지점에서 직접 읽는다.

##### Step 1: Model Parameter로 σ(Vth) 계산
* Pelgrom mismatch model: σ(Vth) = AVTH0 / sqrt(W_eff × L_eff)
* AVTH0는 .MODEL 카드의 mismatch coefficient (foundry 제공)
* W_eff = NFIN * (2*H_FIN + T_FIN) for FinFET, or W for planar

.PARAM AVTH0_MODEL=2E-3        * V-um, from .MODEL card
.PARAM W_EFF=160N              * Effective width
.PARAM L_EFF=30N               * Effective length
.PARAM SIGMA_VTH='AVTH0_MODEL / SQRT(W_EFF * L_EFF)'
* ↑ HSPICE가 model parameter로 1σ(Vth)를 runtime 계산

##### Step 2: ΔVth Sweep — Nonlinearity를 model이 직접 계산하게 함
* Pass-gate device에 Vth offset을 NSIG * SIGMA_VTH 만큼 인가
* DC sweep으로 NSIG: 0 → -8 (0.1σ step)
* 각 step에서 HSPICE device model이 Iread를 계산 (GIDL, junction leak 모두 반영)

* File: sram_tail_extraction.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=6 MEASOUT=1

* SSG global corner
.LIB './corners.lib' SSG

* Local mismatch sigma from model parameters
.PARAM AVTH0_PG=2E-3           * from .MODEL card
.PARAM WPG=160N LCELL=30N
.PARAM SIGMA_VTH='AVTH0_PG / SQRT(WPG * LCELL)'

* Sweep variable: number of sigma from nominal
.PARAM NSIG=0

* 6T SRAM — pass-gate with explicit Vth modulation
MPG1 BL WL VVDD 0 NMOS_SRAM W=WPG L=LCELL
+ VTH0='VTH0_NOM + NSIG * SIGMA_VTH'
*           ↑ model-based sigma로 Vth shift

* Other devices at nominal SSG corner
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W=120N L=30N
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W=120N L=30N
MPD1 VVDD VVDD2 0 0 NMOS_SRAM W=200N L=30N
MPD2 VVDD2 VVDD 0 0 NMOS_SRAM W=200N L=30N
MPG2 BLB WL VVDD2 0 NMOS_SRAM W=WPG L=LCELL

* Read condition
WL WL 0 DC=VDD
BL BL 0 DC=VDD
BLB BLB 0 DC=VDD

* Core: NSIG sweep
.DC NSIG 0 -8 -0.1
.MEASURE DC IREAD_EACH I(MPG1)        * Each step's Iread
.MEASURE DC IREAD_6SIG FIND I(MPG1) AT NSIG=-6    * Direct 6σ tail

##### Step 3: (Optional) MC로 σ(Vth) 검증
* 작은 MC로 model의 실제 σ(Vth)를 추출하여 SIGMA_VTH와 비교
.MC 200 RUN MEASURE VTH_MON
.MEASURE MC SIGMA_MC STD VTH_MON
* SIGMA_MC ≈ SIGMA_VTH → model 공식 신뢰 가능

#### 3.8.3 Result Interpretation

| NSIG | Iread | Notes |
|------|-------|-------|
| 0 (SSG mean) | 5.23 uA | SSG corner nominal |
| -3 | 3.11 uA | Near-linear region |
| -6 | **1.15 uA** | **6σ tail (HVT nonlinearity + GIDL 포함)** |
| -8 | 0.51 uA | GIDL dominant, flattening |

* Linear extrapolation (wrong): 5.23 - 6*0.5 = **2.23 uA**
* Model direct (correct): **1.15 uA** ← 약 2배 차이

#### 3.8.4 Multi-Device Mismatch (Full Cell)
* 실제 SRAM cell은 PG, PD, PU 6개 device 모두 mismatch
* Full cell tail은 각 device Vth를 동시에 shift하여 worst-case 조합 탐색
* 6차원 sweep 대신 sensitivity-guided approach:

.PARAM NSIG=0
* All devices shift proportionally
MPU1 ... VTH0='VTH0_NOM + NSIG * SIGMA_VTH_PU'
MPU2 ... VTH0='VTH0_NOM + NSIG * SIGMA_VTH_PU'
MPD1 ... VTH0='VTH0_NOM + NSIG * SIGMA_VTH_PD'
MPD2 ... VTH0='VTH0_NOM + NSIG * SIGMA_VTH_PD'
MPG1 ... VTH0='VTH0_NOM + NSIG * SIGMA_VTH_PG'
MPG2 ... VTH0='VTH0_NOM + NSIG * SIGMA_VTH_PG'

.DC NSIG 0 -6 -0.1
.MEASURE DC IREAD_6SIG_FULL FIND I(MPG1) AT NSIG=-6

#### 3.8.5 When to Use This Method
| Scenario | Linear MC (mean-6σ) | Model-Based Sweep |
|----------|-------------------|-------------------|
| SVT (Standard Vt) | Acceptable (~10% error) | Better but overkill |
| HVT (High Vt) | **Unsafe (~50% error)** | Required |
| LVT (Low Vt) | Acceptable | Not needed |
| Stacked devices | Moderate error | Recommended |
| Subthreshold operation (VDD < Vth) | **Unsafe** | Required |

---

## 4. SRAM VMIN Distribution Extraction

### 4.1 VMIN Definition
VMIN is the minimum supply voltage at which the bitcell operates correctly across all failure criteria:
- RSNM > RSNM_MIN (e.g., 0.1 * VDD)
- IREAD > IREAD_MIN (e.g., 1 uA)
- WNM > WNM_MIN (e.g., 0.15 * VDD)
- SNM_HOLD > HSNM_MIN (e.g., 0.15 * VDD)
- TWRITE < TWRITE_MAX (e.g., 2x wordline pulse)

### 4.2 VMIN Extraction Methodology
For each Monte Carlo trial at a given nominal VDD:
1. Bias the cell at VDD
2. Measure all metrics (RSNM, IREAD, WNM, etc.)
3. Check against pass/fail criteria
4. Record pass (1) or fail (0) at this VDD
5. Repeat at multiple VDD points
6. Fit cumulative failure vs VDD

Step 1: Define failure criteria as .MEASURE expressions
.MEASURE DC RSNM_CHECK PARAM='RSNM - 0.1*VDD'
.MEASURE DC IREAD_CHECK PARAM='IREAD - 1E-6'
.MEASURE DC WNM_CHECK PARAM='WNM - 0.15*VDD'

Step 2: Define cell pass/fail (all checks must pass)
.MEASURE DC CELL_OK PARAM='MIN(RSNM_CHECK, IREAD_CHECK, WNM_CHECK)'
.MEASURE DC CELL_FAIL PARAM='CELL_OK < 0'

### 4.3 VMIN Sweep Across VDD
* Parameterized VDD sweep for Vmin characterization
.PARAM VDD_SWEEP=0.8

* Run .DC at each VDD in .ALTER
.ALTER case=VDD_0.80V
    VDD_SRC VDD 0 DC=0.80
.ALTER case=VDD_0.75V
    VDD_SRC VDD 0 DC=0.75
.ALTER case=VDD_0.70V
    VDD_SRC VDD 0 DC=0.70
.ALTER case=VDD_0.65V
    VDD_SRC VDD 0 DC=0.65
.ALTER case=VDD_0.60V
    VDD_SRC VDD 0 DC=0.60

### 4.4 VMIN Statistical Extraction
* For each MC trial, find VDD at which cell passes
.MEASURE DC VMIN_FOUND FIND V(VDD) WHEN RSNM=0.1*V(VDD) CROSS=1
.MEASURE DC VMIN_WR FIND V(VDD) WHEN WNM=0.15*V(VDD) CROSS=1
.MEASURE DC VMIN_RD FIND V(VDD) WHEN IREAD=1E-6 CROSS=1
.MEASURE DC VMIN_MAX PARAM='MAX(VMIN_FOUND, VMIN_WR, VMIN_RD)'

### 4.5 VMIN Distribution Post-Processing
After 1000 MC runs, extract from .mc0:
VMIN_READ: MU=0.62V SIGMA=0.035V
VMIN_WRITE: MU=0.58V SIGMA=0.040V

6-sigma VMIN = mu + 6 * sigma
VMIN_6SIGMA_READ = 0.62 + 6*0.035 = 0.83V
VMIN_6SIGMA_WRITE = 0.58 + 6*0.040 = 0.82V

### 4.6 VMIN Binning for Yield Analysis
.MEASURE DC VMIN_BIN_0_6 PARAM='VMIN_MAX < 0.6'
.MEASURE DC VMIN_BIN_0_7 PARAM='VMIN_MAX < 0.7'
.MEASURE DC VMIN_BIN_0_8 PARAM='VMIN_MAX < 0.8'

---

## 5. Corner Analysis (PVT)

### 5.1 Process Corners
| Corner | NMOS | PMOS | Description |
|--------|------|------|-------------|
| TT | Typical | Typical | Nominal process |
| SS | Slow | Slow | Worst-case speed |
| FF | Fast | Fast | Best-case speed |
| SF | Slow | Fast | Cross corner |
| FS | Fast | Slow | Cross corner |

### 5.2 Temperature Corners
| Corner | Temperature | Description |
|--------|-------------|-------------|
| Cold | -40C | Best performance, worst leakage |
| Nominal | 25C | Room temperature |
| Hot | 85C | Typical operating |
| Extreme | 125C | Worst-case leakage |

### 5.3 Voltage Corners
| Corner | VDD | Description |
|--------|-----|-------------|
| High | VDD_NOM + 10% | Max supply |
| Nominal | VDD_NOM | Typical |
| Low | VDD_NOM - 10% | Min supply |

### 5.4 Corner Workbench with .ALTER
* File: sram_corners.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1

.PARAM VDD_NOM=0.8
.PARAM WPU=120N WPD=200N WPG=160N LCELL=30N

* Device models (selected by .ALTER)
.LIB models_tt.lib TT

* Nominal run
.MEASURE DC RSNM MIN V(VVDD,VVDD2)
.MEASURE DC IREAD FIND I(MPG1) WHEN V(VVDD)=0 CROSS=1
.MEASURE DC WNM_TRIP FIND V(BL) WHEN V(VVDD)=V(VVDD2) CROSS=1

* --- PVT Corners ---
.ALTER case=TT_25C
    .LIB models_tt.lib TT
    .TEMP 25
.ALTER case=SS_125C
    .LIB models_ss.lib SS
    .TEMP 125
.ALTER case=FF_m40C
    .LIB models_ff.lib FF
    .TEMP -40
.ALTER case=SF_25C
    .LIB models_sf.lib SF
    .TEMP 25
.ALTER case=FS_25C
    .LIB models_fs.lib FS
    .TEMP 25
.ALTER case=TT_125C
    .LIB models_tt.lib TT
    .TEMP 125
.ALTER case=TT_m40C
    .LIB models_tt.lib TT
    .TEMP -40

### 5.5 Corner Table Output (.mt0)
MT0 columns for each .ALTER corner:
Case   RSNM    IREAD    WNM
TT_25C 0.185   3.2E-05  0.245
SS_125C 0.145  2.1E-05  0.195
FF_m40C 0.225  4.5E-05  0.285

### 5.6 Worst-Case Corner Identification
* Read VMIN worst case: SS_125C (slow + hot = weakest read)
* Write Margin worst case: SF (slow NMOS pass-gate, fast PMOS pull-up)
* Leakage worst case: FF_125C (fast + hot = max leakage)

---

## 6. Mismatch Modeling

### 6.1 Pelgrom Mismatch Model
Pelgrom's law describes random mismatch variance:
  sigma^2(Vth) = Avth^2 / (W * L) + Svth^2

where:
- Avth = matching constant (um*mV, process-specific)
- Svth = variation independent of area
- W, L = device dimensions in um

### 6.2 Mismatch Parameter Setup with Pelgrom Scaling
.PARAM AVTH_PU=3E-3  * 3 mV-um for PU
.PARAM AVTH_PD=2.8E-3  * 2.8 mV-um for PD
.PARAM AVTH_PG=3.2E-3  * 3.2 mV-um for PG

.PARAM WPU=120N WPD=200N WPG=160N LCELL=30N

.PARAM SIGMA_PU='AVTH_PU / SQRT(WPU*LCELL)'
.PARAM SIGMA_PD='AVTH_PD / SQRT(WPD*LCELL)'
.PARAM SIGMA_PG='AVTH_PG / SQRT(WPG*LCELL)'

* Per-device mismatch (unique random seed per device)
.PARAM MIS_PU1='AGAUSS(0, SIGMA_PU, 1)'
.PARAM MIS_PU2='AGAUSS(0, SIGMA_PU, 2)'
.PARAM MIS_PD1='AGAUSS(0, SIGMA_PD, 3)'
.PARAM MIS_PD2='AGAUSS(0, SIGMA_PD, 4)'
.PARAM MIS_PG1='AGAUSS(0, SIGMA_PG, 5)'
.PARAM MIS_PG2='AGAUSS(0, SIGMA_PG, 6)'

* Apply to devices via VTH0
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W={WPU} L={LCELL}
+ VTH0='VTH0_PU_NOM + MIS_PU1'

### 6.3 Device Mismatch Distribution (.SIGMA)
* Directly specify mismatch using .SIGMA parameter on .MODEL
* This is passed directly to BSIM4 model parameters

.MODEL NMOS_SRAM NMOS LEVEL=14
+ VTH0=0.35
+ SIGMA0=0.03  * Global sigma for VTH0
+ SIGMA1=0.02  * Mismatch sigma for VTH0

* With SIGMA specification, HSPICE automatically:
* - Generates random variations on VTH0
* - Creates separate instances for each device instantiation
* - Scales by 1/sqrt(W*L) automatically

### 6.4 Corner + Mismatch Combined
* Global corner (e.g., SS) shifts mean
* Local mismatch adds variance around corner mean

.DC VVDD_INJ 0 'VDD_NOM' 0.005
.MC 500 DC RSNM IREAD WNM OUTPUT=ALL SEED=42

---

## 7. Failure Probability Estimation

### 7.1 Failure Rate from Monte Carlo
After N Monte Carlo runs:
- Count F = number of failing cells (any criterion violated)
- Failure rate p_fail = F / N
- Yield = 1 - p_fail

### 7.2 Yield Calculation for N_cell Array
For an array with N_cell independent cells:
- Cell failure probability: p_cell = F / N_MC
- Array yield: Y_array = (1 - p_cell)^N_cell
- Equivalent sigma: sigma_eq = NORMSINV(Y_array)

Example:
- p_cell = 1E-6 (1 ppm per cell)
- N_cell = 1M (1 Mbit SRAM)
- Y_array = (1 - 1E-6)^1E6 = exp(-1) = 36.8%

### 7.3 Sigma Level from Monte Carlo
* From RSNM distribution (Gaussian fit):
* mu_RSNM = 0.185V, sigma_RSNM = 0.012V
* Fail condition: RSNM < 0.08V (0.1*VDD at 0.8V)
* Sigma level = (mu - fail_condition) / sigma = (0.185-0.08)/0.012 = 8.75 sigma

### 7.4 Number of MC Runs for Yield Estimation
| Desired Precision | Min MC Runs | Notes |
|------------------|-------------|-------|
| +/-10% on sigma | 200 | Quick estimate |
| +/-5% on sigma | 1000 | Standard |
| +/-2% on sigma | 5000 | Production |
| 6-sigma yield | 1M+ | Use importance sampling |

### 7.5 Failure Probability from .MEASURE < 0
.MEASURE DC RSNM_MIN MIN V(VVDD,VVDD2)
.MEASURE DC RSNM_FAIL PARAM='RSNM_MIN < 0.1*VDD_NOM'

* In .mc0 output:
RSNM_FAIL: SUM=5  * 5 failures out of 1000 runs
p_fail = 5/1000 = 0.005

---

## 8. Importance Sampling for Rare Events

### 8.1 Why Importance Sampling
Standard Monte Carlo for 6-sigma (2E-9 failure rate) requires billions of runs.
Importance sampling shifts the distribution mean to increase failure rate,
then re-weights results to recover true distribution.

### 8.2 Importance Sampling in HSPICE (Mean Shift)
* Increase mismatch sigma artificially to generate more failures
* Shift global corner to worst-case (SS + high mismatch)

* Standard MC
.PARAM SIGMA_SCALE=1.0
.PARAM MIS_SIGMA='0.02 * SIGMA_SCALE'

* Importance sampling: scale up mismatch to generate more failures
.ALTER case=IS_2x
    .PARAM SIGMA_SCALE=2.0  * Double mismatch, 4x failure rate

.ALTER case=IS_3x
    .PARAM SIGMA_SCALE=3.0  * Triple mismatch, 9x failure rate

### 8.3 Post-Processing: Re-Weighting
Python re-weighting formula:
  w_i = exp(-0.5 * (x_i^2 - ((x_i - shift)/scale)^2))
  p_fail = sum(w_i * I_fail_i) / sum(w_i)

* I_fail_i = 1 if run i failed, 0 otherwise
* x_i = original random variable value
* shift = mean shift applied
* scale = sigma scaling factor

---

## 9. Mini-Array Statistical Simulation

### 9.1 Problem
Realistic SRAM yield requires simulating multiple cells simultaneously
to capture array-level interactions (bitline leakage, column mux, etc.)

### 9.2 2x2 Mini-Array Setup
* File: sram_mini_array_mc.sp
.OPTIONS POST=2 RUNLVL=5 MEASOUT=1

.PARAM NROW=2 NCOL=2

* Bitcell array (4 cells, each with independent mismatch)
XCELL_00 BL_0 BLB_0 WL_0 VDD VSS VVDD_00 VVDD_00B SRAM6T
XCELL_01 BL_1 BLB_1 WL_0 VDD VSS VVDD_01 VVDD_01B SRAM6T
XCELL_10 BL_0 BLB_0 WL_1 VDD VSS VVDD_10 VVDD_10B SRAM6T
XCELL_11 BL_1 BLB_1 WL_1 VDD VSS VVDD_11 VVDD_11B SRAM6T

* Wordline drivers
WL_DRV_0 WL_0 0 PULSE(0 VDD 0 10P 10P 'WL_PW' 'PERIOD')
WL_DRV_1 WL_1 0 PULSE(0 VDD 'PERIOD/2' 10P 10P 'WL_PW' 'PERIOD')

* Sense amplifier instance
XSA BL_0 BLB_0 SA_OUT_0 SA_EN VDD VSS SA_LATCH

* Measurements per cell
.MEASURE DC RSNM_00 MIN V(VVDD_00,VVDD_00B)
.MEASURE DC RSNM_01 MIN V(VVDD_01,VVDD_01B)
.MEASURE DC RSNM_10 MIN V(VVDD_10,VVDD_10B)
.MEASURE DC RSNM_11 MIN V(VVDD_11,VVDD_11B)

* Array-level metrics
.MEASURE DC RSNM_ARRAY_MIN MIN RSNM_00 RSNM_01 RSNM_10 RSNM_11
.MEASURE DC RSNM_FAIL_ARRAY PARAM='RSNM_ARRAY_MIN < 0.1*VDD'

* Monte Carlo across 4 cells simultaneously
.MC 1000 DC RSNM_00 RSNM_01 RSNM_10 RSNM_11 OUTPUT=ALL

### 9.3 Array Timing with Monte Carlo
* Transient analysis for access time distribution
.MEASURE TRAN TREAD_00 TRIG V(WL_0) VAL='VDD*0.5' RISE=1
+                      TARG V(BL_0) VAL='VDD*0.9' FALL=1
.MEASURE TRAN TREAD_ARRAY MAX TREAD_00 TREAD_01 TREAD_10 TREAD_11
.MEASURE TRAN TREAD_FAIL PARAM='TREAD_ARRAY > TREAD_MAX'

.MC 500 TRAN TREAD_ARRAY TREAD_FAIL OUTPUT=ALL

---

## 10. Complete Yield Workbench Template

### 10.1 Full SRAM Yield Analysis Deck
* File: sram_yield_complete.sp
* Purpose: Complete yield analysis for 6T SRAM bitcell
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1 LISFILE=1
.TEMP 25

* === PARAMETERS ===
.PARAM VDD_NOM=0.8
.PARAM WPU=120N WPD=200N WPG=160N LCELL=30N

* === MISMATCH PARAMETERS ===
.PARAM MIS_PU1='AGAUSS(0, 0.02, 1)'
.PARAM MIS_PU2='AGAUSS(0, 0.02, 2)'
.PARAM MIS_PD1='AGAUSS(0, 0.02, 3)'
.PARAM MIS_PD2='AGAUSS(0, 0.02, 4)'
.PARAM MIS_PG1='AGAUSS(0, 0.02, 5)'
.PARAM MIS_PG2='AGAUSS(0, 0.02, 6)'

* === SUPPLIES ===
VDD_SRC VDD 0 DC='VDD_NOM'
VSS_SRC VSS 0 DC=0
WL_SRC WL 0 DC='VDD_NOM'
BL_SRC BL 0 DC='VDD_NOM'
BLB_SRC BLB 0 DC='VDD_NOM'
VVDD_INJ VVDD VSS DC 0

* === 6T SRAM BITCELL ===
* (with individual mismatch per device)
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W={WPU} L={LCELL}
+ VTH0='0.35 + MIS_PU1'
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W={WPU} L={LCELL}
+ VTH0='0.35 + MIS_PU2'
MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W={WPD} L={LCELL}
+ VTH0='0.35 + MIS_PD1'
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W={WPD} L={LCELL}
+ VTH0='0.35 + MIS_PD2'
MPG1 BL WL VVDD VSS NMOS_SRAM W={WPG} L={LCELL}
+ VTH0='0.35 + MIS_PG1'
MPG2 BLB WL VVDD2 VSS NMOS_SRAM W={WPG} L={LCELL}
+ VTH0='0.35 + MIS_PG2'

* === DC ANALYSIS ===
.DC VVDD_INJ 0 'VDD_NOM' 0.005

* === READ MEASUREMENTS ===
.MEASURE DC RSNM MIN V(VVDD,VVDD2)
.MEASURE DC IREAD FIND I(MPG1) WHEN V(VVDD)=0 CROSS=1

* === WRITE MEASUREMENTS ===
.MEASURE DC WNM_TRIP FIND V(BL) WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE DC WNM PARAM='VDD_NOM - WNM_TRIP'

* === HOLD MEASUREMENTS ===
.MEASURE DC HSNM MIN V(VVDD,VVDD2)

* === FAILURE CONDITIONS ===
.MEASURE DC FAIL_READ PARAM='RSNM < 0.1*VDD_NOM'
.MEASURE DC FAIL_WRITE PARAM='WNM < 0.15*VDD_NOM'
.MEASURE DC FAIL_HOLD PARAM='HSNM < 0.15*VDD_NOM'
.MEASURE DC FAIL_TOTAL PARAM='FAIL_READ + FAIL_WRITE + FAIL_HOLD'

* === MONTE CARLO ===
.MC 1000 DC RSNM IREAD WNM HSNM
+ FAIL_READ FAIL_WRITE FAIL_HOLD FAIL_TOTAL
+ OUTPUT=ALL SEED=42

* === TEMPERATURE CORNERS ===
.ALTER case=hot
    .TEMP 125
    .MC 1000 DC RSNM FAIL_READ FAIL_WRITE FAIL_HOLD FAIL_TOTAL
+   OUTPUT=ALL SEED=42

.ALTER case=cold
    .TEMP -40
    .MC 1000 DC RSNM FAIL_READ FAIL_WRITE FAIL_HOLD FAIL_TOTAL
+   OUTPUT=ALL SEED=42

.END

