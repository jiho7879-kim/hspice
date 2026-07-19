# ngspice SRAM butterfly — integration status & next steps

> **STATUS 2026-07-06: ngspice track PAUSED by user decision** (toy 검증의 곁다리).
> 아래 "2026-07-06 verification findings"만 반영하고 코드 수정은 하지 않음.
> 재개 시 이 섹션부터 읽을 것.

## 2026-07-06 verification findings (읽고 나서 재개할 것)

이 세션에서 기존 pipeline의 두 가지 근본 결함을 **수치 검증으로 확정**했다 (코드는 미수정):

1. **SNM 추출 방법이 잘못됨** — `y1 = min |v1-v2|` (`.measure` 및
   `test_ngspice.py::compute_snm_from_data`)는 crossing 근처에서 ~0이 되는
   무의미한 값. 올바른 Seevinck는 **로브(eye)별 max |v1-v2| / sqrt(2), 두 로브의
   min** — 로브는 vdiff의 (pseudo-)crossing 사이 구간으로 제한해야 함 (구간 제한
   없이는 wing 영역이 오염). 원좌표계 최대 내접 정사각형 무차별 탐색과 0.4mV
   이내 일치 확인. 좌표 복원: `A=(v±u)/sqrt2, B=(v∓u)/sqrt2`.
   - 기존 "SNM ~7mV, 12x scale factor 필요, Vop 추세 역전, (cn,pu)에 flat"은
     모두 이 버그 + 아래 모델 카드 문제의 아티팩트.
   - Pseudo-crossing 주의: 안정점에서 두 곡선이 접선처럼 스쳐 sign change가
     grid에서 미검출될 수 있음 → |vdiff| 국소최소 < ~20mV도 crossing으로 처리.

2. **`14nm_HP.pm` 모델 카드가 SRAM 불능 상태** — 검증된 문제:
   - `xl = -9e-9` (추가된 shrink): L_GATE=20nm에서 **Leff = 7nm** → bulk BSIM4
     완전 붕괴 (인버터 이득 < 2.3)
   - PMOS `u0 = 0.0095` (NMOS의 1/4.2): 1-fin PU가 NMOS 누설도 못 이겨 출력
     high가 0.53V/0.8V로 붕괴. FinFET 시대 3:2:1 fin 사이징에는 균형 u0 필요
   - NMOS `toxe = 2.5e-9` (자신의 toxref=1.05e-9와 모순), `nfactor = 2.3`
     (SS~138mV/dec), 미스캘리브레이션된 igc/GIDL 파라미터
   - **수리 카드**: `templates/14nm_HP_sram.pm` 생성됨 (xl=0, PMOS u0=0.028,
     nfactor=1.25, NMOS toxe=1.05n, igcmod/igbmod=0, agidl=0, vth0 0.38/-0.36).
     수리 후: 인버터 이득 7.4~11.2, read disturb ~0.13V, butterfly 3-crossing 정상.
   - 수리 카드 + 올바른 추출로 얻은 기준값 (deterministic, 125C):
     TT@0.8V=126mV, Vop 추세 정상(62.6→129.8mV @ 0.4→0.9V),
     corner: FSG 78.8(최악)/FFG 100.0/SSG 144.3/SFG 162.6mV — 물리와 일치.

3. **기존 결론 정정**: "deterministic butterfly SNM은 global shift에 불변이라
   MC 없이는 (cn,pu) variation이 없다"는 이전 세션 결론은 아티팩트였음.
   올바른 설정에서는 deterministic SNM도 corner에 따라 79→163mV로 강하게 변함.
   단, **sigma_SNMR은 여전히 local mismatch MC 필요** (Vmin z-score의 분모).

4. **OSDI 불가**: 현재 `bin/ngspice_con.exe` (ngspice-46)는 OSDI 미컴파일
   (`pre_osdi`/`.osdi` 없음) → `templates/ptm_14nm/BSIMCMG.osdi` FinFET 경로는
   OSDI 지원 빌드로 교체 전까지 사용 불가.

재개 시 작업 순서: (a) 템플릿에 per-instance DVT 6개 파라미터 추가(전역 shift와
동일한 vsk 방식, subckt param으로 전달), (b) `model_card.pm` 이름으로 카드 선택
가능하게, (c) raw `.print v(u) v(v1) v(v2)` 3컬럼(단일 테이블)로 축소, (d) Python
eye-restricted Seevinck 추출을 test/gen 공용 모듈로, (e) MC: sigma_vt(1fin) 기준
1/sqrt(nfin) 스케일, N_MC~150-200이면 60cond×6Vop ≈ 10분 (@0.07s/run, 8 workers).

