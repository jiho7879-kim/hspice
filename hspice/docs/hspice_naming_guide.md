---
title: 'HSPICE Naming Convention Guide'
subtitle: 'Consistent Naming Rules for Device, Node, Port, Source, Parameter, and Measurement Identifiers'
version: '1.0'
date: '2026-06-30'
description: 'Standardized naming conventions for HSPICE netlist identifiers derived from SRAM cell characterization and unit-transistor characterization patterns. Covers devices, nodes, ports, sources, parameters, measurements, and analysis types.'
tags: [HSPICE, naming convention, coding standard, netlist, identifier, SRAM, UT]
language: 'HSPICE'
keywords: [naming convention, identifier, device, node, port, source, parameter, measurement, netlist]
---

# HSPICE Naming Convention Guide

> **Purpose**: Establish consistent naming rules for all identifiers appearing in HSPICE netlists, measurements, and automation scripts.
> **Scope**: SRAM bitcell characterization, unit-transistor (UT) characterization, yield-modeling workbench, and output-parsing automation.
> **Basis**: Patterns established in hspice_sram_cell_char.md and standard TR-level characterization practices.

---

## Table of Contents

1. [General Principles](#1-general-principles)
2. [Device Naming (M-Devices)](#2-device-naming-m-devices)
3. [Node / Net Naming](#3-node--net-naming)
4. [Port Naming](#4-port-naming)
5. [Source / Stimulus Naming](#5-source--stimulus-naming)
6. [Parameter Naming](#6-parameter-naming)
7. [Measurement (.MEASURE) Naming](#7-measurement-measure-naming)
8. [Model, Subcircuit, and Instance Naming](#8-model-subcircuit-and-instance-naming)
9. [Analysis and Sweep Naming](#9-analysis-and-sweep-naming)
10. [File and Variable Naming](#10-file-and-variable-naming)
11. [Naming Quick-Reference Table](#11-naming-quick-reference-table)
12. [Pattern Violations to Avoid](#12-pattern-violations-to-avoid)

---

## 1. General Principles

### 1.1 Core Rules
- **UPPERCASE** for all HSPICE identifiers (HSPICE is case-insensitive, but uppercase improves readability in mixed environments).
- **Underscore** _ as word separator. No spaces or hyphens in identifiers.
- **Type prefix** indicates what the identifier represents (mnenomic prefix pattern).
- **Suffix** indicates instance number (1, 2) or variant (A, B, _NORM, _TRIP).
- **No special characters** other than _. No leading digits.

### 1.2 Naming Hierarchy
`
  [TYPE]_[FUNCTION]_[QUALIFIER]_[INSTANCE]
   ^        ^            ^           ^
   |        |            |           +-- instance / variant
   |        |            +-------------- condition qualifier
   |        +--------------------------- circuit function
   +------------------------------------ identifier type
`

### 1.3 Identifier Type Prefixes
| Prefix | Type | Example |
|--------|------|---------|
| (M, MP, MN) | MOSFET device | MPU1, MPD2, MPG1 |
| V | Source / voltage supply | VDD_SRC, VVDD_INJ |
| I | Current source | IREF_BIAS |
| X | Subcircuit instance | XCELL, XARRAY |
| .PARAM name | Parameter | VDD_NOM, WPU, L |
| (measure name) | Measurement | RSNM, IREAD, VTRIP |
| (model name) | Model | NMOS_SRAM, PMOS_UT |
| (subckt name) | Subcircuit | SRAM6T |

---

## 2. Device Naming (M-Devices)

### 2.1 6T SRAM Bitcell Naming Pattern
Pattern: M[P/N][U/D/G][1/2]

| Position | Meaning | Values |
|----------|---------|--------|
| 1: M | MOSFET indicator | fixed |
| 2: P or N | PMOS or NMOS | P = PMOS, N = NMOS |
| 3: U / D / G | Function | U = Pull-Up, D = Pull-Down, G = Pass-Gate |
| 4: instance# | 1 or 2 | 1 = left half, 2 = right half |

**Defined SRAM names:**
| Name | Type | Function |
|------|------|----------|
| MPU1, MPU2 | PMOS | Cross-coupled pull-up (load) |
| MPD1, MPD2 | NMOS | Cross-coupled pull-down (driver) |
| MPG1, MPG2 | NMOS | Pass-gate (access) |

### 2.2 Unit-Transistor (UT) Naming
Pattern: M_[TYPE]_[WxL]_[INST]

| Name | Description |
|------|-------------|
| M_NCH_W1 | Single NMOS, width variant 1 |
| M_PCH_W1 | Single PMOS, width variant 1 |
| M_DUT | Device-under-test in characterization |
| M_REF | Reference device (matched pair) |

### 2.3 Inverter / Logic Gate Devices
Pattern: M_[TYPE]_[GATE]_[INST]

| Name | Description |
|------|-------------|
| MP_INV1 | PMOS of inverter 1 |
| MN_INV1 | NMOS of inverter 1 |
| MN_NAND_A | NMOS of NAND, input A leg |
| MP_CLK_INV | PMOS of clocked inverter |

### 2.4 Matching / Replica Devices
Pattern suffixes: _MATCH, _REPLICA, _DUMMY, _SEN, _LOAD

| Name | Description |
|------|-------------|
| M_NCH_MATCH | matched NMOS pair |
| M_PCH_REPLICA | replica PMOS for biasing |
| M_DUMMY1 | dummy device (layout matching) |
| M_LOAD_ACT | active load device |

---

## 3. Node / Net Naming

### 3.1 Power and Ground Naming
| Node | Convention | Alias |
|------|------------|-------|
| VDD | Main positive supply | ? |
| VSS | Main ground (0V) | GND |
| VDD_CORE | Core supply (separate) | VDDC |
| VDD_IO | I/O supply | VDDPAD |
| VSSA | Analog ground | ? |
| VSS_SUB | Substrate contact | SUB |

### 3.2 SRAM Storage Nodes
| Node | Convention | Description |
|------|------------|-------------|
| VVDD | Storage node '1' side | (single V prefix for voltage node) |
| VVDD2 | Storage node '0' side (complement) | |

**Rule**: Internal storage nodes use V prefix + function name. No underscore between V and name for 2-3 char names.

### 3.3 SRAM Bitline Naming
| Node | Convention |
|------|------------|
| BL | Bitline true |
| BLB | Bitline complement (bar) |

**Rule**: Complementary signals use B suffix for bar (inverted). No underscore before B.

### 3.4 SRAM Control Node Naming
| Node | Convention |
|------|------------|
| WL | Wordline |
| WLB | Wordline complement |
| RBL | Read bitline |
| WBL | Write bitline |
| WBLB | Write bitline complement |
| SA_EN | Sense-amplifier enable (multi-word with underscore) |
| PRE_N | Precharge (active low, _N suffix) |
| COL_SEL | Column select (multi-word) |

### 3.5 UT Characterization Nodes
| Node | Convention | Description |
|------|------------|-------------|
| D | Drain of UT | (single char for bulk terminals) |
| G | Gate of UT | |
| S | Source of UT | |
| B | Body / bulk of UT | |
| VG | Gate bias node | |
| VD | Drain bias node | |
| VS | Source bias node | |
| VB | Body bias node | |

### 3.6 General Node Naming Rules
- **Global nets**: VDD, VSS, VREF, VBIAS
- **Functional nets**: [BLOCK]_[FUNCTION] e.g., SA_OUT, SA_OUTB
- **Internal probe points**: [BLOCK]_[NODE]_PROBE
- **Array structures**: [BLOCK]_ROW[#]_COL[#]

---

## 4. Port Naming

### 4.1 Subcircuit Port Order Convention
`
.SUBCKT [NAME] [CONTROL_PORTS] [DATA_PORTS] [SUPPLY_PORTS]
`

**Port ordering rule:** Control ? Data ? Supply
`
.SUBCKT SRAM6T BL BLB WL VDD VSS
.SUBCKT INV IN OUT VDD VSS
.SUBCKT NAND A B Z VDD VSS
`

### 4.2 Subcircuit Port Naming Rules
- Upper-level ports match the top-level nodes they connect to.
- No direction modifiers (HSPICE does not use IN/OUT).
- Power/ground ports are **always last** in the port list.
- Bidirectional ports (e.g., BL in SRAM) appear before supply.

### 4.3 Port Name Mapping Convention
`
 Subcircuit Port   ?   Top-level Node
 ???????????????????????????????????
 BL               ?   BL[COL#]
 WL               ?   WL[ROW#]
 VDD              ?   VDD_MUX  (hierarchical)
 VSS              ?   VSS
`

---

## 5. Source / Stimulus Naming

### 5.1 Voltage Source Naming
Pattern: [NODE]_SRC or V[FUNCTION]_[NODE]

**Rule**: Sources are named after the node they bias, with _SRC suffix.

| Source | Biased Node | Purpose |
|--------|-------------|---------|
| VDD_SRC | VDD | Main supply |
| VSS_SRC | VSS | Ground |
| WL_SRC | WL | Wordline bias |
| BL_SRC | BL | Bitline bias |
| BLB_SRC | BLB | Complement bitline bias |
| VVDD_SRC | VVDD | Injection/sweep source |
| VVDD_INJ | VVDD | Explicit injection (N-curve) |

### 5.2 Current Source Naming
Pattern: I_[FUNCTION]_[INST]

| Name | Description |
|------|-------------|
| IREF_MIRR | Reference current for mirror |
| ILOAD | Load current |
| IBIAS_SA | Sense-amplifier bias current |
| IDAC_N | DAC current, NMOS side |

### 5.3 Pulse / PWL Source Suffixes
| Suffix | Meaning |
|--------|---------|
| _PULSE | Pulse source (single) |
| _CLK | Clock source (periodic) |
| _PWL | Piecewise-linear source |
| _SINE | Sinusoidal source |

### 5.4 Sweep Source Pattern
| Source | Sweep Type | Usage |
|--------|------------|-------|
| VVDD_INJ | DC sweep | N-curve injection at storage node |
| VDD_SWEEP | DC sweep | Supply voltage ramping (Vret) |
| BL_SWEEP | DC sweep | Bitline voltage sweep (WNM) |
| WL_SWEEP | DC sweep | Wordline voltage sweep |

---

## 6. Parameter Naming

### 6.1 Device Geometry Parameters
Pattern: [DEVICE_TYPE]_[PARAM]

| Parameter | Description | Unit |
|-----------|-------------|------|
| WPU | Pull-up width | m |
| WPD | Pull-down width | m |
| WPG | Pass-gate width | m |
| L | Channel length | m |
| W | Width (single device) | m |
| W_NCH | NMOS width (UT) | m |
| W_PCH | PMOS width (UT) | m |
| NFIN | Number of fins (FinFET) | ? |
| M | Multiplier (parallel fingers) | ? |

### 6.2 Bias Condition Parameters
Pattern: [CONDITION]_[NODE]

| Parameter | Description |
|-----------|-------------|
| VDD_NOM | Nominal supply voltage |
| VREAD | Read condition WL voltage (0 or VDD) |
| VWRITE | Write condition voltage |
| VW | Wordline voltage (generic) |
| VBL_PRE | Bitline precharge voltage |
| VBL_SEN | Sense-amplifier trigger voltage |

### 6.3 Sweep and Analysis Parameters
Pattern: [ANALYSIS]_[VARIABLE]

| Parameter | Description |
|-----------|-------------|
| VSTART | Sweep start voltage |
| VSTOP | Sweep stop voltage |
| VSTEP | Sweep step voltage |
| TSTART | Transient start time |
| TSTOP | Transient stop time |
| TSTEP | Transient step (or max timestep) |

### 6.4 Process / Mismatch Parameters
Pattern: [DEVICE]_[PARAM]_[STAT]

| Parameter | Description |
|-----------|-------------|
| VTH0 | Threshold voltage (BSIM4) |
| U0 | Mobility (BSIM4) |
| TOX | Oxide thickness |
| RSH | Sheet resistance |
| VTH_SIGMA | Vth mismatch sigma |
| VTH_AG | Vth global variation |
| VTH_A | Vth mismatch slope (Pelgrom) |

### 6.5 Temperature Parameters
| Parameter | Description |
|-----------|-------------|
| TEMP_OP | Operating temperature |
| TEMP_NOM | Nominal temperature |
| TEMP_HOT | Hot temperature |
| TEMP_COLD | Cold temperature |

---

## 7. Measurement (.MEASURE) Naming

### 7.1 Measurement Name Rule
Pattern: [MEASURED][_QUALIFIER][_CONDITION][_VARIANT]

- **No leading digit**
- **Uppercase** with underscore separators
- **Measurand prefix** identifies the quantity
- **Condition suffix** identifies bias/operation point

### 7.2 Measurand Prefix Table

| Prefix | Quantity | Unit | Example |
|--------|----------|------|---------|
| V | Voltage | V | VTRIP, VMAX |
| I | Current | A | IREAD, ISTBY |
| R | Resistance | ? | RCH, ROD |
| C | Capacitance | F | CGG, CDD |
| P | Power | W | PSTATIC, PDYN |
| Q | Charge | C | QCHANNEL |
| T | Time | s | TWRITE, TREAD |
| DV | Voltage difference | V | DVIN |
| DI | Current difference | A | DICELL |
| F | Frequency | Hz | FRING |

### 7.3 Measurement Naming ? SRAM Cell

**Current measurements:**
| Name | Description | Pattern |
|------|-------------|---------|
| IREAD | Read current through PG | I[FUNCTION] |
| ICELL | Cell read current (avg) | I[FUNC]_PARAM |
| IREAD_TRIG | Read current at trigger | I[FUNC]_[POINT] |
| IREAD_NT | Read current at near-threshold | I[FUNC]_[MODE] |
| ICRIT_READ | Critical read current | I_CRIT_[MODE] |
| ICRIT_READ_VAR | Icrit read sigma | I_CRIT_[MODE]_VAR |
| ICRIT_WRITE | Critical write current | I_CRIT_[MODE] |
| ISTBY | Standby leakage current | I_[MODE] |
| IRET | Retention current | I_[MODE] |
| IRET_CHECK | Retention normalized | I_[MODE]_CHECK |
| ILEAK_PU1 | Leakage PU1 | ILEAK_[DEV] |
| ILEAK_TOTAL | Total leakage | ILEAK_TOTAL |
| ILEAK_G_PU1 | Gate leakage PU1 | ILEAK_G_[DEV] |
| ILEAK_S_PU1 | Subthreshold leakage PU1 | ILEAK_S_[DEV] |

**Voltage measurements:**
| Name | Description | Pattern |
|------|-------------|---------|
| VTRIP1 | Trip voltage (method 1) | V[FUNC][#] |
| VTRIP_AC | Trip voltage (AC method) | V[FUNC]_[MODE] |
| VTRIP_HT | Trip voltage at high temp | V[FUNC]_[COND] |
| VMAX | Maximum voltage | V[MODIFIER] |
| VMIN | Minimum voltage | V[MODIFIER] |
| VRET_POINT | Retention voltage | V[FUNC]_POINT |
| VRET_MARGIN | Retention margin | V[FUNC]_MARGIN |
| VRET_SIGMA | Retention sigma | V[FUNC]_SIGMA |
| VRET_HOT | Retention hot | V[FUNC]_[COND] |
| VRET_COLD | Retention cold | V[FUNC]_[COND] |

**SNM measurements:**
| Name | Description | Pattern |
|------|-------------|---------|
| SNM_DIFF | SNM via voltage difference | SNM_[METHOD] |
| SNM_FLOOR | SNM floor | SNM_[QUAL] |
| SNM_CALC | Analytic SNM | SNM_[METHOD] |
| SNM_SIDE | SNM square side | SNM_[QUAL] |
| SNM_MIN | SNM minimum | SNM_[QUAL] |
| RSNM | Read SNM | [MODE]SNM |
| RSNM_NORM | RSNM / VDD | [MODE]SNM_NORM |
| HSNM | Hold SNM | [MODE]SNM |
| HSNM_NORM | HSNM / VDD | [MODE]SNM_NORM |
| WSNM | Write SNM | [MODE]SNM |

**Write margin measurements:**
| Name | Description | Pattern |
|------|-------------|---------|
| WNM_TRIG | Write noise margin trigger | WNM_[QUAL] |
| WNM_PARAM | WNM parameter | WNM_[QUAL] |
| WNM_NORM | WNM normalized | WNM_NORM |
| WRITE_END | Write end point | WRITE_[POINT] |
| WRITE_TIME | Write time | WRITE_[MEAS] |
| WRITE_OK | Write success check | WRITE_[CHECK] |
| WRITE_FAIL | Write fail quantity | WRITE_[CHECK] |
| WRITE_FAIL_LVL | Write fail voltage | WRITE_FAIL_[QUAL] |
| WLM | Wordline margin | WLM |
| WTV_TRIP | Write-trip voltage trigger | WTV_[QUAL] |
| WTV_WINDOW | Write-trip voltage window | WTV_[QUAL] |

**N-curve measurements:**
| Name | Description | Pattern |
|------|-------------|---------|
| SVNM | Static voltage noise margin | SVNM |
| SINM | Static current noise margin | SINM |
| WTV | Write-trip voltage | WTV |
| WTI | Write-trip current | WTI |
| N_PEAK1 | N-curve peak (positive) | N_[QUAL][#] |
| N_PEAK2 | N-curve peak (negative) | N_[QUAL][#] |
| N_SVNM1 | SVNM first crossing | N_[MEAS][#] |
| N_SVNM2 | SVNM second crossing | N_[MEAS][#] |

**VTC measurements:**
| Name | Description | Pattern |
|------|-------------|---------|
| VTC1 | Forward VTC max diff | VTC[#] |
| VTC2 | Reverse VTC max diff | VTC[#] |
| SNM_DIAG | Diagonal of SNM square | SNM_[QUAL] |

### 7.4 Measurement Naming ? Unit Transistor (UT)

**Standard UT measurements:**
| Name | Description | Pattern |
|------|-------------|---------|
| VTSAT | Saturation Vth | VT[MODE] |
| VTLIN | Linear Vth | VT[MODE] |
| IDSAT | Saturation Id | ID[MODE] |
| IDLIN | Linear Id | ID[MODE] |
| ISOFF | Off-state leakage | IS[MODE] |
| IDOFF | Drain off leakage | ID[MODE] |
| DIBL | Drain-induced barrier lowering | DIBL |
| SSAT | Subthreshold swing (sat) | S[MODE] |
| RODLIN | Output resistance (linear) | ROD[MODE] |
| RCH | Channel resistance | RCH |
| GM_MAX | Peak transconductance | GM_[QUAL] |
| GMMAX_VTH | Vth@peak Gm | GM[MEAS]_[QUAL] |
| VON | Overdrive voltage | VON |
| CGG | Gate capacitance | CGG |

### 7.5 Measurement Naming ? Yield and Statistics

| Name | Description | Pattern |
|------|-------------|---------|
| VMIN_READ | Read VMIN | VMIN_[MODE] |
| VMIN_WRITE | Write VMIN | VMIN_[MODE] |
| VMIN_HOLD | Hold VMIN | VMIN_[MODE] |
| VMIN_SIGMA | VMIN sigma | VMIN_SIGMA |
| MU_READ | Read VMIN mean | MU_[MODE] |
| SIGMA_READ | Read VMIN std | SIGMA_[MODE] |
| SIGMA_TO_MU | Variation ratio | SIGMA_TO_MU |
| FAIL_RATE | Failure rate | FAIL_[QUAL] |
| YIELD | Yield | YIELD |
| N_SIGMA | Number of sigma | N_SIGMA |

---

## 8. Model, Subcircuit, and Instance Naming

### 8.1 Model Naming
Pattern: [TYPE]_[DEVICE]_[NODE] or [APPLICATION]_[DEVICE]

| Model Name | Description |
|------------|-------------|
| NMOS_SRAM | SRAM NMOS model |
| PMOS_SRAM | SRAM PMOS model |
| NMOS_UT | Unit-transistor NMOS model |
| PMOS_UT | Unit-transistor PMOS model |
| NMOS_CORE | Core-logic NMOS model |
| PMOS_IO | I/O PMOS model |

**Model suffix convention:**
| Suffix | Meaning |
|--------|---------|
| _TT | Typical-Typical (nominal) |
| _SS | Slow-Slow (worst-case) |
| _FF | Fast-Fast (best-case) |
| _SF | Slow-Fast (cross) |
| _FS | Fast-Slow (cross) |
| _TT_25 | TT at 25C |
| _TT_125 | TT at 125C |

### 8.2 Subcircuit Naming
Pattern: [CIRCUIT][FUNCTION][SIZE]

| Subcircuit | Description |
|------------|-------------|
| SRAM6T | 6T SRAM bitcell |
| SRAM8T | 8T SRAM bitcell (read-buffered) |
| INV | Inverter |
| NAND2 | 2-input NAND |
| NOR2 | 2-input NOR |
| SA_LATCH | Latch-type sense amplifier |
| SA_CD | Current-differential sense amplifier |
| WD_STD | Standard write driver |
| DEC_N2P | N:2 pre-decoder |
| ARRAY_MXN | M-row x N-col array |

### 8.3 Instance Naming
Pattern: X[FUNCTION]_[ROW]_[COL]

| Instance | Description |
|----------|-------------|
| XCELL | Single cell instance (char workbench) |
| XARRAY | Full array instance |
| XSA_ROW0 | Sense-amp, row 0 |
| XDEC_ROW | Row decoder |
| XWD_COL0 | Write driver, column 0 |
| XMON | Monitor subcircuit |

---

## 9. Analysis and Sweep Naming

### 9.1 Analysis Type Conventions
| Analysis | Card | Convention |
|----------|------|------------|
| DC sweep | .DC | [SWEEP_VAR] 0 [VDD] [STEP] |
| Transient | .TRAN | [TSTEP] [TSTOP] |
| AC | .AC | DEC [N] [FSTART] [FSTOP] |
| Monte Carlo | .MC | [N_RUNS] [MEASURE] [OUTPUT] |
| Sensitivity | .SENS | V([OUT_NODE]) |

### 9.2 Sweep Variable Naming
Sweep variables match the bias source they drive:

| Sweep | Source Swept | Sweep Type |
|-------|-------------|------------|
| VVDD_SRC | VVDD injection | DC (0 ? VDD) |
| VDD_SWEEP | VDD supply | DC (VDD_NOM ? 0, Vret) |
| BL_SWEEP | BL voltage | DC (VDD ? 0, WNM) |
| WL_SWEEP | WL voltage | DC (VDD ? 0, write margin) |
| TEMP_SWEEP | Temperature | DC (-40 ? 125) |

---

## 10. File and Variable Naming

### 10.1 Netlist File Naming
Pattern: [PROJECT]_[CIRCUIT]_[ANALYSIS].sp

| File | Description |
|------|-------------|
| sram6t_char.sp | 6T SRAM characterization workbench |
| sram6t_snm.sp | SNM measurement deck |
| sram6t_iread.sp | Read current measurement |
| ut_nch_char.sp | NMOS unit-transistor characterization |
| ut_pch_char.sp | PMOS unit-transistor characterization |
| sram_vmin_mc.sp | Monte Carlo VMIN analysis |
| inv_ring_osc.sp | Ring oscillator (inverter chain) |
| array_sim.sp | Mini-array simulation |

### 10.2 Output File Naming
Pattern: [DECK]_[ANALYSIS]_[CORNER].[ext]

| File | Extension | Description |
|------|-----------|-------------|
| sram6t_char | .mt0 | Measurement results (DC) |
| sram6t_char | .st0 | Measurement results (TRAN) |
| sram6t_char | .lis | Listing / log file |
| sram6t_char | .tr0 | Transient waveform output |
| sram6t_char | .sw0 | DC sweep waveform |
| sram6t_mc | .mt# | Monte Carlo measurement results |
| sram6t_char | .ac0 | AC analysis output |

### 10.3 .MEASURE Output Naming (within .mt0/.st0)
The .mt0 file headers use the measurement name directly:
`
 SOURCE='HSPICE' VERSION='2021.09'

IREAD    ICELL    RSNM    HSNM    VTRIP
3.21e-05 3.18e-05 0.185   0.205   0.412
`

### 10.4 Python Script Variable Name Mapping
When parsing .mt0/.st0 into Python, use the exact HSPICE measure name as dictionary key:

`python
data = {
    'IREAD': 3.21e-05,
    'ICELL': 3.18e-05,
    'RSNM': 0.185,
    'VTRIP': 0.412,
}
`

---

## 11. Naming Quick-Reference Table

### 11.1 SRAM Bitcell ? Full Name Map
`	ext
Devices:   MPU1, MPU2, MPD1, MPD2, MPG1, MPG2
Nodes:     VVDD, VVDD2, BL, BLB, WL
Supplies:  VDD, VSS
Params:    WPU, WPD, WPG, L, VDD_NOM
Sources:   VDD_SRC, VSS_SRC, WL_SRC, BL_SRC, BLB_SRC, VVDD_INJ
Measures:  RSNM, HSNM, WSNM, IREAD, ICELL, VTRIP,
           WNM_TRIP, WRITE_TIME, SVNM, SINM, WTV, WTI,
           ISTBY, IRET, VRET_POINT
Subckts:   SRAM6T
Models:    NMOS_SRAM, PMOS_SRAM
`

### 11.2 Unit Transistor ? Full Name Map
`	ext
Devices:   M_NCH_W1, M_PCH_W1, M_DUT
Nodes:     D, G, S, B, VG, VD, VS, VB
Params:    W_NCH, L_NCH, VTH0, U0
Sources:   VG_SRC, VD_SRC, VS_SRC, VB_SRC
Measures:  VTSAT, VTLIN, IDSAT, IDLIN, ISOFF, DIBL, SSAT
Subckts:   UT_NCH, UT_PCH
Models:    NMOS_UT, PMOS_UT
`

### 11.3 Mini-Array ? Full Name Map
`	ext
Devices:   MPU_ROWn_COLm, MPD_ROWn_COLm, MPG_ROWn_COLm
Nodes:     BL_COLm, BLB_COLm, WL_ROWn, SA_OUT
Params:    NROW, NCOL, VDD_ARRAY
Instances: XARRAY, XDEC, XSA_COLm, XWD_COLm
`

---

## 12. Pattern Violations to Avoid

### 12.1 Banned Patterns
| Violation | Why | Correct |
|-------------|-----|------------|
| M1, M2 (bare) | No function info | MPU1, MPD2 |
| vdd_src (lowercase) | HSPICE mixed case confusion | VDD_SRC |
| BL-bar (hyphen) | HSPICE interprets hyphen as minus | BLB |
| Icell_read (camelCase) | Non-standard mix | ICELL_READ |
| SNM@25C (special char) | Not a valid identifier | SNM_25C |
| 1st_measure (leading digit) | HSPICE may reject | MEAS_1ST |
| nmos_sram_tt (generic TT) | Must be explicit | NMOS_SRAM_TT |
| VDD=1.8V (unit in name) | Unit embedded in name | VDD_NOM=1.8 |
| READ_CURRENT (too generic) | Ambiguous device | IREAD_MPG1 |
| Vth (Greek letters) | Non-ASCII in netlist | VTH |

### 12.2 Common Ambiguities to Avoid
- **W**: Width of which device? Use WPU, WPD, WPG.
- **L**: Length is usually global, but clarify: L_CELL.
- **I(VDD)**: Which component? Use named measures per device: ILEAK_PU1.
- **V(VDD)**: Is this the supply or a swept source? Name the source: VDD_SRC.
- **SNM alone**: Hold, read, or write? Use HSNM, RSNM, WSNM.
- **VTRIP**: Specify method: VTRIP1, VTRIP2, VTRIP_AC.

### 12.3 Cross-Document Consistency
When extending to other circuits (inverter, NAND, mini-array, yield bench):
- Inherit prefixes and naming logic from this guide.
- New circuit blocks derive from these base patterns.
- Keep measure names mnemonic: first letter = type (V/I/R/C/T), rest = function.

---

> **Revision History**
> - 2026-06-30: Initial version. Derived from hspice_sram_cell_char.md patterns.
