@echo off
REM Windows CMD entry — .ps1 from cmd opens Notepad unless run via powershell.exe -File
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stack-kit.ps1" %*
exit /b %ERRORLEVEL%
