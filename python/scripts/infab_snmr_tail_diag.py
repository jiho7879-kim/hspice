"""
IN-FAB SNMR TAIL DIAGNOSTIC  (TAILDIAG v1)
==========================================
Runs INSIDE the fab on raw Monte-Carlo SNMR samples. Nothing leaves the fab
except the short text block this script prints -- you can simply read that
block out / retype it.

WHY THIS EXISTS
---------------
Our Vmin flow reports only mean & std of the SNMR minimum, then extrapolates a
Gaussian to Z_t = 6.50. But SNMR is the MIN of the two butterfly lobes, and the
minimum of two Gaussians is NOT Gaussian -- its left tail is fatter. Fitting a
Gaussian to it and extrapolating to 6.5 sigma is therefore OPTIMISTIC.

How much? On our data dz/dVop ~ 13.2 /V in the spec band, so a 0.7 sigma
optimism = ~53 mV of Vmin -- larger than the entire T0(0.625V) -> EOL(0.675V)
margin budget of 50 mV. This script measures whether that optimism is real.

We cannot observe 6.5 sigma directly (that needs ~1e10 samples). Instead we
measure the SHAPE of the distribution in the range we CAN see (down to about
-3.5 to -4 sigma) and check which model it matches:
    H0  : plain Gaussian            -> no correction needed
    H1  : min of two Gaussians      -> correction needed; size depends on rho
Both models make different, testable predictions already at -2 to -3 sigma.

DEPENDENCIES
------------
numpy only (matplotlib optional -- if missing, the plot is skipped and the
numeric block is still printed).

HOW TO USE
----------
1. Re-simulate the conditions listed in tail_diag_conditions.csv with a LARGE
   MC count (see that file / the accompanying instructions). n_mc >= 50,000 is
   strongly preferred; 100,000 is ideal. 5,000 is NOT enough to see the tail.
2. Dump the raw per-sample SNMR values (one number per MC sample) to a file.
3. Set INPUT below (or pass the path as argv[1]) and run:
       python infab_snmr_tail_diag.py <rawfile> [deck_no] [vop]
4. Read out the "=== TAILDIAG v1 ... ===" block that gets printed.

INPUT FORMAT
------------
Any of:
  * one numeric value per line (.txt/.dat/.csv)
  * a CSV with a header -- set COLUMN to the SNMR column name
Non-numeric lines are skipped automatically. Units may be V or mV; the script
auto-detects and reports what it assumed (shape statistics are unit-free).
"""

import math
import sys

import numpy as np

# ---------------------------------------------------------------- settings --
INPUT = "snmr_raw.txt"     # path to the raw per-sample SNMR dump
COLUMN = None              # set to a column name if INPUT is a CSV with header
DECK_NO = "?"              # e.g. 1832   (for labelling only)
VOP = "?"                  # e.g. 0.70   (for labelling only)
Z_TARGET = 6.50            # our array Vmin z target
MAKE_PLOT = True           # write taildiag_<deck>_<vop>.png if matplotlib works
N_REF = 4_000_000          # reference-model sample size (internal, ~30 MB)


# ------------------------------------------------------------------ helpers --
def _phi(x):
    """Standard normal CDF (numpy-only, no scipy)."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _phi_inv(p):
    """Standard normal quantile -- Acklam's rational approximation."""
    if p <= 0.0 or p >= 1.0:
        return float("nan")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def load_samples(path, column=None):
    """Read raw SNMR samples; tolerant of headers, blanks and junk lines."""
    vals = []
    with open(path, "r", errors="ignore") as fh:
        lines = fh.read().splitlines()
    if column is not None:
        header = [h.strip().strip('"').lower() for h in
                  lines[0].replace("\t", ",").split(",")]
        try:
            idx = header.index(column.strip().lower())
        except ValueError:
            raise SystemExit(f"column {column!r} not found in header: {header}")
        body = lines[1:]
    else:
        idx = None
        body = lines
    for ln in body:
        parts = ln.replace("\t", ",").split(",") if ("," in ln or "\t" in ln) else [ln]
        tok = parts[idx] if (idx is not None and idx < len(parts)) else parts[0]
        try:
            vals.append(float(tok.strip().strip('"')))
        except (ValueError, AttributeError):
            continue
    x = np.asarray(vals, dtype=np.float64)
    return x[np.isfinite(x)]


def min_of_two_reference(rho, n, rng):
    """Standardised min(L,R) for two correlated standard normals."""
    z1 = rng.standard_normal(n)
    z2 = rho * z1 + math.sqrt(max(0.0, 1.0 - rho * rho)) * rng.standard_normal(n)
    m = np.minimum(z1, z2)
    return (m - m.mean()) / m.std(ddof=0)


