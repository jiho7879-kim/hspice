// Builds the IEEE-format Word manuscript from the test.txt narrative.
//
//   node manuscript/code/make_docx.js          -> manuscript/SRAM_Vmin_IEEE.docx
//   node manuscript/code/make_docx.js --kr     -> manuscript/SRAM_Vmin_IEEE_KR.docx
//
// Every number is read out of manuscript/results/*.json at build time -- nothing
// is typed in twice, so the document cannot drift from the results the way a
// hand-copied figure would.  (README: "숫자는 반드시 출처가 있다".)
const fs = require("fs");
const path = require("path");
const d = require("docx");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, WidthType, ShadingType, BorderStyle,
  SectionType, TabStopType, Tab, convertInchesToTwip,
} = d;

const KR = process.argv.includes("--kr");
const ROOT = path.resolve(__dirname, "..");
const FIG = (n) => path.join(ROOT, "figures", n + ".png");
// Python's json.dump emits bare NaN/Infinity, which strict JSON.parse rejects.
// Only ever appears in audit/diagnostic fields, so mapping them to null is safe.
const R = (n, optional) => {
  const fp = path.join(ROOT, "results", n + ".json");
  if (optional && !fs.existsSync(fp)) return null;
  return JSON.parse(fs.readFileSync(fp, "utf8")
    .replace(/(:\s*)-?(NaN|Infinity)\b/g, "$1null"));
};

// ============================================================ numbers, from results/
const fwd = R("forward"), fwdW = R("forward_write");
const cor = R("corner"), corW = R("corner_write");
const inv = R("inverse"), lobe = R("lobe"), sens = R("sensitivity");
// the combo point is part of the filename (vi_cost.py L331); the paper quotes the
// 400-condition / 500-sample cut
const cost = R("cost_combined_c400_mc500");
const costW = R("cost_combined_write_c400_mc500");
const scen = R("scenario", true);   // §IV-B; section is omitted until it exists

const f = (x, n) => Number(x).toFixed(n);
const ST = sens.sobol.ST[Object.keys(sens.sobol.ST).find((k) => k.startsWith("z("))];

// device-name symbols for the nine variation axes (README, edition D)
const AXIS = {
  cn: ["ΔV_{th,N}", "NMOS global threshold shift", "NMOS 전역 threshold shift", true],
  pu: ["ΔV_{th,P}", "PMOS global threshold shift", "PMOS 전역 threshold shift", true],
  sk: ["ΔV_{th,skew}", "N/P threshold skew", "N/P threshold skew", false],
  l_com: ["k_{σN}", "NMOS common local-σ (mismatch)", "NMOS 공통 local-σ (mismatch)", false],
  l_sk: ["Δk_{σN}", "NMOS local-σ skew", "NMOS local-σ skew", false],
  lpu: ["k_{σP}", "PMOS local-σ", "PMOS local-σ", false],
  m_com: ["k_{μN}", "NMOS mobility multiplier", "NMOS mobility 배율", false],
  m_sk: ["Δk_{μN}", "NMOS mobility skew", "NMOS mobility skew", false],
  mpu: ["k_{μP}", "PMOS mobility multiplier", "PMOS mobility 배율", false],
};
const CORNER_SUM = ST.cn + ST.pu;                 // upper bound on the corner axes' joint share
const OFF_CORNER = Math.floor((1 - CORNER_SUM) * 100);   // "at least N %"
const RHO = lobe.rho_pooled;
const LOBE_RATIO = (1 - RHO) / (1 + RHO);

const N = {
  rmseR: f(fwd.vmin_rmse_mV_holdout, 2), rmseW: f(fwdW.vmin_rmse_mV_holdout, 2),
  corR: f(cor.vmin_rmse_mV, 1), corW: f(corW.vmin_rmse_mV, 1),
  sigR2R: f(fwd.sigma_r2, 4), sigR2W: f(fwdW.sigma_r2, 4),
  muR2R: f(fwd.mu_r2, 4), muR2W: f(fwdW.mu_r2, 4),
  invCn: f(inv.recovery.cn.rmse_mV, 2), invPu: f(inv.recovery.pu.rmse_mV, 2),
  stKsn: f(ST.l_com, 3), stPu: f(ST.pu, 3), stCn: f(ST.cn, 3),
  cornerSum: f(CORNER_SUM, 2), offCorner: String(OFF_CORNER),
  rho: f(RHO, 3), lobeRatio: f(LOBE_RATIO, 1),
  tailMv: f(lobe.vmin_optimism_population_mV, 0),
  speedR: f(cost.speedup, 0), speedW: f(costW.speedup, 1),
  costRmseR: f(cost.combined_on_full.vmin_rmse_mV, 2),
  costRmseW: f(costW.combined_on_full.vmin_rmse_mV, 2),
  degR: f(cost.combined_on_full.vmin_rmse_mV - fwd.vmin_rmse_mV_holdout, 1),
  degW: f(costW.combined_on_full.vmin_rmse_mV - fwdW.vmin_rmse_mV_holdout, 1),
};
// the read/write ordering claim in section V-A must actually hold in the data
if (!(ST.l_com > ST.pu)) throw new Error("S_T(k_sigmaN) no longer exceeds S_T(dVth,P) — section V-A text is stale");

// Limiting corner: the highest non-censored reference Vmin. Derived, not named,
// so a re-derivation that moves it cannot leave the body text pointing at the
// old one -- and "identified correctly" in Table I is checked, not asserted.
const limitingBy = (j, key, cen) => j.corners.filter((c) => !c[cen])
  .reduce((a, b) => (b[key] > a[key] ? b : a)).corner;
N.limR = limitingBy(cor, "vmin_meas", "censored_meas");
N.limW = limitingBy(corW, "vmin_meas", "censored_meas");
N.limOkR = N.limR === limitingBy(cor, "vmin_pred", "censored_pred") ? "Correct" : "MISMATCH";
N.limOkW = N.limW === limitingBy(corW, "vmin_pred", "censored_pred") ? "Correct" : "MISMATCH";

// ----------------------------------------- figure/table numbers, in document order
// IEEE numbers by order of first citation, and inserting section IV-B shifts
// everything after it. Deriving the numbers from one ordered list means the body
// text, the captions and the table headers cannot disagree.
const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII"];
const FIG_ORDER = ["Pipe", "Fwd", "Corner", "Inv", ...(scen ? ["Scen"] : []),
                   "Sens", "Cost"];
const TAB_ORDER = ["Acc", "Corner", "Inv", ...(scen ? ["Scen"] : []), "Sobol", "Cost"];
FIG_ORDER.forEach((k, i) => { N["fig" + k] = String(i + 1); });
TAB_ORDER.forEach((k, i) => { N["tab" + k] = ROMAN[i + 1]; });

// -------------------------------------------------- section IV-B, from scenario.json
let scenRows = null;
if (scen) {
  N.scTarget = f(scen.v_target, 3);
  N.scGapR = f(scen.baseline_gap_mV.read, 1);
  N.scGapW = f(scen.baseline_gap_mV.write, 1);

  const single = scen.cases.filter((c) => c.case !== "k_sigmaNP");
  const combo = scen.cases.find((c) => c.case === "k_sigmaNP");
  const ok = single.filter((c) => c.reachable).map((c) => c.label);
  const no = single.filter((c) => !c.reachable).map((c) => c.label);
  // The verdict sentence is written from the result, not assumed: whether a single
  // lever suffices is exactly what this analysis is for, so it must not be hard-coded.
  const say = (list, join) => list.join(join);
  if (ok.length === 0) {
    N.scVerdict = KR
      ? `단일 축으로는 어느 것도 설계 상자 안에서 목표에 닿지 못한다(${say(no, ", ")}). ${combo && combo.reachable ? `두 local-σ 축을 함께 움직여야 도달하며, 그때 필요한 감소폭은 축당 ${f(combo.sigma_reduction_pct, 1)} %다.` : "두 축을 함께 움직여도 닿지 않는다 — 이 목표는 device 개선만으로는 열리지 않는다."}`
      : `No single lever reaches the target inside the design box (${say(no, ", ")}). ${combo && combo.reachable ? `The two local-σ axes have to move together, at ${f(combo.sigma_reduction_pct, 1)} % per axis.` : "Moving both together does not reach it either — this target does not open on device improvement alone."}`;
  } else {
    // "smallest ask" = the least relative movement demanded of the process, which
    // is all the surrogate can rank -- it does not know what any lever costs.
    const best = single.filter((c) => c.reachable)
      .sort((a, b) => (a.sigma_reduction_pct ?? a.corner_shrink_pct)
                    - (b.sigma_reduction_pct ?? b.corner_shrink_pct))[0];
    const cheapest = best.sigma_reduction_pct !== undefined
      ? (KR ? `${best.label}을(를) ${f(best.sigma_reduction_pct, 1)} % 줄이는 것`
            : `a ${f(best.sigma_reduction_pct, 1)} % reduction in ${best.label}`)
      : (KR ? `${best.label}을(를) PDK offset의 ${f(100 - best.corner_shrink_pct, 0)} %까지 조이는 것`
            : `tightening ${best.label} to ${f(100 - best.corner_shrink_pct, 0)} % of the PDK offset`);
    N.scVerdict = KR
      ? `단일 축으로 도달 가능한 것은 ${say(ok, ", ")}이고${no.length ? `, ${say(no, ", ")}은(는) 상자 안에서 닿지 않는다` : ""}. 요구가 가장 작은 단일 경로는 ${cheapest}이다.${combo && combo.reachable ? ` 두 local-σ 축에 부담을 나누면 축당 ${f(combo.sigma_reduction_pct, 1)} %로 줄어든다.` : ""}`
      : `The levers that reach it on their own are ${say(ok, ", ")}${no.length ? `, while ${say(no, ", ")} cannot inside the box` : ""}. The smallest single ask is ${cheapest}.${combo && combo.reachable ? ` Splitting the burden across both local-σ axes drops each to ${f(combo.sigma_reduction_pct, 1)} %.` : ""}`;
  }

  scenRows = scen.cases.map((c) => {
    if (!c.reachable) {
      const floor = c.sigma_reduction_pct !== undefined
        ? (KR ? `하한 σ × ${f(c.knob_floor, 2)} (−${f(c.sigma_reduction_pct, 0)} %)에서도 부족`
              : `short even at the floor, σ × ${f(c.knob_floor, 2)} (−${f(c.sigma_reduction_pct, 0)} %)`)
        : (KR ? "설계 상자 안에서 도달 불가" : "not reachable in the box");
      return [c.label, floor,
        `${f(c.vmin_at_floor, 4)} V` + (KR ? " (하한)" : " (at floor)")];
    }
    if (c.sigma_reduction_pct !== undefined) {
      return [c.label,
        `σ × ${f(c.s_required, 3)}  (−${f(c.sigma_reduction_pct, 1)} %)`,
        `${f(c.vmin_at_s, 4)} V`];
    }
    return [c.label,
      KR ? `PDK offset의 ${f(100 - c.corner_shrink_pct, 0)} % (−${f(c.corner_shrink_pct, 0)} %)`
         : `${f(100 - c.corner_shrink_pct, 0)} % of the PDK offset (−${f(c.corner_shrink_pct, 0)} %)`,
      `${f(c.vmin_at_s, 4)} V`];
  });
}

