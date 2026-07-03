---
title: 'HSPICE SRAM Mini-Array Peripheral Modeling Guide'
subtitle: 'Column/Row Peripheral Circuits, Assists (WLUD / NBL / VDD-Lowering), and Array Load Modeling for Realistic Mini-Array Simulation'
version: '1.0'
date: '2026-06-30'
description: 'Comprehensive HSPICE guide for constructing SRAM mini-array simulation environments with realistic peripheral circuits. Covers row decoder and WL driver modeling (with WL underdrive), column path (precharge, write driver, NBL assist, sense amplifier), VDD lowering assist, array parasitic load modeling via lumped R/C, and subarray architecture definition.'
tags: [HSPICE, SRAM, mini-array, peripheral, WLUD, NBL, sense amplifier, precharge, write driver, array modeling]
language: 'HSPICE'
keywords: [mini-array, peripheral circuit, row decoder, WL driver, WL underdrive, NBL, sense amplifier, precharge, write driver, VDD collapse, array load modeling]
---

# HSPICE SRAM Mini-Array Peripheral Modeling Guide

> **Purpose**: Construction of realistic SRAM mini-array simulation environments with full peripheral circuit modeling, without instantiating a complete memory array.
> **Coverage**: Row/column periphery definition, assist circuits (WLUD, NBL, VDD collapse), sense amplifier, precharge, write driver, array parasitic load modeling via lumped R/C, dummy cell insertion.
> **Target**: SRAM characterization engineers building realistic mini-array decks for timing/power/yield simulation.

---

## Getting Started (Read This First)

### Parameter Template File
All user-configurable values are collected in a single file:

| File | Purpose |
|------|---------|
| `array_params_template.inc` | Template with all parameters, marked `<<< USER:` |
| `array_params.inc` | **Your copy** — fill in values, then `.INCLUDE` in the main deck |

**Workflow:**
```
Step 1: Copy array_params_template.inc → array_params.inc
Step 2: Open array_params.inc and fill in ALL <<< USER: values
        (array size, metal R/C, device dimensions, assist levels, timing)
Step 3: .INCLUDE 'array_params.inc' in your netlist
Step 4: Run simulation — all lumped R/C and timing derived automatically
```

### What You Must Provide (from PDK or layout)
| Data | Where to Find | Example |
|------|---------------|---------|
| Array dimensions (N_ROWS, N_COLS) | Memory compiler spec | 256 rows × 64 cols |
| Cell height/width | PDK layout document | 0.5um × 0.25um |
| Metal sheet R, wire C | PDK BEOL document | M2: 10 ohm/sq |
| Device dimensions (W, L) | Your cell design | PG: W=160nm |
| Device parasitics (C_drain, C_GD) | .OP output or PDK model | 0.5fF |
| Peripheral transistor sizes | Your peripheral design | W_PCH=400nm |

### Parameter File Location Convention
Keep all support files with your deck:
```
project/
  sram_miniarray.sp      ← Main deck (includes params + circuits)
  array_params.inc        ← YOUR parameter values (edit this)
  array_load_model.inc    ← BL/WL Pi-model (reads params)
  precharge.inc           ← Precharge subcircuit
  write_driver_nbl.inc    ← Write driver + NBL
  sense_amp.inc           ← Sense amplifier
  wlud_gen.inc            ← WLUD generator
  vdd_collapse.inc        ← VDD collapse header
```

---

## Table of Contents

