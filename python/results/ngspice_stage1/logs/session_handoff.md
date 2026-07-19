HANDOFF CONTEXT
===============

USER REQUESTS (AS-IS)
---------------------
- "What did we do so far?" (session resume request)
- "이걸 이용해서 result 폴더에 구분할 수 있도록 잘 폴더 구성한다음 stage1만 quick하게 진행해줘"
  (Use the ngspice pipeline, organize results/ folder, run Stage 1 quickly)
- "ngspice학습은 곁다리이고 메인이 아니므로 이점을 고려해서 전체 구조를 모두 변경하면 안되 필요하다면 따로 파일을 만들어서 addup하는 방식으로 해야해"
  (ngspice is a side track. Do not modify core project structure. Create new standalone files.)
- "stage1 결과를 보면 true와 gp 차이가 너무 많이 나는데 원인이 뭘까"
  (Why is the Stage 1 GP result so different from true/analytic Vmin?)
- "아 static dc는 무조건 left,right가 같아 mc로 해야지만 차이가 발생해. 일단 여기까지 status를 정리하고 지금 잠시 컴퓨터 종료해야해서 나중에 이어서하게 도와줘"
  (Need to use MC not static DC. Create handoff summary to continue after restart.)

GOAL
----
Continue the ngspice SRAM Vmin estimation pipeline by adding MC mismatch analysis (per-instance Vth variation via .mc) so that the butterfly SNM varies meaningfully with global (cn, pu) shifts, enabling realistic GP surrogate training and Vmin contour extraction.

WORK COMPLETED
--------------
- Created ngspice butterfly netlist template (python/templates/sram_butterfly_ng.sp, 149 lines): B-sources for auxiliary signals (vdiff, vdiffn, vabs), Seevinck SNM extraction via .measure, 14nm HP BSIM4 model
- Created test_ngspice.py: multi-table .print parser, .measure parser, Seevinck SNM computation, end-to-end validation (TT corner 125C/25C both pass)
- Created gen_ngspice_data.py: batch dataset generator via ThreadPoolExecutor, renders template per (cn, pu, Vop), parses y1 from .measure, saves as .npz
- Documented ngspice syntax decisions in docs/decisions/ngspice_integration.md (no .wrdata, no v(node1,node2) in .measure, no inline * comments, etc.)
- Created results/ngspice_stage1/ directory structure: data/, models/, figures/, logs/
- Generated 360-sample ngspice dataset (60 conditions x 6 Vop, TT 125C) in 5 seconds (72.3 sim/s)
- Created standalone script scripts/stage1_ngspice.py that loads ngspice data, trains GP, produces Vmin contour + z-score diagnostic figure
- Confirmed src/surrogate.py was reverted to original (no core file modifications)

CURRENT STATE
-------------
- ngspice pipeline: template -> run -> parse -> save .npz  is fully functional
- Stage 1 result: GP fit is excellent (mu RMSE=0.00095, sigma RMSE=0.00025)
- CRITICAL FINDING: Deterministic DC butterfly SNM (Seeminck y1) is nearly constant across global Vth shifts. Both half-cells shift identically, so butterfly SNM barely changes. This makes GP learn a flat mu surface in (cn, pu).
- Vmin contour from ngspice GP differs significantly from analytic model (0.168V RMSE) because:
  (a) Deterministic DC SNM is NOT the same as MC-mismatch mu_SNMR needed for Vmin
  (b) 14nm HP PTM BSIM4 model at L=20nm shows inverted Vop-SNM trend (higher Vop = lower SNM)
  (c) ngspice SNM absolute magnitude (~7-10 mV) is far too small, requiring scale factor 12x
- All core src/ files are unchanged. Only new standalone scripts under scripts/ and data under results/.

