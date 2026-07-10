"""
inhouse_deck_gen.py — SELF-CONTAINED deck-generation core for the fab env.

╔══════════════════════════════════════════════════════════════════════════╗
║  TO THE IN-HOUSE CODE ASSISTANT / ENGINEER:                               ║
║                                                                          ║
║  DO NOT MODIFY the functions in the "FROZEN CORE" section below          ║
║  (generate_conditions, _unit_samples, _quadrant_cnpu, deck_number,       ║
║   iter_decks). They define the EXACT conditions and deck numbering that   ║
║  must match our local run so that only measured RESULTS need to be sent   ║
║  back (never the conditions).                                            ║
║                                                                          ║
║  DO adapt ONLY the "SITE ADAPTER" section at the bottom: file naming,     ║
║  paths, the deck template string, and how you invoke the simulator.      ║
║                                                                          ║
║  Reproducibility contract (must equal our side):                         ║
║    VERSION, stage, n_cond, seed, metric, method, vops, deck_prefix, start ║
║  Default method="rng" uses numpy PCG64 (version-stable). Only numpy is    ║
║  required (scipy only if method="sobol").                                 ║
╚══════════════════════════════════════════════════════════════════════════╝

Deck numbering (per the reference deck TT-N convention):
  numbering RESTARTS at `start` for EACH Vop and runs over the condition
  index. condition i (0-based) at a given Vop -> deck_id f"{prefix}-{start+i}".
  So every Vop has its own TT-1..TT-N over the same condition order, and a
  result is identified by (vop, deck_no) alone.
"""

from __future__ import annotations
import numpy as np

# ===========================================================================
# ############################  FROZEN CORE  ################################
# ###  DO NOT MODIFY anything between here and "END FROZEN CORE".         ###
# ###  Changing it breaks condition reproducibility with the model side.  ###
# ===========================================================================

VERSION = "1.0"

CN_MIN, CN_MAX = -60.0, 60.0
PU_MIN, PU_MAX = -60.0, 60.0
SK_MIN, SK_MAX = -20.0, 20.0
LOC_MIN, LOC_MAX = 0.7, 1.3
MOM_MIN, MOM_MAX = 0.7, 1.3

QW_SNMR = {(-1, +1): 0.45, (-1, -1): 0.20, (+1, +1): 0.15, (+1, -1): 0.20}
QW_VTRIP = {(-1, +1): 0.10, (-1, -1): 0.15, (+1, +1): 0.30, (+1, -1): 0.45}

STAGE_COLUMNS = {
    "A": ["cn", "pu"],
    "B": ["cn", "sk", "pu"],
    "D": ["cn", "sk", "pu", "lpu", "lpg", "lpd", "mpu", "mpg", "mpd"],
}


def _unit_samples(n: int, d: int, seed: int, method: str) -> np.ndarray:
    if method == "rng":
        return np.random.default_rng(seed).random((n, d))
    if method == "sobol":
        from scipy.stats import qmc
        s = qmc.Sobol(d=d, scramble=True, seed=seed)
        m = int(np.ceil(np.log2(max(n, 1))))
        return s.random_base2(m=m)[:n]
    raise ValueError(f"unknown method {method!r} (use 'rng' or 'sobol')")


def _quadrant_cnpu(n_total: int, weights: dict, seed: int, method: str) -> np.ndarray:
    parts = []
    for i, ((cn_s, pu_s), w) in enumerate(weights.items()):
        n = int(round(n_total * w))
        if n <= 0:
            continue
        u = _unit_samples(n, 2, seed + 1 + i, method)
        cn_lo, cn_hi = (0.0, CN_MAX) if cn_s > 0 else (CN_MIN, 0.0)
        pu_lo, pu_hi = (0.0, PU_MAX) if pu_s > 0 else (PU_MIN, 0.0)
        cn = cn_lo + (cn_hi - cn_lo) * u[:, 0]
        pu = pu_lo + (pu_hi - pu_lo) * u[:, 1]
        parts.append(np.column_stack([cn, pu]))
    pts = np.vstack(parts)
    np.random.default_rng(seed).shuffle(pts)
    if len(pts) < n_total:
        extra = _unit_samples(n_total - len(pts), 2, seed + 999, method)
        extra = np.column_stack([CN_MIN + (CN_MAX - CN_MIN) * extra[:, 0],
                                 PU_MIN + (PU_MAX - PU_MIN) * extra[:, 1]])
        pts = np.vstack([pts, extra])
    return pts[:n_total]


