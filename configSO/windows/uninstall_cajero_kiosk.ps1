#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Revierte la configuración kiosk de Windows para la expendedora.
#>
param(
    [string]$KioskUser = "cajero",
    [switch]$RemoveUser,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$TaskName = "ExpendedoraKioskLauncher"
$profilePath = Join-Path $env:SystemDrive "Users\$KioskUser"
$kioskDir = Join-Path $profilePath "ExpendedoraKiosk"

Write-Host "Desinstalando kiosk Expendedora (usuario: $KioskUser)"

# Auto-login off
$winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
if (-not $WhatIf) {
    Set-ItemProperty -Path $winlogon -Name "AutoAdminLogon" -Value "0" -Type String -Force
    Remove-ItemProperty -Path $winlogon -Name "DefaultPassword" -ErrorAction SilentlyContinue
    Write-Host "  Auto-login deshabilitado."
}

# Tarea programada
if (-not $WhatIf) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "  Tarea $TaskName eliminada."
}

# Restaurar shell explorer
$ntuser = Join-Path $profilePath "NTUSER.DAT"
$tempHive = "ExpendedoraKiosk_$KioskUser"
if ((Test-Path $ntuser) -and -not $WhatIf) {
    reg.exe unload "HKU\$tempHive" 2>$null | Out-Null
    reg.exe load "HKU\$tempHive" $ntuser | Out-Null
    $hiveRoot = "Registry::HKEY_USERS\$tempHive"
    $shellKey = "$hiveRoot\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
    if (Test-Path $shellKey) {
        Remove-ItemProperty -Path $shellKey -Name "Shell" -ErrorAction SilentlyContinue
    }
    reg.exe unload "HKU\$tempHive" | Out-Null
    Write-Host "  Shell restaurado a explorer (eliminar clave Shell)."
}

# Startup
$startup = Join-Path $profilePath "AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ExpendedoraKiosk.vbs"
if ((Test-Path $startup) -and -not $WhatIf) {
    Remove-Item $startup -Force
}

if ($RemoveUser -and -not $WhatIf) {
    Remove-LocalUser -Name $KioskUser -ErrorAction SilentlyContinue
    Write-Host "  Usuario $KioskUser eliminado."
}

Write-Host "Listo. Reiniciá para volver al inicio de sesión normal."
