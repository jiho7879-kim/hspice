"""
Stage B: real HSPICE data Gate (Phase 2) -- 4D with PG/PD skew.

Second real-data gate (after Stage A / stage4_real_data.py), now on the
4D input [cn, sk, pu, Vop] where sk = PG-PD Vth skew (PG = cn+sk, PD = cn-sk).
Data: hand-transcribed in-house PrimeSim results, data/260713_stageB_snmr.xlsx
(sheet stageB_snmr), 348 conditions x 5 Vop levels (0.4-0.8).

Go/No-Go mirrors the Stage A criteria (hspice_sim_scope.md), extended with
skew diagnostics:
  1. hold-out mu R2 >= 0.95
  2. Vmin gradient direction physical (dVmin/dcn < 0, dVmin/dpu > 0)
  3. FSG (fast-N slow-P) is the worst (highest-Vmin) corner
Informational: ell hierarchy (PG vs PU), skew sensitivity (ell_sk, dVmin/dsk),
sigma R2.

Usage:  cd python && python scripts/stageB_real_data.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils import (
    Z_FIXED, COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX, derive_z_target,
)
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z
from src.contour import extract_contour
from src.hspice_io import parse_manual_xlsx

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "260713_stageB_snmr.xlsx"
OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "stageB_real"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Vop levels actually present in the Stage B data (Z=6.50 -> 0.4..0.8 suffices).
# Do NOT use the global 6-level VOPS (would extrapolate the GP to 0.9).
DATA_VOPS = np.array([0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float64)

# Ideal process corners in (cn, pu) at sk=0 (skew nominal).
CORNERS = {
    "FSG": (-60, 60), "SFG": (60, -60), "FFG": (-60, -60), "SSG": (60, 60),
}

print("=" * 70)
print("Stage B: Real HSPICE Data Gate (4D: cn, sk, pu, Vop)")
print("=" * 70)

# ============================================================
# 1. Load + QC
# ============================================================
print(f"\n=== 1. Load {DATA_PATH.name} ===")
d = parse_manual_xlsx(DATA_PATH)
X, y = d["X"], d["y"]
n_qc = len(d["qc_flags"])
n_device = X.shape[1] - 1          # 3 (cn, sk, pu)
vop_col = n_device                 # 3
pu_col = vop_col - 1               # 2
sk_col = 1
assert n_device == 3, f"expected 4D Stage-B input, got X{X.shape}"
print(f"  Loaded X{X.shape} y{y.shape}  (n_device={n_device}, vop_col={vop_col}, QC flags={n_qc})")
print(f"  cn [{X[:,0].min():.0f},{X[:,0].max():.0f}]  sk [{X[:,sk_col].min():.0f},{X[:,sk_col].max():.0f}]  "
      f"pu [{X[:,pu_col].min():.0f},{X[:,pu_col].max():.0f}]  Vop [{X[:,vop_col].min():.2f},{X[:,vop_col].max():.2f}]")
print(f"  mu_SNMR range:    [{y[:,0].min():.4f}, {y[:,0].max():.4f}] V")
print(f"  sigma_SNMR range: [{y[:,1].min():.5f}, {y[:,1].max():.5f}] V")
uniq_cond = np.unique(X[:, :vop_col], axis=0)
print(f"  distinct conditions (cn,sk,pu): {len(uniq_cond)}")

# ============================================================
# 2. Condition-grouped train / hold-out split (group by ALL device dims)
#    (src.stratified_train_test_split groups by X[:,:2]=(cn,sk) only -- wrong
#     for Stage B; do a proper (cn,sk,pu)-level split here to avoid leakage.)
# ============================================================
print("\n=== 2. Train/hold-out split (condition-grouped) + GP fit ===")
_, inv = np.unique(X[:, :vop_col], axis=0, return_inverse=True)
cond_ids = np.unique(inv)
rng = np.random.default_rng(42)
rng.shuffle(cond_ids)
n_test = max(1, int(len(cond_ids) * 0.15))
test_ids = set(cond_ids[:n_test].tolist())
test_mask = np.array([i in test_ids for i in inv])
X_tr, X_te, y_tr, y_te = X[~test_mask], X[test_mask], y[~test_mask], y[test_mask]
print(f"  conditions: train={len(cond_ids)-n_test} hold-out={n_test}  "
      f"rows: train={len(X_tr)} hold-out={len(X_te)}")

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
# 3. Lengthscale analysis (PG(cn,sk) vs PU hierarchy)
# ============================================================
print("\n=== 3. Lengthscale analysis (standardized-input scale) ===")
ls_mu = surr.get_lengthscales("mu")
labels = ["cn", "sk", "pu", "Vop"]
for lbl, v in zip(labels, ls_mu):
    print(f"  mu ell_{lbl} = {v:.4f}")
ell_pu_cn = float(ls_mu[pu_col] / ls_mu[0])       # pu / cn  (>1 => cn more sensitive)
ell_pu_sk = float(ls_mu[pu_col] / ls_mu[sk_col])  # pu / sk
print(f"  ell_pu/ell_cn = {ell_pu_cn:.3f}  "
      f"({'cn (PG baseline) more sensitive' if ell_pu_cn > 1.05 else 'PU more sensitive/tied'})")
print(f"  ell_pu/ell_sk = {ell_pu_sk:.3f}  (skew sensitivity relative to PU)")

# ============================================================
# 4. Vmin helper + corner behavior (at sk=0)
# ============================================================
def vmin_curve(cn, sk, pu, vops=DATA_VOPS):
    Xp = np.column_stack([np.full(len(vops), cn), np.full(len(vops), sk),
                          np.full(len(vops), pu), vops])
    mu, _, sigma, _ = surr.predict(Xp)
    z = mu / (sigma + 1e-12)
    v, cens = compute_vmin_from_z(z.reshape(1, -1), z_target=Z_FIXED, vops=vops,
                                  return_censored=True)
    return float(v[0]), bool(cens[0]), z


print("\n=== 4. Corner behavior (nearest sampled condition, sk=0 ideal) ===")
corner_report = {}
for name, (c, p) in CORNERS.items():
    ideal = np.array([c, 0.0, p])
    d2 = np.sum((uniq_cond - ideal) ** 2, axis=1)
    i = int(np.argmin(d2))
    cn_i, sk_i, pu_i = uniq_cond[i]
    vmin_c, cens_c, z_c = vmin_curve(cn_i, sk_i, pu_i)
    corner_report[name] = {
        "nearest_cond_mV": (float(cn_i), float(sk_i), float(pu_i)),
        "dist_mV": float(np.sqrt(d2[i])),
        "vmin_V": None if (np.isnan(vmin_c) or cens_c) else vmin_c,
        "censored": cens_c,
    }
    tag = "CENSORED(<0.4V)" if cens_c else ("FAIL(>0.8V)" if np.isnan(vmin_c) else f"{vmin_c:.3f}V")
    print(f"  {name}: nearest=({cn_i:+.0f},{sk_i:+.0f},{pu_i:+.0f})mV dist={np.sqrt(d2[i]):.1f}mV  "
          f"Vmin={tag}  Z={[f'{v:.2f}' for v in z_c]}")

finite_vmins = {k: v["vmin_V"] for k, v in corner_report.items() if v["vmin_V"] is not None}
fsg_is_worst = (len(finite_vmins) >= 2 and
                finite_vmins.get("FSG") == max(finite_vmins.values())) if "FSG" in finite_vmins else None
print(f"  FSG worst-corner check: {'PASS' if fsg_is_worst else ('N/A' if fsg_is_worst is None else 'FAIL')}")

# ============================================================
# 5. Gradient direction check (finite difference at cn=sk=pu=0)
# ============================================================
print("\n=== 5. Gradient direction check (finite difference at origin) ===")
eps = 5.0  # mV
v0, _, _ = vmin_curve(0, 0, 0)
def _g(dcn, dsk, dpu):
    vp, cp, _ = vmin_curve(dcn, dsk, dpu)
    vm, cm, _ = vmin_curve(-dcn, -dsk, -dpu)
    if np.isnan(vp) or np.isnan(vm) or cp or cm:
        return float("nan")
    return (vp - vm) / (2 * eps)
grad_cn = _g(eps, 0, 0)
grad_sk = _g(0, eps, 0)
grad_pu = _g(0, 0, eps)
print(f"  Vmin(0,0,0) = {v0:.4f} V")
print(f"  dVmin/dcn ~ {grad_cn:+.5f}  (expect < 0: slower NMOS baseline -> lower Vmin)")
print(f"  dVmin/dsk ~ {grad_sk:+.5f}  (informational: PG-PD asymmetry effect on read stability)")
print(f"  dVmin/dpu ~ {grad_pu:+.5f}  (expect > 0: slower PMOS -> weaker pull-up -> higher Vmin)")
grad_ok = (not np.isnan(grad_cn) and not np.isnan(grad_pu) and grad_cn < 0 and grad_pu > 0)

# ============================================================
# 6. Vmin contour over (cn, pu) at sk=0  (manual grid, DATA_VOPS)
# ============================================================
print("\n=== 6. Vmin contour (GP prediction at sk=0) ===")
n_grid = 60
cna = np.linspace(COMMON_N_MIN, COMMON_N_MAX, n_grid)
pua = np.linspace(PU_MIN, PU_MAX, n_grid)
CN, PU = np.meshgrid(cna, pua, indexing="xy")
nv = len(DATA_VOPS)
Xg = np.zeros((n_grid * n_grid * nv, 4))
for i in range(n_grid):
    for j in range(n_grid):
        base = (i * n_grid + j) * nv
        Xg[base:base + nv, 0] = CN[i, j]
        Xg[base:base + nv, sk_col] = 0.0
        Xg[base:base + nv, pu_col] = PU[i, j]
        Xg[base:base + nv, vop_col] = DATA_VOPS
mu_g, _, sig_g, _ = surr.predict(Xg)
z_g = (mu_g / (sig_g + 1e-12)).reshape(n_grid * n_grid, nv)
vmin_grid = compute_vmin_from_z(z_g, z_target=Z_FIXED, vops=DATA_VOPS).reshape(n_grid, n_grid)
finite = np.isfinite(vmin_grid)
print(f"  Vmin finite cells: {int(finite.sum())}/{finite.size}  "
      f"range [{np.nanmin(vmin_grid[finite]):.3f}, {np.nanmax(vmin_grid[finite]):.3f}] V")
contour_level = float(np.clip(np.nanmedian(vmin_grid[finite]), 0.4, 0.8))
pred_cn, pred_pu = extract_contour(vmin_grid, CN, PU, contour_level=contour_level)
print(f"  Contour @ Vmin={contour_level:.3f}V (domain median): {len(pred_cn)} pts")

# ============================================================
# 7. Plot
# ============================================================
print("\n=== 7. Plot ===")
fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
ax = axes[0]
cf = ax.contourf(CN, PU, vmin_grid, levels=20, cmap="RdYlBu_r", alpha=0.85)
fig.colorbar(cf, ax=ax, label="Vmin (V)", pad=0.02)
if len(pred_cn) > 0:
    ax.plot(pred_cn, pred_pu, "b-", lw=2.5, label=f"Vmin={contour_level:.2f}V (median)")
sk0 = np.abs(X[:, sk_col]) <= 6
ax.scatter(X[sk0, 0], X[sk0, pu_col], s=5, c="k", alpha=0.25, label="conditions (|sk|<=6)")
for name, (c, p) in CORNERS.items():
    ax.plot(c, p, "D", ms=7, color="darkred", zorder=5)
    ax.annotate(name, (c, p), xytext=(4, 4), textcoords="offset points", fontsize=8, color="darkred")
ax.set_xlabel("common_N_shift (mV)"); ax.set_ylabel("PU_shift (mV)")
ax.set_title("(a) Stage B Vmin surface @ sk=0")
ax.legend(fontsize=8, loc="upper left")
ax.set_xlim(COMMON_N_MIN, COMMON_N_MAX); ax.set_ylim(PU_MIN, PU_MAX); ax.grid(True, alpha=0.15)

ax = axes[1]
for v in DATA_VOPS:
    m = np.isclose(X[:, vop_col], v)
    ax.scatter(X[m, sk_col], y[m, 0], s=9, alpha=0.5, label=f"Vop={v:.1f}")
ax.set_xlabel("PG-PD skew sk (mV)"); ax.set_ylabel("mu_SNMR (V)")
ax.set_title("(b) mu_SNMR vs skew (raw data)")
ax.legend(fontsize=7, ncol=2); ax.grid(True, alpha=0.2)
fig.savefig(OUT_DIR / "stageB_real_contour.png", dpi=150, bbox_inches="tight")
print(f"  Saved: {OUT_DIR / 'stageB_real_contour.png'}")
plt.close(fig)

# ============================================================
# 8. Metrics + Go/No-Go
# ============================================================
metrics = {
    "n_conditions": int(len(uniq_cond)),
    "n_samples": int(len(X)),
    "qc_flags": n_qc,
    "mu_rmse": f"{mu_rmse:.5f}", "mu_r2": f"{mu_r2:.4f}",
    "sigma_rmse": f"{sigma_rmse:.5f}", "sigma_r2": f"{sigma_r2:.4f}",
    "ell_cn": f"{ls_mu[0]:.4f}", "ell_sk": f"{ls_mu[sk_col]:.4f}",
    "ell_pu": f"{ls_mu[pu_col]:.4f}", "ell_vop": f"{ls_mu[vop_col]:.4f}",
    "ell_pu_over_cn": f"{ell_pu_cn:.3f}", "ell_pu_over_sk": f"{ell_pu_sk:.3f}",
    "grad_dVmin_dcn": f"{grad_cn:.5f}", "grad_dVmin_dsk": f"{grad_sk:.5f}",
    "grad_dVmin_dpu": f"{grad_pu:.5f}", "gradient_direction_ok": grad_ok,
    "fsg_worst_corner": fsg_is_worst,
    "z_fixed_used": Z_FIXED, "z_target_exact": f"{derive_z_target():.3f}",
}
print("\n--- Metrics ---")
for k, v in metrics.items():
    print(f"  {k}: {v}")
with open(OUT_DIR / "metrics.txt", "w") as f:
    for k, v in metrics.items():
        f.write(f"{k}: {v}\n")

print("\n--- Go/No-Go (Stage A criteria, extended) ---")
go = True
if mu_r2 < 0.95:
    print(f"  [FAIL] mu R2 {mu_r2:.4f} < 0.95"); go = False
else:
    print(f"  [PASS] mu R2 {mu_r2:.4f} >= 0.95")
if not grad_ok:
    print(f"  [FAIL] gradient direction (dVmin/dcn={grad_cn:.5f}, dVmin/dpu={grad_pu:.5f})"); go = False
else:
    print(f"  [PASS] gradient direction physical")
if fsg_is_worst is False:
    print(f"  [FAIL] FSG not worst corner"); go = False
else:
    print(f"  [{'PASS' if fsg_is_worst else 'SKIP'}] FSG worst-corner check")
if n_qc > 0:
    print(f"  [WARN] {n_qc} transcription QC flags remain")

print(f"\n  >>> {'GO' if go else 'NO-GO'} <<<")
with open(OUT_DIR / "go_decision.txt", "w") as f:
    f.write("GO\n" if go else "NO-GO\n")
surr.save(OUT_DIR / "surrogate_stageB.pth")
print("\n=== Stage B gate complete ===")
