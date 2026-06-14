# Nautilus Home Sections & Config — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the launcher's empty lower area with Pinned / Recent / Frequent sections, driven by launch history and a config window.

**Architecture:** Pure logic lives in `src/core/` (config, history, sections); thin I/O wrappers (`src/configStore.js`, `src/historyStore.js`) persist JSON to `data/`; `main.js` wires startup load + IPC + a config `BrowserWindow`; the renderer shows the home view on empty query and a new config page manages settings. Mirrors the existing core/wrapper/main split.

**Tech Stack:** Electron 42, vanilla JS (CommonJS), `node:test`. Zero runtime deps.

**Spec:** `docs/superpowers/specs/2026-06-14-home-sections-and-config-design.md`

**Conventions to follow:**
- Items have shape `{ id, type, title, subtitle, target }`. Types: `app`, `folder`, `site`, `claude`, `calc`.
- History/pinned key is `` `${type}:${target}` `` (note: folder items use `type: 'folder'`, not the `dir:` id prefix).
- Run tests with `npm test` (`node --test` discovers `tests/*.test.js`).
- Tests use `node:test` + `node:assert`, temp dirs via `fs.mkdtempSync(path.join(os.tmpdir(), ...))`.
- `'use strict';` at the top of every source file.

---

## File Structure

**Create (pure logic):**
- `src/core/config.js` — defaults, `mergeConfig`, `seedPinned`
- `src/core/history.js` — `record`, `recent`, `frequent`, `keyOf`
- `src/core/sections.js` — `buildHome`

**Create (I/O wrappers):**
- `src/configStore.js` — `loadConfig`, `saveConfig`
- `src/historyStore.js` — `loadHistory`, `saveHistory`

**Create (config window UI):**
- `renderer/config.html`
- `renderer/config.js`

**Create (tests):**
- `tests/config.test.js`, `tests/history.test.js`, `tests/sections.test.js`, `tests/configStore.test.js`, `tests/historyStore.test.js`

**Modify:**
- `main.js` — load config/history on startup, seed on first run, record on launch, new IPC handlers, config window + tray item
- `preload.js` — expose `getHome`, `getConfig`, `saveConfig`, `searchIndex`
- `renderer/app.js` — home view rendering + header-aware navigation
- `renderer/styles.css` — `.section-label` style + config page styles

---

## Task 1: Config module (pure)

**Files:**
- Create: `src/core/config.js`
- Test: `tests/config.test.js`

- [ ] **Step 1: Write the failing tests**

```js
const { test } = require('node:test');
const assert = require('node:assert');
const { DEFAULT_CONFIG, mergeConfig, seedPinned } = require('../src/core/config.js');

test('mergeConfig fills all defaults from empty input', () => {
  const c = mergeConfig({});
  assert.deepStrictEqual(c, DEFAULT_CONFIG);
  assert.strictEqual(c.sections.recent.limit, 5);
  assert.strictEqual(c.sections.pinned.limit, 8);
});

test('mergeConfig keeps valid overrides', () => {
  const c = mergeConfig({ sections: { recent: { enabled: false, typeFilter: 'app', limit: 3 } } });
  assert.deepStrictEqual(c.sections.recent, { enabled: false, typeFilter: 'app', limit: 3 });
  assert.deepStrictEqual(c.sections.frequent, DEFAULT_CONFIG.sections.frequent);
});

test('mergeConfig coerces bad values to defaults', () => {
  const c = mergeConfig({ sections: { recent: { typeFilter: 'bogus', limit: -2 }, frequent: { limit: 1.5 } } });
  assert.strictEqual(c.sections.recent.typeFilter, 'all');
  assert.strictEqual(c.sections.recent.limit, 5);
  assert.strictEqual(c.sections.frequent.limit, 5);
});

test('mergeConfig drops malformed pinned entries and normalizes good ones', () => {
  const c = mergeConfig({ pinned: [
    { type: 'app', title: 'Cursor', target: 'C:\\a\\Cursor.lnk' },
    { type: 'claude', title: 'x', target: 'https://claude.ai' },   // not pinnable
    { type: 'site', target: 'https://github.com' },                // missing title -> defaults to target
    { type: 'folder' },                                            // no target -> dropped
    null,
  ] });
  assert.deepStrictEqual(c.pinned, [
    { type: 'app', title: 'Cursor', subtitle: '', target: 'C:\\a\\Cursor.lnk' },
    { type: 'site', title: 'https://github.com', subtitle: '', target: 'https://github.com' },
  ]);
});

test('mergeConfig is idempotent', () => {
  const once = mergeConfig({ sections: { recent: { limit: 9 } } });
  assert.deepStrictEqual(mergeConfig(once), once);
});

test('seedPinned matches apps by case-insensitive title (exact preferred, then substring)', () => {
  const index = [
    { id: 'a', type: 'app', title: 'Cursor', subtitle: 'Programs', target: 'C:\\Cursor.lnk' },
    { id: 'b', type: 'app', title: 'Microsoft Excel', subtitle: 'Office', target: 'C:\\Excel.lnk' },
    { id: 'c', type: 'folder', title: 'Notepad docs', subtitle: '', target: 'C:\\nd' },
  ];
  const pins = seedPinned(index, ['Cursor', 'Excel', 'Notepad']);
  // Cursor: exact app match; Excel: substring app match; Notepad: no APP match -> skipped
  assert.deepStrictEqual(pins, [
    { type: 'app', title: 'Cursor', subtitle: 'Programs', target: 'C:\\Cursor.lnk' },
    { type: 'app', title: 'Microsoft Excel', subtitle: 'Office', target: 'C:\\Excel.lnk' },
  ]);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/config.test.js`
Expected: FAIL — `Cannot find module '../src/core/config.js'`

- [ ] **Step 3: Implement `src/core/config.js`**

