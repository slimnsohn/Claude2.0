# Deploy Skill

Promotes a project to production-ready status. Enforces security audit before any promotion.

## Trigger

User says something like:
- "deploy this"
- "ship it"
- "this is done"
- "move to shipped"

## Steps

### 1. Pre-flight: Security Audit (mandatory)

Run the security audit protocol (`_skills/security-audit/SKILL.md`) against the project.

- **CRITICAL or HIGH findings** → Block. Show findings. Fix first.
- **MEDIUM or below** → Warn, but allow if user confirms.
- If audit was already run this session and no code changed since, skip re-run.

### 2. Verify it runs

- Run `start.bat` and confirm the project starts without errors
- For Electron projects, verify `launch.vbs` launches without terminal
- Confirm the chat widget loads (browser projects)

### 3. Promote to shipped

- Move the project folder from `apps/` (or `sandbox/`) to `shipped/`
- Update `workspace.json` at workspace root — set `status` to `shipped`, update `location`, add `shippedDate`
- Update the project's own `TODO.md` with ship date

### 4. Report

- Confirm what was moved and where
- Flag any remaining TODO items that weren't completed

## Rules

- Never skip the security audit. This is the whole point of the skill.
- Never ship with hardcoded API keys, secrets, or debug mode enabled.
- Confirm with the user before moving folders.
