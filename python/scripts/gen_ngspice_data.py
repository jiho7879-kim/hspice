"""
Generate Vmin training dataset via ngspice butterfly extraction.

For each (common_N_shift, PU_shift, Vop) condition:
  1. Render the ngspice butterfly deck template
  2. Run ngspice_con.exe -b (batch mode, deterministic DC sweep)
  3. Parse .measure results to extract SNM = y1 (Seevinck min |v1-v2|)
  4. Store mu_SNMR = SNM, sigma_SNMR from an empirical model

Usage:
    python scripts/gen_ngspice_data.py
    python scripts/gen_ngspice_data.py --n-cond 50 --parallel 8
    python scripts/gen_ngspice_data.py --data ./data/ngspice_dataset.npz
"""

from __future__ import annotations

import sys
import time
import re
import subprocess
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.utils import (
    COMMON_N_MIN, COMMON_N_MAX, PU_MIN, PU_MAX,
    VOPS, N_VOP, VOP_COL,
    sample_common_n_pu,
)
from src.data import save_intermediate

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

NSPICE = Path(r"C:\Users\User\Documents\HSPICE\bin\ngspice_con.exe")
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "sram_butterfly_ng.sp"
MODEL_PATH = Path(__file__).resolve().parent.parent / "templates" / "14nm_HP.pm"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "dataset_ngspice.npz"

# Empirical sigma model (matches src/physics.py)
SIGMA0 = 0.015
SIGMA_VOP_SLOPE = 0.004

# ---------------------------------------------------------------------------
# Deck rendering
# ---------------------------------------------------------------------------


def render_deck(
    template: str,
    *,
    cn_mv: float,
    pu_mv: float,
    vop: float,
    vwl: float,
    temp_c: float,
) -> str:
    """Render the Mustache-style {{ }} template with one parameter set."""
    deck = template.replace("{{ VOP }}", f"{vop:.4f}")
    deck = deck.replace("{{ COMMON_N_SHIFT }}", f"{cn_mv / 1000:.6f}")
    deck = deck.replace("{{ PU_SHIFT }}", f"{pu_mv / 1000:.6f}")
    deck = deck.replace("{{ TEMP }}", f"{temp_c:.1f}")
    deck = deck.replace("{{ VWL }}", f"{vwl:.4f}")
    return deck


# ---------------------------------------------------------------------------
# ngspice runner
# ---------------------------------------------------------------------------


