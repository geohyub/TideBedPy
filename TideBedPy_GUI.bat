@echo off
chcp 65001 >nul 2>&1
title TideBedPy - 조석보정 프로그램

REM 스크립트 위치 기준으로 tidebedpy 폴더 이동
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%tidebedpy"

REM Python 탐색
where python >nul 2>&1
if %errorlevel%==0 (
    python gui.py
    goto :end
)

REM Python 전체 경로 시도
if exist "C:\Program Files\Python312\python.exe" (
    "C:\Program Files\Python312\python.exe" gui.py
    goto :end
)
if exist "C:\Program Files\Python311\python.exe" (
    "C:\Program Files\Python311\python.exe" gui.py
    goto :end
)

REM py 런처 시도
where py >nul 2>&1
if %errorlevel%==0 (
    py gui.py
    goto :end
)

echo [ERROR] Python을 찾을 수 없습니다.
echo Python 3.10 이상을 설치해주세요: https://www.python.org/downloads/
pause

:end
