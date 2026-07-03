---
title: 'HSPICE Unit Transistor (UT) Characterization Guide'
subtitle: 'Complete Measurement Methodology for Single-Device Characterization'
version: '1.0'
date: '2026-06-30'
description: 'Complete HSPICE measurement guide for unit-transistor characterization. Covers Vtsat, Vtlin, Idsat, Idlin, DIBL, subthreshold swing (Ssat), Isoff, Idoff, Gmmax, Rodlin, Rch, and all standard MOSFET metrics.'
tags: [HSPICE, UT, unit transistor, characterization, measurement, MOSFET, BSIM, device]
language: 'HSPICE'
keywords: [Vtsat, Vtlin, Idsat, DIBL, SSAT, Isoff, Gmmax, Rodlin, Rch, MOSFET, BSIM4]
---

# HSPICE Unit Transistor (UT) Characterization Guide

> **Purpose**: Complete measurement methodology for single MOSFET (unit transistor) characterization.
> **Coverage**: Saturation/linear Vth, drive current, DIBL, subthreshold swing, leakage, transconductance, output resistance.
> **Target**: Test-structure level characterization for model-to-hardware correlation (MHC).

---

## Table of Contents

1. [UT Characterization Overview](#1-ut-characterization-overview)
2. [DC Id-Vg Sweep ? Saturation and Linear](#2-dc-id-vg-sweep--saturation-and-linear)
3. [Vtsat (Saturation Threshold Voltage)](#3-vtsat-saturation-threshold-voltage)
4. [Vtlin (Linear Threshold Voltage)](#4-vtlin-linear-threshold-voltage)
5. [Idsat and Idlin (Drive Current)](#5-idsat-and-idlin-drive-current)
6. [DIBL (Drain-Induced Barrier Lowering)](#6-dibl-drain-induced-barrier-lowering)
7. [Subthreshold Swing (SSAT)](#7-subthreshold-swing-ssat)
8. [Isoff and Idoff (Off-State Leakage)](#8-isoff-and-idoff-off-state-leakage)
9. [Transconductance (Gm and Gmmax)](#9-transconductance-gm-and-gmmax)
10. [Output Resistance (Rodlin, Rch)](#10-output-resistance-rodlin-rch)
11. [Body Effect and Back-Bias Characterization](#11-body-effect-and-back-bias-characterization)
12. [Capacitance-Voltage (CV) Characterization](#12-capacitance-voltage-cv-characterization)
13. [Temperature Dependence](#13-temperature-dependence)
14. [Complete UT Workbench Template](#14-complete-ut-workbench-template)
15. [References](#15-references)

---

## 1. UT Characterization Overview

### 1.1 Device Naming Convention (per naming guide)
| Name | Type | Description |
|------|------|-------------|
| M_DUT | NMOS or PMOS | Device under test |
| M_NCH_W1 | NMOS, width variant 1 | Width = W1 |
| M_PCH_W1 | PMOS, width variant 2 | Width = W1 |
| M_REF | Reference device | Matched pair reference |

### 1.2 Terminal Naming
| Terminal | Node | Description |
|----------|------|-------------|
| Gate | G | Gate bias |
| Drain | D | Drain bias |
| Source | S | Source (usually 0V) |
| Body/Bulk | B | Body bias (well) |

### 1.3 Standard Bias Voltages
| Parameter | NMOS | PMOS |
|-----------|------|------|
| VDD_NOM | 0.8V (nominal) | 0.8V |
| VG_MAX | VDD_NOM | VDD_NOM |
| VD_SAT | VDD_NOM | VDD_NOM |
| VD_LIN | 0.05V | 0.05V |

### 1.4 Standard Subcircuit Model
.SUBCKT UT_NCH D G S B PARAMS: W=1U L=30N
M1 D G S B NMOS_UT W={W} L={L}
.ENDS UT_NCH

.SUBCKT UT_PCH D G S B PARAMS: W=1U L=30N
M1 D G S B PMOS_UT W={W} L={L}
.ENDS UT_PCH

---

## 2. DC Id-Vg Sweep ? Saturation and Linear

### 2.1 Saturation Id-Vg Setup (VD = VDD)
* NMOS: VD = VDD_NOM, VG sweep 0 -> VDD_NOM, VS = 0, VB = 0
.OPTIONS POST=2
.TEMP 25

VG_SRC G 0 DC=0
VD_SRC D 0 DC='VDD_NOM'
VS_SRC S 0 DC=0
VB_SRC B 0 DC=0

M_DUT D G S B NMOS_UT W=1U L=30N

.DC VG_SRC 0 'VDD_NOM' 0.005
.PRINT DC I(VD_SRC) I(VG_SRC) V(G) V(D)

### 2.2 Linear Id-Vg Setup (VD = 0.05V)
* NMOS: VD = 0.05V, VG sweep 0 -> VDD_NOM, VS = 0, VB = 0
.DC VG_SRC 0 'VDD_NOM' 0.005

### 2.3 Id-Vd Sweep (Output Characteristic)
* Sweep VD at multiple VG bias points
.DC VD_SRC 0 'VDD_NOM' 0.01 VG_SRC 0.3 'VDD_NOM' 0.15
.PRINT DC I(VD_SRC) V(D) V(G)

### 2.4 Measure Current Naming
.MEASURE DC IDS_VD N I(VD_SRC)
.MEASURE DC IGS AT I(VG_SRC) * Gate leakage at max VG

---

## 3. Vtsat (Saturation Threshold Voltage)

### 3.1 Definition
Vtsat is the gate voltage at which the channel inverts in saturation (VD = VDD).
The industry-standard extraction method uses the **constant-current method**:
Vth = VG at ID = 100 nA x (W/L) or at peak Gm linear extrapolation.

### 3.2 Method 1: Constant-Current Method (Industry Standard)
Ith = Ith0 * (W/L), where Ith0 = 100 nA for NMOS (or 70 nA for PMOS)

.MEASURE DC VTSAT_CC FIND V(G) WHEN I(VD_SRC)=100N*W/L

### 3.3 Method 2: Linear Extrapolation (Max Gm Method)
* Find VG at maximum transconductance, then extrapolate to ID=0

* Step 1: Compute Gm = dId/dVg
.MEASURE DC GM_SAT DERIV OF I(VD_SRC) BY V(G)

* Step 2: Find VG at peak Gm
.MEASURE DC VG_GMMAX_SAT FIND V(G) WHEN GM_SAT=MAX

* Step 3: Find Id at peak Gm point
.MEASURE DC ID_GMMAX_SAT FIND I(VD_SRC) AT='VG_GMMAX_SAT'

* Step 4: Extrapolate to Vth (Id=0)
.MEASURE DC VTSAT_LE PARAM='VG_GMMAX_SAT - ID_GMMAX_SAT/GM_MAX_SAT'

### 3.4 Method 3: Second-Derivative Method
.MEASURE DC GM2_SAT DERIV OF GM_SAT BY V(G)
.MEASURE DC VTSAT_SD FIND V(G) WHEN GM2_SAT=MAX

### 3.5 Vtsat Temperature Dependence
.MEASURE DC VTSAT_HT FIND V(G) WHEN I(VD_SRC)=100N*W/L
.MEASURE DC DVTSAT_DT PARAM='(VTSAT_HT - VTSAT_CC)/105'
* Vth typically drops ~-0.8 to -1.2 mV/C

---

## 4. Vtlin (Linear Threshold Voltage)

### 4.1 Definition
Vtlin is the threshold voltage measured at low drain bias (VD = 0.05V).
Linear Vth is higher than saturation Vth due to less DIBL.

### 4.2 Constant-Current Method (Linear)
.MEASURE DC VTLIN_CC FIND V(G) WHEN I(VD_SRC)=100N*W/L

### 4.3 Linear Extrapolation (Gm method, VD=0.05V)
.MEASURE DC GM_LIN DERIV OF I(VD_SRC) BY V(G)
.MEASURE DC VG_GMMAX_LIN FIND V(G) WHEN GM_LIN=MAX
.MEASURE DC ID_GMMAX_LIN FIND I(VD_SRC) AT='VG_GMMAX_LIN'
.MEASURE DC GM_MAX_LIN MAX GM_LIN
.MEASURE DC VTLIN_LE PARAM='VG_GMMAX_LIN - ID_GMMAX_LIN/GM_MAX_LIN'

### 4.4 Vtlin Comparison
.MEASURE DC DVT_VTV PARAM='VTLIN_CC - VTSAT_CC'
* Typically Vtlin > Vtsat by 20-80 mV depending on DIBL

---

## 5. Idsat and Idlin (Drive Current)

### 5.1 Idsat (Saturation Drive Current)
Drain current at VG = VD = VDD_NOM (saturation condition).

.MEASURE DC IDSAT FIND I(VD_SRC) AT='VD_SAT'
.MEASURE DC IDSAT_W PARAM='IDSAT / W'  * Normalized to width

.MEASURE DC IDSAT_VBD FIND I(VD_SRC) AT='VDD_NOM'
.MEASURE DC IDSAT_VAR SIGMA IDSAT  * Mismatch sigma

### 5.2 Idlin (Linear Drive Current)
Drain current at VG = VDD_NOM, VD = 0.05V.
.MEASURE DC IDLIN FIND I(VD_SRC) AT='VDD_NOM'
.MEASURE DC IDLIN_W PARAM='IDLIN / W'

### 5.3 Ion and Ioff
.MEASURE DC ION IDSAT  * Ion = drive current
.MEASURE DC IOFF FIND I(VD_SRC) AT=0  * Ioff = leakage at VG=0, VD=VDD

### 5.4 Current Ratio Metrics
.MEASURE DC ION_IOFF PARAM='ION / IOFF'
.MEASURE DC IDSAT_IDLIN PARAM='IDSAT / IDLIN'
* Higher IDSAT/IDLIN ratio indicates better saturation (short-channel effects)

---

## 6. DIBL (Drain-Induced Barrier Lowering)

### 6.1 Definition
DIBL is the shift in threshold voltage due to increased drain voltage.
DIBL = (Vtlin - Vtsat) / (VD_SAT - VD_LIN)

### 6.2 HSPICE .MEASURE for DIBL
.MEASURE DC DIBL_CC PARAM='(VTLIN_CC - VTSAT_CC) / (VD_SAT - VD_LIN)'
.MEASURE DC DIBL_LE PARAM='(VTLIN_LE - VTSAT_LE) / (VD_SAT - VD_LIN)'

### 6.3 DIBL in mV/V
.MEASURE DC DIBL_MVV PARAM='DIBL_CC * 1000'
* Units: mV/V. Target: <100 mV/V for good short-channel devices

### 6.4 Alternative: Fixed Vg Method
.MEASURE DC ID_VDHI FIND I(VD_SRC) AT='VDD_NOM'
.MEASURE DC ID_VDLO FIND I(VD_SRC) AT='VD_LIN'
.MEASURE DC DIBL_ID PARAM='(ID_VDHI - ID_VDLO) / (VDD_NOM - 0.05)'

### 6.5 Advanced DIBL Extraction (Vth vs Vd sweep)
* Sweep both VG and VD for complete DIBL characterization
.DC VG_SRC 0 'VDD_NOM' 0.01 VD_SRC 0.05 'VDD_NOM' 0.2
.MEASURE DC VTH_VDLO FIND V(G) WHEN I(VD_SRC)=100N*W/L
.MEASURE DC VTH_VDHI FIND V(G) WHEN I(VD_SRC)=100N*W/L
.MEASURE DC DIBL_FULL PARAM='(VTH_VDLO - VTH_VDHI) / (VDD_NOM - 0.05)'

---

## 7. Subthreshold Swing (SSAT)

### 7.1 Definition
Subthreshold swing measures how sharply the device turns on/off.
SS = dVg / d(log10 Id) in the subthreshold region (weak inversion).

### 7.2 Ideal Swing
SS_ideal = ln(10) * kT/q = 60 mV/dec at 300K

### 7.3 HSPICE .MEASURE for Subthreshold Swing
* Measure in sub-Vth region: find slope of log(Id) vs Vg

* Step 1: Find Vg range in subthreshold (typically Vth - 0.3V to Vth - 0.1V)
.MEASURE DC VT_POINT FIND V(G) WHEN I(VD_SRC)=100N*W/L
.MEASURE DC VG_SUB1 PARAM='VT_POINT - 0.3'
.MEASURE DC VG_SUB2 PARAM='VT_POINT - 0.1'

* Step 2: Find Id at these Vg points
.MEASURE DC ID_SUB1 FIND I(VD_SRC) AT='VG_SUB1'
.MEASURE DC ID_SUB2 FIND I(VD_SRC) AT='VG_SUB2'

* Step 3: Compute SS = (VG2 - VG1) / (log10(ID2) - log10(ID1))
.MEASURE DC SSAT_RAW PARAM='(VG_SUB2 - VG_SUB1) / (LOG10(ID_SUB2) - LOG10(ID_SUB1))'

* Step 4: Unit conversion to mV/dec
.MEASURE DC SSAT_MV PARAM='SSAT_RAW * 1000'

### 7.4 Alternative: Direct derivation in HSPICE
.MEASURE DC LOGID DERIV OF LOG10(I(VD_SRC)) BY V(G)
.MEASURE DC SSAT_DIRECT PARAM='1/MAX(LOGID)'

### 7.5 Subthreshold Swing Temperature Dependence
.MEASURE DC SSAT_HT PARAM='(VG_SUB2 - VG_SUB1) / (LOG10(ID_SUB2) - LOG10(ID_SUB1))'

* SS increases with temperature (directly proportional to kT/q)

---

## 8. Isoff and Idoff (Off-State Leakage)

### 8.1 Isoff (Off-State Current)
Drain current when VG = 0, VD = VDD_NOM (device off).
.MEASURE DC ISOFF FIND I(VD_SRC) AT=0
.MEASURE DC ISOFF_W PARAM='ISOFF / W'  * Normalized to width
.MEASURE DC ISOFF_LG LOG10 ISOFF  * Log-scale for reporting

### 8.2 Idoff (Drain Off Leakage)
Same as Isoff for single device. In circuits, Idoff includes drain-to-well leakage.
.MEASURE DC IDOFF FIND I(VD_SRC) AT=0
.MEASURE DC IDOFF_GT I(VG_SRC) AT='VDD_NOM'  * Gate leakage component

### 8.3 Leakage Components
.MEASURE DC IG_OFF I(VG_SRC) AT=0  * Gate leakage in off state
.MEASURE DC IS_OFF I(VS_SRC) AT=0  * Source leakage in off state
.MEASURE DC IB_OFF I(VB_SRC) AT=0  * Bulk leakage in off state
.MEASURE DC ILEAK_TOTAL PARAM='IDOFF + IG_OFF + IS_OFF + IB_OFF'

### 8.4 Gate-Induced Drain Leakage (GIDL)
Measure at VG = 0, VD = VDD, or VG negative for GIDL peak.
.MEASURE DC IGIDL FIND I(VD_SRC) AT=0
.MEASURE DC IGIDL_PEAK MAX I(VD_SRC) FROM='-0.5*VDD' TO='0.2*VDD'

### 8.5 Temperature Effect on Leakage
.MEASURE DC ISOFF_125 FIND I(VD_SRC) AT=0  * Isoff at 125C
.MEASURE DC ISOFF_RATIO PARAM='ISOFF_125 / ISOFF'
* Leakage typically increases ~10x per 30-40C

---

## 9. Transconductance (Gm and Gmmax)

### 9.1 Definition
Transconductance Gm = dId / dVg at constant VD.
Peak Gm (Gmmax) is used for Vth extraction and analog performance metrics.

### 9.2 HSPICE .MEASURE for Gm
* Gm in saturation (VD = VDD)
.MEASURE DC GM_ID DERIV OF I(VD_SRC) BY V(G)
.MEASURE DC GM_MAX MAX GM_ID
.MEASURE DC VG_GMMAX FIND V(G) WHEN GM_ID=MAX

* Gm in linear (VD = 0.05V)
.MEASURE DC GM_LIN_ID DERIV OF I(VD_SRC) BY V(G)
.MEASURE DC GM_LIN_MAX MAX GM_LIN_ID

### 9.3 Normalized Gm Metrics
.MEASURE DC GM_PER_W PARAM='GM_MAX / W'  * Gm normalized to width
.MEASURE DC GM_PER_ID PARAM='GM_MAX / IDSAT'  * Gm/Id efficiency
.MEASURE DC GM_ID_PEAK MAX GM_ID  * Same as GM_MAX

### 9.4 Gm/Id Design Methodology
The Gm/Id ratio is a key analog design metric for inversion level:
- Gm/Id > 20: Weak inversion (subthreshold)
- Gm/Id 10-20: Moderate inversion
- Gm/Id < 10: Strong inversion

.MEASURE DC GMID_RATIO PARAM='GM_MAX / IDSAT'
.MEASURE DC GMID_MAX MAX PARAM='GM_ID / I(VD_SRC)'

### 9.5 Transconductance Derivatives and Linearity
.MEASURE DC GM3 DERIV OF GM_ID BY V(G)  * Third-order nonlinearity
.MEASURE DC VIP2 PARAM='2 * GM_MAX / GM3'  * Second-order intercept
.MEASURE DC GM_ID_1ST DERIV OF GM_ID BY V(G)  * Gm' for linearity

---

## 10. Output Resistance (Rodlin, Rch)

### 10.1 Rodlin (Linear Output Resistance)
Measured at VD = 0.05V, VG = VDD_NOM. Key parameter for transistor matching
and current mirror accuracy.

.MEASURE DC RODLIN_RAW FIND V(D) / I(VD_SRC) AT='VDD_NOM'
.MEASURE DC RODLIN_PARAM PARAM='RODLIN_RAW'  * Units: Ohms

* Alternative: small-signal output resistance
.MEASURE DC ROD_SS DERIV OF V(D) BY I(VD_SRC) AT='VDD_NOM'

### 10.2 Rch (Channel Resistance)
Channel resistance in linear region.
.MEASURE DC RCH PARAM='VD_LIN / IDLIN'
.MEASURE DC RON PARAM='RCH'  * ON resistance (same as Rch)

### 10.3 Rout (Output Resistance in Saturation)
Measured in saturation (VD = VDD, VG = VDD).
.MEASURE DC ROUT_SAT DERIV OF V(D) BY I(VD_SRC) AT='VDD_NOM'
.MEASURE DC RO_SAT PARAM='ROUT_SAT'
* High Rout indicates good saturation (low output conductance)

### 10.4 Output Conductance (Gds)
.MEASURE DC GDS DERIV OF I(VD_SRC) BY V(D) AT='VDD_NOM'
.MEASURE DC GDS_SAT MIN GDS  * Saturation output conductance
.MEASURE DC ROUT_PARAM PARAM='1/GDS_SAT'

### 10.5 Self-Heating Correction
* For high-power devices, correct for self-heating
.MEASURE DC RTH_THERMAL FIND V(D) / I(VD_SRC)
* Use .OPTIONS SELFHEAT=1 for thermal node simulation

---

## 11. Body Effect and Back-Bias Characterization

### 11.1 Body Effect (Gamma)
Threshold voltage shift due to body bias (VBS). Body effect coefficient gamma:
gamma = dVth / d(sqrt(2*phi_f + VSB))

### 11.2 Vth vs VBS Sweep
* Sweep body bias from forward to reverse
.DC VG_SRC 0 'VDD_NOM' 0.01 VB_SRC -0.3 'VDD_NOM' 0.15

.MEASURE DC VTH_VB0 FIND V(G) WHEN I(VD_SRC)=100N*W/L
+ VB_SRC=0
.MEASURE DC VTH_VB1 FIND V(G) WHEN I(VD_SRC)=100N*W/L
+ VB_SRC='VDD_NOM/2'
.MEASURE DC VTH_VB2 FIND V(G) WHEN I(VD_SRC)=100N*W/L
+ VB_SRC='VDD_NOM'

### 11.3 Body Effect Coefficient (Gamma)
.MEASURE DC GAMMA_PARAM
+ PARAM='(VTH_VB2 - VTH_VB0) / (SQRT(0.6+VDD_NOM) - SQRT(0.6))'
* 0.6V = 2*phi_f (surface potential)

### 11.4 Body Transconductance (Gmb)
.MEASURE DC GMB DERIV OF I(VD_SRC) BY V(B) AT='VDD_NOM'
.MEASURE DC GMB_PER_GM PARAM='GMB / GM_MAX'
* Ratio of body effect to gate transconductance

---

## 12. Capacitance-Voltage (CV) Characterization

### 12.1 Gate Capacitance (Cgg)
Total gate capacitance in inversion, depletion, and accumulation.

* AC analysis for CV
.AC DEC 10 1K 1G
VAC_SRC G 0 AC=1 SIN=0 0.05 1MEG
VD_SRC D 0 DC=VDDNOM

.MEASURE AC CGG_INTEG PARAM='IMAG(I(VG_SRC))/(6.283*FREQ)'
.MEASURE AC CGG_INV FIND CGG_INTEG WHEN V(G)='VDD_NOM'
.MEASURE AC CGG_DEP FIND CGG_INTEG WHEN V(G)='VDD_NOM/2'

### 12.2 Gate-to-Channel Capacitance Partitioning
.MEASURE AC CGD_INTEG PARAM='IMAG(I(VD_SRC))/(6.283*FREQ)'
.MEASURE AC CGS_INTEG PARAM='IMAG(I(VS_SRC))/(6.283*FREQ)'

### 12.3 Overlap Capacitance (Cov)
.MEASURE DC COV_PARAM PARAM='CGG_INV - COX*W*L'
* Extract overlap from Cgg vs L split measurements

---

## 13. Temperature Dependence

### 13.1 Multi-Temperature Workbench
.TEMP -40 25 85 125  * Four corners in one run

### 13.2 Temperature Coefficient Extraction
.MEASURE DC VTH_25C FIND V(G) WHEN I(VD_SRC)=100N*W/L
.MEASURE DC VTH_125C FIND V(G) WHEN I(VD_SRC)=100N*W/L
.MEASURE TC1_VTH PARAM='(VTH_125C - VTH_25C) / 100'
* Vth TC1 typically -0.8 to -1.2 mV/C

.MEASURE DC IDSAT_25C FIND I(VD_SRC) AT='VDD_NOM'
.MEASURE DC IDSAT_125C FIND I(VD_SRC) AT='VDD_NOM'
.MEASURE TC1_IDSAT PARAM='(IDSAT_125C - IDSAT_25C) / (IDSAT_25C * 100)'
* Idsat TC1 typically -0.1 to -0.3 %/C

---

## 14. Complete UT Workbench Template

### 14.1 NMOS Characterization Workbench
* File: ut_nch_char.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* Parameters
.PARAM VDD_NOM=0.8 VG_MAX=0.8 VD_SAT=0.8 VD_LIN=0.05
.PARAM W=1U L=30N

* Sources
VG_SRC G 0 DC=0
VD_SRC D 0 DC='VD_SAT'
VS_SRC S 0 DC=0
VB_SRC B 0 DC=0

* DUT
M_DUT D G S B NMOS_UT W={W} L={L}

* DC Sweep: Saturation Id-Vg
.DC VG_SRC 0 'VG_MAX' 0.005
.PRINT DC I(VD_SRC) V(G)

* === SATURATION MEASURES (VD=VD_SAT) ===
.MEASURE DC VTSAT FIND V(G) WHEN I(VD_SRC)=100N*{W/L}
.MEASURE DC IDSAT FIND I(VD_SRC) AT='VG_MAX'
.MEASURE DC IDSAT_W PARAM='IDSAT / W'
.MEASURE DC ISOFF FIND I(VD_SRC) AT=0
.MEASURE DC GM_SAT DERIV OF I(VD_SRC) BY V(G)
.MEASURE DC GMMAX_SAT MAX GM_SAT
.MEASURE DC VG_GMMAX FIND V(G) WHEN GM_SAT=MAX
.MEASURE DC ID_GMMAX FIND I(VD_SRC) AT='VG_GMMAX'

* === LINEAR MEASURES (VD=VD_LIN) ===
.ALTER case=linear
    VD_SRC D 0 DC='VD_LIN'
    .DC VG_SRC 0 'VG_MAX' 0.005

.MEASURE DC VTLIN FIND V(G) WHEN I(VD_SRC)=100N*{W/L}
.MEASURE DC IDLIN FIND I(VD_SRC) AT='VG_MAX'
.MEASURE DC GM_LIN DERIV OF I(VD_SRC) BY V(G)
.MEASURE DC GMMAX_LIN MAX GM_LIN

* === DIBL ===
.MEASURE DC DIBL PARAM='(VTLIN - VTSAT) / (VD_SAT - VD_LIN)'
.MEASURE DC DIBL_MVV PARAM='DIBL * 1000'

* === SUBTHRESHOLD SWING ===
.MEASURE DC VG_SW1 PARAM='VTSAT - 0.3'
.MEASURE DC VG_SW2 PARAM='VTSAT - 0.1'
.MEASURE DC ID_SW1 FIND I(VD_SRC) AT='VG_SW1'
.MEASURE DC ID_SW2 FIND I(VD_SRC) AT='VG_SW2'
.MEASURE DC SSAT PARAM='(VG_SW2 - VG_SW1) / (LOG10(ID_SW2) - LOG10(ID_SW1))'
.MEASURE DC SSAT_MV PARAM='SSAT * 1000'

* === OUTPUT RESISTANCE ===
.MEASURE DC VDS_PARAM FIND V(D) / I(VD_SRC) AT='VG_MAX'
.MEASURE DC RODLIN PARAM='VD_LIN / IDLIN'
.MEASURE DC ROUT_SAT DERIV OF V(D) BY I(VD_SRC) AT='VG_MAX'

* === BODY EFFECT ===
.ALTER case=body_effect
    VB_SRC B 0 DC='VDD_NOM'
    .DC VG_SRC 0 'VG_MAX' 0.005

.MEASURE DC VTSAT_VB FIND V(G) WHEN I(VD_SRC)=100N*{W/L}
.MEASURE DC GAMMA_INFER PARAM='(VTSAT_VB - VTSAT) / VDD_NOM'

.END

