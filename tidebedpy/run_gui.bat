@echo off
chcp 65001 >nul 2>&1
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
python gui.py
pause
