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
test('parseCsv_ ignores fields beyond the header count', () => {
  assert.deepStrictEqual(lib.parseCsv_('a,b\n1,2,3'), [{ a: '1', b: '2' }]);
});
test('parseCsv_ returns [] for empty input', () => {
  assert.deepStrictEqual(lib.parseCsv_(''), []);
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

// --- minutesToHHMM_ ---
test('minutesToHHMM_ zero-pads the hour', () => {
  assert.strictEqual(lib.minutesToHHMM_(451), '07:31');
});
test('minutesToHHMM_ afternoon', () => {
  assert.strictEqual(lib.minutesToHHMM_(1032), '17:12');
});
test('minutesToHHMM_ midnight', () => {
  assert.strictEqual(lib.minutesToHHMM_(0), '00:00');
});

// --- headsignDirection_ ---
test('headsignDirection_ Chicago is southbound', () => {
  assert.strictEqual(lib.headsignDirection_('Chicago'), 'SB');
});
test('headsignDirection_ Milwaukee is northbound', () => {
  assert.strictEqual(lib.headsignDirection_('Milwaukee'), 'NB');
});
test('headsignDirection_ Seattle is northbound', () => {
  assert.strictEqual(lib.headsignDirection_('Seattle'), 'NB');
});

// --- calendarBitstring_ / unionBits_ ---
test('calendarBitstring_ builds a Mon-Sun bitstring', () => {
  const row = { monday: '1', tuesday: '1', wednesday: '1', thursday: '1',
                friday: '1', saturday: '0', sunday: '0' };
  assert.strictEqual(lib.calendarBitstring_(row), '1111100');
});
test('calendarBitstring_ all days', () => {
  const row = { monday: '1', tuesday: '1', wednesday: '1', thursday: '1',
                friday: '1', saturday: '1', sunday: '1' };
  assert.strictEqual(lib.calendarBitstring_(row), '1111111');
});
test('unionBits_ ORs two bitstrings', () => {
  assert.strictEqual(lib.unionBits_('1111100', '0000011'), '1111111');
});
test('unionBits_ is idempotent', () => {
  assert.strictEqual(lib.unionBits_('1000001', '1000001'), '1000001');
});

// --- dateInWindow_ ---
test('dateInWindow_ true inside the window', () => {
  assert.strictEqual(lib.dateInWindow_('20260518', '20260517', '20270517'), true);
});
test('dateInWindow_ false before the window', () => {
  assert.strictEqual(lib.dateInWindow_('20260516', '20260517', '20270517'), false);
});
test('dateInWindow_ inclusive on both ends', () => {
  assert.strictEqual(lib.dateInWindow_('20260517', '20260517', '20270517'), true);
  assert.strictEqual(lib.dateInWindow_('20270517', '20260517', '20270517'), true);
});

// --- extractAmtrakRows_ ---
const GTFS_FIXTURE = {
  routes: [
    { route_id: '54', route_long_name: 'Hiawatha Service' },
    { route_id: '75', route_long_name: 'Empire Builder' },
    { route_id: '99', route_long_name: 'Some Other Route' }
  ],
  calendar: [
    { service_id: 'WK', monday: '1', tuesday: '1', wednesday: '1', thursday: '1',
      friday: '1', saturday: '0', sunday: '0', start_date: '20260101', end_date: '20270101' },
    { service_id: 'WE', monday: '0', tuesday: '0', wednesday: '0', thursday: '0',
      friday: '0', saturday: '1', sunday: '1', start_date: '20260101', end_date: '20270101' },
    { service_id: 'OLD', monday: '1', tuesday: '1', wednesday: '1', thursday: '1',
      friday: '1', saturday: '1', sunday: '1', start_date: '20200101', end_date: '20200201' }
  ],
  trips: [
    // train 329 NB, runs weekdays
    { route_id: '54', service_id: 'WK', trip_id: 't1', trip_short_name: '329',
      trip_headsign: 'Milwaukee' },
    // train 329 NB again, weekend service -> should union into the same row
    { route_id: '54', service_id: 'WE', trip_id: 't2', trip_short_name: '329',
      trip_headsign: 'Milwaukee' },
    // train 330 SB
    { route_id: '54', service_id: 'WK', trip_id: 't3', trip_short_name: '330',
      trip_headsign: 'Chicago' },
    // expired service -> excluded
    { route_id: '54', service_id: 'OLD', trip_id: 't4', trip_short_name: '999',
      trip_headsign: 'Milwaukee' },
    // other route -> excluded
    { route_id: '99', service_id: 'WK', trip_id: 't5', trip_short_name: '500',
      trip_headsign: 'Chicago' }
  ],
  stopTimes: [
    { trip_id: 't1', stop_id: 'GLN', departure_time: '08:24:00' },
    { trip_id: 't2', stop_id: 'GLN', departure_time: '08:24:00' },
    { trip_id: 't3', stop_id: 'GLN', departure_time: '06:43:00' },
    { trip_id: 't4', stop_id: 'GLN', departure_time: '09:00:00' },
    { trip_id: 't5', stop_id: 'GLN', departure_time: '07:00:00' },
    { trip_id: 't1', stop_id: 'CHI', departure_time: '08:50:00' }
  ]
};
test('extractAmtrakRows_ joins, filters, sorts, and unions service days', () => {
  const rows = lib.extractAmtrakRows_(GTFS_FIXTURE, '20260518');
  assert.deepStrictEqual(rows, [
    { trainNum: '330', direction: 'SB', glenviewTime: '06:43', days: '1111100' },
    { trainNum: '329', direction: 'NB', glenviewTime: '08:24', days: '1111111' }
  ]);
});
test('extractAmtrakRows_ excludes expired services and other routes', () => {
  const rows = lib.extractAmtrakRows_(GTFS_FIXTURE, '20260518');
  assert.ok(!rows.some(r => r.trainNum === '999'));
  assert.ok(!rows.some(r => r.trainNum === '500'));
});
test('extractAmtrakRows_ returns [] when nothing matches', () => {
  assert.deepStrictEqual(lib.extractAmtrakRows_(GTFS_FIXTURE, '20990101'), []);
});

// --- parseHHMM_ ---
test('parseHHMM_ parses a zero-padded time', () => {
  assert.strictEqual(lib.parseHHMM_('06:43'), 403);
});
test('parseHHMM_ parses a non-padded hour', () => {
  assert.strictEqual(lib.parseHHMM_('6:43'), 403);
});
test('parseHHMM_ throws on a bad string', () => {
  assert.throws(() => lib.parseHHMM_('not a time'), /Bad time/);
});

// --- parseDays_ ---
test('parseDays_ parses a weekday bitstring', () => {
  assert.deepStrictEqual(lib.parseDays_('1111100'), [1, 2, 3, 4, 5]);
});
test('parseDays_ parses a weekend bitstring', () => {
  assert.deepStrictEqual(lib.parseDays_('0000011'), [0, 6]);
});
test('parseDays_ all seven days', () => {
  assert.deepStrictEqual(lib.parseDays_('1111111'), [0, 1, 2, 3, 4, 5, 6]);
});
test('parseDays_ Sunday only', () => {
  assert.deepStrictEqual(lib.parseDays_('0000001'), [0]);
});
test('parseDays_ Monday only', () => {
  assert.deepStrictEqual(lib.parseDays_('1000000'), [1]);
});

// --- northbrookMinutes_ ---
test('northbrookMinutes_ NB adds 3 minutes', () => {
  assert.strictEqual(lib.northbrookMinutes_('06:43', 'NB'), 406);
});
test('northbrookMinutes_ SB subtracts 3 minutes', () => {
  assert.strictEqual(lib.northbrookMinutes_('06:43', 'SB'), 400);
});
test('northbrookMinutes_ wraps past midnight', () => {
  assert.strictEqual(lib.northbrookMinutes_('00:01', 'SB'), 1438);
});

// --- formatCountdown_ ---
test('formatCountdown_ under an hour', () => {
  assert.strictEqual(lib.formatCountdown_(9), '9 min');
});
test('formatCountdown_ at zero', () => {
  assert.strictEqual(lib.formatCountdown_(0), '0 min');
});
test('formatCountdown_ at 59 minutes', () => {
  assert.strictEqual(lib.formatCountdown_(59), '59 min');
});
test('formatCountdown_ at exactly an hour', () => {
  assert.strictEqual(lib.formatCountdown_(60), '1h 0m');
});
test('formatCountdown_ over an hour', () => {
  assert.strictEqual(lib.formatCountdown_(69), '1h 9m');
});

// --- formatClockTime_ ---
test('formatClockTime_ morning', () => {
  assert.strictEqual(lib.formatClockTime_(403), '6:43 AM');
});
test('formatClockTime_ midnight', () => {
  assert.strictEqual(lib.formatClockTime_(0), '12:00 AM');
});
test('formatClockTime_ noon', () => {
  assert.strictEqual(lib.formatClockTime_(720), '12:00 PM');
});
test('formatClockTime_ evening pads minutes', () => {
  assert.strictEqual(lib.formatClockTime_(1382), '11:02 PM');
});
test('formatClockTime_ wraps tomorrow values', () => {
  assert.strictEqual(lib.formatClockTime_(1446), '12:06 AM');
});

// --- computeAmtrakTrains_ ---
const SAMPLE_SCHEDULE = [
  { trainNum: '329', direction: 'NB', glenviewTime: '06:43', days: '1111100' },
  { trainNum: '330', direction: 'SB', glenviewTime: '08:00', days: '0000011' },
  { trainNum: '8',   direction: 'SB', glenviewTime: '09:42', days: '1111111' }
];
test('computeAmtrakTrains_ keeps only trains running on the given day', () => {
  // Wednesday = 3 -> 329 (Mon-Fri) and 8 (Daily) run; 330 (Sat,Sun) does not
  const out = lib.computeAmtrakTrains_(SAMPLE_SCHEDULE, 3);
  assert.strictEqual(out.length, 2);
});
test('computeAmtrakTrains_ computes Northbrook pass times and type', () => {
  // Saturday = 6 -> 330 (SB 08:00 -> 477) and 8 (SB 09:42 -> 579)
  const out = lib.computeAmtrakTrains_(SAMPLE_SCHEDULE, 6);
  assert.deepStrictEqual(out, [
    { type: 'Amtrak', passMinutes: 477 },
    { type: 'Amtrak', passMinutes: 579 }
  ]);
});
test('computeAmtrakTrains_ returns empty for an empty schedule', () => {
  assert.deepStrictEqual(lib.computeAmtrakTrains_([], 3), []);
});

// --- selectTrains_ ---
const SEL_OPTS = { windowMin: 30, maxCount: 3, respectHours: true, startHour: 6, endHour: 21 };
// now = 12:42 PM -> 762 minutes, hour 12
test('selectTrains_ lists trains inside the window, soonest first', () => {
  const trains = [
    { type: 'Amtrak', passMinutes: 783 }, // 13:03, +21 min
    { type: 'Amtrak', passMinutes: 771 }, // 12:51, +9 min
    { type: 'Amtrak', passMinutes: 900 }  // 15:00, out of window
  ];
  const r = lib.selectTrains_(trains, 762, 12, SEL_OPTS);
  assert.strictEqual(r.message, null);
  assert.deepStrictEqual(r.list, [
    { type: 'Amtrak', time: '12:51 PM', countdown: '9 min' },
    { type: 'Amtrak', time: '1:03 PM', countdown: '21 min' }
  ]);
});
test('selectTrains_ caps the list at maxCount', () => {
  const trains = [
    { type: 'Amtrak', passMinutes: 765 },
    { type: 'Amtrak', passMinutes: 770 },
    { type: 'Amtrak', passMinutes: 775 },
    { type: 'Amtrak', passMinutes: 780 }
  ];
  const r = lib.selectTrains_(trains, 762, 12, SEL_OPTS);
  assert.strictEqual(r.list.length, 3);
});
test('selectTrains_ messages when nothing is in the window', () => {
  const trains = [{ type: 'Amtrak', passMinutes: 900 }]; // 15:00
  const r = lib.selectTrains_(trains, 762, 12, SEL_OPTS);
  assert.deepStrictEqual(r.list, []);
  assert.strictEqual(r.message, 'No train in next 30 min — next: 3:00 PM');
});
test('selectTrains_ outside display hours shows "No train until"', () => {
  const trains = [{ type: 'Amtrak', passMinutes: 783 }];
  // now 22:00 -> 1320 minutes, hour 22, outside 6..21
  const r = lib.selectTrains_(trains, 1320, 22, SEL_OPTS);
  assert.deepStrictEqual(r.list, []);
  assert.strictEqual(r.message, 'No train until 1:03 PM');
});
test('selectTrains_ drops trains that already passed', () => {
  const trains = [
    { type: 'Amtrak', passMinutes: 700 }, // already passed
    { type: 'Amtrak', passMinutes: 771 }
  ];
  const r = lib.selectTrains_(trains, 762, 12, SEL_OPTS);
  assert.strictEqual(r.list.length, 1);
  assert.strictEqual(r.list[0].time, '12:51 PM');
});
test('selectTrains_ messages when there are no trains at all', () => {
  const r = lib.selectTrains_([], 762, 12, SEL_OPTS);
  assert.deepStrictEqual(r, { list: [], message: 'No more trains' });
});
test('selectTrains_ outside hours prefers the soonest upcoming train', () => {
  const trains = [
    { type: 'Amtrak', passMinutes: 400 },         // already passed today
    { type: 'Amtrak', passMinutes: 1375 },        // 10:55 PM, still upcoming
    { type: 'Amtrak', passMinutes: 400 + 1440 }   // tomorrow's run of the first
  ];
  // now 22:00 -> 1320 minutes, hour 22, outside the 6..21 window
  const r = lib.selectTrains_(trains, 1320, 22, SEL_OPTS);
  assert.deepStrictEqual(r.list, []);
  assert.strictEqual(r.message, 'No train until 10:55 PM');
});

// --- pbString_ ---
test('pbString_ builds a string from a byte range', () => {
  assert.strictEqual(lib.pbString_([0x68, 0x69], { start: 0, end: 2 }), 'hi');
});
test('pbString_ reads only the given sub-range', () => {
  // bytes spell "XNBROOKX"; range covers the middle 6
  assert.strictEqual(
    lib.pbString_([0x58, 0x4E, 0x42, 0x52, 0x4F, 0x4F, 0x4B, 0x58], { start: 1, end: 7 }),
    'NBROOK');
});

// --- parseTripUpdates_ (uses the committed real-feed fixture) ---
const metraFixture = fs.readFileSync(
  path.join(__dirname, 'fixtures/metra-tripupdates.bin'));
test('parseTripUpdates_ extracts the NBROOK trains from a real feed', () => {
  const trains = lib.parseTripUpdates_(metraFixture, 'NBROOK');
  assert.deepStrictEqual(trains, [
    { routeId: 'MD-N', tripId: 'MD-N_MN2623_V7_AA', arrivalEpoch: 1779071189 },
    { routeId: 'MD-N', tripId: 'MD-N_MN2620_V7_AA', arrivalEpoch: 1779070729 }
  ]);
});
test('parseTripUpdates_ returns [] for a stop with no updates', () => {
  assert.deepStrictEqual(lib.parseTripUpdates_(metraFixture, 'NOSUCHSTOP'), []);
});
test('parseTripUpdates_ handles an empty feed', () => {
  assert.deepStrictEqual(lib.parseTripUpdates_([], 'NBROOK'), []);
});

// --- decodeProtobuf_ ---
test('decodeProtobuf_ reads a single varint field', () => {
  // field 1 wire 0 (tag 0x08), value 5
  assert.deepStrictEqual(lib.decodeProtobuf_([0x08, 0x05], 0, 2), { 1: [5] });
});
test('decodeProtobuf_ reads a multi-byte varint', () => {
  // field 1, value 300 -> varint bytes 0xAC 0x02
  assert.deepStrictEqual(lib.decodeProtobuf_([0x08, 0xAC, 0x02], 0, 3), { 1: [300] });
});
test('decodeProtobuf_ reads a length-delimited field as a range', () => {
  // field 2 wire 2 (tag 0x12), length 2, then 2 bytes
  assert.deepStrictEqual(lib.decodeProtobuf_([0x12, 0x02, 0x68, 0x69], 0, 4),
    { 2: [{ start: 2, end: 4 }] });
});
test('decodeProtobuf_ collects repeated fields', () => {
  assert.deepStrictEqual(lib.decodeProtobuf_([0x08, 0x01, 0x08, 0x02], 0, 4),
    { 1: [1, 2] });
});
test('decodeProtobuf_ throws on a bad wire type', () => {
  // tag 0x0F -> field 1, wire 7 (invalid)
  assert.throws(() => lib.decodeProtobuf_([0x0F], 0, 1), /wire type/);
});

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
