"""
PrimeSim / HSPICE Monte-Carlo .mt0 parsing for in-house data extraction.

Two problems this module solves (reported from real PrimeSim runs):

1. **Auto-wrapped rows.** With the reference deck's options, the measure
   output wraps to a new physical line after ~5 columns, so one MC sample
   spans several lines. Line-based parsers break. We instead read *all*
   numeric tokens flat and reshape by the column count — wrap position no
   longer matters.

2. **Vtrip left/right split.** SNMR carries trailing summary stats in the
   same file (avg/std are trivial to read). Vtrip, however, is written to
   separate left and right files; the write margin per MC sample is
   min(left, right), and only then do we take the mean/median over samples.
   `vtrip_min_stats` joins the two files by MC index and does exactly that.

The wrap handling is format-agnostic; only the column-name matching uses
HSPICE/PrimeSim conventions (index / temper / alter# / time are treated as
non-measure columns). If your headers differ, pass `measure=` explicitly or
adjust `_NON_MEASURE`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# Column names that are never the measured quantity (case-insensitive).
_NON_MEASURE = {"index", "temper", "temperature", "alter#", "alter", "time"}

# Lines that are metadata, not header/data tokens.
_SKIP_PREFIX = ("$", ".", "*")


def _is_float(tok: str) -> bool:
    try:
        float(tok)
        return True
    except ValueError:
        return False


def parse_mt0_wrapped(
    path: str | Path,
) -> tuple[dict[str, np.ndarray], list[str]]:
    """Parse a (possibly line-wrapped) PrimeSim/HSPICE .mt0 MC file.

    Strategy: collect every token past the metadata lines; the leading
    non-numeric tokens are the (wrapped) column names, and the trailing
    numeric tokens are the (wrapped) data. len(data) // n_cols = n_rows;
    reshape. This is immune to where the simulator inserts line breaks.

    Trailing summary blocks (some tools append avg/std rows labelled with
    text) are cut off automatically: numeric parsing stops at the first
    non-numeric token after the data begins.

    Returns:
        columns: dict{lowercased_name: (n_rows,) array}
        col_order: list of column names in file order
    """
    path = Path(path)
    raw = path.read_text(errors="replace").splitlines()

    tokens: list[str] = []
    for ln in raw:
        s = ln.strip()
        if not s or s.startswith(_SKIP_PREFIX):
            continue
        tokens.extend(s.split())

    if not tokens:
        raise ValueError(f"no data tokens in {path}")

    # Leading non-numeric tokens = column names (may be wrapped across lines)
    i = 0
    col_order: list[str] = []
    while i < len(tokens) and not _is_float(tokens[i]):
        col_order.append(tokens[i].lower())
        i += 1
    n_cols = len(col_order)
    if n_cols == 0:
        raise ValueError(f"no column header found in {path}")

    # Trailing numeric block = data; stop at the first non-numeric token
    # (guards against text-labelled summary rows appended after the samples)
    nums: list[float] = []
    for t in tokens[i:]:
        if _is_float(t):
            nums.append(float(t))
        else:
            break

    n_rows = len(nums) // n_cols
    if n_rows == 0:
        raise ValueError(
            f"{path}: found {len(nums)} values for {n_cols} columns")
    dropped = len(nums) - n_rows * n_cols
    if dropped:
        # a partial trailing row (e.g. a lone summary value) — drop it
        nums = nums[: n_rows * n_cols]

    arr = np.asarray(nums, dtype=np.float64).reshape(n_rows, n_cols)
    columns = {name: arr[:, j] for j, name in enumerate(col_order)}
    return columns, col_order


def _pick_measure(
    columns: dict[str, np.ndarray], col_order: list[str],
    measure: str | None,
) -> np.ndarray:
    """Return the measured-quantity column.

    If `measure` is given, use it (case-insensitive). Otherwise pick the
    first column that is not index/temper/alter#/time.
    """
    if measure is not None:
        key = measure.lower()
        if key not in columns:
            raise KeyError(f"measure '{measure}' not in columns {col_order}")
        return columns[key]
    for name in col_order:
        if name not in _NON_MEASURE:
            return columns[name]
    raise ValueError(f"no measure column among {col_order}")


def _index_order(columns: dict[str, np.ndarray], n: int) -> np.ndarray:
    """Return a permutation that sorts rows by the 'index' column if present,
    else identity (assume already in MC-sample order)."""
    if "index" in columns:
        return np.argsort(columns["index"], kind="stable")
    return np.arange(n)


def mc_stats(
    path: str | Path,
    measure: str | None = None,
    snm_floor: float | None = None,
) -> dict:
    """Per-condition statistics from one MC .mt0 file (e.g. SNMR).

    Computes mu/sigma/median directly from the raw MC samples (more robust
    than scraping a trailing summary line, and identical when the samples
    are the summary's source). If `snm_floor` is given, also reports the
    fraction of samples at/below it (fail-mixing flag).
    """
    columns, order = parse_mt0_wrapped(path)
    vals = _pick_measure(columns, order, measure)
    vals = vals[~np.isnan(vals)]
    out = {
        "mu": float(np.mean(vals)),
        "sigma": float(np.std(vals, ddof=1)),
        "median": float(np.median(vals)),
        "n": int(len(vals)),
    }
    if snm_floor is not None:
        out["frac_below_floor"] = float(np.mean(vals <= snm_floor))
    return out


def vtrip_min_stats(
    left_path: str | Path,
    right_path: str | Path,
    measure: str | None = None,
) -> dict:
    """Write-margin stats from separate left/right Vtrip MC files.

    Per MC index: v_min = min(v_left, v_right). Then aggregate over samples.
    Files are joined by their 'index' column when present (order-independent);
    otherwise samples are paired positionally (both files must then have the
    same length and ordering).

    Returns mu / median / sigma / n and the raw `min_samples` vector (for QC
    histograms or lobe-style diagnostics).
    """
    cl, ol = parse_mt0_wrapped(left_path)
    cr, orr = parse_mt0_wrapped(right_path)
    vl = _pick_measure(cl, ol, measure)
    vr = _pick_measure(cr, orr, measure)

    if "index" in cl and "index" in cr:
        pl = _index_order(cl, len(vl))
        pr = _index_order(cr, len(vr))
        idx_l = cl["index"][pl]
        idx_r = cr["index"][pr]
        common = np.intersect1d(idx_l, idx_r)
        if len(common) == 0:
            raise ValueError("left/right files share no MC index")
        map_l = {v: k for k, v in enumerate(idx_l)}
        map_r = {v: k for k, v in enumerate(idx_r)}
        vl = vl[pl][[map_l[c] for c in common]]
        vr = vr[pr][[map_r[c] for c in common]]
        n_dropped = max(len(idx_l), len(idx_r)) - len(common)
    else:
        if len(vl) != len(vr):
            raise ValueError(
                f"no index column and lengths differ "
                f"({len(vl)} vs {len(vr)}); cannot pair samples")
        n_dropped = 0

    v_min = np.minimum(vl, vr)
    v_min = v_min[~np.isnan(v_min)]
    return {
        "mu": float(np.mean(v_min)),
        "median": float(np.median(v_min)),
        "sigma": float(np.std(v_min, ddof=1)),
        "n": int(len(v_min)),
        "n_dropped": int(n_dropped),
        "min_samples": v_min,
    }


# ---------------------------------------------------------------------------
# CLI — validate on a real file
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Parse PrimeSim/HSPICE MC .mt0 (wrap-safe)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("snmr", help="stats from one MC file")
    p1.add_argument("file")
    p1.add_argument("--measure", default=None)
    p1.add_argument("--floor", type=float, default=None)

    p2 = sub.add_parser("vtrip", help="min-margin stats from left+right files")
    p2.add_argument("left")
    p2.add_argument("right")
    p2.add_argument("--measure", default=None)

    p3 = sub.add_parser("show", help="dump parsed columns/shape")
    p3.add_argument("file")

    args = ap.parse_args()

    if args.cmd == "snmr":
        r = mc_stats(args.file, args.measure, args.floor)
        print(f"SNMR  mu={r['mu']:.6g}  sigma={r['sigma']:.6g}  "
              f"median={r['median']:.6g}  n={r['n']}"
              + (f"  frac<=floor={r['frac_below_floor']:.4f}"
                 if "frac_below_floor" in r else ""))
    elif args.cmd == "vtrip":
        r = vtrip_min_stats(args.left, args.right, args.measure)
        print(f"Vtrip(min L,R)  mu={r['mu']:.6g}  median={r['median']:.6g}  "
              f"sigma={r['sigma']:.6g}  n={r['n']}  dropped={r['n_dropped']}")
    elif args.cmd == "show":
        cols, order = parse_mt0_wrapped(args.file)
        n = len(next(iter(cols.values())))
        print(f"columns ({len(order)}): {order}")
        print(f"rows: {n}")
        for name in order:
            v = cols[name]
            print(f"  {name:12s} [{v.min():.4g}, {v.max():.4g}]  e.g. {v[:3]}")


if __name__ == "__main__":
    _main()
