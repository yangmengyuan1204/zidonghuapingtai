@echo off
chcp 65001 >nul
title Auto Test Platform - Dev Server
cd /d "%~dp0"

echo ========================================
echo   Auto Test Platform
echo   URL: http://127.0.0.1:8000/
echo   Mode: stable
echo ========================================
echo.

echo [1/2] Stop existing service on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>nul

set "PYTHONPATH=%~dp0.venv\Lib\site-packages;%~dp0"
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0ms-playwright"

echo [2/2] Start service...
echo.
set "PYTHON_CMD="
set "PY314=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%VENV_PY%"
)

if not defined PYTHON_CMD if exist "%PY314%" (
    "%PY314%" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%PY314%"
)

if defined PYTHON_CMD (
    "%PYTHON_CMD%" run_server.py --host 127.0.0.1 --port 8000
) else (
    py -3.14 run_server.py --host 127.0.0.1 --port 8000
)

echo.
echo Service exited. Press any key to close.
pause >nul
