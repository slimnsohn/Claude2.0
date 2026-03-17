"""
Project Manager — Workspace Dashboard
Scans the Claude 2.0 workspace and serves a management UI.
"""

import json
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

import re

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder='static')

# Workspace root is two levels up from this file
WORKSPACE = Path(__file__).resolve().parent.parent.parent
MANIFEST = WORKSPACE / 'workspace.json'

# Folder mappings
FOLDERS = {
    'incoming': 'PORT PROJECTS FROM HERE',
    'active': 'apps',
    'shipped': 'shipped',
    'sandbox': 'sandbox',
}

# ── Manifest I/O ──────────────────────────────────────────────────────

def load_manifest():
    if MANIFEST.exists():
        with open(MANIFEST, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'version': 1, 'projects': [], 'types': ['BROWSER', 'ELECTRON', 'OTHER'],
            'statuses': ['incoming', 'active', 'shipped', 'sandbox']}


def save_manifest(data):
    with open(MANIFEST, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Project Detection ─────────────────────────────────────────────────

def detect_type(project_path):
    """Auto-detect project type: BROWSER, ELECTRON, or OTHER."""
    p = Path(project_path)

    # Check for Electron
    pkg = p / 'package.json'
    if pkg.exists():
        try:
            with open(pkg, 'r', encoding='utf-8') as f:
                pj = json.load(f)
            all_deps = {**pj.get('dependencies', {}), **pj.get('devDependencies', {})}
            if 'electron' in all_deps:
                return 'ELECTRON'
        except (json.JSONDecodeError, IOError):
            pass

    # Check for browser project
    if (p / 'index.html').exists():
        return 'BROWSER'
    if pkg.exists():
        return 'BROWSER'  # Node project with package.json = likely browser
    for py_file in p.glob('*.py'):
        try:
            content = py_file.read_text(encoding='utf-8', errors='ignore')[:2000]
            if any(fw in content for fw in ['Flask', 'FastAPI', 'flask', 'fastapi', 'http.server']):
                return 'BROWSER'
        except IOError:
            pass

    # Check for requirements.txt with web frameworks
    req = p / 'requirements.txt'
    if req.exists():
        try:
            content = req.read_text(encoding='utf-8', errors='ignore').lower()
            if any(fw in content for fw in ['flask', 'fastapi', 'django', 'streamlit']):
                return 'BROWSER'
        except IOError:
            pass

    return 'OTHER'


def get_description(project_path):
    """Try to extract a one-line description from CLAUDE.md."""
    claude_md = Path(project_path) / 'CLAUDE.md'
    if claude_md.exists():
        try:
            lines = claude_md.read_text(encoding='utf-8', errors='ignore').splitlines()
            for i, line in enumerate(lines):
                if line.strip().startswith('## Overview'):
                    # Return the next non-empty line
                    for next_line in lines[i+1:]:
                        stripped = next_line.strip()
                        if stripped and not stripped.startswith('#') and not stripped.startswith('<!--'):
                            return stripped[:200]
                    break
        except IOError:
            pass
    return ''


def get_todo_counts(project_path):
    """Count open and done TODO items."""
    todo_md = Path(project_path) / 'TODO.md'
    open_count = 0
    done_count = 0
    if todo_md.exists():
        try:
            content = todo_md.read_text(encoding='utf-8', errors='ignore')
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith('- [ ]'):
                    open_count += 1
                elif stripped.startswith('- [x]') or stripped.startswith('- [X]'):
                    done_count += 1
        except IOError:
            pass
    return open_count, done_count


def get_tech_stack(project_path):
    """Detect technologies used."""
    p = Path(project_path)
    techs = []

    if (p / 'package.json').exists():
        techs.append('Node.js')
        try:
            with open(p / 'package.json', 'r', encoding='utf-8') as f:
                pj = json.load(f)
            all_deps = {**pj.get('dependencies', {}), **pj.get('devDependencies', {})}
            for dep in ['react', 'vue', 'svelte', 'express', 'electron', 'next', 'vite']:
                if dep in all_deps:
                    techs.append(dep.capitalize())
        except (json.JSONDecodeError, IOError):
            pass

    if (p / 'requirements.txt').exists() or list(p.glob('*.py')):
        techs.append('Python')

    if (p / 'index.html').exists() and not techs:
        techs.append('Static HTML')

    if (p / 'Dockerfile').exists():
        techs.append('Docker')

    return techs


def get_file_count(project_path):
    """Count files, excluding node_modules, .git, venv, __pycache__."""
    skip = {'node_modules', '.git', 'venv', '__pycache__', '.venv', 'dist', 'build'}
    count = 0
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in skip]
        count += len(files)
    return count


