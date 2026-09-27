'use strict';

// Keep the bilinear-saddle rule test dependency-free.  The browser source is
// evaluated only up to the contour helpers, so no DOM/network/UI boot occurs.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appPath = path.resolve(__dirname, '..', 'static', 'app.js');
const source = fs.readFileSync(appPath, 'utf8');
const cutoff = source.indexOf('function drawInterpolatedContour');
assert.notEqual(cutoff, -1, 'contour helper must remain available');

const context = {
  document: { querySelector: () => null, querySelectorAll: () => [] },
  window: {},
  fetch: async () => { throw new Error('not used by contour helper test'); },
};
vm.runInNewContext(source.slice(0, cutoff), context, { filename: appPath });

function pairing(values) {
  const corners = values.map((value) => ({ value }));
  return JSON.parse(JSON.stringify(context.contourPairIndices(corners, 4, 0.6)));
}

test('bilinear saddle joins around isolated low corners instead of crossing diagonals', () => {
  // Corner order is SW, SE, NE, NW; edge order is bottom, right, top, left.
  assert.deepEqual(pairing([0.59, 0.90, 0.59, 0.90]), [[0, 3], [1, 2]]);
});

test('bilinear saddle uses the complementary topology when high corners are isolated', () => {
  assert.deepEqual(pairing([0.90, 0.59, 0.90, 0.59]), [[0, 1], [2, 3]]);
});

test('ordinary cells keep consecutive intersection pairing', () => {
  const corners = [{ value: 0.5 }, { value: 0.7 }, { value: 0.8 }, { value: 0.9 }];
  const pairs = context.contourPairIndices(corners, 2, 0.6);
  assert.deepEqual(JSON.parse(JSON.stringify(pairs)), [[0, 1]]);
});
