# Nautilus — Home Sections & Config

**Date:** 2026-06-14
**Status:** Approved design, ready for implementation plan

## Problem

When Nautilus opens with an empty query the panel is blank below the search
box. The launcher should fill that space with useful entry points — the user's
pinned apps, recently launched items, and frequently launched items — and let
the user control what appears via a configuration window.

## Goals

- Show a **home view** below the search box when the query is empty: Pinned,
  Recent, and Frequent sections.
- Let the user **pin** specific apps/folders/sites that always appear.
- Track launch history to drive Recent and Frequent.
- Provide a **config window** to toggle sections, filter each by type, set
  per-section limits, and manage the pinned list.
- First-run convenience: best-effort pre-pin Cursor, Notepad, Excel.

## Non-Goals

- No frequency decay model (plain count + lastLaunched tiebreak). Future work.
- No pinning directly from the launcher (Ctrl+P style). Config window only.
- No live push to the launcher on config change; sections refresh on each open.
- No tile/grid layout for Pinned (layout A — one list — was chosen).

## Behavior

- **Trigger:** the home view renders when the query input is empty. As soon as
  the user types a character, search results replace it (current behavior
  unchanged). Clearing the box returns to the home view.
- **Layout (A):** one scrolling list with uppercase section labels
  (`PINNED`, `RECENT`, `FREQUENT`) followed by their rows. Rows reuse the exact
  styling of search-result rows.
- **Keyboard / mouse nav:** ArrowDown/ArrowUp/Tab move through *launchable rows
  only* — section headers are skipped and are not selectable. Enter launches the
  selected row; clicking a row launches it; mousemove selects the hovered row.
  This mirrors the existing results behavior.
- **Icons:** reuse the existing `attachIcons` path in `main.js` — real app
  icons and the Windows folder icon via `app.getFileIcon`, site favicons via the
  Google favicon service, badge fallback on failure.
- **Empty/disabled:** disabled sections render nothing. An enabled section with
  no items renders nothing (no empty header). If the whole home view is empty
  (e.g. fresh install, no pins resolved, no history), the panel shows just the
  search box, as today.

## Sections

Three section types, each independently configured:

| Section  | Source                                  | Default order            |
|----------|-----------------------------------------|--------------------------|
| Pinned   | user-chosen list in config              | user-defined order       |
| Recent   | launch history, by `lastLaunched` desc  | newest first             |
| Frequent | launch history, by `count` desc         | count desc, lastLaunched tiebreak |

Per-section config fields:

- `enabled` (bool)
- `typeFilter` — one of `all | app | folder | site`
- `limit` (int) — default 5 for Recent/Frequent, 8 for Pinned

Rules:

- An item present in **Pinned** is suppressed from Recent and Frequent (dedup by
  `type:target` key) to avoid showing the same thing twice.
- `claude` and `calc` items are never recorded to history and never appear in
  Recent/Frequent. They can still be pinned only if a real target exists — in
  practice Pinned holds apps/folders/sites.
- Default section order in the home view: Pinned, Recent, Frequent.

## Data & Persistence

Two new JSON files in `data/` (already gitignored, alongside `launcher.log`):

### `config.json`

```json
{
  "version": 1,
  "sections": {
    "pinned":   { "enabled": true, "typeFilter": "all", "limit": 8 },
    "recent":   { "enabled": true, "typeFilter": "all", "limit": 5 },
    "frequent": { "enabled": true, "typeFilter": "all", "limit": 5 }
  },
  "pinned": [
    { "type": "app", "title": "Cursor", "subtitle": "", "target": "C:\\...\\Cursor.lnk" }
  ]
}
```

- Each pinned entry stores enough to render and launch (`type`, `title`,
  `subtitle`, `target`) so it survives reindex even if the live index is briefly
  unavailable.

### `history.json`

```json
{
  "version": 1,
  "items": {
    "app:C:\\...\\Cursor.lnk": {
      "type": "app", "title": "Cursor", "subtitle": "",
      "target": "C:\\...\\Cursor.lnk",
      "count": 12, "lastLaunched": 1750000000000
    }
  }
}
```

- Keyed by `type:target`. Updated on every **successful** launch of a trackable
  item (apps/folders/sites). `lastLaunched` is epoch ms.

### First-run seed

If `config.json` does not exist on startup, build the default config and
attempt to pin **Cursor, Notepad, Excel** by matching the live index (case-
insensitive title match against indexed apps). Whatever is not found is silently
skipped. The seeded config is then written so it never re-seeds.

## Architecture

