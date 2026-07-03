---
title: 'HSPICE Convergence and Options Guide'
subtitle: '.OPTIONS, RUNLVL, GMIN Stepping, ITL1/ITL2, METHOD, IC/NODESET, and Convergence Debugging'
version: '1.0'
date: '2026-06-30'
description: 'Comprehensive HSPICE convergence tuning guide for SRAM and transistor-level simulation. Covers .OPTIONS parameters, RUNLVL selection, GMIN stepping, iteration limits, integration methods, initial conditions, DC sweep convergence, and debugging non-convergent circuits.'
tags: [HSPICE, convergence, options, RUNLVL, GMIN, ITL1, ITL2, METHOD, IC, NODESET, troubleshooting]
language: 'HSPICE'
keywords: [convergence, .OPTIONS, RUNLVL, GMIN stepping, ITL1, ITL2, METHOD=GEAR, .IC, .NODESET, DC sweep, non-convergence, .OPTION, SRAM convergence]
---

# HSPICE Convergence and Options Guide

> **Purpose**: Tuning HSPICE simulation options for robust convergence in SRAM and transistor-level circuits.
> **Coverage**: .OPTIONS syntax, RUNLVL levels, GMIN stepping, iteration limits, integration methods, initial conditions, DC convergence, AC convergence, and troubleshooting.
> **Target**: HSPICE users debugging convergence failures in memory and analog circuits.

---

## Table of Contents

