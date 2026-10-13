@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Ejecutando diagnostico... espera unos segundos.
echo ================ DIAGNOSTICO LITCH ================ > diagnostico.txt
echo Fecha: %date% %time% >> diagnostico.txt
echo. >> diagnostico.txt

echo --- where python --- >> diagnostico.txt
where python >> diagnostico.txt 2>&1
echo --- python --version --- >> diagnostico.txt
python --version >> diagnostico.txt 2>&1
echo --- where py --- >> diagnostico.txt
where py >> diagnostico.txt 2>&1
echo --- py --version --- >> diagnostico.txt
py --version >> diagnostico.txt 2>&1
echo. >> diagnostico.txt

echo --- pip list (python) --- >> diagnostico.txt
python -m pip list >> diagnostico.txt 2>&1
echo --- pip list (py) --- >> diagnostico.txt
py -m pip list >> diagnostico.txt 2>&1
echo. >> diagnostico.txt

echo --- INTENTO DE ARRANQUE DE LITCH (python) --- >> diagnostico.txt
python litch.py >> diagnostico.txt 2>&1
echo --- INTENTO DE ARRANQUE DE LITCH (py) --- >> diagnostico.txt
py litch.py >> diagnostico.txt 2>&1
echo. >> diagnostico.txt
echo ================ FIN DIAGNOSTICO ================ >> diagnostico.txt

echo.
echo Listo. Se creo el archivo diagnostico.txt en esta carpeta.
echo Revisa el archivo de diagnostico generado.
pause
