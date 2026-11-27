"""01_extract 시험: 가짜 PrimeSim 덱 + .mt0 를 만들어 끝까지 돌린다.

    python vminkit/tests/test_extract.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("extract", ROOT / "01_extract.py")
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)  # type: ignore[union-attr]

VOPS = [0.4, 0.5, 0.6, 0.7, 0.8]
N_MC = 5000

DECK = """* fake PrimeSim deck
.temp '({temp}) +(0)'
.param VOP='({vop}) +(0)'
""" + "".join(
    f".param {fam}_{dev}{i}=' ({{{fam}_{dev}}}) + (0)'\n"
    for fam in ("VTMSKEW", "VTSGSKEW", "VTSLSKEW", "MOMSKEW")
    for dev in ("PU", "PG", "PD") for i in (1, 2)) + ".end\n"


def write_mt0(path: Path, cols, data, per_line=5):
    lines = ["$DATA1 SOURCE='PrimeSim'", ".TITLE '* mc'"]

    def wrap(tok):
        return ["  ".join(tok[i:i + per_line]) for i in range(0, len(tok), per_line)]

    lines += wrap(list(cols))
    for row in data:
        lines += wrap([f"{v:.6e}" for v in row])
    path.write_text("\n".join(lines) + "\n")


def make_conditions(n, rng):
    return [dict(cn=float(rng.integers(-40, 41)), sk=float(rng.integers(-20, 21)),
                 pu=float(rng.integers(-40, 41)), lpu=round(rng.uniform(0.8, 1.2), 2),
                 l_com=round(rng.uniform(0.8, 1.2), 2), l_sk=round(rng.uniform(-0.1, 0.1), 2),
                 mpu=round(rng.uniform(0.9, 1.1), 2), m_com=round(rng.uniform(0.9, 1.1), 2),
                 m_sk=round(rng.uniform(-0.05, 0.05), 2)) for _ in range(n)]


def deck_params(c, vop, temp):
    p = {"temp": temp, "vop": vop,
         "VTMSKEW_PG": (c["cn"] + c["sk"]) / 1000, "VTMSKEW_PD": (c["cn"] - c["sk"]) / 1000,
         "VTMSKEW_PU": c["pu"] / 1000,
         "VTSLSKEW_PG": c["l_com"] + c["l_sk"], "VTSLSKEW_PD": c["l_com"] - c["l_sk"],
         "VTSLSKEW_PU": c["lpu"],
         "MOMSKEW_PG": c["m_com"] + c["m_sk"], "MOMSKEW_PD": c["m_com"] - c["m_sk"],
         "MOMSKEW_PU": c["mpu"]}
    for d in ("PU", "PG", "PD"):
        p[f"VTSGSKEW_{d}"] = 1.0
    return p


def true_mu(c, vop):  # V, Vop 에 따라 증가
    return 0.25 * vop - 0.0005 * c["cn"] + 0.0003 * c["pu"]


def build(tmp: Path, rng):
    conds = make_conditions(12, rng)
    rd, wr = tmp / "read", tmp / "write"
    rd.mkdir(); wr.mkdir()
    for ci, c in enumerate(conds):
        for vop in VOPS:
            stem = f"c{ci:03d}_v{int(vop * 10)}"
            # read
            (rd / f"{stem}.in").write_text(DECK.format(**deck_params(c, vop, 125)))
            mu = true_mu(c, vop)
            if ci == 3 and vop == 0.7:
                mu = true_mu(c, 0.4)          # 일부러 Vop 역전
            s = rng.normal(mu, 0.012, N_MC)
            idx = np.arange(1, N_MC + 1)
            if not (ci == 5 and vop == 0.5):  # 일부러 결과 누락
                write_mt0(rd / f"{stem}.mt0", ["index", "snmr", "temper", "alter#"],
                          np.column_stack([idx, s, np.full(N_MC, 125), np.ones(N_MC)]))
            # write: a0 = left(bwrm_1), a1 = right(bwrm_2, bwrm_1 은 Vop 로 고정)
            (wr / f"{stem}.in").write_text(DECK.format(**deck_params(c, vop, -40)))
            left = rng.normal(mu + 0.05, 0.02, N_MC)
            right = rng.normal(mu + 0.05, 0.02, N_MC)
            perm = rng.permutation(N_MC)        # 파일 순서가 달라도 index 로 짝을 맞추는지
            write_mt0(wr / f"{stem}_a0.mt0", ["index", "bwrm_1", "temper", "alter#"],
                      np.column_stack([idx, left, np.full(N_MC, -40), np.ones(N_MC)]))
            write_mt0(wr / f"{stem}_a1.mt0", ["index", "bwrm_1", "bwrm_2", "temper", "alter#"],
                      np.column_stack([idx[perm], np.full(N_MC, vop), right[perm],
                                       np.full(N_MC, -40), np.ones(N_MC)]))
    return conds


def main():
    rng = np.random.default_rng(1)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        conds = build(tmp, rng)
        cfg = json.load(open(ROOT / "configs" / "example_node.json", encoding="utf-8"))
        cfg["work_dir"] = str(tmp / "work")
        cfg["modes"]["read"]["sim_dirs"] = [str(tmp / "read")]
        cfg["modes"]["write"]["sim_dirs"] = [str(tmp / "write")]
        cp = tmp / "node.json"
        cp.write_text(json.dumps(cfg))

        extract.main(["--config", str(cp), "--workers", "2", "--save-samples"])

        out = tmp / "work" / "01_extract"
        rd = pd.read_csv(out / "dataset_read.csv")
        wr = pd.read_csv(out / "dataset_write.csv")
        iss = pd.read_csv(out / "qc_issues_read.csv")

        assert len(rd) == 60 and rd["cond_id"].nunique() == 12, (len(rd), rd["cond_id"].nunique())
        assert rd["mu_mV"].isna().sum() == 1
        assert set(iss["kind"]) >= {"missing_result", "non_monotonic_vop", "incomplete_vop"}, set(iss["kind"])
        # 9D 역변환이 맞는지
        r0 = rd[rd["deck"] == "c000_v4"].iloc[0]
        for k, v in conds[0].items():
            assert abs(r0[k] - v) < 1e-6, (k, r0[k], v)
        # 통계: 5000 표본, sigma 12 mV 근처
        good = rd[rd["mu_mV"].notna()]
        assert (good["n_mc"] == N_MC).all()
        assert abs(good["sigma_mV"].median() - 12.0) < 0.5
        # write: min(left, right) 의 평균은 mu+50mV 보다 작아야 (두 정규의 min)
        w0 = wr[wr["deck"] == "c000_v4"].iloc[0]
        exp = (true_mu(conds[0], 0.4) + 0.05) * 1000 - 20 / np.sqrt(np.pi)
        assert abs(w0["mu_mV"] - exp) < 1.5, (w0["mu_mV"], exp)
        assert (out / "qc_read.md").exists() and (out / "qc_read.png").exists()
        assert len(np.load(out / "samples_read.npz").files) == 59

        # 덮어쓰기 방지
        try:
            extract.main(["--config", str(cp)])
            raise AssertionError("--force 없이 덮어씀")
        except SystemExit as e:
            assert "--force" in str(e)
        print((out / "qc_read.md").read_text())
    print("OK test_extract")


if __name__ == "__main__":
    main()
