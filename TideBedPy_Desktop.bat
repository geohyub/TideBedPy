@echo off
chcp 65001 >nul 2>&1
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
set PYTHONPATH=%SCRIPT_DIR%;%SCRIPT_DIR%\..\..\_shared;%PYTHONPATH%
python -m tidebedpy.desktop
pause
