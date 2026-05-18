# Wall Dashboard — Phone Widget & OLED Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the compact phone widget view (plus a JSON route) and the OLED-protection polish, completing every non-deployment piece of the dashboard.

**Architecture:** The phone widget reuses the existing train pipeline: `getCombinedTrains_` is parameterized so the phone view can ask for "next 3 trains, any hour, no window" while the TV keeps "next 3 within 30 min during display hours". `buildTrainsData_` assembles a trains-only payload; `renderTrainsOnly_` serves it as a minimal phone page (`Trains.html`); `renderTrainsJson_` serves it as JSON. OLED polish adds a periodic pixel nudge and a 60-second live refresh via `google.script.run` (the Apps Script-correct way to re-pull data without a full reload).

**Tech Stack:** Google Apps Script (V8), HTML/CSS/vanilla JS. The existing `Code.gs` + `tests/pure-logic.test.js`. No new dependencies.

**Depends on:** the trains plans (`getCombinedTrains_`, `selectTrains_`, `buildDashboardData_` exist). Covers spec build-steps 4 (phone widget) and 7 (polish).

**Commit policy:** Work is on the isolated, unpushed `worktree-wall-dashboard` branch. Run the commit steps as written.

**Test count note:** the suite stands at **102 passing**. Task 1 modifies an existing test (count stays 102); the other tasks are I/O / HTML with no automated tests.

---

## File Structure

| File | Change |
|---|---|
| `apps/wall-dashboard/apps-script/Code.gs` | `countdownMin` in `selectTrains_`; parameterize `getCombinedTrains_`; add `buildTrainsData_`, `renderTrainsOnly_`, `renderTrainsJson_`, `dashboardData`; wire `doGet` |
| `apps/wall-dashboard/apps-script/Trains.html` | New — the phone widget view |
| `apps/wall-dashboard/apps-script/Dashboard.html` | Add the OLED pixel-nudge + 60 s live refresh |
| `apps/wall-dashboard/tests/pure-logic.test.js` | Update one `selectTrains_` test for `countdownMin` |

All paths below are relative to `C:\Users\slims\Desktop\Claude 2.0\.claude\worktrees\wall-dashboard\`.

### Data shapes

- **Display item** (`selectTrains_` output) gains a numeric field: `{ type, time, countdown, countdownMin }`.
- **Trains payload** (`buildTrainsData_`): `{ location, trains: { available, list, message }, updatedAt }`.
- **JSON route output**: `{ trains: [{ type, time, countdown_min, countdown_str }], updated_at }`.

---

## Task 1: Add `countdownMin` to `selectTrains_` display items (TDD)

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/tests/pure-logic.test.js`

- [ ] **Step 1: Update the existing test to expect `countdownMin`**

In `pure-logic.test.js`, find the test `selectTrains_ lists trains inside the window, soonest first`. Replace its `assert.deepStrictEqual(r.list, [...])` call with:

```javascript
  assert.deepStrictEqual(r.list, [
    { type: 'Amtrak', time: '12:51 PM', countdown: '9 min', countdownMin: 9 },
    { type: 'Amtrak', time: '1:03 PM', countdown: '21 min', countdownMin: 21 }
  ]);
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: FAIL — the test expects a `countdownMin` field the code does not yet produce.

- [ ] **Step 3: Add `countdownMin` to the `display` helper inside `selectTrains_`**

In `Code.gs`, `selectTrains_` contains an inner `display` function. Replace it with:

```javascript
  function display(t) {
    var delta = t.passMinutes - nowMinutes;
    return {
      type: t.type,
      time: formatClockTime_(t.passMinutes),
      countdown: formatCountdown_(delta),
      countdownMin: delta
    };
  }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `102 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/tests/pure-logic.test.js
git commit -m "feat: add numeric countdownMin to train display items"
```

---

## Task 2: Parameterize `getCombinedTrains_`

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Replace `getCombinedTrains_` with the parameterized version**

In `Code.gs`, replace the entire existing `getCombinedTrains_` function with:

```javascript
/**
 * Gather every train source (Amtrak + Metra), merge, and run selectTrains_.
 * `opts` = { windowMin, maxCount, respectHours }; display-hour bounds come
 * from config. A Metra feed failure must never drop the Amtrak trains.
 */
function getCombinedTrains_(now, tz, config, opts) {
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
    windowMin: opts.windowMin,
    maxCount: opts.maxCount,
    respectHours: opts.respectHours,
    startHour: parseInt(config.display_start_hour, 10),
    endHour: parseInt(config.display_end_hour, 10)
  });
}
```

