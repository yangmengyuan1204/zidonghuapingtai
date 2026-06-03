@echo off
chcp 65001 >nul
title Auto Test Platform - Stop Server
cd /d "%~dp0"

echo Stop service on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>nul
taskkill /f /im uvicorn.exe >nul 2>nul

echo Done. Press any key to close.
pause >nul
