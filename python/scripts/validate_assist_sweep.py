"""
Validation sweep at multiple Vmin targets using plain Surrogate.

Trains a single 4D plain GP Surrogate (not PhysicsConstrainedSurrogate) on
analytic SNMR data with WLUD ratio as the 4th dimension, then evaluates
estimate_required_assist accuracy at TARGET_VMIN = 0.55, 0.60, 0.65, 0.70 V.

Each target evaluation shares the same train/test split for fair comparison.

Usage:
    python scripts/validate_assist_sweep.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.utils import (
    Z_FIXED, VOPS, VOP_COL, WLUD_COL,
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
    WLUD_FACTORS, N_WLUD,
)
from src.data import build_dataset, stratified_train_test_split
from src.surrogate import Surrogate
from src.physics import analytic_snmr
from src.physics_layer import compute_vmin_from_z, estimate_required_assist

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
N_COND = 30
MU_NOISE_STD = 0.002
SIGMA_NOISE_STD = 0.0005
N_GRID = 30
N_WLUD_EVAL = 20
WLUD_LO = 0.90
TARGET_VMINS = [0.55, 0.60, 0.65, 0.70]
N_ITER = 50

# Dense WLUD grid for ground truth Vmin computation.
#
# DESIGN-RANGE truth (primary): same actionable range the GP searches
# ([WLUD_LO, 1.0]).  The 2026-07-02 run compared GP feasibility (search
# range [0.90, 1.0]) against truth over [0.50, 1.0], so every point that
# needed >10% underdrive was counted as a GP miss — an unfair metric
# (74-90% "agreement" artifact).  Feasibility must be defined over the
# same actionable WLUD range on both sides.
DENSE_WLUD = np.linspace(WLUD_LO, 1.0, 20, dtype=np.float64)
# Full-range diagnostic: strongest physically-considered assist (WLUD=0.50)
# used only to report how many points would need out-of-design-range assist.
WLUD_FULL_MIN = 0.50

rng = np.random.default_rng(42)

# ===================================================================
# 1. Generate 4D training data
#    Input:  [common_N (mV), PU (mV), Vop (V), WLUD (ratio)]
#    Target: [mu_SNMR (V), sigma_SNMR (V)]
# ===================================================================
print("=" * 72)
print("Validation Sweep: Assist Estimation at Multiple Vmin Targets")
print("=" * 72)

print("\n=== 1. Generate 4D synthetic training data ===")
X_cnpu = build_dataset(N_COND)  # (N_COND * 6, 3): [cn, pu, Vop]
n_base = len(X_cnpu)

X_4d = np.zeros((n_base * N_WLUD, 4), dtype=np.float64)
y_4d = np.zeros((n_base * N_WLUD, 2), dtype=np.float64)
for i in range(N_WLUD):
    wlud = WLUD_FACTORS[i]
    start = i * n_base
    end = (i + 1) * n_base
    X_4d[start:end, :3] = X_cnpu
    X_4d[start:end, WLUD_COL] = wlud  # WLUD ratio, not absolute Vwl
    for j in range(n_base):
        cn, pu, vop = X_cnpu[j]
        vwl = vop * wlud  # Vwl = WLUD * Vop
        mu, sigma = analytic_snmr(cn, pu, vop, vwl_v=vwl)
        y_4d[start + j] = [
            mu + rng.normal(0, MU_NOISE_STD),
            sigma + rng.normal(0, SIGMA_NOISE_STD),
        ]

print(f"  4D dataset: X {X_4d.shape}, y {y_4d.shape}")
print(f"  WLUD range in train: [{X_4d[:, WLUD_COL].min():.2f}, {X_4d[:, WLUD_COL].max():.2f}]")

# ===================================================================
# 2. Train GP surrogate (plain Surrogate — NOT PhysicsConstrainedSurrogate)
# ===================================================================
print("\n=== 2. Train GP surrogate (plain Surrogate, 4D) ===")
X_tr, X_te, y_tr, y_te = stratified_train_test_split(X_4d, y_4d, test_frac=0.15)
surr = Surrogate(device="cpu")
surr.fit(X_tr, y_tr, verbose=True, n_iter=N_ITER)

mu_pred, _, sigma_pred, _ = surr.predict(X_te)
mu_rmse = float(np.sqrt(np.mean((mu_pred - y_te[:, 0]) ** 2)))
sigma_rmse = float(np.sqrt(np.mean((sigma_pred - y_te[:, 1]) ** 2)))
print(f"\n  Test RMSE: mu={mu_rmse:.5f}, sigma={sigma_rmse:.5f}")


def surrogate_fn(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Wrapper: predict -> (mu, sigma) for physics_layer functions."""
    mu, _, sigma, _ = surr.predict(x)
    return mu, sigma


