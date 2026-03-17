# Synthetic Population Engine — Web UI Design Spec

**Date:** 2026-03-17
**Project:** `apps/synthetic-population/`
**Status:** Draft
**Depends on:** `docs/superpowers/specs/2026-03-16-synthetic-population-design.md`

---

## Purpose

Build a web UI for the synthetic population engine. The primary action is polling — ask a question, get demographically-weighted opinion results from 362+ synthetic profiles via Claude-in-Chrome automation. Secondary features: browsing the population, managing events/drift, and backtesting polls against historical population snapshots with strict temporal isolation.

## Design Decisions

- **Layout:** Sidebar + main content (dashboard feel). Sidebar has navigation + always-visible population stats.
- **Stack:** Vanilla HTML/CSS/JS frontend (per workspace conventions), Python Flask backend, JSON file storage.
- **Polling automation:** Claude-in-Chrome MCP tools, orchestrated from the Claude Code session. The Flask server prepares prompts and records responses; Claude Code drives the browser interaction.
- **Polling UX:** Fire and forget. Hit "Run Poll", see progress text, get results when done. No live response feed.
- **Backtesting:** Snapshot-based temporal isolation. Snapshots are immutable frozen copies of the population at a point in time. Polls against snapshots cannot access future data.
- **Chat widget:** Included per workspace conventions. Context function provides population summary + recent poll results.

---

## Architecture

### Frontend

Single-page app served by Flask. Vanilla HTML/CSS/JS — no framework, no build step.

- Uses `_shared/styles/base.css` for theme variables (dark/light mode)
- Project-specific CSS for layout, components
- Imperative DOM rendering with template literals
- Canvas API for charts (demographic bars, time series)
- Shared fetch wrapper for API calls
- Chat widget integration

### Backend

Python Flask server (`server.py`) that:

- Serves static frontend files
- Exposes REST API (see API Endpoints below)
- Imports and calls existing Python modules directly: `generator`, `engine`, `monitor`, `pipeline`, `schema`
- Does NOT call Claude directly — polling prompts are prepared by the server, but the actual LLM interaction is driven by the Claude Code session via MCP tools

### Data Layer

Existing JSON file storage plus new snapshot system:

- `data/profiles/registry.json` — live population (existing)
- `data/polls/` — poll results (existing)
- `data/events/` — event log (existing)
- `data/snapshots/` — NEW: frozen population states for backtesting
- `data/snapshots/manifest.json` — NEW: snapshot index with metadata

### Polling Flow (Claude-in-Chrome)

1. User submits question + snapshot selection in the UI
2. Flask creates a poll record, selects representative profiles per archetype, generates prompt batch
3. Flask saves prompts to `data/polls/{poll_id}/prompts.json` (structured, not just text)
4. The Claude Code session picks up the pending poll, iterates through prompts using `mcp__claude-in-chrome__*` tools to send each to Claude in a browser tab
5. Responses are POSTed back to Flask via `/api/polls/{id}/responses`
6. Flask runs integrity checks (hedge detection, consistency) and aggregates results
7. UI polls `/api/polls/{id}` until status is "complete", then renders results

This separation means the Flask server works without Claude — you can manually record responses too.

---

## Snapshot System (Backtesting Core)

### Data Model

```json
// data/snapshots/manifest.json
{
  "snapshots": [
    {
      "snapshot_id": "SNAP-20260315-pre-fed",
      "date": "2026-03-15",
      "label": "Pre-Fed rate decision",
      "profile_count": 362,
      "events_applied_through": "2026-03-14",
      "created_at": "2026-03-15T10:00:00",
      "file": "SNAP-20260315-pre-fed.json"
    }
  ]
}

// data/snapshots/SNAP-20260315-pre-fed.json
// Full copy of registry.json at that point in time — all profiles with their
// drift_logs as they existed on 2026-03-15. Immutable once created.
```

### Temporal Isolation Rules

**Rule 1: Snapshots are immutable.** Once saved, a snapshot's profiles never change. New events applied to the live population do not affect existing snapshots.

**Rule 2: Polls record their context.** Every poll result stores:
- `snapshot_id` — which snapshot was used (or `"live"` for current population)
- `timestamp` — when the poll was run
- `population_count` — how many profiles were in the snapshot
- `events_applied_through` — latest event date in the snapshot's history

This makes every poll result reproducible and auditable.

**Rule 3: Prompt construction uses snapshot state.** When backtesting, `build_poll_prompt()` receives the profile as it existed in the snapshot — including that snapshot's drift_log, not the current one. If a profile's opinion on immigration shifted after an event in April, a March snapshot poll won't see that shift.

