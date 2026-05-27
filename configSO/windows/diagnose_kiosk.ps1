#Requires -RunAsAdministrator
<#
Diagnostico kiosk: rutas, venv, tarea, permisos.
#>
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "kiosk_paths.ps1")

$KioskUser = "cajero"
$TaskName = "ExpendedoraKioskLauncher"
$cfg = Get-KioskConfig
$appPath = Find-KioskAppPath
$venvPy = if ($appPath) { Join-Path $appPath ".venv\Scripts\python.exe" } else { "" }
$py = if ($appPath) { Find-PythonForKiosk -AppPath $appPath } else { $null }
$log = Join-Path $env:SystemDrive "Users\$KioskUser\expendedora-kiosk.log"
$launcher = Join-Path $script:KioskProgramDataDir "launch_expendedora_kiosk.ps1"

$taskState = "NO EXISTE"
try {
    $taskState = (Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop).State
}
catch { }

$autoLogon = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name AutoAdminLogon -ErrorAction SilentlyContinue).AutoAdminLogon

Write-Host "=== Diagnostico kiosk ==="
Write-Host ""
Write-Host "CONFIG ($script:KioskConfigFile)"
if ($cfg) {
    Write-Host "  app_path:   $($cfg.app_path)"
    Write-Host "  python_exe: $($cfg.python_exe)"
    if ($cfg.python_exe -and $appPath -and -not [string]$cfg.python_exe.StartsWith($appPath, [StringComparison]::OrdinalIgnoreCase)) {
        Write-Host "  AVISO: python_exe no coincide con app_path (ruta vieja). Ejecutar repair_kiosk.ps1"
    }
}
Write-Host ""
Write-Host "APP"
Write-Host "  AppPath:    $appPath"
Write-Host "  main.py:    $(Test-Path (Join-Path $appPath 'main.py'))"
Write-Host "  venv local: $(Test-Path -LiteralPath $venvPy)  -> $venvPy"
Write-Host "  Python OK:  $py"
Write-Host ""
Write-Host "KIOSK"
Write-Host "  Launcher:   $(Test-Path $launcher)"
Write-Host "  Tarea:      $taskState"
Write-Host "  AutoLogin:  $autoLogon (esperado: $KioskUser)"
Write-Host "  Log:        $log"
if (Test-Path $log) {
    Write-Host "  --- ultimas lineas ---"
    Get-Content $log -Tail 20 -ErrorAction SilentlyContinue
}
else {
    Write-Host "  (sin log: launcher no corrio como cajero o fallo al inicio)"
}
Write-Host ""

$ok = $true
if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "PROBLEMA: falta .venv en $appPath"
    Write-Host "SOLUCION:"
    Write-Host "  cd $appPath"
    Write-Host "  py -3 -m venv .venv"
    Write-Host "  .\.venv\Scripts\pip.exe install -r requirements.txt"
    Write-Host "  powershell -File configSO\windows\repair_kiosk.ps1 -AppPath $appPath"
    $ok = $false
}
if ($taskState -eq "NO EXISTE") {
    Write-Host "PROBLEMA: falta tarea $TaskName -> repair_kiosk.ps1"
    $ok = $false
}
if ($ok) {
    Write-Host "Configuracion coherente. Probar como cajero:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File `"$launcher`""
}
