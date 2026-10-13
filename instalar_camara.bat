@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "data" mkdir "data"
set PYREAL=C:\Users\G\AppData\Local\Python\pythoncore-3.14-64\python.exe
if not exist "%PYREAL%" set PYREAL=C:\Users\G\AppData\Local\Python\bin\python.exe

echo Instalando OpenCV para la camara de Litch...
echo (el resultado queda en data\salida_camara.txt)
echo ===== INSTALACION OPENCV ===== > "data\salida_camara.txt"
"%PYREAL%" --version >> "data\salida_camara.txt" 2>&1

echo --- intento 1: opencv-python (solo binario) --- >> "data\salida_camara.txt"
"%PYREAL%" -m pip install --only-binary=:all: opencv-python >> "data\salida_camara.txt" 2>&1

"%PYREAL%" -c "import cv2; print('CV2 OK', cv2.__version__)" >> "data\salida_camara.txt" 2>&1
if errorlevel 1 (
    echo --- intento 2: opencv-python-headless --- >> "data\salida_camara.txt"
    "%PYREAL%" -m pip install --only-binary=:all: opencv-python-headless >> "data\salida_camara.txt" 2>&1
    "%PYREAL%" -c "import cv2; print('CV2 OK', cv2.__version__)" >> "data\salida_camara.txt" 2>&1
)
echo ===== FIN ===== >> "data\salida_camara.txt"
echo.
echo Listo. Instalacion de camara completada.
pause