**Rule 4: No future events in backstory context.** The conviction anchoring prompt includes prior opinions from drift_log. For backtests, only drift_log entries dated before the snapshot date are included in the prompt.

**Rule 5: Comparison requires same question text.** Time series charts only link polls with identical question strings. No fuzzy matching — reuse exact wording to track changes over time.

### Snapshot Operations

- **Create:** Copy current `registry.json` to `data/snapshots/{id}.json`, add entry to manifest
- **Load:** Read snapshot file, return profiles as-is (no modification)
- **Delete:** Remove file + manifest entry (polls referencing it retain their results but are marked "snapshot deleted")
- **Compare:** Load two snapshots (or snapshot + live), run same question against both, display results side by side

---

## Views

### Sidebar (persistent)

Always visible. Contains:

- **App title** — "Synthetic Population Engine"
- **Navigation links** — Poll, Results, Population, Backtest, Events. Active state: accent-colored background.
- **Population stats** (bottom of sidebar):
  - Profile count (e.g., "362")
  - Archetype count (e.g., "56")
  - Polls run (e.g., "12")
  - Last event date

### View 1: Poll (default, hero view)

**Purpose:** Ask a question and get results.

**Components:**
- **Question input** — textarea, placeholder: "Ask your population anything..."
- **Snapshot selector** — dropdown with options:
  - "Current Population (live)" — default
  - Each saved snapshot: "{date} — {label} ({count} profiles)"
- **Run Poll button** — accent-colored, triggers poll creation
- **Progress text** — appears after clicking Run: "Polling... 12/56 archetypes complete"
- **Recent polls** — table below input showing last 10 polls:
  - Columns: Question (truncated), Date, Snapshot, Result (headline %), Status
  - Click row → navigates to Results view for that poll

### View 2: Results

**Purpose:** Deep-dive into a single poll's results.

**Components:**
- **Header** — question text, date, snapshot badge (blue for live, orange for backtest)
- **Headline numbers** — large yes/no/unsure percentages with 95% CI ranges
- **Mean confidence** — average confidence score across respondents
- **Demographic breakdowns** — collapsible sections, one per demographic variable:
  - Party ID, Race, Education, Age bracket, Urban/Rural
  - Each shows horizontal stacked bar chart (yes/no/unsure proportions)
  - Sorted by most interesting split (largest delta between groups)
- **Time series** — if same question polled multiple times:
  - Line chart, X = poll date, Y = % yes
  - Points colored by snapshot (blue = live, orange = backtest)
  - Hover shows snapshot label + full result
- **Snapshot comparison** — if two polls used different snapshots for the same question, show side-by-side column layout with delta highlighting
- **Raw responses** — expandable table showing each archetype's:
  - Archetype ID, population weight, opinion, confidence, hedge score, flags
  - Click to expand and see full response text

### View 3: Population

**Purpose:** Browse and explore the synthetic population.

**Components:**
- **Filter bar** — text search + dropdown filters for: sex, race, education, party_id, state, urban_rural, archetype_id
- **Profile table** — sortable columns:
  - Name (from backstory first name), Age, Sex, Race, Education, State, Party, Archetype
  - Pagination or virtual scroll (362 rows is manageable without)
- **Profile detail panel** — clicking a row opens a slide-out panel (right side) with:
  - Full backstory (highlighted section at top)
  - Demographics grouped by category (matching schema categories)
  - Drift log timeline (chronological list of opinion changes)
  - Archetype membership info
- **Quick filter buttons** — row of toggles: "Democrats", "Republicans", "College+", "Rural", "65+", etc.

### View 4: Backtest

**Purpose:** Manage snapshots and run historical comparisons.

**Components:**
- **Snapshot list** — table: Date, Label, Profile Count, Events Through, Actions (Load, Delete)
- **Create snapshot** — form: date picker (defaults to today), label text input, "Save Snapshot" button
- **Timeline visualization** — horizontal timeline with:
  - Snapshot dots (blue, clickable)
  - Event markers (orange triangles)
  - Hover shows details
  - Click a snapshot → sets it as active in the Poll view's dropdown
- **Comparison launcher** — select 2 snapshots (or 1 snapshot + live), enter a question, "Compare" button runs the poll against both and navigates to Results view in comparison mode

### View 5: Events

**Purpose:** Manage events and apply drift.

**Components:**
- **Event log** — chronological table: Date, Description, Affected Segments, Status (applied/pending)
- **Add event form:**
  - Date input
  - Description textarea
  - Affected segments builder — select a segment variable (e.g., party_id), select values, set variable deltas
  - "Add Event" button (saves without applying)
- **Apply drift button** — per event, applies drift to current live population
- **Impact preview** — before applying, expandable section showing:
  - Number of profiles affected
  - Which archetypes are hit
  - Magnitude of changes per variable
  - "Apply" / "Cancel" confirmation

