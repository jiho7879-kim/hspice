* =============================================================================
* SRAM MINI-ARRAY PARAMETER TEMPLATE
* =============================================================================
* Purpose: Single file collecting ALL user-configurable values for
*          mini-array peripheral simulation.
*
* How to use:
*   1. Copy this file → array_params.inc
*   2. Fill in all values marked "<<< USER:"
*   3. .INCLUDE 'array_params.inc' in your main deck
*
* Units: Si (m, F, ohm, s, V, A) unless noted
* =============================================================================


* =============================================================================
* SECTION 1: ARRAY DIMENSIONS
* =============================================================================
* Define your target array size. All RC loads scale from these.
* --- Subarray dimensions ---
.PARAM N_ROWS          = 256     <<< USER: number of rows per subarray
.PARAM N_COLS          = 64      <<< USER: number of columns per subarray
.PARAM N_COL_MUX       = 8       <<< USER: column MUX ratio (e.g., 8:1)

* --- Derived subarray counts ---
.PARAM N_SENSE         = 'N_COLS / N_COL_MUX'  * number of SAs (auto-derived)
.PARAM N_WL_STAGGER    = 4       <<< USER: WL stagger groups for ripple timing

* --- Bitcell dimensions (from PDK or layout) ---
.PARAM CELL_HEIGHT     = 0.5E-6  <<< USER: bitcell height (m)
.PARAM CELL_WIDTH      = 0.25E-6 <<< USER: bitcell width (m)


* =============================================================================
* SECTION 2: METAL PARASITICS (per process node)
* =============================================================================
* --- BL metal (typically M2, vertical routing) ---
.PARAM R_BL_PER_UM     = 10      <<< USER: BL sheet resistance (ohm/um-width)
.PARAM C_BL_WIRE_PER_UM= 0.1E-15 <<< USER: BL wire capacitance (F/um)
.PARAM C_BL_FRINGE_PER_UM=0.05E-15 <<< USER: BL fringe capacitance (F/um)
.PARAM W_BL            = 1E-6    <<< USER: BL metal width (m)

* --- WL metal strap (typically M4, horizontal) ---
.PARAM R_WL_PER_UM     = 6       <<< USER: WL sheet resistance (ohm/um-width)
.PARAM C_WL_WIRE_PER_UM= 0.12E-15 <<< USER: WL wire capacitance (F/um)
.PARAM C_WL_FRINGE_PER_UM=0.06E-15 <<< USER: WL fringe capacitance (F/um)
.PARAM W_WL            = 1E-6    <<< USER: WL metal width (m)

* --- BL-BLB coupling ---
.PARAM C_BLB_COUPLE_PER_UM=0.08E-15 <<< USER: BL-BLB coupling capacitance per um (F/um)

* --- Via/contact resistance ---
.PARAM R_VIA_BL       = 5        <<< USER: BL via resistance (ohm)
.PARAM R_VIA_WL       = 5        <<< USER: WL via resistance (ohm)


* =============================================================================
* SECTION 3: DEVICE PARASITICS (per cell, from .OP or PDK)
* =============================================================================
* --- Pass-gate (PG) ---
.PARAM C_DRAIN_PG      = 0.5E-15 <<< USER: PG drain junction capacitance (F)
.PARAM C_GD_PG         = 0.3E-15 <<< USER: PG gate-drain overlap capacitance (F)
.PARAM I_LEAK_PG       = 5E-12   <<< USER: PG off-state leakage per cell (A)

* --- Pull-down (PD) ---
.PARAM C_DRAIN_PD      = 0.8E-15 <<< USER: PD drain junction capacitance (F)

* --- Pull-up (PU) ---
.PARAM C_DRAIN_PU      = 0.5E-15 <<< USER: PU drain junction capacitance (F)

* --- Device dimensions (for mismatch sigma calculation) ---
.PARAM W_PG            = 160E-9  <<< USER: pass-gate width (m)
.PARAM W_PD            = 200E-9  <<< USER: pull-down width (m)
.PARAM W_PU            = 120E-9  <<< USER: pull-up width (m)
.PARAM L_CELL          = 30E-9   <<< USER: cell channel length (m)


