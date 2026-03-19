@echo off
chcp 65001 >nul 2>&1
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM GUI mode (default - no arguments)
if "%~1"=="" (
    python gui.py
    goto :end
)

REM CLI mode (with arguments)
python main.py %*

:end
pause
