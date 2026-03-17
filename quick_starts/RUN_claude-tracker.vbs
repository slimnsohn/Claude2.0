Set WshShell = CreateObject("WScript.Shell")
WshShell.Run Chr(34) & Replace(WScript.ScriptFullName, "RUN_claude-tracker.vbs", "claude-tracker_start.bat") & Chr(34), 0, False
