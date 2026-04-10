@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0checks-fast.ps1"
exit /b %errorlevel%
