# Wall Dashboard — Skeleton & Weather Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a working Google Apps Script wall dashboard that renders an OLED-safe TV page through a Fire Stick, then make it show live Glenview weather.

**Architecture:** A single Apps Script web app attached to a Google Sheet. `Code.gs` holds routing, config/weather I/O, caching, and rendering; pure helper logic lives in the same file behind a guarded `module.exports` footer so it can be unit-tested in Node. `doGet` builds a plain `data` object, injects it as JSON into `Dashboard.html`, and client JS renders it — so the HTML never changes once written. Claude produces all files in a local repo; the user creates the Sheet and deploys.

**Tech Stack:** Google Apps Script (V8 runtime), HTML/CSS/vanilla JS, NWS weather API, Node.js (`node:assert` + `vm`) for unit tests — no npm dependencies.

**Scope:** This plan covers spec build-steps 1 (Skeleton) and 2 (Weather) from `docs/superpowers/specs/2026-05-17-wall-dashboard-design.md`. Trains (Amtrak, Metra), the phone widget, and OLED polish are deferred to follow-up plans.

**Commit policy:** This workspace requires explicit user approval before any `git commit`. The commit steps below are real checkpoints — when executing, stage the changes and confirm with the user at each one rather than committing silently.

**Two user checkpoints:** Task 6 (skeleton renders on the TV) and Task 14 (live weather renders on the TV). At each, the user deploys and confirms before work continues.

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/wall-dashboard/CLAUDE.md` | Project rules + documented chat-widget exception |
| `apps/wall-dashboard/TODO.md` | Task tracker (manually controlled) |
| `apps/wall-dashboard/README.md` | Setup + deployment guide the user follows |
| `apps/wall-dashboard/apps-script/appsscript.json` | Apps Script manifest (timezone, web app config) |
| `apps/wall-dashboard/apps-script/Code.gs` | Routing, config/weather I/O, caching, pure helpers, rendering |
| `apps/wall-dashboard/apps-script/Dashboard.html` | TV view — OLED-safe layout, client-side render |
| `apps/wall-dashboard/docs/sheet-setup.md` | Exact Config tab contents to paste into the Sheet |
| `apps/wall-dashboard/docs/api-notes.md` | NWS + Metra quirks discovered during the build |
| `apps/wall-dashboard/tests/pure-logic.test.js` | Node test harness + tests for pure functions |

All paths below are relative to `C:\Users\slims\Desktop\Claude 2.0\`.

---

# STEP 1 — Skeleton (de-risk the display pipeline)

## Task 1: Scaffold project directory and metadata files

**Files:**
- Create: `apps/wall-dashboard/CLAUDE.md`
- Create: `apps/wall-dashboard/TODO.md`
- Create: `apps/wall-dashboard/docs/api-notes.md`

- [ ] **Step 1: Create `apps/wall-dashboard/CLAUDE.md`**

```markdown
# Wall Dashboard

Glanceable wall-mounted TV dashboard (weather + Northbrook trains) plus a phone
widget. Google Apps Script web app, mirrored to this local repo.

## Layout
- `apps-script/` — files pasted into the Apps Script editor (Code.gs, Dashboard.html, appsscript.json)
- `docs/` — Sheet setup + API notes
- `tests/` — Node unit tests for pure logic: `node tests/pure-logic.test.js`

## Rules
- API keys (Metra token) live in the Google Sheet `Config` tab, never in code.
- Pure functions stay GAS-free and are unit-tested; I/O functions are verified with Logger.log.
- Chat-widget exception: the workspace rule to embed the shared chat widget does
  NOT apply here — this is a non-interactive OLED kiosk display. Deliberate, documented.

## Deploy
See `README.md`. Always reuse the existing deployment ID so the Fire Stick URL never breaks.
```

- [ ] **Step 2: Create `apps/wall-dashboard/TODO.md`**

```markdown
# Wall Dashboard — TODO

## Now
- Step 1: deployable skeleton renders on the TV via Fire Stick.

## Next
- Step 2: live NWS weather + today/tomorrow flip.

## Later
- Amtrak trains, phone widget, Metra realtime, OLED polish (separate plans).
```

- [ ] **Step 3: Create `apps/wall-dashboard/docs/api-notes.md`**

```markdown
# API Notes

## NWS (weather.gov)
- No auth. Requires a `User-Agent` header or requests are rejected.
- `GET /points/{lat},{lon}` → `properties.forecastHourly` is the hourly URL. Cache it.
- Hourly periods include `temperature`, `probabilityOfPrecipitation.value`,
  `relativeHumidity.value`, `windSpeed` (string like "5 mph"), `shortForecast`.