def run_one(
    deck_text: str,
    model_text: str,
    *,
    timeout: int = 120,
) -> dict[str, float]:
    """Run one ngspice butterfly simulation and return .measure results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        deck_path = tmp / "run.sp"
        model_path = tmp / "14nm_HP.pm"
        deck_path.write_text(deck_text, encoding="utf-8")
        model_path.write_text(model_text, encoding="utf-8")

        result = subprocess.run(
            [str(NSPICE), "-b", str(deck_path)],
            cwd=str(tmp),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    if result.returncode != 0:
        err_lines = [l for l in result.stderr.splitlines() if "error" in l.lower()]
        detail = err_lines[-1] if err_lines else result.stderr[:200]
        raise RuntimeError(f"ngspice exited {result.returncode}: {detail}")

    # Parse .measure results from stdout
    meas: dict[str, float] = {}
    for line in result.stdout.splitlines():
        s = line.strip()
        if "=" in s and not s.startswith("*") and not s.startswith("Index"):
            parts = s.split("=", 1)
            key = parts[0].strip()
            m = re.match(r"([+-]?\d+\.?\d*[eE]?[+-]?\d*)", parts[1].strip())
            if m:
                try:
                    meas[key] = float(m.group(1))
                except ValueError:
                    pass
    return meas


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate ngspice Vmin dataset")
    parser.add_argument("--n-cond", type=int, default=60,
                        help="Number of (common_N, PU) conditions (default: 60)")
    parser.add_argument("--parallel", type=int, default=4,
                        help="Parallel worker count (default: 4)")
    parser.add_argument("--temp", type=float, default=125.0,
                        help="Temperature in degC (default: 125)")
    parser.add_argument("--vwl-ratio", type=float, default=1.0,
                        help="Vwl/Vop ratio (default: 1.0 = no underdrive)")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed for condition sampling")
    parser.add_argument("--data", type=str, default=str(DEFAULT_OUT),
                        help=f"Output .npz path (default: {DEFAULT_OUT})")
    args = parser.parse_args()

    # Load template and model
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    model_text = MODEL_PATH.read_text(encoding="utf-8")

    # Sample conditions
    rng = np.random.default_rng(args.seed)
    conditions = sample_common_n_pu(args.n_cond, seed=args.seed)
    total = args.n_cond * N_VOP

    print(f"Conditions: {args.n_cond} x {N_VOP} Vop = {total} simulations")
    print(f"  cn range: [{COMMON_N_MIN}, {COMMON_N_MAX}] mV")
    print(f"  pu range: [{PU_MIN}, {PU_MAX}] mV")
    print(f"  Vop range: [{VOPS[0]:.1f}, {VOPS[-1]:.1f}] V")
    print(f"  Temp: {args.temp:.0f} degC, Vwl/Vop: {args.vwl_ratio:.2f}")
    print(f"  Workers: {args.parallel}")
    print()

    # Build task list
    X_list: list[np.ndarray] = []
    y_list: list[np.ndarray] = []

    tasks = []
    for cn_mv, pu_mv in conditions:
        for vop in VOPS:
            deck = render_deck(
                template_text,
                cn_mv=float(cn_mv),
                pu_mv=float(pu_mv),
                vop=float(vop),
                vwl=float(vop * args.vwl_ratio),
                temp_c=args.temp,
            )
            tasks.append((deck, float(cn_mv), float(pu_mv), float(vop)))

    t0 = time.time()
    n_ok = 0
    n_fail = 0

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        fut_to_task = {
            pool.submit(run_one, deck, model_text): (cn, pu, vop)
            for deck, cn, pu, vop in tasks
        }

        for fut in as_completed(fut_to_task):
            cn, pu, vop = fut_to_task[fut]
            try:
                meas = fut.result()
            except Exception as exc:
                print(f"  FAIL cn={cn:+.1f} pu={pu:+.1f} Vop={vop:.1f}: {exc}")
                n_fail += 1
                continue

            # SNM from Seevinck y1 (min |v1-v2| in left butterfly lobe)
            snm = meas.get("y1", float("nan"))

            # Empirical sigma model
            sigma = SIGMA0 + SIGMA_VOP_SLOPE * (0.9 - vop)

            X_list.append(np.array([cn, pu, vop]))
            y_list.append(np.array([snm, sigma]))
            n_ok += 1

    elapsed = time.time() - t0

    # Report
    print(f"\nDone: {n_ok}/{total} succeeded, {n_fail} failed in {elapsed:.1f}s")
    print(f"  Throughput: {n_ok / max(elapsed, 0.01):.1f} sim/s")

    if n_ok == 0:
        print("  ERROR: No simulations succeeded. Aborting.")
        sys.exit(1)

    X = np.array(X_list, dtype=np.float64)
    y = np.array(y_list, dtype=np.float64)

    valid = ~np.isnan(y[:, 0])
    n_valid = valid.sum()
    print(f"  Valid SNM values: {n_valid}/{n_ok}")

    # Print stats
    for j, vop in enumerate(VOPS):
        mask = np.abs(X[:, VOP_COL] - vop) < 0.01
        if mask.sum() > 0:
            snm_vals = y[mask, 0]
            mu = np.nanmean(snm_vals)
            std = np.nanstd(snm_vals)
            n_nan = np.isnan(snm_vals).sum()
            print(f"  Vop={vop:.1f}V: mu={mu:.4f}V sigma={std:.4f}V (raw) "
                  f"[{int(mask.sum())} pts, {n_nan} NaN]")

    # Save
    out_path = Path(args.data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_intermediate(str(out_path), X, y)
    print(f"\nSaved: {out_path}")
    print(f"  X: {X.shape}, y: {y.shape}")


if __name__ == "__main__":
    main()