// ---------------------------------------------------------------- page setup
const PAGE = { size: { width: 12240, height: 15840 } };            // US Letter, DXA
const MARGIN = { top: 1080, right: 900, bottom: 1440, left: 900 }; // text width 10440 DXA = 7.25"
const COL_DXA = 5040, FULL_DXA = 10440;
const FULL_PX = 672, COL_PX = 326;
// Batang is the Korean serif that pairs with the IEEE look; Malgun Gothic is sans
// and reads like a slide deck next to the figures.
const FONT = KR ? "Batang" : "Times New Roman";
const BODY = { font: FONT, size: 20 };  // 10 pt
const SMALL = { font: FONT, size: 16 };

const secProps = (cols) => ({
  type: SectionType.CONTINUOUS,
  page: { ...PAGE, margin: MARGIN },
  column: cols === 2 ? { count: 2, space: 360, equalWidth: true } : { count: 1 },
});

// ------------------------------------------------- inline markup + interpolation
// **bold**  *italic*  _{sub}  ^{sup}  {{key}} -> N[key]
function runs(text, base = {}) {
  text = String(text).replace(/\{\{(\w+)\}\}/g, (_, k) => {
    if (!(k in N)) throw new Error("unknown number key: " + k);
    return N[k];
  });
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|_\{[^}]*\}|\^\{[^}]*\})/g;
  let last = 0, m;
  const push = (t, opt) => {
    if (!t) return;
    t.split("\t").forEach((seg, i) => {
      if (i > 0) out.push(new TextRun({ ...base, ...opt, children: [new Tab()] }));
      if (seg) out.push(new TextRun({ text: seg, ...base, ...opt }));
    });
  };
  while ((m = re.exec(text)) !== null) {
    push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) push(tok.slice(2, -2), { bold: true });
    else if (tok.startsWith("*")) push(tok.slice(1, -1), { italics: true });
    else if (tok.startsWith("_{")) push(tok.slice(2, -1), { subScript: true });
    else push(tok.slice(2, -1), { superScript: true });
    last = re.lastIndex;
  }
  push(text.slice(last));
  return out;
}

// ------------------------------------------------------------------ blocks
const HANG = convertInchesToTwip(0.25);
const p = (text, opt = {}) => {
  const isItem = /^(\d\)|•)\t/.test(text);
  return new Paragraph({
    children: runs(text, { ...BODY, ...(opt.run || {}) }),
    alignment: opt.align || AlignmentType.JUSTIFIED,
    spacing: { after: opt.after === undefined ? 0 : opt.after, line: KR ? 260 : 240 },
    tabStops: isItem ? [{ type: TabStopType.LEFT, position: HANG }] : undefined,
    indent: isItem ? { left: HANG, hanging: HANG }
      : (opt.noIndent ? undefined : { firstLine: convertInchesToTwip(0.2) }),
  });
};

const h1 = (text) => new Paragraph({
  children: runs(text, BODY),
  alignment: AlignmentType.CENTER,
  spacing: { before: 240, after: 120 },
  heading: HeadingLevel.HEADING_1,
});

const h2 = (text) => new Paragraph({
  children: runs(text, { ...BODY, italics: !KR }),
  alignment: AlignmentType.LEFT,
  spacing: { before: 160, after: 80 },
  heading: HeadingLevel.HEADING_2,
});

const eq = (text, num) => new Paragraph({
  children: runs(text + "\t(" + num + ")", BODY),
  tabStops: [{ type: TabStopType.RIGHT, position: COL_DXA - 100 }],
  spacing: { before: 120, after: 120 },
  indent: { left: convertInchesToTwip(0.35) },
});

function figure(file, wPx, hPx, caption, full) {
  return [
    new Paragraph({
      children: [new ImageRun({
        type: "png", data: fs.readFileSync(FIG(file)),
        transformation: { width: wPx, height: hPx },
      })],
      alignment: AlignmentType.CENTER,
      spacing: { before: 160, after: 60 },
    }),
    new Paragraph({
      children: runs(caption, SMALL),
      alignment: full ? AlignmentType.JUSTIFIED : AlignmentType.LEFT,
      spacing: { after: 200, line: 220 },
    }),
  ];
}

function table(label, title, header, rows, full) {
  const total = full ? FULL_DXA : COL_DXA;
  const n = header.length;
  const first = Math.round(total * (n <= 3 ? 0.42 : 0.26));
  const widths = [first];
  for (let i = 1; i < n; i++) widths.push(Math.round((total - first) / (n - 1)));
  widths[n - 1] = total - widths.slice(0, n - 1).reduce((a, b) => a + b, 0);

  const cell = (txt, i, opts = {}) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    shading: opts.head ? { type: ShadingType.CLEAR, fill: "F2F2F2" } : undefined,
    margins: { top: 40, bottom: 40, left: 80, right: 80 },
    children: [new Paragraph({
      children: runs(txt, { ...SMALL, bold: !!opts.head }),
      alignment: i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
      spacing: { line: 220 },
    })],
  });

  const b = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
  return [
    new Paragraph({ children: runs(label, SMALL), alignment: AlignmentType.CENTER,
      spacing: { before: 200, after: 0 } }),
    new Paragraph({ children: runs(title, { ...SMALL, smallCaps: !KR }),
      alignment: AlignmentType.CENTER, spacing: { after: 60 } }),
    new Table({
      columnWidths: widths,
      width: { size: total, type: WidthType.DXA },
      borders: { top: b, bottom: b, left: b, right: b,
        insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "808080" },
        insideVertical: { style: BorderStyle.SINGLE, size: 2, color: "808080" } },
      rows: [
        new TableRow({ tableHeader: true, children: header.map((t, i) => cell(t, i, { head: true })) }),
        ...rows.map((r) => new TableRow({ children: r.map((t, i) => cell(t, i)) })),
      ],
    }),
    new Paragraph({ text: "", spacing: { after: 200 } }),
  ];
}

// data-driven table rows -------------------------------------------------------
const cornerRows = () => {
  const byName = (j) => Object.fromEntries(j.corners.map((c) => [c.corner, c]));
  const r = byName(cor), w = byName(corW);
  const order = ["FSG", "SFG", "FFG", "SSG"];
  const cellFor = (q, limiting) => (q.censored_meas || q.censored_pred)
    ? (KR ? "censored (< 0.4 V)" : "clamped < 0.4 V")
    : `${f(q.vmin_meas, 4)} → ${f(q.vmin_pred, 4)}` + (limiting ? (KR ? "  ← 최악" : "  ← worst") : "");
  const limR = N.limR, limW = N.limW;
  return order.map((k) => [
    (k === limR || k === limW) ? `**${k}**` : k,
    `(${f(r[k].cn, 2)}, ${f(r[k].pu, 2)})`,
    cellFor(r[k], k === limR),
    cellFor(w[k], k === limW),
  ]);
};

const sobolRows = () => Object.entries(AXIS)
  .map(([k, v]) => ({ k, sym: v[0], desc: KR ? v[2] : v[1], corner: v[3], st: ST[k] }))
  .sort((a, b) => b.st - a.st)
  .map((r) => [r.sym, r.desc,
    r.corner ? (KR ? "예" : "yes") : (KR ? "아니오" : "no"),
    r.st >= 0.15 ? `**${f(r.st, 3)}**` : f(r.st, 3)]);