- No apparent-temperature field — "feels like" is computed locally from temp/humidity/wind.

## Metra (deferred)
- `/gtfs/public/tripupdates` is protobuf binary, not JSON. Notes added when that step starts.
```

- [ ] **Step 4: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/CLAUDE.md apps/wall-dashboard/TODO.md apps/wall-dashboard/docs/api-notes.md
git commit -m "feat: scaffold wall-dashboard project"
```

---

## Task 2: Apps Script manifest

**Files:**
- Create: `apps/wall-dashboard/apps-script/appsscript.json`

- [ ] **Step 1: Create the manifest**

```json
{
  "timeZone": "America/Chicago",
  "dependencies": {},
  "exceptionLogging": "STACKDRIVER",
  "runtimeVersion": "V8",
  "webapp": {
    "executeAs": "USER_DEPLOYING",
    "access": "ANYONE_ANONYMOUS"
  }
}
```

The `America/Chicago` timezone makes `Utilities.formatDate(..., 'America/Chicago', ...)` and all hour math match local Northbrook time.

- [ ] **Step 2: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/apps-script/appsscript.json
git commit -m "feat: add Apps Script manifest"
```

---

## Task 3: Node test harness + view router (TDD)

**Files:**
- Create: `apps/wall-dashboard/tests/pure-logic.test.js`
- Create: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Create the test harness with the first failing test**

Create `apps/wall-dashboard/tests/pure-logic.test.js`:

```javascript
// Run with: node tests/pure-logic.test.js  (from apps/wall-dashboard/)
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

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

// === MORE TESTS APPENDED BELOW BY LATER TASKS ===

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `Code.gs` does not exist yet, harness throws `ENOENT`.

- [ ] **Step 3: Create `Code.gs` with `routeView_` and the export footer**

Create `apps/wall-dashboard/apps-script/Code.gs`:

```javascript
/**
 * Wall Dashboard — Apps Script web app.
 * Pure helpers are exported at the bottom for Node unit tests.
 */

// ---- Routing ---------------------------------------------------------------

/** Pure: map URL params to a route name. */
function routeView_(view, format) {
  if (view === 'trains' && format === 'json') return 'trainsJson';
  if (view === 'trains') return 'trains';
  return 'dashboard';
}

// ---- Node test export (no-op inside Apps Script) ---------------------------

if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `3 passed, 0 failed`.

- [ ] **Step 5: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/tests/pure-logic.test.js apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: add test harness and view router"
```

---

## Task 4: doGet skeleton + placeholder dashboard data

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Add `buildDashboardData_`, `renderDashboard_`, and `doGet`**

In `Code.gs`, insert the following AFTER the `routeView_` function and BEFORE the `if (typeof module ...)` export footer:

```javascript
// ---- Data assembly ---------------------------------------------------------

/**
 * Build the data object the dashboard renders.
 * Step 1: placeholder weather + trains. Step 2 replaces the weather block.
 */
function buildDashboardData_() {
  var now = new Date();
  var tz = 'America/Chicago';
  return {
    location: 'Glenview',
    dateStr: Utilities.formatDate(now, tz, 'EEE MMM d'),
    timeStr: Utilities.formatDate(now, tz, 'h:mm a'),
    weather: {
      available: true,
      temp: 72,
      feelsLike: 70,
      condition: 'Partly cloudy (placeholder)',
      hourly: [
        { label: '1p', temp: 74, precip: 10 },
        { label: '2p', temp: 76, precip: 15 },
        { label: '3p', temp: 78, precip: 20 },
        { label: '4p', temp: 77, precip: 35 },
        { label: '5p', temp: 74, precip: 40 },
        { label: '6p', temp: 70, precip: 20 },
        { label: '7p', temp: 67, precip: 5 }
      ]
    },
    trains: {
      available: false,
      list: [],
      message: 'Trains — coming in a later step'
    },
    updatedAt: Utilities.formatDate(now, tz, 'h:mm a')
  };
}

// ---- Rendering -------------------------------------------------------------

/** Inject the data object as JSON into Dashboard.html and return HtmlOutput. */
function renderDashboard_(data) {
  var t = HtmlService.createTemplateFromFile('Dashboard');
  t.dataJson = JSON.stringify(data);
  return t.evaluate()
    .setTitle('Wall Dashboard')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Minimal error page that still auto-refreshes. */
function errorPage_(message) {
  return HtmlService.createHtmlOutput(
    '<body style="margin:0;background:#0a0a0a;color:#e0e0e0;' +
    'font-family:sans-serif;font-size:32px;padding:48px">' +
    'Dashboard error — retrying<br><small style="font-size:18px;color:#888">' +
    message + '</small>' +
    '<meta http-equiv="refresh" content="60"></body>');
}

// ---- Entry point -----------------------------------------------------------

function doGet(e) {
  try {
    var p = (e && e.parameter) || {};
    var route = routeView_(p.view, p.format);
    if (route !== 'dashboard') {
      return HtmlService.createHtmlOutput(
        '<body style="margin:0;background:#0a0a0a;color:#e0e0e0;' +
        'font-family:sans-serif;font-size:32px;padding:48px">' +
        'Trains view — coming in a later step</body>');
    }
    return renderDashboard_(buildDashboardData_());
  } catch (err) {
    return errorPage_(String(err));
  }
}
```

