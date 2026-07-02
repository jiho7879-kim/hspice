# ngspice SRAM butterfly — integration status & next steps

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