// ================================================================= text bodies
const T = {
  title: {
    en: "A Physics-Guided Framework for Forward and Inverse SRAM V_{min} Estimation Under Process Variation",
    kr: "공정 변동 하의 SRAM V_{min} 순·역방향 추정을 위한 physics-guided framework",
  },
  authors: { en: "[Author Names — to be supplied]", kr: "[저자 — 미정]" },
  affil: { en: "*[Affiliation — to be supplied]*", kr: "*[소속 — 미정]*" },

  abstract: {
    en: "**Abstract—**Verifying the minimum operating voltage (V_{min}) of SRAM bitcells involves a difficult trade-off: Monte Carlo (MC) simulation is too expensive for routine use, while standard PDK corner analysis often misses critical variation caused by local mismatch. This paper presents a physics-guided framework that bridges this gap. Using a single, fixed simulation budget, the method delivers high-fidelity V_{min} predictions and enables inverse process-window analysis. Unlike black-box machine-learning models, the approach explicitly separates device-level margin statistics — the mean and the standard deviation — from the analytic yield relation, preserving physical interpretability. Validated on silicon-calibrated simulation data from an advanced FinFET node, the framework predicts hold-out V_{min} with millivolt-level accuracy ({{rmseR}} mV RMSE for read, {{rmseW}} mV for write) and correctly identifies limiting PDK corners unseen during training. Crucially, a total-order global sensitivity analysis exposes a fundamental blind spot in conventional corner-based verification: a local NMOS mismatch axis contributes more read-margin variance than the global PMOS threshold-shift corner axis, and at least {{offCorner}} % of the read-margin variance lies in process directions orthogonal to the conventional corner set. Corner-only flows may therefore underestimate V_{min} by ignoring mismatch-driven tails. The framework also supports inverse queries, letting engineers determine the process shifts — a V_{th} tolerance, for example — needed to meet a target V_{min}. The margin distribution is treated as Gaussian throughout, and tail-shape correction is left to future work. Within that assumption the proposed method establishes a robust, efficient workflow that connects statistical variation, yield targets, and actionable process specifications.",
    kr: "**요약—**SRAM bitcell의 최소 동작 전압(V_{min}) 검증에는 풀기 어려운 trade-off가 있다. Monte Carlo(MC) simulation은 통계적으로 완결되지만 일상적으로 돌리기에 너무 비싸고, PDK corner 해석은 빠른 대신 local mismatch가 만드는 결정적인 변동을 놓친다. 이 논문은 그 사이를 메우는 physics-guided framework를 제안한다. 고정된 simulation budget 한 번으로 높은 정확도의 V_{min} 예측과 역방향 process window 해석을 동시에 얻는다. black-box machine learning 모델과 달리, 소자 수준 margin 통계량(평균과 표준편차)을 analytic yield 관계식에서 분리해 물리적 해석 가능성을 유지한다. 선단 FinFET 공정의 silicon-calibrated simulation 데이터로 검증한 결과, hold-out V_{min}을 millivolt 수준(read {{rmseR}} mV, write {{rmseW}} mV RMSE)으로 예측했고 학습에 쓰지 않은 PDK corner에서도 최악 corner를 정확히 짚었다. 무엇보다 total-order 전역 민감도 해석이 기존 corner 기반 검증의 사각지대를 드러낸다. local NMOS mismatch 축이 전역 PMOS threshold shift corner 축보다 read margin 분산에 더 크게 기여하며, read margin 분산의 최소 {{offCorner}} %가 기존 corner 집합과 직교하는 공정 방향에 놓인다. 즉 corner만 보는 flow는 mismatch가 만드는 tail을 빠뜨려 V_{min}을 낙관적으로 잡을 수 있다. 이 framework는 역방향 질의도 지원해서, 목표 V_{min}을 맞추는 데 필요한 공정 shift(예: V_{th} 허용폭)를 바로 구할 수 있다. margin 분포는 전 구간에서 Gaussian으로 두었고 tail 형상 보정은 후속 연구로 남긴다. 그 가정 안에서 제안한 방법은 통계적 변동과 yield 목표, 그리고 실행 가능한 공정 사양을 잇는 견고하고 효율적인 workflow를 만든다.",
  },
  index: {
    en: "**Index Terms—**SRAM, minimum operating voltage (V_{min}), process variation, local mismatch, Gaussian process, yield analysis, global sensitivity analysis, design-technology co-optimization (DTCO).",
    kr: "**색인어—**SRAM, minimum operating voltage (V_{min}), process variation, local mismatch, Gaussian process, yield analysis, global sensitivity analysis, design-technology co-optimization (DTCO).",
  },

  s1h: { en: "I.  Introduction", kr: "I.  서론" },
  s1a: {
    en: "In advanced technology nodes, process variation and device mismatch increasingly constrain SRAM bitcell stability, which is expressed through the minimum operating voltage (V_{min}) [1]–[3]. Traditional verification faces a dilemma. Full Monte Carlo (MC) analysis offers statistical completeness but is prohibitively expensive [4]–[6], while PDK corner analysis is fast but samples only a few predefined global directions.",
    kr: "선단 공정으로 갈수록 process variation과 device mismatch가 SRAM bitcell의 안정성을 조인다. 그 안정성을 대표하는 값이 최소 동작 전압 V_{min}이다 [1]–[3]. 기존 검증 방식은 딜레마에 놓여 있다. 전수 Monte Carlo(MC) 해석은 통계적으로 빠짐이 없지만 비용을 감당하기 어렵고 [4]–[6], PDK corner 해석은 빠른 대신 미리 정해둔 몇 개의 전역 방향만 훑는다.",
  },
  s1b: {
    en: "The critical flaw in corner-based analysis is its inability to capture variance driven by local mismatch, which does not align with the standard global corners (SSG, FFG, and their skewed variants). Consequently, designs signed off using corner simulations alone risk silicon yield loss from unmodeled statistical tails. Conversely, relying on MC sweeps for every design iteration is impractical under runtime constraints.",
    kr: "corner 해석의 결정적인 약점은 local mismatch가 만드는 분산을 담지 못한다는 것이다. mismatch의 방향은 표준 전역 corner(SSG, FFG와 그 skew 변형)와 어긋나 있다. 그래서 corner simulation만으로 sign-off한 설계는 모델에 없는 통계적 tail 때문에 silicon yield를 잃을 위험을 안는다. 그렇다고 설계를 고칠 때마다 MC를 돌리는 것은 runtime이 허락하지 않는다.",
  },
  s1c: {
    en: "This work proposes a physics-guided framework that resolves the trade-off. The goal is not to replace circuit simulation with a statistical surrogate, but to maximize the insight extracted from a fixed simulation budget. The core idea is to model the process-dependent statistics of the noise margin — its mean μ and standard deviation σ — rather than regressing V_{min} directly. By retaining an analytic yield relation, the framework preserves the physical link between the margin distribution and the yield probability. This provides three capabilities:",
    kr: "이 연구는 그 trade-off를 푸는 physics-guided framework를 제안한다. 목표는 circuit simulation을 통계 surrogate로 대체하는 것이 아니라, 정해진 simulation budget에서 뽑아낼 수 있는 정보를 최대로 끌어내는 것이다. 핵심은 V_{min}을 직접 회귀하지 않고 noise margin의 공정 의존 통계량 — 평균 μ와 표준편차 σ — 를 모델링하는 데 있다. yield 관계식을 analytic하게 남겨 두면 margin 분포와 yield 확률 사이의 물리적 연결이 끊기지 않는다. 여기서 세 가지 기능이 나온다.",
  },
  s1i1: {
    en: "1)\tAccurate forward prediction: estimating V_{min} for arbitrary process conditions with millivolt precision.",
    kr: "1)\t순방향 예측: 임의의 공정 조건에서 V_{min}을 millivolt 수준으로 추정한다.",
  },
  s1i2: {
    en: "2)\tInverse process specification: determining the maximum allowable process shift — the process window — that still meets a target V_{min}.",
    kr: "2)\t역방향 공정 사양 도출: 목표 V_{min}을 지키는 최대 허용 공정 shift, 즉 process window를 구한다.",
  },
  s1i3: {
    en: "3)\tSensitivity-driven insight: quantifying the impact of global shifts against local mismatch, exposing the blind spots of corner-only verification.",
    kr: "3)\t민감도 기반 통찰: 전역 shift와 local mismatch의 기여를 정량 비교해서 corner만 보는 검증의 사각지대를 드러낸다.",
  },
  s1d: {
    en: "We demonstrate the framework on an advanced FinFET node and show that local mismatch can dominate read-margin variance — a phenomenon invisible to standard corner analysis. This makes a compelling case for integrating statistical sensitivity analysis into the standard SRAM sign-off flow.",
    kr: "선단 FinFET 공정에서 이 framework를 시연하고, local mismatch가 read margin 분산을 지배할 수 있음을 보인다. 표준 corner 해석으로는 보이지 않는 현상이다. 통계적 민감도 해석을 SRAM sign-off flow에 넣어야 할 이유가 여기 있다.",
  },

  s2h: { en: "II.  Physics-Guided Modeling Framework", kr: "II.  Physics-guided 모델링 framework" },
  s2ah: { en: "A.  Decoupling Margin Statistics From the Yield Definition", kr: "A.  margin 통계량과 yield 정의의 분리" },
  s2a1: {
    en: "Directly regressing V_{min} hides the physical causes of failure. Instead, the framework models the conditional mean μ and standard deviation σ of the SRAM noise margin as continuous functions of the process parameters p — gate length, threshold voltage, oxide thickness, and the local-mismatch axes — and of the supply voltage V_{DD}. The yield probability Y then follows analytically from the standard normal cumulative distribution function Φ:",
    kr: "V_{min}을 바로 회귀하면 fail의 물리적 원인이 가려진다. 그래서 이 framework는 SRAM noise margin의 조건부 평균 μ와 표준편차 σ를 공정 파라미터 p — gate length, threshold voltage, oxide thickness, 그리고 local mismatch 축들 — 와 공급 전압 V_{DD}의 연속 함수로 모델링한다. yield 확률 Y는 표준정규 누적분포함수 Φ로 analytic하게 따라온다.",
  },
  s2a2: {
    en: "and V_{min} is the lowest supply that still satisfies the yield target, equivalently the lowest supply at which the margin tail stays non-negative:",
    kr: "V_{min}은 yield 목표를 만족하는 가장 낮은 공급 전압, 달리 말해 margin tail이 음수로 내려가지 않는 최저 전압이다.",
  },
  s2a3: {
    en: "where k is the yield-referenced tail multiplier set by the array size and the target failure probability. Two properties matter for device engineers.",
    kr: "여기서 k는 array 크기와 목표 fail 확률이 정하는 yield 기준 tail 배율이다. 소자 엔지니어 입장에서 중요한 성질은 두 가지다.",
  },
  s2a4: {
    en: "**Physical transparency.** The model explicitly separates how process variation moves the center of the margin distribution from how it changes the spread. This makes it possible to diagnose whether a V_{min} shift stems from a global process drift or from increased local variability — a distinction a direct V_{min} regression collapses.",
    kr: "**물리적 투명성.** 공정 변동이 margin 분포의 중심을 옮기는 효과와 폭을 넓히는 효과를 모델이 따로 들고 있다. 덕분에 V_{min}이 밀린 원인이 전역 공정 drift인지 국소 변동 증가인지 진단할 수 있다. V_{min}을 직접 회귀하면 이 구분이 뭉개진다.",
  },
  s2a5: {
    en: "**Robust inverse solving.** Because the yield relation is analytic and monotonic in V_{DD} over the queried range, finding V_{min} in the forward direction or the limiting process parameter in the inverse direction becomes a stable root-finding problem, avoiding the instability of black-box inversion. The pipeline is summarized in Fig. {{figPipe}}.",
    kr: "**안정적인 역해.** yield 관계식이 analytic하고 질의 구간에서 V_{DD}에 대해 단조롭기 때문에, 순방향의 V_{min}이든 역방향의 한계 공정 파라미터든 안정적인 root-finding 문제가 된다. black-box 역산이 겪는 불안정성을 피한다. 전체 pipeline은 Fig. {{figPipe}}에 정리했다.",
  },

  s2bh: { en: "B.  Capturing Process Continuity and Sensitivity", kr: "B.  공정 연속성과 민감도의 포착" },
  s2b1: {
    en: "To model the mapping from process space to margin statistics we use a Gaussian process (GP) regressor [10], [11]. In device-physics terms the GP acts as a smooth, physics-consistent interpolator: it assumes that a small change in a process parameter — a 1 nm shift in gate length, say — produces a small, continuous change in the margin statistics, respecting the continuity of semiconductor behavior.",
    kr: "공정 공간에서 margin 통계량으로 가는 사상을 모델링하는 데 Gaussian process(GP) regressor를 쓴다 [10], [11]. 소자 물리의 언어로 하면 GP는 매끄럽고 물리에 어긋나지 않는 interpolator다. 공정 파라미터가 조금 움직이면 — 예를 들어 gate length가 1 nm 밀리면 — margin 통계량도 조금 연속적으로 움직인다고 가정한다. 반도체 거동의 연속성을 그대로 반영한 셈이다.",
  },
  s2b2: {
    en: "The model further uses automatic relevance determination (ARD) to learn a lengthscale per process axis. This lets the framework distinguish parameters whose variation produces rapid changes in stability, such as local V_{th} mismatch, from those that trend smoothly. The fitted lengthscales inform the model; the variance decomposition that quantifies risk is developed separately in Section V.",
    kr: "여기에 automatic relevance determination(ARD)을 얹어 공정 축마다 lengthscale을 학습한다. local V_{th} mismatch처럼 조금만 흔들려도 안정성이 급격히 변하는 축과, 완만하게 움직이는 축을 모델이 스스로 구분한다. 다만 학습된 lengthscale은 모델을 설명할 뿐이고, 위험을 정량화하는 분산 분해는 Section V에서 따로 다룬다.",
  },

  s2ch: { en: "C.  Inverse Query: From Electrical Target to Process Window", kr: "C.  역방향 질의: 전기적 목표에서 process window로" },
  s2c1: {
    en: "A distinguishing feature of the framework is the inverse query, which reverses the conventional analysis flow. Instead of asking *what is the V_{min} at this process corner?*, the engineer asks *what process shift degrades V_{min} to our target limit?*",
    kr: "이 framework를 다른 것과 구분 짓는 기능이 역방향 질의다. 해석의 방향이 뒤집힌다. *이 공정 corner에서 V_{min}이 얼마인가*를 묻는 대신 *어떤 공정 shift가 V_{min}을 목표 한계까지 끌어내리는가*를 묻는다.",
  },
  s2c2: {
    en: "Mathematically, for a fixed target V_{min} and yield we solve for the value of a single process axis p_{i} while holding the remaining axes fixed. Because the other coordinates are frozen, the problem is one-dimensional and is solved by bisection on an interval whose monotonicity has been verified. This maps the electrical specification boundary back into the process-control space, which is directly useful for:",
    kr: "수식으로 보면, 목표 V_{min}과 yield를 고정한 뒤 나머지 축을 묶어 두고 공정 축 p_{i} 하나의 값을 푼다. 다른 좌표가 고정되므로 문제는 1차원이 되고, 단조성을 확인한 구간에서 이분 탐색으로 푼다. 전기적 사양 경계가 공정 관리 공간으로 되돌아오는 것이다. 쓰임새는 두 가지다.",
  },
  s2ci1: {
    en: "•\t**Setting process specs.** Defining realistic 3σ limits for V_{th} or gate length from actual circuit yield targets rather than from historical convention.",
    kr: "•\t**공정 사양 설정.** V_{th}나 gate length의 3σ 한계를 관행이 아니라 실제 회로 yield 목표에서 뽑아낸다.",
  },
  s2ci2: {
    en: "•\t**Yield debugging.** Identifying the process parameter most likely responsible when silicon V_{min} exceeds expectation.",
    kr: "•\t**Yield 디버깅.** silicon V_{min}이 예상보다 높게 나왔을 때 어느 공정 파라미터가 범인일 가능성이 큰지 짚어낸다.",
  },

  s3h: { en: "III.  Validation: Prediction Accuracy and Corner Generalization", kr: "III.  검증: 예측 정확도와 corner 일반화" },
  s3a: {
    en: "The framework was validated on silicon-calibrated simulation data from an advanced FinFET technology. Throughout this paper the reference values are independent circuit simulations, not silicon measurements. The evaluation focused on two metrics: prediction accuracy on unseen conditions, and generalization to standard PDK corners excluded from training.",
    kr: "선단 FinFET 공정의 silicon-calibrated simulation 데이터로 framework를 검증했다. 이 논문에서 기준값은 모두 독립적으로 돌린 circuit simulation이며 silicon 실측이 아니다. 평가는 두 가지에 맞췄다. 학습에 쓰지 않은 조건에서의 예측 정확도, 그리고 학습에서 제외한 표준 PDK corner로의 일반화다.",
  },
  s3ah: { en: "A.  Millivolt-Level Prediction Accuracy", kr: "A.  millivolt 수준의 예측 정확도" },
  s3a1: {
    en: "The model shows high fidelity in predicting V_{min} across the process space: {{rmseR}} mV RMSE for read and {{rmseW}} mV for write on hold-out data (Table {{tabAcc}}, Fig. {{figFwd}}). Sub-{{rmseW}}-mV accuracy is well inside the error budget required for early-stage design exploration, and the read and write errors now sit within roughly a factor of two of each other.",
    kr: "공정 공간 전체에서 V_{min} 예측 정확도가 높다. hold-out 기준으로 read {{rmseR}} mV, write {{rmseW}} mV RMSE다(Table {{tabAcc}}, Fig. {{figFwd}}). 초기 설계 탐색에 필요한 오차 예산 안에 충분히 들어오고, read와 write의 오차 차이도 대략 2배 안쪽으로 좁혀졌다.",
  },
  s3a2: {
    en: "The remaining read/write gap is a σ-model effect, not a difference in the switching physics. With the σ GP specified as a full-ARD kernel on log σ — the scale on which the MC observation noise sem_{σ} = σ/√(2N) is homoscedastic — the write σ fit (R² = {{sigR2W}}) is comparable to read (R² = {{sigR2R}}). An earlier additive-kernel, linear-σ specification produced a much weaker write σ fit and invited the explanation that the write margin is intrinsically harder to model because V_{trip} is a ratio of two drive strengths. That explanation does not survive: the gap was kernel misspecification. Since V_{min} is the crossing of z = μ/σ, any σ error is inherited directly by V_{min}, which is why the σ kernel dominates the accuracy budget.",
    kr: "남은 read/write 격차는 σ 모델의 문제이지 switching 물리의 차이가 아니다. σ GP를 log σ 위의 full-ARD kernel로 두면 — MC 관측잡음 sem_{σ} = σ/√(2N)이 등분산이 되는 축이 log σ다 — write의 σ 적합도(R² = {{sigR2W}})가 read(R² = {{sigR2R}})와 비슷해진다. 이전의 가법 kernel · linear σ 설정에서는 write σ가 훨씬 나쁘게 나왔고, 그걸 두고 V_{trip}이 두 구동 전류의 비라서 write margin이 본질적으로 모델링하기 어렵다는 설명이 붙었다. 그 설명은 성립하지 않는다. 격차의 정체는 kernel 오지정이었다. V_{min}은 z = μ/σ의 교차점이므로 σ 오차가 그대로 V_{min}으로 넘어간다. σ kernel이 정확도 예산을 좌우하는 이유다.",
  },
  t1: { en: ["TABLE {{tabAcc}}", "V_{MIN} PREDICTION ACCURACY", ["Test set", "Read", "Write"]],
        kr: ["표 {{tabAcc}}", "V_{min} 예측 정확도", ["평가 집합", "Read", "Write"]] },
  t1r: { en: [["Hold-out conditions (RMSE)", "**{{rmseR}} mV**", "**{{rmseW}} mV**"],
              ["Unseen PDK corners (RMSE)", "**{{corR}} mV**", "**{{corW}} mV**"],
              ["Limiting corner identified", "{{limOkR}}", "{{limOkW}}"],
              ["Margin σ fit (R²)", "{{sigR2R}}", "{{sigR2W}}"]],
        kr: [["Hold-out 조건 (RMSE)", "**{{rmseR}} mV**", "**{{rmseW}} mV**"],
             ["미학습 PDK corner (RMSE)", "**{{corR}} mV**", "**{{corW}} mV**"],
             ["최악 corner 식별", "{{limOkR}}", "{{limOkW}}"],
             ["Margin σ 적합도 (R²)", "{{sigR2R}}", "{{sigR2W}}"]] },

  s3bh: { en: "B.  Robustness to Unseen PDK Corners", kr: "B.  미학습 PDK corner에 대한 견고성" },
  s3b1: {
    en: "A critical test for any compact model is extrapolation to the standard industry corners — SSG, FFG, SFG, FSG — held out of the training set. The model achieved {{corR}} mV (read) and {{corW}} mV (write) RMSE on the four unseen corners, and identified the worst-case corner correctly for both read and write. Table {{tabCorner}} lists the per-corner results and Fig. {{figCorner}} plots both modes on one axis.",
    kr: "compact model이 반드시 통과해야 할 시험이 학습에서 뺀 표준 corner — SSG, FFG, SFG, FSG — 로의 외삽이다. 네 개의 미학습 corner에서 read {{corR}} mV, write {{corW}} mV RMSE가 나왔고, read와 write 모두 최악 corner를 정확히 짚었다. corner별 결과는 Table {{tabCorner}}에, 두 mode를 한 축에 겹쳐 그린 것은 Fig. {{figCorner}}에 있다.",
  },
  s3b2: {
    en: "Two qualifications keep the claim honest. First, where two corners sit closer together than the corner RMSE, their predicted ordering is not supportable — the claim is that the *limiting* corner is identified, not that corners a few millivolts apart are ranked. That is what sign-off uses in any case. Second, read and write are limited by *different* corners ({{limR}} and {{limW}} respectively), each of which is censored below 0.4 V in the other mode, so a single-mode corner sweep sees only half the picture.",
    kr: "주장을 정확히 하려면 단서를 두 개 달아야 한다. 첫째, 두 corner의 간격이 corner RMSE보다 좁으면 그 둘의 예측 순서는 주장할 수 없다. 여기서 말할 수 있는 것은 *최악* corner를 짚었다는 것이지, 몇 millivolt 차이의 서열을 맞혔다는 것이 아니다. sign-off가 쓰는 정보도 어차피 전자다. 둘째, read와 write는 서로 *다른* corner에서 걸린다(각각 {{limR}}와 {{limW}}). 그리고 각 corner는 반대 mode에서 0.4 V 아래로 censored된다. 한 mode만 corner sweep으로 보면 절반만 보는 셈이다.",
  },
  s3b3: {
    en: "These results confirm that the framework acts as a high-fidelity verification layer, filling the gaps between discrete PDK corners without the cost of full MC sweeps.",
    kr: "이 결과는 framework가 이산적인 PDK corner 사이의 빈 곳을 메우는 고정밀 검증 층으로 동작한다는 것을 보여준다. 전수 MC를 돌리는 비용 없이 그렇게 한다.",
  },
  t2: { en: ["TABLE {{tabCorner}}", "V_{MIN} PER PDK CORNER — REFERENCE SIMULATION vs. SURROGATE",
             ["Corner", "(ΔV_{th,N}, ΔV_{th,P}) mV", "Read: ref → GP", "Write: ref → GP"]],
        kr: ["표 {{tabCorner}}", "PDK corner별 V_{min} — 기준 simulation 대 surrogate",
             ["Corner", "(ΔV_{th,N}, ΔV_{th,P}) mV", "Read: 기준 → GP", "Write: 기준 → GP"]] },

  s4h: { en: "IV.  Inverse Analysis: Deriving Process Specifications", kr: "IV.  역방향 해석: 공정 사양의 도출" },
  s4a: {
    en: "The inverse capability turns the tool from a passive predictor into an active specification engine. We evaluated the model's ability to recover the threshold-voltage shift required to hit a specified target V_{min}, holding the other process axes fixed. The model recovers V_{th} shifts with {{invCn}}–{{invPu}} mV RMSE (Table {{tabInv}}), and Fig. {{figInv}} shows the corresponding V_{min} contours and the recovered specification boundary in the (ΔV_{th,N}, ΔV_{th,P}) plane.",
    kr: "역방향 기능은 이 도구를 수동적인 예측기에서 능동적인 사양 엔진으로 바꾼다. 나머지 공정 축을 고정한 채, 지정한 목표 V_{min}에 도달하는 데 필요한 threshold voltage shift를 모델이 복원할 수 있는지 평가했다. V_{th} shift를 {{invCn}}–{{invPu}} mV RMSE로 복원한다(Table {{tabInv}}). Fig. {{figInv}}는 (ΔV_{th,N}, ΔV_{th,P}) 평면에서의 V_{min} 등고선과 복원된 사양 경계를 보여준다.",
  },
  t3: { en: ["TABLE {{tabInv}}", "INVERSE RECOVERY OF THRESHOLD-VOLTAGE SHIFT",
             ["Recovered axis", "RMSE", "Median", "Bias"]],
        kr: ["표 {{tabInv}}", "Threshold voltage shift의 역방향 복원",
             ["복원 축", "RMSE", "중앙값", "편향"]] },
  s4b: {
    en: "This accuracy lets process-integration teams tighten or loosen process windows on the basis of actual circuit sensitivity. If the analysis shows that a 5 mV V_{th} shift causes a V_{min} violation, the process spec can be set with confidence at ±15 mV (3σ). The direct mapping from an electrical target to a process limit streamlines the design-technology co-optimization (DTCO) loop, and because the inverse runs on the already-validated surrogate, no additional simulation campaign is needed per query.",
    kr: "이 정확도면 process integration 팀이 실제 회로 민감도를 근거로 process window를 조이거나 풀 수 있다. 5 mV의 V_{th} shift가 V_{min} 위반을 일으킨다는 분석이 나오면 공정 사양을 ±15 mV(3σ)로 자신 있게 잡는 식이다. 전기적 목표에서 공정 한계로 바로 이어지는 이 사상이 design-technology co-optimization(DTCO) loop를 짧게 만든다. 역해는 이미 검증된 surrogate 위에서 돌기 때문에 질의마다 simulation을 새로 돌릴 필요가 없다.",
  },
  f4cap: {
    en: "**Fig. {{figInv}}.**  V_{min} contours over the (ΔV_{th,N}, ΔV_{th,P}) plane with the specification boundary recovered by axis-wise inverse query.",
    kr: "**Fig. {{figInv}}.**  (ΔV_{th,N}, ΔV_{th,P}) 평면의 V_{min} 등고선과 축별 역방향 질의로 복원한 사양 경계.",
  },

  s4ah: { en: "A.  Coordinate Recovery Accuracy", kr: "A.  좌표 복원 정확도" },
  s4bh: { en: "B.  Scenario: Meeting a 50 mV Lower V_{min} Target", kr: "B.  시나리오: V_{min} 목표를 50 mV 낮출 때" },
  s4b1: {
    en: "The same machinery answers the question a customer actually asks. Suppose the target moves from V_{T0} = 0.625 V down to {{scTarget}} V. Section III-B established that FSG limits read and SFG limits write, and that each is censored below 0.4 V in the other mode, so both Vmin(FSG, read) and Vmin(SFG, write) must clear the new target — today they exceed it by {{scGapR}} mV and {{scGapW}} mV. Treating each improvement lever as the axis to solve for, the same one-dimensional bisection returns how far that lever has to move (Table {{tabScen}}). {{scVerdict}} Fig. {{figScen}} draws the resulting passing window for each case, with the read and write boundaries on one plane; the shipped window is their intersection, not either one alone.",
    kr: "같은 구조가 고객이 실제로 던지는 질문에도 답한다. 목표가 V_{T0} = 0.625 V에서 {{scTarget}} V로 내려간다고 하자. Section III-B에서 read는 FSG가, write는 SFG가 한계이고 각각 반대 mode에서는 0.4 V 아래로 censored된다는 것을 확인했다. 따라서 Vmin(FSG, read)와 Vmin(SFG, write)가 동시에 새 목표를 넘어야 하는데, 지금은 각각 {{scGapR}} mV, {{scGapW}} mV 초과한다. 개선 수단 하나하나를 풀어야 할 축으로 놓으면 같은 1차원 이분 탐색이 그 축을 얼마나 움직여야 하는지 돌려준다(Table {{tabScen}}). {{scVerdict}} Fig. {{figScen}}은 각 case의 통과 영역을 read·write 경계와 함께 한 평면에 그린 것이다. 실제로 출하 가능한 영역은 둘의 교집합이지 어느 한쪽이 아니다.",
  },
  t6: { en: ["TABLE {{tabScen}}", "PROCESS IMPROVEMENT REQUIRED FOR V_{MIN} = {{scTarget}} V",
             ["Improvement lever", "Required setting", "Binding V_{min}"]],
        kr: ["표 {{tabScen}}", "V_{min} = {{scTarget}} V 달성에 필요한 공정 개선",
             ["개선 수단", "필요 수준", "한계 V_{min}"]] },
  f10: { en: "**Fig. {{figScen}}.**  Passing window at V_{min} = {{scTarget}} V for the baseline and each improvement case, over the (ΔV_{th,N}, ΔV_{th,P}) plane. Red is the read boundary, yellow the write boundary, and the hatched region is where both modes clear the target. Stars mark the two limiting PDK corners; a filled star means that corner now passes.",
         kr: "**Fig. {{figScen}}.**  baseline과 각 개선 case에서 V_{min} = {{scTarget}} V를 통과하는 영역을 (ΔV_{th,N}, ΔV_{th,P}) 평면에 그린 것. 빨강이 read 경계, 노랑이 write 경계이고 빗금친 영역이 두 mode 모두 목표를 넘는 구간이다. 별표는 두 한계 PDK corner이며, 속이 찬 별은 그 corner가 이제 통과한다는 뜻이다." },

  s5h: { en: "V.  Key Insight: Exposing the Blind Spots of Corner Analysis", kr: "V.  핵심 통찰: corner 해석의 사각지대" },
  s5a: {
    en: "The most significant contribution of this work is a quantitative demonstration of the limits of corner-only verification. Using total-order Sobol global sensitivity analysis [13], [14] on the surrogate output, we compared the variance contribution of the conventional global corner axes against the local-mismatch axes over the allowed process range, interactions included. Total-order indices are the right instrument here: an ARD lengthscale describes how smooth the function is, whereas a Sobol index measures how much of the output variance an axis actually carries.",
    kr: "이 연구의 가장 중요한 기여는 corner만 보는 검증의 한계를 정량적으로 보인 것이다. surrogate 출력에 total-order Sobol 전역 민감도 해석 [13], [14]을 적용해서, 허용 공정 범위 전체에서 기존 전역 corner 축과 local mismatch 축의 분산 기여를 상호작용까지 포함해 비교했다. 여기서는 total-order 지수가 맞는 도구다. ARD lengthscale은 함수가 얼마나 매끄러운지를 말할 뿐이고, 출력 분산을 실제로 얼마나 지고 있는지를 재는 것은 Sobol 지수다.",
  },
  s5ah: { en: "A.  The Dominance of Local Mismatch", kr: "A.  local mismatch의 우위" },
  s5a1: {
    en: "The analysis produces a counter-intuitive but critical finding: **the local NMOS common-mismatch axis k_{σN} contributes more read-margin variance than the standard PMOS threshold-shift corner axis ΔV_{th,P}** — total-order indices of {{stKsn}} against {{stPu}} (Table {{tabSobol}}, Fig. {{figSens}}). The ranking is a total-order statement; on first-order indices alone the two axes are close and the ordering can reverse, which is precisely why interactions must be included.",
    kr: "해석 결과는 직관에 어긋나지만 중요하다. **local NMOS 공통 mismatch 축 k_{σN}이 표준 PMOS threshold shift corner 축 ΔV_{th,P}보다 read margin 분산에 더 크게 기여한다.** total-order 지수로 {{stKsn}} 대 {{stPu}}다(Table {{tabSobol}}, Fig. {{figSens}}). 이 서열은 total-order 기준이다. first-order 지수만 보면 두 축이 붙어 있고 순서가 뒤집힐 수도 있다. 상호작용을 반드시 넣어야 하는 이유가 그것이다.",
  },
  s5a2: {
    en: "The bound this places on corner methods is quantitative. The two corner axes ΔV_{th,N} and ΔV_{th,P} sum to {{cornerSum}}, and because total-order indices overlap through interactions that sum is an *upper* bound on their joint share. The remaining seven axes therefore carry **at least {{offCorner}} % of the read-margin variance** — variance that lies in process directions orthogonal to the conventional corner set.",
    kr: "여기서 corner 방식에 걸리는 한계는 정량적이다. corner 축인 ΔV_{th,N}과 ΔV_{th,P}의 합은 {{cornerSum}}이고, total-order 지수는 상호작용을 통해 서로 겹치므로 이 합은 두 축이 함께 차지하는 몫의 *상한*이다. 따라서 나머지 일곱 축이 **read margin 분산의 최소 {{offCorner}} %** 를 지고 있다. 기존 corner 집합과 직교하는 공정 방향에 놓인 분산이다.",
  },
  t4: { en: ["TABLE {{tabSobol}}", "TOTAL-ORDER SOBOL INDICES OF THE READ MARGIN",
             ["Process axis", "Physical meaning", "Corner axis?", "S_{T}"]],
        kr: ["표 {{tabSobol}}", "Read margin의 total-order Sobol 지수",
             ["공정 축", "물리적 의미", "Corner 축?", "S_{T}"]] },
  s5bh: { en: "B.  Implications for SRAM Sign-Off", kr: "B.  SRAM sign-off에 주는 함의" },
  s5b0: { en: "This finding has three implications for SRAM verification.", kr: "이 결과가 SRAM 검증에 주는 함의는 세 가지다." },
  s5b1: {
    en: "1)\t**Under-estimation of risk.** Standard corner analysis captures shifts in the *mean* margin but systematically underestimates the *spread* driven by local mismatch. Since V_{min} is set by the distribution tail, V_{min} = μ − kσ, ignoring these axes yields non-conservative, optimistic V_{min} estimates.",
    kr: "1)\t**위험의 과소평가.** 표준 corner 해석은 *평균* margin의 이동은 잡아내지만 local mismatch가 만드는 *산포*는 체계적으로 낮게 본다. V_{min}은 분포의 tail이 정하므로(V_{min} = μ − kσ), 이 축들을 빼면 V_{min}이 낙관적으로, 즉 보수적이지 않게 나온다.",
  },
  s5b2: {
    en: "2)\t**Misleading worst-case identification.** The worst-case corner identified by traditional methods may not be the true yield limiter when local mismatch is the dominant failure mechanism. Any V_{min} quoted at a corner is a worst case *in corner space*, hence a lower bound on the nine-dimensional worst case.",
    kr: "2)\t**최악 조건 오판.** local mismatch가 주된 fail 기구일 때, 기존 방식이 짚은 최악 corner가 실제 yield를 결정하는 지점이 아닐 수 있다. corner에서 뽑은 V_{min}은 어디까지나 *corner 공간 안의* 최악이고, 9차원 최악값의 하한일 뿐이다.",
  },
  s5b3: {
    en: "3)\t**Recommendation.** For advanced nodes, statistical analysis of local mismatch must be integrated alongside global corner checks. Relying solely on PDK corners is insufficient to guarantee yield.",
    kr: "3)\t**권고.** 선단 공정에서는 local mismatch의 통계 해석을 전역 corner 점검과 나란히 돌려야 한다. PDK corner만으로는 yield를 보장할 수 없다.",
  },

  s7h: { en: "VI.  Practical Implications for Design and Process Integration", kr: "VI.  설계·공정 통합 관점의 실용적 함의" },
  s7a: {
    en: "The proposed workflow maximizes the return on a simulation budget. A single calibration campaign enables:",
    kr: "제안한 workflow는 simulation budget의 회수율을 끌어올린다. 한 번의 calibration campaign으로 다음이 가능해진다.",
  },
  s7i1: {
    en: "1)\t**Instant what-if analysis.** Predicting V_{min} for any hypothetical process shift without re-simulation.",
    kr: "1)\t**즉각적인 what-if 해석.** 가정한 공정 shift가 무엇이든 다시 돌리지 않고 V_{min}을 예측한다.",
  },
  s7i2: {
    en: "2)\t**Data-driven spec setting.** Deriving process-control limits directly from circuit yield targets through inverse queries.",
    kr: "2)\t**데이터 기반 사양 설정.** 역방향 질의로 회로 yield 목표에서 공정 관리 한계를 바로 끌어낸다.",
  },
  s7i3: {
    en: "3)\t**Risk prioritization.** Establishing that local mismatch, not the global corners, is the primary risk driver for read V_{min}, so mitigation effort — layout optimization, adaptive biasing — goes where it matters.",
    kr: "3)\t**위험의 우선순위.** read V_{min}의 주된 위험 요인이 전역 corner가 아니라 local mismatch임을 확정해서, layout 최적화나 adaptive biasing 같은 대응을 효과가 큰 쪽에 집중한다.",
  },
  s7b: {
    en: "The budget itself is a design variable, and its price is measurable. Cutting the number of conditions, the supply levels, and the MC depth together reduces the campaign by {{speedR}}× for read and {{speedW}}× for write, at a cost of +{{degR}} mV and +{{degW}} mV in V_{min} RMSE respectively (Table {{tabCost}}, Fig. {{figCost}}). Condition count and MC depth are not independent knobs — both enter the error through the σ estimate — so the combined penalty is smaller than the sum of the individual ones.",
    kr: "budget 자체도 설계 변수이고, 그 대가는 잴 수 있다. 조건 수와 전압 레벨, MC 깊이를 함께 줄이면 campaign이 read에서 {{speedR}}배, write에서 {{speedW}}배 가벼워지고, 그 대가로 V_{min} RMSE가 각각 +{{degR}} mV, +{{degW}} mV 늘어난다(Table {{tabCost}}, Fig. {{figCost}}). 조건 수와 MC 깊이는 독립적인 손잡이가 아니다. 둘 다 σ 추정을 거쳐 오차에 들어오기 때문에, 함께 줄였을 때의 손해가 따로 줄였을 때의 합보다 작다.",
  },
  t5: { en: ["TABLE {{tabCost}}", "COMBINED BUDGET REDUCTION, SAME HOLD-OUT SET", ["Quantity", "Read", "Write"]],
        kr: ["표 {{tabCost}}", "복합 budget 절감, 동일 hold-out 집합", ["항목", "Read", "Write"]] },
  t5r: { en: [["Budget ratio", "**{{speedR}}×**", "**{{speedW}}×**"],
              ["V_{min} RMSE, reduced", "{{costRmseR}} mV", "{{costRmseW}} mV"],
              ["V_{min} RMSE, baseline", "{{rmseR}} mV", "{{rmseW}} mV"],
              ["Degradation", "**+{{degR}} mV**", "**+{{degW}} mV**"]],
        kr: [["Budget 비율", "**{{speedR}}배**", "**{{speedW}}배**"],
             ["V_{min} RMSE, 절감본", "{{costRmseR}} mV", "{{costRmseW}} mV"],
             ["V_{min} RMSE, 기준", "{{rmseR}} mV", "{{rmseW}} mV"],
             ["열화", "**+{{degR}} mV**", "**+{{degW}} mV**"]] },
  s7c: {
    en: "For VLSI designers and process engineers this translates into reduced turn-around time, lower risk of silicon failure, and a deeper physical understanding of the variation-to-yield relationship.",
    kr: "VLSI 설계자와 공정 엔지니어에게 이는 turn-around time 단축, silicon fail 위험 감소, 그리고 변동과 yield의 관계에 대한 더 깊은 물리적 이해로 이어진다.",
  },

  s8h: { en: "VII.  Conclusion", kr: "VII.  결론" },
  s8a: {
    en: "We have presented a physics-guided framework for SRAM V_{min} estimation that overcomes the limitations of traditional corner analysis while avoiding the cost of exhaustive Monte Carlo sweeps. By modeling the margin statistics explicitly and retaining an analytic yield relation, the method achieves millivolt-level accuracy in both forward prediction — {{rmseR}} mV RMSE for read and {{rmseW}} mV for write, {{corR}} mV and {{corW}} mV on four unseen PDK corners with the limiting corner correctly identified — and inverse process recovery at {{invCn}}–{{invPu}} mV RMSE.",
    kr: "전통적인 corner 해석의 한계를 넘으면서 전수 Monte Carlo의 비용은 피하는 SRAM V_{min} 추정 framework를 제시했다. margin 통계량을 명시적으로 모델링하고 yield 관계식을 analytic하게 남겨 둠으로써, 순방향 예측(read {{rmseR}} mV, write {{rmseW}} mV RMSE, 미학습 PDK corner 네 곳에서 {{corR}} mV·{{corW}} mV이며 최악 corner 일치)과 역방향 공정 복원({{invCn}}–{{invPu}} mV RMSE) 모두에서 millivolt 수준의 정확도를 얻었다.",
  },
  s8b: {
    en: "Most critically, the work provides a device-level insight: local mismatch is a dominant driver of read-margin variance, exceeding the impact of the global PMOS threshold shift, with at least {{offCorner}} % of that variance lying off the conventional corner axes. This exposes a significant blind spot in corner-only verification flows, which may produce optimistic V_{min} estimates and yield loss. The Gaussian margin assumption, and whatever tail-shape correction it may eventually require, is left to future work; within it the proposed framework offers a robust, efficient, and interpretable foundation for design-technology co-optimization, connecting statistical variation, yield targets, and actionable process specifications.",
    kr: "무엇보다 이 연구는 소자 수준의 통찰을 하나 남긴다. local mismatch가 read margin 분산의 지배적인 요인이며 전역 PMOS threshold shift보다 영향이 크고, 그 분산의 최소 {{offCorner}} %가 기존 corner 축 바깥에 있다. corner만 보는 검증 flow의 큰 사각지대가 여기서 드러난다. V_{min}을 낙관적으로 잡아 yield를 잃을 수 있는 지점이다. Gaussian margin 가정과 그것이 언젠가 요구할 tail 형상 보정은 후속 연구로 남긴다. 그 안에서 제안한 framework는 통계적 변동과 yield 목표, 실행 가능한 공정 사양을 잇는 견고하고 효율적이며 해석 가능한 기반을 제공한다.",
  },
  refh: { en: "References", kr: "참고문헌" },

  f1: { en: "**Fig. {{figPipe}}.**  Pipeline overview. Two Gaussian-process regressors predict the margin mean μ and standard deviation σ over the nine process axes and the supply voltage; the analytic yield relation of (1)–(2) converts those statistics to V_{min}, and the same relation is inverted axis-wise to recover a process window.",
        kr: "**Fig. {{figPipe}}.**  전체 pipeline. 두 개의 Gaussian process regressor가 아홉 개 공정 축과 공급 전압 위에서 margin 평균 μ와 표준편차 σ를 예측하고, 식 (1)–(2)의 analytic yield 관계식이 그 통계량을 V_{min}으로 옮긴다. 같은 관계식을 축별로 역산하면 process window가 나온다." },
  f2: { en: "**Fig. {{figFwd}}.**  Reference-simulation versus predicted V_{min} on the hold-out conditions, read (left) and write (right). Hold-out RMSE is {{rmseR}} mV and {{rmseW}} mV respectively.",
        kr: "**Fig. {{figFwd}}.**  hold-out 조건에서의 기준 simulation 대 예측 V_{min}. 왼쪽이 read, 오른쪽이 write이며 hold-out RMSE는 각각 {{rmseR}} mV, {{rmseW}} mV다." },
  f3: { en: "**Fig. {{figCorner}}.**  V_{min} at the four PDK corners excluded from training, read and write on one axis. Outlined bars mark each mode's limiting corner — {{limR}} for read, {{limW}} for write — and the label above each pair is the surrogate-minus-reference error in millivolts.",
        kr: "**Fig. {{figCorner}}.**  학습에서 제외한 네 PDK corner의 V_{min}을 read·write 한 축에 겹쳐 그린 것. 테두리를 두른 막대가 각 mode의 최악 corner(read는 {{limR}}, write는 {{limW}})이고, 각 쌍 위의 숫자는 surrogate에서 기준값을 뺀 오차(mV)다." },
  f5: { en: "**Fig. {{figSens}}.**  Total-order Sobol indices with bootstrap confidence intervals for the read margin. The local-mismatch axis k_{σN} outranks the PMOS threshold-shift corner axis ΔV_{th,P}; the non-corner axes carry at least {{offCorner}} % of the variance.",
        kr: "**Fig. {{figSens}}.**  read margin의 total-order Sobol 지수와 bootstrap 신뢰구간. local mismatch 축 k_{σN}이 PMOS threshold shift corner 축 ΔV_{th,P}를 앞서고, corner가 아닌 축들이 분산의 최소 {{offCorner}} %를 지고 있다." },
  f7: { en: "**Fig. {{figCost}}.**  Budget-reduction trade-off: (a) number of process conditions, (b) MC depth per condition, (c) one factor cut alone against all three cut together. The combined {{speedR}}× reduction costs +{{degR}} mV of read V_{min} RMSE.",
        kr: "**Fig. {{figCost}}.**  budget 절감의 trade-off. (a) 공정 조건 수, (b) 조건당 MC 깊이, (c) 한 요인만 줄인 경우와 셋을 함께 줄인 경우의 대조. 셋을 함께 줄여 {{speedR}}배를 얻는 대가가 read V_{min} RMSE +{{degR}} mV다." },
};
const t = (k) => T[k][KR ? "kr" : "en"];

