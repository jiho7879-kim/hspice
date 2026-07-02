"""
Quick validation: render 1 ngspice butterfly deck, run ngspice_con, parse SNM.

End-to-end test of the ngspice SRAM butterfly extraction pipeline:
  1. Template rendering (Mustache-style {{ }} )
  2. Netlist execution via ngspice_con.exe -b
  3. .measure result parsing from stdout
  4. Raw .print data parsing (vu, v1, v2 points)
  5. Python-based SNM extraction (Seevinck method)

Usage:
    python scripts/test_ngspice.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import subprocess
import tempfile
import re
import math

import numpy as np

NSPICE = r"C:\Users\User\Documents\HSPICE\bin\ngspice_con.exe"
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "sram_butterfly_ng.sp"
MODEL_PATH = Path(__file__).resolve().parent.parent / "templates" / "14nm_HP.pm"


# ============================================================================
# Template rendering
# ============================================================================

def render_deck(template: str, *, cn_mv: float, pu_mv: float,
                vop: float, vwl: float, temp_c: float) -> str:
    """Render template with parameter values via .replace() (Mustache-style {{ }})."""
    deck = template.replace("{{ VOP }}", f"{vop:.4f}")
    deck = deck.replace("{{ COMMON_N_SHIFT }}", f"{cn_mv / 1000:.6f}")  # mV -> V
    deck = deck.replace("{{ PU_SHIFT }}", f"{pu_mv / 1000:.6f}")        # mV -> V
    deck = deck.replace("{{ TEMP }}", f"{temp_c:.1f}")
    deck = deck.replace("{{ VWL }}", f"{vwl:.4f}")
    return deck


# ============================================================================
# .measure result parsing
# ============================================================================

def parse_measure_results(log_text: str) -> dict[str, float]:
    """Parse .measure results from ngspice stdout.

    ngspice prints lines like:
        xc1 = 1.234e-01
        y1 = 1.234e-01 at= -1.000e-02
    """
    results: dict[str, float] = {}
    for line in log_text.splitlines():
        stripped = line.strip()
        # Match "key = value" (possibly with " at= ..." suffix)
        if "=" in stripped and not stripped.startswith("$") and not stripped.startswith("*"):
            # Split on first "="
            parts = stripped.split("=", 1)
            key = parts[0].strip()
            val_str = parts[1].strip()
            # Extract first numeric value (discard " at=..." suffix)
            val_match = re.match(r"([+-]?\d+\.?\d*[eE]?[+-]?\d*)", val_str)
            if val_match:
                try:
                    results[key] = float(val_match.group(1))
                except ValueError:
                    pass
    return results


# ============================================================================
# Raw .print data parsing
# ============================================================================

# ngspice .print multi-table signal names (each table has Index + v-sweep + subset)
_SIGNAL_ALIASES: dict[str, str] = {
    "v(u)": "vu",
    "v(hc1out)": "hc1out",
    "v(hc2out)": "hc2out",
    "v(v1)": "v1",
    "v(v2)": "v2",
    "v(vdiff)": "vdiff",
    "v(vabs)": "vabs",
}


def parse_print_data(log_text: str) -> dict[str, np.ndarray]:
    """Parse .print DC tables from ngspice stdout.

    ngspice wraps .print columns across multiple tables when >3 signal
    columns exist.  Each table starts with:
        Index   v-sweep   <col1>   <col2>   ...

    This parser:
      1. Scans for "Index" headers, extracts column names
      2. Reads data rows after each header (split by dash-line separator)
      3. Merges all tables by sweep index into a single dict of arrays.

    Returns dict with keys: "vu", "hc1out", "hc2out", "v1", "v2",
    "vdiff", "vabs" (whichever were found in the .print output).
    """
    lines = log_text.splitlines()
    merged: dict[int, dict[str, float]] = {}

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("Index"):
            # --- Parse header ---
            header_parts = re.split(r"\s+", stripped)
            col_names: list[str] = []
            for hp in header_parts[2:]:  # skip "Index" and "v-sweep"
                alias = _SIGNAL_ALIASES.get(hp, hp)
                col_names.append(alias)

            # Find separator (dash line) then start reading data
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("---"):
                i += 1
            i += 1  # skip separator line

            # Read rows until next blank line or next header
            while i < len(lines):
                row = lines[i].strip()
                if not row or row.startswith("Index"):
                    break
                parts = re.split(r"\s+", row)
                if len(parts) >= 2:
                    try:
                        sweep_idx = int(parts[0])
                        sweep_val = float(parts[1])
                    except (ValueError, IndexError):
                        i += 1
                        continue

                    if sweep_idx not in merged:
                        merged[sweep_idx] = {"vu": sweep_val}
                    elif abs(merged[sweep_idx]["vu"] - sweep_val) > 1e-12:
                        # Duplicate row with different value — skip (corner case)
                        i += 1
                        continue

                    for j, col_name in enumerate(col_names):
                        if j + 2 < len(parts):
                            try:
                                merged[sweep_idx][col_name] = float(parts[j + 2])
                            except (ValueError, IndexError):
                                pass
                i += 1
            continue
        i += 1

    if not merged:
        return {}

    # Convert to dict of arrays
    result: dict[str, list[float]] = {}
    sorted_idxs = sorted(merged.keys())
    for col_name in ("vu", "hc1out", "hc2out", "v1", "v2", "vdiff", "vabs"):
        vals = []
        for idx in sorted_idxs:
            if col_name in merged[idx]:
                vals.append(merged[idx][col_name])
        if vals:
            result[col_name] = np.array(vals)

    return result


# ============================================================================
# SNM extraction from raw data (Seevinck method)
# ============================================================================

def compute_snm_from_data(vu: np.ndarray, v1: np.ndarray, v2: np.ndarray) -> float:
    """Compute SRAM read SNM from butterfly data.

    Seevinck method:
      1. Find crossing points where v1(vu) == v2(vu)
      2. Between consecutive crossings, compute min(|v1 - v2|)
      3. SNM = min of those minima
    """
    diff = v1 - v2

    # Find sign changes (zero crossings)
    crossings: list[int] = []
    for i in range(len(diff) - 1):
        if diff[i] == 0:
            crossings.append(i)
        elif diff[i] * diff[i + 1] < 0:
            crossings.append(i)

    if len(crossings) < 2:
        # If we can't find proper crossings, use the minimum |v1-v2| as SNM
        # (this approximates the Seevinck method when the butterfly is weak)
        return float(np.min(np.abs(diff)))

    # Between each pair of consecutive crossings, compute min |v1-v2|
    distances: list[float] = []
    for i in range(len(crossings) - 1):
        start = crossings[i]
        end = crossings[i + 1]
        segment_min = float(np.min(np.abs(diff[start:end + 1])))
        distances.append(segment_min)

    if not distances:
        return float(np.min(np.abs(diff)))

    return min(distances)


# ============================================================================
# Main test
# ============================================================================

def main() -> None:
    print("=" * 60)
    print("ngspice SRAM butterfly validation")
    print("=" * 60)

    # Read template
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    print(f"\nTemplate: {TEMPLATE_PATH}")

    # Read model card
    model_text = MODEL_PATH.read_text(encoding="utf-8")

    # Render deck for TT corner @ Vop=0.8V
    deck = render_deck(
        template_text,
        cn_mv=0.0,
        pu_mv=0.0,
        vop=0.80,
        vwl=0.80,
        temp_c=125.0,
    )

    # Write to temp dir alongside model card
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        deck_path = tmp / "test_butterfly.sp"
        model_path = tmp / "14nm_HP.pm"
        log_path = tmp / "ngspice.log"

        deck_path.write_text(deck, encoding="utf-8")
        model_path.write_text(model_text, encoding="utf-8")

        print(f"\nDeck written: {deck_path}")
        print(f"Model:        {model_path}")

        # Run ngspice (no -o flag - .print data goes to stdout)
        cmd = [NSPICE, "-b", str(deck_path)]
        print(f"\nRunning: {' '.join(cmd)}  CWD={tmp}")
        result = subprocess.run(
            cmd,
            cwd=str(tmp),
            capture_output=True,
            text=True,
            timeout=120,
        )

        stdout_text = result.stdout

        print(f"\n--- ngspice exit code: {result.returncode} ---")

        # --- 1. Parse .measure results from stdout ---
        print(f"\n{'=' * 60}")
        print("SECTION 1: .measure results")
        print(f"{'=' * 60}")
        measure_results = parse_measure_results(stdout_text)
        if measure_results:
            for k, v in sorted(measure_results.items()):
                print(f"  {k:20s} = {v:.6e}")
        else:
            print("  (no .measure results found)")

        # --- 2. Parse .print data (multi-table format) ---
        print(f"\n{'=' * 60}")
        print("SECTION 2: .print data parsing")
        print(f"{'=' * 60}")
        print_data = parse_print_data(stdout_text)
        if not print_data:
            print("  ERROR: No data parsed from .print output")
        else:
            for key, arr in sorted(print_data.items()):
                print(f"  {key:10s}: {len(arr)} points [{arr.min():.4e}, {arr.max():.4e}]")

        # --- 3. SNM extraction ---
        print(f"\n{'=' * 60}")
        print("SECTION 3: SNM extraction")
        print(f"{'=' * 60}")

        # From .measure
        if "xc1" in measure_results and "xclast" in measure_results:
            print(f"  Crossings (from .measure):")
            for k in sorted(measure_results.keys()):
                if k.startswith("xc"):
                    print(f"    {k:10s} = {measure_results[k]:.6e} V")
            print(f"  y1 (min |v1-v2|, left)  = {measure_results.get('y1', float('nan')):.6e} V")
            print(f"  y2 (min |v1-v2|, right) = {measure_results.get('y2', float('nan')):.6e} V")
            print(f"  snmr1 (max vdiff, left) = {measure_results.get('snmr1', float('nan')):.6e} V")
            print(f"  snmr2 (max vdiffn,right)= {measure_results.get('snmr2', float('nan')):.6e} V")

        # From raw data
        vu = print_data.get("vu", np.array([]))
        v1_arr = print_data.get("v1", np.array([]))
        v2_arr = print_data.get("v2", np.array([]))
        if len(vu) > 0 and len(v1_arr) > 0 and len(v2_arr) > 0:
            snm = compute_snm_from_data(vu, v1_arr, v2_arr)
            print(f"\n  >>> SNM (raw data, Seevinck) = {snm:.6f} V ({snm * 1000:.2f} mV)")

            abs_diff = np.abs(v1_arr - v2_arr)
            min_idx = int(np.argmin(abs_diff))
            print(f"  >>> min |v1-v2| = {abs_diff[min_idx]:.6e} V @ vu={vu[min_idx]:.4f} V")
            print(f"  >>> max |v1-v2| = {abs_diff.max():.6e} V")

        # --- 4. Diagnostics ---
        print(f"\n{'=' * 60}")
        print("SECTION 4: diagnostics")
        print(f"{'=' * 60}")
        print(f"  Template lines: {len(deck.splitlines())}")
        print(f"  Model lines:    {len(model_text.splitlines())}")

        # --- 5. Overall verdict ---
        print(f"\n{'=' * 60}")
        n_points = len(print_data.get("vu", [])) if print_data else 0
        success = result.returncode == 0 and n_points > 0
        if success:
            print("  >>> VERDICT: SIMULATION PASSED <<<")
            print(f"  >>> {n_points} sweep points captured")
            if n_points > 0:
                s = compute_snm_from_data(
                    print_data["vu"], print_data["v1"], print_data["v2"]
                )
                print(f"  >>> SNM ≈ {s:.4f} V @ TT, Vop=0.8V, 125 degC")
        else:
            print("  >>> VERDICT: FAILED <<<")
            if result.returncode != 0:
                print(f"  ngspice exited with code {result.returncode}")
            if n_points == 0:
                print("  Zero data points parsed from .print output")
        print(f"{'=' * 60}")

    print("\nDone.")

    print("\nDone.")


if __name__ == "__main__":
    main()
