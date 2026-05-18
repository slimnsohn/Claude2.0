# Wall Dashboard — Amtrak Trains Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the Northbrook trains section on the Wall Dashboard from the `AmtrakSchedule` tab that the GTFS extraction populates.

**Architecture:** Small pure functions read the `AmtrakSchedule` rows (a `HH:MM` Glenview time and a 7-char weekday bitstring per train), compute each train's Northbrook pass-through time, then filter/sort/message them for display. The pure core is unit-tested in Node; only `getAmtrakSchedule_` touches the Sheet. `getCombinedTrains_` is the seam where Metra trains will later merge in — for now it carries Amtrak only. `Dashboard.html` already renders the trains section, so it needs only a one-line tweak.

**Tech Stack:** Google Apps Script (V8), the existing `Code.gs` + `tests/pure-logic.test.js`. No new dependencies.

**Depends on:** the "Amtrak GTFS extraction" plan (`2026-05-17-wall-dashboard-amtrak-gtfs.md`) — its `refreshAmtrakSchedule` populates the `AmtrakSchedule` tab this plan reads. That plan is already implemented; its `days` column is a 7-char Mon→Sun bitstring (e.g. `1111100`).

**Scope:** This is the second half of spec build-step 3 (Amtrak trains) — the display. The trains section will show **Amtrak only** until the Metra plan lands.

**Commit policy:** Work is on the isolated, unpushed `worktree-wall-dashboard` branch. Run the commit steps as written.

**Test count note:** the suite currently stands at **56 passing** (after the GTFS extraction plan). Each TDD task below states the new running total.

---

## File Structure

| File | Change |
|---|---|
| `apps/wall-dashboard/apps-script/Code.gs` | Add trains module: time/day parsers, Northbrook offset, schedule reader, select logic, wiring |
| `apps/wall-dashboard/tests/pure-logic.test.js` | Add tests for every new pure function |
| `apps/wall-dashboard/apps-script/Dashboard.html` | One-line tweak: wrap the countdown in parentheses |

All paths below are relative to `C:\Users\slims\Desktop\Claude 2.0\.claude\worktrees\wall-dashboard\`.

### Data shapes (the contract across tasks)

- **Schedule row** (`getAmtrakSchedule_`): `{ trainNum, direction, glenviewTime, days }` — `glenviewTime` is `HH:MM`, `days` is a 7-char Mon→Sun bitstring.
- **Train** (`computeAmtrakTrains_`, `getAmtrakTrains_`): `{ type: 'Amtrak', passMinutes }` — `passMinutes` is minutes-since-midnight of the Northbrook pass; tomorrow's trains carry `passMinutes + 1440`.
- **Display item** (`selectTrains_` output, consumed by `Dashboard.html`): `{ type, time, countdown }` — `time` like `"6:43 AM"`, `countdown` like `"9 min"`.
- **Trains result** (`selectTrains_` / `getCombinedTrains_`): `{ list: <display item[]>, message: <string|null> }`.

---

## Task 1: `parseHHMM_` — parse a clock string to minutes (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the last existing test group (before the `console.log` summary line):

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.parseHHMM_ is not a function`.

- [ ] **Step 3: Implement `parseHHMM_`**

In `Code.gs`, add a new section after the GTFS refresh section (after `installAmtrakTrigger`) and before the entry point (`doGet`):

```javascript
// ---- Trains: time + day parsing (pure) -------------------------------------

/** Pure: "HH:MM" or "H:MM" -> minutes since midnight. Throws on bad input. */
function parseHHMM_(str) {
  var m = String(str).trim().match(/^(\d{1,2}):(\d{2})$/);
  if (!m) throw new Error('Bad time: ' + str);
  return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
}
```

Add `parseHHMM_` to the export footer (keep all existing entries):

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_,
    matchHour_: matchHour_,
    cachedFetch_: cachedFetch_,
    aqiInfo_: aqiInfo_,
    parseCsv_: parseCsv_,
    gtfsTimeToMinutes_: gtfsTimeToMinutes_,
    minutesToHHMM_: minutesToHHMM_,
    headsignDirection_: headsignDirection_,
    calendarBitstring_: calendarBitstring_,
    unionBits_: unionBits_,
    dateInWindow_: dateInWindow_,
    extractAmtrakRows_: extractAmtrakRows_,
    parseHHMM_: parseHHMM_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `59 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add HH:MM time parser"
```

---

## Task 2: `parseDays_` — parse a weekday bitstring (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

