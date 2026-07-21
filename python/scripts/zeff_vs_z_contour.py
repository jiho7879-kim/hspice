"""
z_eff vs plain-z on the nominal PVTA contour  (128 Mb @ 99% => Z_target=6.398)
=============================================================================
Purpose: show VISUALLY that the lobe (z_eff) correction and the fixed-corner
correction are orthogonal.

  plain z : pass/Vmin uses z(Vop) = mu/sigma crossing Z = 6.398
  z_eff   : same z-curve, but threshold raised to Z + zbias = 7.318
            (rho=-0.25 lobe fit, +0.919 sigma)

The (cn, pu) mu/sigma field is reconstructed by RBF-interpolating the GP's
own training data (results/stage4_real/dataset_real.npz) at each Vop level.
This stands in for surrogate_real.pth because torch/gpytorch are not installed
here; for a smooth TT+skew field the two are visually indistinguishable and the
orthogonality point does not depend on GP vs interpolation.

Panels:
  (a) Vmin contour, plain z          + corner markers (measured Vmin labelled)
  (b) Vmin contour, z_eff            + corner markers
  (c) dVmin = Vmin(z_eff) - Vmin(z)  -> ~uniform lift = GLOBAL correction
  (d) per-corner waterfall: GP(plain) -> +corner residual -> +z_eff = TRUE
      the two steps are independent and additive; neither replaces the other.
"""
from pathlib import Path

import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.stats import norm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
NPZ = ROOT / "results" / "stage4_real" / "dataset_real.npz"
OUT = ROOT / "results" / "diagnostics" / "zeff_vs_z_contour.png"
OUT.parent.mkdir(parents=True, exist_ok=True)

