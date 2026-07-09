"""
Stage 4: real HSPICE data Gate (Phase 2).

First run of the GP + physics-layer pipeline on hand-transcribed in-house
simulation results (data/hspice_real.xlsx). Unlike the toy stages, there is
no analytic ground truth here -- Go/No-Go is judged from hold-out
prediction accuracy, physical-direction checks, and corner behavior, per
docs/plans/hspice_sim_scope.md (Stage A) and
docs/plans/phase2_to_paper_plan.md sec 3.6.

Usage:
    python scripts/stage4_real_data.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils import (
    Z_FIXED, VOPS, VOP_COL,
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
    derive_z_target,
)
from src.data import save_intermediate, stratified_train_test_split
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z, compute_vmin_on_grid
from src.contour import extract_contour
from src.hspice_io import parse_manual_xlsx

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "hspice_real.xlsx"
OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "stage4_real"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORNERS = {
    "FSG": (-60, 60), "SFG": (60, -60), "FFG": (-60, -60), "SSG": (60, 60),
}

print("=" * 70)
print("Stage 4: Real HSPICE Data Gate")
print("=" * 70)

# ============================================================
# 1. Load + QC
# ============================================================
print(f"\n=== 1. Load {DATA_PATH.name} ===")
d = parse_manual_xlsx(DATA_PATH)
X, y = d["X"], d["y"]
n_qc = len(d["qc_flags"])
print(f"  Loaded X{X.shape} y{y.shape}  (transcription QC flags: {n_qc})")
print(f"  mu_SNMR range:    [{y[:,0].min():.4f}, {y[:,0].max():.4f}] V")
print(f"  sigma_SNMR range: [{y[:,1].min():.5f}, {y[:,1].max():.5f}] V")

save_intermediate(OUT_DIR / "dataset_real.npz", X, y)

# ============================================================
# 2. Train / hold-out split (stratified by condition, all Vop together)
# ============================================================
print("\n=== 2. Train/hold-out split + GP fit ===")
X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.15, seed=42)
print(f"  train={len(X_tr)}  hold-out={len(X_te)}")

surr = Surrogate(device="cpu")
surr.fit(X_tr, y_tr, verbose=True, n_iter=200)

mu_pred, _, sigma_pred, _ = surr.predict(X_te)
mu_rmse = float(np.sqrt(np.mean((mu_pred - y_te[:, 0]) ** 2)))
sigma_rmse = float(np.sqrt(np.mean((sigma_pred - y_te[:, 1]) ** 2)))
mu_r2 = float(1 - np.sum((mu_pred - y_te[:, 0]) ** 2) / np.sum((y_te[:, 0] - y_te[:, 0].mean()) ** 2))
sigma_r2 = float(1 - np.sum((sigma_pred - y_te[:, 1]) ** 2) / np.sum((y_te[:, 1] - y_te[:, 1].mean()) ** 2))
print(f"\n  Hold-out: mu RMSE={mu_rmse:.5f} R2={mu_r2:.4f}  "
      f"sigma RMSE={sigma_rmse:.5f} R2={sigma_r2:.4f}")

# ============================================================
# 3. Lengthscale analysis (PG >> PU hierarchy -- first real-data check)
# ============================================================
print("\n=== 3. Lengthscale analysis (standardized-input scale) ===")
ls_mu = surr.get_lengthscales("mu")
labels = ["cn", "pu", "Vop"]
for lbl, v in zip(labels, ls_mu):
    print(f"  mu ell_{lbl} = {v:.4f}")
ell_ratio = float(ls_mu[1] / ls_mu[0])  # pu / cn
print(f"  ell_pu / ell_cn = {ell_ratio:.4f}  "
      f"({'PG more sensitive (physical, ell_cn<ell_pu)' if ell_ratio > 1.05 else 'PU more sensitive or tied -- check' if ell_ratio < 0.95 else 'roughly tied'})")

# ============================================================
# 4. Vmin grid + contour (no ground truth -- GP-only)
# ============================================================
print("\n=== 4. Vmin contour (GP prediction, no ground truth available) ===")


def surrogate_fn(x):
    mu, _, sigma, _ = surr.predict(x)
    return mu, sigma


CN, PU, vmin_grid = compute_vmin_on_grid(
    surrogate_fn, n_grid=60,
    common_n_range=(COMMON_N_MIN, COMMON_N_MAX),
    pu_range=(PU_MIN, PU_MAX),
)
finite = np.isfinite(vmin_grid)
print(f"  Vmin range (finite cells): "
      f"[{np.nanmin(vmin_grid[finite]):.3f}, {np.nanmax(vmin_grid[finite]):.3f}] V "
      f"({int(finite.sum())}/{finite.size} finite)")

contour_level = float(np.clip(np.nanmedian(vmin_grid[finite]), 0.4, 0.9))
pred_cn, pred_pu = extract_contour(vmin_grid, CN, PU, contour_level=contour_level)
print(f"  Contour @ Vmin={contour_level:.3f}V (domain median, no fixed target "
      f"available yet): {len(pred_cn)} pts")

# ============================================================
# 5. Corner behavior (nearest available condition to each ideal corner)
# ============================================================
print("\n=== 5. Corner behavior (nearest sampled condition) ===")
uniq_cond = np.unique(X[:, :2], axis=0)
corner_report = {}
for name, (c, p) in CORNERS.items():
    d2 = (uniq_cond[:, 0] - c) ** 2 + (uniq_cond[:, 1] - p) ** 2
    i = int(np.argmin(d2))
    cn_i, pu_i = uniq_cond[i]
    Xc = np.column_stack([np.full(len(VOPS), cn_i), np.full(len(VOPS), pu_i), VOPS])
    mu_c, _, sigma_c, _ = surr.predict(Xc)
    z_c = mu_c / (sigma_c + 1e-12)
    vmin_c, cens_c = compute_vmin_from_z(z_c.reshape(1, -1), z_target=Z_FIXED,
                                         return_censored=True)
    corner_report[name] = {
        "nearest_cond_mV": (float(cn_i), float(pu_i)),
        "dist_mV": float(np.sqrt(d2[i])),
        "vmin_V": float(vmin_c[0]) if not np.isnan(vmin_c[0]) else None,
        "censored": bool(cens_c[0]),
        "z_curve": z_c.tolist(),
    }
    tag = "CENSORED(<0.4V)" if cens_c[0] else ("FAIL(>0.9V)" if np.isnan(vmin_c[0]) else f"{vmin_c[0]:.3f}V")
    print(f"  {name}: nearest=({cn_i:+.0f},{pu_i:+.0f})mV dist={np.sqrt(d2[i]):.1f}mV  "
          f"Vmin={tag}  Z(Vop)={[f'{v:.2f}' for v in z_c]}")

# Sanity: FSG (fast N, slow P) should be the worst (highest Vmin) of the 4
finite_vmins = {k: v["vmin_V"] for k, v in corner_report.items() if v["vmin_V"] is not None}
fsg_is_worst = (len(finite_vmins) >= 2 and
               finite_vmins.get("FSG") == max(finite_vmins.values())) if "FSG" in finite_vmins else None
print(f"  FSG worst-corner check: {'PASS' if fsg_is_worst else ('N/A (FSG censored/fail)' if fsg_is_worst is None else 'FAIL')}")

# ============================================================
# 6. Gradient direction check (finite difference at TT)
# ============================================================
print("\n=== 6. Gradient direction check (finite difference at cn=pu=0) ===")
eps = 5.0  # mV


def _vmin_at(cn, pu):
    Xp = np.column_stack([np.full(len(VOPS), cn), np.full(len(VOPS), pu), VOPS])
    mu, _, sigma, _ = surr.predict(Xp)
    z = mu / (sigma + 1e-12)
    v = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED)
    return float(v[0])


v0 = _vmin_at(0, 0)
v_cn_p = _vmin_at(eps, 0)
v_cn_m = _vmin_at(-eps, 0)
v_pu_p = _vmin_at(0, eps)
v_pu_m = _vmin_at(0, -eps)
grad_cn = (v_cn_p - v_cn_m) / (2 * eps) if not (np.isnan(v_cn_p) or np.isnan(v_cn_m)) else float("nan")
grad_pu = (v_pu_p - v_pu_m) / (2 * eps) if not (np.isnan(v_pu_p) or np.isnan(v_pu_m)) else float("nan")
print(f"  Vmin(0,0) = {v0}")
print(f"  dVmin/dcn ~ {grad_cn:.5f}  (expect < 0: slower NMOS -> less PG leakage -> lower Vmin)")
print(f"  dVmin/dpu ~ {grad_pu:.5f}  (expect > 0: slower PMOS -> weaker pull-up -> higher Vmin)")
grad_ok = (not np.isnan(grad_cn) and not np.isnan(grad_pu)
          and grad_cn < 0 and grad_pu > 0)

# ============================================================
# 7. Plot
# ============================================================
print("\n=== 7. Plot ===")
fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

ax = axes[0]
cf = ax.contourf(CN, PU, vmin_grid, levels=20, cmap="RdYlBu_r", alpha=0.85)
fig.colorbar(cf, ax=ax, label="Vmin (V)", pad=0.02)
if len(pred_cn) > 0:
    ax.plot(pred_cn, pred_pu, "b-", linewidth=2.5,
            label=f"Vmin={contour_level:.2f}V (median)")
ax.scatter(X[:, 0], X[:, 1], s=4, c="k", alpha=0.25, label="sampled conditions")
for name, (c, p) in CORNERS.items():
    ax.plot(c, p, "D", markersize=7, color="darkred", zorder=5)
    ax.annotate(name, (c, p), xytext=(4, 4), textcoords="offset points",
                fontsize=8, color="darkred")
ax.set_xlabel("common_N_shift (mV)")
ax.set_ylabel("PU_shift (mV)")
ax.set_title("(a) Real-data Vmin surface + sampled conditions")
ax.legend(fontsize=8, loc="upper left")
ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX)
ax.set_ylim(PU_MIN, PU_MAX)
ax.grid(True, alpha=0.15)

ax = axes[1]
for v in VOPS:
    mask = np.isclose(X[:, VOP_COL], v)
    ax.scatter(X[mask, 0] - X[mask, 1], y[mask, 0], s=10, alpha=0.5,
              label=f"Vop={v:.1f}V")
ax.set_xlabel("common_N - PU (mV, asymmetry proxy)")
ax.set_ylabel("mu_SNMR (V)")
ax.set_title("(b) mu_SNMR vs Vop (raw hand-entered data)")
ax.legend(fontsize=7, ncol=2)
ax.grid(True, alpha=0.2)

fig.savefig(OUT_DIR / "stage4_real_contour.png", dpi=150, bbox_inches="tight")
print(f"  Saved: {OUT_DIR / 'stage4_real_contour.png'}")
plt.close(fig)

# ============================================================
# 8. Metrics + Go/No-Go
# ============================================================
z_target_exact = derive_z_target()
metrics = {
    "n_conditions": int(len(uniq_cond)),
    "n_samples": int(len(X)),
    "qc_flags": n_qc,
    "mu_rmse": f"{mu_rmse:.5f}",
    "mu_r2": f"{mu_r2:.4f}",
    "sigma_rmse": f"{sigma_rmse:.5f}",
    "sigma_r2": f"{sigma_r2:.4f}",
    "ell_pu_over_ell_cn": f"{ell_ratio:.4f}",
    "grad_dVmin_dcn": f"{grad_cn:.5f}",
    "grad_dVmin_dpu": f"{grad_pu:.5f}",
    "gradient_direction_ok": grad_ok,
    "fsg_worst_corner": fsg_is_worst,
    "z_fixed_used": Z_FIXED,
    "z_target_exact_64Mb_999": f"{z_target_exact:.3f}",
}
print("\n--- Metrics ---")
for k, v in metrics.items():
    print(f"  {k}: {v}")
with open(OUT_DIR / "metrics.txt", "w") as f:
    for k, v in metrics.items():
        f.write(f"{k}: {v}\n")

print("\n--- Go/No-Go Check (hspice_sim_scope.md Stage A criteria) ---")
go = True
if mu_r2 < 0.95:
    print(f"  [FAIL] mu R2 {mu_r2:.4f} < 0.95")
    go = False
else:
    print(f"  [PASS] mu R2 {mu_r2:.4f} >= 0.95")
if not grad_ok:
    print(f"  [FAIL] gradient direction not physical (dVmin/dcn={grad_cn:.5f}, dVmin/dpu={grad_pu:.5f})")
    go = False
else:
    print(f"  [PASS] gradient direction physical")
if fsg_is_worst is False:
    print(f"  [FAIL] FSG is not the worst corner")
    go = False
else:
    print(f"  [{'PASS' if fsg_is_worst else 'SKIP'}] FSG worst-corner check")
if n_qc > 0:
    print(f"  [WARN] {n_qc} transcription QC flags remain -- verify before trusting metrics")

print(f"\n  >>> {'GO' if go else 'NO-GO'} <<<")
with open(OUT_DIR / "go_decision.txt", "w") as f:
    f.write("GO\n" if go else "NO-GO\n")

surr.save(OUT_DIR / "surrogate_real.pth")
print(f"\n=== Stage 4 complete ===")
