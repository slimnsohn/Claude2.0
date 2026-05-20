# Wall Dashboard (HAOS) — Design

Date: 2026-05-19
Supersedes: `2026-05-17-wall-dashboard-design.md` (Google Apps Script architecture)
Project: `apps/wall-dashboard/` (rebuild in place)

## Goal

A single, glanceable TV dashboard for a Fire Stick — four panels: Metra trains, Amtrak trains, NWS weather, Open-Meteo US AQI — for the Northbrook, IL home station. Plus a phone web view and a JSON endpoint feeding an existing iOS Scriptable widget. All served by one Python service running as a native Home Assistant add-on on a Home Assistant Green (HAOS, ARM64).

## Context

The existing `apps/wall-dashboard/` is a Google Apps Script web app backed by a Google Sheet for config. The data-source logic (NWS, Open-Meteo, Amtrak GTFS extraction, Metra realtime) works, but the deploy model (Apps Script + Sheets + public `/exec` URL) is wrong for the target environment. The user runs a Home Assistant Green, wants HAOS to do the heavy lifting, wants one less Google dependency to manage, and wants the TV to point at a LAN URL.

The new architecture replaces GAS+Sheets with a Python+FastAPI service shipped as a native HA add-on. Data sources and visual feel carry over; the runtime, config storage, and deploy mechanism change completely.

## Non-goals

- No public reachability. LAN only. (Nabu Casa / Cloudflare Tunnel / Tailscale deferred — addable later without code changes.)
- No web auth, no user accounts, no rate limiting.
- No database. Pickled dicts and in-memory caches only.
- No Home Assistant REST sensors or template sensors. The TV is the goal; HA sensors can come later.
- No alerting (push/email). User checks the dashboard, not the other way around.
- No theme toggle, no settings UI, no light mode.
- No service worker / offline mode / PWA. Kiosk is always online.
- No WebSockets / SSE. 30-second polling is plenty.
- No pandas, no numpy, no heavy native deps (ARM64 + small image discipline).
- No `network_mode: host`. Default bridge networking.

## Architecture

One Python process. One FastAPI app. One Docker container. One HA add-on. APScheduler runs inside the same process for the weekly Amtrak refresh — no separate worker, no external cron.

```
Fire Stick (Fully Kiosk Browser)
  └─ http://<green-ip>:8765/
                                       │
                                       ▼
                       HA Add-on: wall-dashboard
                       ┌──────────────────────────┐
                       │ FastAPI (uvicorn) :8765  │
                       │  ├─ GET /            HTML │
                       │  ├─ GET /trains      HTML │
                       │  ├─ GET /api/dashboard JSON│
                       │  ├─ GET /api/trains    JSON│
                       │  └─ GET /healthz       JSON│
                       │                          │
                       │ APScheduler              │
                       │  ├─ weekly Amtrak GTFS   │
                       │  └─ daily Metra sched    │
                       │                          │
                       │ Cached HTTP client       │
                       │  ├─ Metra realtime  30s  │
                       │  ├─ NWS weather    15m  │
                       │  └─ Open-Meteo AQI 30m  │
                       └──────────────────────────┘
                                       │
              ┌────────────┬───────────┼──────────────┬────────────────┐
              ▼            ▼           ▼              ▼                ▼
        Metra GTFS-RT  Amtrak GTFS  NWS API     Open-Meteo AQI    (no external deps
        (bearer tok)   (public zip) (User-Agent)  (no auth)         for Amtrak after
                                                                    weekly download)
```

## Repo layout

