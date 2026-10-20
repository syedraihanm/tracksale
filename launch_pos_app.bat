@echo off
setlocal
cd /d "%~dp0" || exit /b 1

set "APP_URL=http://127.0.0.1:8000"
set "APP_HEALTH_URL=%APP_URL%/healthz"
set "APP_LOG_DIR=%LOCALAPPDATA%\AmeeMobiles\logs"
if not defined LOCALAPPDATA set "APP_LOG_DIR=%TEMP%\AmeeMobiles\logs"
if not exist "%APP_LOG_DIR%" mkdir "%APP_LOG_DIR%" >nul 2>&1
set "APP_LOG=%APP_LOG_DIR%\launcher.log"

where curl.exe >nul 2>&1
if errorlevel 1 set "USE_POWERSHELL=1"

call :check_health
if not errorlevel 1 goto :open_app

start "" "%SystemRoot%\System32\wscript.exe" //B //NoLogo "%~dp0start_app_silent.vbs"
set "WAIT_COUNT=0"

:wait_for_server
call :check_health
if not errorlevel 1 goto :open_app
set /a WAIT_COUNT+=1
if %WAIT_COUNT% geq 30 goto :server_not_ready
timeout /t 1 /nobreak >nul
goto :wait_for_server

:open_app
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "APP_BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    goto :open_chrome
)
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "APP_BROWSER=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    goto :open_chrome
)
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "APP_BROWSER=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
    goto :open_chrome
)
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    set "APP_BROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
    goto :open_edge
)
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
    set "APP_BROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
    goto :open_edge
)
if exist "%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe" (
    set "APP_BROWSER=%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"
    goto :open_edge
)
start "" "%APP_URL%"
exit /b 0

:open_chrome
start "" "%APP_BROWSER%" --app=%APP_URL%
exit /b 0

:open_edge
start "" "%APP_BROWSER%" --app=%APP_URL%
exit /b 0

:server_not_ready
echo [%date% %time%] Server did not become healthy within 30 seconds.>>"%APP_LOG%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('The repair server did not become ready. Check the log at %APP_LOG%.','Amee Mobiles POS','OK','Error') | Out-Null"
exit /b 1

:check_health
if defined USE_POWERSHELL goto :check_health_powershell
curl.exe --fail --silent --show-error --max-time 2 "%APP_HEALTH_URL%" >nul 2>&1
exit /b %ERRORLEVEL%

:check_health_powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { if ((Invoke-WebRequest -UseBasicParsing -Uri '%APP_HEALTH_URL%' -TimeoutSec 2).StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
exit /b %ERRORLEVEL%
