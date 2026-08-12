@echo off
chcp 65001 >nul
title Auto Test Platform - Dev Server

rem ---- locate project root (%~dp0 may be Desktop if bat copied) ----
set "PROJECT_DIR=%~dp0"
if exist "%PROJECT_DIR%run_server.py" goto :FOUND
if exist "D:\A_zidonghuapingtai\run_server.py" set "PROJECT_DIR=D:\A_zidonghuapingtai\" & goto :FOUND

echo [ERROR] Cannot find project directory (run_server.py not found)
echo [INFO]  Expected location: D:\A_zidonghuapingtai
pause
exit /b 1

:FOUND
cd /d "%PROJECT_DIR%"

echo ========================================
echo   Auto Test Platform - Frontend V3
echo   URL: http://127.0.0.1:8000/v3/login?ui=20260812-v3-enterprise-3
echo   Mode: stable
echo ========================================
echo.

echo [1/2] Stop existing service on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>nul

set "PYTHONPATH=%PROJECT_DIR%.venv\Lib\site-packages;%PROJECT_DIR%"
set "PLAYWRIGHT_BROWSERS_PATH=%PROJECT_DIR%ms-playwright"

echo [2/2] Start service...
echo.
set "PYTHON_CMD="
set "VENV_PY=%PROJECT_DIR%.venv\Scripts\python.exe"
set "SYS_PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
set "SYS_PY314=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"

rem Priority 1: virtual env (Python 3.11)
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%VENV_PY%"
)

rem Priority 2: system Python 3.11 (same version as venv)
if not defined PYTHON_CMD if exist "%SYS_PY311%" (
    "%SYS_PY311%" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%SYS_PY311%"
)

rem Priority 3: system Python 3.14
if not defined PYTHON_CMD if exist "%SYS_PY314%" (
    "%SYS_PY314%" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%SYS_PY314%"
)

if defined PYTHON_CMD (
    rem Wait until the API is ready, then open the cache-busted V3 login page.
    start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "$url='http://127.0.0.1:8000/v3/login?ui=20260812-v3-enterprise-3'; for($i=0; $i -lt 40; $i++){ try { Invoke-WebRequest 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 1 | Out-Null; Start-Process $url; break } catch { Start-Sleep -Milliseconds 500 } }"
    "%PYTHON_CMD%" "%PROJECT_DIR%run_server.py" --host 127.0.0.1 --port 8000
) else (
    echo [ERROR] Python not found. Please install Python 3.11 or 3.14
    pause
    exit /b 1
)

echo.
echo Service exited. Press any key to close.
pause >nul
