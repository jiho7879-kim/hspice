---
title: 'HSPICE Model and PDK Integration Guide'
subtitle: 'BSIM4/BSIM-CMG Parameters, Process Skew Libraries, Temperature Inversion, Model Selection Strategy'
version: '1.0'
date: '2026-06-30'
description: 'Comprehensive HSPICE guide for PDK/model integration in SRAM and transistor-level design. Covers BSIM4 (LEVEL 49/54) and BSIM-CMG (LEVEL 72/73/74) model hierarchies, process corner library structure (.lib), temperature inversion modeling, model selection strategy for different simulation types, PVT binning, and Monte Carlo model setup.'
tags: [HSPICE, PDK, BSIM4, BSIM-CMG, model, process corner, temperature inversion, .LIB, Monte Carlo]
language: 'HSPICE'
keywords: [PDK integration, BSIM4, BSIM-CMG, process corner, .LIB, skew library, temperature inversion, model card, PVT, Monte Carlo]
---

# HSPICE Model and PDK Integration Guide

> **Purpose**: HSPICE model/PDK integration for SRAM and transistor-level circuit simulation.
> **Coverage**: BSIM4 and BSIM-CMG model hierarchy, process corner library structure (.LIB), temperature inversion, model selection strategy, PVT binning, Monte Carlo model setup, PDK file organization.
> **Target**: Engineers integrating foundry PDK models into HSPICE for memory characterization.

---

## Table of Contents

