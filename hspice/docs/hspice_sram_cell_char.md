---
title: "HSPICE SRAM Cell Characterization Guide"
subtitle: "Complete Measurement Methodology for 6T SRAM Bitcell"
version: "1.0"
date: "2026-06-30"
description: "HSPICE measurement guide for SRAM bitcell characterization"
tags: [HSPICE, SRAM, bitcell, measurement, SNM, Vmin]
language: "HSPICE"
keywords: [SRAM, SNM, RSNM, Iread, Iwrite, Vtrip, N-curve, butterfly, write margin]
---

# HSPICE SRAM Cell Characterization Guide

> **Purpose**: Complete measurement methodology for 6T SRAM bitcell characterization.
> **Target**: TR-level simulation for SRAM bitcell workbench.

---

## 1. SRAM Bitcell Basics

### 1.1 6T SRAM Cell

6 transistors: 2 pull-up (PU, PMOS), 2 pull-down (PD, NMOS), 2 pass-gate (PG, NMOS).

**Nodes**: VVDD / VVDD2 (storage), BL / BLB (bitlines), WL (wordline)

**Critical ratios**:
- Beta ratio = W(PD) / W(PG) ? read stability (higher = more stable)
- Gamma ratio = W(PG) / W(PU) ? writeability (higher = easier write)

**Standard dimensions**: PU:PD:PG = 1:2:1.5

### 1.2 6T Standard Subcircuit Model
.SUBCKT SRAM6T BL BLB WL VDD VSS
+ PARAMS: WPU=120N WPD=200N WPG=160N L=30N
MPU1 VVDD WL VDD VDD PMOS_SRAM W={WPU} L={L}
MPU2 VVDD2 WL VDD VDD PMOS_SRAM W={WPU} L={L}
MPD1 VVDD WL VSS VSS NMOS_SRAM W={WPD} L={L}
MPD2 VVDD2 WL VSS VSS NMOS_SRAM W={WPD} L={L}
MPG1 BL WL VVDD VSS NMOS_SRAM W={WPG} L={L}
MPG2 BLB WL VVDD2 VSS NMOS_SRAM W={WPG} L={L}
.ENDS SRAM6T
---

## 2. Read Current (Iread / Icell)

Read current (also called **Icell** or **Iread**) is the current that flows through the access transistor and pull-down when the wordline is asserted and bitline is precharged to VDD.

### 2.1 Importance
- Determines bitline discharge rate ? read access time
- Directly affects sense-amplifier timing (Vbl_min = VDD - Icell * t / Cbl)
- Must be sufficiently high for fast read, but not so high that read stability degrades

### 2.2 HSPICE .MEASURE for Iread

**Netlist setup**: WL=VDD (read condition), BL=precharged to VDD, BLB=floating.
.SUBCKT READ_CELL_BIAS BL BLB WL VDD VSS VVDD VVDD2
+ PARAMS: VDD=0.8V
VVDD VVDD 0 VDDVSS VSS 0 VDD
WL_SRC WL 0 0 'VDD'
BL_SRC BL 0 DC VDD PULSE(VDD 0 0 10P)
BLB_SRC BLB 0 DC VDD
.ENDS

.MEASURE DC IREAD FIND I(MPG1) WHEN V(VVDD)=V(VSS) RISE=1
.MEASURE DC ICELL_PARAM AVG I(MPG1) FROM=0 TO={VDD}
.MEASURE DC IREAD_TRIG AVG I(MPG1) FROM='0.9*VDD' TO='0.1*VDD'
.MEASURE DC IREAD_NT I(MPG1) AT='0.8*VDD'

**Key nodes**: Iread measured as current through MPG1 at VVDD = VVSS (0V).

### 2.3 Icell vs Bitline Capacitance

Icell discharges the bitline capacitance. The bitline voltage drop for a given time t is:
- Delta_Vbl = Icell * t / Cbl

For sense-amplifier triggering:
- Vsense = Icell * t_sa / Cbl
- Typical Vsense target: 50-200 mV

### 2.4 Temperature and Voltage Dependence of Iread
- Increases with VDD (Icell ? (VDD - Vth)^alpha)
- Decreases with temperature (mobility degradation)
- PVT corners: FF gives highest Icell, SS gives lowest

### 2.5 Vread (Read Voltage)
.MEASURE DC VREAD_TRIP FIND V(BL) WHEN V(BLB)=V(0) CROSS=1
.IREAD_AUTOCROSS measure i(M1) when v(BL)=0.5*VDD
---

