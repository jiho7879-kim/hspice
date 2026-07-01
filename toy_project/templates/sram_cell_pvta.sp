* =============================================================================
* SRAM Cell PVTA Sweep - Toy Project
* =============================================================================
* PG-PD shared NMOS shift + PU PMOS shift + Vop sweep
* Hold SNM butterfly measurement with Monte Carlo local variation
*
* Template variables (replaced by gen_decks_pvta.py):
*   {{ COMMON_N_SHIFT }}  - PG/PD NMOS Vth shift (mV), positive = slower
*   {{ PU_SHIFT }}        - PU PMOS Vth shift (mV),    positive = slower
*   {{ VOP }}             - Operating voltage (V)
*   {{ TEMP }}            - Temperature (C)
*   {{ OUTPUT_PREFIX }}   - Job identifier for output files
*   {{ MC_RUNS }}         - Number of Monte Carlo runs
*
* MC: local variation only (global variation OFF via model selection)
* Measure: hold SNM via butterfly method (Seevinck)
* =============================================================================

* --- Options ---
.OPTIONS POST=1 PROBE=0 RUNLVL=5

* --- Temperature ---
.TEMP {{ TEMP }}

* --- Supply ---
.PARAM VDD = {{ VOP }}
VDD VDD 0 DC VDD
VSS VSS 0 DC 0

* --- Vth shifts (from template variables) ---
.PARAM COMMON_N_SHIFT = {{ COMMON_N_SHIFT }}E-3
.PARAM PU_SHIFT = {{ PU_SHIFT }}E-3

* =============================================================================
* >>> INSERT PDK MODEL LIBRARY HERE <<<
* =============================================================================
* Example (Samsung-specific):
*   .LIB 'samsung_pdk.lib' TT
*
* Use a model variant with global variation OFF (typically TT or MC_TT
* with only local mismatch enabled). Global variation will be applied
* analytically through the COMMON_N_SHIFT and PU_SHIFT parameters.
*
* Recommended setup:
*   .LIB 'samsung_mc.lib' NOM
*   .LIB 'samsung_mc.lib' MCLOCAL   (local-only MC models)
*
* =============================================================================

* =============================================================================
* >>> INSERT LOCAL MISMATCH MODEL PARAMETERS HERE <<<
* =============================================================================
* SRAM-specific mismatch sigma values (from PDK characterization):
* Example:
*   .PARAM SIGVTH_PG = 0.015  * 1-sigma Vth mismatch for PG (mV)
*   .PARAM SIGVTH_PD = 0.015  * 1-sigma Vth mismatch for PD (mV)
*   .PARAM SIGVTH_PU = 0.018  * 1-sigma Vth mismatch for PU (mV)
*
* Local variation per device (Gaussian, 3-sigma trim):
*   MN_PG: DELVTH = {GAUSS(0, SIGVTH_PG * 3)}
*   MN_PD: DELVTH = {GAUSS(0, SIGVTH_PD * 3)}
*   MP_PU: DELVTH = {GAUSS(0, SIGVTH_PU * 3)}
*
* =============================================================================

* =============================================================================
* >>> INSERT PDK DEVICE DIMENSIONS HERE <<<
* =============================================================================
* Example:
*   .PARAM W_PG = 0.22U  * access transistor width
*   .PARAM L_PG = 0.06U  * access transistor length
*   .PARAM W_PD = 0.30U  * pull-down transistor width
*   .PARAM L_PD = 0.06U  * pull-down transistor length
*   .PARAM W_PU = 0.14U  * pull-up transistor width
*   .PARAM L_PU = 0.06U  * pull-up transistor length
*
* =============================================================================

* =============================================================================
* 6T SRAM BITCELL - Transistor-level subcircuit
* =============================================================================
* Replace the model names and W/L with PDK-specific values.
* Apply COMMON_N_SHIFT to all NMOS (PG, PD) and PU_SHIFT to PMOS (PU).
*
.SUBCKT SRAM6T Q QB WL VDD VSS
* --- PG (access NMOS) - left ---
* MN_PG_L: Q <-> (internal) / gate = WL
* Replace MODEL_NAME_PG and W/L with PDK values
MN_PG_L  Q     INT_L WL   VSS  VSS MODEL_NAME_PG W=W_PG L=L_PG
+ DELVTH={GAUSS(0, SIGVTH_PG * 3)} + COMMON_N_SHIFT

* --- PG (access NMOS) - right ---
MN_PG_R  QB    INT_R WL   VSS  VSS MODEL_NAME_PG W=W_PG L=L_PG
+ DELVTH={GAUSS(0, SIGVTH_PG * 3)} + COMMON_N_SHIFT

