"""5분 구두 발표용 PPT (Widescreen 13.333 x 7.5 in) + 발표 대본을 노트에 넣어 생성한다.

layout은 ~/.agents/skills/slide-design-patterns 의 측정 spec(Preset A)을 따른다.
좌표는 모두 슬라이드 대비 % [x, y, w, h] 로 쓰고 box()가 Wide 기준 EMU로 환산한다.
수치 출처: SRAM_Vmin_IEEE_KR.docx (= results/*.json, make_docx.js).

usage: .venv/bin/python manuscript/presentation/make_talk_5min.py
"""
from __future__ import annotations

import re
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

HERE = Path(__file__).resolve().parent
FIG = HERE.parent / "figures"
OUT = HERE / "SRAM_Vmin_5min_KR.pptx"

W, H = 12192000, 6858000                      # Widescreen 13.333 x 7.5 in
BOLD, LIGHT = "맑은 고딕", "Malgun Gothic Semilight"

NAVY, STEEL, BLUE, BLACK = "1428A0", "5B728D", "3E7EDE", "000000"
RULE, NEUTRAL, GRAY, FOOT, WHITE = "E7E6E3", "BFBFBF", "7F7F7F", "4C5759", "FFFFFF"
ROLE = {1: NAVY, 2: STEEL, 3: BLUE, 4: BLACK}  # 네 질문의 색 = 뒤 장표의 범례


def rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h)


def emu(x, y, w, h):
    return Emu(round(W * x / 100)), Emu(round(H * y / 100)), Emu(round(W * w / 100)), Emu(round(H * h / 100))


def set_face(run, face: str) -> None:
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        el = rpr.find(qn(tag))
        if el is None:
            el = etree.SubElement(rpr, qn(tag))
        el.set("typeface", face)


