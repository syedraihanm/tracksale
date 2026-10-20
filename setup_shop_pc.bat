@echo off
setlocal
cd /d "%~dp0" || exit /b 1

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_shop_pc.ps1"
set "SETUP_EXIT=%ERRORLEVEL%"

if not "%SETUP_EXIT%"=="0" (
    echo.
    echo Setup did not finish. Check "%LOCALAPPDATA%\AmeeMobiles\logs\setup.log" for details.
    pause
    exit /b %SETUP_EXIT%
)

echo.
echo Setup is complete. Double-click "Amee Mobiles POS" on the Desktop.
pause
