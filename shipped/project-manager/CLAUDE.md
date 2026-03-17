# Project Manager

## Overview
Workspace dashboard for managing all Claude 2.0 projects. Scans the filesystem, reads project metadata, and provides multiple views for organization.

## Tech Stack
Python Flask backend, vanilla HTML/CSS/JS frontend

## Quick Start
```bash
start.bat
```

## Project Structure
- `server.py` — Flask app, scans workspace, serves API + UI
- `static/index.html` — Single-page dashboard
- `static/` — CSS/JS assets

## Skills & Protocols
- **Security Audit**: `../../_skills/security-audit/SKILL.md`
- **Chat Widget**: `../../_skills/llm-chat-widget/SKILL.md`
- **Deploy**: `../../_skills/deploy/SKILL.md`

## Conventions
- Reads `../../workspace.json` as the manifest
- Scans actual folders for live data (apps/, shipped/, sandbox/, PORT PROJECTS FROM HERE/)
- All mutations (reclassify, move) update both filesystem and workspace.json