- [ ] **Step 2: Update the `buildDashboardData_` call site**

In `Code.gs`, inside `buildDashboardData_`, the `// Trains` block calls `getCombinedTrains_(now, tz, config)`. Change that call to pass the dashboard options:

```javascript
    var combined = getCombinedTrains_(now, tz, config, {
      windowMin: parseInt(config.train_window_min, 10),
      maxCount: parseInt(config.max_trains, 10),
      respectHours: true
    });
```

(The rest of the `// Trains` block — assigning `data.trains` from `combined` — is unchanged.)

- [ ] **Step 3: Run the tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `102 passed, 0 failed`.

- [ ] **Step 4: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "refactor: parameterize getCombinedTrains_ for phone vs TV"
```

---

## Task 3: `buildTrainsData_` — the trains-only payload

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Implement `buildTrainsData_`**

In `Code.gs`, add it in the data-assembly section, immediately after `buildDashboardData_`:

```javascript
/**
 * Build the trains-only payload for the phone widget and JSON route:
 * the next 3 trains regardless of hour or window.
 */
function buildTrainsData_() {
  var now = new Date();
  var tz = 'America/Chicago';
  var data = {
    location: 'Northbrook',
    trains: { available: false, list: [], message: 'Trains unavailable' },
    updatedAt: Utilities.formatDate(now, tz, 'h:mm a')
  };
  try {
    var config = getConfig_();
    var combined = getCombinedTrains_(now, tz, config, {
      windowMin: 100000,     // effectively no window
      maxCount: 3,
      respectHours: false
    });
    data.trains = {
      available: combined.list.length > 0,
      list: combined.list,
      message: combined.message
    };
  } catch (err) {
    data.trains = { available: false, list: [], message: 'Trains unavailable' };
  }
  return data;
}
```

This is I/O — verified at the Task 7 checkpoint. No automated test.

- [ ] **Step 2: Run the tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `102 passed, 0 failed`.

- [ ] **Step 3: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: add trains-only payload builder"
```

---

## Task 4: `Trains.html` + `renderTrainsOnly_` — the phone widget view

