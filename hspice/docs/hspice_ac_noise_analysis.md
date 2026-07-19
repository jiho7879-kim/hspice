---
title: 'HSPICE AC and Noise Analysis Guide'
subtitle: '.AC Small-Signal, .NOISE, PSR, Jitter, and Frequency Response Characterization'
version: '1.0'
date: '2026-06-30'
description: 'Comprehensive HSPICE AC and noise analysis guide for SRAM peripheral circuits and transistor-level blocks. Covers .AC frequency sweep, .NOISE output/input-referred noise, power supply rejection (PSR), jitter from phase noise, and small-signal parameter extraction.'
tags: [HSPICE, AC analysis, noise, PSR, jitter, small-signal, frequency response]
language: 'HSPICE'
keywords: [AC analysis, .AC, .NOISE, power supply rejection, PSR, jitter, phase noise, flicker noise, thermal noise, small-signal, frequency response]
---

# HSPICE AC and Noise Analysis Guide

> **Purpose**: HSPICE small-signal AC and noise characterization for SRAM peripheral circuits and basic analog blocks.
> **Coverage**: .AC frequency response, .NOISE (thermal/flicker/shot), PSR/PSRR, jitter from phase noise, small-signal parameter extraction (gain, BW, PM, GM).
> **Target**: Sense amplifiers, write drivers, reference generators, I/O circuits.

---

## Table of Contents

