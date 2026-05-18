# Wall Dashboard — Design Spec

**Date:** 2026-05-17
**Status:** Approved — ready for implementation planning
**Project location:** `apps/wall-dashboard/`

> A glanceable wall-mounted TV dashboard showing local weather and the next 3
> trains through Northbrook, IL. The same backend serves a compact phone widget.
> Runs on an LG C3 OLED via a Fire Stick in kiosk mode, powered on/off by Home
> Assistant (6 AM – 8 PM). Built as a Google Apps Script web app, mirrored to a
> local version-controlled repo.

This document is the design of record. The source brief is
`NEW PROJECT START HERE/Starting MD/WALL_DASHBOARD_SPEC.md`; this spec refines
it with the decisions made during brainstorming.

---

## 1. Goals & Non-Goals

### Goals
- One Apps Script web app exposing **two views** from one `/exec` URL: the TV
  dashboard and a phone widget.
- Current temperature + hourly forecast (temp + precip %) for Glenview, IL.
- Next 3 trains (Metra + Amtrak Hiawatha + Empire Builder) through Northbrook,
  within 30 min for the TV view.
- Time-aware weather window: today's remaining hours through 7 PM, flipping to
  tomorrow 7 AM – 7 PM at 5 PM.
- OLED-safe rendering: dark theme, pixel jitter, no static bright elements.
- Phone widget view at a separate URL param, plus a JSON route.
- Config driven from a Google Sheet.

### Non-Goals
- Freight train data (no reliable API).
- Train direction filtering ("getting stuck" is direction-agnostic).
- User authentication (single-user family network).
- Persistent storage beyond the Sheet.

---

## 2. Build Approach & Division of Labor

**Decided during brainstorming:**

- **Claude builds files; the user deploys.** Claude produces a complete local
  repo (`Code.gs`, `Dashboard.html`, `Trains.html`, `appsscript.json`, README,
  setup docs). The user creates the Google Sheet and Apps Script project and
  pastes the code in / deploys it. No `clasp` automation in the build loop.
- **Hand-held, checkpointed build.** Each step is built, then the user deploys
  and tests it, and both confirm it works before the next step begins.
- **Skeleton-first.** The first priority is de-risking the display pipeline —
  proving a deployed web app renders correctly on the TV through the Fire Stick
  — *before* any data logic is written. Metra realtime is explicitly the lowest
  priority.
- **Amtrak schedule data is user-provided.** The user supplies the real
  Hiawatha + Empire Builder schedule rows (`train_num`, `direction`,
  `glenview_time`, `days`). No schedule data is fabricated.

### Chat-widget exception
Workspace `CLAUDE.md` requires all browser apps to embed the shared chat
widget. The Wall Dashboard is a deliberate, documented exception: it is a
non-interactive glanceable kiosk display with strict OLED-safety constraints —
a chat widget has no place on it. This exception is recorded in the project's
`CLAUDE.md`.

---

## 3. Repo Layout

```
apps/wall-dashboard/
├── CLAUDE.md                    # project rules + chat-widget exception note
├── TODO.md                      # task tracker (manually controlled)
├── README.md                    # setup + deployment guide — the user follows this
├── apps-script/
│   ├── Code.gs                  # routing, API calls, merge logic, protobuf decoder
│   ├── Dashboard.html           # TV view — full screen, dark
│   ├── Trains.html              # phone widget — minimal
│   └── appsscript.json          # Apps Script manifest
├── docs/
│   ├── sheet-setup.md           # exact Config + AmtrakSchedule tab contents to paste
│   └── api-notes.md             # NWS + Metra quirks discovered during build
├── tests/
│   └── pure-logic.test.js       # Node-runnable tests for GAS-independent functions
└── scripts/
    └── find-northbrook-stop.md  # how the Northbrook stop_id was located
```

---

## 4. Architecture

Single Apps Script project attached to a Google Sheet, deployed as a Web App.
`Code.gs` is one file organized into bounded modules, each with one job and a
defined interface.

