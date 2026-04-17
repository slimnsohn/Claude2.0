# House Room Tracker — Design Spec

**Date:** 2026-04-17
**Project:** house-room-tracker
**Location:** apps/house-room-tracker
**House:** Maple (single house, no multi-house support)

---

## Overview

A mobile-first PWA for tracking renovation items room-by-room at the Maple house. Built on the Property Scout pattern: React via CDN in a single `index.html`, Google Sheets as the database, Google Apps Script as the API layer, hosted on GitHub Pages.

The app is a **room carousel** (swipe between rooms) with **drill-in item lists** (add/edit/delete checklist items per room). Rooms, photos, and categories are static — set up once in the sheet. Items are the dynamic CRUD layer managed from the phone.

---

## Architecture

```
GitHub Pages (frontend)
  ├── index.html (React via CDN, single file)
  ├── config.js (git-ignored, API URL + auth token)
  └── manifest.json + service-worker.js (PWA)

Google Apps Script (backend API)
  └── Code.gs (Web App deployment)
        ├── doGet → get_bootstrap (JSON dump of all data)
        └── doPost → create_item, update_item, delete_item, bulk_update_items

Google Sheets (database)
  ├── Rooms tab (static, manually maintained)
  ├── Items tab (dynamic, CRUD from app)
  └── Categories tab (static, seeded once)

Google Drive (photos)
  └── Single shared folder, one image per room, manually uploaded
```

---

## Data Model

### Sheet: Rooms (static — edited manually in the sheet)

| Field | Type | Notes |
|---|---|---|
| room_id | string | Slug, e.g., "kitchen", "master-bed" |
| name | string | Display name, e.g., "Kitchen" |
| floor | string | "1st", "2nd", "Basement" |
| photo_url | string | Google Drive public sharing link |
| notes | text | Free-form |
| sort_order | number | Controls carousel order |

### Sheet: Items (dynamic — CRUD from the app)

| Field | Type | Notes |
|---|---|---|
| item_id | string (UUID) | PK, generated client-side |
| room_id | string | FK → Rooms |
| category | string | FK → Categories |
| description | string | "Replace light switch w/ dimmer" |
| status | enum | `not_started` / `in_progress` / `completed` / `deferred` / `needs_quote` |
| priority | enum | `must` / `should` / `nice` |
| cost_estimate | number | Optional |
| cost_actual | number | Optional |
| vendor | string | Contractor/store name |
| notes | text | Optional |
| created_at | ISO datetime | Set on creation |
| updated_at | ISO datetime | Updated on every edit |

### Sheet: Categories (static — seeded once)

| category_name | icon_emoji | default_items |
|---|---|---|
| Electrical | 💡 | Light switches, Outlets, Fixtures, Smoke alarm |
| Plumbing | 🚰 | Faucets, Shut-offs, Drains |
| Flooring | 🪵 | Carpet, Hardwood, Tile, Transitions |
| Paint | 🎨 | Walls, Trim, Ceiling, Touch-ups |
| HVAC | 🌡️ | Vents, Returns, Thermostat |
| Fixtures | 🔩 | Door hardware, Cabinet pulls, Mirrors |
| Appliances | 🍳 | Fridge, Range, Dishwasher, Washer/Dryer |
| Windows/Doors | 🚪 | Blinds, Weatherstrip, Hinges |
| Ceiling | 🪜 | Fan, Texture, Damage |
| Cabinetry | 🗄️ | Doors, Drawers, Shelves |
| Other | 📦 | |

---

## Apps Script API

Single Web App endpoint. `doGet` returns bootstrap data. `doPost` with `action` discriminator for mutations.

### Actions

| Action | Method | Payload | Returns |
|---|---|---|---|
| `get_bootstrap` | GET | — | `{ rooms: [...], items: [...], categories: [...] }` |
| `create_item` | POST | `{ action, item }` | `{ ok: true, item }` |
| `update_item` | POST | `{ action, item_id, fields }` | `{ ok: true }` |
| `delete_item` | POST | `{ action, item_id }` | `{ ok: true }` |
| `bulk_update_items` | POST | `{ action, item_ids, fields }` | `{ ok: true }` |

