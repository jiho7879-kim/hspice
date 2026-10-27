"use strict";
/* SRAM Vmin Studio — one page, hash routes:
     #/home  #/a/<kind>  #/run/<id>  #/library  #/runs  #/guide
   Forms are generated from /api/meta (the analysis catalogue). The spec object is
   the single source of truth: the form edits it, the JSON panel shows it verbatim,
   and the server stores it with every run so the CLI can replay it. */

const S = { meta: null, presets: [], specs: {}, timer: null };
const main = document.getElementById("main");

// ------------------------------------------------------------------ helpers
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid != null && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
  }
  return el;
}
const clone = (o) => JSON.parse(JSON.stringify(o));
const minus = (s) => String(s).replace(/-/g, "−");
const fmt = (x, d = 4) => (x == null || Number.isNaN(Number(x)) ? "—" : minus(Number(x).toFixed(d)));
const cellText = (v) => (v == null ? "—" : typeof v === "number" ? minus(String(+v.toPrecision(6))) : String(v));

async function api(path, opts) {
  const r = await fetch(path, opts);
  let j = null;
  try { j = await r.json(); } catch { /* not json */ }
  if (!r.ok) throw new Error((j && j.error) || `${r.status} ${r.statusText}`);
  return j;
}
const post = (path, body) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function getAt(o, path) { return path.split(".").reduce((a, k) => (a == null ? undefined : a[k]), o); }
function setAt(o, path, v) {
  const ks = path.split(".");
  let a = o;
  for (const k of ks.slice(0, -1)) { if (a[k] == null || typeof a[k] !== "object") a[k] = {}; a = a[k]; }
  a[ks[ks.length - 1]] = v;
}
function merged(defaults, spec) {
  const out = clone(defaults);
  for (const [k, v] of Object.entries(spec || {})) {
    out[k] = v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object" && !Array.isArray(out[k])
      ? merged(out[k], v) : v;
  }
  return out;
}
let uid = 0;
const nextId = () => `f${++uid}`;

// ------------------------------------------------------------------ boot / frame
async function boot() {
  try {
    [S.meta, S.presets] = await Promise.all([api("/api/meta"), api("/api/presets")]);
  } catch (e) {
    main.replaceChildren(h("p", { class: "error" }, `서버에 연결하지 못했습니다 — ${e.message}. service/main.py serve가 떠 있는지 확인하세요.`));
    return;
  }
  renderTop();
  renderNav();
  window.addEventListener("hashchange", route);
  route();
}

function renderTop() {
  const m = S.meta;
  const sc = m.selfcheck || [];
  const ok = sc.filter((c) => c.ok).length;
  const modes = Object.entries(m.modes).map(([k, v]) => `${k} ${minus(v.temperature_C)} °C`).join(" · ");
  const src = Object.values(m.modes)[0].source;
  document.getElementById("top-status").replaceChildren(
    h("b", {}, modes), ` · ${src} · Z ${fmt(m.z_default[0], 3)} (${m.z_default[1]}) · `,
    h("span", { class: ok === sc.length ? "ok" : "bad", title: "저장된 §V-D corner 예측을 지금 모델이 그대로 내는지" },
      `§V-D self-check ${ok}/${sc.length}`));
}

const GROUPS = [["Forward", "Forward · 조건 → Vmin"], ["Inverse", "Inverse · 목표 → 조건"], ["Sensitivity", "Sensitivity"]];
const navTitle = (a) => a.title.split(" (")[0];

function renderNav() {
  const link = (href, text) => h("a", { href }, text);
  const kids = [h("h2", {}, "Studio"), link("#/home", "시작"), link("#/library", "시나리오 라이브러리"), link("#/runs", "실행 기록")];
  for (const [g, label] of GROUPS) {
    const items = S.meta.analyses.filter((a) => a.group === g);
    if (!items.length) continue;
    kids.push(h("h2", {}, label));
    for (const a of items) kids.push(link(`#/a/${a.kind}`, navTitle(a)));
  }
  kids.push(h("h2", {}, "Help"), link("#/guide", "사용법 · 규약"));
  document.getElementById("nav").replaceChildren(...kids);
}

