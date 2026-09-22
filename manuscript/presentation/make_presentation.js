#!/usr/bin/env node
"use strict";

/**
 * Generates the editable Korean presentation deck for the SRAM Vmin surrogate
 * paper.  The deck deliberately separates (1) validated surrogate error from
 * (2) metric/tail-model risk and (3) silicon qualification; see the companion
 * PRESENTATION_GUIDE_KR.md for the detailed figure-by-figure narration.
 *
 * Run from the repository root:
 *   node manuscript/presentation/make_presentation.js
 */

const path = require("path");
const PptxGenJS = require("pptxgenjs");
const { imageSize } = require("image-size");

const ROOT = path.resolve(__dirname, "../..");
const FIGURES = path.join(ROOT, "manuscript", "figures");
const OUT = path.join(__dirname, "SRAM_Vmin_Surrogate_Presentation_KR.pptx");

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "SRAM Vmin surrogate project";
pptx.company = "";
pptx.subject = "SRAM Vmin Gaussian-process surrogate presentation";
pptx.title = "9차원 공정 window에서의 SRAM Vmin 순·역방향 추정";
pptx.lang = "ko-KR";
pptx.theme = {
  headFontFace: "Malgun Gothic",
  bodyFontFace: "Malgun Gothic",
  lang: "ko-KR",
};
pptx.defineLayout({ name: "CUSTOM_WIDE", width: 13.333, height: 7.5 });
pptx.layout = "CUSTOM_WIDE";
pptx.margin = 0;

const S = { W: 13.333, H: 7.5 };
const C = {
  ink: "10243E",
  midnight: "081A2B",
  navy: "0B3459",
  blue: "006B9A",
  teal: "007C83",
  mint: "AEE7DA",
  mist: "EAF3F6",
  sky: "DCEEF5",
  paper: "FFFFFF",
  pale: "F6F9FB",
  gray: "5C6E7C",
  line: "C7D6DE",
  orange: "D76A26",
  gold: "F0B44D",
  rose: "E37676",
  lightRose: "FAE9E8",
  green: "398C68",
  violet: "6554A8",
};
const FONT = "Malgun Gothic";
const FONT_FALLBACK = "Arial";

function tx(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x, y, w, h,
    fontFace: opts.fontFace || FONT,
    fontSize: opts.fontSize || 16,
    color: opts.color || C.ink,
    bold: opts.bold || false,
    italic: opts.italic || false,
    align: opts.align || "left",
    valign: opts.valign || "mid",
    margin: opts.margin ?? 0,
    breakLine: false,
    fit: "shrink",
    paraSpaceAfterPt: opts.paraSpaceAfterPt || 0,
    lineSpacingMultiple: opts.lineSpacingMultiple || 0,
    transparency: opts.transparency,
  });
}

function shape(slide, type, x, y, w, h, opts = {}) {
  slide.addShape(type, {
    x, y, w, h,
    fill: opts.fill ? { color: opts.fill, transparency: opts.transparency || 0 } : { color: "FFFFFF", transparency: 100 },
    line: opts.line === false ? { color: "FFFFFF", transparency: 100 } : {
      color: opts.line || C.line,
      width: opts.lineWidth || 1,
      transparency: opts.lineTransparency || 0,
    },
    radius: opts.radius,
  });
}

function addPage(slide, n, label = "SRAM Vmin surrogate") {
  tx(slide, label, 0.55, 7.10, 4.3, 0.16, { fontSize: 8.5, color: C.gray, fontFace: FONT_FALLBACK });
  tx(slide, String(n).padStart(2, "0"), 12.16, 7.07, 0.55, 0.20, { fontSize: 9, color: C.gray, align: "right", fontFace: FONT_FALLBACK });
}

function tag(slide, text, x, y, color = C.teal, width = 1.35) {
  shape(slide, pptx.ShapeType.roundRect, x, y, width, 0.33, { fill: color, line: false });
  tx(slide, text, x + 0.08, y + 0.01, width - 0.16, 0.28, { fontSize: 9, color: C.paper, bold: true, align: "center" });
}

function title(slide, label, headline, sub = "") {
  tag(slide, label, 0.58, 0.42, C.teal, Math.max(1.14, label.length * 0.17 + 0.40));
  tx(slide, headline, 0.58, 0.84, 12.05, 0.55, { fontSize: 30, bold: true, color: C.ink });
  if (sub) tx(slide, sub, 0.60, 1.42, 11.9, 0.34, { fontSize: 13, color: C.gray });
}

function note(slide, text) {
  slide.addNotes(text);
}

function card(slide, x, y, w, h, opts = {}) {
  const fill = opts.fill || C.paper;
  shape(slide, pptx.ShapeType.roundRect, x, y, w, h, {
    fill,
    line: opts.line || C.line,
    lineWidth: opts.lineWidth || 0.7,
    transparency: opts.transparency || 0,
  });
  if (opts.kicker) tx(slide, opts.kicker, x + 0.18, y + 0.16, w - 0.36, 0.22, { fontSize: 9.2, color: opts.kickerColor || C.teal, bold: true });
  if (opts.headline) tx(slide, opts.headline, x + 0.18, y + (opts.kicker ? 0.47 : 0.20), w - 0.36, opts.headlineHeight || 0.48, { fontSize: opts.headlineSize || 20, color: opts.headlineColor || C.ink, bold: true, valign: "mid" });
  if (opts.body) tx(slide, opts.body, x + 0.18, y + (opts.bodyY || (opts.kicker ? 1.08 : 0.86)), w - 0.36, h - (opts.bodyY || (opts.kicker ? 1.21 : 1.02)), { fontSize: opts.bodySize || 12.5, color: opts.bodyColor || C.gray, valign: "top", lineSpacingMultiple: 1.06 });
}