```
apps/wall-dashboard/
├── .env.example              # template; real .env lives only on the Green
├── .gitignore                # ignores .env, data/, __pycache__
├── README.md                 # rewritten for HAOS deploy
├── pyproject.toml            # deps: httpx, fastapi, uvicorn, pydantic-settings,
│                             #       typer, rich, gtfs-realtime-bindings, apscheduler,
│                             #       jinja2
├── Dockerfile                # base: ghcr.io/home-assistant/aarch64-base-python
├── config.yaml               # HA add-on schema (name, version, ports, options)
├── docker-compose.yml        # for local dev only; HA add-on uses config.yaml at deploy
├── src/wall_dashboard/
│   ├── __init__.py
│   ├── config.py             # pydantic-settings .env loader
│   ├── client.py             # shared httpx client + cached() decorator
│   ├── metra.py              # GTFS-realtime decode
│   ├── amtrak.py             # weekly GTFS pull; Northbrook = Glenview ± 3 min
│   ├── weather.py            # NWS hourly forecast + feels-like calc
│   ├── aqi.py                # Open-Meteo current US AQI
│   ├── stations.py           # stop_id resolver, disambiguation
│   ├── departures.py         # origin → destination logic
│   ├── scheduler.py          # APScheduler lifespan hook
│   ├── cli.py                # typer CLI for manual probing
│   └── web.py                # FastAPI routes + Jinja templates
├── src/wall_dashboard/static/
│   ├── dashboard.css
│   ├── dashboard.js          # no-flicker refresh loop
│   ├── trains.css
│   └── trains.js
├── src/wall_dashboard/templates/
│   ├── dashboard.html        # clean Jinja, no GAS templating
│   └── trains.html
├── scriptable/
│   └── northbrook-trains.js  # iOS widget (copied back from legacy/, URL retargeted)
├── data/                     # gitignored: cached schedule, parsed.pkl
├── tests/
│   ├── test_metra.py
│   ├── test_amtrak.py
│   ├── test_weather_pure.py
│   ├── test_departures.py    # includes DST regression
│   ├── test_stations.py      # Glenview vs Glen of North Glenview disambiguation
│   ├── test_panel_isolation.py  # one source down ≠ blank page
│   └── fixtures/
└── legacy/                   # old GAS code preserved for reference; delete once Python proven
    ├── Code.gs
    ├── Dashboard.html
    ├── Trains.html
    ├── appsscript.json
    └── scriptable/northbrook-trains.js
```

## Process model

- One `uvicorn wall_dashboard.web:app` process, listening on `0.0.0.0:8765`
- APScheduler started as a FastAPI lifespan hook; stops cleanly on shutdown
- All four data-source modules share one `httpx.AsyncClient` instance
- TTL cache lives in-memory in `client.py`; restart clears it (acceptable, cold start re-warms in ~3s)

## Data sources

All four modules implement the same envelope:

```python
def get() -> dict:
    """Returns: {"available": bool, "error": str | None, ...data}"""
```

They never raise. Failures are caught at the module boundary and packaged into the envelope.

### `metra.py` — realtime trains

