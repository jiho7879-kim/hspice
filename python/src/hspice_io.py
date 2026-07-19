"""
HSPICE I/O utilities: deck generation and .mt0 output parsing.

Deck generation:
    1. Render Mustache templates with PVTA parameter values
    2. Generate N_cond x N_Vop decks for farm submission

Output parsing:
    1. Parse .mt0 MC output files
    2. Run histogram QC
    3. Build dataset.npz from raw output
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from src.utils import (
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
    VOPS, N_VOP, VOP_COL,
    WLUD_COL, WLUD_FACTORS, N_WLUD,
    TEMP_C, TEMP_C_COLD,
    sample_common_n_pu,
    z_eff_from_lobes, effective_mu_sigma,
)
from src.data import build_dataset, save_intermediate

MC_RUNS = 10_000


# ============================================================================
# Deck generation
# ============================================================================

def _load_template(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _render_vth_skew(
    template: str,
    common_n_shift: float,
    pu_shift: float,
    skew_pgpd: float = 0.0,
) -> str:
    """Replace Vth skew parameters with sampled shift values.

    Regex target: .param VTMSKEW_<device><idx> = '(<sys>) + (<rnd>)'
    Mapping (shift convention: positive = slower):
      - PU (PMOS pass-gate pull-up)  → pu_shift
      - PG (NMOS pass-gate)          → common_n_shift + skew_pgpd
      - PD (NMOS pull-down)          → common_n_shift − skew_pgpd

    skew_pgpd is the PER-SIDE PG-PD Vth skew (mV): PG = cn + sk, PD = cn − sk
    (so |PG−PD| = 2·sk).  This matches the condition sheet's `sk` column and
    inhouse_deck_gen.condition_to_deck_params (VTMSKEW_PG=cn+sk, PD=cn−sk).
    Default 0.0 => PG = PD = common_n_shift (Stage A, unchanged).

    The second term (random component) stays 0 for deterministic
    analysis; set to MC_RUNS-dependent value for statistical decks.

    <<< TEMPLATE FORMAT — ADJUST REGEX IF YOUR .in FILE USES
        DIFFERENT DELIMITERS (e.g. single quotes, no quotes, etc.) >>>
    """
    import re

    def _replace_skew(match: re.Match) -> str:
        param_name = match.group(1)  # e.g. "VTMSKEW_PU1"
        skew_val = match.group(2)    # e.g. "0"
        # PMOS (PU)
        if param_name.startswith("VTMSKEW_PU"):
            new_val = f"{pu_shift:.3f}"
        # NMOS pass-gate (PG): common_N + skew
        elif param_name.startswith("VTMSKEW_PG"):
            new_val = f"{common_n_shift + skew_pgpd:.3f}"
        # NMOS pull-down (PD): common_N − skew
        elif param_name.startswith("VTMSKEW_PD"):
            new_val = f"{common_n_shift - skew_pgpd:.3f}"
        else:
            return match.group(0)  # unknown — leave untouched
        # Rebuild: .param VTMSKEW_PU1 = '(sys_shift) + (rnd_shift)'
        #   match.group(3) = first (0), group(4) = second (0)
        return f".param {param_name} = '({new_val}) + ({skew_val})'"

    deck = re.sub(
        r"\.param\s+(VTMSKEW_\w+)\s*=\s*'\(\s*([^)]+)\s*\)\s*\+\s*\(\s*([^)]+)\s*\)'",
        _replace_skew,
        template,
    )
    return deck


def render_deck(
    template: str,
    common_n_shift: float,
    pu_shift: float,
    vop: float,
    vwl: float | None = None,
    temp: float | None = None,
    output_prefix: str = "",
    skew_pgpd: float = 0.0,
) -> str:
    """Render template with parameter values.

    When vwl is provided, also replaces {{ VWL }}.
    When temp is provided, replaces {{ TEMP }} (otherwise uses TEMP_C default).
    skew_pgpd (mV, Stage B+): per-side PG-PD Vth skew -> PG = cn + sk,
    PD = cn − sk. Default 0 keeps PG = PD = common_n_shift (Stage A).
    """
    deck = _render_vth_skew(template, common_n_shift, pu_shift, skew_pgpd)
    deck = deck.replace("{{ COMMON_N_SHIFT }}", f"{common_n_shift:.3f}")
    deck = deck.replace("{{ PU_SHIFT }}", f"{pu_shift:.3f}")
    deck = deck.replace("{{ VOP }}", f"{vop:.4f}")
    deck = deck.replace("{{ TEMP }}", f"{temp:.1f}" if temp is not None else f"{TEMP_C:.1f}")
    deck = deck.replace("{{ OUTPUT_PREFIX }}", output_prefix)
    deck = deck.replace("{{ MC_RUNS }}", str(MC_RUNS))
    if vwl is not None:
        deck = deck.replace("{{ VWL }}", f"{vwl:.4f}")
    return deck


def generate_decks(
    template: str,
    n_cond: int = 200,
    out_dir: str | Path = "decks",
    seed: int = 42,
    stage: int = 1,
    submit_script: bool = True,
    vwl_levels: np.ndarray | None = None,
) -> None:
    """Generate all decks and a batch submit script.

    Stage 1: core 3D (cn, pu, Vop) — no Vwl.
    Stage 2+: 4D with Vwl grid per Vop level.

    Directory structure:
        out_dir/
            cond_000001.sp
            cond_000002.sp
            ...
            submit_all.bat
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conditions = sample_common_n_pu(n_cond, seed=seed)

    if stage >= 2:
        if vwl_levels is None:
            # Default: absolute Vwl from WLUD ratios * Vop_mean (for deck rendering)
            vwl_levels = VOPS.mean() * WLUD_FACTORS
        n_vwl = len(vwl_levels)
        total_jobs = n_cond * N_VOP * n_vwl
        print(f"Generating {total_jobs} decks "
              f"({n_cond} conditions x {N_VOP} Vop x {n_vwl} Vwl levels)...")
        job_id = 0
        for i, (cn, pu) in enumerate(conditions):
            for j, vop in enumerate(VOPS):
                for k, vwl in enumerate(vwl_levels):
                    job_id += 1
                    prefix = f"cond_{job_id:06d}"
                    deck_content = render_deck(
                        template, cn, pu, vop, vwl=vwl, output_prefix=prefix,
                    )
                    fname = f"{prefix}.sp"
                    (out_dir / fname).write_text(deck_content, encoding="utf-8")
    else:
        total_jobs = n_cond * N_VOP
        print(f"Generating {total_jobs} decks "
              f"({n_cond} conditions x {N_VOP} Vop levels)...")
        job_id = 0
        for i, (cn, pu) in enumerate(conditions):
            for j, vop in enumerate(VOPS):
                job_id += 1
                prefix = f"cond_{job_id:06d}"
                deck_content = render_deck(template, cn, pu, vop, output_prefix=prefix)
                fname = f"{prefix}.sp"
                (out_dir / fname).write_text(deck_content, encoding="utf-8")

    print(f"  -> {total_jobs} decks written to {out_dir.resolve()}")
    if submit_script:
        _write_submit_script(out_dir, total_jobs)


