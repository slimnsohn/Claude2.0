# nautilus

## Overview
Spotlight/Raycast-style Windows launcher. Ctrl+Space summons a centered search bar that launches Start Menu apps, jumps to websites (Chrome bookmarks bar + built-ins), opens File Explorer folders, and routes question-shaped queries to a new Claude chat (claude.ai/new?q=...).

## Tech Stack
Electron 42, vanilla JS (CommonJS), node:test. Zero runtime dependencies.

## Quick Start
```bash
start.bat        # or launch.vbs for no terminal
npm test         # unit tests (node --test tests/)
```

## Project Structure
- `main.js` — Electron wiring: window/tray/hotkey/IPC/login-item
- `preload.js` — contextBridge IPC surface (`window.nautilus`)
- `src/core/` — pure logic: score, router, bookmarks, startmenu, folders, sites
- `src/` — indexer (refresh + fs.watch), launch dispatch, logger
- `renderer/` — search UI (index.html, app.js, styles.css)
- `tests/` — node:test suites + fixtures
- `data/` — runtime logs (gitignored)

## Key Behaviors
- Routing: strong match (score ≥600) → launch; question-shaped → Ask Claude; Ask Claude row always present.
- Hotkey: Ctrl+Space, fallbacks Ctrl+Shift+Space → Ctrl+Alt+Space; tray tooltip shows active hotkey.
- Tray-resident; window hides on Esc/blur; quit only via tray Exit.

## Skills & Protocols
- **Security Audit**: `../../_skills/security-audit/SKILL.md`
- **Deploy**: `../../_skills/deploy/SKILL.md`
- No chat widget (browser-app requirement; this is Electron).

## Environment Variables
None required.