1. [PDK File Structure Overview](#1-pdk-file-structure-overview)
2. [BSIM4 Model (LEVEL 49/54)](#2-bsim4-model-level-4954)
3. [BSIM-CMG Model (LEVEL 72/73/74)](#3-bsim-cmg-model-level-727374)
4. [Process Corner Libraries (.LIB)](#4-process-corner-libraries-lib)
5. [Temperature Inversion Modeling](#5-temperature-inversion-modeling)
6. [Model Selection by Simulation Type](#6-model-selection-by-simulation-type)
7. [PVT Binning and Corners](#7-pvt-binning-and-corners)
8. [Monte Carlo Model Setup](#8-monte-carlo-model-setup)
9. ['Device' Model Parameters for SRAM](#9-device-model-parameters-for-sram)
10. [Model Debugging and Validation](#10-model-debugging-and-validation)
11. [Complete PDK Integration Workbench](#11-complete-pdk-integration-workbench)
12. [References](#12-references)

---

## 1. PDK File Structure Overview

### 1.1 Typical Foundry PDK Directory Layout
`
pdk_root/
  models/
    hspice/
      nmos/
        nmos_tt.pm          * TT (typical) NMOS model card
        nmos_ss.pm          * SS (slow) NMOS model card
        nmos_ff.pm          * FF (fast) NMOS model card
        nmos_sf.pm          * SF NMOS model card
        nmos_fs.pm          * FS NMOS model card
      pmos/
        pmos_tt.pm
        pmos_ss.pm
        pmos_ff.pm
        pmos_sf.pm
        pmos_fs.pm
      res/
        res_tt.pm           * Resistor model
      cap/
        cap_tt.pm           * Capacitor model
      bjt/
        bjt_tt.pm           * BJT model
    corners.lib              * Corner definitions (references to .pm files)
    mc_params.lib            * Monte Carlo parameter definitions
    sram_cell.lib            * SRAM bitcell subcircuits
    design_rule_check.sp     * PDK-specific simulation setup
`

### 1.2 Corner Library File (corners.lib)
* This is the master file that HSPICE sources to select process corner:
.LIB TT
    .LIB 'models/hspice/nmos/nmos_tt.pm' TT
    .LIB 'models/hspice/pmos/pmos_tt.pm' TT
    .LIB 'models/hspice/res/res_tt.pm' TT
    .PARAM VTH0_NOM_N=0.30
    .PARAM VTH0_NOM_P=0.28
.ENDL TT

.LIB SS
    .LIB 'models/hspice/nmos/nmos_ss.pm' SS
    .LIB 'models/hspice/pmos/pmos_ss.pm' SS
    .PARAM VTH0_NOM_N=0.35
    .PARAM VTH0_NOM_P=0.33
.ENDL SS

* Usage in netlist:
.LIB './corners.lib' TT

---

## 2. BSIM4 Model (LEVEL 49/54)

### 2.1 BSIM4 Model Levels
| LEVEL | Description | Use Case |
|-------|-------------|----------|
| 49 | BSIM3v3 | Legacy, replaced by BSIM4 |
| 54 | BSIM4.6+ | Planar CMOS 180nm-28nm (STANDARD) |
| 69 | BSIM4.8+ | Enhanced BSIM4 for RF/analog |

### 2.2 BSIM4 .MODEL Card Structure
.MODEL NMOS_SRAM nmos
+ LEVEL   = 54
+ VERSION = 4.8
+ MOBMOD  = 1              * Mobility model (0=old, 1=new)
+ CAPMOD  = 2              * Capacitance model (2=charge-thickness)
+ NOIMOD  = 3              * Noise model (3=channel noise + flicker)
+ RDSMOD  = 1              * External resistance model

### 2.3 BSIM4 Critical Parameters for SRAM
* --- DC Parameters ---
+ VTH0   = 0.30            * Long-channel threshold voltage (V)
+ K1     = 0.35            * 1st body-bias coefficient
+ K2     = 0.05            * 2nd body-bias coefficient
+ DVT0   = 2.2             * Short-channel Vth sensitivity
+ DVT1   = 0.53            * Short-channel Vth roll-off
+ DVT2   = -0.032          * Drain-induced Vth shift
+ ETA0   = 0.2             * DIBL coefficient
+ SUBTHM = 0.02            * Subthreshold swing coefficient

* --- Mobility ---
+ U0     = 0.02            * Low-field mobility (m?/Vs)
+ UA     = 1E-15           * Mobility degradation (vertical field)
+ UB     = 1E-16           * Mobility degradation (velocity saturation)
+ UC     = -3E-11          * Mobility degradation (body bias)

* --- S/D Resistance ---
+ RDSW   = 200             * Rds per width at high Vgs (ohm-um)
+ RDSWMIN = 100            * Minimum Rds

* --- Velocity Saturation ---
+ VSAT   = 1E5             * Saturation velocity (m/s)

* --- Leakage ---
+ VOFF   = -0.08           * Subthreshold offset voltage
+ NFACTOR = 1.5            * Subthreshold swing factor
+ CDSC   = 2E-3            * Drain/Source to channel coupling

* --- Capacitance ---
+ CGSO   = 1E-10           * Gate-source overlap (F/m)
+ CGDO   = 1E-10           * Gate-drain overlap (F/m)
+ CGBO   = 1E-11           * Gate-bulk overlap (F/m)
+ CGSL   = 1E-10           * Gate-source fringing
+ CGDL   = 1E-10           * Gate-drain fringing
+ XPART  = 0.5             * Charge partitioning (0=40/60, 0.5=50/50, 1=0/100)

### 2.4 BSIM4 Instance Parameters
M1 D G S B NMOS_SRAM W={W} L={L} M={M} AS={AS} AD={AD} PS={PS} PD={PD}
+ SA={SA} SB={SB} SC={SC}       * LDE parameters (Layout-Dependent Effects)

| Instance Param | Description | SRAM Typical |
|---------------|-------------|-------------|
| W | Channel width (m) | 120-200nm |
| L | Channel length (m) | 30nm |
| M | Multiplier (parallel devices) | 1-4 |
| AS/AD | Source/drain area (m?) | W * diffusion length |
| PS/PD | Source/drain perimeter (m) | 2*(W + diffusion) |
| SA/SB | Length of diffusion (LOD) | 100-500nm |
| SC | Well proximity distance | 0.5-2um |

### 2.5 BSIM4 Temperature Parameters
.MODEL NMOS_SRAM nmos
+ TNOM   = 25              * Nominal temperature (C)
+ AT     = 5.5E-5          * Vth temperature coefficient (V/C)
+ UTE    = -1.5            * Mobility temperature exponent
+ KT1    = -0.11           * Vth temperature effect (V/C)
+ KT1L   = 0               * Vth temperature with L
+ KT2    = 0.022           * Body-bias temperature coefficient

---

## 3. BSIM-CMG Model (LEVEL 72/73/74)

### 3.1 FinFET Model Levels
| LEVEL | Version | Use Case |
|-------|---------|----------|
| 72 | BSIM-CMG v1.0 | Legacy FinFET (14nm baseline) |
| 73 | BSIM-CMG v2.0 | Enhanced Rds, GIDL (7nm LP) |
| 74 | BSIM-CMG v3.0 | Self-heating, AC noise (7nm+ mainstream) |

### 3.2 BSIM-CMG .MODEL Card (FinFET)
.MODEL NMOS_FIN nmos
+ LEVEL   = 74
+ VERSION = 110
+ GEOMOD  = 2              * FinFET geometry (2=standard, 3=GAA)
+ MOBMOD  = 1              * Mobility model
+ RDSMOD  = 1              * External resistance (1=on)
+ SHMOD   = 1              * Self-heating (1=on, 0=off)
+ CAPMOD  = 2              * Charge-based capacitance
+ COREMOD = 1              * Core model (1=charge-based)

* --- Geometry ---
+ H_FIN   = 40N            * Fin height (m) ? instance override possible
+ T_FIN   = 8N             * Fin thickness (m) ? instance override possible
+ T_GATE  = L_DRAW         * Gate length (same as L)

* --- Threshold ---
+ VTH0    = 0.30           * Long-channel Vth (V)
+ PHIG    = 4.5            * Gate workfunction (eV)
+ EPSROX  = 3.9            * Oxide dielectric constant
+ TOXE    = 1.2N           * Electrical oxide thickness (m)

* --- Mobility & Velocity ---
+ U0      = 0.02           * Low-field mobility (m?/Vs)
+ VSAT    = 1.2E5          * Saturation velocity (m/s)

* --- DIBL and SCE ---
+ ETA0    = 0.15           * DIBL coefficient (V/V)
+ CDSC    = 2E-3           * Drain-source to channel coupling
+ DVT0    = 2.0            * Short-channel Vth coefficient

### 3.3 BSIM-CMG vs BSIM4 Key Differences
| Aspect | BSIM4 (Planar) | BSIM-CMG (FinFET) | Impact |
|--------|---------------|--------------------|--------|
| Width | W (continuous) | NFIN (integer) | Quantized sizing |
| Body effect | Gamma (K1, K2) | Back-gate model | Different bias schemes |
| Self-heating | RTH0 optional | SHMOD essential | Higher junction temp |
| Fringe cap | CGSL/CGDL | CF/CFS/CFD | More complex AC model |
| Geometry | W, L, M | NFIN, H_FIN, T_FIN | Fin height/thickness |
| Matching | ACM, AYTH0 | ACM+GEOMOD, AVTH0 | Per-fin matching |

### 3.4 Instance Override for BSIM-CMG
* Key parameters can be set at instance level (overrides .MODEL default):
M1 D G S 0 NMOS_FIN L=20N NFIN=2 H_FIN=40N T_FIN=8N T_GATE=20N

### 3.5 Setting NFIN at Instance vs Model
* Option A: NFIN in .MODEL (fixed value used by all instances)
.MODEL NMOS_FIN nmos LEVEL=74 NFIN=1 ...
* Option B: NFIN at instance (overridable per device ? RECOMMENDED)
M1 D G S 0 NMOS_FIN L=20N NFIN=1
M2 D G S 0 NMOS_FIN L=20N NFIN=4

---

## 4. Process Corner Libraries (.LIB)

### 4.1 Corner Library Organization
* Recommended structure for SRAM characterization:

* File: sram_corners.lib
* --- NOMINAL ---
.LIB NOM
    .PARAM SUPPLY=0.80
    .PARAM TEMP_CELL=25
    .LIB 'nmos_tt.pm' TT
    .LIB 'pmos_tt.pm' TT
.ENDL NOM

* --- SS (Slow NMOS, Slow PMOS) ---
.LIB SS
    .PARAM SUPPLY=0.72       * -10%
    .PARAM TEMP_CELL=125
    .LIB 'nmos_ss.pm' SS
    .LIB 'pmos_ss.pm' SS
.ENDL SS

* --- FF (Fast NMOS, Fast PMOS) ---
.LIB FF
    .PARAM SUPPLY=0.88       * +10%
    .PARAM TEMP_CELL=-40
    .LIB 'nmos_ff.pm' FF
    .LIB 'pmos_ff.pm' FF
.ENDL FF

* --- SF (Slow NMOS, Fast PMOS) ---
.LIB SF
    .LIB 'nmos_ss.pm' SS
    .LIB 'pmos_ff.pm' FF
.ENDL SF

* --- FS (Fast NMOS, Slow PMOS) ---
.LIB FS
    .LIB 'nmos_ff.pm' FF
    .LIB 'pmos_ss.pm' SS
.ENDL FS

### 4.2 Corner Selection in Netlist
* Select corner at top level:
.LIB 'sram_corners.lib' SS
.TEMP {TEMP_CELL}
.PARAM VDD={SUPPLY}

* With .ALTER for multi-corner:
.ALTER case=TT
    .LIB 'sram_corners.lib' NOM
.ALTER case=SS
    .LIB 'sram_corners.lib' SS
.ALTER case=FF
    .LIB 'sram_corners.lib' FF

### 4.3 Temperature-Corner Coupling
* Each corner should define its own temperature:
| Corner | Temperature | Rationale |
|--------|-------------|-----------|
| NOM/TT | 25C | Standard |
| SS | 125C | Slow NMOS/PMOS + hot = worst speed |
| FF | -40C | Fast NMOS/PMOS + cold = best speed |
| SSG | 125C | Worst leakage (SS + hot) |
| FFG | -40C | Best speed (FF + cold) |

* Temperature inversion note: for VDD < 0.65V (FinFET), worst delay may be at -40C even for SS corner. Always check both hot and cold.

### 4.4 Including Monte Carlo Parameters in .LIB
.LIB MC
    .PARAM DELVTH_N='AGAUSS(0, 0.015, 1, 1)'
    .PARAM DELU0_N='AGAUSS(0, 0.02, 2, 1)'
    .PARAM DELVTH_P='AGAUSS(0, 0.015, 3, 1)'
    .PARAM DELU0_P='AGAUSS(0, 0.02, 4, 1)'
.ENDL MC

### 4.5 LIB Nesting Best Practices
* MAX DEPTH: HSPICE supports nested .LIB up to ~5 levels
* Keep it flat for readability:
  - Top-level netlist ? selects corner
  - Corner .lib ? selects model card files + parameters
  - Model card .pm ? one .MODEL card per file

### 4.6 Using .INC vs .LIB for Models
| Directive | Use Case |
|-----------|----------|
| .LIB | For corner/parameter selection (conditional inclusion) |
| .INC | For always-include content (subcircuit definitions, common settings) |

* .LIB is the standard for PDK integration ? use it for all model cards
* .INC for subcircuit definitions only (.SUBCKT)

---

## 5. Temperature Inversion Modeling

### 5.1 Temperature Inversion in BSIM4
* BSIM4 models temperature effects via:
* Vth: VTH(T) = VTH(TNOM) + KT1*(T/TNOM - 1) + KT2*(Vbs/TNOM)
* Mobility: ?(T) = ?(TNOM) * (T/TNOM)^UTE (UTE ~ -1.5)
* VSAT: VSAT(T) = VSAT(TNOM) * (1 + AT*(T - TNOM))

### 5.2 Temperature Inversion Check in BSIM4
* Inversion occurs when VDD < ~0.7V (planar) or VDD < ~0.65V (FinFET)
* Due to Vth drop dominating mobility degradation at low VDD

* HSPICE check across temperature and VDD:
.DC TEMP -40 125 10 SWEEP VDD 0.5 0.9 0.05
.MEASURE DC IDSAT_TEMP I(M1)
* If IDSAT decreases with temperature ? normal region (VDD > VINV)
* If IDSAT increases with temperature ? inversion region (VDD < VINV)

### 5.3 Modeling Temperature Inversion for Corners
* Critical: worst-case corner depends on VDD region
* High VDD (> VINV): SS + 125C is worst (conventional)
* Low VDD (< VINV): SS + -40C may be worst (inverted)

* Define both for each corner:
.LIB SS_HOT
    .LIB 'nmos_ss.pm' SS
    .PARAM TEMP_CELL=125
.ENDL SS_HOT

.LIB SS_COLD
    .LIB 'nmos_ss.pm' SS
    .PARAM TEMP_CELL=-40
.ENDL SS_COLD

### 5.4 Temperature Coefficient Extraction
* Measure dVth/dT for your model:
.TEMP {TEMP_VAL}
.DC TEMP_VAL -40 125 10
.MEASURE DC VTHAT TEMP I(M1) WHEN I(M1)=1E-7*W/L CROSS=1
.MEASURE PARAM DVTH_DT DERIV VTHAT
* Typical: -0.3 to -0.5 mV/C for NMOS, -0.4 to -0.6 mV/C for PMOS

---

## 6. Model Selection by Simulation Type

### 6.1 Model Complexity vs Accuracy Trade-off
| Simulation Type | Model Required | Complexity | Reason |
|----------------|---------------|------------|--------|
| DC operating point | Full BSIM4/CMG | Full | Must model all DC effects |
| DC sweep | Full BSIM4/CMG | Full | Sweep through regions |
| Transient digital | Full + parasitics | Full | C-V accuracy for edges |
| Transient analog | Full + noise | Full + noise | Small-signal accuracy |
| .AC small-signal | Full + capacitance | Full | Poles/zeros depend on C-V |
| .NOISE | Full + noise model | Full + noise | Flicker, thermal models |
| Monte Carlo | Full + mismatch | Full + GAUSS | Random variation |

### 6.2 Model Reduction Options
* HSPICE provides simplified models for faster simulation:
* While full model should always be used for final verification:

| Option | Effect | Speed Gain | Accuracy Cost |
|--------|--------|------------|---------------|
| RUNLVL=3 | Relax tolerances | 2x | ~5% Idsat error |
| .OPTIONS BYPASS=1 | Bypass device model calc | 3x | ~10% error |
| NOIMOD=0 | Disable noise model | 1.2x | No noise (AC only) |
| CAPMOD=0 | Simple C-V | 1.5x | ~20% cap error |

* WARNING: Never use model reduction for final characterization.

### 6.3 Model Selection Flowchart
`
Simulation Type?
?? DC/Transient characterization ? Full BSIM4/CMG, RUNLVL=4-6
?? .AC small-signal ? Full + CAPMOD=2, NOIMOD=1
?? .NOISE ? Full + NOIMOD=3, flicker parameters
?? Monte Carlo ? Full + .PARAM GAUSS/AGAUSS
?? Initial feasibility ? RUNLVL=3, METHOD=TRAP, quick check
?? Final sign-off ? RUNLVL=5-6, METHOD=GEAR, tight tolerances
`

### 6.4 Model File Isolation
* For debugging: isolate models into minimal test deck:
* File: model_sanity_check.sp
* Purpose: verify model card works correctly

.OPTIONS POST=2 PROBE=1 RUNLVL=4

* Single device
M1 D G S 0 NMOS_SRAM W=1U L=20N

* Bias
VD D 0 DC=VDD
VG G 0 DC=VDD
VS S 0 DC=0

.DC VG 0 VDD 0.01
.MEASURE DC IDSAT FIND I(M1) AT VGS=VDD
.MEASURE DC VTSAT WHEN I(M1)=1E-7*1U/20N CROSS=1
.MEASURE DC ISOFF FIND I(M1) AT VGS=0

* If this deck fails ? model card issue, not circuit issue.

---

## 7. PVT Binning and Corners

### 7.1 Standard PVT Corner Matrix
| Corner | Process | VDD | Temp | Target |
|--------|---------|-----|------|--------|
| TYP | TT | Nominal | 25C | Nominal characterization |
| WCS | SS | -10% | 125C | Worst speed, worst leakage |
| WCF | FF | +10% | -40C | Best speed, worst dynamic power |
| WCL | SS | -10% | -40C | Worst speed (temp inversion) |
| WCF_H | FF | +10% | 125C | Best speed (temp inversion at low VDD) |

### 7.2 PVT Binning for SRAM
* SRAM-specific corners:
| Corner | Critical For |
|--------|-------------|
| SS_125C_0.72V | Read access time (worst) |
| FF_m40C_0.88V | Write time, dynamic power |
| SS_m40C_0.72V | Temperature inversion (low VDD read) |
| FF_125C_0.88V | Leakage (worst case) |
| TT_25C_0.80V | Nominal |

### 7.3 PVT Sweep Workbench
* File: pvt_sweep_template.sp
.PARAM CORNER=TT
.LIB 'sram_corners.lib' {CORNER}

* Use .ALTER for multi-corner sweep:
.ALTER case=TT_25_0P80
    .PARAM CORNER=TT
    .TEMP 25
    .PARAM VDD=0.80

.ALTER case=SS_125_0P72
    .PARAM CORNER=SS
    .TEMP 125
    .PARAM VDD=0.72

.ALTER case=FF_m40_0P88
    .PARAM CORNER=FF
    .TEMP -40
    .PARAM VDD=0.88

* Measure Iread at each corner
.MEASURE TRAN IREAD ...

### 7.4 Automatic Binning with .DATA
* Sweep all corners with single simulation:
.DATA PVT_DATA
+ CORNER TEMP VDD_VAL
+ TT    25   0.80
+ SS    125  0.72
+ FF   -40   0.88
+ SF    25   0.80
+ FS    25   0.80
.ENDDATA

.LIB 'sram_corners.lib' {CORNER}
.TEMP {TEMP}
.PARAM VDD={VDD_VAL}

.DC DATA=PVT_DATA
.MEASURE DC IREAD_CELL ...

---

## 8. Monte Carlo Model Setup

### 8.1 Monte Carlo in PDK
* Foundry PDK provides MC parameters in .lib:
* Usually includes: global (die-to-die) + local (within-die/mismatch) variation

* File: mc_params.lib
.LIB GLOBAL_MC
* Global process parameters (same for all devices in run)
.PARAM DVT0_GLOB='AGAUSS(0, 0.1, 1, 1)'
.PARAM DU0_GLOB='AGAUSS(0, 0.02, 2, 1)'
.ENDL GLOBAL_MC

.LIB LOCAL_MC
* Local mismatch parameters (unique per device)
.PARAM DVTH0_LOC='AGAUSS(0, 0.015, 3, 1)'
.PARAM DU0_LOC='AGAUSS(0, 0.02, 4, 1)'
.ENDL LOCAL_MC

### 8.2 Applying MC Parameters to Model
.MODEL NMOS_SRAM nmos
+ VTH0='VTH0_NOM + DVT0_GLOB + DVTH0_LOC'
+ U0='U0_NOM * (1 + DU0_GLOB + DU0_LOC)'

* With per-instance variation (mismatch):
M1 D G S 0 NMOS_SRAM W=W L=L DVTH0_LOC='AGAUSS(0, 0.015, 1, 1)'
M2 D G S 0 NMOS_SRAM W=W L=L DVTH0_LOC='AGAUSS(0, 0.015, 2, 1)'
* Each device gets independent random number (via unique variation_num)

### 8.3 MC Run Syntax with PDK Models
.LIB 'mc_params.lib' GLOBAL_MC        * Global variation
.LIB 'mc_params.lib' LOCAL_MC         * Local variation
.LIB 'sram_corners.lib' SS            * SS corner

.MC 500 RUN MEASURE IREAD MAXFAIL=20 FAILCALL=0

### 8.4 Critical MC Parameters for SRAM
| Parameter | Distribution | Sigma (Typical 7nm) | Impact |
|-----------|-------------|---------------------|--------|
| VTH0 NMOS | Gaussian | 15-30mV | Idsat, Vmin |
| VTH0 PMOS | Gaussian | 15-30mV | Cell stability |
| U0 NMOS | Gaussian | 2-5% | Drive current |
| U0 PMOS | Gaussian | 2-5% | Drive current |
| TOXE | Gaussian | 1-2% | Gate leakage |
| RDSW | Gaussian | 5-10% | Parasitic resistance |

---

## 9. Device Model Parameters for SRAM

### 9.1 SRAM Device Model Requirements
* SRAM uses minimum-geometry devices:
  - 6T cell: 2 PMOS (PU) + 4 NMOS (PD, PG)
  - All devices at minimum L (process-specific)
  - Different W (planar) or NFIN (FinFET) for beta/gamma ratio

### 9.2 Model Parameters Critical for SRAM
| Parameter | SRAM Critical | Reason |
|-----------|--------------|--------|
| VTH0 | Extreme | Cell stability, read current, write margin |
| DVT0/DVT1 | High | Short-channel roll-off at min L |
| ETA0 (DIBL) | High | Vth shift at Vds=VDD |
| RDSW | High | Pass-gate resistance ? Iread |
| U0 | High | Drive current |
| VSAT | High | Velocity saturation at high Vgs |
| TOXE | Moderate | Gate capacitance, leakage |
| CJ/CJSW | Moderate | Bitline capacitance |
| CGSO/CGDO | High | Gate overlap ? BL coupling |

### 9.3 Separate Models for PU, PD, PG
* Foundry PDKs often provide separate model cards:
.LIB 'nmos_sram_pd.pm' PD    * Pull-down: wider, leakage-optimized
.LIB 'nmos_sram_pg.pm' PG    * Pass-gate: low Rds, read-optimized
.LIB 'pmos_sram_pu.pm' PU    * Pull-up: low leakage-optimized

* Or single unified model with W/L-based binning:
.MODEL NMOS_SRAM nmos
+ LMIN  = 20N
+ LMAX  = 40N
+ WMIN  = 80N
+ WMAX  = 1U
+ VTH0  = 0.30              * Nominal for min-L devices

### 9.4 Device Model Validation Checklist
`
[ ] Idsat matches PDK datasheet (within 5%)
[ ] Isoff matches PDK datasheet (within 2x ? acceptable)
[ ] Vth at min L matches target
[ ] DIBL (Vtlin - Vtsat) < 100mV/V for well-tuned device
[ ] Subthreshold slope < 85mV/decade (planar), < 70mV/decade (FinFET)
[ ] Iread per fin (FinFET) within 5-12 uA
[ ] Cgg at Vgs=VDD matches PDK CV data
[ ] Temperature coefficient passes sanity (-0.3~-0.5 mV/C)
`

---

## 10. Model Debugging and Validation

### 10.1 Common Model Card Issues
| Issue | Symptom | Check |
|-------|---------|-------|
| Missing parameter | HSPICE warning | Check .lis for \"Model parameter missing\" |
| Incompatible LEVEL | Wrong model level | Verify LEVEL for BSIM4 (54) vs BSIM-CMG (74) |
| Wrong Vth | Idsat too high/low | Check VTH0, DVT0, DVT1, ETA0 |
| No DIBL | Vth constant with Vds | Check ETA0, CDSC, DVT2 |
| High leakage | Isoff excessive | Check VOFF, NFACTOR, SUBTHM |
| No self-heating | Current too high (FinFET) | Check SHMOD, RTH0, CTH0 |
| Convergence fails | Model stiffness | Check GMIN, ITL1, METHOD |

### 10.2 Model Verification Using PDK Test Decks
* Foundry PDK includes test decks for each device:
* Run these to verify model installation:
* File: sanity_check.sp (from PDK)

.LIB 'models/corners.lib' TT
.OPTIONS POST=2 PROBE=1 RUNLVL=4

* NMOS Id-Vg
VDS D 0 DC=0.8
M1 D G 0 0 NMOS_SRAM W=1U L=20N
.DC VG 0 0.8 0.01
.MEASURE DC IDSAT_N FETCH I(M1) AT VGS=0.8

* PMOS Id-Vg
VDS D 0 DC=0.8
M2 D G 0 VDD PMOS_SRAM W=1U L=20N
.DC VG 0.8 0 -0.01
.MEASURE DC IDSAT_P FETCH I(M2) AT VGS=-0.8

* Compare with PDK datasheet values

### 10.3 Model Parameter Extraction from PDK
* If you need to extract parameters from measurement:
* Use .OPTIMIZE to fit model to measured data:
.PARAM VTH0_FIT=OPT1(0.3, 0.1, 0.5)
.MODEL NMOS_FIT nmos LEVEL=54 VTH0='VTH0_FIT'
...
.MEASURE DC IDS_ERROR PARAM='ABS(I(M1) - IDS_TARGET)'
.MODEL FITMODEL OPT METHOD=BISECTION
.DC VG 0 VDD 0.05 OPTIMIZE=OPT1 RESULTS=IDS_ERROR MODEL=FITMODEL

### 10.4 Checking Model Output in .lis
* After simulation, check .lis for:
* Model parameter summary (all parameters with values)
* Operating point (gm, gds, Cgg, Cgd for each device)
* Warnings about parameter ranges
.grep "model parameters" output.lis
.grep "warning" output.lis
.grep "operating point" output.lis

---

## 11. Complete PDK Integration Workbench

### 11.1 Standard PDK Header Template
* File: sram_pdk_template.sp
* ===== HEADER =====
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* ===== PDK MODEL SELECTION =====
.PARAM CORNER=TT
.LIB './models/corners.lib' {CORNER}

* ===== PROCESS PARAMETERS =====
.PARAM VDD=0.80
.PARAM LCELL=30N
.PARAM W_PU=120N  * Planar: PMOS width
.PARAM W_PD=200N  * Planar: NMOS pull-down
.PARAM W_PG=160N  * Planar: NMOS pass-gate
* --- FinFET alternative: ---
.PARAM NFIN_PU=1
.PARAM NFIN_PD=2
.PARAM NFIN_PG=1

* ===== LDE PARAMETERS =====
.PARAM SA=150N SB=150N SD=200N
.PARAM SC=0.5U

* ===== SUPPLIES =====
VDD_SRC VDD 0 DC='VDD'
VSS_SRC VSS 0 DC=0

* ===== CIRCUIT =====
* (User inserts circuit here)

* ===== ANALYSIS =====
* (User inserts analysis here)

* ===== MEASUREMENTS =====
* (User inserts measurements here)

.END

### 11.2 Multi-Corner + Multi-Analysis Template
* File: sram_full_char.sp
* Include PDK
.LIB './models/corners.lib' CORNER
.LIB './models/mc_params.lib' MC

* Parameters
.PARAM VDD=0.80
.PARAM CORNER=TT

* === CORNER 1: TT Nominal ===
.ALTER case=TT_nom
    .PARAM CORNER=TT
    .TEMP 25
    .PARAM VDD=0.80
    .TRAN 0.5P 1N
    .MEASURE TRAN IREAD ...
    .MEASURE TRAN IWRITE ...

* === CORNER 2: SS Worst Speed ===
.ALTER case=SS_worst
    .PARAM CORNER=SS
    .TEMP 125
    .PARAM VDD=0.72

* === CORNER 3: FF Best Speed ===
.ALTER case=FF_best
    .PARAM CORNER=FF
    .TEMP -40
    .PARAM VDD=0.88

* === CORNER 4: MC at TT ===
.ALTER case=MC_TT
    .PARAM CORNER=TT
    .TEMP 25
    .PARAM VDD=0.80
    .MC 200 RUN MEASURE IREAD FAILCALL=0

### 11.3 PDK File Documentation
* Document which PDK files are used and their versions:
* File: pdk_reference.txt (included as comment in netlist)
* $ PDK: XYZ 7nm FinFET v1.2
* $ Models: nmos_tt.pm v2.3, pmos_tt.pm v2.3
* $ Corners: corners.lib v1.0
* $ MC: mc_params.lib v1.1
* $ Date: 2026-06-30

---

## 12. Quick Reference

### 12.1 Model Selection Quick Table
| Process | Model Level | Key MODE | Device |
|---------|-------------|----------|--------|
| 180nm-130nm | BSIM3 (49) | nmos/pmos | Planar |
| 90nm-28nm | BSIM4 (54) | nmos/pmos | Planar |
| 14nm-7nm | BSIM-CMG (72/74) | nmos/pmos | FinFET |
| 5nm-3nm | BSIM-CMG (74+) | nmos/pmos | FinFET/GAA |

### 12.2 Key Parameters by Device Type
| Parameter | Planar NMOS | Planar PMOS | FinFET NMOS | FinFET PMOS |
|-----------|-------------|-------------|-------------|-------------|
| VTH0 | +0.25~0.35 | -0.25~-0.35 | +0.25~0.35 | -0.25~-0.35 |
| U0 | 0.02-0.05 | 0.005-0.015 | 0.015-0.03 | 0.005-0.012 |
| VSAT | 1-1.5E5 | 0.8-1.2E5 | 1-1.5E5 | 0.8-1.2E5 |
| RDSW | 150-300 | 200-400 | 150-300 | 200-400 |
| ETA0 | 0.1-0.3 | 0.1-0.3 | 0.1-0.2 | 0.1-0.2 |
| TOXE | 1.5-3nm | 1.5-3nm | 1.0-2nm | 1.0-2nm |
| CGSO | 1-3E-10 | 1-3E-10 | 1-3E-10 | 1-3E-10 |

### 12.3 Common PDK Errors and Fixes
| Error | Cause | Fix |
|-------|-------|-----|
| \"Model not found\" | .LIB path wrong | Check relative path from netlist location |
| \"Parameter VTH0 out of range\" | Corner mismatch | Verify corner selected matches model param range |
| \"Version mismatch\" | MODEL version vs HSPICE version | Use PDK-recommended HSPICE version |
| \"Uninitialized parameter\" | .PARAM not defined before use | Reorder .PARAM statements before .LIB |
| \"Nested .LIB too deep\" | Too many .LIB inclusions | Flatten .LIB hierarchy |

> **Revision History**
> - 2026-06-30: Initial version. Covers BSIM4/BSIM-CMG models, process corners, temperature inversion, MC setup, PDK integration.
