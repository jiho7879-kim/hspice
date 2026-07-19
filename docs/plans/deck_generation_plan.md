# Deck Generation Plan — Stage-by-Stage Dimensional Expansion

## CSV Column Convention (all stages)

| Column | Unit | Type | Required | Description |
|--------|------|------|----------|-------------|
| `common_N_shift` | mV | X | ✅ | NMOS Vth shift |
| `PU_shift` | mV | X | ✅ | PMOS Vth shift |
| `Vop` | V | X | ✅ | Supply voltage |
| `Vwl` | V | X | Stage 2+ | Wordline voltage |
| `Temp` | °C | X | Stage 3+ | Temperature |
| `W` | norm | X | Stage 4+ | Transistor width |
| `sigmaL_mult` | norm | X | Stage 4+ | Length variation multiplier |
| `sigmaG` | norm | X | Stage 4+ | Global variation |
| `mu_mobility_mult` | norm | X | Stage 4+ | Mobility multiplier |
| `mu_SNMR` | V | y | ✅ | SNMR mean (from MC) |
| `sigma_SNMR` | V | y | ✅ | SNMR std (from MC) |
| `mu_Vtrip` | V | y | Stage 3+ | Vtrip mean (from MC) |
| `sigma_Vtrip` | V | y | Stage 3+ | Vtrip std (from MC) |

---

## Stage 1: Toy 3D (cn, pu, Vop) — 현재

**Purpose**: Baseline GP validation with analytic ground truth.

### Parameter space

| Variable | Range | Levels | Type |
|----------|-------|--------|------|
| common_N | -60 ~ +60 mV | Sobol 200 | Sobol |
| PU | -60 ~ +60 mV | Sobol 200 | Sobol |
| Vop | 0.4, 0.5, 0.6, 0.7, 0.8, 0.9 V | 6 | Grid |

### Deck count
```
N_cond = 200
Vop    = 6
Total  = 1,200 decks
MC_RUNS = 2,000
```

### Template variables needed
```
{{ COMMON_N_SHIFT }}  → common_N_shift
{{ PU_SHIFT }}        → PU_shift
{{ VOP }}             → Vop
{{ TEMP }}            → 125.0 (fixed hot)
{{ OUTPUT_PREFIX }}
{{ MC_RUNS }}         → 2000
```

### Expected simulation time
~1.5 hours

---

## Stage 2: 4D +Vwl (cn, pu, Vop, Vwl)

**Purpose**: Validate WL underdrive as controllable assist; train GP on 4D.

### Key physics
- WL underdrive → PG strength ↓ → read stability ↑ → SNMR ↑
- Vwl ≈ Vop × WLUD, where WLUD ∈ [0.8, 1.0]
- At same Vop, lower Vwl = stronger assist = lower Vmin

### New template variable
```
{{ VWL }}  → Vwl voltage (V)
```

### Parameter space

| Variable | Range | Levels | Type |
|----------|-------|--------|------|
| common_N | -60 ~ +60 mV | Sobol 200 | Sobol |
| PU | -60 ~ +60 mV | Sobol 200 | Sobol |
| Vop | 0.4 ~ 0.9 V | 6 | Grid |
| Vwl | Vop × [0.80, 0.85, 0.90, 0.95, 1.00] | 5 per Vop | Grid |

### Vwl table (Vwl = Vop × WLUD)

| Vop | WLUD=0.80 | WLUD=0.85 | WLUD=0.90 | WLUD=0.95 | WLUD=1.00 |
|-----|-----------|-----------|-----------|-----------|-----------|
| 0.4 | 0.320 | 0.340 | 0.360 | 0.380 | 0.400 |
| 0.5 | 0.400 | 0.425 | 0.450 | 0.475 | 0.500 |
| 0.6 | 0.480 | 0.510 | 0.540 | 0.570 | 0.600 |
| 0.7 | 0.560 | 0.595 | 0.630 | 0.665 | 0.700 |
| 0.8 | 0.640 | 0.680 | 0.720 | 0.760 | 0.800 |
| 0.9 | 0.720 | 0.765 | 0.810 | 0.855 | 0.900 |

Note: Vwl ≤ Vop (WLUD ≤ 1.0) ensures wordline is always at or below supply.

### Deck count
```
N_cond = 200
Vop    = 6
Vwl    = 5
Total  = 6,000 decks
MC_RUNS = 2,000
```

