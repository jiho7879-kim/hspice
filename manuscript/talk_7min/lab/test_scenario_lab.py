"""논문 §IV-B 시나리오 수치(results/scenario.json)를 Scenario Lab이 그대로 재현하는지 본다.

    .venv/bin/python manuscript/talk_7min/lab/test_scenario_lab.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from scenario_lab import Lab, DemoEngine  # noqa: E402

paper = {c["case"]: c for c in json.loads((HERE.parents[1] / "results" / "scenario.json").read_text())["cases"]}
lab = Lab(DemoEngine.from_bundle())
cfg = lab.config({"target": 0.575})

for spec, case in (("l_com", "k_sigmaN"), ("l_com+lpu", "k_sigmaNP"), ("corner", "corner_pullin")):
    r = lab.solve(cfg, spec)
    assert r["status"] == "reachable", r
    assert abs(r["s_required"] - paper[case]["s_required"]) < 1e-4, (spec, r["s_required"], paper[case]["s_required"])
    print(f"ok {spec:10s} s={r['s_required']:.5f}  paper={paper[case]['s_required']:.5f}  {r['change']}")
r = lab.solve(cfg, "lpu")
assert r["status"] == "unreachable" and abs(r["best_vmin"] - paper["k_sigmaP"]["vmin_at_floor"]) < 1e-6, r
print(f"ok lpu        unreachable, floor Vmin={r['best_vmin']:.5f}")