```js
'use strict';

const TYPE_FILTERS = new Set(['all', 'app', 'folder', 'site']);
const PINNABLE = new Set(['app', 'folder', 'site']);
const SEED_NAMES = ['Cursor', 'Notepad', 'Excel'];

const DEFAULT_CONFIG = {
  version: 1,
  sections: {
    pinned: { enabled: true, typeFilter: 'all', limit: 8 },
    recent: { enabled: true, typeFilter: 'all', limit: 5 },
    frequent: { enabled: true, typeFilter: 'all', limit: 5 },
  },
  pinned: [],
};

function mergeSection(part, def) {
  const p = part && typeof part === 'object' ? part : {};
  const limit = Number.isInteger(p.limit) && p.limit >= 0 ? p.limit : def.limit;
  return {
    enabled: typeof p.enabled === 'boolean' ? p.enabled : def.enabled,
    typeFilter: TYPE_FILTERS.has(p.typeFilter) ? p.typeFilter : def.typeFilter,
    limit,
  };
}

function cleanPinned(list) {
  if (!Array.isArray(list)) return [];
  return list
    .filter((e) => e && PINNABLE.has(e.type) && typeof e.target === 'string' && e.target)
    .map((e) => ({
      type: e.type,
      title: typeof e.title === 'string' && e.title ? e.title : e.target,
      subtitle: typeof e.subtitle === 'string' ? e.subtitle : '',
      target: e.target,
    }));
}

function mergeConfig(partial) {
  const p = partial && typeof partial === 'object' ? partial : {};
  const sec = p.sections && typeof p.sections === 'object' ? p.sections : {};
  return {
    version: 1,
    sections: {
      pinned: mergeSection(sec.pinned, DEFAULT_CONFIG.sections.pinned),
      recent: mergeSection(sec.recent, DEFAULT_CONFIG.sections.recent),
      frequent: mergeSection(sec.frequent, DEFAULT_CONFIG.sections.frequent),
    },
    pinned: cleanPinned(p.pinned),
  };
}

// Best-effort first-run pins: exact app-title match first, then substring.
function seedPinned(index, names = SEED_NAMES) {
  const apps = (index || []).filter((i) => i.type === 'app');
  const out = [];
  for (const name of names) {
    const lc = name.toLowerCase();
    const match = apps.find((i) => i.title.toLowerCase() === lc)
      || apps.find((i) => i.title.toLowerCase().includes(lc));
    if (match) out.push({ type: 'app', title: match.title, subtitle: match.subtitle || '', target: match.target });
  }
  return out;
}

module.exports = { DEFAULT_CONFIG, TYPE_FILTERS, PINNABLE, SEED_NAMES, mergeConfig, seedPinned };
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test tests/config.test.js`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/core/config.js tests/config.test.js
git commit -m "feat(nautilus): config defaults, merge/validate, first-run seed"
```

---

## Task 2: History module (pure)

**Files:**
- Create: `src/core/history.js`
- Test: `tests/history.test.js`

- [ ] **Step 1: Write the failing tests**

```js
const { test } = require('node:test');
const assert = require('node:assert');
const { record, recent, frequent, keyOf } = require('../src/core/history.js');

const app = (t, target, title) => ({ id: target, type: t, title, subtitle: '', target });

test('keyOf is type:target', () => {
  assert.strictEqual(keyOf({ type: 'folder', target: 'C:\\x' }), 'folder:C:\\x');
});

test('record creates and increments counts immutably', () => {
  const h0 = { version: 1, items: {} };
  const h1 = record(h0, app('app', 'C:\\a.lnk', 'A'), 1000);
  assert.strictEqual(h1.items['app:C:\\a.lnk'].count, 1);
  assert.strictEqual(h1.items['app:C:\\a.lnk'].lastLaunched, 1000);
  const h2 = record(h1, app('app', 'C:\\a.lnk', 'A'), 2000);
  assert.strictEqual(h2.items['app:C:\\a.lnk'].count, 2);
  assert.strictEqual(h2.items['app:C:\\a.lnk'].lastLaunched, 2000);
  assert.strictEqual(h0.items['app:C:\\a.lnk'], undefined); // h0 untouched
});

test('record ignores non-trackable types and targetless items', () => {
  const h0 = { version: 1, items: {} };
  assert.strictEqual(record(h0, { type: 'claude', target: 'https://claude.ai/new' }, 1), h0);
  assert.strictEqual(record(h0, { type: 'calc', target: '4' }, 1), h0);
  assert.strictEqual(record(h0, { type: 'app', target: '' }, 1), h0);
});

test('recent orders newest-first and respects limit + typeFilter', () => {
  let h = { version: 1, items: {} };
  h = record(h, app('app', 'C:\\a.lnk', 'A'), 100);
  h = record(h, app('site', 'https://s', 'S'), 200);
  h = record(h, app('folder', 'C:\\f', 'F'), 300);
  const all = recent(h, { typeFilter: 'all', limit: 2 });
  assert.deepStrictEqual(all.map((i) => i.title), ['F', 'S']);
  const apps = recent(h, { typeFilter: 'app', limit: 5 });
  assert.deepStrictEqual(apps.map((i) => i.title), ['A']);
});

test('frequent orders by count then lastLaunched, respects limit + filter', () => {
  let h = { version: 1, items: {} };
  h = record(h, app('app', 'C:\\a.lnk', 'A'), 100);
  h = record(h, app('app', 'C:\\a.lnk', 'A'), 110); // A: count 2
  h = record(h, app('app', 'C:\\b.lnk', 'B'), 120); // B: count 1, newer
  h = record(h, app('site', 'https://s', 'S'), 130);
  h = record(h, app('site', 'https://s', 'S'), 140); // S: count 2, newest
  const top = frequent(h, { typeFilter: 'all', limit: 2 });
  assert.deepStrictEqual(top.map((i) => i.title), ['S', 'A']); // both count 2, S newer
  const apps = frequent(h, { typeFilter: 'app', limit: 5 });
  assert.deepStrictEqual(apps.map((i) => i.title), ['A', 'B']);
});

