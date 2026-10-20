@echo off
setlocal
cd /d "%~dp0" || exit /b 1

set "APP_URL=http://127.0.0.1:8000/healthz"
set "APP_LOG_DIR=%LOCALAPPDATA%\AmeeMobiles\logs"
if not defined LOCALAPPDATA set "APP_LOG_DIR=%TEMP%\AmeeMobiles\logs"
if not exist "%APP_LOG_DIR%" mkdir "%APP_LOG_DIR%" >nul 2>&1
set "APP_LOG=%APP_LOG_DIR%\server.log"

where curl.exe >nul 2>&1
if errorlevel 1 goto :check_health_powershell
curl.exe --fail --silent --show-error --max-time 2 "%APP_URL%" >nul 2>&1
if not errorlevel 1 exit /b 0
goto :start_server

:check_health_powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { if ((Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/healthz' -TimeoutSec 2).StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 exit /b 0

:start_server
echo [%date% %time%] Starting Amee Mobiles server from %CD%.>>"%APP_LOG%"
if exist ".venv\Scripts\python.exe" goto :run_venv
where uv.exe >nul 2>&1
if not errorlevel 1 goto :run_uv
goto :run_python

:run_venv
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >>"%APP_LOG%" 2>&1
set "SERVER_EXIT=%ERRORLEVEL%"
goto :server_exited

:run_uv
uv.exe run --no-sync python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >>"%APP_LOG%" 2>&1
set "SERVER_EXIT=%ERRORLEVEL%"
goto :server_exited

:run_python
python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >>"%APP_LOG%" 2>&1
set "SERVER_EXIT=%ERRORLEVEL%"

:server_exited
echo [%date% %time%] Server process exited with code %SERVER_EXIT%.>>"%APP_LOG%"
exit /b %SERVER_EXIT%
