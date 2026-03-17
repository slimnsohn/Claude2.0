# Scaffold Skill

Creates new projects with consistent structure. Called from `NEW PROJECT START HERE/`.

## Trigger

User says something like:
- "new app {name}" → create in `apps/`
- "new experiment {name}" → create in `sandbox/`
- "new pipeline {name}" → create in `data/_pipelines/`

## Steps

1. **Determine target**: Ask if not obvious — project name, folder (`apps/`, `sandbox/`, `data/`), one-line description
2. **Create project directory**: `../../{target}/{project-name}/`
3. **Copy and fill templates** from this folder (`_skills/scaffold/templates/`):

   | Template | Destination | Placeholders to fill |
   |----------|-------------|---------------------|
   | `CLAUDE.md.template` | `CLAUDE.md` | `{PROJECT_NAME}`, `{PROJECT_DESCRIPTION}`, `{TECH_STACK}` |
   | `TODO.md.template` | `TODO.md` | `{PROJECT_NAME}`, `{FIRST_TASK}` |
   | `index.html.template` | `index.html` (browser only) | `{PROJECT_NAME}`, `{PROJECT_DESCRIPTION}` |

4. **Pick the right launcher**:
   - Browser project → copy `start-browser.bat` as `start.bat`
   - Electron project → copy `start-electron.bat` as `start.bat` + copy `launch.vbs`
   - iOS App (GAS/PWA) → no start.bat needed. Include `SETUP.md` with deploy instructions.

5. **Create starter files** based on project type:
   - Browser (static/Node/Python): copy `index.html.template` as `index.html`, fill placeholders. Already includes base.css, fetch-wrapper, and chat widget.
   - Node: also create `package.json`
   - Python: also create `requirements.txt` + `server.py`
   - iOS App (Google Apps Script): create `Code.gs` + `Index.html` + `SETUP.md`. No local deps, no chat widget (runs in GAS sandbox).
   - All projects: create a local `data/` folder with `.gitkeep` for project-generated data (scraped, downloaded, computed). The workspace-level `data/` is only for external reference data.
   - Projects customize the HTML from there — the template is just the starting point.

6. **Update workspace.json** with the new project:
   ```json
   { "name": "project-name", "type": "BROWSER|ELECTRON|IOS_APP|OTHER", "location": "{target}/{name}", "status": "active|sandbox", "description": "one-line", "createdDate": "YYYY-MM-DD" }
   ```

7. **Create quick_starts shortcut** in `../../quick_starts/`:
   - Browser: `{project-name}_start.bat` that does `cd /d "%~dp0..\{target}\{project-name}" && call start.bat`
   - Electron: same `_start.bat` plus `{project-name}_launch.vbs` that calls the project's `launch.vbs`

8. **Report** what was created and suggest: `cd ../../{target}/{project-name}`

## Rules

- Always use these templates. Don't freestyle project structure.
- Fill ALL placeholders — no `{PLACEHOLDER}` text should remain in output files.
- Chat widget goes in every browser project. No exceptions.
- For projects with a dev server (Flask/Node), `../../` paths won't resolve. Add proxy routes to serve `/_skills/` and `/_shared/` from the workspace root, and use absolute paths (`/_skills/...`) in the HTML instead of relative.
- Never hardcode API keys. Use environment variables.