const REFS = [
  "C. Bae, S. Pae, C.-S. Yu, K. Kim, Y. Kim, and J. Park, \"SRAM stability design comprehending 14 nm FinFET reliability,\" in *Proc. IEEE Int. Rel. Phys. Symp. (IRPS)*, 2015, pp. MY.13.1–MY.13.5.",
  "A. T. Krishnan *et al.*, \"SRAM cell static noise margin and V_{MIN} sensitivity to transistor degradation,\" in *Proc. IEEE Int. Electron Devices Meeting (IEDM)*, 2006, pp. 1–4.",
  "T. Song *et al.*, \"A 14 nm FinFET 128 Mb SRAM with V_{MIN} enhancement techniques for low-power applications,\" *IEEE J. Solid-State Circuits*, vol. 50, no. 1, pp. 158–169, Jan. 2015.",
  "A. Singhee and R. A. Rutenbar, \"Statistical blockade: Very fast statistical simulation and modeling of rare circuit events and its application to memory design,\" *IEEE Trans. Comput.-Aided Design Integr. Circuits Syst.*, vol. 28, no. 8, pp. 1176–1189, Aug. 2009.",
  "R. Kanj, R. Joshi, and S. Nassif, \"Mixture importance sampling and its application to the analysis of SRAM designs in the presence of rare failure events,\" in *Proc. 43rd Design Autom. Conf. (DAC)*, 2006, pp. 69–72.",
  "A. Singhee and R. A. Rutenbar, \"Why quasi-Monte Carlo is better than Monte Carlo or Latin hypercube sampling for statistical circuit analysis,\" *IEEE Trans. Comput.-Aided Design Integr. Circuits Syst.*, vol. 29, no. 11, pp. 1763–1776, Nov. 2010.",
  "S. Yin, X. Jin, L. Shi, K. Wang, and W. W. Xing, \"Efficient Bayesian yield analysis and optimization with active learning,\" in *Proc. 59th ACM/IEEE Design Autom. Conf. (DAC)*, 2022, pp. 1195–1200.",
  "Y. Liu, G. Dai, and W. W. Xing, \"Seeking the yield barrier: High-dimensional SRAM evaluation through optimal manifold,\" in *Proc. 60th ACM/IEEE Design Autom. Conf. (DAC)*, 2023, pp. 1–6.",
  "Z. Guo, W. Sun, Z. Wang, Y. Cai, and L. Shi, \"An efficient SRAM yield analysis method using multi-fidelity neural network,\" in *Proc. 2nd Int. Symp. Electron. Design Autom. (ISEDA)*, 2024, pp. 547–551.",
  "C. E. Rasmussen and C. K. I. Williams, *Gaussian Processes for Machine Learning*. Cambridge, MA, USA: MIT Press, 2006.",
  "J. R. Gardner, G. Pleiss, D. Bindel, K. Q. Weinberger, and A. G. Wilson, \"GPyTorch: Blackbox matrix-matrix Gaussian process inference with GPU acceleration,\" in *Proc. Adv. Neural Inf. Process. Syst. (NeurIPS)*, vol. 31, 2018, pp. 7576–7586.",
  "M. J. M. Pelgrom, A. C. J. Duinmaijer, and A. P. G. Welbers, \"Matching properties of MOS transistors,\" *IEEE J. Solid-State Circuits*, vol. 24, no. 5, pp. 1433–1439, Oct. 1989.",
  "I. M. Sobol', \"Global sensitivity indices for nonlinear mathematical models and their Monte Carlo estimates,\" *Math. Comput. Simul.*, vol. 55, no. 1–3, pp. 271–280, Feb. 2001.",
  "A. Saltelli, P. Annoni, I. Azzini, F. Campolongo, M. Ratto, and S. Tarantola, \"Variance based sensitivity analysis of model output. Design and estimator for the total sensitivity index,\" *Comput. Phys. Commun.*, vol. 181, no. 2, pp. 259–270, Feb. 2010.",
  "S. Gupta and B. H. Calhoun, \"Dynamic read V_{min} and yield estimation for nanoscale SRAMs,\" *IEEE Trans. Circuits Syst. I, Reg. Papers*, vol. 68, no. 3, pp. 1171–1182, Mar. 2021.",
  "E. Seevinck, F. J. List, and J. Lohstroh, \"Static-noise margin analysis of MOS SRAM cells,\" *IEEE J. Solid-State Circuits*, vol. SC-22, no. 5, pp. 748–754, Oct. 1987.",
];