def _write_submit_script(out_dir: Path, total_jobs: int) -> None:
    """Write a batch submission script."""
    lines = [
        "@echo off",
        "REM HSPICE batch submission script",
        f"SET DECK_DIR={out_dir.resolve()}",
        "SET HSPICE_CMD=hspice64",
        "",
        f"echo Submitting {total_jobs} jobs...",
        "",
    ]
    for job_id in range(1, total_jobs + 1):
        lines.append(
            f"REM %HSPICE_CMD% -i {out_dir}\\cond_{job_id:06d}.sp "
            f"-o {out_dir}\\cond_{job_id:06d}"
        )

    lines.extend(["", "echo All jobs submitted."])
    (out_dir / "submit_all.bat").write_text("\r\n".join(lines))
    print(f"  -> submit script written to {out_dir / 'submit_all.bat'}")


def run_validation(out_dir: str | Path) -> None:
    """Run one TT condition at 6 Vop levels to validate the deck."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    template = _load_template(Path(__file__).resolve().parent.parent / "templates" / "sram_cell_pvta.sp")

    print("=" * 60)
    print("Validation run: 1 condition (common_N=0, PU=0) x 6 Vop")
    print("=" * 60)

    for j, vop in enumerate(VOPS):
        prefix = f"val_tt_vop_{j + 1:02d}"
        deck = render_deck(template, 0.0, 0.0, vop, TEMP_C, prefix)
        fname = out_dir / f"{prefix}.sp"
        fname.write_text(deck, encoding="utf-8")
        print(f"  Written: {fname} (Vop={vop:.1f}V)")

    print("\nValidation decks ready. Run manually:")
    print(f"  hspice64 -i {out_dir / 'val_tt_vop_01.sp'} -o {out_dir / 'val_tt_vop_01'}")


# ============================================================================
# Output parsing
# ============================================================================

def _is_comment_or_empty(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("$") or stripped.startswith("*")


def _is_numeric_line(tokens: list[str]) -> bool:
    if not tokens:
        return False
    try:
        for t in tokens:
            float(t)
        return True
    except ValueError:
        return False


def parse_mt0_file(filepath: str | Path) -> np.ndarray:
    """Parse one HSPICE .mt0 file and return SNMR array.

    Handles common HSPICE MC output formats:
      - Lines starting with '$' or '*' are skipped
      - Numeric data: tab/space-separated columns
      - SNMR column identified by header name or falls back to last column

    Returns:
        ndarray of shape (N,) with SNMR values.
    """
    with open(filepath, "r") as f:
        raw_lines = f.readlines()

    content_lines: list[str] = []
    for line in raw_lines:
        if _is_comment_or_empty(line):
            continue
        content_lines.append(line)

    if not content_lines:
        raise ValueError(f"Empty file after stripping comments: {filepath}")

    data_start = None
    for i in range(len(content_lines) - 1, -1, -1):
        tokens = content_lines[i].split()
        if _is_numeric_line(tokens):
            data_start = i
        else:
            break

    if data_start is None:
        raise ValueError(f"No numeric data found in: {filepath}")

    header_tokens: list[str] = []
    if data_start > 0:
        header_tokens = content_lines[data_start - 1].split()

    numeric_rows: list[list[float]] = []
    for i in range(data_start, len(content_lines)):
        tokens = content_lines[i].split()
        if _is_numeric_line(tokens):
            numeric_rows.append([float(t) for t in tokens])

    if not numeric_rows:
        raise ValueError(f"No parseable numeric rows in: {filepath}")

    arr = np.array(numeric_rows, dtype=np.float64)
    n_cols = arr.shape[1]

    if n_cols == 1:
        values = arr[:, 0]
    else:
        col_idx = None
        if header_tokens:
            for j, hdr in enumerate(header_tokens):
                hdr_clean = hdr.strip().lower()
                if "snmr" in hdr_clean or "snpmr" in hdr_clean or "snm" in hdr_clean:
                    col_idx = j
                    break
        if col_idx is not None:
            values = arr[:, col_idx]
        else:
            values = arr[:, -1]

    if len(values) == 0:
        raise ValueError(f"No SNMR values extracted from: {filepath}")

    return values


def histogram_qc(snmr_values: np.ndarray, label: str = "") -> dict:
    """Run QC checks on SNMR histogram.

    Returns dict with keys: mu, sigma, n_valid, outlier_frac, bimodal_flag.
    """
    mu = float(np.mean(snmr_values))
    sigma = float(np.std(snmr_values))
    n_valid = len(snmr_values)
    outlier_frac = float(np.mean(np.abs(snmr_values - mu) > 6 * sigma))

    mean_median_gap = abs(mu - float(np.median(snmr_values))) / (sigma + 1e-12)
    bimodal_flag = mean_median_gap > 0.3

    result = {
        "mu": mu,
        "sigma": sigma,
        "n_valid": n_valid,
        "outlier_frac": outlier_frac,
        "bimodal_flag": bimodal_flag,
    }

    if label:
        status = "[BIMODAL?]" if bimodal_flag else "[OK]"
        print(f"  [{label}] mu={mu:.5f} sigma={sigma:.5f} "
              f"outliers={outlier_frac:.4f} {status}")

    return result


# ============================================================================
# MC statistics: bootstrap SEM, lobe-resolved stats, per-condition QC
# ============================================================================

def bootstrap_sem(
    samples: np.ndarray,
    stat: str = "mean",
    n_boot: int = 500,
    seed: int = 0,
) -> float:
    """Bootstrap standard error of a statistic ('mean' or 'std').

    Preferred over the Gaussian closed forms (sigma/sqrt(N) for the mean,
    sigma/sqrt(2N) for the std) because the std SEM in particular is
    kurtosis-sensitive and MC SNM distributions are not exactly Gaussian
    (adversarial review C3).
    """
    x = np.asarray(samples, dtype=np.float64)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 2:
        return float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    resampled = x[idx]
    if stat == "mean":
        vals = resampled.mean(axis=1)
    elif stat == "std":
        vals = resampled.std(axis=1, ddof=1)
    else:
        raise ValueError(f"unknown stat: {stat}")
    return float(np.std(vals, ddof=1))


def condition_qc(samples: np.ndarray, snm_floor: float = 0.0) -> dict:
    """Per-condition MC QC on a single SNM sample vector.

    Returns mu, sigma (ddof=1), bootstrap SEMs, normality (Anderson-Darling
    statistic + 5% critical value), skewness, excess kurtosis, and the
    fraction of samples at/below the fail floor (which flags left-tail
    fail-mixing that may warrant treating this Vop as censored).
    """
    from scipy.stats import anderson, skew, kurtosis

    x = np.asarray(samples, dtype=np.float64)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 3:
        return {
            "mu": float("nan"), "sigma": float("nan"), "n": n,
            "sem_mu": float("nan"), "sem_sigma": float("nan"),
            "ad_stat": float("nan"), "ad_crit5": float("nan"),
            "normal_ok": False, "skew": float("nan"), "kurtosis": float("nan"),
            "frac_below_floor": float("nan"),
        }

    import warnings

    mu = float(np.mean(x))
    sigma = float(np.std(x, ddof=1))
    try:
        # Keep the table-based critical_values form (no `method` kwarg).
        # SciPy >=1.17 warns that a future default will return a p-value
        # instead; we pin the current behavior and silence that warning
        # until we migrate the QC report to p-values.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            ad = anderson(x, dist="norm")
        ad_stat = float(ad.statistic)
        # critical value at 5% significance (index 2 in scipy's list)
        ad_crit5 = float(ad.critical_values[2])
        normal_ok = ad_stat < ad_crit5
    except Exception:
        ad_stat = ad_crit5 = float("nan")
        normal_ok = False

    return {
        "mu": mu,
        "sigma": sigma,
        "n": n,
        "sem_mu": bootstrap_sem(x, "mean"),
        "sem_sigma": bootstrap_sem(x, "std"),
        "ad_stat": ad_stat,
        "ad_crit5": ad_crit5,
        "normal_ok": bool(normal_ok),
        "skew": float(skew(x)),
        "kurtosis": float(kurtosis(x)),  # excess (0 = Gaussian)
        "frac_below_floor": float(np.mean(x <= snm_floor)),
    }


def lobe_mc_summary(
    snm_l: np.ndarray,
    snm_r: np.ndarray,
    snm_floor: float = 0.0,
) -> dict:
    """Lobe-resolved MC statistics for one condition (adversarial review A1).

    Returns per-lobe (mu, sigma), their correlation rho_LR, the effective
    (mu, sigma) whose ratio equals the union-based Z_eff, and the SEMs of
    the effective mu/sigma (bootstrap over paired resamples so rho is
    preserved).  Use effective (mu, sigma) as the GP target instead of the
    optimistically-biased min-statistics.
    """
    L = np.asarray(snm_l, dtype=np.float64)
    R = np.asarray(snm_r, dtype=np.float64)
    mask = ~(np.isnan(L) | np.isnan(R))
    L, R = L[mask], R[mask]
    n = len(L)
    if n < 3:
        raise ValueError("need >= 3 paired samples for lobe summary")

    mu_l, sg_l = float(np.mean(L)), float(np.std(L, ddof=1))
    mu_r, sg_r = float(np.mean(R)), float(np.std(R, ddof=1))
    rho = float(np.corrcoef(L, R)[0, 1]) if (sg_l > 0 and sg_r > 0) else 0.0
    rho = float(np.clip(rho, -0.999, 0.999))

    mu_eff, sg_eff = effective_mu_sigma(mu_l, sg_l, mu_r, sg_r, rho, snm_floor)
    z_eff = float(z_eff_from_lobes(mu_l, sg_l, mu_r, sg_r, rho, snm_floor))

    # Paired bootstrap for SEM of the effective statistics (keeps rho)
    rng = np.random.default_rng(0)
    n_boot = 400
    idx = rng.integers(0, n, size=(n_boot, n))
    Lb, Rb = L[idx], R[idx]
    mul_b = Lb.mean(1); sgl_b = Lb.std(1, ddof=1)
    mur_b = Rb.mean(1); sgr_b = Rb.std(1, ddof=1)
    rho_b = np.array([
        np.clip(np.corrcoef(Lb[i], Rb[i])[0, 1], -0.999, 0.999)
        if (sgl_b[i] > 0 and sgr_b[i] > 0) else 0.0
        for i in range(n_boot)
    ])
    mu_eff_b, sg_eff_b = effective_mu_sigma(mul_b, sgl_b, mur_b, sgr_b, rho_b, snm_floor)

    return {
        "mu_L": mu_l, "sigma_L": sg_l,
        "mu_R": mu_r, "sigma_R": sg_r,
        "rho_LR": rho,
        "mu_eff": float(mu_eff), "sigma_eff": float(sg_eff),
        "z_eff": z_eff,
        "sem_mu_eff": float(np.std(mu_eff_b, ddof=1)),
        "sem_sigma_eff": float(np.std(sg_eff_b, ddof=1)),
        "n": n,
    }


def write_qc_report(
    qc_rows: list[dict],
    out_path: str | Path,
    title: str = "HSPICE MC QC report",
) -> None:
    """Write a markdown QC report from a list of per-condition QC dicts.

    Each row dict should carry identifying fields (e.g. job_id, cn, pu, Vop)
    plus the keys produced by condition_qc().  A summary table flags any
    non-normal, high-skew, or fail-mixed conditions.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = len(qc_rows)
    n_nonnormal = sum(1 for r in qc_rows if not r.get("normal_ok", True))
    n_failmix = sum(1 for r in qc_rows if r.get("frac_below_floor", 0.0) > 0.001)
    n_highskew = sum(1 for r in qc_rows if abs(r.get("skew", 0.0)) > 1.0)

    lines = [
        f"# {title}",
        "",
        f"- conditions: **{n}**",
        f"- non-normal (AD stat >= 5% crit): **{n_nonnormal}** "
        f"({100 * n_nonnormal / max(n, 1):.1f}%)",
        f"- fail-mixed (frac SNM<=floor > 0.1%): **{n_failmix}** "
        "(candidate for Vop censoring)",
        f"- high-skew (|skew| > 1): **{n_highskew}**",
        "",
        "| job | cn | pu | Vop | n | mu | sigma | sem_mu | sem_sig | "
        "AD/crit | skew | kurt | fail% | flags |",
        "|----:|---:|---:|----:|--:|----:|------:|-------:|--------:|"
        "--------:|-----:|-----:|------:|-------|",
    ]
    for r in qc_rows:
        flags = []
        if not r.get("normal_ok", True):
            flags.append("nonnormal")
        if r.get("frac_below_floor", 0.0) > 0.001:
            flags.append("failmix")
        if abs(r.get("skew", 0.0)) > 1.0:
            flags.append("skew")
        ad = r.get("ad_stat", float("nan"))
        crit = r.get("ad_crit5", float("nan"))
        lines.append(
            f"| {r.get('job_id', '')} | {r.get('cn', ''):.0f} | "
            f"{r.get('pu', ''):.0f} | {r.get('vop', float('nan')):.2f} | "
            f"{r.get('n', 0)} | {r.get('mu', float('nan')):.4f} | "
            f"{r.get('sigma', float('nan')):.5f} | "
            f"{r.get('sem_mu', float('nan')):.5f} | "
            f"{r.get('sem_sigma', float('nan')):.5f} | "
            f"{ad:.2f}/{crit:.2f} | {r.get('skew', float('nan')):.2f} | "
            f"{r.get('kurtosis', float('nan')):.2f} | "
            f"{100 * r.get('frac_below_floor', 0.0):.2f} | "
            f"{','.join(flags) if flags else 'ok'} |"
        )
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  QC report -> {out_path}")