# ===================================================================
# 3. Ground truth: Vmin vs WLUD on validation grid
#    Build once, reuse for all target Vmin evaluations.
# ===================================================================
print("\n=== 3. Compute ground truth Vmin vs WLUD on validation grid ===")
cna = np.linspace(COMMON_N_MIN, COMMON_N_MAX, N_GRID)
pua = np.linspace(PU_MIN, PU_MAX, N_GRID)
CN, PU = np.meshgrid(cna, pua, indexing="xy")

true_vmin_3d = np.full((N_GRID, N_GRID, len(DENSE_WLUD)), np.nan, dtype=np.float64)
true_cens_3d = np.zeros((N_GRID, N_GRID, len(DENSE_WLUD)), dtype=bool)
vmin_full_assist = np.full((N_GRID, N_GRID), np.nan, dtype=np.float64)
for i in range(N_GRID):
    for j in range(N_GRID):
        cn = float(CN[i, j])
        pu = float(PU[i, j])
        for k, wlud in enumerate(DENSE_WLUD):
            z_vals = np.array([
                analytic_snmr(cn, pu, v, vwl_v=v * wlud)[0]
                / analytic_snmr(cn, pu, v, vwl_v=v * wlud)[1]
                for v in VOPS
            ])
            v, cens = compute_vmin_from_z(z_vals.reshape(1, -1), return_censored=True)
            true_vmin_3d[i, j, k] = float(v[0])
            true_cens_3d[i, j, k] = bool(cens[0])
        # Full-range diagnostic: Vmin at the strongest out-of-range assist
        z_full = np.array([
            analytic_snmr(cn, pu, v, vwl_v=v * WLUD_FULL_MIN)[0]
            / analytic_snmr(cn, pu, v, vwl_v=v * WLUD_FULL_MIN)[1]
            for v in VOPS
        ])
        vmin_full_assist[i, j] = float(compute_vmin_from_z(z_full.reshape(1, -1))[0])
print(f"  Ground truth grid: {true_vmin_3d.shape} "
      f"(design-range WLUD [{DENSE_WLUD[0]:.2f}, {DENSE_WLUD[-1]:.2f}]; "
      f"{int(true_cens_3d.sum())} censored cells)")

# ===================================================================
# 4. Validation at each target Vmin
# ===================================================================
print("\n=== 4. Validation sweep ===")

all_results: dict[float, dict] = {}

