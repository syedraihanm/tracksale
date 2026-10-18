@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   Amee Mobiles POS - Setup Autostart on PC Boot
echo ===================================================
echo.

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\AmeeMobilesServer.lnk"
set "VBS_SCRIPT=%~dp0start_app_silent.vbs"

echo Creating autostart shortcut in:
echo "%STARTUP_FOLDER%"
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT_PATH%'); $sc.TargetPath = '%VBS_SCRIPT%'; $sc.WorkingDirectory = '%~dp0'; $sc.Description = 'Start Amee Mobiles Server Silently'; $sc.Save()"

if exist "%SHORTCUT_PATH%" (
    echo [SUCCESS] Autostart configured successfully!
    echo The POS server will now start silently whenever this PC boots or logs in.
) else (
    echo [ERROR] Could not create startup shortcut.
)

echo.
pause