1. [AC Analysis Fundamentals](#1-ac-analysis-fundamentals)
2. [.AC Statement Syntax](#2-ac-statement-syntax)
3. [Small-Signal Parameter Extraction](#3-small-signal-parameter-extraction)
4. [.NOISE Analysis](#4-noise-analysis)
5. [Noise Sources: Thermal, Flicker, Shot](#5-noise-sources-thermal-flicker-shot)
6. [Power Supply Rejection (PSR/PSRR)](#6-power-supply-rejection-psrpsrr)
7. [Jitter and Phase Noise Analysis](#7-jitter-and-phase-noise-analysis)
8. [AC Analysis of Sense Amplifiers](#8-ac-analysis-of-sense-amplifiers)
9. [Frequency Response of SRAM Read Path](#9-frequency-response-of-sram-read-path)
10. [Complete AC/Noise Workbench](#10-complete-acnoise-workbench)
11. [References](#11-references)

---

## 1. AC Analysis Fundamentals

### 1.1 What AC Analysis Does
- Computes small-signal frequency response of a linearized circuit
- .AC runs after .OP (DC operating point)
- All nonlinear devices are linearized at the DC bias point
- Output: magnitude and phase vs frequency

### 1.2 When to Use AC Analysis
| Application | Purpose | Measurement |
|-------------|---------|-------------|
| Sense amplifier bandwidth | Find -3dB frequency of SA gain | .AC V(OUT)/V(IN) |
| Write driver frequency response | Bandwidth of write buffer | .AC V(BL)/V(IN) |
| Power supply rejection | VDD noise attenuation to output | .AC V(OUT)/V(VDD) |
| Op-amp/Comparator | Gain, phase margin, GBW | .AC V(OUT)/V(IN,INN) |
| Noise optimization | Find dominant noise contributors | .NOISE V(OUT) |
| PLL/VCO phase noise | Jitter from phase noise spectrum | .NOISE + integration |

### 1.3 AC Analysis Prerequisites
.OP                    * Required: computes DC operating point
.AC DEC 10 1K 10G      * Frequency sweep: 1KHz to 10GHz, 10 points/decade

* AC stimulus: use AC=1 on the source
VIN IN 0 DC=0.8 AC=1    * DC=0.8V, AC amplitude=1V (small-signal)

---

## 2. .AC Statement Syntax

### 2.1 Frequency Sweep Types
| Type | Syntax | Description | Best For |
|------|--------|-------------|----------|
| DEC | DEC N Fstart Fstop | N points per decade | Wideband (1Hz-10GHz) |
| OCT | OCT N Fstart Fstop | N points per octave | Narrowband audio/RF |
| LIN | LIN N Fstart Fstop | N total points | Linear sweep, fine near resonance |

* Examples:
.AC DEC 10 1K 1G        * 10 points/decade, 1KHz to 1GHz ? 60 points
.AC LIN 1000 1MEG 10MEG * 1000 points, 1MHz-10MHz (fine for PSR)
.AC OCT 5 100K 100M     * 5 points/octave ? ~50 points

### 2.2 Recommended AC Sweep Settings
| Circuit Type | Sweep | Reason |
|-------------|-------|--------|
| Sense amplifier | DEC 20 1K 10G | Need high resolution near bandwidth |
| Write driver | DEC 10 1K 1G | Moderate bandwidth, low resolution OK |
| Power supply (PSR) | DEC 20 1 10G | Wide range: DC to GHz |
| Ring oscillator | DEC 10 10M 100G | Need oscillation frequency resolution |
| Reference/bias | DEC 10 1 100M | Low-frequency dominant |

### 2.3 AC Measurement Syntax
* Voltage gain (magnitude and phase)
.MEASURE AC AVG_MAG MAX V(OUT)        * Error: wrong ? use DB or MAG
.MEASURE AC AVG_DB DB(V(OUT)/V(IN))   * Correct: gain in dB

* Correct forms:
.MEASURE AC GAIN_DB   DB(V(OUT))               * Single-ended, dB
.MEASURE AC GAIN_MAG  MAG(V(OUT)/V(IN))         * Voltage gain magnitude
.MEASURE AC GAIN_PH   VP(V(OUT)/V(IN))          * Voltage gain phase (deg)
.MEASURE AC GAIN_IMAG IMAG(V(OUT)/V(IN))        * Imaginary part
.MEASURE AC GAIN_REAL REAL(V(OUT)/V(IN))        * Real part

### 2.4 Bandwidth and Gain Measurement
* Find -3dB frequency from DC gain
.MEASURE AC GAIN_DC   DB(V(OUT)/V(IN)) AT=1K    * DC gain (at 1KHz)
.MEASURE AC GAIN_DB   FIND V(OUT) WHEN MAG(V(OUT))=PARAM('GAIN_MAG_DC * 0.707')

* OR using RISE/FALL on .AC:
.MEASURE AC BW_3DB    WHEN DB(V(OUT)/V(IN)) = PARAM('GAIN_DC - 3') RISE=1

* Unity-gain bandwidth (UGB):
.MEASURE AC UGB       WHEN DB(V(OUT)/V(IN)) = 0 FALL=1

* Phase margin at UGB:
.MEASURE AC PM        FIND VP(V(OUT)/V(IN)) WHEN DB(V(OUT)/V(IN))=0
.MEASURE AC PM_DEG    PARAM='180 + PM'       * Phase margin in degrees

### 2.5 Differential Measurements
* Differential gain: V(OUT,OUTB) / V(IN,INB)
.MEASURE AC DIFF_GAIN_DB DB(V(OUT,OUTB)/V(IN,INB))

* Common-mode gain:
.MEASURE AC CM_GAIN_DB DB(V(OUT)/V(IN,INB))

* CMRR = differential gain / common-mode gain:
.MEASURE AC CMRR_DB PARAM='DIFF_GAIN_DB - CM_GAIN_DB'

---

## 3. Small-Signal Parameter Extraction

### 3.1 Transistor Small-Signal Parameters
* From .OP, HSPICE outputs gm, gds, gmb, Cgs, Cgd, Cdb in .lis file

.OP
.SAVE OPSORT=ALL         * Full operating point info

* Or extract explicitly:
.MEASURE DC GM_PARAM  DERIV I(M1)                   * gm = dId/dVgs
.MEASURE DC GDS_PARAM DERIV I(M1)                   * gds = dId/dVds
.MEASURE DC GMB_PARAM DERIV I(M1)                   * gmb = dId/dVbs

* Intrinsic gain:
.MEASURE DC AV_INT_PARAM PARAM='GM_PARAM / GDS_PARAM'

### 3.2 Small-Signal Model Extraction (gm, ro, Cgg)
* Use .AC on a single transistor
* File: ss_device_char.sp

M1 D G S 0 NMOS W=1U L=20N
* Bias
VD D 0 DC=VDD
VG G 0 DC=VDD
VS S 0 DC=0
VB B 0 DC=0

.OP
.AC DEC 10 1K 10G

* gm extraction
.MEASURE AC GM_AC IMAG(I(D)) / 6.283     * See note below
* Note: for single-transistor, gm dominates imaginary part of Y21

* Output resistance
.MEASURE AC ROUT_PARAM 1/REAL(Y(D))       * 1/gds at low frequency

* Input capacitance (Cgg)
.MEASURE AC CGG IMAG(Y(G)) / (6.283*FREQ)  * Cgg from Y-parameters

### 3.3 Y-Parameter Extraction
* HSPICE can directly output Y-parameters:
.AC DEC 10 1K 10G
.PRINT AC Y11(M1) Y12(M1) Y21(M1) Y22(M1)

* Key metrics:
* ft = gm / (2*pi*Cgg) ? transition frequency
* fmax = ft / sqrt(4*Rg*(gds+2*pi*ft*Cgd)) ? max oscillation frequency

---

## 4. .NOISE Analysis

### 4.1 .NOISE Syntax
.NOISE V(OUTPUT, REF) INPUT N [INTERVAL=SKIP]

| Parameter | Description | Example |
|-----------|-------------|---------|
| V(OUTPUT,REF) | Output node pair | V(OUT,0) or V(OUT,IN) |
| INPUT | Input source (for gain normalization) | VIN |
| N | Points per summary interval | DEC 10 |
| INTERVAL | Summary frequency interval | SKIP (output per decade) |

* Basic example:
.AC DEC 10 1K 10G
.NOISE V(OUT,0) VIN DEC 10 1K 10G

### 4.2 Noise Measurement
* Integrated output noise (RMS)
.MEASURE NOISE ONOISE_RMS INTEG ONOISE FROM=1K TO=10G
* ONOISE = total output noise density (V/?Hz)

* Input-referred noise (RMS)
.MEASURE NOISE INOISE_RMS INTEG INOISE FROM=1K TO=10G
* INOISE = total input-referred noise density (V/?Hz)

* Peak noise density
.MEASURE NOISE ONOISE_PEAK MAX ONOISE

* Spot noise at specific frequency
.MEASURE NOISE ONOISE_1MHZ FIND ONOISE AT=1MEG

### 4.3 Noise Contribution Summary
.NOISE V(OUT)R1 0 VIN DEC 10 1K 10G
* Prints in .lis: each device's noise contribution as % of total

* To get device-by-device breakdown:
* Check .lis file for:
`
** noise contributions **
  Device    Param    Contribution  % of Total
  M1        M1:flicker  2.34E-09   45.2%
  M2        M2:thermal  1.89E-09   36.5%
  R1        R1:thermal  0.95E-09   18.3%
`

### 4.4 Noise Bandwidth
* Noise bandwidth = (pi/2) * f_3dB for single-pole system
* Used to convert spot noise to RMS noise:
* Vn_rms = sqrt(? Sn(f) df) ? sqrt(Sn_DC * NBW)

.MEASURE AC BW_3DB WHEN DB(V(OUT)/V(IN)) = PARAM('GAIN_DC - 3') RISE=1
.MEASURE PARAM NBW PARAM='1.571 * BW_3DB'

---

## 5. Noise Sources

### 5.1 Thermal Noise (Resistors)
* In HSPICE: automatically included in .NOISE
* Power spectral density: Sv = 4kTR (V?/Hz)

* To manually model a noiseless resistor with specific noise:
R_NOISY N1 N2 10K NOISESCAL=2    * 2x thermal noise

* Or check thermal noise contribution:
* In .lis output:
`
R1  thermal  4.07E-18 V?/Hz  (10Kohm @ 300K)
`

### 5.2 Flicker Noise (1/f)
* MOSFET flicker noise model:
* Parameter KF, AF, EF in .MODEL
.MODEL NMOS nmos
+ KF = 1E-25     * Flicker noise coefficient
+ AF = 1.0       * Flicker noise exponent (typical 0.5-2.0)
+ EF = 1.0       * Frequency exponent (1.0 = ideal 1/f)

* Flicker corner frequency:
* Where 1/f noise = thermal noise
* Typically 1KHz to 100MHz in nanoscale CMOS

### 5.3 Shot Noise
* In HSPICE: included automatically for p-n junctions and BJTs
* For MOSFETs: shot noise is negligible (subthreshold region only)

### 5.4 Total RMS Noise Integration
* File: noise_integration.sp
.AC DEC 20 1 10G
.NOISE V(OUT,0) VIN DEC 20 1 10G

* Integrated noise in bands:
.MEASURE NOISE VN_1M_1G INTEG ONOISE FROM=1MEG TO=1GEG
.MEASURE NOISE VN_DC_1G INTEG ONOISE FROM=1 TO=1GEG
.MEASURE NOISE VN_TOTAL_RMS PARAM='SQRT(VN_DC_1G)'   * Total RMS noise

### 5.5 Signal-to-Noise Ratio (SNR)
* For a given signal swing:
.MEASURE PARAM VIN_SWING=0.5    * 0.5V signal swing
.MEASURE PARAM SNR_PARAM PARAM='20*LOG10(VIN_SWING / VN_TOTAL_RMS)'
.MEASURE PARAM SNR_DB PARAM='SNR_PARAM'

---

## 6. Power Supply Rejection (PSR/PSRR)

### 6.1 PSR Definition
PSR = Vout_ac / Vdd_ac (how much supply noise couples to output)
PSRR = 20*log10(Amplifier gain / PSR) = Av_differential / PSR

### 6.2 PSR Measurement
* Inject AC on VDD, measure output
* File: psr_measurement.sp

* Supply with AC perturbation
VDD_SRC VDD 0 DC=0.8 AC=1      * 1V AC on supply

* Circuit under test (sense amplifier or buffer)
XSA OUT OUTB BL BLB SA_EN VDD VSS SA_LATCH

.OP
.AC DEC 20 1 10G

* PSR = V(OUT) / V(VDD)
.MEASURE AC PSR_DB DB(V(OUT))              * PSR in dB
.MEASURE AC PSR_AT_1MHZ DB(V(OUT)) AT=1MEG

* PSRR = V(OUT)/V(IN)  -  V(OUT)/V(VDD) when both measured

### 6.3 PSRR Measurement (Single-Ended Output)
VIN IN 0 DC=0.8 AC=1        * Signal input
VDD_SRC VDD 0 DC=0.8 AC=1   * Supply with AC

.AC DEC 20 1 10G

* Gain from input
.MEASURE AC AV_DB DB(V(OUT)/V(IN))

* Gain from supply (PSR)
.MEASURE AC PSR_DB DB(V(OUT)/V(VDD))

* PSRR = AV - PSR (in dB)
.MEASURE AC PSRR_DB PARAM='AV_DB - PSR_DB'

### 6.4 PSR Optimization Goals
| Frequency Range | PSR Target | Dominant Coupling |
|-----------------|------------|-------------------|
| DC - 1KHz | < -80dB | Device mismatch (DC offset) |
| 1KHz - 1MHz | < -60dB | Power supply rejection ratio |
| 1MHz - 100MHz | < -40dB | Capacitive coupling through Cgd |
| 100MHz - 10GHz | < -20dB | Substrate coupling, inductance |

### 6.5 PSR with Decoupling
* Simulate with realistic decoupling cap
CDEC VDD VSS 10P          * 10pF on-chip decap

.AC DEC 20 1MEG 10G
.MEASURE AC PSR_WITH_DEC DB(V(OUT)/V(VDD))

* Compare: PSR improves at high frequencies with decap

---

## 7. Jitter and Phase Noise Analysis

### 7.1 Jitter from Noise (Transient Method)
* Inject noise on threshold and measure timing variation

* File: jitter_from_noise.sp
.PARAM VDD=0.8

* Inverter chain with noisy supply
VDD_SRC VDD 0 DC=0.8
+ SIGNAL='SIN(0.8 0.01 1MEG 0 0 0)'   * 10mV sinusoidal noise on VDD

XINV1 IN MID VDD VSS INV
XINV2 MID OUT VDD VSS INV

VIN IN 0 PULSE(0 VDD 0 10P 10P 500P 1N)

.TRAN 0.5P 10N

* Measure jitter as delay variation
.MEASURE TRAN TDELAY_NOM TRIG V(IN) VAL='VDD*0.5' RISE=1
+                         TARG V(OUT) VAL='VDD*0.5' FALL=1
* Repeat for each edge ? jitter = std of many TDELAY measurements

### 7.2 Phase Noise from .NOISE (Oscillator)
* Phase noise = frequency-domain view of jitter
* For oscillators: .NOISE on oscillator output gives phase noise

.SUBCKT INV IN OUT VDD VSS
MP OUT IN VDD VDD PMOS W=200N L=30N
MN OUT IN VSS VSS NMOS W=100N L=30N
.ENDS INV

* 31-stage ring oscillator
.IC V(IN1)=VDD
XINV1 IN1 IN2 VDD VSS INV
...
XINV31 IN31 IN1 VDD VSS INV

.OPTIONS PROBE=1 POST=2 RUNLVL=5
.TRAN 0.1P 10N UIC

* Find oscillation frequency
.MEASURE TRAN F_OSC ...

* Then AC + noise analysis around oscillation
.AC DEC 10 F_OSC 10*F_OSC
.NOISE V(IN1) VDD DEC 10 F_OSC 10*F_OSC

* Phase noise at offset frequencies
.MEASURE NOISE PN_1MHZ FIND ONOISE AT='F_OSC + 1MEG'
.MEASURE NOISE PN_10MHZ FIND ONOISE AT='F_OSC + 10MEG'

### 7.3 RMS Jitter from Phase Noise
* Convert phase noise to jitter:
* RMS jitter = (1 / (2*pi*F_osc)) * sqrt(2 * ? L(f) df)
* Where L(f) = phase noise power spectral density

* Approximate for white noise region:
.MEASURE PARAM JITTER_RMS PARAM='1/(6.283*F_OSC) * SQRT(PN_1MHZ * 1MEG)'

### 7.4 Supply-Induced Jitter
* Jitter caused by VDD noise is dominant in digital circuits
* Sensitivity: K_vdd = d(delay) / d(VDD) (ps/V)

* .DC sweep to find:
.DC VDD 0.7 0.9 0.01
.MEASURE DC TDELAY_VDD ...
.MEASURE DC K_VDD DERIV TDELAY_VDD
* K_VDD = delay sensitivity to VDD (s/V)

---

## 8. AC Analysis of Sense Amplifiers

### 8.1 Latch-Type SA Small-Signal Model
* Latch-type sense amplifier has positive feedback
* Small-signal gain = gm * ro / (1 - gm_cross * ro) ? regenerative gain
* AC analysis must be done with SA_EN asserted

* File: sa_ac_char.sp
.SUBCKT SA_LATCH BL BLB OUT OUTB SA_EN VDD VSS
* Precharge/Enable
MP1 OUT SA_EN VDD VDD PMOS_SA W=400N L=30N
MP2 OUTB SA_EN VDD VDD PMOS_SA W=400N L=30N
* Input diff pair
MN1 OUT BL VSS VSS NMOS_SA W=200N L=30N
MN2 OUTB BLB VSS VSS NMOS_SA W=200N L=30N
* Regenerative cross-couple
MP3 OUT OUTB VDD VDD PMOS_SA W=200N L=30N
MP4 OUTB OUT VDD VDD PMOS_SA W=200N L=30N
MN3 OUT OUTB NS NS NMOS_SA W=200N L=30N
MN4 OUTB OUT NS NS NMOS_SA W=200N L=30N
.ENDS SA_LATCH

* Instantiate
XSA BL BLB OUT OUTB VDD 0 0 SA_LATCH
* BL/BLB with DC offset (Delta_V)
VBL BL 0 DC=0.78 AC=1           * Input signal: BL < VDD
VBLB BLB 0 DC=0.8               * BLB = VDD (reference)

* Enable SA
VSAEN SA_EN 0 DC=VDD             * SA_EN = high (active)

.OP
.AC DEC 10 1K 10G

* SA differential gain
.MEASURE AC SA_GAIN_DB DB(V(OUT,OUTB)/V(BL,BLB))

* SA bandwidth
.MEASURE AC SA_BW_3DB WHEN DB(V(OUT,OUTB)/V(BL,BLB)) =
+ PARAM('SA_GAIN_DB - 3') RISE=1

* SA propagation delay estimate from bandwidth
.MEASURE PARAM SA_TD_PARAM PARAM='0.35 / SA_BW_3DB'
* td ? 0.35 / f_3dB for single-pole system

### 8.2 SA Input Offset from Mismatch
* SA offset voltage determines required BL differential
* .AC alone cannot model offset (it's a DC mismatch effect)
* Use .DC to find:

* Sweep BL offset to find trip point
VBL BL 0 DC='0.8 - VOS'
VBLB BLB 0 DC=0.8
.DC VOS -0.05 0.05 0.001
.MEASURE DC SA_OFFSET FIND VOS WHEN V(OUT)=V(OUTB) CROSS=1

### 8.3 SA Enable Response Time
* SA_EN rising to output valid
* Use .TRAN with AC-like small signal

---

## 9. Frequency Response of SRAM Read Path

### 9.1 Read Path Small-Signal Model
* Read path = WL driver + bitcell pass-gate + BL + SA
* Dominant poles: BL capacitance + SA input capacitance

### 9.2 Read Path AC Measurement
VWL WL 0 DC=0.8 AC=1        * AC on WL (small variation)
VBL BL 0 DC=0.8              * BL precharged

* 6T bitcell discharging
M5 BL WL VVDD 0 NMOS_SRAM W=160N L=30N
...
* SA load
CSA SA_IN 0 20F              * SA input capacitance

.OP
.AC DEC 10 1K 10G

* WL to SA input transfer function
.MEASURE AC READ_PATH_GAIN DB(V(SA_IN)/V(WL))
.MEASURE AC READ_PATH_BW WHEN DB(V(SA_IN)/V(WL)) = PARAM('READ_PATH_GAIN - 3') RISE=1

### 9.3 BL Impedance Characterization
* BL impedance affects read speed and bandwidth
* Use .AC to find BL impedance:

.AC DEC 10 1K 10G
.MEASURE AC ZBL_AT_1GHZ MAG(V(BL)/I(VBL))
.MEASURE AC ZBL_DC MAG(V(BL)/I(VBL)) AT=1K

---

## 10. Complete AC/Noise Workbench

### 10.1 SA AC + Noise Workbench
* File: sa_ac_noise_workbench.sp
.OPTIONS POST=2 PROBE=1 RUNLVL=5 MEASOUT=1
.TEMP 25

* === PARAMETERS ===
.PARAM VDD=0.8
.PARAM DELTA_V=0.05       * BL differential voltage

* === SUPPLIES ===
VDD_SRC VDD 0 DC='VDD'

* === SENSE AMPLIFIER ===
XSA BL BLB OUT OUTB VDD 0 0 SA_LATCH

* === BIAS ===
VBL BL 0 DC='VDD - DELTA_V' AC=1    * Signal on BL
VBLB BLB 0 DC='VDD'                  * Reference on BLB
VSAEN SA_EN 0 DC='VDD'               * SA enabled

* === ANALYSES ===
.OP
.AC DEC 20 10 10G
.NOISE V(OUT,OUTB) VBL DEC 20 10 10G

* === AC MEASUREMENTS ===
.MEASURE AC GAIN_DC DB(V(OUT,OUTB)/V(BL,BLB)) AT=10
.MEASURE AC GAIN_PEAK MAX DB(V(OUT,OUTB)/V(BL,BLB))
.MEASURE AC BW_3DB WHEN DB(V(OUT,OUTB)/V(BL,BLB)) =
+ PARAM('GAIN_DC - 3') RISE=1
.MEASURE AC UGB WHEN DB(V(OUT,OUTB)/V(BL,BLB)) = 0 FALL=1
.MEASURE AC PHASE_MARGIN FIND VP(V(OUT,OUTB)/V(BL,BLB)) WHEN
+ DB(V(OUT,OUTB)/V(BL,BLB)) = 0
.MEASURE AC PM_DEG PARAM='180 + PHASE_MARGIN'

* === NOISE MEASUREMENTS ===
.MEASURE NOISE ONOISE_RMS INTEG ONOISE FROM=1K TO=10G
.MEASURE NOISE INOISE_RMS INTEG INOISE FROM=1K TO=10G
.MEASURE NOISE ONOISE_1M FIND ONOISE AT=1MEG
.MEASURE NOISE ONOISE_10M FIND ONOISE AT=10MEG

* === PSR MEASUREMENT ===
.ALTER case=psr
    VDD_SRC VDD 0 DC='VDD' AC=1    * AC on supply
    VBL BL 0 DC='VDD - DELTA_V'     * No AC on signal
    .MEASURE AC PSR_DB DB(V(OUT,OUTB))
    .MEASURE AC PSRR_DB PARAM='GAIN_DC - PSR_DB'

* === CORNER SWEEP ===
.ALTER case=SS_125
    .LIB models_ss.lib SS
    .TEMP 125
.ALTER case=FF_m40
    .LIB models_ff.lib FF
    .TEMP -40

.END

### 10.2 AC/Noise Quick Reference
| Measurement | Syntax | Description |
|-------------|--------|-------------|
| Gain | DB(V(OUT)/V(IN)) | Voltage gain in dB |
| Phase | VP(V(OUT)/V(IN)) | Phase shift in degrees |
| Bandwidth | WHEN DB(...)=GAIN_DC-3 | -3dB frequency |
| UGB | WHEN DB(...)=0 | Unity-gain bandwidth |
| Phase margin | 180 + VP at UGB | Stability margin |
| Output noise | INTEG ONOISE | RMS output noise |
| Input noise | INTEG INOISE | RMS input-referred noise |
| Spot noise | FIND ONOISE AT=f | Noise density at f |
| PSRR | AV_DB - PSR_DB | Power supply rejection |

### 10.3 Typical Values (7nm FinFET SA)
| Parameter | Typical | Conditions |
|-----------|---------|------------|
| SA gain | 20-40 dB | DC gain of latch |
| SA bandwidth | 1-10 GHz | 7nm FinFET |
| SA offset | 5-30 mV | 1-sigma mismatch |
| Input noise | 10-50 uVrms | 1Hz-10GHz integrated |
| PSRR at DC | >60 dB | With decoupling |
| PSRR at 1GHz | 10-20 dB | Capacitive coupling |

> **Revision History**
> - 2026-06-30: Initial version. Covers .AC, .NOISE, PSR, jitter, SA AC characterization, read path frequency response.