PENDING TASKS
-------------
- Add MC mismatch analysis to ngspice template (per-instance Vth variation via .mc with agauss/mc distributions on each transistor instance)
- Generate proper mu_SNMR and sigma_SNMR from MC distribution at each (cn, pu, Vop) condition
- Retrain GP on MC-derived dataset and compare with analytic model
- If MC data is too slow (100-1000x per condition), reduce N_cond or use analytic proxy
- Integrate with main pipeline (demo.py, train.py) as cross-validation
- Commit new files when ready

KEY FILES
---------
- python/templates/sram_butterfly_ng.sp - ngspice butterfly netlist template (BSIM4 14nm HP, B-sources, .measure Seevinck)
- python/scripts/gen_ngspice_data.py - batch dataset generator (ThreadPoolExecutor, .measure parse, .npz save)
- python/scripts/stage1_ngspice.py - standalone Stage 1: train GP on ngspice data + contour + diagnostic (no core file mods)
- python/scripts/test_ngspice.py - end-to-end validation script (render -> run -> parse -> SNM)
- python/results/ngspice_stage1/data/dataset.npz - 360-sample ngspice dataset (60 cond x 6 Vop)
- python/results/ngspice_stage1/models/mu_gp.pth - trained mu GP state dict
- python/results/ngspice_stage1/models/sigma_gp.pth - trained sigma GP state dict
- python/results/ngspice_stage1/figures/contour_ngspice.png - Vmin contour + z-score diagnostic figure
- docs/decisions/ngspice_integration.md - ngspice syntax decisions and findings documented

IMPORTANT DECISIONS
-------------------
- Deterministic DC butterfly SNM is insufficient for Vmin estimation. MC mismatch is required to create meaningful mu_SNMR variation with (cn, pu).
- All ngspice additions must be standalone files (scripts/ or results/) -- core src/ files must NOT be modified.
- SNM scale factor (12x) was a temporary workaround for Stage 1 GP training. Real fix: add MC mismatch.
- ngspice-46 syntax limitations: no .wrdata, no v(node1,node2) in .measure, no inline * comments, no ternary in .measure param
- VOP_COL and Z_FIXED from src/utils.py must be used in any physics-constrained code (never hardcode 2 or 6.0)

EXPLICIT CONSTRAINTS
--------------------
- Do not suppress Python type errors -- all src/ files use strict typing (from __future__ import annotations)
- Do not rename VOPS, Z_FIXED, COMMON_N_MIN, COMMON_N_MAX, VOP_COL
- Do not change the data shape convention (X: Nxd, y: Nx2)
- Do not hardcode Vop column index as 2 -- use VOP_COL from src.utils
- Do not use gp.forward() for L_mono -- use gp.eval() with prediction_strategy = None
- Do not run scripts from wrong directory -- all scripts expect CWD = python/
- Do not skip the sys.path.insert(0, ...) import boilerplate -- each script is self-contained
- Do not use matplotlib.use("Agg") if running interactively

CONTEXT FOR CONTINUATION
------------------------
- The ngspice pipeline runs at ~72 sim/s (ThreadPoolExecutor, 6 workers) on a desktop CPU
- Next major step: add .mc analysis with per-instance Vth mismatch (agauss distribution on each transistor's Vth0)
- The 14nm HP PTM model (L=20nm, W=100-300nm) is a predictive model, likely not well-calibrated for absolute SNM values
- ngspice-46 binary is at C:\Users\User\Documents\HSPICE\bin\ngspice_con.exe
- Run all scripts from the python/ directory (Set-Location first), use `py` not `python` on this Windows setup
- Starting point for continuation: modify sram_butterfly_ng.sp template to add .mc analysis, then update gen_ngspice_data.py to run MC and extract mu/sigma from the distribution

TO CONTINUE IN A NEW SESSION:
1. Press 'n' in OpenCode TUI to open a new session, or run 'opencode' in a new terminal
2. Paste the HANDOFF CONTEXT above as your first message
3. Add your request: "Continue from the handoff context above. [Your next task]"
