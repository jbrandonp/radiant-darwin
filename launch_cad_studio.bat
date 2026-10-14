@echo off
title CAD Studio 2026 - Launcher
cd /d "%~dp0"
echo ===================================================
echo  CAD Studio 2026 (NEXUS-3D Enterprise) - Launcher
echo ===================================================

if exist ".venv\Scripts\python.exe" (
    echo [INFO] Utilisation de l'environnement virtuel local (.venv)...
    ".venv\Scripts\python.exe" "src\main.py" %*
) else (
    echo [INFO] Utilisation du Python systeme...
    python "src\main.py" %*
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERREUR] Le logiciel s'est arrete avec le code d'erreur %ERRORLEVEL%.
    pause
)
