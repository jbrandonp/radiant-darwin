@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo  CAD Studio 2026 - Launcher
echo ===================================================

if exist ".venv\Scripts\python.exe" goto use_venv
goto use_system

:use_venv
echo [INFO] Utilisation de l'environnement virtuel local (.venv)...
".venv\Scripts\python.exe" "src\main.py" %*
goto end

:use_system
echo [INFO] Utilisation du Python systeme...
python "src\main.py" %*
goto end

:end
if errorlevel 1 (
    echo.
    echo [ERREUR] Le logiciel s'est arrete avec une erreur.
    pause
)
endlocal