def process_all(
    raw_dir: str | Path,
    out_file: str | Path,
    n_cond: int = 200,
    qc_threshold_bimodal: float = 0.05,
) -> None:
    """Parse all .mt0 files, run QC, and save dataset."""
    raw_dir = Path(raw_dir)
    if not raw_dir.exists():
        raise FileNotFoundError(f"raw_dir not found: {raw_dir}")

    X = build_dataset(n_cond=n_cond)
    y = np.zeros((len(X), 2), dtype=np.float64)

    n_bimodal = 0
    n_fail = 0

    for i in range(len(X)):
        job_id = i + 1
        fname = None
        for candidate in [
            f"cond_{job_id:06d}.mt0",
            f"cond_{job_id:06d}.txt",
            f"cond_{job_id:06d}/raw/mc_data.txt",
        ]:
            p = raw_dir / candidate
            if p.exists():
                fname = p
                break

        if fname is None:
            print(f"  [WARN] job #{job_id}: .mt0 not found, skipping")
            y[i] = np.nan
            n_fail += 1
            continue

        try:
            snmr_vals = parse_mt0_file(fname)
        except Exception as e:
            print(f"  [WARN] job #{job_id}: parse error: {e}")
            y[i] = np.nan
            n_fail += 1
            continue

        qc = histogram_qc(snmr_vals, label=f"job #{job_id}")
        y[i, 0] = qc["mu"]
        y[i, 1] = qc["sigma"]

        if qc["bimodal_flag"]:
            n_bimodal += 1

    total = len(X)
    print(f"\n{'=' * 60}")
    print(f"Processed: {total - n_fail}/{total}")
    print(f"Failed:    {n_fail}")
    print(f"Bimodal:   {n_bimodal} ({n_bimodal / max(total, 1) * 100:.1f}%)")
    print(f"{'=' * 60}\n")

    save_intermediate(out_file, X, y)
    print(f"Saved: {out_file}")