test('recent/frequent return launchable items with id', () => {
  let h = record({ version: 1, items: {} }, app('app', 'C:\\a.lnk', 'A'), 100);
  const [it] = recent(h, { typeFilter: 'all', limit: 1 });
  assert.deepStrictEqual(it, { id: 'app:C:\\a.lnk', type: 'app', title: 'A', subtitle: '', target: 'C:\\a.lnk' });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/history.test.js`
Expected: FAIL — `Cannot find module '../src/core/history.js'`

- [ ] **Step 3: Implement `src/core/history.js`**

```js
'use strict';

const TRACKABLE = new Set(['app', 'folder', 'site']);

function keyOf(item) {
  return `${item.type}:${item.target}`;
}

function record(history, item, now) {
  if (!item || !TRACKABLE.has(item.type) || !item.target) return history;
  const items = { ...(history && history.items) };
  const key = keyOf(item);
  const prev = items[key] || { count: 0 };
  items[key] = {
    type: item.type,
    title: item.title || item.target,
    subtitle: item.subtitle || '',
    target: item.target,
    count: prev.count + 1,
    lastLaunched: now,
  };
  return { version: 1, items };
}

function toItem(rec) {
  return { id: keyOf(rec), type: rec.type, title: rec.title, subtitle: rec.subtitle, target: rec.target };
}

function select(history, sortFn, { typeFilter = 'all', limit = 5 } = {}) {
  const list = Object.values((history && history.items) || {}).sort(sortFn);
  const filtered = typeFilter === 'all' ? list : list.filter((i) => i.type === typeFilter);
  return filtered.slice(0, limit).map(toItem);
}

function recent(history, opts) {
  return select(history, (a, b) => b.lastLaunched - a.lastLaunched, opts);
}

function frequent(history, opts) {
  return select(history, (a, b) => b.count - a.count || b.lastLaunched - a.lastLaunched, opts);
}

module.exports = { record, recent, frequent, keyOf };
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test tests/history.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/history.js tests/history.test.js
git commit -m "feat(nautilus): launch history record + recent/frequent selectors"
```

---

## Task 3: Sections module (pure)

**Files:**
- Create: `src/core/sections.js`
- Test: `tests/sections.test.js`

Note: to keep dedup-then-limit correct, `buildHome` requests `limit + pinnedCount` items from the selectors, removes any that are pinned, then slices to the configured limit.

- [ ] **Step 1: Write the failing tests**

```js
const { test } = require('node:test');
const assert = require('node:assert');
const { buildHome } = require('../src/core/sections.js');
const { record } = require('../src/core/history.js');

const cfg = (over = {}) => ({
  version: 1,
  sections: {
    pinned: { enabled: true, typeFilter: 'all', limit: 8 },
    recent: { enabled: true, typeFilter: 'all', limit: 5 },
    frequent: { enabled: true, typeFilter: 'all', limit: 5 },
    ...over,
  },
  pinned: over.pinned || [],
});

const app = (t, target, title) => ({ id: `${t}:${target}`, type: t, title, subtitle: '', target });

test('buildHome emits headers then items, only for non-empty enabled sections', () => {
  let h = { version: 1, items: {} };
  h = record(h, app('app', 'C:\\a.lnk', 'A'), 100);
  const config = cfg({ pinned: [] });
  const out = buildHome({ config, history: h, index: [] });
  assert.deepStrictEqual(out.map((r) => r.kind === 'header' ? `#${r.label}` : r.item.title),
    ['#Recent', 'A', '#Frequent', 'A']);
});

test('buildHome resolves pinned against the live index, falls back to stored payload', () => {
  const config = {
    version: 1,
    sections: {
      pinned: { enabled: true, typeFilter: 'all', limit: 8 },
      recent: { enabled: false, typeFilter: 'all', limit: 5 },
      frequent: { enabled: false, typeFilter: 'all', limit: 5 },
    },
    pinned: [
      { type: 'app', title: 'Stale', subtitle: '', target: 'C:\\live.lnk' },  // present in index
      { type: 'app', title: 'Gone', subtitle: '', target: 'C:\\gone.lnk' },   // not in index
    ],
  };
  const index = [{ id: 'app:C:\\live.lnk', type: 'app', title: 'Live', subtitle: 'Programs', target: 'C:\\live.lnk' }];
  const out = buildHome({ config, history: { version: 1, items: {} }, index });
  const items = out.filter((r) => r.kind === 'item').map((r) => r.item);
  assert.strictEqual(items[0].title, 'Live');             // live index wins
  assert.strictEqual(items[1].title, 'Gone');             // fallback to stored
  assert.strictEqual(items[1].id, 'app:C:\\gone.lnk');
});

test('buildHome suppresses pinned items from Recent and Frequent', () => {
  let h = { version: 1, items: {} };
  h = record(h, app('app', 'C:\\a.lnk', 'A'), 100); // pinned below
  h = record(h, app('app', 'C:\\b.lnk', 'B'), 200);
  const config = cfg({ pinned: [{ type: 'app', title: 'A', subtitle: '', target: 'C:\\a.lnk' }] });
  const out = buildHome({ config, history: h, index: [] });
  const recentItems = sectionItems(out, 'Recent');
  assert.deepStrictEqual(recentItems.map((i) => i.title), ['B']); // A excluded
});

test('buildHome fills Recent up to limit after removing pinned', () => {
  let h = { version: 1, items: {} };
  for (let i = 0; i < 6; i++) h = record(h, app('app', `C:\\x${i}.lnk`, `X${i}`), 100 + i);
  // pin the two newest so they would otherwise occupy the top of Recent
  const config = cfg({
    recent: { enabled: true, typeFilter: 'all', limit: 3 },
    frequent: { enabled: false, typeFilter: 'all', limit: 5 },
    pinned: [
      { type: 'app', title: 'X5', subtitle: '', target: 'C:\\x5.lnk' },
      { type: 'app', title: 'X4', subtitle: '', target: 'C:\\x4.lnk' },
    ],
  });
  const recentItems = sectionItems(buildHome({ config, history: h, index: [] }), 'Recent');
  assert.deepStrictEqual(recentItems.map((i) => i.title), ['X3', 'X2', 'X1']); // 3 filled, not 1
});

test('buildHome omits a disabled section entirely', () => {
  let h = record({ version: 1, items: {} }, app('app', 'C:\\a.lnk', 'A'), 100);
  const config = cfg({ recent: { enabled: false, typeFilter: 'all', limit: 5 }, pinned: [] });
  const out = buildHome({ config, history: h, index: [] });
  assert.strictEqual(out.find((r) => r.kind === 'header' && r.label === 'Recent'), undefined);
});

test('buildHome on empty everything returns []', () => {
  const config = cfg({ pinned: [] });
  assert.deepStrictEqual(buildHome({ config, history: { version: 1, items: {} }, index: [] }), []);
});

function sectionItems(rows, label) {
  const start = rows.findIndex((r) => r.kind === 'header' && r.label === label);
  if (start === -1) return [];
  const items = [];
  for (let i = start + 1; i < rows.length && rows[i].kind === 'item'; i++) items.push(rows[i].item);
  return items;
}
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/sections.test.js`
Expected: FAIL — `Cannot find module '../src/core/sections.js'`

- [ ] **Step 3: Implement `src/core/sections.js`**

```js
'use strict';

const { recent, frequent } = require('./history.js');

function indexByKey(index) {
  const map = new Map();
  for (const it of index || []) map.set(`${it.type}:${it.target}`, it);
  return map;
}

function resolvePinned(pinned, byKey, { typeFilter, limit }) {
  const out = [];
  for (const entry of pinned) {
    if (typeFilter !== 'all' && entry.type !== typeFilter) continue;
    const key = `${entry.type}:${entry.target}`;
    out.push(byKey.get(key) || { id: key, ...entry });
    if (out.length >= limit) break;
  }
  return out;
}

function pushSection(out, label, items) {
  if (!items.length) return;
  out.push({ kind: 'header', label });
  for (const item of items) out.push({ kind: 'item', item });
}

function buildHome({ config, history, index }) {
  const byKey = indexByKey(index);
  const cfg = config.sections;
  const out = [];
  const pinnedKeys = new Set();

  if (cfg.pinned.enabled) {
    const items = resolvePinned(config.pinned, byKey, cfg.pinned);
    items.forEach((i) => pinnedKeys.add(i.id));
    pushSection(out, 'Pinned', items);
  }

  const headroom = config.pinned.length;

  if (cfg.recent.enabled) {
    const items = recent(history, { typeFilter: cfg.recent.typeFilter, limit: cfg.recent.limit + headroom })
      .filter((i) => !pinnedKeys.has(i.id))
      .slice(0, cfg.recent.limit);
    pushSection(out, 'Recent', items);
  }

  if (cfg.frequent.enabled) {
    const items = frequent(history, { typeFilter: cfg.frequent.typeFilter, limit: cfg.frequent.limit + headroom })
      .filter((i) => !pinnedKeys.has(i.id))
      .slice(0, cfg.frequent.limit);
    pushSection(out, 'Frequent', items);
  }

  return out;
}

module.exports = { buildHome };
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test tests/sections.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/sections.js tests/sections.test.js
git commit -m "feat(nautilus): buildHome assembles Pinned/Recent/Frequent sections"
```

---

## Task 4: Persistence wrappers (I/O)

**Files:**
- Create: `src/configStore.js`, `src/historyStore.js`
- Test: `tests/configStore.test.js`, `tests/historyStore.test.js`

- [ ] **Step 1: Write the failing tests**

`tests/configStore.test.js`:

```js
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { loadConfig, saveConfig } = require('../src/configStore.js');
const { DEFAULT_CONFIG } = require('../src/core/config.js');

function tmp() {
  return path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'nautilus-cfg-')), 'config.json');
}