def generate_conditions(stage, n_cond, seed=42, metric="snmr", method="rng",
                        quadrant_weighted=True):
    """Return (column_names, conditions[n_cond, n_col]). DETERMINISTIC.
    cn/sk/pu integer mV, loc/mom 2 decimals. Vop added downstream."""
    stage = stage.upper()
    if stage not in STAGE_COLUMNS:
        raise ValueError(f"stage must be A/B/D, got {stage!r}")
    weights = QW_SNMR if metric == "snmr" else QW_VTRIP
    if quadrant_weighted and stage in ("B", "D"):
        cnpu = _quadrant_cnpu(n_cond, weights, seed, method)
    else:
        u = _unit_samples(n_cond, 2, seed, method)
        cnpu = np.column_stack([CN_MIN + (CN_MAX - CN_MIN) * u[:, 0],
                                PU_MIN + (PU_MAX - PU_MIN) * u[:, 1]])
    cn = np.round(cnpu[:, 0]).astype(int)
    pu = np.round(cnpu[:, 1]).astype(int)
    if stage == "A":
        return STAGE_COLUMNS["A"], np.column_stack([cn, pu]).astype(float)
    n_extra = 1 if stage == "B" else 7
    e = _unit_samples(n_cond, n_extra, seed + 100, method)
    sk = np.round(SK_MIN + (SK_MAX - SK_MIN) * e[:, 0]).astype(int)
    if stage == "B":
        return STAGE_COLUMNS["B"], np.column_stack([cn, sk, pu]).astype(float)
    loc = np.round(LOC_MIN + (LOC_MAX - LOC_MIN) * e[:, 1:4], 2)
    mom = np.round(MOM_MIN + (MOM_MAX - MOM_MIN) * e[:, 4:7], 2)
    return STAGE_COLUMNS["D"], np.column_stack([cn, sk, pu, loc, mom]).astype(float)


def deck_number(cond_index: int, start: int = 1) -> int:
    """deck_no for the (0-based) condition index. Numbering restarts per Vop."""
    return start + cond_index


def iter_decks(stage, n_cond, vops, seed=42, metric="snmr", method="rng",
               deck_prefix="TT", start=1):
    """Yield one record per (Vop, condition) in the EXACT order the fab loop
    and our sheet must share. Each record:
        {deck_no, deck_id, vop, <condition columns...>}
    Outer loop = Vop (numbering restarts each Vop), inner = condition index.
    """
    cols, cond = generate_conditions(stage, n_cond, seed, metric, method)
    int_cols = {"cn", "sk", "pu"}
    for v in vops:
        for i in range(len(cond)):
            no = deck_number(i, start)
            rec = {"deck_no": no, "deck_id": f"{deck_prefix}-{no}", "vop": float(v)}
            for j, c in enumerate(cols):
                val = cond[i, j]
                rec[c] = int(val) if c in int_cols else round(float(val), 2)
            yield rec

# ===========================================================================
# ##########################  END FROZEN CORE  #############################
# ===========================================================================


# ---------------------------------------------------------------------------
# ############################  SITE ADAPTER  ##############################
# ###  ADAPT THIS SECTION to the in-house environment: deck template,     ###
# ###  file naming/paths, simulator invocation. Do NOT touch the core.    ###
# ---------------------------------------------------------------------------

# Vop levels (project standard: 5 levels 0.4-0.8 at Z_target=6.50).
VOPS = [0.4, 0.5, 0.6, 0.7, 0.8]


def condition_to_deck_params(rec: dict) -> dict:
    """Map a core record to deck .param values (PG=cn+sk, PD=cn-sk, PU=pu).
    Stage A: no sk/loc/mom -> PG=PD=cn. Stage B: no loc/mom."""
    cn = rec["cn"]; pu = rec["pu"]
    sk = rec.get("sk", 0)
    p = {
        "VTMSKEW_PG1": cn + sk, "VTMSKEW_PG2": cn + sk,
        "VTMSKEW_PD1": cn - sk, "VTMSKEW_PD2": cn - sk,
        "VTMSKEW_PU1": pu,      "VTMSKEW_PU2": pu,
        "VOP": rec["vop"],
    }
    for dev in ("PU", "PG", "PD"):
        p[f"VTSLSKEW_{dev}1"] = p[f"VTSLSKEW_{dev}2"] = rec.get(f"l{dev.lower()}", 1.0)
        p[f"MOMSKEW_{dev}1"]  = p[f"MOMSKEW_{dev}2"]  = rec.get(f"m{dev.lower()}", 1.0)
    return p


def make_deck(rec: dict) -> None:
    """<<< SITE: render the deck template with condition_to_deck_params(rec)
    and write it to your naming/path, e.g. f\"{rec['deck_id']}_vop{rec['vop']}.sp\".
    Then submit to the simulator. This stub only prints. >>>"""
    params = condition_to_deck_params(rec)
    print(f"  {rec['deck_id']:8s} vop={rec['vop']:.1f}  ->  {params}")


def main():
    """Example driver — ADAPT stage/n_cond/seed and the make_deck body."""
    STAGE, N_COND, SEED, METRIC, METHOD = "D", 500, 42, "snmr", "rng"
    print(f"inhouse_deck_gen v{VERSION}: stage {STAGE} n_cond={N_COND} "
          f"seed={SEED} metric={METRIC} method={METHOD}")
    n = 0
    for rec in iter_decks(STAGE, N_COND, VOPS, SEED, METRIC, METHOD):
        make_deck(rec)          # <<< SITE: real deck write + submit here
        n += 1
    print(f"generated {n} decks ({N_COND} conditions x {len(VOPS)} Vop)")


if __name__ == "__main__":
    main()
