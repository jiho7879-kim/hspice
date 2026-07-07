# HSPICE Sim Scope — 남은 Phase의 시뮬 범위 확정 (시간 절약용)

> 작성일: 2026-07-07
> 목적: 어떤 조건(온도/Vop/PVTA/변동)을 **얼마나** 돌려야 하는지 단계별로 확정해
> 불필요한 sim을 줄인다. 선행: `phase2_to_paper_plan.md`, `deck_generation_plan.md`
> (후자는 온도 5레벨 등 stale — 본 문서가 상위).
> 핵심 원칙: **지금 검증된 파이프라인은 3D(cn,pu,Vop)+4D(assist)까지**. 검증 안 된
> 차원(σL/σG/mobility)은 지금 돌리지 않는다. 조기 Gate로 재작업을 막는다.

---

## 0. 한 줄 요약

**1단계는 SNMR-only @ 125°C, PVTA 200쌍 × Vop 6레벨 = 1,200 sim.**
σL/σG/mobility/assist/Vtrip은 전부 나중. 온도도 1개. 이게 최대 시간 절약.

---

## 1. 조건별 범위 (무엇을, 왜, 얼마나)

| 조건 | 기호 | 범위 / 레벨 | 지금 필수 | 이유 / 비고 |
|------|------|-------------|:--------:|-------------|
| NMOS Vth shift (PG=PD) | common_N | −60 ~ +60 mV | ✅ | 3σ global corner. FSG 사분면 집중 sampling |
| PMOS Vth shift | PU | −60 ~ +60 mV | ✅ | common_N과 함께 **200쌍 stratified Sobol** |
| 공급 전압 | **Vop** | 0.4, 0.5, 0.6, 0.7, 0.8, 0.9 V (**6레벨 grid**) | ✅ | Vmin = z-crossing 보간에 필수. 연속 sweep 아니라 **고정 6레벨** (조건마다 같은 Vop여야 보간 가능) |
| 온도 | Temp | **125°C 단일** | ✅ (SNMR) | SNMR worst = hot. Vtrip 할 때만 −40°C 추가 |
| 워드라인 assist | Vwl | Vop × {0.90…1.00}, 5레벨 | ⬜ 2단계 | 4D. **3D Gate 통과 후.** WLUD=Vwl/Vop |
| Local variation | σL_mult | nominal = 1 **고정** | ❌ Phase 4 | 지금 안 돌림 (파이프라인 미검증 차원) |
| Global variation | σG_mult | nominal = 1 **고정** | ❌ Phase 4 | 〃 |
| Mobility | mob_mult | nominal = 1 **고정** | ❌ Phase 4 | 〃 |

**단위/규칙 주의:**
- PG=PD 동일 shift 가정(common_N 하나). PG≠PD skew는 별도 확장(Phase 4).
- deck의 PU1=PU2, PG1=PG2, PD1=PD2 (동일값). 파서가 collapse.
- MC 로컬 mismatch는 각 sim의 `.dc ... sweep monte=N` 안에 있음 (조건은 global shift).

---

## 2. 단계별 Sim 계획

### Stage A — 최소 Gate (3D SNMR) ★ 지금 이것부터

```
조건:  PVTA 200쌍 (stratified: FSG 35% / SFG 25% / 나머지 40%)
Vop:   6레벨 (0.4~0.9)
Temp:  125°C 단일
변동:  σL/σG/mob = nominal(1), assist 없음(Vwl=Vop)
--------------------------------------------------------
Sim 수: 200 × 6 = 1,200
결과:   조건당 SNMR (mu, sigma) — MC 분포의 avg/std
검증점: 4 global corner(FSG/SFG/FFG/SSG) + hold-out 20쌍 (별도, 고MC)
```

**목적**: 실데이터에서 GP surrogate + physics layer가 toy만큼 동작하는지 Gate.
**Go 기준** (phase2_to_paper_plan §3.6): mu R²>0.95, contour Hausdorff < 15mV,
corner |Vmin_pred − Vmin_MC| < 15mV, gradient 방향 물리적.
**이 단계에서 절대 안 돌리는 것**: σL/σG/mobility sweep, Vwl assist, Vtrip, 다른 온도.

### Stage B — Assist (4D) : Gate 통과 & assist 필요 시

