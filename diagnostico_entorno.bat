@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo  Diagnostico del entorno de Litch...

set PY=
set PYREAL=C:\Users\G\AppData\Local\Python\bin\python.exe
if exist "%PYREAL%" set PY=%PYREAL%
if not defined PY (
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        echo %%i | findstr /i "WindowsApps" >nul || (
            if not defined PY set PY=%%i
        )
    )
)
if not defined PY (where py >nul 2>&1 && set PY=py)
if not defined PY (
    echo  [ERROR] Python no se encuentra.
    pause
    exit /b 1
)
"%PY%" diagnostico_entorno.py
pause
