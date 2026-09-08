#!/usr/bin/env bash
# Re-derive every result that depends on surrogate_vb*.pth, in dependency order.
# Needed after the sigma-kernel change of D-16 (AdditiveGPModel/linear ->
# ExactGPModel/log).  v_b_forward.py --refit must have run FIRST and written the
# new checkpoints; everything here loads them.
#
#   bash manuscript/code/rederive_all.sh <logdir>
#
# Stops at the first failure so a stale JSON never survives next to a fresh one.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=.venv/bin/python
LOG="${1:?usage: rederive_all.sh <logdir>}"
mkdir -p "$LOG"

run() {                       # run <logname> <args...>
  local name="$1"; shift
  echo "--- $name : $* "
  "$PY" "$@" > "$LOG/$name.log" 2>&1
  echo "    ok"
}

# §V-D corner, §V-E inverse, §V-F lobe, §V-G external, §V-B robustness
run corner_read    manuscript/code/v_d_corner.py
run corner_write   manuscript/code/v_d_corner.py --write
run inverse        manuscript/code/v_e_inverse.py
run inverse_write  manuscript/code/v_e_inverse.py --write
run scenario       manuscript/code/v_e_scenario.py
run lobe           manuscript/code/v_f_lobe.py
run external_read  manuscript/code/v_g_external.py
run external_write manuscript/code/v_g_external.py --write
run robust_read    manuscript/code/v_b_robustness.py
run robust_write   manuscript/code/v_b_robustness.py --write

# §VII sensitivity (Sobol base 4096, matches the n_base already in the JSON)
run sens_read      manuscript/code/vii_sensitivity.py -n 4096
run sens_write     manuscript/code/vii_sensitivity.py --write -n 4096

# §VI cost -- the expensive one: each part refits the GP many times
run cost_voltage        manuscript/code/vi_cost.py --part voltage
run cost_voltage_write  manuscript/code/vi_cost.py --part voltage --write
run cost_conditions     manuscript/code/vi_cost.py --part conditions
run cost_conditions_s1  manuscript/code/vi_cost.py --part conditions --seed-offset 1
run cost_mc             manuscript/code/vi_cost.py --part mc
run cost_combined       manuscript/code/vi_cost.py --part combined
run cost_combined_write manuscript/code/vi_cost.py --part combined --write

echo "ALL RESULTS RE-DERIVED"
