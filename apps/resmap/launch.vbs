' ResMap silent launcher — double-click to start both servers with NO terminal
' window, then open the website. (start.bat does the same but shows consoles.)
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
py = root & "\.venv\Scripts\python.exe"

' 0 = hidden window, False = don't wait
sh.CurrentDirectory = root
sh.Run "cmd /c """ & py & """ -m uvicorn tool.api.main:app --port 8077", 0, False
sh.Run "cmd /c """ & py & """ -m uvicorn tool.api.control:app --host 127.0.0.1 --port 8078", 0, False
WScript.Sleep 3000
sh.Run """" & root & "\tool\web\index.html""", 1, False
