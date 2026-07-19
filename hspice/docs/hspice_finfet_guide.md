---
title: 'HSPICE FinFET/BSIM-CMG Guide'
subtitle: 'FinFET-Specific Simulation: BSIM-CMG, NFIN Quantization, Parasitics, Self-Heating, and Back-Bias'
version: '1.0'
date: '2026-06-30'
description: 'Comprehensive HSPICE guide for FinFET node simulation (7nm/5nm/3nm). Covers BSIM-CMG (LEVEL 72/73/74) model specifics, NFIN quantization rules, parasitic resistances and capacitances, self-heating effects, back-bias operation, layout-dependent effects, and corner modeling.'
tags: [HSPICE, FinFET, BSIM-CMG, NFIN, self-heating, back-bias, FDSOI, 7nm, 5nm, 3nm]
language: 'HSPICE'
keywords: [FinFET, BSIM-CMG, LEVEL 72, NFIN, R_ext, self-heating, back-gate bias, LOD, process corner]
---

# HSPICE FinFET/BSIM-CMG Simulation Guide

> **Purpose**: HSPICE simulation methodology for FinFET technology nodes (7nm, 5nm, 3nm, and beyond).
> **Coverage**: BSIM-CMG model hierarchy, fin quantization, parasitic modeling, self-heating, back-bias, layout-dependent effects.
> **Target**: FinFET-specific HSPICE usage for transistor-level characterization and SRAM design.

---

## Table of Contents

