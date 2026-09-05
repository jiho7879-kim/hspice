"""Shared paths + project constants. Import this first in every manuscript script.

    import _paths                       # noqa: F401  -- puts python/ on sys.path
    from _paths import DATA, RESULTS, Z_TARGET

Keeps data location, library location and the two constants that every result
depends on (Z_TARGET, zbias) in ONE place. See ../DECISIONS.md D-01, D-02.
"""
import sys
from pathlib import Path

MANUSCRIPT = Path(__file__).resolve().parent.parent
ROOT = MANUSCRIPT.parent
PYTHON = ROOT / "python"
DATA = PYTHON / "data"
RESULTS = MANUSCRIPT / "results"
FIGURES = MANUSCRIPT / "figures"

sys.path.insert(0, str(PYTHON))
sys.path.insert(0, str(PYTHON / "scripts"))   # infab_snmr_tail_diag lives here
RESULTS.mkdir(exist_ok=True)
FIGURES.mkdir(exist_ok=True)

# --- D-01: array yield target -------------------------------------------------
ARRAY_MB = 128
YIELD_TARGET = 0.99
Z_TARGET = 6.3984          # derive_z_target(mb=128, y_target=0.99, "poisson")

# --- D-07: lobe (min-of-two) correction, evaluated AT Z_TARGET ----------------
# The fab table's +0.941/+1.233 are at Z=6.50 AND on its 4-point rho grid --
# do not reuse either. rho_LR is fitted continuously in code/v_f_lobe.py.
RHO_LR = -0.3710           # skewness inversion, 9 conditions, inverse-var pooled
ZBIAS = 1.0542             # bias_at_target(RHO_LR, Z_TARGET)
Z_EFF = Z_TARGET + ZBIAS   # 7.4526

# --- spec voltage -------------------------------------------------------------
# T0 only. The EOL (0.675 V) view was dropped -- see DECISIONS.md D-05.
V_T0 = 0.625

DEVICE_COLS = ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"]
VOPS = [0.4, 0.5, 0.6, 0.7, 0.8]


def selfcheck():
    from src.utils import derive_z_target
    from infab_snmr_tail_diag import bias_at_target
    import numpy as np

    z = derive_z_target(mb=ARRAY_MB, y_target=YIELD_TARGET, model="poisson")
    assert abs(z - Z_TARGET) < 5e-4, f"Z_TARGET stale: {z:.4f} != {Z_TARGET}"
    _, b = bias_at_target(RHO_LR, Z_TARGET, np.random.default_rng(12345))
    assert abs(b - ZBIAS) < 2e-3, f"ZBIAS stale: {b:.4f} != {ZBIAS}"
    assert DATA.is_dir(), f"missing {DATA}"
    print(f"_paths OK  Z_TARGET={Z_TARGET:.4f}  rho_LR={RHO_LR:+.4f}  "
          f"Z_eff={Z_EFF:.4f}")


if __name__ == "__main__":
    selfcheck()