test('loadConfig returns defaults and existed:false when file is missing', () => {
  const { config, existed } = loadConfig(tmp());
  assert.strictEqual(existed, false);
  assert.deepStrictEqual(config, DEFAULT_CONFIG);
});

test('saveConfig then loadConfig round-trips a merged config', () => {
  const p = tmp();
  saveConfig(p, { sections: { recent: { limit: 2 } }, pinned: [{ type: 'app', title: 'A', target: 'C:\\a.lnk' }] });
  const { config, existed } = loadConfig(p);
  assert.strictEqual(existed, true);
  assert.strictEqual(config.sections.recent.limit, 2);
  assert.strictEqual(config.pinned[0].target, 'C:\\a.lnk');
});

test('loadConfig falls back to defaults on corrupt JSON', () => {
  const p = tmp();
  fs.writeFileSync(p, '{ not json');
  const { config } = loadConfig(p);
  assert.deepStrictEqual(config, DEFAULT_CONFIG);
});
```

`tests/historyStore.test.js`:

```js
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { loadHistory, saveHistory } = require('../src/historyStore.js');

function tmp() {
  return path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'nautilus-hist-')), 'history.json');
}

test('loadHistory returns empty when file missing', () => {
  assert.deepStrictEqual(loadHistory(tmp()), { version: 1, items: {} });
});

test('saveHistory then loadHistory round-trips', () => {
  const p = tmp();
  const h = { version: 1, items: { 'app:C:\\a.lnk': { type: 'app', title: 'A', subtitle: '', target: 'C:\\a.lnk', count: 3, lastLaunched: 9 } } };
  saveHistory(p, h);
  assert.deepStrictEqual(loadHistory(p), h);
});

test('loadHistory falls back to empty on corrupt JSON or bad shape', () => {
  const p = tmp();
  fs.writeFileSync(p, 'garbage');
  assert.deepStrictEqual(loadHistory(p), { version: 1, items: {} });
  fs.writeFileSync(p, '{"items": 5}');
  assert.deepStrictEqual(loadHistory(p), { version: 1, items: {} });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test tests/configStore.test.js tests/historyStore.test.js`
Expected: FAIL — cannot find the store modules

- [ ] **Step 3: Implement the wrappers**

`src/configStore.js`:

```js
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { mergeConfig } = require('./core/config.js');

function loadConfig(filePath, log) {
  try {
    const raw = fs.readFileSync(filePath, 'utf8');
    return { config: mergeConfig(JSON.parse(raw)), existed: true };
  } catch (err) {
    if (err.code !== 'ENOENT' && log) log.error(`config load failed, using defaults: ${err.message}`);
    return { config: mergeConfig({}), existed: false };
  }
}

function saveConfig(filePath, config) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(mergeConfig(config), null, 2));
}

