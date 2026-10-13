@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo  Iniciando Litch...

:: --- Ruta directa al Python real (prioridad maxima) ---
set PYREAL=C:\Users\G\AppData\Local\Python\bin\python.exe
if exist "%PYREAL%" (
    "%PYREAL%" litch.py
    echo  --- Litch termino. Si hubo un error, aparece arriba. ---
    pause
    goto fin
)

:: --- Buscar python en PATH (ignorando stub de Microsoft Store) ---
for /f "tokens=*" %%i in ('where python 2^>nul') do (
    echo %%i | findstr /i "WindowsApps" >nul || (
        "%%i" litch.py
        goto fin
    )
)

:: --- Fallback: py launcher ---
where py >nul 2>&1
if %errorlevel%==0 (
    py litch.py
    goto fin
)

echo ============================================================
echo  [ERROR] Python no esta instalado o no se encuentra.
echo.
echo  SOLUCION:
echo  1. Abre  https://www.python.org/downloads/
echo  2. Descarga Python 3.12 y ejecuta el instalador.
echo  3. IMPORTANTE: marca [x] Add python.exe to PATH
echo  4. Ejecuta instalar.bat y luego este archivo de nuevo.
echo ============================================================
pause
:fin