for tgt in TARGET_VMINS:
    print(f"\n  --- Target Vmin = {tgt:.2f} V ---")

    # 4a. GP-based assist estimation
    CN_est, PU_est, wlud_required, vmin_achieved = estimate_required_assist(
        surrogate_fn, target_vmin=tgt, vop_fixed=0.7,
        n_grid=N_GRID, wlud_lo=WLUD_LO, n_wlud_eval=N_WLUD_EVAL,
    )

    # 4b. Ground truth: what WLUD does the analytic model really need?
    true_wlud_required = np.full((N_GRID, N_GRID), np.nan, dtype=np.float64)
    true_vmin_at_found = np.full((N_GRID, N_GRID), np.nan, dtype=np.float64)

    for i in range(N_GRID):
        for j in range(N_GRID):
            cn = float(CN[i, j])
            pu = float(PU[i, j])
            vmin_curve = true_vmin_3d[i, j, :]

            if np.isnan(vmin_curve).all():
                continue

            # Vmin at max WLUD (= 1.0, no assist)
            vmin_no_assist = vmin_curve[-1]
            if np.isnan(vmin_no_assist):
                continue
            if vmin_no_assist <= tgt:
                true_wlud_required[i, j] = 1.0  # no assist needed
                true_vmin_at_found[i, j] = vmin_no_assist
                continue

            # Vmin at min WLUD (strongest assist in dense grid = 0.50)
            vmin_max_assist = vmin_curve[0]
            if np.isnan(vmin_max_assist) or vmin_max_assist > tgt:
                continue  # infeasible even with strongest assist

            # Binary search on true model
            lo, hi = 0, len(DENSE_WLUD) - 1
            for _ in range(30):
                mid = (lo + hi) // 2
                if vmin_curve[mid] < tgt:
                    lo = mid
                else:
                    hi = mid
                if hi - lo <= 1:
                    break

            v_lo, v_hi = vmin_curve[lo], vmin_curve[hi]
            if np.isnan(v_lo) or np.isnan(v_hi) or abs(v_hi - v_lo) < 1e-12:
                continue
            t = np.clip((tgt - v_lo) / (v_hi - v_lo), 0.0, 1.0)
            true_wlud_required[i, j] = DENSE_WLUD[lo] + t * (DENSE_WLUD[hi] - DENSE_WLUD[lo])
            true_vmin_at_found[i, j] = vmin_curve[lo] + t * (vmin_curve[hi] - vmin_curve[lo])

    # 4c. Compute metrics
    gp_feasible = ~np.isnan(wlud_required)
    true_feasible = ~np.isnan(true_wlud_required)
    agree = gp_feasible == true_feasible
    n_total = N_GRID * N_GRID
    n_feasible_gp = int(gp_feasible.sum())
    n_feasible_true = int(true_feasible.sum())
    feas_agreement_pct = float(agree.sum() / n_total * 100)

    feasible_mask = gp_feasible & true_feasible
    n_feasible_both = int(feasible_mask.sum())

    # Out-of-design-range diagnostic: needs assist stronger than WLUD_LO
    # (feasible at WLUD_FULL_MIN but not within [WLUD_LO, 1.0])
    oor_mask = (~true_feasible) & ~np.isnan(vmin_full_assist) & (vmin_full_assist <= tgt)
    n_out_of_range = int(oor_mask.sum())

    if n_feasible_both > 0:
        # WLUD error
        wlud_error = wlud_required[feasible_mask] - true_wlud_required[feasible_mask]
        wlud_rmse = float(np.sqrt(np.mean(wlud_error ** 2)))
        wlud_mae = float(np.mean(np.abs(wlud_error)))

        # Vmin achieved at GP-predicted WLUD (interpolated from true model).
        # Censoring: if either interpolation endpoint sits at the heuristic
        # floor (true Vmin < min Vop), the achieved value is not a real
        # number — the target is met with margin beyond the measurable
        # range.  Those points are counted separately, NOT in the RMSE.
        vmin_at_gp_wlud = np.full((N_GRID, N_GRID), np.nan, dtype=np.float64)
        achieved_censored = np.zeros((N_GRID, N_GRID), dtype=bool)
        for idx in zip(*np.where(feasible_mask)):
            i, j = idx
            wlud_gp = float(wlud_required[i, j])

            if wlud_gp <= DENSE_WLUD[0]:
                vmin_at_gp_wlud[i, j] = true_vmin_3d[i, j, 0]
                achieved_censored[i, j] = true_cens_3d[i, j, 0]
                continue
            if wlud_gp >= DENSE_WLUD[-1]:
                vmin_at_gp_wlud[i, j] = true_vmin_3d[i, j, -1]
                achieved_censored[i, j] = true_cens_3d[i, j, -1]
                continue

            hi = int(np.searchsorted(DENSE_WLUD, wlud_gp))
            lo = hi - 1
            t_frac = (wlud_gp - DENSE_WLUD[lo]) / (DENSE_WLUD[hi] - DENSE_WLUD[lo] + 1e-12)
            v_lo = true_vmin_3d[i, j, lo]
            v_hi = true_vmin_3d[i, j, hi]
            if np.isnan(v_lo) or np.isnan(v_hi):
                continue
            vmin_at_gp_wlud[i, j] = v_lo + t_frac * (v_hi - v_lo)
            achieved_censored[i, j] = bool(true_cens_3d[i, j, lo] or true_cens_3d[i, j, hi])

        # Assist-active subset: cells where the GP actually dialed in an
        # interior WLUD.  Cells returned as wlud_required == 1.0 mean "no
        # assist needed" — their natural Vmin sits below the target by
        # margin, which is a SUCCESS, not an estimation error; including
        # them turned natural margin into fake RMSE.
        assist_active = feasible_mask & (wlud_required < 1.0 - 1e-9)
        n_no_assist = int((feasible_mask & ~assist_active).sum())

        # Interpolable subset: achieved Vmin is a real (non-censored) number
        interp_mask = assist_active & ~achieved_censored & ~np.isnan(vmin_at_gp_wlud)
        n_censored = int((assist_active & achieved_censored).sum())

        if interp_mask.sum() > 0:
            vmin_error = vmin_at_gp_wlud[interp_mask] - tgt
            vmin_rmse = float(np.sqrt(np.mean(vmin_error ** 2)))
            vmin_mae = float(np.mean(np.abs(vmin_error)))
            abs_err = np.abs(vmin_error)
            p5 = float(np.percentile(abs_err, 5))
            p50 = float(np.percentile(abs_err, 50))
            p95 = float(np.percentile(abs_err, 95))
        else:
            vmin_rmse = vmin_mae = p5 = p50 = p95 = np.nan

        # Legacy metric (censored + no-assist points included) — kept to
        # quantify the size of the artifact vs the 2026-07-02 report.
        legacy_valid = feasible_mask & ~np.isnan(vmin_at_gp_wlud)
        if legacy_valid.sum() > 0:
            legacy_err = vmin_at_gp_wlud[legacy_valid] - tgt
            vmin_rmse_legacy = float(np.sqrt(np.mean(legacy_err ** 2)))
        else:
            vmin_rmse_legacy = np.nan
    else:
        wlud_rmse = wlud_mae = np.nan
        vmin_rmse = vmin_mae = p5 = p50 = p95 = np.nan
        vmin_rmse_legacy = np.nan
        n_censored = 0
        n_no_assist = 0

    all_results[tgt] = {
        "n_feasible_gp": n_feasible_gp,
        "n_feasible_true": n_feasible_true,
        "n_feasible_both": n_feasible_both,
        "n_out_of_range": n_out_of_range,
        "n_censored": n_censored,
        "n_no_assist": n_no_assist,
        "feas_agreement_pct": feas_agreement_pct,
        "wlud_rmse": wlud_rmse,
        "wlud_mae": wlud_mae,
        "vmin_rmse": vmin_rmse,
        "vmin_rmse_legacy": vmin_rmse_legacy,
        "vmin_mae": vmin_mae,
        "p5": p5,
        "p50": p50,
        "p95": p95,
    }

    # Print per-target summary
    print(f"    Feasible (GP, design range):    {n_feasible_gp:>4d} / {n_total}")
    print(f"    Feasible (true, design range):  {n_feasible_true:>4d} / {n_total}")
    print(f"    Needs out-of-range assist:      {n_out_of_range:>4d}  (WLUD < {WLUD_LO})")
    print(f"    Feasibility agreement:          {feas_agreement_pct:>6.2f}%")
    print(f"    No assist needed (natural met): {n_no_assist:>4d}  (WLUD_req = 1.0)")
    print(f"    Target met w/ margin (censored): {n_censored:>4d}  (achieved < {VOPS[0]:.2f} V)")
    print(f"    WLUD RMSE:              {wlud_rmse:.6f}" if not np.isnan(wlud_rmse) else "    WLUD RMSE:              N/A")
    print(f"    WLUD MAE:               {wlud_mae:.6f}" if not np.isnan(wlud_mae) else "    WLUD MAE:               N/A")
    print(f"    Vmin RMSE (interpolable): {vmin_rmse:.6f} V" if not np.isnan(vmin_rmse) else "    Vmin RMSE (interpolable): N/A")
    print(f"    Vmin RMSE (legacy, w/ censored): {vmin_rmse_legacy:.6f} V" if not np.isnan(vmin_rmse_legacy) else "    Vmin RMSE (legacy):     N/A")
    if not np.isnan(p5):
        print(f"    |Vmin err| percentiles: p5={p5:.6f}  p50={p50:.6f}  p95={p95:.6f} V")