---

## API Endpoints

### Profiles

```
GET  /api/profiles
  Query params: sex, race, education, party_id, state, urban_rural, archetype_id, search (text)
  Returns: [{profile summary}] (excludes backstory for list performance)

GET  /api/profiles/:id
  Returns: {full profile with all 143 fields + backstory + drift_log}
```

### Archetypes

```
GET  /api/archetypes
  Returns: [{archetype_id, party, race, education, religiosity, urban_rural, count, weight}]
```

### Polls

```
POST /api/polls
  Body: {question: str, snapshot_id: str|"live"}
  Returns: {poll_id, status: "preparing"}
  Effect: Creates poll, selects archetypes, generates prompts, saves to data/polls/

GET  /api/polls
  Returns: [{poll_id, question, date, snapshot_id, status, headline_result}]

GET  /api/polls/:id
  Returns: {full poll result — distribution, breakdowns, CI, metadata}

GET  /api/polls/:id/prompts
  Returns: [{archetype_id, prompt_text, weight}] — for Claude-in-Chrome automation

POST /api/polls/:id/responses
  Body: {archetype_id: str, response_text: str, opinion: str, confidence: int}
  Effect: Records response, runs integrity check

POST /api/polls/:id/aggregate
  Effect: Runs weighted aggregation, saves results, sets status to "complete"

GET  /api/polls/:id/responses
  Returns: [{archetype_id, opinion, confidence, hedge_score, flags, response_text}]
```

### Snapshots

```
POST /api/snapshots
  Body: {date: str, label: str}
  Effect: Copies current registry.json to snapshots dir, updates manifest
  Returns: {snapshot_id}

GET  /api/snapshots
  Returns: [{snapshot_id, date, label, profile_count, events_applied_through}]

GET  /api/snapshots/:id
  Returns: {snapshot metadata + profile list}

DELETE /api/snapshots/:id
  Effect: Removes file + manifest entry
```

### Events

```
GET  /api/events
  Query params: start_date, end_date
  Returns: [{event_id, date, description, affected_segments, applied}]

POST /api/events
  Body: {date, description, affected_segments}
  Returns: {event_id}

POST /api/events/:id/apply
  Effect: Applies drift to live population, marks event as applied
  Returns: {profiles_affected: int, changes: [{archetype_id, variable, old, new}]}

GET  /api/events/:id/preview
  Returns: {profiles_affected, changes} — without applying
```

### Stats

```
GET  /api/stats
  Returns: {
    profile_count, archetype_count, polls_run, last_event_date,
    demographic_summary: {sex: {}, race: {}, education: {}, party_id: {}}
  }
```

---

## File Structure

```
apps/synthetic-population/
├── server.py                    # Flask backend — API + static serving
├── start.bat                    # Launch script (existing, update to start Flask)
├── static/
│   ├── index.html               # Single-page app
│   ├── styles.css               # Project CSS (uses base.css variables)
│   └── app.js                   # Frontend application code
├── api/
│   ├── __init__.py
│   ├── profiles.py              # Profile endpoints
│   ├── polls.py                 # Poll endpoints
│   ├── snapshots.py             # Snapshot endpoints
│   ├── events.py                # Event endpoints
│   └── stats.py                 # Stats endpoint
├── snapshots/
│   ├── __init__.py
│   └── manager.py               # Snapshot CRUD + temporal isolation logic
│
│   ... (existing schema/, pipeline/, generator/, engine/, monitor/, tests/)
```

---

## Tech Stack

- **Backend:** Python 3.11+, Flask
- **Frontend:** Vanilla HTML/CSS/JS, Canvas API for charts
- **Data:** JSON file storage (existing)
- **LLM Integration:** Claude-in-Chrome MCP tools (external orchestration)
- **CSS:** Workspace base.css + project-specific styles
- **Chat Widget:** `_skills/llm-chat-widget/dist/chat-widget.js`

---

## Testing Strategy

- **API tests:** pytest against Flask test client — each endpoint tested with valid/invalid inputs
- **Snapshot isolation tests:** Verify that loading a snapshot returns profiles as they were, verify drift_log filtering by date, verify poll results correctly reference snapshot
- **Frontend:** Manual testing (vanilla JS, no unit test framework needed for DOM rendering)
- **Integration:** End-to-end test: create snapshot → create event → apply drift → poll live vs snapshot → verify different results

---

## Open Questions / Future Work

- Automated poll scheduling (run same question weekly)
- Polymarket integration (auto-create polls from active markets)
- Export poll results to CSV/PDF
- Profile generation from the UI (currently CLI-only)
- Real CES data integration to replace synthetic political variables
