"""QC round 1 -- every headline number must (a) match results/*.json and (b) appear in
both language versions.

    .venv/bin/python manuscript/code/qc_numbers.py

Fails loudly. A number that is in the paper but not here is not checked; a number that is
here but missing from a paper is reported.
"""
import json
import re
import sys

import _paths  # noqa: F401
from _paths import MANUSCRIPT, RESULTS

KR = (MANUSCRIPT / "paper_kr.md").read_text()
EN = (MANUSCRIPT / "paper_en.md").read_text()


def load(n):
    return json.load(open(RESULTS / n))


fwd, fwdw = load("forward.json"), load("forward_write.json")
cor, corw = load("corner.json"), load("corner_write.json")
inv, lob = load("inverse.json"), load("lobe.json")
ext, extw = load("external.json"), load("external_write.json")
cv, cc, cm = load("cost_voltage.json"), load("cost_conditions.json"), load("cost_mc.json")
cb, cbw = load("cost_combined.json"), load("cost_combined_write.json")
sen, senw = load("sensitivity.json"), load("sensitivity_write.json")
corner = {c["corner"]: c for c in cor["corners"]}
cornerw = {c["corner"]: c for c in corw["corners"]}
lobe_c = {c["corner"]: c for c in lob["corners"]}

# (label, value from results, string as printed in the papers)
CHECKS = [
    ("Z_t",                        6.3984,                              "6.398"),
    ("rho_LR",                     lob["rho_pooled"],                   "−0.371"),
    ("zbias",                      lob["zbias_pooled"],                 "1.054"),
    ("Z_eff",                      lob["z_eff_pooled"],                 "7.453"),
    ("read mu RMSE",               fwd["mu_rmse_mV"],                   "2.50"),
    ("read sigma RMSE",            fwd["sigma_rmse_mV"],                "0.256"),
    ("read Vmin RMSE",             fwd["vmin_rmse_mV_holdout"],         "8.35"),
    ("read Vmin P90",              fwd["vmin_abs_err_p90_mV"],          "10.69"),
    ("read Vmin max",              fwd["vmin_abs_err_max_mV"],          "53.78"),
    ("read censored",              fwd["vmin_conditions_censored"],     "49"),
    ("write mu RMSE",              fwdw["mu_rmse_mV"],                  "2.17"),
    ("write sigma RMSE",           fwdw["sigma_rmse_mV"],               "2.04"),
    ("write Vmin RMSE",            fwdw["vmin_rmse_mV_holdout"],        "14.45"),
    ("ell ratio pu/cn",            fwd["ell_mu"]["pu"] / fwd["ell_mu"]["cn"], "1.093"),
    ("ell Vop",                    fwd["ell_mu"]["Vop"],                "4.64"),
    ("FSG read measured",          corner["FSG"]["vmin_meas"],          "0.5903"),
    ("FSG read predicted",         corner["FSG"]["vmin_pred"],          "0.5908"),
    ("SFG write measured",         cornerw["SFG"]["vmin_meas"],         "0.5924"),
    ("SFG write predicted",        cornerw["SFG"]["vmin_pred"],         "0.6070"),
    ("FSG z at T0",                lobe_c["FSG"]["z_at_T0"],            "6.927"),
    ("FSG corrected Vmin",         lobe_c["FSG"]["vmin_corrected"],     "0.6619"),
    ("FSG headroom",               lob["zbias_headroom_sigma"],         "0.529"),
    ("cn recovery RMSE",           inv["recovery"]["cn"]["rmse_mV"],    "2.60"),
    ("pu recovery RMSE",           inv["recovery"]["pu"]["rmse_mV"],    "3.20"),
    ("ext read clean Vmin RMSE",   ext["clean"]["vmin_rmse_mV"],        "4.26"),
    ("ext write clean Vmin RMSE",  extw["clean"]["vmin_rmse_mV"],       "13.63"),
    ("write 0.8V extrap bias",     extw["vop_extrapolation"]["mu_bias_mV"], "−6.45"),
    ("T0 bracket max dz (x1e15)",  cv["t0_bracket_max_dz"] * 1e15,      "1.78"),
    ("voltage reduced Vmin RMSE",  cv["reduced_on_full"]["vmin_rmse_mV"], "6.99"),
    ("400-condition Vmin RMSE",    cc["pareto"][2]["vmin_rmse_mV"],     "8.78"),
    ("mc500 Vmin RMSE",            [p for p in cm["pareto"] if p["n_mc"] == 500][0]["vmin_rmse_mV"], "7.63"),
    ("combined read Vmin RMSE",    cb["combined_on_full"]["vmin_rmse_mV"], "10.95"),
    ("combined read speedup",      cb["speedup"],                       "53"),
    ("combined write Vmin RMSE",   cbw["combined_on_full"]["vmin_rmse_mV"], "15.83"),
    ("combined write speedup",     cbw["speedup"],                      "42.5"),
    ("ST cn read (z)",             sen["sobol"]["ST"]["z(0.625V)"]["cn"],     "0.419"),
    ("ST l_com read (z)",          sen["sobol"]["ST"]["z(0.625V)"]["l_com"],  "0.276"),
    ("ST p_u read (z)",            sen["sobol"]["ST"]["z(0.625V)"]["pu"],     "0.188"),
    ("ST cn write (z)",            senw["sobol"]["ST"]["z(0.625V)"]["cn"],    "0.421"),
    ("ST l_com read (sigma)",      sen["sobol"]["ST"]["sigma(0.625V)"]["l_com"],  "0.847"),
    ("ST l_com write (sigma)",     senw["sobol"]["ST"]["sigma(0.625V)"]["l_com"], "0.722"),
    ("ARD ell Vop write",          senw["ard"]["ell_mu"]["Vop"],              "4.00"),
    ("skew full range, read Zt",   sen["skew_tolerance"]["z_target"]["full_range_pct"],  "82.7"),
    ("skew full range, read Zeff", sen["skew_tolerance"]["z_eff"]["full_range_pct"],     "67.0"),
    ("skew full range, write Zt",  senw["skew_tolerance"]["z_target"]["full_range_pct"], "77.6"),
    ("skew full range, write Zeff", senw["skew_tolerance"]["z_eff"]["full_range_pct"],   "62.9"),
]

