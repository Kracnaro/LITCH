@echo off
chcp 65001 >nul
echo Creando acceso directo "Litch Trading-IA" en el escritorio...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Litch Trading-IA.lnk'); $s.TargetPath = '%~dp0iniciar.bat'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0litch.ico'; $s.Description = 'Asistente Litch - Trading IA (IQ Option demo)'; $s.Save()"
if errorlevel 1 (
    echo [ERROR] No se pudo crear el acceso directo.
) else (
    echo Listo. Busca "Litch Trading-IA" en tu escritorio, con su icono.
)
pause
