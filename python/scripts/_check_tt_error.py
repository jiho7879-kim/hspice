"""
Check: corner-corrected RBF interpolation impact at TT (0,0) and nearby points.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from scipy.interpolate import RBFInterpolator
from src.utils import Z_FIXED, VOPS, N_VOP
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z

TRAINING_NPZ = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "dataset_real.npz"
ORIGINAL_PTH = Path(__file__).resolve().parent.parent / "results" / "stage4_real" / "surrogate_real.pth"
CORNER_XLSX  = Path(__file__).resolve().parent.parent / "data" / "hspice_real_corner.xlsx"

train = np.load(TRAINING_NPZ)
X_tt, y_tt = train["X"], train["y"]
surr = Surrogate.load(ORIGINAL_PTH, X_tt, y_tt, device="cpu")

df = pd.read_excel(CORNER_XLSX).dropna(how="all")
df["mu_V"] = df["snmr_avg"] / 1000.0
df["sigma_V"] = df["snmr_std"] / 1000.0

CORNER_SHIFTS = {"FFG": (-36.42, -44.32), "FSG": (-29.16, 38.64),
                 "SFG": (31.63, -36.76), "SSG": (36.3, 44.79998)}
CORNER_NAMES = ["FFG", "FSG", "SFG", "SSG"]

# Build RBF
corner_mu_res, corner_sigma_res, corner_cnpu = {}, {}, {}
for cn_name in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn_name]
    corner_cnpu[cn_name] = (cn_sh, pu_sh)
    sub = df[df["corner"] == cn_name]
    grp = sub.groupby("vop")[["mu_V", "sigma_V"]].mean().sort_index()
    mu_meas, sigma_meas = grp["mu_V"].values, grp["sigma_V"].values
    Xp = np.zeros((N_VOP, 3), dtype=np.float64)
    Xp[:,0]=cn_sh; Xp[:,1]=pu_sh; Xp[:,2]=VOPS
    mu_pred,_,sigma_pred,_ = surr.predict(Xp)
    corner_mu_res[cn_name] = mu_meas - mu_pred
    corner_sigma_res[cn_name] = sigma_meas - sigma_pred

rbf_points_4 = np.array([corner_cnpu[cn] for cn in CORNER_NAMES])
rbf_points_5 = np.array([corner_cnpu[cn] for cn in CORNER_NAMES] + [(0.0, 0.0)])

def build_rbf(points, include_tt_zero):
    mu_list, sigma_list = [], []
    for vop_idx in range(N_VOP):
        mu_vals = np.array([corner_mu_res[cn][vop_idx] for cn in CORNER_NAMES])
        sg_vals = np.array([corner_sigma_res[cn][vop_idx] for cn in CORNER_NAMES])
        if include_tt_zero:
            mu_vals = np.append(mu_vals, 0.0)
            sg_vals = np.append(sg_vals, 0.0)
        mu_list.append(RBFInterpolator(points, mu_vals.reshape(-1,1), kernel="linear", epsilon=1.0))
        sigma_list.append(RBFInterpolator(points, sg_vals.reshape(-1,1), kernel="linear", epsilon=1.0))
    return mu_list, sigma_list

rbf4_mu, rbf4_sigma = build_rbf(rbf_points_4, False)
rbf5_mu, rbf5_sigma = build_rbf(rbf_points_5, True)

def eval_rbf(mu_rbf, sigma_rbf, cn, pu):
    q = np.array([[cn, pu]])
    mr = np.array([float(mu_rbf[vi](q).ravel()[0]) for vi in range(N_VOP)])
    sr = np.array([float(sigma_rbf[vi](q).ravel()[0]) for vi in range(N_VOP)])
    return mr, sr

# Quick sanity: RBF5 still passes through corners
print("Sanity: RBF5 at FSG Vop=0.6V",
      f"mu_res={float(rbf5_mu[2](np.array([[-29.16, 38.64]])).ravel()[0])*1000:+.2f}mV",
      f"(expected {corner_mu_res['FSG'][2]*1000:+.2f}mV)")

print("=" * 60)
print("Residual at TT (cn=0, pu=0): RBF4 vs RBF5")
print("=" * 60)
mr4, sr4 = eval_rbf(rbf4_mu, rbf4_sigma, 0, 0)
mr5, sr5 = eval_rbf(rbf5_mu, rbf5_sigma, 0, 0)
print(f"  Vop     RBF4_mu     RBF5_mu     RBF4_sg     RBF5_sg")
for vi, vv in enumerate(VOPS):
    print(f"  {vv:.1f}V   {mr4[vi]*1000:>+8.2f}mV {mr5[vi]*1000:>+8.2f}mV  {sr4[vi]*1000:>+8.2f}mV {sr5[vi]*1000:>+8.2f}mV")

# ========================================
# Vmin comparison at TT
# ========================================
Xp = np.zeros((N_VOP, 3), dtype=np.float64)
Xp[:,2] = VOPS
mu_o,_,sigma_o,_ = surr.predict(Xp)

def corrected_vmin(mu_rbf, sigma_rbf, cn=0, pu=0):
    mu_c = mu_o.copy()
    sg_c = sigma_o.copy()
    for vi in range(N_VOP):
        q = np.array([[cn, pu]])
        mu_c[vi] += float(mu_rbf[vi](q).ravel()[0])
        sg_c[vi] += float(sigma_rbf[vi](q).ravel()[0])
    sg_c = np.clip(sg_c, 1e-6, None)
    z = mu_c/(sg_c+1e-12)
    v, _ = compute_vmin_from_z(z.reshape(1,-1), Z_FIXED, return_censored=True)
    return v[0]

# Original Vmin (no correction)
z_orig = mu_o/(sigma_o+1e-12)
v_orig, _ = compute_vmin_from_z(z_orig.reshape(1,-1), Z_FIXED, return_censored=True)
v_orig = v_orig[0]

v_rbf4 = corrected_vmin(rbf4_mu, rbf4_sigma)
v_rbf5 = corrected_vmin(rbf5_mu, rbf5_sigma)
print(f"\nVmin at TT(0,0):  Orig={v_orig:.4f}V  RBF4={v_rbf4:.4f}V  RBF5={v_rbf5:.4f}V")
print(f"  RBF4 delta: {(v_rbf4-v_orig)*1000:+.2f}mV   RBF5 delta: {(v_rbf5-v_orig)*1000:+.2f}mV")

# ========================================
# TT-area training data impact
# ========================================
tt_mask = (np.abs(X_tt[:,0]) < 10) & (np.abs(X_tt[:,1]) < 10)
X_near = X_tt[tt_mask]
y_near = y_tt[tt_mask]
print(f"\nTT-area training pts (|cn|<10,|pu|<10): {len(X_near)}")

mu_orig,_,sg_orig,_ = surr.predict(X_near)

def apply_correction(mu_rbf, sg_rbf, mu_b, sg_b, X):
    mu_c = mu_b.copy()
    sg_c = sg_b.copy()
    for vi, vv in enumerate(VOPS):
        m = np.isclose(X[:,2], vv)
        if not m.any(): continue
        q = np.column_stack([X[m,0], X[m,1]])
        mu_c[m] += float(mu_rbf[vi](q).ravel()[0])
        sg_c[m] += float(sg_rbf[vi](q).ravel()[0])
    return mu_c, np.clip(sg_c, 1e-6, None)

mu_c4, sg_c4 = apply_correction(rbf4_mu, rbf4_sigma, mu_orig, sg_orig, X_near)
mu_c5, sg_c5 = apply_correction(rbf5_mu, rbf5_sigma, mu_orig, sg_orig, X_near)

def rmse(p, t): return np.sqrt(np.mean((p-t)**2))*1000
def bias(p, t): return np.mean(p-t)*1000

print(f"  {'':>20} {'Orig GP':>10} {'RBF4':>10} {'RBF5(+TT)':>12}")
print(f"  {'mu_RMSE':>20} {rmse(mu_orig, y_near[:,0]):>9.2f}mV {rmse(mu_c4, y_near[:,0]):>9.2f}mV {rmse(mu_c5, y_near[:,0]):>9.2f}mV")
print(f"  {'sg_RMSE':>20} {rmse(sg_orig, y_near[:,1]):>9.2f}mV {rmse(sg_c4, y_near[:,1]):>9.2f}mV {rmse(sg_c5, y_near[:,1]):>9.2f}mV")
print(f"  {'mu_bias':>20} {bias(mu_orig, y_near[:,0]):>+9.2f}mV {bias(mu_c4, y_near[:,0]):>+9.2f}mV {bias(mu_c5, y_near[:,0]):>+9.2f}mV")

# ========================================
# Corner Vmin: RBF5 (does it still correct corners?)
# ========================================
print(f"\n--- Corner Vmin: RBF4 (4-corner) vs RBF5 (TT-anchored) ---")
# FIX: For corner Vmin, add correction to GP prediction at the corner, not TT
for cn_name in CORNER_NAMES:
    cn_sh, pu_sh = CORNER_SHIFTS[cn_name]
    sub = df[df["corner"] == cn_name]
    grp = sub.groupby("vop")[["mu_V", "sigma_V"]].mean().sort_index()
    mu_t, sg_t = grp["mu_V"].values, grp["sigma_V"].values
    z_t = mu_t/(sg_t+1e-12)
    v_true, _ = compute_vmin_from_z(z_t.reshape(1,-1), Z_FIXED, return_censored=True)
    v_true = v_true[0]

    # GP prediction at this corner
    Xp = np.zeros((N_VOP, 3), dtype=np.float64)
    Xp[:,0]=cn_sh; Xp[:,1]=pu_sh; Xp[:,2]=VOPS
    mu_cp,_,sg_cp,_ = surr.predict(Xp)

    def _eval_at_pnt(mu_rbf, sg_rbf, cn, pu):
        mu_c = mu_cp.copy()
        sg_c = sg_cp.copy()
        for vi in range(N_VOP):
            q = np.array([[cn, pu]])
            mu_c[vi] += float(mu_rbf[vi](q).ravel()[0])
            sg_c[vi] += float(sg_rbf[vi](q).ravel()[0])
        sg_c = np.clip(sg_c, 1e-6, None)
        z = mu_c/(sg_c+1e-12)
        v, _ = compute_vmin_from_z(z.reshape(1,-1), Z_FIXED, return_censored=True)
        return v[0]

    v_rbf4_corner = _eval_at_pnt(rbf4_mu, rbf4_sigma, cn_sh, pu_sh)
    v_rbf5_corner = _eval_at_pnt(rbf5_mu, rbf5_sigma, cn_sh, pu_sh)
    e4 = (v_rbf4_corner - v_true)*1000
    e5 = (v_rbf5_corner - v_true)*1000
    print(f"  {cn_name}: true={v_true:.4f}V  RBF4={v_rbf4_corner:.4f}V(err={e4:+.2f}mV)  "
          f"RBF5={v_rbf5_corner:.4f}V(err={e5:+.2f}mV)")

# ========================================
# Summary table
# ========================================
print()
print("=" * 60)
print("Summary: RBF4 vs RBF5 (TT-anchored)")
print("=" * 60)
print(f"  {'Metric':>25} {'Orig':>8} {'RBF4':>8} {'RBF5':>8}")
print(f"  {'TT Vmin (V)':>25} {v_orig:>8.4f} {v_rbf4:>8.4f} {v_rbf5:>8.4f}")
print(f"  {'TT Vmin delta (mV)':>25} {'—':>8} {(v_rbf4-v_orig)*1000:>+8.2f} {(v_rbf5-v_orig)*1000:>+8.2f}")
print(f"  {'TT-area mu_RMSE (mV)':>25} {rmse(mu_orig, y_near[:,0]):>8.2f} {rmse(mu_c4, y_near[:,0]):>8.2f} {rmse(mu_c5, y_near[:,0]):>8.2f}")
print(f"  {'TT-area sg_RMSE (mV)':>25} {rmse(sg_orig, y_near[:,1]):>8.2f} {rmse(sg_c4, y_near[:,1]):>8.2f} {rmse(sg_c5, y_near[:,1]):>8.2f}")