This task adds no automated test — `doGet` and `renderDashboard_` are I/O (they need `HtmlService`/`Utilities`). They are verified by the deployment checkpoint in Task 6.

- [ ] **Step 2: Run the existing tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `3 passed, 0 failed` (the new code only adds function declarations; the harness still loads cleanly).

- [ ] **Step 3: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: add doGet routing and placeholder dashboard data"
```

---

## Task 5: Dashboard.html — OLED-safe TV layout

**Files:**
- Create: `apps/wall-dashboard/apps-script/Dashboard.html`

- [ ] **Step 1: Create `Dashboard.html`**

This file renders whatever `DATA` it is given and never changes again — Step 2 only swaps the data, not the markup.

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="300">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      width: 100%; height: 100%;
      background: #0a0a0a; color: #e0e0e0;
      font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
      overflow: hidden;
    }
    #root { padding: 48px 64px; height: 100%; display: flex; flex-direction: column; }
    .header { display: flex; justify-content: space-between; align-items: flex-start; }
    .location { font-size: 44px; font-weight: 600; letter-spacing: 2px; }
    .clock { text-align: right; }
    .date { font-size: 30px; color: #9a9a9a; }
    .time { font-size: 40px; }
    .current { margin-top: 36px; display: flex; align-items: baseline; gap: 28px; }
    .current .temp { font-size: 110px; font-weight: 300; color: #7ab8ff; line-height: 1; }
    .current .meta { font-size: 30px; color: #c0c0c0; }
    .current .feels { font-size: 24px; color: #8a8a8a; }
    .section-label {
      margin-top: 40px; font-size: 22px; letter-spacing: 3px;
      color: #6a6a6a; border-bottom: 1px solid #242424; padding-bottom: 8px;
    }
    .hourly {
      margin-top: 20px;
      display: grid; grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));
      gap: 12px;
    }
    .hour { text-align: center; }
    .hour .h { font-size: 26px; color: #9a9a9a; }
    .hour .t { font-size: 40px; margin-top: 6px; }
    .hour .p { font-size: 22px; color: #6f9fd0; margin-top: 4px; }
    .trains { margin-top: 16px; }
    .train-row {
      display: flex; justify-content: space-between;
      font-size: 38px; padding: 10px 0;
    }
    .train-row .cd { color: #9a9a9a; }
    .unavailable { font-size: 30px; color: #8a8a8a; margin-top: 16px; }
    .footer { margin-top: auto; font-size: 20px; color: #4a4a4a; }
  </style>
</head>
<body>
  <div id="root"></div>

  <script>
    const DATA = <?!= dataJson ?>;

    function el(tag, cls, text) {
      const n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text != null) n.textContent = text;
      return n;
    }

    function render(d) {
      const root = document.getElementById('root');
      root.innerHTML = '';

      // Header
      const header = el('div', 'header');
      header.appendChild(el('div', 'location', d.location.toUpperCase()));
      const clock = el('div', 'clock');
      clock.appendChild(el('div', 'date', d.dateStr));
      clock.appendChild(el('div', 'time', d.timeStr));
      header.appendChild(clock);
      root.appendChild(header);

      // Current weather
      if (d.weather.available) {
        const cur = el('div', 'current');
        cur.appendChild(el('div', 'temp', (d.weather.temp != null ? d.weather.temp : '--') + '°'));
        const meta = el('div', 'meta');
        meta.appendChild(el('div', null, d.weather.condition || ''));
        if (d.weather.feelsLike != null) {
          meta.appendChild(el('div', 'feels', 'Feels ' + d.weather.feelsLike + '°'));
        }
        cur.appendChild(meta);
        root.appendChild(cur);

        root.appendChild(el('div', 'section-label', 'HOURLY'));
        const grid = el('div', 'hourly');
        d.weather.hourly.forEach(function (h) {
          const cell = el('div', 'hour');
          cell.appendChild(el('div', 'h', h.label));
          cell.appendChild(el('div', 't', (h.temp != null ? h.temp : '--') + '°'));
          cell.appendChild(el('div', 'p', (h.precip != null ? h.precip : '--') + '%'));
          grid.appendChild(cell);
        });
        root.appendChild(grid);
      } else {
        root.appendChild(el('div', 'unavailable', 'Weather unavailable'));
      }

      // Trains
      root.appendChild(el('div', 'section-label', 'NORTHBROOK TRAINS'));
      const trains = el('div', 'trains');
      if (d.trains.available && d.trains.list.length) {
        d.trains.list.forEach(function (t) {
          const row = el('div', 'train-row');
          row.appendChild(el('div', null, t.type + '   ' + t.time));
          row.appendChild(el('div', 'cd', t.countdown));
          trains.appendChild(row);
        });
      } else {
        trains.appendChild(el('div', 'unavailable', d.trains.message || 'Trains unavailable'));
      }
      root.appendChild(trains);

      root.appendChild(el('div', 'footer', 'Updated ' + d.updatedAt));
    }

    render(DATA);
  </script>
</body>
</html>
```

