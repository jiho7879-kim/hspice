"""
SKY130-calibrated SRAM Vmin contour plot.

Extracted from SKY130 PDK model files:
  NMOS (nfet_01v8):  Avt = 0.003356 V.um  (vth0_slope)
  PMOS (pfet_01v8):  Avt = 0.005856 V.um  (vth0_slope, 1.74x NMOS)

SRAM cell sizing (OpenRAM SKY130 config):
  PD (NMOS driver): W=1.6um  L=0.15um  sigma_Vth = Avt/sqrt(W*L) = 6.85 mV
  PG (NMOS access): W=0.8um  L=0.15um  sigma_Vth = 9.69 mV
  PU (PMOS load):   W=0.6um  L=0.15um  sigma_Vth = 19.52 mV

Beta ratio (PD:PG) = 2:1, Pull-up ratio (PU:PG) = 0.75:1
Nominal Vdd = 1.8V, Vth0_n(nmos) ≈ 0.494V, Vth0_p(pmos) ≈ -0.66V
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.stats import qmc

# ============================================================
# SKY130 Pelgrom coefficients (from PDK model files)
# ============================================================
AVT_NMOS = 0.003356   # V.um  (nfet_01v8 vth0_slope)
AVT_PMOS = 0.005856   # V.um  (pfet_01v8 vth0_slope)

# SKY130 SRAM cell sizing (from OpenRAM config)
L_MIN = 0.15   # um
W_PD  = 1.6    # um  (NMOS driver)
W_PG  = 0.8    # um  (NMOS access)
W_PU  = 0.6    # um  (PMOS load)

# Per-device local mismatch sigma (Pelgrom scaling)
SIGMA_VTH_PD = AVT_NMOS / np.sqrt(W_PD * L_MIN) * 1000   # mV
SIGMA_VTH_PG = AVT_NMOS / np.sqrt(W_PG * L_MIN) * 1000   # mV
SIGMA_VTH_PU = AVT_PMOS / np.sqrt(W_PU * L_MIN) * 1000   # mV

print("=== SKY130 Per-Device Mismatch (1-sigma) ===")
print(f"  PD (NMOS, W={W_PD}um):  {SIGMA_VTH_PD:.2f} mV")
print(f"  PG (NMOS, W={W_PG}um):  {SIGMA_VTH_PG:.2f} mV")
print(f"  PU (PMOS, W={W_PU}um):  {SIGMA_VTH_PU:.2f} mV")
print(f"  PMOS/NMOS Avt ratio: {AVT_PMOS/AVT_NMOS:.2f}")

# Combined local mismatch contribution to SNM sigma
# 6 devices in 6T SRAM: 2 PD + 2 PG + 2 PU
# First-order: equal weight w=0.4 (typical Vth-to-SNM gain)
W_GAIN = 0.4
SIGMA_SNM_LOCAL = W_GAIN * np.sqrt(
    2 * (AVT_NMOS / np.sqrt(W_PD * L_MIN))**2 +
    2 * (AVT_NMOS / np.sqrt(W_PG * L_MIN))**2 +
    2 * (AVT_PMOS / np.sqrt(W_PU * L_MIN))**2
)
print(f"\n  Combined local SNM sigma: {SIGMA_SNM_LOCAL*1000:.1f} mV (gain={W_GAIN})")

# ============================================================
# Global process variation bounds
# ============================================================
# SKY130 corner Vth spread: SS-FF ≈ 100-150mV for nominal devices
# 3-sigma global per type ≈ ±60mV
CN_MIN, CN_MAX = -60.0, 60.0   # mV  (common NMOS shift)
PU_MIN, PU_MAX = -60.0, 60.0   # mV  (common PMOS shift)

# ============================================================
# Vop sweep
# ============================================================
VOPS = np.array([0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
N_VOP = len(VOPS)
VDD_NOM = 1.8

# ============================================================
# Analytic SNMR model (coefficients derived from SKY130)
# ============================================================
# The PMOS has 1.74x larger Avt than NMOS, and PU devices are
# 2.67x weaker than PD (strength ratio = W_PD/W_PU for same L).
# Combined: PMOS Vth sensitivity ≈ 1.74 * (W_PD/W_PU) / ... 
# More directly: trip point sensitivity ratio from beta ratio analysis
# With PD:PG:PU = 1.6:0.8:0.6 um:
#   Inverter NMOS/PMOS strength ratio = W_PD/W_PU = 2.67
#   For hold SNM, both inverter devices (PD, PU) and access (PG) contribute
#   Net sensitivity ratio |C_MU/B_MU| ≈ (W_PD/W_PU)^0.7 ≈ 2.0
# This is the SKY130-calibrated ratio (vs 1.5 in the toy project default)

A_MU = 0.15            # Vop sensitivity (V/V): same as toy project
B_MU = +0.001          # common_N shift (V/mV): NMOS Vth sensitivity
C_MU = -0.0020         # PU shift (V/mV): PMOS Vth sensitivity (2.0x NMOS)
D_MU = 0.0             # bias term (V)

# Sigma model: Vop-dependent, derived from combined local mismatch
# At Vop=VDD_NOM=1.8V, sigma_local ≈ 12.9mV (with gain=0.4)
# At lower Vop, relative variation increases
SIGMA0 = 0.013         # sigma at Vop=0.9V (~13mV from combined mismatch)
SIGMA_VOP_SLOPE = 0.004  # increase at lower Vop

print(f"\n=== Model coefficients ===")
print(f"  A_MU={A_MU}, B_MU={B_MU}, C_MU={C_MU}, D_MU={D_MU}")
print(f"  |C_MU/B_MU| = {abs(C_MU/B_MU):.2f} (SKY130-target: ~2.0)")
print(f"  SIGMA0={SIGMA0}, SIGMA_VOP_SLOPE={SIGMA_VOP_SLOPE}")

# ============================================================
# Sobol sampling (35/25/20/20 balanced)
# ============================================================
N_COND = 400

def sobol_2d(n_pts, lo, hi, seed=42):
    sampler = qmc.Sobol(d=2, scramble=True, seed=seed)
    m = int(2 ** np.ceil(np.log2(n_pts)))
    pts = sampler.random(n=m)
    pts = qmc.scale(pts, lo, hi)
    return pts[:n_pts].astype(np.float64)

def sample_conditions(n_total, seed=42):
    n_fsg = int(n_total * 0.35)
    n_sfg = int(n_total * 0.25)
    n_ffg = int(n_total * 0.20)
    n_ssg = n_total - n_fsg - n_sfg - n_ffg
    rng = np.random.default_rng(seed)
    pts = []
    pts.append(sobol_2d(n_fsg, [CN_MIN, 0.0], [0.0, PU_MAX], seed))
    pts.append(sobol_2d(n_sfg, [0.0, PU_MIN], [CN_MAX, 0.0], seed+1))
    pts.append(sobol_2d(n_ffg, [CN_MIN, PU_MIN], [0.0, 0.0], seed+2))
    pts.append(sobol_2d(n_ssg, [0.0, 0.0], [CN_MAX, PU_MAX], seed+3))
    out = np.concatenate(pts, axis=0)
    rng.shuffle(out)
    return out  # (n_total, 2): [common_N, PU]

# ============================================================
# Generate synthetic data
# ============================================================
print(f"\n=== Generating {N_COND} conditions x {N_VOP} Vop ===")
cn_pu = sample_conditions(N_COND)
np.savez_compressed(Path(__file__).resolve().parent / "data.npz",
    X=cn_pu, A_MU=A_MU, B_MU=B_MU, C_MU=C_MU, D_MU=D_MU,
    SIGMA0=SIGMA0, SIGMA_VOP_SLOPE=SIGMA_VOP_SLOPE)

X = np.zeros((N_COND * N_VOP, 3))
y = np.zeros((N_COND * N_VOP, 2))
rng = np.random.default_rng(42)

for i in range(N_COND):
    cn, pu = cn_pu[i]
    for j, vop in enumerate(VOPS):
        idx = i * N_VOP + j
        mu = A_MU * vop + B_MU * cn + C_MU * pu + D_MU
        sigma_here = SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - vop)
        X[idx] = [cn, pu, vop]
        y[idx] = [mu + rng.normal(0, 0.002), sigma_here + rng.normal(0, 0.0005)]

print(f"  X: {X.shape}, y: {y.shape}")
print(f"  mu range: [{y[:,0].min():.4f}, {y[:,0].max():.4f}]")
print(f"  sigma range: [{y[:,1].min():.5f}, {y[:,1].max():.5f}]")

# ============================================================
# GP Surrogate (use proven class from toy_project)
# ============================================================
print("\n=== GP Surrogate ===")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "toy_project"))
from src.toy_surrogate import Surrogate, stratified_train_test_split

X_tr, X_te, y_tr, y_te = stratified_train_test_split(X, y, test_frac=0.15)

print(f"  Train: {X_tr.shape}, Test: {X_te.shape}")

surr = Surrogate(device="cpu")
print("  Training mu GP...")
surr.fit(X_tr, y_tr, verbose=False, n_iter=80)
mu_pred, _, sigma_pred, _ = surr.predict(X_te)
mu_rmse = np.sqrt(np.mean((mu_pred - y_te[:, 0])**2))
sigma_rmse = np.sqrt(np.mean((sigma_pred - y_te[:, 1])**2))
print(f"  mu RMSE: {mu_rmse:.5f}")
print(f"  sigma RMSE: {sigma_rmse:.5f}")

# Combined predictor
def surrogate_fn(x):
    mu, _, sigma, _ = surr.predict(x)
    return mu, sigma

# ============================================================
# Vmin on grid
# ============================================================
print("\n=== Vmin Grid & Contour ===")

def compute_vmin(z, z_target=6.0, vops=VOPS):
    """Interpolate Vmin where Z = z_target."""
    n = z.shape[0]
    vmin = np.full(n, np.nan)
    for i in range(n):
        zi = z[i]
        if zi[0] > z_target:
            vmin[i] = vops[0] - 0.05
            continue
        if zi[-1] < z_target:
            continue
        for j in range(len(vops) - 1):
            if zi[j] <= z_target <= zi[j+1]:
                t = (z_target - zi[j]) / (zi[j+1] - zi[j] + 1e-12)
                vmin[i] = vops[j] + t * (vops[j+1] - vops[j])
                break
    return vmin

n_grid = 60
cna = np.linspace(CN_MIN, CN_MAX, n_grid)
pua = np.linspace(PU_MIN, PU_MAX, n_grid)
CN, PU = np.meshgrid(cna, pua, indexing="xy")

# Predicted Vmin
X_grid = np.zeros((n_grid * n_grid * N_VOP, 3))
for i in range(n_grid):
    for j in range(n_grid):
        idx = (i * n_grid + j) * N_VOP
        X_grid[idx:idx+N_VOP, 0] = CN[i, j]
        X_grid[idx:idx+N_VOP, 1] = PU[i, j]
        X_grid[idx:idx+N_VOP, 2] = VOPS

mu_g, sigma_g = surrogate_fn(X_grid)
z_g = mu_g / (sigma_g + 1e-12)
vmin_pred = compute_vmin(z_g.reshape(n_grid, n_grid, N_VOP).reshape(-1, N_VOP))
vmin_pred = vmin_pred.reshape(n_grid, n_grid)

# True Vmin
true_analytic = np.full((n_grid, n_grid), np.nan)
for i in range(n_grid):
    for j in range(n_grid):
        cn = float(CN[i, j])
        pu = float(PU[i, j])
        z = np.array([
            (A_MU * v + B_MU * cn + C_MU * pu + D_MU) /
            (SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - v))
            for v in VOPS
        ])
        true_analytic[i, j] = float(compute_vmin(z.reshape(1, -1))[0])

print(f"  True Vmin: [{np.nanmin(true_analytic):.3f}, {np.nanmax(true_analytic):.3f}]")
print(f"  Pred Vmin: [{np.nanmin(vmin_pred):.3f}, {np.nanmax(vmin_pred):.3f}]")

# Extract 0.6V contour
def extract_contour(vmin_g, CN, PU, level=0.6):
    """Extract contour line at Vmin=level using contourpy."""
    from contourpy import contour_generator
    v = vmin_g.copy()
    v[np.isnan(v)] = level + 999
    cg = contour_generator(x=CN[0], y=PU[:, 0], z=v)
    try:
        lines = cg.lines(level)
        if len(lines) > 0:
            verts = lines[0]
            return verts[:, 0], verts[:, 1]
        return np.array([]), np.array([])
    except Exception:
        return np.array([]), np.array([])

pred_cn, pred_pu = extract_contour(vmin_pred, CN, PU, 0.6)
true_cn, true_pu = extract_contour(true_analytic, CN, PU, 0.6)
print(f"  True contour @ 0.6V: {len(true_cn)} pts")
print(f"  Pred contour @ 0.6V: {len(pred_cn)} pts")

# ============================================================
# Plot
# ============================================================
print("\n=== Plot ===")
corners = {"FSG": (-60, 60), "SFG": (60, -60), "FFG": (-60, -60), "SSG": (60, 60)}

fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

# (a) Vmin surface
ax = axes[0]
cf = ax.contourf(CN, PU, vmin_pred, levels=np.linspace(0.3, 0.9, 25),
                 cmap="RdYlBu_r", alpha=0.85)
fig.colorbar(cf, ax=ax, label="Vmin (V)", pad=0.02)
ax.contour(CN, PU, vmin_pred, levels=[0.5, 0.6, 0.7, 0.8],
           colors="k", linewidths=0.6, linestyles="--", alpha=0.4)
if len(true_cn) > 0:
    ax.plot(true_cn, true_pu, "r--", lw=2, alpha=0.8, label="True Vmin=0.6V")
if len(pred_cn) > 0:
    ax.plot(pred_cn, pred_pu, "b-", lw=2.5, alpha=0.9, label="GP Vmin=0.6V")
for name, (cn, pu) in corners.items():
    ax.plot(cn, pu, "D", markersize=7, color="darkred", zorder=5)
    ax.annotate(name, (cn, pu), xytext=(4, 4),
                textcoords="offset points", fontsize=8, color="darkred")
ax.set_xlabel("common_N_shift (mV)  [+ = slower NMOS]", fontsize=11)
ax.set_ylabel("PU_shift (mV)  [+ = slower PMOS]", fontsize=11)
ax.set_title("(a) Vmin surface + 0.6V contour (SKY130-calibrated)", fontsize=12)
ax.legend(fontsize=8, loc="upper left")
ax.set_xlim(CN_MIN, CN_MAX); ax.set_ylim(PU_MIN, PU_MAX)
ax.grid(True, alpha=0.15); ax.axhline(0, color="gray", lw=0.5); ax.axvline(0, color="gray", lw=0.5)

# (b) Error map
ax = axes[1]
vmin_err = vmin_pred - true_analytic
valid = ~np.isnan(vmin_err)
vmax = max(abs(vmin_err[valid].min()), abs(vmin_err[valid].max()))
vmin_err[~valid] = 0.0
cf2 = ax.contourf(CN, PU, vmin_err, levels=np.linspace(-vmax, vmax, 21),
                  cmap="bwr", alpha=0.85)
fig.colorbar(cf2, ax=ax, label="Vmin error (V)", pad=0.02)
if len(true_cn) > 0:
    ax.plot(true_cn, true_pu, "k--", lw=1.5, alpha=0.6, label="True Vmin=0.6V")
if len(pred_cn) > 0:
    ax.plot(pred_cn, pred_pu, "g-", lw=1.5, alpha=0.8, label="GP Vmin=0.6V")
ax.set_xlabel("common_N_shift (mV)", fontsize=11)
ax.set_ylabel("PU_shift (mV)", fontsize=11)
ax.set_title(f"(b) GP error: pred - true  |v|max={vmax:.3f}V", fontsize=12)
ax.legend(fontsize=8, loc="upper left")
ax.set_xlim(CN_MIN, CN_MAX); ax.set_ylim(PU_MIN, PU_MAX)
ax.grid(True, alpha=0.15); ax.axhline(0, color="gray", lw=0.5); ax.axvline(0, color="gray", lw=0.5)

# Sidebar
fig.text(0.01, 0.02,
    f"SKY130 PDK: NMOS Avt={AVT_NMOS*1000:.0f} mV.um, PMOS Avt={AVT_PMOS*1000:.0f} mV.um\n"
    f"SRAM cell: PD={W_PD}/{L_MIN}  PG={W_PG}/{L_MIN}  PU={W_PU}/{L_MIN}  (W/L um)\n"
    f"Per-device sigma: PD={SIGMA_VTH_PD:.1f}  PG={SIGMA_VTH_PG:.1f}  PU={SIGMA_VTH_PU:.1f} mV\n"
    f"Model: |C_MU/B_MU|={abs(C_MU/B_MU):.2f}  SIGMA0={SIGMA0}  SIGMA_VOP_SLOPE={SIGMA_VOP_SLOPE}\n"
    f"GP train={len(X_tr)} test={len(X_te)}  mu RMSE={mu_rmse:.5f}  sigma RMSE={sigma_rmse:.5f}",
    fontsize=7, color="gray")

out = Path(__file__).resolve().parent / "sky130_contour.png"
fig.savefig(str(out), dpi=150, bbox_inches="tight")
print(f"  Saved: {out}")
plt.close(fig)
print("\n=== Done ===")