# ============================================================================
# CSV dataset parsing
# ============================================================================

def parse_csv_to_dataset(
    csv_path: str | Path,
) -> tuple[np.ndarray, np.ndarray]:
    """Parse a CSV with per-condition MC stats into (X, y) arrays.

    Expected CSV columns (flexible naming):
        X: common_N_shift (mV), PU_shift (mV), Vop (V) [, Vwl (V), Temp (degC), ...]
        y: mu_SNMR (V), sigma_SNMR (V)

    Column name aliases accepted:
        - common_N_shift / common_n / cn / common_N
        - PU_shift / pu / PU
        - Vop / vop / vdd
        - Vwl / vwl / wl_voltage / wordline (optional)
        - Temp / temperature / temp_c (optional)
        - mu_SNMR / mu / median / mean / mu_snmr
        - sigma_SNMR / sigma / std / sigma_snmr

    Returns:
        X: (N, d) array [common_N_shift, PU_shift, Vop, Vwl?, Temp?, ...]
           shape is 3D (no Vwl/Temp), 4D (Vwl only), or 5D (Vwl + Temp)
        y: (N, 2) array [mu_SNMR, sigma_SNMR]
    """
    import pandas as pd

    df = pd.read_csv(csv_path)

    # Column name normalization
    col_map: dict[str, str] = {}
    for col in df.columns:
        cl = col.strip().lower()
        if cl in ("common_n_shift", "common_n", "cn", "common_n (mv)", "common n shift"):
            col_map["cn"] = col
        elif cl in ("pu_shift", "pu", "pu_shift (mv)", "pu shift"):
            col_map["pu"] = col
        elif cl in ("vop", "vdd", "vop (v)", "vdd (v)"):
            col_map["vop"] = col
        elif cl in ("vwl", "wl_voltage", "wordline", "vwl (v)", "wl voltage"):
            col_map["vwl"] = col
        elif cl in ("temp", "temperature", "temp_c", "temp (c)", "temperature (c)"):
            col_map["temp"] = col
        elif cl in ("mu_snmr", "mu", "median", "mean", "mu_snmr (v)"):
            col_map["mu"] = col
        elif cl in ("sigma_snmr", "sigma", "std", "sigma_snmr (v)"):
            col_map["sigma"] = col

    required = ["cn", "pu", "vop", "mu", "sigma"]
    missing = [r for r in required if r not in col_map]
    if missing:
        raise ValueError(
            f"CSV missing required columns {missing}. "
            f"Found columns: {list(df.columns)}. "
            f"Mapped: {col_map}"
        )

    # Build X columns — optional Vwl, Temp in column order
    x_cols = [col_map["cn"], col_map["pu"], col_map["vop"]]
    extra_col_names: list[str] = []
    for opt_key in ["vwl", "temp"]:
        if opt_key in col_map:
            extra_col_names.append(opt_key)
            x_cols.append(col_map[opt_key])

    X_raw = np.column_stack([
        df[c].values.astype(np.float64) for c in x_cols
    ])
    y = np.column_stack([
        df[col_map["mu"]].values.astype(np.float64),
        df[col_map["sigma"]].values.astype(np.float64),
    ])

    # Convert 4th dim: if Vwl column exists, change from absolute Vwl to WLUD ratio
    # X format: [cn, pu, Vop, Vwl?, Temp?]
    # After conversion: [cn, pu, Vop, WLUD_ratio?, Temp?]
    vwl_has_col = "vwl" in extra_col_names
    if vwl_has_col:
        # Vwl is at index VOP_COL + 1 before Temp
        vwl_col_idx = X_raw.shape[1] - len(extra_col_names) + extra_col_names.index("vwl")
        # Convert: WLUD = Vwl / Vop
        X_raw[:, vwl_col_idx] = X_raw[:, vwl_col_idx] / X_raw[:, VOP_COL]

    # Validate no NaN in key columns
    if np.isnan(X_raw).any():
        raise ValueError("NaN values found in X columns")
    if np.isnan(y).any():
        print("  [WARN] NaN values found in y columns — check MC convergence")

    n_dims = X_raw.shape[1]
    print(f"  CSV -> dataset: X {X_raw.shape}, y {y.shape} ({n_dims}D)")
    print(f"    cn range [{X_raw[:, 0].min():.1f}, {X_raw[:, 0].max():.1f}] mV")
    print(f"    pu range [{X_raw[:, 1].min():.1f}, {X_raw[:, 1].max():.1f}] mV")
    print(f"    Vop range [{X_raw[:, VOP_COL].min():.2f}, {X_raw[:, VOP_COL].max():.2f}] V")
    if vwl_has_col:
        vwl_idx = X_raw.shape[1] - len(extra_col_names) + extra_col_names.index("vwl")
        print(f"    WLUD range [{X_raw[:, vwl_idx].min():.4f}, {X_raw[:, vwl_idx].max():.4f}]")
    if X_raw.shape[1] > VOP_COL + 1:
        temp_col = X_raw.shape[1] - 1 if extra_col_names[-1] == "temp" else None
        if temp_col is not None:
            print(f"    Temp range [{X_raw[:, temp_col].min():.1f}, {X_raw[:, temp_col].max():.1f}] C")
    print(f"    mu range [{y[:, 0].min():.4f}, {y[:, 0].max():.4f}] V")
    print(f"    sigma range [{y[:, 1].min():.5f}, {y[:, 1].max():.5f}] V")

    return X_raw, y