## 3. Butterfly Curve and Static Noise Margin (SNM)

### 3.1 What SNM Measures
The maximum DC noise voltage that can be tolerated before the stored data flips. Measured from the butterfly (VN) curve ? the voltage transfer characteristic (VTC) of the two cross-coupled inverters.

### 3.2 SNM Classification (Read vs Hold vs Write)
- **Hold SNM (HSNM)**: Wordline = 0V, bitlines at VDD. Most stable condition.
- **Read SNM (RSNM)**: Wordline = VDD, bitlines at VDD. The PD+PG voltage-divider lifts VVDD ? read disturb.
- **Write SNM**: During write operation.

### 3.3 Minimum SNM Criteria
- RSNM > 0.1 * VDD (engineering rule of thumb)
- RSNM > 30mV at VDD_min for 6-sigma yield
- Correlates directly to VMIN read

### 3.4 HSPICE Butterfly Sweep (.DC + .MEASURE)

**Step 1**: Sweep VVDD from 0 ? VDD, measure VVDD2 and the inverter VTC.

Method ? **two-step sweep**:
.DC VVDD_INIT 0 VDD 0.01

**Netlist for butterfly measurement**:
.OPTIONS POST=2
.TEMP 25

V_VDD VDD 0 DC='VDD'
V_VSS VSS 0 DC=0
V_WL WL 0 DC='VW'  * VW=0 for hold, VDD for read
V_BL BL 0 DC='VDD'
V_BLB BLB 0 DC='VDD'

* 6T cell instance
X1 BL BLB WL VDD VSS VVDD VVDD2 SRAM6T

* Sweep VVDD via source
VVDD_SRC VVDD 0 DC

* Measure the cross-inverter VTC
.DC VVDD_SRC 0 VDD 0.01
.PRINT DC V(VVDD) V(VVDD2) V(VVDD,VVDD2)

**Computing SNM**: The square-root method:
1. Get VTC1 = V(VVDD2) vs V(VVDD)
2. Get VTC2 = V(VVDD) vs V(VVDD2) [swap axes]
3. Find the maximum square that fits between the two curves
4. SNM = side length of the largest square

### 3.5 HSPICE .MEASURE for SNM (Direct Method)

* Find SNM as the maximum difference between VTC and mirrored VTC
.MEASURE SNM_DIFF MAX V(VVDD,VVDD2)
.MEASURE SNM_FLOOR MIN V(VVDD,VVDD2)

* SNM = side of maximum square embedded between VTC curves
.MEASURE SNM_CALC
+ PARAM='MIN(V(VVDD,VVDD2))/SQRT(2)'

**Analytic SNM formula**:
SNM ~= VDD - (3/4)*VDD*(1/beta_ratio) - Vth/2

### 3.6 .MEASURE for Read SNM (RSNM)
* Read condition: WL=VDD, BL=BLB=VDD
.MEASURE DC RSNM MIN V(VVDD,VVDD2)
.MEASURE DC RSNM_NORM PARAM='ABS(RSNM)/VDD'

### 3.7 .MEASURE for Hold SNM (HSNM)
* Hold condition: WL=0, BL=VDD, BLB=VDD
.MEASURE DC HSNM MIN V(VVDD,VVDD2)
.MEASURE DC HSNM_NORM PARAM='ABS(HSNM)/VDD'

### 3.8 .MEASURE for Write SNM (WSNM)
* Write condition: WL=VDD, BL=VDD, BLB=0 (writing opposite data)
.MEASURE DC WSNM MIN V(VVDD,VVDD2)

### 3.9 SNM Temperature Sensitivity
.MEASURE DC SNM_TEMP DERIV OF SNM BY V(VDD)
* SNM degrades at high temp due to threshold shift

---

## 4. Write Margin (WM / WNM)

### 4.1 Definition
Write Margin is the ability to correctly write new data into the cell. Two methodologies exist: **Write Noise Margin (WNM)** from butterfly VTC, and **Bitline Write Margin (BLWM)** from sweeping BL voltage.

### 4.2 Method 1: Dynamic Write Margin (Twin-Cell / Wordline Pulse)
.OPTIONS POST=2
.TEMP 25

* Write driver forces the new data
.MEASURE TRAN WRITE_END WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE TRAN WRITE_TIME PARAM='WRITE_END - WRITE_START'