function formula(slide, text, x, y, w, h, opts = {}) {
  shape(slide, pptx.ShapeType.roundRect, x, y, w, h, { fill: opts.fill || C.mist, line: opts.line || C.sky, lineWidth: 0.8 });
  tx(slide, text, x + 0.15, y + 0.08, w - 0.30, h - 0.16, { fontSize: opts.fontSize || 22, color: opts.color || C.navy, bold: opts.bold ?? true, align: opts.align || "center", fontFace: FONT_FALLBACK });
}

function imageContain(slide, file, x, y, w, h, opts = {}) {
  const size = imageSize(file);
  const scale = Math.min(w / size.width, h / size.height);
  const iw = size.width * scale;
  const ih = size.height * scale;
  const ix = x + (w - iw) / 2;
  const iy = y + (h - ih) / 2;
  if (opts.frame !== false) {
    shape(slide, pptx.ShapeType.roundRect, x, y, w, h, { fill: opts.fill || C.paper, line: opts.line || C.line, lineWidth: 0.7 });
  }
  slide.addImage({ path: file, x: ix, y: iy, w: iw, h: ih, transparency: opts.transparency || 0 });
  return { x: ix, y: iy, w: iw, h: ih };
}

function figureCaption(slide, text, x, y, w) {
  tx(slide, text, x, y, w, 0.24, { fontSize: 9.3, color: C.gray, italic: true, valign: "mid" });
}

function arrow(slide, x1, y1, x2, y2, color = C.teal, width = 1.5) {
  slide.addShape(pptx.ShapeType.line, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color, width, beginArrowType: "none", endArrowType: "triangle" } });
}

function newSlide(bg = C.pale) {
  const slide = pptx.addSlide();
  slide.background = { color: bg };
  return slide;
}

// 1. Title
{
  const slide = newSlide(C.midnight);
  // Repeated motif: translucent circular "samples" becoming a compact surrogate surface.
  [[1.05, 1.13, 0.38, C.mint], [1.58, 0.83, 0.21, C.gold], [2.03, 1.25, 0.31, C.sky], [2.51, 0.75, 0.17, C.rose], [2.83, 1.26, 0.42, C.mint], [3.42, 0.96, 0.22, C.gold]].forEach(([x, y, r, c]) => {
    shape(slide, pptx.ShapeType.ellipse, x, y, r, r, { fill: c, line: false, transparency: 7 });
  });
  shape(slide, pptx.ShapeType.roundRect, 0.68, 0.60, 3.45, 1.40, { fill: C.navy, line: C.teal, lineWidth: 1.1 });
  tx(slide, "HSPICE labels", 1.02, 0.91, 2.77, 0.25, { fontSize: 13, color: C.mint, bold: true, align: "center" });
  tx(slide, "9개 공정 축 + VDD", 0.92, 1.27, 2.98, 0.34, { fontSize: 19, color: C.paper, bold: true, align: "center" });
  arrow(slide, 4.32, 1.31, 5.52, 1.31, C.gold, 2.3);
  shape(slide, pptx.ShapeType.roundRect, 5.68, 0.60, 3.70, 1.40, { fill: "103C55", line: C.mint, lineWidth: 1.1 });
  tx(slide, "GP SURROGATE", 6.10, 0.90, 2.85, 0.27, { fontSize: 13, color: C.mint, bold: true, align: "center", fontFace: FONT_FALLBACK });
  tx(slide, "μ  +  log σ", 6.10, 1.22, 2.85, 0.40, { fontSize: 26, color: C.paper, bold: true, align: "center", fontFace: FONT_FALLBACK });
  arrow(slide, 9.57, 1.31, 10.68, 1.31, C.gold, 2.3);
  shape(slide, pptx.ShapeType.roundRect, 10.86, 0.60, 1.80, 1.40, { fill: C.teal, line: false });
  tx(slide, "Forward\nInverse", 11.05, 0.87, 1.42, 0.70, { fontSize: 18, color: C.paper, bold: true, align: "center", valign: "mid" });
  tx(slide, "9차원 공정 window에서의\nSRAM Vmin 순·역방향 추정", 0.72, 2.66, 11.5, 1.37, { fontSize: 35, color: C.paper, bold: true, valign: "mid" });
  tx(slide, "한 번의 simulation campaign을 여러 설계 질문으로 재사용하는 physics-guided GP surrogate", 0.76, 4.26, 10.95, 0.34, { fontSize: 17, color: C.mint });
  formula(slide, "HSPICE를 대체하는 AI가 아니라  →  HSPICE 결과를 반복 질의 가능한 설계 모델로 전환", 0.75, 5.24, 11.80, 0.65, { fill: "12344A", line: "2C6376", color: C.paper, fontSize: 18 });
  tx(slide, "발표 자료 · 2026-09-23 · 한국어 해설/발표자 노트 포함", 0.76, 6.70, 8.5, 0.22, { fontSize: 10, color: "A9C2CF" });
  note(slide, "핵심 한 문장: 이 연구는 HSPICE/PDK를 AI로 대체하는 것이 아닙니다. 이미 얻은 비싼 회로 simulation 결과를 forward, inverse, sensitivity, scenario에 반복 활용할 수 있는 surrogate 계층으로 만드는 것입니다.");
}