def std_quantiles(x, ps):
    """Standardised empirical quantiles: (x_p - mean)/std."""
    mu, sd = x.mean(), x.std(ddof=0)
    return [(np.quantile(x, p) - mu) / sd for p in ps]


def bias_at_target(rho, z_target, rng, n=2_000_000):
    """
    If the truth is min(L,R) with correlation rho, and our flow reports
    z_naive = mean/std of that minimum = z_target, what is the TRUE z?
    Returns (z_true, bias = z_target - z_true).
    """
    z1 = rng.standard_normal(n)
    z2 = rho * z1 + math.sqrt(max(0.0, 1.0 - rho * rho)) * rng.standard_normal(n)
    m = np.minimum(z1, z2)
    e, s = m.mean(), m.std(ddof=0)
    # lobe z-score that makes the reported (min) z equal z_target
    z_lobe = z_target * s - e
    # exact union failure probability: P(L<0 or R<0) with both at z_lobe
    p_single = _phi(-z_lobe)
    # P(both fail) via bivariate normal, small; bound it with the rho-dependent
    # Slepian-style approximation (negligible at 6+ sigma unless rho ~ 1)
    p_both = 0.0
    if rho > 0.0:
        p_both = min(p_single, p_single ** (2.0 / (1.0 + rho)))
    p_fail = 2.0 * p_single - p_both
    p_fail = min(max(p_fail, 1e-300), 1.0 - 1e-16)
    z_true = -_phi_inv(p_fail)
    return z_true, z_target - z_true


