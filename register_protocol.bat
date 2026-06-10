@echo off
REM register_protocol.bat — Register hermes:// protocol handler
REM Run once (no admin needed, registers for current user only)

python -c "import winreg; k=winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Classes\hermes');winreg.SetValueEx(k,'',0,winreg.REG_SZ,'URL:Hermes Protocol');winreg.SetValueEx(k,'URL Protocol',0,winreg.REG_SZ,'');winreg.CloseKey(k);k=winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Classes\hermes\shell\open\command');winreg.SetValueEx(k,'',0,winreg.REG_SZ,r'\"C:\Users\24701\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe\" \"C:\Users\24701\AppData\Local\hermes\plugins\win_notify\focus_terminal.py\" \"%1\"');winreg.CloseKey(k);print('hermes:// protocol registered')"