module.exports = { loadConfig, saveConfig };
```

`src/historyStore.js`:

```js
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const EMPTY = () => ({ version: 1, items: {} });

function loadHistory(filePath, log) {
  try {
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    if (data && typeof data.items === 'object' && data.items !== null && !Array.isArray(data.items)) {
      return { version: 1, items: data.items };
    }
    return EMPTY();
  } catch (err) {
    if (err.code !== 'ENOENT' && log) log.error(`history load failed, starting empty: ${err.message}`);
    return EMPTY();
  }
}

function saveHistory(filePath, history) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(history, null, 2));
}

module.exports = { loadHistory, saveHistory };
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test tests/configStore.test.js tests/historyStore.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/configStore.js src/historyStore.js tests/configStore.test.js tests/historyStore.test.js
git commit -m "feat(nautilus): config/history JSON persistence wrappers"
```

---

## Task 5: Wire history + config into main.js

**Files:**
- Modify: `main.js`

This task loads config/history on startup, seeds pins on first run, records launches, and adds the `getHome` / `getConfig` / `saveConfig` / `searchIndex` IPC handlers. (The config window + tray item come in Task 8.)

- [ ] **Step 1: Add requires**

In `main.js`, after the existing `const { createLogger } = require('./src/log.js');` line, add:

```js
const { buildHome } = require('./src/core/sections.js');
const { record } = require('./src/core/history.js');
const { mergeConfig, seedPinned } = require('./src/core/config.js');
const { loadConfig, saveConfig } = require('./src/configStore.js');
const { loadHistory, saveHistory } = require('./src/historyStore.js');
```

- [ ] **Step 2: Add file paths and in-memory state**

After `const log = createLogger(path.join(__dirname, 'data', 'launcher.log'));`, add:

```js
const CONFIG_PATH = path.join(__dirname, 'data', 'config.json');
const HISTORY_PATH = path.join(__dirname, 'data', 'history.json');
```

Inside the `else` block (after `let quitting = false;`), add:

```js
  let config = mergeConfig({});
  let history = { version: 1, items: {} };
```

- [ ] **Step 3: Load config/history + first-run seed at startup**

In `app.whenReady().then(() => { ... })`, immediately after `indexer.start();`, add:

```js
    // Config + history (after the first index is built so the seed can match apps).
    history = loadHistory(HISTORY_PATH, log);
    const loaded = loadConfig(CONFIG_PATH, log);
    config = loaded.config;
    if (!loaded.existed) {
      config = mergeConfig({ ...config, pinned: seedPinned(indexer.getItems()) });
      try { saveConfig(CONFIG_PATH, config); } catch (err) { log.error(`config seed save failed: ${err.message}`); }
      log.info(`First run: seeded ${config.pinned.length} pinned app(s).`);
    }
```

- [ ] **Step 4: Record launches in the launch IPC handler**

Replace the existing `ipcMain.handle('launch', ...)` body with one that records on success:

```js
  ipcMain.handle('launch', async (event, item) => {
    const result = await launchItem(item, { shell, clipboard });
    if (result.ok) {
      hideWindow();
      history = record(history, item, Date.now());
      try { saveHistory(HISTORY_PATH, history); } catch (err) { log.error(`history save failed: ${err.message}`); }
    } else {
      log.error(`Launch failed for ${item.title}: ${result.error}`);
    }
    return result;
  });
```

- [ ] **Step 5: Add the new IPC handlers**

After the `launch` handler, add:

```js
  ipcMain.handle('getHome', async () => {
    const rows = buildHome({ config, history, index: indexer.getItems() });
    const items = await attachIcons(rows.filter((r) => r.kind === 'item').map((r) => r.item));
    let k = 0;
    return rows.map((r) => (r.kind === 'item' ? { kind: 'item', item: items[k++] } : r));
  });

  ipcMain.handle('getConfig', async () => config);

  ipcMain.handle('saveConfig', async (event, incoming) => {
    config = mergeConfig(incoming);
    try { saveConfig(CONFIG_PATH, config); } catch (err) { log.error(`config save failed: ${err.message}`); }
    return config;
  });

  ipcMain.handle('searchIndex', async (event, query) => {
    const { results } = route(query, indexer.getItems());
    return { results: await attachIcons(results) };
  });
```

- [ ] **Step 6: Verify the app boots and tests still pass**

Run: `npm test`
Expected: PASS (existing + new suites)

Run: `npm start`, press the hotkey.
Expected: launcher opens; no crash. (Home rendering arrives in Task 7 — for now the list may still look blank since the renderer hasn't been updated. Confirm no errors in `data/launcher.log` and that `data/config.json` was created with seeded pins.)

- [ ] **Step 7: Commit**

```bash
git add main.js
git commit -m "feat(nautilus): load config/history, seed pins, record launches, home/config IPC"
```

---

## Task 6: Expose new IPC on the preload bridge

**Files:**
- Modify: `preload.js`

- [ ] **Step 1: Add the new methods**

Replace the `contextBridge.exposeInMainWorld('nautilus', { ... })` object with:

```js
contextBridge.exposeInMainWorld('nautilus', {
  search: (query) => ipcRenderer.invoke('search', query),
  launch: (item) => ipcRenderer.invoke('launch', item),
  getHome: () => ipcRenderer.invoke('getHome'),
  getConfig: () => ipcRenderer.invoke('getConfig'),
  saveConfig: (config) => ipcRenderer.invoke('saveConfig', config),
  searchIndex: (query) => ipcRenderer.invoke('searchIndex', query),
  hide: () => ipcRenderer.send('window:hide'),
  onShown: (cb) => ipcRenderer.on('window:shown', cb),
});
```

- [ ] **Step 2: Verify**

Run: `npm test`
Expected: PASS (no test touches preload, but confirm nothing broke).

- [ ] **Step 3: Commit**

```bash
git add preload.js
git commit -m "feat(nautilus): expose getHome/getConfig/saveConfig/searchIndex on bridge"
```

---

## Task 7: Home view in the renderer

**Files:**
- Modify: `renderer/app.js` (full rewrite — adds header-aware rows + home view)
- Modify: `renderer/styles.css` (add `.section-label`)

- [ ] **Step 1: Rewrite `renderer/app.js`**

```js
'use strict';

