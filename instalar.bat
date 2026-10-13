@echo off
chcp 65001 >nul
echo ============================================
echo   Instalador de Litch Trading-IA  (v2)
echo ============================================
echo.

:: --- Encontrar Python real (ignorar stub Microsoft Store) ---
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
    echo [ERROR] Python no esta instalado.
    echo Instala Python 3.12 desde https://www.python.org/downloads/
    echo marcando la casilla "Add python.exe to PATH".
    pause
    exit /b 1
)

echo Python detectado: %PY%
"%PY%" --version
echo Actualizando pip...
"%PY%" -m pip install --upgrade pip setuptools wheel --quiet

echo.
echo Instalando librerias...
for %%p in (edge-tts SpeechRecognition mss numpy Pillow pyautogui pyotp qrcode) do (
    echo   instalando %%p...
    "%PY%" -m pip install %%p --quiet
    if errorlevel 1 (echo   [AVISO] %%p fallo. Litch funcionara sin esa parte.) else (echo   %%p OK)
)

echo.
echo Intentando pyaudio (opcional para microfono)...
"%PY%" -m pip install pyaudio --quiet 2>nul || echo   [INFO] pyaudio no disponible para Python 3.14 aun - el microfono estara deshabilitado por ahora.

echo.
echo ============================================
echo  Instalacion terminada.
echo  Ejecuta iniciar.bat para arrancar a Litch.
echo ============================================
pause