| Module | Functions | Responsibility |
|---|---|---|
| Routing | `doGet(e)` | Parse `view` param, dispatch, catch all errors |
| Config | `getConfig_()`, `getAmtrakSchedule_()` | Read Sheet tabs into plain objects |
| Weather | `getWeather_()`, `bootstrapNwsUrl_()`, `getWeatherWindow_(now)` | NWS fetch + time-flip window logic |
| Air quality | `getAqi_(config)`, `aqiInfo_(value)` | Open-Meteo AQI fetch + pure category/alert mapping |
| Trains | `getMetraTrains_()`, `getAmtrakTrains_()`, `getCombinedTrains_(windowMin, maxCount, respectHours)` | Per-source fetch + merge/sort/filter |
| Protobuf | `decodeProtobuf_(bytes)`, `parseTripUpdates_(decoded)` | Generic GTFS-RT wire decoder + field mapping |
| Time helpers | `isWithinDisplayHours_(date)`, `nextTrainAfterHours_()`, `formatCountdown_(min)` | Pure date/format helpers |
| Rendering | `renderDashboard_(data)`, `renderTrainsOnly_(data)`, `renderTrainsJson_(data)` | Data objects → output (no fetching inside) |
| Caching | `cachedFetch_(key, ttlSec, fn)` | Wraps every network call via `CacheService` |

### Data flow — dashboard request

```
doGet → getConfig_ → getWeather_ ─────────────┐
                   → getCombinedTrains_(30,3,true)
                        ├─ getMetraTrains_  → cachedFetch_ → decodeProtobuf_ → parseTripUpdates_
                        └─ getAmtrakTrains_ → getAmtrakSchedule_
                   → renderDashboard_(weather, trains) → HtmlOutput
```

The dashboard calls `getCombinedTrains_(30, 3, true)`; the phone widget calls
`getCombinedTrains_(Infinity, 3, false)` — same merge logic, different framing.

---

## 5. Data Sources

### 5.1 Weather — NWS API (no auth)
- One-time: `GET /points/{lat},{lon}` → `properties.forecastHourly` URL, cached
  in the Config sheet (`bootstrapNwsUrl_()`, run once from the editor).
- Each refresh: `GET <forecastHourly URL>` → hourly forecast.
- Glenview, IL: lat `42.0728`, lon `-87.7878`.
- Required header: `User-Agent: WallDashboard/1.0 (help.sohn@gmail.com)`.
- Cache 15 min via `CacheService`.

### 5.2 Metra — GTFS-Realtime API (auth required) — *lowest priority*
- Base: `https://gtfspublic.metrarr.com`, endpoint `/gtfs/public/tripupdates`.
- Auth: `?api_token=YOUR_KEY` query param. Key is held by the user
  (`Starting MD/GTFSAPIREQUEST.txt`) and goes in the Config sheet, never in code.
- Static schedule `https://schedules.metrarail.com/gtfs/schedule.zip` — used
  one-time to locate the Northbrook `stop_id`.
- Filter to `stop_id = NORTHBROOK`, departure within next 30 min. Client polls
  every 60 s; cache 45 s.

**Implementation risk:** the `tripupdates` feed is protobuf binary. Apps Script
has no protobuf library and the build avoids npm bundling. `Code.gs` therefore
needs a minimal hand-rolled protobuf wire-format decoder (varint /
length-delimited / fixed32-64) producing a nested object keyed by field number,
plus a `parseTripUpdates_` mapping of GTFS-RT field numbers to semantics. This
decoder is isolated and unit-tested against captured feed bytes. The approach
is prototyped against the live feed before being committed to. Because Metra is
the lowest-priority step, this risk does not block the skeleton or weather work.

### 5.3 Amtrak Hiawatha + Empire Builder — hardcoded schedule
- No reliable realtime API. Static schedule lives in the `AmtrakSchedule` Sheet
  tab, with rows **provided by the user** (no fabrication).
- Northbrook pass-through computed from Glenview time: **NB +3 min**,
  **SB −3 min**.
- Day-of-week filtering required (`Mo-Fr`, `Sa`, `Su`, `Daily`, `Su-Fr`, etc.).

### 5.4 Air Quality — Open-Meteo Air Quality API (no auth)
- NWS does not provide AQI; Open-Meteo's air-quality API does, free and keyless.
- `GET https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=us_aqi&timezone=America/Chicago`
- Reuses the `nws_lat` / `nws_lon` Config values — no new Sheet rows needed.
- Read `current.us_aqi` (integer, US EPA AQI scale). Cache 30 min.
- `aqiInfo_(value)` is a pure function mapping the value to `{category, level,
  alert}`: ≤50 Good (no alert); 51–100 Moderate (alert); 101–150 Unhealthy for
  Sensitive (alert); 151–200 Unhealthy (alert); 201–300 Very Unhealthy (alert);
  301+ Hazardous (alert). `level` is `good` / `moderate` / `unhealthy` for
  styling.
