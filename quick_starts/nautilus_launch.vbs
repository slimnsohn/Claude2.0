' Shortcut to apps\nautilus\launch.vbs — starts nautilus with no terminal.
Dim fso, shell, strLauncher
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
strLauncher = fso.GetAbsolutePathName(fso.GetParentFolderName(WScript.ScriptFullName) & "\..\apps\nautilus\launch.vbs")
shell.Run "wscript.exe """ & strLauncher & """", 0, False
