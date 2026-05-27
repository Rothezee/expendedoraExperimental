<#
.SYNOPSIS
    Reaplica shell y restricciones kiosk al usuario (tras primer inicio de sesión).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File configSO\windows\apply_kiosk_user_registry.ps1 -KioskUser cajero
#>
param(
    [string]$KioskUser = "cajero",
    [ValidateSet("Shell", "Startup", "Both")]
    [string]$LaunchMode = "Both"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$registryHelper = Join-Path $ScriptDir "kiosk_registry.ps1"
if (-not (Test-Path $registryHelper)) {
    $registryHelper = Join-Path (Split-Path $ScriptDir -Parent) "windows\kiosk_registry.ps1"
}
. $registryHelper

$kioskDir = Join-Path $env:ProgramData "ExpendedoraKiosk"
$profilePath = Join-Path $env:SystemDrive "Users\$KioskUser"
$launcherCmd = Join-Path $kioskDir "launch_expendedora_kiosk.cmd"
$SetupTaskName = "ExpendedoraKioskApplyRegistry"

if (-not (Test-Path $kioskDir)) {
    throw "No existe $kioskDir. Ejecutá primero install_cajero_kiosk.ps1"
}

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$currentUser = $identity.Name
$isAdmin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)
$runningAsKiosk = $currentUser -match "\\$([regex]::Escape($KioskUser))$"

if ($runningAsKiosk -and -not $isAdmin) {
    Write-Host "Aplicando kiosk en sesión de $KioskUser (HKCU)..."
    Apply-KioskRestrictionsHKCU
    # No configurar Shell aquí: provoca bucle si Python/ruta fallan al reiniciar.
    # La app arranca por tarea ExpendedoraKioskLauncher + Startup.
    Unregister-ScheduledTask -TaskName $SetupTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Listo (solo restricciones). La expendedora arranca por tarea al iniciar sesión."
    exit 0
}

if (-not $isAdmin) {
    throw "Ejecutá como Administrador o iniciá sesión como $KioskUser para aplicar HKCU."
}

$helperDir = Split-Path $registryHelper -Parent
Write-Host "Aplicando registro kiosk para $KioskUser (admin)..."
$ok = Apply-KioskUserRegistry -KioskUser $KioskUser -ProfilePath $profilePath `
    -KioskDir $kioskDir -ScriptDir $helperDir -LaunchMode $LaunchMode
Unregister-ScheduledTask -TaskName $SetupTaskName -Confirm:$false -ErrorAction SilentlyContinue
if ($ok) {
    Write-Host "Listo. Reiniciá o cerrá sesión del usuario $KioskUser para que el shell tome efecto."
}
else {
    Write-Host "No se pudo aplicar todo el registro. Ver mensajes arriba."
}
