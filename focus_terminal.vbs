' focus_terminal.vbs — Run focus_terminal.ps1 completely hidden
' VBScript can hide the PowerShell window that .bat cannot
Set objShell = CreateObject("WScript.Shell")
strPath = Replace(WScript.ScriptFullName, WScript.ScriptName, "")
objShell.Run "powershell.exe -ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File """ & strPath & "focus_terminal.ps1""", 0, False