# The shares quoted in Sec. VII-B are sums over Table XVII, not stored fields. Recompute
# them here so a sentence cannot drift away from the table above it.
_st, _stw = sen["sobol"]["ST"]["z(0.625V)"], senw["sobol"]["ST"]["z(0.625V)"]
_ss, _ssw = sen["sobol"]["ST"]["sigma(0.625V)"], senw["sobol"]["ST"]["sigma(0.625V)"]
CHECKS += [
    ("non-corner share of z, read",
     100 * (sum(_st.values()) - _st["cn"] - _st["pu"]) / sum(_st.values()), "41"),
    ("non-corner share of z, write",
     100 * (sum(_stw.values()) - _stw["cn"] - _stw["pu"]) / sum(_stw.values()), "40"),
    ("length-axis share of sigma, read",
     100 * (_ss["l_com"] + _ss["lpu"] + _ss["l_sk"]) / sum(_ss.values()), "98.8"),
    ("length-axis share of sigma, write",
     100 * (_ssw["l_com"] + _ssw["lpu"] + _ssw["l_sk"]) / sum(_ssw.values()), "93.8"),
]

# Table IV must account for all 300 hold-out conditions: scored + floor-censored +
# above-grid. The third number is not stored anywhere, so the table is the only place it
# appears -- read it back out and check the sum closes.
for mode, res, pat in (("read", fwd, r"above the top level \| (\d+) / 300"),
                       ("write", fwdw, r"above the top level \| \d+ / 300 \| (\d+) / 300")):
    m = re.search(pat, EN)
    if not m:
        fails_early = f"STRUCT Table IV: no above-grid row for {mode}"
        print("FAIL " + fails_early)
        sys.exit(1)
    off = int(m.group(1))
    total = res["vmin_conditions_scored"] + res["vmin_conditions_censored"] + off
    if total != 300:
        print(f"FAIL COUNT Table IV {mode}: {res['vmin_conditions_scored']} scored + "
              f"{res['vmin_conditions_censored']} censored + {off} above grid = {total} ≠ 300")
        sys.exit(1)

fails = []
for label, value, printed in CHECKS:
    # (a) the printed string must round-trip to the stored value
    digits = len(printed.split(".")[1]) if "." in printed else 0
    numeric = float(printed.replace("−", "-"))
    if abs(round(float(value), digits) - numeric) > 10 ** (-digits) / 2 + 1e-12:
        fails.append(f"VALUE  {label}: results={value!r} but paper prints {printed!r}")
    # (b) it must appear in both languages
    pat = re.escape(printed)
    for name, text in (("KR", KR), ("EN", EN)):
        if not re.search(pat, text):
            fails.append(f"MISSING {label} ({printed}) not found in {name}")

# cross-language structure: same number of tables, figures, equations
for kind, pat_kr, pat_en in (("tables", r"^\*\*표 [IVX]+\.", r"^\*\*TABLE [IVX]+\."),
                             ("figures", r"^\*\*그림 \d", r"^\*\*Fig\. \d")):
    a = len(re.findall(pat_kr, KR, re.M))
    b = len(re.findall(pat_en, EN, re.M))
    if a != b:
        fails.append(f"STRUCT {kind}: KR has {a}, EN has {b}")
    else:
        print(f"  {kind}: {a} in both")

# every in-text citation must exist in the reference list, and vice versa
for name, text, head in (("KR", KR, "## 참고문헌"), ("EN", EN, "## References")):
    body, refs = text.split(head, 1)
    cited = {int(x) for x in re.findall(r"\[(\d+)\]", body)}
    listed = {int(x) for x in re.findall(r"^\[(\d+)\]", refs, re.M)}
    # a range like [22]-[24] cites the interior too
    for lo, hi in re.findall(r"\[(\d+)\][–-]\[(\d+)\]", body):
        cited |= set(range(int(lo), int(hi) + 1))
    if cited - listed:
        fails.append(f"REFS {name}: cited but not listed: {sorted(cited - listed)}")
    if listed - cited:
        fails.append(f"REFS {name}: listed but never cited: {sorted(listed - cited)}")

for f in fails:
    print("FAIL " + f)
print(f"\n{len(CHECKS)} numbers checked, {len(fails)} problems")
sys.exit(1 if fails else 0)
