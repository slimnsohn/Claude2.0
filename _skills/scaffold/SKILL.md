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

5. **Create starter files** based on project type:
   - Browser (static/Node/Python): copy `index.html.template` as `index.html`, fill placeholders. Already includes base.css, fetch-wrapper, and chat widget.
   - Node: also create `package.json`
   - Python: also create `requirements.txt` + `server.py`
   - Projects customize the HTML from there — the template is just the starting point.

6. **Update workspace.json** with the new project:
   ```json
   { "name": "project-name", "type": "BROWSER|ELECTRON|OTHER", "location": "{target}/{name}", "status": "active|sandbox", "description": "one-line", "createdDate": "YYYY-MM-DD" }
   ```

7. **Report** what was created and suggest: `cd ../../{target}/{project-name}`

## Rules

- Always use these templates. Don't freestyle project structure.
- Fill ALL placeholders — no `{PLACEHOLDER}` text should remain in output files.
- Chat widget goes in every browser project. No exceptions.
- Never hardcode API keys. Use environment variables.
