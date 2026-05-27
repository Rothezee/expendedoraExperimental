#Requires -RunAsAdministrator
<#
Genera C:\Expendedora\Expendedora.exe (PyInstaller). Opcional; más fiable que Python en PATH.

  pip install pyinstaller
  powershell -ExecutionPolicy Bypass -File configSO\windows\build_expendedora_exe.ps1 -AppPath C:\Expendedora
#>
param(
    [string]$AppPath = "C:\Expendedora"
)

$ErrorActionPreference = "Stop"
$AppPath = (Resolve-Path $AppPath).Path
$mainPy = Join-Path $AppPath "main.py"
if (-not (Test-Path $mainPy)) {
    throw "No existe $mainPy"
}

$py = Join-Path $AppPath ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    throw "Creá .venv primero (install_cajero_kiosk.ps1 -DeployTo)"
}

& $py -m pip install pyinstaller -q
Push-Location $AppPath
try {
    & $py -m PyInstaller --noconfirm --windowed --name Expendedora `
        --collect-all mysql.connector `
        --hidden-import serial `
        main.py
    $built = Join-Path $AppPath "dist\Expendedora.exe"
    if (Test-Path $built) {
        Copy-Item $built (Join-Path $AppPath "Expendedora.exe") -Force
        Write-Host "OK: $AppPath\Expendedora.exe"
        Write-Host "Copiá config.json, registro.json junto al exe o en $AppPath"
    }
}
finally {
    Pop-Location
}