// 2. Problem
{
  const slide = newSlide();
  title(slide, "PROBLEM", "직접 MC는 신뢰할 수 있지만, 질문이 늘수록 비용이 곱셈으로 증가한다.", "corner 네 점만으로는 local mismatch·mobility를 포함한 9D window를 충분히 설명할 수 없다.");
  formula(slide, "공정 조건 수  ×  VDD level 수  ×  조건·전압별 MC sample 수", 0.75, 2.05, 11.85, 0.68, { fontSize: 23 });
  const blocks = [
    ["1", "Direct MC", "새 조건마다 회로 simulation과 mismatch 표본이 필요", C.navy],
    ["2", "Corner check", "대표점은 보지만 연속적인 허용 경계는 주지 못함", C.orange],
    ["3", "Design question", "‘어느 축을 얼마나 바꾸면 되는가?’까지 답해야 함", C.teal],
  ];
  blocks.forEach(([num, head, body, color], i) => {
    const x = 0.77 + i * 4.15;
    shape(slide, pptx.ShapeType.ellipse, x, 3.19, 0.72, 0.72, { fill: color, line: false });
    tx(slide, num, x, 3.30, 0.72, 0.28, { fontSize: 19, color: C.paper, bold: true, align: "center", fontFace: FONT_FALLBACK });
    card(slide, x + 0.91, 2.94, 3.01, 1.32, { kicker: "WHY IT MATTERS", headline: head, headlineSize: 17, body, bodySize: 11.4, bodyY: 0.82 });
  });
  card(slide, 0.76, 5.08, 5.83, 1.32, { fill: C.mist, line: C.sky, kicker: "SURROGATE의 역할", headline: "비싼 label을 ‘질의 가능한 함수’로 압축", headlineSize: 18, body: "학습 이후에는 새로운 what-if / inverse 질문에 추가 MC를 매번 수행하지 않는다.", bodySize: 12.2, bodyY: 0.87 });
  card(slide, 6.76, 5.08, 5.83, 1.32, { fill: C.lightRose, line: "EAB9B5", kicker: "남는 역할", kickerColor: C.orange, headline: "최종 sign-off는 원 회로 simulation과 silicon", headlineSize: 18, body: "surrogate는 screening·우선순위화·후보 생성을 빠르게 한다. 물리 검증을 없애지 않는다.", bodySize: 12.2, bodyY: 0.87 });
  addPage(slide, 2);
  note(slide, "Direct MC 자체가 나쁘다는 뜻이 아닙니다. 한 조건의 통계를 보기에는 좋은 방법입니다. 문제는 공정 조건, 전압, MC 표본이 곱해지고 새 질문마다 재실행해야 한다는 점입니다. surrogate는 이 expensive label을 재사용하는 계층입니다.");
}

// 3. Vmin primer
{
  const slide = newSlide();
  title(slide, "METRIC", "Vmin은 ‘μ−kσ’ 자체가 아니라, lower-tail margin이 0을 넘는 전압이다.", "같은 평균이라도 cell-to-cell mismatch 산포 σ가 크면 tail cell이 먼저 실패한다.");
  // Distribution sketch.
  shape(slide, pptx.ShapeType.roundRect, 0.72, 2.05, 5.75, 3.95, { fill: C.paper, line: C.line });
  tx(slide, "한 공정 조건 p, 전압 V에서의 margin M", 1.02, 2.28, 4.98, 0.26, { fontSize: 14, color: C.navy, bold: true });
  slide.addShape(pptx.ShapeType.line, { x: 1.22, y: 5.12, w: 4.55, h: 0, line: { color: C.gray, width: 1.1 } });
  slide.addShape(pptx.ShapeType.line, { x: 2.22, y: 5.37, w: 0, h: -2.44, line: { color: C.rose, width: 1.2, dash: "dash" } });
  // A simple normal curve made from segments.
  const pts = [[1.35, 5.08], [1.62, 4.97], [1.92, 4.58], [2.22, 3.70], [2.52, 3.03], [2.82, 2.72], [3.12, 2.59], [3.42, 2.72], [3.72, 3.03], [4.02, 3.70], [4.32, 4.58], [4.62, 4.97], [4.90, 5.08]];
  for (let i = 0; i < pts.length - 1; i++) slide.addShape(pptx.ShapeType.line, { x: pts[i][0], y: pts[i][1], w: pts[i + 1][0] - pts[i][0], h: pts[i + 1][1] - pts[i][1], line: { color: C.teal, width: 2.4 } });
  tx(slide, "failure\nM < 0", 1.27, 5.29, 1.15, 0.47, { fontSize: 11, color: C.rose, align: "center" });
  tx(slide, "0 margin", 1.72, 5.36, 1.00, 0.20, { fontSize: 10, color: C.rose, align: "center" });
  tx(slide, "μ", 3.02, 2.32, 0.22, 0.20, { fontSize: 14, color: C.teal, bold: true, align: "center" });
  tx(slide, "σ", 3.96, 4.20, 0.22, 0.20, { fontSize: 14, color: C.navy, bold: true, align: "center" });
  slide.addShape(pptx.ShapeType.line, { x: 3.16, y: 4.46, w: 0.94, h: 0, line: { color: C.navy, width: 1.0, beginArrowType: "triangle", endArrowType: "triangle" } });
  formula(slide, "M(p,V) ~ Normal( μ(p,V), σ(p,V)² )", 1.15, 5.59, 4.88, 0.54, { fontSize: 17 });
  // Definition path.
  card(slide, 7.03, 2.05, 5.56, 1.15, { kicker: "STEP 1", headline: "z(p,V) = μ / σ", headlineSize: 22, body: "평균이 0 margin에서 표준편차 몇 개만큼 떨어져 있는가", bodySize: 12, bodyY: 0.78 });
  card(slide, 7.03, 3.47, 5.56, 1.15, { kicker: "STEP 2", headline: "g(p,V) = μ − Ztarget · σ", headlineSize: 22, body: "목표 yield를 만족하기 위한 lower-tail margin", bodySize: 12, bodyY: 0.78 });
  card(slide, 7.03, 4.89, 5.56, 1.15, { fill: C.mist, line: C.teal, kicker: "STEP 3", headline: "Vmin(p) = min { V : g(p,V) ≥ 0 }", headlineSize: 19, body: "전압축에서 g가 처음 0을 넘는 교차점", bodySize: 12, bodyY: 0.78 });
  tx(slide, "현재 분석 기준: 128 Mb · array yield 99% · Ztarget = 6.3984", 7.08, 6.36, 5.43, 0.25, { fontSize: 11, color: C.gray, align: "center" });
  addPage(slide, 3);
  note(slide, "이 슬라이드의 핵심은 단위를 구분하는 것입니다. μ−Ztarget·σ는 특정 전압에서의 lower-tail margin입니다. Vmin은 그 margin이 전압축에서 0을 넘는 위치입니다. ‘Vmin=μ−kσ’라고 말하면 안 됩니다.");
}

