// Run with: node tests/pure-logic.test.js  (from apps/wall-dashboard/)
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

// Node 24 vm sandboxes create a separate realm whose Array prototype does not
// satisfy `instanceof Array` in the host realm.  deepStrictEqual uses realm
// identity, so cross-sandbox array comparisons fail even when values are equal.
// Patch: JSON-normalize both sides before comparing objects/arrays.
const _origDSE = assert.deepStrictEqual.bind(assert);
assert.deepStrictEqual = function (a, b, msg) {
  const norm = (v) => (v !== null && typeof v === 'object') ? JSON.parse(JSON.stringify(v)) : v;
  _origDSE(norm(a), norm(b), msg);
};

function loadCode(extraGlobals) {
  const code = fs.readFileSync(path.join(__dirname, '../apps-script/Code.gs'), 'utf8');
  const sandbox = Object.assign(
    { module: { exports: {} }, console, JSON, Math, Date },
    extraGlobals || {}
  );
  vm.runInNewContext(code, sandbox);
  return sandbox.module.exports;
}

let pass = 0, fail = 0;
function test(name, fn) {
  try { fn(); pass++; console.log('  PASS ' + name); }
  catch (e) { fail++; console.log('  FAIL ' + name + '\n    ' + e.message); }
}

const lib = loadCode();

// --- routeView_ ---
test('routeView_ defaults to dashboard', () => {
  assert.strictEqual(lib.routeView_(undefined, undefined), 'dashboard');
});
test('routeView_ maps trains', () => {
  assert.strictEqual(lib.routeView_('trains', undefined), 'trains');
});
test('routeView_ maps trains json', () => {
  assert.strictEqual(lib.routeView_('trains', 'json'), 'trainsJson');
});
test('routeView_ unknown view falls back to dashboard', () => {
  assert.strictEqual(lib.routeView_('something-else', undefined), 'dashboard');
});

// --- getWeatherWindow_ ---
test('getWeatherWindow_ before flip shows rest of today', () => {
  const w = lib.getWeatherWindow_(8, 17, 19);
  assert.strictEqual(w.dayOffset, 0);
  assert.deepStrictEqual(w.hours, [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);
});
test('getWeatherWindow_ late afternoon narrows to three hours', () => {
  const w = lib.getWeatherWindow_(16, 17, 19);
  assert.strictEqual(w.dayOffset, 0);
  assert.deepStrictEqual(w.hours, [17, 18, 19]);
});
test('getWeatherWindow_ at flip hour shows tomorrow', () => {
  const w = lib.getWeatherWindow_(17, 17, 19);
  assert.strictEqual(w.dayOffset, 1);
  assert.deepStrictEqual(w.hours, [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);
});
test('getWeatherWindow_ evening shows tomorrow', () => {
  const w = lib.getWeatherWindow_(21, 17, 19);
  assert.strictEqual(w.dayOffset, 1);
  assert.strictEqual(w.hours[0], 7);
});

// --- formatHourLabel_ ---
test('formatHourLabel_ morning', () => {
  assert.strictEqual(lib.formatHourLabel_(9), '9a');
});
test('formatHourLabel_ afternoon', () => {
  assert.strictEqual(lib.formatHourLabel_(13), '1p');
});
test('formatHourLabel_ noon and midnight', () => {
  assert.strictEqual(lib.formatHourLabel_(12), '12p');
  assert.strictEqual(lib.formatHourLabel_(0), '12a');
});

// --- feelsLike_ ---
test('feelsLike_ mild temp returns temp itself', () => {
  assert.strictEqual(lib.feelsLike_(70, 50, 5), 70);
});
test('feelsLike_ hot+humid uses heat index (higher than temp)', () => {
  const f = lib.feelsLike_(90, 70, 5);
  assert.ok(f >= 104 && f <= 110, 'expected ~106, got ' + f);
});
test('feelsLike_ cold+windy uses wind chill (lower than temp)', () => {
  const f = lib.feelsLike_(20, 40, 20);
  assert.ok(f >= 2 && f <= 8, 'expected ~4, got ' + f);
});
test('feelsLike_ null temp returns null', () => {
  assert.strictEqual(lib.feelsLike_(null, 50, 5), null);
});

// === MORE TESTS APPENDED BELOW BY LATER TASKS ===

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
