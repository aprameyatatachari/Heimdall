@echo off
REM Stop the Heimdall stack and free its ports. Safe to run at any time.
REM   stop.bat -KeepDatabase   leave PostgreSQL running
REM   stop.bat -Force          stop a port holder that does not look like Heimdall
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1" %*
endlocal
