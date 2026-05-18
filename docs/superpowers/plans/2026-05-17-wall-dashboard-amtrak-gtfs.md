# Wall Dashboard — Amtrak GTFS Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-populate the `AmtrakSchedule` Sheet tab every week by extracting the real Hiawatha + Empire Builder trains through Glenview from Amtrak's official GTFS feed.

**Architecture:** A weekly Apps Script time-trigger calls `refreshAmtrakSchedule` (public, so it can be a trigger handler), which downloads `GTFS.zip`, unzips it, parses four CSVs, joins routes → trips → Glenview stop times → service calendars, and rewrites the `AmtrakSchedule` tab. The join logic and every parser are pure functions, unit-tested in Node; only `refreshAmtrakSchedule` and `installAmtrakTrigger` touch the network and Sheet.

**Tech Stack:** Google Apps Script (V8) — `UrlFetchApp`, `Utilities.unzip`, `SpreadsheetApp`, `ScriptApp` triggers. The existing `Code.gs` + `tests/pure-logic.test.js`. No new dependencies.

**Scope:** This is the first half of spec build-step 3 (Amtrak trains) — the data pipeline. It produces a populated `AmtrakSchedule` tab. The second half (reading that tab and rendering the trains section) is the separate "Amtrak trains display" plan, built next.

**GTFS facts (verified 2026-05-17 against the live feed):**
- Feed: `https://content.amtrak.com/content/gtfs/GTFS.zip` — ~18 MB, no auth.
- `routes.txt`: `route_id,agency_id,route_short_name,route_long_name,...` — Hiawatha is `route_long_name` "Hiawatha Service", Empire Builder is "Empire Builder".
- `trips.txt`: `route_id,service_id,trip_id,trip_short_name,direction_id,shape_id,trip_headsign` — `trip_short_name` is the train number; `trip_headsign` is "Chicago" / "Milwaukee" / "Seattle" / "Portland".
- `stop_times.txt`: `trip_id,arrival_time,departure_time,stop_id,stop_sequence,...` — Glenview `stop_id` is `GLN`; `departure_time` is `H:MM:SS` and **can exceed 24h** (multi-day Empire Builder, e.g. `65:12:00`).
- `calendar.txt`: `service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date` — weekday flags `1`/`0`, dates `YYYYMMDD`. There is no `calendar_dates.txt`.
- A train number recurs under several `service_id`s with different date windows.

**Commit policy:** Work is on the isolated, unpushed `worktree-wall-dashboard` branch. Run the commit steps as written.

**Test count note:** the suite currently stands at **30 passing**. Each TDD task states the new running total.

---

## File Structure

| File | Change |
|---|---|
| `apps/wall-dashboard/apps-script/Code.gs` | Rename `bootstrapNwsUrl_`→`bootstrapNwsUrl`; add the GTFS parsers, the `extractAmtrakRows_` join, `refreshAmtrakSchedule`, `installAmtrakTrigger` |
| `apps/wall-dashboard/tests/pure-logic.test.js` | Add tests for every new pure function |

