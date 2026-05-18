# Wall Dashboard — Metra Realtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add live Metra train arrivals at Northbrook to the dashboard, merged with the Amtrak trains.

**Architecture:** Metra publishes a GTFS-Realtime **protobuf** feed (no JSON). Apps Script has no protobuf library, so `Code.gs` hand-decodes the wire format: a generic decoder (`decodeProtobuf_`) plus a GTFS-RT walk (`parseTripUpdates_`) that pulls Northbrook stop-time updates. `getMetraTrains_` fetches the feed and converts each predicted arrival into the same `passMinutes` space the Amtrak trains use, so `getCombinedTrains_` simply concatenates the two sources and the existing `selectTrains_` handles merge/sort/window. The decoder and parser are pure and unit-tested — the parser against a real captured feed.

**Tech Stack:** Google Apps Script (V8) — `UrlFetchApp`. The existing `Code.gs` + `tests/pure-logic.test.js`. No new dependencies.

**Depends on:** the Amtrak trains display plan (`getCombinedTrains_`, `selectTrains_` exist). The Metra deep dive is already done — see `apps/wall-dashboard/docs/api-notes.md` and the committed fixture `apps/wall-dashboard/tests/fixtures/metra-tripupdates.bin`.

**Scope:** spec build-step 5 (Metra realtime). After this, the dashboard's trains section is fully complete (Metra + Amtrak). The phone widget and OLED polish remain separate plans.

**Verified GTFS-RT facts (from the deep dive — see `docs/api-notes.md`):**
- Feed: `GET https://gtfspublic.metrarr.com/gtfs/public/tripupdates?api_token=<TOKEN>` → protobuf bytes.
- Northbrook `stop_id` is `NBROOK`. The feed carries all Metra lines; filter to that stop.
- Field numbers: `FeedMessage`{1=header,2=entity}, `FeedEntity`{1=id,3=trip_update}, `TripUpdate`{1=trip,2=stop_time_update}, `TripDescriptor`{1=trip_id,5=route_id}, `StopTimeUpdate`{2=arrival,3=departure,4=stop_id}, `StopTimeEvent`{2=time}.
- `departure` is often absent; use `arrival`, fall back to `departure`. Time is a Unix epoch (seconds), which fits a JS `Number`.
- Wire types: 0 = varint, 2 = length-delimited, 1 = 64-bit, 5 = 32-bit. Tag = `(field << 3) | wire`.

**Commit policy:** Work is on the isolated, unpushed `worktree-wall-dashboard` branch. Run the commit steps as written.

**Test count note:** the suite currently stands at **87 passing**. Each TDD task states the new running total.

---

## File Structure

| File | Change |
|---|---|
| `apps/wall-dashboard/apps-script/Code.gs` | Add a Metra section: protobuf decoder, GTFS-RT parser, `getMetraTrains_`; modify `getCombinedTrains_` to merge Metra |
| `apps/wall-dashboard/tests/pure-logic.test.js` | Add tests for the decoder, parser, and time conversion |
| `apps/wall-dashboard/docs/sheet-setup.md` | Fill in the `metra_stop_id` value and note the token |

The test fixture `apps/wall-dashboard/tests/fixtures/metra-tripupdates.bin` (a real
captured feed) already exists and is committed. The harness already requires
Node's `fs` and `path`.

All paths below are relative to `C:\Users\slims\Desktop\Claude 2.0\.claude\worktrees\wall-dashboard\`.

### Data shapes (the contract across tasks)

- **Decoded protobuf** (`decodeProtobuf_`): `{ fieldNumber: [values] }`. A varint value is a `Number`; a length-delimited value is a `{ start, end }` range into the same `bytes`.
- **Parsed train** (`parseTripUpdates_` output): `{ routeId, tripId, arrivalEpoch }`.
- **Metra train** (`getMetraTrains_` output): `{ type: 'Metra', passMinutes }` — same shape the Amtrak trains use, so `selectTrains_` treats both uniformly.

---

## Task 1: `decodeProtobuf_` — generic protobuf wire decoder (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the last existing test group (before the `console.log` summary line):

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.decodeProtobuf_ is not a function`.

- [ ] **Step 3: Implement `decodeProtobuf_`**