// 4. Implementation
{
  const slide = newSlide();
  title(slide, "IMPLEMENTATION", "9개 process 축과 VDD를 입력으로, μ와 log σ를 분리해 학습한다.", "입력은 10차원(9 process/device coordinates + Vop)이며 read/write는 별도 모델이다.");
  const groups = [
    ["Vth shift ×3", "cn · sk · pu", "공통 NMOS / PG–PD NMOS skew / PMOS", C.navy],
    ["local mismatch σ ×3", "l_com · l_sk · lpu", "각 소자 역할의 mismatch 산포 배율", C.orange],
    ["mobility ×3", "m_com · m_sk · mpu", "각 소자 역할의 mobility 배율", C.violet],
  ];
  groups.forEach(([label, codes, body, color], i) => {
    const x = 0.70 + i * 3.92;
    card(slide, x, 2.05, 3.45, 1.55, { fill: C.paper, line: color, lineWidth: 1.2, kicker: label, kickerColor: color, headline: codes, headlineSize: 17, body, bodySize: 11.3, bodyY: 0.95 });
  });
  formula(slide, "+  Vop", 11.76, 2.43, 0.85, 0.62, { fill: C.mist, fontSize: 17 });
  arrow(slide, 6.08, 4.21, 7.00, 4.21, C.gold, 2.0);
  card(slide, 0.70, 4.01, 5.15, 1.43, { fill: C.navy, line: C.navy, kicker: "MODEL", kickerColor: C.mint, headline: "GP #1: μ    |    GP #2: log σ", headlineSize: 21, headlineColor: C.paper, body: "Matérn 5/2 + full ARD · 입력 표준화 · σ>0를 log σ로 보장", bodyColor: "D9E8EE", bodySize: 11.8, bodyY: 0.89 });
  card(slide, 7.16, 4.01, 5.45, 1.43, { fill: C.teal, line: C.teal, kicker: "PHYSICS LAYER", kickerColor: C.mint, headline: "μ, σ  →  z, g  →  Vmin", headlineSize: 21, headlineColor: C.paper, body: "학습하지 않은 명시적 yield relation으로 conversion; forward와 inverse에 공통 사용", bodyColor: "D9F0EB", bodySize: 11.8, bodyY: 0.89 });
  formula(slide, "총 4개 GP:  read(μ, log σ)  +  write(μ, log σ)", 1.13, 5.95, 11.05, 0.59, { fontSize: 18 });
  tx(slide, "주의: sk는 N/P skew가 아니라 PG–PD NMOS skew이며, l_*는 gate length가 아니라 local mismatch σ 배율이다.", 0.78, 6.67, 11.95, 0.23, { fontSize: 10.4, color: C.orange, bold: true, align: "center" });
  addPage(slide, 4);
  note(slide, "입력을 열 개라고 하는 이유는 9개의 공정 좌표와 VDD가 있기 때문입니다. 모델은 Vmin을 바로 회귀하지 않고, margin의 μ와 log σ를 각각 학습합니다. 그러면 평균 악화와 mismatch 증가를 분리해서 읽을 수 있습니다.");
}

// 5. Forward validation
{
  const slide = newSlide();
  title(slide, "FORWARD VALIDATION", "학습에 쓰지 않은 조건에서도 Gaussian-reference Vmin을 mV 수준으로 추정한다.", "이 오차는 surrogate 대 reference simulation의 오차이며, silicon yield 정확도를 뜻하지 않는다.");
  imageContain(slide, path.join(FIGURES, "fig3_forward.png"), 0.67, 2.01, 8.20, 4.55, { line: C.line });
  figureCaption(slide, "Fig. 3 | 점 = hold-out condition. 대각선에 가까울수록 reference와 surrogate Vmin이 일치한다.", 0.84, 6.49, 7.85);
  card(slide, 9.22, 2.08, 3.39, 1.34, { fill: C.mist, line: C.sky, kicker: "READ / SNMR", headline: "RMSE 3.98 mV", headlineSize: 22, body: "scorable 245 conditions\n(censored 49 제외)", bodySize: 11.6, bodyY: 0.88 });
  card(slide, 9.22, 3.72, 3.39, 1.34, { fill: C.mist, line: C.sky, kicker: "WRITE / VTRIP", headline: "RMSE 5.65 mV", headlineSize: 22, body: "scorable 228 conditions\n(censored 69 제외)", bodySize: 11.6, bodyY: 0.88 });
  card(slide, 9.22, 5.36, 3.39, 1.05, { fill: C.lightRose, line: "EAB9B5", kicker: "HOW TO SAY IT", kickerColor: C.orange, headline: "“정의된 reference에 대한 surrogate error”", headlineSize: 13.8, headlineColor: C.ink, body: "metric 가정·silicon error와 혼동하지 않음", bodySize: 10.4, bodyY: 0.72 });
  addPage(slide, 5);
  note(slide, "대각선은 reference와 prediction이 같은 경우입니다. read 3.98 mV, write 5.65 mV는 hold-out 조건 중 Vmin을 grid 안에서 채점할 수 있던 조건의 RMSE입니다. Censored 조건을 0.4 V로 대입해 점수 낸 것이 아닙니다. 이 숫자는 silicon yield 오차가 아니라 Gaussian reference 정의에 대한 surrogate 오차입니다.");
}

