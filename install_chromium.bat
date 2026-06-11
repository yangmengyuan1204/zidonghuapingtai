@echo off
chcp 65001 >nul
title Auto Test Platform - Install Chromium
cd /d "%~dp0"

set "PLAYWRIGHT_BROWSERS_PATH=%~dp0ms-playwright"
set "PYTHONPATH=%~dp0.venv\Lib\site-packages;%~dp0"

echo Install Playwright Chromium...
echo Browser path: %PLAYWRIGHT_BROWSERS_PATH%
echo.

set "PYTHON_CMD="
set "PY314=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if exist "%PY314%" (
    "%PY314%" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%PY314%"
)

if not defined PYTHON_CMD if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%VENV_PY%"
)

if defined PYTHON_CMD (
    "%PYTHON_CMD%" -m playwright install chromium
) else (
    py -3.14 -m playwright install chromium
)

echo.
echo Done. Press any key to close.
pause >nul
