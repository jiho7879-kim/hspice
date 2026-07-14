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

VERSION = "2.1"

CN_MIN, CN_MAX = -60.0, 60.0
PU_MIN, PU_MAX = -60.0, 60.0
SK_MIN, SK_MAX = -20.0, 20.0
LOC_MIN, LOC_MAX = 0.7, 1.3
MOM_MIN, MOM_MAX = 0.7, 1.3
LSK_MIN, LSK_MAX = -0.075, 0.075
MSK_MIN, MSK_MAX = -0.075, 0.075

# SNMR decks weight FSG; Vtrip decks are a SEPARATE deck set weighting SFG.
QW_SNMR = {(-1, +1): 0.45, (-1, -1): 0.20, (+1, +1): 0.15, (+1, -1): 0.20}
QW_VTRIP = {(-1, +1): 0.10, (-1, -1): 0.15, (+1, +1): 0.30, (+1, -1): 0.45}

# Stage D (v2.1): common + PG-PD skew for the ratio dims (NOT independent
# lpg/lpd).  com and skew are independent draws (no clamp); derived PG/PD
# ratios may spill to [0.625, 1.375].  PG/PD derived in condition_to_deck_params.
STAGE_COLUMNS = {
    "A": ["cn", "pu"],
    "B": ["cn", "sk", "pu"],
    "D": ["cn", "sk", "pu", "lpu", "l_com", "l_sk", "mpu", "m_com", "m_sk"],
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
    lpu = np.round(LOC_MIN + (LOC_MAX - LOC_MIN) * e[:, 1], 2)
    l_com = np.round(LOC_MIN + (LOC_MAX - LOC_MIN) * e[:, 2], 2)
    l_sk = np.round(LSK_MIN + (LSK_MAX - LSK_MIN) * e[:, 3], 2)
    mpu = np.round(MOM_MIN + (MOM_MAX - MOM_MIN) * e[:, 4], 2)
    m_com = np.round(MOM_MIN + (MOM_MAX - MOM_MIN) * e[:, 5], 2)
    m_sk = np.round(MSK_MIN + (MSK_MAX - MSK_MIN) * e[:, 6], 2)
    return STAGE_COLUMNS["D"], np.column_stack(
        [cn, sk, pu, lpu, l_com, l_sk, mpu, m_com, m_sk]).astype(float)


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
# ###  이 아래만 사내 환경에 맞게 수정. FROZEN CORE는 절대 수정 금지.       ###
# ###  이 파일 하나만 reference deck이 있는 폴더에 복사해서 실행하면 됨.    ###
# ###  의존성: numpy 뿐 (method="rng"일 때. scipy는 method="sobol"만).     ###
# ---------------------------------------------------------------------------
#
# 사용법 (metric별 폴더에서 각각 실행):
#
#   cd <snmr reference deck 폴더>
#   python inhouse_deck_gen.py --metric snmr
#
#   cd <vtrip reference deck 폴더>
#   python inhouse_deck_gen.py --metric vtrip
#
#   (--metric 생략 시 폴더 안의 reference deck 파일명에서 자동 감지)
#
# 전제:
#   - 폴더 안에 Vop별 reference deck 5개(0.4~0.8V)가 있고, 각 deck의 조건
#     파라미터(VTMSKEW/VTSLSKEW/MOMSKEW)는 default 값으로 채워져 있음.
#   - 이 스크립트는 reference deck을 읽어 파라미터 값만 정규식으로 치환한
#     새 deck을 OUT_DIR에 생성. deck 번호는 Vop마다 TT-1부터 재시작.
#
# 검증 (이식 후 1회):
#   python inhouse_deck_gen.py --selftest
#   출력되는 fingerprint가 모델 측과 일치하면 조건 재현 성공.
#
# 재현성 계약 (모델 측과 반드시 동일해야 하는 값):
#   VERSION, STAGE, N_COND, SEED(metric별), METHOD, VOPS, DECK_PREFIX, START

import re
import csv
import argparse
from pathlib import Path

# --- 실행 파라미터 (모델 측과 공유되는 계약) --------------------------------
STAGE = "D"
N_COND = 2000
METHOD = "rng"                        # numpy PCG64 — 버전 무관 재현 보장
SEEDS = {"snmr": 2027, "vtrip": 2028} # metric별 seed (모델 측과 공유)
VOPS = [0.4, 0.5, 0.6, 0.7, 0.8]
DECK_PREFIX = "TT"
START = 1

# --- 파일/치환 설정 (사내 환경에 맞게 여기만 조정) --------------------------
# reference deck 파일명 glob. {metric}, {vop} 자리에 값이 들어감.
# 예: 02-sp-bc-snmr-TT-1_0.4V-125C-LOC-MC-xxx.in
REF_DECK_GLOB = "*{metric}*{prefix}-1_{vop}V*"

# 출력 폴더 (실행 폴더 기준)
OUT_DIR = "./generated_decks_{metric}"

# 파라미터 치환 정규식 (사내 기존 파싱 코드의 deck 문법에 맞춤).
#
#   .param VTMSKEW_PU1 = '( <A> ) + <B>'
#                           ^^^^^ 여기(괄호 안 A)만 조건값으로 교체.
#                                 '+ <B>' 항은 손대지 않는다.
#
# {name} 자리에 'VTMSKEW_PU\d' 같은 디바이스 패밀리 패턴이 들어가므로
# 한 규칙이 PU1, PU2를 함께 매치한다 (-> EXPECTED_OCCURRENCES = 2).
# 부호를 허용해야 함: 조건값은 음수가 될 수 있다 (기존 사내 정규식의 \d+ 는
# 음수를 매치하지 못했다 -- reference deck의 기본값이 양수라 드러나지 않았을 뿐).
PARAM_PATTERN = r"(\.param\s+{name}\s*=\s*'\s*\(\s*)[-+]?\d+(?:\.\d+)?(\s*\))"

# 치환할 디바이스 패밀리 -> condition_to_deck_params()의 키.
# 각 패밀리는 deck에서 <name>1, <name>2 두 번 나온다.
PARAM_FAMILIES = [
    (r"VTMSKEW_PU\d",  "VTMSKEW_PU"),
    (r"VTMSKEW_PG\d",  "VTMSKEW_PG"),
    (r"VTMSKEW_PD\d",  "VTMSKEW_PD"),
    (r"VTSLSKEW_PU\d", "VTSLSKEW_PU"),
    (r"VTSLSKEW_PG\d", "VTSLSKEW_PG"),
    (r"VTSLSKEW_PD\d", "VTSLSKEW_PD"),
    (r"MOMSKEW_PU\d",  "MOMSKEW_PU"),
    (r"MOMSKEW_PG\d",  "MOMSKEW_PG"),
    (r"MOMSKEW_PD\d",  "MOMSKEW_PD"),
]

# deck의 Vth skew 단위: 'V'면 core의 mV 값을 /1000 해서 기록, 'mV'면 그대로.
# (사내 기존 코드가 BOUNDS를 V 단위(+-0.06)로 두고 그대로 기록했으므로 'V'.)
VTH_UNIT = "V"

# 한 패밀리가 deck에 몇 번 나와야 하는지 (PU1/PU2 -> 2).
# 개수가 다르면 잘못된 reference deck이므로 즉시 중단한다.
EXPECTED_OCCURRENCES = 2


def condition_to_deck_params(rec: dict) -> dict:
    """Map a core record to deck .param values (per device family).

    Vth shift (mV):   PG = cn + sk,  PD = cn - sk,  PU = pu
    Local sigma:      PG = l_com + l_sk,  PD = l_com - l_sk,  PU = lpu
    Mobility:         PG = m_com + m_sk,  PD = m_com - m_sk,  PU = mpu
    Stage A: no sk/loc/mom -> PG=PD=cn, ratios 1.0.  Stage B: no loc/mom.
    """
    cn = rec["cn"]; pu = rec["pu"]
    sk = rec.get("sk", 0)
    l_com, l_sk = rec.get("l_com", 1.0), rec.get("l_sk", 0.0)
    m_com, m_sk = rec.get("m_com", 1.0), rec.get("m_sk", 0.0)
    return {
        "VTMSKEW_PG": cn + sk,
        "VTMSKEW_PD": cn - sk,
        "VTMSKEW_PU": pu,
        "VTSLSKEW_PG": l_com + l_sk,
        "VTSLSKEW_PD": l_com - l_sk,
        "VTSLSKEW_PU": rec.get("lpu", 1.0),
        "MOMSKEW_PG": m_com + m_sk,
        "MOMSKEW_PD": m_com - m_sk,
        "MOMSKEW_PU": rec.get("mpu", 1.0),
        "VOP": rec["vop"],
    }


def deck_param_strings(rec: dict) -> dict:
    """치환할 문자열 값. Vth는 VTH_UNIT에 맞게 변환, 전부 소수 6자리.

    reference deck이 Vop별로 이미 나뉘어 있으므로 VOP은 치환하지 않는다.
    """
    scale = 1e-3 if VTH_UNIT.upper() == "V" else 1.0
    out = {}
    for k, v in condition_to_deck_params(rec).items():
        if k == "VOP":
            continue
        out[k] = f"{v * scale:.6f}" if k.startswith("VTMSKEW") else f"{v:.6f}"
    return out


def replace_params(text: str, values: dict, src_name: str) -> str:
    """reference deck의 각 파라미터 괄호 안 값을 조건값으로 치환.

    '(A) + B' 에서 A만 바뀌고 '+ B'는 보존된다.
    매치 개수가 EXPECTED_OCCURRENCES와 다르면 즉시 중단 (조용한 오염 방지).
    """
    for name_pat, key in PARAM_FAMILIES:
        val = values[key]
        pat = PARAM_PATTERN.format(name=name_pat)
        text, n = re.subn(pat, lambda m, v=val: m.group(1) + v + m.group(2),
                          text, flags=re.IGNORECASE | re.MULTILINE)
        if n != EXPECTED_OCCURRENCES:
            raise RuntimeError(
                f"[{src_name}] '{name_pat}' matched {n} time(s), expected "
                f"{EXPECTED_OCCURRENCES}. reference deck 문법 또는 "
                f"PARAM_PATTERN을 확인할 것 — 조용히 넘어가면 조건이 틀어짐.")
    return text


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def find_reference_decks(metric: str, folder: Path) -> dict:
    """Vop -> reference deck 경로. 각 Vop당 정확히 1개여야 한다."""
    refs = {}
    for vop in VOPS:
        pat = REF_DECK_GLOB.format(metric=metric, prefix=DECK_PREFIX, vop=vop)
        hits = sorted(folder.glob(pat))
        if len(hits) != 1:
            raise FileNotFoundError(
                f"Vop={vop}V reference deck: 패턴 '{pat}' 매치 {len(hits)}개 "
                f"(정확히 1개 필요). 폴더={folder.resolve()}")
        refs[vop] = hits[0]
    return refs


def detect_metric(folder: Path) -> str:
    """폴더의 reference deck 파일명에서 metric 자동 감지."""
    found = [m for m in ("snmr", "vtrip")
             if list(folder.glob(f"*{m}*{DECK_PREFIX}-1_*"))]
    if len(found) != 1:
        raise RuntimeError(
            f"metric 자동 감지 실패 (발견: {found or '없음'}). "
            f"--metric snmr|vtrip 을 명시할 것.")
    return found[0]


def selftest() -> None:
    """이식 검증용 fingerprint. 모델 측과 값이 일치해야 한다."""
    cols, cond = generate_conditions("D", 16, seed=42)
    print(f"inhouse_deck_gen v{VERSION} selftest")
    print(f"  D columns : {cols}")
    print(f"  D[0] (n=16, seed=42): {cond[0].tolist()}")
    for metric, seed in SEEDS.items():
        _, c = generate_conditions(STAGE, N_COND, seed, metric, METHOD)
        print(f"  {metric:5s} (n={N_COND}, seed={seed}) cond[0]: {c[0].tolist()}")
        print(f"  {metric:5s} checksum: {float(c.sum()):.6f}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="in-house deck generator (single portable file)")
    ap.add_argument("--metric", choices=["snmr", "vtrip"], default=None,
                    help="생략 시 폴더의 reference deck에서 자동 감지")
    ap.add_argument("--n_cond", type=int, default=N_COND)
    ap.add_argument("--seed", type=int, default=None,
                    help="생략 시 metric별 기본값 (snmr=2027, vtrip=2028)")
    ap.add_argument("--out", default=None, help="출력 폴더 (기본 OUT_DIR)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Vop당 앞 N개 조건만 생성 (스모크 테스트용)")
    ap.add_argument("--selftest", action="store_true",
                    help="조건 fingerprint만 출력 (deck 생성 안 함)")
    ap.add_argument("--preview", action="store_true",
                    help="첫 조건의 치환 전/후 .param 라인만 출력 (파일 안 씀). "
                         "본 실행 전에 deck 문법이 맞는지 눈으로 확인할 것.")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    here = Path(".")
    metric = args.metric or detect_metric(here)
    seed = args.seed if args.seed is not None else SEEDS[metric]
    out_dir = Path(args.out or OUT_DIR.format(metric=metric))

    refs = find_reference_decks(metric, here)
    ref_text = {v: _read_text(p) for v, p in refs.items()}

    print(f"inhouse_deck_gen v{VERSION}: stage={STAGE} metric={metric} "
          f"n_cond={args.n_cond} seed={seed} method={METHOD}")
    for v, p in refs.items():
        print(f"  ref {v}V: {p.name}")

    if args.preview:
        rec = next(iter(iter_decks(STAGE, args.n_cond, VOPS[:1], seed, metric,
                                   METHOD, DECK_PREFIX, START)))
        src = refs[VOPS[0]]
        before = ref_text[VOPS[0]]
        after = replace_params(before, deck_param_strings(rec), src.name)
        print(f"\n--- preview: {src.name} -> {DECK_PREFIX}-{rec['deck_no']} "
              f"(vop={rec['vop']}) ---")
        print(f"  condition: " + ", ".join(
            f"{c}={rec[c]}" for c in STAGE_COLUMNS[STAGE]))
        keys = tuple(k for _, k in PARAM_FAMILIES)
        for b, a in zip(before.splitlines(), after.splitlines()):
            if b != a:
                print(f"  BEFORE | {b.strip()}")
                print(f"  AFTER  | {a.strip()}")
        n_changed = sum(1 for b, a in zip(before.splitlines(), after.splitlines())
                        if b != a)
        print(f"  changed lines: {n_changed} (expect "
              f"{len(PARAM_FAMILIES) * EXPECTED_OCCURRENCES})")
        print("\n위 AFTER 라인의 문법이 정상이면 --limit 3 으로 스모크 실행할 것.")
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    # deck 생성 + 매핑 CSV (조건은 모델 측이 재생성하므로 CSV는 사내 QC용)
    cols = STAGE_COLUMNS[STAGE]
    map_path = out_dir / f"condition_mapping_{metric}_seed{seed}.csv"
    n_written = 0
    with open(map_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["deck_file", "deck_no", "vop"] + cols)
        for rec in iter_decks(STAGE, args.n_cond, VOPS, seed, metric, METHOD,
                              DECK_PREFIX, START):
            if args.limit is not None and rec["deck_no"] > args.limit:
                continue
            vop = rec["vop"]
            src = refs[vop]
            new_name = re.sub(rf"{DECK_PREFIX}-\d+", rec["deck_id"],
                              src.name, count=1)
            text = replace_params(ref_text[vop], deck_param_strings(rec),
                                  src.name)
            (out_dir / new_name).write_text(text, encoding="utf-8")
            writer.writerow([new_name, rec["deck_no"], vop]
                            + [rec[c] for c in cols])
            n_written += 1

    n_cond_eff = args.limit if args.limit is not None else args.n_cond
    print(f"generated {n_written} decks "
          f"({n_cond_eff} conditions x {len(VOPS)} Vop) -> {out_dir.resolve()}")
    print(f"mapping: {map_path.name}  (사내 QC용 — 반출 불필요, "
          f"모델 측은 seed로 동일 조건을 재생성)")


if __name__ == "__main__":
    main()