- Independent failure: if the AQI fetch fails the rest of the dashboard renders
  normally and the AQI element is simply omitted.

---

## 6. Sheet Schema

### Tab: `Config` — two-column key/value, row 1 = headers

| Key | Value |
|---|---|
| `metra_api_token` | (user pastes key) |
| `metra_stop_id` | `NORTHBROOK` (exact id confirmed from GTFS static) |
| `nws_lat` | `42.0728` |
| `nws_lon` | `-87.7878` |
| `nws_forecast_hourly_url` | (cached after `bootstrapNwsUrl_()`) |
| `nws_user_agent` | `WallDashboard/1.0 (help.sohn@gmail.com)` |
| `display_start_hour` | `6` |
| `display_end_hour` | `21` |
| `weather_flip_hour` | `17` |
| `weather_end_hour` | `19` |
| `max_trains` | `3` |
| `train_window_min` | `30` |

### Tab: `AmtrakSchedule` — user-provided rows

| train_num | direction | glenview_time | days |
|---|---|---|---|
| (NB or SB) | (HH:MM 24h) | (e.g. `Mo-Fr`) |

Code handles an empty tab gracefully.

---

## 7. URL Routes

`doGet(e)` parses `e.parameter.view`:

| URL | Returns |
|---|---|
| `<exec>?view=dashboard` | Full TV dashboard HTML |
| `<exec>?view=trains` | Phone widget HTML (trains only) |
| `<exec>?view=trains&format=json` | JSON for programmatic use |
| `<exec>` (no param) | Defaults to dashboard |

---

## 8. TV Dashboard View

1920×1080, dark. Sections: header (location, date, time, AQI), current temp +
condition, hourly weather strip, Northbrook trains list.

**AQI** (under the time, right-aligned):
- Good (≤50) → dim plain text `AQI <n>`, no alert.
- Moderate / Unhealthy / worse (≥51) → an alert pill: `⚠ AQI <n> · <category>`,
  amber for Moderate, red for Unhealthy and above. The pill stays OLED-safe —
  small, thin-bordered, near-black fill, no large bright element.

**Weather window** (`getWeatherWindow_(now)`, pure):
- Before 17:00 → next full hour through 19:00 today.
- 17:00 or later → tomorrow 07:00–19:00.
- Columns auto-flex via CSS Grid `repeat(auto-fit, minmax(...))`.

**Trains section:**
- Next 3 trains merged Metra + Amtrak, sorted by Northbrook pass-through, only
  within next 30 min.
- Format `[type]  [time]  ([countdown])`; countdown `(9 min)` under 60 min,
  `(1h 9m)` at/over 60 min.
- Outside 6 AM–9 PM → `"No train until <time>"`.
- No trains in next 30 min during active hours → `"No train in next 30 min —
  next: <time>"`.

**OLED protection:** background `#0a0a0a`, text `#e0e0e0`, "now" temp accent
`#7ab8ff`. Every 60 min JS applies a 1–3 px random translate to `body`. System
sans, 32–72 px hierarchy.

**Refresh:** `<meta http-equiv="refresh" content="300">` (5 min full reload);
JS interval re-fetches train JSON every 60 s and swaps the DOM without reload.

---

## 9. Phone Widget View

Max-width 380 px, vertical. Always shows the next 3 trains regardless of hour
(no 6 AM–9 PM filter, no 30-min window). Overnight gap → first 3 trains
tomorrow morning. Auto-refresh every 60 s while open. Light background allowed.

`?format=json` returns:
```json
{
  "trains": [
    {"type": "Metra", "time": "12:51 PM", "countdown_min": 9, "countdown_str": "9 min"}
  ],
  "updated_at": "2026-05-17T12:42:00-05:00"
}
```

---

## 10. Caching

`cachedFetch_(key, ttlSec, fn)` wraps every network call via
`CacheService.getScriptCache()`.

| Data | TTL |
|---|---|
| NWS hourly | 15 min |
| Open-Meteo AQI | 30 min |
| Metra realtime | 45 s |
| Config sheet | 5 min |
| Amtrak schedule | 1 hr |

