Dim fso, shell, strProjectDir, strCmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
strProjectDir = fso.GetAbsolutePathName(fso.GetParentFolderName(WScript.ScriptFullName) & "\..\shipped\sportsbook-tools-desktop")
shell.CurrentDirectory = strProjectDir
strCmd = """" & strProjectDir & "\node_modules\electron\dist\electron.exe"" """ & strProjectDir & """"
shell.Run strCmd, 1, False