// ================================================================== assemble
const front = [
  new Paragraph({ children: runs(t("title"), { font: FONT, size: KR ? 40 : 48 }),
    alignment: AlignmentType.CENTER, spacing: { after: 240 } }),
  new Paragraph({ children: runs(t("authors"), { font: FONT, size: 24 }),
    alignment: AlignmentType.CENTER, spacing: { after: 60 } }),
  new Paragraph({ children: runs(t("affil"), BODY),
    alignment: AlignmentType.CENTER, spacing: { after: 300 } }),
];

const S2 = [
  p(t("abstract"), { after: 160 }), p(t("index"), { after: 240 }),
  h1(t("s1h")),
  p(t("s1a"), { noIndent: true, after: 120 }), p(t("s1b"), { after: 120 }),
  p(t("s1c"), { after: 120 }),
  p(t("s1i1"), { after: 40 }), p(t("s1i2"), { after: 40 }), p(t("s1i3"), { after: 120 }),
  p(t("s1d"), { after: 120 }),
  h1(t("s2h")), h2(t("s2ah")),
  p(t("s2a1"), { noIndent: true, after: 60 }),
  eq("Y(V_{DD}, p) = Φ[ μ(p, V_{DD}) / σ(p, V_{DD}) ]", 1),
  p(t("s2a2"), { noIndent: true, after: 60 }),
  eq("V_{min}(p) = min { V_{DD} : μ(p, V_{DD}) − k·σ(p, V_{DD}) ≥ 0 }", 2),
  p(t("s2a3"), { after: 120 }), p(t("s2a4"), { after: 120 }), p(t("s2a5"), { after: 120 }),
];