```
+ Vwl: Vop × {0.90, 0.925, 0.95, 0.975, 1.00}  (5레벨)
--------------------------------------------------------
Sim 수: 200 × 6 × 5 = 6,000  (Stage A 재사용분 제외하면 +4,800)
결과:   조건×Vwl 당 SNMR (mu, sigma)
```
**목적**: inverse assist(required-WLUD) 역추정 실데이터 검증.

### Stage C — Write margin (Vtrip) : write 제약 필요 시

```
+ Temp: −40°C (cold, Vtrip worst)   ← SNMR은 125 유지
Vtrip:  left/right 별도 출력 (a0=bwrm_1, a1=bwrm_2), 조건당 2 파일
--------------------------------------------------------
Sim 수: SNMR 1,200 @125  +  Vtrip 1,200 @−40  (assist 포함 시 각 ×5)
결과:   SNMR(mu,sigma) + Vtrip min(L,R)의 (mu, sigma/median)
Vmin_cell = max(Vmin_read, Vmin_write)   ← 코드가 계산 (sim 아님)
```
**주의**: write 파일럿(20쌍 × 2온도)으로 hot-read/cold-write 지배 가정 먼저 확인
(deck plan Stage 3 pilot). 지배 성립하면 위처럼 worst 온도만.

### Stage D — Full PVTA (Phase 4) : 논문 확장

```
Sobol DOE over: common_N, PU, Vwl, σL_mult, σG_mult, mob_mult (+Temp)
Vop만 6레벨 grid 유지 (Vmin 보간)
--------------------------------------------------------
Sim 수: ~3,000 Sobol 조건 × 6 Vop = 18,000
선행:   500-조건 파일럿으로 Sobol sensitivity → Vmin 분산 90% 설명하는
        top-k 차원만 남겨 full run 차원 축소 (시간 절약)
```

---

## 3. 조건당 MC 수 (정확도 vs 시간)

노이즈 플로어: δVmin ≈ (Z_target/√(2·N_MC)) / (dZ/dVop). Z≈6.6, dZ/dVop는
Stage A에서 실측. 목표 해상도(스펙 10-15mV)에 맞춰:

| 용도 | N_MC | δVmin(1σ, 조건당) | 비고 |
|------|------|-------------------|------|
| 훈련 surface | 2,000 | ~12 mV | GP가 조건 간 평활화로 흡수 (noise-aware GP) |
| 검증 기준점 (corner 4 + hold-out 20) | 10,000 | ~5 mV | 판정 임계값과 같은 자릿수 |

- 사내 sim이 빠르면 훈련도 5,000까지 올려도 됨 (noise-aware GP가 SEM으로 가중).
- **조건당 MC 수(n_mc)를 결과에 기록** → noise-aware GP가 자동 활용.

---

## 4. 시간 절약 요약 (지금 안 돌리는 것)

| 항목 | 원 계획(stale) | 본 계획 | 절약 |
|------|---------------|---------|------|
| 온도 | 5레벨 (−40/25/85/125/150) | **1레벨 (125)** | 5× |
| local/global/mobility | sweep | **nominal 고정** | 차원 3개 제거 |
| assist(Vwl) | 항상 포함 | **Gate 후에만** | 5× (3D 단계) |
| 초기 sim 수 | 6,000~18,000 | **1,200** | 5~15× |

→ **Stage A 1,200 sim으로 시작**해 파이프라인부터 확정하고, 통과분만 확장.

---

## 5. 사용자 결정 필요 (착수 전)

1. **시작 범위**: Stage A(SNMR-only @125)로 시작 vs 처음부터 Vtrip(+−40) 포함?
   - 권고: **Stage A 먼저** (재작업 리스크 최소).
2. **Vop 6레벨 유지 여부**: 실데이터 z-curve가 0.4~0.9 안에서 Z_target을 crossing하는지
   Stage A 첫 배치(예: TT + 4 corner)로 확인 → crossing이 좁으면 레벨 재배치.
3. **온도**: SNMR만이면 125 단일 확정. Vtrip 추가 시 −40 1개만(중간 온도 불필요).

---

## 6b. Full Job Manifest — 미리 큐에 올릴 전체 job (2026-07-07 확정)