def text(slide, x, y, w, h, paras, size=16, color=BLACK, emph=None, align="l",
         anchor="t", bold=False, spacing=1.1):
    """paras: str 또는 str 리스트. '**구절**'은 Bold + emph 색 (skim line)."""
    tb = slide.shapes.add_textbox(*emu(x, y, w, h))
    tf = tb.text_frame
    tf.word_wrap, tf.auto_size = True, MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    for i, para in enumerate([paras] if isinstance(paras, str) else paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
        p.line_spacing = spacing
        for j, seg in enumerate(re.split(r"\*\*", para)):
            if not seg:
                continue
            strong = bold or j % 2 == 1
            r = p.add_run()
            r.text = seg
            r.font.size = Pt(size)
            r.font.bold = strong
            r.font.color.rgb = rgb(emph if (j % 2 == 1 and emph) else color)
            set_face(r, BOLD if strong else LIGHT)
    return tb


def rect(slide, x, y, w, h, fill, shape=MSO_SHAPE.RECTANGLE, line=None, lw=0.75):
    s = slide.shapes.add_shape(shape, *emu(x, y, w, h))
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb, s.line.width = rgb(line), Pt(lw)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    return s


def hline(slide, x, y, w, color=RULE, pt=1.9):
    h_pct = pt / 540 * 100                       # 선 두께(pt) → 세로 %
    return rect(slide, x, y - h_pct / 2, w, h_pct, color)


def vline(slide, x, y, h, color=RULE, pt=2.5):
    return rect(slide, x - pt / 960 * 100 / 2, y, pt / 960 * 100, h, color)


def picture(slide, path, x, y, w=None, h=None):
    X, Y, Wd, Hd = emu(x, y, w or 0, h or 0)
    return slide.shapes.add_picture(str(path), X, Y, Wd if w else None, Hd if h else None)


def frame(prs, n, title, notes, kicker=None, role=None, foot=None):
    """공통 frame: 제목 [3.9, 3.4] · rule y 13.3 · 좌하단 번호/주석 (design-system §2–3)."""
    s = prs.slides.add_slide(prs.slide_layouts[6])
    text(s, 3.9, 3.4, 92.3, 7.9, title, size=30, bold=True, anchor="m")
    hline(s, 3.8, 13.3, 92.4, pt=3.8)
    text(s, 3.5, 94.5, 1.5, 3, str(n), size=10, color="44566A", bold=True)
    if foot:
        text(s, 5.5, 94.7, 74, 3, foot, size=9, color=FOOT)
    text(s, 76, 94.6, 20.2, 3, "SRAM Vmin surrogate", size=9, color=GRAY, align="r")
    if kicker:
        text(s, 3.9, 15.4, 92.3, 4.4, kicker, size=18, color=ROLE[role], bold=True)
    s.notes_slide.notes_text_frame.text = notes
    return s


def kpi(slide, x, y, w, value, unit, label, color, size=32):
    """숫자 32pt + 단위 18pt (비율 0.56) + 아래 라벨."""
    tb = text(slide, x, y, w, 8, [f"**{value}**"], size=size, color=color, emph=color, align="c")
    r = tb.text_frame.paragraphs[0].add_run()
    r.text, r.font.size, r.font.color.rgb = f" {unit}", Pt(18), rgb(color)
    set_face(r, LIGHT)
    text(slide, x, y + 8.6, w, 3.5, label, size=12, color=GRAY, align="c")


# --------------------------------------------------------------------------- script
NOTES = {
    1: "안녕하세요. 공정 변동이 있을 때 SRAM의 Vmin을 순방향과 역방향으로 함께 추정하는 physics-guided surrogate framework를 발표하겠습니다.",
    2: "먼저 배경입니다. Vmin은 목표 yield를 지키면서 셀이 동작하는 가장 낮은 전압이고, 평균이 아니라 margin 분포의 꼬리가 정합니다. "
       "이걸 검증하는 방법은 크게 두 가지입니다. Monte Carlo는 빠짐없이 보지만 조건 하나에 수천 번씩 돌려야 해서, 설계를 바꿀 때마다 다시 돌리기가 어렵습니다. "
       "PDK corner는 빠르지만 전역 공정 방향 몇 개만 보기 때문에 local mismatch가 만드는 산포를 놓치고, 그만큼 Vmin을 낙관적으로 잡을 수 있습니다.",
    3: "그래서 이 연구의 목표는 simulation을 대체하는 게 아니라, 이미 돌린 simulation 한 번으로 더 많은 질문에 답하는 것입니다. "
       "질문은 네 가지입니다. 이 조건의 Vmin이 얼마인지, 어느 공정 축이 Vmin을 흔드는지, 목표를 맞추려면 무엇을 얼마나 바꿔야 하는지, 그리고 simulation을 얼마나 줄일 수 있는지입니다. "
       "뒤에서 이 순서대로, 같은 색으로 답을 보여드리겠습니다.",
    4: "구현은 이렇습니다. 입력은 Vth shift, local mismatch σ 배율, mobility 배율 세 종류를 NMOS 공통, pass-gate와 pull-down 사이 skew, PMOS로 나눈 9개 공정 축과 공급 전압입니다. "
       "HSPICE MC 결과로 Gaussian process 두 개를 학습하는데, 하나는 margin의 평균 μ, 다른 하나는 산포 log σ를 맞춥니다. "
       "Vmin은 직접 학습하지 않고, μ − kσ가 0 이상이 되는 가장 낮은 전압으로 식에서 계산합니다. "
       "이렇게 나누면 Vmin이 밀린 원인이 중심 이동인지 산포 증가인지 구분할 수 있고, 식이 전압에 단조롭기 때문에 역방향 계산도 안정적인 1차원 탐색이 됩니다.",
    5: "첫 번째, 정확도입니다. 학습에 쓰지 않은 조건에서 Vmin 오차는 read 3.98 mV, write 5.65 mV RMSE입니다. "
       "학습에서 뺀 PDK corner 네 개에서도 8.5 mV와 5.8 mV이고, read는 FSG, write는 SFG로 최악 corner를 정확히 짚었습니다. "
       "여기서 기준값은 독립적으로 돌린 HSPICE MC이고, silicon 측정은 아닙니다.",
    6: "두 번째는 커버리지, 어느 축이 중요한가입니다. 9개 축 전체 범위에서 total-order Sobol 지수로 read margin 분산을 나눠 봤습니다. "
       "NMOS local mismatch 축이 0.272로, corner 축인 PMOS Vth shift 0.200보다 큽니다. "
       "그리고 corner 두 축을 다 합쳐도 0.61이 상한이라, 분산의 최소 38 %는 corner가 보지 않는 방향에 있습니다. "
       "corner만 보면 이 부분을 놓치고, 개선 우선순위도 이 기여도 순으로 잡아야 한다는 뜻입니다.",
    7: "세 번째는 역방향입니다. 나머지 축을 고정하고 한 축을 1차원 이분 탐색으로 풀면, 목표 Vmin에 맞는 공정 값을 얻습니다. Vth shift 복원 오차는 1.5에서 1.9 mV 수준입니다. "
       "예를 들어 Vmin 목표를 0.625 V에서 0.575 V로 50 mV 낮추면, 수단 하나로는 NMOS local-σ를 10.9 % 줄이는 것이 가장 작은 요구이고, NMOS와 PMOS에 나누면 각각 7.8 %면 됩니다. "
       "PMOS local-σ만으로는 30 %를 줄여도 닿지 않습니다. 이 계산에 추가 simulation은 필요 없습니다.",
    8: "네 번째는 비용입니다. 기준 학습에는 1,700개 조건, 전압 5개, 조건당 MC 5,000개를 썼습니다. "
       "이걸 400개 조건, 전압 4개, MC 500개로 줄이면 budget이 53배 줄고, 그 대가로 read Vmin 오차가 3.5 mV 늘어납니다. "
       "그리고 한 번 학습하면 이후 what-if나 역방향 질의에는 MC가 더 들지 않습니다.",
    9: "정리하면, simulation campaign 한 번으로 정확도, 커버리지, 역방향 사양, 비용 네 가지 질문에 답할 수 있습니다. "
       "다만 margin을 Gaussian으로 가정했고, 역방향은 나머지 축을 고정한 조건부 결과라는 점은 한계로 남깁니다. 감사합니다.",
}
TIMES = {1: "0:00–0:15", 2: "0:15–0:50", 3: "0:50–1:20", 4: "1:20–2:05", 5: "2:05–2:40",
         6: "2:40–3:20", 7: "3:20–4:00", 8: "4:00–4:30", 9: "4:30–5:00"}


def build() -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H

    # 1. Cover (full-bleed, 단색) ---------------------------------------------
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, 100, 100, NAVY)
    text(s, 5, 27, 90, 12, "SRAM Vmin 순·역방향 추정", size=48, color=WHITE, bold=True, align="c", anchor="m")
    text(s, 5, 41, 90, 6, "공정 변동 하의 physics-guided surrogate framework", size=24, color=WHITE, align="c")
    hline(s, 44, 51.5, 12, color="8BB2EB", pt=1)
    text(s, 5, 54, 90, 4, "Gaussian process  ·  Sobol 민감도  ·  역방향 공정 사양", size=16, color="B9C6F0", align="c")
    text(s, 5, 78, 90, 4, "[발표자]  ·  [소속]", size=18, color=WHITE, align="c")
    text(s, 5, 84, 90, 3.5, "2026", size=14, color="B9C6F0", align="c")
    s.notes_slide.notes_text_frame.text = NOTES[1]

    # 2. Background — MC vs corner (Two-party + label column) ----------------
    s = frame(prs, 2, "배경: Vmin 검증은 비용과 사각지대 사이에 끼어 있다", NOTES[2],
              foot="Vmin = 목표 yield(array 크기·fail 확률)에서 margin의 tail이 0에 닿는 최저 공급 전압")
    text(s, 3.9, 15.4, 92.3, 4.4, "Vmin은 평균이 아니라 **margin 분포의 tail**이 정한다 — 그래서 산포(σ)를 놓치면 안 된다",
         size=18, color=BLACK, emph=BLUE, align="c")
    for x, name, col in ((16.0, "Monte Carlo (MC)", NAVY), (56.6, "PDK corner", BLACK)):
        rect(s, x, 22.4, 39.6, 7.1, col)
        text(s, x, 22.4, 39.6, 7.1, name, size=20, color=WHITE, bold=True, align="c", anchor="m")
    rows = [
        ("장점", "통계적으로 **빠짐없이** 본다",
                 "몇 개 corner만 돌리면 되어 **빠르다**"),
        ("비용", "조건 하나에 **수천 번**의 simulation",
                 "corner 4개 — **비용이 작다**"),
        ("한계", "설계를 바꿀 때마다 **다시 돌려야** 한다",
                 ["local mismatch의 **산포를 못 본다**", "→ Vmin을 **낙관적**으로 잡을 위험"]),
    ]
    for i, (lab, left, right) in enumerate(rows):
        y0 = 30.5 + i * 20.5
        text(s, 3.9, y0, 11, 18, lab, size=18, color=GRAY, bold=True, anchor="m")
        text(s, 17.5, y0, 36.6, 18, left, size=17, emph=NAVY, anchor="m")
        text(s, 58.1, y0, 36.6, 18, right, size=17, emph=BLACK, anchor="m")
        if i < 2:
            hline(s, 3.8, y0 + 19.3, 92.4)
    vline(s, 55.3, 22.4, 69.6)

    # 3. Motivation — 네 질문 (Column cards 4) --------------------------------
    s = frame(prs, 3, "목표: simulation 한 번으로 네 가지 질문에 답한다", NOTES[3],
              foot="대체가 아니라 재사용 — 이미 돌린 HSPICE MC를 반복 질의 가능한 모델로 바꾼다")
    cards = [
        ("① 정확도", "이 공정 조건에서\nVmin은?", ["MC를 다시 돌리지 않고", "임의 조건의 Vmin을", "mV 수준으로 예측"], "GP surrogate"),
        ("② 커버리지", "어느 공정 축이\nVmin을 흔드나?", ["corner 밖까지", "9개 축 전체의 기여를", "정량화"], "Sobol 민감도"),
        ("③ 가역성", "목표를 맞추려면\n무엇을 얼마나?", ["목표 Vmin에서", "공정 허용폭을", "거꾸로 계산"], "1차원 역해"),
        ("④ 비용", "simulation을\n얼마나 줄이나?", ["학습 budget과", "정확도의 교환비를", "측정"], "budget 절감 실험"),
    ]
    for i, (head, q, desc, tool) in enumerate(cards):
        x, col = (3.8, 27.8, 51.8, 75.7)[i], ROLE[i + 1]
        rect(s, x, 15.8, 20.3, 12.2, col)
        text(s, x, 15.8, 20.3, 12.2, head, size=22, color=WHITE, bold=True, align="c", anchor="m")
        text(s, x + 0.8, 32, 18.7, 13, q.split("\n"), size=20, color=col, bold=True, align="c", spacing=1.15)
        text(s, x + 1.2, 50, 17.9, 16, desc, size=15, align="c", spacing=1.2)
        text(s, x, 72, 20.3, 3.5, "답하는 도구", size=12, color=GRAY, align="c")
        text(s, x, 76.5, 20.3, 5, tool, size=18, color=col, bold=True, align="c")
        if i:
            vline(s, x - 1.95, 15.8, 77.3)

    # 4. Method — pipeline (Chevron timeline + two panels) -------------------
    s = frame(prs, 4, "구현: Vmin 대신 margin의 평균 μ와 산포 σ를 학습한다", NOTES[4],
              foot="k: array 크기와 목표 fail 확률이 정하는 tail 배율 · read(125 °C)와 write(−40 °C)를 각각 학습")
    steps = [("입력", "9개 공정 축 + VDD\nHSPICE MC 1,700 조건"), ("학습 ①", "GP: margin 평균 μ"),
             ("학습 ②", "GP: margin 산포 log σ"), ("해석식", "Vmin = 최저 VDD\ns.t.  μ − k·σ ≥ 0")]
    fills = (NAVY, "2C47C0", "4F65E9", BLUE)
    seg = 92.9 / 4
    for i, (lab, body) in enumerate(steps):
        x = 3.6 + i * seg
        text(s, x, 14.3, seg, 4.3, lab, size=18, color=fills[i], bold=True, align="c")
        shp = MSO_SHAPE.PENTAGON if i == 0 else MSO_SHAPE.CHEVRON
        rect(s, x, 19.9, seg + (1.2 if i < 3 else 0), 10.5, fills[i], shape=shp)
        text(s, x + (1.5 if i else 0.8), 19.9, seg - 3.2, 10.5, body.split("\n"), size=14, color=WHITE,
             bold=True, align="c", anchor="m", spacing=1.0)
    rect(s, 3.6, 33.3, 44.4, 7.5, NAVY)
    text(s, 5.5, 33.3, 42, 7.5, "왜 Vmin을 바로 맞추지 않나", size=20, color=WHITE, bold=True, anchor="m")
    rect(s, 51.8, 33.3, 44.4, 7.5, BLUE)
    text(s, 53.7, 33.3, 42, 7.5, "입력: 9개 공정 축 (3 종류 × 3 위치)", size=20, color=WHITE, bold=True, anchor="m")
    why = ["**원인 분리** — 중심 이동(μ)과 산포 증가(σ)를 따로 본다",
           "**안정적인 역해** — yield 식이 VDD에 단조 → 1차원 이분 탐색",
           "**σ가 정확도를 좌우** — log σ 위 full-ARD kernel"]
    axes = [("Vth shift (mV)", "NMOS 공통 · PG–PD skew · PMOS"),
            ("local-σ 배율 (mismatch)", "NMOS 공통 · PG–PD skew · PMOS"),
            ("mobility 배율", "NMOS 공통 · PG–PD skew · PMOS")]
    for i in range(3):
        y0 = 43.5 + i * 15.2
        text(s, 3.9, y0, 44, 12.5, why[i], size=16, emph=NAVY, anchor="m", spacing=1.15)
        text(s, 53.7, y0, 18.5, 12.5, axes[i][0], size=16, color=BLUE, bold=True, anchor="m")
        text(s, 72.5, y0, 23.7, 12.5, axes[i][1], size=15, anchor="m")
        if i < 2:
            hline(s, 3.8, y0 + 13.9, 92.4)

    # 5. Forward accuracy (figure + KPI stack) --------------------------------
    s = frame(prs, 5, "학습에 없던 조건에서도 Vmin 오차는 수 mV", NOTES[5],
              kicker="① 정확도 — 이 공정 조건에서 Vmin은?", role=1,
              foot="기준값 = 독립 HSPICE MC (silicon 실측 아님) · hold-out 300 조건 중 판정 가능한 read 245 / write 228 조건")
    picture(s, FIG / "fig3_forward.png", 3.8, 21.5, w=60.5)
    text(s, 3.9, 69, 60, 8, ["점이 대각선에 붙을수록 정확 · 회색 띠 = ±10 mV",
                             "왼쪽 read (SNM, 125 °C) · 오른쪽 write (Vtrip, −40 °C)"], size=13, color=GRAY, spacing=1.3)
    blocks = [("Hold-out Vmin RMSE", ("3.98", "mV", "Read"), ("5.65", "mV", "Write")),
              ("미학습 PDK corner 4개 RMSE", ("8.5", "mV", "Read"), ("5.8", "mV", "Write")),
              ("최악 corner 식별", ("FSG ✓", "", "Read"), ("SFG ✓", "", "Write"))]
    for i, (lab, a, b) in enumerate(blocks):
        y0 = 21.5 + i * 22.5
        text(s, 67.5, y0, 28.7, 4, lab, size=14, bold=True)
        for j, (v, u, m) in enumerate((a, b)):
            kpi(s, 67.5 + j * 14.4, y0 + 5, 14.3, v, u, m, NAVY, size=30 if u else 24)
        vline(s, 81.85, y0 + 5.5, 10, color="D9D9D9", pt=0.75)
        if i < 2:
            hline(s, 67.5, y0 + 20.5, 28.7)

    # 6. Sensitivity (bar chart + findings) -----------------------------------
    s = frame(prs, 6, "Read margin 분산의 38 % 이상은 corner 축 밖에 있다", NOTES[6],
              kicker="② 커버리지 — 어느 공정 축이 Vmin을 흔드나?", role=2,
              foot="total-order Sobol 지수 ST, read margin z at VDD = 0.625 V, 9개 축 전 범위 · ST는 상호작용을 포함해 합이 1을 넘을 수 있다")
    st = [("ΔVth,N  NMOS Vth (corner)", 0.413, True), ("kσN  NMOS local-σ", 0.272, False),
          ("ΔVth,P  PMOS Vth (corner)", 0.200, True), ("ΔVth,skew  PG–PD Vth", 0.065, False),
          ("kσP  PMOS local-σ", 0.045, False), ("kμN  NMOS mobility", 0.015, False),
          ("ΔkμN  PG–PD mobility", 0.015, False), ("kμP  PMOS mobility", 0.008, False),
          ("ΔkσN  PG–PD local-σ", 0.001, False)]
    cd = CategoryChartData()
    cd.categories = [n for n, _, _ in reversed(st)]
    cd.add_series("ST", [v for _, v, _ in reversed(st)])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, *emu(3.8, 21, 55, 64), cd)
    ch = gf.chart
    ch.has_legend = ch.has_title = False
    ch.font.size, ch.font.name = Pt(12), BOLD
    plot = ch.plots[0]
    plot.gap_width, plot.has_data_labels = 45, True
    plot.data_labels.number_format, plot.data_labels.number_format_is_linked = "0.000", False
    plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    plot.data_labels.font.size = Pt(12)
    for idx, (_, _, corner) in enumerate(reversed(st)):
        pt_ = plot.series[0].points[idx]
        pt_.format.fill.solid()
        pt_.format.fill.fore_color.rgb = rgb("A6A6A6" if corner else STEEL)
    va = ch.value_axis
    va.visible, va.has_major_gridlines, va.maximum_scale, va.minimum_scale = False, False, 0.5, 0
    ch.category_axis.format.line.color.rgb = rgb("D9D9D9")
    ch.category_axis.tick_labels.font.size = Pt(12)
    rect(s, 20, 87.3, 1.3, 2.3, "A6A6A6")
    text(s, 21.8, 86.8, 14, 3.3, "corner 축", size=12, color=GRAY)
    rect(s, 33, 87.3, 1.3, 2.3, STEEL)
    text(s, 34.8, 86.8, 16, 3.3, "corner 밖 축", size=12, color=STEEL)
    finds = [("0.272 > 0.200", ["NMOS local mismatch(kσN)가", "PMOS Vth corner 축(ΔVth,P)보다", "read 분산에 **더 크게** 기여"]),
             ("≥ 38 %", ["corner 두 축의 합은 **0.61이 상한**", "→ 나머지 7개 축이 분산의 **최소 38 %**"]),
             ("→ DTCO", ["corner만 보면 Vmin을 **낙관적**으로 잡는다", "개선 우선순위는 **분산 기여 순**"])]
    for i, (big, body) in enumerate(finds):
        y0 = 21 + i * 22.3
        text(s, 62.5, y0, 33.7, 7, big, size=28 if i < 2 else 24, color=STEEL, bold=True)
        text(s, 62.5, y0 + 7, 33.7, 12, body, size=15, emph=STEEL, spacing=1.05)
        if i < 2:
            hline(s, 62.5, y0 + 20.5, 33.7)

    # 7. Inverse / DTCO scenario (figure + label-row) -------------------------
    s = frame(prs, 7, "Vmin 목표를 50 mV 낮추려면 무엇을 얼마나 바꿔야 하나", NOTES[7],
              kicker="③ 가역성 — 목표 Vmin → 공정 사양", role=3,
              foot="나머지 축을 고정한 조건부 1차원 이분 탐색 · 필요 수준은 read(FSG)·write(SFG) 한계 corner가 모두 0.575 V를 통과하는 값")
    picture(s, FIG / "fig5_inverse.png", 3.8, 21, h=62)
    text(s, 3.9, 84.3, 41, 5, "셀 Vmin = max(read, write) · 빨강 점선 = read 경계, 노랑 = write 경계 (0.625 V)",
         size=11, color=GRAY)
    text(s, 49, 21, 47.2, 9, "현재 0.625 V → 목표 **0.575 V**: read 한계 FSG가 **+21.1 mV**, write 한계 SFG가 **+18.3 mV** 초과",
         size=16, emph=BLUE, spacing=1.2)
    levers = [("NMOS local-σ", "σ −10.9 %", "단일 수단 중 가장 작은 요구", BLUE),
              ("NMOS + PMOS\nlocal-σ", "각 σ −7.8 %", "부담을 두 축에 나눈다", BLUE),
              ("Global Vth\ncorner", "PDK offset −47 %", "corner 폭을 절반 가까이 좁혀야", BLUE),
              ("PMOS local-σ", "−30 %에도 부족", "이 축만으로는 도달하지 못한다", NEUTRAL)]
    for i, (lab, need, note, col) in enumerate(levers):
        y0 = 32 + i * 12.4
        rect(s, 49, y0, 15.5, 12.4, col)
        text(s, 49.5, y0, 14.5, 12.4, lab.split("\n"), size=14, color=WHITE, bold=True, align="c", anchor="m", spacing=1.0)
        text(s, 67, y0 + 1.8, 29, 5, need, size=20, color=BLUE if col == BLUE else GRAY, bold=True)
        text(s, 67, y0 + 7.3, 29, 4, note, size=13, color=GRAY)
        if i:
            hline(s, 49, y0, 15.5, color=WHITE, pt=5)
            hline(s, 64.5, y0, 31.7)
    text(s, 49, 83.5, 47.2, 7, "Vth shift 역복원 RMSE **ΔVth,N 1.46 mV · ΔVth,P 1.94 mV** — 질의마다 추가 simulation **0회**",
         size=14, emph=BLUE, spacing=1.2)

    # 8. Cost (before → after) -------------------------------------------------
    s = frame(prs, 8, "학습 budget을 53배 줄여도 read Vmin 오차는 +3.5 mV", NOTES[8],
              kicker="④ 비용 — simulation을 얼마나 줄일 수 있나?", role=4,
              foot="53×는 조건 수·전압 레벨·MC 표본 수로 계산한 budget 비율 (HSPICE wall-clock 실측 아님) · MC 깊이 절감은 noise emulation")
    rows = [("공정 조건 수", "1,700", "400"), ("전압 레벨", "5", "4  (0.8 V 제외)"),
            ("조건당 MC 표본", "5,000", "500"), ("총 MC 표본", "4,250만", "80만"),
            ("Read Vmin RMSE", "3.98 mV", "7.51 mV  (+3.5)"), ("Write (42.5× 절감)", "5.65 mV", "8.46 mV  (+2.8)")]
    for x, head in ((3.8, "기준 campaign"), (60.6, "절감 campaign")):
        text(s, x, 21.5, 35.6, 5, head, size=20, bold=True)
        hline(s, x, 27.3, 35.6, color="D9D9D9", pt=1)
    for i, (lab, before, after) in enumerate(rows):
        y0 = 29 + i * 8.6
        for x, val, strong in ((3.8, before, False), (60.6, after, True)):
            text(s, x, y0, 15, 7.5, lab, size=13, color=GRAY, anchor="m")
            text(s, x + 15, y0, 20.6, 7.5, f"**{val}**" if strong else val, size=19, anchor="m")
            hline(s, x, y0 + 8.1, 35.6, pt=0.75)
    rect(s, 41.8, 43, 16.4, 13, "D9D9D9", shape=MSO_SHAPE.RIGHT_ARROW)
    text(s, 40, 30, 20, 11, "53×", size=44, bold=True, align="c", anchor="b")
    text(s, 40, 57.5, 20, 4, "read budget 절감", size=13, color=GRAY, align="c")
    rect(s, 3.8, 83, 92.4, 8, BLACK)
    text(s, 5.5, 83, 89, 8, "학습이 끝나면 what-if · 역방향 질의는 추가 MC 0회 — 비용은 한 번만 낸다",
         size=18, color=WHITE, bold=True, anchor="m", align="c")

    # 9. Summary (key-message bullets) ---------------------------------------
    s = frame(prs, 9, "정리: simulation campaign 한 번으로 네 질문에 답한다", NOTES[9])
    msgs = [(1, "hold-out Vmin 오차 **read 3.98 mV · write 5.65 mV**, 미학습 corner에서도 **최악 corner 일치**"),
            (2, "**local NMOS mismatch**가 PMOS corner 축보다 크고, read 분산의 **38 % 이상이 corner 밖**"),
            (3, "목표 Vmin에서 **공정 사양을 역산** — 50 mV 낮추려면 **NMOS local-σ −10.9 %**"),
            (4, "budget **53배 절감에 +3.5 mV**, 학습 후 질의는 **추가 MC 0회**")]
    for i, (role, m) in enumerate(msgs):
        y0 = 17 + i * 12.5
        rect(s, 4.3, y0 + 3.3, 1.6, 2.8, ROLE[role])
        text(s, 7.5, y0, 88.7, 9.4, m, size=19, emph=ROLE[role], anchor="m")
        hline(s, 3.8, y0 + 11, 92.4)
    text(s, 7.5, 68.5, 88.7, 10, "**한계** — margin을 Gaussian으로 가정 (tail 형상 보정은 후속) · 역해는 나머지 축을 고정한 조건부 경계 · 기준값은 silicon이 아닌 HSPICE MC",
         size=14, color=GRAY, emph=GRAY, spacing=1.3)
    text(s, 60, 82, 36.2, 8, "감사합니다", size=28, color=NAVY, bold=True, align="r", anchor="m")
    return prs


def write_script(path: Path) -> None:
    lines = ["# SRAM Vmin surrogate — 5분 발표 대본 (한국어)", "",
             "슬라이드 `SRAM_Vmin_5min_KR.pptx`의 노트에도 같은 대본이 들어 있다. 수치 출처는 `SRAM_Vmin_IEEE_KR.docx`.", ""]
    for n, t in NOTES.items():
        lines += [f"## {n}. ({TIMES[n]})", "", t, ""]
    total = sum(len(re.sub(r"\s", "", t)) for t in NOTES.values())
    lines += ["---", "", f"공백 제외 {total}자 · 분당 약 330자 기준 약 {total / 330:.1f}분."]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    build().save(OUT)
    write_script(HERE / "SCRIPT_5min_KR.md")
    print("saved", OUT)
