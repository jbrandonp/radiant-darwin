@echo off
title CAD Studio - Demarrage
cd /d "%~dp0"
echo ========================================================
echo Demarrage de CAD Studio (Suite CAO / FEA / CAM / Dessin)...
echo ========================================================
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0src\main.py"
exit