const S4 = [
  h2(t("s2bh")), p(t("s2b1"), { noIndent: true, after: 120 }), p(t("s2b2"), { after: 120 }),
  h2(t("s2ch")), p(t("s2c1"), { noIndent: true, after: 120 }), p(t("s2c2"), { after: 120 }),
  p(t("s2ci1"), { after: 40 }), p(t("s2ci2"), { after: 120 }),
  h1(t("s3h")), p(t("s3a"), { noIndent: true, after: 120 }),
  h2(t("s3ah")), p(t("s3a1"), { noIndent: true, after: 120 }), p(t("s3a2"), { after: 120 }),
  ...table(t("t1")[0], t("t1")[1], t("t1")[2], t("t1r"), false),
];

const S6 = [
  h2(t("s3bh")),
  p(t("s3b1"), { noIndent: true, after: 120 }), p(t("s3b2"), { after: 120 }), p(t("s3b3"), { after: 120 }),
];

const S8 = [
  h1(t("s4h")),
  ...(scen ? [h2(t("s4ah"))] : []),
  p(t("s4a"), { noIndent: true, after: 120 }),
  ...table(t("t3")[0], t("t3")[1], t("t3")[2], [
    ["ΔV_{th,N} (NMOS)", `**${N.invCn} mV**`, `${f(inv.recovery.cn.p50_mV, 2)} mV`, `${f(inv.recovery.cn.bias_mV, 2)} mV`],
    ["ΔV_{th,P} (PMOS)", `**${N.invPu} mV**`, `${f(inv.recovery.pu.p50_mV, 2)} mV`, `+${f(inv.recovery.pu.bias_mV, 2)} mV`],
  ], false),
  p(t("s4b"), { after: 120 }),
  ...figure("fig5_inverse", COL_PX, 280, t("f4cap"), false),
  ...(scen ? [
    h2(t("s4bh")),
    p(t("s4b1"), { noIndent: true, after: 120 }),
  ] : []),
];