function markNav(href) {
  for (const a of document.querySelectorAll("#nav a")) {
    if (a.getAttribute("href") === href) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

function route() {
  clearTimeout(S.timer);
  const [view, arg] = location.hash.replace(/^#\/?/, "").split("/");
  if (view === "a" && arg) { markNav(`#/a/${arg}`); return viewAnalysis(arg); }
  if (view === "run" && arg) return viewRun(arg);
  if (view === "library") { markNav("#/library"); return viewLibrary(); }
  if (view === "runs") { markNav("#/runs"); return viewRuns(); }
  if (view === "guide") { markNav("#/guide"); return viewGuide(); }
  markNav("#/home");
  return viewHome();
}

// ------------------------------------------------------------------ analysis workspace
const entry = (kind) => S.meta.analyses.find((a) => a.kind === kind);
function specFor(kind) {
  if (!S.specs[kind]) S.specs[kind] = clone(entry(kind).defaults);
  return S.specs[kind];
}

function viewAnalysis(kind, result, progress) {
  const a = entry(kind);
  if (!a) return viewHome();
  const spec = specFor(kind);
  const formBox = h("div", { class: "form" });
  const resBox = h("div", { class: "result", "aria-live": "polite" });
  main.replaceChildren(
    h("p", { class: "eyebrow" }, a.group),
    h("h1", {}, a.title),
    h("p", { class: "lede" }, a.description),
    h("div", { class: "work" }, formBox, resBox));
  renderForm(formBox, a, spec, resBox);
  if (result) renderResult(resBox, result);
  else if (progress) renderProgress(resBox, progress);
  else resBox.append(h("p", { class: "result-empty" },
    "조건을 정하고 실행을 누르면 결과가 여기에 나옵니다. 모든 실행은 spec·그림·CSV와 함께 실행 기록에 남습니다."));
  main.focus();
}

function row(labelText, control, hint) {
  if (!control.id) control.id = nextId();
  return h("div", { class: "row" },
    h("label", { for: control.id }, labelText),
    h("div", {}, control, hint ? h("span", { class: "hint" }, hint) : null));
}

function numInput(spec, path, touch, { int = false } = {}) {
  const v = getAt(spec, path);
  const el = h("input", { type: "number", step: int ? "1" : "any", value: v == null ? "" : String(v) });
  el.addEventListener("change", () => {
    const t = el.value.trim();
    setAt(spec, path, t === "" ? null : int ? parseInt(t, 10) : parseFloat(t));
    touch();
  });
  return el;
}

function checkbox(spec, path, text, touch) {
  const id = nextId();
  const el = h("input", { type: "checkbox", id });
  el.checked = !!getAt(spec, path);
  el.addEventListener("change", () => { setAt(spec, path, el.checked); touch(); });
  return h("label", { for: id }, el, text);
}

function axisSelect(spec, path, touch) {
  const el = h("select", {}, ...S.meta.axes.map((ax) => h("option", { value: ax.key }, `${ax.key} — ${ax.name}`)));
  el.value = getAt(spec, path) || S.meta.axes[0].key;
  el.addEventListener("change", () => { setAt(spec, path, el.value); touch(); });
  return el;
}

function fieldControl(spec, f, touch) {
  const v = getAt(spec, f.key);
  if (f.type === "number" || f.type === "int") return numInput(spec, f.key, touch, { int: f.type === "int" });
  if (f.type === "axis") return axisSelect(spec, f.key, touch);
  if (f.type === "bool") return checkbox(spec, f.key, "", touch);
  if (f.type === "select") {
    const el = h("select", {}, ...f.options.map(([val, lab]) => h("option", { value: JSON.stringify(val) }, lab)));
    el.value = JSON.stringify(v ?? null);
    el.addEventListener("change", () => { setAt(spec, f.key, JSON.parse(el.value)); touch(); });
    return el;
  }
  if (f.type === "multi") {
    const cur = new Set(v || []);
    return h("div", { class: "checks" }, ...f.options.map(([val, lab]) => {
      const id = nextId();
      const el = h("input", { type: "checkbox", id });
      el.checked = cur.has(val);
      el.addEventListener("change", () => {
        const now = new Set(getAt(spec, f.key) || []);
        if (el.checked) now.add(val); else now.delete(val);
        setAt(spec, f.key, f.options.map(([x]) => x).filter((x) => now.has(x)));
        touch();
      });
      return h("label", { for: id }, el, lab);
    }));
  }
  if (f.type === "numbers") {
    const el = h("input", { type: "text", value: (v || []).join(", ") });
    el.addEventListener("change", () => {
      setAt(spec, f.key, el.value.split(/[,\s]+/).filter(Boolean).map(Number).filter((x) => Number.isFinite(x)));
      touch();
    });
    return el;
  }
  const el = h("input", { type: "text", value: Array.isArray(v) ? v.join(", ") : v ?? "" });
  el.addEventListener("change", () => { setAt(spec, f.key, el.value); touch(); });
  return el;
}

// lever editor ---------------------------------------------------------------
const LEVER_TYPES = [["scale", "scale · 배율"], ["pull", "pull · global 폭"], ["shift", "shift · Vth 이동"]];
const pctType = (t) => t !== "shift";

function leverEditor(spec, f, touch) {
  const wrap = h("div");
  const fixed = !!f.fixed;
  const cols = new Set(f.columns);
  const draw = () => {
    const L = spec.levers || (spec.levers = []);
    if (fixed) L.forEach((lv) => { lv.usage = 1; });
    const items = L.map((lv, i) => {
      const move = (d) => () => {
        const j = i + d;
        if (j < 0 || j >= L.length) return;
        [L[i], L[j]] = [L[j], L[i]];
        touch(); draw();
      };
      const small = (c, label) => cols.has(c)
        ? h("label", { class: "lv-f" }, h("span", {}, label), leverCell(lv, c, touch, draw)) : null;
      const unit = pctType(lv.type) ? "%" : "mV";
      return h("div", { class: "lever" },
        h("div", { class: "lv-top" },
          h("span", { class: "lv-n" }, fixed ? "" : `${i + 1}`),
          leverCell(lv, "label", touch, draw), leverCell(lv, "type", touch, draw),
          h("span", { class: "ops" },
            fixed ? null : h("button", { type: "button", class: "iconbtn", title: "위로 (priority 앞으로)", onclick: move(-1) }, "↑"),
            fixed ? null : h("button", { type: "button", class: "iconbtn", title: "아래로", onclick: move(1) }, "↓"),
            h("button", { type: "button", class: "iconbtn", title: "삭제", onclick: () => { L.splice(i, 1); touch(); draw(); } }, "×"))),
        h("div", { class: "lv-bottom" },
          small("axes", "축"), small("max_change", `${fixed ? "변화" : "상한"} (${unit})`),
          small("weight", "weight"), small("id", "id")));
    });
    const add = () => {
      L.push({ id: `lever${L.length + 1}`, label: "새 lever", type: "scale", axes: ["l_com"], max_change: -0.1, weight: 1, ...(fixed ? { usage: 1 } : {}) });
      touch(); draw();
    };
    wrap.replaceChildren(
      ...(L.length ? items : [h("p", { class: "hint" }, fixed ? "없음 — 오늘 공정 그대로" : "lever가 없습니다")]),
      L.length ? h("p", { class: "hint" }, "scale·pull은 % (−10 = 10 % 감소), shift는 mV. 축은 l_com+lpu처럼 +로 묶습니다.") : null,
      h("button", { type: "button", class: "iconbtn", onclick: add }, "+ lever 추가"));
  };
  draw();
  return wrap;
}

function leverCell(lv, c, touch, draw) {
  if (c === "type") {
    const el = h("select", {}, ...LEVER_TYPES.map(([v, l]) => h("option", { value: v }, l)));
    el.value = lv.type || "scale";
    el.addEventListener("change", () => { lv.type = el.value; touch(); draw(); });
    return el;
  }
  if (c === "axes") {
    const el = h("input", { type: "text", value: (lv.axes || []).join("+"), placeholder: "l_com+lpu" });
    const keys = new Set(S.meta.axes.map((a) => a.key));
    const check = () => {
      const ax = el.value.split(/[+,\s]+/).filter(Boolean);
      el.setAttribute("aria-invalid", ax.some((a) => !keys.has(a)) ? "true" : "false");
      return ax;
    };
    check();
    el.addEventListener("change", () => { lv.axes = check(); touch(); });
    return el;
  }
  if (c === "max_change" || c === "weight") {
    const scale = c === "max_change" && pctType(lv.type) ? 100 : 1;
    const v = lv[c];
    const el = h("input", { type: "number", step: "any", class: "num", value: v == null ? "" : String(+(v * scale).toPrecision(6)) });
    el.addEventListener("change", () => { lv[c] = el.value.trim() === "" ? null : parseFloat(el.value) / scale; touch(); });
    return el;
  }
  const el = h("input", { type: "text", value: lv[c] ?? "" });
  el.addEventListener("change", () => { lv[c] = el.value; touch(); });
  return el;
}

// shared sections -------------------------------------------------------------
function secTarget(spec, a, touch) {
  const s = h("section", {}, h("h4", {}, "목표"));
  if (a.uses.includes("target")) {
    s.append(row("target Vmin (V)", numInput(spec, "target", touch), "모든 binding 조건이 이 값 이하여야 통과"));
  }
  s.append(row("reference (V)", numInput(spec, "reference_vmin", touch),
    a.kind === "roadmap" ? "개선량을 재는 기준 (오늘 spec)" : "오늘 spec — 그림의 회색 점선"));
  return s;
}

function secZ(spec, touch) {
  return h("section", {}, h("h4", {}, "Z 기준 (array · yield)"),
    row("array (Mb)", numInput(spec, "z.array_mb", touch)),
    row("yield", numInput(spec, "z.yield", touch), "0.99 = 99 % (Poisson)"),
    row("Z 직접 입력", numInput(spec, "z.value", touch), "빈칸이면 위 사양으로 계산 — 128 Mb @ 99 % → 6.398"),
    h("div", { class: "checks" }, checkbox(spec, "z.lobe", "lobe 보정 (min-of-two, D-07)", touch)));
}

const CHECK_PRESETS = [
  ["limiting", "mode별 한계 corner (read FSG · write SFG)"],
  ["all_corners", "PDK corner 4종 × mode"],
  ["nominal", "기준 좌표 (nominal)"],
  ["custom", "직접 지정"],
];

function secChecks(spec, touch) {
  const custom = h("div");
  const sel = h("select", {}, ...CHECK_PRESETS.map(([v, l]) => h("option", { value: v }, l)));
  sel.value = Array.isArray(spec.checks) ? "custom" : spec.checks || "limiting";
  const drawCustom = () => {
    if (!Array.isArray(spec.checks)) { custom.replaceChildren(); return; }
    const corners = [...Object.keys(S.meta.corners), "nominal"];
    const rows = spec.checks.map((c, i) => {
      const mode = h("select", {}, ...Object.keys(S.meta.modes).map((m) => h("option", { value: m }, m)));
      mode.value = c.mode;
      mode.addEventListener("change", () => { c.mode = mode.value; touch(); });
      const corner = h("select", {}, ...corners.map((k) => h("option", { value: k }, k)));
      corner.value = c.corner || "nominal";
      corner.addEventListener("change", () => { c.corner = corner.value; touch(); });
      const pt = h("input", { type: "text", placeholder: "cn=-20, pu=30",
        value: Object.entries(c.point || {}).map(([k, v]) => `${k}=${v}`).join(", ") });
      pt.addEventListener("change", () => {
        c.point = Object.fromEntries(pt.value.split(",").map((x) => x.split("=").map((y) => y.trim()))
          .filter(([k, v]) => k && v !== undefined && v !== "").map(([k, v]) => [k, parseFloat(v)]));
        touch();
      });
      const lab = h("input", { type: "text", placeholder: "이름 (선택)", value: c.label || "" });
      lab.addEventListener("change", () => { c.label = lab.value || undefined; touch(); });
      return h("tr", {}, h("td", {}, mode), h("td", {}, corner), h("td", {}, pt), h("td", {}, lab),
        h("td", {}, h("button", { type: "button", class: "iconbtn", title: "삭제",
          onclick: () => { spec.checks.splice(i, 1); touch(); drawCustom(); } }, "×")));
    });
    custom.replaceChildren(
      h("table", { class: "levers" },
        h("thead", {}, h("tr", {}, h("th", {}, "mode"), h("th", {}, "corner"), h("th", {}, "좌표 덮어쓰기"), h("th", {}, "이름"), h("th", {}, ""))),
        h("tbody", {}, ...rows)),
      h("button", { type: "button", class: "iconbtn",
        onclick: () => { spec.checks.push({ mode: "read", corner: "nominal" }); touch(); drawCustom(); } }, "+ 조건 추가"));
  };
  sel.addEventListener("change", () => {
    spec.checks = sel.value === "custom"
      ? [{ mode: "read", corner: "FSG" }, { mode: "write", corner: "SFG" }] : sel.value;
    touch(); drawCustom();
  });
  drawCustom();
  const modes = h("div", { class: "checks" }, ...Object.entries(S.meta.modes).map(([m, info]) => {
    const id = nextId();
    const el = h("input", { type: "checkbox", id });
    el.checked = (spec.modes || []).includes(m);
    el.addEventListener("change", () => {
      const now = new Set(spec.modes || []);
      if (el.checked) now.add(m); else now.delete(m);
      spec.modes = Object.keys(S.meta.modes).filter((x) => now.has(x));
      touch();
    });
    return h("label", { for: id }, el, `${info.label} (${minus(info.temperature_C)} °C)`);
  }));
  return h("section", {}, h("h4", {}, "binding 조건 — 모두 동시에 통과해야 함"),
    row("조건", sel), row("mode", modes), custom);
}

function secBase(spec, touch) {
  const ref = h("select", {},
    h("option", { value: "mode_nominal" }, "mode별 학습 중앙값 (논문)"),
    h("option", { value: "read_nominal" }, "read 중앙값을 두 mode에"),
    h("option", { value: "write_nominal" }, "write 중앙값을 두 mode에"));
  ref.value = (spec.base && spec.base.reference) || "mode_nominal";
  ref.addEventListener("change", () => { setAt(spec, "base.reference", ref.value); touch(); });
  const nom = Object.fromEntries(Object.entries(S.meta.modes).map(([m, v]) => [m, v.nominal]));
  const grid = h("div", { class: "axisgrid" }, ...S.meta.axes.map((ax) => {
    const el = numInput(spec, `base.overrides.${ax.key}`, touch);
    el.placeholder = Object.entries(nom).map(([m, n]) => `${m[0]} ${+n[ax.key].toPrecision(4)}`).join(" / ");
    el.id = nextId();
    return h("div", {}, h("label", { for: el.id, title: ax.name }, `${ax.key} (${ax.unit})`), el);
  }));
  const set = Object.values((spec.base && spec.base.overrides) || {}).some((v) => v !== null && v !== "");
  return h("section", {}, h("details", { open: set },
    h("summary", {}, "기준 좌표 ", h("span", {}, "— 나머지 축의 고정값 (빈칸 = 중앙값)")),
    row("기준", ref), grid));
}

function renderForm(box, a, spec, resBox) {
  const ta = h("textarea", { spellcheck: "false", "aria-label": "spec JSON" });
  const syncJSON = () => { ta.value = JSON.stringify(spec, null, 2); };
  const touch = () => {
    if (spec._preset || spec.expect) {        // an edited preset no longer reproduces the paper
      delete spec._preset;
      delete spec.expect;
      if (spec.title && !spec.title.endsWith("(수정)")) spec.title += " (수정)";
    }
    syncJSON();
  };
  const title = h("input", { type: "text", value: spec.title || "", placeholder: a.title });
  title.addEventListener("change", () => { spec.title = title.value || undefined; syncJSON(); });

  const specific = h("section", {}, h("h4", {}, "분석 설정"));
  for (const f of a.fields) {
    if (f.type === "levers") {
      specific.append(h("div", { style: "margin: 10px 0 4px" }, h("p", { class: "hint", style: "font-weight:700;color:var(--ink)" }, f.label),
        f.hint ? h("p", { class: "hint" }, f.hint) : null, leverEditor(spec, f, touch)));
    } else {
      specific.append(row(f.label, fieldControl(spec, f, touch), f.hint));
    }
  }
  const parts = [h("section", {}, row("실행 이름", title))];
  if (a.uses.includes("target") || a.uses.includes("reference")) parts.push(secTarget(spec, a, touch));
  if (a.fields.length) parts.push(specific);
  if (a.uses.includes("checks")) parts.push(secChecks(spec, touch));
  if (a.uses.includes("z")) parts.push(secZ(spec, touch));
  if (a.uses.includes("base")) parts.push(secBase(spec, touch));

  const msg = h("span", { class: "hint", "aria-live": "polite" });
  const runBtn = h("button", { type: "button", class: "primary" }, "실행");
  runBtn.addEventListener("click", async () => {
    runBtn.disabled = true;
    try {
      const { id } = await post("/api/runs", spec);
      location.hash = `#/run/${id}`;
    } catch (e) {
      resBox.replaceChildren(h("div", { class: "error" }, e.message));
    } finally { runBtn.disabled = false; }
  });
  const json = h("details", {}, h("summary", {}, "spec JSON ", h("span", {}, "— 이 내용이 그대로 저장·재현됩니다")),
    ta,
    h("div", { class: "actions", style: "position:static" },
      h("button", { type: "button", class: "secondary", onclick: () => {
        try {
          const obj = JSON.parse(ta.value);
          const kind = obj.kind || a.kind;
          if (!entry(kind)) throw new Error(`알 수 없는 kind '${kind}'`);
          S.specs[kind] = merged(entry(kind).defaults, obj);
          if (kind !== a.kind) location.hash = `#/a/${kind}`; else viewAnalysis(kind);
        } catch (e) { msg.textContent = `JSON 적용 실패 — ${e.message}`; }
      } }, "JSON 적용"),
      h("button", { type: "button", class: "secondary", onclick: () => navigator.clipboard && navigator.clipboard.writeText(ta.value).then(() => { msg.textContent = "복사했습니다"; }) }, "복사")));
  const save = h("button", { type: "button", class: "secondary" }, "시나리오로 저장");
  save.addEventListener("click", async () => {
    const name = window.prompt("저장할 이름 (영문·한글·숫자·_·-, scenarios/user/에 저장)", (spec.title || a.kind).replace(/[^A-Za-z0-9가-힣_-]+/g, "_").slice(0, 60));
    if (!name) return;
    try {
      const body = clone(spec);
      delete body._preset;
      const r = await post("/api/presets", { name, spec: body });
      S.presets = await api("/api/presets");
      msg.textContent = `저장했습니다 — scenarios/${r.name}.json`;
    } catch (e) { msg.textContent = `저장 실패 — ${e.message}`; }
  });
  syncJSON();
  box.replaceChildren(...parts, json, h("div", { class: "actions" }, runBtn, save, msg));
}

// ------------------------------------------------------------------ run + result
async function viewRun(id) {
  const kind = id.split("-")[2];
  markNav(`#/a/${kind}`);
  let r;
  try { r = await api(`/api/runs/${id}`); } catch (e) {
    main.replaceChildren(h("p", { class: "error" }, `실행 ${id}를 찾지 못했습니다 — ${e.message}`));
    return;
  }
  if (r.status === "queued" || r.status === "running") {
    if (!document.querySelector(".result")) viewAnalysis(kind, null, r);
    else renderProgress(document.querySelector(".result"), r);
    S.timer = setTimeout(() => viewRun(id), 800);
    return;
  }
  try { S.specs[r.kind] = merged(entry(r.kind).defaults, await api(`/runs/${id}/spec.json`)); } catch { /* keep form */ }
  viewAnalysis(r.kind, r);
}

function renderProgress(box, r) {
  const t = r.started ? ` · ${Math.round(Date.now() / 1000 - r.started)} s` : "";
  box.replaceChildren(
    h("h2", {}, r.status === "queued" ? "대기 중" : "계산 중"),
    h("p", { class: "progress" }, `${r.progress || ""}${t}${r.status === "queued" && r.queue > 1 ? ` · 앞에 ${r.queue - 1}건` : ""}`),
    h("div", { class: "bar", role: "progressbar", "aria-label": "계산 진행" }));
}

function reproLine(r) {
  const c = (r.data && r.data.context) || {};
  const parts = [];
  if (c.target != null) parts.push(["target", `${fmt(c.target, 3)} V`]);
  if (c.reference != null) parts.push(["ref", `${fmt(c.reference, 3)} V`]);
  if (c.z != null) parts.push(["Z", `${fmt(c.z, 3)} (${c.z_text})`]);
  if (c.base) {
    const ov = Object.entries(c.overrides || {}).map(([k, v]) => `${k}=${minus(v)}`).join(" ");
    parts.push(["base", c.base + (ov ? ` + ${ov}` : "")]);
  }
  if (c.checks) parts.push(["checks", c.checks.join(" ∧ ")]);
  for (const lv of c.levers || []) parts.push(["lever", `${lv.label} ${lv.applied ? "= " + lv.applied : "≤ " + lv.limit.replace("max ", "")}`]);
  return h("div", { class: "line" }, ...parts.flatMap(([k, v], i) => [i ? "  ·  " : "", h("b", {}, k), " ", v]));
}

function renderResult(box, r) {
  const head = [
    h("h2", {}, r.title || r.kind),
    h("p", { class: "meta" }, `${r.id} · ${r.created || ""} · ${r.elapsed_s != null ? r.elapsed_s + " s" : ""}`),
  ];
  if (r.status === "error") {
    box.replaceChildren(...head, h("div", { class: "error" }, r.error || "실패"),
      h("p", { class: "hint" }, "왼쪽 조건을 고쳐 다시 실행하세요."));
    return;
  }
  const cmd = `.venv/bin/python service/main.py run service/runs/${r.id}/spec.json`;
  const copy = h("button", { type: "button", class: "link" }, "복사");
  copy.addEventListener("click", () => navigator.clipboard && navigator.clipboard.writeText(cmd).then(() => { copy.textContent = "복사됨"; }));
  const out = [...head, h("div", { class: "repro" }, reproLine(r), h("div", { class: "cmd" }, h("span", {}, "재현"), h("code", {}, cmd), copy))];

  const ver = r.verification || [];
  if (ver.length) {
    const ok = ver.filter((v) => v.ok).length;
    out.push(h("div", { class: "ledger", "aria-label": "논문 수치 대조" },
      h("span", { class: ok === ver.length ? "pass" : "fail" }, `논문 대조 ${ok}/${ver.length}`),
      ...ver.map((v) => h("span", { class: `chip ${v.ok ? "ok" : "no"}`,
        title: `${v.path}\n실제 ${cellText(v.actual)} · 기대 ${cellText(v.expected)} ± ${cellText(v.tol)}${v.note ? "\n" + v.note : ""}` },
        `${v.ok ? "✓" : "✕"} ${v.ledger || ""} ${v.path.split(".").slice(-2).join(".")} = ${cellText(v.actual)}`))));
  }
  if ((r.summary || []).length) {
    out.push(h("div", { class: "cards" }, ...r.summary.map((c) =>
      h("div", { class: "card" }, h("div", { class: "k" }, c.label), h("div", { class: "v" }, minus(c.value)),
        c.hint ? h("div", { class: "s" }, c.hint) : null))));
  }
  if ((r.notes || []).length) out.push(h("ul", { class: "notes" }, ...r.notes.map((n) => h("li", {}, n))));
  for (const f of r.figures || []) {
    const img = h("img", { src: `/runs/${r.id}/${f.png}`, alt: f.title, loading: "lazy" });
    img.addEventListener("load", () => { img.style.width = `${Math.round(img.naturalWidth / 2)}px`; });
    out.push(h("figure", {},
      img,
      h("figcaption", {}, h("b", {}, f.title),
        h("a", { href: `/runs/${r.id}/${f.png}?dl=1` }, "PNG"), h("a", { href: `/runs/${r.id}/${f.pdf}?dl=1` }, "PDF (논문용)"))));
  }
  for (const t of r.tables || []) {
    out.push(h("div", { class: "tablehead" }, h("h3", {}, t.title), h("a", { href: `/runs/${r.id}/${t.csv}?dl=1` }, `CSV (${t.n_rows}행)`)));
    if (t.rows) {
      out.push(h("div", { class: "tablewrap" }, h("table", { class: "data" },
        h("thead", {}, h("tr", {}, ...t.columns.map((c) => h("th", {}, c)))),
        h("tbody", {}, ...t.rows.slice(0, 300).map((rw) => h("tr", {}, ...rw.map((v) => h("td", {}, cellText(v)))))))));
    } else {
      out.push(h("p", { class: "hint" }, "행이 많아 CSV로만 제공합니다."));
    }
  }
  out.push(h("p", { class: "hint", style: "margin-top:24px" },
    "spec.json·result.json·그림·CSV 전부: ", h("code", {}, `service/runs/${r.id}/`)));
  box.replaceChildren(...out);
}

// ------------------------------------------------------------------ home
function viewHome() {
  const m = S.meta;
  const modeRows = Object.entries(m.modes).map(([k, v]) => h("tr", {},
    h("td", {}, v.label), h("td", {}, `${minus(v.temperature_C)} °C`), h("td", {}, v.vops.map((x) => x.toFixed(1)).join(" ")),
    h("td", { title: v.source }, v.checkpoint || "—")));
  const sc = (m.selfcheck || []).map((c) => h("tr", {},
    h("td", {}, `${c.corner}·${c.mode}`), h("td", {}, fmt(c.saved)), h("td", {}, fmt(c.now)),
    h("td", {}, c.hspice_censored ? "< 0.40" : fmt(c.hspice)), h("td", { class: c.ok ? "pass" : "fail" }, c.ok ? "✓" : "✕")));
  const paper = S.presets.filter((p) => p.expect);
  const live = h("ul", { class: "list" });
  const verifyAll = h("button", { type: "button", class: "primary" }, `논문 수치 전부 다시 확인 (${paper.length}개 preset)`);
  verifyAll.addEventListener("click", async () => {
    verifyAll.disabled = true;
    live.replaceChildren();
    for (const p of paper) {
      const spec = await api(`/api/presets/${p.name}`);
      const { id } = await post("/api/runs", { ...spec, _preset: p.name });
      const status = h("span", { class: "muted" }, "대기 중");
      live.append(h("li", {}, h("div", { class: "t" }, h("a", { href: `#/run/${id}` }, p.title)), h("div", { class: "b" }, status)));
      watch(id, status);
    }
    verifyAll.disabled = false;
  });
  main.replaceChildren(
    h("p", { class: "eyebrow" }, "시작"),
    h("h1", {}, "조건을 주면 Vmin, 목표를 주면 조건"),
    h("p", { class: "lede" },
      "논문의 read·write GP surrogate와 physics layer를 그대로 씁니다. 분석 하나는 JSON spec 하나이고, " +
      "실행마다 spec·결과·그림(PNG·PDF)·CSV가 service/runs/에 남아 CLI로 똑같이 다시 돌릴 수 있습니다."),
    h("div", { class: "cols" },
      h("div", {},
        h("h3", {}, "모델"),
        h("div", { class: "tablewrap" }, h("table", { class: "data" },
          h("thead", {}, h("tr", {}, ...["mode", "온도", "Vop grid (V)", "checkpoint"].map((x) => h("th", {}, x)))),
          h("tbody", {}, ...modeRows))),
        h("h3", {}, "§V-D self-check — 저장된 예측을 지금 모델이 그대로 내는가"),
        h("div", { class: "tablewrap" }, h("table", { class: "data" },
          h("thead", {}, h("tr", {}, ...["corner", "저장된 예측", "지금", "HSPICE", ""].map((x) => h("th", {}, x)))),
          h("tbody", {}, ...sc)))),
      h("div", {},
        h("h3", {}, "논문 재현"),
        h("p", { class: "hint" }, "LEDGER 수치가 박힌 preset을 다시 돌려 허용오차 안에 드는지 확인합니다. 몇 분 걸립니다."),
        verifyAll, live,
        h("h3", {}, "바로 가기"),
        h("ul", { class: "list" }, ...[
          ["levers", "목표 Vmin에 필요한 공정 lever 조합 — 상한·우선순위·robust"],
          ["plane", "ΔVth,N × ΔVth,P process window"],
          ["retarget", "array 크기·yield를 바꾸면"],
          ["recenter", "σ 대신 Vth target을 옮기면"],
        ].map(([k, d]) => h("li", {}, h("div", { class: "t" }, h("a", { href: `#/a/${k}` }, navTitle(entry(k)))), h("div", { class: "d" }, d)))))),
    h("h3", {}, "최근 실행"),
    runsTable(8));
}

function watch(id, el) {
  const tick = async () => {
    let r;
    try { r = await api(`/api/runs/${id}`); } catch (e) { el.textContent = e.message; return; }
    if (r.status === "queued" || r.status === "running") {
      el.textContent = r.status === "queued" ? "대기 중" : `계산 중 — ${r.progress || ""}`;
      setTimeout(tick, 1500);
      return;
    }
    const v = r.verification || [];
    const ok = v.filter((x) => x.ok).length;
    el.className = r.status === "done" && ok === v.length ? "pass" : "fail";
    el.textContent = r.status === "done" ? `논문 대조 ${ok}/${v.length} · ${r.elapsed_s} s` : `실패 — ${r.error}`;
  };
  tick();
}

// ------------------------------------------------------------------ library / runs / guide
async function openPreset(name, run) {
  const spec = await api(`/api/presets/${name}`);
  const kind = spec.kind;
  if (!entry(kind)) return;
  if (run) {
    const { id } = await post("/api/runs", { ...spec, _preset: name });
    location.hash = `#/run/${id}`;
    return;
  }
  S.specs[kind] = merged(entry(kind).defaults, { ...spec, _preset: name });
  location.hash = `#/a/${kind}`;
  if (location.hash === `#/a/${kind}`) viewAnalysis(kind);
}

async function viewLibrary() {
  try { S.presets = await api("/api/presets"); } catch { /* keep the cached list */ }
  const groups = {};
  for (const p of S.presets) (groups[p.group || "기타"] ||= []).push(p);
  const order = ["논문 재현", "시나리오", "내 시나리오"];
  const names = [...order.filter((g) => groups[g]), ...Object.keys(groups).filter((g) => !order.includes(g))];
  main.replaceChildren(
    h("p", { class: "eyebrow" }, "시나리오 라이브러리"),
    h("h1", {}, "저장된 spec"),
    h("p", { class: "lede" }, "service/scenarios/ 아래 JSON 파일입니다. 폼으로 열어 고치거나 그대로 실행합니다. " +
      "폼에서 저장한 시나리오는 scenarios/user/에 쌓입니다."),
    ...names.flatMap((g) => [h("h3", {}, g), h("ul", { class: "list" }, ...groups[g].map((p) => h("li", {},
      h("div", { class: "t" }, p.title),
      h("div", { class: "d" }, p.description),
      h("div", { class: "b" },
        h("span", { class: "tag" }, navTitle(entry(p.kind) || { title: p.kind })),
        p.expect ? h("span", { class: "tag" }, `논문 대조 ${p.expect}개`) : null,
        h("button", { type: "button", class: "link", onclick: () => openPreset(p.name, false) }, "폼으로 열기"),
        h("button", { type: "button", class: "link", onclick: () => openPreset(p.name, true) }, "바로 실행"),
        h("code", { class: "muted" }, `scenarios/${p.name}.json`)))))]));
}

function runsTable(limit) {
  const box = h("div", { class: "tablewrap" }, h("p", { class: "hint" }, "불러오는 중…"));
  api("/api/runs").then((runs) => {
    if (!runs.length) { box.replaceChildren(h("p", { class: "hint" }, "아직 실행한 분석이 없습니다.")); return; }
    box.replaceChildren(h("table", { class: "data" },
      h("thead", {}, h("tr", {}, ...["시각", "분석", "제목", "핵심 결과", "논문 대조", "소요"].map((x) => h("th", {}, x)))),
      h("tbody", {}, ...runs.slice(0, limit || runs.length).map((r) => {
        const tr = h("tr", { class: "click", tabindex: "0" },
          h("td", {}, r.created || ""), h("td", {}, r.kind), h("td", {}, r.title || ""),
          h("td", { class: r.status === "error" ? "fail" : "" }, minus(r.headline || "")),
          h("td", {}, r.verified || ""), h("td", {}, r.elapsed_s != null ? `${r.elapsed_s} s` : ""));
        const go = () => { location.hash = `#/run/${r.id}`; };
        tr.addEventListener("click", go);
        tr.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
        return tr;
      }))));
  }).catch((e) => box.replaceChildren(h("p", { class: "error" }, e.message)));
  return box;
}

function viewRuns() {
  main.replaceChildren(
    h("p", { class: "eyebrow" }, "실행 기록"),
    h("h1", {}, "지금까지 돌린 분석"),
    h("p", { class: "lede" }, "행을 누르면 그 실행의 결과와 spec이 열립니다. 조건을 고쳐 다시 실행하면 새 기록이 생깁니다."),
    runsTable());
}

function viewGuide() {
  const dl = (pairs) => h("dl", {}, ...pairs.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]));
  main.replaceChildren(h("div", { class: "guide" },
    h("p", { class: "eyebrow" }, "사용법 · 규약"),
    h("h1", {}, "무엇을 계산하고, 무엇을 계산하지 않는가"),
    h("p", { class: "lede" }, "Vmin은 논문과 같은 방식으로 냅니다: GP가 Vop마다 μ·σ를 예측 → z = μ/σ → z가 Z를 넘는 전압을 선형 보간. " +
      "read는 SNMR(125 °C), write는 Vtrip(−40 °C) 모델이고, binding Vmin은 고른 조건 전부의 최댓값입니다."),
    h("h3", {}, "좌표 규약"),
    dl([
      ["cn, pu", "Vth shift (mV). 양수 = 느린 소자 (NMOS·PMOS 모두). FSG = (cn < 0, pu > 0) — read 최악, SFG = write 최악"],
      ["l_com, lpu", "local-σ 배율. 1 = nominal mismatch"],
      ["m_com, mpu", "mobility 배율"],
      ["sk, l_sk, m_sk", "PG–PD 사이 어긋남 (Vth · σ · mobility)"],
      ["기준 좌표", "기본은 mode별 학습 중앙값 — 논문과 같고, read와 write의 기준점이 다릅니다"],
    ]),
    h("h3", {}, "lever 세 종류"),
    dl([
      ["scale", "축 값 × (1 + 변화). local σ −10 % = l_com × 0.9"],
      ["pull", "corner와 기준 좌표 사이 거리 × (1 + 변화). global 분포 폭을 줄이는 것 — corner가 기준점 쪽으로 당겨집니다"],
      ["shift", "축 값 + 변화 (mV). 분포 전체를 옮김 — Vth target 재조정"],
    ]),
    h("p", {}, "priority는 lever 목록 순서대로 상한까지 쓰고 마지막 것만 필요한 만큼 씁니다. balanced는 모든 lever를 각자 상한의 같은 비율만큼 씁니다. " +
      "min-cost는 weight × (상한 대비 사용률)의 합이 가장 작은 조합을 격자로 찾습니다."),
    h("h3", {}, "robust 기준과 P(pass)"),
    h("p", {}, "GP posterior(μ와 log σ의 잠재 함수, Vop 사이 상관 포함)에서 표본을 뽑아 binding Vmin 분포를 만듭니다. " +
      "mean 기준 해는 정의상 목표선 위에 놓이므로 P(pass) ≈ 0.5입니다. 95 % 기준은 표본의 95 % 분위가 목표 이하가 되도록 다시 풉니다. " +
      "모델 구조 오차(학습 데이터 밖의 물리)는 이 분포에 들어 있지 않습니다."),
    h("h3", {}, "이 도구가 하지 않는 것"),
    h("ul", {},
      h("li", {}, "학습 범위 밖 좌표는 GP 외삽입니다 — 결과에 경고가 붙습니다."),
      h("li", {}, "lever의 실제 공정 비용, leakage·speed trade-off, area 환산은 모델에 없습니다."),
      h("li", {}, "Vop 격자 밖 Vmin은 숫자로 만들지 않고 '< 0.40 V'·'> 최고 Vop'로 표시합니다."),
      h("li", {}, "sign-off를 대신하지 않습니다. 고른 해는 HSPICE MC로 확인해야 합니다.")),
    h("h3", {}, "CLI"),
    h("pre", { class: "mono" },
      ".venv/bin/python service/main.py serve            # 이 화면\n" +
      ".venv/bin/python service/main.py run SPEC.json    # spec 하나 실행\n" +
      ".venv/bin/python service/main.py verify           # 논문 대조 preset 전부\n" +
      ".venv/bin/python service/main.py list             # preset 목록")));
}

boot();
