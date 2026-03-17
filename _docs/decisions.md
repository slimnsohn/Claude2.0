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

### Why data/ Is External-Only
**Date:** 2026-03-14
**Choice:** data/ stores only externally sourced data. Projects keep their own generated/scraped/downloaded data locally.
**Why:** Projects stay independent and self-contained. Shared data creates coupling between projects. Only centralize what's expensive or impossible to recreate — external datasets, curated reference data, things you can't just re-download from a free API.
**Alternatives considered:** All data centralized (creates coupling, projects can't move independently), data inside each app only (loses expensive-to-collect external datasets when projects get deleted)

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
