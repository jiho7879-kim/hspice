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
) -> str:
    """Replace Vth skew parameters with sampled shift values.

    Regex target: .param VTMSKEW_<device><idx> = '(<sys>) + (<rnd>)'
    Mapping (shift convention: positive = slower):
      - PU (PMOS pass-gate pull-up)  → pu_shift
      - PG (NMOS pass-gate)          → common_n_shift
      - PD (NMOS pull-down)          → common_n_shift

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
        # NMOS (PG, PD)
        elif param_name.startswith("VTMSKEW_PG") or param_name.startswith("VTMSKEW_PD"):
            new_val = f"{common_n_shift:.3f}"
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
) -> str:
    """Render template with parameter values.

    When vwl is provided, also replaces {{ VWL }}.
    When temp is provided, replaces {{ TEMP }} (otherwise uses TEMP_C default).
    """
    deck = _render_vth_skew(template, common_n_shift, pu_shift)
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