# ============================================================================
# Hand-entry ingestion
#
# When the simulator results are transcribed by hand (no auto file export),
# the transcription burden dominates.  These helpers accept a structured
# CSV/sheet the user fills condition-by-condition and turn it into the
# training tensors + noise + QC in one call.  Two schemas:
#
#   simple : cn, pu, Vop [, Vwl] , mu_SNMR, sigma_SNMR [, n_mc]
#   lobe   : cn, pu, Vop [, Vwl] , mu_L, sigma_L, mu_R, sigma_R, rho_LR [, n_mc]
#
# The lobe schema removes the min-of-lobes optimism (adversarial review A1)
# at 2.5x the transcription cost.  Recommended split: transcribe the whole
# sweep in the simple schema, and a handful of worst-case corners in the
# lobe schema, to measure the A1 bias without paying it everywhere.
# ============================================================================

_ALIASES = {
    # --- conditions (X) ---
    "cn": ("common_n_shift", "common_n", "cn", "common n shift",
          "vtmskew_n", "vtmskew_pg"),
    "sk": ("sk", "skew", "skew_pgpd", "pg_pd_skew", "pgpd_skew",
          "pg-pd skew", "skew_pg_pd"),
    "pu": ("pu_shift", "pu", "pu shift", "vtmskew_pu", "vtmskew_p"),
    "vop": ("vop", "vdd"),
    "vwl": ("vwl", "wl_voltage", "wordline", "wl voltage"),
    "temp": ("temp", "temperature", "temp_c"),
    "sig_g": ("sigg_mult", "sig_g", "sigmag", "vtsg", "sigg", "global_sigma"),
    "sig_l": ("sigl_mult", "sig_l", "sigmal", "vtsl", "sigl", "local_sigma"),
    "mob": ("mob_mult", "mob", "mobility", "mom", "mom_mult"),
    # --- SNMR results (y) ---
    "mu": ("mu_snmr", "mu", "mean", "avg", "snmr_avg"),
    "sigma": ("sigma_snmr", "sigma", "std", "stdev", "snmr_std"),
    "median": ("median", "snmr_med", "med"),  # QC only, never trained on
    # --- SNMR lobe-resolved (optional, worst corners only) ---
    "mu_l": ("mu_l", "mu_snmr_l", "mul", "mu_left"),
    "sigma_l": ("sigma_l", "sigma_snmr_l", "sigl", "sigma_left"),
    "mu_r": ("mu_r", "mu_snmr_r", "mur", "mu_right"),
    "sigma_r": ("sigma_r", "sigma_snmr_r", "sigr", "sigma_right"),
    "rho": ("rho_lr", "rho", "corr", "correlation"),
    # --- Vtrip / write-margin results (optional) ---
    "vtrip_mu": ("vtrip_min_mu", "vtrip_mu", "vtripmin_mu", "wrm_mu", "bwrm_mu"),
    "vtrip_sigma": ("vtrip_min_sigma", "vtrip_sigma", "wrm_sigma", "bwrm_sigma"),
    # --- MC count (noise) ---
    "n_mc": ("n_mc", "nmc", "mc_runs", "n"),
}

