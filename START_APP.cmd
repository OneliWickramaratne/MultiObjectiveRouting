@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-hospital.ps1"
if errorlevel 1 (
  echo.
  echo The app could not be started. Review the message above.
  pause
)
endlocal
