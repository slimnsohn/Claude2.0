# House Room Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mobile-first PWA for tracking renovation items room-by-room at the Maple house, using a Property Scout-style swipe carousel.

**Architecture:** Single-file React app (CDN) on GitHub Pages. Google Apps Script Web App as API. Google Sheets as database (Rooms, Items, Categories tabs). Google Drive for room photos (manual upload). Shared-secret auth.

**Tech Stack:** React 18 (CDN), Google Apps Script, Google Sheets, GitHub Pages, PapaParse (not needed — using JSON API instead of CSV)

**Reference:** Property Scout source at `https://github.com/slimnsohn/property-scout` — same carousel/swipe pattern, dark theme, font choices.

**Design Spec:** `docs/superpowers/specs/2026-04-17-house-room-tracker-design.md`

---

## File Structure

```
apps/house-room-tracker/
  index.html            # Single-file React app (all HTML/CSS/JS inline, like Property Scout)
  config.js             # Git-ignored: { API_URL, AUTH_TOKEN }
  config.sample.js      # Committed placeholder
  manifest.json         # PWA manifest
  service-worker.js     # Offline cache for app shell + bootstrap data
  icon-192.png          # PWA icon (generated)
  icon-512.png          # PWA icon (generated)
  CLAUDE.md             # Project context
  TODO.md               # Task checklist
  start.bat             # Local dev launcher
  apps-script/
    Code.gs             # Apps Script source (paste into Google, version-controlled here)
```

Also creates:
```
quick_starts/house-room-tracker_start.bat   # Shortcut launcher
```

---

## Task 1: Scaffold project structure

**Files:**
- Create: `apps/house-room-tracker/CLAUDE.md`
- Create: `apps/house-room-tracker/TODO.md`
- Create: `apps/house-room-tracker/config.sample.js`
- Create: `apps/house-room-tracker/.gitignore`
- Create: `apps/house-room-tracker/start.bat`
- Create: `quick_starts/house-room-tracker_start.bat`

- [ ] **Step 1: Create project directory**

```bash
mkdir -p apps/house-room-tracker/apps-script
```

- [ ] **Step 2: Create CLAUDE.md from template**

```markdown
# House Room Tracker

## Overview
Mobile PWA to track renovation items per room for the Maple house. Swipe carousel of rooms, drill into item checklists, summary/shopping list view.

## Tech Stack
React 18 (CDN, single index.html), Google Apps Script backend, Google Sheets + Drive storage, GitHub Pages hosting.

## Quick Start
```bash
start.bat
```

## Data Model
- **Rooms** (static): room_id, name, floor, photo_url, notes, sort_order
- **Items** (CRUD): item_id, room_id, category, description, status, priority, cost_estimate, cost_actual, vendor, notes, created_at, updated_at
- **Categories** (static): category_name, icon_emoji, default_items

## API Contract
- `GET` → `get_bootstrap` returns `{ rooms, items, categories }`
- `POST` actions: `create_item`, `update_item`, `delete_item`, `bulk_update_items`
- Auth: `X-Auth-Token` header

## Deployment
- Frontend: GitHub Pages (push to main deploys)
- Backend: Apps Script Web App (manual deploy via Editor → Deploy → Manage → new version)
- Sheet: [paste URL after creation]
- Drive folder: [paste URL after creation]

## Conventions
- Never store photos as base64 in sheet cells
- Never commit config.js
- Never rename sheet headers without updating Code.gs column mappings
- Rooms/Items IDs are permanent — never reuse

## Skills & Protocols
- **Security Audit**: `../../_skills/security-audit/SKILL.md`
- **Chat Widget**: `../../_skills/llm-chat-widget/SKILL.md`
- **Deploy**: `../../_skills/deploy/SKILL.md`

## Shared Assets
- Base CSS: `<link rel="stylesheet" href="../../_shared/styles/base.css">`
- Fetch wrapper: `<script src="../../_shared/fetch-wrapper.js"></script>`
- Chat widget: `<script src="../../_skills/llm-chat-widget/dist/chat-widget.js"></script>`
```

- [ ] **Step 3: Create TODO.md**

```markdown
# TODO — House Room Tracker

> Update manually. This file persists across sessions.

## Now

- [ ] Build Apps Script backend (Code.gs)
- [ ] Build frontend (index.html)

## Next

- [ ] PWA setup (manifest, service worker, icons)
- [ ] Dark mode toggle
- [ ] CSV export

## Backlog

- [ ] Offline mutation queue
- [ ] Default room seed on first launch

## Done

-
```

- [ ] **Step 4: Create config.sample.js**

```javascript
// Copy this file to config.js and fill in your values.
// config.js is git-ignored — never commit it.
const CONFIG = {
  API_URL: 'https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec',
  AUTH_TOKEN: 'your-secret-token-here'
};
```

- [ ] **Step 5: Create .gitignore**

```
config.js
```

- [ ] **Step 6: Create start.bat**

Use the scaffold template `start-browser.bat` with `{PROJECT_NAME}` = `House Room Tracker` and `{PROJECT_SLUG}` = `house-room-tracker`. This is a static HTML project so it will use `python -m http.server 8080`.

- [ ] **Step 7: Create quick_starts shortcut**

```bat
@echo off
cd /d "%~dp0..\apps\house-room-tracker"
call start.bat
```

- [ ] **Step 8: Commit**

```bash
git add apps/house-room-tracker/ quick_starts/house-room-tracker_start.bat
git commit -m "feat: scaffold house-room-tracker project"
```

---

## Task 2: Apps Script backend (Code.gs)

**Files:**
- Create: `apps/house-room-tracker/apps-script/Code.gs`

This is the complete backend. It will be pasted into Google Apps Script Editor manually.

- [ ] **Step 1: Write Code.gs with auth middleware**

The script reads from and writes to the bound Google Sheet. Auth via `X-Auth-Token` header checked against Script Property `AUTH_TOKEN`.

```javascript
// ---- Configuration ----
function getSheet(name) {
  return SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
}

function checkAuth(e) {
  var token = '';
  if (e && e.parameter && e.parameter.token) {
    token = e.parameter.token;
  }
  // Also check POST body for token
  if (e && e.postData) {
    try {
      var body = JSON.parse(e.postData.contents);
      if (body.token) token = body.token;
    } catch(err) {}
  }
  var expected = PropertiesService.getScriptProperties().getProperty('AUTH_TOKEN');
  if (token !== expected) {
    return false;
  }
  return true;
}

function jsonResponse(data) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function errorResponse(msg, code) {
  return jsonResponse({ ok: false, error: msg });
}
```

Note: Apps Script Web Apps don't support custom request headers from cross-origin fetches (CORS limitation). The token is passed as a query parameter `?token=xxx` for GET and in the POST JSON body for mutations. This is safe because both URLs are HTTPS.

- [ ] **Step 2: Write doGet — bootstrap endpoint**

```javascript
function doGet(e) {
  if (!checkAuth(e)) return errorResponse('Unauthorized');

  var roomsSheet = getSheet('Rooms');
  var itemsSheet = getSheet('Items');
  var catsSheet = getSheet('Categories');

  var rooms = sheetToObjects(roomsSheet);
  var items = sheetToObjects(itemsSheet);
  var categories = sheetToObjects(catsSheet);

  return jsonResponse({ ok: true, rooms: rooms, items: items, categories: categories });
}

function sheetToObjects(sheet) {
  if (!sheet) return [];
  var data = sheet.getDataRange().getValues();
  if (data.length < 2) return [];
  var headers = data[0].map(function(h) { return h.toString().trim(); });
  var rows = [];
  for (var i = 1; i < data.length; i++) {
    var obj = {};
    for (var j = 0; j < headers.length; j++) {
      var val = data[i][j];
      if (val instanceof Date) {
        val = val.toISOString();
      }
      obj[headers[j]] = val;
    }
    rows.push(obj);
  }
  return rows;
}
```

