@echo off
chcp 65001 >nul 2>&1
title TideBedPy CLI

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%tidebedpy"

REM Python 탐색
set PYTHON=
where python >nul 2>&1 && set PYTHON=python
if not defined PYTHON (
    if exist "C:\Program Files\Python312\python.exe" set PYTHON="C:\Program Files\Python312\python.exe"
)
if not defined PYTHON (
    where py >nul 2>&1 && set PYTHON=py
)
if not defined PYTHON (
    echo [ERROR] Python을 찾을 수 없습니다.
    pause
    exit /b 1
)

REM 인수가 없으면 사용법 표시
if "%~1"=="" (
    echo.
    echo   TideBedPy CLI - 조석보정 프로그램
    echo   ─────────────────────────────────
    echo   사용법: TideBedPy_CLI.bat [옵션]
    echo.
    %PYTHON% main.py --help
    pause
    exit /b 0
)

%PYTHON% main.py %*
if errorlevel 1 (
    echo.
    echo [ERROR] TideBedPy 오류 발생 (코드: %errorlevel%)
    pause
)
