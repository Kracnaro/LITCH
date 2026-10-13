@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ══════════════════════════════════════════════════════
echo    TRANSCRIBIR UN VIDEO PARA PASARSELO A CLAUDE
echo  ══════════════════════════════════════════════════════
echo.
echo   Pega la URL del reel, TikTok o video de YouTube.
echo   (Tambien vale la ruta de un archivo .mp4 local)
echo.

set /p URL="  URL o ruta: "
if "%URL%"=="" (
    echo.
    echo   No escribiste nada. Salgo.
    pause
    exit /b 1
)

if not exist "TRANSCRIPCIONES" mkdir "TRANSCRIPCIONES"

echo.
echo  ── 1. Buscando subtitulos ya existentes ──────────────
echo.

:: Muchos videos YA traen subtitulos. Si los hay, esto termina
:: en dos segundos y no hace falta transcribir nada.
yt-dlp --skip-download --write-auto-subs --write-subs ^
       --sub-langs "es.*,en.*" --convert-subs srt ^
       -o "TRANSCRIPCIONES/%%(title).60s.%%(ext)s" "%URL%" 2>nul

dir /b "TRANSCRIPCIONES\*.srt" >nul 2>&1
if %errorlevel%==0 (
    echo.
    echo   ✓ Encontre subtitulos. No hace falta transcribir.
    goto :limpiar
)

echo.
echo  ── 2. Sin subtitulos. Descargando el audio ───────────
echo.

yt-dlp -f "bestaudio/best" -x --audio-format mp3 ^
       -o "TRANSCRIPCIONES/audio_temp.%%(ext)s" "%URL%"

if not exist "TRANSCRIPCIONES\audio_temp.mp3" (
    echo.
    echo   [X] No pude descargar el audio.
    echo       Si es de Instagram, puede que pida sesion iniciada.
    echo       Prueba: yt-dlp --cookies-from-browser chrome "%URL%"
    echo.
    pause
    exit /b 1
)

echo.
echo  ── 3. Transcribiendo con Whisper ─────────────────────
echo.
echo   Esto usa tu configuracion de Groq Whisper.
echo   Si falla, transcribe el audio como prefieras: el
echo   archivo esta en TRANSCRIPCIONES\audio_temp.mp3
echo.

whisper "TRANSCRIPCIONES\audio_temp.mp3" --language Spanish ^
        --output_format txt --output_dir "TRANSCRIPCIONES" 2>nul

:limpiar
echo.
echo  ══════════════════════════════════════════════════════
echo    LISTO
echo  ══════════════════════════════════════════════════════
echo.
echo   Los archivos estan en:
echo     %CD%\TRANSCRIPCIONES
echo.
echo   ABRE EL .srt O EL .txt, COPIA EL TEXTO Y PEGAMELO
echo   EN EL CHAT. Con eso ya entiendo el video entero.
echo.
echo   Consejo: si el video ENSEÑA algo en pantalla (menus,
echo   botones, rutas), mandame ademas 3 o 4 capturas de los
echo   momentos clave. El texto me da lo que se dice; las
echo   capturas me dan lo que se ve. Con las dos cosas lo
echo   entiendo completo.
echo.

explorer "TRANSCRIPCIONES"
pause
