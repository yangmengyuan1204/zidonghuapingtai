@echo off
chcp 65001 >nul
title Auto Test Platform - Dev Server + SSH Tunnel

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
echo   Auto Test Platform + SSH Tunnel
echo   Local : http://127.0.0.1:8000/
echo   Public: (printed by ssh tunnel below)
echo   No signup, no download, no token.
echo ========================================
echo.

echo [1/3] Stop existing service on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>nul

rem ---- locate ssh ----
set "SSH_CMD="
where ssh >nul 2>nul && for /f "delims=" %%i in ('where ssh') do set "SSH_CMD=%%i"
if not defined SSH_CMD if exist "%SystemRoot%\System32\OpenSSH\ssh.exe" set "SSH_CMD=%SystemRoot%\System32\OpenSSH\ssh.exe"

if not defined SSH_CMD (
    echo [ERROR] ssh not found. Install "OpenSSH Client" via Windows Settings - Apps - Optional features.
    pause
    exit /b 1
)

echo [2/3] ssh found: %SSH_CMD%
echo.

set "PYTHONPATH=%PROJECT_DIR%.venv\Lib\site-packages;%PROJECT_DIR%"
set "PLAYWRIGHT_BROWSERS_PATH=%PROJECT_DIR%ms-playwright"

set "PYTHON_CMD="
set "VENV_PY=%PROJECT_DIR%.venv\Scripts\python.exe"
set "SYS_PY311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
set "SYS_PY314=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"

rem Priority 1: virtual env (Python 3.11)
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%VENV_PY%"
)
rem Priority 2: system Python 3.11
if not defined PYTHON_CMD if exist "%SYS_PY311%" (
    "%SYS_PY311%" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%SYS_PY311%"
)
rem Priority 3: system Python 3.14
if not defined PYTHON_CMD if exist "%SYS_PY314%" (
    "%SYS_PY314%" -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=%SYS_PY314%"
)

if not defined PYTHON_CMD (
    echo [ERROR] Python not found. Please install Python 3.11 or 3.14
    pause
    exit /b 1
)

echo [3/3] Starting uvicorn in a new window...
start "uvicorn - 8000" cmd /k "cd /d "%PROJECT_DIR%" && set "PYTHONPATH=%PYTHONPATH%" && set "PLAYWRIGHT_BROWSERS_PATH=%PLAYWRIGHT_BROWSERS_PATH%" && "%PYTHON_CMD%" "%PROJECT_DIR%run_server.py" --host 127.0.0.1 --port 8000"

echo [INFO] Waiting 5s for uvicorn to boot...
timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo   SSH tunnel starting via localhost.run
echo   Look for a https://xxx.lhr.life URL below
echo   Press Ctrl+C in THIS window to stop tunnel
echo ========================================
echo.

"%SSH_CMD%" -o StrictHostKeyChecking=no -o UserKnownHostsFile=NUL -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -R 80:127.0.0.1:8000 nokey@localhost.run

echo.
echo [INFO] Tunnel closed. If it was unstable, try serveo.net backup:
echo        ssh -o StrictHostKeyChecking=no -R 80:localhost:8000 serveo.net
echo.
echo Local uvicorn still running in its own window. Close it to stop service.
pause >nul
