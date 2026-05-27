@echo off

REM Arranque expendedora (usuario kiosk). Muestra login de la app (sin EXPENDEDORA_KIOSK).

setlocal EnableExtensions

set "APP=__APP_PATH__"

set "LOG=%USERPROFILE%\expendedora-kiosk.log"

set "PYFILE=C:\ProgramData\ExpendedoraKiosk\python_exe.txt"



if not exist "%APP%\main.py" (

    echo [%date% %time%] ERROR: no existe %APP%\main.py>>"%LOG%"

    echo No se encontro la aplicacion en %APP%

    pause

    exit /b 1

)



set "PY="

if exist "%PYFILE%" (

    set /p PY=<"%PYFILE%"

)

if not defined PY set "PY=%APP%\.venv\Scripts\python.exe"



if not exist "%PY%" (

    echo [%date% %time%] ERROR: Python no encontrado: %PY%>>"%LOG%"

    echo.

    echo Como ADMIN ejecute:

    echo   repair_kiosk.ps1 -AppPath %APP%

    echo.

    pause

    exit /b 1

)



cd /d "%APP%"

echo [%date% %time%] Iniciando main.py (con login)>>"%LOG%"

"%PY%" "%APP%\main.py"

set "RC=%ERRORLEVEL%"

echo [%date% %time%] Salida codigo %RC%>>"%LOG%"

exit /b %RC%

