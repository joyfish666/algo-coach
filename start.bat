@echo off
rem AlgoCoach launcher: double-click this file to start the local server.
rem coach serves the built frontend and opens the browser automatically once
rem it is ready; closing the browser tabs shuts the server (and this window)
rem down after the idle deadline, and closing the window stops it right away.
rem One-time setup (see docs/zh/USAGE.md): python -m venv .venv,
rem .venv\Scripts\pip install -e ., then build the frontend
rem (cd web && npm install && npm run build).

cd /d "%~dp0"

if not exist "web\dist\index.html" if not exist "server\webdist\index.html" (
    echo The frontend has not been built yet. One-time setup:
    echo   cd web ^&^& npm install ^&^& npm run build
    echo Then double-click this file again.
    pause
    exit /b 1
)

if exist ".venv\Scripts\coach.exe" (
    ".venv\Scripts\coach.exe" --idle-exit 2
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" cli.py --idle-exit 2
) else (
    echo AlgoCoach is not installed yet. One-time setup:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -e .
    echo   cd web ^&^& npm install ^&^& npm run build
    echo Then double-click this file again.
    pause
    exit /b 1
)

rem clean exits (idle shutdown, Ctrl+C) close the window; refusals and
rem startup errors keep it open so the message can be read
set EXITCODE=%errorlevel%
if not "%EXITCODE%"=="0" (
    echo.
    echo [AlgoCoach] exited with code %EXITCODE%. See the message above or coach.log.
    pause
)
