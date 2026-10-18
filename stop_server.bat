@echo off
setlocal
echo Stopping Amee Mobiles POS server...

:: Find and terminate process listening on port 8000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r ":8000\>" ^| findstr "LISTENING"') do (
    echo Terminating PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo Done. Server stopped.
pause