On a fetch failure `cachedFetch_` serves the last good value at a longer
fallback TTL rather than erroring.

---

## 11. Error Handling

Each data source fails independently — no failure may blank the screen.
- `doGet` wraps everything in try/catch; total failure → a minimal
  "Dashboard error — retrying" page that still auto-refreshes.
- Weather fails → trains still render; weather area shows "Weather unavailable".
- AQI fails → the AQI element is omitted; the rest of the dashboard renders.
- Trains fail → weather still renders; trains area shows "Trains unavailable".
- `cachedFetch_` last-good-value fallback absorbs transient API blips.

---

## 12. Testing

Apps Script cannot run a standard test runner, so pure logic is isolated into
GAS-independent functions and exercised by a Node-runnable test file
(`tests/pure-logic.test.js`):
- `getWeatherWindow_` (today→tomorrow flip)
- `aqiInfo_` (AQI value → category / level / alert)
- `formatCountdown_`
- day-of-week parsing
- Northbrook offset (NB +3 / SB −3)
- `decodeProtobuf_` (against captured feed bytes)
- merge/sort/filter inside `getCombinedTrains_`

I/O functions (`getWeather_`, `getMetraTrains_`) are verified manually with
`Logger.log` — each appears as a concrete checkpoint artifact in the build.

---

## 13. Deployment

- Deploy → New deployment → Web app. Execute as **Me**, access **Anyone**.
- During development use the **Test deployment** URL (auto-picks up changes).
- The `/exec` URL is stable across redeployments of the same deployment ID —
  **always reuse the existing deployment ID** so the Fire Stick bookmark in
  Fully Kiosk never breaks.

Home Assistant on/off automation is documented in the source brief and is out
of scope for this build.

---

## 14. Build Order (skeleton-first, checkpointed)

Each step is built by Claude, deployed and tested by the user, and confirmed by
both before the next step begins.

| Step | Deliverable | Verification |
|---|---|---|
| **1** | Bare `Code.gs` + `Dashboard.html` — dark page, hardcoded placeholder weather/trains, OLED-safe styling, `doGet` routing. `appsscript.json`, repo scaffold, setup README. | User deploys as web app, opens `/exec`, points Fully Kiosk on the Fire Stick at it — **confirm it fills the TV correctly**. This proves the display pipeline. |
| **2** | Real weather (NWS) — `bootstrapNwsUrl_`, `getWeather_`, `getWeatherWindow_`, caching. Dashboard weather section live. | Page shows live Glenview temps; verify the 5 PM today→tomorrow flip. |
| **3** | Amtrak trains — `getAmtrakSchedule_`, `getAmtrakTrains_`, day-of-week parsing, Northbrook offset. Trains section (Amtrak only). | Trains section matches the user's schedule for today. |
| **4** | Phone widget view + `?format=json` route. | Loads on the user's phone. |
| **5** | Metra realtime — protobuf decoder, `getMetraTrains_`, `getCombinedTrains_` merge. *(lowest priority)* | Live ETAs at Northbrook; raw feed logged and verified. |
| **6** | OLED polish — pixel jitter, 60 s data refresh, 5 min reload. | 24-hour soak on the TV. |

---

## 15. Acceptance Criteria

1. TV displays the dashboard 6 AM–8 PM, auto on/off via HA.
2. Weather reflects current Glenview conditions, refreshes every 5 min.
3. Hourly window flips today→tomorrow at 5 PM.
4. Trains section shows next 3 within 30 min, merged Metra + Amtrak.
5. Outside 6 AM–9 PM the trains section shows "No train until X".
6. Phone widget loads in under 1 s on mobile data.
7. Phone widget always shows the next 3 trains, ignoring hour restrictions.
8. No detectable OLED burn-in after 30 days.
9. Survives Fire Stick reboot (Fully Kiosk auto-launches).
10. Survives Apps Script redeploy without breaking the Fire Stick URL.

---

## 16. Open Items

- Northbrook Metra `stop_id` — confirmed from GTFS static during Step 5 prep;
  recorded in `docs/sheet-setup.md`.
- Amtrak Northbrook offset (NB +3 / SB −3 min) is an estimate; may be refined
  after observing real passes.
- Phone widget delivery mechanism (iOS Shortcut vs Safari home-screen icon) —
  decided at Step 4.
