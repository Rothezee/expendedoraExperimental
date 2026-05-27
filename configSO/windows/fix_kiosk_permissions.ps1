#Requires -RunAsAdministrator
<#
Corrige permisos de cajero sobre la carpeta de la app (p. ej. C:\expendedoraExperimental).
Quita Startup duplicado (solo queda tarea + acceso directo).

  powershell -ExecutionPolicy Bypass -File configSO\windows\fix_kiosk_permissions.ps1
#>
param(
    [string]$KioskUser = "cajero",
    [string]$AppPath = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "kiosk_paths.ps1")

$kioskDir = $script:KioskProgramDataDir
$profilePath = Join-Path $env:SystemDrive "Users\$KioskUser"

Write-Host "Corrigiendo permisos para $KioskUser ..."

if (-not $AppPath) {
    $AppPath = Find-KioskAppPath
}
if (-not $AppPath) {
    throw "No se encontró la app. Usá -AppPath C:\expendedoraExperimental"
}
$AppPath = (Resolve-Path -LiteralPath $AppPath).Path
Write-Host "AppPath: $AppPath"

Grant-KioskAppAccess -AppPath $AppPath -KioskUser $KioskUser
Grant-KioskPathAcl -Path $kioskDir -KioskUser $KioskUser

$launcherPs1 = Join-Path $kioskDir "launch_expendedora_kiosk.ps1"
if (Test-Path $launcherPs1) {
    $sid = Get-KioskUserSid -KioskUser $KioskUser
    if ($sid) {
        icacls $launcherPs1 /grant "*${sid}:RX" /C 2>$null | Out-Null
    }
}

# Un solo arranque automático: tarea (no Startup VBS duplicado).
$startup = Join-Path $profilePath "AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
$vbs = Join-Path $startup "ExpendedoraKiosk.vbs"
if (Test-Path $vbs) {
    Remove-Item $vbs -Force
    Write-Host "  Eliminado Startup duplicado: $vbs"
}

Write-Host ""
Write-Host "Listo. Reiniciá sesión de $KioskUser o la PC."
Write-Host "Si sigue 'acceso denegado' en COM/ESP32, probá puerto con admin o tarea con privilegios elevados."
