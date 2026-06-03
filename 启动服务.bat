@echo off
chcp 65001 >nul
title Auto Test Platform - Dev Server
cd /d "%~dp0"

echo ========================================
echo   Auto Test Platform
echo   URL: http://127.0.0.1:8000/
echo   Mode: auto reload
echo ========================================
echo.

echo [1/2] Stop existing service on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>nul

echo [2/2] Start service with auto reload...
echo.
.venv\Scripts\python.exe run_server.py --host 127.0.0.1 --port 8000 --reload

echo.
echo Service exited. Press any key to close.
pause >nul
