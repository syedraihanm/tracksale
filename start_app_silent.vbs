Option Explicit

Dim WshShell, fso, strPath, strBatch, strCommand, strComSpec, appDataDir, logDir, logFile, log
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
strBatch = fso.BuildPath(strPath, "run_server.bat")
strComSpec = WshShell.ExpandEnvironmentStrings("%ComSpec%")

If Not fso.FileExists(strBatch) Then
    appDataDir = fso.BuildPath(WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%"), "AmeeMobiles")
    If Not fso.FolderExists(appDataDir) Then fso.CreateFolder appDataDir
    logDir = fso.BuildPath(appDataDir, "logs")
    If Not fso.FolderExists(logDir) Then fso.CreateFolder logDir
    logFile = fso.BuildPath(logDir, "launcher.log")
    Set log = fso.OpenTextFile(logFile, 8, True)
    log.WriteLine Now & " Missing server launcher: " & strBatch
    log.Close
    WScript.Quit 1
End If

' Explicitly run the batch through cmd.exe, hidden and without waiting.
strCommand = Chr(34) & strComSpec & Chr(34) & " /d /c " & Chr(34) & Chr(34) & strBatch & Chr(34) & Chr(34)
WshShell.Run strCommand, 0, False
