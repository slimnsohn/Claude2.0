# Claude 2.0 — Workspace Rules

## Folder Map

```
_docs/       Guides, architecture notes, how-things-work references
_shared/     Runtime code used across projects (utils, CSS, API clients)
_skills/     Claude Code skills. Each has SKILL.md + implementation.
apps/        Active projects under development
data/        Flat data stores + collection pipelines
sandbox/     Experiments and throwaway exploration
shipped/     Deployed and stable
NEW PROJECT START HERE/   Default Claude Code entry point
```

## Rules That Always Apply

- API keys live in Windows environment variables. Never hardcode. Never commit.
- GEMINI_API_KEY is available system-wide for the shared chat widget.
- TODO.md files are manually controlled. Never auto-append dead ends from exploration.
- Keep all CLAUDE.md files under 50 lines.
- Data files use JSON or CSV. No proprietary formats.
- Run security-audit skill before any deploy.
- All browser-based apps include the chat widget from `_skills/llm-chat-widget/`.

## Launch Conventions

- Every browser project gets a `start.bat` — single entry point, handles deps + open browser.
- Every Electron project gets `start.bat` + `launch.vbs` — user double-clicks the .vbs, no terminal visible.
- Templates live in `_skills/scaffold/templates/`. Always use them.

## Communication Style

- Be direct. Skip disclaimers.
- Show tradeoffs honestly — don't advocate.
- Data-driven reasoning over opinions.
- When uncertain, say so.

## Code Preferences

- Stack: Whatever fits the project. No default framework loyalty.
- Scripting/backend: Python or Node — pick whichever fits the context.
- Package manager: Use whatever the project already uses.
- Testing: Full test coverage. Write tests alongside code, not as an afterthought.

## Problem-Solving

- When stuck, try 2-3 different approaches before stopping.
- If none work, explain what was tried, why each failed, and what the options are.
- Don't ask permission to try the next approach — just try it.