The `days` column is a 7-char bitstring, **Monday→Sunday** (e.g. `1111100` = Mon–Fri).
`parseDays_` converts it to day indices that match JavaScript `Date.getDay()`:
`0`=Sunday … `6`=Saturday. So bitstring position 0 (Monday) → index `1`, position 5
(Saturday) → index `6`, position 6 (Sunday) → index `0`.

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `parseHHMM_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.parseDays_ is not a function`.

- [ ] **Step 3: Implement `parseDays_`**

In `Code.gs`, add in the trains time/day section, after `parseHHMM_`:

```javascript
/**
 * Pure: a 7-char Mon..Sun weekday bitstring -> sorted day indices
 * (0=Sun..6=Sat). Position i (0=Mon) maps to index (i + 1) % 7.
 */
function parseDays_(bitstring) {
  var s = String(bitstring);
  var out = [];
  for (var i = 0; i < 7 && i < s.length; i++) {
    if (s.charAt(i) === '1') out.push((i + 1) % 7);
  }
  return out.sort(function (a, b) { return a - b; });
}
```

Add `parseDays_` to the export footer (keep all existing entries):

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_,
    matchHour_: matchHour_,
    cachedFetch_: cachedFetch_,
    aqiInfo_: aqiInfo_,
    parseCsv_: parseCsv_,
    gtfsTimeToMinutes_: gtfsTimeToMinutes_,
    minutesToHHMM_: minutesToHHMM_,
    headsignDirection_: headsignDirection_,
    calendarBitstring_: calendarBitstring_,
    unionBits_: unionBits_,
    dateInWindow_: dateInWindow_,
    extractAmtrakRows_: extractAmtrakRows_,
    parseHHMM_: parseHHMM_,
    parseDays_: parseDays_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `64 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add weekday bitstring parser"
```

---

## Task 3: `northbrookMinutes_` — Glenview time → Northbrook pass (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

Northbrook is ~3 min from Glenview on the same MD-N tracks. Northbound (toward Milwaukee) reaches Northbrook 3 min *after* Glenview; Southbound (toward Chicago) 3 min *before*.

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `parseDays_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.northbrookMinutes_ is not a function`.

- [ ] **Step 3: Implement `northbrookMinutes_`**

In `Code.gs`, add in the trains time/day section, after `parseDays_`:

```javascript
/**
 * Pure: Glenview "HH:MM" + direction -> Northbrook pass, minutes since
 * midnight. NB reaches Northbrook +3 min, SB -3 min. Wraps within 0..1439.
 */
function northbrookMinutes_(glenviewHHMM, direction) {
  var base = parseHHMM_(glenviewHHMM);
  var offset = (String(direction).trim().toUpperCase() === 'NB') ? 3 : -3;
  return ((base + offset) % 1440 + 1440) % 1440;
}
```

Add `northbrookMinutes_` to the export footer (keep all existing entries):

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_,
    matchHour_: matchHour_,
    cachedFetch_: cachedFetch_,
    aqiInfo_: aqiInfo_,
    parseCsv_: parseCsv_,
    gtfsTimeToMinutes_: gtfsTimeToMinutes_,
    minutesToHHMM_: minutesToHHMM_,
    headsignDirection_: headsignDirection_,
    calendarBitstring_: calendarBitstring_,
    unionBits_: unionBits_,
    dateInWindow_: dateInWindow_,
    extractAmtrakRows_: extractAmtrakRows_,
    parseHHMM_: parseHHMM_,
    parseDays_: parseDays_,
    northbrookMinutes_: northbrookMinutes_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `67 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add Northbrook pass-through offset"
```

---

## Task 4: `formatCountdown_` — minutes to a countdown string (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `northbrookMinutes_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.formatCountdown_ is not a function`.

- [ ] **Step 3: Implement `formatCountdown_`**

In `Code.gs`, add in the trains time/day section, after `northbrookMinutes_`:

```javascript
/** Pure: minutes -> "9 min" under an hour, "1h 9m" at/over an hour. */
function formatCountdown_(minutes) {
  if (minutes < 60) return minutes + ' min';
  return Math.floor(minutes / 60) + 'h ' + (minutes % 60) + 'm';
}
```

Add `formatCountdown_` to the export footer (keep all existing entries):

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_,
    matchHour_: matchHour_,
    cachedFetch_: cachedFetch_,
    aqiInfo_: aqiInfo_,
    parseCsv_: parseCsv_,
    gtfsTimeToMinutes_: gtfsTimeToMinutes_,
    minutesToHHMM_: minutesToHHMM_,
    headsignDirection_: headsignDirection_,
    calendarBitstring_: calendarBitstring_,
    unionBits_: unionBits_,
    dateInWindow_: dateInWindow_,
    extractAmtrakRows_: extractAmtrakRows_,
    parseHHMM_: parseHHMM_,
    parseDays_: parseDays_,
    northbrookMinutes_: northbrookMinutes_,
    formatCountdown_: formatCountdown_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `72 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add countdown formatter"
```