> 결정: Stage A로 **시작(판정)**하되, sim이 빠르므로 job은 미리 올려둔다.
> **원칙: submit은 한 번에, 판정은 A→B→C 순차.** A가 No-Go면 B/C 결과는 버린다
> (낭비를 감수하고 큐 대기시간을 없애는 트레이드오프 — 사용자 선택).
> Stage D만은 예외: 파일럿 먼저 (아래 이유).

**공통 축**: PVTA 200쌍 (stratified Sobol, seed 고정) × Vop 6레벨(0.4~0.9).
파일명은 `cond_{id:06d}` 식별자만; 조건은 deck에서 파싱하므로 파일명에 인코딩 불필요.

| # | Job 그룹 | 조건 조합 | 온도 | Sim 수 | MC | 파이프라인 | 미리 올림? |
|---|---------|-----------|------|-------:|----:|-----------|:---------:|
| A | SNMR read (Gate) | 200 × 6 Vop, Vwl=Vop(=no assist), 변동 nominal | 125 | **1,200** | 2,000 | ✅ 3D 검증됨 | ✅ |
| A+ | 검증 기준점 | (4 corner + 20 hold-out) × 6 Vop, 고MC | 125 | 144 | **10,000** | 검증용 | ✅ |
| B | SNMR assist | 200 × 6 × Vwl{0.90,0.925,0.95,0.975} | 125 | **4,800** | 2,000 | ✅ 4D 검증됨 | ✅ |
| C | Vtrip write margin | 200 × 6 × Vwl{0.90…1.00} (5), write 조건, a0/a1 출력 | **−40** | **6,000** | 2,000 | write (신규) | △ 선택 |
| D | Full PVTA Sobol | 3,000 Sobol(cn,pu,Vwl,σL,σG,mob) × 6 Vop | 125 | **18,000** | 5,000 | ❌ 미검증 | ❌ 파일럿 먼저 |

**미리 올릴 권고 세트 = A + A+ + B ( = 약 6,150 jobs )**
- 전부 이미 검증된 3D/4D 파이프라인. Gate 통과 시 재sim 없이 바로 assist까지 감.
- Vwl=Vop 케이스가 A(no-assist)와 B(assist)의 공통 경계 — 중복 없이 A는 Vwl=Vop만.

**Stage C (Vtrip, +6,000)**: write margin이 이번 논문 범위에 들어가면 같이 올림.
단 **write 파일럿(20쌍 × 2온도)** 으로 hot-read/cold-write 지배부터 확인 후 full C.
Vtrip은 조건당 a0(bwrm_1)/a1(bwrm_2) 두 출력 → `vtrip_min_stats`로 병합.

**Stage D (Full PVTA, +18,000)**: **미리 올리지 말 것.** 이유:
1. σL/σG/mobility는 GP 파이프라인에서 아직 미검증 차원 (Phase 4).
2. **Sobol sensitivity 파일럿(500 sim)** 으로 Vmin 분산 90%를 설명하는 top-k 차원을
   먼저 식별 → full run을 top-k로 축소. 미리 18,000을 다 올리면 버려질 차원에
   sim 낭비. 파일럿 500 → 결과 보고 → 축소된 full.

**총계**: 지금 올릴 것 A+A++B ≈ **6,150**. C 포함 시 ≈ 12,150. D는 파일럿 500 후 결정.

**Deck 생성**: `scripts/gen_hspice.py` 확장 (stage/Vwl/Temp 파라미터). Stage A는
현재 스크립트로 바로 가능(`--n_cond 200`). B/C/D는 CLI 인자 추가 필요.

---

## 6. 이 문서와 데이터 파이프라인 연결

- 조건은 `.in` deck에서 자동 파싱(`primesim_io.parse_in_deck`) → 손 전사 불필요.
- 결과는 `.mt0`에서 파싱(`mc_stats`, `vtrip_min_stats`) → 조건과 merge해 CSV 1개.
- 그 CSV = 손 전사 표준 형식 = 학습 입력(`hspice_io.parse_manual_csv`).
- **CSV에는 raw 통계만**(mu_SNMR, sigma_SNMR, vtrip_min_*, n_mc). z-score/Vmin은
  학습·physical layer가 계산 (지표 정의 바뀌어도 재전사 불필요).
