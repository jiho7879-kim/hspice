"""1단계: PrimeSim 결과 → 학습 데이터셋 + QC 리포트.

    python vminkit/01_extract.py --config vminkit/configs/my_node.json
    python vminkit/01_extract.py --config ... --mode read --workers 8
    python vminkit/01_extract.py --config ... --force          # 기존 결과 덮어쓰기

설정 파일의 modes 마다 sim_dirs 안의 덱(*.in)을 하나씩 읽어서
  - 덱의 .param 에서 조건(9D 축, VOP, temp)을 뽑고
  - 짝이 되는 .mt0 MC 결과에서 mu / sigma / median / n 을 계산한다
    (write 는 a0/a1 두 파일을 MC index 로 맞춰 min(left, right) 을 먼저 취한다).

출력 (work_dir/01_extract/):
  dataset_<mode>.csv    조건 x Vop 당 한 행. 값 단위는 mV. 02_train 의 입력.
  qc_<mode>.md          사람이 보고 다음 단계로 갈지 판단하는 리포트
  qc_issues_<mode>.csv  문제 행 목록 (덱 이름 포함)
  qc_<mode>.png         분포 그림
  samples_<mode>.npz    (--save-samples) 덱별 원시 MC 표본, float32

이 스크립트는 다음 단계를 자동으로 실행하지 않는다. 리포트를 보고 판단한 뒤
`02_train.py` 를 직접 실행한다.
"""
from __future__ import annotations

import argparse
import sys
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.axes import AXES  # noqa: E402
from core.config import ConfigError, load_config  # noqa: E402
from core.worker import process_deck  # noqa: E402

STEP_DIR = "01_extract"


# ---------------------------------------------------------------------------
# 모드 하나 처리
# ---------------------------------------------------------------------------