---

## Task 5: `formatClockTime_` — minutes to a clock string (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `formatCountdown_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.formatClockTime_ is not a function`.

- [ ] **Step 3: Implement `formatClockTime_`**

In `Code.gs`, add in the trains time/day section, after `formatCountdown_`:

```javascript
/** Pure: minutes since midnight (any value) -> "6:43 AM". Wraps mod 1440. */
function formatClockTime_(minutes) {
  var t = ((minutes % 1440) + 1440) % 1440;
  var h = Math.floor(t / 60), m = t % 60;
  var period = h < 12 ? 'AM' : 'PM';
  var h12 = h % 12;
  if (h12 === 0) h12 = 12;
  return h12 + ':' + (m < 10 ? '0' + m : '' + m) + ' ' + period;
}
```

Add `formatClockTime_` to the export footer (keep all existing entries):

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_,
    matchHour_: matchHour_,
    cachedFetch_: cachedFetch_,
    aqiInfo_: aqiInfo_,
    parseCsv_: parseCsv_,
    gtfsTimeToMinutes_: gtfsTimeToMinutes_,
    minutesToHHMM_: minutesToHHMM_,
    headsignDirection_: headsignDirection_,
    calendarBitstring_: calendarBitstring_,
    unionBits_: unionBits_,
    dateInWindow_: dateInWindow_,
    extractAmtrakRows_: extractAmtrakRows_,
    parseHHMM_: parseHHMM_,
    parseDays_: parseDays_,
    northbrookMinutes_: northbrookMinutes_,
    formatCountdown_: formatCountdown_,
    formatClockTime_: formatClockTime_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `77 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add clock-time formatter"
```

---

## Task 6: `computeAmtrakTrains_` — schedule rows to trains for a day (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `formatClockTime_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.computeAmtrakTrains_ is not a function`.

- [ ] **Step 3: Implement `computeAmtrakTrains_`**

In `Code.gs`, add in the trains time/day section, after `formatClockTime_`:

```javascript
/**
 * Pure: schedule rows + a day index (0=Sun..6=Sat) -> trains running that
 * day, each { type:'Amtrak', passMinutes }. Order follows the input rows.
 */
function computeAmtrakTrains_(rows, dayIndex) {
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    if (parseDays_(r.days).indexOf(dayIndex) < 0) continue;
    out.push({
      type: 'Amtrak',
      passMinutes: northbrookMinutes_(r.glenviewTime, r.direction)
    });
  }
  return out;
}
```

Add `computeAmtrakTrains_` to the export footer (keep all existing entries):

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_,
    matchHour_: matchHour_,
    cachedFetch_: cachedFetch_,
    aqiInfo_: aqiInfo_,
    parseCsv_: parseCsv_,
    gtfsTimeToMinutes_: gtfsTimeToMinutes_,
    minutesToHHMM_: minutesToHHMM_,
    headsignDirection_: headsignDirection_,
    calendarBitstring_: calendarBitstring_,
    unionBits_: unionBits_,
    dateInWindow_: dateInWindow_,
    extractAmtrakRows_: extractAmtrakRows_,
    parseHHMM_: parseHHMM_,
    parseDays_: parseDays_,
    northbrookMinutes_: northbrookMinutes_,
    formatCountdown_: formatCountdown_,
    formatClockTime_: formatClockTime_,
    computeAmtrakTrains_: computeAmtrakTrains_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `80 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: compute Amtrak trains for a given day"
```

---

## Task 7: `selectTrains_` — filter, sort, and message trains (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

`selectTrains_` takes an already-merged train array (Amtrak now; Metra will be
concatenated in later), the current time, and options. It returns
`{ list, message }`: a non-empty `list` of display items when trains fall in
the window, otherwise an empty list with an explanatory `message`.

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `computeAmtrakTrains_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.selectTrains_ is not a function`.

- [ ] **Step 3: Implement `selectTrains_`**

In `Code.gs`, add a new section after the trains time/day section and before the entry point (`doGet`):