Follows the existing split: pure logic in `src/core/`, I/O wrappers in `src/`,
wiring in `main.js`, IPC surface in `preload.js`.

### New pure modules (`src/core/`)

- **`config.js`** — `DEFAULT_CONFIG`, `mergeConfig(partial)` that validates and
  fills defaults (clamps limits ≥ 0, coerces unknown `typeFilter` to `all`,
  drops malformed pinned entries).
- **`history.js`**
  - `record(history, item, now)` → new history object (immutable update):
    increments `count`, sets `lastLaunched`, refreshes title/subtitle. Returns
    history unchanged for non-trackable types.
  - `recent(history, { typeFilter, limit })` → array of items, newest first.
  - `frequent(history, { typeFilter, limit })` → array, count desc then
    lastLaunched desc.
- **`sections.js`** — `buildHome({ config, history, index })` → ordered array of
  renderable entries. Resolves pinned entries (prefers the live indexed item by
  `type:target` for fresh icon/title, falls back to the stored payload),
  applies type filters and limits, dedups Recent/Frequent against Pinned, omits
  disabled/empty sections. Output is a flat list of `{ kind: 'header', label }`
  and `{ kind: 'item', item }` entries so the renderer can render and the nav
  logic can skip headers.

### New I/O wrappers (`src/`)

- **`configStore.js`** — `load(path)` (returns merged defaults if missing/
  corrupt, logging a warning), `save(path, config)`. Mirrors `log.js` style.
- **`historyStore.js`** — `load(path)`, `save(path, history)`. Same pattern.

### `main.js` wiring

- On startup: load config (seed on first run), load history.
- New IPC handlers (see below).
- Launch handler: on success, `history.record` + persist (`historyStore.save`).
- New tray item **"Settings…"** opens the config window.
- `createConfigWindow()` — a separate frameless `BrowserWindow` (dark theme,
  resizable, normal show; does **not** hide on blur) loading
  `renderer/config.html`. Single instance (focus existing if already open).

### IPC additions (`preload.js` → `window.nautilus`)

- `getHome()` → `buildHome(...)` result with icons attached (called by the
  renderer on `window:shown` when the query is empty).
- `getConfig()` → current config.
- `saveConfig(cfg)` → validate, persist, return saved config.
- `searchIndex(q)` → reuse `route(q, index)` results (with icons) for the
  pinned picker.

### Renderer changes

- **`app.js`** — on `window:shown` and whenever the query becomes empty, call
  `getHome()` and render the home list; the existing `render()` is extended to
  handle header entries (non-selectable label rows) and selection logic skips
  headers. Typing falls back to the existing search path.
- **`config.html` / `config.js` / shared styles** — the config window UI:
  per-section enabled toggle + type dropdown + limit input, and a Pinned editor
  (search box → results to add, up/down reorder, remove). Save button writes via
  `saveConfig`.

## Data Flow

```
open (empty query) ──▶ getHome() ──▶ buildHome({config, history, index})
                                   └▶ attachIcons ──▶ render home list
type ──▶ search() ──▶ route() ──▶ render results        (unchanged)
launch(item) ──▶ launchItem() ──ok─▶ history.record + historyStore.save
Settings… ──▶ config window ──▶ getConfig / searchIndex / saveConfig
```

## Error Handling

- Missing/corrupt `config.json` or `history.json` → log a warning, fall back to
  defaults / empty; never crash the launcher.
- Pinned target no longer launchable → launch fails through the existing
  `flashError` path; the entry remains until the user removes it.
- Live index unavailable for a pinned item → render from the stored payload.
- `saveConfig` validates input; invalid sections are coerced to defaults rather
  than rejected.

## Testing

Pure modules — full `node:test` coverage:

- **config:** merge fills defaults; clamps/validates limits and typeFilter;
  drops malformed pinned entries; idempotent merge.
- **history:** `record` increments count and updates lastLaunched/title; ignores
  `claude`/`calc`; `recent` orders newest-first and respects typeFilter + limit;
  `frequent` orders by count then lastLaunched and respects filter + limit.
- **sections:** `buildHome` emits correct headers + items; dedups Recent/
  Frequent against Pinned; resolves pinned against index with fallback; omits
  disabled and empty sections; respects limits and ordering.

I/O wrappers — light tests using temp files: load-missing returns defaults,
round-trip save/load, corrupt-file fallback.

## Open Questions

None outstanding. Layout A, separate config window, search-picker pinning,
per-section type filter, and {Pinned, Recent, Frequent} sections all confirmed.
