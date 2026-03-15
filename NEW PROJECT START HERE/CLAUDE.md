# StartHere — Project Launchpad

You are in the launchpad directory. This is the default Claude Code entry point.

## First Action

When the user describes what they want to build, immediately:

1. **Ask** (if not obvious): project name, which folder (`apps/`, `sandbox/`, `data/`), one-line description
2. **Create** the project folder at `../{target}/{project-name}/`
3. **Copy & fill** templates from `../_skills/scaffold/templates/`:
   - `CLAUDE.md.template` → `CLAUDE.md` (fill all `{PLACEHOLDERS}`)
   - `TODO.md.template` → `TODO.md` (fill `{PROJECT_NAME}` and `{FIRST_TASK}`)
4. **Scaffold** starter files based on project type (see `../_skills/scaffold/SKILL.md`)
5. **Wire up** the chat widget script tag if it's a browser project
6. **Report** what was created and suggest `cd ../{target}/{project-name}` to continue

## If the user just wants to chat or explore

Not every session is a new project. If the user asks questions, wants to work on an existing project, or is just thinking out loud — help normally. Only scaffold when they're clearly starting something new.

## Workspace Reference

Read `../CLAUDE.md` for the full workspace structure, rules, and available skills.

## Quick Commands

The user might say shorthand things like:
- "new app {name}" → scaffold in `apps/`
- "new experiment {name}" → scaffold in `sandbox/`
- "new pipeline {name}" → scaffold in `data/_pipelines/`
- "continue {name}" → open existing project, read its CLAUDE.md
- "what's active" → list folders in `apps/` with their one-line descriptions
- "status" → for each project in `apps/`, read its CLAUDE.md one-liner and TODO.md "Now" section, then summarize
- "recent" → list projects sorted by last-modified, show top 5 with timestamps
- "port {name}" → run port skill (`../_skills/port/SKILL.md`) on a project in `PORT PROJECTS FROM HERE/`
- "port" (no name) → list everything in `PORT PROJECTS FROM HERE/` and offer to port each one
- "what's in sandbox" → list `sandbox/` folders with one-line descriptions
- "audit {name}" → run full security-audit skill (`../_skills/security-audit/SKILL.md`) against the named project
- "audit" (no name) → run against the current working directory
- "quick check" → run security-audit quick mode (secrets + gitignore only) on current project
- "ship {name}" → run deploy skill (`../_skills/deploy/SKILL.md`) to promote a project to shipped
- "widget {name}" → wire the chat widget into an existing project that doesn't have it yet (add the script tag + optional config block)