// 6. Corner validation
{
  const slide = newSlide();
  title(slide, "GENERALIZATION", "학습에서 뺀 PDK corner에서도 mode별 limiting corner를 재현한다.", "read의 limiting corner는 FSG, write의 limiting corner는 SFG다.");
  imageContain(slide, path.join(FIGURES, "fig4_corner.png"), 0.64, 1.95, 8.86, 4.88, { line: C.line });
  figureCaption(slide, "Fig. 4 | 진한 막대=reference simulation, 연한 막대=surrogate. 막대 위 ±mV는 surrogate−reference.", 0.83, 6.58, 8.50);
  card(slide, 9.86, 2.13, 2.70, 1.37, { kicker: "READ", headline: "8.48 mV", headlineSize: 24, body: "3개의 scorable corner RMSE\nFSG가 worst", bodySize: 11.2, bodyY: 0.88 });
  card(slide, 9.86, 3.78, 2.70, 1.37, { kicker: "WRITE", headline: "5.79 mV", headlineSize: 24, body: "3개의 scorable corner RMSE\nSFG가 worst", bodySize: 11.2, bodyY: 0.88 });
  card(slide, 9.86, 5.43, 2.70, 1.02, { fill: C.lightRose, line: "EAB9B5", kicker: "CENSORING", kickerColor: C.orange, headline: "<0.4 V는 ‘값’이 아님", headlineSize: 14, body: "RMSE denominator에 네 corner를 모두 넣지 않음", bodySize: 10.1, bodyY: 0.70 });
  addPage(slide, 6);
  note(slide, "이것은 더 어려운 generalization test입니다. 네 PDK corner를 훈련에서 제외했지만 read FSG와 write SFG가 limiting이라는 방향을 맞췄습니다. 다만 한 corner가 grid 하한 아래로 censored되므로 RMSE는 mode별 세 개의 scorable corner 기준입니다. 네 corner 전체 순위를 매우 정밀하게 맞췄다는 주장은 하지 않습니다.");
}

// 7. Inverse boundary
{
  const slide = newSlide();
  title(slide, "INVERSE", "Forward: ‘얼마인가?’  →  Inverse: ‘목표를 위해 어디까지 허용되는가?’", "read와 write의 boundary가 다르므로 usable process window는 두 조건의 교집합이다.");
  imageContain(slide, path.join(FIGURES, "fig5_inverse.png"), 0.68, 1.95, 5.62, 4.95, { line: C.line });
  figureCaption(slide, "Fig. 5 | cell Vmin=max(read, write)의 cn×pu 조건부 2D slice. 다른 7축은 reference로 고정.", 0.80, 6.73, 5.35);
  const sequence = [
    ["1", "목표 설정", "T0 = 0.625 V"],
    ["2", "boundary scan", "root bracket 존재 확인"],
    ["3", "one-axis / plane", "허용 경계 좌표를 산출"],
  ];
  sequence.forEach(([n, h, b], i) => {
    const x = 6.88 + i * 1.86;
    shape(slide, pptx.ShapeType.ellipse, x + 0.45, 2.26, 0.54, 0.54, { fill: i === 2 ? C.teal : C.navy, line: false });
    tx(slide, n, x + 0.45, 2.36, 0.54, 0.20, { fontSize: 14, color: C.paper, bold: true, align: "center", fontFace: FONT_FALLBACK });
    tx(slide, h, x, 3.02, 1.43, 0.28, { fontSize: 13, color: C.ink, bold: true, align: "center" });
    tx(slide, b, x - 0.05, 3.37, 1.54, 0.45, { fontSize: 10.4, color: C.gray, align: "center", valign: "top" });
    if (i < 2) arrow(slide, x + 1.42, 2.54, x + 1.80, 2.54, C.gold, 1.3);
  });
  card(slide, 6.83, 4.47, 5.75, 1.44, { fill: C.mist, line: C.sky, kicker: "CORRECT INTERPRETATION", headline: "‘다른 8축을 고정한’ 조건부 설계 경계", headlineSize: 18, body: "9개의 실제 원인을 유일하게 추정하거나 root 하나를 강요하는 진단기가 아니다. GUI는 no-root / multiple-root도 결과로 표시한다.", bodySize: 11.4, bodyY: 0.89 });
  addPage(slide, 7);
  note(slide, "이 그림의 색은 combined cell Vmin=max(read,write)입니다. dashed와 solid boundary를 각각 읽어야 합니다. read와 write를 모두 통과하는 교집합만 usable 합니다. 중요하게도 이것은 cn과 pu만 움직이고 다른 7축을 고정한 2D conditional slice입니다. 9D 전체 yield window나 9개 원인의 고유 진단은 아닙니다.");
}

// 8. Sobol
{
  const slide = newSlide();
  title(slide, "SENSITIVITY", "Sobol은 ‘모델이 빨리 변하는 축’이 아니라, 지정한 design box에서 z 분산을 크게 움직이는 축을 묻는다.", "분석 범위: z(VT0=0.625 V), 독립 uniform input within training box, total-order ST.");
  imageContain(slide, path.join(FIGURES, "fig8_sensitivity.png"), 0.62, 1.96, 8.42, 4.72, { line: C.line });
  figureCaption(slide, "Fig. 8 | (a) read/write z(VT0)의 total-order Sobol ST; (b) σ variance; (c) ARD relevance 비교.", 0.82, 6.53, 7.98);
  card(slide, 9.38, 2.09, 3.21, 1.10, { fill: C.mist, line: C.sky, kicker: "RANKING", headline: "cn  >  l_com  >  pu", headlineSize: 17.5, body: "read ST: 0.413, 0.272, 0.200", bodySize: 10.8, bodyY: 0.75 });
  card(slide, 9.38, 3.47, 3.21, 1.20, { kicker: "DTCO HINT", headline: "NMOS local σ가 PMOS Vth보다 큼", headlineSize: 15.5, body: "global Vth만 보면 놓칠 수 있는 우선순위", bodySize: 10.8, bodyY: 0.82 });
  card(slide, 9.38, 4.95, 3.21, 1.20, { fill: C.lightRose, line: "EAB9B5", kicker: "DO NOT SAY", kickerColor: C.orange, headline: "‘27.2% 불량의 원인’이 아님", headlineSize: 14.0, body: "ST는 interaction을 포함하므로 합이 100%일 필요도 없음", bodySize: 10.5, bodyY: 0.83 });
  addPage(slide, 8);
  note(slide, "ARD와 Sobol을 구분해야 합니다. ARD lengthscale은 GP가 어느 축에서 빨리 굽는지를 말하는 model-local property입니다. Sobol total-order ST는 독립 uniform으로 정의한 design box에서 z(0.625V)의 variance가 각 축에 얼마나 민감한지를 말합니다. 여기서 cn이 1위이고, l_com이 pu보다 큽니다. 그러나 0.272를 실제 불량의 27.2%라고 읽으면 안 됩니다.");
}