// §IV-B's table and figure are wide -- full-width section of their own
const S8b = scen ? [
  ...table(t("t6")[0], t("t6")[1], t("t6")[2], scenRows, true),
  ...figure("fig10_scenario", FULL_PX, 291, t("f10"), true),
] : [];

const S9 = [h1(t("s5h")), p(t("s5a"), { noIndent: true, after: 120 })];

const S10 = [
  h2(t("s5ah")), p(t("s5a1"), { noIndent: true, after: 120 }), p(t("s5a2"), { after: 120 }),
  h2(t("s5bh")), p(t("s5b0"), { noIndent: true, after: 120 }),
  p(t("s5b1"), { after: 60 }), p(t("s5b2"), { after: 60 }), p(t("s5b3"), { after: 120 }),
];

const S12 = [
  h1(t("s7h")), p(t("s7a"), { noIndent: true, after: 120 }),
  p(t("s7i1"), { after: 40 }), p(t("s7i2"), { after: 40 }), p(t("s7i3"), { after: 120 }),
  p(t("s7b"), { after: 120 }),
  ...table(t("t5")[0], t("t5")[1], t("t5")[2], t("t5r"), false),
  p(t("s7c"), { after: 120 }),
];

const S14 = [
  h1(t("s8h")), p(t("s8a"), { noIndent: true, after: 120 }), p(t("s8b"), { after: 200 }),
  h1(t("refh")),
  ...REFS.map((ref, i) => new Paragraph({
    children: runs("[" + (i + 1) + "]\t" + ref, SMALL),
    alignment: AlignmentType.JUSTIFIED, spacing: { after: 60, line: 220 },
    indent: { left: convertInchesToTwip(0.25), hanging: convertInchesToTwip(0.25) },
  })),
];

