@echo off
REM Start the Heimdall stack: PostgreSQL, migrations, the API and the web app.
REM Each service opens in its own window. Run stop.bat to shut everything down.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
if errorlevel 1 (
  echo.
  pause
)
endlocal