### Expected simulation time
~8 hours (over-night)

### CSV format
```
common_N_shift, PU_shift, Vop, Vwl, mu_SNMR, sigma_SNMR
```

### Code changes required
- `src/utils.py`: Add `VWL_COL = 3`
- `src/models.py`: Update `AdditiveGPModel` kernel — `active_dims=[2, 3]` for operating group
- `src/physics.py`: `generate_probe_points`, `generate_corner_anchor_data` → `n_extra` for Vwl
- `src/physics_layer.py`: `compute_vmin_on_grid` → accept Vwl parameter
- `src/hspice_io.py`: `render_deck` → add Vwl; CSV parser → add Vwl column mapping
- **New**: `estimate_required_assist()` — inverse estimation

---

## Stage 3: 5D +Temp (worst-temp optimization)

**Purpose**: Validate temperature-aware GP; exploit SNMR-hot / Vtrip-cold dominance.

### Key physics
- **Hot (125°C)**: PG leakage↑ → SNMR worst → **Vmin = SNMR_Vmin**
- **Cold (-40°C)**: PMOS drive↑ → Vtrip worst → **Vmin = Vtrip_Vmin**
- Room (25°C): bounded by hot/cold → can skip

### New measurements needed
- `.MEASURE SNMR` (read noise margin, already doing)
- `.MEASURE Vtrip` (inverter trip point) — **new**
- Vmin = **max(SNMR_Vmin, Vtrip_Vmin)**

### Pilot study (before full run)

Run 20 conditions × 3 temps to verify dominance assumption:

```
각 quadrant별 5 조건 (= 20 total)
  × 3 temps (hot, room, cold)
  × 6 Vop × 5 Vwl = 90 decks per condition
Total pilot: 1,800 decks
→ ~3h (MC_RUNS=500, screening quality)
```

Pilot pass criteria:
- All 20 conditions: SNMR_Vmin(hot) > SNMR_Vmin(cold)
- All 20 conditions: Vtrip_Vmin(cold) > Vtrip_Vmin(hot)
- Room Vmin ≤ max(hot_SNMR, cold_Vtrip) ∀ conditions

### Full run (after pilot passes)

```
N_cond = 500
Vop    = 6
Vwl    = 5
Temp   = 1 worst per metric
Total  = 500 × 6 × 5 × 1 = 15,000 decks (worst temp only)
MC_RUNS = 5,000
```

### Min vs max operation nuance

SNMR은 높을수록 좋고, Vtrip은 낮을수록 좋습니다 (read 안정성 측면에서).

However, `Vmin = f⁻¹(Z_target)` 계산에서:

- **SNMR**: mu_SNMR(Vop) ↑ → Z = mu/sigma ↑ → Vmin ↓ (높을수록 좋음)
- **Vtrip**: mu_Vtrip(Vop) ↑ (trip point high) → ... 

Wait — Vtrip의 의미를 정확히 해야 합니다.

Read 동작에서:
- BL, BLB는 Vop으로 precharge
- WL = Vwl로 turn on
- Cell에 저장된 값에 따라 BL/BLB 중 하나가 discharge 시작
- Vtrip = inverter trip point — 이 값이 너무 낮으면 read disturbance에脆弱

Vtrip에 대한 Z-score와 Vmin 정의는 SNMR과 다른 방향일 수 있습니다. **이 부분은 논의 필요**.

### CSV format
```
common_N_shift, PU_shift, Vop, Vwl, Temp, mu_SNMR, sigma_SNMR, mu_Vtrip, sigma_Vtrip
```

### Expected simulation time
Full run: ~20-25 hours (over-night × 2)
Includes both SNMR-hot + Vtrip-cold measurements in same deck.

### 코드 변경
- `src/utils.py`: Add `TEMP_COL = 4`
- `src/data.py`: `build_dataset` → accept temp as optional dim
- `src/physics_layer.py`: Vmin = max(SNMR_Vmin, Vtrip_Vmin) logic
- `scripts/gen_hspice.py`: Temp-aware deck generation

---

## Stage 4: Full 8D (Sobol DOE) — 논문

**Purpose**: Full process variation + operating condition GP.

### Parameter space (Sobol design)

