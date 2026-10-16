@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONPATH=%CD%;%PYTHONPATH%"

echo ===================================================
echo  CAD Studio 2026 - GUI Quick Launcher
echo ===================================================

set "PYTHON_CMD="

if exist ".venv\Scripts\python.exe" (
    echo [INFO] Environnement virtuel local (.venv) detecte.
    set "PYTHON_CMD=.venv\Scripts\python.exe"
    goto run_app
)

where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo [INFO] Moteur uv detecte, execution via uv run...
    uv run python -m src.main %*
    goto check_exit
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    echo [INFO] Utilisation de l'interpreteur Python systeme...
    set "PYTHON_CMD=python"
    goto run_app
)

echo [ERREUR CRITIQUE] Aucun interpreteur Python (.venv, uv, ou systeme) n'a ete trouve sur cette machine.
echo Veuillez executer: uv venv && uv pip install -e ".[dev]"
pause
exit /b 1

:run_app
"%PYTHON_CMD%" -m src.main %*

:check_exit
if %errorlevel% neq 0 (
    echo.
    echo ===================================================
    echo  [CRASH DETECTE] CAD Studio s'est arrete avec le code %errorlevel%.
    echo  Consultez la trace ci-dessus ou debug_run.log.
    echo ===================================================
    pause
)
endlocal