---

##  What was built

| File | Purpose | Status |
|------|---------|--------|
| `python/templates/sram_butterfly_ng.sp` | ngspice butterfly netlist template (Mustache `{{ }}` ) | ✅ Working |
| `python/scripts/test_ngspice.py` | Validation script (render → run → parse → SNM) | ✅ Working |
| `python/scripts/gen_ngspice_data.py` | Batch dataset generation via ThreadPoolExecutor | ✅ Working |

## Template design (key decisions)

### B-sources, not E-sources
ngspice-46 rejects `Ename … value={…}` for arbitrary expressions.  Use `Bname … V={…}` (behavioral source) with the same expression.

### `{-VOP}` not `-{VOP}`
`-{VOP}` expands to a space between minus sign and numeric value, causing a parse error.  Use `{-VOP}` to keep them adjacent.

### No inline `* comments` on `.param` lines
In SPICE, `*` starts a comment only at the beginning of a line.  `.param X = 0.0 * Volts` is parsed as `0.0 * Volts` (multiplication), not as a comment.

### Auxiliary B-sources for `.measure`
ngspice `.measure` does not accept `v(node1, node2)` (HSPICE syntax) or complex expressions in `MAX/MIN/WHEN` clauses.  Define auxiliary B-sources (`Bdiff vdiff …`, `Babs vabs …`) and use simple node voltages as targets.

### `.print` wraps to multiple tables
When a `.print` line lists >3 signal columns, ngspice splits output across multiple tables (each with `Index` header + dash separator).  The multi-table parser in `test_ngspice.py` handles this by merging on sweep index.

### `.wrdata` not supported
ngspice-46 does not implement `.wrdata`.  Batch mode requires at least one `.print`/`.plot`/`.fourier` line or it reports "no simulations run".

### `.print` data goes to stdout only without `-o`
When `-o logfile` is passed, `.print` output goes to the log file (not stdout).  Without `-o`, it goes to stdout.  The test script runs without `-o` and parses stdout directly.

## Current findings

### Deterministic butterfly SNM ≈ const across global Vth shifts
The butterfly method applies Vth shifts equally to both half-cells.  Since both curves shift symmetrically, the DC SNM (minimum |v1-v2| in the rotated frame) stays nearly constant regardless of common_N/PU variation.

**Implication**: The deterministic ngspice pipeline cannot produce the `mu_SNMR` variation that drives Vmin estimation in the GP surrogate — that variation comes from **local mismatch** (Monte Carlo), not from global corners.

### Estimated throughput
- Single simulation: ~0.07 s (DC sweep, 161 points, TT corner)
- Batch (36 runs, 4 workers): 0.9 s → 38.4 sim/s
- Full dataset (200 × 6 = 1200 runs): ≈ 31 s at 4 workers

### SNM magnitude
PD=3fin, PG=2fin, PU=1fin at Vop=0.8V, 125°C:
- Room temp (25°C): y1 ≈ 6.1 mV (3 crossings, xc1≈0, xc2≈0.294, xc3≈0.302)
- Hot (125°C): y1 ≈ 7.4 mV (3 crossings, xc1≈0, xc2≈0.254, xc3≈0.273)

These are below typical SRAM read SNM (50–300 mV) — the 14nm HP BSIM4 models or the cell sizing may need calibration, but the template itself is correct.

## Next steps

1. **MC mismatch analysis** — The real value of ngspice is running `.mc` with local mismatch (add `.param` for `agauss`/`aunif` variation on Vth).  This would require:
   - Per-instance Vth mismatch parameters (e.g., `AVT` model)
   - `.mc` analysis instead of `.dc` (or add `.dc` nested inside `.mc`)
   - Much longer run time (100–1000 samples × 0.07 s)

2. **gen_ngspice_data.py** currently uses deterministic SNM as `mu_SNMR` + empirical sigma.  This is useful for pipeline validation but will not match the GP's expectation of MC-derived (mu, sigma).

3. **Validation use** — The deterministic butterfly is best used as a **cross-check** against the `analytic_snmr` model at a few (cn, pu, Vop) points.