In `Code.gs`, add a new section after the trains selection section (after `selectTrains_`) and before the data-assembly section (`buildDashboardData_`):

```javascript
// ---- Metra GTFS-Realtime (pure protobuf decoding) --------------------------

/**
 * Pure: generic protobuf wire-format decoder.
 * Returns { fieldNumber: [values] }. A varint value is a Number; a
 * length-delimited value is a { start, end } range into the same `bytes`
 * (sub-messages decode in place, no copying). 64-bit / 32-bit fields skipped.
 * `bytes` may be a Node Buffer, a Uint8Array, or a (possibly signed) byte
 * array — `& 0xff` normalizes each byte.
 */
function decodeProtobuf_(bytes, start, end) {
  var pos = start;
  var fields = {};
  function readVarint() {
    var result = 0, shift = 0, b;
    do {
      b = bytes[pos++] & 0xff;
      result += (b & 0x7f) * Math.pow(2, shift);
      shift += 7;
    } while (b & 0x80);
    return result;
  }
  while (pos < end) {
    var tag = readVarint();
    var field = Math.floor(tag / 8), wire = tag & 7;
    if (wire === 0) {
      (fields[field] || (fields[field] = [])).push(readVarint());
    } else if (wire === 2) {
      var len = readVarint();
      (fields[field] || (fields[field] = [])).push({ start: pos, end: pos + len });
      pos += len;
    } else if (wire === 1) {
      pos += 8;
    } else if (wire === 5) {
      pos += 4;
    } else {
      throw new Error('Bad protobuf wire type: ' + wire);
    }
  }
  return fields;
}
```

Add `decodeProtobuf_` to the export footer (keep all existing entries):

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
    selectTrains_: selectTrains_,
    decodeProtobuf_: decodeProtobuf_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `92 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add generic protobuf wire decoder"
```

---

## Task 2: `pbString_` — byte range to string (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `decodeProtobuf_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.pbString_ is not a function`.

- [ ] **Step 3: Implement `pbString_`**

In `Code.gs`, add in the Metra section, after `decodeProtobuf_`:

```javascript
/**
 * Pure: a { start, end } byte range -> string. GTFS-RT ids (route_id,
 * trip_id, stop_id) are ASCII, so a per-byte char code is sufficient.
 */
function pbString_(bytes, range) {
  var s = '';
  for (var i = range.start; i < range.end; i++) {
    s += String.fromCharCode(bytes[i] & 0xff);
  }
  return s;
}
```

Add `pbString_` to the export footer (keep all existing entries):

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
    selectTrains_: selectTrains_,
    decodeProtobuf_: decodeProtobuf_,
    pbString_: pbString_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `94 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add protobuf byte-range string reader"
```

---

## Task 3: `parseTripUpdates_` — GTFS-RT feed to Northbrook trains (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

This task walks the GTFS-RT message tree and is tested against the real
captured feed `tests/fixtures/metra-tripupdates.bin`, which contains exactly
two Northbrook trains.

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `pbString_` tests:

```javascript
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
```