def get_last_modified(project_path):
    """Get the most recent file modification time."""
    skip = {'node_modules', '.git', 'venv', '__pycache__', '.venv'}
    latest = 0
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            try:
                t = os.path.getmtime(os.path.join(root, f))
                if t > latest:
                    latest = t
            except OSError:
                pass
    return latest if latest > 0 else None


# ── Scan Workspace ────────────────────────────────────────────────────

def scan_workspace():
    """Scan all workspace folders and return project data."""
    manifest = load_manifest()
    manifest_lookup = {p['name']: p for p in manifest.get('projects', [])}
    projects = []

    for status, folder_name in FOLDERS.items():
        folder = WORKSPACE / folder_name
        if not folder.exists():
            continue
        for item in sorted(folder.iterdir()):
            if not item.is_dir():
                continue
            # Skip known non-project directories
            if item.name.startswith('.') or item.name == '__pycache__':
                continue
            # Skip project-manager itself in the scan display
            if item.name == 'project-manager' and status == 'active':
                continue

            name = item.name
            manifest_entry = manifest_lookup.get(name, {})

            proj_type = manifest_entry.get('type') or detect_type(item)
            description = manifest_entry.get('description') or get_description(item)
            open_todos, done_todos = get_todo_counts(item)
            tech_stack = get_tech_stack(item)
            file_count = get_file_count(item)
            last_modified = get_last_modified(item)
            port = manifest_entry.get('port') or detect_port(item)

            projects.append({
                'name': name,
                'type': proj_type,
                'port': port,
                'status': status,
                'location': f'{folder_name}/{name}',
                'description': description,
                'techStack': tech_stack,
                'fileCount': file_count,
                'openTodos': open_todos,
                'doneTodos': done_todos,
                'lastModified': last_modified,
                'lastModifiedFmt': datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M') if last_modified else 'Unknown',
                'hasClaudeMd': (item / 'CLAUDE.md').exists(),
                'hasTodoMd': (item / 'TODO.md').exists(),
                'hasStartBat': (item / 'start.bat').exists(),
                'hasLaunchVbs': (item / 'launch.vbs').exists(),
                'hasChatWidget': _has_chat_widget(item),
            })

    return projects


def _has_chat_widget(project_path):
    """Check if any HTML file references the chat widget."""
    for html_file in Path(project_path).rglob('*.html'):
        try:
            content = html_file.read_text(encoding='utf-8', errors='ignore')[:10000]
            if 'chat-widget.js' in content:
                return True
        except IOError:
            pass
    return False


# ── Port Detection & Process Status ──────────────────────────────────

def detect_port(project_path):
    """Try to detect the port a project runs on from its files."""
    p = Path(project_path)

    # Check Python files for port=XXXX in app.run() etc.
    for py_file in p.glob('*.py'):
        try:
            content = py_file.read_text(encoding='utf-8', errors='ignore')[:5000]
            match = re.search(r'port[=:]\s*(\d{4,5})', content)
            if match:
                return int(match.group(1))
        except IOError:
            pass

    # Check start.bat for localhost:PORT or http.server PORT
    start_bat = p / 'start.bat'
    if start_bat.exists():
        try:
            content = start_bat.read_text(encoding='utf-8', errors='ignore')
            match = re.search(r'localhost:(\d{4,5})', content)
            if match:
                return int(match.group(1))
            match = re.search(r'http\.server\s+(\d{4,5})', content)
            if match:
                return int(match.group(1))
        except IOError:
            pass

    return None


def is_port_listening(port):
    """Fast check if a port is accepting connections."""
    if port is None:
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex(('127.0.0.1', port)) == 0
    except OSError:
        return False


def find_pid_on_port(port):
    """Use netstat to find the PID listening on a port."""
    if port is None:
        return None
    try:
        result = subprocess.run(
            ['netstat', '-ano', '-p', 'TCP'],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            # Match lines like:  TCP    127.0.0.1:5050    0.0.0.0:0    LISTENING    12345
            if f':{port}' in line and 'LISTENING' in line:
                parts = line.split()
                try:
                    return int(parts[-1])
                except (ValueError, IndexError):
                    pass
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def find_electron_pid(project_name):
    """Find an Electron process whose command line includes the project name."""
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where', "name='electron.exe'",
             'get', 'ProcessId,CommandLine', '/format:csv'],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            if project_name in line:
                # CSV format: Node,CommandLine,ProcessId
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    try:
                        return int(parts[-1])
                    except ValueError:
                        pass
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def kill_process_tree(pid):
    """Kill a process and all its children."""
    try:
        subprocess.run(
            ['taskkill', '/F', '/T', '/PID', str(pid)],
            capture_output=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return True
    except (subprocess.TimeoutExpired, OSError):
        return False


# ── Input Validation ──────────────────────────────────────────────────

def validate_project_name(name):
    """Reject path traversal attempts and invalid names."""
    if not name or not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9 _\-\.]*$', name):
        return False
    if '..' in name or '/' in name or '\\' in name:
        return False
    return True