const queryEl = document.getElementById('query');
const resultsEl = document.getElementById('results');
const errorEl = document.getElementById('error');

let rows = [];          // [{kind:'header',label} | {kind:'item',item}]
let selectedIndex = -1; // index into rows; points at an item, or -1
let errorTimer = null;

const BADGE_LABEL = { app: 'APP', site: 'SITE', folder: 'FOLDER', claude: 'CLAUDE', calc: 'CALC' };

function faviconUrl(target) {
  try {
    return `https://www.google.com/s2/favicons?domain=${new URL(target).hostname}&sz=32`;
  } catch {
    return null;
  }
}

function iconOrBadge(item) {
  const badge = document.createElement('span');
  badge.className = `badge ${item.type}`;
  badge.textContent = BADGE_LABEL[item.type] || '?';

  const src = item.icon || (item.type === 'site' ? faviconUrl(item.target) : null);
  if (!src) return badge;

  const img = document.createElement('img');
  img.className = 'icon';
  img.src = src;
  img.addEventListener('error', () => img.replaceWith(badge));
  return img;
}

function itemIndices() {
  const idxs = [];
  rows.forEach((r, i) => { if (r.kind === 'item') idxs.push(i); });
  return idxs;
}

function selectFirstItem() {
  selectedIndex = rows.findIndex((r) => r.kind === 'item');
}

function moveSelection(delta) {
  const idxs = itemIndices();
  if (!idxs.length) return;
  const pos = idxs.indexOf(selectedIndex);
  const next = pos === -1 ? (delta > 0 ? 0 : idxs.length - 1)
                          : (pos + delta + idxs.length) % idxs.length;
  selectedIndex = idxs[next];
  render();
}

function render() {
  resultsEl.replaceChildren(
    ...rows.map((row, i) => {
      if (row.kind === 'header') {
        const li = document.createElement('li');
        li.className = 'section-label';
        li.textContent = row.label;
        return li;
      }
      const item = row.item;
      const li = document.createElement('li');
      if (i === selectedIndex) li.classList.add('selected');

      const title = document.createElement('span');
      title.className = 'title';
      title.textContent = item.title;

      const subtitle = document.createElement('span');
      subtitle.className = 'subtitle';
      subtitle.textContent = item.subtitle || '';

      li.append(iconOrBadge(item), title, subtitle);
      li.addEventListener('mousemove', () => {
        if (selectedIndex !== i) { selectedIndex = i; render(); }
      });
      li.addEventListener('click', () => launch(item));
      return li;
    })
  );
  const selected = resultsEl.children[selectedIndex];
  if (selected) selected.scrollIntoView({ block: 'nearest' });
}

function flashError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
  clearTimeout(errorTimer);
  errorTimer = setTimeout(() => { errorEl.hidden = true; }, 2500);
}

let seq = 0; // shared between search() and showHome() so stale responses drop

async function search(value) {
  const mine = ++seq;
  const response = await window.nautilus.search(value);
  if (mine !== seq) return;
  rows = response.results.map((item) => ({ kind: 'item', item }));
  selectFirstItem();
  render();
}

async function showHome() {
  const mine = ++seq;
  const home = await window.nautilus.getHome();
  if (mine !== seq) return;
  rows = home;
  selectFirstItem();
  render();
}

function onQueryChanged() {
  if (queryEl.value.trim() === '') showHome();
  else search(queryEl.value);
}

async function launch(item) {
  if (!item) return;
  if (item.type === 'calc' && !item.target) return; // mid-typing — ignore Enter
  const result = await window.nautilus.launch(item);
  if (!result.ok) flashError(`Couldn't launch ${item.title}: ${result.error}`);
}

queryEl.addEventListener('input', onQueryChanged);

queryEl.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown' || (e.key === 'Tab' && !e.shiftKey)) {
    e.preventDefault();
    moveSelection(1);
  } else if (e.key === 'ArrowUp' || (e.key === 'Tab' && e.shiftKey)) {
    e.preventDefault();
    moveSelection(-1);
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const row = rows[selectedIndex];
    if (row && row.kind === 'item') launch(row.item);
  } else if (e.key === 'Escape') {
    e.preventDefault();
    window.nautilus.hide();
  }
});

window.nautilus.onShown(() => {
  queryEl.value = '';
  errorEl.hidden = true;
  showHome();
  requestAnimationFrame(() => queryEl.focus());
});

