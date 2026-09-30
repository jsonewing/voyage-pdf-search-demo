@echo off
setlocal
cd /d "%~dp0"
if "%PORT%"=="" set PORT=8020

python -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info < (3, 14) else 1)" >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python 3.11, 3.12, or 3.13 is required by this launcher.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the local Python environment...
  python -m venv .venv || goto :error
  .venv\Scripts\pip.exe install --require-hashes -r requirements.lock || goto :error
)

start "" /b powershell -NoProfile -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:%PORT%/'"
echo Starting Voyage PDF Search at http://127.0.0.1:%PORT%/
echo Press Ctrl+C to stop.
set PYTHONPATH=.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
exit /b %errorlevel%

:error
echo Setup failed. Confirm a supported Python version is installed and try again.
pause
exit /b 1
