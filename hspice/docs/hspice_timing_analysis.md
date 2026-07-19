---
title: 'HSPICE Transient Timing Analysis Guide for SRAM'
subtitle: 'Read Access, Write Timing, Sense-Amplifier Characterization, Ring Oscillators, and Edge Rate Measurement'
version: '1.0'
date: '2026-06-30'
description: 'Comprehensive HSPICE transient timing analysis guide for SRAM read/write characterization. Covers read access time, write completion time, sense-amplifier timing, setup/hold, ring oscillator frequency, delay chains, and edge rate/slew measurement with complete .MEASURE syntax.'
tags: [HSPICE, timing, transient, SRAM, read access, write time, sense amplifier, ring oscillator, delay, slew]
language: 'HSPICE'
keywords: [timing analysis, read access time, write time, sense amplifier, TRIG, TARG, ring oscillator, FO4, delay, slew, .MEASURE TRAN]
---

# HSPICE Transient Timing Analysis Guide for SRAM

> **Purpose**: Complete HSPICE transient timing analysis for SRAM read/write paths and basic logic gates.
> **Coverage**: Read access, write completion, sense-amplifier timing, setup/hold, ring oscillator, FO4 delay, edge rate.
> **Target**: TR-level timing characterization for SRAM bitcell, mini-array, and peripheral circuits.

---

## Table of Contents

