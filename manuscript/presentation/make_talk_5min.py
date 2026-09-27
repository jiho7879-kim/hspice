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
TF = HERE / "talk_figs"
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


def fit(slide, path, x, y, w, h, valign="t"):
    """그림을 [x, y, w, h] 상자 안에 비율 유지로 맞춰 가로 가운데 정렬."""
    from PIL import Image
    iw, ih = Image.open(path).size
    bw, bh = W * w / 100, H * h / 100
    scale = min(bw / iw, bh / ih)
    pw, ph = iw * scale, ih * scale
    left = W * x / 100 + (bw - pw) / 2
    top = H * y / 100 + ({"t": 0, "m": (bh - ph) / 2, "b": bh - ph}[valign])
    return slide.shapes.add_picture(str(path), Emu(round(left)), Emu(round(top)), Emu(round(pw)), Emu(round(ph)))


def chip(slide, x, y, w, h, label, fill, color=WHITE, size=13, bold=True):
    rect(slide, x, y, w, h, fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    text(slide, x + 0.6, y, w - 1.2, h, label, size=size, color=color, bold=bold, align="c", anchor="m")


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
    1: "SRAM Vmin을 순방향과 역방향으로 함께 추정하는 physics-guided surrogate를 소개하겠습니다.",
    2: "출발점은 고객 VOC였습니다. Vmin은 더 낮추고, 성능도 같이 올려 달라는 요구였습니다. "
       "목표를 0.575 V로 잡으면 지금은 read가 21 mV, write가 18 mV 모자랍니다. "
       "공정 쪽에서 움직일 수 있는 knob은 셀의 PU, PD, PG마다 Vth, local mismatch, mobility가 있습니다. "
       "그런데 이 중 어느 knob이 Vmin에 가장 잘 듣는지, 얼마나 움직여야 하는지 빨리 비교할 방법이 없었습니다.",
    3: "기존 방법은 둘입니다. 왼쪽 그림처럼 MC는 학습 조건 하나에 수천 번을 돌려야 하고, corner는 별 네 개, 네 점만 봅니다. "
       "오른쪽은 margin 분포입니다. 평균이 같아도 local mismatch로 σ가 커지면 tail이 0을 넘어가고, 그만큼 Vmin이 올라갑니다. "
       "corner로는 이게 안 보여서 Vmin을 낙관적으로 잡기 쉽습니다.",
    4: "그래서 simulation은 한 번만 돌리고, 그 결과에 여러 번 묻기로 했습니다. "
       "이 조건의 Vmin은 얼마인지, 어느 축이 Vmin을 흔드는지, 목표를 맞추려면 얼마나 바꿔야 하는지, simulation은 얼마나 줄일 수 있는지. "
       "뒤에서 이 네 가지를 같은 색으로 짚겠습니다.",
    5: "구현은 단순합니다. 입력은 오른쪽 표처럼 Vth shift, local-σ, mobility를 NMOS 공통, pass-gate와 pull-down 사이 skew, PMOS로 나눈 9개 축과 공급 전압입니다. "
       "HSPICE MC 결과로 GP 두 개를 학습합니다. 하나는 margin 평균 μ, 하나는 산포 log σ입니다. "
       "Vmin은 따로 배우지 않습니다. 그림처럼 μ에서 kσ를 뺀 선이 0이 되는 가장 낮은 전압이 Vmin입니다. "
       "이렇게 나눠 두면 Vmin이 밀린 원인이 중심인지 산포인지 보이고, 역산도 1차원 이분 탐색으로 끝납니다.",
    6: "정확도부터 보겠습니다. 학습에 안 쓴 조건에서 Vmin 오차는 read 3.98 mV, write 5.65 mV RMSE입니다. "
       "학습에서 뺀 PDK corner 네 곳에서도 8.5 mV와 5.8 mV이고, read는 FSG, write는 SFG로 최악 corner를 제대로 짚었습니다. "
       "기준값은 따로 돌린 HSPICE MC입니다.",
    7: "다음은 어느 축이 Vmin을 흔드는지입니다. total-order Sobol 지수로 read margin 분산을 나눠 보면, "
       "NMOS local mismatch가 0.272로 corner 축인 PMOS Vth shift 0.200보다 큽니다. "
       "corner 두 축을 합쳐도 0.61이 상한이라, 적어도 38 %는 corner 밖에서 나옵니다. "
       "성능 쪽 knob인 mobility 축은 0.015 이하로 작았습니다. VOC 대응 action을 어떤 순서로 볼지 이 결과로 정했습니다.",
    8: "이제 VOC로 돌아가겠습니다. 앞에서 본 read 21 mV, write 18 mV 차이를 없애려면 무엇을 얼마나 바꿔야 할까요. "
       "나머지 축을 고정하고 knob 하나씩 거꾸로 풀면, NMOS local-σ를 10.9 % 줄이는 게 가장 작은 변화였습니다. "
       "NMOS와 PMOS에 나누면 각각 7.8 %면 되고, PMOS local-σ만으로는 30 %를 줄여도 닿지 않습니다. "
       "공정 action 후보를 simulation을 더 돌리지 않고 이렇게 바로 비교할 수 있었던 게 가장 쓸모 있었습니다.",
    9: "비용입니다. 기준 학습은 1,700개 조건, 전압 5개, 조건당 MC 5,000개였습니다. "
       "400개 조건, 전압 4개, MC 500개로 줄이면 budget은 53배 줄고 read 오차는 3.5 mV 늡니다. "
       "한 번 학습해 두면 이후 질의에는 MC가 더 들지 않습니다.",
    10: "정리하면, simulation을 한 번 돌려 정확도, 민감도, 역산, 비용 네 가지에 답했고, 실제 VOC에서 어떤 공정 action이 효과적인지 고르는 데 썼습니다. "
        "다만 margin을 Gaussian으로 가정했고, 역산은 나머지 축을 고정한 결과라는 한계가 있습니다. 감사합니다.",
}
TIMES = {1: "0:00–0:10", 2: "0:10–0:45", 3: "0:45–1:15", 4: "1:15–1:40", 5: "1:40–2:20",
         6: "2:20–2:50", 7: "2:50–3:25", 8: "3:25–4:05", 9: "4:05–4:30", 10: "4:30–4:55"}