```javascript
// ---- Trains: selection (pure) ----------------------------------------------

/**
 * Pure: pick the trains to show.
 * trains: [{ type, passMinutes }] (tomorrow's carry passMinutes + 1440).
 * nowMinutes / nowHour: current time. opts: { windowMin, maxCount,
 * respectHours, startHour, endHour }.
 * Returns { list:[{type,time,countdown}], message }. message is null when
 * list is non-empty.
 */
function selectTrains_(trains, nowMinutes, nowHour, opts) {
  var candidates = trains
    .filter(function (t) { return t.passMinutes >= nowMinutes; })
    .sort(function (a, b) { return a.passMinutes - b.passMinutes; });
  var next = candidates.length ? candidates[0] : null;

  function display(t) {
    return {
      type: t.type,
      time: formatClockTime_(t.passMinutes),
      countdown: formatCountdown_(t.passMinutes - nowMinutes)
    };
  }

  var outsideHours = nowHour < opts.startHour || nowHour >= opts.endHour;
  if (opts.respectHours && outsideHours) {
    // Prefer the soonest upcoming train; fall back to the earliest of all
    // (a passed train represents tomorrow's run, same clock time mod 24h).
    var allSorted = trains.slice().sort(function (a, b) { return a.passMinutes - b.passMinutes; });
    var anyNext = candidates.length ? candidates[0]
                : (allSorted.length ? allSorted[0] : null);
    return anyNext
      ? { list: [], message: 'No train until ' + formatClockTime_(anyNext.passMinutes) }
      : { list: [], message: 'No more trains' };
  }

  var windowed = candidates
    .filter(function (t) { return t.passMinutes - nowMinutes <= opts.windowMin; })
    .slice(0, opts.maxCount);
  if (windowed.length) {
    return { list: windowed.map(display), message: null };
  }
  return next
    ? { list: [], message: 'No train in next ' + opts.windowMin
        + ' min — next: ' + formatClockTime_(next.passMinutes) }
    : { list: [], message: 'No more trains' };
}
```

Add `selectTrains_` to the export footer (keep all existing entries):

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_,
    matchHour_: matchHour_,
    cachedFetch_: cachedFetch_,
    aqiInfo_: aqiInfo_,
    parseCsv_: parseCsv_,
    gtfsTimeToMinutes_: gtfsTimeToMinutes_,
    minutesToHHMM_: minutesToHHMM_,
    headsignDirection_: headsignDirection_,
    calendarBitstring_: calendarBitstring_,
    unionBits_: unionBits_,
    dateInWindow_: dateInWindow_,
    extractAmtrakRows_: extractAmtrakRows_,
    parseHHMM_: parseHHMM_,
    parseDays_: parseDays_,
    northbrookMinutes_: northbrookMinutes_,
    formatCountdown_: formatCountdown_,
    formatClockTime_: formatClockTime_,
    computeAmtrakTrains_: computeAmtrakTrains_,
    selectTrains_: selectTrains_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `86 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add train selection and messaging logic"
```

---

## Task 8: `getAmtrakSchedule_` — read the AmtrakSchedule tab

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Implement `getAmtrakSchedule_`**

In `Code.gs`, add a new section after the Config section (after `getConfig_`) and before the Amtrak GTFS extraction section:

```javascript
// ---- Amtrak schedule read --------------------------------------------------

/**
 * Read the AmtrakSchedule tab -> [{ trainNum, direction, glenviewTime, days }].
 * The tab is machine-written by refreshAmtrakSchedule. Skips blank rows.
 * Returns [] if the tab does not exist yet. Cached 1 hour.
 */
function getAmtrakSchedule_() {
  return cachedFetch_('amtrak', 3600, function () {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('AmtrakSchedule');
    if (!sheet) return [];
    var rows = sheet.getDataRange().getValues();
    var out = [];
    for (var i = 1; i < rows.length; i++) {
      var trainNum = String(rows[i][0]).trim();
      if (!trainNum) continue;
      out.push({
        trainNum: trainNum,
        direction: String(rows[i][1]).trim(),
        glenviewTime: String(rows[i][2]).trim(),
        days: String(rows[i][3]).trim()
      });
    }
    return out;
  });
}
```

This is I/O (`SpreadsheetApp`) — verified at the Task 9 checkpoint. No automated test.

- [ ] **Step 2: Run the existing tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `86 passed, 0 failed`.

- [ ] **Step 3: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: add AmtrakSchedule sheet reader"
```

---

## Task 9: Wire trains into the dashboard + Step 3 checkpoint

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/apps-script/Dashboard.html`

- [ ] **Step 1: Add `getAmtrakTrains_` and `getCombinedTrains_`**

In `Code.gs`, add a new section after the Amtrak GTFS refresh section (after `installAmtrakTrigger`) and before the trains time/day section:

