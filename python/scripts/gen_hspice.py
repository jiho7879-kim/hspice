"""
Generate HSPICE simulation decks for SRAM PVTA analysis.

Usage:
    python scripts/gen_hspice.py --n_cond 200              # Stage 1 (3D)
    python scripts/gen_hspice.py --n_cond 200 --stage 2    # Stage 2 (+Vwl)
    python scripts/gen_hspice.py --validation               # Validation (TT only)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
import numpy as np
from src.hspice_io import generate_decks, run_validation, _load_template
from src.utils import WLUD_FACTORS, N_WLUD, VOPS


def main() -> None:
    parser = argparse.ArgumentParser(description="SRAM PVTA deck generator")
    parser.add_argument("--out_dir", default=str(Path.cwd() / "decks"),
                        help="Output directory for decks")
    parser.add_argument("--n_cond", type=int, default=200,
                        help="Number of (common_N, PU) conditions")
    parser.add_argument("--validation", action="store_true",
                        help="Generate validation decks instead of full set")
    parser.add_argument("--stage", type=int, default=1, choices=[1, 2, 3],
                        help="Dimensional expansion stage (1=3D, 2=4D+Vwl, 3=5D+Temp)")
    parser.add_argument("--n_vwl", type=int, default=None,
                        help="Number of Vwl levels (default: all WLUD_FACTORS = 5)")
    parser.add_argument("--wlud_start", type=float, default=0.80,
                        help="Lowest WLUD factor (default: 0.80)")
    parser.add_argument("--wlud_stop", type=float, default=1.00,
                        help="Highest WLUD factor (default: 1.00)")
    args = parser.parse_args()

    template_path = Path(__file__).resolve().parent.parent / "templates" / "sram_cell_pvta.sp"
    template = _load_template(template_path)

    if args.validation:
        run_validation(args.out_dir)
        return

    # Stage 2+: Vwl levels from WLUD factors
    vwl_levels = None
    if args.stage >= 2:
        n_vwl = args.n_vwl if args.n_vwl is not None else N_WLUD
        wlud_levels = np.linspace(args.wlud_start, args.wlud_stop, n_vwl, dtype=np.float64)
        # Vwl = Vop × WLUD, but Vop varies → we compute Vwl per condition.
        # Template receives {{ VWL }} as actual voltage, so we pass the
        # vwl_levels as absolute voltages derived from the average Vop.
        vwl_levels = VOPS.mean() * wlud_levels

    print(f"Stage {args.stage}: {args.n_cond} conditions"
          f"{f' x {len(vwl_levels)} Vwl' if vwl_levels is not None else ''}")

    generate_decks(
        template,
        n_cond=args.n_cond,
        out_dir=args.out_dir,
        stage=args.stage,
        vwl_levels=vwl_levels,
    )


if __name__ == "__main__":
    main()