- [ ] **Step 2: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/apps-script/Dashboard.html
git commit -m "feat: add OLED-safe TV dashboard layout"
```

---

## Task 6: README deployment guide + Step 1 deployment checkpoint

**Files:**
- Create: `apps/wall-dashboard/README.md`
- Create: `apps/wall-dashboard/docs/sheet-setup.md`

- [ ] **Step 1: Create `docs/sheet-setup.md`**

```markdown
# Google Sheet Setup

Create one Google Sheet named **Wall Dashboard Config** with these tabs.

## Tab: `Config`  (two columns; row 1 is the header `Key | Value`)

| Key | Value |
|---|---|
| metra_api_token | (leave blank until the Metra step) |
| metra_stop_id | (leave blank until the Metra step) |
| nws_lat | 42.0728 |
| nws_lon | -87.7878 |
| nws_forecast_hourly_url | (leave blank — filled by bootstrapNwsUrl_) |
| nws_user_agent | WallDashboard/1.0 (help.sohn@gmail.com) |
| display_start_hour | 6 |
| display_end_hour | 21 |
| weather_flip_hour | 17 |
| weather_end_hour | 19 |
| max_trains | 3 |
| train_window_min | 30 |

## Tab: `AmtrakSchedule`  (header row: `train_num | direction | glenview_time | days`)

Leave the rows empty for now — populated in the trains step.
```

- [ ] **Step 2: Create `README.md`**

```markdown
# Wall Dashboard

Wall-mounted TV dashboard (Glenview weather + Northbrook trains) built as a
Google Apps Script web app.

## One-time setup

1. **Create the Sheet.** Follow `docs/sheet-setup.md` — make the Sheet and its
   `Config` and `AmtrakSchedule` tabs.
2. **Open the script editor.** In the Sheet: Extensions → Apps Script.
3. **Add the files.** In the editor, recreate each file from `apps-script/`:
   - `Code.gs` — paste over the default `Code.gs`.
   - `Dashboard.html` — File → New → HTML, name it `Dashboard`, paste.
   - `appsscript.json` — Project Settings → check "Show appsscript.json", then
     paste its contents over the manifest.
4. **Deploy.** Deploy → New deployment → type **Web app**.
   - Execute as: **Me**
   - Who has access: **Anyone**
   - Click Deploy, authorize when prompted, copy the `/exec` URL.
   - **Record the deployment ID** — always reuse it for future updates so the
     Fire Stick bookmark never breaks.

## Updating later

Edit files in the editor, then Deploy → Manage deployments → edit the existing
deployment → New version. The `/exec` URL stays the same.

## Fire Stick

Install **Fully Kiosk Browser**, set the start URL to the `/exec` URL, enable
kiosk mode and auto-launch on boot.

## Tests

Pure logic is unit-tested with Node (no dependencies):

    cd apps/wall-dashboard
    node tests/pure-logic.test.js
```

- [ ] **Step 3: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/README.md apps/wall-dashboard/docs/sheet-setup.md
git commit -m "docs: add deployment guide and sheet setup"
```

- [ ] **Step 4: USER CHECKPOINT — deploy and verify on the TV**

