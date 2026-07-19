"""
stageB_leakage_check.py — how much do the Stage B numbers drop under an
honest (mirror-grouped) split?

WHY
---
The in-house condition generator re-used ONE Sobol stream across all four
(cn, pu) quadrants and only flipped the signs of cn / pu.  So conditions come
in MIRROR groups: members of a group share every coordinate except the sign of
cn and/or pu.  Stage B (348 conditions) contains 114 such pu-mirror pairs.

A condition-level split (what stageB_real_data.py does) still puts mirror twins
on OPPOSITE sides of the split -- the model sees a near-copy of every hold-out
point during training, so hold-out R2 / Vmin RMSE are optimistic.

This script re-fits the SAME surrogate with the SAME settings and compares:
    (a) condition-level random split   <- what the Stage B gate reported
    (b) mirror-grouped split           <- honest: whole mirror group held out
over several seeds, and reports the gap.

Usage:  cd python && python scripts/stageB_leakage_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.utils import Z_FIXED
from src.surrogate import Surrogate
from src.physics_layer import compute_vmin_from_z
from src.hspice_io import parse_manual_xlsx

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "260713_stageB_snmr.xlsx"
OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "stageB_real"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_VOPS = np.array([0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float64)
TEST_FRAC = 0.15
SEEDS = [42, 43, 44, 45, 46]
N_ITER = 200


def mirror_group_key(cond: np.ndarray) -> np.ndarray:
    """Mirror group id for Stage-B conditions (cn, sk, pu).

    Members of one group came from the SAME Sobol row; the generator only
    flipped the sign of cn and/or pu.  So (|cn|, |pu|, sk) identifies the group.
    """
    key = np.column_stack([np.abs(cond[:, 0]), np.abs(cond[:, 2]), cond[:, 1]])
    _, inv = np.unique(np.round(key, 6), axis=0, return_inverse=True)
    return inv


def vmin_of(surr: Surrogate, cond: np.ndarray) -> np.ndarray:
    """Vmin per condition (n_cond,) from the GP, over the data's Vop grid."""
    n, nv = len(cond), len(DATA_VOPS)
    Xp = np.zeros((n * nv, 4))
    for i, (cn, sk, pu) in enumerate(cond):
        s = i * nv
        Xp[s:s + nv, 0] = cn
        Xp[s:s + nv, 1] = sk
        Xp[s:s + nv, 2] = pu
        Xp[s:s + nv, 3] = DATA_VOPS
    mu, _, sig, _ = surr.predict(Xp)
    z = (mu / (sig + 1e-12)).reshape(n, nv)
    return compute_vmin_from_z(z, z_target=Z_FIXED, vops=DATA_VOPS)


def vmin_true(cond: np.ndarray, cond_all: np.ndarray, y: np.ndarray,
              X: np.ndarray) -> np.ndarray:
    """Vmin from the MEASURED mu/sigma of each condition (no GP)."""
    out = []
    for c in cond:
        m = np.all(np.isclose(X[:, :3], c), axis=1)
        rows = X[m]
        order = np.argsort(rows[:, 3])
        yy = y[m][order]
        z = (yy[:, 0] / (yy[:, 1] + 1e-12)).reshape(1, -1)
        out.append(compute_vmin_from_z(z, z_target=Z_FIXED, vops=DATA_VOPS)[0])
    return np.asarray(out)


def r2(pred, true):
    return float(1 - np.sum((pred - true) ** 2) / np.sum((true - true.mean()) ** 2))


def evaluate(X, y, cond, inv, test_mask_cond, seed):
    """Fit on train conditions, score on hold-out conditions."""
    test_rows = test_mask_cond[inv]
    X_tr, y_tr = X[~test_rows], y[~test_rows]
    X_te, y_te = X[test_rows], y[test_rows]

    surr = Surrogate(device="cpu")
    surr.fit(X_tr, y_tr, verbose=False, n_iter=N_ITER)
    mu_p, _, sig_p, _ = surr.predict(X_te)

    te_cond = cond[test_mask_cond]
    v_pred = vmin_of(surr, te_cond)
    v_true = vmin_true(te_cond, cond, y, X)
    ok = np.isfinite(v_pred) & np.isfinite(v_true)
    vmin_rmse = float(np.sqrt(np.mean((v_pred[ok] - v_true[ok]) ** 2))) * 1000  # mV

    return {
        "mu_r2": r2(mu_p, y_te[:, 0]),
        "sigma_r2": r2(sig_p, y_te[:, 1]),
        "mu_rmse_mV": float(np.sqrt(np.mean((mu_p - y_te[:, 0]) ** 2))) * 1000,
        "vmin_rmse_mV": vmin_rmse,
        "n_vmin": int(ok.sum()),
        "n_test_cond": int(test_mask_cond.sum()),
    }


