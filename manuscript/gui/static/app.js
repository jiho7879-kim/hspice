/* Local UI for SRAM Vmin Inverse Studio.  No external CDN, analytics, or upload. */
'use strict';

const state = {
  metadata: null,
  mode: 'read',
  coordinates: {},
  forward: { read: null, write: null },
  stale: { forward: false, inverse: false, plane: false, combination: false },
  inverse: null,
  plane: null,
  planeKind: null,
  combination: null,
  combinationAxes: ['cn', 'pu'],
  busy: false,
  scenario: null,
  sensitivity: null,
  activeTab: 'concepts',
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const conceptCards = [
  {
    title: 'Monte Carlo (MC)',
    definition: '같은 회로 조건에서 소자 mismatch를 무작위로 많이 바꿔 회로를 반복 실행하는 방법입니다. “가능한 셀들 중 얼마나 불리한 셀이 있는가”를 표본으로 봅니다.',
    context: '이 논문에서는 각 조건·전압에서 MC 결과로 margin 평균 μ와 표준편차 σ를 얻어 학습 label로 사용합니다.',
    avoid: 'MC 5,000회가 6σ 꼬리를 직접 측정했다는 뜻은 아닙니다. 극단 tail은 분포 가정과 추가 검증이 필요합니다.',
  },
  {
    title: 'μ와 σ: 평균과 셀 간 산포',
    definition: 'μ는 조건이 바뀌었을 때 margin 중심이 어디로 움직이는지, σ는 동일 조건의 셀들이 얼마나 퍼지는지를 나타냅니다.',
    context: '이 도구는 Vmin을 직접 하나의 회귀기로 맞히지 않고 μ GP와 log σ GP를 별도로 예측한 뒤 z=μ/σ로 결합합니다.',
    avoid: '셀 간 물리적 σ와 “GP가 자기 예측을 얼마나 자신하는가”라는 GP uncertainty는 다른 양입니다.',
  },
  {
    title: 'z-score와 yield target',
    definition: 'z=μ/σ는 평균이 표준편차의 몇 배만큼 0에서 떨어져 있는지입니다. z가 클수록 실패 쪽 꼬리에서 멀다는 뜻입니다.',
    context: '현재 모델의 target은 128 Mb·99%라는 가정에서 z target=6.3984입니다. Vmin은 전압을 올리며 z가 이 target을 처음 넘는 지점입니다.',
    avoid: 'μ−kσ는 특정 전압의 tail margin입니다. 그것 자체가 공급전압 Vmin은 아닙니다.',
  },
  {
    title: 'Gaussian process (GP)',
    definition: '관측한 입력점 사이를 “가까운 공정 조건은 비슷한 결과를 낼 것”이라는 kernel 가정으로 부드럽게 보간하는 확률적 회귀기입니다.',
    context: '읽기와 쓰기에 각각 μ GP와 log σ GP가 있어 총 네 개의 GP가 동작합니다. 현재 구현은 full-ARD Matérn 5/2 kernel입니다.',
    avoid: 'GP가 반도체 물리법칙을 자동으로 증명하거나 외삽을 안전하게 만든다는 뜻은 아닙니다.',
  },
  {
    title: 'ARD lengthscale',
    definition: 'ARD는 축마다 다른 lengthscale을 학습합니다. 짧은 lengthscale은 그 축을 따라 함수가 더 빨리 휘었다는 뜻입니다.',
    context: '학습 모델이 어느 좌표에서 굴곡을 필요로 했는지 보는 무료 진단값입니다.',
    avoid: 'ARD 역수는 global sensitivity가 아닙니다. 입력 범위 전체에서 출력 분산을 얼마나 만드는지는 Sobol로 따로 봅니다.',
  },
  {
    title: 'Sobol S1과 ST',
    definition: 'S1은 한 축만의 1차 효과, ST는 그 축이 참여하는 모든 상호작용까지 포함한 total-order 효과입니다.',
    context: '논문의 저장 결과는 읽기 125 °C에서 z(0.625 V)의 분산을, 학습 상자 안 독립 균등분포에서 분해한 것입니다.',
    avoid: 'ST는 상호작용을 여러 축에 중복 포함하므로 막대를 100% pie chart처럼 더하면 안 됩니다.',
  },
  {
    title: 'RMSE와 R²',
    definition: 'RMSE는 오차를 제곱해 평균낸 뒤 제곱근을 취한 전형적 오차 크기입니다. R²는 label 변동 중 모델이 설명한 비율입니다.',
    context: 'Vmin hold-out RMSE는 read 3.98 mV, write 5.65 mV입니다. 이는 점수에 들어간 유효 조건의 평균적 오차입니다.',
    avoid: 'RMSE가 모든 점의 최대 오차도 아니고, 각각의 prediction에 ±RMSE 보증구간을 준다는 뜻도 아닙니다.',
  },
  {
    title: 'Censoring',
    definition: '전압 grid 최저점에서 이미 target을 통과하면 실제 Vmin은 “그보다 낮다”만 알 수 있습니다. 숫자 하나를 정확히 알 수 없습니다.',
    context: '이 화면은 < 최저 전압 또는 > 최고 전압을 별도 상태로 표시하고 RMSE/근 찾기와 혼동하지 않습니다.',
    avoid: '“<0.4 V”를 정확히 0.4 V 또는 내부 계산용 placeholder 전압처럼 읽으면 안 됩니다.',
  },
  {
    title: 'Inverse와 공동 만족 후보',
    definition: '한 축 inverse는 나머지 축을 고정하고 target 교차 bracket만 이분 탐색으로 좁힙니다. 다축 화면은 여러 축을 함께 표본화해 read·write가 모두 통과하는 후보를 찾습니다.',
    context: '논문에서 검증한 inverse는 주로 cn·pu의 한 축 조건부 복원입니다. 공동 후보는 같은 9D 좌표를 두 model에 함께 넣는 설계 탐색입니다.',
    avoid: '다축 후보는 연속 공간의 유일 root, 전역 최적해, 실제 제조 원인 또는 최소 비용 해가 아닙니다.',
  },
];

function setToast(message) {
  const toast = $('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  window.clearTimeout(setToast.timeout);
  setToast.timeout = window.setTimeout(() => toast.classList.remove('show'), 4200);
}

async function request(path, body = null) {
  const options = body === null ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload.data;
}

function text(el, value) { el.textContent = value; }
function number(value, digits = 4) { return value === null || value === undefined ? '—' : Number(value).toFixed(digits); }
function axisByKey(key) { return state.metadata.axes.find((axis) => axis.key === key); }
function currentTarget() { return Number($('#target-input').value); }
function currentAxis() { return $('#axis-select').value; }
function currentCoordinates() { return { ...state.coordinates }; }
function currentCombinationAxes() { return [...state.combinationAxes]; }

function setStatus(selector, label, kind = 'neutral') {
  const node = $(selector);
  node.textContent = label;
  node.className = `status-pill ${kind}`;
}

function setInferenceBusy(busy) {
  state.busy = busy;
  [
    '#mode-select', '#target-input', '#axis-select', '#reset-button', '#predict-button',
    '#inverse-button', '#plane-button', '#joint-plane-button', '#combination-button',
  ].forEach((selector) => {
    const control = $(selector);
    if (control) control.disabled = busy;
  });
  $$('#axis-controls input, #combination-axis-controls input, .apply-candidate').forEach((control) => { control.disabled = busy; });
}

function markResultsStale({ forward = true } = {}) {
  if (forward) state.stale.forward = true;
  if (state.inverse) { state.stale.inverse = true; setStatus('#inverse-status', '입력 변경됨', 'warn'); }
  if (state.plane) { state.stale.plane = true; setStatus('#plane-status', '입력 변경됨', 'warn'); }
  if (state.combination) { state.stale.combination = true; setStatus('#combination-status', '입력 변경됨', 'warn'); }
  renderForward();
}

function clearCombinationResult(message = '좌측에서 2개 이상 축을 선택한 뒤 공동 만족 후보 찾기를 누르세요.') {
  state.combination = null;
  state.stale.combination = false;
  setStatus('#combination-status', '계산 대기', 'neutral');
  text($('#combination-summary'), message);
  $('#combination-table-head').replaceChildren();
  $('#combination-table-body').replaceChildren();
  $('#combination-caveats').replaceChildren();
}

function sameNumber(left, right) {
  return Number.isFinite(left) && Number.isFinite(right) && Math.abs(left - right) < 1e-12;
}

function rangeStep(axis, bounds) {
  if (axis.unit === 'mV') return bounds[1] - bounds[0] <= 1 ? 0.001 : 0.5;
  return bounds[1] - bounds[0] <= 0.2 ? 0.001 : 0.005;
}

function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }

function renderAxisControls() {
  const container = $('#axis-controls');
  container.replaceChildren();
  const modeInfo = state.metadata.modes[state.mode];
  state.metadata.axes.forEach((axis) => {
    const bounds = modeInfo.bounds[axis.key];
    const value = clamp(Number(state.coordinates[axis.key]), bounds[0], bounds[1]);
    state.coordinates[axis.key] = value;
    const item = document.createElement('div');
    item.className = 'axis-control';

    const top = document.createElement('div');
    top.className = 'axis-topline';
    const name = document.createElement('span'); name.className = 'axis-name'; name.textContent = axis.label_kr;
    const symbol = document.createElement('span'); symbol.className = 'axis-symbol'; symbol.textContent = `${axis.symbol} · ${axis.unit}`;
    top.append(name, symbol);
    const short = document.createElement('p'); short.className = 'axis-short'; short.textContent = axis.short_kr;
    const row = document.createElement('div'); row.className = 'axis-input-row';
    const slider = document.createElement('input');
    slider.type = 'range'; slider.min = bounds[0]; slider.max = bounds[1]; slider.step = rangeStep(axis, bounds); slider.value = value;
    slider.setAttribute('aria-label', axis.label_kr);
    const numeric = document.createElement('input');
    numeric.type = 'number'; numeric.min = bounds[0]; numeric.max = bounds[1]; numeric.step = rangeStep(axis, bounds); numeric.value = value;
    numeric.setAttribute('aria-label', `${axis.label_kr} 숫자 입력`);
    const update = (raw) => {
      const parsed = Number(raw);
      if (!Number.isFinite(parsed)) return;
      const next = clamp(parsed, bounds[0], bounds[1]);
      const changed = !sameNumber(state.coordinates[axis.key], next);
      state.coordinates[axis.key] = next;
      slider.value = next; numeric.value = next;
      if (changed) markResultsStale();
    };
    slider.addEventListener('input', () => update(slider.value));
    numeric.addEventListener('change', () => update(numeric.value));
    row.append(slider, numeric);
    item.append(top, short, row);
    container.append(item);
  });
}

function resetCoordinates() {
  state.coordinates = { ...state.metadata.modes[state.mode].reference_coordinates };
  renderAxisControls();
  updateModeDetail();
}

function renderCombinationAxisControls() {
  const container = $('#combination-axis-controls');
  const available = state.metadata.axes.map((axis) => axis.key);
  const selected = new Set(state.combinationAxes.filter((key) => available.includes(key)));
  if (selected.size < 2) { selected.clear(); selected.add('cn'); selected.add('pu'); }
  state.combinationAxes = available.filter((key) => selected.has(key));
  container.replaceChildren();
  state.metadata.axes.forEach((axis) => {
    const label = document.createElement('label'); label.className = 'axis-choice';
    label.classList.toggle('selected', selected.has(axis.key));
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = selected.has(axis.key);
    checkbox.setAttribute('aria-label', `${axis.label_kr} 공동 만족 후보 축`);
    const caption = document.createElement('span'); caption.textContent = `${axis.symbol} · ${axis.short_kr}`;
    checkbox.addEventListener('change', () => {
      const next = new Set(state.combinationAxes);
      if (checkbox.checked) next.add(axis.key);
      else if (next.size > 2) next.delete(axis.key);
      else {
        checkbox.checked = true;
        setToast('공동 만족 후보 탐색에는 축을 최소 2개 선택해야 합니다.');
        return;
      }
      state.combinationAxes = available.filter((key) => next.has(key));
      renderCombinationAxisControls();
      clearCombinationResult('선택 축이 바뀌었습니다. 새 축 조합으로 다시 탐색하세요.');
    });
    label.append(checkbox, caption);
    container.append(label);
  });
}

function updateModeDetail() {
  const mode = state.metadata.modes[state.mode];
  text($('#mode-detail'), `${mode.label_kr} · 학습 온도 ${mode.temperature} · metric: ${mode.metric_kr}`);
  text($('#reference-label'), mode.reference_label);
  const target = currentTarget();
  const min = mode.vops[0]; const max = mode.vops.at(-1);
  $('#target-input').min = min; $('#target-input').max = max;
  if (target < min || target > max) $('#target-input').value = String(Math.min(max, Math.max(min, target)));
}

function populateSelects() {
  const axis = $('#axis-select');
  axis.replaceChildren();
  state.metadata.axes.forEach((item) => {
    const option = document.createElement('option'); option.value = item.key;
    option.textContent = `${item.symbol} — ${item.label_kr}`;
    axis.append(option);
  });
  axis.value = 'cn';
  renderCombinationAxisControls();
}

function vminDisplay(report) {
  if (!report) return '—';
  return report.vmin.label;
}

function renderForward() {
  for (const mode of ['read', 'write']) {
    const report = state.forward[mode];
    const card = $(`#${mode}-vmin`);
    const note = $(`#${mode}-note`);
    if (!report) { text(card, '—'); text(note, '계산 대기'); continue; }
    text(card, vminDisplay(report));
    if (state.stale.forward) {
      text(note, '입력 변경됨 — Vmin 예측을 다시 실행하세요.');
      continue;
    }
    const notes = [];
    if (!report.in_training_box) notes.push(`외삽 축: ${report.extrapolated_axes.join(', ')}`);
    if (!report.supply_monotone_on_grid) notes.push('전압 z가 grid에서 단조가 아님');
    if (!notes.length) notes.push('학습 상자 안의 surrogate 점예측');
    text(note, notes.join(' · '));
  }
  text($('#target-display'), `${number(currentTarget(), 4)} V`);
}

async function runPrediction() {
  if (state.busy) { setToast('현재 계산이 끝난 뒤 다시 실행하세요.'); return; }
  setInferenceBusy(true);
  try {
    const coordinates = currentCoordinates();
    const [read, write] = await Promise.all([
      request('/api/predict', { mode: 'read', coordinates }),
      request('/api/predict', { mode: 'write', coordinates }),
    ]);
    state.forward = { read, write };
    state.stale.forward = false;
    renderForward();
    const outOfBox = [...read.extrapolated_axes, ...write.extrapolated_axes];
    setToast(outOfBox.length ? '예측 완료: 다른 mode에서 외삽 경고가 있습니다.' : '읽기·쓰기 Vmin 예측을 갱신했습니다.');
  } catch (error) {
    setToast(`예측 실패: ${error.message}`);
  } finally {
    setInferenceBusy(false);
  }
}

function chartContext(canvas, heightFactor) {
  const width = Math.max(360, Math.floor(canvas.clientWidth));
  const height = Math.max(260, Math.floor(width * heightFactor));
  const dpr = window.devicePixelRatio || 1;
  canvas.style.height = `${height}px`;
  canvas.width = Math.floor(width * dpr); canvas.height = Math.floor(height * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return { ctx, width, height };
}

function drawEmpty(canvas, label, factor = 0.42) {
  const { ctx, width, height } = chartContext(canvas, factor);
  ctx.fillStyle = '#f8fbfd'; ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = '#607089'; ctx.font = '13px Segoe UI'; ctx.textAlign = 'center';
  ctx.fillText(label, width / 2, height / 2);
}

function drawSweep(result) {
  const canvas = $('#sweep-chart');
  if (!result) { drawEmpty(canvas, '선택 축 inverse 결과가 여기 표시됩니다.'); return; }
  const { ctx, width, height } = chartContext(canvas, 0.42);
  const pad = { left: 54, right: 20, top: 24, bottom: 46 };
  const plotW = width - pad.left - pad.right; const plotH = height - pad.top - pad.bottom;
  const xs = result.scan.axis_values; const ys = result.scan.vmin_values_V;
  const target = result.target_vmin_V;
  const finite = ys.filter((value) => value !== null && Number.isFinite(value));
  const lo = Math.min(target, ...finite) - 0.01; const hi = Math.max(target, ...finite) + 0.01;
  const yMin = Math.floor(lo * 100) / 100; const yMax = Math.ceil(hi * 100) / 100;
  const xMap = (value) => pad.left + (value - xs[0]) / (xs.at(-1) - xs[0]) * plotW;
  const yMap = (value) => pad.top + (yMax - value) / (yMax - yMin || .01) * plotH;
  ctx.fillStyle = '#fbfdfe'; ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = '#dce6ec'; ctx.lineWidth = 1;
  ctx.font = '10px Segoe UI'; ctx.fillStyle = '#607089'; ctx.textAlign = 'right';
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (plotH * i / 4); const value = yMax - ((yMax - yMin) * i / 4);
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
    ctx.fillText(`${value.toFixed(3)} V`, pad.left - 6, y + 3);
  }
  ctx.strokeStyle = '#9a4b23'; ctx.setLineDash([6, 5]); ctx.beginPath(); ctx.moveTo(pad.left, yMap(target)); ctx.lineTo(width - pad.right, yMap(target)); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle = '#9a4b23'; ctx.textAlign = 'left'; ctx.fillText(`target ${target.toFixed(3)} V`, pad.left + 5, yMap(target) - 6);
  ctx.strokeStyle = '#1d6594'; ctx.lineWidth = 2; ctx.beginPath(); let drawing = false;
  xs.forEach((x, index) => {
    const y = ys[index];
    if (y === null) { drawing = false; return; }
    if (!drawing) { ctx.moveTo(xMap(x), yMap(y)); drawing = true; } else ctx.lineTo(xMap(x), yMap(y));
  });
  ctx.stroke();
  result.solutions.forEach((solution) => {
    ctx.fillStyle = solution.status === 'in_range' ? '#18765c' : '#a93b3b';
    ctx.beginPath(); ctx.arc(xMap(solution.axis_value), yMap(target), 5, 0, Math.PI * 2); ctx.fill();
  });
  ctx.strokeStyle = '#6f7e8a'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(pad.left, pad.top); ctx.lineTo(pad.left, height - pad.bottom); ctx.lineTo(width - pad.right, height - pad.bottom); ctx.stroke();
  ctx.fillStyle = '#607089'; ctx.textAlign = 'center'; ctx.font = '10px Segoe UI';
  [xs[0], xs[Math.floor(xs.length / 2)], xs.at(-1)].forEach((value) => ctx.fillText(value.toFixed(2), xMap(value), height - pad.bottom + 15));
  ctx.fillText(`${result.axis_label} (${axisByKey(result.axis).unit})`, pad.left + plotW / 2, height - 9);
  ctx.save(); ctx.translate(14, pad.top + plotH / 2); ctx.rotate(-Math.PI / 2); ctx.fillText('surrogate Vmin', 0, 0); ctx.restore();
}

function drawPlane(plane) {
  const canvas = $('#plane-chart');
  if (!plane) { drawEmpty(canvas, '2D 단면 계산 결과가 여기 표시됩니다.', 0.58); return; }
  const { ctx, width, height } = chartContext(canvas, 0.58);
  const pad = { left: 54, right: 14, top: 20, bottom: 44 };
  const plotW = width - pad.left - pad.right; const plotH = height - pad.top - pad.bottom;
  const n = plane.points_per_axis; const values = plane.vmin_values_V; const statuses = plane.vmin_statuses;
  const finite = values.filter((value) => value !== null); const low = Math.min(...finite, 0.4); const high = Math.max(...finite, 0.75);
  const color = (value, status) => {
    if (status === 'below_grid') return '#214d87';
    if (status === 'above_grid') return '#b9243e';
    const t = Math.max(0, Math.min(1, (value - low) / (high - low || 1)));
    const stops = [[33,77,135], [132,183,207], [246,239,179], [242,160,68], [185,36,62]];
    const pos = t * (stops.length - 1); const i = Math.min(stops.length - 2, Math.floor(pos)); const local = pos - i;
    const a = stops[i]; const b = stops[i + 1];
    return `rgb(${a.map((c, j) => Math.round(c + (b[j] - c) * local)).join(',')})`;
  };
  ctx.fillStyle = '#fbfdfe'; ctx.fillRect(0, 0, width, height);
  const cellW = plotW / n; const cellH = plotH / n;
  for (let iy = 0; iy < n; iy++) {
    for (let ix = 0; ix < n; ix++) {
      const idx = iy * n + ix;
      ctx.fillStyle = color(values[idx], statuses[idx]);
      ctx.fillRect(pad.left + ix * cellW, pad.top + (n - 1 - iy) * cellH, Math.ceil(cellW) + .5, Math.ceil(cellH) + .5);
    }
  }
  const target = plane.target_vmin_V ?? currentTarget();
  ctx.strokeStyle = '#142335'; ctx.lineWidth = 1.2; ctx.setLineDash([4, 3]);
  for (let iy = 0; iy < n - 1; iy++) {
    for (let ix = 0; ix < n - 1; ix++) {
      const ids = [iy * n + ix, iy * n + ix + 1, (iy + 1) * n + ix, (iy + 1) * n + ix + 1];
      const cell = ids.map((id) => values[id]);
      if (cell.some((value) => value === null)) continue;
      if (Math.min(...cell) <= target && target <= Math.max(...cell)) {
        ctx.strokeRect(pad.left + ix * cellW, pad.top + (n - 2 - iy) * cellH, cellW, cellH);
      }
    }
  }
  ctx.setLineDash([]); ctx.strokeStyle = '#526474'; ctx.lineWidth = 1; ctx.strokeRect(pad.left, pad.top, plotW, plotH);
  const xVals = plane.x_values; const yVals = plane.y_values;
  ctx.fillStyle = '#607089'; ctx.font = '10px Segoe UI'; ctx.textAlign = 'center';
  [0, Math.floor((n - 1) / 2), n - 1].forEach((idx) => ctx.fillText(xVals[idx].toFixed(1), pad.left + idx * cellW + cellW / 2, height - pad.bottom + 15));
  ctx.fillText(`${axisByKey(plane.x_axis).symbol} (${axisByKey(plane.x_axis).unit})`, pad.left + plotW / 2, height - 9);
  ctx.textAlign = 'right';
  [0, Math.floor((n - 1) / 2), n - 1].forEach((idx) => ctx.fillText(yVals[idx].toFixed(1), pad.left - 6, pad.top + (n - 1 - idx) * cellH + cellH / 2 + 3));
  ctx.save(); ctx.translate(14, pad.top + plotH / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'center'; ctx.fillText(`${axisByKey(plane.y_axis).symbol} (${axisByKey(plane.y_axis).unit})`, 0, 0); ctx.restore();
  ctx.fillStyle = '#142335'; ctx.font = '10px Segoe UI'; ctx.textAlign = 'left'; ctx.fillText(`dashed cells: target ${target.toFixed(3)} V crosses`, pad.left + 7, pad.top + 14);
}

function isFiniteContourNode(value, status) {
  return status === 'in_range' && Number.isFinite(value);
}

function appendDistinctPoint(points, point) {
  if (!points.some((seen) => Math.abs(seen.x - point.x) < 1e-10 && Math.abs(seen.y - point.y) < 1e-10)) points.push(point);
}

function contourPairIndices(corners, intersectionCount, target) {
  if (intersectionCount !== 4) {
    const pairs = [];
    for (let index = 0; index + 1 < intersectionCount; index += 2) pairs.push([index, index + 1]);
    return pairs;
  }
  // Asymptotic decider for a bilinear saddle.  Intersections are ordered as
  // bottom, right, top, left.  Consecutive pairing invents a diagonal crossing.
  const delta = corners.map((corner) => corner.value - target);
  const determinant = delta[0] * delta[2] - delta[1] * delta[3];
  return determinant >= 0 ? [[0, 1], [2, 3]] : [[0, 3], [1, 2]];
}

function drawInterpolatedContour(ctx, xs, ys, values, statuses, finite, supplyMonotone, n, target, mapPoint, color) {
  let segments = 0;
  ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = 2.3; ctx.lineCap = 'round';
  const valueAt = (ix, iy) => iy * n + ix;
  for (let iy = 0; iy < n - 1; iy++) {
    for (let ix = 0; ix < n - 1; ix++) {
      const corners = [
        { x: xs[ix], y: ys[iy], index: valueAt(ix, iy) },
        { x: xs[ix + 1], y: ys[iy], index: valueAt(ix + 1, iy) },
        { x: xs[ix + 1], y: ys[iy + 1], index: valueAt(ix + 1, iy + 1) },
        { x: xs[ix], y: ys[iy + 1], index: valueAt(ix, iy + 1) },
      ].map((node) => ({ ...node, value: values[node.index], status: statuses[node.index] }));
      if (!corners.every((node) => isFiniteContourNode(node.value, node.status) && finite[node.index] && supplyMonotone[node.index])) continue;
      const intersections = [];
      [[0, 1], [1, 2], [2, 3], [3, 0]].forEach(([left, right]) => {
        const a = corners[left]; const b = corners[right];
        const da = a.value - target; const db = b.value - target;
        if (Math.abs(da) < 1e-12 && Math.abs(db) < 1e-12) return;
        if (Math.abs(da) < 1e-12) { appendDistinctPoint(intersections, a); return; }
        if (Math.abs(db) < 1e-12) { appendDistinctPoint(intersections, b); return; }
        if (da * db < 0) {
          const ratio = da / (da - db);
          appendDistinctPoint(intersections, { x: a.x + ratio * (b.x - a.x), y: a.y + ratio * (b.y - a.y) });
        }
      });
      contourPairIndices(corners, intersections.length, target).forEach(([startIndex, endIndex]) => {
        const start = mapPoint(intersections[startIndex]); const end = mapPoint(intersections[endIndex]);
        ctx.beginPath(); ctx.moveTo(start.x, start.y); ctx.lineTo(end.x, end.y); ctx.stroke(); segments += 1;
      });
    }
  }
  ctx.restore();
  return segments;
}

function drawJointPlane(plane) {
  const canvas = $('#plane-chart');
  if (!plane) { drawEmpty(canvas, 'read·write 공동 contour 결과가 여기 표시됩니다.', .58); return { read: 0, write: 0 }; }
  const { ctx, width, height } = chartContext(canvas, .58);
  const pad = { left: 54, right: 14, top: 20, bottom: 44 };
  const plotW = width - pad.left - pad.right; const plotH = height - pad.top - pad.bottom;
  const n = plane.points_per_axis; const xs = plane.x_values; const ys = plane.y_values;
  const target = plane.target_vmin_V;
  const read = plane.modes.read; const write = plane.modes.write;
  const xMap = (value) => pad.left + ((value - xs[0]) / (xs.at(-1) - xs[0] || 1)) * plotW;
  const yMap = (value) => pad.top + ((ys.at(-1) - value) / (ys.at(-1) - ys[0] || 1)) * plotH;
  const mapPoint = (point) => ({ x: xMap(point.x), y: yMap(point.y) });
  const cellW = plotW / (n - 1); const cellH = plotH / (n - 1);
  ctx.fillStyle = '#fbfdfe'; ctx.fillRect(0, 0, width, height);
  for (let iy = 0; iy < n - 1; iy++) {
    for (let ix = 0; ix < n - 1; ix++) {
      const ids = [iy * n + ix, iy * n + ix + 1, (iy + 1) * n + ix, (iy + 1) * n + ix + 1];
      const passes = ids.filter((id) => plane.joint_feasible[id]).length;
      const unknown = ids.some((id) => plane.unknown[id]);
      if (passes === 4) ctx.fillStyle = 'rgb(24 118 92 / 30%)';
      else if (passes > 0) ctx.fillStyle = 'rgb(24 118 92 / 12%)';
      else if (unknown) ctx.fillStyle = 'rgb(154 170 181 / 16%)';
      else continue;
      ctx.fillRect(pad.left + ix * cellW, pad.top + (n - 2 - iy) * cellH, Math.ceil(cellW) + .5, Math.ceil(cellH) + .5);
    }
  }
  const segments = {
    read: drawInterpolatedContour(ctx, xs, ys, read.vmin_values_V, read.vmin_statuses, read.finite, read.supply_monotone, n, target, mapPoint, '#1d6594'),
    write: drawInterpolatedContour(ctx, xs, ys, write.vmin_values_V, write.vmin_statuses, write.finite, write.supply_monotone, n, target, mapPoint, '#bc542c'),
  };
  ctx.strokeStyle = '#526474'; ctx.lineWidth = 1; ctx.strokeRect(pad.left, pad.top, plotW, plotH);
  ctx.fillStyle = '#607089'; ctx.font = '10px Segoe UI'; ctx.textAlign = 'center';
  [0, Math.floor((n - 1) / 2), n - 1].forEach((index) => ctx.fillText(xs[index].toFixed(1), xMap(xs[index]), height - pad.bottom + 15));
  ctx.fillText(`${axisByKey(plane.x_axis).symbol} (${axisByKey(plane.x_axis).unit})`, pad.left + plotW / 2, height - 9);
  ctx.textAlign = 'right';
  [0, Math.floor((n - 1) / 2), n - 1].forEach((index) => ctx.fillText(ys[index].toFixed(1), pad.left - 6, yMap(ys[index]) + 3));
  ctx.save(); ctx.translate(14, pad.top + plotH / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'center'; ctx.fillText(`${axisByKey(plane.y_axis).symbol} (${axisByKey(plane.y_axis).unit})`, 0, 0); ctx.restore();
  ctx.fillStyle = '#142335'; ctx.font = '10px Segoe UI'; ctx.textAlign = 'left';
  ctx.fillText(`blue/read · orange/write · target ${target.toFixed(3)} V`, pad.left + 7, pad.top + 14);
  return segments;
}

function renderInverse(result) {
  state.inverse = result;
  state.stale.inverse = false;
  drawSweep(result);
  const statusMap = {
    root_found: ['경계 1개 발견', 'good'],
    multiple_roots: ['복수 경계 발견', 'warn'],
    no_root_in_box: ['학습 상자 안 해 없음', 'warn'],
  };
  const [label, kind] = statusMap[result.status] || [result.status, 'neutral'];
  setStatus('#inverse-status', label, kind);
  text($('#inverse-title'), `${result.axis_label}을 scan하고, bracket이 있는 경계만 풉니다`);
  const callout = $('#inverse-result'); callout.replaceChildren();
  if (result.status === 'root_found') {
    const item = result.solutions[0];
    const prefix = document.createElement('strong'); prefix.textContent = `${result.axis_label}: ${item.axis_value.toFixed(3)} ${axisByKey(result.axis).unit}`;
    callout.append(prefix, document.createElement('br'), document.createTextNode(`target ${result.target_vmin_V.toFixed(4)} V에서 residual ${number(item.residual_mV, 3)} mV`));
  } else if (result.status === 'multiple_roots') {
    callout.textContent = `${result.solutions.length}개 교차를 찾았습니다. 한 축에 대해 유일한 경계라고 가정하면 안 됩니다.`;
  } else {
    callout.textContent = `선택한 ${result.axis_label} 범위에서는 target ${result.target_vmin_V.toFixed(4)} V를 가로지르는 scan bracket이 없습니다.`;
  }
  const caveats = $('#inverse-caveats'); caveats.replaceChildren();
  result.caveats.forEach((item) => { const li = document.createElement('li'); li.textContent = item; caveats.append(li); });
  if (result.scan.axis_direction === 'nonmonotonic_on_scan') {
    const li = document.createElement('li'); li.textContent = '현재 scan에서 축 방향이 단조가 아닙니다. 복수 해와 구간 선택을 확인하세요.'; caveats.append(li);
  }
}

function renderPlane(plane) {
  plane.target_vmin_V = plane.target_vmin_V ?? currentTarget();
  state.plane = plane;
  state.planeKind = 'single';
  state.stale.plane = false;
  $('#plane-layout').classList.remove('joint-view');
  drawPlane(plane);
  const status = plane.supply_monotone_count === plane.points_per_axis ** 2 ? ['grid 계산 완료', 'good'] : ['일부 전압 비단조', 'warn'];
  setStatus('#plane-status', status[0], status[1]);
  text($('#plane-title'), `${state.metadata.modes[plane.mode].label_kr} · ΔVth,N × ΔVth,P 단면`);
  text($('#plane-subtitle'), '선택 mode만 표시한 조건부 열지도입니다. 나머지 7축은 현재 좌표에 고정합니다.');
  text($('#plane-note'), plane.caveat);
}

function renderJointPlane(plane) {
  state.plane = plane;
  state.planeKind = 'joint';
  state.stale.plane = false;
  $('#plane-layout').classList.add('joint-view');
  const segments = drawJointPlane(plane);
  const total = plane.points_per_axis ** 2;
  const feasible = plane.joint_feasible.filter(Boolean).length;
  const unknown = plane.unknown.filter(Boolean).length;
  const readOutside = plane.modes.read.extrapolated_axes;
  const writeOutside = plane.modes.write.extrapolated_axes;
  const warnings = [];
  if (readOutside.length) warnings.push(`read 외삽 축: ${readOutside.join(', ')}`);
  if (writeOutside.length) warnings.push(`write 외삽 축: ${writeOutside.join(', ')}`);
  if (unknown) warnings.push(`${unknown}/${total} node은 censoring·비단조·비유한 상태로 공동 통과를 인증하지 않았습니다`);
  if (!segments.read) warnings.push('read target contour는 유한 Vmin node 사이에서 검출되지 않았습니다');
  if (!segments.write) warnings.push('write target contour는 유한 Vmin node 사이에서 검출되지 않았습니다');
  setStatus('#plane-status', feasible ? `공동 통과 ${feasible}/${total}` : '공동 통과 node 없음', feasible && !unknown ? 'good' : 'warn');
  text($('#plane-title'), `read·write 공동 contour · ${axisByKey(plane.x_axis).symbol} × ${axisByKey(plane.y_axis).symbol}`);
  text($('#plane-subtitle'), '동일한 9D 행을 read/write 모델에 함께 질의했습니다. 선택 두 축은 두 학습 상자의 교집합에서만 sweep합니다.');
  text($('#plane-note'), [
    `파란선 read, 주황선 write, 초록 음영은 양쪽 Vmin ≤ ${plane.target_vmin_V.toFixed(3)} V인 grid node입니다.`,
    ...warnings,
  ].join(' · '));
}

function candidateVminLabel(candidate, mode) {
  const value = candidate.modes[mode];
  const vops = state.metadata.modes[mode].vops;
  if (value.status === 'below_grid') return `< ${vops[0].toFixed(3)} V`;
  if (value.status === 'above_grid') return `> ${vops.at(-1).toFixed(3)} V`;
  return value.vmin_V === null ? '—' : `${number(value.vmin_V, 4)} V`;
}

function candidateDeltaLabel(axisKey, candidate, baseline) {
  const axis = axisByKey(axisKey); const delta = candidate.coordinates[axisKey] - baseline[axisKey];
  const digits = axis.unit === 'mV' ? 2 : 3;
  const prefix = delta >= 0 ? '+' : '';
  return `${prefix}${delta.toFixed(digits)} ${axis.unit}`;
}

function renderCombination(result) {
  state.combination = result;
  state.stale.combination = false;
  const feasible = result.feasible_count;
  const method = result.method === 'cartesian' ? 'Cartesian grid' : '결정론적 Latin-hypercube 표본';
  const baselineNote = result.provenance.baseline_included
    ? '현재 입력점도 shared-domain 표본으로 포함했습니다.'
    : '현재 선택 축 좌표가 shared training interval 밖이라 baseline은 후보 표본에 넣지 않았습니다.';
  const summary = $('#combination-summary');
  if (feasible) {
    summary.textContent = `${result.sampled_count}개 ${method} 중 ${feasible}개가 read·write 모두 ${result.target_vmin_V.toFixed(3)} V 이하였습니다. ${baselineNote} 아래는 입력점에서의 정규화 이동 거리가 작은 표본 후보입니다.`;
  } else {
    summary.textContent = `${result.sampled_count}개 ${method}에서 공동 만족 표본을 찾지 못했습니다. ${baselineNote} 이는 연속 공간에 해가 없다는 증명이 아닙니다.`;
  }
  setStatus('#combination-status', feasible ? `후보 ${feasible}/${result.sampled_count}` : '공동 만족 표본 없음', feasible && !result.unknown_count ? 'good' : 'warn');
  const head = $('#combination-table-head'); const body = $('#combination-table-body');
  head.replaceChildren(); body.replaceChildren();
  const headerRow = document.createElement('tr');
  ['#', ...result.axes.map((axis) => `${axisByKey(axis).symbol} 변화`), 'read Vmin', 'write Vmin', '정규화 거리', '적용'].forEach((label) => {
    const cell = document.createElement('th'); cell.scope = 'col'; cell.textContent = label; headerRow.append(cell);
  });
  head.append(headerRow);
  if (!result.candidates.length) {
    const row = document.createElement('tr'); const cell = document.createElement('td');
    cell.colSpan = result.axes.length + 5; cell.textContent = '표시할 공동 만족 표본 후보가 없습니다.'; row.append(cell); body.append(row);
  }
  result.candidates.forEach((candidate, index) => {
    const row = document.createElement('tr');
    const order = document.createElement('td'); order.textContent = String(index + 1); row.append(order);
    result.axes.forEach((axis) => {
      const cell = document.createElement('td'); cell.textContent = candidateDeltaLabel(axis, candidate, result.coordinates_fixed); row.append(cell);
    });
    ['read', 'write'].forEach((mode) => {
      const cell = document.createElement('td'); cell.className = 'candidate-vmin'; cell.textContent = candidateVminLabel(candidate, mode); row.append(cell);
    });
    const distance = document.createElement('td'); distance.textContent = number(candidate.normalized_distance, 4); row.append(distance);
    const action = document.createElement('td'); const button = document.createElement('button');
    button.type = 'button'; button.className = 'apply-candidate'; button.textContent = '이 후보 적용';
    button.addEventListener('click', () => {
      if (state.busy) { setToast('현재 계산이 끝난 뒤 후보를 적용하세요.'); return; }
      state.coordinates = { ...candidate.coordinates };
      renderAxisControls(); markResultsStale();
      setToast('선택 후보를 입력 축에 적용했습니다. Vmin 예측을 갱신합니다.');
      runPrediction();
    });
    action.append(button); row.append(action); body.append(row);
  });
  const caveats = $('#combination-caveats'); caveats.replaceChildren();
  result.caveats.forEach((item) => { const row = document.createElement('li'); row.textContent = item; caveats.append(row); });
  if (result.unknown_count) {
    const row = document.createElement('li'); row.textContent = `${result.unknown_count}개 표본은 비단조·비유한 값 또는 grid 밖 상태여서 공동 통과로 인증하지 않았습니다.`; caveats.append(row);
  }
  Object.entries(result.extrapolated_axes_by_mode).forEach(([mode, axes]) => {
    if (axes.length) { const row = document.createElement('li'); row.textContent = `${mode} 외삽 축: ${axes.join(', ')}`; caveats.append(row); }
  });
}

function card(title, definition, context, avoid) {
  const item = document.createElement('article'); item.className = 'concept-card';
  const h = document.createElement('h3'); h.textContent = title;
  const d = document.createElement('p'); d.className = 'definition'; d.textContent = definition;
  const c = document.createElement('p'); c.className = 'context'; c.textContent = `이 논문: ${context}`;
  const a = document.createElement('p'); a.className = 'avoid'; a.textContent = `주의: ${avoid}`;
  item.append(h, d, c, a); return item;
}

function renderKnowledge() {
  const target = $('#knowledge-content'); target.replaceChildren();
  if (state.activeTab === 'concepts') {
    conceptCards.forEach((item) => target.append(card(item.title, item.definition, item.context, item.avoid)));
  } else if (state.activeTab === 'sensitivity') {
    const intro = document.createElement('p'); intro.className = 'microcopy'; intro.textContent = '읽기 z(0.625 V)의 저장된 total-order Sobol ST 순위입니다. 막대의 합은 100%가 아닙니다.'; target.append(intro);
    (state.sensitivity?.rows || []).forEach((row) => {
      const item = document.createElement('div'); item.className = 'sensitivity-row';
      const left = document.createElement('div'); const name = document.createElement('strong'); name.textContent = row.label_kr;
      const sub = document.createElement('small'); sub.textContent = `S1=${number(row.S1, 3)} · ST에는 interaction 포함`;
      left.append(name, sub); const value = document.createElement('span'); value.textContent = number(row.ST, 3); item.append(left, value); target.append(item);
    });
    (state.sensitivity?.scope || []).forEach((item) => { const p = document.createElement('p'); p.className = 'limit-banner'; p.textContent = item; target.append(p); });
  } else if (state.activeTab === 'scenario') {
    const s = state.scenario?.scenario;
    if (!s) { target.textContent = '논문 시나리오를 불러오는 중…'; return; }
    const intro = document.createElement('p'); intro.className = 'microcopy'; intro.textContent = `저장된 논문 시나리오: 사양 ${s.v_t0.toFixed(3)} V → 목표 ${s.v_target.toFixed(3)} V.`; target.append(intro);
    s.cases.forEach((item) => {
      const cardNode = document.createElement('article'); cardNode.className = 'scenario-card';
      const h = document.createElement('h3'); h.textContent = item.label;
      const p = document.createElement('p');
      if (item.reachable) {
        const change = item.sigma_reduction_pct ?? item.corner_shrink_pct;
        p.textContent = `surrogate point estimate: ${number(change, 1)}% 변화 → binding Vmin ${number(item.vmin_at_s, 4)} V`;
      } else p.textContent = `설정 하한에서도 ${number(item.vmin_at_floor, 4)} V. 이것만으로 물리적 불가능을 단정하지 않습니다.`;
      cardNode.append(h, p); target.append(cardNode);
    });
    (state.scenario.caveats || []).forEach((item) => { const p = document.createElement('p'); p.className = 'limit-banner'; p.textContent = item; target.append(p); });
  } else {
    const title = document.createElement('h3'); title.textContent = '이 화면에서 반드시 함께 말할 한계'; target.append(title);
    state.metadata.limitations.forEach((item) => { const p = document.createElement('p'); p.className = 'limit-banner'; p.textContent = item; target.append(p); });
  }
}

async function runInverse() {
  if (state.busy) { setToast('현재 계산이 끝난 뒤 다시 실행하세요.'); return; }
  setInferenceBusy(true); setStatus('#inverse-status', 'scan 중…', 'neutral');
  try {
    const result = await request('/api/inverse', {
      mode: state.mode,
      coordinates: currentCoordinates(),
      axis: currentAxis(),
      target_vmin: currentTarget(),
      scan_points: 81,
    });
    renderInverse(result);
    setToast(result.status === 'root_found' ? '조건부 inverse 경계를 찾았습니다.' : 'scan 결과를 확인하세요. 해가 유일하지 않거나 없을 수 있습니다.');
  } catch (error) {
    setStatus('#inverse-status', '입력 확인 필요', 'bad'); setToast(`inverse 실패: ${error.message}`);
  } finally { setInferenceBusy(false); }
}

async function runPlane() {
  if (state.busy) { setToast('현재 계산이 끝난 뒤 다시 실행하세요.'); return; }
  const target = currentTarget();
  setInferenceBusy(true); setStatus('#plane-status', '2D grid 계산 중…', 'neutral');
  try {
    const plane = await request('/api/plane', { mode: state.mode, coordinates: currentCoordinates(), x_axis: 'cn', y_axis: 'pu', points: 31 });
    plane.target_vmin_V = target;
    renderPlane(plane); setToast('2D 조건부 단면을 계산했습니다.');
  } catch (error) {
    setStatus('#plane-status', '계산 실패', 'bad'); setToast(`2D 단면 실패: ${error.message}`);
  } finally { setInferenceBusy(false); }
}

function combinationBudget(axisCount) {
  if (axisCount === 2) return 31 ** 2;
  if (axisCount === 3) return 11 ** 3;
  return 2048;
}

function jointTargetOrNull() {
  const target = currentTarget();
  const low = Math.max(state.metadata.modes.read.vops[0], state.metadata.modes.write.vops[0]);
  const high = Math.min(state.metadata.modes.read.vops.at(-1), state.metadata.modes.write.vops.at(-1));
  if (!Number.isFinite(target) || target < low || target > high) {
    setToast(`공동 탐색 target은 양쪽 voltage grid 공통 범위 ${low.toFixed(3)}–${high.toFixed(3)} V 안이어야 합니다.`);
    return null;
  }
  return target;
}

async function runJointPlane() {
  if (state.busy) { setToast('현재 계산이 끝난 뒤 다시 실행하세요.'); return; }
  const target = jointTargetOrNull(); if (target === null) return;
  setInferenceBusy(true); setStatus('#plane-status', '공동 contour 계산 중…', 'neutral');
  try {
    const plane = await request('/api/joint-plane', {
      coordinates: currentCoordinates(), x_axis: 'cn', y_axis: 'pu', target_vmin: target, points: 31,
    });
    renderJointPlane(plane); setToast('동일 좌표의 read·write 공동 contour를 계산했습니다.');
  } catch (error) {
    setStatus('#plane-status', '계산 실패', 'bad'); setToast(`공동 contour 실패: ${error.message}`);
  } finally { setInferenceBusy(false); }
}

async function runCombination() {
  if (state.busy) { setToast('현재 계산이 끝난 뒤 다시 실행하세요.'); return; }
  const axes = currentCombinationAxes();
  if (axes.length < 2) { setToast('공동 만족 후보 탐색에는 축을 최소 2개 선택해야 합니다.'); return; }
  const target = jointTargetOrNull(); if (target === null) return;
  setInferenceBusy(true); setStatus('#combination-status', '후보 표본 계산 중…', 'neutral');
  try {
    const result = await request('/api/combination', {
      coordinates: currentCoordinates(), axes, target_vmin: target, budget: combinationBudget(axes.length),
    });
    renderCombination(result);
    setToast(result.feasible_count ? '공동 만족 표본 후보를 찾았습니다.' : '이번 표본에서는 공동 만족 후보가 없습니다.');
  } catch (error) {
    setStatus('#combination-status', '입력 확인 필요', 'bad'); setToast(`다축 후보 탐색 실패: ${error.message}`);
  } finally { setInferenceBusy(false); }
}

function exportResult() {
  const payload = {
    tool: state.metadata.app_name,
    version: state.metadata.app_version,
    exported_at_local: new Date().toString(),
    query: {
      mode: state.mode, target_vmin_V: currentTarget(), inverse_axis: currentAxis(),
      combination_axes: currentCombinationAxes(), coordinates: currentCoordinates(),
    },
    forward: state.forward,
    inverse: state.inverse,
    plane: state.plane,
    plane_kind: state.planeKind,
    combination: state.combination,
    result_staleness: { ...state.stale },
    results_stale_for_current_inputs: Object.values(state.stale).some(Boolean),
    disclosure: 'Local surrogate result only. This export contains no raw model weights or training labels.',
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `sram-vmin-query-${new Date().toISOString().slice(0, 10)}.json`; link.click(); URL.revokeObjectURL(link.href);
  setToast('현재 query와 결과를 JSON으로 저장했습니다.');
}

async function initialize() {
  try {
    state.metadata = await request('/api/metadata');
    state.scenario = await request('/api/scenario');
    state.sensitivity = await request('/api/sensitivity');
    text($('#model-status'), '로컬 모델 준비 완료 · 원본 data를 네트워크로 보내지 않습니다.');
    text($('#target-chip'), `z target = ${state.metadata.z_target.toFixed(4)}`);
    populateSelects(); resetCoordinates(); renderKnowledge(); drawEmpty($('#sweep-chart'), '선택 축 inverse 결과가 여기 표시됩니다.'); drawJointPlane(null);
    await runPrediction();
  } catch (error) {
    text($('#model-status'), `초기화 실패: ${error.message}`); setToast(`도구 초기화 실패: ${error.message}`);
  }
}

$('#mode-select').addEventListener('change', (event) => {
  state.mode = event.target.value; resetCoordinates(); state.stale = { forward: true, inverse: false, plane: false, combination: false }; state.inverse = null; state.plane = null; state.planeKind = null; state.combination = null;
  drawEmpty($('#sweep-chart'), 'mode가 바뀌었습니다. inverse를 다시 계산하세요.'); drawJointPlane(null);
  setStatus('#inverse-status', '계산 대기', 'neutral'); setStatus('#plane-status', '계산 대기', 'neutral'); clearCombinationResult();
  runPrediction();
});
$('#reset-button').addEventListener('click', () => { resetCoordinates(); markResultsStale(); runPrediction(); });
$('#predict-button').addEventListener('click', runPrediction);
$('#inverse-button').addEventListener('click', runInverse);
$('#plane-button').addEventListener('click', runPlane);
$('#joint-plane-button').addEventListener('click', runJointPlane);
$('#combination-button').addEventListener('click', runCombination);
$('#export-button').addEventListener('click', exportResult);
$('#axis-select').addEventListener('change', () => { if (state.inverse) { state.stale.inverse = true; setStatus('#inverse-status', 'inverse 축 변경됨', 'warn'); } });
$('#presentation-toggle').addEventListener('click', () => { document.body.classList.toggle('presentation-mode'); const on = document.body.classList.contains('presentation-mode'); $('#presentation-toggle').textContent = on ? '편집 화면' : '발표 화면'; window.setTimeout(() => { drawSweep(state.inverse); if (state.planeKind === 'joint') drawJointPlane(state.plane); else drawPlane(state.plane); }, 120); });
$('#target-input').addEventListener('change', () => { text($('#target-display'), `${number(currentTarget(), 4)} V`); markResultsStale({ forward: false }); });
$$('.tab').forEach((button) => button.addEventListener('click', () => { state.activeTab = button.dataset.tab; $$('.tab').forEach((tab) => { const active = tab === button; tab.classList.toggle('active', active); tab.setAttribute('aria-selected', String(active)); }); renderKnowledge(); }));
window.addEventListener('resize', () => { drawSweep(state.inverse); if (state.planeKind === 'joint') drawJointPlane(state.plane); else drawPlane(state.plane); });

initialize();
