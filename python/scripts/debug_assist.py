"""Quick diagnostic: test WLUD-ratio-based model at single (cn,pu) point.

The 4th GP input is WLUD ratio (Vwl/Vop), not absolute Vwl.
When calling analytic_snmr, compute Vwl = WLUD * Vop.
"""
import sys, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import VOPS, VOP_COL, WLUD_COL, Z_FIXED, COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX, WLUD_FACTORS, N_WLUD
from src.physics_layer import compute_vmin_from_z, estimate_required_assist, compute_vmin_vs_vwl
from src.physics import analytic_snmr
from src.surrogate import Surrogate
from src.data import build_dataset, stratified_train_test_split

TARGET_VMIN, VOP_FIXED, N_COND = 0.55, 0.7, 50
rng = np.random.default_rng(42)

# generate data
X_cnpu = build_dataset(N_COND)
n_base = len(X_cnpu)
X_4d = np.zeros((n_base * N_WLUD, 4), dtype=np.float64)
y_4d = np.zeros((n_base * N_WLUD, 2), dtype=np.float64)
for i in range(N_WLUD):
    wlud = WLUD_FACTORS[i]; s = i * n_base; e = (i + 1) * n_base
    X_4d[s:e, :3] = X_cnpu; X_4d[s:e, WLUD_COL] = wlud
    for j in range(n_base):
        cn, pu, vop = X_cnpu[j]
        vwl = vop * wlud  # Vwl = WLUD * Vop
        mu, sigma = analytic_snmr(cn, pu, vop, vwl_v=vwl)
        y_4d[s + j] = [mu + rng.normal(0, 0.002), sigma + rng.normal(0, 0.0005)]

X_tr, X_te, y_tr, y_te = stratified_train_test_split(X_4d, y_4d, 0.15)
surr = Surrogate(device="cpu")
surr.fit(X_tr, y_tr, n_iter=100, verbose=False)

def surrogate_fn(x):
    m, _, s, _ = surr.predict(x)
    return m, s

# Test a single (cn, pu) point at various WLUD levels
print("=== Single-point diagnostic (cn=0, pu=0) ===")
cn, pu = 0.0, 0.0
wlud_test = np.linspace(0.90, 1.0, 20)
print(f"{'WLUD':>8s} {'True_mu':>8s} {'GP_mu':>8s} {'mu_err':>8s} {'True_Vmin':>10s} {'GP_Vmin':>10s}")
for wlud in wlud_test[::4]:
    # True: Vwl = WLUD * Vop per Vop level
    vwl_for_true = [v * wlud for v in VOPS]
    z_true = np.array([analytic_snmr(cn, pu, v, vwl_v=vwl_for_true[ki])[0] / analytic_snmr(cn, pu, v, vwl_v=vwl_for_true[ki])[1]
                       for ki, v in enumerate(VOPS)])
    vmin_true = float(compute_vmin_from_z(z_true.reshape(1, -1))[0])
    mu_true = analytic_snmr(cn, pu, VOP_FIXED, vwl_v=VOP_FIXED * wlud)[0]

    # GP: X=[cn,pu,VOP_FIXED, wlud_ratio]
    X_test = np.array([[cn, pu, VOP_FIXED, wlud]], dtype=np.float64)
    mu_gp = float(surr.predict(X_test)[0][0])

    z_gp = np.array([surrogate_fn(np.array([[cn, pu, v, wlud]]))[0][0] /
                     surrogate_fn(np.array([[cn, pu, v, wlud]]))[1][0] for v in VOPS])
    vmin_gp = float(compute_vmin_from_z(z_gp.reshape(1, -1))[0])

    print(f"{wlud:>8.4f} {mu_true:>8.5f} {mu_gp:>8.5f} {mu_true-mu_gp:>8.5f} {vmin_true:>10.4f} {vmin_gp:>10.4f}")

# Now check estimate_required_assist accuracy
print("\n=== Estimate required assist diagnostic ===")
n_grid = 20
CN_est, PU_est, wlud_req, vmin_gp_res = estimate_required_assist(
    surrogate_fn, TARGET_VMIN, VOP_FIXED, n_grid=n_grid, wlud_lo=0.90, n_wlud_eval=20)

feas = ~np.isnan(wlud_req)
idxs = np.argwhere(feas)
print(f"Feasible: {len(idxs)}/{n_grid*n_grid}")

# Sample points for detailed check
errors = []
for idx in idxs[:20]:
    i, j = idx
    cn, pu = float(CN_est[i, j]), float(PU_est[i, j])
    wlud = wlud_req[i, j]

    # True Vmin at GP's recommended WLUD: Vwl = WLUD * Vop per point
    z = np.array([analytic_snmr(cn, pu, v, vwl_v=v * wlud)[0] /
                  analytic_snmr(cn, pu, v, vwl_v=v * wlud)[1] for v in VOPS])
    vmin_true = float(compute_vmin_from_z(z.reshape(1, -1))[0])
    err = vmin_true - TARGET_VMIN
    errors.append(err)

errors = np.array(errors)
print(f"Vmin error: mean={np.mean(errors):.4f} std={np.std(errors):.4f} RMSE={np.sqrt(np.mean(errors**2)):.4f}")
print(f"Error min={np.min(errors):.4f} max={np.max(errors):.4f}")
print(f"Positive errors: {np.sum(errors > 0)}/{len(errors)} (GP WLUD too conservative)")
print(f"Negative errors: {np.sum(errors < 0)}/{len(errors)} (GP WLUD too aggressive)")
