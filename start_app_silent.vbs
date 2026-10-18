Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
' Run run_server.bat hidden (0 = hide window, False = don't wait)
WshShell.Run """" & strPath & "\run_server.bat""", 0, False