Hand off to the user. They:
1. Create the Sheet per `docs/sheet-setup.md`.
2. Add the three files to the Apps Script editor and deploy as a web app per `README.md`.
3. Open the `/exec` URL in a browser — confirm a dark dashboard with placeholder weather (72°, hourly strip) and a "Trains — coming in a later step" line.
4. Point Fully Kiosk on the Fire Stick at the URL and **confirm it fills the TV correctly** (dark, readable, no overflow).

Do not start Step 2 until the user confirms the skeleton renders correctly on the TV. If layout problems appear, fix `Dashboard.html` and redeploy before proceeding.

---

# STEP 2 — Live Weather

## Task 7: `getWeatherWindow_` — today/tomorrow flip (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert this block immediately after the `routeView_` tests (before the `// === MORE TESTS` marker):

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.getWeatherWindow_ is not a function`.

- [ ] **Step 3: Implement `getWeatherWindow_`**

In `Code.gs`, add a new section after `routeView_` and before `buildDashboardData_`:

```javascript
// ---- Weather window (pure) -------------------------------------------------

/**
 * Pure: which hours of weather to display.
 * Before flipHour -> rest of today (next full hour..endHour).
 * At/after flipHour -> tomorrow 7..endHour.
 */
function getWeatherWindow_(nowHour, flipHour, endHour) {
  var hours = [];
  if (nowHour < flipHour) {
    for (var h = nowHour + 1; h <= endHour; h++) hours.push(h);
    return { dayOffset: 0, hours: hours };
  }
  for (var t = 7; t <= endHour; t++) hours.push(t);
  return { dayOffset: 1, hours: hours };
}
```

Add `getWeatherWindow_` to the export footer:

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `7 passed, 0 failed`.

- [ ] **Step 5: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add weather window flip logic"
```

---

## Task 8: `formatHourLabel_` (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `getWeatherWindow_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.formatHourLabel_ is not a function`.

- [ ] **Step 3: Implement `formatHourLabel_`**

In `Code.gs`, add inside the weather-window section, after `getWeatherWindow_`:

```javascript
/** Pure: hour 0-23 -> compact label like "9a" / "1p" / "12p". */
function formatHourLabel_(hour) {
  var period = hour < 12 ? 'a' : 'p';
  var hr = hour % 12;
  if (hr === 0) hr = 12;
  return hr + period;
}
```

Add `formatHourLabel_` to the export footer:

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `10 passed, 0 failed`.

- [ ] **Step 5: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add hour label formatter"
```

---

## Task 9: `feelsLike_` — apparent temperature (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `formatHourLabel_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.feelsLike_ is not a function`.

- [ ] **Step 3: Implement `feelsLike_`**

In `Code.gs`, add inside the weather-window section, after `formatHourLabel_`:

```javascript
/**
 * Pure: apparent temperature in F.
 * Heat index when hot+humid, wind chill when cold+windy, else the temp itself.
 * Uses the NWS Rothfusz heat-index and the standard wind-chill regressions.
 */
function feelsLike_(tempF, humidityPct, windMph) {
  if (tempF == null) return null;
  if (tempF >= 80 && humidityPct != null) {
    var T = tempF, R = humidityPct;
    var hi = -42.379 + 2.04901523 * T + 10.14333127 * R
      - 0.22475541 * T * R - 0.00683783 * T * T - 0.05481717 * R * R
      + 0.00122874 * T * T * R + 0.00085282 * T * R * R
      - 0.00000199 * T * T * R * R;
    return Math.round(hi);
  }
  if (tempF <= 50 && windMph >= 3) {
    var v = Math.pow(windMph, 0.16);
    return Math.round(35.74 + 0.6215 * tempF - 35.75 * v + 0.4275 * tempF * v);
  }
  return Math.round(tempF);
}
```

Add `feelsLike_` to the export footer:

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `14 passed, 0 failed`.

- [ ] **Step 5: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add feels-like temperature calculation"
```

---

## Task 10: `matchHour_` — pick a forecast hour (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `feelsLike_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.matchHour_ is not a function`.

- [ ] **Step 3: Implement `matchHour_`**

In `Code.gs`, add inside the weather-window section, after `feelsLike_`:

```javascript
/** Pure: find the hourly entry whose hourKey equals key, or null. */
function matchHour_(hourly, key) {
  for (var i = 0; i < hourly.length; i++) {
    if (hourly[i].hourKey === key) return hourly[i];
  }
  return null;
}
```

Add `matchHour_` to the export footer:

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_,
    matchHour_: matchHour_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `16 passed, 0 failed`.