# Extra conditions carried through for the future 8-D model (not yet in the
# core GP input; kept in the returned dict for record-keeping / Phase 4).
_EXTRA_CONDITION_KEYS = ("temp", "sig_g", "sig_l", "mob")


def _map_columns(df) -> dict[str, str]:
    col_map: dict[str, str] = {}
    for col in df.columns:
        cl = str(col).strip().lower().split("(")[0].strip()
        for key, names in _ALIASES.items():
            if cl in names:
                col_map[key] = col
                break
    return col_map


def parse_manual_csv(csv_path: str | Path) -> dict[str, np.ndarray]:
    """Parse a hand-entered CSV into training arrays + noise + lobe stats.

    See _parse_manual_df for the schema/unit contract. CSV values are
    assumed already in project units (V, mV as documented in the standard
    template) -- use parse_manual_xlsx for a sheet in raw MC units (mV).
    """
    import pandas as pd

    df = pd.read_csv(csv_path, comment="#")
    df = df.dropna(how="all")
    return _parse_manual_df(df, source=str(csv_path))


def parse_manual_xlsx(
    xlsx_path: str | Path,
    sheet_name: str | int = 0,
    mu_sigma_unit: str = "mV",
) -> dict:
    """Parse a hand-transcribed .xlsx sheet (e.g. in-house PrimeSim results
    copied out by hand) into the same training-array contract as
    parse_manual_csv.

    mu_sigma_unit: "mV" (default -- matches PrimeSim SNM/Vtrip magnitudes,
    ~10-200) converts mu/sigma to volts by /1000. "V" leaves them as-is.
    cn/pu/Vop are read as-is (cn, pu already mV; Vop already V) regardless.

    Runs transcription-error QC (see _median_digit_shift_qc,
    _vop_interpolation_outlier_qc) and prints (does not silently "fix")
    any suspected typos -- these are hand-entered numbers and only the
    user can confirm the correct value.
    """
    import pandas as pd

    df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
    df = df.dropna(how="all")
    df = df.dropna(axis=1, how="all")  # drop the blank trailing columns

    qc_flags = _manual_data_qc(df)

    result = _parse_manual_df(df, source=str(xlsx_path),
                              mu_sigma_scale=(1e-3 if mu_sigma_unit == "mV" else 1.0))
    result["qc_flags"] = qc_flags
    return result


def _parse_manual_df(df, source: str, mu_sigma_scale: float = 1.0) -> dict:
    """Shared body of parse_manual_csv / parse_manual_xlsx.

    Auto-detects the simple vs lobe schema.  Vwl (absolute) is converted to
    the WLUD ratio (Vwl/Vop).  When n_mc is present, per-point standard
    errors are derived (sem_mu = sigma/sqrt(N), sem_sigma = sigma/sqrt(2N))
    for the noise-aware GP.  mu_sigma_scale multiplies mu/sigma/vtrip_mu/
    vtrip_sigma only (e.g. 1e-3 for a sheet in mV); cn/pu/Vop are never
    rescaled (already in project units: mV, mV, V).

    Returns a dict with:
        X        : (N, d)  [cn, pu, Vop, WLUD?]
        y        : (N, 2)  [mu, sigma]  (effective, if lobe schema; volts)
        y_noise  : (N, 2) or None
        rho_LR   : (N,) or None   (lobe schema only; QC/diagnostics)
        schema   : "simple" | "lobe"
    """
    cm = _map_columns(df)

    base = ["cn", "pu", "vop"]
    missing_base = [b for b in base if b not in cm]
    if missing_base:
        raise ValueError(f"missing base columns {missing_base}; found {list(df.columns)}")

    lobe_keys = ["mu_l", "sigma_l", "mu_r", "sigma_r", "rho"]
    has_lobe = all(k in cm for k in lobe_keys)
    has_simple = ("mu" in cm and "sigma" in cm)
    if not (has_lobe or has_simple):
        raise ValueError(
            "need either simple (mu_SNMR, sigma_SNMR) or lobe "
            "(mu_L, sigma_L, mu_R, sigma_R, rho_LR) columns; "
            f"found {list(df.columns)}"
        )

    def col(key: str) -> np.ndarray:
        return df[cm[key]].to_numpy(dtype=np.float64)

    # X is device-first: [cn, (sk,) pu] then Vop, then optional WLUD.
    # sk (PG-PD skew) is a Stage-B+ DEVICE dim -> placed between cn and pu, so
    # Vop shifts to index 3 (n_device=3).  Without sk it's the 3D layout
    # (n_device=2, Vop at 2).  See src.utils device-first layout / VOP_COL.
    has_sk = "sk" in cm
    if has_sk:
        x_list = [col("cn"), col("sk"), col("pu"), col("vop")]
        x_names = ["cn", "sk", "pu", "vop"]
        vop_col = 3
    else:
        x_list = [col("cn"), col("pu"), col("vop")]
        x_names = ["cn", "pu", "vop"]
        vop_col = 2
    # optional WLUD from absolute Vwl. A blank Vwl cell means "no assist"
    # (Vwl = Vop, i.e. WLUD = 1.0) rather than a missing value.
    if "vwl" in cm:
        vwl_raw = col("vwl")
        vop_raw = col("vop")
        blank = np.isnan(vwl_raw)
        wlud = np.where(blank, 1.0, np.divide(
            vwl_raw, vop_raw, out=np.ones_like(vop_raw), where=~blank))
        x_list.append(wlud)
        x_names.append("wlud")
    X = np.column_stack(x_list)

    rho_out = None
    if has_lobe:
        mu, sigma = effective_mu_sigma(
            col("mu_l") * mu_sigma_scale, col("sigma_l") * mu_sigma_scale,
            col("mu_r") * mu_sigma_scale, col("sigma_r") * mu_sigma_scale,
            col("rho"),
        )
        rho_out = col("rho")
        schema = "lobe"
    else:
        mu, sigma = col("mu") * mu_sigma_scale, col("sigma") * mu_sigma_scale
        schema = "simple"
    y = np.column_stack([mu, sigma])

    y_noise = None
    if "n_mc" in cm:
        n_mc = np.clip(col("n_mc"), 2, None)
        sem_mu = sigma / np.sqrt(n_mc)
        sem_sigma = sigma / np.sqrt(2.0 * n_mc)
        y_noise = np.column_stack([np.maximum(sem_mu, 1e-9),
                                   np.maximum(sem_sigma, 1e-9)])

    # extra conditions carried through (Phase-4 dims; not in core GP X yet)
    extras = {k: col(k) for k in _EXTRA_CONDITION_KEYS if k in cm}

    # optional Vtrip / write-margin results
    y_vtrip = None
    if "vtrip_mu" in cm and "vtrip_sigma" in cm:
        y_vtrip = np.column_stack([col("vtrip_mu") * mu_sigma_scale,
                                   col("vtrip_sigma") * mu_sigma_scale])

    if np.isnan(X).any():
        raise ValueError("NaN in X columns")
    n_bad = int(np.isnan(y).any(axis=1).sum())
    if n_bad:
        print(f"  [WARN] {n_bad} rows with NaN in y — check those conditions")

    print(f"  {source} [{schema}] -> X {X.shape}, y {y.shape}"
          f"{', y_noise ' + str(y_noise.shape) if y_noise is not None else ''}"
          f"{', +' + ','.join(extras) if extras else ''}"
          f"{', y_vtrip ' + str(y_vtrip.shape) if y_vtrip is not None else ''}")
    if has_lobe:
        print(f"    rho_LR range [{rho_out.min():+.2f}, {rho_out.max():+.2f}]  "
              f"(A1: negative rho => larger min-stats bias corrected)")
    return {"X": X, "y": y, "y_noise": y_noise, "rho_LR": rho_out,
            "schema": schema, "extras": extras, "y_vtrip": y_vtrip,
            # layout so downstream knows the device/operating split (Stage B
            # has sk -> n_device=3, Vop at col 3). Pass n_device to AdditiveGP.
            "x_cols": x_names, "vop_col": vop_col, "n_device": vop_col}