def build() -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H

    # 1. Cover (full-bleed, 단색) ---------------------------------------------
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, 100, 100, NAVY)
    text(s, 5, 27, 90, 12, "SRAM Vmin 순·역방향 추정", size=48, color=WHITE, bold=True, align="c", anchor="m")
    text(s, 5, 41, 90, 6, "공정 변동을 반영한 physics-guided surrogate", size=24, color=WHITE, align="c")
    hline(s, 44, 51.5, 12, color="8BB2EB", pt=1)
    text(s, 5, 54, 90, 4, "Gaussian process  ·  Sobol 민감도  ·  공정 사양 역산", size=16, color="B9C6F0", align="c")
    text(s, 5, 78, 90, 4, "[발표자]  ·  [소속]", size=18, color=WHITE, align="c")
    text(s, 5, 84, 90, 3.5, "2026", size=14, color="B9C6F0", align="c")
    s.notes_slide.notes_text_frame.text = NOTES[1]

    # 2. Case — 고객 VOC (VOC bubble + Vmin gap chart | 6T knob map) ----------
    s = frame(prs, 2, "사례: 고객이 Vmin은 낮추고 성능은 올려 달라고 했다", NOTES[2],
              foot="knob 이름은 이 연구의 9개 공정 축에 맞췄다 · 고객명과 제품 정보는 생략 · 막대는 surrogate가 계산한 한계 corner의 Vmin")
    bub = rect(s, 3.8, 16.2, 43, 12.5, "EEF1FB", shape=MSO_SHAPE.ROUNDED_RECTANGULAR_CALLOUT, line=NAVY, lw=1.25)
    bub.adjustments[0], bub.adjustments[1] = -0.30, 0.78
    text(s, 5.2, 16.9, 40, 3.5, "고객 VOC", size=12, color=GRAY, bold=True)
    text(s, 5.2, 20.6, 40, 6, "“Vmin은 더 낮게, 성능은 더 좋게”", size=21, color=NAVY, bold=True)
    text(s, 3.9, 33, 43, 4, "새 목표 0.575 V까지 남은 거리", size=15, bold=True)
    fit(s, TF / "s2_vmin_target.png", 3.8, 37.5, 43, 45)
    text(s, 51.5, 16.4, 44.7, 4, "공정에서 움직일 수 있는 knob", size=15, bold=True)
    fit(s, TF / "s2_cell6t.png", 51.5, 21, 44.7, 38)
    chip(s, 51.5, 60.5, 11, 5.4, "PU (PMOS)", BLUE)
    text(s, 63.5, 60.5, 32.7, 5.4, "Vth,P · local-σP · mobility μP", size=14, anchor="m")
    chip(s, 51.5, 67.4, 11, 5.4, "PD·PG (NMOS)", NAVY)
    text(s, 63.5, 67.4, 32.7, 5.4, "Vth,N · local-σN · mobility μN · PG–PD skew", size=14, anchor="m")
    for i, q in enumerate(("어느 knob이 잘 듣나?", "얼마나 움직여야 하나?", "read·write 동시에?")):
        chip(s, 51.5 + i * 15.1, 75, 14.4, 5.4, q, "F2F2F2", color=BLACK, size=12)
    rect(s, 3.8, 84, 92.4, 7.5, NAVY)
    text(s, 5.5, 84, 89, 7.5, "knob마다 MC를 다시 돌리지 않고 한자리에서 비교할 방법이 필요했다",
         size=19, color=WHITE, bold=True, anchor="m", align="c")

    # 3. Background — 비용 vs 사각지대 (figure pair) ----------------------------
    s = frame(prs, 3, "기존 방법은 느리거나, 산포를 놓친다", NOTES[3],
              foot="왼쪽 점은 학습 조건 분포를 보여 주는 예시 (실제 조건은 9차원) · 오른쪽은 개념도 · Vmin: margin tail이 0에 닿는 가장 낮은 VDD")
    text(s, 3.9, 15.6, 44, 4.5, "비용 — MC는 조건마다 수천 번, corner는 4점", size=17, color=NAVY, bold=True)
    text(s, 51.5, 15.6, 44.7, 4.5, "사각지대 — Vmin은 분포의 tail이 정한다", size=17, color=BLACK, bold=True)
    fit(s, TF / "s3_plane.png", 3.8, 21, 44, 60)
    fit(s, TF / "s3_tail.png", 51.5, 21, 44.7, 60)
    vline(s, 49.65, 16, 75)
    hline(s, 3.8, 82.3, 92.4)
    text(s, 3.9, 83.5, 44, 7, ["**MC**: 정확하지만 knob을 바꿀 때마다 **처음부터 다시**"], size=16, emph=NAVY, anchor="m")
    text(s, 51.5, 83.5, 44.7, 7, ["**corner**: 빠르지만 σ가 커지는 건 **못 본다** → Vmin **낙관**"], size=16, emph=BLACK, anchor="m")

    # 4. Goal — 네 질문 (cards with real-result thumbnails) --------------------
    s = frame(prs, 4, "목표: simulation은 한 번만, 질문은 여러 번", NOTES[4],
              foot="썸네일은 뒤 장표의 실제 결과 · 이미 돌린 HSPICE MC를 계속 물어볼 수 있는 모델로 바꾼다")
    cards = [("① 정확도", "이 조건에서\nVmin은 얼마?", "t1_accuracy", "GP surrogate"),
             ("② 민감도", "Vmin을 흔드는\n축은 어디?", "t2_sobol", "Sobol 지수"),
             ("③ 역산", "목표를 맞추려면\n얼마나?", "t3_inverse", "1차원 이분 탐색"),
             ("④ 비용", "simulation은\n얼마나 줄이나?", "t4_cost", "budget 절감 실험")]
    for i, (head_, q, thumb, tool) in enumerate(cards):
        x, col = (3.8, 27.8, 51.8, 75.7)[i], ROLE[i + 1]
        rect(s, x, 15.8, 20.3, 9, col)
        text(s, x, 15.8, 20.3, 9, head_, size=22, color=WHITE, bold=True, align="c", anchor="m")
        text(s, x + 0.5, 27.5, 19.3, 11, q.split("\n"), size=19, color=col, bold=True, align="c", spacing=1.1)
        fit(s, TF / f"{thumb}.png", x + 0.5, 41, 19.3, 30, valign="m")
        text(s, x, 74, 20.3, 3.5, "쓰는 도구", size=12, color=GRAY, align="c")
        text(s, x, 78, 20.3, 5, tool, size=18, color=col, bold=True, align="c")
        if i:
            vline(s, x - 1.95, 15.8, 77.3)

    # 5. Method — pipeline (chevron band + concept figure + 3x3 axis grid) ----
    s = frame(prs, 5, "구현: Vmin을 바로 배우지 않고 μ와 σ를 따로 배운다", NOTES[5],
              foot="k: array 크기와 목표 fail 확률로 정하는 tail 배율 · σ GP는 log σ에 full-ARD kernel · read(125 °C)와 write(−40 °C)는 따로 학습")
    steps = [("입력", "9개 공정 축 + VDD\nHSPICE MC 1,700 조건"), ("학습 ①", "GP: margin 평균 μ"),
             ("학습 ②", "GP: margin 산포 log σ"), ("계산", "μ − k·σ ≥ 0이 되는\n가장 낮은 VDD = Vmin")]
    fills = (NAVY, "2C47C0", "4F65E9", BLUE)
    seg = 92.9 / 4
    for i, (lab, body) in enumerate(steps):
        x = 3.6 + i * seg
        text(s, x, 14.3, seg, 4.3, lab, size=18, color=fills[i], bold=True, align="c")
        shp = MSO_SHAPE.PENTAGON if i == 0 else MSO_SHAPE.CHEVRON
        rect(s, x, 19.9, seg + (1.2 if i < 3 else 0), 10.5, fills[i], shape=shp)
        text(s, x + (1.5 if i else 0.8), 19.9, seg - 3.2, 10.5, body.split("\n"), size=14, color=WHITE,
             bold=True, align="c", anchor="m", spacing=1.0)
    fit(s, TF / "s5_mu_sigma.png", 3.8, 33.5, 50, 58)
    text(s, 57, 33.5, 39.2, 4.5, "입력 9개 축 = 3종 × 3위치", size=16, color=BLUE, bold=True)
    cols = ("NMOS 공통", "PG–PD skew", "PMOS")
    grid = [("Vth shift", ("ΔVth,N", "ΔVth,skew", "ΔVth,P")),
            ("local-σ", ("kσN", "ΔkσN", "kσP")),
            ("mobility", ("kμN", "ΔkμN", "kμP"))]
    for j, c in enumerate(cols):
        text(s, 68.5 + j * 9.25, 39.5, 9, 4, c, size=12, color=GRAY, bold=True, align="c")
    for i, (row, cells) in enumerate(grid):
        y0 = 44 + i * 8.6
        text(s, 57, y0, 11, 8, row, size=14, color=BLUE, bold=True, anchor="m")
        for j, sym in enumerate(cells):
            corner = sym in ("ΔVth,N", "ΔVth,P")
            rect(s, 68.5 + j * 9.25, y0 + 0.3, 8.9, 7.8, "E4E4E4" if corner else "E3ECFB")
            text(s, 68.5 + j * 9.25, y0 + 0.3, 8.9, 7.8, sym, size=13, bold=True, align="c", anchor="m",
                 color="595959" if corner else NAVY)
    text(s, 68.5, 70.3, 27.7, 3.5, "회색 = PDK corner가 다루는 축", size=11, color=GRAY)
    text(s, 57, 76, 39.2, 14, ["**μ·σ로 나누면** Vmin이 밀린 원인이 보인다", "**식이 VDD에 단조** → 역산은 1차원 이분 탐색"],
         size=15, emph=NAVY, spacing=1.35)

    # 6. Forward accuracy (figure + KPI stack) --------------------------------
    s = frame(prs, 6, "처음 보는 조건에서도 Vmin 오차는 수 mV", NOTES[6],
              kicker="① 정확도 — 이 조건에서 Vmin은 얼마?", role=1,
              foot="기준값은 따로 돌린 HSPICE MC (silicon 측정 아님) · hold-out 300개 조건 중 판정 가능한 read 245개, write 228개")
    picture(s, FIG / "fig3_forward.png", 3.8, 21.5, w=60.5)
    text(s, 3.9, 69, 60, 8, ["대각선에 붙을수록 정확하고, 회색 띠는 ±10 mV",
                             "왼쪽 read (SNM, 125 °C), 오른쪽 write (Vtrip, −40 °C)"], size=13, color=GRAY, spacing=1.3)
    blocks = [("Hold-out Vmin RMSE", ("3.98", "mV", "Read"), ("5.65", "mV", "Write")),
              ("학습에서 뺀 PDK corner 4개 RMSE", ("8.5", "mV", "Read"), ("5.8", "mV", "Write")),
              ("최악 corner", ("FSG ✓", "", "Read"), ("SFG ✓", "", "Write"))]
    for i, (lab, a, b) in enumerate(blocks):
        y0 = 21.5 + i * 22.5
        text(s, 67.5, y0, 28.7, 4, lab, size=14, bold=True)
        for j, (v, u, m) in enumerate((a, b)):
            kpi(s, 67.5 + j * 14.4, y0 + 5, 14.3, v, u, m, NAVY, size=30 if u else 24)
        vline(s, 81.85, y0 + 5.5, 10, color="D9D9D9", pt=0.75)
        if i < 2:
            hline(s, 67.5, y0 + 20.5, 28.7)

    # 7. Sensitivity (bar chart + findings) -----------------------------------
    s = frame(prs, 7, "Read margin 분산의 38 % 이상이 corner 밖에서 나온다", NOTES[7],
              kicker="② 민감도 — Vmin을 흔드는 축은 어디?", role=2,
              foot="total-order Sobol 지수 ST · read margin z, VDD = 0.625 V · 9개 축 전 범위 · 상호작용이 겹쳐 합이 1을 넘을 수 있다")
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
    finds = [("0.272 > 0.200", ["NMOS local mismatch(kσN)가", "PMOS Vth corner 축(ΔVth,P)보다", "read 분산에 **더 크게** 기여한다"]),
             ("≥ 38 %", ["corner 두 축을 합쳐도 **0.61이 상한**", "→ 나머지 7개 축 몫이 **최소 38 %**"]),
             ("→ VOC 대응", ["corner만 보면 Vmin을 **낙관적**으로 잡는다", "action은 **기여가 큰 축부터** 본다"])]
    for i, (big, body) in enumerate(finds):
        y0 = 21 + i * 22.3
        text(s, 62.5, y0, 33.7, 7, big, size=28 if i < 2 else 24, color=STEEL, bold=True)
        text(s, 62.5, y0 + 7, 33.7, 12, body, size=15, emph=STEEL, spacing=1.05)
        if i < 2:
            hline(s, 62.5, y0 + 20.5, 33.7)

    # 8. Inverse — VOC 답 (figure + label-row) --------------------------------
    s = frame(prs, 8, "VOC 답: Vmin 50 mV는 NMOS local-σ 10.9 %면 닿는다", NOTES[8],
              kicker="③ 역산 — 목표 Vmin에서 공정 사양으로", role=3,
              foot="나머지 축을 고정하고 한 축씩 이분 탐색 · 필요 수준 = read(FSG)와 write(SFG) 한계 corner가 모두 0.575 V를 통과하는 값")
    picture(s, FIG / "fig5_inverse.png", 3.8, 21, h=62)
    text(s, 3.9, 84.3, 41, 5, "셀 Vmin = max(read, write), 빨강 점선은 read 경계, 노랑은 write 경계 (0.625 V)",
         size=11, color=GRAY)
    text(s, 49, 21, 47.2, 9, ["지금 0.625 V → 목표 **0.575 V**",
                              "read 한계 FSG는 **21.1 mV**, write 한계 SFG는 **18.3 mV** 넘친다"],
         size=16, emph=BLUE, spacing=1.2)
    levers = [("NMOS local-σ", "σ −10.9 %", "knob 하나로는 가장 작은 변화", BLUE),
              ("NMOS + PMOS\nlocal-σ", "각각 σ −7.8 %", "두 축에 나눠 부담", BLUE),
              ("Global Vth\ncorner", "PDK offset −47 %", "corner 폭을 절반 가까이 줄여야", BLUE),
              ("PMOS local-σ", "−30 %로도 부족", "이 축 하나로는 닿지 않는다", NEUTRAL)]
    for i, (lab, need, note, col) in enumerate(levers):
        y0 = 32 + i * 12.4
        rect(s, 49, y0, 15.5, 12.4, col)
        text(s, 49.5, y0, 14.5, 12.4, lab.split("\n"), size=14, color=WHITE, bold=True, align="c", anchor="m", spacing=1.0)
        text(s, 67, y0 + 1.8, 29, 5, need, size=20, color=BLUE if col == BLUE else GRAY, bold=True)
        text(s, 67, y0 + 7.3, 29, 4, note, size=13, color=GRAY)
        if i:
            hline(s, 49, y0, 15.5, color=WHITE, pt=5)
            hline(s, 64.5, y0, 31.7)
    text(s, 49, 83.5, 47.2, 7, ["Vth shift 역산 오차 **ΔVth,N 1.46 mV · ΔVth,P 1.94 mV**",
                                "질의할 때 simulation을 더 돌리지 않는다"],
         size=14, emph=BLUE, spacing=1.2)

    # 9. Cost (bar charts + recipe) ------------------------------------------
    s = frame(prs, 9, "학습 budget을 53배 줄이면 read 오차는 +3.5 mV", NOTES[9],
              kicker="④ 비용 — simulation은 얼마나 줄이나?", role=4,
              foot="53×는 조건 수·전압 레벨·MC 표본 수로 계산한 budget 비율 (HSPICE 실행 시간을 잰 값 아님) · MC 깊이 절감은 noise emulation")
    fit(s, TF / "s9_cost.png", 3.8, 21.5, 62, 60, valign="m")
    text(s, 69, 22, 27.2, 4.5, "줄인 학습 recipe", size=16, bold=True)
    for i, (lab, before, after) in enumerate((("공정 조건", "1,700", "400"), ("VDD 레벨", "5", "4"),
                                              ("조건당 MC", "5,000", "500"))):
        y0 = 28 + i * 9
        hline(s, 69, y0, 27.2, pt=0.75)
        text(s, 69, y0 + 0.8, 10, 7, lab, size=13, color=GRAY, anchor="m")
        text(s, 79, y0 + 0.8, 17.2, 7, f"{before}  →  **{after}**", size=18, emph=BLACK, anchor="m")
    hline(s, 69, 55, 27.2, pt=0.75)
    text(s, 69, 58, 27.2, 12, ["read **53×**, write **42.5×** 절감", "오차는 read **+3.5 mV**, write **+2.8 mV**"],
         size=15, emph=BLACK, spacing=1.35)
    rect(s, 3.8, 83, 92.4, 8, BLACK)
    text(s, 5.5, 83, 89, 8, "한 번 학습해 두면 what-if와 역산 질의에는 MC가 더 들지 않는다",
         size=18, color=WHITE, bold=True, anchor="m", align="c")

    # 10. Summary — 네 질문의 답 (cards mirror slide 4) ------------------------
    s = frame(prs, 10, "정리: 한 번 돌린 simulation으로 VOC에 답했다", NOTES[10])
    answers = [("① 정확도", "t1_accuracy", "3.98 mV", ["hold-out read RMSE", "write 5.65 mV · 최악 corner 일치"]),
               ("② 민감도", "t2_sobol", "≥ 38 %", ["read 분산 중 corner 밖 몫", "kσN 0.272 > ΔVth,P 0.200"]),
               ("③ 역산", "t3_inverse", "σN −10.9 %", ["VOC −50 mV의 가장 작은 action", "추가 simulation 없이"]),
               ("④ 비용", "t4_cost", "53×", ["학습 budget 절감", "대가는 read +3.5 mV"])]
    for i, (head_, thumb, big, cap) in enumerate(answers):
        x, col = (3.8, 27.8, 51.8, 75.7)[i], ROLE[i + 1]
        rect(s, x, 15.8, 20.3, 7.5, col)
        text(s, x, 15.8, 20.3, 7.5, head_, size=18, color=WHITE, bold=True, align="c", anchor="m")
        fit(s, TF / f"{thumb}.png", x + 1, 25, 18.3, 25, valign="m")
        text(s, x, 51.5, 20.3, 7.5, big, size=28, color=col, bold=True, align="c", anchor="m")
        text(s, x, 59.5, 20.3, 8, cap, size=12, color="404040", align="c", spacing=1.2)
        if i:
            vline(s, x - 1.95, 15.8, 53)
    rect(s, 3.8, 71, 92.4, 7.5, NAVY)
    text(s, 5.5, 71, 89, 7.5, "공정 action 우선순위를 simulation 추가 없이 정할 수 있었다",
         size=19, color=WHITE, bold=True, anchor="m", align="c")
    text(s, 3.9, 81, 60, 9, ["**한계** — margin은 Gaussian 가정 (tail 보정은 후속 연구)",
                             "역산은 나머지 축을 고정한 결과 · 기준값은 silicon이 아닌 HSPICE MC"],
         size=12, color=GRAY, emph=GRAY, spacing=1.3)
    text(s, 66, 80.5, 30.2, 9, "감사합니다", size=28, color=NAVY, bold=True, align="r", anchor="m")
    return prs


def write_script(path: Path) -> None:
    lines = ["# SRAM Vmin surrogate — 5분 발표 대본", "",
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