# ===================================================================
# 5. Comparison table
# ===================================================================
print("\n" + "=" * 72)
print("COMPARISON TABLE: Validation Sweep at Multiple Vmin Targets")
print("=" * 72)

# Column widths
col_w = [8, 8, 10, 6, 8, 6, 6, 10, 12, 12, 8, 8]
headers = ["Target", "Feas_GP", "Feas_True", "OoR", "Agree%", "NoAst", "Cens",
           "WLUD_RMSE", "VminRMSE_int", "VminRMSE_leg", "|err|p50", "|err|p95"]
hdr_line = "  ".join(f"{h:>{w}}" for h, w in zip(headers, col_w))
sep_line = "  ".join("-" * w for w in col_w)
print(hdr_line)
print(sep_line)

for tgt in TARGET_VMINS:
    r = all_results[tgt]

    def _fmt(v: float, w: int, dec: int = 4) -> str:
        if np.isnan(v):
            return f"{'N/A':>{w}}"
        return f"{v:>{w}.{dec}f}"

    vals = [
        f"{tgt:>{col_w[0]}.2f}",
        f"{r['n_feasible_gp']:>{col_w[1]}d}",
        f"{r['n_feasible_true']:>{col_w[2]}d}",
        f"{r['n_out_of_range']:>{col_w[3]}d}",
        f"{r['feas_agreement_pct']:>{col_w[4] - 1}.1f}%",
        f"{r['n_no_assist']:>{col_w[5]}d}",
        f"{r['n_censored']:>{col_w[6]}d}",
        _fmt(r['wlud_rmse'], col_w[7], 4),
        _fmt(r['vmin_rmse'], col_w[8], 6),
        _fmt(r['vmin_rmse_legacy'], col_w[9], 6),
        _fmt(r['p50'], col_w[10], 6),
        _fmt(r['p95'], col_w[11], 6),
    ]
    print("  ".join(vals))
