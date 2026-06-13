' Shortcut to ResMap's silent launcher (no-terminal start of both servers + site).
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run """" & here & "\..\apps\resmap\launch.vbs""", 0, False
