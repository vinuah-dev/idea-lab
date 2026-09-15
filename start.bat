@echo off
setlocal
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo Dependencies not installed yet - running setup.bat first...
  call setup.bat || exit /b 1
)
echo Starting MedOrchestra API on http://localhost:8000 ...
start "MedOrchestra API" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
echo Starting web app on http://localhost:5173 ...
start "MedOrchestra Web" cmd /k "cd /d "%~dp0frontend" && npm run dev"
timeout /t 6 /nobreak >nul
start "" http://localhost:5173
echo.
echo MedOrchestra is running. Close the two console windows to stop it.
echo Demo login: admin / admin123   (more accounts on the login page)