# ---------------------------------------------------------------------------
# Transcription-error QC (hand-entered data only)
#
# Two failure modes seen in practice, both are digit/decimal-point slips
# during manual transcription -- NOT simulator errors:
#   (a) a "median" column off by 10x or 100x from mu (decimal point moved)
#   (b) a mu value that jumps off the trend formed by the SAME (cn,pu)
#       condition's other Vop rows (a single mis-keyed digit)
# Neither is auto-corrected: only the user who transcribed the sheet can
# confirm the true value. These just print/return actionable flags.
# ---------------------------------------------------------------------------

def _median_digit_shift_qc(df, cm: dict) -> list[dict]:
    """Flag rows where median/mu looks like a decimal-point slip (~10x/100x)."""
    if "mu" not in cm or "median" not in cm:
        return []
    mu = df[cm["mu"]].to_numpy(dtype=np.float64)
    med = df[cm["median"]].to_numpy(dtype=np.float64)
    valid = ~(np.isnan(mu) | np.isnan(med)) & (mu != 0)
    ratio = np.full(len(mu), np.nan)
    ratio[valid] = med[valid] / mu[valid]
    flags = []
    for i in np.where(valid)[0]:
        for k in (10.0, 100.0):
            if abs(ratio[i] - k) / k < 0.05:  # within 5% of an exact 10x/100x
                flags.append({
                    "row": int(i), "issue": "median_digit_shift",
                    "mu": float(mu[i]), "median": float(med[i]),
                    "ratio": float(ratio[i]), "suspected_factor": k,
                    "note": (f"median is ~{k:.0f}x mu -- likely a misplaced "
                            f"decimal point in the median column; mu/sigma "
                            f"(used for training) are unaffected"),
                })
                break
    return flags


def _vop_interpolation_outlier_qc(
    df, cm: dict, rel_threshold: float = 0.5,
) -> list[dict]:
    """Flag a mu value that deviates from the trend formed by the SAME
    (cn, pu) condition's other Vop rows (linear interpolation from the two
    nearest-Vop neighbours), by more than rel_threshold of the local scale.
    Needs >= 3 Vop rows for a condition to interpolate; skips otherwise.
    """
    for k in ("cn", "pu", "vop", "mu"):
        if k not in cm:
            return []
    cn = df[cm["cn"]].to_numpy(dtype=np.float64)
    pu = df[cm["pu"]].to_numpy(dtype=np.float64)
    vop = df[cm["vop"]].to_numpy(dtype=np.float64)
    mu = df[cm["mu"]].to_numpy(dtype=np.float64)
    # Stage B: sk is part of the condition identity, so the same (cn, pu) with
    # different skew must NOT be merged into one Vop trend. Include sk in the key.
    sk = df[cm["sk"]].to_numpy(dtype=np.float64) if "sk" in cm else None

    flags = []
    conditions: dict[tuple, list[int]] = {}
    for i in range(len(cn)):
        key = (cn[i], pu[i]) if sk is None else (cn[i], sk[i], pu[i])
        conditions.setdefault(key, []).append(i)

    for key, idxs in conditions.items():
        c, s, p = (key[0], None, key[1]) if sk is None else key
        if len(idxs) < 3:
            continue
        idxs = sorted(idxs, key=lambda i: vop[i])
        vops = vop[idxs]
        mus = mu[idxs]
        scale = max(float(np.median(np.abs(mus))), 1e-9)
        for j in range(1, len(idxs) - 1):
            v_lo, v_hi = vops[j - 1], vops[j + 1]
            m_lo, m_hi = mus[j - 1], mus[j + 1]
            if v_hi == v_lo:
                continue
            t = (vops[j] - v_lo) / (v_hi - v_lo)
            expected = m_lo + t * (m_hi - m_lo)
            dev = abs(mus[j] - expected)
            if dev / scale > rel_threshold:
                flags.append({
                    "row": int(idxs[j]), "issue": "vop_trend_outlier",
                    "cn": float(c), "pu": float(p),
                    **({"sk": float(s)} if s is not None else {}),
                    "vop": float(vops[j]),
                    "mu": float(mus[j]), "expected_from_neighbors": float(expected),
                    "neighbor_vops": [float(v_lo), float(v_hi)],
                    "neighbor_mus": [float(m_lo), float(m_hi)],
                    "note": (f"mu={mus[j]:.3g} deviates from the trend set by "
                            f"the same condition at Vop={v_lo:.2g}->{mus[j-1]:.3g} "
                            f"and Vop={v_hi:.2g}->{mus[j+1]:.3g} "
                            f"(expected ~{expected:.3g})"),
                })
    return flags


