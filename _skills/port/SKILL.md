# Port Skill

Intake workflow for migrating old projects into the Claude 2.0 workspace.

## Trigger

User drops a project into `PORT PROJECTS FROM HERE/` and says:
- "port this project"
- "analyze what's in the port folder"
- "migrate [name] into the workspace"

## Steps

### 1. Scan the project

- Identify languages, frameworks, package managers
- Find entry points (index.html, main.py, server.py, package.json main/start scripts)
- Check for Electron (look for electron in package.json dependencies, main.js with BrowserWindow)
- Catalog existing files and structure

### 2. Auto-classify

| Type | Detection |
|------|-----------|
| **BROWSER** | Has index.html, or package.json with a dev server, or Python with Flask/FastAPI serving HTML |
| **ELECTRON** | package.json lists electron as dependency, or has main.js with BrowserWindow/app imports |
| **OTHER** | CLI tools, pure scripts, data pipelines, APIs without UI |

Present the classification to the user for confirmation. They can override.

### 3. Security audit

Run `_skills/security-audit/SKILL.md` against the project before porting.
- Flag any hardcoded secrets, exposed keys, or critical vulnerabilities
- These MUST be fixed before the project moves into the workspace

### 4. Port into workspace

- Create target folder in `apps/{project-name}/`
- Copy project files
- Generate `CLAUDE.md` from `_skills/scaffold/templates/CLAUDE.md.template` (fill placeholders from scan results)
- Generate `TODO.md` from `_skills/scaffold/templates/TODO.md.template`
- Copy appropriate launcher: `start-browser.bat` or `start-electron.bat` + `launch.vbs`
- Wire up chat widget for BROWSER projects
- Update `workspace.json` at workspace root with project metadata

### 5. Update workspace manifest

Add entry to `workspace.json`:
```json
{
  "name": "project-name",
  "type": "BROWSER|ELECTRON|OTHER",
  "location": "apps/project-name",
  "status": "active",
  "portedFrom": "PORT PROJECTS FROM HERE/original-folder",
  "portedDate": "2026-03-14",
  "description": "one-line description"
}
```

### 6. Clean up

- Remove the original from `PORT PROJECTS FROM HERE/` after successful port
- Report what was done

## Rules

- Always confirm classification with the user before porting
- Always run security audit — no exceptions
- Never copy secrets or .env files with real values
- Preserve the project's original git history if it has one
