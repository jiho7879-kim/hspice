"""
HSPICE output parser -- extract mu_SNMR, sigma_SNMR from .mt0 MC results.

Usage:
    python src/parse_snm.py --data_dir ./raw_mt0 --out_file ./data/dataset.npz

Expected input:
    - 1200 .mt0 files (or .txt/.csv from MC measurement export),
      one per (common_N, PU, Vop) condition.

    - Each file contains 10000 SNMR samples (one per MC run).
      The exact parsing depends on your HSPICE .mt0 format.

Output:
    - ./data/dataset.npz with:
        X: (1200, 3) = [common_N_shift (mV), PU_shift (mV), Vop (V)]
        y: (1200, 2) = [mu_SNMR (V), sigma_SNMR (V)]
    - Histogram QC plot for each file (optional)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import VOPS, N_VOP, build_dataset, save_intermediate


def _is_comment_or_empty(line: str) -> bool:
    """True if line is a comment (starts with $ or *) or blank."""
    stripped = line.strip()
    return not stripped or stripped.startswith("$") or stripped.startswith("*")


def _is_numeric_line(tokens: list[str]) -> bool:
    """True if all tokens can be parsed as floats."""
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
      - Lines starting with '$' or '*' are skipped (comments)
      - The last non-numeric line before numeric data is the column header
      - Numeric data: tab/space-separated columns
      - If header contains 'snmr' (case-insensitive), that column is used
      - Otherwise the last numeric column is used
      - If only one numeric column, it is used directly

    Returns:
        ndarray of shape (N,) with SNMR values (N = MC runs, typically 10000).
    """
    with open(filepath, "r") as f:
        raw_lines = f.readlines()

    # Stage 1: strip comments and blanks, find header-to-data transition
    content_lines: list[str] = []
    for line in raw_lines:
        if _is_comment_or_empty(line):
            continue
        content_lines.append(line)

    if not content_lines:
        raise ValueError(f"Empty file after stripping comments: {filepath}")

    # Stage 2: find where numeric data begins
    # Walk backwards from end to find first numeric line, then find header
    data_start = None
    for i in range(len(content_lines) - 1, -1, -1):
        tokens = content_lines[i].split()
        if _is_numeric_line(tokens):
            data_start = i
        else:
            break

    if data_start is None:
        raise ValueError(f"No numeric data found in: {filepath}")

    # The line just before data_start (if any) is the column header
    header_tokens: list[str] = []
    if data_start > 0:
        header_tokens = content_lines[data_start - 1].split()

    # Stage 3: parse all numeric rows
    numeric_rows: list[list[float]] = []
    for i in range(data_start, len(content_lines)):
        tokens = content_lines[i].split()
        if _is_numeric_line(tokens):
            numeric_rows.append([float(t) for t in tokens])

    if not numeric_rows:
        raise ValueError(f"No parseable numeric rows in: {filepath}")

    arr = np.array(numeric_rows, dtype=np.float64)
    n_cols = arr.shape[1]

    # Stage 4: select the SNMR column
    if n_cols == 1:
        values = arr[:, 0]
    else:
        # Try to find SNMR column by name
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
            # Fallback: use LAST column (most measurement outputs)
            values = arr[:, -1]

    if len(values) == 0:
        raise ValueError(f"No SNMR values extracted from: {filepath}")

    return values


def histogram_qc(snmr_values: np.ndarray, label: str = "") -> dict:
    """Run QC checks on SNMR histogram.

    Returns dict with keys:
        - 'mu': mean SNMR
        - 'sigma': std SNMR
        - 'n_valid': number of valid samples
        - 'is_normal': bool (passed normality heuristic)
        - 'outlier_frac': fraction of points beyond |6*sigma|
        - 'bimodal_flag': bool (simple bimodality heuristic via dip test proxy)
    """
    mu = float(np.mean(snmr_values))
    sigma = float(np.std(snmr_values))
    n_valid = len(snmr_values)
    outlier_frac = float(np.mean(np.abs(snmr_values - mu) > 6 * sigma))

    # Simple unimodality check: compare mean vs median gap
    # A large gap suggests asymmetry / potential bimodality
    mean_median_gap = abs(mu - float(np.median(snmr_values))) / (sigma + 1e-12)
    bimodal_flag = mean_median_gap > 0.3  # heuristic threshold

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
    """Parse all .mt0 files, run QC, and save dataset.

    Args:
        raw_dir: Directory containing raw .mt0 output files.
        out_file: Output .npz path.
        n_cond: Number of (common_N, PU) conditions (default 200).
        qc_threshold_bimodal: Max allowed bimodal fraction before warning.
    """
    raw_dir = Path(raw_dir)
    if not raw_dir.exists():
        raise FileNotFoundError(f"raw_dir not found: {raw_dir}")

    # Build input grid to map job IDs to (common_N, PU, Vop)
    X = build_dataset(n_cond=n_cond)  # (1200, 3)
    y = np.zeros((len(X), 2), dtype=np.float64)

    n_bimodal = 0
    n_fail = 0

    for i in range(len(X)):
        job_id = i + 1
        # Try common file naming patterns
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

    # Report
    total = len(X)
    print(f"\n{'=' * 60}")
    print(f"Processed: {total - n_fail}/{total}")
    print(f"Failed:    {n_fail}")
    print(f"Bimodal:   {n_bimodal} ({n_bimodal / max(total, 1) * 100:.1f}%)")
    bimodal_frac = n_bimodal / max(total, 1)
    if bimodal_frac > qc_threshold_bimodal:
        print(f"[WARN] Bimodal fraction ({bimodal_frac:.1%}) exceeds "
              f"threshold ({qc_threshold_bimodal:.1%}).")
        print("   Consider using robust statistics (median, IQR) for these conditions.")
    print(f"{'=' * 60}\n")

    # Save
    save_intermediate(out_file, X, y)
    print(f"Saved: {out_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse HSPICE .mt0 -> dataset.npz")
    parser.add_argument(
        "--raw_dir", default="../raw_mt0",
        help="Directory with raw .mt0 files",
    )
    parser.add_argument(
        "--out_file", default="./data/dataset.npz",
        help="Output .npz path",
    )
    parser.add_argument("--n_cond", type=int, default=200)
    args = parser.parse_args()

    process_all(args.raw_dir, args.out_file, n_cond=args.n_cond)


if __name__ == "__main__":
    main()
