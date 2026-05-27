#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Sale del bucle de reinicio / shell kiosk (ejecutar como Administrador).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File configSO\windows\recover_from_kiosk_loop.ps1
#>
param(
    [string]$KioskUser = "cajero"
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$registryHelper = Join-Path $ScriptDir "kiosk_registry.ps1"
if (Test-Path $registryHelper) {
    . $registryHelper
}

$winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
$profilePath = Join-Path $env:SystemDrive "Users\$KioskUser"
$kioskDir = Join-Path $env:ProgramData "ExpendedoraKiosk"
$TaskName = "ExpendedoraKioskLauncher"
$SetupTaskName = "ExpendedoraKioskApplyRegistry"

Write-Host "=========================================="
Write-Host " Recuperación bucle kiosk"
Write-Host "=========================================="

Write-Host "[1] Desactivando auto-login..."
Set-ItemProperty -Path $winlogon -Name "AutoAdminLogon" -Value "0" -Type String -Force
Remove-ItemProperty -Path $winlogon -Name "DefaultPassword" -ErrorAction SilentlyContinue
if (Get-ItemProperty -Path $winlogon -Name "ForceAutoLogon" -ErrorAction SilentlyContinue) {
    Set-ItemProperty -Path $winlogon -Name "ForceAutoLogon" -Value "0" -Type String -Force
}

Write-Host "[2] Eliminando tareas programadas..."
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $SetupTaskName -Confirm:$false -ErrorAction SilentlyContinue

function Clear-KioskShellInHive {
    param([string]$HiveName)
    $shellKey = "Registry::HKEY_USERS\$HiveName\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
    if (Test-Path $shellKey) {
        Remove-ItemProperty -Path $shellKey -Name "Shell" -ErrorAction SilentlyContinue
        Write-Host "  Shell quitado en HKU\$HiveName"
    }
}

Write-Host "[3] Quitando shell personalizado en perfiles cargados..."
Get-ChildItem -Path Registry::HKEY_USERS -ErrorAction SilentlyContinue | ForEach-Object {
    $name = $_.PSChildName
    if ($name -match '^S-1-5-21-') {
        Clear-KioskShellInHive -HiveName $name
    }
}

$ntuser = Join-Path $profilePath "NTUSER.DAT"
if ((Test-Path -LiteralPath $ntuser) -and (Get-Command Load-NtUserHive -ErrorAction SilentlyContinue)) {
    Write-Host "[4] Quitando shell en NTUSER.DAT offline..."
    $loaded = $false
    try {
        if (-not (Test-KioskUserSessionActive -UserName $KioskUser)) {
            $hive = Load-NtUserHive -NtUserPath $ntuser
            $loaded = $true
            Clear-KioskShellInHive -HiveName $hive
        }
        else {
            Write-Host "  Sesión de $KioskUser activa: cerrala y volvé a ejecutar este script."
        }
    }
    catch {
        Write-Host "  No se pudo cargar NTUSER: $($_.Exception.Message)"
    }
    finally {
        if ($loaded) { Unload-NtUserHive }
    }
}
else {
    Write-Host "[4] NTUSER offline omitido."
}

Write-Host "[5] Quitando Startup VBS..."
$startup = Join-Path $profilePath "AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ExpendedoraKiosk.vbs"
if (Test-Path $startup) {
    Remove-Item $startup -Force
}

Write-Host "[6] Iniciando Explorer (escritorio normal)..."
Start-Process explorer.exe -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Listo. Reiniciá la PC:"
Write-Host "  shutdown /r /t 0"
Write-Host ""
Write-Host "Luego entrá con tu usuario admin (rotha). Para kiosk sin shell custom:"
Write-Host "  install_cajero_kiosk.ps1 -NoPassword -LaunchMode Startup"