(The harness already declares `fs` and `path` at the top of the file — reuse them.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.parseTripUpdates_ is not a function`.

- [ ] **Step 3: Implement `stopTimeEventTime_` and `parseTripUpdates_`**

In `Code.gs`, add in the Metra section, after `pbString_`:

```javascript
/** Internal: StopTimeEvent.time (field 2) from an arrival/departure field. */
function stopTimeEventTime_(bytes, eventField) {
  if (!eventField) return null;
  var ev = decodeProtobuf_(bytes, eventField[0].start, eventField[0].end);
  return ev[2] ? ev[2][0] : null;
}

/**
 * Pure: decode a GTFS-Realtime tripUpdates feed (raw bytes) -> a list of
 * { routeId, tripId, arrivalEpoch } for every stop_time_update whose stop_id
 * equals `stopId`. Uses the arrival time, falling back to departure.
 */
function parseTripUpdates_(bytes, stopId) {
  var root = decodeProtobuf_(bytes, 0, bytes.length);
  var entities = root[2] || [];                       // FeedMessage.entity
  var out = [];
  for (var i = 0; i < entities.length; i++) {
    var e = decodeProtobuf_(bytes, entities[i].start, entities[i].end);
    if (!e[3]) continue;                              // FeedEntity.trip_update
    var tu = decodeProtobuf_(bytes, e[3][0].start, e[3][0].end);
    var routeId = '', tripId = '';
    if (tu[1]) {                                      // TripUpdate.trip
      var trip = decodeProtobuf_(bytes, tu[1][0].start, tu[1][0].end);
      if (trip[1]) tripId = pbString_(bytes, trip[1][0]);   // trip_id
      if (trip[5]) routeId = pbString_(bytes, trip[5][0]);  // route_id
    }
    var stus = tu[2] || [];                           // TripUpdate.stop_time_update
    for (var j = 0; j < stus.length; j++) {
      var stu = decodeProtobuf_(bytes, stus[j].start, stus[j].end);
      if (!stu[4] || pbString_(bytes, stu[4][0]) !== stopId) continue; // stop_id
      var epoch = stopTimeEventTime_(bytes, stu[2]);  // arrival
      if (epoch == null) epoch = stopTimeEventTime_(bytes, stu[3]); // departure
      if (epoch == null) continue;
      out.push({ routeId: routeId, tripId: tripId, arrivalEpoch: epoch });
    }
  }
  return out;
}
```

Add `parseTripUpdates_` to the export footer (keep all existing entries — `stopTimeEventTime_` stays internal):

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
    selectTrains_: selectTrains_,
    decodeProtobuf_: decodeProtobuf_,
    pbString_: pbString_,
    parseTripUpdates_: parseTripUpdates_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `97 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: parse Metra GTFS-RT feed for Northbrook trains"
```

---

## Task 4: `metraPassMinutes_` — arrival epoch to passMinutes (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

Metra arrivals are absolute Unix epochs. Converting to a delta from now and
adding `nowMinutes` lands them in the exact `passMinutes` space the Amtrak
trains use (a train tomorrow naturally exceeds 1440; a passed train falls
below `nowMinutes` and is filtered out by `selectTrains_`).

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `parseTripUpdates_` tests:

```javascript
// --- metraPassMinutes_ ---
test('metraPassMinutes_ for an upcoming train', () => {
  // arrival 1320 s (22 min) after now
  assert.strictEqual(lib.metraPassMinutes_(1779071320, 1779070000, 1260), 1282);
});
test('metraPassMinutes_ for a train arriving now', () => {
  assert.strictEqual(lib.metraPassMinutes_(1779070000, 1779070000, 1260), 1260);
});
test('metraPassMinutes_ for a train that already passed', () => {
  // arrival 600 s (10 min) before now
  assert.strictEqual(lib.metraPassMinutes_(1779069400, 1779070000, 1260), 1250);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.metraPassMinutes_ is not a function`.

- [ ] **Step 3: Implement `metraPassMinutes_`**

In `Code.gs`, add in the Metra section, after `parseTripUpdates_`:

```javascript
/**
 * Pure: a train's arrival epoch (seconds) -> passMinutes, in the same
 * minutes-since-midnight space the Amtrak trains use.
 */
function metraPassMinutes_(arrivalEpoch, nowEpochSec, nowMinutes) {
  return nowMinutes + Math.round((arrivalEpoch - nowEpochSec) / 60);
}
```

Add `metraPassMinutes_` to the export footer (keep all existing entries):

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
    selectTrains_: selectTrains_,
    decodeProtobuf_: decodeProtobuf_,
    pbString_: pbString_,
    parseTripUpdates_: parseTripUpdates_,
    metraPassMinutes_: metraPassMinutes_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `100 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add Metra arrival-to-passMinutes conversion"
```

---

## Task 5: `getMetraTrains_` — fetch and decode the live feed

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/docs/sheet-setup.md`

- [ ] **Step 1: Implement `getMetraTrains_`**

In `Code.gs`, add in the Metra section, after `metraPassMinutes_`:

```javascript
/**
 * Fetch the Metra realtime feed and return [{ type:'Metra', passMinutes }]
 * for trains approaching the configured stop. Cached 45 s. Returns [] when
 * Metra is not configured (no token / stop id in the Config tab).
 */
function getMetraTrains_(now, tz, config) {
  if (!config.metra_api_token || !config.metra_stop_id) return [];
  var parsed = cachedFetch_('metra', 45, function () {
    var url = 'https://gtfspublic.metrarr.com/gtfs/public/tripupdates?api_token='
      + encodeURIComponent(config.metra_api_token);
    var resp = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (resp.getResponseCode() !== 200) {
      throw new Error('Metra feed returned ' + resp.getResponseCode());
    }
    return parseTripUpdates_(resp.getBlob().getBytes(), config.metra_stop_id);
  });
  var nowEpochSec = Math.floor(now.getTime() / 1000);
  var nowMinutes = parseInt(Utilities.formatDate(now, tz, 'H'), 10) * 60
                 + parseInt(Utilities.formatDate(now, tz, 'm'), 10);
  return parsed.map(function (t) {
    return {
      type: 'Metra',
      passMinutes: metraPassMinutes_(t.arrivalEpoch, nowEpochSec, nowMinutes)
    };
  });
}
```

This is I/O (`UrlFetchApp`) — verified at the Task 6 checkpoint. No automated test.

- [ ] **Step 2: Update `sheet-setup.md` for the Metra Config values**

In `apps/wall-dashboard/docs/sheet-setup.md`, in the `Config` table, change the
`metra_api_token` and `metra_stop_id` rows:
- `metra_api_token` value: change `(leave blank until the Metra step)` to
  `(paste your Metra GTFS API token)`
- `metra_stop_id` value: change `(leave blank until the Metra step)` to `NBROOK`

- [ ] **Step 3: Run the existing tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `100 passed, 0 failed`.

- [ ] **Step 4: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/docs/sheet-setup.md
git commit -m "feat: add Metra realtime feed fetch"
```

---

## Task 6: Merge Metra into `getCombinedTrains_` + checkpoint

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Replace `getCombinedTrains_` to merge the Metra trains**

In `Code.gs`, replace the entire existing `getCombinedTrains_` function with:

```javascript
/**
 * Gather every train source (Amtrak + Metra), merge, and run selectTrains_.
 * A Metra feed failure must never drop the Amtrak trains.
 */
function getCombinedTrains_(now, tz, config) {
  var all = getAmtrakTrains_(now, tz);
  try {
    all = all.concat(getMetraTrains_(now, tz, config));
  } catch (err) {
    // Metra unavailable — fall through with Amtrak only.
  }
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

(The merge is the only change: `selectTrains_` already sorts and windows the
combined list, and `Metra`/`Amtrak` display items differ only by their `type`
label, which `Dashboard.html` already renders.)

- [ ] **Step 2: Run the tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `100 passed, 0 failed`.

- [ ] **Step 3: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: merge Metra trains into the combined trains list"
```

- [ ] **Step 4: USER CHECKPOINT — add the token, deploy, and verify**

Hand off to the user. They:
1. In the Sheet's `Config` tab, paste the Metra GTFS API token into the
   `metra_api_token` value cell, and set `metra_stop_id` to `NBROOK`.
2. Re-paste the updated `Code.gs` into the Apps Script editor.
3. Deploy a new version of the existing deployment (Manage deployments → edit → New version).
4. Open the `/exec` URL — confirm the **NORTHBROOK TRAINS** section now shows
   `Metra` entries (when trains are in service) merged and time-sorted with any
   `Amtrak` entries. Metra realtime only lists in-service trains, so an empty
   Metra set late at night is normal.
5. Optionally, in the editor, run a quick check: `Logger.log(getMetraTrains_(new Date(), 'America/Chicago', getConfig_()))` and confirm it logs Metra trains (or `[]` if none are running).
6. Confirm weather and AQI still display correctly.

This plan is complete once the user confirms Metra trains appear in the trains
section. The trains feature (Amtrak + Metra) is then fully done.

---

## Verification Summary

After all tasks the full unit-test suite passes (Node `assert`, no dependencies):

    cd apps/wall-dashboard && node tests/pure-logic.test.js

Expected: `100 passed, 0 failed`. New pure functions covered: `decodeProtobuf_`,
`pbString_`, `parseTripUpdates_` (against the real captured feed fixture), and
`metraPassMinutes_`.

Functional verification of `getMetraTrains_` and the merged
`getCombinedTrains_` happens at the Task 6 user checkpoint — there is no
automated test for the live feed fetch, by design.
