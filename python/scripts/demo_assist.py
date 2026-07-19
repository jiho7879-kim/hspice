"""
Demo Stage 3: Inverse assist estimation validation on analytic 4D model.

Validates estimate_required_assist() with the corrected metric definitions
(2026-07-06, see docs/decisions/session_20260706_root_cause_fixes.md):
  - ground truth restricted to the DESIGN RANGE WLUD in [0.90, 1.00]
    (same actionable range the GP searches — range mismatch artifact fix)
  - left-censored true Vmin (below min sampled Vop) excluded from RMSE
  - only ASSIST-ACTIVE cells (0.90 < WLUD_req < 1.0) enter the accuracy
    metric; wlud_required == 1.0 cells met the target naturally (margin,
    not error)

Trains BOTH the plain Surrogate and the PhysicsConstrainedSurrogate
(input scaling fixed 2026-07-06) and quantifies the physics gain; figures
and the Go/No-Go decision use the physics-constrained model.

The 4th GP dimension stores WLUD ratio (Vwl/Vop), not absolute Vwl.
When evaluating the analytic model, compute Vwl = WLUD * Vop.

Usage:
    python scripts/demo_assist.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils import (
    VOPS,
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
    WLUD_FACTORS, N_WLUD, WLUD_COL,
)
from src.data import build_dataset, stratified_train_test_split
from src.surrogate import Surrogate
from src.physics import PhysicsConstrainedSurrogate, analytic_snmr
from src.physics_layer import (
    compute_vmin_from_z, estimate_required_assist,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "stage3_assist"
OUT_DIR.mkdir(parents=True, exist_ok=True)

N_COND = 50
# 0.60 V: the project's canonical inverse target (plan Sec.14).  With the
# corrected metrics all targets 0.55-0.70 give ~3-5 mV inverse accuracy;
# the earlier "0.55 V too low" conclusion was a metric artifact.
TARGET_VMIN = 0.60
VOP_FIXED = 0.7
MU_NOISE_STD = 0.002
SIGMA_NOISE_STD = 0.0005
WLUD_LO = 0.90
N_GRID = 30
# L_mono off: on the strictly monotonic analytic toy it only adds training
# noise (ablation re-run 2026-07-06); re-enable for real HSPICE data.
PHYSICS_KW = dict(use_mono=False, use_boundary=True, use_pelgrom=True)

print("=" * 60)
print("Stage 3: Inverse Assist Estimation Validation")
print("=" * 60)

# ============================================================
# 1. Generate 4D data + train both surrogates
# ============================================================
print("\n=== 1. Train 4D surrogates (plain + physics-constrained) ===")
rng = np.random.default_rng(42)
X_cnpu = build_dataset(N_COND)
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
        vwl = vop * wlud  # Vwl = WLUD * Vop per point
        mu, sigma = analytic_snmr(cn, pu, vop, vwl_v=vwl)
        y_4d[start + j] = [mu + rng.normal(0, MU_NOISE_STD),
                           sigma + rng.normal(0, SIGMA_NOISE_STD)]

X_tr, X_te, y_tr, y_te = stratified_train_test_split(X_4d, y_4d, test_frac=0.15)


def _test_rmse(surr) -> tuple[float, float]:
    mu_p, _, sg_p, _ = surr.predict(X_te)
    return (float(np.sqrt(np.mean((mu_p - y_te[:, 0]) ** 2))),
            float(np.sqrt(np.mean((sg_p - y_te[:, 1]) ** 2))))


print("\n--- plain Surrogate ---")
surr_plain = Surrogate(device="cpu")
surr_plain.fit(X_tr, y_tr, verbose=False, n_iter=100)
surr_plain.save(OUT_DIR / "checkpoint_plain.pth")
mu_rmse_plain, sigma_rmse_plain = _test_rmse(surr_plain)
print(f"  Test RMSE: mu={mu_rmse_plain:.5f}, sigma={sigma_rmse_plain:.5f}")

print("\n--- PhysicsConstrainedSurrogate (boundary + pelgrom) ---")
surr_phys = PhysicsConstrainedSurrogate(device="cpu")
surr_phys.fit(X_tr, y_tr, n_iter=100, verbose=False, **PHYSICS_KW)
mu_rmse_phys, sigma_rmse_phys = _test_rmse(surr_phys)
print(f"  Test RMSE: mu={mu_rmse_phys:.5f}, sigma={sigma_rmse_phys:.5f}")


def make_fn(surr):
    def fn(x):
        mu, _, sigma, _ = surr.predict(x)
        return mu, sigma
    return fn


# ============================================================
# 2. Ground truth Vmin(WLUD) on the DESIGN RANGE, with censoring
# ============================================================
print("\n=== 2. Compute ground truth (design range WLUD) ===")
wlud_levels_dense = np.linspace(WLUD_LO, 1.0, 20, dtype=np.float64)

cna = np.linspace(COMMON_N_MIN, COMMON_N_MAX, N_GRID)
pua = np.linspace(PU_MIN, PU_MAX, N_GRID)
CN, PU = np.meshgrid(cna, pua, indexing="xy")

true_vmin_3d = np.full((N_GRID, N_GRID, len(wlud_levels_dense)), np.nan)
true_cens_3d = np.zeros((N_GRID, N_GRID, len(wlud_levels_dense)), dtype=bool)
for i in range(N_GRID):
    for j in range(N_GRID):
        cn = float(CN[i, j])
        pu = float(PU[i, j])
        for k, wlud in enumerate(wlud_levels_dense):
            z_vals = np.array([
                analytic_snmr(cn, pu, v, vwl_v=v * wlud)[0] /
                analytic_snmr(cn, pu, v, vwl_v=v * wlud)[1]
                for v in VOPS
            ])
            v, cens = compute_vmin_from_z(z_vals.reshape(1, -1), return_censored=True)
            true_vmin_3d[i, j, k] = float(v[0])
            true_cens_3d[i, j, k] = bool(cens[0])
print(f"  True Vmin grid: {true_vmin_3d.shape} "
      f"({int(true_cens_3d.sum())} censored cells)")

# True required WLUD within the design range
true_wlud_required = np.full((N_GRID, N_GRID), np.nan, dtype=np.float64)
for i in range(N_GRID):
    for j in range(N_GRID):
        vmin_curve = true_vmin_3d[i, j, :]
        if np.isnan(vmin_curve).all():
            continue
        vmin_no_assist = vmin_curve[-1]
        if np.isnan(vmin_no_assist):
            continue
        if vmin_no_assist <= TARGET_VMIN:
            true_wlud_required[i, j] = 1.0  # no assist needed
            continue
        vmin_max_assist = vmin_curve[0]
        if np.isnan(vmin_max_assist) or vmin_max_assist > TARGET_VMIN:
            continue  # infeasible within design range
        lo, hi = 0, len(wlud_levels_dense) - 1
        for _ in range(30):
            mid = (lo + hi) // 2
            if vmin_curve[mid] < TARGET_VMIN:
                lo = mid
            else:
                hi = mid
            if hi - lo <= 1:
                break
        v_lo, v_hi = vmin_curve[lo], vmin_curve[hi]
        if np.isnan(v_lo) or np.isnan(v_hi) or abs(v_hi - v_lo) < 1e-12:
            continue
        t = np.clip((TARGET_VMIN - v_lo) / (v_hi - v_lo), 0.0, 1.0)
        true_wlud_required[i, j] = (wlud_levels_dense[lo]
                                    + t * (wlud_levels_dense[hi] - wlud_levels_dense[lo]))


# ============================================================
# 3. GP assist estimation + corrected metrics (both surrogates)
# ============================================================
print("\n=== 3. Estimate required assist + corrected metrics ===")


def evaluate_surrogate(tag: str, surrogate_fn) -> dict:
    CN_est, PU_est, wlud_required, vmin_achieved = estimate_required_assist(
        surrogate_fn, target_vmin=TARGET_VMIN, vop_fixed=VOP_FIXED,
        n_grid=N_GRID, wlud_lo=WLUD_LO, n_wlud_eval=20,
    )

    gp_feasible = ~np.isnan(wlud_required)
    true_feasible = ~np.isnan(true_wlud_required)
    n_total = N_GRID * N_GRID
    feas_agreement_pct = float((gp_feasible == true_feasible).sum() / n_total * 100)
    feasible_mask = gp_feasible & true_feasible

    # WLUD accuracy on jointly feasible cells
    wlud_error = wlud_required[feasible_mask] - true_wlud_required[feasible_mask]
    wlud_rmse = float(np.sqrt(np.mean(wlud_error ** 2))) if wlud_error.size else np.nan
    wlud_mae = float(np.mean(np.abs(wlud_error))) if wlud_error.size else np.nan

    # Achieved Vmin at the GP's WLUD (interpolated on the true model),
    # with censor propagation from the interpolation endpoints
    vmin_at_gp = np.full((N_GRID, N_GRID), np.nan)
    achieved_cens = np.zeros((N_GRID, N_GRID), dtype=bool)
    for idx in zip(*np.where(feasible_mask)):
        i, j = idx
        w = float(wlud_required[i, j])
        if w <= wlud_levels_dense[0]:
            vmin_at_gp[i, j] = true_vmin_3d[i, j, 0]
            achieved_cens[i, j] = true_cens_3d[i, j, 0]
            continue
        if w >= wlud_levels_dense[-1]:
            vmin_at_gp[i, j] = true_vmin_3d[i, j, -1]
            achieved_cens[i, j] = true_cens_3d[i, j, -1]
            continue
        hi = int(np.searchsorted(wlud_levels_dense, w))
        lo = hi - 1
        t = (w - wlud_levels_dense[lo]) / (wlud_levels_dense[hi] - wlud_levels_dense[lo])
        v_lo, v_hi = true_vmin_3d[i, j, lo], true_vmin_3d[i, j, hi]
        if np.isnan(v_lo) or np.isnan(v_hi):
            continue
        vmin_at_gp[i, j] = v_lo + t * (v_hi - v_lo)
        achieved_cens[i, j] = bool(true_cens_3d[i, j, lo] or true_cens_3d[i, j, hi])

    # Assist-active cells: GP dialed in an interior WLUD
    assist_active = feasible_mask & (wlud_required < 1.0 - 1e-9)
    n_no_assist = int((feasible_mask & ~assist_active).sum())
    interp_mask = assist_active & ~achieved_cens & ~np.isnan(vmin_at_gp)
    n_censored = int((assist_active & achieved_cens).sum())

    if interp_mask.sum() > 0:
        err = vmin_at_gp[interp_mask] - TARGET_VMIN
        vmin_rmse = float(np.sqrt(np.mean(err ** 2)))
        vmin_p95 = float(np.percentile(np.abs(err), 95))
    else:
        vmin_rmse = vmin_p95 = np.nan

    legacy_valid = feasible_mask & ~np.isnan(vmin_at_gp)
    vmin_rmse_legacy = (float(np.sqrt(np.mean((vmin_at_gp[legacy_valid] - TARGET_VMIN) ** 2)))
                        if legacy_valid.sum() else np.nan)

    print(f"\n  [{tag}]")
    print(f"    Feasible GP/true:        {int(gp_feasible.sum())}/{int(true_feasible.sum())} of {n_total}")
    print(f"    Feasibility agreement:   {feas_agreement_pct:.1f}%")
    print(f"    No assist needed:        {n_no_assist}   censored: {n_censored}")
    print(f"    WLUD RMSE / MAE:         {wlud_rmse:.4f} / {wlud_mae:.4f}")
    print(f"    Vmin RMSE (assist-active): {vmin_rmse * 1e3:.2f} mV   p95={vmin_p95 * 1e3:.2f} mV")
    print(f"    Vmin RMSE (legacy defn):   {vmin_rmse_legacy * 1e3:.1f} mV")

    return dict(
        wlud_required=wlud_required, vmin_at_gp=vmin_at_gp,
        feasible_mask=feasible_mask, assist_active=assist_active,
        interp_mask=interp_mask, gp_feasible=gp_feasible,
        n_no_assist=n_no_assist, n_censored=n_censored,
        feas_agreement_pct=feas_agreement_pct,
        wlud_rmse=wlud_rmse, wlud_mae=wlud_mae,
        vmin_rmse=vmin_rmse, vmin_p95=vmin_p95,
        vmin_rmse_legacy=vmin_rmse_legacy,
    )


res_plain = evaluate_surrogate("plain Surrogate", make_fn(surr_plain))
res_phys = evaluate_surrogate("PhysicsConstrainedSurrogate", make_fn(surr_phys))

# ============================================================
# 4. Plots (physics-constrained model)
# ============================================================
print("\n=== 4. Plots (physics-constrained surrogate) ===")
wlud_required = res_phys["wlud_required"]
vmin_at_gp = res_phys["vmin_at_gp"]
feasible_mask = res_phys["feasible_mask"]
interp_mask = res_phys["interp_mask"]

# 4a. Assist map: required WLUD ratio (design range)
fig, ax = plt.subplots(figsize=(8, 6))
cf = ax.contourf(CN, PU, wlud_required, levels=np.linspace(WLUD_LO, 1.0, 21),
                 cmap="viridis", alpha=0.85)
fig.colorbar(cf, ax=ax, label="Required WLUD ratio (Vwl/Vop)")
cs = ax.contour(CN, PU, wlud_required, levels=[0.92, 0.95, 0.98, 1.0],
                colors="w", linewidths=1, linestyles="--")
ax.clabel(cs, inline=True, fontsize=9, fmt="%.2f")
infeasible = np.isnan(wlud_required)
if infeasible.any():
    ax.scatter(CN[infeasible], PU[infeasible], c="red", s=8, alpha=0.5,
               label="Infeasible (design range)")
    ax.legend(fontsize=9)
ax.set_xlabel("common_N (mV)")
ax.set_ylabel("PU (mV)")
ax.set_title(f"Required WLUD for Vmin = {TARGET_VMIN}V @ Vop={VOP_FIXED}V "
             f"(physics-constrained GP)", fontsize=12)
ax.grid(True, alpha=0.15)
fig.savefig(OUT_DIR / "assist_map.png", dpi=150, bbox_inches="tight")
print(f"  Saved: {OUT_DIR / 'assist_map.png'}")
plt.close(fig)

# 4b. Accuracy: WLUD predicted vs true (scatter, assist-active only)
fig, ax = plt.subplots(figsize=(7, 7))
aa = res_phys["assist_active"]
if aa.sum() > 0:
    sc = ax.scatter(true_wlud_required[aa], wlud_required[aa],
                    c=(vmin_at_gp[aa] - TARGET_VMIN) * 1e3,
                    cmap="bwr", s=20, alpha=0.7, vmin=-10, vmax=10)
    fig.colorbar(sc, ax=ax, label="achieved Vmin - target (mV)")
    lo_v = float(min(np.nanmin(true_wlud_required[aa]), np.nanmin(wlud_required[aa])))
    hi_v = float(max(np.nanmax(true_wlud_required[aa]), np.nanmax(wlud_required[aa])))
    ax.plot([lo_v, hi_v], [lo_v, hi_v], "k--", linewidth=1, alpha=0.5)
ax.set_xlabel("True required WLUD ratio")
ax.set_ylabel("GP estimated WLUD ratio")
ax.set_title(f"WLUD estimation, assist-active cells "
             f"(RMSE={res_phys['wlud_rmse']:.4f})")
ax.grid(True, alpha=0.3)
ax.axis("equal")
fig.savefig(OUT_DIR / "assist_accuracy.png", dpi=150, bbox_inches="tight")
print(f"  Saved: {OUT_DIR / 'assist_accuracy.png'}")
plt.close(fig)

# 4c. Achieved Vmin histogram (assist-active, interpolable)
fig, ax = plt.subplots(figsize=(8, 4))
if interp_mask.sum() > 0:
    ax.hist(vmin_at_gp[interp_mask], bins=20, alpha=0.7,
            color="steelblue", edgecolor="white")
    ax.axvline(TARGET_VMIN, color="red", linewidth=2, linestyle="--",
               label=f"Target Vmin={TARGET_VMIN}V")
    ax.set_xlabel("Achieved Vmin (V)")
    ax.set_ylabel("Count")
    ax.set_title(f"Achieved Vmin at GP WLUD (assist-active)  |  "
                 f"RMSE={res_phys['vmin_rmse'] * 1e3:.2f} mV")
    ax.legend()
    ax.grid(True, alpha=0.3)
fig.savefig(OUT_DIR / "achieved_vmin_hist.png", dpi=150, bbox_inches="tight")
print(f"  Saved: {OUT_DIR / 'achieved_vmin_hist.png'}")
plt.close(fig)

# ============================================================
# 5. Metrics + Go/No-Go (physics-constrained model)
# ============================================================
metrics = {
    "stage": 3,
    "surrogate": "PhysicsConstrainedSurrogate(boundary+pelgrom)",
    "target_vmin_V": f"{TARGET_VMIN:.2f}",
    "vop_fixed_V": f"{VOP_FIXED:.1f}",
    "wlud_design_range": f"[{WLUD_LO:.2f}, 1.00]",
    "mu_rmse_plain": f"{mu_rmse_plain:.5f}",
    "mu_rmse_physics": f"{mu_rmse_phys:.5f}",
    "sigma_rmse_plain": f"{sigma_rmse_plain:.5f}",
    "sigma_rmse_physics": f"{sigma_rmse_phys:.5f}",
    "n_grid": N_GRID,
    "feasibility_agreement_pct_plain": f"{res_plain['feas_agreement_pct']:.1f}",
    "feasibility_agreement_pct_physics": f"{res_phys['feas_agreement_pct']:.1f}",
    "wlud_rmse_plain": f"{res_plain['wlud_rmse']:.4f}",
    "wlud_rmse_physics": f"{res_phys['wlud_rmse']:.4f}",
    "vmin_rmse_assist_active_mV_plain": f"{res_plain['vmin_rmse'] * 1e3:.2f}",
    "vmin_rmse_assist_active_mV_physics": f"{res_phys['vmin_rmse'] * 1e3:.2f}",
    "vmin_rmse_legacy_mV_physics": f"{res_phys['vmin_rmse_legacy'] * 1e3:.1f}",
    "n_no_assist_physics": res_phys["n_no_assist"],
    "n_censored_physics": res_phys["n_censored"],
}
print("\n--- Metrics ---")
for k, v in metrics.items():
    print(f"  {k}: {v}")

with open(OUT_DIR / "metrics.txt", "w") as f:
    for k, v in metrics.items():
        f.write(f"{k}: {v}\n")

# Go / No-Go (corrected definitions; thresholds unchanged from plan)
print("\n--- Go/No-Go Check (physics-constrained surrogate) ---")
go = True
r = res_phys
if np.isnan(r["wlud_rmse"]) or r["wlud_rmse"] > 0.05:
    print(f"  [FAIL] WLUD RMSE {r['wlud_rmse']:.4f} > 0.05 (or NaN)")
    go = False
else:
    print(f"  [PASS] WLUD RMSE {r['wlud_rmse']:.4f} <= 0.05")
if r["feas_agreement_pct"] < 90:
    print(f"  [FAIL] Feasibility agreement {r['feas_agreement_pct']:.1f}% < 90%")
    go = False
else:
    print(f"  [PASS] Feasibility agreement {r['feas_agreement_pct']:.1f}% >= 90%")
if np.isnan(r["vmin_rmse"]) or r["vmin_rmse"] > 0.02:
    print(f"  [FAIL] Vmin RMSE (assist-active) {r['vmin_rmse']:.4f} > 0.02 V (or NaN)")
    go = False
else:
    print(f"  [PASS] Vmin RMSE (assist-active) {r['vmin_rmse']:.4f} <= 0.02 V")

print(f"\n  >>> {'GO' if go else 'NO-GO'} <<<")
with open(OUT_DIR / "go_decision.txt", "w") as f:
    f.write("GO\n" if go else "NO-GO\n")
    f.write(f"target_vmin={TARGET_VMIN}V  surrogate=physics(boundary+pelgrom)\n")
    f.write(f"vmin_rmse_assist_active={r['vmin_rmse'] * 1e3:.2f}mV  "
            f"wlud_rmse={r['wlud_rmse']:.4f}  "
            f"feas_agreement={r['feas_agreement_pct']:.1f}%\n")

print("\n=== Stage 3 complete ===")
