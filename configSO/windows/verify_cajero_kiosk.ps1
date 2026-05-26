#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Verifica que la configuración kiosk esté presente.
#>
param(
    [string]$KioskUser = "cajero",
    [string]$AppPath = ""
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
if (-not $AppPath) { $AppPath = $RepoRoot.Path }

$ok = $true
function Test-Check([string]$Name, [bool]$Pass, [string]$Detail = "") {
    $script:ok = $script:ok -and $Pass
    $mark = if ($Pass) { "[OK]" } else { "[FAIL]" }
    Write-Host "$mark $Name $(if ($Detail) { "- $Detail" })"
}

Write-Host "Verificación Kiosk Windows - usuario $KioskUser"
Write-Host ""

$user = Get-LocalUser -Name $KioskUser -ErrorAction SilentlyContinue
Test-Check "Usuario local existe" ([bool]$user) $(if ($user) { $user.Enabled } else { "no encontrado" })

$admins = Get-LocalGroupMember -Group "Administrators" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "\\$KioskUser$" }
Test-Check "Usuario NO es administrador" (-not $admins)

Test-Check "main.py accesible" (Test-Path (Join-Path $AppPath "main.py")) $AppPath

$winlogon = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -ErrorAction SilentlyContinue
Test-Check "AutoAdminLogon" ($winlogon.AutoAdminLogon -eq "1") "user=$($winlogon.DefaultUserName)"

$task = Get-ScheduledTask -TaskName "ExpendedoraKioskLauncher" -ErrorAction SilentlyContinue
Test-Check "Tarea ExpendedoraKioskLauncher" ([bool]$task) $(if ($task) { $task.State })

$launcher = Join-Path $env:SystemDrive "Users\$KioskUser\ExpendedoraKiosk\launch_expendedora_kiosk.ps1"
Test-Check "Launcher en perfil" (Test-Path $launcher) $launcher

$py = $false
if (Get-Command py -ErrorAction SilentlyContinue) { $py = $true }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $py = $true }
Test-Check "Python disponible" $py

Write-Host ""
if ($ok) {
    Write-Host "Resultado: configuración kiosk parece correcta."
    exit 0
}
Write-Host "Resultado: hay problemas. Re-ejecutá install_cajero_kiosk.ps1 como administrador."
exit 1
