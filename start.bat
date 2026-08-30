@echo off
rem AlgoCoach launcher: double-click this file to start the local server.
rem coach serves the built frontend and opens the browser automatically once
rem it is ready; closing this window stops the server. One-time setup (see
rem docs/zh/USAGE.md): python -m venv .venv, .venv\Scripts\pip install -e .,
rem then build the frontend (cd web && npm install && npm run build).

cd /d "%~dp0"

if exist ".venv\Scripts\coach.exe" (
    ".venv\Scripts\coach.exe"
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" cli.py
) else (
    echo AlgoCoach is not installed yet. One-time setup:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -e .
    echo   cd web ^&^& npm install ^&^& npm run build
    echo Then double-click this file again.
    pause
    exit /b 1
)

echo.
echo [AlgoCoach] server stopped.
pause
