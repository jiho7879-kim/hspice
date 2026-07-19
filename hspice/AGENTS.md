# AGENTS.md — HSPICE domain

HSPICE circuit simulation domain: reference guides, raw data, PDK integration.

---

## Structure

```
hspice/
├── docs/    # 14 reference guides (YAML frontmatter)
└── raw/     # Raw HSPICE output metadata
```

---

## HSPICE docs (14 guides)

All guides follow `hspice_{topic}.md` naming with YAML frontmatter:
- `title`, `subtitle`, `version: "1.0"`, `date`, `description`, `tags`, `language: "HSPICE"`, `keywords`

| Guide | Lines | Topic |
|-------|-------|-------|
| hspice_naming_guide.md | 667 | Device/measurement naming conventions |
| hspice_modularization_guide.md | 1096 | Include hierarchy (9 layers) |
| hspice_sram_cell_char.md | 454 | SNM, Iread, N-curve, Vtrip |
| hspice_convergence_options.md | ~300 | Convergence troubleshooting |
| hspice_finfet_guide.md | ~300 | FinFET-specific modeling |
| hspice_model_pdk_integration.md | ~250 | PDK model integration |
| hspice_output_parsing.md | ~200 | .mt0/.st0/.tr0 parsing |
| hspice_timing_analysis.md | ~200 | Timing analysis methodology |
| hspice_power_analysis.md | ~200 | Power analysis methodology |
| hspice_ac_noise_analysis.md | ~200 | AC/noise analysis |
| hspice_optimization_guide.md | ~200 | HSPICE optimization techniques |
| hspice_ut_char.md | ~200 | Unit transistor characterization |
| hspice_yield_workbench.md | ~200 | Yield workbench guide |
| hspice_miniarray_peri_guide.md | ~200 | Mini-array periphery guide |

---

## Key conventions from docs

### Naming (hspice_naming_guide.md)
```
[TYPE]_[FUNCTION]_[QUALIFIER]_[INSTANCE]
```
- Device: `M{P/N}{U/D/G}{1/2}` (MPU1, MPD1, MPG1)
- Measurement: `{MEASURAND}[_QUALIFIER][_CONDITION][_VARIANT]`
- Prefix: V=voltage, I=current, R=resistance, T=time, DV=voltage diff

**Banned**: bare device numbers (M1), hyphens (BL-bar), camelCase, leading digits, embedded units.

### Modularization (hspice_modularization_guide.md)
9-layer include hierarchy:
1. Setup (.OPTIONS, .TEMP)
2. Config (.PARAM user values)
3. Models (.LIB, .MODEL)
4. Common (math helpers)
5. Circuits (.SUBCKT)
6. Specs (.MEASURE)
7. Testbench (instances)
8. Analysis (.TRAN, .DC)
9. Output (.PROBE)

**Rule**: Config files contain ONLY `.PARAM` — no subcircuits, no instances.

### SRAM cell (hspice_sram_cell_char.md)
- Standard 6T dimensions: PU:PD:PG = 1:2:1.5
- Port order: `BL BLB WL VDD VSS`
- Key measurements: IREAD, RSNM, HSNM, VTRIP1, SNM_SIDE

---

## Simulation commands

```bash
hspice64 -i deck.sp -o output_prefix     # Synopsys HSPICE
ngspice.exe deck.sp                       # ngspice (bin/ngspice.exe on Windows)
```

---

## Bridge to Python

- `python/src/hspice_io.py` — deck rendering, .mt0 parsing
- `python/src/primesim_io.py` — PrimeSim wrapped .mt0 parsing
- `python/templates/` — Mustache templates for deck generation
- `python/src/condition_gen.py` — FROZEN CORE condition generator