* Wordline pulse width margin
.MEASURE TRAN TWRITE TRIG V(WL) VAL='VDD*0.5' RISE=1
+                         TARG V(WL) VAL='VDD*0.5' FALL=2

* Measure if write succeeded
.MEASURE TRAN WRITE_OK FIND V(VVDD) AT='WRITE_END + 100P'
.MEASURE TRAN WRITE_FAIL PARAM='WRITE_OK - VDD*0.5'  

### 4.3 Method 2: Static Write Margin (BL Sweep)
* Sweep BL from VDD downward while BLB=0
.MEASURE DC WNM_TRIG FIND V(BL) WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE DC WNM_PARAM PARAM='VDD - WNM_TRIG'

* Write margin as % of VDD
.MEASURE DC WNM_NORM PARAM='(VDD - WNM_TRIG) / VDD'

### 4.4 Method 3: Wordline Write Margin
* Sweep wordline voltage until cell fails to write
.MEASURE DC WRITE_FAIL_LVL FIND V(WL) WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE DC WLM PARAM='VDD - WRITE_FAIL_LVL'

### 4.5 Method 4: Write-Trip Voltage (WTV) by BL Current Method
.MEASURE DC WTV_TRIP FIND V(BL) WHEN I(MPG1)=0 CROSS=1
.MEASURE DC WTV_WINDOW PARAM='VDD - WTV_TRIP'

### 4.6 BL Write Margin and Write Assist
- Lower VDDcell (collapse) improves write margin at read stability cost
- Negative BL (NBL) boosts BL voltage below VSS for write assist
- Write margin degrades at high VDD due to stacked pass-gate resistance

---

## 5. N-Curve Methodology

### 5.1 What N-Curve Measures
The N-curve (current-based stability metric) characterizes cell stability through current injected at the storage node. It captures both read stability and writeability in a single measurement.

### 5.2 Key N-Curve Parameters
- **SVNM** ? Static Voltage Noise Margin (read stability voltage metric)
- **SINM** ? Static Current Noise Margin (read stability current metric)
- **WTV** ? Write-Trip Voltage (voltage at which write occurs)
- **WTI** ? Write-Trip Current (current at write trip)

### 5.3 N-Curve Simulation Setup
* Bias: WL=VDD (read), BL=BLB=VDD (precharged)
* Inject current at VVDD, sweep VVDD from 0 to VDD

.DC VVDD_SRC 0 VDD 0.005
.PRINT DC I(VVDD_SRC) V(VVDD) V(VVDD2)

.MEASURE DC N_SVNM FIND V(VVDD) WHEN I(VVDD_SRC)=0 CROSS=2
.MEASURE DC N_SINM FIND I(VVDD_SRC) WHEN I(VVDD_SRC)=MIN CROSS=1

.MEASURE DC N_WTV FIND V(VVDD) WHEN I(VVDD_SRC)=0 CROSS=3
.MEASURE DC N_WTI FIND I(VVDD_SRC) WHEN I(VVDD_SRC)=MAX CROSS=1

### 5.4 N-Curve Interpretation
- **SVNM** > 0.3V typically indicates robust read stability
- **SINM** > 20uA indicates good noise current immunity
- **WTV** > 0.2V indicates good writeability
- Larger N-curve peaks = more stable cell

### 5.5 Automatic Peak Detection
.MEASURE DC N_PEAK1 MAX I(VVDD_SRC) FROM=0 TO='VDD/2'
.MEASURE DC N_PEAK2 MIN I(VVDD_SRC) FROM='VDD/2' TO='VDD'
.MEASURE DC N_SVNM1 FIND V(VVDD) WHEN I(VVDD_SRC)=0 CROSS=1
.MEASURE DC N_SVNM2 FIND V(VVDD) WHEN I(VVDD_SRC)=0 CROSS=2

---

## 6. Trip Voltage (Vtrip / Vmeta)

### 6.1 Definition
The **trip voltage** (also called **meta-stable point** or **Vtrip**) is the voltage on VVDD = VVDD2 where the cross-coupled inverters are balanced. At this point, the cell is in meta-stable equilibrium.

### 6.2 Importance
- If VVDD > Vtrip, the cell resolves to '1' after WL goes low
- If VVDD < Vtrip, the cell resolves to '0'
- Used for SNM calculation and write margin characterization

### 6.3 HSPICE .MEASURE for Vtrip

