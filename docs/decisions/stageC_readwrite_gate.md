# Stage C — Read-Write Integrated Vmin (GO)

> Date: 2026-07-13
> Script: `python/scripts/stageC_readwrite.py`
> Data: `python/data/260713_stageB_snmr.xlsx`, sheets `stageB_snmr` (read/SNMR
>   @125C) + `stageB_bwrm` (write/Vtrip @-40C)
> Output: `python/results/stageC_readwrite/`
> Predecessor: Stage B SNMR gate `stageB_real_data_gate.md` (GO, 2026-07-13)

## Verdict: **GO** — Vtrip surrogate gate passes (3/3), combined Vmin behaves physically

Adds the Vtrip **write-margin** surrogate to the Stage B SNMR **read-margin**
surrogate and integrates them into a unified
**Vmin = smooth_max(Vmin_SNMR, Vmin_Vtrip, α=2 mV)**
(deck_scenarios.md §1.5; α ≤ 2 mV per revised_plan_review_20260709 — α=10 mV gave
a 6.93 mV crossing bias).

## Part 1 — Vtrip write-margin surrogate gate

Data: `stageB_bwrm` = **399 conditions × 5 Vop = 2000 samples**, Vtrip @−40 °C.
(Read/write condition sets overlap only 214 of ~348/399 — fine: each metric gets
its own GP, combined on a common grid.)

| Criterion | Result | Verdict |
|-----------|--------|---------|
| hold-out mu R² ≥ 0.95 | **0.9990** (RMSE 2.67 mV) | PASS |
| gradient direction | dVmin_Vtrip/dcn=+0.00198 (>0), dVmin_Vtrip/dpu=−0.00161 (<0) | PASS |
| SFG worst corner | SFG=0.625 V, the max finite (FSG censored-low) | PASS |

- **Opposite signs to SNMR** (SNMR: dVmin/dcn<0, dVmin/dpu>0) — the read-write
  tradeoff is explicit in the gradients.
- Vtrip corner Vmin: **SFG 0.625 V (worst write)** > SSG 0.496 > FFG 0.409 >
  **FSG censored <0.4 (best write)**. Exactly physical: slow-N/fast-P (SFG) is
  hardest to write; fast-N/slow-P (FSG) is easiest.
- Lengthscales (mu GP): `ell_pu=6.81 < ell_cn=8.15 < ell_sk=8.70`, `ell_Vop=3.23`.
  → **Vtrip is most sensitive to pu (PMOS pull-up)**, then cn (PG), then sk —
  write-ability is gated by overpowering the PMOS, so pu-dominant is expected.
  (Contrast SNMR, where cn/PG dominates.) sigma R²=0.858 (RMSE 0.2 mV).

## Part 2 — Combined read-write Vmin surface

Both GPs retrained on all data; Vmin on a 60×60 (cn,pu) grid at sk=0.

- Vmin_SNMR ∈ [0.35, 0.85] (FSG worst, censored-high), Vmin_Vtrip ∈ [0.35, 0.655]
  (SFG worst), **Vmin_combined ∈ [0.477, 0.85]**.
- **read-limited 43.5 % / write-limited 56.5 %** of the (cn,pu) plane — both
  mechanisms materially bind; neither dominates.
- Corner accounting (SNMR / Vtrip / combined, limiting mechanism):

  | corner | SNMR | Vtrip | combined | binds |
  |--------|------|-------|----------|-------|
  | FSG (−60,+60) | 0.850 | 0.350 | **0.850** | READ |
  | SFG (+60,−60) | 0.350 | 0.655 | **0.655** | WRITE |
  | FFG (−60,−60) | 0.488 | 0.464 | 0.488 | READ |
  | SSG (+60,+60) | 0.463 | 0.542 | 0.542 | WRITE |

  → The combined Vmin surface is a **saddle**: high at BOTH FSG (read) and SFG
  (write), with a low-Vmin valley along the FFG–SSG diagonal. The 0.60 V
  combined contour encloses a diagonal safe band (see `stageC_combined_vmin.png`,
  `stageC_limiting_region.png`).

## Significance

First real-data demonstration of the **read-write Vmin tradeoff** on this PDK:
the two failure mechanisms own opposite process corners, so the array Vmin is set
by whichever binds locally. This is the Stage C deliverable and the substrate for
the paper's combined-margin contour and any co-optimization (a process/assist
shift that helps read at FSG generally hurts write at SFG).

## Read-write PG-PD skew co-optimization (2026-07-13, `stageC_skew_cooptimization.py`)

Both GPs on all data; evaluated at the real PDK 3-sigma corners
(FSG(−29,+39), SFG(+32,−37), FFG(−36,−44), SSG(+36,+45)). Outputs:
`stageC_skew_corners.png`, `stageC_worstcase_vs_skew.png`,
`stageC_combined_sensitivity.png`, `stageC_skew_coopt_summary.txt`.

**A. Skew is a pure read-write trade-off.** Positive skew (slower PG) **helps
read** (dVmin_SNMR/dsk ≈ −2.3…−3.4 mV/mV across corners) but **hurts write**
(dVmin_Vtrip/dsk ≈ +2.4…+6.2 mV/mV). The two binding corners want opposite skew:
FSG (read-binding) → +skew, SFG (write-binding) → −skew. At FFG/SSG the read
(falling) and write (rising) curves cross, so the combined Vmin is a V with its
minimum at the crossover (FFG sk≈−5, SSG sk≈−3).

**B. Optimal global skew ≈ −2 mV (essentially symmetric).** Worst-case array
Vmin = max over the 4 corners of combined Vmin:
- sk = 0: **603.0 mV**, binds **SFG (write)**
- sk* = **−2 mV**: **599.9 mV**, binds **FSG (read)** — the read/write balance point
- gain only **+3.1 mV** vs sk=0; the V is steep (±20 mV skew costs ~40–65 mV).

→ The nominal symmetric PG=PD design is already near-optimal for worst-case Vmin;
static skew offers no meaningful free margin, and **skew tolerance should be kept
tight** (large skew in either direction significantly worsens the binding corner).
This is the actionable read-write conclusion — contrast the SNMR-only view
(Stage B), where positive skew looked purely beneficial because write was ignored.

**C. Combined Vmin is interaction-dominated.** GP Sobol on Vmin_combined
(cn,sk,pu): S1 small, ST large (ΣS1≈0.32 → ~68 % from interactions), because the
read-write max() couples the dims (which mechanism binds depends jointly on cn &
pu). Totals: **cn ST=0.887 > pu ST=0.627 > sk ST=0.271**; first-order
cn S1=0.246, pu 0.042, sk 0.036. (Contrast the near-additive SNMR-only Sobol.)

## Follow-ups / caveats

- FSG combined Vmin is censored-high (>0.8 V, read-limited) — same sampled-Vop
  ceiling caveat as the Stage B gate; worst-read-corner Vmin is an extrapolation
  above 0.8 V. Consider whether the write side needs a Vop level >0.8 too (it does
  NOT here — Vtrip worst SFG = 0.625 V, well inside range).
- smooth_max α=2 mV used; the max is at sk=0. Skew dependence of the *combined*
  Vmin (both surfaces shift with sk) is a natural extension of the Stage B skew
  analysis — not yet done.
- Stage D (9D Sobol: +local σ, mobility) once `stageD_*` sheets are populated
  (currently empty).
