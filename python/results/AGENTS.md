# AGENTS.md — Python results/

Output figures, ablation results, checkpoints, and experiment data.

---

## Directory structure

```
results/
├── ablation/              # 5-config physics ablation (20 .pth + metrics JSON)
├── budget_pareto/         # Budget vs accuracy Pareto (3600+ experiment records)
├── diagnostics/           # Multi-panel error diagnostics (5 PNGs)
├── gradient_inversion/    # Autograd inversion trajectories
├── legacy/toy/            # DEPRECATED — old toy model results
├── ngspice_stage1/        # SIDE TRACK: ngspice pipeline
├── stage1_3d/             # Active Stage 1: 3D GP
├── stage2_4d_wlud/        # Active Stage 2: 4D +WLUD
├── stage3_assist/         # Active Stage 3: Assist-active
├── stage4_real/           # Stage 4: Real HSPICE data
├── stage4_corner_retrain_contour/  # Per-corner retrain (contour)
├── stage4_corner_retrain_sep/      # Per-corner retrain (separated)
├── stage4_corner_verification/     # Corner verification
├── stageB_real/           # Stage B: Real data (4D+skew)
├── stageC_readwrite/      # Stage C: Read/write combined
├── fig_*.png              # Root-level paper figures (8 files)
└── *.png                  # Root-level paper figures
```

---

## File type distribution

| Extension | Count | Purpose |
|-----------|-------|---------|
| .png | 52 | Visual outputs — all figures |
| .pth | 28 | PyTorch model checkpoints |
| .json | 3 | Structured metrics/experiment results |
| .npz | 2 | NumPy compressed datasets |
| .md | 1 | Session handoff document |

---

## Checkpoint versioning convention

```
gp_{config}_{target}.pth       → Version 1 (original)
gp_{config}_{target}_v2.pth    → Version 2 (retrained)
```

**Config taxonomy**: baseline, mono, boundary, mono_boundary, all

**Naming evolution**:
- Legacy: `checkpoint.pth` (generic, overwritten)
- Active: `gp_{config}_{target}_v{n}.pth` (descriptive, versioned)
- Transitional: `checkpoint_plain.pth` (no physics constraint)

---

## Directory naming convention

| Era | Pattern | Example |
|-----|---------|---------|
| Legacy | `stage{N}_{dim}d_{feature}` | `stage2_4d_vwl` |
| Active pre-A | `stage{N}_{dim}d_{feature}` | `stage2_4d_wlud` |
| Active 4+ | `stage4_{purpose}` | `stage4_real` |
| Post-A | `stage{letter}_{purpose}` | `stageB_real` |

Side tracks get simulator prefix: `ngspice_stage1/`

---

## Anti-patterns

- **Do NOT commit** `*.tr0`, `*.mt0`, `*.lis`, `*.log` — all gitignored
- **Do NOT overwrite** checkpoint files — use `_v2` suffix for retrained versions
- **Do NOT delete** legacy results without documenting in `docs/decisions/`