const doc = new Document({
  styles: {
    default: { document: { run: BODY } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", quickFormat: true,
        run: { font: FONT, size: 20, smallCaps: !KR, bold: KR } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", quickFormat: true,
        run: { font: FONT, size: 20, italics: !KR, bold: KR } },
    ],
  },
  sections: [
    { properties: secProps(1), children: front },
    { properties: secProps(2), children: S2 },
    { properties: secProps(1), children: figure("fig1_pipeline", FULL_PX, 202, t("f1"), true) },
    { properties: secProps(2), children: S4 },
    { properties: secProps(1), children: figure("fig3_forward", FULL_PX, 278, t("f2"), true) },
    { properties: secProps(2), children: S6 },
    { properties: secProps(1), children: [
      ...table(t("t2")[0], t("t2")[1], t("t2")[2], cornerRows(), true),
      ...figure("fig4_corner", FULL_PX, 291, t("f3"), true)] },
    { properties: secProps(2), children: S8 },
    ...(scen ? [{ properties: secProps(1), children: S8b }] : []),
    { properties: secProps(2), children: S9 },
    { properties: secProps(1), children: [
      ...table(t("t4")[0], t("t4")[1], t("t4")[2], sobolRows(), true),
      ...figure("fig8_sensitivity", FULL_PX, 274, t("f5"), true)] },
    { properties: secProps(2), children: S10 },
    { properties: secProps(2), children: S12 },
    { properties: secProps(1), children: figure("fig7_cost", FULL_PX, 246, t("f7"), true) },
    { properties: secProps(2), children: S14 },
  ],
});

const out = path.join(ROOT, KR ? "SRAM_Vmin_IEEE_KR.docx" : "SRAM_Vmin_IEEE.docx");
Packer.toBuffer(doc).then((b) => {
  fs.writeFileSync(out, b);
  console.log("wrote", out);
  console.log("  read %s mV / write %s mV | corner %s / %s | off-corner >=%s%% | %sx budget",
    N.rmseR, N.rmseW, N.corR, N.corW, N.offCorner, N.speedR);
});
