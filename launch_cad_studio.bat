@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONPATH=%CD%;%PYTHONPATH%"

echo ===================================================
echo  CAD Studio 2026 - Launcher
echo ===================================================

if exist ".venv\Scripts\python.exe" (
    echo [INFO] Utilisation de l'environnement virtuel local (.venv)...
    ".venv\Scripts\python.exe" -m src.main %*
    goto check_exit
)

where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo [INFO] Utilisation de uv run...
    uv run python -m src.main %*
    goto check_exit
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    echo [INFO] Utilisation du Python systeme...
    python -m src.main %*
    goto check_exit
)

echo [ERREUR] Aucun interpreteur Python valide detecte (.venv, uv ou systeme).
pause
exit /b 1

:check_exit
if %errorlevel% neq 0 (
    echo.
    echo ===================================================
    echo  [ERREUR] Le logiciel s'est arrete avec le code %errorlevel%.
    echo ===================================================
    pause
)
endlocal
