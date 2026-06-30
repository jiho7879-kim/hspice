---
title: 'HSPICE Netlist Modularization & Project Organization Guide'
subtitle: 'Functional Separation, Reusable Modules, and Automation Patterns for SRAM Characterization'
version: '1.0'
date: '2026-06-30'
description: 'Guide to organizing HSPICE netlists into functionally separated, reusable modules — analogous to Python package structure. Covers directory layout, include hierarchy, module interface design, measurement templates, and automation patterns for SRAM characterization workflows.'
tags: [HSPICE, modularization, automation, project structure, netlist organization, reusable modules, SRAM]
language: 'HSPICE'
keywords: [HSPICE modularization, netlist organization, include hierarchy, measurement templates, automation, parameterized subcircuits, run control]
---

# HSPICE Netlist Modularization & Project Organization Guide

## Table of Contents

1. [Why Modularize HSPICE?](#1-why-modularize-hspice)
2. [Recommended Project Directory Structure](#2-recommended-project-directory-structure)
3. [Functional Separation: What Goes Where](#3-functional-separation-what-goes-where)
4. [Include Hierarchy & Dependency Order](#4-include-hierarchy--dependency-order)
5. [Configuration Layer vs Topology Layer](#5-configuration-layer-vs-topology-layer)
6. [Reusable Module Patterns](#6-reusable-module-patterns)
7. [Measurement Template Library](#7-measurement-template-library)
8. [Automation Patterns](#8-automation-patterns)
9. [Module Interface Design](#9-module-interface-design)
10. [Run Control Architecture](#10-run-control-architecture)
11. [Version Control & Team Considerations](#11-version-control--team-considerations)
12. [Example: Full SRAM Characterization Project](#12-example-full-sram-characterization-project)

---

## 1. Why Modularize HSPICE?

HSPICE netlists grow from simple testbenches into sprawling decks. Without modularization, you get:

| Anti-Pattern | Symptom | Consequence |
|-------------|---------|-------------|
| Monolithic deck | 5000+ line single `.sp` file | Nobody can find anything |
| Copy-paste drift | 12 nearly identical `.sp` files with different constants | Fix one, miss 11 |
| Hardcoded values | `.PARAM VDD=0.8` buried inside a subcircuit | Have to edit subcircuit to change voltage |
| `.MEASURE` spaghetti | 200 `.MEASURE` statements mixed with transistor instances | Impossible to reuse across corners |
| No interface contract | Subcircuit assumes global `.PARAM` exists | Breaks when used in different project |

**Modularization solves this** by separating concerns:

```
Monolithic:     run_all.sp (everything in one file)

Modularized:    config/         <- What values to use (user edits this)
                specs/          <- What to measure (reusable)
                circuits/       <- What to simulate (reusable)
                setup/          <- Simulator options (rarely touched)
                run.sp          <- Orchestrator (5 lines, includes everything)
```

### When to Modularize

| Project Size | Approach |
|-------------|----------|
| 1–2 testbenches, < 200 lines | Simple header breakdown (sections in one file) |
| 3–10 testbenches, 200–2000 lines | Per-function `.inc` files + one config file |
| > 10 testbenches, > 2000 lines | Full directory hierarchy + run control |
| Multiple projects sharing cells | Subcircuit library in shared path |

---

## 2. Recommended Project Directory Structure

### 2.1 Standard SRAM Characterization Project Layout

```
sram_char_project/
│
├── run.sp                          # Main run deck (5–20 lines, orchestrates includes)
├── run_mc.sp                       # Monte Carlo run deck (includes run.sp + MC config)
├── run_corners.sp                  # Corner sweep run deck
│
├── config/                         # USER EDITS: all tunable values
│   ├── process.inc                 #   Process corner: .PARAM CORNER=TT, VDD=0.8V
│   ├── device_params.inc           #   Device dimensions: W_PG, L_CELL, etc.
│   ├── bias_conditions.inc         #   Bias: VDD, VWL, temperatures
│   ├── analysis_settings.inc       #   .TRAN stop time, .DC sweep range, .STEP values
│   └── measurement_thresholds.inc  #   Pass/fail criteria, target values
│
├── models/                         # PDK model files (read-only once locked)
│   ├── models.inc                  #   .INCLUDE path to PDK model library
│   ├── model_select.inc            #   .LIB corner_name TT/SS/FF selection logic
│   └── custom_models.inc           #   Behavioral/macro models (if any)
│
├── circuits/                       # Reusable circuit blocks (subcircuits)
│   ├── sram_cell.inc               #   6T/8T bitcell subcircuit
│   ├── sense_amp.inc               #   Sense amplifier subcircuit
│   ├── write_driver.inc            #   Write driver subcircuit
│   ├── precharge.inc               #   Precharge subcircuit
│   ├── wl_driver.inc               #   WL driver subcircuit
│   ├── nbl_assist.inc              #   NBL assist subcircuit
│   ├── array_load.inc              #   BL/WL RC Pi-model
│   └── control_signals.inc         #   Pulse generator / timing controller
│
├── specs/                          # Measurement definitions (reusable across runs)
│   ├── read_timing.spec            #   .MEASURE: TREAD, TWL_RISE, TBL_DISCHARGE
│   ├── write_timing.spec           #   .MEASURE: TWRITE, TBL_NBL_BOOST
│   ├── power.spec                  #   .MEASURE: I_LEAK, I_DYN, P_ACTIVE
│   ├── read_stability.spec         #   .MEASURE: RSNM, SNM, N-curve metrics
│   └── write_margin.spec           #   .MEASURE: WNM, BL_trip, NBL_effectiveness
│
├── setup/                          # Simulator configuration (rarely changed)
│   ├── options.inc                 #   .OPTIONS POST=2 PROBE=1 RUNLVL=5
│   ├── simulation_control.inc      #   .TRAN, .DC, .AC analysis cards
│   └── output_format.inc           #   .PRINT, .PROBE, .MEASOUT formatting
│
├── common/                         # Shared utilities
│   ├── math_utils.inc              #   .PARAM expressions, derived quantities
│   ├── corner_defs.inc             #   Corner definitions, .DATA tables
│   └── monte_carlo.inc             #   .PARAM GAUSS distribution definitions
│
└── results/                        # Simulation output (auto-generated)
    ├── measurements/               #   .mt0, .mt1 files
    ├── waveforms/                  #   .tr0, .sw0 files
    └── logs/                       #   .lis, .st0 files
```

### 2.2 Minimal Project Layout (3–10 testbenches)

```
mini_project/
├── run_read.sp                     # Run deck for read characterization
├── run_write.sp                    # Run deck for write characterization
├── run_power.sp                    # Run deck for power analysis
├── config.inc                      # All config in one file
├── models.inc                      # Model includes
├── circuits.inc                    # All subcircuits in one file
├── measurements.inc                # All .MEASURE in one file
└── setup.inc                       # Options + analysis control
```

### 2.3 Single-File Breakdown (1–2 testbenches)

```
read_char.sp:
    * === SECTION 1: OPTIONS ===
    * === SECTION 2: MODELS ===
    * === SECTION 3: PARAMETERS ===
    * === SECTION 4: CIRCUITS ===
    * === SECTION 5: ANALYSIS ===
    * === SECTION 6: MEASUREMENTS ===
    * === SECTION 7: OUTPUT ===
```

No external files needed, but still functionally separated by section headers.

---

## 3. Functional Separation: What Goes Where

### 3.1 Configuration Layer (`config/`)

Everything the user **must edit** to adapt to a new process/node/project:

| File | Contents | Example |
|------|----------|---------|
| `process.inc` | Process corner, temperature | `.PARAM CORNER=TT TEMP=25` |
| `device_params.inc` | W, L, M factors for all devices | `.PARAM W_PG=160N L_MIN=30N` |
| `bias_conditions.inc` | Voltage values | `.PARAM VDD=0.8 VWL=0.8` |
| `analysis_settings.inc` | Simulation control parameters | `.PARAM T_STOP=10N T_STEP=1P` |
| `measurement_thresholds.inc` | Pass/fail criteria | `.PARAM TARGET_IREAD=10U` |

**Rule**: Config files contain **only** `.PARAM` statements. No subcircuits, no instances, no analysis cards.

```hspice
* File: config/bias_conditions.inc
.PARAM VDD    = 0.8        <<< USER: Core supply voltage (V)
.PARAM VWL    = 'VDD'      <<< USER: Wordline voltage (typically VDD or VDD-WLUD)
.PARAM VBL    = 'VDD'      <<< USER: Bitline precharge voltage
.PARAM TEMP   = 25         <<< USER: Simulation temperature (°C)
.PARAM CORNER = TT         <<< USER: Process corner
```

### 3.2 Setup Layer (`setup/`)

Simulator configuration that changes rarely:

| File | Contents | Example |
|------|----------|---------|
| `options.inc` | `.OPTIONS` global settings | `.OPTIONS POST=2 PROBE=1 RUNLVL=5` |
| `simulation_control.inc` | Analysis type, sweep, time step | `.TRAN 'T_STEP' 'T_STOP'` |
| `output_format.inc` | `.PRINT`, `.PROBE`, `.MEASOUT` | `.PROBE TRAN V(*) I(*)` |

**Rule**: Setup files may reference config parameters but should never need editing.

```hspice
* File: setup/simulation_control.inc
* Depends on: config/analysis_settings.inc (defines T_STEP, T_STOP, SWEEP_START, SWEEP_END, SWEEP_STEP)

.TRAN 'T_STEP' 'T_STOP' UIC
* .DC analysis (uncomment when used)
* .DC VDD 'SWEEP_START' 'SWEEP_END' 'SWEEP_STEP'
```

### 3.3 Circuit Layer (`circuits/`)

Reusable subcircuit definitions. Pure topology — no global parameter assumptions.

```hspice
* File: circuits/sense_amp.inc
* Ports: BL BLB SA_OUT SA_OUTB SA_EN VDD VSS
* Parameters passed via .PARAM on instance call

.SUBCKT SA_LATCH BL BLB SA_OUT SA_OUTB SA_EN VDD VSS W_IN=200N W_LOAD=400N W_CROSS=200N L=30N
* Precharge
MP1 SA_OUT SA_EN VDD VDD PMOS_SA W='W_LOAD' L='L'
MP2 SA_OUTB SA_EN VDD VDD PMOS_SA W='W_LOAD' L='L'
* Input pair
MN1 SA_OUT BL SAS VSS NMOS_SA W='W_IN' L='L'
MN2 SA_OUTB BLB SAS VSS NMOS_SA W='W_IN' L='L'
* Regenerative latch
MP3 SA_OUT SA_OUTB VDD VDD PMOS_SA W='W_CROSS' L='L'
MP4 SA_OUTB SA_OUT VDD VDD PMOS_SA W='W_CROSS' L='L'
MN3 SA_OUT SA_OUTB SAS SAS NMOS_SA W='W_CROSS' L='L'
MN4 SA_OUTB SA_OUT SAS SAS NMOS_SA W='W_CROSS' L='L'
* Enable tail
MN5 SAS SA_EN VSS VSS NMOS_SA W='W_IN*2' L='L'
.ENDS SA_LATCH
```

**Subcircuit Design Rules:**
- All sizes as formal parameters with defaults (caller overrides only what differs)
- No references to global `.PARAM` — include a comment showing typical invocation
- Supply pins always explicit (VDD, VSS)
- One subcircuit per file (or closely related group)

### 3.4 Spec Layer (`specs/`)

Pure `.MEASURE` blocks, organized by characterization target:

```hspice
* File: specs/read_timing.spec
* Measures read path timing.
* Depends on: config/measurement_thresholds.inc, config/bias_conditions.inc
*
* Nodes assumed: WL_IN, SA_IN, SA_OUT, SA_EN (set by run deck)

.MEASURE TRAN TREAD TRIG V(WL_IN)  VAL='VDD*0.5' RISE=1  + TARG V(SA_OUT) VAL='VDD*0.5' RISE=1

.MEASURE TRAN TWL_RISE TRIG V(WL_IN) VAL='VDD*0.1' RISE=1 + TARG V(WL_IN)  VAL='VDD*0.9' RISE=1

.MEASURE TRAN TBL_DISCHARGE TRIG V(WL_IN) VAL='VDD*0.5' RISE=1 + TARG V(SA_IN) VAL='VDD*0.9' FALL=1

.MEASURE TRAN TSA_TRIG2OUT TRIG V(SA_EN) VAL='VDD*0.5' RISE=1 + TARG V(SA_OUT) VAL='VDD*0.5' RISE=1
```

**Spec file rules:**
- Comments document which nodes/parameters the spec assumes
- No `.PARAM` definitions — everything comes from config files
- No instances or subcircuits
- Reusable across run decks by simple `.INCLUDE`

### 3.5 Analysis-Specific Measurements

When a measurement is only relevant for a specific analysis (e.g., DC sweep for SNM), keep it in a dedicated file:

```hspice
* File: specs/read_stability.spec (used only in DC sweep runs)
* Depends on: config/device_params.inc

.MEASURE DC RSNM FIND V(Q) WHEN V(SA_OUT)=V(SA_OUTB)
.MEASURE DC SNM FIND V(Q) WHEN V(Q)=V(QB)
```

---

## 4. Include Hierarchy & Dependency Order

### 4.1 Golden Order

The order of `.INCLUDE` in the run deck is **critical**. Follow this sequence:

```
Position  | Layer          | Contents                     | Depends On
----------|----------------|------------------------------|-----------
1         | Setup          | .OPTIONS, .TEMP              | Nothing
2         | Config         | .PARAM all user values       | Nothing
3         | Models         | .LIB, .MODEL, .INCLUDE PDK   | Config (corner selection)
4         | Common/utils   | Math helpers, derived params | Config
5         | Circuits       | .SUBCKT definitions          | Models
6         | Specs          | .MEASURE templates           | Nothing (no instances yet)
7         | Main circuit   | Instance calls, testbench    | Circuits, config
8         | Analysis       | .TRAN, .DC, .AC cards        | Setup (overrides)
9         | Output         | .PROBE, .PRINT, .MEASOUT    | Config
```

### 4.2 Concrete Example: Run Deck

```hspice
* File: run.sp
* SRAM Read Timing Characterization — Modular Run Deck

* === 1. SETUP ===
.INCLUDE 'setup/options.inc'
.TEMP 25

* === 2. CONFIGURATION ===
.INCLUDE 'config/bias_conditions.inc'
.INCLUDE 'config/device_params.inc'
.INCLUDE 'config/analysis_settings.inc'

* === 3. MODELS ===
.INCLUDE 'models/model_select.inc'

* === 4. COMMON ===
.INCLUDE 'common/math_utils.inc'

* === 5. CIRCUITS ===
.INCLUDE 'circuits/sram_cell.inc'
.INCLUDE 'circuits/sense_amp.inc'
.INCLUDE 'circuits/precharge.inc'
.INCLUDE 'circuits/wl_driver.inc'
.INCLUDE 'circuits/array_load.inc'

* === 6. SPECS (loaded before testbench for measurement visibility) ===
.INCLUDE 'specs/read_timing.spec'
.INCLUDE 'specs/power.spec'

* === 7. TESTBENCH ===
* Instantiate circuits, connect signals
XCELL BL BLB WL VDD_INT VSS SRAM_BITCELL
XSA    BL BLB SA_OUT SA_OUTB SA_EN VDD VSS SA_LATCH
...
* Voltage sources
VDD_SRC VDD 0 DC='VDD'
...

* === 8. ANALYSIS ===
.INCLUDE 'setup/simulation_control.inc'

* === 9. OUTPUT ===
.INCLUDE 'setup/output_format.inc'

.END
```

### 4.3 Why This Order Matters

| Wrong Order | Symptom |
|-------------|---------|
| `.SUBCKT` before `.MODEL` | HSPICE error: "Model not defined" |
| `.MEASURE` before `.PARAM` it references | Undefined parameter in measure |
| `.LIB` after circuit instances | Model not found for devices |
| Config after testbench | Parameters defined too late, instances use default values |
| `.PROBE` at very top | Works technically, but conventions vary by team |

---

## 5. Configuration Layer vs Topology Layer

This is the **single most important** modularization principle.

### 5.1 What Is Configuration?

Values that **change** between runs, corners, or projects:
- Supply voltages, temperatures
- Device dimensions
- Measurement thresholds
- Analysis time ranges

### 5.2 What Is Topology?

Structure that **stays the same** across runs:
- Subcircuit connectivity
- Measurement formulas (not thresholds)
- Analysis types (not durations)

### 5.3 Anti-Pattern: Hardcoded Config in Topology

```hspice
* BAD: Config buried inside topology file
.SUBCKT SA_LATCH BL BLB SA_OUT SA_OUTB SA_EN VDD VSS
* ... (circuit) ...
MN5 SAS SA_EN VSS VSS NMOS_SA W=200N L=30N   * Hardcoded!
.ENDS SA_LATCH
```

### 5.4 Correct: Parameterized Topology

```hspice
* GOOD: Topology is parameterized
.SUBCKT SA_LATCH BL BLB SA_OUT SA_OUTB SA_EN VDD VSS W_IN=200N L=30N
* ... (circuit) ...
MN5 SAS SA_EN VSS VSS NMOS_SA W='W_IN*2' L='L'
.ENDS SA_LATCH

* GOOD: Caller supplies config
XSA BL BLB SO SOB SA_EN VDD VSS SA_LATCH W_IN='W_SA_IN' L='L_CELL'
```

### 5.5 Multi-Layer Configuration

```
Layer 0 (project default):    config/default/device_params.inc
Layer 1 (corner override):    config/tt/device_params.inc   (only overrides what differs)
Layer 2 (run override):       command-line: .PARAM VDD=0.7
```

```hspice
* Run deck that layers configuration:
.INCLUDE 'config/default/device_params.inc'    * Project baselines
.INCLUDE 'config/tt/device_params.inc'         * Corner-specific overrides
* Command-line option overrides anything above:
* hspice run.sp -runlvl=5 -define VDD=0.7
```

---

## 6. Reusable Module Patterns

### 6.1 Parameterized Subcircuit Template

```hspice
* File: circuits/write_driver.inc
* Reusable write driver with configurable width
*
* Usage:
*   XWD BL BLB DATA EN VDD VSS WRITE_DRIVER W=800N L=30N
*
* Ports:
*   BL, BLB  : bitline pair
*   DATA     : write data input
*   EN       : write enable
*   VDD, VSS : supplies

.SUBCKT WRITE_DRIVER BL BLB DATA EN VDD VSS W=800N L=30N
* Data input buffer
MNI1 D_INV DATA VSS VSS NMOS_WD W='W/4' L='L'
MIP1 D_INV DATA VDD VDD PMOS_WD W='W/2' L='L'
* BL pull-down (write '0')
MN_BL BL EN VSS VSS NMOS_WD W='W' L='L'
* BLB pull-up (write '1')
MP_BLB BLB EN VDD VDD PMOS_WD W='W*2' L='L'
* Enable buffer
MEN1 EN_INV EN VSS VSS NMOS_WD W='W/4' L='L'
.ENDS WRITE_DRIVER
```

### 6.2 Measurement Template with Conditionals

```hspice
* File: specs/power.spec
* Power measurements — use WITH_LEAKAGE=1 to enable leakage meas
*
* Depends on: VDD from config, I(VDD_SRC) available

.IF (WITH_LEAKAGE)
  .MEASURE TRAN I_LEAK AVG I(VDD_SRC) FROM='T_LEAK_START' TO='T_LEAK_END'
.ENDIF

.MEASURE TRAN I_DYN_AVG AVG I(VDD_SRC) FROM='T_DYN_START' TO='T_DYN_STOP'
.MEASURE TRAN P_ACTIVE PARAM='I_DYN_AVG * VDD'
```

### 6.3 Sweep Controller Module

```hspice
* File: common/sweep_controller.inc
* Provides sweep variables that can be toggled by the run deck.
*
* Usage in run deck:
*   .PARAM SWEEP_TYPE=VDD    * VDD | TEMP | CORNER
*
* Then uncomment the appropriate sweep:

* --- VDD Sweep ---
* .DC VDD 0.6 0.9 0.02

* --- Temperature Sweep ---
* .DC TEMP -40 125 5

* --- Corner Sweep ---
* .DATA CORNERS
* + TT  FF  SS  SF  FS
* .ENDDATA
* .DC DATA=CORNERS
```

### 6.4 Conditional Include Pattern

```hspice
* File: common/assist_control.inc
* Selectively includes assist circuits based on config flags.
*
* Depends on: WLUD_EN, NBL_EN, VCOL_EN from config

.IF (WLUD_EN)
  .INCLUDE 'circuits/wlud_gen.inc'
  .PARAM VWL_SUP = 'VDD - WLUD_DELTA'
.ELSE
  .PARAM VWL_SUP = VDD
.ENDIF

.IF (NBL_EN)
  .INCLUDE 'circuits/nbl_assist.inc'
.ENDIF

.IF (VCOL_EN)
  .INCLUDE 'circuits/vdd_collapse.inc'
.ENDIF
```

---

## 7. Measurement Template Library

### 7.1 Why a Measurement Library

.MEASURE statements are the most copy-pasted (and most error-prone) part of any HSPICE deck. A reusable measurement library eliminates:
- Inconsistent threshold values across runs
- Typo'd node names
- Missing or extra timing margins

### 7.2 Template: Read Timing

```hspice
* File: specs/read_timing.spec
* === READ TIMING — Template ===
* Node conventions (override via .ALTER if needed):
*   WL_IN  : wordline after driver
*   SA_IN  : sense-amp input (BL after Pi-model)
*   SA_OUT : sense-amp output
*   SA_EN  : sense-amp enable
*
* Parameters from config:
*   VDD          : supply voltage
*   TARGET_DV    : target BL differential for SA trigger (e.g., 0.05)

* --- WL propagation: driver input → far-end cell ---
.MEASURE TRAN T_WL_PROP  TRIG V(WL_DRV) VAL='VDD*0.5' RISE=1 +
+                          TARG V(WL_IN)  VAL='VDD*0.5' RISE=1

* --- WL rise time (10% → 90%) ---
.MEASURE TRAN T_WL_RISE  TRIG V(WL_IN) VAL='VDD*0.1' RISE=1 +
+                          TARG V(WL_IN) VAL='VDD*0.9' RISE=1

* --- BL discharge time: WL rise → BL falls to VDD - TARGET_DV ---
.MEASURE TRAN T_BL_DISCH TRIG V(WL_IN) VAL='VDD*0.5' RISE=1 +
+                          TARG V(SA_IN) VAL='VDD - TARGET_DV' FALL=1

* --- SA propagation: SA_EN rise → SA_OUT rise ---
.MEASURE TRAN T_SA_PROP  TRIG V(SA_EN) VAL='VDD*0.5' RISE=1 +
+                          TARG V(SA_OUT) VAL='VDD*0.5' RISE=1

* --- Total read access: WL rise → SA_OUT valid ---
.MEASURE TRAN T_READ_ACL TRIG V(WL_IN) VAL='VDD*0.5' RISE=1 +
+                          TARG V(SA_OUT) VAL='VDD*0.5' RISE=1

* --- Read timing margin: BL_delta(TARGET_DV) + guardband vs SA_EN ---
.MEASURE TRAN T_READ_MARGIN TRIG V(SA_IN) VAL='VDD - TARGET_DV' FALL=1 +
+                            TARG V(SA_EN) VAL='VDD*0.5' RISE=1
```

### 7.3 Template: Write Timing

```hspice
* File: specs/write_timing.spec
* === WRITE TIMING — Template ===
* Node conventions:
*   WL_IN    : wordline
*   Q, QB    : bitcell internal nodes
*   BL, BLB  : bitline pair (measuring at cell)

* --- Write completion: WL rise → cell flips (Q and QB cross VDD/2) ---
.MEASURE TRAN T_WRITE TRIG V(WL_IN) VAL='VDD*0.5' RISE=1 +
+                        TARG V(Q)   VAL='VDD*0.5' CROSS=LAST

* --- NBL boost propagation: NBL_EN → BL negative ---
.MEASURE TRAN T_NBL_PROP TRIG V(NBL_EN) VAL='VDD*0.5' RISE=1 +
+                          TARG V(BL)   VAL='-0.05'    FALL=1

* --- Write setup: WR_EN → BL starts falling ---
.MEASURE TRAN T_WR_SETUP TRIG V(WR_EN) VAL='VDD*0.5' RISE=1 +
+                          TARG V(BL)   VAL='VDD*0.9' FALL=1

* --- Write margin: write completion vs WL fall ---
.MEASURE TRAN T_WR_MARGIN TRIG V(Q) VAL='VDD*0.5' CROSS=LAST +
+                          TARG V(WL_IN) VAL='VDD*0.5' FALL=1
```

### 7.4 Template: Leakage & Power

```hspice
* File: specs/leakage_power.spec
* === LEAKAGE & POWER — Template ===
* Depends on: VDD, T_LEAK_START, T_LEAK_END, T_CYCLE from config

* --- Standby leakage (all devices off, BL=VDD) ---
.MEASURE TRAN I_LEAK_STBY AVG I(VDD_SRC) FROM='T_LEAK_START' +
+                          TO='T_LEAK_END'

* --- Active current during read ---
.MEASURE TRAN I_READ_AVG AVG I(VDD_SRC) FROM='T_READ_START' +
+                          TO='T_READ_END'

* --- Active power ---
.MEASURE TRAN P_READ PARAM='I_READ_AVG * VDD'

* --- Energy per access ---
.MEASURE TRAN E_ACCESS INTEG I(VDD_SRC) FROM='T_CYCLE_START' +
+                          TO='T_CYCLE_END'

* --- Peak current ---
.MEASURE TRAN I_PEAK MAX I(VDD_SRC) FROM='T_CYCLE_START' TO='T_CYCLE_END'
```

### 7.5 Template: Read Stability (DC)

```hspice
* File: specs/read_stability.spec
* === READ STABILITY (Butterfly / N-curve) — Template ===
* DC analysis only. Requires sweep of V(Q) or V(BL).
*
* Depends on: VDD from config

* --- Static Noise Margin ---
.MEASURE DC SNM FIND V(Q) WHEN V(Q)=V(QB)

* --- Read Static Noise Margin ---
.MEASURE DC RSNM FIND V(Q) WHEN V(SA_OUT)=V(SA_OUTB)

* --- N-curve metrics ---
.MEASURE DC I_CRITICAL MIN I(VREAD_SRC)
.MEASURE DC Q_CRITICAL INTEG I(VREAD_SRC)
```

---

## 8. Automation Patterns

### 8.1 .ALTER-Based Multi-Corner Automation

Run the same testbench across multiple corners in a single simulation:

```hspice
* File: run_corners.sp
* Single run that sweeps TT, FF, SS automatically

.INCLUDE 'setup/options.inc'
.INCLUDE 'config/bias_conditions.inc'
.INCLUDE 'models/model_select.inc'
.INCLUDE 'circuits/*.inc'
.INCLUDE 'specs/read_timing.spec'

* --- Testbench ---
* (instantiate standard testbench)

* --- Initial run: TT corner ---
.PARAM CORNER=TT
.INCLUDE 'setup/simulation_control.inc'
.INCLUDE 'setup/output_format.inc'

* --- ALTER 1: FF corner ---
.ALTER
.PARAM CORNER=FF

* --- ALTER 2: SS corner ---
.ALTER
.PARAM CORNER=SS

* --- ALTER 3: SF corner ---
.ALTER
.PARAM CORNER=SF

* --- ALTER 4: FS corner ---
.ALTER
.PARAM CORNER=FS

.END
```

### 8.2 .DATA-Driven Parametric Sweep

Run a design of experiments (DOE) without editing the deck:

```hspice
* File: config/sweep_table.inc
* Sweep table for VDD × TEMP × W_PG DOE

.DATA DOE_SWEEP
+ VDD    TEMP   W_PG
+ 0.6    -40    120N
+ 0.6    -40    160N
+ 0.6     25    120N
+ 0.6     25    160N
+ 0.6    125    120N
+ 0.6    125    160N
+ 0.8    -40    120N
+ 0.8    -40    160N
+ 0.8     25    120N
+ 0.8     25    160N
+ 0.8    125    120N
+ 0.8    125    160N
+ 1.0    -40    120N
+ 1.0    -40    160N
+ 1.0     25    120N
+ 1.0     25    160N
+ 1.0    125    120N
+ 1.0    125    160N
.ENDDATA

* In run deck:
.INCLUDE 'config/sweep_table.inc'
.DC DATA=DOE_SWEEP
```

### 8.3 Monte Carlo Parameter Generator

```hspice
* File: common/monte_carlo.inc
* Gaussian variation generators for Monte Carlo analysis
*
* Depends on: W_PG, W_PD, W_PU, L_CELL from config
*             SIGMA_VTH_PG, SIGMA_VTH_PD from config

* --- Vth mismatch (Gaussian, 3-sigma truncation) ---
.PARAM DVT_PG = 'AGAUSS(0, SIGMA_VTH_PG, 3)'
.PARAM DVT_PD = 'AGAUSS(0, SIGMA_VTH_PD, 3)'
.PARAM DVT_PU = 'AGAUSS(0, SIGMA_VTH_PU, 3)'

* --- LER (line-edge roughness) ---
.PARAM DL_PG = 'AGAUSS(0, SIGMA_LER, 3)'
.PARAM DL_PD = 'AGAUSS(0, SIGMA_LER, 3)'

* --- Apply to device instances ---
* (used in the subcircuit instantiation, not here)
```

### 8.4 Templated Run Deck Generator (Python + HSPICE)

For maximum automation, generate run decks from a template:

```python
# File: gen_run.py
# Generate HSPICE run decks from parameter templates
# Usage: python gen_run.py --corner TT --vdd 0.8 --temp 25

import os
import sys

TEMPLATE = """* Auto-generated run deck
* Corner: {corner}  VDD: {vdd}V  TEMP: {temp}C

.INCLUDE 'setup/options.inc'
.TEMP {temp}

.INCLUDE 'config/bias_conditions.inc'
.INCLUDE 'config/device_params.inc'

.PARAM VDD={vdd}
.PARAM CORNER={corner}

* (rest of includes and testbench...)
.INCLUDE 'run_template.inc'

.END
"""

if __name__ == '__main__':
    corner = sys.argv[1] if len(sys.argv) > 1 else 'TT'
    vdd    = sys.argv[2] if len(sys.argv) > 2 else '0.8'
    temp   = sys.argv[3] if len(sys.argv) > 3 else '25'

    filename = f'run_{corner}_{vdd}v_{temp}c.sp'
    with open(filename, 'w') as f:
        f.write(TEMPLATE.format(corner=corner, vdd=vdd, temp=temp))

    print(f'Generated: {filename}')
```

---

## 9. Module Interface Design

### 9.1 Subcircuit Interface Contract

Every subcircuit file should document:

```hspice
* File: circuits/precharge.inc
*
* INTERFACE:
*   Ports:     BL, BLB, PCH, VDD  (supplies explicit, not global)
*   Params:    W=400N, L=30N      (defaults provided, caller overrides)
*   Depends:   Models PMOS_PCH must exist
*   Provides:  BL = BLB = VDD when PCH=0
*   Used by:   precharge_controller in testbench
*   Example:
*     XPRECH BL BLB PCH_EN VDD PRECHARGE W='W_PCH' L='L_PCH'
*
.SUBCKT PRECHARGE BL BLB PCH VDD W=400N L=30N
MP1 BL PCH VDD VDD PMOS_PCH W='W' L='L'
MP2 BLB PCH VDD VDD PMOS_PCH W='W' L='L'
MP3 BL BLB VDD VDD PMOS_PCH W='W/2' L='L'
.ENDS PRECHARGE
```

### 9.2 Global vs Local Parameter Rules

| Scope | Declaration | Visibility | Use Case |
|-------|------------|------------|----------|
| Global | `.PARAM NAME=value` in config file | Entire deck | VDD, TEMP, N_ROWS |
| Local | `.PARAM NAME=value` inside `.SUBCKT` | Subcircuit only | Internal bias, derived w/in cell |
| Instance | On `.SUBCKT` call line | That instance only | W, L overrides |
| Expressions | `'expression'` | Where used | Derived quantities |

**Example of correct scoping:**

```hspice
* Global: in config/bias_conditions.inc
.PARAM VDD=0.8

* Local to subcircuit:
.SUBCKT WL_BUF IN OUT VDD VSS W_N=800N W_P=1.6U L=30N
* Internal: this parameter only exists inside WL_BUF
.PARAM W_RATIO = 'W_P / W_N'
* ... instance uses W_RATIO ...
.ENDS WL_BUF

* Instance-level override:
XWL WL_IN WL_INT VDD VSS WL_BUF W_N='W_WL_DRV_N' W_P='W_WL_DRV_P'
```

### 9.3 Dependency Declaration Convention

Each `.inc` file should declare its dependencies in the header comments:

```hspice
* File: circuits/array_load.inc
*
* PROVIDES:
*   - BL Pi-model: R_BL_METAL/2 + C_BL_TOTAL/2 topology
*
* REQUIRES (from includes read BEFORE this file):
*   - config/device_params.inc: C_DRAIN_PG, C_GD_PG
*   - config/bias_conditions.inc: N_ROWS, N_COLS
*   - models/model_select.inc: NMOS_SRAM, PMOS_SRAM
*
* OUTPUT VALUES (computed from config params):
*   None (pure topology — uses config params directly in expressions)
```

---

## 10. Run Control Architecture

### 10.1 Single-Purpose Run Decks

Each run deck has **one job**:

| Run Deck | Purpose | Config Override | Specs Used |
|----------|---------|----------------|------------|
| `run_read.sp` | Read timing characterization | bias_conditions + analysis_settings | read_timing.spec |
| `run_write.sp` | Write timing characterization | bias_conditions (enable NBL) | write_timing.spec |
| `run_power.sp` | Power analysis | analysis_settings (longer T_STOP) | leakage_power.spec |
| `run_snm.sp` | Read stability (DC sweep) | analysis_settings (DC sweep) | read_stability.spec |
| `run_mc.sp` | Monte Carlo yield | monte_carlo.inc | all specs |
| `run_corners.sp` | Multi-corner sweep | corner_defs.inc | all specs |

### 10.2 Run Deck Template

```hspice
* File: run_read.sp
* ============================================
* PURPOSE:  Read timing characterization
* AUTHOR:   <your name>
* USAGE:    hspice run_read.sp -runlvl=5
* OUTPUTS:  run_read.mt0, run_read.tr0
* ============================================

* --- 1. SETUP ---
.INCLUDE 'setup/options.inc'
.TEMP {TEMP}

* --- 2. CONFIG ---
.INCLUDE 'config/bias_conditions.inc'
.INCLUDE 'config/device_params.inc'
.INCLUDE 'config/analysis_settings.inc'
.PARAM NBL_EN=0                        * No NBL for read char
.PARAM WLUD_EN=1                       * WLUD enabled for read stability
.PARAM WITH_LEAKAGE=0                  * Skip leakage meas for faster sim

* --- 3. MODELS ---
.INCLUDE 'models/model_select.inc'

* --- 4. CIRCUITS ---
.INCLUDE 'circuits/sram_cell.inc'
.INCLUDE 'circuits/sense_amp.inc'
.INCLUDE 'circuits/precharge.inc'
.INCLUDE 'circuits/wl_driver.inc'
.INCLUDE 'circuits/array_load.inc'
.INCLUDE 'circuits/control_signals.inc'

* --- 5. TESTBENCH ---
* (standard read testbench)
.INCLUDE 'testbenches/read_testbench.inc'

* --- 6. SPECS ---
.INCLUDE 'specs/read_timing.spec'
.INCLUDE 'specs/power.spec'

* --- 7. ANALYSIS & OUTPUT ---
.INCLUDE 'setup/simulation_control.inc'
.INCLUDE 'setup/output_format.inc'

.END
```

### 10.3 Configuration File Pattern (Single Source of Truth)

```hspice
* File: config/bias_conditions.inc
* ============================================
* SINGLE SOURCE OF TRUTH for all bias values.
* Every run deck includes this file.
* Override individual values in the run deck when needed.
* ============================================

* --- Supplies ---
.PARAM VDD    = 0.8      <<< Core supply
.PARAM VSS    = 0.0      <<< Ground
.PARAM VBL    = 'VDD'    <<< BL precharge target (= VDD for full restore)

* --- WL ---
.PARAM WL_PW  = 200E-12  <<< WL pulse width (s)
.PARAM VWL_ON = 'VDD'    <<< WL active voltage (= VDD for full write, VDD-WLUD for read)

* --- Timing ---
.PARAM PERIOD = 1E-9     <<< Clock period (s)
.PARAM T_RISE = 5E-12    <<< Signal rise time (s)
.PARAM T_FALL = 5E-12    <<< Signal fall time (s)

* --- Temperature ---
.PARAM TEMP   = 25       <<< Simulation temperature (°C)
```

---

## 11. Version Control & Team Considerations

### 11.1 What to Commit

| File Type | Commit? | Reason |
|-----------|---------|--------|
| Source `.inc` files | ✅ Yes | Reusable IP |
| Run decks `.sp` | ✅ Yes | Reproducibility |
| Config `.inc` with **generic** defaults | ✅ Yes | Starting point for new projects |
| Config with **project-specific** values | ⚠️ Project-level only | Don't share confidential process params |
| Generated `.sp` files | ❌ No | Regenerate from template |
| Binary output `.tr0`, `.sw0` | ❌ No | Large, regenerate |
| Measurement `.mt0` files | ❌ No | Regenerate |
| Log `.lis` files | ❌ No | Noise |

### 11.2 Team Convention File

Create a `CONTRIBUTING.md` or `NETLIST_CONVENTIONS.md` at project root:

```markdown
# HSPICE Netlist Conventions

## Naming
- Subcircuit files: `snake_case.inc`
- Run decks: `run_<purpose>.sp`
- Config: `config/<domain>.inc`
- Spec: `specs/<metric>.spec`

## Header
Every .inc file must have a header block documenting:
- PROVIDES: what this file contains
- REQUIRES: what must be included before this file
- INTERFACE: ports, parameters, usage example

## Global Parameters
- VDD, TEMP, PERIOD always come from config/ — never hardcoded
- No global .PARAM inside circuit/ files (use subcircuit parameters)

## Measurements
- All .MEASURE in specs/ directory
- Never mix .MEASURE with instances
- Spec files document their node conventions
```

### 11.3 Diff-Friendly Formatting

```hspice
* BAD for diffs (everything on one line):
RBL1 BL BL_MID 'R_BL_METAL/2' RBL2 BL_MID BL_INT 'R_BL_METAL/2'

* GOOD for diffs (one element per line):
RBL1 BL     BL_MID 'R_BL_METAL/2'
RBL2 BL_MID BL_INT 'R_BL_METAL/2'
```

---

## 12. Example: Full SRAM Characterization Project

### 12.1 Directory Tree

```
sram_char/
├── run_read.sp
├── run_write.sp
├── run_snm.sp
├── run_mc.sp
│
├── config/
│   ├── bias_conditions.inc
│   ├── device_params.inc
│   ├── analysis_settings.inc
│   ├── measurement_thresholds.inc
│   └── process_corners.inc
│
├── models/
│   ├── model_select.inc        # .LIB path + corner selection
│   └── custom_models.inc
│
├── circuits/
│   ├── sram_cell.inc           # Parameterized 6T
│   ├── sense_amp.inc
│   ├── write_driver.inc
│   ├── precharge.inc
│   ├── wl_driver.inc
│   ├── nbl_assist.inc
│   ├── array_load.inc          # BL/WL Pi-model
│   └── control_signals.inc     # Pulse generators
│
├── specs/
│   ├── read_timing.spec
│   ├── write_timing.spec
│   ├── leakage_power.spec
│   └── read_stability.spec
│
├── testbenches/
│   ├── read_testbench.inc
│   ├── write_testbench.inc
│   └── snm_testbench.inc
│
├── setup/
│   ├── options.inc
│   ├── simulation_control.inc
│   └── output_format.inc
│
├── common/
│   ├── math_utils.inc
│   ├── monte_carlo.inc
│   └── sweep_helpers.inc
│
└── tools/
    └── gen_run.py              # Run deck generator
```

### 12.2 Typical User Workflow

```
1. SETUP (one-time per project):
   cp -r template_project/ my_project/
   Edit config/bias_conditions.inc    → set VDD, TEMP
   Edit config/device_params.inc      → set W_PG, W_PD, W_PU, L_CELL
   Edit models/model_select.inc       → point to PDK .lib path

2. RUN (per characterization target):
   hspice run_read.sp       → run_read.mt0 (read timing results)
   hspice run_snm.sp        → run_snm.mt0 (SNM results)
   hspice run_mc.sp         → run_mc.mt0 (Monte Carlo results)

3. VIEW:
   Open .tr0 in waveforms
   Parse .mt0 with scripts/tools

4. ITERATE (no file editing needed):
   hspice run_read.sp -define VDD=0.7  → lower voltage
   hspice run_read.sp -define VDD=0.9  → higher voltage
```

### 12.3 What Each Layer Handles (Summary Table)

| Layer | Files | Responsibility | User Edits? |
|-------|-------|----------------|-------------|
| Run control | `run_*.sp` | Orchestration: include order, overrides, analysis type | Per-run selection |
| Config | `config/*.inc` | All tunable values | **Yes, per project** |
| Models | `models/*.inc` | PDK .LIB path, model selection | Once per PDK |
| Circuits | `circuits/*.inc` | .SUBCKT definitions (parameterized) | Rarely (new cell) |
| Specs | `specs/*.spec` | .MEASURE templates | Once per metric |
| Testbench | `testbenches/*.inc` | Instance wiring, signal sources | Per-test |
| Setup | `setup/*.inc` | Simulator options, analysis cards | Rarely |
| Common | `common/*.inc` | Math helpers, sweep/MC utilities | Once |

---

> **Revision History**
> - 2026-06-30: Initial version. HSPICE modularization principles, directory structure, reusable module patterns, measurement template library, automation patterns, interface design.