# ── API Routes ────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/_skills/<path:filepath>')
def serve_skills(filepath):
    """Serve shared skill assets (chat widget, etc.)."""
    skills_dir = WORKSPACE / '_skills'
    return send_from_directory(str(skills_dir), filepath)


@app.route('/_shared/<path:filepath>')
def serve_shared(filepath):
    """Serve shared assets (base.css, fetch-wrapper, etc.)."""
    shared_dir = WORKSPACE / '_shared'
    return send_from_directory(str(shared_dir), filepath)


@app.route('/api/projects')
def api_projects():
    projects = scan_workspace()
    # Compute summary stats
    stats = {
        'total': len(projects),
        'byStatus': {},
        'byType': {},
        'totalOpenTodos': sum(p['openTodos'] for p in projects),
        'staleCount': 0,
    }
    two_weeks_ago = time.time() - (14 * 86400)
    for p in projects:
        stats['byStatus'][p['status']] = stats['byStatus'].get(p['status'], 0) + 1
        stats['byType'][p['type']] = stats['byType'].get(p['type'], 0) + 1
        if p['lastModified'] and p['lastModified'] < two_weeks_ago and p['status'] == 'active':
            stats['staleCount'] += 1
            p['isStale'] = True
        else:
            p['isStale'] = False

    return jsonify({'projects': projects, 'stats': stats})


@app.route('/api/projects/<name>/reclassify', methods=['POST'])
def reclassify(name):
    if not validate_project_name(name):
        return jsonify({'error': 'Invalid project name'}), 400

    body = request.get_json() or {}
    new_type = body.get('type', '').upper()
    if new_type not in ('BROWSER', 'ELECTRON', 'OTHER'):
        return jsonify({'error': 'Invalid type. Must be BROWSER, ELECTRON, or OTHER'}), 400

    manifest = load_manifest()
    found = False
    for p in manifest['projects']:
        if p['name'] == name:
            p['type'] = new_type
            found = True
            break
    if not found:
        manifest['projects'].append({
            'name': name,
            'type': new_type,
            'updatedDate': datetime.now().strftime('%Y-%m-%d'),
        })
    save_manifest(manifest)
    return jsonify({'ok': True, 'name': name, 'type': new_type})


@app.route('/api/projects/<name>/move', methods=['POST'])
def move_project(name):
    if not validate_project_name(name):
        return jsonify({'error': 'Invalid project name'}), 400

    body = request.get_json() or {}
    target_status = body.get('status', '')
    if target_status not in FOLDERS:
        return jsonify({'error': f'Invalid status. Must be one of: {list(FOLDERS.keys())}'}), 400

    # Find current location
    current_path = None
    current_status = None
    for status, folder_name in FOLDERS.items():
        candidate = WORKSPACE / folder_name / name
        if candidate.exists():
            current_path = candidate
            current_status = status
            break

    # Verify resolved path stays within workspace
    if current_path and not str(current_path.resolve()).startswith(str(WORKSPACE.resolve())):
        return jsonify({'error': 'Invalid project path'}), 400

    if not current_path:
        return jsonify({'error': f'Project "{name}" not found'}), 404

    if current_status == target_status:
        return jsonify({'error': 'Project is already in that location'}), 400

    target_folder = WORKSPACE / FOLDERS[target_status]
    target_folder.mkdir(exist_ok=True)
    target_path = target_folder / name

    if target_path.exists():
        return jsonify({'error': f'A project named "{name}" already exists in {FOLDERS[target_status]}/'}), 409

    shutil.move(str(current_path), str(target_path))

    # Update manifest
    manifest = load_manifest()
    for p in manifest['projects']:
        if p['name'] == name:
            p['status'] = target_status
            p['location'] = f'{FOLDERS[target_status]}/{name}'
            p['movedDate'] = datetime.now().strftime('%Y-%m-%d')
            break
    save_manifest(manifest)

    return jsonify({
        'ok': True,
        'name': name,
        'from': f'{FOLDERS[current_status]}/{name}',
        'to': f'{FOLDERS[target_status]}/{name}',
    })


