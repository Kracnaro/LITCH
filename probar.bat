@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYREAL=C:\Users\G\AppData\Local\Python\pythoncore-3.14-64\python.exe
if not exist "%PYREAL%" set PYREAL=C:\Users\G\AppData\Local\Python\bin\python.exe
echo Lanzando Litch y guardando salida en data\salida_litch.txt ...
if not exist "data" mkdir "data"
"%PYREAL%" litch.py > "data\salida_litch.txt" 2>&1
echo.
echo Litch se cerro. Revisa data\salida_litch.txt para ver que paso.
pause
