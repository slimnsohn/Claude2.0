# House Room Tracker

## Overview
Mobile PWA to track renovation items per room for the Maple house. Swipe carousel of rooms, drill into item checklists, summary/shopping list view.

## Tech Stack
React 18 (CDN, single index.html), Google Apps Script backend, Google Sheets + Drive storage, GitHub Pages hosting.

## Quick Start
```
start.bat
```

## Data Model
- **Rooms** (static): room_id, name, floor, photo_url, notes, sort_order
- **Items** (CRUD): item_id, room_id, category, description, status, priority, cost_estimate, cost_actual, vendor, notes, created_at, updated_at
- **Categories** (static): category_name, icon_emoji, default_items

## API Contract
- `GET` → `get_bootstrap` returns `{ rooms, items, categories }`
- `POST` actions: `create_item`, `update_item`, `delete_item`, `bulk_update_items`
- Auth: `X-Auth-Token` header (passed as query param for GET, body field for POST)

## Deployment
- Frontend: GitHub Pages (push to main deploys)
- Backend: Apps Script Web App (manual deploy via Editor → Deploy → Manage → new version)

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