@app.route('/api/projects/<name>/launch', methods=['POST'])
def launch_project(name):
    if not validate_project_name(name):
        return jsonify({'error': 'Invalid project name'}), 400

    body = request.get_json() or {}
    launcher = body.get('launcher', 'bat')  # 'bat' or 'vbs'
    if launcher not in ('bat', 'vbs'):
        return jsonify({'error': 'Invalid launcher type. Must be bat or vbs'}), 400

    # Find the project directory
    project_path = None
    for status, folder_name in FOLDERS.items():
        candidate = WORKSPACE / folder_name / name
        if candidate.exists():
            project_path = candidate
            break

    if not project_path:
        return jsonify({'error': f'Project "{name}" not found'}), 404

    # Verify resolved path stays within workspace
    if not str(project_path.resolve()).startswith(str(WORKSPACE.resolve())):
        return jsonify({'error': 'Invalid project path'}), 400

    if launcher == 'vbs':
        launch_file = project_path / 'launch.vbs'
        if not launch_file.exists():
            return jsonify({'error': 'No launch.vbs found'}), 404
        subprocess.Popen(['wscript.exe', str(launch_file)], cwd=str(project_path))
    else:
        launch_file = project_path / 'start.bat'
        if not launch_file.exists():
            return jsonify({'error': 'No start.bat found'}), 404
        # Use start "title" /D to set working dir, then call the bat directly.
        # This preserves %~dp0 inside the bat file.
        cmd_str = f'start "{name}" /D "{project_path}" "{launch_file}"'
        subprocess.Popen(cmd_str, shell=True, cwd=str(project_path))

    return jsonify({'ok': True, 'name': name, 'launcher': launcher})


@app.route('/api/projects/status')
def projects_status():
    """Lightweight endpoint — checks which projects are running."""
    projects = scan_workspace()
    statuses = {}
    for p in projects:
        name = p['name']
        port = p.get('port')
        proj_type = p['type']

        running = False
        pid = None

        if port and is_port_listening(port):
            running = True
            pid = find_pid_on_port(port)
        elif proj_type == 'ELECTRON':
            epid = find_electron_pid(name)
            if epid:
                running = True
                pid = epid

        statuses[name] = {
            'running': running,
            'pid': pid,
            'port': port,
        }

    return jsonify(statuses)


@app.route('/api/projects/<name>/stop', methods=['POST'])
def stop_project(name):
    if not validate_project_name(name):
        return jsonify({'error': 'Invalid project name'}), 400

    # Don't allow stopping the project-manager itself from the UI
    if name == 'project-manager':
        return jsonify({'error': 'Cannot stop the project manager from its own UI'}), 400

    # Find the project to get its port/type
    project_path = None
    proj_type = None
    for status, folder_name in FOLDERS.items():
        candidate = WORKSPACE / folder_name / name
        if candidate.exists():
            project_path = candidate
            break

    if not project_path:
        return jsonify({'error': f'Project "{name}" not found'}), 404

    manifest = load_manifest()
    manifest_entry = {p['name']: p for p in manifest.get('projects', [])}.get(name, {})
    proj_type = manifest_entry.get('type') or detect_type(project_path)
    port = manifest_entry.get('port') or detect_port(project_path)

    pid = None
    if port:
        pid = find_pid_on_port(port)
    if not pid and proj_type == 'ELECTRON':
        pid = find_electron_pid(name)

    if not pid:
        return jsonify({'error': 'No running process found for this project'}), 404

    success = kill_process_tree(pid)
    if success:
        return jsonify({'ok': True, 'name': name, 'pid': pid})
    else:
        return jsonify({'error': 'Failed to stop process'}), 500


@app.route('/api/workspace/stats')
def workspace_stats():
    """High-level workspace health metrics."""
    projects = scan_workspace()
    two_weeks_ago = time.time() - (14 * 86400)

    stale = [p for p in projects if p['lastModified'] and p['lastModified'] < two_weeks_ago and p['status'] == 'active']
    missing_dna = [p for p in projects if not p['hasClaudeMd'] or not p['hasTodoMd'] or not p['hasStartBat']]
    browser_no_chat = [p for p in projects if p['type'] == 'BROWSER' and not p['hasChatWidget'] and p['status'] != 'incoming']

    return jsonify({
        'health': {
            'staleProjects': [{'name': p['name'], 'daysSinceModified': int((time.time() - p['lastModified']) / 86400)} for p in stale],
            'missingDna': [{'name': p['name'], 'missing': _missing_parts(p)} for p in missing_dna],
            'browserNoChatWidget': [p['name'] for p in browser_no_chat],
            'totalOpenTodos': sum(p['openTodos'] for p in projects),
        }
    })


def _missing_parts(p):
    parts = []
    if not p['hasClaudeMd']: parts.append('CLAUDE.md')
    if not p['hasTodoMd']: parts.append('TODO.md')
    if not p['hasStartBat']: parts.append('start.bat')
    return parts


if __name__ == '__main__':
    print(f'Workspace: {WORKSPACE}')
    print(f'Manifest:  {MANIFEST}')
    app.run(host='127.0.0.1', port=5050, debug=False)