// Initial focus + home for the first show (window:shown may fire before load).
queryEl.focus();
showHome();
```

- [ ] **Step 2: Add `.section-label` style to `renderer/styles.css`**

Append:

```css
#results li.section-label {
  color: var(--text2, #8a8a99);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 12px 14px 4px;
  cursor: default;
}
#results li.section-label:first-child {
  padding-top: 6px;
}
```

- [ ] **Step 3: Manual verification**

Run: `npm start`, press the hotkey.
Expected:
- Empty box shows `PINNED` (seeded Cursor/Notepad/Excel if found), and once you've launched a few things, `RECENT` / `FREQUENT`.
- Arrow keys / Tab skip the gray section labels and move only between launchable rows.
- Typing replaces the home view with search results; clearing the box brings the home view back.
- Launch something, reopen — it appears under Recent.

- [ ] **Step 4: Commit**

```bash
git add renderer/app.js renderer/styles.css
git commit -m "feat(nautilus): render Pinned/Recent/Frequent home view with header-skipping nav"
```

---

## Task 8: Config window

**Files:**
- Modify: `main.js` (add `createConfigWindow` + tray "Settings…" item)
- Create: `renderer/config.html`, `renderer/config.js`
- Modify: `renderer/styles.css` (config page styles)

- [ ] **Step 1: Add `createConfigWindow` to `main.js`**

After the `createWindow()` function definition, add:

```js
  let configWin = null;
  function createConfigWindow() {
    if (configWin && !configWin.isDestroyed()) { configWin.focus(); return; }
    configWin = new BrowserWindow({
      width: 560,
      height: 640,
      title: 'Nautilus Settings',
      backgroundColor: '#16161e',
      autoHideMenuBar: true,
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });
    configWin.loadFile(path.join(__dirname, 'renderer', 'config.html'));
    configWin.on('closed', () => { configWin = null; });
  }
```

- [ ] **Step 2: Add the tray "Settings…" item**

In the tray `Menu.buildFromTemplate([...])` array, add a `Settings…` item before `Refresh Index`:

```js
      { label: 'Show Nautilus', click: showWindow },
      { label: 'Settings…', click: createConfigWindow },
      { label: 'Refresh Index', click: () => indexer.refresh() },
```

- [ ] **Step 3: Create `renderer/config.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://www.google.com" />
  <title>Nautilus Settings</title>
  <link rel="stylesheet" href="../../../_shared/styles/base.css" />
  <link rel="stylesheet" href="styles.css" />
</head>
<body class="config-body">
  <div id="config">
    <h1>Nautilus Settings</h1>

    <section id="sections-config">
      <h2>Sections</h2>
      <div id="section-rows"></div>
    </section>

    <section id="pinned-config">
      <h2>Pinned</h2>
      <ul id="pinned-list"></ul>
      <input id="pin-search" type="text" placeholder="Search apps, sites, folders to pin…" autocomplete="off" spellcheck="false" />
      <ul id="pin-results"></ul>
    </section>

    <div id="config-footer">
      <span id="save-status"></span>
      <button id="save-btn">Save</button>
    </div>
  </div>
  <script src="config.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create `renderer/config.js`**

```js
'use strict';

const SECTIONS = [
  { key: 'pinned', label: 'Pinned' },
  { key: 'recent', label: 'Recent' },
  { key: 'frequent', label: 'Frequent' },
];
const TYPE_OPTIONS = [
  { value: 'all', label: 'All types' },
  { value: 'app', label: 'Apps' },
  { value: 'folder', label: 'Folders' },
  { value: 'site', label: 'Sites' },
];

let config = null;

const sectionRowsEl = document.getElementById('section-rows');
const pinnedListEl = document.getElementById('pinned-list');
const pinSearchEl = document.getElementById('pin-search');
const pinResultsEl = document.getElementById('pin-results');
const saveBtn = document.getElementById('save-btn');
const saveStatus = document.getElementById('save-status');

function key(entry) { return `${entry.type}:${entry.target}`; }

function renderSections() {
  sectionRowsEl.replaceChildren(...SECTIONS.map(({ key: k, label }) => {
    const cfg = config.sections[k];
    const row = document.createElement('div');
    row.className = 'section-row';

    const enabled = document.createElement('input');
    enabled.type = 'checkbox';
    enabled.checked = cfg.enabled;
    enabled.addEventListener('change', () => { cfg.enabled = enabled.checked; });

    const name = document.createElement('span');
    name.className = 'section-name';
    name.textContent = label;

    const type = document.createElement('select');
    TYPE_OPTIONS.forEach((o) => {
      const opt = document.createElement('option');
      opt.value = o.value; opt.textContent = o.label;
      if (o.value === cfg.typeFilter) opt.selected = true;
      type.append(opt);
    });
    type.addEventListener('change', () => { cfg.typeFilter = type.value; });

    const limit = document.createElement('input');
    limit.type = 'number'; limit.min = '0'; limit.value = cfg.limit;
    limit.className = 'limit-input';
    limit.addEventListener('change', () => {
      const n = parseInt(limit.value, 10);
      cfg.limit = Number.isInteger(n) && n >= 0 ? n : cfg.limit;
      limit.value = cfg.limit;
    });

    const enableLabel = document.createElement('label');
    enableLabel.className = 'enable-label';
    enableLabel.append(enabled, name);

    row.append(enableLabel, type, limit);
    return row;
  }));
}

function renderPinned() {
  pinnedListEl.replaceChildren(...config.pinned.map((entry, i) => {
    const li = document.createElement('li');

    const title = document.createElement('span');
    title.className = 'pin-title';
    title.textContent = entry.title;

    const up = document.createElement('button');
    up.textContent = '↑'; up.disabled = i === 0;
    up.addEventListener('click', () => { swap(i, i - 1); });

    const down = document.createElement('button');
    down.textContent = '↓'; down.disabled = i === config.pinned.length - 1;
    down.addEventListener('click', () => { swap(i, i + 1); });

    const remove = document.createElement('button');
    remove.textContent = '✕';
    remove.addEventListener('click', () => { config.pinned.splice(i, 1); renderPinned(); });

    li.append(title, up, down, remove);
    return li;
  }));
}

function swap(a, b) {
  const p = config.pinned;
  [p[a], p[b]] = [p[b], p[a]];
  renderPinned();
}

let searchSeq = 0;
async function searchToPin(value) {
  if (value.trim() === '') { pinResultsEl.replaceChildren(); return; }
  const mine = ++searchSeq;
  const { results } = await window.nautilus.searchIndex(value);
  if (mine !== searchSeq) return;
  const pinnable = results.filter((r) => ['app', 'folder', 'site'].includes(r.type));
  pinResultsEl.replaceChildren(...pinnable.map((item) => {
    const li = document.createElement('li');
    li.textContent = item.title;
    const already = config.pinned.some((e) => key(e) === `${item.type}:${item.target}`);
    if (already) { li.className = 'pinned-already'; }
    li.addEventListener('click', () => {
      if (config.pinned.some((e) => key(e) === `${item.type}:${item.target}`)) return;
      config.pinned.push({ type: item.type, title: item.title, subtitle: item.subtitle || '', target: item.target });
      renderPinned();
      searchToPin(pinSearchEl.value);
    });
    return li;
  }));
}

pinSearchEl.addEventListener('input', () => searchToPin(pinSearchEl.value));

saveBtn.addEventListener('click', async () => {
  config = await window.nautilus.saveConfig(config);
  renderSections();
  renderPinned();
  saveStatus.textContent = 'Saved';
  setTimeout(() => { saveStatus.textContent = ''; }, 1500);
});

(async function init() {
  config = await window.nautilus.getConfig();
  renderSections();
  renderPinned();
})();
```