* --- PD (pull-down NMOS) - left ---
* Replace MODEL_NAME_PD with PDK-specific NMOS model for PD
MN_PD_L  INT_L QB   VSS  VSS  VSS MODEL_NAME_PD W=W_PD L=L_PD
+ DELVTH={GAUSS(0, SIGVTH_PD * 3)} + COMMON_N_SHIFT

* --- PD (pull-down NMOS) - right ---
MN_PD_R  INT_R Q    VSS  VSS  VSS MODEL_NAME_PD W=W_PD L=L_PD
+ DELVTH={GAUSS(0, SIGVTH_PD * 3)} + COMMON_N_SHIFT

* --- PU (pull-up PMOS) - left ---
* Replace MODEL_NAME_PU with PDK-specific PMOS model for PU
MP_PU_L  INT_L QB   VDD  VDD  VDD MODEL_NAME_PU W=W_PU L=L_PU
+ DELVTH={GAUSS(0, SIGVTH_PU * 3)} + PU_SHIFT

* --- PU (pull-up PMOS) - right ---
MP_PU_R  INT_R Q    VDD  VDD  VDD MODEL_NAME_PU W=W_PU L=L_PU
+ DELVTH={GAUSS(0, SIGVTH_PU * 3)} + PU_SHIFT
.ENDS SRAM6T

* =============================================================================
* BUTTERFLY MEASUREMENT CIRCUIT (hold mode)
* =============================================================================
* Two identical cells cross-coupled for butterfly VTC measurement.
* A large isolation resistor (R_ISO) prevents the sweep source from
* shorting the cross-coupled feedback, allowing both VTCs to develop
* naturally:
*
*   VTC1: V(QB_INT) vs V(Q_INT)  - left inverter characteristic
*   VTC2: V(Q_INT)  vs V(QB_INT) - right inverter characteristic (mirrored)
*
* The hold SNM is the side of the largest square that fits between
* the two VTCs (Seevinck method).
*
* Schematic:
*   V_SWEEP --[R_ISO 1G]-- Q_INT --[Cell 1]-- QB_INT --[Cell 2]--+
*                              ^                                  |
*                              +--- internal feedback path -------+
*   R_ISO breaks the DC feedback so V_SWEEP can sweep Q_INT
*   without conflict. Cell 1's output (QB_INT) drives Cell 2's input.
*   Cell 2's output feeds back to Q_INT through the internal
*   cross-coupling but R_ISO dominates.
*
* --------------------------------------------------------------------------

* --- Hold mode: WL = VSS ---
VWL WL_INT 0 DC 0

* --- Isolation resistor between sweep source and Q_INT ---
* Prevents DC conflict between V_SWEEP and the cross-coupled feedback
R_ISO Q_DRV Q_INT 1G

* --- Two matched cells for butterfly ---
XCELL1 Q_INT  QB_INT  WL_INT VDD VSS SRAM6T
XCELL2 QB_INT Q_INT   WL_INT VDD VSS SRAM6T

* --- DC sweep source ---
V_SWEEP Q_DRV 0 DC 0

* =============================================================================
* ANALYSIS
* =============================================================================

* --- DC analysis: sweep Q from 0 to VDD ---
.DC V_SWEEP 0 VDD 0.001

* --- Monte Carlo: local variation only ---
.MC {{ MC_RUNS }} RUN

* =============================================================================
* MEASUREMENTS
* =============================================================================
* Hold SNM (butterfly method):
*   SNMR = min(SNMR_VTC1, SNMR_VTC2)
*   where SNMR_VTC1 = max over V_SWEEP of min(V(Q_INT), VDD-V(QB_INT))
*   and   SNMR_VTC2 = max over V_SWEEP of min(V(QB_INT), VDD-V(Q_INT))
*
* For a symmetric SRAM cell, both are equal, but we take the minimum
* to be robust.

* --- SNMR from VTC1 (lower-right half of butterfly) ---
.MEASURE DC SNMR_VTC1 MAX='MIN(V(Q_INT), VDD-V(QB_INT))'

* --- SNMR from VTC2 (upper-left half of butterfly) ---
.MEASURE DC SNMR_VTC2 MAX='MIN(V(QB_INT), VDD-V(Q_INT))'

* --- Hold SNMR = min of the two ---
.MEASURE DC SNMR PARAM='MIN(SNMR_VTC1, SNMR_VTC2)'

* =============================================================================
* OUTPUT
* =============================================================================

* --- Save butterfly curve data (for post-processing validation) ---
.PROBE DC V(Q_INT) V(QB_INT)

* --- Save SNMR measurement for .mt0 output ---
.PROBE DC SNMR

.END
