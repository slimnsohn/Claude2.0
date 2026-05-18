// Run with: node tests/pure-logic.test.js  (from apps/wall-dashboard/)
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

// Node 24's vm.runInNewContext runs Code.gs in a separate realm, so arrays it
// returns fail deepStrictEqual's cross-realm prototype check against host-realm
// array literals. JSON-normalize both sides before comparing. Test-harness only.
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
test('feelsLike_ hot but humidity missing returns raw temp', () => {
  assert.strictEqual(lib.feelsLike_(90, null, 5), 90);
});
test('feelsLike_ cold but wind below 3mph returns raw temp', () => {
  assert.strictEqual(lib.feelsLike_(20, 40, 2), 20);
});
test('feelsLike_ at 79F just below heat-index threshold returns raw temp', () => {
  assert.strictEqual(lib.feelsLike_(79, 90, 0), 79);
});
test('feelsLike_ at 51F just above wind-chill threshold returns raw temp', () => {
  assert.strictEqual(lib.feelsLike_(51, 40, 30), 51);
});

// --- matchHour_ ---
test('matchHour_ finds the period with the matching key', () => {
  const hourly = [
    { hourKey: '2026-05-17-13', temp: 74 },
    { hourKey: '2026-05-17-14', temp: 76 }
  ];
  assert.strictEqual(lib.matchHour_(hourly, '2026-05-17-14').temp, 76);
});
test('matchHour_ returns null when no period matches', () => {
  assert.strictEqual(lib.matchHour_([], '2026-05-17-14'), null);
});

// --- cachedFetch_ (uses an injected CacheService stub) ---
function makeStubbedLib() {
  const store = {};
  const fakeCache = {
    get: function (k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
    put: function (k, v) { store[k] = v; }
  };
  const stubbedLib = loadCode({ CacheService: { getScriptCache: function () { return fakeCache; } } });
  return { lib: stubbedLib, store: store };
}
test('cachedFetch_ returns the cached value on the second call', () => {
  const ctx = makeStubbedLib();
  let calls = 0;
  const r1 = ctx.lib.cachedFetch_('k', 60, function () { calls++; return { n: 1 }; });
  const r2 = ctx.lib.cachedFetch_('k', 60, function () { calls++; return { n: 2 }; });
  assert.strictEqual(r1.n, 1);
  assert.strictEqual(r2.n, 1);
  assert.strictEqual(calls, 1);
});
test('cachedFetch_ serves last-good value when the fetch throws', () => {
  const ctx = makeStubbedLib();
  ctx.lib.cachedFetch_('k', 60, function () { return { n: 1 }; });
  delete ctx.store['k']; // primary cache expired, last-good remains
  const r = ctx.lib.cachedFetch_('k', 60, function () { throw new Error('network down'); });
  assert.strictEqual(r.n, 1);
});
test('cachedFetch_ rethrows when there is no last-good value', () => {
  const ctx = makeStubbedLib();
  assert.throws(function () {
    ctx.lib.cachedFetch_('k', 60, function () { throw new Error('network down'); });
  }, /network down/);
});

// --- aqiInfo_ ---
test('aqiInfo_ Good has no alert', () => {
  const r = lib.aqiInfo_(42);
  assert.strictEqual(r.category, 'Good');
  assert.strictEqual(r.level, 'good');
  assert.strictEqual(r.alert, false);
});
test('aqiInfo_ Moderate alerts', () => {
  const r = lib.aqiInfo_(86);
  assert.strictEqual(r.category, 'Moderate');
  assert.strictEqual(r.level, 'moderate');
  assert.strictEqual(r.alert, true);
});
test('aqiInfo_ Unhealthy for Sensitive alerts', () => {
  const r = lib.aqiInfo_(130);
  assert.strictEqual(r.category, 'Unhealthy for Sensitive');
  assert.strictEqual(r.level, 'unhealthy');
  assert.strictEqual(r.alert, true);
});
test('aqiInfo_ Unhealthy alerts', () => {
  const r = lib.aqiInfo_(175);
  assert.strictEqual(r.category, 'Unhealthy');
  assert.strictEqual(r.level, 'unhealthy');
  assert.strictEqual(r.alert, true);
});
test('aqiInfo_ boundaries (50 Good, 51 Moderate)', () => {
  assert.strictEqual(lib.aqiInfo_(50).alert, false);
  assert.strictEqual(lib.aqiInfo_(51).alert, true);
});
test('aqiInfo_ Hazardous alerts', () => {
  assert.strictEqual(lib.aqiInfo_(420).category, 'Hazardous');
});

// === MORE TESTS APPENDED BELOW BY LATER TASKS ===

// --- parseCsv_ ---
test('parseCsv_ parses rows into header-keyed objects', () => {
  const rows = lib.parseCsv_('a,b\n1,2\n3,4');
  assert.deepStrictEqual(rows, [{ a: '1', b: '2' }, { a: '3', b: '4' }]);
});
test('parseCsv_ tolerates CRLF line endings', () => {
  const rows = lib.parseCsv_('a,b\r\n1,2\r\n');
  assert.deepStrictEqual(rows, [{ a: '1', b: '2' }]);
});
test('parseCsv_ handles quoted fields with embedded commas', () => {
  const rows = lib.parseCsv_('a,b\n"x,y",z');
  assert.deepStrictEqual(rows, [{ a: 'x,y', b: 'z' }]);
});
test('parseCsv_ returns [] for header-only text', () => {
  assert.deepStrictEqual(lib.parseCsv_('a,b'), []);
});

// --- gtfsTimeToMinutes_ ---
test('gtfsTimeToMinutes_ parses a zero-padded time', () => {
  assert.strictEqual(lib.gtfsTimeToMinutes_('07:31:00'), 451);
});
test('gtfsTimeToMinutes_ parses a non-padded hour', () => {
  assert.strictEqual(lib.gtfsTimeToMinutes_('7:31:00'), 451);
});
test('gtfsTimeToMinutes_ wraps hours past 24 (multi-day trip)', () => {
  assert.strictEqual(lib.gtfsTimeToMinutes_('65:12:00'), 1032);
});
test('gtfsTimeToMinutes_ throws on a bad string', () => {
  assert.throws(() => lib.gtfsTimeToMinutes_('nope'), /Bad GTFS time/);
});

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