### Auth

Shared-secret header: `X-Auth-Token`. Stored in:
- Frontend: `config.js` (git-ignored)
- Backend: Apps Script → Project Settings → Script Properties

---

## Frontend Views

### Carousel (default view)

- Property Scout-style swipe carousel — one room card fills the screen
- Each card: hero photo (Drive link), room name, floor pill, progress bar (% items completed), open item count, cost remaining
- Swipe left/right with drag mechanics (60px threshold, rotation + opacity transform)
- Dot indicators, nav arrows as fallback
- Tap card → drill into Room Detail

### Room Detail (drill-in)

- Back button to carousel
- Room name header, photo (smaller), floor
- **Item list**: each row = status checkbox, description, category emoji chip, priority chip, cost
- **Filters**: segmented control — All / Open / Done / By Category / By Priority
- **Add item**: input field + category dropdown + priority picker → submit
- "Add default items" shortcut: pick a category, get its common items pre-populated
- **Edit item**: tap row → inline edit or detail sheet for all fields
- **Delete item**: swipe-left on row, confirm toast with undo
- **Status toggle**: tap checkbox to cycle status, optimistic UI

### Summary (tab)

- Cost rollup by room, by category, by status
- **Shopping list**: all open items grouped by category across all rooms — the killer feature for Home Depot and contractor visits
- Priority breakdown (how many must-dos remain)
- CSV export (generated client-side from in-memory data)

### Settings (tab)

- House name (Maple) / address
- Drive folder link
- Sync status / last sync timestamp
- Dark mode toggle
- Clear local cache

### Navigation

- Bottom tab bar: Rooms (carousel) / Summary / Settings
- Room Detail pushes on top of Rooms tab (back button returns to carousel)

---

## UX Details

- **Optimistic UI**: mutations update locally first, sync to Apps Script, revert on failure + error toast
- **Dark theme**: matches Property Scout aesthetic, `prefers-color-scheme` + manual toggle
- **Loading skeletons**: not spinners
- **Empty states**: helpful CTAs, not blank screens
- **Large tap targets**: 44pt minimum
- **Fonts**: Playfair Display (headings), DM Sans (body), DM Mono (numbers) — same as Property Scout

---

## PWA Setup

- `manifest.json`: name, icons (192, 512), theme color, `display: standalone`
- Apple meta tags: `apple-mobile-web-app-capable`, `apple-touch-icon`, status bar style
- Service Worker: cache the HTML/JS shell + last `get_bootstrap` response for offline read-only access
- "Add to Home Screen" guidance for iOS

---

## What's Explicitly Not In Scope

- Multi-house support — Maple only
- Add/edit/archive rooms from the app — manual sheet edit
- Photo upload from the app — manual Drive upload
- Item-level photos — room cover photos only
- Offline write queue — read-only offline is sufficient
- Audit log — not needed
- Sharing / snapshot export — CSV export covers contractor needs
- OAuth — shared secret is fine for single user

---

## Installation Steps (for the user)

1. Create Google Sheet with Rooms, Items, Categories tabs (headers provided)
2. Seed Categories rows
3. Fill in Rooms (room_id, name, floor, photo_url, sort_order)
4. Open Extensions → Apps Script, paste Code.gs
5. Set Script Property: `AUTH_TOKEN` = chosen secret
6. Deploy → Web App (execute as me, access: anyone)
7. Copy Web App URL into `config.js` in the GitHub repo
8. Push to GitHub — Pages serves the app
9. Open Pages URL on phone, add to home screen

---

## Acceptance Criteria (v1)

- [ ] Carousel swipes between rooms with photos and progress indicators
- [ ] Can add an item to a room from mobile in under 10 seconds
- [ ] Can edit item status, notes, cost, vendor inline
- [ ] Can delete an item with swipe or tap
- [ ] Summary shopping list groups open items by category across all rooms
- [ ] CSV export opens cleanly in Numbers / Excel
- [ ] App installs to iOS home screen in standalone mode
- [ ] Opening offline shows last-cached data
- [ ] No secrets in the repo