* =============================================================================
* SECTION 4: PERIPHERAL CIRCUIT SIZING
* =============================================================================
* --- Precharge PMOS ---
.PARAM W_PCH           = 400E-9  <<< USER: precharge PMOS width (m)
.PARAM L_PCH           = 30E-9   <<< USER: precharge PMOS length (m)
* ron ≈ 1 / (beta * (VDD - Vth)) → adjust for 90% restore within cycle

* --- Write driver NMOS (BL pull-down) ---
.PARAM W_WD_N          = 800E-9  <<< USER: write driver NMOS width (m)
.PARAM L_WD_N          = 30E-9   <<< USER: write driver NMOS length (m)

* --- Sense amplifier ---
.PARAM W_SA_IN         = 200E-9  <<< USER: SA input pair width (m)
.PARAM W_SA_LOAD       = 400E-9  <<< USER: SA precharge PMOS width (m)
.PARAM W_SA_CROSS      = 200E-9  <<< USER: SA cross-couple width (m)
.PARAM C_SA_IN         = 5E-15   <<< USER: SA input capacitance (F) — from .OP or estimate

* --- WL driver ---
.PARAM W_WL_DRV_N      = 800E-9  <<< USER: WL driver final stage NMOS width (m)
.PARAM W_WL_DRV_P      = 1.6E-6  <<< USER: WL driver final stage PMOS width (m)
.PARAM R_WL_DRIVER     = 50      <<< USER: WL driver output resistance (ohm)


* =============================================================================
* SECTION 5: ASSIST CIRCUIT PARAMETERS
* =============================================================================
* --- WL Underdrive ---
.PARAM WLUD_DELTA      = 0.15    <<< USER: WL underdrive from VDD (V)
.PARAM WLUD_EN         = 0       <<< USER: 0=disabled, 1=enabled

* --- Negative Bitline ---
.PARAM VBOOST_MAG      = 0.3     <<< USER: NBL boost magnitude (V)
.PARAM C_NBL_VAL       = 100E-15 <<< USER: NBL coupling capacitance (F)
.PARAM NBL_EN          = 0       <<< USER: 0=disabled, 1=enabled

* --- VDD Collapse ---
.PARAM VCOL_DELTA      = 0.1     <<< USER: VDD collapse voltage drop (V)
.PARAM VCOL_EN         = 0       <<< USER: 0=disabled, 1=enabled


* =============================================================================
* SECTION 6: TIMING PARAMETERS
* =============================================================================
* --- WL ---
.PARAM WL_PW           = 200E-12 <<< USER: WL pulse width (s)
.PARAM WL_STAGGER      = 10E-12  <<< USER: WL stagger between adjacent rows (s)
.PARAM PERIOD          = 1E-9    <<< USER: clock period (s)

* --- Precharge ---
.PARAM TPCH_OFF        = -10E-12 <<< USER: precharge turn-off before WL (s) — negative = before WL rise
.PARAM TPCH_ON         = 'WL_PW + 20E-12' <<< USER: precharge turn-on after WL (s)

* --- SA Enable ---
.PARAM BL_DELTA_TARGET = 0.05    <<< USER: target BL differential before SA_EN (V)
.PARAM TSAE_MARGIN     = 10E-12  <<< USER: SA_EN margin after ΔV target reached (s)

* --- Write driver enable ---
.PARAM TWR_EN_START    = 10E-12  <<< USER: write enable start (s after WL rise)
.PARAM TWR_EN_WIDTH    = 'WL_PW + 10E-12' <<< USER: write enable pulse width (s)

* --- NBL timing ---
.PARAM TD_NBL          = 20E-12  <<< USER: NBL boost start after WL rise (s)
.PARAM NBL_PW          = 'WL_PW - 30E-12' <<< USER: NBL boost pulse width (s)


* =============================================================================
* SECTION 7: SUPPLY PARAMETERS
* =============================================================================
.PARAM VDD_NOM         = 0.8     <<< USER: nominal supply voltage (V)
.PARAM R_VDD_MESH      = 5       <<< USER: VDD mesh resistance (ohm) — 0 for ideal
.PARAM R_VSS_MESH      = 5       <<< USER: VSS mesh resistance (ohm) — 0 for ideal
.PARAM I_PEAK_ARRAY_EST = 10E-3  <<< USER: estimated peak array current (A) — for IR drop


