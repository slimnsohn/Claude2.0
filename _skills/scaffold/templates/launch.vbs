' ============================================================
' {PROJECT_NAME} — Headless Launcher
' Double-click this to start the Electron app with no terminal.
' Pin this to Start menu or taskbar for quick access.
'
' To pin: Right-click > Create shortcut > drag to taskbar
'         Or: Right-click shortcut > Pin to Start
' ============================================================

Set WshShell = CreateObject("WScript.Shell")

' Run start.bat in the same directory, window hidden (0), don't wait (False)
WshShell.Run Chr(34) & Replace(WScript.ScriptFullName, WScript.ScriptName, "") & "start.bat" & Chr(34), 0, False

Set WshShell = Nothing