* Method 1: Find where V(VVDD) = V(VVDD2)
.MEASURE DC VTRIP1 FIND V(VVDD) WHEN V(VVDD) = V(VVDD2) CROSS=1

* Method 2: DC sweep with matched initial conditions
.IC V(VVDD)=VDD/2 V(VVDD2)=VDD/2

.MEASURE DC VTRIP2 FIND V(VVDD) WHEN ABS(V(VVDD)-V(VVDD2))<1MV CROSS=1

* Method 3: Small-signal analysis at meta-stable point
.MEASURE DC VTRIP_AC FIND V(VVDD) WHEN I(VVDD_SRC)=0 CROSS=2

### 6.4 Temperature Dependent Vtrip
.MEASURE DC VTRIP_HT FIND V(VVDD) WHEN V(VVDD)=V(VVDD2) CROSS=1

### 6.5 Vtrip Mismatch Sensitivity
* Use .SENS to find sensitivity to device parameters
.SENS V(VVDD)
* Monitor dVtrip/dVth for each device

---

## 7. Hold Margin and Vretention

### 7.1 Hold Margin
The ability of the cell to retain data when WL=0.

### 7.2 Vretention (Vret)
The minimum VDD at which the cell retains data during standby (hold condition).

### 7.3 HSPICE .MEASURE for Vret
* Sweep VDD from nominal to 0, monitor cell state
.MEASURE DC VRET_POINT FIND V(VDD) WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE DC VRET_MARGIN PARAM='VDD_NOMINAL - VRET_POINT'

### 7.4 Hold Current (Iret) Measurement
.MEASURE DC IRET AVG I(VDD) FROM='VDD_NOMINAL*0.5' TO='VDD_NOMINAL'

* Compare to target leakage specification
.MEASURE DC IRET_CHECK PARAM='IRET / CORE_AREA'

### 7.5 Data Retention Voltage Sigma
.MEASURE DC VRET_SIGMA SIGMA VRET_POINT

### 7.6 Vret and Temperature
.MEASURE DC VRET_HOT FIND V(VDD) WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE DC VRET_COLD FIND V(VDD) WHEN V(VVDD)=V(VVDD2) CROSS=1

---

## 8. Leakage Currents (Istby, Iret)

### 8.1 Istby (Standby Current)
Total leakage from VDD when WL=0, BL=BLB=VDD.
.MEASURE DC ISTBY AVG I(VDD) FROM=0 TO='VDD'

### 8.2 Leakage Components
Each component can be individually measured:
.MEASURE DC ILEAK_PU1 I(MPU1)
.MEASURE DC ILEAK_PU2 I(MPU2)
.MEASURE DC ILEAK_PD1 I(MPD1)
.MEASURE DC ILEAK_PD2 I(MPD2)
.MEASURE DC ILEAK_PG1 I(MPG1)
.MEASURE DC ILEAK_PG2 I(MPG2)
.MEASURE DC ILEAK_TOTAL PARAM='ILEAK_PU1+ILEAK_PU2+ILEAK_PD1+ILEAK_PD2+ILEAK_PG1+ILEAK_PG2'

### 8.3 Gate vs Subthreshold Leakage
* Gate leakage (Ig) ? dominant at 45nm and below
.MEASURE DC ILEAK_G_PU1 I(MPU1) WHEN V(VVDD)=VDD

* Subthreshold leakage (Isub) ? dominant at 65nm and above
.MEASURE DC ILEAK_S_PU1 I(MPU1) WHEN V(VVDD2)=VDD

---

## 9. Standby Current Components

### 9.1 Iret (Retention Current)
.MEASURE DC IRET1 I(VDD_SUPPLY)
.MEASURE DC IRET2 I(MPU1,MPU2)
.MEASURE DC IRET_CELL PARAM='IRET1+IRET2'

### 9.2 Temperature Effects on Leakage
.MEASURE DC LEAK_25 C I(VDD) * At 25C
.MEASURE DC LEAK_85 C I(VDD) * At 85C
.MEASURE DC LEAK_125 C I(VDD) * At 125C (worst-case leakage)

---

## 10. Icritical ? Critical Read/Write Current

### 10.1 Definition
Minimum current required to reliably read or write the cell.

### 10.2 Critical Read Current
.MEASURE DC ICRIT_READ MIN I(MPG1)
.MEASURE DC ICRIT_READ_VAR SIGMA ICRIT_READ

