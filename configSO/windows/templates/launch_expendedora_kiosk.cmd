@echo off
REM Shell personalizado para usuario kiosk (Winlogon).
setlocal
set "LAUNCHER=%~dp0launch_expendedora_kiosk.ps1"
set "LOG=%USERPROFILE%\expendedora-kiosk-shell.log"

:loop
echo [%date% %time%] Iniciando launcher>>"%LOG%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%LAUNCHER%"
echo [%date% %time%] Launcher finalizado, reiniciando...>>"%LOG%"
timeout /t 3 /nobreak >nul
goto loop