All paths below are relative to `C:\Users\slims\Desktop\Claude 2.0\.claude\worktrees\wall-dashboard\`.

### Data shapes (the contract across tasks)

- **CSV table** (`parseCsv_`): array of plain objects, one per row, keyed by header name.
- **GTFS tables** (input to `extractAmtrakRows_`): `{ routes, trips, stopTimes, calendar }` — each a CSV table.
- **Extracted row** (`extractAmtrakRows_` output, one per train+direction): `{ trainNum, direction, glenviewTime, days }` — `direction` is `'NB'`/`'SB'`, `glenviewTime` is `'HH:MM'` 24h, `days` is a 7-char Mon→Sun bitstring.
- **`AmtrakSchedule` tab**: header `train_num | direction | glenview_time | days`, then one row per extracted row. The whole range is formatted as plain text so bitstrings and times are not coerced to numbers.

### Apps Script private-function rule

A function whose name ends with `_` is **private** in Apps Script: it cannot appear in the editor Run menu and cannot be a trigger handler. Internal helpers keep the `_`. Functions the user runs manually or that a trigger calls — `bootstrapNwsUrl`, `refreshAmtrakSchedule`, `installAmtrakTrigger` — must have **no** trailing underscore.

---

## Task 1: Fix the `bootstrapNwsUrl_` private-function bug

`bootstrapNwsUrl_` (added in the weather plan) is meant to be run once from the editor, but its trailing underscore makes it private and invisible in the Run menu. Rename it.

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Rename the function definition**

In `Code.gs`, change the function declaration:
- from: `function bootstrapNwsUrl_() {`
- to: `function bootstrapNwsUrl() {`

- [ ] **Step 2: Update the reference in `getWeather_`'s error message**

In `Code.gs`, `getWeather_` throws an error mentioning the helper. Change that message:
- from: `throw new Error('nws_forecast_hourly_url not set — run bootstrapNwsUrl_ first');`
- to: `throw new Error('nws_forecast_hourly_url not set — run bootstrapNwsUrl first');`

Search `Code.gs` for any other occurrence of `bootstrapNwsUrl_` and update it the same way. There must be no `bootstrapNwsUrl_` (with underscore) left.

- [ ] **Step 3: Run the tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `30 passed, 0 failed`.

- [ ] **Step 4: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "fix: rename bootstrapNwsUrl so the editor Run menu can see it"
```

---

## Task 2: `parseCsv_` — CSV text to row objects (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the last existing test group (before the `console.log` summary line):

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.parseCsv_ is not a function`.

- [ ] **Step 3: Implement `parseCsv_`**

In `Code.gs`, add a new section after the `errorPage_` function and before the entry point (`doGet`):

```javascript
// ---- Amtrak GTFS extraction (pure) -----------------------------------------

/** Pure: split one CSV line into fields, honoring "quoted" fields. */
function splitCsvLine_(line) {
  var out = [], cur = '', inQ = false;
  for (var i = 0; i < line.length; i++) {
    var c = line.charAt(i);
    if (inQ) {
      if (c === '"') {
        if (line.charAt(i + 1) === '"') { cur += '"'; i++; }
        else inQ = false;
      } else { cur += c; }
    } else if (c === '"') {
      inQ = true;
    } else if (c === ',') {
      out.push(cur); cur = '';
    } else {
      cur += c;
    }
  }
  out.push(cur);
  return out;
}

/** Pure: CSV text -> array of objects keyed by the header row. */
function parseCsv_(text) {
  var lines = String(text).split(/\r?\n/);
  if (lines.length < 2) return [];
  var headers = splitCsvLine_(lines[0]);
  var rows = [];
  for (var i = 1; i < lines.length; i++) {
    if (lines[i] === '') continue;
    var fields = splitCsvLine_(lines[i]);
    var obj = {};
    for (var j = 0; j < headers.length; j++) {
      obj[headers[j]] = j < fields.length ? fields[j] : '';
    }
    rows.push(obj);
  }
  return rows;
}
```

Add `parseCsv_` to the export footer (keep all existing entries):

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
    parseCsv_: parseCsv_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `34 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add CSV parser"
```

---

## Task 3: `gtfsTimeToMinutes_` — GTFS time to minutes (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

GTFS `departure_time` is `H:MM:SS` and may exceed 24h for multi-day trips. We want minutes-since-midnight, wrapped into 0..1439.

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `parseCsv_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.gtfsTimeToMinutes_ is not a function`.

- [ ] **Step 3: Implement `gtfsTimeToMinutes_`**

In `Code.gs`, add in the GTFS extraction section, after `parseCsv_`:

```javascript
/** Pure: GTFS "H:MM:SS" (hours may exceed 24) -> minutes since midnight 0..1439. */
function gtfsTimeToMinutes_(str) {
  var m = String(str).trim().match(/^(\d{1,3}):(\d{2}):(\d{2})$/);
  if (!m) throw new Error('Bad GTFS time: ' + str);
  var total = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
  return ((total % 1440) + 1440) % 1440;
}
```

Add `gtfsTimeToMinutes_` to the export footer (keep all existing entries):

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
    gtfsTimeToMinutes_: gtfsTimeToMinutes_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `38 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add GTFS time parser"
```

---

## Task 4: `minutesToHHMM_` — minutes to a 24h clock string (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `gtfsTimeToMinutes_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.minutesToHHMM_ is not a function`.

- [ ] **Step 3: Implement `minutesToHHMM_`**

In `Code.gs`, add in the GTFS extraction section, after `gtfsTimeToMinutes_`:

```javascript
/** Pure: minutes since midnight -> "HH:MM" 24-hour, zero-padded. */
function minutesToHHMM_(minutes) {
  var t = ((minutes % 1440) + 1440) % 1440;
  var h = Math.floor(t / 60), m = t % 60;
  return (h < 10 ? '0' + h : '' + h) + ':' + (m < 10 ? '0' + m : '' + m);
}
```

Add `minutesToHHMM_` to the export footer (keep all existing entries):

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
    minutesToHHMM_: minutesToHHMM_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `41 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add minutes-to-HHMM formatter"
```

---

## Task 5: `headsignDirection_` — headsign to NB/SB (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

A train heading toward Chicago passes Northbrook Southbound; anything else (Milwaukee, Seattle, Portland) is Northbound.

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `minutesToHHMM_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.headsignDirection_ is not a function`.

- [ ] **Step 3: Implement `headsignDirection_`**

In `Code.gs`, add in the GTFS extraction section, after `minutesToHHMM_`:

```javascript
/** Pure: GTFS trip_headsign -> 'SB' toward Chicago, else 'NB'. */
function headsignDirection_(headsign) {
  return String(headsign).trim() === 'Chicago' ? 'SB' : 'NB';
}
```

Add `headsignDirection_` to the export footer (keep all existing entries):

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
    headsignDirection_: headsignDirection_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `44 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add headsign-to-direction mapping"
```

---

## Task 6: `calendarBitstring_` + `unionBits_` — weekday bitstrings (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

A weekday bitstring is 7 chars, Monday→Sunday.

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `headsignDirection_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.calendarBitstring_ is not a function`.

- [ ] **Step 3: Implement `calendarBitstring_` and `unionBits_`**

In `Code.gs`, add in the GTFS extraction section, after `headsignDirection_`:

```javascript
/** Pure: a calendar.txt row -> 7-char Mon..Sun bitstring. */
function calendarBitstring_(row) {
  var days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday',
              'saturday', 'sunday'];
  return days.map(function (d) {
    return String(row[d]).trim() === '1' ? '1' : '0';
  }).join('');
}

/** Pure: bitwise-OR two 7-char weekday bitstrings. */
function unionBits_(a, b) {
  var out = '';
  for (var i = 0; i < 7; i++) {
    out += (a.charAt(i) === '1' || b.charAt(i) === '1') ? '1' : '0';
  }
  return out;
}
```

Add both to the export footer (keep all existing entries):

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
    unionBits_: unionBits_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `48 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add weekday bitstring helpers"
```

---

## Task 7: `dateInWindow_` — service-window date check (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

GTFS dates are `YYYYMMDD` strings, so a lexicographic compare is also a date compare.

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `unionBits_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.dateInWindow_ is not a function`.

- [ ] **Step 3: Implement `dateInWindow_`**

In `Code.gs`, add in the GTFS extraction section, after `unionBits_`:

```javascript
/** Pure: is YYYYMMDD `today` within [start, end] inclusive? */
function dateInWindow_(today, start, end) {
  return today >= start && today <= end;
}
```

Add `dateInWindow_` to the export footer (keep all existing entries):

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
    dateInWindow_: dateInWindow_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `51 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add service-window date check"
```

---

## Task 8: `extractAmtrakRows_` — the GTFS join (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

This is the heart of the extraction: given the four parsed GTFS tables and today's
`YYYYMMDD`, produce one row per (train number, direction), sorted by Glenview time.

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `dateInWindow_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.extractAmtrakRows_ is not a function`.

- [ ] **Step 3: Implement `extractAmtrakRows_`**

In `Code.gs`, add in the GTFS extraction section, after `dateInWindow_`:

```javascript
/**
 * Pure: GTFS tables { routes, trips, stopTimes, calendar } + today's YYYYMMDD
 * -> [{ trainNum, direction, glenviewTime, days }], one per (train, direction),
 * sorted by Glenview time. Keeps only Hiawatha/Empire Builder trips that stop
 * at Glenview under a service active today; unions weekday bits per train.
 */
function extractAmtrakRows_(tables, todayYmd) {
  var WANTED = { 'Hiawatha Service': true, 'Empire Builder': true };
  var routeIds = {};
  tables.routes.forEach(function (r) {
    if (WANTED[String(r.route_long_name).trim()]) routeIds[r.route_id] = true;
  });

  var calById = {};
  tables.calendar.forEach(function (c) { calById[c.service_id] = c; });

  var glnDeparture = {};
  tables.stopTimes.forEach(function (st) {
    if (String(st.stop_id).trim() === 'GLN') {
      glnDeparture[st.trip_id] = st.departure_time;
    }
  });

  var byKey = {};
  tables.trips.forEach(function (t) {
    if (!routeIds[t.route_id]) return;
    var cal = calById[t.service_id];
    if (!cal) return;
    if (!dateInWindow_(todayYmd, cal.start_date, cal.end_date)) return;
    var departure = glnDeparture[t.trip_id];
    if (departure == null) return;

    var trainNum = String(t.trip_short_name).trim();
    var direction = headsignDirection_(t.trip_headsign);
    var bits = calendarBitstring_(cal);
    var key = trainNum + '|' + direction;
    if (byKey[key]) {
      byKey[key].days = unionBits_(byKey[key].days, bits);
    } else {
      byKey[key] = {
        trainNum: trainNum,
        direction: direction,
        glenviewMinutes: gtfsTimeToMinutes_(departure),
        days: bits
      };
    }
  });

  var rows = [];
  for (var k in byKey) {
    if (byKey.hasOwnProperty(k)) rows.push(byKey[k]);
  }
  rows.sort(function (a, b) { return a.glenviewMinutes - b.glenviewMinutes; });
  return rows.map(function (r) {
    return {
      trainNum: r.trainNum,
      direction: r.direction,
      glenviewTime: minutesToHHMM_(r.glenviewMinutes),
      days: r.days
    };
  });
}
```

Add `extractAmtrakRows_` to the export footer (keep all existing entries):

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
    extractAmtrakRows_: extractAmtrakRows_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `54 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add GTFS-to-schedule join"
```

---

## Task 9: `refreshAmtrakSchedule` — download GTFS and write the tab

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Implement `refreshAmtrakSchedule`**

In `Code.gs`, add a new section after the GTFS extraction section and before the entry point (`doGet`):

```javascript
// ---- Amtrak GTFS refresh (I/O) ---------------------------------------------

/**
 * Download Amtrak's GTFS feed, extract the Glenview Hiawatha + Empire Builder
 * trains, and rewrite the AmtrakSchedule tab. Public (no trailing underscore)
 * so it can be run from the editor and used as a weekly trigger handler.
 */
function refreshAmtrakSchedule() {
  var resp = UrlFetchApp.fetch('https://content.amtrak.com/content/gtfs/GTFS.zip', {
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error('GTFS download returned ' + resp.getResponseCode());
  }
  var need = { 'routes.txt': 1, 'trips.txt': 1, 'stop_times.txt': 1, 'calendar.txt': 1 };
  var raw = {};
  Utilities.unzip(resp.getBlob()).forEach(function (f) {
    var base = f.getName().split('/').pop();
    if (need[base]) raw[base] = f.getDataAsString();
  });
  ['routes.txt', 'trips.txt', 'stop_times.txt', 'calendar.txt'].forEach(function (n) {
    if (raw[n] == null) throw new Error('GTFS feed missing ' + n);
  });

  var tables = {
    routes: parseCsv_(raw['routes.txt']),
    trips: parseCsv_(raw['trips.txt']),
    stopTimes: parseCsv_(raw['stop_times.txt']),
    calendar: parseCsv_(raw['calendar.txt'])
  };
  var today = Utilities.formatDate(new Date(), 'America/Chicago', 'yyyyMMdd');
  var extracted = extractAmtrakRows_(tables, today);

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('AmtrakSchedule');
  if (!sheet) sheet = ss.insertSheet('AmtrakSchedule');
  sheet.clearContents();

  var values = [['train_num', 'direction', 'glenview_time', 'days']];
  extracted.forEach(function (r) {
    values.push([r.trainNum, r.direction, r.glenviewTime, r.days]);
  });
  // Plain-text format first, so "06:43" and bitstrings like "0000011" are not
  // coerced to a time or a number.
  var range = sheet.getRange(1, 1, values.length, 4);
  range.setNumberFormat('@');
  range.setValues(values);

  Logger.log('AmtrakSchedule refreshed: ' + extracted.length + ' trains for ' + today);
}
```

This is I/O — verified at the Task 10 checkpoint. No automated test.

- [ ] **Step 2: Run the existing tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `54 passed, 0 failed`.

- [ ] **Step 3: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: add Amtrak GTFS refresh"
```

---

## Task 10: `installAmtrakTrigger` + checkpoint

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Implement `installAmtrakTrigger`**

In `Code.gs`, add in the GTFS refresh section, after `refreshAmtrakSchedule`:

```javascript
/**
 * Install (or re-install) the weekly trigger that runs refreshAmtrakSchedule.
 * Public so it can be run once from the editor. Idempotent — clears any
 * existing refreshAmtrakSchedule trigger first.
 */
function installAmtrakTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'refreshAmtrakSchedule') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('refreshAmtrakSchedule')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.MONDAY)
    .atHour(3)
    .create();
  Logger.log('Weekly refreshAmtrakSchedule trigger installed (Mondays ~3 AM).');
}
```

This is I/O — verified at the checkpoint below. No automated test.

- [ ] **Step 2: Run the existing tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `54 passed, 0 failed`.

- [ ] **Step 3: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: add weekly Amtrak refresh trigger installer"
```

- [ ] **Step 4: USER CHECKPOINT — run the refresh and verify the tab fills**

Hand off to the user. They:
1. Re-paste the updated `Code.gs` into the Apps Script editor.
2. In the editor, select `refreshAmtrakSchedule` from the function dropdown and click Run. Authorize the new permissions when prompted (external fetch + Sheet write).
3. Open the Sheet's `AmtrakSchedule` tab — confirm it now lists real Amtrak trains: `train_num`, `direction` (`NB`/`SB`), `glenview_time` (`HH:MM`), `days` (a 7-character bitstring like `1111100`). Spot-check a couple against amtrak.com's Hiawatha timetable.
4. Check the execution log shows `AmtrakSchedule refreshed: N trains` with a sensible N (roughly 14–30).
5. Select `installAmtrakTrigger` from the dropdown and Run it once to schedule the weekly auto-refresh. Confirm under Triggers (clock icon) that a weekly `refreshAmtrakSchedule` trigger now exists.

This plan is complete once the user confirms the `AmtrakSchedule` tab is populated and the weekly trigger is installed. The next plan ("Amtrak trains display") reads this tab and renders the trains section.

---

## Verification Summary

After all tasks the full unit-test suite passes (Node `assert`, no dependencies):

    cd apps/wall-dashboard && node tests/pure-logic.test.js

Expected: `54 passed, 0 failed`. New pure functions covered: `parseCsv_`,
`gtfsTimeToMinutes_`, `minutesToHHMM_`, `headsignDirection_`,
`calendarBitstring_`, `unionBits_`, `dateInWindow_`, `extractAmtrakRows_`.

Functional verification of `refreshAmtrakSchedule` and `installAmtrakTrigger`
happens at the Task 10 user checkpoint — there is no automated test for the
GTFS download, unzip, or Sheet write, by design.
