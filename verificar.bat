@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  Verificando sintaxis de Litch...
echo  ---------------------------------

:: --- Ruta directa al Python real (prioridad maxima) ---
set PY=
set PYREAL=C:\Users\G\AppData\Local\Python\bin\python.exe
if exist "%PYREAL%" set PY=%PYREAL%

:: --- Buscar python en PATH (ignorando stub de Microsoft Store) ---
if not defined PY (
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        echo %%i | findstr /i "WindowsApps" >nul || (
            if not defined PY set PY=%%i
        )
    )
)

:: --- Fallback: py launcher ---
if not defined PY (where py >nul 2>&1 && set PY=py)

if not defined PY (
    echo  [ERROR] Python no se encuentra.
    echo  Ejecuta iniciar.bat una vez para confirmar tu instalacion.
    echo.
    pause
    exit /b 1
)

echo  Python detectado: %PY%
echo.
"%PY%" verificar.py
echo.
pause
