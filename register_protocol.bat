@echo off
REM register_protocol.bat — Register hermes:// protocol handler in Windows registry
REM Run once as Administrator

reg add "HKCU\Software\Classes\hermes" /ve /d "URL:Hermes Protocol" /f
reg add "HKCU\Software\Classes\hermes" /v "URL Protocol" /d "" /f
reg add "HKCU\Software\Classes\hermes\shell\open\command" /ve /d "wscript.exe \"%~dp0focus_terminal.vbs\"" /f
echo Protocol handler registered: hermes://