| Variable | Range | Levels | Sampling |
|----------|-------|--------|----------|
| common_N | -60 ~ +60 mV | — | Sobol |
| PU | -60 ~ +60 mV | — | Sobol |
| Vop | 0.4 ~ 0.9 V | 6 | **Grid** (Vmin 계산 필수) |
| Vwl | Vop × [0.80, 1.00] | — | Sobol |
| W | 0.8 ~ 1.2 (norm) | — | Sobol |
| σL_mult | 0.5 ~ 2.0 (norm) | — | Sobol |
| σG | 0.0 ~ 0.05 | — | Sobol |
| μ_mobility | 0.7 ~ 1.3 (norm) | — | Sobol |
| Temp | -40 ~ 125 °C | — | Sobol |

### Vop은 Grid로 남기는 이유

Vmin = f⁻¹(Z_target) 계산은 discrete Vop에서의 Z값을 보간합니다. 따라서:
- Vop이 grid가 아니면 동일 Vop 값이 중복되지 않아 **각 condition에서 Vmin 계산 불가**
- Sobol로 뽑은 Vop 값이 condition마다 달라지면 Vmin 보간을 할 수 없음

해결책: **Vop = 6 fixed levels, 나머지 7D를 Sobol로 joint sampling**

### Deck count
```
N_cond (Sobol over 7D) = 3,000
Vop (grid)             = 6
Total                  = 18,000 decks
MC_RUNS                = 5,000
```

### Expected simulation time
~25-30 hours (farm parallel)

### CSV format
```
common_N_shift, PU_shift, Vop, Vwl, W, sigmaL_mult, sigmaG, mu_mobility_mult, Temp, mu_SNMR, sigma_SNMR, mu_Vtrip, sigma_Vtrip
```

### 코드 변경
- `src/data.py`: Sobol-based multi-dimensional `build_dataset_sobol()`
- `src/utils.py`: Full 8D constants
- `src/models.py`: `AdditiveGPModel` → grouped kernel definition (operating, device, process, temperature)
- `scripts/gen_hspice.py`: Sobol DOE support

---

## Summary Table

| Stage | Dim | Decks | MC_RUNS | Total MC | 시간 | 비고 |
|-------|-----|-------|---------|----------|------|------|
| **1: Toy 3D** | 3 | 1,200 | 2,000 | 2.4M | 1.5h | ✅ current |
| **2: +Vwl (4D)** | 4 | 6,000 | 2,000 | 12M | 8h | 본 작업 |
| **3a: Pilot** | 5 | 1,800 | 500 | 0.9M | 3h | dominance 검증 |
| **3b: +Temp (5D)** | 5 | 15,000 | 5,000 | 75M | 25h | worst-temp 최적화 |
| **4: Full 8D** | 8 | 18,000 | 5,000 | 90M | 30h | Sobol DOE, farm |

## Template Variables Checklist

| Variable | Stage 1 | Stage 2 | Stage 3 | Stage 4 |
|----------|---------|---------|---------|---------|
| `{{ COMMON_N_SHIFT }}` | ✅ | ✅ | ✅ | ✅ |
| `{{ PU_SHIFT }}` | ✅ | ✅ | ✅ | ✅ |
| `{{ VOP }}` | ✅ | ✅ | ✅ | ✅ |
| `{{ TEMP }}` | ✅ (fix 125) | ✅ (fix 125) | ✅ | ✅ |
| `{{ VWL }}` | — | ✅ | ✅ | ✅ |
| `VTMSKEW_PU*` | ✅ (=PU_shift) | ✅ | ✅ | ✅ |
| `VTMSKEW_PG*` | ✅ (=cn_shift) | ✅ | ✅ | ✅ |
| `VTMSKEW_PD*` | ✅ (=cn_shift) | ✅ | ✅ | ✅ |
| `{{ MC_RUNS }}` | ✅ | ✅ | ✅ | ✅ |
| `{{ OUTPUT_PREFIX }}` | ✅ | ✅ | ✅ | ✅ |

## CSV Validation Checklist

Before loading into GP, verify for each CSV:
- [ ] All required columns present (per stage)
- [ ] No NaN in X columns
- [ ] mu_SNMR > 0 (read stability, 양수여야 정상)
- [ ] sigma_SNMR > 0
- [ ] Vwl ≤ Vop for all rows (WLUD constraint)
- [ ] N_rows = N_cond × N_Vop × N_Vwl × N_Temp
- [ ] Each (cn, pu) appears exactly N_Vop × N_Vwl × N_Temp times