- [ ] **Step 5: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add forecast-hour matcher"
```

---

## Task 11: `cachedFetch_` — caching with last-good fallback (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `matchHour_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.cachedFetch_ is not a function`.

- [ ] **Step 3: Implement `cachedFetch_`**

In `Code.gs`, add a new section after the weather-window section and before `buildDashboardData_`:

```javascript
// ---- Caching ---------------------------------------------------------------

/**
 * Run fn() at most once per ttlSec, caching the JSON-serializable result.
 * On a fetch failure, serve the last good value (kept for 6 h) if one exists.
 */
function cachedFetch_(key, ttlSec, fn) {
  var cache = CacheService.getScriptCache();
  var hit = cache.get(key);
  if (hit) return JSON.parse(hit);
  try {
    var fresh = fn();
    var serialized = JSON.stringify(fresh);
    cache.put(key, serialized, ttlSec);
    cache.put(key + '__last_good', serialized, 21600);
    return fresh;
  } catch (err) {
    var lastGood = cache.get(key + '__last_good');
    if (lastGood) return JSON.parse(lastGood);
    throw err;
  }
}
```

Add `cachedFetch_` to the export footer:

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_,
    matchHour_: matchHour_,
    cachedFetch_: cachedFetch_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `19 passed, 0 failed`.

- [ ] **Step 5: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add cachedFetch with last-good fallback"
```

---

## Task 12: `getConfig_` — read the Config sheet

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Implement `getConfig_`**

In `Code.gs`, add a new section after the caching section and before `buildDashboardData_`:

```javascript
// ---- Config ----------------------------------------------------------------

/** Read the Config tab into a {key: value} object. Cached 5 min. */
function getConfig_() {
  return cachedFetch_('config', 300, function () {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Config');
    if (!sheet) throw new Error('Config sheet tab not found');
    var rows = sheet.getDataRange().getValues();
    var cfg = {};
    for (var i = 1; i < rows.length; i++) {
      var key = String(rows[i][0]).trim();
      if (key) cfg[key] = rows[i][1];
    }
    return cfg;
  });
}
```

This is I/O (`SpreadsheetApp`); it is verified in Task 14's checkpoint. No automated test.

- [ ] **Step 2: Run the existing tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `19 passed, 0 failed`.

- [ ] **Step 3: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: add Config sheet reader"
```

---

## Task 13: `bootstrapNwsUrl_` + `getWeather_` — NWS integration

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Implement the weather fetch functions**

In `Code.gs`, add a new section after the Config section and before `buildDashboardData_`:

```javascript
// ---- Weather fetch ---------------------------------------------------------

/**
 * One-time helper: resolve the NWS hourly-forecast URL and write it into the
 * Config tab. Run manually from the editor (Run -> bootstrapNwsUrl_).
 */
