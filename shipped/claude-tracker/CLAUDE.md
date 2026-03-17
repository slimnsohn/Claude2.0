# CLAUDE.md — Claude Tracker

## Project Overview
Electron desktop widget that tracks Claude.ai usage by polling the internal usage API endpoint. Displays session and weekly usage with historical charts.

## Tech Stack
- Electron 28 (main + renderer process)
- Chart.js 4 (time-series charts, vendored)
- electron-store (settings + usage history persistence)
- Pure JS, no framework — single HTML file renderer

## Key Architecture Decisions
- **fetchViaWindow**: API calls go through a hidden BrowserWindow to bypass Cloudflare bot detection.
- **safeStorage**: Session key encrypted via Electron's `safeStorage` (OS keychain) when available, with AES-256-GCM fallback.
- **contextIsolation: true**: Renderer has no direct Node.js access. All IPC goes through preload.js bridge.
- **Resizable window**: `resizable: true` in main process + CSS resize handle in bottom-right corner.

## File Layout
```
main.js              Main process: auth, cookies, API fetch, IPC handlers, history
preload.js           IPC bridge exposed as window.api
src/renderer/
  index.html         Dashboard shell (login, compact, expanded, settings views)
  styles.css         Dark terminal aesthetic, JetBrains Mono, yellow session timer
  app.js             UI logic, Chart.js rendering, polling, resize handle
```

## Common Tasks
- **Add a new stat card**: Add HTML in viewDashboard's dash-grid, update `updateUI()` in app.js
- **Change chart styling**: Modify `renderChart()` in app.js
- **Build for Windows**: `npm run build:win`
