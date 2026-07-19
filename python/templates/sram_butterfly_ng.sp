* SRAM Butterfly Curve Extraction - ngspice
* 14 nm HP BSIM4 FinFET, PD = 3 fin PG = 2 fin PU = 1 fin (CR = 1.5)
*
* Template variables (rendered by Python):
*   {{ VOP }}            - supply voltage (V)
*   {{ COMMON_N_SHIFT }} - NMOS Vth shift (V, positive = slower)
*   {{ PU_SHIFT }}       - PMOS Vth shift (V, positive = slower)
*   {{ TEMP }}           - temperature (degC)
*   {{ VWL }}            - wordline voltage (V)

.title SRAM butterfly SNM - ngspice BSIM4 14 nm HP

* --- Options ---
.options post = 2 brief noacct

* --- Model include ---
.include '14nm_HP.pm'

* --- Rendered parameters ---
.param VOP             = {{ VOP }}
.param COMMON_N_SHIFT_V = {{ COMMON_N_SHIFT }}
.param PU_SHIFT_V      = {{ PU_SHIFT }}
.param VWL_VAL         = {{ VWL }}

.temp {{ TEMP }}

* --- Device sizing ---
.param L_GATE  = 20e-9
.param W_1FIN  = 100e-9
.param W_PU    = 'W_1FIN'
.param W_PG    = '2*W_1FIN'
.param W_PD    = '3*W_1FIN'

* --- Boundary constants ---
.param SQRT2   = 'sqrt(2)'
.param V_BND   = 'VOP/SQRT2'
.param V_MID   = 'VOP/3'

* ====================================================================
* Vth-skew FET wrappers
*
* Global params COMMON_N_SHIFT_V / PU_SHIFT_V are accessible via { }
* inside subcircuits in ngspice.
*
* NMOS: g_int = g − COMMON_N_SHIFT_V  ⇒ positive shift ⇒ slower
* PMOS: g_int = g + PU_SHIFT_V         ⇒ positive shift ⇒ slower
* ====================================================================

.subckt nfet_pd d g s b
vsk g_int g dc = '-{COMMON_N_SHIFT_V}'
mn   d g_int s b nmos L = {L_GATE} W = {W_PD}
.ends nfet_pd

.subckt nfet_pg d g s b
vsk g_int g dc = '-{COMMON_N_SHIFT_V}'
mn   d g_int s b nmos L = {L_GATE} W = {W_PG}
.ends nfet_pg

.subckt pfet_pu d g s b
vsk g_int g dc = '{PU_SHIFT_V}'
mp   d g_int s b pmos L = {L_GATE} W = {W_PU}
.ends pfet_pu

* --- Global nets ---
.global vdda vssa bl1 bl2 wl1 wl2

* ====================================================================
* Half-cell subcircuits
* ====================================================================

.subckt hc1 in out
xpu out in vdda vdda pfet_pu
xpg bl1 wl1 out vssa nfet_pg
xpd out in vssa vssa nfet_pd
.ends hc1

.subckt hc2 in out
xpu out in vdda vdda pfet_pu
xpg bl2 wl2 out vssa nfet_pg
xpd out in vssa vssa nfet_pd
.ends hc2

* --- Supplies ---
vdda vdda 0 DC {VOP}
vssa vssa 0 DC 0
vbl1 bl1  0 DC {VOP}
vbl2 bl2  0 DC {VOP}
vwl1 wl1  0 DC {VWL_VAL}
vwl2 wl2  0 DC {VWL_VAL}

* --- Cross-coupled SRAM cell ---
xhc1 hc1in hc1out hc1
xhc2 hc2in hc2out hc2

* --- Butterfly sweep source ---
vu u 0 0

* ====================================================================
* Coordinate rotation B-sources (Seevinck method)
*
* ngspice: use B-sources with V = { … } (E-sources with value{ … }
* do not work for arbitrary expressions in this ngspice version).
* ====================================================================

Bhc1nv  v1     0 V = { v(hc1out)*sqrt(2) + v(u) }
Bhc2nv  v2     0 V = { v(hc2out)*sqrt(2) - v(u) }
Bhc1in  hc1in  0 V = { v(u)/sqrt(2) + v(v1)/sqrt(2) }
Bhc2in  hc2in  0 V = { -v(u)/sqrt(2) + v(v2)/sqrt(2) }

* --- Auxiliary signals for .measure (ngspice needs a node, not an
*     expression, for MAX / MIN / WHEN targets) ---
Bdiff   vdiff  0 V = { v(v1) - v(v2) }
Bdiffn  vdiffn 0 V = { v(v2) - v(v1) }
Babs    vabs   0 V = { abs(v(v1) - v(v2)) }

* --- DC sweep ---
* NOTE: {-VOP} not -{VOP} - the braced form prevents a space between
* the minus sign and the value, which would cause a parse error.
.dc vu {-VOP} {VOP} 0.01

* ====================================================================
* SNM extraction via .measure (Seevinck method)
*
* The read SNM is the minimum enclosed-square side length between
* the butterfly VTC crossings in the 45° rotated coordinate frame.
* ====================================================================

* --- Crossing detection (up to 4 crossings) ---
.measure dc xc1    when v(vdiff) = 0 cross = 1
.measure dc xc2    when v(vdiff) = 0 cross = 2
.measure dc xc3    when v(vdiff) = 0 cross = 3
.measure dc xc4    when v(vdiff) = 0 cross = 4
.measure dc xclast when v(vdiff) = 0 cross = last

* --- Seevinck method: min |v1−v2| in each lobe ---
.measure dc y1 min v(vabs) from = {-V_BND} to = 0
.measure dc y2 min v(vabs) from = 0       to = {V_BND}

* --- Diagonal method: max difference in each region ---
.measure dc snmr1 MAX v(vdiff)  from = {-V_BND}  to = {V_MID}
.measure dc snmr2 MAX v(vdiffn) from = {-V_MID}  to = {V_BND}

* --- Print raw data for Python-based SNM extraction ---
* Note: ngspice-46 batch mode requires at least one .print/.plot/.fourier
* line or it reports "no simulations run".
* .print output wraps to multiple tables when >3 signal columns exist.
.print dc v(u) v(hc1out) v(hc2out) v(v1) v(v2) v(vdiff) v(vabs)

.end