// 9. DTCO scenario
{
  const slide = newSlide();
  title(slide, "DTCO SCENARIO", "Sensitivity로 후보 축을 고르고, inverse로 목표 Vmin에 필요한 surrogate-coordinate 변화를 계산한다.", "0.625 V → 0.575 V scenario: local mismatch σ 축이 유망한 candidate로 나타난다.");
  imageContain(slide, path.join(FIGURES, "fig10_scenario.png"), 0.61, 1.93, 8.85, 4.91, { line: C.line });
  figureCaption(slide, "Fig. 10 | baseline과 local-σ 개선 후보의 combined Vmin process window. 두 mode 모두 통과해야 한다.", 0.85, 6.63, 8.25);
  card(slide, 9.78, 2.05, 2.81, 1.35, { fill: C.mist, line: C.sky, kicker: "NMOS LOCAL-σ", headline: "약 −10.9%", headlineSize: 21, body: "one-axis candidate\n0.575 V target", bodySize: 10.9, bodyY: 0.89 });
  card(slide, 9.78, 3.73, 2.81, 1.35, { fill: C.mist, line: C.sky, kicker: "N + P LOCAL-σ", headline: "각 약 −7.8%", headlineSize: 20, body: "두 knob를 분담한\nsurrogate point estimate", bodySize: 10.7, bodyY: 0.90 });
  card(slide, 9.78, 5.41, 2.81, 0.93, { fill: C.lightRose, line: "EAB9B5", kicker: "NEXT STEP", kickerColor: C.orange, headline: "process mapping + circuit re-validation", headlineSize: 12.2, body: "제조비용 최소해·물리 실현성의 증명은 아님", bodySize: 9.6, bodyY: 0.67 });
  addPage(slide, 9);
  note(slide, "여기서 연결고리를 보여줍니다. Sobol이 우선 볼 축을 가리키고, inverse가 목표를 만족하는 데 필요한 변화량을 줍니다. 두 local σ를 함께 바꾸면 각각 약 7.8% 개선이라는 surrogate-coordinate 후보가 나옵니다. 이 숫자는 곧바로 implant나 layout 규칙으로 번역되지 않으며, process mapping과 circuit simulation 재검증이 필요합니다.");
}

// 10. Cost trade-off
{
  const slide = newSlide();
  title(slide, "SIMULATION COST", "‘무손실 절감’이 아니라, 정확도 대가를 보면서 training budget을 선택하게 한다.", "한 번 학습한 후에는 수많은 what-if / inverse 질의에 추가 MC가 필요 없다는 것이 주된 운영상 이점이다.");
  imageContain(slide, path.join(FIGURES, "fig7_cost.png"), 0.58, 1.95, 8.80, 4.75, { line: C.line });
  figureCaption(slide, "Fig. 7 | (a) condition 수, (b) MC depth, (c) combined training-budget trade-off.", 0.82, 6.53, 8.30);
  card(slide, 9.71, 2.13, 2.89, 1.20, { kicker: "READ CANDIDATE", headline: "53.125×", headlineSize: 26, body: "sample-count budget ratio", bodySize: 11.0, bodyY: 0.82 });
  card(slide, 9.71, 3.61, 2.89, 1.20, { kicker: "PRICE", kickerColor: C.orange, headline: "+3.53 mV", headlineSize: 25, headlineColor: C.orange, body: "Vmin RMSE increase", bodySize: 11.0, bodyY: 0.82 });
  card(slide, 9.71, 5.09, 2.89, 1.20, { fill: C.lightRose, line: "EAB9B5", kicker: "IMPORTANT", kickerColor: C.orange, headline: "HSPICE wall-clock 53×가 아님", headlineSize: 13.2, body: "조건·전압·MC sample 수로 계산한 budget ratio; MC depth는 noise-emulation", bodySize: 9.7, bodyY: 0.80 });
  addPage(slide, 10);
  note(slide, "53.125배라는 수치는 HSPICE runtime을 실제로 재서 얻은 속도향상이 아닙니다. 조건 수와 MC depth를 이용한 sample-count budget ratio입니다. MC depth 부분도 실제 재실행이 아니라 noise-emulation이 포함됩니다. 따라서 올바른 결론은 lossless saving이 아니라, accuracy와 budget의 Pareto trade-off를 숫자로 관리할 수 있다는 것입니다.");
}

