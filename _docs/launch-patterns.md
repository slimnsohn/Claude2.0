# Launch Patterns

## Browser Projects

Every browser project has a `start.bat` in its root. Double-click it and it:

1. Detects project type (Node, Python, or static HTML)
2. Installs dependencies if missing (first run only)
3. Starts the dev server
4. Opens the browser to the right port

No terminal knowledge needed. One click.

## Electron Projects

Electron projects have two files:

| File | What it does |
|------|-------------|
| `start.bat` | Installs deps + launches Electron. Shows terminal output. |
| `launch.vbs` | Calls start.bat invisibly. No terminal window appears. |

**For daily use:** double-click `launch.vbs` (or pin it to Start/taskbar).  
**For debugging:** double-click `start.bat` to see console output.

### Pinning to Start Menu

1. Right-click `launch.vbs` > **Create shortcut**
2. Move shortcut to `%AppData%\Microsoft\Windows\Start Menu\Programs\`
3. Rename it to the app name
4. Optional: right-click shortcut > Properties > Change Icon to customize

### Pinning to Taskbar

1. Create a shortcut to `launch.vbs`
2. Right-click shortcut > Properties
3. Change Target to: `wscript.exe "C:\full\path\to\launch.vbs"`
4. Now you can pin it to taskbar

### Error Logging

If the app fails to start from `launch.vbs`, check `launch-error.log` in the project folder.
