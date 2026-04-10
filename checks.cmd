@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0checks.ps1"
exit /b %errorlevel%