// 11. GUI
{
  const slide = newSlide();
  title(slide, "LOCAL DEMO TOOL", "논문 모델을 그대로 활용하는 Windows local-only inverse 시연 도구", "PDK·model data는 PC 밖으로 전송하지 않으며, localhost에서만 동작하도록 설계했다.");
  // Stylized screenshot architecture (not a fake screenshot).
  shape(slide, pptx.ShapeType.roundRect, 0.74, 2.02, 7.40, 4.48, { fill: C.paper, line: C.line, lineWidth: 1.1 });
  shape(slide, pptx.ShapeType.roundRect, 0.96, 2.27, 6.96, 0.46, { fill: C.navy, line: false });
  tx(slide, "SRAM Vmin Inverse Studio   ·   localhost only", 1.17, 2.36, 5.85, 0.20, { fontSize: 11.5, color: C.paper, bold: true, fontFace: FONT_FALLBACK });
  card(slide, 1.02, 2.99, 1.85, 2.86, { fill: C.pale, line: C.line, kicker: "CONTROLS", headline: "9 axes", headlineSize: 17, body: "sliders\ntarget Vmin\nread / write\naxis selection", bodySize: 11, bodyY: 0.83 });
  card(slide, 3.09, 2.99, 2.15, 1.20, { fill: C.mist, line: C.sky, kicker: "FORWARD", headline: "Read / Write Vmin", headlineSize: 14.5, body: "같은 좌표 두 mode 질의", bodySize: 9.6, bodyY: 0.77 });
  card(slide, 5.50, 2.99, 2.12, 1.20, { fill: C.mist, line: C.sky, kicker: "INVERSE", headline: "scan → bracket → root", headlineSize: 14.0, body: "없거나 여러 해도 표시", bodySize: 9.6, bodyY: 0.77 });
  shape(slide, pptx.ShapeType.roundRect, 3.09, 4.46, 4.53, 1.39, { fill: C.pale, line: C.line });
  slide.addShape(pptx.ShapeType.line, { x: 3.40, y: 5.52, w: 3.74, h: -0.73, line: { color: C.teal, width: 2 } });
  slide.addShape(pptx.ShapeType.line, { x: 3.40, y: 4.96, w: 3.74, h: 0, line: { color: C.rose, width: 1.1, dash: "dash" } });
  tx(slide, "inverse sweep · target crossing", 3.39, 4.61, 3.81, 0.19, { fontSize: 10, color: C.gray, align: "center" });
  const steps = [
    ["1", "현재 좌표 forward prediction"],
    ["2", "선택 축 scan과 root 상태 확인"],
    ["3", "cn×pu 2D conditional slice"],
    ["4", "Sobol·scenario 설명 패널"],
  ];
  steps.forEach(([num, t], i) => {
    const y = 2.08 + i * 1.02;
    shape(slide, pptx.ShapeType.ellipse, 8.70, y + 0.03, 0.49, 0.49, { fill: i === 3 ? C.orange : C.teal, line: false });
    tx(slide, num, 8.70, y + 0.13, 0.49, 0.18, { fontSize: 12, color: C.paper, bold: true, align: "center", fontFace: FONT_FALLBACK });
    tx(slide, t, 9.42, y, 3.11, 0.48, { fontSize: 15, color: C.ink, bold: i === 0, valign: "mid" });
  });
  card(slide, 8.65, 6.08, 3.95, 0.58, { fill: C.lightRose, line: "EAB9B5", headline: "해가 없으면 ‘no root’도 결과로 보여준다.", headlineSize: 11.5, headlineColor: C.orange, body: "", bodyY: 0.58 });
  addPage(slide, 11);
  note(slide, "이 도구는 웹 서버를 외부에 띄우지 않고 Windows PC의 localhost에서만 동작합니다. 발표에서는 read/SNMR을 선택해 Vmin을 먼저 보여주고, cn 혹은 l_com에 대해 scan을 실행한 뒤 root를 보여줍니다. 해가 없거나 하나가 아니면 숨기지 않고 no-root 또는 multiple-root로 표시합니다. 2D plane은 나머지 7축을 고정한 conditional slice라고 반드시 말합니다.");
}

// 12. Conclusion
{
  const slide = newSlide(C.midnight);
  tx(slide, "CONCLUSION", 0.76, 0.66, 2.1, 0.23, { fontSize: 11, color: C.mint, bold: true, fontFace: FONT_FALLBACK });
  tx(slide, "한 simulation campaign에서\nforward · inverse · DTCO screening을 연결한다.", 0.74, 1.12, 11.56, 1.03, { fontSize: 32, color: C.paper, bold: true });
  const conclusions = [
    ["01", "Surrogate의 효용", "비싼 HSPICE label을 반복 질의 가능한 설계 함수로 전환", C.mint],
    ["02", "구현의 투명성", "9D+VDD → μ GP / logσ GP → yield physics → Vmin", C.gold],
    ["03", "DTCO 연결", "Sobol 우선순위 + conditional inverse로 재검증 후보 생성", C.mint],
    ["04", "비용 관리", "무손실을 약속하지 않고 accuracy–budget trade-off를 수치화", C.gold],
  ];
  conclusions.forEach(([n, h, b, col], i) => {
    const x = 0.74 + (i % 2) * 6.10;
    const y = 2.66 + Math.floor(i / 2) * 1.45;
    shape(slide, pptx.ShapeType.roundRect, x, y, 5.54, 1.12, { fill: "103044", line: "285367", lineWidth: 0.8 });
    tx(slide, n, x + 0.20, y + 0.22, 0.54, 0.26, { fontSize: 14, color: col, bold: true, fontFace: FONT_FALLBACK });
    tx(slide, h, x + 0.91, y + 0.16, 4.35, 0.28, { fontSize: 18, color: C.paper, bold: true });
    tx(slide, b, x + 0.91, y + 0.59, 4.36, 0.25, { fontSize: 11.2, color: "C8DCE3" });
  });
  formula(slide, "surrogate error  ≠  tail/metric error  ≠  silicon qualification", 0.86, 5.86, 11.62, 0.69, { fill: "15384C", line: "30677A", color: C.paper, fontSize: 19 });
  tx(slide, "Final sign-off: high-fidelity circuit simulation + silicon validation", 0.76, 6.89, 11.7, 0.20, { fontSize: 11, color: "A9C2CF", align: "center", fontFace: FONT_FALLBACK });
  tx(slide, "12", 12.16, 7.07, 0.55, 0.20, { fontSize: 9, color: "A9C2CF", align: "right", fontFace: FONT_FALLBACK });
  note(slide, "마지막으로 세 층을 분리해 말합니다. surrogate error, tail/metric 모델의 오차, silicon qualification은 서로 다른 문제입니다. 이번 연구의 기여는 빠른 숫자 하나가 아니라, simulation budget으로부터 forward prediction, process boundary, sensitivity, scenario screening을 연결한 것입니다. 최종 sign-off는 여전히 high-fidelity circuit simulation과 silicon validation입니다.");
}

