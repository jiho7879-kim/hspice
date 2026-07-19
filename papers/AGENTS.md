# AGENTS.md — Papers

Paper manuscripts and figures for publication.

---

## Structure

```
papers/
├── paper_en_v3_ieee.md      # CANONICAL — English, IEEE manuscript format
├── paper_kr_v3_ieee.md      # CANONICAL — Korean, IEEE manuscript format
├── archive/                 # superseded drafts, reference only (frozen)
│   ├── paper_en.md          #   v0.5 original
│   ├── paper_kr.md          #   v0.5 original
│   ├── paper_enhanced_en.md #   v1.1 beginner-background pass
│   ├── paper_kr_enhanced.md #   v1.1 beginner-background pass
│   ├── paper_en_v2.md       #   v2.0 process-centric restructure
│   └── paper_kr_v2.md       #   v2.0 process-centric restructure
└── figures/                 # paper figures (PNG)
```

**Edit only the two `*_v3_ieee.md` files.** Archived drafts are historical.

---

## Version history

| Version | Change |
|---------|--------|
| v0.5 | Contribution-driven structure, 9-D production-calibrated batch |
| v1.1 | Accessible background for non-ML readers, plain-language glossary |
| v2.0 | Restructured around the sign-off problem; spec (T0 0.625 V / EOL 0.675 V) anchors the paper; cost promoted to its own section; device basics compressed |
| **v3.0** | **IEEE format: abstract + index terms, roman-numeral sections, numbered tables/figures/equations, reference list. Analogies removed from body; GP tutorial moved to Appendix A.** |

---

## Figures for v3

v3 references Fig. 1–7. **Not yet generated** — `gen_paper_figures.py` produces
8 figures matching the older structure. Regeneration against the v3 layout is
outstanding (`docs/plans/remaining_work_20260720.md` §E).

| Figure | Content |
|--------|---------|
| Fig. 1 | Pipeline overview (variation params → GP → physics layer → Vmin) |
| Fig. 2 | Design visualization: quadrant weighting + (l_com,l_sk) → (l_PG,l_PD) band |
| Fig. 3 | Predicted vs measured (μ, σ), hold-out |
| Fig. 4 | Vmin contours, GP vs measurement, with 4 corners |
| Fig. 5 | Multi-start inversion trajectories |
| Fig. 6 | Budget–accuracy relationship |
| Fig. 7 | Grouped sensitivity: ARD vs Sobol + skew window |

Generation (headless, `matplotlib.use("Agg")`):
```bash
cd python && python scripts/gen_paper_figures.py
```

---

## Key numbers (v3 — final 9-D batch, 0.4–0.7 V)

Must stay identical across both language versions:

- Spec: nominal 0.75 V, T0 **0.625 V**, EOL **0.675 V**, margin budget **50 mV**
- Hold-out: μ R² **0.9817** (RMSE 5.35 mV), σ R² **0.9845** (RMSE 0.22 mV)
- Vmin RMSE: **13.50 mV** overall, **9.14 mV** in the spec region
- Spec verdict: T0 **295/300 (98.3%)**, EOL **298/300 (99.3%)**, FP 1 at EOL
- Population: T0 pass 81.2%, EOL pass 88.5%, EOL fail 11.4%
- Sobol S_T: cn 0.464 > pu 0.298 > **l_com 0.199** > sk 0.108 … l_sk 0.001
- ΣS₁ = 0.948 (near-additive); Var[Vmin] sd = 94.5 mV
- ℓ_pu/ℓ_cn = 1.083 (hold-out fit) / 1.073 (all-data fit)
- 0.8 V removal: verdict identical 2000/2000, max|Δz| exactly 0
- z-bias (**unresolved**): +0.7σ ≈ 53 mV → EOL 80.5%; +1.9σ ≈ 144 mV → 63.0%

---

## Conventions

- Both language versions are maintained in parallel and must stay numerically
  identical — update both or neither.
- `[TBD]` marks pending measurement. Open items live in
  `docs/plans/remaining_work_20260720.md`.
- References are placeholders pending bibliographic completion.
- Vtrip (write metric) results are **not yet transcribed**; v3 cites the 4-D
  Stage-C batch as reference only and says so explicitly.

---

## Anti-patterns

- **Do NOT edit** files under `archive/` — frozen.
- **Do NOT update** only one language version — keep EN/KR in sync.
- **Do NOT present** absolute Vmin or spec pass rates as final while the §II-D
  tail diagnostic is unresolved — they are pre-correction quantities.
- **Do NOT commit** intermediate figure drafts.
- **Do NOT delete** figures without documenting in `docs/decisions/`.
