Set WshShell = CreateObject("WScript.Shell")
WshShell.Run Chr(34) & Replace(WScript.ScriptFullName, "launch.vbs", "start.bat") & Chr(34), 0, False