### 10.3 Critical Write Current
.MEASURE TRAN ICRIT_WRITE AVG I(MPG1) FROM='TRIG_VAL' TO='END_VAL'
.MEASURE TRAN ICRIT_WRITE_MIN MIN I(MPG1)

---

## 11. Complete Cell Characterization Workbench

### 11.1 Single .DC Sweep for Multi-Parameter Extraction
.OPTIONS POST=2

VDD_SRC VDD 0 DC='VDD_NOM'
WL_SRC WL 0 DC='VREAD'  * VREAD=0 for hold, VDD for read
BL_SRC BL 0 DC='VDD'
BLB_SRC BLB 0 DC='VDD'
VSS_SRC VSS 0 DC=0

XCELL BL BLB WL VDD VSS VVDD VVDD2 SRAM6T

* Single sweep from 0 to VDD
.DC VVDD_SRC 0 'VDD' 0.001

* Extract all key metrics in one run
.MEASURE DC VTC1 MAX V(VVDD2,VVDD)   * Inverter VTC forward
.MEASURE DC VTC2 MAX V(VVDD,VVDD2)   * Inverter VTC reverse
.MEASURE DC SNM_SIDE MIN V(VVDD,VVDD2) * SNM diagonal
.MEASURE DC VTRIP FIND V(VVDD) WHEN V(VVDD)=V(VVDD2) CROSS=1

* Write margin via BL sweep
.MEASURE DC WNM_TRIP FIND V(BL) WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE DC WNM PARAM='VDD - WNM_TRIP'

### 11.2 N-Curve Extraction (single run)
.MEASURE DC SVNM FIND V(VVDD) WHEN I(VVDD_SRC)=0 CROSS=2
.MEASURE DC SINM FIND I(VVDD_SRC) WHEN I(VVDD_SRC)=MIN CROSS=1
.MEASURE DC WTV FIND V(VVDD) WHEN I(VVDD_SRC)=0 CROSS=3
.MEASURE DC WTI FIND I(VVDD_SRC) WHEN I(VVDD_SRC)=MAX CROSS=1

### 11.3 Full Workbench Netlist Template
* File: sram_char_workbench.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

.PARAM VDD_NOM=0.8 VREAD=0.8

* Cell instance with 6 transistors
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W=120N L=30N
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W=120N L=30N
MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W=200N L=30N
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W=200N L=30N
MPG1 BL WL VVDD VSS NMOS_SRAM W=160N L=30N
MPG2 BLB WL VVDD2 VSS NMOS_SRAM W=160N L=30N

* Supplies
VDD_SRC VDD 0 DC='VDD_NOM'
VSS_SRC VSS 0 DC=0
WL_SRC WL 0 DC='VREAD'
BL_SRC BL 0 DC='VDD_NOM'
BLB_SRC BLB 0 DC='VDD_NOM'

* Sweep source at VVDD
VVDD_INJ VVDD VSS DC 0

* DC analysis
.DC VVDD_INJ 0 'VDD_NOM' 0.001

* All measurements
.MEASURE DC VMAX MAX V(VVDD) 
.MEASURE DC VMIN MIN V(VVDD)
.MEASURE DC IDD MAX I(VDD_SRC)
.MEASURE DC ISUP AVG I(VDD_SRC)
.MEASURE DC SNM_DIAG ABS(V(VVDD)-V(VVDD2))
.MEASURE DC SNM_MIN MIN SNM_DIAG
.MEASURE DC IREAD_VAL FIND I(MPG1) WHEN V(VVDD)=0 CROSS=1
.MEASURE DC VTRIP_VAL FIND V(VVDD) WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE DC SVNM_VAL FIND V(VVDD) WHEN I(VVDD_INJ)=0 CROSS=2
.MEASURE DC SINM_VAL FIND I(VVDD_INJ) WHEN I(VVDD_INJ)=MIN CROSS=1
.MEASURE DC WTV_VAL FIND V(VVDD) WHEN I(VVDD_INJ)=0 CROSS=3
.MEASURE DC WTI_VAL FIND I(VVDD_INJ) WHEN I(VVDD_INJ)=MAX CROSS=1

.PROBE DC V(VVDD) V(VVDD2) I(VVDD_INJ)
.ALTER case=read
    WL_SRC WL 0 DC='VDD_NOM'
.ALTER case=write
    WL_SRC WL 0 DC='VDD_NOM'
    BLB_SRC BLB 0 DC=0
.ALTER case=hold
    WL_SRC WL 0 DC=0

.END