1. [Convergence Overview](#1-convergence-overview)
2. [RUNLVL Selection Guide](#2-runlvl-selection-guide)
3. [GMIN and GMIN Stepping](#3-gmin-and-gmin-stepping)
4. [Iteration Limits (ITL1, ITL2, ITL4)](#4-iteration-limits-itl1-itl2-itl4)
5. [Integration Methods (METHOD)](#5-integration-methods-method)
6. [Initial Conditions (.IC, .NODESET)](#6-initial-conditions-ic-nodeset)
7. [DC Sweep Convergence](#7-dc-sweep-convergence)
8. [Transient Convergence](#8-transient-convergence)
9. [DC Operating Point (.OP) Convergence](#9-dc-operating-point-op-convergence)
10. [Common Convergence Errors and Fixes](#10-common-convergence-errors-and-fixes)
11. [SRAM-Specific Convergence Issues](#11-sram-specific-convergence-issues)
12. [Convergence Debugging Workflow](#12-convergence-debugging-workflow)
13. [Complete Convergence Options Reference](#13-complete-convergence-options-reference)
14. [References](#14-references)

---

## 1. Convergence Overview

### 1.1 What Convergence Means
HSPICE solves circuits using Newton-Raphson iterations:
1. Linearize the circuit at current operating point
2. Solve linear equations (G * V = I)
3. Check if voltages changed less than tolerance (ABSTOL, VNTOL, RELTOL)
4. If not converged, update operating point and repeat

### 1.2 Non-Convergence Symptoms
| Symptom | Error Message | Likely Cause |
|---------|---------------|--------------|
| DC timeout | \"Can't converge DC\" | High gain / feedback loops |
| No DC op point | \"No convergence in DC analysis\" | Initial guess far from solution |
| Transient rejection | \"Time step too small\" | Sharp edges / discontinuous models |
| Internal timestep crash | \"Convergence failure at t=X\" | Model discontinuities |
| Oscillating solution | \"Bypass converged but internal didn't\" | Bistable circuits (SRAM) without IC |

### 1.3 Convergence Strategy Hierarchy
1. **Always try first**: RUNLVL=4, METHOD=TRAP
2. **If DC fails**: .NODESET critical nodes, use GMINDC=1E-6
3. **If transient fails**: reduce max timestep, use METHOD=GEAR
4. **If still failing**: GMIN stepping, ITL1 increase, PIVOT options
5. **Last resort**: ITL4, then .OPTIONS RELTOL=1E-4 (from 1E-3), then CONVERGE=1

---

## 2. RUNLVL Selection Guide

### 2.1 RUNLVL Levels
| RUNLVL | Description | Speed | Convergence | Accuracy | When to Use |
|--------|-------------|-------|-------------|----------|-------------|
| 0 | Minimum | Fastest | Poor | Low | Final check only |
| 1 | Basic | Very fast | Fair | Low | Pre-simulation sanity |
| 2 | Standard | Fast | Good | Medium | Quick exploratory sweeps |
| 3 | Default | Moderate | Good | Medium | General-purpose nominal runs |
| 4 | Enhanced | Moderate | Very good | High | SRAM Vmin, read margin |
| 5 | Aggressive | Slow | Excellent | High | Yield, Monte Carlo, sensitive nodes |
| 6 | Maximum | Slowest | Best | Highest | Research, final verification |
| 7 | Extreme | Very slow | Ultimate | Highest | Pathological circuits only |

### 2.2 RUNLVL Expands to These Options
* Each RUNLVL sets a group of .OPTIONS automatically:

* RUNLVL=4 (recommended for SRAM characterization)
.OPTIONS RUNLVL=4
* Expands to:
*   RELTOL=1E-4, ABSTOL=1E-6, VNTOL=1E-6
*   PIVTOL=1E-13, PIVREL=1E-3
*   ITL1=500, ITL2=500, ITL4=40
*   GMINDC=1E-6, GMIN=1E-12
*   METHOD=TRAP, MAXORD=2

* RUNLVL=6 (for yield/Monte Carlo final runs)
.OPTIONS RUNLVL=6
*   RELTOL=1E-5, ABSTOL=1E-8, VNTOL=1E-6
*   ITL1=2000, ITL2=2000, ITL4=100
*   METHOD=GEAR, MAXORD=6
*   GMIN=1E-15, PIVTOL=1E-16

### 2.3 Manual Override of RUNLVL Defaults
* You can set RUNLVL then override specific options
.OPTIONS RUNLVL=4 RELTOL=1E-6    * Override tolerance even tighter
.OPTIONS RUNLVL=5 ITL1=2000       * Override iteration limit

* To see all expanded options:
* .OPTIONS BRIEF=1 (or check .lis file)

---

## 3. GMIN and GMIN Stepping

### 3.1 GMIN Overview
GMIN = minimum conductance in parallel with every p-n junction.
- Purpose: aid convergence by providing a DC path
- Default: 1E-12 S (1 pS)
- Danger: too large GMIN distorts leakage current

### 3.2 GMIN Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| GMIN | 1E-12 | Minimum conductance (S) across all junctions |
| GMINDC | 1E-12 | GMIN used only during DC analysis |
| GMINMIN | 1E-15 | Minimum allowed GMIN during stepping |
| NOGMIN | off | Disable GMIN (not recommended) |

### 3.3 GMIN Stepping (Automatic)
* HSPICE automatically reduces GMIN from a large value to target:
* GMIN_start ? GMIN_default if DC fails initially
* Controlled by:

.OPTIONS GMINSTEPS=10    * Number of GMIN steps (default=5)
.OPTIONS GMINSTEP=2      * Step divisor (default=2, each step halves GMIN)

* Process:
* Step 1: Solve with GMIN=1E-5
* Step 2: Solve with GMIN=5E-6  (using step 1 as initial guess)
* ...
* Final: Solve with GMIN=target

### 3.4 Manual GMIN Stepping
* For stubborn circuits, manual GMIN sweep works better:
* File: gmin_stepping.sp
.PARAM GMIN_VAL=1E-5
.OPTIONS GMIN='GMIN_VAL'

.DC GMIN_VAL 1E-5 1E-15 DEC 2
.MEASURE DC V_SOLUTION V(VVDD)

* Or with .ALTER:
.ALTER case=GMIN_1E5
    .OPTIONS GMIN=1E-5
.ALTER case=GMIN_1E7
    .OPTIONS GMIN=1E-7
.ALTER case=GMIN_1E9
    .OPTIONS GMIN=1E-9
.ALTER case=GMIN_1E12
    .OPTIONS GMIN=1E-12

### 3.5 GMIN Impact on Leakage Accuracy
GMIN | Leakage Error | Convergence
-----|--------------|------------
1E-12 | <1% (good) | Standard
1E-9 | ~1-5% (ok) | Easy
1E-6 | >10% (poor) | Very easy

* Always verify: GMIN << actual junction conductance
* For Isoff measurement: use GMIN ? 1E-15 or set GMINDC to small value

---

## 4. Iteration Limits (ITL1, ITL2, ITL4)

### 4.1 Iteration Parameters
| Parameter | Default | Scope | Description |
|-----------|---------|-------|-------------|
| ITL1 | 200 (RUNLVL) | DC operating point | Max Newton-Raphson iterations for DC bias |
| ITL2 | 200 (RUNLVL) | DC transfer sweep | Max iterations per step in .DC sweep |
| ITL4 | 10 (RUNLVL) | Transient | Max Newton iterations per time point |
| ITL5 | 0 | Transient | Max total time points (0=unlimited) |

### 4.2 When to Increase ITLx
* **ITL1**: Increase if .OP or .DC (first step) fails to converge
* **ITL2**: Increase if .DC sweep fails mid-sweep (abrupt transitions)
* **ITL4**: Increase if transient fails with "time step too small" at sharp transitions

.OPTIONS ITL1=1000 ITL2=1000     * Generous DC limits
.OPTIONS ITL4=50                 * Generous transient limit

### 4.3 When ITL Increase Doesn't Help
* If Newton iterations reach limit and still don't converge:
  - Solution oscillates between two states (limit cycle)
  - Solution diverges exponentially
* Fix: improve initial guess (.NODESET, .IC) rather than increasing ITL

### 4.4 ITL4 and Transient Time Step
* When ITL4 exceeded, HSPICE cuts timestep in half and retries
* Cut continues until timestep < MINSTEP or ITL4_TIM
* Solutions:
  1. Increase ITL4 (allow more iterations per step)
  2. Tighten integration with METHOD=GEAR and MAXORD=2
  3. Use .OPTIONS PROBE=1 (reduce output nodes ? faster ? fewer iterations)

---

## 5. Integration Methods (METHOD)

### 5.1 Available METHODS
| METHOD | Type | Accuracy | Stability | Best For |
|--------|------|----------|-----------|----------|
| TRAP | Trapezoidal | Good | Moderate | General transient (default) |
| GEAR | Gear (BDF) | Good | High | Stiff circuits, long transients |
| GEAR2 | Gear 2nd order | Good | High | Stiff circuits with ringing |
| EULER | Forward Euler | Poor | Low | Not recommended |
| TRAPGEAR | Trap with Gear fallback | Good | Adaptive | When TRAP fails, auto-switch |

### 5.2 METHOD=TRAP (Default)
.OPTIONS METHOD=TRAP
* +: Default, good accuracy, moderate speed
* -: Can ring at sharp transitions
* -: Numerical ringing on LC tanks (circuits with inductance)

### 5.3 METHOD=GEAR (Recommended for SRAM)
.OPTIONS METHOD=GEAR MAXORD=6
* +: Excellent stability, no ringing
* +: Good for stiff SRAM circuits (wide time constants)
* -: Slightly less accurate than TRAP at same timestep
* -: Slower for low-frequency circuits

* For SRAM transient:
.OPTIONS METHOD=GEAR MAXORD=2
* MAXORD=2 = Gear 2nd order, stable and fast for digital switching

### 5.4 METHOD Choice Flowchart
* Circuit has steep edges (WL rise < 5ps)?
  ? METHOD=GEAR MAXORD=2 (avoid TRAP ringing)
* Circuit has long time constants (leakage + fast switching)?
  ? METHOD=GEAR MAXORD=6 (handle stiffness)
* Circuit is analog with smooth signals?
  ? METHOD=TRAP (higher accuracy)
* All else fails?
  ? METHOD=TRAPGEAR (auto-switch on ringing)

---

## 6. Initial Conditions (.IC, .NODESET)

### 6.1 .IC (Initial Conditions)
* Sets initial voltage for transient analysis
* Acts as initial guess for DC operating point

* Syntax:
.IC V(NODE1) = VALUE1 V(NODE2) = VALUE2

* SRAM example (pre-set bitcell state):
.IC V(VVDD)=VDD V(VVDD2)=0 V(BL)=VDD V(BLB)=VDD
* Sets bitcell to store '1' with both bitlines precharged

### 6.2 .NODESET (DC Operating Point Hint)
* Sets initial guess for DC convergence only
* Overwritten during Newton iteration ? does NOT force final value
* Ideal for SRAM bistable circuits

* Syntax:
.NODESET V(NODE1) = VALUE1 V(NODE2) = VALUE2

* SRAM DC operating point:
.NODESET V(VVDD)=VDD V(VVDD2)=0
* Helps DC converge to the correct stable state

### 6.3 .IC vs .NODESET Comparison
| Aspect | .IC | .NODESET |
|--------|-----|----------|
| Scope | Transient initial condition | DC initial guess only |
| Final value | Overridden by solution | Overridden by solution |
| Bistable circuits | Selects which state | Helps find a state |
| Convergence help | Indirect (via initial DC) | Direct (improves DC guess) |
| Can force value? | With .IC MOD/NODCHG | No |

### 6.4 Strong Initialization (.IC MOD)
* Force initial condition despite DC solution:
.OPTIONS IC=1 MOD=1
.IC V(VVDD)=VDD V(VVDD2)=0

* Equivalent to UIC (Use Initial Conditions) on .TRAN:
.TRAN 0.5P 1N UIC
* UIC = use .IC values as starting point, skip DC operating point

### 6.5 SRAM-Specific .NODESET Usage
* Always set both storage nodes to opposite states:
.NODESET V(VVDD)=VDD V(VVDD2)=0     * Stores '1' on VVDD
* OR
.NODESET V(VVDD)=0 V(VVDD2)=VDD     * Stores '0' on VVDD

* If .NODESET omitted, SRAM may converge to metastable state:
* V(VVDD) = V(VVDD2) = VDD/2  ?  not a valid digital state!

### 6.6 .NODESET for Write Driver
* Without .NODESET, write driver and bitcell may fight
.NODESET V(BL)=VDD V(BLB)=0
* Sets BL=1, BLB=0 before write driver turns on

---

## 7. DC Sweep Convergence

### 7.1 DC Sweep Convergence Issues
* DC sweep steps through voltage/current values
* At each step, HSPICE uses previous step's solution as initial guess
* Convergence fails when:
  - Abrupt transitions (e.g., SRAM cell flip)
  - Multiple solutions (bistable circuits)
  - Gain > 1 feedback loops

### 7.2 DC Sweep Convergence Options
.OPTIONS DCSTEP=1E-3     * Min DC step size (V) ? larger = fewer steps
.OPTIONS DCON=1           * Use continuation method
.OPTIONS GMINDC=1E-6      * Higher GMIN during DC only

### 7.3 DC Sweep Direction Matters
* Sweeping forward (0 ? VDD) vs reverse (VDD ? 0) can give different results for bistable circuits
* SRAM example: sweeping VDD down shows retention point, sweeping up shows trip point

* Sweep BOTH directions:
.DC VDD 0 1 0.01           * Forward sweep
.MEASURE DC VTRIP_FW V(VVDD)
.ALTER case=reverse
    .DC VDD 1 0 -0.01      * Reverse sweep
    .MEASURE DC VTRIP_RV V(VVDD)

### 7.4 Avoiding DC Convergence Failures
| Technique | Syntax | When |
|-----------|--------|------|
| Source stepping | .DC VDD 0 1 0.01 | Always (gradual ramp is safest) |
| GMIN stepping | .OPTIONS GMINSTEPS=10 | Persistent DC failures |
| .NODESET | .NODESET V(OUT)=0.5*VDD | Circuits with feedback |
| DCON option | .OPTIONS DCON=1 | Enable continuation method |
| Change sweep variable | Use current source instead | Voltage-controlled loops |

### 7.5 DC Sweep of SRAM Butterfly Curve
* Butterfly curve requires two DC sweeps per VDD
* Difficulty: SRAM flips at trip point ? convergence difficult near trip

* Solution: use bisection method with .NODESET at each step
.PARAM VOFFSET=0
V_VVDD_SRC VVDD VVDD_EXT DC=0
VVDD2_SRC VVDD2 0 DC=0
.DC VOFFSET -0.2 0.2 0.01
.NODESET V(VVDD)=VDD V(VVDD2)=0

---

## 8. Transient Convergence

### 8.1 Transient-Specific Convergence Options
| Option | Default | Description |
|--------|---------|-------------|
| ITL4 | 10 | Max iterations per time point |
| ITL4_TIM | 0 | Max total transient rejections (0=unlimited) |
| MAXORD | 2 | Max integration order |
| DELMAX | (auto) | Maximum allowed time step |
| DELMIN | 0 | Minimum allowed time step |
| PROBE | 0 | Output all nodes (1=subset, faster convergence) |
| CONVERGE | 0 | Convergence force (1=helps tough circuits) |

### 8.2 Controlling Time Step
* Maximum time step prevents HSPICE from skipping over transitions:
.TRAN 0.1P 1N              * Step=0.1ps, Stop=1ns
* OR:
.TRAN 1P 1N SWEEP OPT...    * Use 1ps step; adjust if needed

* Problem: 0.1P (0.1fs) creates many points ? slow
* Solution: use .OPTIONS DELMAX=1P to set max step without .TRAN step

.OPTIONS DELMAX=1P          * Max step = 1ps
.TRAN 1P 1N                 * Step=1ps (approximate), max=1ps

### 8.3 Transient Convergence Failure Fixes
| Symptom | Cause | Fix |
|---------|-------|-----|
| \"time step too small\" | Model discontinuity | METHOD=GEAR, DELMIN=1E-18 |
| Oscillation at settle | Trapezoidal ringing | METHOD=GEAR MAXORD=2 |
| Slow simulation | Too many timesteps | DELMAX=0.1*PERIOD (relax) |
| Bypass failed | High gain/feedback | Increase ITL4 to 50 |

### 8.4 Transient with SRAM Bistable
* SRAM starts metastable without .IC ? convergence fails
* Fix: always provide .IC for storage nodes

.IC V(VVDD)=VDD V(VVDD2)=0
.TRAN 0.5P 1N

### 8.5 Transient with Write Driver
* Write driver forces BL/BLB to opposite states
* Large current spike during cell flip ? transient convergence failure
.OPTIONS METHOD=GEAR MAXORD=2 ITL4=50
* Use smaller timestep around write event

---

## 9. DC Operating Point (.OP) Convergence

### 9.1 .OP Common Failures
* .OP is the foundation for all subsequent analyses
* If .OP fails, everything fails

### 9.2 .OP Convergence Options
.OPTIONS OPTOP=1           * Use optimal .OP algorithm
.OPTIONS OPITER=0          * Skip .OP (use initial only) ? risky
.OPTIONS GMINDC=1E-6       * Higher GMIN during .OP only

### 9.3 .OP for SRAM Bistable Cell
* SRAM has 3 DC solutions: '0', '1', and metastable (VDD/2)
* HSPICE may converge to metastable state
* Solution: .NODESET

.NODESET V(VVDD)=VDD V(VVDD2)=0
.OP

### 9.4 .OP Skipping
* If .OP fails but transient runs: skip .OP with UIC
.TRAN 0.5P 1N UIC       * UIC = use IC values, skip .OP

* OR:
.OPTIONS OPITER=0         * Skip .OP calculation
.TRAN 0.5P 1N

### 9.5 .OP for Feedback Circuits
* Op-amps, sense amps with feedback ? .OP fails due to high gain
* Solution: break feedback with .NODESET, converge DC, then release
.NODESET V(SA_OUT)=VDD V(SA_OUTB)=0
.OP

---

## 10. Common Convergence Errors and Fixes

### 10.1 Error Message Reference
| Error | Likely Cause | Fix |
|-------|-------------|-----|
| \"Can't converge DC\" | No DC solution found | .NODESET, GMIN stepping, check circuit topology |
| \"Time step too small\" | Transient convergence failure | METHOD=GEAR, increase ITL4, reduce DELMAX |
| \"Singular matrix\" | Floating node or inductor loop | Check unconnected nodes, add series R |
| \"Internal timestep too small\" | Model discontinuity | Check model parameters, use METHOD=GEAR2 |
| \"Bypass converged, internal not\" | Device model convergence issue | CDS=1, try different model options |
| \"GMIN stepping failed\" | Even with GMIN=1E-6 no DC | Check circuit topology, floating nodes |
| \"DC diverged\" | Solution diverges with each iteration | .NODESET, reduce source step size |
| \"No convergence in .DC\" | Sweep through region with no solution | Add .NODESET at each step, use DCON |

### 10.2 Floating Node Detection
* Symptoms: \"singular matrix\", \"zero diagonal\"
* Check: list of all nodes from .lis file

.OPTIONS LIST=1 NODE=1     * Full node list in .lis
* Search for nodes with no DC path to ground

* Float fix: add large resistor to ground (1G-ohm)
R_FLOAT FLOAT_NODE 0 1G

### 10.3 Model Discontinuity Fixes
* Models with piecewise-linear regions (BSIM4 C-V near Vth=0)
.OPTIONS CDS=1              * Convergent device solution
.OPTIONS METHOD=GEAR        * Stiff integration handles discontinuities
.OPTIONS RELTOL=1E-4        * Relaxed tolerance (default 1E-3 for HSPICE, relax to 1E-2)
* Note: RELTOL=1E-3 is default in HSPICE; RELTOL=1E-2 is faster but less accurate

### 10.4 Global Convergence Options (BRUTAL)
* When everything else fails ? use as LAST RESORT:
.OPTIONS ABSTOL=1E-6 VNTOL=1E-4 RELTOL=1E-3
.OPTIONS ITL1=5000 ITL2=5000 ITL4=100
.OPTIONS GMIN=1E-9 GMINDC=1E-6
.OPTIONS PIVTOL=1E-12 PIVREL=1E-4
.OPTIONS METHOD=TRAPGEAR

* Warning: relaxed accuracy, verify results against tighter settings

### 10.5 Speed vs Convergence Trade-off
| Configuration | Speed | Convergence | Accuracy | Use Case |
|-------------|-------|-------------|----------|----------|
| Default | Fast | Fair | Good | First test |
| RUNLVL=4 | Moderate | Good | High | SRAM Vmin |
| RUNLVL=6 | Slow | Excellent | Very high | Yield/Final |
| Manual (relaxed) | Very fast | Best | Low | Quick check only |
| Manual (tight) | Very slow | Excellent | Highest | Research |

---

## 11. SRAM-Specific Convergence Issues

### 11.1 Bistable Cell DC Convergence
* Problem: HSPICE finds V(VVDD)=V(VVDD2)=VDD/2 (metastable)
* Fix: always provide .NODESET or .IC

.NODESET V(VVDD)=VDD V(VVDD2)=0

### 11.2 Butterfly Curve Convergence
* Two separate DC sweeps are needed for butterfly (N-curve)

.ALTER case=butterfly_A
    V_VVDD_S VVDD 0 DC=0
    .DC V_VVDD_S 0 VDD 0.01
    .NODESET V(VVDD)=0 V(VVDD2)=VDD
    .MEASURE DC V_A V(VVDD2)

.ALTER case=butterfly_B
    V_VVDD2_S VVDD2 0 DC=0
    .DC V_VVDD2_S 0 VDD 0.01
    .NODESET V(VVDD)=VDD V(VVDD2)=0
    .MEASURE DC V_B V(VVDD)

* Convergence often fails near SNM trip point
* Fix: smaller step (0.005V), METHOD=GEAR for DC

### 11.3 Write Assist Convergence
* Negative BL or WL boost ? voltages beyond supply rail
* Convergence may fail at extreme bias points
.OPTIONS GMINSTEP=20        * More GMIN steps for wide bias range
* Use DC sweep from VDD to negative BL to find stable starting point

### 11.4 Monte Carlo Convergence
* Random variations (VTH0, U0) push devices to extreme corners
* Some MC runs may fail to converge
* Solution: .MC with FAILCALL=0 to skip failed runs

.MC 1000 RUN MEASURE IREAD FAILCALL=0 MAXFAIL=50
* FAILCALL=0: skip MC runs that fail to converge
* MAXFAIL=50: stop after 50 failed runs (prevent infinite loop)

### 11.5 Sense Amplifier Convergence
* High positive feedback ? DC convergence hard
* Solution: break feedback loop during .OP

.NODESET V(SA_OUT)=0 V(SA_OUTB)=VDD    * Force initial state
* HSPICE will converge to correct state during transient

---

## 12. Convergence Debugging Workflow

### 12.1 Step-by-Step Debug
`
Step 1: Isolate the failing analysis
  ?? .DC fails? ? skip to Step 2
  ?? .TRAN fails? ? skip to Step 4
  ?? .OP fails? ? skip to Step 3

Step 2: Fix DC sweep
  ?? Add .NODESET for critical nodes
  ?? Increase GMINDC to 1E-6
  ?? Increase ITL2 to 1000
  ?? Reduce DC step size
  ?? Use .DC ... SWEEP with source stepping (0?VDD)

Step 3: Fix .OP
  ?? Add .NODESET for all feedback nodes
  ?? Increase ITL1 to 1000
  ?? Use .OPTIONS GMINDC=1E-6

Step 4: Fix transient
  ?? Reduce DELMAX (max time step)
  ?? Change METHOD to GEAR
  ?? Increase ITL4 to 50
  ?? Add .IC for storage nodes

Step 5: Last resort
  ?? Relax RELTOL to 1E-3 (or 1E-2 for check only)
  ?? Increase GMIN to 1E-9
  ?? Enable CONVERGE=1
  ?? Use METHOD=TRAPGEAR
`

### 12.2 Checking .lis File for Clues
* The .lis file contains detailed convergence information:

.grep "convergence" output.lis
.grep "failed" output.lis
.grep "GMIN" output.lis
.grep "time step" output.lis

* Key lines to find:
`
**warning** convergence failed at step 45
**note** reducing time step to 1E-15
**error** can't converge after 500 iterations
`

### 12.3 Diagnostic Options
.OPTIONS BRIEF=1           * Shorter .lis, faster
.OPTIONS PROBE=1           * Only probe nodes with .PROBE statement > faster

* Collect convergence data:
.OPTIONS ITL1=500          * Record iteration count
* Check .lis for \"iterations = X\" at each step

---

## 13. Complete Convergence Options Quick Reference

### 13.1 Option Summary Table
| Option | Default | Range | Description |
|--------|---------|-------|-------------|
| ABSTOL | 1pA | 1f-1n | Absolute current tolerance |
| VNTOL | 1uV | 1n-1m | Absolute voltage tolerance |
| RELTOL | 0.001 | 1e-6-0.1 | Relative tolerance |
| GMIN | 1e-12 | 1e-18-1e-6 | Minimum conductance |
| GMINDC | 1e-12 | 1e-18-1e-3 | GMIN for DC only |
| GMINSTEPS | 5 | 0-50 | Number of GMIN steps |
| PIVTOL | 1e-13 | 1e-18-1e-9 | Pivot threshold |
| PIVREL | 1e-3 | 1e-6-1e-1 | Pivot relative threshold |
| ITL1 | 200 | 100-5000 | DC op point iterations |
| ITL2 | 200 | 50-5000 | DC sweep iterations |
| ITL4 | 10 | 5-100 | Transient per-point iterations |
| METHOD | 2 (TRAP) | 1-6 | Integration method |
| MAXORD | 2 | 1-6 | Integration order |
| DELMAX | auto | 1e-18-1e-9 | Max time step |
| DCON | 0 | 0/1 | DC continuation method |
| CONVERGE | 0 | 0/1 | Force convergence |
| CDS | 0 | 0/1 | Convergent device solution |

### 13.2 SRAM-Optimized Configuration
* General SRAM characterization (recommended start):
.OPTIONS RUNLVL=4 POST=2 PROBE=1 MEASOUT=1

* Transient SRAM with write assist:
.OPTIONS RUNLVL=5 METHOD=GEAR MAXORD=2 ITL4=50
.OPTIONS DELMAX=1P

* DC SRAM butterfly / N-curve:
.OPTIONS RUNLVL=4 GMINDC=1E-6 ITL2=2000
.DC V_VVDD 0 VDD 0.005

* Monte Carlo with SRAM:
.OPTIONS RUNLVL=6 METHOD=TRAP
.MC 1000 RUN MEASURE IREAD FAILCALL=0

### 13.3 Checklist for Convergence
`
Before simulation:
  [ ] All nodes have DC path to ground
  [ ] .NODESET for bistable (SRAM) nodes
  [ ] .IC for storage nodes in transient
  [ ] No floating nodes (check .lis with LIST=1)

After convergence failure:
  [ ] Check .lis for specific error
  [ ] Isolate which analysis fails (.OP / .DC / .TRAN)
  [ ] Increase iteration limits first
  [ ] Add GMIN stepping
  [ ] Try METHOD=GEAR
  [ ] Relax tolerance as last resort
`

> **Revision History**
> - 2026-06-30: Initial version. Covers RUNLVL, GMIN, ITL, METHOD, .IC/.NODESET, DC/transient/.OP convergence, SRAM-specific issues, debug workflow.
