# Architectural Decisions Log

### Why Gemini for the Chat Widget
**Date:** 2026-03-14
**Choice:** Google Gemini API for the shared chat widget
**Why:** Low usage volume makes the free tier sufficient, and the API key was already available system-wide.
**Alternatives considered:** OpenAI (costs money per request), local LLM (too heavy for a widget), Claude API (save for primary work)

### Why sessionStorage for the API Key
**Date:** 2026-03-14
**Choice:** sessionStorage for browser-side API key handling
**Why:** Tab-scoped and auto-clears on tab close, eliminating persistence risk.
**Alternatives considered:** localStorage (persists across sessions, leakable), cookies (sent to server unnecessarily), env var only (no browser access without a server proxy)

### Why VBS for Electron Launcher
**Date:** 2026-03-14
**Choice:** VBScript (.vbs) as the Electron app launcher on Windows
**Why:** Native to Windows with zero dependencies, hides the terminal window, and can be pinned to Start menu or taskbar.
**Alternatives considered:** PowerShell (execution policy headaches), shortcut with window style (fragile), compiled exe (overkill)

### Why CLAUDE.md Cascading Instead of One Big Config
**Date:** 2026-03-14
**Choice:** Cascading CLAUDE.md files at each directory level
**Why:** Enables room-level overrides, keeps files small (<50 lines each), and makes each project self-contained and portable.
**Alternatives considered:** Single workspace config (too big, no project-specific overrides), .env-style config (not readable by Claude Code natively)

### Why data/ Separated from apps/
**Date:** 2026-03-14
**Choice:** Dedicated top-level data/ directory independent of apps/
**Why:** Multiple apps can consume the same data without duplicating collection logic, and pipelines remain independent of presentation.
**Alternatives considered:** Data inside each app (duplicates pipelines), shared database (over-engineering for flat files)

### Why _skills/ Uses SKILL.md Convention
**Date:** 2026-03-14
**Choice:** SKILL.md file as the entry point for each skill
**Why:** Matches Claude Code's skill system and enables progressive disclosure — read the SKILL.md to learn what a skill does. Skills are verbs, not nouns.
**Alternatives considered:** Inline in CLAUDE.md (bloats the file), separate tool scripts (loses the instruction context)

### Why Full Test Coverage as Default
**Date:** 2026-03-14
**Choice:** Full test coverage required by default for all projects
**Why:** Solo developer with no code review process — tests are the only safety net against regressions.
**Alternatives considered:** Test critical paths only (too subjective about what's critical), no default (leads to zero tests)