**Files:**
- Create: `apps/wall-dashboard/apps-script/Trains.html`
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Create `Trains.html`**

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
      background: #ffffff; color: #111111;
    }
    .wrap { max-width: 380px; margin: 0 auto; padding: 22px; }
    .loc { font-size: 22px; font-weight: 600; letter-spacing: 1px; margin-bottom: 14px; }
    .train { padding: 14px 0; border-bottom: 1px solid #ededed; }
    .train .top { display: flex; justify-content: space-between; font-size: 25px; }
    .train .cd { font-size: 18px; color: #5a5a5a; margin-top: 3px; }
    .empty { font-size: 20px; color: #777777; padding: 14px 0; }
    .upd { font-size: 14px; color: #9a9a9a; margin-top: 18px; }
  </style>
</head>
<body>
  <div class="wrap" id="root"></div>
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
      root.appendChild(el('div', 'loc', d.location.toUpperCase()));
      if (d.trains.available && d.trains.list.length) {
        d.trains.list.forEach(function (t) {
          const row = el('div', 'train');
          const top = el('div', 'top');
          top.appendChild(el('div', null, t.type));
          top.appendChild(el('div', null, t.time));
          row.appendChild(top);
          row.appendChild(el('div', 'cd', t.countdown));
          root.appendChild(row);
        });
      } else {
        root.appendChild(el('div', 'empty', d.trains.message || 'No trains'));
      }
      root.appendChild(el('div', 'upd', 'Updated ' + d.updatedAt));
    }

    render(DATA);
  </script>
</body>
</html>
```

- [ ] **Step 2: Add `renderTrainsOnly_`**

In `Code.gs`, add it in the rendering section, after `renderDashboard_`:

```javascript
/** Inject the trains payload into Trains.html and return HtmlOutput. */
function renderTrainsOnly_(data) {
  var t = HtmlService.createTemplateFromFile('Trains');
  t.dataJson = JSON.stringify(data).replace(/<\/script>/gi, '<\\/script>');
  return t.evaluate()
    .setTitle('Northbrook Trains')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}
```

- [ ] **Step 3: Run the tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `102 passed, 0 failed`.

- [ ] **Step 4: Commit**

```bash
git add apps/wall-dashboard/apps-script/Trains.html apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: add phone widget view"
```

---

## Task 5: `renderTrainsJson_` — the JSON route

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Add `renderTrainsJson_`**

In `Code.gs`, add it in the rendering section, after `renderTrainsOnly_`:

```javascript
/** Serve the trains payload as JSON (for a future phone app). */
function renderTrainsJson_(data) {
  var trains = data.trains.list.map(function (t) {
    return {
      type: t.type,
      time: t.time,
      countdown_min: t.countdownMin,
      countdown_str: t.countdown
    };
  });
  var payload = { trains: trains, updated_at: data.updatedAt };
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
```

This is I/O — verified at the Task 7 checkpoint. No automated test.

- [ ] **Step 2: Run the tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `102 passed, 0 failed`.

- [ ] **Step 3: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: add trains JSON route"
```

---

## Task 6: Wire `doGet` to the trains routes

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`

- [ ] **Step 1: Replace `doGet` with the routed version**

In `Code.gs`, replace the entire `doGet` function with:

```javascript
function doGet(e) {
  try {
    var p = (e && e.parameter) || {};
    var route = routeView_(p.view, p.format);
    if (route === 'trainsJson') return renderTrainsJson_(buildTrainsData_());
    if (route === 'trains') return renderTrainsOnly_(buildTrainsData_());
    return renderDashboard_(buildDashboardData_());
  } catch (err) {
    return errorPage_(String(err));
  }
}
```

(`routeView_` already maps `?view=trains` → `trains` and `?view=trains&format=json` → `trainsJson`; this replaces the earlier "coming in a later step" placeholder branch.)

- [ ] **Step 2: Run the tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `102 passed, 0 failed`.

- [ ] **Step 3: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs
git commit -m "feat: route phone widget and JSON views in doGet"
```

---

## Task 7: OLED polish — pixel nudge + 60-second live refresh

**Files:**
- Modify: `apps/wall-dashboard/apps-script/Code.gs`
- Modify: `apps/wall-dashboard/apps-script/Dashboard.html`

- [ ] **Step 1: Add the public `dashboardData` function**

`google.script.run` can only call functions without a trailing underscore. In `Code.gs`, add this in the data-assembly section, immediately after `buildTrainsData_`:

```javascript
/** Public wrapper so the page can re-pull dashboard data via google.script.run. */
function dashboardData() {
  return buildDashboardData_();
}
```

- [ ] **Step 2: Add the live refresh + pixel nudge to `Dashboard.html`**

In `apps/wall-dashboard/apps-script/Dashboard.html`, find the line `render(DATA);` near the end of the `<script>` block. Replace it with:

```javascript
    render(DATA);

    // Live refresh: re-pull data every 60 s without a full page reload.
    setInterval(function () {
      google.script.run.withSuccessHandler(render).dashboardData();
    }, 60000);

    // OLED burn-in protection: nudge the whole frame a few pixels every 60 min.
    setInterval(function () {
      var dx = Math.floor(Math.random() * 7) - 3;  // -3..3 px
      var dy = Math.floor(Math.random() * 7) - 3;
      document.body.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';
    }, 3600000);
```

The `<meta http-equiv="refresh" content="300">` full reload stays as a 5-minute backstop.

- [ ] **Step 3: Run the tests to confirm nothing broke**

Run: `cd apps/wall-dashboard && node tests/pure-logic.test.js`
Expected: PASS — `102 passed, 0 failed`.

- [ ] **Step 4: Commit**

```bash
git add apps/wall-dashboard/apps-script/Code.gs apps/wall-dashboard/apps-script/Dashboard.html
git commit -m "feat: add OLED pixel nudge and 60s live refresh"
```

- [ ] **Step 5: USER CHECKPOINT — deploy and verify the phone widget + polish**

Hand off to the user. They:
1. Re-paste the updated `Code.gs` and `Dashboard.html` into the Apps Script editor, and add `Trains.html` as a new HTML file named exactly `Trains`.
2. Deploy a new version of the existing deployment.
3. Open `<exec-url>?view=trains` on a phone — confirm a clean, compact list of the next 3 trains with "Updated …".
4. Open `<exec-url>?view=trains&format=json` — confirm valid JSON (`trains` array + `updated_at`).
5. Open `<exec-url>` (the TV dashboard) — confirm it still renders; after ~60 s the data refreshes without a visible full reload.

This plan is complete once the user confirms the phone view and JSON route work and the dashboard still renders. After this, every non-deployment piece of the project is done.

---

## Verification Summary

After all tasks the full unit-test suite passes (Node `assert`, no dependencies):

    cd apps/wall-dashboard && node tests/pure-logic.test.js

Expected: `102 passed, 0 failed`.

Functional verification of the phone widget, JSON route, and OLED polish
happens at the Task 7 user checkpoint — there is no automated test for the
deployed web app, by design.
