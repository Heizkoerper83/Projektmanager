@echo off
set "PM_BASE_URL=http://100.80.250.84:8765"
cd /d "%~dp0"
py -3 pr.py
if errorlevel 1 python pr.py
pause