1. [Mini-Array Architecture Overview](#1-mini-array-architecture-overview)
2. [Array Load Modeling (Without Full Array)](#2-array-load-modeling-without-full-array)
3. [Row Peripheral: WL Decoder and Driver](#3-row-peripheral-wl-decoder-and-driver)
4. [WL Underdrive (WLUD) Assist](#4-wl-underdrive-wlud-assist)
5. [Column Peripheral: Precharge Circuit](#5-column-peripheral-precharge-circuit)
6. [Column Peripheral: Write Driver](#6-column-peripheral-write-driver)
7. [Negative Bitline (NBL) Assist](#7-negative-bitline-nbl-assist)
8. [Sense Amplifier (SA)](#8-sense-amplifier-sa)
9. [VDD Lowering (Cell Supply Collapse) Assist](#9-vdd-lowering-cell-supply-collapse-assist)
10. [Subarray Architecture Definition](#10-subarray-architecture-definition)
11. [Complete Mini-Array Workbench Template](#11-complete-mini-array-workbench-template)
12. [Post-Sim Like RC Modeling Guide](#12-post-sim-like-rc-modeling-guide)
13. [Column MUX and Shared SA Loading](#13-column-mux-and-shared-sa-loading)
14. [Replica Timing Path (Self-Timed SA_EN)](#14-replica-timing-path-self-timed-sa_en)
15. [BL Precharge RC and Cycle Time](#15-bl-precharge-rc-and-cycle-time)
16. [Read Disturb on Unselected Columns](#16-read-disturb-on-unselected-columns)
17. [Timing Path RC Separation (Read vs Write)](#17-timing-path-rc-separation-read-vs-write)
18. [Peripheral Signal Timing Quick Reference](#18-peripheral-signal-timing-quick-reference)

---


## 1. Mini-Array Architecture Overview

### 1.1 Why Mini-Array Instead of Full Array
| Full Array | Mini-Array Equivalent |
|-----------|----------------------|
| 256 rows ? 256 cols = 65,536 cells | 4-16 rows ? 1-4 cols + parasitic R/C |
| Simulation: hours to days | Simulation: minutes |
| Convergence: difficult (huge netlist) | Convergence: easy |
| Assists: hard to debug | Assists: each signal visible |

### 1.2 Mini-Array Block Diagram
`
                    ???????????????????????
    WL<255:0> ??????  Row Decoder + WL    ??? WL<0>
    (resistive     ?  Driver (WLUD)       ??? WL<1>
     model)        ?                      ??? ... (to mini-array)
                    ???????????????????????
                               ?
                    ???????????????????????
                    ?                     ?
  BL<0>??????????????  SRAM MINI-ARRAY    ??? BLB<0>
         ?          ?   (4-16 rows        ?
  Prechrg?          ?    1-4 cols +       ?
   circuit?          ?     dummy edge)     ?
         ?          ?                     ?
    ???????????     ???????????????????????
    ? Write   ?                ?
    ? Driver  ?     ???????????????????????
    ? + NBL   ???????  Sense Amplifier    ??? SA_OUT
    ???????????     ?  (with SA_EN)       ?
                    ???????????????????????
`

### 1.3 Peripheral Mapping Table
| Peripheral | Function | Mini-Array Model | Section |
|-----------|----------|-----------------|---------|
| Row decoder | WL address decode | Lumped R + pulse gen | ?3 |
| WL driver | WL rise time control | Inverter chain + WLUD | ?3-4 |
| Precharge | BL=VDD before access | PMOS + control signal | ?5 |
| Write driver | BL write data + NBL | NMOS/PMOS + cap boost | ?6-7 |
| Sense amp | BL differential ? output | Latch SA + SA_EN | ?8 |
| VDD collapse | Cell supply reduction | Variable supply VVDD | ?9 |
| Array load | BL/WL parasitic R/C | Lumped Pi-model | ?2 |
| Dummy cells | Edge effect mitigation | 2 rows top + bottom | ?2 |

---

## 2. Array Load Modeling (Without Full Array)

### 2.1 BL Parasitic Load Model
Full array BL has: 256 cells ? drain capacitance + metal wire R+C.
Replace with a Pi-model (lumped R + 2xC):

* File: array_load_model.inc
*
* NOTE: All parameters (N_ROWS, R_BL_PER_UM, C_BL_WIRE_PER_UM, C_DRAIN_PG, etc.)
*       are in array_params.inc — .INCLUDE that file BEFORE this one.
*       This file defines only the Pi-model topology and uses the derived
*       R_BL_METAL, C_BL_TOTAL, C_BL_BLB, R_WL_METAL, C_WL_TOTAL from it.

* --- BITLINE LOAD MODEL (Pi-model using derived params from array_params.inc) ---
* R_BL_METAL, C_BL_TOTAL come from array_params.inc derived section

* Pi-model: R_BL_METAL/2 ? C_BL_TOTAL/2 ? R_BL_METAL/2 ? C_BL_TOTAL/2
RBL1 BL BL_MID 'R_BL_METAL/2'
RBL2 BL_MID BL_INT 'R_BL_METAL/2'
CBL1 BL 0 'C_BL_TOTAL/2'
CBL2 BL_INT 0 'C_BL_TOTAL/2'

* Usage: connect mini-array to BL, connect BL_INT to column periphery

### 2.2 WL Parasitic Load Model
* Wordline: polysilicon + metal strap, RC distributed
* Uses derived R_WL_METAL, C_WL_TOTAL from array_params.inc (computed from N_COLS, CELL_WIDTH, metal R/C)

* Pi-model for WL
RWL1 WL_IN WL_MID 'R_WL_METAL/2'
RWL2 WL_MID WL_INT 'R_WL_METAL/2'
CWL1 WL_IN 0 'C_WL_TOTAL/2'
CWL2 WL_INT 0 'C_WL_TOTAL/2'

* Usage: WL driver ? WL_IN ? RWL ? WL_INT ? pass-gate of all cells

### 2.3 BL-to-BL Coupling Capacitance
* Adjacent BL coupling (important for differential sensing)
* C_BL_BLB derived from C_BLB_COUPLE_PER_UM × ARRAY_HEIGHT in array_params.inc
CBLBL BL BLB 'C_BL_BLB'

### 2.4 Dummy Cells (Top/Bottom Edge Replica)
* Insert 2 dummy rows (top + bottom) for edge effect matching
* Dummy WL: always OFF (tied to VSS)
* Dummy cell: identical to real cell but WL=0

* Dummy row at top
.SUBCKT DUMMY_CELL_TOP BL BLB VDD VSS
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W=120N L=30N
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W=120N L=30N
MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W=200N L=30N
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W=200N L=30N
MPG1 BL VSS VVDD VSS NMOS_SRAM W=160N L=30N   * WL=0 = OFF
MPG2 BLB VSS VVDD2 VSS NMOS_SRAM W=160N L=30N  * WL=0 = OFF
.ENDS DUMMY_CELL_TOP

* Instance 2 dummies at each end
XDUMMY_T1 BL BLB VDD VSS DUMMY_CELL_TOP
XDUMMY_T2 BL BLB VDD VSS DUMMY_CELL_TOP
XDUMMY_B1 BL BLB VDD VSS DUMMY_CELL_TOP
XDUMMY_B2 BL BLB VDD VSS DUMMY_CELL_TOP

### 2.5 Array Leakage Current Model
* All unselected cells contribute leakage on BL.
* I_LEAK_BL_TOTAL derived as N_ROWS × I_LEAK_PG in array_params.inc.
* Lumped current source replaces N_ROWS leaky cells:

* Instead of N_ROWS leaky cells, use one current source
ILEAK_BL BL 0 DC='I_LEAK_BL_TOTAL'
ILEAK_BLB BLB 0 DC='I_LEAK_BL_TOTAL'
* ? This captures BL leakage without instantiating 256 cells

### 2.6 Full Array Parasitic Summary Table (from array_params.inc)
| Parameter | Symbol | Formula | Scaling |
|-----------|--------|---------|---------|
| BL metal R | R_BL | N_ROWS × R_BL_PER_PITCH | O(N) |
| BL capacitance | C_BL_TOTAL | C_BL_WIRE + N_ROWS × C_DRAIN_PG | O(N) |
| WL metal R | R_WL | N_COLS × R_WL_PER_PITCH | O(N) |
| WL capacitance | C_WL_TOTAL | C_WL_WIRE + N_COLS × C_GD_PG | O(N) |
| BL-BLB coupling | C_BL_BLB | C_BLB_COUPLE_PER_UM × ARRAY_HEIGHT | O(N) |
| BL leakage | I_LEAK_BL | N_ROWS × I_LEAK_PG | O(N) |
| BL RC time const | τ_BL | R_BL × C_BL_TOTAL / 2 | O(N²) |

---

## 3. Row Peripheral: WL Decoder and Driver

### 3.1 Row Decoder (Lumped Model)
* For mini-array, full decoder not needed ? use lumped buffer chain.
* Captures: WL rise time, WL pulse width, WL resistance.

* File: row_peri.inc
* NOTE: Uses W_PG, L_CELL from array_params.inc for buffer sizing.
*       R_WL_DRIVER, WL_STAGGER, WL_PW, PERIOD also from array_params.inc.

* --- WL DECODER BUDDER CHAIN ---
* Model WL path delay through 3-stage buffer
.SUBCKT WL_BUF IN OUT VDD VSS
* Stage 1: pre-decoder (small)
MP1 N1 IN VDD VDD PMOS W=200N L=30N
MN1 N1 IN VSS VSS NMOS W=100N L=30N
* Stage 2: level-shifter/driver (medium)
MP2 N2 N1 VDD VDD PMOS W=400N L=30N
MN2 N2 N1 VSS VSS NMOS W=200N L=30N
* Stage 3: final WL driver (large)
MP3 OUT N2 VDD_VWL VDD \ PMOS_WL W=1.6U L=30N
MN3 OUT N2 VSS VSS NMOS_WL W=0.8U L=30N
.ENDS WL_BUF
* ? VDD_VWL: WL voltage (may be VDD or WLUD level)

### 3.2 WL Driver with Resistance
* Wordline driver output resistance = total WL load
* R_WL_DRIVER from array_params.inc; R_WL_METAL, R_WL_TOTAL derived in template derived section

* Simplified: driver + Pi-model directly
VWL_DRV WL_DRV 0 PULSE(0 VDD_VWL 0 10P 10P 'WL_PW' 'PERIOD')
RWL_DRV WL_DRV WL 'R_WL_DRIVER'     * Driver output resistance
* WL ? Pi-model (from ?2.2) ? WL_INT ? cell

### 3.3 Multiple-row Timing (Ripple)
* For mini-array with 8 rows: sequential WL pulse with stagger
* WL_STAGGER from array_params.inc (default 10ps)

* Row 0: fastest WL (closest to driver)
WL0_SRC WL0 0 PULSE(0 VDD_VWL 0 10P 10P 'WL_PW' 'PERIOD')

* Row 1: staggered by WL_STAGGER
WL1_SRC WL1 0 PULSE(0 VDD_VWL 'WL_STAGGER' 10P 10P 'WL_PW' 'PERIOD')

* Row 2: +2*WL_STAGGER
WL2_SRC WL2 0 PULSE(0 VDD_VWL '2*WL_STAGGER' 10P 10P 'WL_PW' 'PERIOD')
...

### 3.4 WL Timing Measurement
.MEASURE TRAN TWL_RISE TRIG V(WL_DRV) VAL='VDD*0.5' RISE=1
+                       TARG V(WL_INT) VAL='VDD*0.5' RISE=1
* ? WL propagation delay from driver to far-end cell

.MEASURE TRAN TWL_SLEW TRIG V(WL) VAL='VDD*0.1' RISE=1
+                      TARG V(WL) VAL='VDD*0.9' RISE=1
* ? WL rise time (affected by RWL total + CWL)

---

## 4. WL Underdrive (WLUD) Assist

### 4.1 WLUD Concept
* WL voltage = VDD - delta (e.g., 0.65V instead of 0.8V)
* Effect: reduces pass-gate strength ? improves read stability
* Trade-off: reduces Iread ? slower read

### 4.2 WLUD Voltage Generation
* File: wlud_gen.inc
* NOTE: WLUD_DELTA, WLUD_EN, VDD_NOM from array_params.inc.
*       V_WLUD = VDD_NOM - WLUD_DELTA is derived in array_params.inc derived section.

* Option A: Resistive divider from VDD
* WLUD_DELTA, V_WLUD from array_params.inc (V_WLUD = VDD_NOM - WLUD_DELTA)

* Option B: Dedicated regulator (diode-connected PMOS)
MPWLUD V_WLUD BIAS VDD VDD PMOS_WL W=10U L=100N
IBIAS BIAS 0 DC=10U

* V_WLUD = VDD - Vgs_MPWLUD ? VDD - 150mV

* Option C: Simple voltage source (for mini-array)
VWL_SUP V_WLUD 0 DC='V_WLUD'

### 4.3 WL Driver with WLUD
* WL driver supply = V_WLUD instead of VDD
.SUBCKT WL_BUF_WLUD IN OUT VDD V_WLUD VSS
MP1 N1 IN VDD VDD PMOS W=200N L=30N
MN1 N1 IN VSS VSS NMOS W=100N L=30N
MP2 N2 N1 VDD VDD PMOS W=400N L=30N
MN2 N2 N1 VSS VSS NMOS W=200N L=30N
MP3 OUT N2 V_WLUD V_WLUD PMOS_WL W=1.6U L=30N   * Supply = V_WLUD
MN3 OUT N2 VSS VSS NMOS_WL W=0.8U L=30N
.ENDS WL_BUF_WLUD

* Instance:
XWL WL_IN WL_INT VDD V_WLUD VSS WL_BUF_WLUD

### 4.4 WLUD: Read vs Write
* Read: WL underdrive ON (stability enhancement)
* Write: WL underdrive OFF (= full VDD, write margin enhancement)
* Switch between modes:

.PARAM WLUD_MODE=0               * 0=normal read, 1=write boost
* In write: V_WLUD = VDD (full voltage)
VWL_SUP V_WLUD 0 DC='VDD - WLUD_DELTA * (1-WLUD_MODE)'

### 4.5 WLUD Timing Measurement
.MEASURE TRAN V_WLUD_MEAS AVG V(WL) FROM='50P' TO='100P'
* ? ?? WL ?? (WLUD ??)

.MEASURE TRAN IREAD_WLUD AVG I(MPG1) FROM='50P' TO='100P'
* ? WLUD ???? Iread

.MEASURE TRAN TACC_WLUD TRIG V(WL) VAL='VDD*0.5' RISE=1
+                        TARG V(BL) VAL='VDD*0.9' FALL=1
* ? WLUD? read access time penalty

---

## 5. Column Peripheral: Precharge Circuit

### 5.1 Precharge Operation
* Before read: BL = BLB = VDD
* Precharge signal (PCH) active low
* Precharge turned off before WL asserted, then BL begins discharging

### 5.2 Precharge Circuit Netlist
* File: precharge.inc
* NOTE: W_PCH, L_PCH, TPCH_OFF, TPCH_ON, WL_PW, PERIOD from array_params.inc.

.SUBCKT PRECHARGE BL BLB PCH VDD
* PMOS precharge transistors (W_PCH, L_PCH from array_params.inc)
MP1 BL PCH VDD VDD PMOS_PCH W='W_PCH' L='L_PCH'
MP2 BLB PCH VDD VDD PMOS_PCH W='W_PCH' L='L_PCH'
* Equalization transistor (shorts BL-BLB)
MP3 BL BLB VDD VDD PMOS_PCH W='W_PCH/2' L='L_PCH'
.ENDS PRECHARGE

* Control: PCH = 0 ? precharge ON, PCH = VDD ? precharge OFF
VPCH PCH 0 PULSE(0 VDD 'TPCH_OFF' 5P 5P 'TPCH_ON' 'PERIOD')
* TPCH_OFF = WL rise - margin (precharge turns off just before WL)

* Instance for each bit-cell column
XPRECH BL BLB PCH VDD PRECHARGE

### 5.3 Precharge Timing
* TPCH_OFF, TPCH_ON, WL_PW, PERIOD from array_params.inc.
* Default: TPCH_OFF = -10ps (before WL), TPCH_ON = WL_PW + 20ps (after WL falls).

VPCH PCH 0 PULSE(0 VDD 'TPCH_OFF' 5P 5P 'TPCH_ON' 'PERIOD')

### 5.4 Precharge Measurement
.MEASURE TRAN VBL_PRECHK AVG V(BL) FROM=0 TO='TPCH_OFF'
* ? BL precharge level (should be VDD)

.MEASURE TRAN I_PRECHARGE AVG I(VDD_SRC) FROM='TPCH_OFF' TO='TPCH_ON'
* ? Precharge dynamic current

### 5.5 Precharge with Array Load
* Precharge must account for BL RC delay
* Connect BL to array Pi-model then to precharge:

* Precharge ? BL_PAR ? Pi-model ? BL_INT ? cell + periphery
XPRECH BL_PAR BLB_PAR PCH VDD PRECHARGE    * Precharge at column edge
* Array Pi-model (from ?2.1)
RBL1 BL_PAR BL_MID 'R_BL_METAL/2'
RBL2 BL_MID BL_INT 'R_BL_METAL/2'
CBL1 BL_PAR 0 'C_BL_TOTAL/2'
CBL2 BL_INT 0 'C_BL_TOTAL/2'
* Cell & periphery at BL_INT

---

## 6. Column Peripheral: Write Driver

### 6.1 Write Driver Circuit
* Forces BL to VDD and BLB to 0 (write '0')
* Drives large BL capacitance ? wide transistors

* File: write_driver.inc
* NOTE: W_WD_N, L_WD_N from array_params.inc.
*       TWR_EN_START, TWR_EN_WIDTH also from array_params.inc.

.SUBCKT WRITE_DRIVER BL BLB WR_DATA WR_EN VDD VSS
* Data input buffer
MN1 WR_DATA_INV WR_DATA VSS VSS NMOS_WD W='W_WD_N/4' L='L_WD_N'
MP1 WR_DATA_INV WR_DATA VDD VDD PMOS_WD W='W_WD_N/2' L='L_WD_N'

* BL driver (NMOS pull-down for BL=0, PMOS pull-up for BL=VDD)
* For write '0': BL = 0, BLB = VDD
* WR_DATA = 1 => MN_BL on => BL=0
* WR_DATA = 0 => MP_BLB on => BLB=VDD

* BL pull-down (to write '0')
MN_BL BL WR_EN VSS VSS NMOS_WD W='W_WD_N' L='L_WD_N'
* BLB pull-up (to write '1' on BLB)
MP_BLB BLB WR_EN VDD VDD PMOS_WD W='W_WD_N*2' L='L_WD_N'

* Enable path
MN2 WR_EN_IN WR_EN VSS VSS NMOS_WD W='W_WD_N/4' L='L_WD_N'
.ENDS WRITE_DRIVER

* Instance:
XWD BL_INT BLB_INT WR_DATA WR_EN VDD VSS WRITE_DRIVER

### 6.2 Write Driver Timing
.MEASURE TRAN TWR_DATA_SET TRIG V(WR_EN) VAL='VDD*0.5' RISE=1
+                         TARG V(BL_INT) VAL='VDD*0.1' FALL=1
* ? Enable to BL driven low

.MEASURE TRAN TWR_DRIVE TRIG V(WR_EN) VAL='VDD*0.5' RISE=1
+                       TARG V(BLB_INT) VAL='VDD*0.9' RISE=1
* ? Enable to BLB driven high

### 6.3 Write Driver Sizing vs BL Load
* Write driver must overcome BL capacitance within WL pulse width
* Required current: I_WD = C_BL_total ? VDD / T_WRITE
* For C_BL=180fF, VDD=0.8V, T_WRITE=100ps ? I_WD ? 1.44mA
* ? NMOS_WD width ? 800nm (Ion~1.8mA/um for 7nm)

---

## 7. Negative Bitline (NBL) Assist

### 7.1 NBL Circuit Architecture
* NBL: coupling capacitor + boost signal ? BL voltage below VSS
* Write driver + NBL integrated together

* File: nbl_assist.inc
* NOTE: VBOOST_MAG, C_NBL_VAL, TD_NBL, NBL_PW from array_params.inc.
*       Write driver uses W_WD_N, L_WD_N from array_params.inc.

.SUBCKT WRITE_DRIVER_NBL BL BLB WR_DATA WR_EN NBL_BOOST VDD VSS
* --- Write driver core (from Section 6) ---
MN_BL BL WR_EN NBL_SOURCE VSS NMOS_WD W='W_WD_N' L='L_WD_N'
MP_BLB BLB WR_EN VDD VDD PMOS_WD W='W_WD_N*2' L='L_WD_N'

* --- NBL coupling capacitor ---
* Coupling cap between BL and NBL_BOOST signal
CNBL BL NBL_BOOST 'C_NBL_VAL'

* --- NBL boost signal generation ---
* NBL_BOOST: 0V ? -VBOOST (negative pulse aligned with write)
* This is generated externally (see below)

* --- NBL clamp diode (optional: prevents BL < -VMAX) ---
* DCLAMP BL VSS DNODE AREA=1
* OR: parasitic model

.ENDS WRITE_DRIVER_NBL

### 7.2 NBL Boost Signal Generator
* External boost generation (VBOOST_MAG, TD_NBL, NBL_PW from array_params.inc):
* VBOOST_MAG: boost magnitude (default 0.3V)
* TD_NBL: boost start after WL rise
* NBL_PW: boost pulse width

* Boost signal: 0V ? -VBOOST_MAG
VNBL_BOOST NBL_BOOST 0 PULSE(0 '-VBOOST_MAG' 'TD_NBL' 5P 5P 'NBL_PW' 'PERIOD')

* Coupling cap from NBL_BOOST to BL (via write driver subcircuit)
* BL voltage drop: ?VBL = VBOOST_MAG ? C_NBL / (C_NBL + C_BL_total)

### 7.3 NBL Timing Diagram
* Signal    | 0          | 20ps       | 200ps      | 1ns
* ----------|------------|------------|------------|-----
* PCH       | 0 (ON)     | VDD (OFF)  | VDD (OFF)  | 0
* WL        | 0          | VDD        | 0          | 0
* WR_EN     | 0          | VDD        | VDD        | 0
* NBL_BOOST | 0          | -VBOOST    | -VBOOST    | 0
* BL        | VDD        | VDD-?V_NBL | discharged | VDD
* BLB       | VDD        | VDD (held) | 0 (write)  | VDD

### 7.4 NBL Measurement
.MEASURE TRAN VBL_NBL_MIN MIN V(BL) FROM='TD_NBL' TO='TD_NBL+100P'
* ? NBL boost ? BL ?? ?? (negative? ? ??)

.MEASURE TRAN TWRITE_NBL TRIG V(WL) VAL='VDD*0.5' RISE=1
+                        TARG V(VVDD) VAL='VDD*0.5' RISE=1
* ? NBL ?? ? write completion time

.MEASURE TRAN VBL_BOOST_EFF PARAM='VDD - VBL_NBL_MIN'
* ? Effective NBL boost voltage

### 7.5 NBL Boost Level Sweep
.DC VBOOST_MAG 0 0.4 0.02
.MEASURE DC TWRITE_VBOOST FIND TWRITE_NBL
* ? NBL boost level vs write time (saturation ??)

---

## 8. Sense Amplifier (SA)

### 8.1 SA Architecture for Mini-Array
* Latch-type SA: BL differential → full-rail output
* Enable by SA_EN after sufficient BL ΔV

* File: sense_amp.inc
* NOTE: SA transistor sizes (W_SA_*, L_CELL) from array_params.inc.
*       BL_DELTA_TARGET, TSAE_MARGIN also from array_params.inc.

.SUBCKT SA_LATCH BL BLB SA_OUT SA_OUTB SA_EN VDD VSS
* Precharge (W_SA_LOAD from array_params.inc)
MP1 SA_OUT SA_EN VDD VDD PMOS_SA W='W_SA_LOAD' L='L_CELL'
MP2 SA_OUTB SA_EN VDD VDD PMOS_SA W='W_SA_LOAD' L='L_CELL'

* Input pair (BL/BLB → SA nodes) (W_SA_IN from array_params.inc)
MN1 SA_OUT BL SAS VSS NMOS_SA W='W_SA_IN' L='L_CELL'
MN2 SA_OUTB BLB SAS VSS NMOS_SA W='W_SA_IN' L='L_CELL'

* Regenerative latch (W_SA_CROSS from array_params.inc)
MP3 SA_OUT SA_OUTB VDD VDD PMOS_SA W='W_SA_CROSS' L='L_CELL'
MP4 SA_OUTB SA_OUT VDD VDD PMOS_SA W='W_SA_CROSS' L='L_CELL'
MN3 SA_OUT SA_OUTB SAS SAS NMOS_SA W='W_SA_CROSS' L='L_CELL'
MN4 SA_OUTB SA_OUT SAS SAS NMOS_SA W='W_SA_CROSS' L='L_CELL'

* SA enable tail (2× W_SA_IN for sufficient current)
MN5 SAS SA_EN VSS VSS NMOS_SA W='W_SA_IN*2' L='L_CELL'
.ENDS SA_LATCH

### 8.2 SA Enable Timing
* SA_EN rising edge: must wait for BL ΔV > SA offset
* BL_DELTA_TARGET from array_params.inc (default 50mV)
.PARAM TREAD_DV50M = 'R_BL * C_BL_TOTAL * 0.7 * LOG(VDD_NOM / (VDD_NOM - BL_DELTA_TARGET))'
.PARAM TSAE_DELAY='TREAD_DV50M + TSAE_MARGIN'

* Read ?V timing:
.MEASURE TRAN TBL_DV50 TRIG V(WL) VAL='VDD*0.5' RISE=1
+                      TARG PARAM='VDD - V(BL)' VAL=0.05 RISE=1

VSA_EN SA_EN 0 PULSE(0 VDD 'TSAE_DELAY' 5P 5P '100P' 'PERIOD')

### 8.3 SA Timing Measurement
.MEASURE TRAN TSA_TRIG2OUT TRIG V(SA_EN) VAL='VDD*0.5' RISE=1
+                          TARG V(SA_OUT) VAL='VDD*0.5' RISE=1
* ? SA propagation delay

.MEASURE TRAN TREAD_TOTAL TRIG V(WL) VAL='VDD*0.5' RISE=1
+                         TARG V(SA_OUT) VAL='VDD*0.5' RISE=1
* ? Full read path: WL ? SA_OUT

### 8.4 SA Input-Output Connection
* SA connects to BL_INT (after array Pi-model)
* SA_OUT goes to data-out latch

XSA BL_INT BLB_INT SA_OUT SA_OUTB SA_EN VDD VSS SA_LATCH

---

## 9. VDD Lowering (Cell Supply Collapse) Assist

### 9.1 VDD Collapse Concept
* Read assist: lower cell supply (VVDD < VDD) to improve read stability.
* WL driver still at full VDD ? pass-gate relatively stronger? No ? WLUD is separate.
* VDD collapse reduces cell feedback strength ? improves RSNM.

### 9.2 VDD Collapse Circuit
* File: vdd_collapse.inc
* NOTE: VCOL_DELTA, VCOL_EN, VDD_NOM from array_params.inc.

* Option A: Series PMOS header (simplest for mini-array)
* VVDD_COL derived as VDD_NOM - VCOL_DELTA × VCOL_EN in array_params.inc

MPHEAD VVDD_INT VCOL_EN VDD VDD PMOS_HEAD W=10U L=100N
* VCOL_EN = 0 ? VVDD_INT ? VDD (normal)
* VCOL_EN = VDD ? VVDD_INT ? VDD - |Vgs| ? VDD - VCOL_DELTA (collapsed)

* Option B: Simple voltage source (for mini-array, use this)
VVDD_SUP VVDD_INT 0 DC='VVDD_COL'

* Connect to bitcell supply:
* Cell VDD = VVDD_INT (collapsed) instead of global VDD
MPU1 VVDD VVDD2 VVDD_INT VVDD_INT PMOS_SRAM W=120N L=30N
MPU2 VVDD2 VVDD VVDD_INT VVDD_INT PMOS_SRAM W=120N L=30N

### 9.3 VDD Collapse + WLUD Combinatio
* Read assist often combines both:
*   WLUD: reduces pass-gate current (stability ?, read current ?)
*   VDD collapse: weakens cell feedback (stability ?, read current ?)
*   Together: strong stability boost, but significant Iread penalty

.PARAM VWLUD_TARGET='VDD - 0.15'
.PARAM VVDD_COL_TARGET='VDD - 0.1'

* Check Iread at combined assist:
.MEASURE TRAN IREAD_ASSIST AVG I(MPG1) FROM='50P' TO='100P'
* Compare with no-assist Iread

### 9.4 Assist Measurement Summary
.MEASURE TRAN IREAD_NO_ASSIST ...
.MEASURE TRAN IREAD_WLUD ...
.MEASURE TRAN IREAD_COLAPSE ...
.MEASURE TRAN IREAD_BOTH ...

* Assist effectiveness = Iread penalty vs stability gain
* Sweep assist levels for optimal point

---

## 10. Subarray Architecture Definition

### 10.1 Subarray Floorplan
* A realistic SRAM subarray has defined dimensions.
* **All parameters are in `array_params.inc`** — see the template file for descriptions.
* Key parameters that define the subarray floorplan:

| Parameter | Description | Default |
|-----------|-------------|---------|
| N_ROWS | Rows per subarray | 256 |
| N_COLS | Columns per subarray | 64 |
| N_COL_MUX | Column MUX ratio | 8 |
| N_SENSE | Number of SAs (N_COLS/N_COL_MUX) | 8 |
| N_WL_STAGGER | WL stagger groups | 4 |
| CELL_HEIGHT | Bitcell height (m) | 0.5E-6 |
| CELL_WIDTH | Bitcell width (m) | 0.25E-6 |

* Derived dimensions (from array_params.inc derived section):
*   ARRAY_HEIGHT = N_ROWS × CELL_HEIGHT
*   ARRAY_WIDTH = N_COLS × CELL_WIDTH
*   R_BL_METAL, R_WL_METAL, C_BL_TOTAL, C_WL_TOTAL — all derived from array dims + metal R/C

### 10.2 Hierarchical Subarray Template
* File: subarray_template.sp

* ===== SUBARRAY TOP =====
.SUBCKT SRAM_SUBARRAY A<N:0> D_IN SA_OUT CLK VDD VSS
* Address latch + row pre-decode
* WL driver with WLUD (1 driver per row)
* 256 WLs ? resistive load model for 252 unselected + 4 selected

* ===== COLUMN MUX =====
* 64 columns, 8:1 MUX ? 8 sense amps
* Selected column connects to SA
* Unselected columns: BL = VDD (precharged)

* ===== TIMING GENERATION =====
* Internal timing: PCH, SA_EN, WR_EN derived from CLK
* Self-timed: replica path for tracking

* ===== ASSIST CONTROLS =====
* WLUD_EN: WL underdrive enable
* NBL_EN: negative bitline enable
* VCOL_EN: VDD collapse enable

.ENDS SRAM_SUBARRAY

---

## 11. Complete Mini-Array Workbench Template

* File: sram_miniarray_workbench.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* ===== INCLUDE PARAMETER FILE (EDIT YOUR VALUES HERE) =====
.INCLUDE 'array_params.inc'

* ===== INCLUDE ALL PERIPHERAL MODELS =====
.INCLUDE 'array_load_model.inc'       * Section 2: BL/WL Pi-model, dummy cells
.INCLUDE 'wlud_gen.inc'               * Section 4: WLUD voltage generation
.INCLUDE 'precharge.inc'              * Section 5: Precharge circuit
.INCLUDE 'write_driver_nbl.inc'       * Sections 6-7: Write driver + NBL
.INCLUDE 'sense_amp.inc'              * Section 8: Sense amplifier
.INCLUDE 'vdd_collapse.inc'           * Section 9: VDD collapse header

* ===== SUPPLIES =====
* All voltages derived from array_params.inc parameters
VDD_SRC VDD 0 DC='VDD_NOM'
VDD_VWL VWL 0 DC='VDD_NOM - WLUD_DELTA * WLUD_EN'
VVDD_COL VVDD_INT 0 DC='VDD_NOM - VCOL_DELTA * VCOL_EN'
VSS_SRC VSS 0 DC=0

* ===== BITCELL (6T with collapsed supply) =====
* Device dimensions from array_params.inc (W_PG, W_PD, W_PU, L_CELL)
MPU1 VVDD VVDD2 VVDD_INT VVDD_INT PMOS_SRAM W='W_PU' L='L_CELL'
MPU2 VVDD2 VVDD VVDD_INT VVDD_INT PMOS_SRAM W='W_PU' L='L_CELL'
MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W='W_PD' L='L_CELL'
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W='W_PD' L='L_CELL'
MPG1 BL_INT WL_SEL VVDD VSS NMOS_SRAM W='W_PG' L='L_CELL'
MPG2 BLB_INT WL_SEL VVDD2 VSS NMOS_SRAM W='W_PG' L='L_CELL'

* ===== ARRAY LOAD =====
* BL Pi-model (uses R_BL, C_BL_TOTAL from derived params)
RBL1 BL BL_MID 'R_BL/2'
RBL2 BL_MID BL_INT 'R_BL/2'
CBL1 BL 0 'C_BL_TOTAL/2'
CBL2 BL_INT 0 'C_BL_TOTAL/2'
* BL-BLB coupling
CBLBL BL BLB 'C_BL_BLB'
* WL Pi-model (uses R_WL, C_WL_TOTAL from derived params)
RWL1 WL_IN WL_MID 'R_WL/2'
RWL2 WL_MID WL_SEL 'R_WL/2'
CWL1 WL_IN 0 'C_WL_TOTAL/2'
CWL2 WL_SEL 0 'C_WL_TOTAL/2'
* Dummy cells (2 rows — mimics edge mismatch)
XDUMMY_T BL_INT BLB_INT VDD VSS DUMMY_CELL
XDUMMY_B BL_INT BLB_INT VDD VSS DUMMY_CELL

* ===== COLUMN MUX =====
XCOLMUX SA_IN SA_INB BL_INT BLB_INT BL_UNSEL0 BLB_UNSEL0 +
+        BL_UNSEL1 BLB_UNSEL1 SEL<0> SEL<1> SEL<2> VSS COL_MUX
* SEL timing
VSEL0 SEL<0> 0 PULSE(0 'VDD_NOM' '10E-12' '5E-12' '5E-12' 'WL_PW+300E-12' 'PERIOD')
VSEL1 SEL<1> 0 DC=0   * Unused in this test
VSEL2 SEL<2> 0 DC=0   * Unused in this test

* Unselected column loads (for disturb monitoring — Section 16)
RBL_UNSEL0 BL_UNSEL0 BL_UNSEL_MID0 'R_BL/2'
RBL_UNSEL1 BL_UNSEL1 BL_UNSEL_MID1 'R_BL/2'
CBL_UNSEL0 BL_UNSEL0 0 'C_BL_TOTAL/2'
CBL_UNSEL1 BL_UNSEL1 0 'C_BL_TOTAL/2'

* ===== ROW PERIPHERY =====
* WL driver
XWL_BUF WL_TRIG WL_IN VDD VWL VSS WL_BUF_WLUD
VWL_TRIG WL_TRIG 0 PULSE(0 'VDD_NOM' '10E-12' '5E-12' '5E-12' 'WL_PW' 'PERIOD')

* ===== COLUMN PERIPHERY =====
* Precharge
XPRECH SA_IN SA_INB PCH 'VDD_NOM' PRECHARGE
VPCH PCH 0 PULSE(0 'VDD_NOM' 0 '5E-12' '5E-12' 'WL_PW+20E-12' 'PERIOD')

* Write driver + NBL
XWD SA_IN SA_INB WR_DATA WR_EN 'VBOOST_MAG' 'VDD_NOM' VSS WRITE_DRIVER_NBL
VWR_DATA WR_DATA 0 DC='VDD_NOM'
VWR_EN WR_EN 0 PULSE(0 'VDD_NOM' 'TWR_EN_START' '5E-12' '5E-12' 'TWR_EN_WIDTH' 'PERIOD')
VNBL_EN NBL_EN_NODE 0 PULSE(0 'VDD_NOM' 'TD_NBL' '5E-12' '5E-12' 'NBL_PW' 'PERIOD')

* NBL boost voltage (negative pulse on bitline)
* NBL boost applied differentially — see Section 7 for details
VNBL_BOOST NBL_BOOST 0 PULSE(0 '-VBOOST_MAG' 'TD_NBL' '5E-12' '5E-12' 'NBL_PW' 'PERIOD')

* ===== REPLICA TIMING PATH =====
* If REPLICA_EN=1, SA_EN is self-timed (Section 14)
* If REPLICA_EN=0, use fixed delay
.IF (REPLICA_EN == 1)
 .INCLUDE 'replica_timing.inc'
.ELSE
 VSA_EN SA_EN 0 PULSE(0 'VDD_NOM' 'WL_PW - 50E-12' '5E-12' '5E-12' '100E-12' 'PERIOD')
.ENDIF

* Sense amplifier
XSA SA_IN SA_INB SA_OUT SA_OUTB SA_EN 'VDD_NOM' VSS SA_LATCH

* ===== INITIAL CONDITIONS =====
.IC V(VVDD)=VDD V(VVDD2)=0
.IC V(SA_IN)='VDD_NOM' V(SA_INB)='VDD_NOM'

* ===== TRANSIENT =====
.TRAN '1E-15' 'PERIOD' UIC

* ===== MEASUREMENTS =====
.MEASURE TRAN IREAD_MEAS AVG I(MPG1) FROM='50E-12' TO='100E-12'
.MEASURE TRAN TREAD_MEAS TRIG V(WL_IN) VAL='VDD_NOM*0.5' RISE=1
+                       TARG V(SA_OUT) VAL='VDD_NOM*0.5' RISE=1
.MEASURE TRAN TWRITE_MEAS TRIG V(WL_IN) VAL='VDD_NOM*0.5' RISE=1
+                        TARG V(VVDD) VAL='VDD_NOM*0.5' RISE=1
.MEASURE TRAN VBL_MIN_MEAS MIN V(SA_IN) FROM=0 TO='WL_PW'
.MEASURE TRAN VWL_MEAS AVG V(WL_SEL) FROM='50E-12' TO='100E-12'

* ===== READ DISTURB MONITORS (Section 16) =====
.MEASURE TRAN V_Q_UNSEL0_MIN MIN V(BL_UNSEL_MID0) FROM=0 TO='WL_PW'

.END

---

## 12. Post-Sim Like RC Modeling Guide

### 12.1 Philosophy: What "Post-Sim Like" Means
??? **PEX extraction ??**,

> ??? dominant parasitic R/C? **lumped model? ??**??  
> ideal schematic? real silicon ??? ?? ??? simulation.

| Level | R/C Sources | Accuracy | Simulation Time |
|-------|-------------|----------|----------------|
| Schematic ideal | None | Low (optimistic) | Seconds |
| **Post-sim like (this)** | **Lumped R + C per segment** | **Medium (?15%)** | **Minutes** |
| Full PEX | Distributed RC + CC | High (?5%) | Hours~Days |

### 12.2 Which Parasitics Matter (Dominance Matrix)

| Parasitic | BL ?? | WL ?? | Timing ?? | Post-sim like ?? |
|-----------|---------|---------|-------------|------------------|
| BL metal R | ????? | ? | ???? | **??** |
| BL metal C (??+ fringe) | ????? | ? | ???? | **??** |
| BL-BLB coupling C | ???? | ? | ??? | **??** (differential) |
| WL metal R | ? | ????? | ???? | **??** |
| WL metal C | ? | ????? | ???? | **??** |
| WL-BL overlap C (Cgd_PG) | ??? | ??? | ??? | **??** (bump) |
| Diffusion C (drain) | ??? | ? | ??? | Device model ?? |
| Supply IR drop (VDD/VSS) | ?? | ?? | ?? | **??** (? array) |
| Substrate coupling | ? | ? | ? | ?? ?? |
| Via/contact R | ? | ? | ? | lumped R? ?? |

### 12.3 Metal Layer Parameter Reference (Typical 7nm)

| Layer | Pitch (nm) | Sheet R (ohm/sq) | Wire C (aF/um) | Fringe C (aF/um) | Use |
|-------|-----------|-------------------|----------------|------------------|-----|
| M1 (local) | 40 | 8-12 | 80-120 | 40-60 | Cell internal |
| M2 (BL) | 40 | 8-12 | 80-120 | 40-60 | **Bitline** |
| M3 (VSS mesh) | 40 | 8-12 | 80-120 | 40-60 | Ground |
| M4 (WL strap) | 48 | 5-8 | 100-140 | 50-70 | **Wordline strap** |
| M5 (VDD mesh) | 48 | 5-8 | 100-140 | 50-70 | Supply |
| M6-M7 (global) | 64-80 | 2-5 | 120-180 | 60-80 | Global routing |

* **BL**: M2, vertical, half pitch = cell height ? N_rows ? cell_height ? R_per_um
* **WL strap**: M4, horizontal, half pitch = cell width ? N_cols ? cell_width ? R_per_um

* R_per_um example:
  BL on M2: 256rows ? 0.5um ? 10 ohm/sq / 1um (width) ? **1280 ohm**
  (divided by width in squares ? ???: BL width? 1 square?? 256 ? 0.5 ? 10 = 1280)

* ?? ???:
  R_BL = N_rows ? CELL_HEIGHT ? Rsheet_M2 / W_BL
  C_BL = N_rows ? CELL_HEIGHT ? (Cwire_M2 + Cfringe_M2)
  ?_BL = R_BL ? C_BL / 2  (distributed ? lumped approximation: R ? C / 2)

### 12.4 RC Time Constant Approximation

| Component | RC Formula | Example (256rows, 64cols, 7nm) | ? |
|-----------|-----------|-------------------------------|---|
| BL (M2) | ?_BL = (R_BL ? C_BL) / 2 | 1280? ? 164fF / 2 | **105ps** |
| WL (M4) | ?_WL = (R_WL ? C_WL) / 2 | 640? ? 205fF / 2 | **66ps** |
| BL-BLB coupling | ?_couple = R_BL ? C_BLB | 1280? ? 26fF | **33ps** |
| SA input | ?_SA = R_BL ? C_SA_IN | 1280? ? 5fF | **6ps** |

* ?_BL ? 105ps ? Read access time? dominant term
* ?_WL ? 66ps ? WL slew rate ??

### 12.5 WL-to-BL Coupling (The "Bump")

?? ?? ???? parasitic. WL ??? PG? Cgd? ?? BL? feedthrough:

`spice
* WL-BL coupling through MPG1 Cgd
* ? ??? model? ??:
.PARAM C_WL_BL='WPG * 0.3F/1U'       * 160nm ? 0.3fF/um = 48aF
* Effective: small cap, but WL swing = VDD, BL swing = small (?V)
* ? WL rising creates ~20-50mV bump on BL
* ? ? bump? BL discharge? ??? timing ??? ??

* ???:
* Option A: Explicit capacitor (??)
CWLBL WL_SEL BL_INT 'C_WL_BL'

* Option B: BSIM4 Cgd already models this (more accurate)
* .MODEL? CGDO ???? ?? ?? ? ?? cap ???
`

**WL Bump Effect**:
`
BL voltage
  ?
VDD ???????  ???????????????????
          ?  ? ? WL rising edge ? Cgd coupling ? BL bump (+20~50mV)
          ?  ?
          ?  ?    ??? BL discharge ?? (Iread? ??)
          ?  ?    ?
          ?  ?????????????????????? time
              ?
           WL rise ??
`

? bump?:
- BL discharge timing? ~5-10ps ???? (bump? ???? discharge ??)
- SA offset? ??? ? ? ?? (bump? BL/BLB? ????? coupling)
- **WLUD ?? ? bump ??? ???** (WL swing ??)

### 12.6 Supply IR Drop Model

Large array?? VDD/VSS? IR drop? ???? timing? ???(optimistic)?? ??.

`spice
* Simple lumped IR drop model
* I_PEAK_ARRAY_EST from array_params.inc (alias: I_PEAK_ARRAY)
* R_VDD_MESH from array_params.inc; DELTA_VDD_IR, VDD_LOCAL derived there
.PARAM I_PEAK_ARRAY=10E-3          * 10mA peak current (overrides template default if needed)
.PARAM R_VDD_MESH=5                 * VDD mesh resistance (ohm)
.PARAM DELTA_VDD_IR='I_PEAK_ARRAY * R_VDD_MESH / 2'   * ~25mV drop
.PARAM VDD_LOCAL='VDD - DELTA_VDD_IR'

* Local supply after IR drop
VDD_LOCAL_SRC VDD_LOCAL 0 DC='VDD_LOCAL'
* Use VDD_LOCAL for bitcell and periphery
`

### 12.7 Calibration: How to Tune Against Real PEX

1. **Target metric**: BL discharge time (WL?90% BL) in ps
2. **Reference**: ?? full PEX? ?? ?, R_BL, C_BL ?? tuning
3. **Tuning knob**:
   - R_BL: metal sheet resistance multiplier (0.8x ~ 1.2x)
   - C_BL: total capacitance multiplier
   - C_BL_BLB: coupling ratio (0.5x ~ 1.5x)
4. **Iteration**: 
   `
   Step 1: Run mini-array model + PEX (once)
   Step 2: Extract ?_BL, ?_WL from PEX
   Step 3: Adjust R_BL/C_BL in lumped model to match
   Step 4: Verify: TREAD_lumped ? TREAD_PEX ?5%
   Step 5: Use lumped model for all subsequent runs
   `

### 12.8 Parasitic Inclusion Decision Flowchart
`
Starting condition:
?? Array < 32 rows? ? BL R ?? (C?)
?? Array 32-128 rows? ? BL R + C, WL C
?? Array 128-512 rows? ? BL R + C + coupling, WL R + C, WL-BL Cgd
?? Array > 512 rows? ? Full Pi-model + IR drop + ?? coupling

Simulation target:
?? Read timing (?10%)? ? BL/WL RC, WL-BL bump, SA C
?? Write timing (?10%)? ? BL R, NBL coupling ratio
?? Power (?20%)? ? C_BL_total, C_WL_total (C dominant, R ?? ??)
?? Yield/MC (?15%)? ? Full model (R + C + coupling)
`

---

## 13. Column MUX and Shared SA Loading

### 13.1 Motivation

Column MUX (multiplexing) is essential for area-efficient SRAM: multiple bitline pairs share one sense amplifier, reducing SA count by the MUX ratio
(typically 4:1, 8:1, or 16:1). However, the MUX introduces parasitic loading,
access-transistor resistance, and read-disturb paths that **must** be modeled.

### 13.2 Column MUX Structure

```
              SA
               |
         MUX_OUT (shared)
         /    |    \
       MUX0  MUX1  MUX2 ... MUX{N-1}
        |     |     |
      BL0   BL1   BL2 ... BL{N-1}
      :     :     :       :
```

| MUX Ratio | SAs Saved | Parasitic Load Added | Typical Use |
|-----------|-----------|----------------------|-------------|
| 4:1 | 4× | 3 PG drains on MUX_OUT | High-performance |
| 8:1 | 8× | 7 PG drains on MUX_OUT | Balanced |
| 16:1 | 16× | 15 PG drains on MUX_OUT | High-density |

### 13.3 Circuit Model

The MUX is built from NMOS pass-gates. Each MUX device adds:

- **Drain capacitance** on the shared MUX_OUT (SA input) node
- **Source/drain capacitance** on the selected/unselected BL pairs
- **Series resistance** when the pass-gate is ON

```hspice
* Column MUX — N:1 selector
* N_COL_MUX: MUX ratio (PARAM from array_params.inc)
* BL<0:N-1>, BLB<0:N-1>: local bitline pairs
* SA_IN, SA_INB: shared sense-amp input nodes
* SEL<0:N-1>: column select signals

.SUBCKT COL_MUX SA_IN SA_INB BL<0> BLB<0> BL<1> BLB<1> BL<2> BLB<2> +
+                  SEL<0> SEL<1> SEL<2> VSS
* Use MUX devices from the bitcell PG (same size)
* MUX device = bitcell pass-gate (W=W_PG, L=L_CELL)

* --- MUX 0 ---
MMUX0_P SA_IN  SEL<0> BL<0>  VSS NCH W='W_PG' L='L_CELL'
MMUX0_N SA_INB SEL<0> BLB<0> VSS NCH W='W_PG' L='L_CELL'

* --- MUX 1 ---
MMUX1_P SA_IN  SEL<1> BL<1>  VSS NCH W='W_PG' L='L_CELL'
MMUX1_N SA_INB SEL<1> BLB<1> VSS NCH W='W_PG' L='L_CELL'

* --- MUX 2 ---
MMUX2_P SA_IN  SEL<2> BL<2>  VSS NCH W='W_PG' L='L_CELL'
MMUX2_N SA_INB SEL<2> BLB<2> VSS NCH W='W_PG' L='L_CELL'

.ENDS COL_MUX
```

**Key**: MUX device size = bitcell pass-gate. Using larger MUX devices
reduces resistance but increases SA input capacitance — this is a
critical tradeoff for sense-amplifier offset and speed.

### 13.4 Parasitic Load on Sense Amplifier

The shared MUX_OUT node sees the drain capacitance of (N_COL_MUX - 1) **OFF**
MUX devices plus the one **ON** device's channel resistance:

```
C_MUX_LOAD = (N_COL_MUX - 1) × C_DRAIN_PG
R_MUX_ON   = transistor resistance of one MUX device at VGS = VDD
```

**Impact on SA input:**
- Total SA input capacitance: `C_SA_TOTAL = C_SA_IN + C_MUX_LOAD`
- Read delay increases by: `Δt ≈ 0.7 × R_BL × ΔC_MUX × ln(VDD / ΔV)`

| MUX Ratio | C_MUX_LOAD (fF) | SA Input Δt Penalty |
|-----------|-----------------|---------------------|
| 4:1 | 3 × C_DRAIN_PG ≈ 1.5 fF | +3~5% |
| 8:1 | 7 × C_DRAIN_PG ≈ 3.5 fF | +8~12% |
| 16:1 | 15 × C_DRAIN_PG ≈ 7.5 fF | +15~25% |

> **Parameterized in**: `array_params.inc` → `C_MUX_LOAD = (N_COL_MUX - 1) * C_DRAIN_PG`

### 13.5 MUX Timing Control

The MUX select signals must be timed relative to the WL and SA_EN:

```
WL     : ████████████████████████____________
SEL    : ██████████████████████████████████████  (hold across WL + SA)
SA_EN  : ____________████████_________________
PCH    : ████________________________________████
```

**Rules:**
1. SEL must go high **before** WL → BL discharge must flow through an already-on MUX
2. SEL must hold **after** SA_EN → SA must not see a node floating when it fires
3. SEL must hold **after** WL falls → restore path for unselected columns

```
* Timing in the testbench:
VSEL_0 SEL<0> 0 PULSE(0 VDD 'T_SEL_ON' 5E-12 5E-12 'WL_PW + 300E-12' 'PERIOD')
.PARAM T_SEL_ON = '0.1 * PERIOD'  * SEL before WL
```

---

## 14. Replica Timing Path (Self-Timed SA_EN)

### 14.1 Concept

A replica timing path generates the SA_EN signal by mimicking the BL
discharge delay of the **slowest** column, adding a programmable margin:

```
WL rise → replica BL discharge → SA_EN rise
```

The replica column tracks PVT variations automatically because it uses
the same bitcell and BL structure — no fixed delay line needed.

### 14.2 Replica Column Architecture

```
            VDD
             |
            PCH (same as data columns)
             |
     REPLICA_BL ──── R_BL_REP (lumped) ──── C_BL_REP (lumped)
             |
          PG_REP (dummy cell, always ON)
             |
        VSS (or VSS + extra Iread for margin)
             |
        INV_REP (trip point = ΔV_REF)
             |_____ SA_EN
```

| Component | Implementation | Notes |
|-----------|---------------|-------|
| Dummy bitcell PG | One NMOS, gate tied to VDD | Mimics ON cell |
| BL RC | Same R_BL/C_BL derived values | Maybe scaled if N_REPLICA_COLS > 1 |
| Margin | Extra current starvability or inverter trip-point tuning | +10~20ps margin over worst column |
| Disable | REPLICA_EN = 0 → fixed SA_EN delay | For debug/comparison |

### 14.3 HSPICE Implementation

```hspice
* Replica timing path
.PARAM REPLICA_TRIP = 'REPLICA_ΔV_REF'  * Trigger level from params

* --- Replica BL load (same RC as data BL) ---
RREP_BL REPLICA_BL REPLICA_BL_INT R_BL
CREP_BL REPLICA_BL_INT 0 C_BL_TOTAL

* --- Replica bitcell pass-gate (always ON) ---
MREP_PG REPLICA_BL_INT REP_VDD VSS VSS NCH W='W_PG' L='L_CELL'
VREP_VDD REP_VDD 0 VDD

* --- Replica discharge (can add margin with extra current) ---
* Margin = extra NMOS in parallel with PG_REP
.IF (REPLICA_MARGIN > 0)
 MREP_MARGIN REPLICA_BL_INT REP_VDD VSS VSS NCH +
 +   W='W_PG * REPLICA_MARGIN' L='L_CELL'
.ENDIF

* --- Replica sense inverter ---
* Inverter trip: adjust W_P/N ratio so output switches at ΔV_REF drop
VREP_PCH REPLICA_BL 0 VDD
.IC V(REPLICA_BL) = VDD  * Start precharged

XREP_INV REPLICA_BL SA_EN_INT REP_INV

* --- Buffer chain (mimics SA clock distribution) ---
XREP_BUF1 SA_EN_INT SA_EN1 INV
XREP_BUF2 SA_EN1    SA_EN2 INV
XREP_BUF3 SA_EN2    SA_EN  INV

* --- SA_EN override (if REPLICA_EN=0, use fixed delay) ---
.IF (REPLICA_EN == 0)
 VP_SA_EN SA_EN 0 PULSE(0 VDD 'T_SAE_FIXED' 5E-12 5E-12 'WL_PW - T_SAE_FIXED' 'PERIOD')
.PARAM T_SAE_FIXED = 'TPCH_ON + 50E-12'
.ENDIF
```

### 14.4 Replica Margin Setting

Set the SA_EN point to track the **slowest** column in the array, not the
nominal one:

| Variation Source | Margin Needed | How Replica Tracks |
|-----------------|---------------|-------------------|
| Random Vt mismatch | +3σ ≈ +15~25% Iread sigma | N/A (add margin via extra current or inverter offset) |
| Systematic WL RC | -10~15% delay | Replica BL uses same R_BL |
| Systematic temperature | ~5% / 10°C | Same die, tracks |
| Systematic VDD droop | ~3% IR shift | Same mesh resistance |

**Rule of thumb:** Set replica trip point to `ΔV_REF = 50 mV + 3σ_Vt_sigma × (W_PG / W_PG_nom)⁻¹`.
A more aggressive approach: use two stacked dummy cells in the replica for worst-case
corner tracking.

> **Parameters in**: `array_params.inc` → `REPLICA_ΔV_REF`, `REPLICA_EN`, `N_REPLICA_COLS`

---

## 15. BL Precharge RC and Cycle Time

### 15.1 Problem Statement

After a read or write operation, BL and BLB must be restored to VDD before
the next access. Incomplete precharge directly causes:

- **Read**: Reduced BL differential → SA margin loss → read failure
- **Write**: Asymmetric starting voltages → mistaken write completion → write failure
- **Cycle time**: Precharge time can dominate if RC is large

### 15.2 Precharge RC Model

The precharge PMOS (PCH) charges the BL through its on-resistance:

```
R_PCH ≈ 1 / [β_PCH × (VDD - Vth_PCH)]
C_LOAD = C_BL_TOTAL + C_BLB_COUPLE  (both BL and BLB must be restored)

τ_PCH = R_PCH × C_LOAD
```

**Voltage recovery equation:**
```
V_BL(t) = VDD - [VDD - V_BL(0)] × e^(-t / τ_PCH)
```

**Time to reach X% of VDD:**
```
t_X% = τ_PCH × ln[(VDD - V_BL(0)) / (VDD × (1 - X/100))]
```

| Recovery Target | Required τ | Example for τ_PCH = 50 ps |
|----------------|-----------|--------------------------|
| 90% (V_BL = 0.72 V at VDD=0.8V) | 2.3 × τ_PCH | 115 ps |
| 95% (V_BL = 0.76 V) | 3.0 × τ_PCH | 150 ps |
| 99% (V_BL = 0.792 V) | 4.6 × τ_PCH | 230 ps |
| 99.9% (V_BL = 0.799 V) | 6.9 × τ_PCH | 345 ps |

### 15.3 Cycle Time Constraint

```
Tcycle ≥ WL_PW + TSA_latch + TPCH_on + t_90%
```

For a typical 256-row × 64-col mini-array at 0.8V:

| Component | Delay (ps) | Notes |
|-----------|-----------|-------|
| WL pulse | 200 | From WL driver spec |
| SA latch + data out | 50 | From SA offset simulation |
| Precharge enable delay | 20 | PCH control buffer |
| BL restore (90%) | 115 | R_PCH × C_BL × 2.3 |
| **Minimum Tcycle** | **385 ps** | **~2.6 GHz** |

If precharge restore is incomplete (cycle time too short), the residual
ΔV_BL mismatch feeds into the next cycle as an initial offset:

```
ΔV_residual = VDD - V_BL(t_PCH)   → converted to equivalent SA offset
```

**Using parameters:**
```
TPCH_ON_min = TPCH_OFF + WL_PW + 50E-12   * SA done before precharge
TPCH_width  = 0.3 * PERIOD                 * ~30% of cycle for restore
```

> **Parameters in**: `array_params.inc` → `TPCH_OFF`, `TPCH_ON`, `PERIOD`

### 15.4 Precharge Optimization

| Technique | Effect | Tradeoff |
|-----------|--------|----------|
| Wider PCH (2× width) | 2× current → ½ τ_PCH | Area, CLK load |
| Dual-rail precharge | Two PCH per BL | 2× area |
| Half-hold (weak keeper) | Fast restore from mid-rail | Extra leakage |
| Precharge during WL active | Overlap → +20% recovery | WL-BL coupling noise |

**Typical sizing:**
```
W_PCH ≥ 2 × (C_BL_TOTAL × R_ch) / (TPCH_width × VDD)
where R_ch = channel resistance of PCH at saturation
```

---

## 16. Read Disturb on Unselected Columns

### 16.1 Mechanism

In a column-muxed architecture, when one column is selected for read,
**unselected columns** in the same subarray still experience:

1. **Half-select disturb**: WL goes high for ALL rows in the selected row,
   but only the selected column's SA reads. Unselected columns' bitcells
   on the same row are half-selected: WL=VDD but BL/BLB ≈ VDD (not developing
   differential).
2. **BL leakage coupling**: Unselected BLs at VDD can couple charge into
   the selected BL through MUX drain capacitance.
3. **Read disturb on unselected columns**: A half-selected cell that is
   storing a '0' (node Q=0V, QB=VDD) experiences stress: PG tries to pull
   the Q node up through the ON pass-gate against the PD. This can flip
   weak cells at low VDD.

### 16.2 Read Disturb Model

The critical case is an unselected column on the **same row** as the
selected column, where WL=VDD:

```
Selected column:    BL develops ΔV → SA reads
Unselected col:     BL stays at VDD → half-selected cell stressed
```

**Disturb current per half-selected cell:**
```
I_disturb ≈ Iread(ΔV_GS = VDD - V_Q)
```

Where the internal node Q (stored '0') rises due to leakage and PG current:
```
ΔQ_rise = I_disturb × WL_PW
V_Q_rise = ΔQ_rise / C_Q  (C_Q ≈ C_DRAIN_PD + C_GD_PG)
```

A cell flips when V_Q_rise > V_trip of the cross-coupled inverter
(approximately VDD/2 for a balanced cell).

### 16.3 Read Disturb Probability

| Condition | Disturb Risk | Mitigation |
|-----------|-------------|------------|
| VDD high, W_PG nominal | Negligible | Iread is large but PD is stronger |
| Low VDD, weak PD | Moderate | Reduce WL_PW, use WLUD |
| Low VDD + sigma Vt mismatch | **High** | WLUD, half-select assist, write-back |
| Long WL pulse | Higher | Minimize WL_PW for read |

### 16.4 HSPICE Disturb Monitor

Monitor unselected columns to directly observe the disturb:

```hspice
* Unselected column monitor — same row, different column
* Place this on 2~3 unselected BL/BLB pairs in the same row

* --- Unselected column 0 (Q=0, QB=1 — worst-case disturb) ---
XCELL_UNSEL0 BL0 BLB0 WL VDD_CORE VSS SRAM_BITCELL
* Initial condition: stored '0'
.IC V(Q_UNSEL0) = 0 V(QB_UNSEL0) = VDD

* --- Internal node probe (inside cell, if subcircuit allows) ---
* Alternative: monitor BL0-Q voltage difference to detect partial flip

* --- Disturb metric ---
.MEASURE TRAN V_Q_RISE_MAX MAX V(Q_UNSEL0) FROM=T_WL_RISE TO=T_WL_FALL
.MEASURE TRAN V_Q_QB_CROSS TRIG V(Q_UNSEL0) VAL='VDD/2' RISE=1 +
+                                      TARG V(QB_UNSEL0) VAL='VDD/2' FALL=1

* --- Force disturb assessment: measure critical charge ---
* Incremental approach:
* .STEP param VTH_OFFSET -50MV 50MV 10MV  * Sweep Vt offset on unsel cell
* .MEASURE TRAN Q_CRIT INTEG I(VPG_UNSEL) FROM=T_WL_RISE TO=T_WL_FALL
```

### 16.5 Mitigation Strategies

| Technique | Disturb Reduction | Cost |
|-----------|------------------|------|
| WLUD | -30~50% Iread in all cells | Read speed |
| VDD Collapse (write) | -40% disturb current | Write assist complexity |
| Column-invariant WL width | Equal WL rise for all columns | Minimal |
| Short WL pulse | Minimize stress time | SA timing margin |
| Write-back after read | Restore half-selected cells | Cycle time, power |
| Dummy column insertion | Extra BL loading dampens disturb | Area |

> **Unselected column monitoring always recommended** — disturb failures
> appear as soft errors that are invisible in a single-column simulation.

---

## 17. Timing Path RC Separation (Read vs Write)

### 17.1 Why Separate Read and Write Paths?

Read and write operations have fundamentally different timing-critical
paths through the BL:

| Path | Read | Write |
|------|------|-------|
| Critical direction | BL discharge (BL → VSS) | BLB charge (BLB → VDD via NBL) |
| Dominant R | R_BL from cell to SA | R_BL from WD to cell |
| Dominant C | C_BL_TOTAL (drains + wire) | C_BL_TOTAL + C_NBL |
| Current direction | Cell PG → BL → SA | WD → BL → Cell PG |
| Distributed vs lumped | Distributed (cell along BL) | Lumped (WD at BL edge) |
| Sensitivity to BL R | High (discharge rate) | Very high (NBL time constant) |

### 17.2 Read Critical Path RC

```
CELL (nearest)              CELL (farthest)
  |←---- 1/2 C_BL ----→|←-- 1/2 C_BL + R_BL ---→|
  ↓ Iread                                           SA
  BL ──── R_BL_segment ──── R_BL_segment ──── MUX ── SA_IN
```

For read timing, the **farthest cell** from the SA is worst-case because:

- BL discharge current (Iread) must travel through the full BL resistance
- The RC delay is distributed: `τ_read ≈ 0.7 × (R_BL × C_BL_TOTAL / 2)`

The **nearest cell** is worst-case for SA offset because:
- Minimal R_BL → faster discharge → larger ΔV at same t → less integration
  needed → more sensitive to SA offset

### 17.3 Write Critical Path RC

```
WD ──── R_BL ──── BL ──── CELL
       C_BL_TOTAL
       C_NBL (during NBL)
```

For write timing, the **farthest cell** from the WD is worst-case:

- The WD must drive the BL through the full BL resistance
- NBL boost travels through R_BL before reaching the cell:
  `τ_NBL_propagation ≈ 2.2 × R_BL × C_BL_TOTAL` (step response to 90%)
- If NBL_EN=1, the delay for the negative boost at the cell is:
  `V_BL_cell(t) ≈ VBOOST × [1 - e^(-t / (R_BL × C_BL_TOTAL))]`

### 17.4 Read vs Write Timing Equations

| Parameter | Read | Write |
|-----------|------|-------|
| Delay model | Distributed RC line | Lumped RC (dominant pole) |
| τ formula | `0.7 × C_BL_TOTAL × (R_BL/2)` | `2.2 × R_BL × C_BL_TOTAL` |
| ΔV target | 50~100 mV BL discharge | Cell trip point (~VDD/2) |
| Assist relevance | WLUD slows, VCOL slows | NBL accelerates |
| R_BL impact | Proportional to R_BL × C_BL | **Stronger**: proportional to R_BL |

### 17.5 HSPICE: Measure Both Timing Paths

```hspice
* --- Read timing: cell → SA ---
* Selected cell at bottom (farthest from SA for worst-case read)
.MEASURE TRAN T_READ_CELL_FAR TRIG V(WL) VAL='VDD/2' RISE=1 +
+                           TARG V(SA_IN) VAL='VDD-0.05' FALL=1

* Selected cell at top (nearest to SA — worst-case SA offset, best read delay)
.MEASURE TRAN T_READ_CELL_NEAR TRIG V(WL) VAL='VDD/2' RISE=1 +
+                            TARG V(SA_IN) VAL='VDD-0.05' FALL=1

* --- Write timing: WD → cell ---
* Include NBL boost if enabled
.MEASURE TRAN T_WRITE_CELL TRIG V(WL) VAL='VDD/2' RISE=1 +
+                         TARG V(Q_CELL) VAL='VDD/2' CROSS=2

* --- NBL propagation delay ---
.MEASURE TRAN T_NBL_CELL TRIG V(NBL_EN) VAL='VDD/2' RISE=1 +
+                       TARG V(BL_WRITE_CELL) VAL='-0.1' FALL=1

* --- Path-specific constraint check ---
* Write must complete before WL falls AND before precharge starts
* Read must complete ΔV >= target before SA_EN fires
.ALTER check_read_setup
  .MEASURE TRAN T_READ_MARGIN +
+   TRIG V(SA_EN) VAL='VDD/2' RISE=1 +
+   TARG V(BL_READ_CELL) VAL='VDD - BL_DELTA_TARGET' FALL=1
  .MEASURE TRAN T_READ_FAIL PARAM='T_READ_MARGIN' < 0
```

### 17.6 Unified Timing Margin Check

For write, the margin is defined as:

```
write_complete_time < WL_fall_time — 20 ps (guardband)
```

For read:

```
BL_delta_target_time < SA_EN_time — 10 ps (guardband)
```

Both should be checked across PVT corners.

> **Parameters in**: `array_params.inc` → `BL_DELTA_TARGET`, `TSAE_MARGIN`, `TWR_EN_START`

---

## 18. Peripheral Signal Timing Quick Reference

### 18.1 Signal Timing Dependency on RC Load
| Signal | Dominant Load | Delay Formula | Typical (256-row × 64-col) |
|--------|--------------|--------------|-------------------|
| WL rise | R_WL × C_WL | 0.7 × R_WL × C_WL | ~46 ps |
| BL discharge | R_BL × C_BL/2 | 0.7 × τ_BL × ln(VDD/ΔV) | ~105 ps |
| SA enable | R_BL × C_SA_IN | 0.7 × R_BL × C_SA | ~5 ps |
| Write completion | R_BL × C_BL/2 | 0.7 × τ_BL × ln(VDD/Vtrip) | ~95 ps |
| Precharge restore | R_PCH × C_BL | 0.7 × R_PCH × C_BL | ~50 ps |
| NBL boost | R_BL × C_NBL | R_BL × C_NBL × ln(VBOOST/ΔV) | ~30 ps |

### 18.2 Assist Impact on Timing
| Assist | Effect on Delay | Mechanism |
|--------|----------------|-----------|
| WLUD | +15~30% read delay | Lower WL voltage ? less Iread |
| VDD collapse | +20~40% read delay | Lower cell supply ? less Iread |
| NBL | -30~50% write delay | Lower BL ? faster cell flip |
| WL full VDD (write) | -20~30% write delay | Higher PG current |

> **Revision History**
> - 2026-06-30: V1.0 — Initial version. Mini-array peripheral modeling, assist circuits, post-sim like RC calibration guide.
> - 2026-06-30: V2.0 — Added Sections 13–17 (Column MUX, Replica Timing Path, Precharge RC & Cycle Time, Read Disturb, Timing Path RC Separation). Renumbered former Section 13 → 18. Created `array_params_template.inc` — all user-configurable parameters collected into a single file with `<<< USER:` markers. All sections now reference the parameter file. Section 11 workbench updated with MUX, replica timing, and .INCLUDE 'array_params.inc'.