- [ ] **Step 3: Write doPost — mutation dispatcher**

```javascript
function doPost(e) {
  if (!checkAuth(e)) return errorResponse('Unauthorized');

  var body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch(err) {
    return errorResponse('Invalid JSON');
  }

  var action = body.action;
  switch(action) {
    case 'create_item': return createItem(body);
    case 'update_item': return updateItem(body);
    case 'delete_item': return deleteItem(body);
    case 'bulk_update_items': return bulkUpdateItems(body);
    default: return errorResponse('Unknown action: ' + action);
  }
}
```

- [ ] **Step 4: Write createItem**

```javascript
function createItem(body) {
  var item = body.item;
  if (!item || !item.room_id || !item.description) {
    return errorResponse('Missing required fields: room_id, description');
  }

  var sheet = getSheet('Items');
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var now = new Date().toISOString();

  var row = headers.map(function(h) {
    h = h.toString().trim();
    if (h === 'item_id') return item.item_id || Utilities.getUuid();
    if (h === 'created_at') return now;
    if (h === 'updated_at') return now;
    return item[h] !== undefined ? item[h] : '';
  });

  sheet.appendRow(row);
  return jsonResponse({ ok: true, item_id: row[headers.indexOf('item_id')] });
}
```

- [ ] **Step 5: Write updateItem**

```javascript
function updateItem(body) {
  var itemId = body.item_id;
  var fields = body.fields;
  if (!itemId || !fields) return errorResponse('Missing item_id or fields');

  var sheet = getSheet('Items');
  var data = sheet.getDataRange().getValues();
  var headers = data[0].map(function(h) { return h.toString().trim(); });
  var idCol = headers.indexOf('item_id');
  if (idCol === -1) return errorResponse('item_id column not found');

  for (var i = 1; i < data.length; i++) {
    if (data[i][idCol].toString() === itemId.toString()) {
      for (var key in fields) {
        var col = headers.indexOf(key);
        if (col !== -1 && key !== 'item_id' && key !== 'created_at') {
          sheet.getRange(i + 1, col + 1).setValue(fields[key]);
        }
      }
      // Always update updated_at
      var updCol = headers.indexOf('updated_at');
      if (updCol !== -1) {
        sheet.getRange(i + 1, updCol + 1).setValue(new Date().toISOString());
      }
      return jsonResponse({ ok: true });
    }
  }
  return errorResponse('Item not found: ' + itemId);
}
```

- [ ] **Step 6: Write deleteItem**

```javascript
function deleteItem(body) {
  var itemId = body.item_id;
  if (!itemId) return errorResponse('Missing item_id');

  var sheet = getSheet('Items');
  var data = sheet.getDataRange().getValues();
  var headers = data[0].map(function(h) { return h.toString().trim(); });
  var idCol = headers.indexOf('item_id');
  if (idCol === -1) return errorResponse('item_id column not found');

  for (var i = 1; i < data.length; i++) {
    if (data[i][idCol].toString() === itemId.toString()) {
      sheet.deleteRow(i + 1);
      return jsonResponse({ ok: true });
    }
  }
  return errorResponse('Item not found: ' + itemId);
}
```

- [ ] **Step 7: Write bulkUpdateItems**

```javascript
function bulkUpdateItems(body) {
  var itemIds = body.item_ids;
  var fields = body.fields;
  if (!itemIds || !itemIds.length || !fields) {
    return errorResponse('Missing item_ids or fields');
  }

  var sheet = getSheet('Items');
  var data = sheet.getDataRange().getValues();
  var headers = data[0].map(function(h) { return h.toString().trim(); });
  var idCol = headers.indexOf('item_id');
  if (idCol === -1) return errorResponse('item_id column not found');

  var idSet = {};
  for (var k = 0; k < itemIds.length; k++) {
    idSet[itemIds[k].toString()] = true;
  }

  var updated = 0;
  for (var i = 1; i < data.length; i++) {
    if (idSet[data[i][idCol].toString()]) {
      for (var key in fields) {
        var col = headers.indexOf(key);
        if (col !== -1 && key !== 'item_id' && key !== 'created_at') {
          sheet.getRange(i + 1, col + 1).setValue(fields[key]);
        }
      }
      var updCol = headers.indexOf('updated_at');
      if (updCol !== -1) {
        sheet.getRange(i + 1, updCol + 1).setValue(new Date().toISOString());
      }
      updated++;
    }
  }
  return jsonResponse({ ok: true, updated: updated });
}
```

- [ ] **Step 8: Commit**

```bash
git add apps/house-room-tracker/apps-script/Code.gs
git commit -m "feat: Apps Script backend — bootstrap, CRUD items, auth"
```

---

## Task 3: Frontend — index.html shell + carousel

**Files:**
- Create: `apps/house-room-tracker/index.html`

This is the big task. Single-file React app like Property Scout. We build it in stages within the same file.