def main() -> None:
    print("=" * 74)
    print("Stage B — leakage check: condition split vs MIRROR-GROUPED split")
    print("=" * 74)

    d = parse_manual_xlsx(DATA_PATH)
    X, y = d["X"], d["y"]
    cond, inv = np.unique(X[:, :3], axis=0, return_inverse=True)
    grp = mirror_group_key(cond)
    n_cond, n_grp = len(cond), len(np.unique(grp))
    print(f"\n  rows={len(X)}  conditions={n_cond}  mirror groups={n_grp}")
    sizes = np.bincount(np.bincount(grp))
    for s in range(1, len(sizes)):
        if sizes[s]:
            print(f"    group size {s}: {sizes[s]} groups -> {s*sizes[s]} conditions")
    twins = sum(s * sizes[s] for s in range(2, len(sizes)))
    print(f"  conditions with a twin: {twins}/{n_cond} ({twins/n_cond:.0%})")

    rows = {"condition": [], "mirror_grouped": []}
    for seed in SEEDS:
        rng = np.random.default_rng(seed)

        # (a) condition-level split -- what the gate used
        ids = np.arange(n_cond)
        rng.shuffle(ids)
        n_te = max(1, int(n_cond * TEST_FRAC))
        m_cond = np.zeros(n_cond, bool)
        m_cond[ids[:n_te]] = True

        # (b) mirror-grouped split -- whole group goes to one side
        gids = np.unique(grp)
        rng.shuffle(gids)
        m_grp = np.zeros(n_cond, bool)
        picked, n_target = [], int(n_cond * TEST_FRAC)
        for g in gids:
            if m_grp.sum() >= n_target:
                break
            m_grp |= (grp == g)
            picked.append(g)

        for name, mask in (("condition", m_cond), ("mirror_grouped", m_grp)):
            r = evaluate(X, y, cond, inv, mask, seed)
            rows[name].append(r)
            print(f"  seed {seed} [{name:15s}] test_cond={r['n_test_cond']:3d}  "
                  f"mu R2={r['mu_r2']:.4f}  sigma R2={r['sigma_r2']:+.4f}  "
                  f"mu RMSE={r['mu_rmse_mV']:.2f}mV  Vmin RMSE={r['vmin_rmse_mV']:.2f}mV (n={r['n_vmin']})")

    print("\n" + "=" * 74)
    print(f"  {'metric':<16}{'condition split':>20}{'mirror-grouped':>20}{'delta':>16}")
    print("-" * 74)
    lines = []
    for k, unit, hi_good in (("mu_r2", "", True), ("sigma_r2", "", True),
                             ("mu_rmse_mV", " mV", False), ("vmin_rmse_mV", " mV", False)):
        a = np.array([r[k] for r in rows["condition"]])
        b = np.array([r[k] for r in rows["mirror_grouped"]])
        delta = b.mean() - a.mean()
        line = (f"  {k:<16}{a.mean():>13.4f}+-{a.std():.4f}{b.mean():>13.4f}+-{b.std():.4f}"
                f"{delta:>+12.4f}{unit}")
        print(line)
        lines.append(f"{k}: condition={a.mean():.4f}+-{a.std():.4f} "
                     f"mirror_grouped={b.mean():.4f}+-{b.std():.4f} delta={delta:+.4f}")
    print("=" * 74)

    mu_a = np.mean([r["mu_r2"] for r in rows["condition"]])
    mu_b = np.mean([r["mu_r2"] for r in rows["mirror_grouped"]])
    print(f"\n  Go/No-Go (mu R2 >= 0.95):")
    print(f"    condition split : {mu_a:.4f}  -> {'PASS' if mu_a >= 0.95 else 'FAIL'}")
    print(f"    mirror-grouped  : {mu_b:.4f}  -> {'PASS' if mu_b >= 0.95 else 'FAIL'}  <- honest number")

    with open(OUT_DIR / "leakage_check.txt", "w") as f:
        f.write(f"seeds={SEEDS} test_frac={TEST_FRAC} n_iter={N_ITER}\n")
        f.write(f"conditions={n_cond} mirror_groups={n_grp} with_twin={twins}\n")
        for ln in lines:
            f.write(ln + "\n")
    print(f"\n  -> {OUT_DIR / 'leakage_check.txt'}")


if __name__ == "__main__":
    main()
