@echo off
REM Launcher kiosk (Winlogon shell o tarea programada). No debe terminar nunca.
setlocal
set "LAUNCHER=%~dp0launch_expendedora_kiosk.ps1"
set "LOG=%USERPROFILE%\expendedora-kiosk-shell.log"

:loop
echo [%date% %time%] Iniciando launcher>>"%LOG%"
if not exist "%LAUNCHER%" (
    echo [%date% %time%] ERROR launcher no encontrado: %LAUNCHER%>>"%LOG%"
    timeout /t 30 /nobreak >nul
    goto loop
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%LAUNCHER%"
echo [%date% %time%] Launcher finalizado, reiniciando...>>"%LOG%"
timeout /t 5 /nobreak >nul
goto loop
