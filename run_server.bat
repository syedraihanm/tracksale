@echo off
setlocal
cd /d "%~dp0"

:: 1. Check if uv is available; fallback to python if not
where uv >nul 2>&1
if %ERRORLEVEL% equ 0 (
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
) else if exist ".venv\Scripts\uvicorn.exe" (
    ".venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port 8000
) else (
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
)