1. [FinFET Technology Overview](#1-finfet-technology-overview)
2. [BSIM-CMG Model (LEVEL 72/73/74)](#2-bsim-cmg-model-level-727374)
3. [NFIN Quantization and Electrical Width](#3-nfin-quantization-and-electrical-width)
4. [External Resistance (R_ext) Modeling](#4-external-resistance-r_ext-modeling)
5. [Fringing Capacitance](#5-fringing-capacitance)
6. [Self-Heating Effect (SHE)](#6-self-heating-effect-she)
7. [Back-Gate Bias (VBack)](#7-back-gate-bias-vback)
8. [Layout-Dependent Effects (LDE)](#8-layout-dependent-effects-lde)
9. [FinFET SRAM-Specific Considerations](#9-finfet-sram-specific-considerations)
10. [Process Corners for FinFET Nodes](#10-process-corners-for-finfet-nodes)
11. [Temperature Inversion in FinFET](#11-temperature-inversion-in-finfet)
12. [Complete FinFET Characterization Workbench](#12-complete-finfet-characterization-workbench)
13. [References](#13-references)

---

## 1. FinFET Technology Overview

### 1.1 What Changes from Planar (Bulk/BSIM4) to FinFET
| Aspect | Planar (BSIM4) | FinFET (BSIM-CMG) | Impact |
|--------|---------------|--------------------|--------|
| Channel control | Gate from top | Gate wraps 3 sides | Better DIBL, more complex model |
| Width quantization | Continuous W | Discrete NFIN integer | Layout fixed before simulation |
| Body terminal | Separate Bulk | Floating / tied back-gate | Different bias schemes |
| Corner effect | None | Round-corner model | W_OD, H_FIN parameters |
| Self-heating | Optional | Essential (FIN confined) | Higher Rth, bigger temp rise |
| Fringe capacitance | Single component | Multi-path fringe | AC model more complex |
| Well proximity | LOD, WPE, etc. | LOD, WPE, plus OD width | LDE rules differ |

### 1.2 FinFET Node Mapping
| Foundry Node | Fin Pitch | Fin Height | Device | BSIM-CMG Level |
|-------------|-----------|------------|--------|-----------------|
| 7nm (N7) | 30-36nm | 35-40nm | FinFET | LEVEL=72 or 74 |
| 5nm (N5) | 24-30nm | 35-45nm | FinFET + EUV | LEVEL=74 |
| 3nm (N3) | 20-24nm | 40-50nm | FinFET / GAA-like | LEVEL=74+ |
| 14nm/16nm | 42-48nm | 30-35nm | FinFET | LEVEL=72 |

### 1.3 Key Parameter Changes in Netlists
* PLANAR: W=1N means width = 1e-9 m (continuous)
* FinFET: NFIN=1 means exactly 1 fin (quantized, integer only)

* Multi-fin device: total effective current = NFIN * current per fin
* Effective width: W_eff = NFIN * (2 * H_FIN + T_FIN)

---

## 2. BSIM-CMG Model (LEVEL 72/73/74)

### 2.1 Model Level Selection
| LEVEL | Description | Use Case |
|-------|-------------|----------|
| 72 | BSIM-CMG basic (2013 baseline) | Legacy FinFET, 14nm/16nm |
| 73 | BSIM-CMG v2 (enhanced R_ds, GIDL) | 7nm LP, IoT FinFET |
| 74 | BSIM-CMG v3 (self-heating, AC, noise) | 7nm+ and beyond (HIGH PERFORMANCE) |
| 75 | BSIM-CMG v4 (latest, junctionless support) | Emerging nodes, R&D |

### 2.2 BSIM-CMG .MODEL Syntax
* Basic NMOS FinFET model invocation
.MODEL NMOS_FIN nmos
+ LEVEL   = 74
+ VERSION = 110        * BSIM-CMG version
+ MOBMOD  = 1          * Mobility model (1=default)
+ RDSMOD  = 1          * External resistance model
+ SHMOD   = 1          * Self-heating model (1=on, 0=off)
+ COREMOD = 1          * Core model selection (0=SurfPot, 1=Charge)
+ GEOMOD  = 2          * Geometry model (2=standard FinFET)
+ CAPMOD  = 2          * Capacitance model (2=charge-based)
+ ...

### 2.3 Core BSIM-CMG Parameters (Essential)
* --- GEOMETRY ---
.PARAM L_DRAW=20N      * Drawn channel length (m)
.PARAM NFIN=1           * Number of fins (integer, ?1)
.PARAM H_FIN=40N        * Fin height (m)
.PARAM T_FIN=8N         * Fin body thickness (m)
.PARAM T_GATE=30N       * Gate length (same as L_DRAW typically)

* --- THRESHOLD ---
.PARAM VTH0=0.3         * Long-channel Vth (V)
.PARAM PHIG=4.5         * Gate workfunction (eV)
.PARAM EPSROX=3.9       * Gate oxide dielectric constant
.PARAM TOXE=1.2N        * Electrical oxide thickness (m)

* --- MOBILITY ---
.PARAM U0=0.02          * Low-field mobility (m?/Vs)
.PARAM UA=1E-15         * 1st mobility degradation coefficient
.PARAM UB=1E-16         * 2nd mobility degradation coefficient
.PARAM UC=-3E-11        * 3rd mobility degradation coefficient

* --- S/D RESISTANCE ---
.PARAM RDSW=200         * Source/drain sheet resistance (ohm/um)
.PARAM RDSWMIN=100      * Minimum Rds at high Vgs

* --- DIBL AND SS ---
.PARAM ETA0=0.2         * DIBL coefficient
.PARAM CDSC=2E-3        * Drain-induced barrier lowering
.PARAM CIT=0            * Interface state capacitance (F/m?)

### 2.4 Geometry Model (GEOMOD)
| GEOMOD | Description | Equation |
|--------|-------------|----------|
| 0 | Planar-like (not FinFET) | W_eff = NFIN * (2 * H_FIN + T_FIN) |
| 1 | Double-gate (DG) | W_eff = NFIN * 2 * H_FIN |
| 2 | Standard FinFET (recommended) | W_eff = NFIN * (2 * H_FIN + T_FIN) |
| 3 | Gate-all-around (GAA/NS) | Cylindrical/rectangular wire |

For standard 7nm FinFET (GEOMOD=2):
* W_eff = NFIN * (2 * H_FIN + T_FIN)
* Example: NFIN=2, H_FIN=40nm, T_FIN=8nm ? W_eff = 2 * (80N + 8N) = 176nm

### 2.5 Device Instance for FinFET
* Standard invocation (4-terminal: D, G, S, body/sub)
M1 D G S SB SUB NMOS_FIN L='L_DRAW' NFIN='NFIN' \
    H_FIN='H_FIN' T_FIN='T_FIN' T_GATE='T_GATE'

* With back-gate bias (5-terminal: D, G, S, SBG, B)
* The SBG terminal connects to back-gate/secondary gate
M1 D G S BG NWELL NMOS_FIN L='L_DRAW' NFIN='NFIN' \
    H_FIN='H_FIN' T_FIN='T_FIN'

### 2.6 Minimum and Maximum NFIN Limits
* Foundry DRC rules typically specify:
* Min NFIN: 1 (single-fin)
* Max NFIN: 8 ~ 48 (wide devices via fin fingers)
* NFIN must be INTEGER ? fractional NFIN causes error or scaling mismatch

* WRONG (will trigger DRC/model warning):
M1 D G S 0 NMOS_FIN L=20N NFIN=1.5

* CORRECT:
M1 D G S 0 NMOS_FIN L=20N NFIN=2

---

## 3. NFIN Quantization and Electrical Width

### 3.1 NFIN Quantization Impact
In FinFET, width = NFIN * (effective width per fin). NFIN is set at layout time and must be an integer.

| Planar (continuous) | FinFET (discrete) |
|---------------------|-------------------|
| W = 1.5um possible | NFIN=12 (per fin width) |
| W = 1.7um possible | Must round up to NFIN=14 |
| Analog sizing flexible | Digital/analog sizing quantized |

### 3.2 NFIN Sweep for Sizing
* Sweep integer fin counts using .DATA or .ALTER

.PARAM NFIN=1
M1 D G S 0 NMOS_FIN L=20N NFIN='NFIN'

.DATA NFIN_DATA
+ 1
+ 2
+ 3
+ 4
+ 6
+ 8
.ENDDATA

.DC DATA=NFIN_DATA
.MEASURE DC IDSAT_NFIN FIND I(M1) AT VGS=VDD

* --- OR use .ALTER ---
.ALTER case=NFIN1
    .PARAM NFIN=1
.ALTER case=NFIN2
    .PARAM NFIN=2
.ALTER case=NFIN4
    .PARAM NFIN=4

### 3.3 Fin Multipliers vs Fin Fingers
| Concept | Meaning | HSPICE Usage |
|---------|---------|-------------|
| NFIN | Number of fins in 1 device finger | M1 D G S 0 ... NFIN=4 |
| M | Number of parallel device fingers | M1 D G S 0 ... NFIN=1 M=4 |
| NFIN+M combo | Total fins = NFIN * M | M1 D G S 0 ... NFIN=2 M=2 (total 4 fins) |

* M=1, NFIN=4 ? 4 fins in single layout stripe
* M=4, NFIN=1 ? 4 fin fingers in parallel, layout spreads over 4 stripes
* M=2, NFIN=2 ? 4 fins total, 2 stripes of 2 fins each

### 3.4 Current Scaling Examples
* Saturation current per fin (Idsat_per_fin)  ~ 5-12 uA at nominal VDD
* Total Idsat = NFIN * Idsat_per_fin

| NFIN | Total Idsat (8uA/fin) | Use Case |
|------|----------------------|----------|
| 1 | 8 uA | SRAM pass-gate (minimum) |
| 3 | 24 uA | SRAM pull-down |
| 6 | 48 uA | Standard logic cell |
| 16 | 128 uA | Strong driver |
| 48 | 384 uA | Clock buffer |

### 3.5 Fin Aspect Ratio and Corner Effects
BSIM-CMG models the fin corners with parameters:
| Parameter | Description | Impact |
|-----------|-------------|--------|
| W_OD | Oxide definition width | Corner rounding, Vth shift |
| H_FIN | Fin height (process determined) | Higher fin = more current per fin |
| T_FIN | Fin thickness | Thin fin = better short-channel control |
| ALPHA0 | Corner conduction factor | Lower = less corner conduction |

* Typical H_FIN : T_FIN ratio = 5:1 (40nm : 8nm)
* Corner effect creates lower Vth near fin edges ? adjusted by ALPHA0/ALPHA1

---

## 4. External Resistance (R_ext) Modeling

### 4.1 R_ext Components in FinFET
FinFET parasitic resistance consists of:
1. **R_sd** (extension resistance) ? S/D under spacer (largest component)
2. **R_contact** ? contact to S/D epi (Tier of silicide + barrier)
3. **R_via** ? via resistance from metal 1
4. **R_sheet** ? sheet resistance of fin body

### 4.2 BSIM-CMG Resistance Model (RDSMOD)
| RDSMOD | Description | Usage |
|--------|-------------|-------|
| 0 | No external resistance | Fast but inaccurate |
| 1 | Bias-dependent Rds(Vgs) | Default, recommended |
| 2 | Fixed Rds (external R only) | Simple back-of-envelope |

### 4.3 RDSMOD=1 Syntax
.MODEL NMOS_FIN nmos
+ RDSMOD = 1
* Intrinsic Rds parameters
+ RDSW   = 250   * Rds per unit width at high Vgs (ohm-um)
+ RDSWMIN = 120  * Minimum Rds (ohm-um)
+ RDSW_SF = 1.0  * Scaling factor for RDSW
+ RDSWDR = 1.0   * Drain-side Rds weight
+ PRWB    = 1E-3 * Rds sensitivity to body bias
+ PRWG    = -0.2 * Rds sensitivity to gate bias
+ ...

### 4.4 External Resistor (R_ext) Subcircuit
* For precise modeling with known parasitic extraction data
.SUBCKT FIN_FET D G S B L=20N NFIN=1 H_FIN=40N T_FIN=8N
* Internal device without Rds (RDSMOD=0)
M1 DI GI SI B NMOS_CORE L='L' NFIN='NFIN' H_FIN='H_FIN' T_FIN='T_FIN'
+ RDSMOD=0
* External resistors from extraction
RD D DI 'RDE*NFIN'   * Drain contact + via + SD
RS S SI 'RSE*NFIN'   * Source contact + via + SD
RG G GI 'RGE'        * Gate resistance
.ENDS FIN_FET

### 4.5 R_ext Variation with NFIN
* Contact resistance per fin: R_cont_per_fin = 50 ~ 200 ohm (process dependent)
* Total R_ext (source side): R_s = R_cont_per_fin / NFIN
* For NFIN=1 ? R_s = 150 ohm
* For NFIN=4 ? R_s = 37.5 ohm

### 4.6 Impact on Idsat and Transconductance
* High R_ext degrades:
  - Idsat (voltage drop across R_ext reduces intrinsic Vds)
  - Gmmax (Rs = 100 ohm reduces Gm by ~15% in high-performance FinFET)
  - RF performance (ft, fmax)

* Quick check: Idsat ratio = VDD / (VDD + 2 * Idsat * R_ext)

---

## 5. Fringing Capacitance

### 5.1 FinFET Capacitance Components
In FinFET, parasitic capacitances are more complex due to 3D structure:
1. **C_gate_overlap** ? gate to S/D overlap
2. **C_fringe_outer** ? gate spacer to S/D (fringing through spacer)
3. **C_fringe_inner** ? gate to channel through spacer (bias dependent)
4. **C_fin_to_fin** ? adjacent fin coupling
5. **C_substrate** ? fin to substrate

### 5.2 BSIM-CMG Capacitance Parameters (CAPMOD=2)
* CAPMOD = 2 (charge-based capacitance model, recommended)
.MODEL NMOS_FIN nmos
+ CAPMOD = 2

* Fringing capacitance parameters
+ CF    = 5E-11  * Fringing capacitance coefficient (F/m)
+ CFS   = 5E-11  * Source-side fringing capacitance (F/m)
+ CFD   = 5E-11  * Drain-side fringing capacitance (F/m)
+ CGSO  = 1E-10  * Gate-source overlap capacitance per unit length (F/m)
+ CGDO  = 1E-10  * Gate-drain overlap capacitance per unit length (F/m)
+ CGBO  = 1E-11  * Gate-body overlap capacitance per unit length (F/m)

* Capacitance of the gate electrode
+ XPART = 0.5   * Charge partitioning (0.5 = 50/50, recommended for AC)

### 5.3 Gate Resistance
* Gate resistance is critical for FinFET AC/RF modeling
.MODEL NMOS_FIN nmos
+ RSHG  = 5     * Gate sheet resistance (ohm/sq)
+ XGW   = 1     * Gate width multiplier for Rg calculation
+ XGL   = 1     * Gate length multiplier for Rg calculation
+ NGCON = 2     * Number of gate contacts (1=one side, 2=both sides)

* R_gate total = RSHG * (W_eff / (L_eff * NGCON * 0.5))

---

## 6. Self-Heating Effect (SHE)

### 6.1 Why Self-Heating Matters in FinFET
FinFET channels are thermally isolated (buried oxide, narrow fin):
- **Planar**: Heat dissipates through bulk silicon
- **FinFET**: Heat trapped in fin + BOX ? higher channel temperature
- Typical self-heating: +10C to +40C rise under DC bias
- Impacts: Idsat reduction, lifetime, mobility degradation

### 6.2 BSIM-CMG Self-Heating Model (SHMOD)
| SHMOD | Description |
|-------|-------------|
| 0 | No self-heating (isothermal) |
| 1 | Self-heating enabled (must define RTH0, CTH0) |
| 2 | Self-heating with transient thermal model |

### 6.3 Self-Heating Model Parameters
.MODEL NMOS_FIN nmos
+ SHMOD = 1
* Thermal resistance (K/W)
+ RTH0 = 2000      * Thermal resistance per unit length (K*m/W)
+ RTH0W = 2000     * Width scaling version
* Thermal capacitance (J/K)
+ CTH0 = 1E-12     * Thermal capacitance per unit length (J*K/m)
+ CTH0W = 1E-12    * Width scaling version

### 6.4 Self-Heating Measurement in HSPICE
* Measure junction temperature rise
.TRAN 1P 100N
.MEASURE TRAN T_JUNCTION TEMP M1_DEVNAME

* Compare DC vs pulsed current
.DC VGS 0 VDD 0.05
.MEASURE DC IDS_DC V(M1_DEVNAME)
* Pulsed measurement at 1ns (minimal self-heating)
.TRAN 1P 2N
.MEASURE TRAN IDS_PULSED FIND I(M1) AT=1.5N

* Self-heating degradation factor
.MEASURE PARAM IDS_DEGRADE PARAM='(IDS_PULSED - IDS_DC) / IDS_PULSED * 100'

### 6.5 Thermal Resistance Dependence on NFIN
* RTH per device = RTH0 / NFIN (more fins = lower thermal resistance)
* For RTH0=2000 K*m/W, L=20nm:
  - NFIN=1 ? RTH = 40,000 K/W (40K rise at 1mA)
  - NFIN=4 ? RTH = 10,000 K/W (10K rise at 1mA)

### 6.6 Mitigating Self-Heating
| Method | HSPICE Implementation | Effect |
|--------|----------------------|--------|
| Pulsed measurement | .TRAN with pulse width < 10ns | Reduces temp rise |
| Fin spacing | Model with RTH0 adjusted per layout | Thermal resistance reduction |
| Back-end metal | Not modeled in BSIM-CMG | Helps heat dissipation |
| BOX thinning | Adjust RTH0 in model card | Lower thermal resistance |

---

## 7. Back-Gate Bias (VBack)

### 7.1 Back-Gate in FinFET vs Planar
In planar bulk, the well bias (body effect) modulates Vth via:
- Vth shift = gamma * (sqrt(2*phi_f + Vsb) - sqrt(2*phi_f))

In FinFET (BSIM-CMG), back-gate bias modulates the channel through:
- **Dynamic Vth adjustment** without body effect penalty
- **Wider bias range** (back-gate can be biased opposite of main gate)
- **Lower body factor** than planar (less sensitivity but wider usable range)

### 7.2 Back-Gate Terminals in BSIM-CMG
| Terminal | Name | Bias Range | Effect |
|----------|------|------------|--------|
| B (bulk) | Back-gate / well | VSS ? bias | Vth modulation |
| SBG | Second back-gate | VSS ? bias | Dual-gate control |
| BG | Back-gate (4-terminal) | Independent bias | SOI/UTBB bias |

### 7.3 Back-Gate Bias Syntax
* 4-terminal device (D, G, S, B)
M1 D G S 0 NMOS_FIN L=20N NFIN=1

* With explicit back-gate voltage
VBG BG 0 DC='VBack'

* If subcircuit model has back-gate terminal:
M1 D G S BG NMOS_FIN L=20N NFIN=1

### 7.4 Back-Gate Bias Sweep
.PARAM VBack=0

M1 D G S 0 NMOS_FIN L=20N NFIN=1 H_FIN=40N T_FIN=8N

* Sweep back-gate bias
.DC VBack -0.5 0.5 0.05
.MEASURE DC VTH_BACK WHEN I(M1) = '1E-7 * W_eff / L' 
+ CROSS=1

* Back-gate modulation of Vth (mV/V)
.MEASURE DC DVTH_DVBack DERIV VTH_BACK

### 7.5 Back-Gate Bias Impact Summary
| VBack | Vth Shift | Use Case |
|-------|-----------|----------|
| 0V (nominal) | 0 | Standard operation |
| +0.3V | -15 to -30mV | Higher drive (lower Vth) |
| -0.3V | +15 to +30mV | Lower leakage (higher Vth) |
| +1.0V (well forward) | -50 to -100mV | Performance boost |
| -1.0V (well reverse) | +50 to +100mV | Sleep mode leakage reduction |

### 7.6 Back-Bias in FDSOI (vs Bulk FinFET)
FDSOI has more pronounced back-gate effect:
- **Forward back-bias (FBB)**: Vth reduction, higher speed
- **Reverse back-bias (RBB)**: Vth increase, lower leakage
- **Wider range**: ?3V typical (vs ?1V in bulk FinFET)

* FDSOI example
M1 D G S B NMOS_FDSOI L=20N W=100N
VBG B 0 DC='VBack'
.DC VBack -2 2 0.1

---

## 8. Layout-Dependent Effects (LDE)

### 8.1 FinFET LDE Overview
FinFET LDEs are more complex than planar due to 3D structure:

| Effect | BSIM-CMG Parameter | Description |
|--------|-------------------|-------------|
| LOD (Length of Diffusion) | SA, SB, SD | Stress from STI edge proximity |
| WPE (Well Proximity) | SC | Well implant shadowing |
| OD Width Effect | W_OD, N_OD | Active width effect on stress |
| Dummy Gate | NGC, DMCG | Poly spacing effect |
| Fin Stress | STR_* | Fin-level stress modeling |
| Metal Fill | ? | Back-end stress (proximity) |

### 8.2 LOD (Length of Diffusion) Parameters
* LOD = distance from gate edge to STI on each side
.PARAM SA=150N     * Distance from gate to STI on source side
.PARAM SB=150N     * Distance from gate to STI on drain side
.PARAM SD=200N     * Distance between gates (multi-finger)

M1 D G S 0 NMOS_FIN L=20N NFIN=1 SA='SA' SB='SB' SD='SD'

* SA < 200nm ? compressive stress ? lower NFET Vth, higher PFET Vth
* SA >> 500nm ? stress negligible ? standard Vth

### 8.3 WPE (Well Proximity Effect)
* SC = distance from active to well edge
.PARAM SC=0.5U     * Well edge distance
M1 D G S 0 NMOS_FIN L=20N NFIN=1 SC='SC'

* SC < 1um ? threshold shift (higher Vth near well edge)
* SC > 2um ? WPE negligible

### 8.4 Oxide Definition (OD) Width Effect
* FinFET Vth depends on N_OD (number of OD squares)
.PARAM N_OD=1      * OD width in squares
M1 D G S 0 NMOS_FIN L=20N NFIN=1 N_OD='N_OD'

* W_OD affects strain ? Vth modulation
* W_OD < 200nm ? stronger stress ? Vth drops
* W_OD >> 1um ? bulk-like ? relaxed stress

### 8.5 LDE-Aware Corner Selection
* LDE effects must be included in corner modeling:
* Typical LDE variations change Idsat by ?5-15%
* Worst-case LDE corners are often separate from process corners

.ALTER case=worst_LDE
    .PARAM SA=50N SB=50N     * Dense layout, high stress
    .PARAM SC=0.3U
    .PARAM N_OD=1

.ALTER case=best_LDE
    .PARAM SA=1U SB=1U      * Isolated, relaxed stress
    .PARAM SC=2U
    .PARAM N_OD=100

---

## 9. FinFET SRAM-Specific Considerations

### 9.1 FinFET SRAM Bitcell Ratios
In FinFET, SRAM cell ratios are expressed in NFIN (not W):
* Planar: beta = W_PD/W_PG, gamma = W_PU/W_PG
* FinFET: beta = NFIN_PD / NFIN_PG, gamma = NFIN_PU / NFIN_PG

### 9.2 Common FinFET SRAM Bitcell Configurations
| Node | Cell Name | PU | PD | PG | beta | gamma | Use Case |
|------|-----------|----|----|----|------|-------|----------|
| 14nm | 0.120um? | 1 | 3 | 1 | 3.0 | 0.33 | High speed |
| 7nm | 0.039um? | 1 | 2 | 1 | 2.0 | 0.50 | Balanced HDC |
| 7nm | 0.031um? | 1 | 3 | 1 | 3.0 | 0.33 | High density |
| 5nm | 0.021um? | 1 | 2 | 1 | 2.0 | 0.50 | HD SRAM |
| 3nm | ~0.018um? | 1 | 2 | 1 | 2.0 | 0.50 | HD (buried rail) |

### 9.3 FinFET SRAM Netlist Example (1-1-2 for 7nm)
* 1-1-2 = PU:PG:PD = 1 fin : 1 fin : 2 fins
* Note: PFET (PU) = NFIN=1, NFET pass-gate (PG) = NFIN=1, NFET pull-down (PD) = NFIN=2

.SUBCKT SRAM_CELL6 VVDD VVDD2 BL BLB WL VDD VSS
* Pull-up (PMOS)
MPU1 VVDD VVDD2 VDD VDD PMOS_FIN L=20N NFIN=1 H_FIN=40N T_FIN=8N
MPU2 VVDD2 VVDD VDD VDD PMOS_FIN L=20N NFIN=1 H_FIN=40N T_FIN=8N

* Pull-down (NMOS)
MPD1 VVDD VVDD2 VSS VSS NMOS_FIN L=20N NFIN=2 H_FIN=40N T_FIN=8N
MPD2 VVDD2 VVDD VSS VSS NMOS_FIN L=20N NFIN=2 H_FIN=40N T_FIN=8N

* Pass-gate (NMOS)
MPG1 BL WL VVDD VSS NMOS_FIN L=20N NFIN=1 H_FIN=40N T_FIN=8N
MPG2 BLB WL VVDD2 VSS NMOS_FIN L=20N NFIN=1 H_FIN=40N T_FIN=8N
.ENDS SRAM_CELL6

### 9.4 FinFET Read Current (Iread)
* Iread per fin = 5-10 uA for 7nm NMOS at VDD=0.7V
* Total Iread = NFIN_PG * Iread_per_fin
* For 1-1-2 cell: Iread ? 5-10 uA (single pass-gate fin)

.MEASURE TRAN IREAD_CELL AVG I(MPG1) FROM='TWLRISE+5P' TO='TWLRISE+50P'

### 9.5 FinFET Write Margin Issues
* beta ratio in FinFET may be lower than planar:
  - Planar: beta = 2.0 ~ 3.0
  - FinFET: beta = 2.0 (with PD=2, PG=1)
* Lower beta ? easier write but less read stability
* Write margin must be verified at each NFIN ratio

### 9.6 FinFET SRAM Vmin
* Vmin dominated by:
  1. WL overdrive requirement (write margin)
  2. Read SNM degradation at low VDD
  3. Local mismatch (fin height variation, RDF)
* 7nm FinFET SRAM Vmin ? 0.55V - 0.70V

### 9.7 FinFET Back-Bias for SRAM Assist
* WL boost with back-bias (positive well bias reduces Vth of pass-gate)
* BL negative bias for write assist (common in FinFET SRAM)
* Read assist via VDD drop or negative WL

---

## 10. Process Corners for FinFET Nodes

### 10.1 FinFET Corner Strategies
FinFET corners differ from planar due to discrete fin quantization:

| Corner | Description | Key Parameter Changes |
|--------|-------------|----------------------|
| TT | Typical NMOS & PMOS | Nominal VTH0, U0, RDSW |
| SS | Slow NMOS & PMOS | +VTH0, -U0, +RDSW |
| FF | Fast NMOS & PMOS | -VTH0, +U0, -RDSW |
| SF | Slow NMOS, Fast PMOS | NMOS weak, PMOS strong |
| FS | Fast NMOS, Slow PMOS | NMOS strong, PMOS weak |

### 10.2 FinFET-Specific Corner Parameters
* In FinFET, corners must also vary:
  - H_FIN: Fin height variation (?2-5% across process)
  - T_FIN: Fin thickness variation (?3-6%)
  - RTH0: Thermal resistance (depends on H_FIN)
  - L_gate: Gate CD variation (?1-2nm)

### 10.3 FinFET Corner Library Example
* File: finfet_corners.lib
.LIB TT
    .PARAM VTH0_N=0.30
    .PARAM VTH0_P=0.28
    .PARAM U0_N=0.020
    .PARAM U0_P=0.008
    .PARAM H_FIN=40N
    .PARAM T_FIN=8N
    .PARAM RDSW_N=200
    .PARAM RDSW_P=250
.ENDL TT

.LIB SS
    .PARAM VTH0_N=0.35   +50mV
    .PARAM VTH0_P=0.33   +50mV
    .PARAM U0_N=0.016    -20%
    .PARAM U0_P=0.0064   -20%
    .PARAM H_FIN=38N     -5%
    .PARAM T_FIN=8.4N    +5%
    .PARAM RDSW_N=260    +30%
    .PARAM RDSW_P=325    +30%
.ENDL SS

.LIB FF
    .PARAM VTH0_N=0.25   -50mV
    .PARAM VTH0_P=0.23   -50mV
    .PARAM U0_N=0.024    +20%
    .PARAM U0_P=0.0096   +20%
    .PARAM H_FIN=42N     +5%
    .PARAM T_FIN=7.6N    -5%
    .PARAM RDSW_N=140    -30%
    .PARAM RDSW_P=175    -30%
.ENDL FF

### 10.4 Corner Application to .MODEL
* Use .LIB to select corner, then .PARAM applies to .MODEL
.LIB finfet_corners.lib TT

.MODEL NMOS_FIN nmos
+ LEVEL=74
+ VTH0='VTH0_N'
+ U0='U0_N'
+ RDSW='RDSW_N'
+ H_FIN='H_FIN'
+ T_FIN='T_FIN'

### 10.5 Global vs Local Variation in FinFET
* Global (die-to-die): Gate CD, fin height, oxide thickness
* Random (within-die): RDF (random dopant fluctuation), MGG (metal gate granularity), FER (fin edge roughness)

* For Monte Carlo:
* RDF in FinFET is significant due to discrete channel doping
* MGG (workfunction variation) dominant at advanced nodes
* Fin CD variation (fin width, fin height) adds to mismatch

### 10.6 FinFET Mismatch Parameters
* BSIM-CMG mismatch support:
.MODEL NMOS_FIN nmos
+ ACM = 12             * Area calculation method for matching
+ ACM_GEOMOD = 2       * FinFET geometry matching

* Pelgrom coefficient for FinFET (AYY parameter)
+ AVTH0 = 2E-3 * 1U   * Vth mismatch coefficient (V*um)
+ AU0   = 2           * Mobility mismatch (%)

* In FinFET, AVTH0 ~ 1.5-2.5 mV*um (similar to planar but per-fin)
* Total mismatch for NFIN fin device:
  sigma_Vth = AVTH0 / sqrt(2 * NFIN * H_FIN * L)

---

## 11. Temperature Inversion in FinFET

### 11.1 Temperature Inversion Phenomenon
In bulk planar: delay always increases with temperature (higher T = slower).

In FinFET: **temperature inversion** occurs at low VDD:
- Below ~0.7V (node-dependent), delay DECREASES as temperature increases
- This is critical for timing corners ? worst-case delay may be at -40C, not 125C!

### 11.2 Cause of Temperature Inversion
1. **Mobility**: ? ? T^(-1.5) ?  decreases with temperature (slower)
2. **Vth**: Vth ? -T ? decreases with temperature (faster)

At high VDD (VGS >> Vth), mobility dominates ? hotter = slower
At low VDD (VGS ? Vth), Vth drop dominates ? hotter = faster

### 11.3 Inversion Voltage (VINV)
VINV = the VDD where delay is temperature-independent.

Typical FinFET VINV ? 0.55-0.70V (process dependent)
- Above VINV: conventional corner (SS_125C = worst)
- Below VINV: inverted corner (SS_m40C = worst)

### 11.4 HSPICE Temperature Inversion Check
* Measure delay at both hot and cold for each VDD
.ALTER case=hot_highV
    .TEMP 125
    .PARAM VDD=0.80

.ALTER case=cold_highV
    .TEMP -40
    .PARAM VDD=0.80

.ALTER case=hot_lowV
    .TEMP 125
    .PARAM VDD=0.55

.ALTER case=cold_lowV
    .TEMP -40
    .PARAM VDD=0.55

* Ratio indicates inversion
.MEASURE TRAN TDELAY_PARAM PARAM='TDELAY'
* If TDELAY(cold) > TDELAY(hot) at lowV ? inversion active

### 11.5 Practical Impact on Timing Corners
| VDD region | Slow Corner | Fast Corner |
|------------|-------------|-------------|
| High VDD (> VINV) | SS, 125C, low VDD | FF, -40C, high VDD |
| Low VDD (< VINV) | SS, -40C, low VDD | FF, 125C, high VDD |

* Always sweep both hot and cold at the target VDD to find actual worst case
* Temp inversion is strongest at near-threshold (VDD ? Vth)

---

## 12. Complete FinFET Characterization Workbench

### 12.1 FinFET UT Characterization (NFIN-Aware)
* File: finfet_ut_char.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* === PARAMETERS ===
.PARAM VDD=0.75
.PARAM L_DRAW=20N
.PARAM H_FIN=40N
.PARAM T_FIN=8N
.PARAM NFIN=1
.PARAM W_eff='NFIN * (2 * H_FIN + T_FIN)'

* === DEVICE ===
M1 D G S 0 NMOS_FIN L='L_DRAW' NFIN='NFIN' \
    H_FIN='H_FIN' T_FIN='T_FIN'

* === BIAS ===
VD D 0 DC='VDD'
VG G 0 DC='VDD'
VS S 0 DC=0
VB B 0 DC=0

* === DC ANALYSIS ===
.DC VG 0 'VDD' 0.005

* === THRESHOLD VOLTAGE: CONSTANT-CURRENT ===
.MEASURE DC VTSAT_CC WHEN I(M1)='1E-7 * W_eff / L_DRAW' CROSS=1

* === THRESHOLD VOLTAGE: MAX-GM ===
.MEASURE DC GMMAX DERIV OF I(M1) AT=VGS
.MEASURE DC VTSAT_MAXGM WHEN DERIV(I(M1))='GMMAX * 0.5' CROSS=1

* === SATURATION CURRENT ===
.MEASURE DC IDSAT FIND I(M1) AT VGS='VDD'

* === LEAKAGE CURRENT ===
.MEASURE DC ISOFF FIND I(M1) AT VGS=0

* === TRANSCONDUCTANCE ===
.MEASURE DC GM_MAX MAX DERIV(I(M1))

* === DRAIN CONDUCTANCE ===
.ALTER case=output_char
    .DC VD 0 'VDD' 0.01
    .MEASURE DC GDS_AT_VDD DERIV I(M1)

* === NFIN SWEEP ===
.ALTER case=NFIN2
    .PARAM NFIN=2
.ALTER case=NFIN4
    .PARAM NFIN=4

* === SELF-HEATING COMPARISON ===
.ALTER case=self_heat_comparison
    * Use pulsed bias to compare
    .TRAN 1P 10N
    VG G 0 PULSE(0 'VDD' 0 1P 1P '1N' '10N')
    .MEASURE TRAN IDSAT_PULSED FIND I(M1) AT=5N

### 12.2 FinFET SRAM Workbench
* File: finfet_sram_char.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=6 MEASOUT=1
.TEMP 25

* === PARAMETERS ===
.PARAM VDD=0.75
.PARAM NFIN_PU=1
.PARAM NFIN_PG=1
.PARAM NFIN_PD=2
.PARAM L_CELL=20N
.PARAM H_FIN=40N T_FIN=8N

* === SUPPLIES ===
VDD_S VDD 0 DC='VDD'
WL_S WL 0 PULSE(0 'VDD' 0 20P 20P 200P 1N)

* === 6T SRAM ===
* Pull-up (PMOS)
MPU1 VVDD VVDD2 VDD VDD PMOS_FIN L='L_CELL' NFIN='NFIN_PU'
MPU2 VVDD2 VVDD VDD VDD PMOS_FIN L='L_CELL' NFIN='NFIN_PU'
* Pull-down (NMOS)
MPD1 VVDD VVDD2 0 0 NMOS_FIN L='L_CELL' NFIN='NFIN_PD'
MPD2 VVDD2 VVDD 0 0 NMOS_FIN L='L_CELL' NFIN='NFIN_PD'
* Pass-gate (NMOS)
MPG1 BL WL VVDD 0 NMOS_FIN L='L_CELL' NFIN='NFIN_PG'
MPG2 BLB WL VVDD2 0 NMOS_FIN L='L_CELL' NFIN='NFIN_PG'

* === BITLINE PRECHARGE ===
BL_S BL 0 DC='VDD'
BLB_S BLB 0 DC='VDD'
CBL BL 0 20F
CBLB BLB 0 20F

.TRAN 0.5P 1N

* === READ TIMING ===
.MEASURE TRAN TREAD
+ TRIG V(WL) VAL='VDD*0.5' RISE=1
+ TARG V(BL) VAL='VDD*0.9' FALL=1

* === READ CURRENT PER FIN ===
.MEASURE TRAN IREAD_AVG AVG I(MPG1) FROM='100P' TO='200P'
.MEASURE TRAN IREAD_PER_FIN PARAM='IREAD_AVG / NFIN_PG'

* === NFIN RATIO SWEEP ===
.ALTER case=pu1_pg1_pd2
    .PARAM NFIN_PU=1 NFIN_PG=1 NFIN_PD=2

.ALTER case=pu1_pg1_pd3
    .PARAM NFIN_PU=1 NFIN_PG=1 NFIN_PD=3

.ALTER case=pu2_pg1_pd2
    .PARAM NFIN_PU=2 NFIN_PG=1 NFIN_PD=2

### 12.3 FinFET Ring Oscillator (NFIN-Based)
* File: finfet_ro.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1

.PARAM VDD=0.75
.PARAM NFIN=2
.PARAM H_FIN=40N T_FIN=8N

* 31-stage RO
.SUBCKT FIN_INV IN OUT VDD VSS
MP OUT IN VDD VDD PMOS_FIN L=20N NFIN='NFIN' H_FIN='H_FIN' T_FIN='T_FIN'
MN OUT IN VSS VSS NMOS_FIN L=20N NFIN='NFIN' H_FIN='H_FIN' T_FIN='T_FIN'
.ENDS FIN_INV

.IC V(IN1)=VDD

XINV1 IN1 IN2 VDD VSS FIN_INV
XINV2 IN2 IN3 VDD VSS FIN_INV
...
XINV31 IN31 IN1 VDD VSS FIN_INV

.TRAN 0.1P 5N UIC

.MEASURE TRAN TRO_PERIOD
+ TRIG V(IN1) VAL='VDD*0.5' RISE=3
+ TARG V(IN1) VAL='VDD*0.5' RISE=4

.MEASURE TRAN TRO_FREQ PARAM='1/TRO_PERIOD'
.MEASURE TRAN TRO_STAGE PARAM='TRO_PERIOD / (2 * 31)'

* === NFIN vs FREQUENCY ===
.ALTER case=NFIN1
    .PARAM NFIN=1
.ALTER case=NFIN4
    .PARAM NFIN=4

---

## 13. Quick Reference

### 13.1 BSIM-CMG Parameter Quick Reference
| Parameter | Description | Typical Value (7nm N) |
|-----------|-------------|----------------------|
| LEVEL | Model level selector | 74 |
| VERSION | BSIM-CMG version | 110 |
| GEOMOD | Geometry model (2=FinFET) | 2 |
| SHMOD | Self-heating (0=off, 1=on) | 1 |
| RDSMOD | External resistance (1=on) | 1 |
| CAPMOD | Capacitance model (2=rec) | 2 |
| MOBMOD | Mobility model | 1 |
| COREMOD | Core model | 1 |
| VTH0 | Long-channel Vth | 0.30 V |
| U0 | Low-field mobility | 0.020 m?/Vs |
| RDSW | Source/drain sheet R | 200 ohm-um |
| RTH0 | Thermal resistance coeff | 2000 K*m/W |
| CTH0 | Thermal capacitance coeff | 1E-12 J*K/m |
| AVTH0 | Vth mismatch coefficient | 2 mV*um |

### 13.2 FinFET to Planar Parameter Mapping
| Planar (BSIM4) | FinFET (BSIM-CMG) | Comment |
|----------------|-------------------|---------|
| W (continuous) | NFIN (integer) | Quantized width |
| L | L (same) | Channel length |
| M (multiplier) | M (multiplier) | Same concept |
| TOXE | TOXE (same) | Oxide thickness |
| VTH0 | VTH0 (same) | Threshold voltage |
| U0 | U0 (same) | Mobility |
| RDSW | RDSW (same) | S/D resistance |
| XJ | H_FIN | Fin height replaces junction depth |
| GAMMA | Not directly used | Back-gate model, different equation |
| ACM | ACM+GEOMOD | Area calculation for matching |

### 13.3 Common FinFET HSPICE Errors
| Error | Cause | Fix |
|-------|-------|-----|
| NFIN must be integer | NFIN set to non-integer | Use integer (1, 2, 3...) |
| GEOMOD 2 requires H_FIN | GEOMOD=2 but H_FIN missing | Specify H_FIN in .MODEL or instance |
| SHMOD=1 requires RTH0 | Self-heating enabled, no RTH0 | Add RTH0, CTH0 to .MODEL |
| Negative RTH0 not allowed | RTH0 negative or zero | RTH0 > 0 |
| CAPMOD 2 mismatch | CAPMOD=2 but ACT/QM mismatch | Set CAPMOD=1 if QM parameters missing |
| Device not converging | Self-heating thermal RC oscillation | Reduce RTH0 or increase CTH0 |

> **Revision History**
> - 2026-06-30: Initial version. BSIM-CMG, NFIN quantization, R_ext, self-heating, back-bias, LDE, FinFET SRAM, temperature inversion.