- [ ] **Step 5: Add config page styles to `renderer/styles.css`**

Append:

```css
/* ---- config window ---- */
.config-body { background: var(--surface, #16161e); color: var(--text, #e8e8f0); margin: 0; overflow: auto; }
#config { padding: 20px 24px; font-size: 14px; }
#config h1 { font-size: 20px; margin: 0 0 16px; }
#config h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text2, #8a8a99); margin: 20px 0 8px; }
.section-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border, #2a2a35); }
.enable-label { display: flex; align-items: center; gap: 8px; flex: 1; cursor: pointer; }
.section-name { font-size: 15px; }
.section-row select, .section-row input.limit-input,
#pin-search { background: var(--surface2, #20202c); color: var(--text, #e8e8f0); border: 1px solid var(--border, #2a2a35); border-radius: 6px; padding: 6px 8px; outline: none; }
.limit-input { width: 60px; }
#pin-search { width: 100%; margin: 10px 0 6px; font-size: 14px; box-sizing: border-box; }
#pinned-list, #pin-results { list-style: none; margin: 0; padding: 0; }
#pinned-list li { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 8px; }
#pinned-list li:hover { background: var(--surface2, #20202c); }
.pin-title { flex: 1; }
#pinned-list button { background: var(--surface2, #20202c); color: var(--text, #e8e8f0); border: 1px solid var(--border, #2a2a35); border-radius: 6px; width: 28px; height: 28px; cursor: pointer; }
#pinned-list button:disabled { opacity: 0.35; cursor: default; }
#pin-results li { padding: 8px 10px; border-radius: 8px; cursor: pointer; }
#pin-results li:hover { background: var(--surface2, #20202c); }
#pin-results li.pinned-already { color: var(--text2, #8a8a99); cursor: default; }
#config-footer { display: flex; align-items: center; justify-content: flex-end; gap: 12px; margin-top: 24px; }
#save-status { color: var(--green, #3ecf8e); font-size: 13px; }
#save-btn { background: var(--accent, #7c5cff); color: #fff; border: none; border-radius: 8px; padding: 9px 20px; font-size: 14px; cursor: pointer; }
```

- [ ] **Step 6: Manual verification**

Run: `npm start`. Right-click the tray icon → **Settings…**.
Expected:
- A dark settings window opens. Each section has an enable checkbox, a type dropdown, and a limit field, pre-filled from `config.json`.
- The Pinned list shows current pins with ↑/↓/✕ buttons that reorder/remove.
- Typing in the pin search lists pinnable index items; clicking one adds it (already-pinned items are greyed and non-clickable).
- Click **Save**, see "Saved", reopen the launcher → the home view reflects the changes (toggled sections appear/disappear, new pins show).
- Disable a section, save, confirm it's gone from the launcher; re-enable, save, confirm it returns.

- [ ] **Step 7: Commit**

```bash
git add main.js renderer/config.html renderer/config.js renderer/styles.css
git commit -m "feat(nautilus): config window for sections + pinned management"
```

---

## Task 9: Full verification + docs

**Files:**
- Modify: `CLAUDE.md` (document the new behavior, keep under 50 lines)

- [ ] **Step 1: Run the whole test suite**

Run: `npm test`
Expected: PASS — all suites green (config, history, sections, configStore, historyStore + existing).

- [ ] **Step 2: End-to-end smoke test**

Run: `npm start`. Verify the full flow:
- First run (delete `data/config.json` first to simulate): launcher opens with seeded pins under PINNED.
- Launch several apps/sites/folders; reopen → RECENT and FREQUENT populate correctly.
- A pinned item does not also appear under Recent/Frequent.
- Settings → toggle/limit/type changes apply after Save + reopen.
- Typing still searches; calculator and Ask Claude still work.

- [ ] **Step 3: Update `CLAUDE.md` Key Behaviors**

Add a bullet under the `## Key Behaviors` section:

```markdown
- Home view (empty query): Pinned / Recent / Frequent sections from data/config.json + data/history.json. Tray → Settings… opens the config window (toggle sections, set type filter + limit, manage pins). First run seeds Cursor/Notepad/Excel if found.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(nautilus): document home sections + config window"
```

---

## Self-Review Notes

- **Spec coverage:** home view trigger/layout/nav (T7), three sections + per-section enable/type/limit (T1, T3, T8), dedup of pinned from recent/frequent (T3), no tracking of claude/calc (T2), config.json + history.json persistence (T4), first-run seed (T1, T5), config window with search-picker pinning + reorder (T8), record-on-launch (T5), IPC surface (T5, T6), tests for all pure modules + wrappers (T1–T4). All covered.
- **Dedup-then-limit:** handled by requesting `limit + pinnedCount` from selectors, then filtering pinned, then slicing (T3).
- **Type consistency:** `buildHome({config, history, index})` returns `[{kind:'header',label} | {kind:'item',item}]` — consumed identically by the `getHome` IPC handler (T5) and the renderer (T7). `record(history, item, now)`, `recent/frequent(history, {typeFilter, limit})`, `mergeConfig(partial)`, `seedPinned(index, names)`, `loadConfig→{config, existed}` signatures are consistent across tasks.