* =============================================================================
* SECTION 8: REPLICA TIMING PATH
* =============================================================================
.PARAM REPLICA_EN      = 1       <<< USER: 0=fixed SA_EN delay, 1=self-timed replica
.PARAM N_REPLICA_COLS  = 1       <<< USER: number of replica columns (typically 1)
.PARAM REPLICA_ΔV_REF  = 0.05    <<< USER: replica BL discharge trigger level (V)


* =============================================================================
* SECTION 9: UNUSED COLUMN / READ DISTURB
* =============================================================================
.PARAM N_UNSEL_COLS_MON= 2       <<< USER: number of unselected columns to monitor for read disturb


* =============================================================================
* END OF USER PARAMETERS
* =============================================================================
* All derived values below — do not edit unless you understand the math.
* =============================================================================

* --- Derived: BL total R and C ---
.PARAM ARRAY_HEIGHT = 'N_ROWS * CELL_HEIGHT'
.PARAM ARRAY_WIDTH  = 'N_COLS * CELL_WIDTH'
.PARAM R_BL_PER_PITCH = 'R_BL_PER_UM * CELL_HEIGHT / W_BL'
.PARAM R_BL_METAL = 'N_ROWS * R_BL_PER_PITCH'
.PARAM R_BL = 'R_BL_METAL + R_VIA_BL'
.PARAM C_BL_WIRE = '(C_BL_WIRE_PER_UM + C_BL_FRINGE_PER_UM) * ARRAY_HEIGHT'
.PARAM C_BL_DRAIN = 'N_ROWS * C_DRAIN_PG'
.PARAM C_BL_TOTAL = 'C_BL_WIRE + C_BL_DRAIN'
* Aliases for section compatibility
.PARAM C_BL_METAL = C_BL_WIRE
.PARAM C_BL_DEVICE = C_BL_DRAIN
.PARAM C_BL_BLB   = 'C_BLB_COUPLE_PER_UM * ARRAY_HEIGHT'

* --- Derived: WL total R and C ---
.PARAM R_WL_PER_PITCH = 'R_WL_PER_UM * CELL_WIDTH / W_WL'
.PARAM R_WL_METAL = 'N_COLS * R_WL_PER_PITCH'
.PARAM R_WL = 'R_WL_METAL + R_VIA_WL'
.PARAM R_WL_TOTAL = 'R_WL_DRIVER + R_WL_METAL'
.PARAM C_WL_WIRE = '(C_WL_WIRE_PER_UM + C_WL_FRINGE_PER_UM) * ARRAY_WIDTH'
.PARAM C_WL_GATE = 'N_COLS * C_GD_PG'
.PARAM C_WL_TOTAL = 'C_WL_WIRE + C_WL_GATE'

* --- Derived: BL RC time constants ---
.PARAM TAU_BL = 'R_BL * C_BL_TOTAL / 2'
.PARAM TAU_WL = 'R_WL * C_WL_TOTAL / 2'

* --- Derived: Supply IR drop ---
.PARAM DELTA_VDD_IR = 'I_PEAK_ARRAY_EST * R_VDD_MESH / 2'
.PARAM VDD_LOCAL = 'VDD_NOM - DELTA_VDD_IR'
.PARAM I_PEAK_ARRAY = I_PEAK_ARRAY_EST             * Alias for section compatibility
.PARAM VDD = VDD_NOM                                 * Alias for backward compat with doc examples

* --- Derived: Assist voltages ---
.PARAM V_WLUD  = 'VDD_NOM - WLUD_DELTA'            * WL underdrive voltage
.PARAM VVDD_COL = 'VDD_NOM - VCOL_DELTA * VCOL_EN' * Collapsed cell supply

* --- Derived: MUX load on SA input ---
.PARAM C_MUX_LOAD = '(N_COL_MUX - 1) * C_DRAIN_PG'

* --- Derived: BL leakage ---
.PARAM I_LEAK_BL_TOTAL = 'N_ROWS * I_LEAK_PG'