// Appendix 13. Lobe/metric risk
{
  const slide = newSlide();
  title(slide, "BACKUP · METRIC RISK", "GP가 μ/σ reference를 잘 맞혀도, tail metric 가정은 별도의 큰 risk일 수 있다.", "이 슬라이드는 baseline RMSE와 합산하지 않는 backup analysis다.");
  imageContain(slide, path.join(FIGURES, "fig6_lobe.png"), 0.64, 1.98, 8.68, 4.68, { line: C.line });
  figureCaption(slide, "Fig. 6 | lobe correlation과 lobe-corrected Vmin의 model-based estimate.", 0.82, 6.52, 8.22);
  card(slide, 9.69, 2.20, 2.91, 1.23, { fill: C.lightRose, line: "EAB9B5", kicker: "KEY POINT", kickerColor: C.orange, headline: "metric 가정 영향이 수십 mV일 수 있음", headlineSize: 15.1, body: "min-of-two tail model·상관 추정에 의존", bodySize: 10.4, bodyY: 0.84 });
  card(slide, 9.69, 3.77, 2.91, 1.23, { kicker: "CORRECT READING", headline: "‘GP가 틀렸다’는 그림이 아님", headlineSize: 14.1, body: "μ/σ reference와 yield conversion을 분리해서 봐야 함", bodySize: 10.4, bodyY: 0.84 });
  card(slide, 9.69, 5.34, 2.91, 1.02, { fill: C.lightRose, line: "EAB9B5", kicker: "DO NOT COMBINE", kickerColor: C.orange, headline: "3.98/5.65 mV와 합산 금지", headlineSize: 13.5, body: "silicon Vmin error도 아님", bodySize: 10.0, bodyY: 0.72 });
  addPage(slide, 13, "SRAM Vmin surrogate · backup");
  note(slide, "이것은 backup입니다. lobe correction은 baseline Gaussian reference RMSE와 더해 실제 Vmin error라고 말하면 안 됩니다. 메시지는 GP가 μ/σ reference를 잘 맞추더라도, min-of-two tail metric의 가정이 sign-off에는 더 큰 영향을 줄 수 있다는 것입니다. 이 보정 역시 model-based estimate이고 silicon validation이 아닙니다.");
}

// Appendix 14. Skew
{
  const slide = newSlide();
  title(slide, "BACKUP · SKEW WINDOW", "tail 가정의 보정은 Vmin 숫자뿐 아니라 허용 process window의 모양도 바꿀 수 있다.", "PG–PD NMOS skew tolerance 분석: sk는 N/P skew가 아님.");
  imageContain(slide, path.join(FIGURES, "fig9_skew.png"), 0.64, 2.00, 8.80, 4.66, { line: C.line });
  figureCaption(slide, "Fig. 9 | 각 cn, pu 위치에서 허용되는 PG–PD skew 폭. 색은 tolerance, 검은 선은 every-skew boundary.", 0.82, 6.52, 8.30);
  card(slide, 9.77, 2.21, 2.80, 1.33, { kicker: "WHAT COLOR MEANS", headline: "허용되는 skew 폭", headlineSize: 17.5, body: "빨강: 거의 허용되지 않음\n파랑: ±40 mV sweep 허용", bodySize: 10.5, bodyY: 0.90 });
  card(slide, 9.77, 3.91, 2.80, 1.22, { kicker: "OBSERVATION", headline: "every-skew 면적 82% → 67%", headlineSize: 14.8, body: "Ztarget → Zeff comparison", bodySize: 10.4, bodyY: 0.84 });
  card(slide, 9.77, 5.46, 2.80, 0.85, { fill: C.lightRose, line: "EAB9B5", kicker: "BACKUP", kickerColor: C.orange, headline: "기본 Gaussian accuracy와 혼용 금지", headlineSize: 11.8, body: "", bodyY: 0.56 });
  addPage(slide, 14, "SRAM Vmin surrogate · backup");
  note(slide, "이 그림은 sk 허용폭의 조건부 2D window입니다. 색은 각 cn, pu 위치에서 허용되는 PG–PD NMOS skew 폭입니다. naive Gaussian Ztarget와 lobe-corrected Zeff를 비교하면 every-skew 영역이 줄어듭니다. 이 역시 metric-risk backup이며 baseline Gaussian RMSE와 섞지 않습니다.");
}

// Appendix 15. Discussion guardrails
{
  const slide = newSlide();
  title(slide, "BACKUP · Q&A GUARDRAILS", "발표에서 신뢰도를 지키는 네 가지 구분", "이 네 문장을 지키면 결과를 과장하지 않으면서도 contribution을 명확히 전달할 수 있다.");
  const guards = [
    ["SURROGATE", "3.98/5.65 mV", "Gaussian reference simulation에 대한 hold-out Vmin error", C.teal],
    ["INVERSE", "조건부 boundary", "다른 8축을 고정한 one-axis / 2D slice; 9개 원인의 고유 진단 아님", C.navy],
    ["SOBOL", "분포·출력 조건부", "z(0.625V), uniform training box, ST는 interaction 포함", C.violet],
    ["COST", "sample budget", "53.125×는 HSPICE wall-clock 측정값이 아님", C.orange],
  ];
  guards.forEach(([tagText, head, body, color], i) => {
    const x = 0.80 + (i % 2) * 6.12;
    const y = 2.08 + Math.floor(i / 2) * 1.78;
    card(slide, x, y, 5.54, 1.36, { fill: C.paper, line: color, lineWidth: 1.2, kicker: tagText, kickerColor: color, headline: head, headlineSize: 20, body, bodySize: 11.1, bodyY: 0.88 });
  });
  formula(slide, "가장 안전한 결론: ‘surrogate로 설계 후보를 빠르게 좁히고, 원 회로 simulation으로 검증한다.’", 1.03, 5.88, 11.22, 0.63, { fontSize: 17 });
  addPage(slide, 15, "SRAM Vmin surrogate · backup");
  note(slide, "Q&A에서는 이 네 구분을 반복하면 됩니다. 3.98/5.65mV는 Gaussian reference에 대한 surrogate error, inverse는 conditional boundary, Sobol은 지정 분포와 출력에 조건부, 53.125x는 sample budget ratio입니다. 가장 안전한 결론은 surrogate로 후보를 빠르게 좁히고 원 회로 simulation으로 검증한다는 것입니다.");
}

pptx.writeFile({ fileName: OUT });
console.log(`Wrote ${OUT}`);
