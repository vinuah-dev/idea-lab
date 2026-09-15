@echo off
setlocal
cd /d "%~dp0"
echo ==============================================
echo   MedOrchestra - one-time setup
echo ==============================================

where python >nul 2>nul || (echo [ERROR] Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
where node >nul 2>nul || (echo [ERROR] Node.js 18+ is required: https://nodejs.org/ & pause & exit /b 1)

echo.
echo [1/3] Creating Python virtual environment...
if not exist "backend\.venv\Scripts\python.exe" python -m venv backend\.venv || goto :fail

echo [2/3] Installing backend packages (FastAPI, OR-Tools, scikit-learn, ...)
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip >nul
"backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt || goto :fail

echo [3/3] Installing frontend packages...
pushd frontend
call npm install --no-fund --no-audit || (popd & goto :fail)
popd

if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul
echo.
echo Setup complete. Run start.bat to launch MedOrchestra.
pause
exit /b 0

:fail
echo.
echo [ERROR] Setup failed - see the messages above.
pause
exit /b 1