def _manual_data_qc(df) -> list[dict]:
    """Run all transcription-error QC checks and print a summary."""
    cm = _map_columns(df)
    flags = _median_digit_shift_qc(df, cm) + _vop_interpolation_outlier_qc(df, cm)
    if flags:
        print(f"  [QC] {len(flags)} suspected transcription error(s) "
              f"(flagged, NOT auto-corrected -- confirm against the source):")
        for f in flags:
            print(f"    row {f['row']:5d} [{f['issue']:20s}] {f['note']}")
    else:
        print("  [QC] no transcription-error patterns detected")
    return flags


# The one standard transcription form. Fill one row per (condition x Vop).
# Only sweep-varying columns need real values; blank optional columns take
# the nominal shown in the comment. Record RAW statistics only — z-score,
# Vmin, and censoring are computed downstream, so a change in those
# definitions never requires re-transcribing.
_STANDARD_HEADER_COMMENT = (
    "# SRAM Vmin training data — standard hand-entry form.\n"
    "# One row per (condition x Vop). '#' lines are ignored.\n"
    "#\n"
    "# CONDITIONS (from the deck; record what you actually swept):\n"
    "#   common_N_shift  mV   NMOS (PG=PD) Vth shift          [required]\n"
    "#   PU_shift        mV   PMOS Vth shift                  [required]\n"
    "#   Vop             V    supply voltage                  [required]\n"
    "#   Vwl             V    wordline (assist); blank => = Vop (no assist)\n"
    "#   temp            C    temperature;        blank => 125\n"
    "#   sigG_mult       -    global-sigma mult (VTSG); blank => 1\n"
    "#   sigL_mult       -    local-sigma  mult (VTSL); blank => 1\n"
    "#   mob_mult        -    mobility     mult (MOM);  blank => 1\n"
    "# RESULTS (raw MC statistics; NOT z-score or Vmin):\n"
    "#   mu_SNMR         V    SNMR mean (MC avg)              [required]\n"
    "#   sigma_SNMR      V    SNMR std  (MC std)              [required]\n"
    "#   n_mc            -    MC sample count (enables noise-aware GP)\n"
    "#   vtrip_min_mu    V    mean of per-sample min(L,R) write margin  [optional]\n"
    "#   vtrip_min_sigma V    its std                                   [optional]\n"
    "#\n"
)

_STANDARD_COLS = (
    "common_N_shift,PU_shift,Vop,Vwl,temp,sigG_mult,sigL_mult,mob_mult,"
    "mu_SNMR,sigma_SNMR,n_mc,vtrip_min_mu,vtrip_min_sigma"
)


def write_entry_templates(out_dir: str | Path) -> None:
    """Write the standard hand-entry template (+ a lobe-schema variant).

    `manual_entry_standard.csv` is the one form to fill: conditions from the
    deck + raw MC results. `manual_entry_lobe.csv` is the optional per-lobe
    variant for worst-case corners only (removes the min-of-lobes A1 bias at
    2.5x transcription cost).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    standard = (
        _STANDARD_HEADER_COMMENT
        + _STANDARD_COLS + "\n"
        + "-60,60,0.6,,,,,,0.0721,0.0203,5000,,\n"          # FSG corner, nominal PVTA
        + "0,0,0.6,0.54,125,1,1,1,0.1183,0.0198,5000,0.281,0.018\n"  # TT + assist + Vtrip
    )
    lobe = (
        "# LOBE variant — worst-case corners only (removes A1 min-of-lobes bias).\n"
        "# 2.5x transcription cost; use for a handful of corners, standard form elsewhere.\n"
        "common_N_shift,PU_shift,Vop,mu_L,sigma_L,mu_R,sigma_R,rho_LR,n_mc\n"
        "-60,60,0.6,0.0731,0.0205,0.0725,0.0201,-0.35,5000\n"
        "60,-60,0.6,0.0902,0.0210,0.0898,0.0208,-0.30,5000\n"
    )
    (out_dir / "manual_entry_standard.csv").write_text(standard, encoding="utf-8")
    (out_dir / "manual_entry_lobe.csv").write_text(lobe, encoding="utf-8")
    print(f"  templates -> {out_dir / 'manual_entry_standard.csv'}")
    print(f"             {out_dir / 'manual_entry_lobe.csv'}")


# ============================================================================
# CLI
# ============================================================================

def main_gen() -> None:
    """CLI entrypoint for deck generation."""
    parser = argparse.ArgumentParser(description="SRAM PVTA deck generator")
    parser.add_argument("--out_dir", default=str(Path.cwd() / "decks"),
                        help="Output directory for decks")
    parser.add_argument("--n_cond", type=int, default=200,
                        help="Number of (common_N, PU) conditions")
    parser.add_argument("--validation", action="store_true",
                        help="Generate validation decks instead of full set")
    args = parser.parse_args()

    template_path = Path(__file__).resolve().parent.parent / "templates" / "sram_cell_pvta.sp"
    template = _load_template(template_path)

    if args.validation:
        run_validation(args.out_dir)
    else:
        generate_decks(template, n_cond=args.n_cond, out_dir=args.out_dir)


def main_parse() -> None:
    """CLI entrypoint for .mt0 parsing."""
    parser = argparse.ArgumentParser(description="Parse HSPICE .mt0 -> dataset.npz")
    parser.add_argument("--raw_dir", default="../raw_mt0",
                        help="Directory with raw .mt0 files")
    parser.add_argument("--out_file", default="./data/dataset.npz",
                        help="Output .npz path")
    parser.add_argument("--n_cond", type=int, default=200)
    args = parser.parse_args()

    process_all(args.raw_dir, args.out_file, n_cond=args.n_cond)


if __name__ == "__main__":
    main_gen()
