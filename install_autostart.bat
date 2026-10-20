@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   Amee Mobiles POS - Setup Autostart on Windows Login
echo ===================================================
echo.

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\AmeeMobilesServer.lnk"

echo Creating autostart shortcut in:
echo "%STARTUP_FOLDER%"
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { $project = (Get-Location).Path; $startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'; $link = Join-Path $startup 'AmeeMobilesServer.lnk'; $script = Join-Path $project 'start_app_silent.vbs'; $ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut($link); $sc.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'; $sc.Arguments = '//B //NoLogo ' + [char]34 + $script + [char]34; $sc.WorkingDirectory = $project; $sc.Description = 'Start Amee Mobiles Server Silently'; $sc.WindowStyle = 7; $sc.Save(); exit 0 } catch { Write-Error $_; exit 1 }"

if errorlevel 1 (
    echo [ERROR] PowerShell could not create the startup shortcut.
    goto :done
)

if exist "%SHORTCUT_PATH%" (
    echo [SUCCESS] Autostart configured successfully!
    echo The POS server will now start silently when the shop user signs in.
) else (
    echo [ERROR] Could not create startup shortcut.
)

echo.
pause

:done
