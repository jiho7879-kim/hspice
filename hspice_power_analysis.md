---
title: 'HSPICE Power and Energy Analysis Guide'
subtitle: 'Dynamic Power, Leakage Power, Energy per Access, VDD Scaling, and Thermal Analysis'
version: '1.0'
date: '2026-06-30'
description: 'Comprehensive HSPICE power analysis guide for SRAM and transistor-level circuits. Covers dynamic power (switching), leakage (subthreshold, gate, GIDL), energy per access (read/write), average current method, VDD scaling effects, and thermal power analysis with complete .MEASURE syntax.'
tags: [HSPICE, power, energy, leakage, SRAM, dynamic power, thermal]
language: 'HSPICE'
keywords: [power analysis, energy per access, leakage current, dynamic power, Iddq, IVDD_AVG, .MEASURE POWER, VDD scaling, thermal analysis]
---

# HSPICE Power and Energy Analysis Guide

> **Purpose**: Complete HSPICE power/energy characterization for SRAM and transistor-level circuits.
> **Coverage**: Dynamic switching power, leakage power components, energy per access (read/write), VDD scaling, thermal analysis.
> **Target**: TR-level SRAM and logic power analysis.

---

## Table of Contents

1. [Power Components Overview](#1-power-components-overview)
2. [Dynamic Power Measurement](#2-dynamic-power-measurement)
3. [Leakage Power Measurement](#3-leakage-power-measurement)
4. [Energy per Access (Read/Write)](#4-energy-per-access-readwrite)
5. [Standby and Retention Power](#5-standby-and-retention-power)
6. [VDD Scaling and Power](#6-vdd-scaling-and-power)
7. [Short-Circuit Power](#7-short-circuit-power)
8. [Power Measurement with PVT Corners](#8-power-measurement-with-pvt-corners)
9. [Thermal Power and Temperature Effects](#9-thermal-power-and-temperature-effects)
10. [Complete Power Analysis Workbench](#10-complete-power-analysis-workbench)
11. [References](#11-references)

---

## 1. Power Components Overview

### 1.1 Total Power in CMOS SRAM
P_total = P_dynamic + P_leakage + P_short_circuit

#### P_dynamic (Switching)
P_dyn = alpha * C_load * VDD? * f
- alpha: activity factor (0 < alpha < 1)
- C_load: total switched capacitance
- f: operating frequency
- Dominant at high performance (>100MHz)

#### P_leakage (Static)
P_leak = Ileak * VDD
- Consists of: I_sub (subthreshold), I_gate (gate oxide), I_GIDL, I_junc (junction)
- Dominant at standby / low activity

#### P_short_circuit (Crowbar)
P_sc = I_sc * VDD * trise/tperiod
- Occurs during switching when both NMOS and PMOS conduct
- Typically 5-15% of P_dynamic in well-designed circuits

### 1.2 Power Contributions by Component (SRAM)
| Component | Dynamic | Leakage | Relative Share |
|-----------|---------|---------|----------------|
| Bitcell array | Low | High | Leakage dominant at idle |
| WL decoder | Medium | Low | WL switching per cycle |
| Sense amplifiers | Medium | Low | SA enable per read |
| Write drivers | High | Low | BL full-swing per write |
| Data out drivers | High | Low | Output pad switching |

---

## 2. Dynamic Power Measurement

### 2.1 Average Current Method (Recommended)
The most accurate method in HSPICE: measure average supply current, multiply by VDD.

.MEASURE TRAN IVDD_AVG AVG I(VDD_SRC) FROM=0 TO='PERIOD'
.MEASURE TRAN IVSS_AVG AVG I(VSS_SRC) FROM=0 TO='PERIOD'
.MEASURE TRAN PDYNAMIC PARAM='ABS(IVDD_AVG) * VDD'

### 2.2 Instantaneous Power Measurement
.MEASURE TRAN PVDD_INST AVG P(VDD_SRC) FROM=0 TO='PERIOD'
* P(device) returns instantaneous power in HSPICE (V * I)

### 2.3 Cell-Specific Dynamic Power
* Power contributed only by the bitcell (not peripheral)
.MEASURE TRAN PCELL_DYN AVG P(MPU1) + P(MPU2) + P(MPD1) + P(MPD2)
+ P(MPG1) + P(MPG2) FROM=10P TO='PERIOD'

### 2.4 Activity Factor Extraction
* For realistic power: measure over many cycles
* Use periodic input patterns

.MEASURE TRAN IVDD_10CYCLES AVG I(VDD_SRC) FROM=0 TO='10 * PERIOD'
.MEASURE TRAN P_10CYCLES PARAM='IVDD_10CYCLES * VDD'

* Energy per cycle = total energy / cycles
.MEASURE TRAN E_PER_CYCLE PARAM='P_10CYCLES * PERIOD'

### 2.5 Dynamic Power Example (WL Switching)
* File: sram_dynamic_power.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

.PARAM VDD=0.8
.PARAM FREQ=1E9 PERIOD='1/FREQ'

VDD_SRC VDD 0 DC='VDD'
VSS_SRC VSS 0 DC=0

* Active WL every cycle
WL_SRC WL 0 PULSE(0 VDD 0 10P 10P 'PERIOD/2' 'PERIOD')

* 6T SRAM cell (only one shown, array of 256 cells)
XCELL VVDD VVDD2 BL BLB WL VDD VSS SRAM6

* BL precharge between cycles
BL_SRC BL 0 DC=VDD PULSE(VDD 0 '0.8*PERIOD' 10P 10P '0.2*PERIOD' 'PERIOD')
BLB_SRC BLB 0 DC=VDD

.TRAN 0.5P '5 * PERIOD'

* Average power over steady-state cycles (skip first cycle)
.MEASURE TRAN IVDD_AVG AVG I(VDD_SRC) FROM='PERIOD' TO='5*PERIOD'
.MEASURE TRAN P_TOTAL PARAM='ABS(IVDD_AVG) * VDD'

---

## 3. Leakage Power Measurement

### 3.1 Leakage Components in HSPICE
| Component | Origin | .MEASURE | Key Parameter |
|-----------|--------|----------|---------------|
| Isub (subthreshold) | Vgs < Vth | I(M1) @ Vgs=0 | VTH0, SUBTHM |
| Igate (gate oxide) | Gate tunneling | Ig(M1) @ all biases | TOXE, IGT |
| I_GIDL | Gate-induced drain leakage | Igd(M1) @ Vgd=-VDD | GIDL, VTH0 |
| I_junc (junction) | Reverse bias p-n | Is(M1) @ Vdb=VDD | CJ, CJSW |

### 3.2 Total Leakage Current
* Measure total supply current when all inputs are static
VDD_SRC VDD 0 DC=0.8
* All nodes stable, no switching

.MEASURE DC ILEAK_TOTAL I(VDD_SRC)
* Includes all subthreshold + gate + GIDL + junction components

### 3.3 Subthreshold Leakage (Isub)
* Measure with Vgs = 0, Vds = VDD
VG G 0 DC=0
VD D 0 DC='VDD'
VS S 0 DC=0

.MEASURE DC ISOFF I(M1)
* ISOFF = W/L * I0 * (1 - exp(-Vds/Vt)) * exp(-Vth/(n*Vt))

### 3.4 Gate Leakage (Igate)
* Measure gate current with Vgs = VDD
VG G 0 DC='VDD'
VD D 0 DC='VDD'
VS S 0 DC=0

.MEASURE DC IGATE IG(M1)
* Measures Igate = Ig(M1) + Igd(M1) + Igs(M1)

### 3.5 GIDL (Gate-Induced Drain Leakage)
* Measure with Vgd = -VDD (gate grounded, drain at VDD)
VG G 0 DC=0
VD D 0 DC='VDD'
VS S 0 DC=0
VB B 0 DC=0

.MEASURE DC IGIDL I(VD)
* High GIDL = high drain-to-body leakage at Vgd = -VDD
* Dominant in high-VDD and thick-oxide devices

### 3.6 Bitcell Array Leakage (Iret)
* Total retention current for a 6T SRAM cell
* All wordlines = 0, bitlines = VDD

WL_SRC WL 0 DC=0
BL_SRC BL 0 DC='VDD'
BLB_SRC BLB 0 DC='VDD'

XCELL VVDD VVDD2 BL BLB WL VDD VSS SRAM6
* VVDD stores '1', VVDD2 stores '0'

.DC VDD VDD_NOM VDD_NOM 0.01
.MEASURE DC IRET I(VDD_SRC)
* Iret range: 1-100pA per cell (7nm FinFET at 0.75V)

### 3.7 Temperature Effect on Leakage
* Isub doubles every ~8-10?C (subthreshold slope)
* IGIDL increases, but less temperature-sensitive than Isub
* Junction leakage increases ~2x per 15-20?C

.ALTER case=leak_125C
    .TEMP 125
    .MEASURE DC ISOFF_125C I(M1)

.ALTER case=leak_m40C
    .TEMP -40
    .MEASURE DC ISOFF_m40C I(M1)

* Leakage ratio
.MEASURE PARAM LEAK_RATIO_125_25 PARAM='ISOFF_125C / ISOFF'

---

## 4. Energy per Access (Read/Write)

### 4.1 Energy per Read Access
* Energy = integral of instantaneous power over the read cycle
* Using .MEASURE TRAN with integration

* Read cycle: WL pulse + BL discharge + SA enable + precharge
WL_SRC WL 0 PULSE(0 VDD 0 10P 10P 'WL_PW' 'PERIOD')
SA_EN_SRC SA_EN 0 PULSE(0 VDD 'SA_DELAY' 5P 5P 'SA_PW' 'PERIOD')

* Total energy for one read cycle
.MEASURE TRAN E_READ INTEG P(VDD_SRC) FROM=0 TO='PERIOD'
.MEASURE TRAN E_READ_PJ PARAM='E_READ * 1E12'     * Convert to pJ

### 4.2 Energy per Write Access
* Write cycle: same pattern but higher energy due to BL full-swing

.ALTER case=write_access
    * Write drivers force BL=0 on one side
    BL_SRC BL 0 DC=VDD
    BLB_SRC BLB 0 DC=0

    .MEASURE TRAN E_WRITE INTEG P(VDD_SRC) FROM=0 TO='PERIOD'
    .MEASURE TRAN E_WRITE_PJ PARAM='E_WRITE * 1E12'

### 4.3 Energy Breakdown by Component
.MEASURE TRAN E_CELL_READ INTEG
+    + P(XCELL.MPU1) + P(XCELL.MPU2)
+    + P(XCELL.MPD1) + P(XCELL.MPD2)
+    + P(XCELL.MPG1) + P(XCELL.MPG2)
+    FROM=0 TO='PERIOD'

.MEASURE TRAN E_SA_READ INTEG P(XSA.VDD_SRC) FROM=0 TO='PERIOD'
.MEASURE TRAN E_WD_READ INTEG P(XWD.VDD_SRC) FROM=0 TO='PERIOD'

### 4.4 Energy vs Activity
* Idle energy (leakage only, no switching)
.MEASURE TRAN E_LEAK INTEG P(VDD_SRC) FROM='PERIOD' TO='PERIOD*10'

* Active energy per read (leakage subtracted)
.MEASURE TRAN E_DYN_READ PARAM='E_READ - E_LEAK / 9'

### 4.5 Average Power vs Energy per Operation
| Metric | Formula | HSPICE Method |
|--------|---------|---------------|
| Average power | P_avg = E_cycle / T_cycle | AVG P(VDD) over full period |
| Energy per read | E_read = integral P(VDD) over read | INTEG P(VDD) from 0 to T_read |
| Energy per write | E_write = integral P(VDD) over write | INTEG P(VDD) from 0 to T_write |
| Peak power | max P(VDD) over transient | MAX P(VDD) FROM=t1 TO=t2 |
| Leakage power | Ileak * VDD when idle | I(VDD) MEASURE at DC |

### 4.6 Read Energy Example (Compact)
.MEASURE TRAN E_OP INTEG P(VDD_SRC) FROM=0 TO='PERIOD'
.MEASURE TRAN P_AVG PARAM='E_OP / PERIOD'
.MEASURE TRAN P_PEAK MAX P(VDD_SRC) FROM=0 TO='PERIOD'
.MEASURE TRAN E_FJ PARAM='E_OP * 1E15'     * pJ or fJ

---

## 5. Standby and Retention Power

### 5.1 Standby Mode (Sleep/Power-Gate)
* In standby: WL = 0, all BL = VDD, no switching
* Only leakage remains from bitcell + peripheral

.DC VDD VDD_MIN VDD_MAX 0.01
.MEASURE DC ISTBY I(VDD_SRC)
.MEASURE DC PSTBY PARAM='ISTBY * VDD'

### 5.2 Retention Voltage (Vret_min)
* Minimum VDD to retain SRAM data (no read, just storage)
* Typically 50-70% of nominal VDD

.ALTER case=retention
    .PARAM VDD=0.5
    .DC VDD 0.3 0.8 0.01
    * Check if VVDD and VVDD2 maintain correct state
    .MEASURE DC V_RET_NODE V(VVDD)
    .MEASURE DC V_RET_NODE2 V(VVDD2)
    .MEASURE DC Vret_min MIN VDD WHEN V(VVDD)>0.8*VDD
    * If VVDD drops below 80% of VDD, data may be lost

### 5.3 Leakage by Bias Condition
| Condition | WL | BL/BLB | VDD | Leakage Range |
|-----------|----|--------|-----|---------------|
| Active standby | 0 | VDD | Nominal | 1-10nA/cell |
| Retention | 0 | VDD | Vret | 10-100pA/cell |
| Power-gated | 0 | 0 or VDD | 0 | 0 |
| Deep sleep | 0 | VDD | Vret/2 | <10pA/cell |

### 5.4 Array-Level Leakage Estimation
* Leakage_total = N_cells * I_cell_leak + I_peripheral
* For 1Mb array: N = 1,048,576
* I_cell_leak @ 25C ? 5pA ? I_array ? 5uA
* I_cell_leak @ 125C ? 50nA ? I_array ? 50mA (dominates)

---

## 6. VDD Scaling and Power

### 6.1 Power vs VDD Trade-off
* Dynamic power ? VDD? (quadratic reduction as VDD drops)
* Leakage power ? VDD * Ileak(VDD) (leakage also drops at lower VDD)
* Delay ? 1/(VDD - Vth)^alpha (slower at lower VDD)

### 6.2 VDD Sweep for Power Analysis
* File: vdd_scale_power.sp
.PARAM VDD=0.8
VDD_SRC VDD 0 DC='VDD'

* SRAM active with switching
WL_SRC WL 0 PULSE(0 VDD 0 10P 10P 'PERIOD/2' 'PERIOD')
BL_SRC BL 0 DC=VDD

* Measure power at multiple VDD points
.DC VDD 0.4 0.9 0.05

.MEASURE DC I_ACTIVE AVG I(VDD_SRC)
.MEASURE DC P_ACTIVE PARAM='I_ACTIVE * VDD'
.MEASURE DC I_LEAK FIND I(VDD_SRC) AT VGS=0  * At WL=0

### 6.3 Power Efficiency Metrics
* Energy per operation at each VDD
.MEASURE DC E_PER_OP PARAM='P_ACTIVE / FREQ'

* Energy-delay product (EDP)
* Measure delay at same VDD
.MEASURE DC TDELAY_PARAM ...
.MEASURE DC EDP PARAM='E_PER_OP * TDELAY'

* Energy-delay^2 (ED?P) ? optimal for low-power design
.MEASURE DC ED2P PARAM='E_PER_OP * TDELAY * TDELAY'

### 6.4 Optimal VDD (Energy-Optimal Point)
* At very low VDD: leakage energy dominates (slow, long active time)
* At high VDD: dynamic energy dominates
* Energy-optimal VDD typically near Vth + 100-200mV

* Energy breakdown sweep
.DC VDD Vth VDD_MAX 0.02
.MEASURE DC E_TOTAL INTEG P(VDD_SRC)
.MEASURE DC E_LEAK FIND I(VDD_SRC) AT...
.MEASURE DC E_DYN PARAM='E_TOTAL - E_LEAK'

### 6.5 VDD Corners for Power
| Corner | VDD | Purpose |
|--------|-----|---------|
| High VDD | +10% | Max dynamic power |
| Nominal | VDD_nom | Typical power |
| Low VDD | -10% | Low power (check functionality) |
| Retention | 0.5-0.7*VDD | Standby power |

---

## 7. Short-Circuit Power

### 7.1 Short-Circuit Current Mechanism
* Occurs during input transition when both transistors conduct
* Peak Isc proportional to input edge rate (faster edges = less Isc)
* Typically 5-15% of P_dynamic

.MEASURE TRAN ISC_PEAK MAX I(VDD_SRC) FROM='TIN_RISE-5P' TO='TIN_RISE+30P'

### 7.2 Short-Circuit Power Measurement
* Use a chain of inverters (measuring across multiple stages isolates I_sc from switching power)

.SUBCKT INV IN OUT VDD VSS
MP OUT IN VDD VDD PMOS W=200N L=30N
MN OUT IN VSS VSS NMOS W=100N L=30N
.ENDS INV

XINV1 IN MID VDD VSS INV
XINV2 MID OUT VDD VSS INV

VIN IN 0 PULSE(0 VDD 0 20P 20P 250P 500P)

.TRAN 0.5P 1N

* Measure VDD current through XINV1 during switching
.MEASURE TRAN ISC_XINV1 PEAK I(VDD_SRC) FROM=0 TO=500P

* Short-circuit power = Isc * VDD * trise / Tperiod
.MEASURE TRAN P_SC PARAM='ISC_PEAK * VDD * 20P / 500P'

### 7.3 Minimizing Short-Circuit Power
* Faster input edges ? less time both ON ? lower Isc
* Balanced PMOS/NMOS strength ? equal rise/fall ? lower Isc
* Lower VDD ? less Vgs overdrive ? lower Isc

---

## 8. Power Measurement with PVT Corners

### 8.1 Power-Specific Corners
| Corner | Temperature | VDD | Process | Power Mode |
|--------|-------------|-----|---------|------------|
| WCS (Worst-Case Slow) | 125C | -10% | SS | Worst leakage |
| TYP (Typical) | 25C | Nominal | TT | Nominal power |
| WCF (Worst-Case Fast) | 125C | +10% | FF | Worst dynamic |
| LT (Leakage Test) | 125C | Nominal | FF | Worst static |

### 8.2 Multi-Corner Power Workbench
* File: sram_power_corners.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.PARAM VDD_NOM=0.8

* Base deck
VDD_SRC VDD 0 DC='VDD_NOM'
WL_SRC WL 0 PULSE(0 'VDD_NOM' 0 10P 10P 200P 1N)
BL_SRC BL 0 DC='VDD_NOM'
BLB_SRC BLB 0 DC='VDD_NOM'

XCELL VVDD VVDD2 BL BLB WL VDD VSS SRAM6
CBL BL 0 50F

.TRAN 0.5P 2N

* Power measurements
.MEASURE TRAN I_AVG AVG I(VDD_SRC) FROM=0 TO=1N
.MEASURE TRAN P_AVG PARAM='ABS(I_AVG) * VDD_NOM'
.MEASURE TRAN E_1CYCLE INTEG P(VDD_SRC) FROM=0 TO=1N
.MEASURE TRAN I_LEAK FIND I(VDD_SRC) AT WL=0 AT=2N

* Corner 1: Worst leakage (SS, 125C, -10% VDD)
.ALTER case=WCS_leak
    .LIB models_ss.lib SS
    .TEMP 125
    .PARAM VDD_NOM=0.72
    .MEASURE TRAN I_LEAK_WCS FIND I(VDD_SRC) AT=2N

* Corner 2: Best dynamic (FF, -40C, +10% VDD)
.ALTER case=WCF_dyn
    .LIB models_ff.lib FF
    .TEMP -40
    .PARAM VDD_NOM=0.88
    .MEASURE TRAN P_DYN_WCF AVG P(VDD_SRC) FROM=0 TO=1N

* Corner 3: Nominal (TT, 25C)
.ALTER case=TYP
    .LIB models_tt.lib TT
    .TEMP 25
    .PARAM VDD_NOM=0.80

### 8.3 Reporting Power by Corner
* Output in .mt0 file:
.MEASURE TRAN P_TOTAL PARAM='ABS(I_AVG) * VDD_NOM'

* Post-processing guidance:
* P_dynamic scales with (VDD/VDD_nom)? * (f/f_nom)
* P_leakage scales with exp(-Vth/(n*Vt)) * VDD
* Temperature exponent: leak doubles every ~10?C

---

## 9. Thermal Power and Temperature Effects

### 9.1 Temperature vs Power in HSPICE
* HSPICE can model thermal feedback using:
  - .TEMP (global temperature)
  - Self-heating (SHMOD in FinFET)
  - Temperature sweep via .DC

### 9.2 Temperature-Dependent Leakage Model
* Subthreshold leakage temperature dependence:
* Ileak(T) = Ileak(T0) * 2^((T - T0)/Td)
* Td = temperature doubling constant (typically 8-12?C for subthreshold)

* HSPICE direct measurement:
.TEMP 25
.MEASURE DC ISOFF_25 I(M1)

.TEMP 125
.MEASURE DC ISOFF_125 I(M1)

.MEASURE PARAM LEAK_TD PARAM='(125-25)/LOG(ISOFF_125/ISOFF_25)/LOG(2)'

### 9.3 Self-Heating and Power
* Self-heating raises junction temperature:
* T_junction = T_ambient + Rth * P_device

* HSPICE self-heating measurement (FinFET):
VDS D 0 DC='VDD'
VGS G 0 DC='VDD'
M1 D G 0 0 NMOS_FIN L=20N NFIN=1

.MEASURE DC P_DEVICE PARAM='VDD * I(M1)'
.MEASURE DC T_JUNCTION TEMP M1
.MEASURE DC DELTA_T PARAM='T_JUNCTION - 25'

### 9.4 Thermal Runaway Check
* Positive feedback: higher T ? more leakage ? more power ? higher T
* Check if power stabilizes or diverges

* DC sweep with self-heating (keep Vgs, Vds fixed)
.DC TEMP -40 150 10
.MEASURE DC P_SELF_HEAT PARAM='VDD * I(M1)'
* If P increases super-linearly with T, thermal runaway risk

### 9.5 Temperature-VDD Cross Analysis
* File: temp_vdd_power.sp
* Sweep both temperature and VDD to find worst-case power

.DC VDD 0.6 0.9 0.05 SWEEP TEMP -40 125 10
.MEASURE DC I_VDD SWEEP I(VDD_SRC)
* Results show max power at highest VDD + highest temp

---

## 10. Complete Power Analysis Workbench

### 10.1 SRAM Power Characterization Workbench
* File: sram_power_workbench.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1

* === PARAMETERS ===
.PARAM VDD=0.8
.PARAM PERIOD=1N
.PARAM WL_PW=200P
.PARAM WPU=120N WPD=200N WPG=160N LCELL=30N

* === SUPPLIES ===
VDD_SRC VDD 0 DC='VDD'
VSS_SRC VSS 0 DC=0

* === WORDLINE ===
WL_SRC WL 0 PULSE(0 VDD 0 10P 10P 'WL_PW' 'PERIOD')

* === BITLINES ===
BL_SRC BL 0 DC=VDD PULSE(VDD 0 'PERIOD*0.8' 10P 10P 'PERIOD*0.2' 'PERIOD')
BLB_SRC BLB 0 DC=VDD

* === 6T SRAM ===
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W={WPU} L={LCELL}
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W={WPU} L={LCELL}
MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W={WPD} L={LCELL}
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W={WPD} L={LCELL}
MPG1 BL WL VVDD VSS NMOS_SRAM W={WPG} L={LCELL}
MPG2 BLB WL VVDD2 VSS NMOS_SRAM W={WPG} L={LCELL}

CBL BL VSS 50F
CBLB BLB VSS 50F

* === TRANSIENT ===
.TRAN 0.5P '3*PERIOD'

* === ACTIVE POWER MEASUREMENTS ===
.MEASURE TRAN I_AVG AVG I(VDD_SRC) FROM='PERIOD' TO='3*PERIOD'
.MEASURE TRAN P_TOTAL PARAM='ABS(I_AVG) * VDD'
.MEASURE TRAN E_CYCLE INTEG P(VDD_SRC) FROM='PERIOD' TO='2*PERIOD'
.MEASURE TRAN E_CYCLE_PJ PARAM='E_CYCLE * 1E12'
.MEASURE TRAN P_PEAK MAX P(VDD_SRC) FROM='PERIOD' TO='2*PERIOD'

* === LEAKAGE (idle period, WL=0) ===
.MEASURE TRAN I_LEAK_AVG AVG I(VDD_SRC) FROM='2.5*PERIOD' TO='3*PERIOD'
.MEASURE TRAN P_LEAK PARAM='ABS(I_LEAK_AVG) * VDD'

* === DYNAMIC POWER (total - leakage) ===
.MEASURE TRAN P_DYN PARAM='P_TOTAL - P_LEAK'

* === CELL COMPONENT POWER ===
.MEASURE TRAN P_CELL_AVG AVG
+ (P(MPU1)+P(MPU2)+P(MPD1)+P(MPD2)+P(MPG1)+P(MPG2))
+ FROM='PERIOD' TO='2*PERIOD'

* === READ POWER ===
.ALTER case=read_power
    .MEASURE TRAN P_READ AVG P(VDD_SRC) FROM='PERIOD' TO='PERIOD+500P'
    .MEASURE TRAN E_READ INTEG P(VDD_SRC) FROM='PERIOD' TO='PERIOD+500P'

* === WRITE POWER ===
.ALTER case=write_power
    BL_SRC BL 0 DC=VDD
    BLB_SRC BLB 0 DC=0
    .MEASURE TRAN P_WRITE AVG P(VDD_SRC) FROM='PERIOD' TO='PERIOD+500P'
    .MEASURE TRAN E_WRITE INTEG P(VDD_SRC) FROM='PERIOD' TO='PERIOD+500P'

* === VDD SWEEP ===
.ALTER case=vdd_sweep
    .DC VDD 0.5 0.9 0.05
    .MEASURE DC P_VDD_DC AVG P(VDD_SRC)

* === TEMPERATURE SWEEP ===
.ALTER case=temp_sweep
    .TEMP -40
    .MEASURE TRAN I_LEAK_COLD AVG I(VDD_SRC) FROM='2.5*PERIOD' TO='3*PERIOD'

.ALTER case=temp_hot
    .TEMP 125
    .MEASURE TRAN I_LEAK_HOT AVG I(VDD_SRC) FROM='2.5*PERIOD' TO='3*PERIOD'

.END

### 10.2 Power Analysis Quick Reference
| Measurement | Syntax | Unit | Description |
|-------------|--------|------|-------------|
| Average current | AVG I(VDD_SRC) | A | Mean supply current |
| Average power | AVG P(VDD_SRC) | W | Mean power dissipation |
| Energy per cycle | INTEG P(VDD_SRC) | J | Energy over 1 period |
| Peak power | MAX P(VDD_SRC) | W | Max instantaneous power |
| Leakage current | I(VDD_SRC) @ DC | A | Static supply current |
| Power-delay product | P_AVG * TDELAY | J | Energy per operation |
| Energy efficiency | E / operation | pJ | Common SRAM metric |

### 10.3 Typical Power Values (7nm FinFET SRAM)
| Metric | Value | Conditions |
|--------|-------|------------|
| Iread per bitcell | 5-10 uA | VDD=0.75V, NFIN_PG=1 |
| Energy per read | 0.5-2 fJ/bit | 7nm, VDD=0.75V |
| Energy per write | 1-4 fJ/bit | Full BL swing |
| Leakage per cell | 1-100 pA | 25C, VDD=0.75V |
| Leakage (125C) | 100x-1000x higher | High temp dominant |
| Bitline switching C | 20-50 fF/col | 256-cells per BL |
| Standby power | 1-100 nW/Mb | Retention mode |

> **Revision History**
> - 2026-06-30: Initial version. Covers dynamic/leakage power, energy per access, VDD scaling, thermal, short-circuit, corners.