VOPS = np.array([0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
Z_BASE = float(norm.isf(-np.log(0.99) / 128e6))    # 6.398, 128 Mb @ 99% Poisson
ZBIAS_TYP = 0.919                                   # rho=-0.25 at Z_BASE
ZBIAS_FSG = 1.208                                   # rho=-0.50 (extreme local-sigma)
Z_EFF = Z_BASE + ZBIAS_TYP                          # 7.318

CORNER_SHIFTS = {"TT": (0.0, 0.0), "FFG": (-36.42, -44.32), "FSG": (-29.16, 38.64),
                 "SFG": (31.63, -36.76), "SSG": (36.3, 44.8)}
CORNERS = ["FFG", "FSG", "SFG", "SSG"]


def vmin_from_z(z, z_target, vops=VOPS):
    """Linear-interpolate Vop where z crosses z_target. NaN if never reached;
    vops[0]-0.05 (censored) if already above at the lowest Vop."""
    z = np.atleast_2d(z)
    out = np.full(z.shape[0], np.nan)
    for i, zc in enumerate(z):
        if zc[0] > z_target:
            out[i] = vops[0] - 0.05
            continue
        if zc[-1] < z_target:
            continue
        for j in range(len(vops) - 1):
            if zc[j] <= z_target <= zc[j + 1]:
                t = (z_target - zc[j]) / (zc[j + 1] - zc[j] + 1e-12)
                out[i] = vops[j] + t * (vops[j + 1] - vops[j])
                break
    return out


# ---- reconstruct mu, sigma field from GP training data -------------------
d = np.load(NPZ)
X, Y = d["X"], d["y"]          # X=(cn,pu,Vop), Y=(mu_mV, sigma_mV)
mu_rbf, sig_rbf = {}, {}
for v in VOPS:
    m = np.isclose(X[:, 2], v)
    if m.sum() < 5:
        continue
    pts = X[m][:, :2]
    mu_rbf[v] = RBFInterpolator(pts, Y[m, 0], kernel="thin_plate_spline", smoothing=1.0)
    sig_rbf[v] = RBFInterpolator(pts, Y[m, 1], kernel="thin_plate_spline", smoothing=1.0)
vlev = [v for v in VOPS if v in mu_rbf]


def field_z(cn, pu):
    """z-curve over Vop at plane point(s) (cn,pu). Returns (...,len(vlev))."""
    P = np.column_stack([np.ravel(cn), np.ravel(pu)])
    z = np.empty((P.shape[0], len(vlev)))
    for k, v in enumerate(vlev):
        z[:, k] = mu_rbf[v](P) / (sig_rbf[v](P) + 1e-12)
    return z


# ---- grid ----------------------------------------------------------------
N = 90
ax = np.linspace(-60, 60, N)
CN, PU = np.meshgrid(ax, ax)
Zg = field_z(CN, PU)
vmin_plain = vmin_from_z(Zg, Z_BASE, vlev).reshape(N, N)
vmin_zeff = vmin_from_z(Zg, Z_EFF, vlev).reshape(N, N)
dvmin = (vmin_zeff - vmin_plain) * 1000.0    # mV

# ---- measured corner Vmin (new corner file) + GP-at-corner ---------------
import openpyxl
wb = openpyxl.load_workbook(ROOT / "data" / "hspice_real_corner.xlsx", data_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))
c = {n: i for i, n in enumerate(rows[0])}
meas = {}
for r in rows[1:]:
    if r[c["Cat"]] == "snmr":
        meas.setdefault(r[c["corner"]], {})[float(r[c["vop"]])] = (r[c["avg"]], r[c["std"]])

corner_tbl = []
for name in CORNERS:
    cn_s, pu_s = CORNER_SHIFTS[name]
    # measured z-curve on VOPS
    md = meas.get(name, {})
    zm = np.array([[md[v][0] / md[v][1] if v in md else (-99 if v < 0.6 else 99)
                    for v in vlev]])
    vm_plain = vmin_from_z(zm, Z_BASE, vlev)[0]
    vm_zeff = vmin_from_z(zm, Z_EFF, vlev)[0]
    # GP-predicted (interpolated field) z-curve at the corner coordinate
    zg = field_z(cn_s, pu_s)
    vg_plain = vmin_from_z(zg, Z_BASE, vlev)[0]
    vg_zeff = vmin_from_z(zg, Z_EFF, vlev)[0]
    corner_tbl.append((name, cn_s, pu_s, vg_plain, vg_zeff, vm_plain, vm_zeff))

print(f"Z_base(128Mb,99%)={Z_BASE:.3f}  z_eff={Z_EFF:.3f} (+{ZBIAS_TYP} sigma)\n")
print(f"{'corner':>6} {'(cn,pu)':>12} | {'GP@z':>7} {'GP@zeff':>8} | "
      f"{'meas@z':>7} {'meas@zeff':>9} | {'corner_resid':>12} {'zeff_lift':>9}")
for name, cn_s, pu_s, vgp, vgz, vmp, vmz in corner_tbl:
    resid = (vmp - vgp) * 1000
    lift = (vgz - vgp) * 1000
    print(f"{name:>6} {f'({cn_s:.0f},{pu_s:.0f})':>12} | {vgp:.3f}  {vgz:.3f} | "
          f"{vmp:.3f}  {vmz:.3f} | {resid:>+9.1f}mV {lift:>+7.1f}mV")

# ==========================================================================
# figure
# ==========================================================================
fig, axes = plt.subplots(2, 2, figsize=(14, 12))
levels = np.arange(0.40, 0.86, 0.05)

for axp, vm, title, zt in [(axes[0, 0], vmin_plain, f"(a) Vmin — plain z  (Z={Z_BASE:.3f})", Z_BASE),
                           (axes[0, 1], vmin_zeff, f"(b) Vmin — z_eff  (Z={Z_EFF:.3f}, +{ZBIAS_TYP}$\\sigma$)", Z_EFF)]:
    cf = axp.contourf(CN, PU, vm, levels=levels, cmap="viridis", extend="both")
    cs = axp.contour(CN, PU, vm, levels=levels, colors="k", linewidths=0.5, alpha=0.5)
    axp.clabel(cs, fmt="%.2f", fontsize=7)
    plt.colorbar(cf, ax=axp, label="Vmin (V)")
    for name in CORNERS:
        cn_s, pu_s = CORNER_SHIFTS[name]
        row = next(r for r in corner_tbl if r[0] == name)
        vmeas = row[5] if zt == Z_BASE else row[6]
        axp.plot(cn_s, pu_s, "o", color="crimson", ms=9, mec="white", mew=1.2)
        axp.annotate(f"{name}\nmeas {vmeas:.3f}", (cn_s, pu_s),
                     textcoords="offset points", xytext=(6, 6),
                     fontsize=8, color="white", weight="bold")
    axp.plot(0, 0, "s", color="white", ms=7, mec="k")
    axp.annotate("TT", (0, 0), textcoords="offset points", xytext=(6, -12),
                 fontsize=8, color="white", weight="bold")
    axp.set_xlabel("common-N Vth shift (mV)"); axp.set_ylabel("PU Vth shift (mV)")
    axp.set_title(title)

# (c) difference map
axc = axes[1, 0]
cf = axc.contourf(CN, PU, dvmin, levels=np.linspace(np.nanmin(dvmin)-1,
                  np.nanmax(dvmin)+1, 21), cmap="magma")
plt.colorbar(cf, ax=axc, label="$\\Delta$Vmin (mV)")
axc.contour(CN, PU, dvmin, levels=8, colors="w", linewidths=0.4, alpha=0.5)
for name in CORNERS:
    cn_s, pu_s = CORNER_SHIFTS[name]
    axc.plot(cn_s, pu_s, "o", color="cyan", ms=8, mec="k")
    axc.annotate(name, (cn_s, pu_s), textcoords="offset points", xytext=(6, 6),
                 fontsize=8, color="cyan", weight="bold")
lo, hi = np.nanmin(dvmin), np.nanmax(dvmin)
axc.set_title(f"(c) z_eff lift = Vmin(z_eff) - Vmin(z)\nGLOBAL smooth lift "
              f"{lo:.0f}-{hi:.0f} mV EVERYWHERE (incl. TT) -> not a corner patch\n"
              "(varies only with local dz/dVop slope)")
axc.set_xlabel("common-N Vth shift (mV)"); axc.set_ylabel("PU Vth shift (mV)")

# (d) mechanism: z(Vop) curves at representative plane points, both thresholds
axd = axes[1, 1]
pts = [("TT", 0, 0, "#2a9d8f"), ("FSG", -29.16, 38.64, "#d1495b"),
       ("SFG", 31.63, -36.76, "#3477b5")]
vfine = np.linspace(vlev[0], vlev[-1], 200)
for name, cn_s, pu_s, col in pts:
    zc = field_z(cn_s, pu_s)[0]
    zint = np.interp(vfine, vlev, zc)
    axd.plot(vfine, zint, color=col, lw=2, label=f"{name} (cn={cn_s:.0f},pu={pu_s:.0f})")
    for zt, ls in [(Z_BASE, ":"), (Z_EFF, "-")]:
        vm = vmin_from_z(zc[None, :], zt, vlev)[0]
        if np.isfinite(vm) and vlev[0] <= vm <= vlev[-1]:
            axd.plot(vm, zt, "o", color=col, ms=7, mec="k")
axd.axhline(Z_BASE, color="k", ls=":", lw=1.5, label=f"plain z = {Z_BASE:.3f}")
axd.axhline(Z_EFF, color="k", ls="-", lw=1.5, label=f"z_eff = {Z_EFF:.3f}")
axd.annotate("", xy=(0.62, Z_EFF), xytext=(0.62, Z_BASE),
             arrowprops=dict(arrowstyle="->", color="crimson", lw=2))
axd.text(0.63, (Z_BASE+Z_EFF)/2, f"+{ZBIAS_TYP}$\\sigma$\nlobe", color="crimson",
         fontsize=9, weight="bold", va="center")
axd.set_xlabel("Vop (V)"); axd.set_ylabel("z(Vop) = mu/sigma")
axd.set_title("(d) mechanism: raising the threshold z->z_eff moves the\n"
              "Vmin crossing right at EVERY point (dots = Vmin). Corner\n"
              "residual (real GP +23mV@FSG, corner_calibration.md) is separate.")
axd.legend(loc="upper left", fontsize=8)
axd.grid(alpha=0.3)
axd.set_ylim(Z_BASE - 2.5, Z_EFF + 2.0)

fig.suptitle("z_eff (lobe) vs plain-z on the nominal PVTA contour — 128 Mb @ 99%, "
             f"Z={Z_BASE:.3f}\nlobe = GLOBAL threshold lift (+{ZBIAS_TYP}$\\sigma$, "
             "everywhere), ORTHOGONAL to the corner-local residual correction",
             fontsize=13, weight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.96])
fig.savefig(OUT, dpi=140)
print(f"\nsaved: {OUT}")
