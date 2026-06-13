Dim strDir, strCmd
strDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
strCmd = """" & strDir & "\node_modules\electron\dist\electron.exe"" """ & strDir & """"
CreateObject("WScript.Shell").Run strCmd, 1, False
