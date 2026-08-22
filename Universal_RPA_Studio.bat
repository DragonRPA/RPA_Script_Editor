@echo off
chcp 65001 > nul
title Universal RPA Studio
echo ===================================================
echo Universal RPA Studio를 실행합니다...
echo ===================================================
"C:\ProgramData\anaconda3\python.exe" "%~dp0run_recorder.py"
if %errorlevel% neq 0 (
    echo.
    echo [오류] 실행 중 문제가 발생했습니다. (종료 코드: %errorlevel%)
    pause
)