1. [Transient Analysis Overview](#1-transient-analysis-overview)
2. [TRIG/TARG Measurement Fundamentals](#2-trigtarg-measurement-fundamentals)
3. [Read Access Time Characterization](#3-read-access-time-characterization)
4. [Write Completion Time Characterization](#4-write-completion-time-characterization)
5. [Sense-Amplifier Timing](#5-sense-amplifier-timing)
6. [Setup and Hold Time Characterization](#6-setup-and-hold-time-characterization)
7. [Ring Oscillator Frequency and Delay](#7-ring-oscillator-frequency-and-delay)
8. [Inverter Chain and FO4 Delay](#8-inverter-chain-and-fo4-delay)
9. [Edge Rate and Slew Measurement](#9-edge-rate-and-slew-measurement)
10. [Minimum Wordline Pulse Characterization](#10-minimum-wordline-pulse-characterization)
11. [Timing Derating and PVT Corners](#11-timing-derating-and-pvt-corners)
12. [Complete Timing Workbench Template](#12-complete-timing-workbench-template)
13. [References](#13-references)

---

## 1. Transient Analysis Overview

### 1.1 When to Use Transient Timing Analysis
- **Read access**: Time from WL assertion to sense-amp output valid
- **Write timing**: Time for bitcell to flip after WL assertion
- **Sense-amp**: Enable-to-output delay, offset voltage
- **Delay chains**: Inverter/buffer delay for peripheral circuits
- **Ring oscillators**: Process monitor, FO4 delay extraction
- **Pulse width**: Minimum WL pulse, write-assist timing
- **Power analysis**: Dynamic energy per access (avg I * VDD * time)

### 1.2 Standard HSPICE Transient Setup
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* Define stimulus
VDD_SRC VDD 0 DC=0.8
VSS_SRC VSS 0 DC=0

* WL pulse: 0 -> VDD -> 0
WL_SRC WL 0 PULSE(0 VDD 0 10P 10P 200P 1N)

* BL precharge: VDD, then release
BL_SRC BL 0 DC VDD PULSE(VDD VDD 0 10P 10P 500P 1N)

* Transient analysis
.TRAN 0.1P 1N

### 1.3 PULSE Source Syntax
PULSE(V1 V2 TD TR TF PW PER)

| Parameter | Description | Typical SRAM |
|-----------|-------------|-------------|
| V1 | Initial voltage | 0 (WL off) |
| V2 | Pulse voltage | VDD (WL on) |
| TD | Delay before first transition | 0~50ps |
| TR | Rise time (10%-90%) | 5~20ps |
| TF | Fall time (90%-10%) | 5~20ps |
| PW | Pulse width at 50% | 100~500ps |
| PER | Period | > PW + recovery |

### 1.4 Key Timing Nodes in SRAM
| Node | Role | Timing Event |
|------|------|-------------|
| WL | Wordline | Start of read/write cycle |
| BL, BLB | Bitlines | Differential development, SA trigger |
| VVDD, VVDD2 | Storage nodes | Cell flip during write |
| SA_OUT | Sense-amp output | End of read access |
| SA_EN | Sense-amp enable | Controls SA firing timing |

---

## 2. TRIG/TARG Measurement Fundamentals

### 2.1 Basic Syntax
.MEASURE TRAN NAME TRIG [NODE] VAL=[threshold] [RISE|FALL]=[#]
+                    TARG [NODE] VAL=[threshold] [RISE|FALL]=[#]

### 2.2 TRIG/TARG Options
| Option | Description | Example |
|--------|-------------|---------|
| TRIG | Start measurement trigger | TRIG V(WL) VAL='0.5*VDD' RISE=1 |
| TARG | Stop measurement target | TARG V(BL) VAL='0.9*VDD' FALL=1 |
| RISE=n | Measure on nth rising edge | RISE=1, RISE=2 |
| FALL=n | Measure on nth falling edge | FALL=1 |
| VAL=x | Threshold voltage | VAL='0.5*VDD', VAL=0.4 |
| TD=t | Time delay before measurement | TD='PER/2' |
| CROSS=n | Use nth crossing (any direction) | CROSS=2 |
| GOAL | Target value for optimization | GOAL=100P |

### 2.3 Common Timing Thresholds
| Measurement | Typical Threshold | Note |
|------------|-------------------|------|
| WL -> BL discharge | 50% VDD (TRIG), 90% VDD (TARG) | Read access |
| WL -> SA_OUT | 50% VDD both | Full read path |
| WL -> cell flip | 50% VDD both; VVDD = VVDD2 | Write completion |
| Signal slew | 10% and 90% of swing | Edge rate |
| Propagation delay | 50% VDD both | Gate delay |

### 2.4 TRIG/TARG Pattern Examples
* Rising edge to falling edge (delay from A rise to B fall)
.MEASURE TRAN T_RISEFALL TRIG V(A) VAL='VDD*0.5' RISE=1
+                         TARG V(B) VAL='VDD*0.5' FALL=1

* First event to last event (timing window)
.MEASURE TRAN T_WINDOW TRIG V(A) VAL='VDD*0.5' RISE=1
+                       TARG V(B) VAL='VDD*0.5' RISE=1

* Multiple cycles (use RISE=n, FALL=n)
.MEASURE TRAN T_CYCLE3 TRIG V(CLK) VAL='VDD*0.5' RISE=3
+                        TARG V(CLK) VAL='VDD*0.5' RISE=4

### 2.5 Using AT and WHEN for Non-Edge Measurements
* Find value at specific absolute time
.MEASURE TRAN V_AT_1NS FIND V(BL) AT=1N

* Find time when a condition is met
.MEASURE TRAN T_DISCHARGE WHEN V(BL)=0.5*VDD
+ TD=2N RISE=1

* Find value at specific relative time
.MEASURE TRAN V_AFTER_WL AVG V(BL) FROM='TD_WL+50P' TO='TD_WL+100P'

---

## 3. Read Access Time Characterization

### 3.1 Read Path Delay Components
Total read access time = WL delay + bitline discharge + SA trigger + SA propagation + output driver

| Component | Description | Typical (65nm) |
|-----------|-------------|----------------|
| T_WL_RISE | WL signal arrival at cell | 10-50 ps |
| T_BL_DISCHARGE | BL drops from VDD to SA trigger (Delta_V) | 30-150 ps |
| T_SA_TRIGGER | SA_EN to SA output valid | 20-80 ps |
| T_OUT_DRIVER | SA output to data-out pad | 10-50 ps |

### 3.2 Read Access: WL to 90% BL Discharge
* File: sram_read_access.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* Supplies
VDD_SRC VDD 0 DC=0.8
VSS_SRC VSS 0 DC=0

* Wordline: 50ps rise, 200ps width, 1ns period
WL_SRC WL 0 PULSE(0 0.8 0 50P 50P 200P 1N)

* Bitlines: precharged to VDD
BL_SRC BL 0 DC=0.8
BLB_SRC BLB 0 DC=0.8

* 6T SRAM cell
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W=120N L=30N
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W=120N L=30N
MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W=200N L=30N
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W=200N L=30N
MPG1 BL WL VVDD VSS NMOS_SRAM W=160N L=30N
MPG2 BLB WL VVDD2 VSS NMOS_SRAM W=160N L=30N

* Load capacitance on BL
CBL BL VSS 50F

* Transient
.TRAN 0.5P 1N

* --- READ TIMING MEASUREMENTS ---

* Time from WL 50% rise to BL drops to 90% of VDD (10% discharge)
.MEASURE TRAN TREAD_90PCT
+ TRIG V(WL) VAL='0.8*0.5' RISE=1
+ TARG V(BL) VAL='0.8*0.9' FALL=1

* Time to 5% BL discharge (Delta_V = 40mV for SA trigger)
.MEASURE TRAN TREAD_DV40M
+ TRIG V(WL) VAL='0.8*0.5' RISE=1
+ TARG V(BL) VAL='0.8-0.04' FALL=1

* Time to 10% BL discharge (Delta_V = 80mV)
.MEASURE TRAN TREAD_DV80M
+ TRIG V(WL) VAL='0.8*0.5' RISE=1
+ TARG V(BL) VAL='0.8-0.08' FALL=1

* BL discharge slope (V/s) at 50% of discharge
.MEASURE TRAN BL_SLOPE DERIV OF V(BL) AT='TREAD_DV40M + 20P'

### 3.3 BL Differential Development (BL - BLB)
* Delta_V between BL and BLB for SA sensing
.MEASURE TRAN BL_DELTA_V PARAM='ABS(V(BLB) - V(BL))'
.MEASURE TRAN BL_DELTA_AT_50P FIND BL_DELTA_V AT=50P
.MEASURE TRAN BL_DELTA_AT_100P FIND BL_DELTA_V AT=100P
.MEASURE TRAN BL_DELTA_AT_200P FIND BL_DELTA_V AT=200P

* Time for Delta_V to reach SA offset + margin
.MEASURE TRAN TREAD_DELTA50M
+ TRIG V(WL) VAL='0.8*0.5' RISE=1
+ TARG BL_DELTA_V VAL=50M RISE=1

### 3.4 Full Read Path: WL to SA_OUT
* Add sense amplifier instance
.SUBCKT SA_LATCH BL BLB SA_OUT SA_EN VDD VSS
* ... latch-type sense amplifier subcircuit
.ENDS SA_LATCH

XSA BL BLB SA_OUT SA_EN VDD VSS SA_LATCH
SA_EN_SRC SA_EN 0 PULSE(0 0.8 'TREAD_DV40M + 20P' 5P 5P 100P 1N)

* Wordline to SA_OUT (full read access)
.MEASURE TRAN TREAD_ACCESS
+ TRIG V(WL) VAL='0.8*0.5' RISE=1
+ TARG V(SA_OUT) VAL='0.8*0.5' RISE=1

* WL to SA_EN timing
.MEASURE TRAN TREAD_SA_EN
+ TRIG V(WL) VAL='0.8*0.5' RISE=1
+ TARG V(SA_EN) VAL='0.8*0.5' RISE=1

* SA_EN to SA_OUT (SA propagation delay)
.MEASURE TRAN TREAD_SA_PROP
+ TRIG V(SA_EN) VAL='0.8*0.5' RISE=1
+ TARG V(SA_OUT) VAL='0.8*0.5' RISE=1

### 3.5 Temperature and Voltage Dependence
.MEASURE TRAN TREAD_HOT ...
* Access time increases ~15% at 125C vs 25C (mobility degradation)

.MEASURE TRAN TREAD_LOWV ...
* Access time increases ~40% at 0.6V vs 0.8V

---

## 4. Write Completion Time Characterization

### 4.1 Write Operation Overview
Write completion time = time from WL rising to storage nodes (VVDD, VVDD2) crossing.

### 4.2 Write Timing: WL to Cell Flip
* File: sram_write_timing.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* Supplies
VDD_SRC VDD 0 DC=0.8
WL_SRC WL 0 PULSE(0 0.8 0 10P 10P 200P 1N)

* Write drivers force BL=0.8, BLB=0 (writing '0' to VVDD2)
BL_SRC BL 0 DC=0.8
BLB_SRC BLB 0 DC=0

* 6T SRAM cell
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W=120N L=30N
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W=120N L=30N
MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W=200N L=30N
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W=200N L=30N
MPG1 BL WL VVDD VSS NMOS_SRAM W=160N L=30N
MPG2 BLB WL VVDD2 VSS NMOS_SRAM W=160N L=30N

.TRAN 0.5P 500P

* --- WRITE TIMING MEASUREMENTS ---

* Write completion: WL rise to VVDD2 = VVDD crossing
.MEASURE TRAN TWRITE_CROSS
+ TRIG V(WL) VAL='0.8*0.5' RISE=1
+ TARG V(VVDD2) VAL='0.8*0.5' RISE=1

* Write completion: to VVDD rising past 50% (cell fully flipped)
.MEASURE TRAN TWRITE_RISE
+ TRIG V(WL) VAL='0.8*0.5' RISE=1
+ TARG V(VVDD) VAL='0.8*0.5' RISE=1

* Write completion: to VVDD2 falling past 50%
.MEASURE TRAN TWRITE_FALL
+ TRIG V(WL) VAL='0.8*0.5' RISE=1
+ TARG V(VVDD2) VAL='0.8*0.5' FALL=1

* Write margin: time from cell flip to WL falling
.MEASURE TRAN TWRITE_MARGIN
+ TRIG V(VVDD) VAL='0.8*0.5' RISE=1
+ TARG V(WL) VAL='0.8*0.5' FALL=1

* Write fail check (if no crossing, TWRITE_CROSS = period)
.MEASURE TRAN TWRITE_OK PARAM='TWRITE_CROSS < 200P'

### 4.3 Write Time Components
.MEASURE TRAN TWL2PG TRIG V(WL) VAL='0.8*0.5' RISE=1
+                      TARG V(VVDD) VAL='0.8-0.1' FALL=1
* Time for pass-gate to pull down storage node

### 4.4 Write Assist Timing
* Negative bitline write assist
.MEASURE TRAN TWRITE_NBL
+ TRIG V(WL) VAL='0.8*0.5' RISE=1
+ TARG V(VVDD2) VAL='0.8*0.5' FALL=1

* Write with lowered cell supply (VDDCELL collapse)
.MEASURE TRAN TWRITE_COLLAPSE ...

### 4.5 BL Swing vs Write Time
* Measure how write time changes with BL voltage
.PARAM BL_LOW=0
BLB_SRC BLB 0 DC='BL_LOW'

.MEASURE TRAN TWRITE_BL1 ...
.ALTER case=BL0p2V
    .PARAM BL_LOW=0.2
    .MEASURE TRAN TWRITE_BL2 ...

---

## 5. Sense-Amplifier Timing

### 5.1 Latch-Type Sense Amplifier
.SUBCKT SA_LATCH BL BLB OUT OUTB SA_EN VDD VSS
MP1 OUT SA_EN VDD VDD PMOS_SA W=400N L=30N
MP2 OUTB SA_EN VDD VDD PMOS_SA W=400N L=30N
MN1 OUT BL VSS VSS NMOS_SA W=200N L=30N
MN2 OUTB BLB VSS VSS NMOS_SA W=200N L=30N
* Regenerative latch (cross-coupled)
MP3 OUT OUTB VDD VDD PMOS_SA W=200N L=30N
MP4 OUTB OUT VDD VDD PMOS_SA W=200N L=30N
MN3 OUT OUTB NS NS NMOS_SA W=200N L=30N
MN4 OUTB OUT NS NS NMOS_SA W=200N L=30N
.ENDS SA_LATCH

### 5.2 SA Timing Measurements
.MEASURE TRAN TSA_EN2OUT
+ TRIG V(SA_EN) VAL='0.8*0.5' RISE=1
+ TARG V(OUT) VAL='0.8*0.5' RISE=1

.MEASURE TRAN TSA_EN2OUTB
+ TRIG V(SA_EN) VAL='0.8*0.5' RISE=1
+ TARG V(OUTB) VAL='0.8*0.5' FALL=1

* SA resolution time (OUT - OUTB) to reach full swing
.MEASURE TRAN TSA_RESOLVE
+ TRIG V(SA_EN) VAL='0.8*0.5' RISE=1
+ TARG PARAM='ABS(V(OUT)-V(OUTB))' VAL='0.7*0.8' RISE=1

### 5.3 SA Offset Voltage Characterization
* Use .DC sweep to find input offset
BLB_SRC BLB 0 DC='0.8 - VOS'
.DC VOS -0.05 0.05 0.001
.MEASURE DC SA_OFFSET FIND VOS WHEN V(OUT)=V(OUTB) CROSS=1

### 5.4 Minimum BL Differential (SA Sensitivity)
* Minimum Delta_V for SA to resolve correctly
.MEASURE TRAN TSA_SENSE TRIG V(SA_EN) VAL='0.8*0.5' RISE=1
+                       TARG V(OUT) VAL='0.8*0.5' RISE=1
* If TSA_SENSE exceeds max limit, Delta_V is insufficient

### 5.5 SA Enable Timing Optimization
* Optimal SA_EN delay after WL (allow BL to develop sufficient Delta_V)
.MEASURE TRAN TSAE_OPTIMAL TRIG V(WL) VAL='0.8*0.5' RISE=1
+                         TARG V(SA_EN) VAL='0.8*0.5' RISE=1
* Must satisfy: V(OUT) resolves correctly AND timing meets target

---

## 6. Setup and Hold Time Characterization

### 6.1 Setup/Hold for SRAM Read
Setup time = time between BL valid and SA_EN.  
Hold time = time SA_EN must stay high after BL changes.

### 6.2 Setup Time: BL data before SA_EN
* Sweep SA_EN delay relative to WL
.PARAM SA_EN_DELAY=50P
SA_EN_SRC SA_EN 0 PULSE(0 0.8 'SA_EN_DELAY' 5P 5P 100P 1N)

.MEASURE TRAN TSETUP CHECK
+ TRIG V(SA_EN) VAL='0.8*0.5' RISE=1
+ TARG V(BL) VAL='0.8-0.05' FALL=1

* Binary search for minimum setup using optimization
.MEASURE TRAN TSETUP_MARGIN PARAM='V(OUT) - 0.4'
* When margin goes negative, setup is violated

### 6.3 Hold Time: SA_EN after BL change
.MEASURE TRAN THOLD CHECK
+ TRIG V(BL) VAL='0.8*0.5' RISE=1
+ TARG V(SA_EN) VAL='0.8*0.5' FALL=1

### 6.4 Flip-Flop Style Setup/Hold
* For register or pipeline stages in periphery
.MEASURE TRAN TSU TRIG V(D) VAL='0.8*0.5' RISE=1
+                    TARG V(CLK) VAL='0.8*0.5' RISE=1

.MEASURE TRAN THD TRIG V(CLK) VAL='0.8*0.5' RISE=1
+                   TARG V(D) VAL='0.8*0.5' RISE=1

---

## 7. Ring Oscillator Frequency and Delay

### 7.1 Ring Oscillator Basics
Ring oscillators are used to characterize:
- Stage delay (td = 1/(2 * N * f))
- FO4 delay (fanout-of-4 inverter delay)
- Process variation monitor
- Temperature/voltage dependence of logic speed

### 7.2 31-Stage Ring Oscillator
* File: ring_osc.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* Supplies
VDD_SRC VDD 0 DC=0.8
VSS_SRC VSS 0 DC=0

* Initial condition to start oscillation
.IC V(IN1)=0.8

* Inverter chain (31 stages)
XINV1 IN1 IN2 VDD VSS INV
XINV2 IN2 IN3 VDD VSS INV
XINV3 IN3 IN4 VDD VSS INV
...
* Connect last output back to first input for oscillation
XINV31 IN31 IN1 VDD VSS INV

.SUBCKT INV IN OUT VDD VSS
MP OUT IN VDD VDD PMOS_RO W=200N L=30N
MN OUT IN VSS VSS NMOS_RO W=100N L=30N
.ENDS INV

* Load capacitance (fanout = 1: same size as next stage)
CLOAD IN31 VSS 5F

.TRAN 0.1P 5N UIC

* --- RING OSCILLATOR MEASUREMENTS ---

* Period measurement (from 3rd to 4th rising edge avoids startup transient)
.MEASURE TRAN TRO_PERIOD
+ TRIG V(IN1) VAL='0.8*0.5' RISE=3
+ TARG V(IN1) VAL='0.8*0.5' RISE=4

* Frequency
.MEASURE TRAN TRO_FREQ PARAM='1 / TRO_PERIOD'

* Stage delay (N = 31 stages, 2 edges per cycle)
.MEASURE TRAN TRO_STAGE_DELAY PARAM='TRO_PERIOD / (2 * 31)'

* Average power
.MEASURE TRAN TRO_POWER AVG P(VDD_SRC) FROM='2N' TO='5N'

* Power-delay product (per stage)
.MEASURE TRAN TRO_PDP PARAM='TRO_POWER * TRO_STAGE_DELAY / 31'

### 7.3 Frequency Stability and Jitter
.MEASURE TRAN TRO_JITTER_P2P
+ TRIG V(IN1) VAL='0.8*0.5' RISE=2
+ TARG V(IN1) VAL='0.8*0.5' RISE=3
* Measure across many cycles for RMS jitter

.ALTER case=measure_jitter
    .TRAN 0.1P 100N UIC
    .MEASURE TRAN TRO_PERIOD_N ...
    * Post-process 100+ cycles for jitter statistics

### 7.4 RO Frequency PVT Dependence
.ALTER case=SS_125C
    .LIB models_ss SS
    .TEMP 125
    .TRAN 0.1P 5N UIC
    .MEASURE TRAN TRO_FREQ_SS ...

.ALTER case=FF_m40C
    .LIB models_ff FF
    .TEMP -40
    .MEASURE TRAN TRO_FREQ_FF ...

---

## 8. Inverter Chain and FO4 Delay

### 8.1 FO4 Delay Definition
FO4 = delay of an inverter driving 4 identical inverters (fanout of 4).
FO4 delay is the standard technology metric for logic speed.

### 8.2 FO4 Inverter Chain
* File: fo4_chain.sp
.SUBCKT INV_W4 IN OUT VDD VSS
MP_W4 OUT IN VDD VDD PMOS W=400N L=30N
MN_W4 OUT IN VSS VSS NMOS W=200N L=30N
.ENDS INV_W4

.SUBCKT INV_W1 IN OUT VDD VSS
MP_W1 OUT IN VDD VDD PMOS W=100N L=30N
MN_W1 OUT IN VSS VSS NMOS W=50N L=30N
.ENDS INV_W1

* Stage 1: drive W=1, load = 4x W=1 (fanout=4)
XDRV IN1 MID VDD VSS INV_W1
* Load: 4 identical inverters
XL1 MID IN2 VDD VSS INV_W1
XL2 MID IN3 VDD VSS INV_W1
XL3 MID IN4 VDD VSS INV_W1
XL4 MID IN5 VDD VSS INV_W1

VIN IN1 0 PULSE(0 0.8 0 10P 10P 100P 200P)

.TRAN 0.1P 500P

* FO4 delay measurement
.MEASURE TRAN TFO4_RISE
+ TRIG V(IN1) VAL='0.8*0.5' RISE=1
+ TARG V(MID) VAL='0.8*0.5' FALL=1

.MEASURE TRAN TFO4_FALL
+ TRIG V(IN1) VAL='0.8*0.5' FALL=1
+ TARG V(MID) VAL='0.8*0.5' RISE=1

.MEASURE TRAN TFO4_AVG PARAM='(TFO4_RISE + TFO4_FALL) / 2'

### 8.3 Inverter Propagation Delay (General)
.MEASURE TRAN TPLH TRIG V(IN) VAL='0.8*0.5' RISE=1
+                    TARG V(OUT) VAL='0.8*0.5' FALL=1

.MEASURE TRAN TPHL TRIG V(IN) VAL='0.8*0.5' FALL=1
+                    TARG V(OUT) VAL='0.8*0.5' RISE=1

.MEASURE TRAN TPLH_AVG PARAM='(TPLH + TPHL) / 2'

### 8.4 Inverter Transition Time
.MEASURE TRAN TRISE TRIG V(OUT) VAL='0.8*0.1' RISE=1
+                     TARG V(OUT) VAL='0.8*0.9' RISE=1

.MEASURE TRAN TFALL TRIG V(OUT) VAL='0.8*0.9' FALL=1
+                     TARG V(OUT) VAL='0.8*0.1' FALL=1

---

## 9. Edge Rate and Slew Measurement

### 9.1 Rise/Fall Time Definition
Rise time = time for signal to go from 10% to 90% of VDD.  
Fall time = time for signal to go from 90% to 10% of VDD.

### 9.2 Single Signal Edge Rate
.MEASURE TRAN TR_10_90 TRIG V(SIG) VAL='0.8*0.1' RISE=1
+                       TARG V(SIG) VAL='0.8*0.9' RISE=1

.MEASURE TRAN TF_90_10 TRIG V(SIG) VAL='0.8*0.9' FALL=1
+                       TARG V(SIG) VAL='0.8*0.1' FALL=1

1 NOMENCLATURE: Most foundry libraries use 10%-90% for rise and 90%-10% for fall

### 9.3 Slope (Slew Rate) in V/s
.MEASURE TRAN SLEW_RISE DERIV OF V(SIG) AT='TR_10_90'
* Instantaneous slope during transition

* Average slew rate
.MEASURE TRAN SLEW_RISE_AVG PARAM='(0.8*0.8) / TR_10_90'
* (VDD * 0.8) / (10%-90% rise time)

### 9.4 Waveform Quality Metrics
.MEASURE TRAN V_OVERSHOOT MAX V(SIG) FROM='TR_10_90' TO='TR_10_90+50P'
.MEASURE TRAN V_OVERSHOOT_PCT PARAM='100 * (V_OVERSHOOT - 0.8) / 0.8'

.MEASURE TRAN V_UNDERSHOOT MIN V(SIG) FROM='TF_90_10' TO='TF_90_10+50P'

.MEASURE TRAN V_RING AMPL V(SIG) FROM='TR_10_90+50P' TO='TR_10_90+200P'

### 9.5 Edge Rate for Multiple Nodes (Timing Arc)
* Measure input slew affecting output delay
.MEASURE TRAN TIN_SLEW TRIG V(IN) VAL='0.8*0.1' RISE=1
+                      TARG V(IN) VAL='0.8*0.9' RISE=1

.MEASURE TRAN TOUT_PROP TRIG V(IN) VAL='0.8*0.5' RISE=1
+                       TARG V(OUT) VAL='0.8*0.5' FALL=1

### 9.6 Edge Rate on Bitlines
.MEASURE TRAN TBL_RISE TRIG V(BL) VAL='0.8*0.1' RISE=1
+                      TARG V(BL) VAL='0.8*0.9' RISE=1
.MEASURE TRAN TBL_FALL TRIG V(BL) VAL='0.8*0.9' FALL=1
+                      TARG V(BL) VAL='0.8*0.1' FALL=1

* BL discharge slew rate
.MEASURE TRAN BL_DISCH_SLEW PARAM='0.8 / TBL_FALL'

---

## 10. Minimum Wordline Pulse Characterization

### 10.1 Problem
Find the minimum WL pulse width that still allows successful write.
* This defines the write timing margin.

### 10.2 Sweep WL Pulse Width
* File: sram_min_wl_pulse.sp
.OPTIONS POST=2 RUNLVL=5 MEASOUT=1
.PARAM WL_PW=200P

* WL with parameterized pulse width
WL_SRC WL 0 PULSE(0 0.8 0 10P 10P 'WL_PW' 1N)

* Write driver: writing '0'
BL_SRC BL 0 DC=0.8
BLB_SRC BLB 0 DC=0

* 6T bitcell
... (cell instantiation)

.TRAN 0.5P 1N

* Measure if write completed
.MEASURE TRAN TWRITE_END WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE TRAN WRITE_OK PARAM='TWRITE_END < WL_PW'

* Sweep WL_PW
.ALTER case=PW_150P
    .PARAM WL_PW=150P
.ALTER case=PW_120P
    .PARAM WL_PW=120P
.ALTER case=PW_100P
    .PARAM WL_PW=100P
.ALTER case=PW_80P
    .PARAM WL_PW=80P
.ALTER case=PW_60P
    .PARAM WL_PW=60P
.ALTER case=PW_40P
    .PARAM WL_PW=40P

### 10.3 Using Optimization for Minimum WL Pulse
* Alternative: use .OPTIMIZE BISECTION to find exact minimum
.PARAM WL_PW_OPT=OPT1(100P, 20P, 300P)
WL_SRC WL 0 PULSE(0 0.8 0 10P 10P 'WL_PW_OPT' 1N)

.MEASURE TRAN TWRITE_FIND WHEN V(VVDD)=V(VVDD2) CROSS=1
.MEASURE TRAN TWRITE_MARGIN PARAM='WL_PW_OPT - TWRITE_FIND'
+ GOAL=0

.MODEL WL_OPT OPT METHOD=BISECTION ITROPT=30
.TRAN 0.5P 1N OPTIMIZE=OPT1 RESULTS=TWRITE_MARGIN MODEL=WL_OPT

---

## 11. Timing Derating and PVT Corners

### 11.1 Timing Derating Factors
| Condition | Delay Scaling (typical) | Cause |
|-----------|------------------------|-------|
| VDD -10% | +25% delay | Reduced drive current |
| Temp +100C | +15% delay | Mobility degradation |
| SS process | +30% delay | Slow transistors everywhere |
| FF process | -25% delay | Fast transistors |

### 11.2 Multi-Corner Timing Measurement
.ALTER case=best
    .LIB models_ff.lib FF
    .TEMP -40
    .PARAM VDD_TYP=0.88   * +10%

.ALTER case=worst
    .LIB models_ss.lib SS
    .TEMP 125
    .PARAM VDD_TYP=0.72   * -10%

.ALTER case=typical
    .LIB models_tt.lib TT
    .TEMP 25
    .PARAM VDD_TYP=0.80

### 11.3 Timing Derating Equation for RAG
`
td_corner = td_nom * K_v * K_t * K_p
K_v = (VDD_nom / VDD_corner)^alpha    (alpha ~1.3 for velocity saturation)
K_t = 1 + TC1_delay * (T - T_nom)     (TC1_delay ~0.0015 / C)
K_p = process scaling factor           (SS ~1.3, FF ~0.75, TT ~1.0)
`

---

## 12. Complete Timing Workbench Template

### 12.1 SRAM Read/Write Timing Workbench
* File: sram_timing_workbench.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* === PARAMETERS ===
.PARAM VDD_NOM=0.8 WL_PW=200P PERIOD=1N
.PARAM WPU=120N WPD=200N WPG=160N LCELL=30N

* === SUPPLIES ===
VDD_SRC VDD 0 DC='VDD_NOM'
VSS_SRC VSS 0 DC=0

* === WORDLINE (read pulse) ===
WL_SRC WL 0 PULSE(0 VDD_NOM 0 10P 10P 'WL_PW' 'PERIOD')

* === BITLINES ===
BL_SRC BL 0 DC='VDD_NOM'
BLB_SRC BLB 0 DC='VDD_NOM'

* === 6T SRAM CELL ===
MPU1 VVDD VVDD2 VDD VDD PMOS_SRAM W={WPU} L={LCELL}
MPU2 VVDD2 VVDD VDD VDD PMOS_SRAM W={WPU} L={LCELL}
MPD1 VVDD VVDD2 VSS VSS NMOS_SRAM W={WPD} L={LCELL}
MPD2 VVDD2 VVDD VSS VSS NMOS_SRAM W={WPD} L={LCELL}
MPG1 BL WL VVDD VSS NMOS_SRAM W={WPG} L={LCELL}
MPG2 BLB WL VVDD2 VSS NMOS_SRAM W={WPG} L={LCELL}

* === LOAD ===
CBL BL VSS 50F
CBLB BLB VSS 50F

* === TRANSIENT ANALYSIS ===
.TRAN 0.5P 'PERIOD'

* === READ TIMING ===
.MEASURE TRAN TREAD_10PCT
+ TRIG V(WL) VAL='VDD_NOM*0.5' RISE=1
+ TARG V(BL) VAL='VDD_NOM*0.9' FALL=1

.MEASURE TRAN TREAD_DV50M
+ TRIG V(WL) VAL='VDD_NOM*0.5' RISE=1
+ TARG V(BL) VAL='VDD_NOM-0.05' FALL=1

.MEASURE TRAN TREAD_DV100M
+ TRIG V(WL) VAL='VDD_NOM*0.5' RISE=1
+ TARG V(BL) VAL='VDD_NOM-0.10' FALL=1

* === BL DIFFERENTIAL ===
.MEASURE TRAN BL_DELTA PARAM='ABS(V(BLB)-V(BL))'
.MEASURE TRAN TREAD_DELTA50M
+ TRIG V(WL) VAL='VDD_NOM*0.5' RISE=1
+ TARG BL_DELTA VAL=0.05 RISE=1

* === WRITE TIMING (with write driver) ===
.ALTER case=write
    BL_SRC BL 0 DC='VDD_NOM'
    BLB_SRC BLB 0 DC=0
    .MEASURE TRAN TWRITE_FLIP
    + TRIG V(WL) VAL='VDD_NOM*0.5' RISE=1
    + TARG V(VVDD) VAL='VDD_NOM*0.5' RISE=1
    .MEASURE TRAN TWRITE_MARGIN
    + TRIG V(VVDD) VAL='VDD_NOM*0.5' RISE=1
    + TARG V(WL) VAL='VDD_NOM*0.5' FALL=1

* === EDGE RATES ===
.MEASURE TRAN TR_BL TRIG V(BL) VAL='VDD_NOM*0.1' FALL=1
+                   TARG V(BL) VAL='VDD_NOM*0.9' FALL=1
.MEASURE TRAN TF_BL TRIG V(BL) VAL='VDD_NOM*0.9' RISE=1
+                   TARG V(BL) VAL='VDD_NOM*0.1' RISE=1

* === POWER ===
.MEASURE TRAN IREAD_AVG AVG I(MPG1) FROM='0.1*WL_PW' TO='0.9*WL_PW'
.MEASURE TRAN E_READ AVG P(VDD_SRC) FROM=0 TO='PERIOD'

.END

---

## 13. Quick Reference Table

### 13.1 Timing Measurement Cheat Sheet
| Measurement | TRIG | TARG | Description | Doc Section |
|-------------|------|------|-------------|-------------|
| TREAD_10PCT | WL@50% rise | BL@90% fall | Read access time (10% BL drop) | 3 |
| TREAD_DV100M | WL@50% rise | BL@VDD-0.1 fall | Time to 100mV BL drop | 3 |
| TWRITE_FLIP | WL@50% rise | VVDD@50% rise | Write completion time | 4 |
| TWRITE_MARGIN | VVDD@50% rise | WL@50% fall | Write margin after cell flip | 4 |
| TSA_PROP | SA_EN@50% rise | OUT@50% rise | SA propagation delay | 5 |
| TPLH | IN@50% rise | OUT@50% fall | Low-to-high propagation | 8 |
| TR_10_90 | SIG@10% rise | SIG@90% rise | Rise time (slew) | 9 |
| TF_90_10 | SIG@90% fall | SIG@10% fall | Fall time (slew) | 9 |
| TRO_PERIOD | RO@50% rise 3 | RO@50% rise 4 | Ring oscillator period | 7 |
| TFO4 | IN@50% rise | MID@50% fall | FO4 inverter delay | 8 |
| TSETUP | D@50% before CLK@50% | ? | Data setup time | 6 |
| THOLD | CLK@50% | D@50% after CLK | Data hold time | 6 |

### 13.2 Common Timing Issues
| Issue | Symptom | Investigation |
|-------|---------|--------------|
| Read too slow | TREAD exceeds spec | Check Iread, BL cap, WL drive |
| Write fails | TWRITE_FLIP > WL_PW | Check write margin, PG ratio |
| SA doesn't fire | OUT floats | Check SA_EN timing vs BL Delta_V |
| Ringing | Overshoot/undershoot | Check impedance matching, damping |
| Setup violation | Output wrong state | Increase SA_EN delay for Delta_V |

---

> **Revision History**
> - 2026-06-30: Initial version. Covers SRAM read/write timing, sense-amp, ring oscillator, FO4, edge rate, setup/hold.