- [ ] **Step 1: Write the HTML shell with all meta tags, fonts, and CDN imports**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, user-scalable=no">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="theme-color" content="#0f0f14">
  <meta name="description" content="Maple house renovation tracker">
  <title>Maple Tracker</title>
  <link rel="manifest" href="manifest.json">
  <link rel="apple-touch-icon" href="icon-192.png">
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=DM+Sans:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
```

- [ ] **Step 2: Write all CSS (inline in `<style>` tag)**

Dark theme matching Property Scout. Key sections:

```css
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; overflow: hidden; }
  body {
    background: #0f0f14;
    color: #e6edf3;
    font-family: 'DM Sans', -apple-system, sans-serif;
    -webkit-tap-highlight-color: transparent;
    user-select: none;
    -webkit-user-select: none;
  }

  /* Safe area padding for notches */
  .app {
    height: 100%;
    display: flex;
    flex-direction: column;
    padding-top: env(safe-area-inset-top);
    padding-bottom: env(safe-area-inset-bottom);
  }

  /* Bottom tab bar */
  .tab-bar {
    display: flex;
    background: #1a1a24;
    border-top: 1px solid #2a2a3a;
    padding: 8px 0 calc(8px + env(safe-area-inset-bottom, 0px));
  }
  .tab-bar button {
    flex: 1;
    background: none;
    border: none;
    color: #666;
    font-size: 11px;
    font-family: 'DM Sans', sans-serif;
    padding: 6px 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    cursor: pointer;
  }
  .tab-bar button.active { color: #58a6ff; }
  .tab-bar button .tab-icon { font-size: 20px; }

  /* Carousel */
  .carousel-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    position: relative;
    touch-action: pan-y;
  }
  .room-card {
    width: calc(100vw - 40px);
    max-width: 420px;
    background: #1a1a24;
    border-radius: 20px;
    overflow: hidden;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    transition: transform 0.25s ease, opacity 0.25s ease;
  }
  .room-card .hero {
    width: 100%;
    height: 240px;
    object-fit: cover;
    display: block;
    background: #2a2a3a;
  }
  .room-card .hero-placeholder {
    width: 100%;
    height: 240px;
    background: linear-gradient(135deg, #2a2a3a 0%, #1a1a24 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 48px;
  }
  .room-card .card-body {
    padding: 20px;
  }
  .room-card .room-name {
    font-family: 'Playfair Display', serif;
    font-size: clamp(22px, 5vw, 28px);
    font-weight: 700;
    margin-bottom: 4px;
  }
  .room-card .floor-pill {
    display: inline-block;
    background: #2a2a3a;
    color: #8b949e;
    font-size: 12px;
    font-family: 'DM Mono', monospace;
    padding: 2px 10px;
    border-radius: 12px;
    margin-bottom: 16px;
  }
  .room-card .progress-bar-container {
    background: #2a2a3a;
    border-radius: 6px;
    height: 8px;
    overflow: hidden;
    margin-bottom: 8px;
  }
  .room-card .progress-bar-fill {
    height: 100%;
    background: #3fb950;
    border-radius: 6px;
    transition: width 0.3s ease;
  }
  .room-card .stats {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    font-family: 'DM Mono', monospace;
    color: #8b949e;
  }

  /* Dot indicators */
  .dots {
    display: flex;
    gap: 8px;
    padding: 16px;
    justify-content: center;
  }
  .dots .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #2a2a3a;
    cursor: pointer;
    transition: background 0.2s;
  }
  .dots .dot.active { background: #58a6ff; }

  /* Nav arrows */
  .nav-arrow {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    background: rgba(255,255,255,0.1);
    border: none;
    color: #e6edf3;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    font-size: 18px;
    cursor: pointer;
    z-index: 10;
    backdrop-filter: blur(4px);
  }
  .nav-arrow.left { left: 4px; }
  .nav-arrow.right { right: 4px; }

  /* Room Detail view */
  .room-detail {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .room-detail-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: #1a1a24;
    border-bottom: 1px solid #2a2a3a;
  }
  .room-detail-header .back-btn {
    background: none;
    border: none;
    color: #58a6ff;
    font-size: 24px;
    cursor: pointer;
    padding: 4px;
    min-width: 44px;
    min-height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .room-detail-header .room-title {
    font-family: 'Playfair Display', serif;
    font-size: 20px;
    font-weight: 700;
    flex: 1;
  }
  .room-detail-header .room-floor {
    font-family: 'DM Mono', monospace;
    font-size: 12px;
    color: #8b949e;
  }

  /* Filter bar */
  .filter-bar {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    background: #0f0f14;
  }
  .filter-bar button {
    background: #1a1a24;
    border: 1px solid #2a2a3a;
    color: #8b949e;
    font-family: 'DM Sans', sans-serif;
    font-size: 12px;
    padding: 6px 14px;
    border-radius: 16px;
    white-space: nowrap;
    cursor: pointer;
    min-height: 32px;
  }
  .filter-bar button.active {
    background: #58a6ff;
    border-color: #58a6ff;
    color: #fff;
  }

  /* Item list */
  .item-list {
    flex: 1;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    padding: 0 16px 16px;
  }
  .item-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 12px;
    background: #1a1a24;
    border-radius: 12px;
    margin-bottom: 8px;
    cursor: pointer;
    position: relative;
    overflow: hidden;
  }
  .item-row .checkbox {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    border: 2px solid #3a3a4a;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    cursor: pointer;
    font-size: 14px;
  }
  .item-row .checkbox.checked {
    background: #3fb950;
    border-color: #3fb950;
    color: #fff;
  }
  .item-row .item-content { flex: 1; min-width: 0; }
  .item-row .item-desc {
    font-size: 14px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .item-row .item-desc.completed {
    text-decoration: line-through;
    color: #666;
  }
  .item-row .item-meta {
    display: flex;
    gap: 6px;
    margin-top: 4px;
    font-size: 11px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    background: #2a2a3a;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    color: #8b949e;
  }
  .chip.priority-must { background: #3d1f1f; color: #f85149; }
  .chip.priority-should { background: #3d2e0a; color: #d29922; }
  .chip.priority-nice { background: #1a2e1a; color: #3fb950; }
  .item-row .cost {
    font-family: 'DM Mono', monospace;
    font-size: 13px;
    color: #8b949e;
    flex-shrink: 0;
  }
  .item-row .delete-btn {
    background: #f85149;
    border: none;
    color: #fff;
    width: 32px;
    height: 32px;
    border-radius: 8px;
    font-size: 16px;
    cursor: pointer;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  /* Add item bar */
  .add-item-bar {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    background: #1a1a24;
    border-top: 1px solid #2a2a3a;
  }
  .add-item-bar input {
    flex: 1;
    background: #0f0f14;
    border: 1px solid #2a2a3a;
    color: #e6edf3;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 14px;
    font-family: 'DM Sans', sans-serif;
    min-height: 44px;
  }
  .add-item-bar input::placeholder { color: #555; }
  .add-item-bar select {
    background: #0f0f14;
    border: 1px solid #2a2a3a;
    color: #e6edf3;
    padding: 10px 8px;
    border-radius: 10px;
    font-size: 13px;
    font-family: 'DM Sans', sans-serif;
    min-height: 44px;
  }
  .add-item-bar .add-btn {
    background: #58a6ff;
    border: none;
    color: #fff;
    padding: 10px 16px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    min-height: 44px;
    min-width: 44px;
  }

  /* Summary view */
  .summary-view {
    flex: 1;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    padding: 16px;
  }
  .summary-section {
    margin-bottom: 24px;
  }
  .summary-section h2 {
    font-family: 'Playfair Display', serif;
    font-size: 20px;
    margin-bottom: 12px;
  }
  .summary-section h3 {
    font-size: 14px;
    color: #8b949e;
    margin-bottom: 8px;
    font-weight: 500;
  }
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
    margin-bottom: 20px;
  }
  .stat-card {
    background: #1a1a24;
    border-radius: 12px;
    padding: 16px;
  }
  .stat-card .stat-value {
    font-family: 'DM Mono', monospace;
    font-size: 24px;
    font-weight: 700;
  }
  .stat-card .stat-label {
    font-size: 12px;
    color: #8b949e;
    margin-top: 4px;
  }
  .shopping-list-category {
    margin-bottom: 16px;
  }
  .shopping-list-category .cat-header {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .shopping-list-item {
    padding: 8px 12px;
    background: #1a1a24;
    border-radius: 8px;
    margin-bottom: 4px;
    font-size: 13px;
    display: flex;
    justify-content: space-between;
  }
  .shopping-list-item .room-tag {
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    color: #8b949e;
  }

  /* Export button */
  .export-btn {
    width: 100%;
    background: #1a1a24;
    border: 1px solid #2a2a3a;
    color: #58a6ff;
    padding: 14px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    min-height: 44px;
  }

  /* Settings view */
  .settings-view {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }
  .setting-group {
    margin-bottom: 24px;
  }
  .setting-group h2 {
    font-family: 'Playfair Display', serif;
    font-size: 20px;
    margin-bottom: 12px;
  }
  .setting-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px;
    background: #1a1a24;
    border-radius: 12px;
    margin-bottom: 8px;
  }
  .setting-row .setting-label {
    font-size: 14px;
  }
  .setting-row .setting-value {
    font-family: 'DM Mono', monospace;
    font-size: 13px;
    color: #8b949e;
  }
  .danger-btn {
    width: 100%;
    background: rgba(248, 81, 73, 0.1);
    border: 1px solid #f85149;
    color: #f85149;
    padding: 14px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    min-height: 44px;
  }

  /* Toast */
  .toast {
    position: fixed;
    bottom: 100px;
    left: 50%;
    transform: translateX(-50%);
    background: #1a1a24;
    border: 1px solid #2a2a3a;
    color: #e6edf3;
    padding: 10px 20px;
    border-radius: 12px;
    font-size: 13px;
    z-index: 100;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    animation: toast-in 0.3s ease;
  }
  @keyframes toast-in {
    from { opacity: 0; transform: translateX(-50%) translateY(10px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
  }

  /* Loading skeleton */
  .skeleton {
    background: linear-gradient(90deg, #1a1a24 25%, #2a2a3a 50%, #1a1a24 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 12px;
  }
  @keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  /* Item edit modal */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    backdrop-filter: blur(4px);
    z-index: 50;
    display: flex;
    align-items: flex-end;
    justify-content: center;
  }
  .modal-sheet {
    background: #1a1a24;
    border-radius: 20px 20px 0 0;
    width: 100%;
    max-width: 500px;
    max-height: 80vh;
    overflow-y: auto;
    padding: 24px 20px calc(20px + env(safe-area-inset-bottom, 0px));
  }
  .modal-sheet h2 {
    font-family: 'Playfair Display', serif;
    font-size: 20px;
    margin-bottom: 16px;
  }
  .form-field {
    margin-bottom: 14px;
  }
  .form-field label {
    display: block;
    font-size: 12px;
    color: #8b949e;
    margin-bottom: 4px;
  }
  .form-field input,
  .form-field select,
  .form-field textarea {
    width: 100%;
    background: #0f0f14;
    border: 1px solid #2a2a3a;
    color: #e6edf3;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 14px;
    font-family: 'DM Sans', sans-serif;
    min-height: 44px;
  }
  .form-field textarea { min-height: 80px; resize: vertical; }
  .form-actions {
    display: flex;
    gap: 10px;
    margin-top: 16px;
  }
  .form-actions button {
    flex: 1;
    padding: 12px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    min-height: 44px;
    border: none;
  }
  .btn-primary { background: #58a6ff; color: #fff; }
  .btn-secondary { background: #2a2a3a; color: #e6edf3; }
  .btn-danger { background: #f85149; color: #fff; }
</style>
```

- [ ] **Step 3: Write the JavaScript — config loader, API module, state management**

```html
<script src="config.js"></script>
<script>
const { createElement: h, useState, useEffect, useRef, useCallback } = React;

// ---- API ----
const api = {
  async bootstrap() {
    const res = await fetch(CONFIG.API_URL + '?token=' + encodeURIComponent(CONFIG.AUTH_TOKEN));
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Bootstrap failed');
    return data;
  },
  async post(action, payload) {
    const res = await fetch(CONFIG.API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: JSON.stringify({ ...payload, action, token: CONFIG.AUTH_TOKEN })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || action + ' failed');
    return data;
  },
  createItem(item) { return this.post('create_item', { item }); },
  updateItem(itemId, fields) { return this.post('update_item', { item_id: itemId, fields }); },
  deleteItem(itemId) { return this.post('delete_item', { item_id: itemId }); },
  bulkUpdate(itemIds, fields) { return this.post('bulk_update_items', { item_ids: itemIds, fields }); }
};
```

Note: `Content-Type: text/plain` is used instead of `application/json` to avoid CORS preflight requests. Apps Script Web Apps don't handle OPTIONS requests. The body is still JSON — we just lie about the content type. This is the standard workaround and is safe.

- [ ] **Step 4: Write UUID generator and helpers**

```javascript
function uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

function formatCost(n) {
  if (!n && n !== 0) return '';
  return '$' + Number(n).toLocaleString();
}

function getDriveImageUrl(url) {
  // Convert Drive sharing URL to direct image embed URL
  // Input: https://drive.google.com/file/d/FILE_ID/view?usp=sharing
  // Output: https://drive.google.com/thumbnail?id=FILE_ID&sz=w800
  if (!url) return null;
  var match = url.match(/\/d\/([a-zA-Z0-9_-]+)/);
  if (match) return 'https://drive.google.com/thumbnail?id=' + match[1] + '&sz=w800';
  // Already a direct URL or thumbnail URL
  return url;
}

const CATEGORY_EMOJI = {};
const CATEGORY_DEFAULTS = {};
// Populated from bootstrap data
```

- [ ] **Step 5: Write the RoomCard component (carousel card)**

```javascript
function RoomCard({ room, items, onTap, style }) {
  var roomItems = items.filter(function(it) { return it.room_id === room.room_id; });
  var completed = roomItems.filter(function(it) { return it.status === 'completed'; }).length;
  var total = roomItems.length;
  var pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  var openMust = roomItems.filter(function(it) {
    return it.priority === 'must' && it.status !== 'completed';
  }).length;
  var costRemaining = roomItems
    .filter(function(it) { return it.status !== 'completed'; })
    .reduce(function(sum, it) { return sum + (Number(it.cost_estimate) || 0); }, 0);
  var imgUrl = getDriveImageUrl(room.photo_url);

  return h('div', { className: 'room-card', style: style, onClick: onTap },
    imgUrl
      ? h('img', { className: 'hero', src: imgUrl, alt: room.name, loading: 'lazy' })
      : h('div', { className: 'hero-placeholder' }, room.name.charAt(0)),
    h('div', { className: 'card-body' },
      h('div', { className: 'room-name' }, room.name),
      h('span', { className: 'floor-pill' }, room.floor),
      h('div', { className: 'progress-bar-container' },
        h('div', { className: 'progress-bar-fill', style: { width: pct + '%' } })
      ),
      h('div', { className: 'stats' },
        h('span', null, completed + '/' + total + ' done'),
        openMust > 0 ? h('span', { style: { color: '#f85149' } }, openMust + ' must-do') : null,
        costRemaining > 0 ? h('span', null, formatCost(costRemaining) + ' est.') : null
      )
    )
  );
}
```

- [ ] **Step 6: Write the carousel (App-level) with swipe gestures**

```javascript
function Carousel({ rooms, items, onSelectRoom }) {
  var [idx, setIdx] = useState(0);
  var isDragging = useRef(false);
  var startX = useRef(0);
  var startY = useRef(0);
  var currentX = useRef(0);
  var isHorizontal = useRef(null);
  var [dragOffset, setDragOffset] = useState(0);

  function swipeNav(dir) {
    var next = idx + dir;
    if (next < 0 || next >= rooms.length) return;
    setIdx(next);
  }

  function onPointerDown(e) {
    isDragging.current = true;
    isHorizontal.current = null;
    startX.current = e.clientX || e.touches[0].clientX;
    startY.current = e.clientY || e.touches[0].clientY;
    currentX.current = startX.current;
  }

  function onPointerMove(e) {
    if (!isDragging.current) return;
    var x = e.clientX || e.touches[0].clientX;
    var y = e.clientY || e.touches[0].clientY;
    if (isHorizontal.current === null) {
      var dx = Math.abs(x - startX.current);
      var dy = Math.abs(y - startY.current);
      if (dx > 6 || dy > 6) {
        isHorizontal.current = dx > dy;
        if (!isHorizontal.current) { isDragging.current = false; return; }
      } else { return; }
    }
    e.preventDefault();
    currentX.current = x;
    setDragOffset(x - startX.current);
  }

  function onPointerUp() {
    if (!isDragging.current) return;
    isDragging.current = false;
    var dx = currentX.current - startX.current;
    if (Math.abs(dx) > 60) {
      swipeNav(dx < 0 ? 1 : -1);
    }
    setDragOffset(0);
  }

  useEffect(function() {
    window.addEventListener('mousemove', onPointerMove);
    window.addEventListener('mouseup', onPointerUp);
    window.addEventListener('touchmove', onPointerMove, { passive: false });
    window.addEventListener('touchend', onPointerUp);
    return function() {
      window.removeEventListener('mousemove', onPointerMove);
      window.removeEventListener('mouseup', onPointerUp);
      window.removeEventListener('touchmove', onPointerMove);
      window.removeEventListener('touchend', onPointerUp);
    };
  }, [idx]);

  if (rooms.length === 0) {
    return h('div', { className: 'carousel-container' },
      h('div', { style: { textAlign: 'center', color: '#8b949e', padding: '40px' } },
        h('div', { style: { fontSize: '48px', marginBottom: '16px' } }, '\uD83C\uDFE0'),
        h('div', { style: { fontSize: '16px' } }, 'No rooms yet'),
        h('div', { style: { fontSize: '13px', marginTop: '8px' } }, 'Add rooms in the Google Sheet')
      )
    );
  }

  var cardStyle = {
    transform: 'translateX(' + dragOffset + 'px) rotate(' + (dragOffset * 0.03) + 'deg)',
    opacity: 1 - Math.abs(dragOffset) / 600
  };

  return h('div', { className: 'carousel-container',
    onMouseDown: onPointerDown, onTouchStart: onPointerDown },
    idx > 0 ? h('button', { className: 'nav-arrow left', onClick: function() { swipeNav(-1); } }, '\u2039') : null,
    h(RoomCard, {
      room: rooms[idx],
      items: items,
      style: cardStyle,
      onTap: function() { if (Math.abs(dragOffset) < 5) onSelectRoom(rooms[idx]); }
    }),
    idx < rooms.length - 1 ? h('button', { className: 'nav-arrow right', onClick: function() { swipeNav(1); } }, '\u203A') : null,
    h('div', { className: 'dots' },
      rooms.map(function(r, i) {
        return h('div', {
          key: r.room_id,
          className: 'dot' + (i === idx ? ' active' : ''),
          onClick: function() { setIdx(i); }
        });
      })
    )
  );
}
```

- [ ] **Step 7: Commit carousel progress**

```bash
git add apps/house-room-tracker/index.html
git commit -m "feat: frontend shell — carousel with swipe gestures"
```

---

## Task 4: Frontend — Room Detail view with item CRUD

**Files:**
- Modify: `apps/house-room-tracker/index.html`

- [ ] **Step 1: Write the ItemRow component**

```javascript
function ItemRow({ item, categories, onToggle, onEdit, onDelete }) {
  var isCompleted = item.status === 'completed';
  var emoji = (categories[item.category] || {}).icon_emoji || '\uD83D\uDCE6';
  var priorityClass = item.priority ? 'chip priority-' + item.priority : 'chip';

  return h('div', { className: 'item-row' },
    h('div', {
      className: 'checkbox' + (isCompleted ? ' checked' : ''),
      onClick: function(e) { e.stopPropagation(); onToggle(item); }
    }, isCompleted ? '\u2713' : ''),
    h('div', { className: 'item-content', onClick: function() { onEdit(item); } },
      h('div', { className: 'item-desc' + (isCompleted ? ' completed' : '') }, item.description),
      h('div', { className: 'item-meta' },
        h('span', { className: 'chip' }, emoji + ' ' + (item.category || 'Other')),
        item.priority ? h('span', { className: priorityClass }, item.priority) : null
      )
    ),
    (item.cost_estimate && Number(item.cost_estimate) > 0)
      ? h('span', { className: 'cost' }, formatCost(item.cost_estimate))
      : null,
    h('button', { className: 'delete-btn', onClick: function(e) {
      e.stopPropagation(); onDelete(item);
    } }, '\u00D7')
  );
}
```

- [ ] **Step 2: Write the ItemEditModal component**

```javascript
function ItemEditModal({ item, categories, onSave, onClose }) {
  var [fields, setFields] = useState({
    description: item.description || '',
    category: item.category || 'Other',
    status: item.status || 'not_started',
    priority: item.priority || 'should',
    cost_estimate: item.cost_estimate || '',
    cost_actual: item.cost_actual || '',
    vendor: item.vendor || '',
    notes: item.notes || ''
  });

  function update(key, val) {
    setFields(function(prev) {
      var next = Object.assign({}, prev);
      next[key] = val;
      return next;
    });
  }

  var catNames = Object.keys(categories);

  return h('div', { className: 'modal-overlay', onClick: onClose },
    h('div', { className: 'modal-sheet', onClick: function(e) { e.stopPropagation(); } },
      h('h2', null, 'Edit Item'),
      h('div', { className: 'form-field' },
        h('label', null, 'Description'),
        h('input', { value: fields.description, onChange: function(e) { update('description', e.target.value); } })
      ),
      h('div', { className: 'form-field' },
        h('label', null, 'Category'),
        h('select', { value: fields.category, onChange: function(e) { update('category', e.target.value); } },
          catNames.map(function(c) { return h('option', { key: c, value: c }, (categories[c].icon_emoji || '') + ' ' + c); })
        )
      ),
      h('div', { className: 'form-field' },
        h('label', null, 'Status'),
        h('select', { value: fields.status, onChange: function(e) { update('status', e.target.value); } },
          ['not_started', 'in_progress', 'completed', 'deferred', 'needs_quote'].map(function(s) {
            return h('option', { key: s, value: s }, s.replace(/_/g, ' '));
          })
        )
      ),
      h('div', { className: 'form-field' },
        h('label', null, 'Priority'),
        h('select', { value: fields.priority, onChange: function(e) { update('priority', e.target.value); } },
          ['must', 'should', 'nice'].map(function(p) {
            return h('option', { key: p, value: p }, p);
          })
        )
      ),
      h('div', { style: { display: 'flex', gap: '10px' } },
        h('div', { className: 'form-field', style: { flex: 1 } },
          h('label', null, 'Est. Cost'),
          h('input', { type: 'number', value: fields.cost_estimate, onChange: function(e) { update('cost_estimate', e.target.value); } })
        ),
        h('div', { className: 'form-field', style: { flex: 1 } },
          h('label', null, 'Actual Cost'),
          h('input', { type: 'number', value: fields.cost_actual, onChange: function(e) { update('cost_actual', e.target.value); } })
        )
      ),
      h('div', { className: 'form-field' },
        h('label', null, 'Vendor'),
        h('input', { value: fields.vendor, onChange: function(e) { update('vendor', e.target.value); } })
      ),
      h('div', { className: 'form-field' },
        h('label', null, 'Notes'),
        h('textarea', { value: fields.notes, onChange: function(e) { update('notes', e.target.value); } })
      ),
      h('div', { className: 'form-actions' },
        h('button', { className: 'btn-secondary', onClick: onClose }, 'Cancel'),
        h('button', { className: 'btn-primary', onClick: function() { onSave(fields); } }, 'Save')
      )
    )
  );
}
```

- [ ] **Step 3: Write the RoomDetail component**

```javascript
function RoomDetail({ room, items, categories, onBack, onItemsChanged }) {
  var [filter, setFilter] = useState('all');
  var [editItem, setEditItem] = useState(null);
  var [newDesc, setNewDesc] = useState('');
  var [newCat, setNewCat] = useState('Other');
  var [newPriority, setNewPriority] = useState('should');
  var [toast, setToast] = useState(null);
  var inputRef = useRef(null);

  var roomItems = items
    .filter(function(it) { return it.room_id === room.room_id; })
    .sort(function(a, b) {
      var statusOrder = { not_started: 0, in_progress: 1, needs_quote: 2, deferred: 3, completed: 4 };
      return (statusOrder[a.status] || 0) - (statusOrder[b.status] || 0);
    });

  var filtered = roomItems;
  if (filter === 'open') filtered = roomItems.filter(function(it) { return it.status !== 'completed'; });
  else if (filter === 'done') filtered = roomItems.filter(function(it) { return it.status === 'completed'; });
  else if (filter.startsWith('cat:')) {
    var catName = filter.slice(4);
    filtered = roomItems.filter(function(it) { return it.category === catName; });
  }
  else if (filter === 'must') filtered = roomItems.filter(function(it) { return it.priority === 'must'; });

  function showToast(msg) {
    setToast(msg);
    setTimeout(function() { setToast(null); }, 2500);
  }

  function toggleItem(item) {
    var newStatus = item.status === 'completed' ? 'not_started' : 'completed';
    // Optimistic update
    onItemsChanged(items.map(function(it) {
      return it.item_id === item.item_id ? Object.assign({}, it, { status: newStatus }) : it;
    }));
    api.updateItem(item.item_id, { status: newStatus }).catch(function(err) {
      showToast('Failed to update: ' + err.message);
      onItemsChanged(items); // revert
    });
  }

  function deleteItemHandler(item) {
    // Optimistic delete
    var prev = items.slice();
    onItemsChanged(items.filter(function(it) { return it.item_id !== item.item_id; }));
    showToast('Deleted "' + item.description + '"');
    api.deleteItem(item.item_id).catch(function(err) {
      showToast('Failed to delete: ' + err.message);
      onItemsChanged(prev); // revert
    });
  }

  function addItem() {
    if (!newDesc.trim()) return;
    var item = {
      item_id: uuid(),
      room_id: room.room_id,
      category: newCat,
      description: newDesc.trim(),
      status: 'not_started',
      priority: newPriority,
      cost_estimate: '',
      cost_actual: '',
      vendor: '',
      notes: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };
    // Optimistic add
    onItemsChanged(items.concat([item]));
    setNewDesc('');
    if (inputRef.current) inputRef.current.focus();
    api.createItem(item).catch(function(err) {
      showToast('Failed to add: ' + err.message);
      onItemsChanged(items.filter(function(it) { return it.item_id !== item.item_id; }));
    });
  }

  function saveEdit(fields) {
    var itemId = editItem.item_id;
    // Optimistic update
    onItemsChanged(items.map(function(it) {
      return it.item_id === itemId ? Object.assign({}, it, fields) : it;
    }));
    setEditItem(null);
    api.updateItem(itemId, fields).catch(function(err) {
      showToast('Failed to save: ' + err.message);
      onItemsChanged(items);
    });
  }

  var catNames = Object.keys(categories);
  var completedCount = roomItems.filter(function(it) { return it.status === 'completed'; }).length;

  return h('div', { className: 'room-detail' },
    h('div', { className: 'room-detail-header' },
      h('button', { className: 'back-btn', onClick: onBack }, '\u2190'),
      h('span', { className: 'room-title' }, room.name),
      h('span', { className: 'room-floor' }, room.floor),
      h('span', { style: { fontFamily: "'DM Mono', monospace", fontSize: '13px', color: '#8b949e' } },
        completedCount + '/' + roomItems.length
      )
    ),
    h('div', { className: 'filter-bar' },
      [['all', 'All'], ['open', 'Open'], ['done', 'Done'], ['must', 'Must-Do']].map(function(f) {
        return h('button', {
          key: f[0],
          className: filter === f[0] ? 'active' : '',
          onClick: function() { setFilter(f[0]); }
        }, f[1]);
      }),
      catNames.map(function(c) {
        return h('button', {
          key: 'cat:' + c,
          className: filter === 'cat:' + c ? 'active' : '',
          onClick: function() { setFilter('cat:' + c); }
        }, (categories[c].icon_emoji || '') + ' ' + c);
      })
    ),
    h('div', { className: 'item-list' },
      filtered.length === 0
        ? h('div', { style: { textAlign: 'center', color: '#8b949e', padding: '40px' } },
            h('div', { style: { fontSize: '32px', marginBottom: '12px' } }, '\u2705'),
            h('div', null, filter === 'all' ? 'No items yet \u2014 add one below' : 'No items match this filter')
          )
        : filtered.map(function(item) {
            return h(ItemRow, {
              key: item.item_id,
              item: item,
              categories: categories,
              onToggle: toggleItem,
              onEdit: function(it) { setEditItem(it); },
              onDelete: deleteItemHandler
            });
          })
    ),
    h('div', { className: 'add-item-bar' },
      h('input', {
        ref: inputRef,
        placeholder: 'Add item...',
        value: newDesc,
        onChange: function(e) { setNewDesc(e.target.value); },
        onKeyDown: function(e) { if (e.key === 'Enter') addItem(); }
      }),
      h('select', { value: newCat, onChange: function(e) { setNewCat(e.target.value); } },
        catNames.map(function(c) {
          return h('option', { key: c, value: c }, (categories[c].icon_emoji || '') + ' ' + c);
        })
      ),
      h('select', { value: newPriority, onChange: function(e) { setNewPriority(e.target.value); } },
        ['must', 'should', 'nice'].map(function(p) {
          return h('option', { key: p, value: p }, p);
        })
      ),
      h('button', { className: 'add-btn', onClick: addItem }, '+')
    ),
    editItem ? h(ItemEditModal, {
      item: editItem,
      categories: categories,
      onSave: saveEdit,
      onClose: function() { setEditItem(null); }
    }) : null,
    toast ? h('div', { className: 'toast' }, toast) : null
  );
}
```

- [ ] **Step 4: Commit room detail**

```bash
git add apps/house-room-tracker/index.html
git commit -m "feat: room detail view with item CRUD"
```

---

## Task 5: Frontend — Summary view + CSV export

**Files:**
- Modify: `apps/house-room-tracker/index.html`

- [ ] **Step 1: Write the SummaryView component**

```javascript
function SummaryView({ rooms, items, categories }) {
  var totalItems = items.length;
  var completedItems = items.filter(function(it) { return it.status === 'completed'; }).length;
  var openItems = totalItems - completedItems;
  var totalEstimate = items.reduce(function(s, it) { return s + (Number(it.cost_estimate) || 0); }, 0);
  var costRemaining = items
    .filter(function(it) { return it.status !== 'completed'; })
    .reduce(function(s, it) { return s + (Number(it.cost_estimate) || 0); }, 0);
  var costActual = items
    .filter(function(it) { return it.status === 'completed'; })
    .reduce(function(s, it) { return s + (Number(it.cost_actual) || Number(it.cost_estimate) || 0); }, 0);
  var mustDos = items.filter(function(it) {
    return it.priority === 'must' && it.status !== 'completed';
  }).length;

  // Shopping list: open items grouped by category
  var byCat = {};
  items.filter(function(it) { return it.status !== 'completed'; }).forEach(function(it) {
    var cat = it.category || 'Other';
    if (!byCat[cat]) byCat[cat] = [];
    byCat[cat].push(it);
  });

  // Room name lookup
  var roomMap = {};
  rooms.forEach(function(r) { roomMap[r.room_id] = r.name; });

  function exportCSV() {
    var headers = ['Room', 'Category', 'Description', 'Status', 'Priority', 'Est. Cost', 'Actual Cost', 'Vendor', 'Notes'];
    var csvRows = [headers.join(',')];
    items.forEach(function(it) {
      var row = [
        '"' + (roomMap[it.room_id] || '') + '"',
        '"' + (it.category || '') + '"',
        '"' + (it.description || '').replace(/"/g, '""') + '"',
        it.status || '',
        it.priority || '',
        it.cost_estimate || '',
        it.cost_actual || '',
        '"' + (it.vendor || '').replace(/"/g, '""') + '"',
        '"' + (it.notes || '').replace(/"/g, '""') + '"'
      ];
      csvRows.push(row.join(','));
    });
    var blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'maple-tracker-' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return h('div', { className: 'summary-view' },
    h('div', { className: 'summary-section' },
      h('h2', null, 'Maple Overview'),
      h('div', { className: 'stat-grid' },
        h('div', { className: 'stat-card' },
          h('div', { className: 'stat-value' }, totalItems), h('div', { className: 'stat-label' }, 'Total Items')),
        h('div', { className: 'stat-card' },
          h('div', { className: 'stat-value' }, openItems), h('div', { className: 'stat-label' }, 'Open')),
        h('div', { className: 'stat-card' },
          h('div', { className: 'stat-value', style: { color: '#f85149' } }, mustDos), h('div', { className: 'stat-label' }, 'Must-Do')),
        h('div', { className: 'stat-card' },
          h('div', { className: 'stat-value' }, formatCost(costRemaining)), h('div', { className: 'stat-label' }, 'Est. Remaining'))
      )
    ),
    h('div', { className: 'summary-section' },
      h('h2', null, 'Shopping List'),
      h('div', { style: { fontSize: '13px', color: '#8b949e', marginBottom: '12px' } },
        'Open items grouped by category \u2014 bring this to Home Depot'
      ),
      Object.keys(byCat).sort().map(function(cat) {
        var emoji = (categories[cat] || {}).icon_emoji || '\uD83D\uDCE6';
        return h('div', { key: cat, className: 'shopping-list-category' },
          h('div', { className: 'cat-header' }, emoji + ' ' + cat + ' (' + byCat[cat].length + ')'),
          byCat[cat].map(function(it) {
            return h('div', { key: it.item_id, className: 'shopping-list-item' },
              h('span', null, it.description),
              h('span', { className: 'room-tag' }, roomMap[it.room_id] || '')
            );
          })
        );
      })
    ),
    h('div', { className: 'summary-section' },
      h('h2', null, 'Cost Summary'),
      h('div', { className: 'stat-grid' },
        h('div', { className: 'stat-card' },
          h('div', { className: 'stat-value' }, formatCost(totalEstimate)), h('div', { className: 'stat-label' }, 'Total Estimated')),
        h('div', { className: 'stat-card' },
          h('div', { className: 'stat-value' }, formatCost(costActual)), h('div', { className: 'stat-label' }, 'Spent So Far'))
      )
    ),
    h('div', { className: 'summary-section' },
      h('button', { className: 'export-btn', onClick: exportCSV }, '\uD83D\uDCC4 Export CSV')
    )
  );
}
```

- [ ] **Step 2: Commit summary view**

```bash
git add apps/house-room-tracker/index.html
git commit -m "feat: summary view with shopping list + CSV export"
```

---

## Task 6: Frontend — Settings view + App root component

**Files:**
- Modify: `apps/house-room-tracker/index.html`

- [ ] **Step 1: Write SettingsView component**

```javascript
function SettingsView({ lastSync, onRefresh }) {
  function clearCache() {
    localStorage.removeItem('maple-tracker-data');
    location.reload();
  }

  return h('div', { className: 'settings-view' },
    h('div', { className: 'setting-group' },
      h('h2', null, 'Maple House'),
      h('div', { className: 'setting-row' },
        h('span', { className: 'setting-label' }, 'House'),
        h('span', { className: 'setting-value' }, 'Maple')
      )
    ),
    h('div', { className: 'setting-group' },
      h('h2', null, 'Sync'),
      h('div', { className: 'setting-row' },
        h('span', { className: 'setting-label' }, 'Last synced'),
        h('span', { className: 'setting-value' }, lastSync
          ? new Date(lastSync).toLocaleString()
          : 'Never')
      ),
      h('div', { style: { marginTop: '8px' } },
        h('button', {
          className: 'export-btn',
          onClick: onRefresh
        }, '\uD83D\uDD04 Refresh Data')
      )
    ),
    h('div', { className: 'setting-group' },
      h('h2', null, 'Danger Zone'),
      h('button', { className: 'danger-btn', onClick: clearCache }, 'Clear Local Cache')
    )
  );
}
```

- [ ] **Step 2: Write the main App component that ties everything together**

```javascript
function App() {
  var [tab, setTab] = useState('rooms');
  var [rooms, setRooms] = useState([]);
  var [items, setItems] = useState([]);
  var [categories, setCategories] = useState({});
  var [selectedRoom, setSelectedRoom] = useState(null);
  var [loading, setLoading] = useState(true);
  var [error, setError] = useState(null);
  var [lastSync, setLastSync] = useState(null);

  function loadData() {
    setLoading(true);
    setError(null);
    api.bootstrap().then(function(data) {
      var sortedRooms = (data.rooms || [])
        .filter(function(r) { return !r.archived; })
        .sort(function(a, b) { return (Number(a.sort_order) || 0) - (Number(b.sort_order) || 0); });
      setRooms(sortedRooms);
      setItems(data.items || []);

      // Build categories lookup
      var cats = {};
      (data.categories || []).forEach(function(c) {
        cats[c.category_name] = {
          icon_emoji: c.icon_emoji || '',
          default_items: c.default_items ? c.default_items.split(',').map(function(s) { return s.trim(); }) : []
        };
      });
      setCategories(cats);

      // Cache in localStorage
      var ts = new Date().toISOString();
      localStorage.setItem('maple-tracker-data', JSON.stringify({
        rooms: sortedRooms, items: data.items || [], categories: data.categories || [], lastSync: ts
      }));
      setLastSync(ts);
      setLoading(false);
    }).catch(function(err) {
      // Try cached data
      var cached = localStorage.getItem('maple-tracker-data');
      if (cached) {
        try {
          var c = JSON.parse(cached);
          setRooms(c.rooms || []);
          setItems(c.items || []);
          var cats = {};
          (c.categories || []).forEach(function(cat) {
            cats[cat.category_name] = {
              icon_emoji: cat.icon_emoji || '',
              default_items: cat.default_items ? cat.default_items.split(',').map(function(s) { return s.trim(); }) : []
            };
          });
          setCategories(cats);
          setLastSync(c.lastSync);
          setLoading(false);
          return;
        } catch(e) {}
      }
      setError(err.message);
      setLoading(false);
    });
  }

  useEffect(loadData, []);

  if (loading) {
    return h('div', { className: 'app' },
      h('div', { className: 'carousel-container' },
        h('div', { style: { width: 'calc(100vw - 40px)', maxWidth: '420px' } },
          h('div', { className: 'skeleton', style: { height: '240px', marginBottom: '16px' } }),
          h('div', { className: 'skeleton', style: { height: '24px', width: '60%', marginBottom: '8px' } }),
          h('div', { className: 'skeleton', style: { height: '16px', width: '40%', marginBottom: '16px' } }),
          h('div', { className: 'skeleton', style: { height: '8px', marginBottom: '8px' } })
        )
      )
    );
  }

  if (error) {
    return h('div', { className: 'app' },
      h('div', { className: 'carousel-container' },
        h('div', { style: { textAlign: 'center', color: '#f85149', padding: '40px' } },
          h('div', { style: { fontSize: '48px', marginBottom: '16px' } }, '\u26A0\uFE0F'),
          h('div', { style: { fontSize: '16px' } }, 'Failed to load'),
          h('div', { style: { fontSize: '13px', color: '#8b949e', marginTop: '8px' } }, error),
          h('button', {
            className: 'export-btn',
            style: { marginTop: '20px', maxWidth: '200px' },
            onClick: loadData
          }, 'Retry')
        )
      )
    );
  }

  var content;
  if (tab === 'rooms' && selectedRoom) {
    content = h(RoomDetail, {
      room: selectedRoom,
      items: items,
      categories: categories,
      onBack: function() { setSelectedRoom(null); },
      onItemsChanged: function(newItems) { setItems(newItems); }
    });
  } else if (tab === 'rooms') {
    content = h(Carousel, {
      rooms: rooms,
      items: items,
      onSelectRoom: function(room) { setSelectedRoom(room); }
    });
  } else if (tab === 'summary') {
    content = h(SummaryView, { rooms: rooms, items: items, categories: categories });
  } else if (tab === 'settings') {
    content = h(SettingsView, { lastSync: lastSync, onRefresh: loadData });
  }

  return h('div', { className: 'app' },
    content,
    h('div', { className: 'tab-bar' },
      h('button', {
        className: tab === 'rooms' ? 'active' : '',
        onClick: function() { setTab('rooms'); setSelectedRoom(null); }
      }, h('span', { className: 'tab-icon' }, '\uD83C\uDFE0'), 'Rooms'),
      h('button', {
        className: tab === 'summary' ? 'active' : '',
        onClick: function() { setTab('summary'); }
      }, h('span', { className: 'tab-icon' }, '\uD83D\uDCCB'), 'Summary'),
      h('button', {
        className: tab === 'settings' ? 'active' : '',
        onClick: function() { setTab('settings'); }
      }, h('span', { className: 'tab-icon' }, '\u2699\uFE0F'), 'Settings')
    )
  );
}

// ---- Mount ----
ReactDOM.createRoot(document.getElementById('root')).render(h(App));
</script>
```

After the script, close the HTML:

```html
</body>
</html>
```

Also add `<div id="root"></div>` in the body before the config script.

- [ ] **Step 3: Commit the complete app**

```bash
git add apps/house-room-tracker/index.html
git commit -m "feat: settings view + app root — complete frontend"
```

---

## Task 7: PWA setup — manifest, service worker, icons

**Files:**
- Create: `apps/house-room-tracker/manifest.json`
- Create: `apps/house-room-tracker/service-worker.js`
- Create: `apps/house-room-tracker/icon-192.png` (generated SVG-to-PNG or placeholder)
- Create: `apps/house-room-tracker/icon-512.png`

- [ ] **Step 1: Create manifest.json**

```json
{
  "name": "Maple Tracker",
  "short_name": "Maple",
  "description": "Room-by-room renovation tracker for Maple house",
  "start_url": ".",
  "display": "standalone",
  "background_color": "#0f0f14",
  "theme_color": "#0f0f14",
  "icons": [
    { "src": "icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

- [ ] **Step 2: Create service-worker.js**

```javascript
var CACHE_NAME = 'maple-tracker-v1';
var SHELL_URLS = [
  './',
  './index.html',
  './manifest.json',
  'https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=DM+Sans:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap',
  'https://unpkg.com/react@18/umd/react.production.min.js',
  'https://unpkg.com/react-dom@18/umd/react-dom.production.min.js'
];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(SHELL_URLS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(names) {
      return Promise.all(
        names.filter(function(n) { return n !== CACHE_NAME; })
          .map(function(n) { return caches.delete(n); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(e) {
  // Cache bootstrap responses for offline read-only
  if (e.request.url.includes('script.google.com') && e.request.method === 'GET') {
    e.respondWith(
      fetch(e.request).then(function(res) {
        var clone = res.clone();
        caches.open(CACHE_NAME).then(function(cache) {
          cache.put(e.request, clone);
        });
        return res;
      }).catch(function() {
        return caches.match(e.request);
      })
    );
    return;
  }

  // App shell: cache-first
  e.respondWith(
    caches.match(e.request).then(function(cached) {
      return cached || fetch(e.request);
    })
  );
});
```

- [ ] **Step 3: Create placeholder PWA icons**

Generate simple SVG-based icons. These are inline SVGs converted to PNG via canvas — or just use a solid-color square with the letter M as a placeholder. The user can replace with proper icons later.

Create a small script or just commit placeholder PNGs. For now, create simple 1x1 pixel PNGs as placeholders (the user will replace these).

Actually, use an inline SVG rendered to canvas approach in a tiny HTML helper, or just note that icons need to be created manually. For the plan, create minimal valid PNGs.

- [ ] **Step 4: Register service worker in index.html**

Add before the closing `</body>` tag:

```html
<script>
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('service-worker.js');
  }
</script>
```

- [ ] **Step 5: Commit PWA setup**

```bash
git add apps/house-room-tracker/manifest.json apps/house-room-tracker/service-worker.js apps/house-room-tracker/index.html
git commit -m "feat: PWA manifest + service worker for offline read-only"
```

---

## Task 8: Integration test — verify end-to-end locally

**Files:** None created — this is a verification task.

- [ ] **Step 1: Create config.js for local testing**

Copy `config.sample.js` to `config.js` and fill in the actual Apps Script URL and token. (This is done by the user after they set up the Google Sheet and deploy Apps Script.)

- [ ] **Step 2: Start local server**

```bash
cd apps/house-room-tracker && python -m http.server 8080
```

- [ ] **Step 3: Open in browser and verify**

Open `http://localhost:8080` and verify:
1. Loading skeleton appears
2. Bootstrap data loads (or shows error with retry if config not set)
3. Room carousel renders with swipe
4. Tapping a room shows item list
5. Adding an item works
6. Toggling item status works
7. Deleting an item works
8. Summary view shows shopping list and stats
9. CSV export downloads a valid file
10. Settings shows sync time and refresh works

- [ ] **Step 4: Test on mobile**

Open `http://<local-ip>:8080` on phone (same network). Verify:
1. Swipe gestures work
2. Tap targets are large enough
3. Add item keyboard doesn't obscure input
4. Bottom tab bar respects safe area

- [ ] **Step 5: Final commit with any fixes**

```bash
git add -A apps/house-room-tracker/
git commit -m "fix: integration test fixes"
```

---

## Google Sheet Setup Guide (for the user)

This is not a code task — these are the manual steps the user follows:

1. **Create new Google Sheet** named "Maple Tracker"
2. **Create tab "Rooms"** with headers: `room_id | name | floor | photo_url | notes | sort_order`
3. **Create tab "Items"** with headers: `item_id | room_id | category | description | status | priority | cost_estimate | cost_actual | vendor | notes | created_at | updated_at`
4. **Create tab "Categories"** with headers: `category_name | icon_emoji | default_items`
5. **Seed Categories** with the 11 rows from the design spec
6. **Add rooms** — e.g.: `kitchen | Kitchen | 1st | [drive-url] | | 1`
7. **Open Extensions → Apps Script**, paste `Code.gs` contents
8. **Project Settings → Script Properties**: add `AUTH_TOKEN` = your chosen secret
9. **Deploy → New deployment → Web app**: Execute as Me, Anyone can access
10. **Copy the deployment URL** to `config.js`