# --------------------------------------------------------------------- main --
def main():
    path = sys.argv[1] if len(sys.argv) > 1 else INPUT
    deck = sys.argv[2] if len(sys.argv) > 2 else DECK_NO
    vop = sys.argv[3] if len(sys.argv) > 3 else VOP

    x = load_samples(path, COLUMN)
    n = len(x)
    if n < 1000:
        raise SystemExit(f"only {n} usable samples in {path!r} -- need >= 1000 "
                         "(and >= 50000 to resolve the tail).")

    mu, sd = float(x.mean()), float(x.std(ddof=0))
    unit = "mV" if abs(mu) > 1.0 else "V"

    xs = (x - mu) / sd
    skew = float((xs ** 3).mean())
    exkurt = float((xs ** 4).mean() - 3.0)

    # quantile ladder -- only where we have enough samples to be meaningful
    ladder = [(0.5, "p50"), (0.1587, "p15.9"), (0.0228, "p2.28"),
              (0.00135, "p0.135"), (0.0002, "p0.02")]
    ps, names, emp, gau = [], [], [], []
    for p, nm in ladder:
        if p * n >= 10:                      # need >=10 samples below the point
            ps.append(p); names.append(nm)
            emp.append(float((np.quantile(x, p) - mu) / sd))
            gau.append(_phi_inv(p))
    obs_min = float((x.min() - mu) / sd)

    # Statistical weight per ladder point. Deep quantiles are estimated from
    # very few samples, so an unweighted fit lets their sampling noise dominate
    # and can "detect" structure in data that is actually Gaussian. Normalise
    # each deviation by the quantile's standard error:
    #     SE(x_p) ~ sqrt(p(1-p)/n) / density(x_p)      [in sigma units]
    se = []
    for p in ps:
        zp = _phi_inv(p)
        dens = math.exp(-zp * zp / 2.0) / math.sqrt(2 * math.pi)
        se.append(math.sqrt(p * (1 - p) / n) / max(dens, 1e-12))

    rng = np.random.default_rng(12345)
    # candidate models
    models = [("GAUSS", None)] + [(f"MIN2(rho={r:+.2f})", r)
                                  for r in (-0.5, -0.25, 0.0, 0.25, 0.5, 0.75)]
    fits = []
    for nm, r in models:
        if r is None:
            pred = [_phi_inv(p) for p in ps]
            ref_skew = 0.0
        else:
            ref = min_of_two_reference(r, N_REF, rng)
            pred = [float(np.quantile(ref, p)) for p in ps]
            ref_skew = float((ref ** 3).mean())
        # chi-square-like badness: sum of squared SE-normalised deviations
        chi2 = sum(((a - b) / s) ** 2 for a, b, s in zip(emp, pred, se))
        fits.append((nm, r, chi2, pred, ref_skew))
    fits.sort(key=lambda t: t[2])
    best_nm, best_rho, best_chi2, _, best_skew = fits[0]
    gauss_chi2 = next(f[2] for f in fits if f[1] is None)

    # Is the plain-Gaussian hypothesis defensible? chi2 ~ dof when it fits.
    dof = len(ps)
    gauss_ok = gauss_chi2 < 3.0 * dof          # ~3x dof: generous, avoids
    #                                            crying wolf on sampling noise
    if best_rho is None or gauss_ok:
        z_true, bias = Z_TARGET, 0.0
        verdict = "GAUSSIAN-CONSISTENT -> no correction needed"
        if best_rho is not None:
            best_nm = f"GAUSS (chi2={gauss_chi2:.1f} ~ dof={dof}; {best_nm} not required)"
    else:
        z_true, bias = bias_at_target(best_rho, Z_TARGET, rng)
        verdict = f"NON-GAUSSIAN -> Vmin optimistic; correction {bias:+.2f} sigma"

    # ------------------------------------------------------- compact report --
    L = []
    L.append(f"=== TAILDIAG v1 | deck {deck} | Vop {vop} | n={n} ===")
    L.append(f"unit={unit}  mean={mu:.4f}  std={sd:.4f}  z_naive={mu/sd:.4f}")
    L.append(f"skew={skew:+.4f}(ref{best_skew:+.4f})  exkurt={exkurt:+.4f}")
    L.append("qz_emp : " + "  ".join(f"{nm}={v:+.3f}" for nm, v in zip(names, emp)))
    L.append("qz_gaus: " + "  ".join(f"{nm}={v:+.3f}" for nm, v in zip(names, gau)))
    L.append("qz_se  : " + "  ".join(f"{nm}={v:.3f}" for nm, v in zip(names, se)))
    L.append(f"obs_min={obs_min:+.3f}")
    L.append("chi2   : " + "  ".join(f"{nm}={c:.1f}" for nm, _, c, _, _ in fits[:4])
             + f"   dof={dof}")
    L.append(f"best={best_nm}")
    L.append(f"z_true@{Z_TARGET}={z_true:.3f}  zbias={bias:+.3f}  -> {verdict}")
    L.append("=== END TAILDIAG ===")
    report = "\n".join(L)
    print()
    print(report)
    print()
    print("  ^^ copy the block above (that is all that needs to leave the fab)")

    try:
        with open(f"taildiag_{deck}_{vop}.txt", "w") as fh:
            fh.write(report + "\n")
    except OSError:
        pass

    # -------------------------------------------------------------- plot ----
    if MAKE_PLOT:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("  (matplotlib not available -- plot skipped, numbers above "
                  "are sufficient)")
            return
        ref = (min_of_two_reference(best_rho, 1_000_000, rng)
               if best_rho is not None else rng.standard_normal(1_000_000))
        fig, ax = plt.subplots(1, 2, figsize=(13, 5))
        lo, hi = xs.min(), xs.max()
        bins = np.linspace(lo, hi, 120)
        ax[0].hist(xs, bins=bins, density=True, alpha=0.55,
                   label=f"measured (n={n})", color="#3477b5")
        g = np.exp(-bins ** 2 / 2) / math.sqrt(2 * math.pi)
        ax[0].plot(bins, g, "k--", lw=1.8, label="Gaussian")
        ax[0].hist(ref, bins=bins, density=True, histtype="step", lw=1.8,
                   color="#d1495b", label=f"best fit: {best_nm}")
        ax[0].set_yscale("log")
        ax[0].set_xlabel("standardised SNMR  (x - mean)/std")
        ax[0].set_ylabel("density (log)")
        ax[0].set_title(f"(a) distribution shape - deck {deck}, Vop {vop}")
        ax[0].legend(fontsize=8)
        ax[0].grid(alpha=0.2)

        # left-tail Q-Q: empirical vs Gaussian, zoomed on the low tail
        qs = np.linspace(1.0 / n, 0.05, 400)
        ax[1].plot([_phi_inv(q) for q in qs],
                   [(np.quantile(x, q) - mu) / sd for q in qs],
                   lw=2, color="#3477b5", label="measured")
        ax[1].plot([_phi_inv(q) for q in qs],
                   [float(np.quantile(ref, q)) for q in qs],
                   lw=1.8, color="#d1495b", label=f"{best_nm}")
        linlo = _phi_inv(1.0 / n)
        ax[1].plot([linlo, 0], [linlo, 0], "k--", lw=1.5, label="Gaussian")
        ax[1].set_xlabel("Gaussian quantile (sigma)")
        ax[1].set_ylabel("observed quantile (sigma)")
        ax[1].set_title("(b) LEFT TAIL Q-Q  (below the dashed line = fatter tail)")
        ax[1].legend(fontsize=8)
        ax[1].grid(alpha=0.2)
        fig.tight_layout()
        out = f"taildiag_{deck}_{vop}.png"
        fig.savefig(out, dpi=140)
        print(f"  plot saved: {out}")


if __name__ == "__main__":
    main()