- Auth: bearer token in `Authorization` header (`config.metra_token`)
- Endpoints: alerts, positions, tripupdates → decoded `gtfs_realtime_pb2.FeedMessage`
- TTL: 30s (matches Metra's own update cadence; docs say no faster)
- Token logging: `token[:4] + "***" + token[-4:]` only — never full

### `amtrak.py` — weekly schedule

- Port of GAS `refreshAmtrakSchedule` + `northbrookMinutes_`
- Downloads Amtrak GTFS zip, extracts `trips.txt` / `stop_times.txt` / `calendar.txt`
- Filters to trains stopping at Glenview (Amtrak does not stop at Northbrook)
- Computes Northbrook pass time:
  - NB (northbound, away from Chicago): Glenview time **+ 3 min**
  - SB (southbound, toward Chicago): Glenview time **− 3 min**
- Persisted as pickled dict in `data/amtrak_schedule.pkl`
- Refreshed weekly by `scheduler.py` (Sunday 03:00 America/Chicago)

### `weather.py` — NWS hourly forecast

- Port of GAS `getWeather_` + `feelsLike_` + `getWeatherWindow_`
- One-time bootstrap: `wall-dashboard bootstrap-nws` CLI command resolves lat/lon → forecast URL, writes it to `.env`
- TTL: 15 min
- Same Rothfusz heat-index / wind-chill formulas as the GAS implementation
- `User-Agent` header from `.env` (NWS terms require a real identifier)

### `aqi.py` — Open-Meteo current US AQI

- Port of GAS `getAqi_` + `aqiInfo_`
- No auth required (chosen over AirNow/PurpleAir specifically for this reason)
- TTL: 30 min
- Same AQI value → `{value, category, level, alert}` tiering as today

### `stations.py` — stop_id resolution

- Function: `resolve_station(name_or_id) -> dict | list[dict]`
- Exact `stop_id` match wins
- Else case-insensitive substring on `stop_name`
- If multiple matches, returns **all of them** — caller disambiguates
- Never silently picks first match (named footgun in spec: Glenview vs. Glen of North Glenview)

### `departures.py` — origin → destination

- `get_next_departures(origin_stop_id, destination_stop_id, limit=4) -> list[Departure]`
- Finds trips serving both stops with `origin.stop_sequence < destination.stop_sequence` (express-aware)
- Applies `calendar.txt` + `calendar_dates.txt` for today's service
- Overlays realtime tripupdate predictions when available
- Falls back to scheduled times when realtime missing (per Metra docs)
- DST-correct via `zoneinfo.ZoneInfo("America/Chicago")`

## API surface

### Pages (HTML)

- `GET /` — TV dashboard, 4 panels
- `GET /trains` — phone-sized trains-only view

### JSON

- `GET /api/dashboard` — single fat endpoint, all four panels in one envelope:
  ```json
  {
    "now_iso": "2026-05-19T18:42:00-05:00",
    "metra":   { "available": true, "northbound": [...], "southbound": [...], "alerts": [...] },
    "amtrak":  { "available": true, "northbound": [...], "southbound": [...] },
    "weather": { "available": true, "current": {...}, "hours": [...] },
    "aqi":     { "available": true, "value": 42, "category": "Good", "level": "ok" }
  }
  ```
- `GET /api/trains` — `metra` + `amtrak` keys only; consumed by phone view and iOS widget
- `GET /api/metra/next?from=<stop>&to=<stop>&limit=4` — ad-hoc
- `GET /api/metra/alerts`, `GET /api/metra/positions` — debug

### Health

- `GET /healthz` — `{"status":"ok"}`

### Why one fat `/api/dashboard` instead of four endpoints

The TV does one fetch per refresh tick, not four. Less code in `dashboard.js`, lower chance of partial-render flicker, and the server warms all caches in parallel inside one handler via `asyncio.gather(return_exceptions=True)`.

### iOS widget contract

`scriptable/northbrook-trains.js` is the existing iOS widget. Currently calls the GAS URL with `?view=trains&format=json`. **Adapt the API's `/api/trains` response shape to match what the widget already consumes** so the widget just needs its base URL constant updated, not its parsing logic.

### Auth

None. LAN-only service. Per spec: "no user accounts, web auth, or rate limiting."

## Display layer

### Template strategy

- Author clean Jinja2 templates from scratch
- Use the existing `Dashboard.html` and `Trains.html` as **visual reference only** for typography, colors, panel positions — do not carry over their structure
- Initial server render passes only `{ now_iso }` so the page has a working clock before the first `/api/dashboard` returns
- `<style>` content lives in `static/dashboard.css`; `<script>` content in `static/dashboard.js`. No inline CSS or JS in templates.

### Refresh loop (no-flicker contract)

`dashboard.js`:
1. `setInterval(refresh, 30_000)` — single tick rate for all panels
2. Inside `refresh()`:
   - `fetch('/api/dashboard')` → JSON
   - Update DOM **text nodes individually** per value — never replace `innerHTML` on any container
   - Toggle CSS classes for state changes (`.delayed`, `.live`, `.unavailable`) — also no `innerHTML`
3. Separate 1-second tick for current-time display, independent of data refresh

### Failure isolation contract

```
Source API → Module → Web handler → JSON envelope → Browser fetch → Panel renderer → DOM
```

| Layer | Contract |
|---|---|
| Module (`metra.py`, etc.) | Never raises. Returns `{available, error, ...data}` envelope. |
| Web handler (`/api/dashboard`) | Calls all four modules in parallel via `asyncio.gather(return_exceptions=True)`. Each result becomes its panel's subtree. Handler never 500s. |
| Browser (`dashboard.js`) | One `renderPanel(name, json)` per panel, each wrapped in try/catch. Render error shows in that panel only. |
| DOM | Per-panel containers, no shared parents that get rewritten. |

There is no global error path. No scenario where one source breaking blanks the page. When a panel goes unavailable, it shows "data unavailable" in its slot — **never stale data** (stale train times mislead a user catching a train).

### Why one 30s tick instead of per-panel cadences

Server-side caching already gives each source its right TTL (Metra 30s, AQI 30m, weather 15m, Amtrak weekly). The browser asks for everything every 30s; the server returns whatever's currently cached. Simpler client, same effective freshness.

## Deployment

### One-time setup on the Green

1. Install the **Advanced SSH & Web Terminal** add-on (HA Settings → Add-ons → Add-on Store; in default catalog, no custom repositories needed).
2. SSH into the Green. Clone the repo into HAOS's local add-ons folder:
   ```bash
   git clone <repo-url> /addons/wall-dashboard
   ```
3. Create `/addons/wall-dashboard/.env` with:
   ```
   METRA_TOKEN=359|...
   NORTHBROOK_STOP_ID=...        # resolved via `wall-dashboard stations northbrook` first
   CUS_STOP_ID=...
   NWS_LAT=42.1275
   NWS_LON=-87.8290
   NWS_USER_AGENT="wall-dashboard help.sohn@gmail.com"
   NWS_FORECAST_HOURLY_URL=      # filled by first `wall-dashboard bootstrap-nws` run
   ```
4. In HA UI: Settings → Add-ons → Add-on Store → **reload** (top-right menu). "Wall Dashboard" appears under "Local add-ons."
5. Click Install → Start. First build takes ~5 min on the Green's ARM64; subsequent rebuilds use layer cache.
6. Fire Stick: install **Fully Kiosk Browser**, start URL `http://<green-ip>:8765/`, enable kiosk mode + boot autostart.

### `config.yaml` (HA add-on schema)

```yaml
name: Wall Dashboard
version: "0.1.0"
slug: wall_dashboard
description: TV dashboard for Northbrook trains, weather, and AQI
arch:
  - aarch64
startup: application
boot: auto
init: false
ports:
  8765/tcp: 8765
ports_description:
  8765/tcp: Web UI and API
map:
  - share:rw
options: {}
schema: {}
```

(Add-on consumes config from `/data/.env` mounted from the user's host file — final mounting details confirmed during implementation against the current HA add-on schema docs.)

### `Dockerfile`

- Base: `ghcr.io/home-assistant/aarch64-base-python:3.11-alpine-3.19` (or current equivalent at implementation time)
- Multi-stage build to keep final image small (<200 MB target)
- `pip install --no-cache-dir`
- Runs as non-root inside container

### Scheduled background work — APScheduler

- **Weekly Amtrak GTFS refresh** (Sunday 03:00 America/Chicago): download zip, parse, pickle to `data/amtrak_schedule.pkl`. Logs success / failure.
- **Daily Metra `published.txt` check** (04:00): re-downloads `schedule.zip` only if the published timestamp changed.

No external cron, no separate worker. `scheduler.py` starts as a FastAPI lifespan hook.

### Day-2 update workflow

1. SSH: `cd /addons/wall-dashboard && git pull`
2. HA UI: Settings → Add-ons → Wall Dashboard → **Rebuild**
3. Watch logs in the add-on's Log tab for the first 30s
4. Fire Stick refreshes on its own every 30s — no kiosk-side action needed

### Logs

stdout/stderr only; no log files. HA add-on UI tails them. `uvicorn --access-log` for HTTP, structured `logging` for module events.

### Restart-on-failure

HA Supervisor manages add-on lifecycle — set `boot: auto` and the add-on restarts on Green reboots. Inside the process, each module's source-API call is wrapped in try/except → returns `{available: false}` envelope. Transient outages don't crash the process; only code bugs do, and Supervisor handles those.

### Backups

The only valuable state is `data/parsed.pkl` and `data/amtrak_schedule.pkl`. Both regenerable from public APIs in <2 minutes. No backups needed.

## Testing

`pytest` + `ruff check`. No CI complexity.

Targeted tests (not exhaustive coverage):

- **`test_departures.py`** — DST regression: a departure across the March/November fold. Asserts wall-clock → UTC conversion is correct.
- **`test_stations.py`** — `resolve_station("Glenview")` returns both Glenview and Glen of North Glenview. Asserts no silent first-match selection.
- **`test_weather_pure.py`** — `feels_like(tempF, humidity, wind)` and `get_weather_window(now, flip, end)` ports of the pure GAS functions; same cases as the existing `tests/pure-logic.test.js`.
- **`test_amtrak.py`** — `northbrook_minutes("18:42", "NB")` → "18:45"; `("18:42", "SB")` → "18:39". Includes minute-rollover edge cases.
- **`test_panel_isolation.py`** — mocks one source raising; asserts `/api/dashboard` returns 200 with that panel's `available: false` and other three populated. Failure-isolation contract made executable.

Fixtures: small binary protobuf samples in `tests/fixtures/` (redacted real API responses).

## Migration path (from existing GAS dashboard)

1. Move existing `apps/wall-dashboard/apps-script/` and `apps/wall-dashboard/scriptable/` into `apps/wall-dashboard/legacy/`.
2. Update `apps/wall-dashboard/CLAUDE.md` and `TODO.md` for the new architecture.
3. Build Python service per layers in the implementation plan.
4. Confirm `/api/trains` JSON shape matches what `northbrook-trains.js` parses; adapt API to match widget (not vice versa).
5. Copy widget back from `legacy/scriptable/` to `apps/wall-dashboard/scriptable/`, update its URL constant.
6. Deploy to Green, point Fire Stick at new URL.
7. Once stable for ~1 week of use, delete `legacy/` and shut down the GAS deployment.

## Open questions deferred to implementation

- Exact HA base image tag (Python version + Alpine version) — pick current LTS at build time.
- Whether to use HA's "ingress" feature to serve the dashboard at `http://<green-ip>:8123/wall-dashboard/` instead of `:8765` — nice integration but adds add-on schema complexity. Default to direct port for v1.
- Final `/api/trains` JSON shape — driven by inspecting existing `northbrook-trains.js` during implementation.
