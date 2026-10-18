@echo off
setlocal
cd /d "%~dp0"

:: Check if server is running on port 8000
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if %ERRORLEVEL% neq 0 (
    start "" wscript.exe "%~dp0start_app_silent.vbs"
    timeout /t 2 /nobreak >nul
)

:: Launch browser in standalone app mode
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --app=http://localhost:8000
) else (
    start "" http://localhost:8000
)
