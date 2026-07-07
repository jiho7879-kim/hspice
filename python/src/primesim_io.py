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
   The two sides may live under different column names — in the in-house
   layout the left value is `bwrm_1` in `*a0.mt0` and the right value is
   `bwrm_2` in `*a1.mt0` (whose own `bwrm_1` is pinned to Vop and unused);
   pass `measure_left`/`measure_right` to select each. Example:

       vtrip_min_stats("cell_a0.mt0", "cell_a1.mt0",
                       measure_left="bwrm_1", measure_right="bwrm_2")

The wrap handling is format-agnostic; only the column-name matching uses
HSPICE/PrimeSim conventions (index / temper / alter# / time are treated as
non-measure columns). If your headers differ, pass `measure=` explicitly or
adjust `_NON_MEASURE`.
"""

from __future__ import annotations

import re
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
    measure_left: str | None = None,
    measure_right: str | None = None,
) -> dict:
    """Write-margin stats from separate left/right MC files.

    Per MC index: v_min = min(v_left, v_right). Then aggregate over samples.
    Files are joined by their 'index' column when present (order-independent);
    otherwise samples are paired positionally (both files must then have the
    same length and ordering).

    Column selection (in-house layout, e.g. PrimeSim write margin):
        the two files may store the wanted quantity under *different* column
        names — e.g. the left value is `bwrm_1` in `*a0.mt0` while the right
        value is `bwrm_2` in `*a1.mt0` (whose `bwrm_1` is pinned to Vop and
        meaningless). Pass `measure_left`/`measure_right` to name each side;
        `measure` is a shared fallback, and if all are None each file's first
        non-index/temper/alter# column is used.

    Returns mu / median / sigma / n and the raw `min_samples` vector (for QC
    histograms or lobe-style diagnostics).
    """
    cl, ol = parse_mt0_wrapped(left_path)
    cr, orr = parse_mt0_wrapped(right_path)
    vl = _pick_measure(cl, ol, measure_left or measure)
    vr = _pick_measure(cr, orr, measure_right or measure)

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


# ===========================================================================
# .in deck condition parsing + merge with result files
#
# The PVTA / local-global variation conditions already live in the input
# deck, so there is no reason to transcribe them by hand again.  We parse
# them from the deck and merge with the (hand-transcribed) result file into
# one row -- the user only writes down the measured statistics.
# ===========================================================================

# Skew families in the deck (see templates/sram_cell_pvta.sp):
#   VTMSKEW  : Vth mean shift   (mV-scale additive)
#   VTSGSKEW : global sigma multiplier (nominal 1)
#   VTSLSKEW : local  sigma multiplier (nominal 1)
#   MOMSKEW  : mobility multiplier      (nominal 1)
# each per device PU/PG/PD and per instance 1/2 (1==2, so we collapse).
_SKEW_FAMILIES = ("VTMSKEW", "VTSGSKEW", "VTSLSKEW", "MOMSKEW")
_DEVICES = ("PU", "PG", "PD")


def _paren_sum(expr: str) -> float:
    """Sum all parenthesized numeric terms in a deck value expression.

    Deck values look like  '(0.75) +(0)'  or  ' (1) + (0)'  — a systematic
    term plus a random/mismatch term.  Their sum is the effective value
    (only one is non-zero in a swept condition).  Falls back to the first
    bare float if there are no parentheses.
    """
    nums = re.findall(r"\(\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\)", expr)
    if nums:
        return float(sum(float(x) for x in nums))
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", expr)
    if not m:
        raise ValueError(f"no numeric value in deck expr: {expr!r}")
    return float(m.group(0))


def parse_in_deck(path: str | Path) -> dict:
    """Parse PVTA / variation conditions from one HSPICE/PrimeSim .in deck.

    Extracts VOP, temperature, and the four skew families x {PU,PG,PD}.
    Instance suffixes 1/2 are collapsed (they carry the same value; a
    mismatch is flagged if they ever differ).  Convenience keys map to the
    project convention: common_N_shift = VTMSKEW_PG, PU_shift = VTMSKEW_PU.

    Returns a flat dict suitable as one row of the merged table.
    """
    path = Path(path)
    text = path.read_text(errors="replace")

    # collect all .param NAME = VALUE
    params: dict[str, str] = {}
    for m in re.finditer(r"^\s*\.param\s+([A-Za-z0-9_]+)\s*=\s*(.+)$",
                         text, flags=re.MULTILINE | re.IGNORECASE):
        params[m.group(1).upper()] = m.group(2).strip().strip("'\"")

    row: dict[str, float | str] = {"deck": path.stem}

    # VOP / temperature
    if "VOP" in params:
        row["VOP"] = _paren_sum(params["VOP"])
    tmatch = re.search(r"^\s*\.temp\s+(.+)$", text, flags=re.MULTILINE | re.IGNORECASE)
    if tmatch:
        row["temp"] = _paren_sum(tmatch.group(1).strip().strip("'\""))

    # skew families x devices, collapsing instance 1/2
    for fam in _SKEW_FAMILIES:
        for dev in _DEVICES:
            vals = []
            for inst in ("1", "2"):
                key = f"{fam}_{dev}{inst}"
                if key in params:
                    vals.append(_paren_sum(params[key]))
            if not vals:
                continue
            if len(vals) == 2 and abs(vals[0] - vals[1]) > 1e-9:
                row[f"{fam}_{dev}_mismatch"] = vals[1] - vals[0]
            row[f"{fam}_{dev}"] = vals[0]

    # project-convention convenience columns
    if "VTMSKEW_PG" in row:
        row["common_N_shift"] = row["VTMSKEW_PG"]
    if "VTMSKEW_PU" in row:
        row["PU_shift"] = row["VTMSKEW_PU"]

    return row


def parse_result_md(path: str | Path) -> dict:
    """Flexible key-value parse of a hand-written result file.

    Accepts `key value`, `key=value`, `key: value` (any run of spaces),
    one pair per line, `#`/`*` comments ignored.  Keys are lowercased.
    Values that parse as float become float, else stay string.  This is a
    starting point -- adjust to the exact in-house layout once a sample is
    available (e.g. map 'avg'/'std' to mu_SNMR/sigma_SNMR).
    """
    path = Path(path)
    out: dict[str, float | str] = {}
    for line in path.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "*", "//")):
            continue
        m = re.match(r"([A-Za-z0-9_./\-]+)\s*[:=]?\s+(.+)$", s)
        if not m:
            continue
        key = m.group(1).strip().lower()
        val = m.group(2).strip()
        try:
            out[key] = float(val.split()[0])
        except (ValueError, IndexError):
            out[key] = val
    return out


def merge_deck_dir(
    in_dir: str | Path,
    result_dir: str | Path | None = None,
    result_ext: str = ".md",
    pattern: str = "*.in",
    out_csv: str | Path | None = None,
    result_parser=None,
):
    """Merge every deck's conditions with its result file into one table.

    For each deck matching `pattern` in `in_dir`, find a result file in
    `result_dir` (defaults to `in_dir`) whose stem CONTAINS the deck stem
    and ends in `result_ext` (loose match, per the in-house naming), parse
    it, and merge deck-conditions + results into one row.  Missing result
    files leave the result columns blank (fill by hand later).

    Returns a pandas DataFrame; writes `out_csv` if given.  This is the
    single merged file for tidy record-keeping.
    """
    import pandas as pd

    in_dir = Path(in_dir)
    result_dir = Path(result_dir) if result_dir else in_dir
    parse_result = result_parser or parse_result_md

    decks = sorted(in_dir.glob(pattern))
    if not decks:
        raise FileNotFoundError(f"no {pattern} in {in_dir}")

    candidates = list(result_dir.glob(f"*{result_ext}"))
    rows, n_matched = [], 0
    for deck in decks:
        row = parse_in_deck(deck)
        matches = [f for f in candidates if deck.stem in f.stem]
        if matches:
            if len(matches) > 1:
                print(f"  [WARN] {deck.name}: {len(matches)} result matches, "
                      f"using {matches[0].name}")
            res = parse_result(matches[0])
            # prefix-free merge; deck keys win on collision (conditions are
            # authoritative), result keys fill the rest
            for k, v in res.items():
                row.setdefault(k, v)
            row["result_file"] = matches[0].name
            n_matched += 1
        else:
            row["result_file"] = ""
        rows.append(row)

    df = pd.DataFrame(rows)
    print(f"  merged {len(decks)} decks ({n_matched} with results) "
          f"-> {df.shape[1]} columns")
    if out_csv:
        df.to_csv(out_csv, index=False)
        print(f"  -> {out_csv}")
    return df


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
    p2.add_argument("left", help="e.g. *a0.mt0")
    p2.add_argument("right", help="e.g. *a1.mt0")
    p2.add_argument("--measure", default=None, help="shared column name")
    p2.add_argument("--measure-left", default=None,
                    help="left-file column (e.g. bwrm_1)")
    p2.add_argument("--measure-right", default=None,
                    help="right-file column (e.g. bwrm_2)")

    p3 = sub.add_parser("show", help="dump parsed columns/shape")
    p3.add_argument("file")

    p4 = sub.add_parser("deck", help="parse conditions from one .in deck")
    p4.add_argument("file")

    p5 = sub.add_parser("merge", help="merge .in decks + result files -> CSV")
    p5.add_argument("in_dir")
    p5.add_argument("--result-dir", default=None)
    p5.add_argument("--result-ext", default=".md")
    p5.add_argument("--pattern", default="*.in")
    p5.add_argument("-o", "--out", default="merged_conditions.csv")

    args = ap.parse_args()

    if args.cmd == "snmr":
        r = mc_stats(args.file, args.measure, args.floor)
        print(f"SNMR  mu={r['mu']:.6g}  sigma={r['sigma']:.6g}  "
              f"median={r['median']:.6g}  n={r['n']}"
              + (f"  frac<=floor={r['frac_below_floor']:.4f}"
                 if "frac_below_floor" in r else ""))
    elif args.cmd == "vtrip":
        r = vtrip_min_stats(args.left, args.right, measure=args.measure,
                            measure_left=args.measure_left,
                            measure_right=args.measure_right)
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
    elif args.cmd == "deck":
        row = parse_in_deck(args.file)
        for k, v in row.items():
            print(f"  {k:22s} = {v}")
    elif args.cmd == "merge":
        merge_deck_dir(args.in_dir, result_dir=args.result_dir,
                       result_ext=args.result_ext, pattern=args.pattern,
                       out_csv=args.out)


if __name__ == "__main__":
    _main()