function bootstrapNwsUrl_() {
  var config = getConfig_();
  var pointsUrl = 'https://api.weather.gov/points/' + config.nws_lat + ',' + config.nws_lon;
  var resp = UrlFetchApp.fetch(pointsUrl, {
    headers: { 'User-Agent': config.nws_user_agent },
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error('NWS /points returned ' + resp.getResponseCode());
  }
  var forecastHourly = JSON.parse(resp.getContentText()).properties.forecastHourly;
  Logger.log('forecastHourly URL: ' + forecastHourly);
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Config');
  var rows = sheet.getDataRange().getValues();
  for (var i = 1; i < rows.length; i++) {
    if (String(rows[i][0]).trim() === 'nws_forecast_hourly_url') {
      sheet.getRange(i + 1, 2).setValue(forecastHourly);
      Logger.log('Wrote URL to Config row ' + (i + 1));
      return;
    }
  }
  throw new Error('Config row nws_forecast_hourly_url not found');
}

/**
 * Fetch the NWS hourly forecast, reduced to the fields the dashboard needs.
 * Returns { hourly: [{hourKey, temp, precip, humidity, windMph, condition}] }.
 * Cached 15 min.
 */
function getWeather_(config) {
  return cachedFetch_('weather', 900, function () {
    var url = config.nws_forecast_hourly_url;
    if (!url) throw new Error('nws_forecast_hourly_url not set — run bootstrapNwsUrl_ first');
    var resp = UrlFetchApp.fetch(url, {
      headers: { 'User-Agent': config.nws_user_agent },
      muteHttpExceptions: true
    });
    if (resp.getResponseCode() !== 200) {
      throw new Error('NWS hourly returned ' + resp.getResponseCode());
    }
    var periods = JSON.parse(resp.getContentText()).properties.periods;
    var hourly = periods.slice(0, 48).map(function (p) {
      return {
        hourKey: Utilities.formatDate(new Date(p.startTime), 'America/Chicago', 'yyyy-MM-dd-HH'),
        temp: p.temperature,
        precip: (p.probabilityOfPrecipitation && p.probabilityOfPrecipitation.value) || 0,
        humidity: (p.relativeHumidity && p.relativeHumidity.value != null)
          ? p.relativeHumidity.value : null,
        windMph: parseInt(p.windSpeed, 10) || 0,
        condition: p.shortForecast
      };
    });
    return { hourly: hourly };
  });
}
```

I/O functions — verified in Task 14's checkpoint.

- [ ] **Step 2: Run the existing tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `19 passed, 0 failed`.

- [ ] **Step 3: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: add NWS weather fetch and bootstrap helper"
```

---

> **Plan amendment (2026-05-17): AQI added.** During the Step 1 checkpoint the
> user requested an Air Quality Index display with an alert state. Step 1 was
> refined to add a placeholder `aqi` object to `buildDashboardData_` and an
> `aqi` element + `renderAqi` to `Dashboard.html` (committed). Tasks 14 and 15
> below add the real AQI logic; Task 16 wires it in. Also note: a router test
> was added during Step 1 review, so every "X passed" count in Tasks 7–13 is
> **+1** higher than printed — verify the count rises by the right delta, not
> the absolute number.

## Task 14: `aqiInfo_` — AQI category / alert mapping (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Write the failing tests**

In `pure-logic.test.js`, insert after the `cachedFetch_` tests:

```javascript
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — `lib.aqiInfo_ is not a function`.

- [ ] **Step 3: Implement `aqiInfo_`**

In `Code.gs`, add inside the weather-window section, after `matchHour_`:

```javascript
/**
 * Pure: US AQI value -> { category, level, alert }.
 * level is good|moderate|unhealthy for styling; alert is true for 51+.
 */
function aqiInfo_(value) {
  if (value <= 50)  return { category: 'Good', level: 'good', alert: false };
  if (value <= 100) return { category: 'Moderate', level: 'moderate', alert: true };
  if (value <= 150) return { category: 'Unhealthy for Sensitive', level: 'unhealthy', alert: true };
  if (value <= 200) return { category: 'Unhealthy', level: 'unhealthy', alert: true };
  if (value <= 300) return { category: 'Very Unhealthy', level: 'unhealthy', alert: true };
  return { category: 'Hazardous', level: 'unhealthy', alert: true };
}
```

Add `aqiInfo_` to the export footer (keep all existing entries):

```javascript
if (typeof module !== 'undefined') {
  module.exports = {
    routeView_: routeView_,
    getWeatherWindow_: getWeatherWindow_,
    formatHourLabel_: formatHourLabel_,
    feelsLike_: feelsLike_,
    matchHour_: matchHour_,
    cachedFetch_: cachedFetch_,
    aqiInfo_: aqiInfo_
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — all tests pass, count up by 6 from the previous run.

- [ ] **Step 5: Stage and commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add AQI category/alert mapping"
```

---

## Task 15: `getAqi_` — Open-Meteo air quality fetch

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Implement `getAqi_`**

In `Code.gs`, add in the weather-fetch section, after `getWeather_`:

```javascript
/**
 * Fetch the current US AQI from Open-Meteo (no auth). Reuses the Config
 * lat/lon. Returns { value: <int> }. Cached 30 min.
 */
function getAqi_(config) {
  return cachedFetch_('aqi', 1800, function () {
    var url = 'https://air-quality-api.open-meteo.com/v1/air-quality'
      + '?latitude=' + config.nws_lat
      + '&longitude=' + config.nws_lon
      + '&current=us_aqi&timezone=America/Chicago';
    var resp = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (resp.getResponseCode() !== 200) {
      throw new Error('Open-Meteo AQI returned ' + resp.getResponseCode());
    }
    var current = JSON.parse(resp.getContentText()).current;
    if (!current || current.us_aqi == null) {
      throw new Error('AQI response missing us_aqi');
    }
    return { value: Math.round(current.us_aqi) };
  });
}
```

I/O function — verified in Task 16's checkpoint.

- [ ] **Step 2: Run the existing tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — same count as after Task 14.

- [ ] **Step 3: Stage and commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: add Open-Meteo AQI fetch"
```

---

## Task 16: Wire live weather + AQI into `buildDashboardData_` + Step 2 checkpoint

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Replace `buildDashboardData_` with the live-data version**

In `Code.gs`, replace the entire `buildDashboardData_` function (the Step 1
placeholder version, which currently has placeholder `aqi`, `weather`, and
`trains`) with the version below. It keeps the `aqi` field but now fills it from
real data; weather and AQI fail independently so one outage never blanks the
screen.

```javascript
/** Build the data object the dashboard renders, with live weather + AQI. */
function buildDashboardData_() {
  var now = new Date();
  var tz = 'America/Chicago';
  var data = {
    location: 'Glenview',
    dateStr: Utilities.formatDate(now, tz, 'EEE MMM d'),
    timeStr: Utilities.formatDate(now, tz, 'h:mm a'),
    aqi: { available: false },
    weather: { available: false },
    trains: { available: false, list: [], message: 'Trains — coming in a later step' },
    updatedAt: Utilities.formatDate(now, tz, 'h:mm a')
  };

  var config;
  try {
    config = getConfig_();
  } catch (err) {
    return data; // no config -> everything stays unavailable
  }

  // Weather
  try {
    var weather = getWeather_(config);
    var nowHour = parseInt(Utilities.formatDate(now, tz, 'H'), 10);
    var win = getWeatherWindow_(nowHour,
      parseInt(config.weather_flip_hour, 10), parseInt(config.weather_end_hour, 10));
    var hourly = win.hours.map(function (h) {
      var match = matchHour_(weather.hourly, hourKeyFor_(now, win.dayOffset, h, tz));
      return {
        label: formatHourLabel_(h),
        temp: match ? match.temp : null,
        precip: match ? match.precip : null
      };
    });
    var current = matchHour_(weather.hourly, hourKeyFor_(now, 0, nowHour, tz));
    data.weather = {
      available: true,
      temp: current ? current.temp : null,
      feelsLike: current ? feelsLike_(current.temp, current.humidity, current.windMph) : null,
      condition: current ? current.condition : '',
      hourly: hourly
    };
  } catch (err) {
    data.weather = { available: false, error: String(err) };
  }

  // Air quality
  try {
    var aqiVal = getAqi_(config).value;
    var info = aqiInfo_(aqiVal);
    data.aqi = {
      available: true,
      value: aqiVal,
      category: info.category,
      level: info.level,
      alert: info.alert
    };
  } catch (err) {
    data.aqi = { available: false };
  }

  return data;
}

/** Build the 'yyyy-MM-dd-HH' key for now + dayOffset days at the given hour. */
function hourKeyFor_(now, dayOffset, hour, tz) {
  var d = new Date(now.getTime() + dayOffset * 86400000);
  var hh = hour < 10 ? '0' + hour : '' + hour;
  return Utilities.formatDate(d, tz, 'yyyy-MM-dd') + '-' + hh;
}
```

- [ ] **Step 2: Run the tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `19 passed, 0 failed`.

- [ ] **Step 3: Stage and commit (confirm with user)**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: wire live weather and AQI into the dashboard"
```

- [ ] **Step 4: USER CHECKPOINT — bootstrap and verify live weather + AQI**

Hand off to the user. They:
1. Re-paste the updated `Code.gs` into the Apps Script editor.
2. In the editor, select `bootstrapNwsUrl_` from the function dropdown and click Run. Authorize if prompted. Confirm the execution log prints a `forecastHourly URL` and "Wrote URL to Config row N" — and that the `nws_forecast_hourly_url` cell in the Sheet is now filled. (No bootstrap is needed for AQI — Open-Meteo needs no setup.)
3. Deploy a new version of the existing deployment (Manage deployments → edit → New version).
4. Open the `/exec` URL — confirm the current temperature, condition, and "Feels" line show **real Glenview values**, and the hourly strip shows real temps/precip.
5. Confirm the **AQI** shows under the time with the real current value — dim text if Good, or the amber/red alert pill if Moderate or worse.
6. Sanity-check the window: before 5 PM it shows the rest of today through 7 PM; at/after 5 PM it shows tomorrow 7 AM–7 PM.
7. Confirm it still renders correctly on the TV via the Fire Stick.

Step 2 is complete once the user confirms live weather and AQI display correctly. Trains, the phone widget, and Metra are covered by follow-up plans.

---

## Verification Summary

After all tasks the full unit-test suite passes (Node `assert`, no dependencies):

    cd apps/wall-dashboard && node tests/pure-logic.test.js

The suite covers `routeView_`, `getWeatherWindow_`, `formatHourLabel_`,
`feelsLike_`, `matchHour_`, `cachedFetch_`, and `aqiInfo_`.

Functional verification happens at the two user checkpoints (Task 6, Task 16) — there is no automated test for the deployed web app, by design (it depends on Google-side deployment the user controls).
