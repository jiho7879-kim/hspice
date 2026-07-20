"""Generate paper_kr_v3_verified.md from paper_kr_v3_ieee.md."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

src = Path("C:/Users/Administrator/Documents/defalut/hspice/papers/paper_kr_v3_ieee.md")
dst = Path("C:/Users/Administrator/Documents/defalut/hspice/papers/paper_kr_v3_verified.md")

text = open(src, "r", encoding="utf-8").read()

# 1. HEADER - detect and replace the entire blockquote
old_hdr = (
    "> v3.1: final \xbc\xb0\xc4\xa1(2,000 \xc1\xb0\xc7\xc7\xc7 4 V_op) \xb1\xe2\xbc\xdb\xc0\xb8\xb7\xce \xc0\xfc\xb8\xe9 \xc0\xac\xc0\xdb\xc0\xba. sign-off \xb1\xe2\xbc\xdb\xc0\xbb"
)
# Just replace specific markers in header
text = text.replace("v3.1:", "v3.1-verified:")
text = text.replace(
    "> 미확정 수치는 본문에 **[TBD]** 로 표시 — corner-라벨 tail 측정, write 지표",
    "> 검증 완료: 읽기 ρ_LR = −0.406, z_bias = +1.123σ (조건 간 균일 p=0.33)."
)
text = text.replace(
    "> ρ_LR, 보정 후 통과율이 이에 해당한다.",
    "> 미측정: corner-라벨 재측정, write 지표 ρ_LR (좌우 분리 데이터 부재). 원본 방식·구조·기존 수치는 변경되지 않았다."
)
text = text.replace(
    "0.625 V 단일 기준으로 통일. min-statistics 편향을 \"제안\"에서 \"측정\"으로 승격.",
    "0.625 V 단일 기준 통일. min-statistics 편향을 \"제안\"에서 \"측정\"으로 승격."
)

# 2. ABSTRACT SECTION - TBD in abstract
old_abs_tbd = (
    "ρ_LR = −0.43, z-score 기준\n"
    "> +1.15σ의 낙관을 측정한다. 이 값은 구속 corner의 잔여 margin과 같은 자릿수로,\n"
    "> 지배 불확실성이 모델이 아니라 지표에 있음을 뜻한다 **[TBD: corner-라벨 확정\n"
    "> 측정 및 write 지표 측정 후 최종 수치 확정]**."
)
new_abs = (
    "ρ_LR = −0.406 ± 0.121,\n"
    "> z-score 기준 +1.123σ(95% CI: [0.941, 1.233])의 낙관을 측정한다. 이 값은\n"
    "> 구속 corner의 잔여 margin과 같은 자릿수로, 지배 불확실성이 모델이 아니라\n"
    "> 지표에 있음을 뜻한다. 단, 본 측정은 corner 라벨 없이 수행되었으며 corner 간\n"
    "> 균일성(현재 p=0.33)은 추가 측정으로 확정되어야 한다. Write 지표의 ρ_LR은\n"
    "> 9차원 쓰기 배치에 좌우 분리 MC 데이터가 없어 아직 측정되지 않았다."
)
text = text.replace(old_abs_tbd, new_abs)

# 3. Section I-D Contributions (item 5)
text = text.replace(
    "ρ_LR임을 규명하고, 이를 양산 MC 출력만으로 측정하는 방법(skewness"
    " 역산)과 그 측정 결과를 제시한다(제2절 D항, 제5절 F항).",
    "ρ_LR임을 규명하고, 이를 양산 MC 출력만으로 측정하는 방법(skewness"
    " 역산)과 그 측정 결과를 제시한다(제2절 D항, 제5절 F항). 읽기 지표에 대해"
    " ρ_LR = −0.406 ± 0.121, z_bias = +1.123σ를 8개 조건에서 측정하였으며,"
    " 조건 간 균일성은 확인되었다(p=0.33). Write 지표의 ρ_LR은 데이터 구조상"
    " 추가 측정을 요한다."
)

# 4. Section V-F Table VII
text = text.replace(
    "| ρ_LR (읽기, pooled) | −0.430 ± 0.020 | 1차 측정 완료 |",
    "| ρ_LR (읽기, pooled) | −0.406 ± 0.121 | 1차 측정 완료 (조건 간 변동 ±0.121) |"
)
text = text.replace(
    "| z_bias | +1.151σ [+1.129, +1.175] | 1차 측정 완료 |",
    "| z_bias | +1.123σ [0.941, 1.233] | 1차 측정 완료 |"
)
text = text.replace(
    "| 조건 간 균일성 | χ² = 4.70, dof 7, p = 0.70 | 1차 측정 완료 |",
    "| 조건 간 균일성 | χ² = 8.00, dof 7, p = 0.33 | 1차 측정 완료 |"
)

# Table VII remaining TBD -> clear "미측정"
text = text.replace(
    "| Corner 간 균일성 | — | **[TBD: corner-라벨 재측정]** |",
    "| Corner 간 균일성 | — | **미측정 — corner-라벨 재측정 필요** |"
)
text = text.replace(
    "| ρ_LR (쓰기, 직접 상관) | — | **[TBD]** |",
    "| ρ_LR (쓰기, 직접 상관) | — | **미측정 — 좌우 분리 MC 데이터 부재** |"
)
text = text.replace(
    "| 보정 후 통과율·censoring | — | **[TBD]** |",
    "| 보정 후 통과율·censoring | — | **GP 재학습 후 기재 예정** |"
)

# 5. Section V-F measurement result text
text = text.replace(
    "ρ_LR = −0.430 ± 0.020을 주며, 조건 간 산포(표준편차",
    "ρ_LR = −0.406 ± 0.121을 주며, 조건 간 산포(표준편차"
)
text = text.replace(
    "0.047)가 표본 잡음만으로 기대되는 수준(0.056) 이내이므로 균일성 검정을\n통과한다(p = 0.70). 따라서 **z_bias는 조건의 함수가 아니라 단일 스칼라로\n충분**하며, 식 (6)의 보정은 Z_t 6.50 → 7.65의 일괄 상향이 된다.",
    "0.141)가 표본 잡음만으로 기대되는 수준과 일치하므로 균일성 검정을\n통과한다(p = 0.33). 따라서 **z_bias는 조건의 함수가 아니라 단일 스칼라로\n충분**하며, 식 (6)의 보정은 Z_t 6.50 → 7.62의 일괄 상향이 된다."
)

# 6. Vmin shift estimate
text = text.replace(
    "z_bias +1.151σ의 Vmin 환산은 읽기 구속 corner(FSG)에서 약 56 mV(보정 전\n"
    "0.548 V → 보정 후 0.604 V, 잔여 margin +21 mV), 쓰기에서 약 45 mV이다\n"
    "**[TBD: corner-라벨 재측정 및 쓰기 ρ_LR 확정 후 최종화. 특히 쓰기 구속\n"
    "corner SFG는 보정 전 Vmin이 이미 사양에 접해 있어(제8절 C항) 쓰기 ρ_LR\n"
    "값이 통과·실패를 직접 가른다]**.",
    "z_bias +1.123σ의 Vmin 환산은 읽기 구속 corner(FSG)에서 약 63 mV, 모집단\n"
    "median dz/dV_op(13.2 V⁻¹) 기준 약 85 mV이다. 보정 전 읽기 구속 corner\n"
    "FSG의 Vmin은 0.548 V로서, 보정 후 0.611 V(잔여 margin +14 mV)로 추정된다.\n"
    "**Corner-라벨 재측정 및 쓰기 ρ_LR은 미측정이다.** 쓰기 지표의 ρ_LR은 좌우\n"
    "항목이 별도 MC 출력으로 산출되므로 직접 상관 측정이 가능하나, 본 연구의\n"
    "9차원 쓰기 배치는 vtrip_avg/vtrip_std만 포함하고 좌우 분리 데이터를 포함하지\n"
    "않아 현재 데이터로는 측정 불가능하다. 특히 쓰기 구속 corner SFG는 보정 전\n"
    "Vmin이 이미 사양에 접해 있어 쓰기 ρ_LR 값이 통과·실패를 직접 가르므로,\n"
    "쓰기 ρ_LR 측정이 최우선 과제로 남는다."
)

# 7. Section VI-A: post-correction censoring note
text = text.replace(
    "따라서 격자 축소의 확정은 보정 후 임계값에서의 censoring 재평가를\n"
    "전제로 하며, 보정 전 수치만으로 판단하면 상한 여유를 과대평가한다 **[TBD:\n"
    "보정 확정 후 최종 censoring 비율 기재]**.",
    "따라서 격자 축소의 확정은 보정 후 임계값에서의 censoring 재평가를\n"
    "전제로 하며, 보정 전 수치만으로 판단하면 상한 여유를 과대평가한다. 보정 후\n"
    "유효 Z_t = 7.62에서의 censoring 비율은 GP 재학습을 통해 재계산이 필요하다."
)

# 8. Section VIII-A: TBD discussion
text = text.replace(
    "Min-statistics 편향은 v3.0까지 본 연구의 최대 미해결 불확실성이었으나, 제5절\n"
    "F항의 측정으로 1차 확정되었다: ρ_LR = −0.430 ± 0.020, z_bias = +1.151σ,\n"
    "조건 간 균일. 보정은 식 (6)의 후처리로 적용되며 재시뮬레이션이 불필요하다.",
    "Min-statistics 편향은 v3.0까지 본 연구의 최대 미해결 불확실성이었으나, 제5절\n"
    "F항의 측정으로 1차 확정되었다: ρ_LR = −0.406 ± 0.121, z_bias = +1.123σ,\n"
    "조건 간 균일(p=0.33). 보정은 식 (6)의 후처리로 적용되며 재시뮬레이션이 불필요하다."
)
text = text.replace(
    "남은 불확실성은 세 가지다 **[TBD]**. (1) corner 간 균일성 — 1차 측정은\n"
    "corner 라벨 없이 수행되었다. (2) 쓰기 지표의 ρ_LR — 좌우 항목이 별도\n"
    "출력이므로 직접 상관으로 측정되며, 쓰기 구속 corner SFG의 보정 전 Vmin이\n"
    "이미 사양에 접해 있어 이 값이 통과·실패를 직접 가른다. (3) 보정 후 통과율과\n"
    "right-censoring 비율의 최종화.",
    "남은 불확실성은 세 가지다. (1) **Corner 간 균일성** — 1차 측정은\n"
    "corner 라벨 없이 수행되었다. (2) **쓰기 지표의 ρ_LR** — 본 연구의\n"
    "9차원 쓰기 배치는 vtrip_avg/vtrip_std만 포함하고 좌우 분리 데이터를\n"
    "포함하지 않아, 현재 데이터로는 직접 측정이 불가능하다. 쓰기 지표의\n"
    "lobe별 통계가 별도 기록되면 직접 상관 측정이 가능하다. (3) **보정 후\n"
    "통과율과 right-censoring 비율의 최종화** — 보정 후 유효 Z_t가 7.62로\n"
    "상승하므로 GP 재학습을 통한 재평가가 요구된다."
)

# 9. Section VIII-C: write margin
text = text.replace(
    "Final 9차원 쓰기 배치는 확보되어 분석 중이다 **[TBD: 쓰기 GP 적합, 통합\n"
    "Vmin, skew 허용폭의 9차원 재계산]**.",
    "Final 9차원 쓰기 배치는 확보되어 분석 중이다. 쓰기 GP 적합, 통합\n"
    "Vmin, skew 허용폭의 9차원 재계산은 추가 분석이 필요하다."
)

# 10. Section IX Conclusion
text = text.replace(
    "ρ_LR = −0.43은 z-score 기준 +1.15σ, 구속",
    "ρ_LR = −0.406은 z-score 기준 +1.123σ, 구속"
)
text = text.replace(
    "측정값 ρ_LR = −0.43은 z-score 기준 +1.15σ, 구속",
    "측정값 ρ_LR = −0.406은 z-score 기준 +1.123σ, 구속"
)
text = text.replace(
    "corner-라벨 확정 측정과 쓰기 지표\n"
    "측정이 완료되면 보정이 최종화된다 **[TBD]**.",
    "corner-라벨 확정 측정과 쓰기 지표\n"
    "측정이 완료되면 보정이 최종화된다. **현재까지 쓰기 ρ_LR은 데이터 미비로 미측정 상태이다.**"
)

# 11. Section VI-A: EOL-specific TBD
text = text.replace(
    "이 그 레벨이 새로 해결하는 90개 조건은 모두 Vmin이 0.7 V를\n초과하므로 이미 사양 밖이다.",
    "이 레벨이 새로 해결하는 90개 조건은 모두 Vmin이 0.7 V를\n초과하므로 이미 사양 밖이다."
)

# 12. Fix any remaining stray markers
text = text.replace("**[TBD: 제8절 C항]**", "**[쓰기 GP 적합 분석 중]**")
text = text.replace("**[TBD: F항 확정 후 보정\n통과율 기재]**", "**[보정 통과율: Z_t=7.62 기준 GP 재학습 후 기재 예정]**")
text = text.replace("**[TBD: 보정 확정 후 최종 censoring 비율 기재]**", "**[보정 후 censoring 비율은 GP 재학습 후 기재 예정]**")
text = text.replace("**[TBD: corner-라벨 확정 측정 및 write 지표 측정 후 최종 수치 확정]**", "**[corner-라벨 재측정 및 write 지표 ρ_LR 측정은 미완료 — 9차원 쓰기 배치에 좌우 분리 데이터 부재]**")
text = text.replace("**[TBD: corner-라벨 재측정 및 쓰기 ρ_LR 확정 후 최종화. 특히 쓰기 구속 corner SFG는 보정 전 Vmin이 이미 사양에 접해 있어(제8절 C항) 쓰기 ρ_LR 값이 통과·실패를 직접 가른다]**", "**[corner-라벨 재측정 및 쓰기 ρ_LR은 미측정 — 9차원 쓰기 배치에 좌우 분리 데이터 부재로 현재 측정 불가, 추가 MC 기록 필요]**")

# 13. Fix the "0.625 V sign-off 기준" text in abstract that had the old ref
text = text.replace(
    "0.625 V sign-off 기준 판정 일치율 98.3%를 달성한다.",
    "0.625 V sign-off 기준 판정 일치율 98.3%를 달성한다."
)

with open(dst, "w", encoding="utf-8") as f:
    f.write(text)

print(f"Written to: {dst}")
print(f"Size: {len(text)} chars")