```javascript
// ---- Trains: orchestration -------------------------------------------------

/**
 * All Amtrak trains relevant to `now`: today's, plus tomorrow's with
 * passMinutes shifted +1440 so overnight lookups work. tz is the script
 * timezone string.
 */
function getAmtrakTrains_(now, tz) {
  var schedule = getAmtrakSchedule_();
  // Apps Script 'u' = 1(Mon)..7(Sun); % 7 maps to 0(Sun)..6(Sat).
  var dow = parseInt(Utilities.formatDate(now, tz, 'u'), 10) % 7;
  var today = computeAmtrakTrains_(schedule, dow);
  var tomorrow = computeAmtrakTrains_(schedule, (dow + 1) % 7).map(function (t) {
    return { type: t.type, passMinutes: t.passMinutes + 1440 };
  });
  return today.concat(tomorrow);
}

/**
 * Gather every train source, merge, and run selectTrains_. Currently Amtrak
 * only; Metra will be concatenated into `all` when that plan lands.
 */
function getCombinedTrains_(now, tz, config) {
  var all = getAmtrakTrains_(now, tz);
  var nowMinutes = parseInt(Utilities.formatDate(now, tz, 'H'), 10) * 60
                 + parseInt(Utilities.formatDate(now, tz, 'm'), 10);
  var nowHour = Math.floor(nowMinutes / 60);
  return selectTrains_(all, nowMinutes, nowHour, {
    windowMin: parseInt(config.train_window_min, 10),
    maxCount: parseInt(config.max_trains, 10),
    respectHours: true,
    startHour: parseInt(config.display_start_hour, 10),
    endHour: parseInt(config.display_end_hour, 10)
  });
}
```

Note: these functions live just below the GTFS refresh code; they reference
`computeAmtrakTrains_` and `selectTrains_`, which are defined later in the
file — fine, since Apps Script hoists function declarations.

- [ ] **Step 2: Wire trains into `buildDashboardData_`**

In `Code.gs`, find the `// Air quality` try/catch block inside `buildDashboardData_`. Immediately after it (before `return data;`), add a trains block:

```javascript
  // Trains
  try {
    var combined = getCombinedTrains_(now, tz, config);
    data.trains = {
      available: combined.list.length > 0,
      list: combined.list,
      message: combined.message
    };
  } catch (err) {
    data.trains = { available: false, list: [], message: 'Trains unavailable' };
  }
```

The `data.trains` placeholder set at the top of `buildDashboardData_` (with
`message: 'Trains — coming in a later step'`) stays as the default — it is
overwritten by this block on success and is the visible fallback only if the
config read itself failed. Leave the placeholder line as-is.

- [ ] **Step 3: Wrap the countdown in parentheses in `Dashboard.html`**

In `apps/wall-dashboard/apps-script/Dashboard.html`, find this line inside the trains rendering loop:

```javascript
          row.appendChild(el('div', 'cd', t.countdown));
```

Replace it with:

```javascript
          row.appendChild(el('div', 'cd', '(' + t.countdown + ')'));
```

(The spec's dashboard format is `[type] [time] ([countdown])`; `formatCountdown_`
stays paren-free so the future phone widget can show a bare `9 min`.)

- [ ] **Step 4: Run the tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `86 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/apps-script/Dashboard.html
git commit -m "feat: wire Amtrak trains into the dashboard"
```

- [ ] **Step 6: USER CHECKPOINT — deploy and verify the trains section**

Hand off to the user. They:
1. Make sure `refreshAmtrakSchedule` has been run at least once (from the GTFS extraction plan's checkpoint) so the `AmtrakSchedule` tab is populated.
2. Re-paste the updated `Code.gs` and `Dashboard.html` into the Apps Script editor.
3. Deploy a new version of the existing deployment (Manage deployments → edit → New version).
4. Open the `/exec` URL — confirm the **NORTHBROOK TRAINS** section shows real Amtrak trains, or a sensible message ("No train in next 30 min — next: …" during the day, "No train until …" outside 6 AM–9 PM). Cross-check against amtrak.com's Hiawatha timetable for the current day.
5. Confirm weather and AQI still display correctly.

This plan is complete once the user confirms the trains section matches the schedule. Note: until the Metra plan lands, this section is Amtrak-only, so a "No train in next 30 min" message will be common.

---

## Verification Summary

After all tasks the full unit-test suite passes (Node `assert`, no dependencies):

    cd apps/wall-dashboard && node tests/pure-logic.test.js

Expected: `86 passed, 0 failed`. The new pure functions covered are `parseHHMM_`,
`parseDays_`, `northbrookMinutes_`, `formatCountdown_`, `formatClockTime_`,
`computeAmtrakTrains_`, and `selectTrains_`.

Functional verification happens at the Task 9 user checkpoint — there is no
automated test for the deployed web app or the Sheet read, by design.
