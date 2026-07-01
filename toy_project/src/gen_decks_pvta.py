"""
HSPICE deck generator for SRAM PVTA toy project.

Generates 200 (common_N, PU) x 6 Vop = 1200 decks using stratified
Sobol sampling. Supports batch directory structure for farm submission.

Usage:
    python src/gen_decks_pvta.py --out_dir ./decks --n_cond 200 --validation
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import (
    COMMON_N_MIN,
    COMMON_N_MAX,
    PU_MIN,
    PU_MAX,
    VOPS,
    N_VOP,
    TEMP_C,
    sample_common_n_pu,
)

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "sram_cell_pvta.sp"
MC_RUNS = 10_000


def _load_template(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def render_deck(
    template: str,
    common_n_shift: float,
    pu_shift: float,
    vop: float,
    temp: float,
    output_prefix: str,
) -> str:
    """Render template with parameter values.

    Uses simple string replacement. If you need robust templating,
    replace with Jinja2.
    """
    deck = template.replace("{{ COMMON_N_SHIFT }}", f"{common_n_shift:.3f}")
    deck = deck.replace("{{ PU_SHIFT }}", f"{pu_shift:.3f}")
    deck = deck.replace("{{ VOP }}", f"{vop:.4f}")
    deck = deck.replace("{{ TEMP }}", f"{temp:.1f}")
    deck = deck.replace("{{ OUTPUT_PREFIX }}", output_prefix)
    deck = deck.replace("{{ MC_RUNS }}", str(MC_RUNS))
    return deck


def generate_decks(
    template: str,
    n_cond: int = 200,
    out_dir: str | Path = "decks",
    seed: int = 42,
    submit_script: bool = True,
) -> None:
    """Generate all 1200 decks and a batch submit script.

    Directory structure:
        out_dir/
            cond_000001/  (or cond_000001_0.4V.sp)
            cond_000002/
            ...
            submit_all.sh  (or .bat for Windows)
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Sample stratified (common_N, PU) pairs
    conditions = sample_common_n_pu(n_cond, seed=seed)  # (n_cond, 2)
    total_jobs = n_cond * N_VOP
    print(f"Generating {total_jobs} decks ({n_cond} conditions x {N_VOP} Vop levels)...")

    for i, (cn, pu) in enumerate(conditions):
        for j, vop in enumerate(VOPS):
            job_id = i * N_VOP + j + 1
            prefix = f"cond_{job_id:06d}"
            # Each deck is its own file
            deck_content = render_deck(
                template, cn, pu, vop, TEMP_C, prefix,
            )
            # Option A: flat directory with individual files
            fname = f"{prefix}.sp"
            (out_dir / fname).write_text(deck_content, encoding="utf-8")

    print(f"  -> {total_jobs} decks written to {out_dir.resolve()}")

    if submit_script:
        _write_submit_script(out_dir, total_jobs)


def _write_submit_script(out_dir: Path, total_jobs: int) -> None:
    """Write a batch submission script for the farm.

    Adapt this to your LSF/PBS/SGE/slurm environment.
    """
    lines = [
        "@echo off",
        "REM HSPICE batch submission script",
        "REM Customize the hspice command and queuing system as needed.",
        "",
        f"SET DECK_DIR={out_dir.resolve()}",
        "SET HSPICE_CMD=hspice64",
        "REM SET LSF_CMD=bsub -q normal -n 1 -R \"rusage[mem=2G]\"",
        "",
        f"echo Submitting {total_jobs} jobs...",
        "",
    ]
    # Simple sequential submission for local testing
    for job_id in range(1, total_jobs + 1):
        lines.append(
            f"REM %LSF_CMD% %HSPICE_CMD% -i {out_dir}\\cond_{job_id:06d}.sp "
            f"-o {out_dir}\\cond_{job_id:06d}"
        )

    lines.extend([
        "",
        "echo All jobs submitted.",
        f"echo Total: {total_jobs} jobs.",
    ])

    (out_dir / "submit_all.bat").write_text("\r\n".join(lines))
    print(f"  -> submit script written to {out_dir / 'submit_all.bat'}")


def run_validation(out_dir: str | Path) -> None:
    """Run one condition at 6 Vop levels manually to validate the deck."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    template = _load_template(TEMPLATE_PATH)

    # Pick TT (common_N=0, PU=0) for validation
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
    print("Then inspect .mt0 output for histogram QC.")


def main() -> None:
    parser = argparse.ArgumentParser(description="SRAM PVTA deck generator")
    parser.add_argument(
        "--out_dir", default=str(Path(__file__).resolve().parent.parent / "decks"),
        help="Output directory for decks",
    )
    parser.add_argument("--n_cond", type=int, default=200, help="Number of (common_N, PU) conditions")
    parser.add_argument(
        "--validation", action="store_true",
        help="Generate validation decks (1 TT condition x 6 Vop) instead of full set",
    )
    args = parser.parse_args()

    template = _load_template(TEMPLATE_PATH)

    if args.validation:
        run_validation(args.out_dir)
    else:
        generate_decks(template, n_cond=args.n_cond, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