def extract_mode(cfg: Dict[str, Any], name: str, out_dir: Path,
                 workers: int, keep: bool) -> None:
    import pandas as pd

    m = cfg["modes"][name]
    res = m["result"]
    vscale = 1000.0 if m["value_unit"] == "V" else 1.0
    floor = None if m.get("snm_floor_mV") is None else float(m["snm_floor_mV"]) / vscale

    jobs = []
    for d in m["sim_dirs"]:
        sdir = Path(d)
        if not sdir.is_dir():
            raise SystemExit(f"[{name}] sim_dir 가 없습니다: {sdir}")
        decks = sorted(sdir.glob(cfg["deck"]["pattern"]))
        print(f"[{name}] {sdir}: 덱 {len(decks)}개")
        jobs += [(str(p), str(sdir), res, cfg["deck"]["vth_unit"], keep, floor)
                 for p in decks]
    if not jobs:
        raise SystemExit(f"[{name}] 덱을 하나도 못 찾았습니다 (pattern {cfg['deck']['pattern']})")

    t0 = time.time()
    results: List[Dict[str, Any]] = []
    step = max(1, len(jobs) // 20)
    if workers > 1:
        with Pool(workers) as pool:
            for i, r in enumerate(pool.imap(process_deck, jobs, chunksize=16)):
                results.append(r)
                if (i + 1) % step == 0:
                    print(f"  {i + 1}/{len(jobs)}  ({time.time() - t0:.0f}s)")
    else:
        for i, j in enumerate(jobs):
            results.append(process_deck(j))
            if (i + 1) % step == 0:
                print(f"  {i + 1}/{len(jobs)}  ({time.time() - t0:.0f}s)")
    print(f"[{name}] 파싱 완료 {len(results)}개, {time.time() - t0:.0f}s")

    # issues / samples 분리
    issues = []
    samples = {}
    for r in results:
        for kind, msg in r.pop("issues"):
            issues.append({"deck": r["deck"], "sim_dir": r["sim_dir"], "kind": kind, "detail": msg})
        s = r.pop("_samples", None)
        if s is not None:
            samples[r["deck"]] = s

    df = pd.DataFrame(results)
    for c in (["mu", "sigma", "median", "n_mc", "n_nan", "result_file", "frac_below_floor"]
              + AXES + ["vop", "temp"]):
        if c not in df.columns:
            df[c] = np.nan
    for c in ("mu", "sigma", "median"):
        df[c] = df[c] * vscale

    # 조건 id: 9D 값이 같으면 같은 조건 (Vop 만 다름)
    ok_axes = df[AXES].notna().all(axis=1)
    df["cond_id"] = -1
    if ok_axes.any():
        _, inv = np.unique(df.loc[ok_axes, AXES].to_numpy(float), axis=0, return_inverse=True)
        df.loc[ok_axes, "cond_id"] = inv.ravel()

    issues += qc_checks(df, m)
    df = df.rename(columns={"mu": "mu_mV", "sigma": "sigma_mV", "median": "median_mV"})
    cols = (["cond_id", "deck"] + AXES + ["vop", "temp", "mu_mV", "sigma_mV", "median_mV",
            "n_mc", "n_nan", "sim_dir", "result_file"])
    if floor is not None:
        cols.insert(cols.index("n_mc"), "frac_below_floor")
    df = df[cols].sort_values(["cond_id", "vop", "deck"]).reset_index(drop=True)

    df.to_csv(out_dir / f"dataset_{name}.csv", index=False)
    iss = pd.DataFrame(issues, columns=["deck", "sim_dir", "kind", "detail"])
    iss.to_csv(out_dir / f"qc_issues_{name}.csv", index=False)
    if keep and samples:
        np.savez_compressed(out_dir / f"samples_{name}.npz", **samples)
    plot_qc(df, name, m, out_dir / f"qc_{name}.png")
    write_report(df, iss, name, m, cfg, out_dir / f"qc_{name}.md")
    print(f"[{name}] → {out_dir}/dataset_{name}.csv, qc_{name}.md")


# ---------------------------------------------------------------------------
# QC
# ---------------------------------------------------------------------------

def qc_checks(df, m: Dict[str, Any]) -> List[Dict[str, Any]]:
    """데이터셋 단위 검사. 자동으로 고치지 않고 목록만 만든다 (논문 때처럼 사람이 판단)."""
    out: List[Dict[str, Any]] = []

    def add(row, kind, detail):
        out.append({"deck": row["deck"], "sim_dir": row["sim_dir"], "kind": kind, "detail": detail})

    good = df[df["mu"].notna()]

    # MC 표본 수가 다른 덱보다 눈에 띄게 적음
    if len(good):
        med_n = float(good["n_mc"].median())
        for _, r in good[good["n_mc"] < 0.9 * med_n].iterrows():
            add(r, "low_n_mc", f"n_mc {int(r['n_mc'])} (중앙값 {med_n:.0f})")
        for _, r in good[good["n_nan"] > 0].iterrows():
            add(r, "nan_samples", f"NaN 표본 {int(r['n_nan'])}개 제외")

    # 온도가 설정과 다름
    t_exp = m.get("temperature_C")
    if t_exp is not None:
        bad = df[df["temp"].notna() & (np.abs(df["temp"] - float(t_exp)) > 1e-6)]
        for _, r in bad.iterrows():
            add(r, "temp_mismatch", f"덱 {r['temp']} °C, 설정 {t_exp} °C")

    # 같은 조건·Vop 가 두 번
    dup = df[(df["cond_id"] >= 0)].duplicated(["cond_id", "vop"], keep=False)
    for _, r in df[(df["cond_id"] >= 0)][dup].iterrows():
        add(r, "duplicate_condition", f"cond {r['cond_id']} Vop {r['vop']} 중복")

    # Vop 가 빠진 조건
    vops = sorted(good["vop"].dropna().unique())
    for cid, g in good[good["cond_id"] >= 0].groupby("cond_id"):
        have = set(g["vop"].round(6))
        miss = [v for v in vops if round(v, 6) not in have]
        if miss:
            add(g.iloc[0], "incomplete_vop", f"cond {cid}: Vop {miss} 없음")

    # mu 는 Vop 에 따라 올라가야 한다 (논문 2026-08-30 audit 규칙).
    # MC 잡음 3배(sigma*sqrt(2/n)) 보다 크게 내려가면 표시.
    for cid, g in good[good["cond_id"] >= 0].groupby("cond_id"):
        g = g.sort_values("vop")
        mu, sg, n = g["mu"].to_numpy(), g["sigma"].to_numpy(), g["n_mc"].to_numpy(float)
        for i in range(1, len(g)):
            tol = 3 * np.hypot(sg[i] / np.sqrt(n[i]), sg[i - 1] / np.sqrt(n[i - 1]))
            if mu[i] < mu[i - 1] - tol:
                r = g.iloc[i]
                add(r, "non_monotonic_vop",
                    f"cond {cid}: Vop {g['vop'].iloc[i - 1]}→{r['vop']} 에서 mu "
                    f"{mu[i - 1]:.2f}→{mu[i]:.2f} mV 감소")
    return out


def plot_qc(df, name: str, m: Dict[str, Any], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    good = df[df["mu_mV"].notna()]
    fig, ax = plt.subplots(2, 2, figsize=(11, 8))
    for v, g in good.groupby("vop"):
        ax[0, 0].hist(g["mu_mV"], bins=50, alpha=0.5, label=f"{v:g} V")
        ax[0, 1].hist(g["sigma_mV"], bins=50, alpha=0.5, label=f"{v:g} V")
    ax[0, 0].set_title(f"{m['metric']} mu (mV) per Vop")
    ax[0, 1].set_title(f"{m['metric']} sigma (mV) per Vop")
    ax[0, 0].legend(fontsize=8)
    rng = np.random.default_rng(0)
    cids = good["cond_id"].unique()
    for cid in rng.choice(cids, size=min(50, len(cids)), replace=False):
        g = good[good["cond_id"] == cid].sort_values("vop")
        ax[1, 0].plot(g["vop"], g["mu_mV"], lw=0.7, alpha=0.6)
    ax[1, 0].set_title("mu vs Vop (50 random conditions)")
    ax[1, 0].set_xlabel("Vop (V)")
    z = good["mu_mV"] / good["sigma_mV"]
    for v, g in good.assign(z=z).groupby("vop"):
        ax[1, 1].hist(g["z"], bins=50, alpha=0.5, label=f"{v:g} V")
    ax[1, 1].set_title("z = mu / sigma per Vop")
    fig.suptitle(f"{name} · {m['metric']} · {len(good)} rows")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def write_report(df, iss, name: str, m: Dict[str, Any], cfg: Dict[str, Any], path: Path) -> None:
    good = df[df["mu_mV"].notna()]
    lines = [
        f"# 01_extract QC · {cfg['node']} · {name} ({m['metric']})",
        "",
        f"- 설정: `{cfg['_path']}`",
        f"- 생성: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 덱 {len(df)}개 중 값이 나온 행 {len(good)}개, 조건 {good['cond_id'].nunique()}개",
        f"- Vop: {', '.join(f'{v:g}' for v in sorted(good['vop'].unique()))} V",
        f"- 온도(덱): {', '.join(f'{t:g}' for t in sorted(df['temp'].dropna().unique()))} °C"
        f" (설정 {m.get('temperature_C')} °C)",
        f"- MC 표본 수: 중앙값 {good['n_mc'].median():.0f}, 최소 {good['n_mc'].min():.0f}"
        if len(good) else "- MC 표본 수: -",
        f"- 목표 z (참고): {cfg['z_target']:.4f}",
        "",
        "## Vop별 요약 (mV)",
        "",
        "| Vop (V) | 행 | mu 평균 | mu 최소 | sigma 평균 | z 최소 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for v, g in good.groupby("vop"):
        z = g["mu_mV"] / g["sigma_mV"]
        lines.append(f"| {v:g} | {len(g)} | {g['mu_mV'].mean():.2f} | {g['mu_mV'].min():.2f} | "
                     f"{g['sigma_mV'].mean():.2f} | {z.min():.2f} |")
    lines += ["", "## 문제 목록", ""]
    if len(iss) == 0:
        lines.append("문제 없음.")
    else:
        lines += ["| 종류 | 개수 | 예시 |", "| --- | --- | --- |"]
        for kind, g in iss.groupby("kind"):
            ex = g.iloc[0]
            lines.append(f"| {kind} | {len(g)} | {ex['deck']}: {ex['detail']} |")
        lines += ["", f"전체 목록: `qc_issues_{name}.csv`"]
    lines += [
        "",
        "## 다음 단계",
        "",
        "문제 목록을 보고 필요하면 시뮬레이션을 다시 돌리거나 `dataset_*.csv` 를 직접 고친 뒤",
        "`python vminkit/02_train.py --config <설정>` 을 실행한다.",
        "`non_monotonic_vop` 은 논문 때 전사 오류로 확인된 유형이라 특히 확인할 것.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="1단계: PrimeSim 결과 → 학습 데이터셋")
    ap.add_argument("--config", required=True, help="노드 설정 JSON")
    ap.add_argument("--mode", default="all", help="read / write / all (설정의 modes 이름)")
    ap.add_argument("--workers", type=int, default=1, help="병렬 프로세스 수")
    ap.add_argument("--save-samples", action="store_true", help="덱별 원시 MC 표본을 npz 로 저장")
    ap.add_argument("--force", action="store_true", help="기존 결과가 있어도 덮어쓰기")
    a = ap.parse_args(argv)

    try:
        cfg = load_config(a.config)
    except ConfigError as e:
        raise SystemExit(f"설정 오류: {e}")

    names = list(cfg["modes"]) if a.mode == "all" else [a.mode]
    for n in names:
        if n not in cfg["modes"]:
            raise SystemExit(f"설정에 mode '{n}' 이 없습니다 ({list(cfg['modes'])})")

    out_dir = Path(cfg["work_dir"]) / STEP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    for n in names:
        if (out_dir / f"dataset_{n}.csv").exists() and not a.force:
            raise SystemExit(f"{out_dir}/dataset_{n}.csv 가 이미 있습니다. 덮어쓰려면 --force")

    for n in names:
        extract_mode(cfg, n, out_dir, a.workers, a.save_samples)
    print("\n완료. QC 리포트를 확인한 뒤 02_train.py 를 실행하세요.")


if __name__ == "__main__":
    main()
