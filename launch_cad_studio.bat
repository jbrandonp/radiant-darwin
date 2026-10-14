@echo off
title CAD Studio 2026 - Launcher
cd /d "%~dp0"
echo Lancement de CAD Studio 2026 (NEXUS-3D Enterprise)...
".venv\Scripts\python.exe" "src\main.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERREUR] Le logiciel s'est arrete avec le code d'erreur %ERRORLEVEL%.
    pause
)