print("\n  VminRMSE_int = assist-active, non-censored points only (the real inverse accuracy)")
print("  VminRMSE_leg = legacy definition incl. no-assist + censored points (artifact)")
print("  OoR   = true-feasible only with WLUD < WLUD_LO (out of design range)")
print("  NoAst = no assist needed (natural Vmin already <= target; success, not error)")
print("  Cens  = target met with margin (achieved Vmin below min sampled Vop)")

print()

# ===================================================================
# 6. Recommendation
# ===================================================================
print("=" * 72)
print("RECOMMENDATION")
print("=" * 72)

# Score each target
best_target = None
best_score = -1e9
for tgt in TARGET_VMINS:
    r = all_results[tgt]
    score = 0.0
    reasons: list[str] = []

    # Feasible overlap (more is better)
    if not np.isnan(r['feas_agreement_pct']):
        score += r['feas_agreement_pct'] / 10.0  # up to 10 pts

    # Vmin RMSE (lower is better, cap at 2.0 pts)
    if not np.isnan(r['vmin_rmse']):
        vmin_score = max(0.0, 2.0 - r['vmin_rmse'] * 100)
        score += vmin_score

    # WLUD RMSE (lower is better, cap at 2.0 pts)
    if not np.isnan(r['wlud_rmse']):
        wlud_score = max(0.0, 2.0 - r['wlud_rmse'] * 20)
        score += wlud_score

    # Fraction of feasible points that are jointly feasible (data quality)
    if r['n_feasible_true'] > 0:
        overlap_frac = r['n_feasible_both'] / r['n_feasible_true']
        score += overlap_frac * 3.0  # up to 3 pts

    if score > best_score:
        best_score = score
        best_target = tgt

    print(f"\n  Target {tgt:.2f}V: score={score:.1f}")
    print(f"    Feasibility agreement: {r['feas_agreement_pct']:.1f}%")
    if not np.isnan(r['vmin_rmse']):
        print(f"    Vmin error RMSE:       {r['vmin_rmse']:.6f} V")
    if not np.isnan(r['wlud_rmse']):
        print(f"    WLUD estimation RMSE:  {r['wlud_rmse']:.4f}")

print(f"\n  >>> RECOMMENDED TARGET VMIN: {best_target:.2f} V "
      f"(score={best_score:.1f}) <<<")

if best_target is not None:
    r = all_results[best_target]
    print(f"\n  Rationale:")
    print(f"    - Feasibility agreement: {r['feas_agreement_pct']:.1f}% "
          f"({r['n_feasible_both']}/{r['n_feasible_true']} jointly feasible)")
    if not np.isnan(r['vmin_rmse']):
        print(f"    - Vmin prediction error: RMSE={r['vmin_rmse']:.6f} V, "
              f"MAE={r['vmin_mae']:.6f} V")
    if not np.isnan(r['wlud_rmse']):
        print(f"    - WLUD estimation error: RMSE={r['wlud_rmse']:.4f}, "
              f"MAE={r['wlud_mae']:.4f}")
    if not np.isnan(r['p50']):
        print(f"    - Median |Vmin error|: {r['p50']:.6f} V "
              f"(p5={r['p5']:.6f}, p95={r['p95']:.6f})")

print(f"\n=== Validation sweep complete ===")
