#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Desinstala modo kiosk (auto-login, tareas, shell, restricciones).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File configSO\windows\uninstall_cajero_kiosk.ps1 -KioskUser cajero
#>
param(
    [string]$KioskUser = "cajero",
    [switch]$RemoveUser,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "kiosk_registry.ps1")
. (Join-Path $ScriptDir "kiosk_paths.ps1")

$TaskName = "ExpendedoraKioskLauncher"
$SetupTaskName = "ExpendedoraKioskApplyRegistry"
$kioskDir = Join-Path $env:ProgramData "ExpendedoraKiosk"
$profilePath = Join-Path $env:SystemDrive "Users\$KioskUser"
$winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"

function Do-Step([string]$Message, [scriptblock]$Action) {
    Write-Host $Message
    if (-not $WhatIf) {
        & $Action
    }
    else {
        Write-Host "  (WhatIf)"
    }
}

Write-Host "Desinstalando kiosk para usuario: $KioskUser"

Do-Step "[1] Quitando auto-login..." {
    Set-ItemProperty -Path $winlogon -Name "AutoAdminLogon" -Value "0" -Type String -Force
    Remove-ItemProperty -Path $winlogon -Name "DefaultPassword" -ErrorAction SilentlyContinue
    if (Get-ItemProperty -Path $winlogon -Name "ForceAutoLogon" -ErrorAction SilentlyContinue) {
        Set-ItemProperty -Path $winlogon -Name "ForceAutoLogon" -Value "0" -Type String -Force
    }
}

Do-Step "[2] Eliminando tareas programadas..." {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $SetupTaskName -Confirm:$false -ErrorAction SilentlyContinue
}

Do-Step "[3] Restaurando shell y restricciones en NTUSER..." {
    if (-not (Test-KioskUserSessionActive -UserName $KioskUser)) {
        $ntuser = Join-Path $profilePath "NTUSER.DAT"
        if (Test-Path -LiteralPath $ntuser) {
            $hiveLoaded = $false
            try {
                $hiveName = Load-NtUserHive -NtUserPath $ntuser
                $hiveLoaded = $true
                $hiveRoot = "Registry::HKEY_USERS\$hiveName"
                $userWinlogon = "$hiveRoot\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
                if (Test-Path $userWinlogon) {
                    Remove-ItemProperty -Path $userWinlogon -Name "Shell" -ErrorAction SilentlyContinue
                }
                $explorer = "$hiveRoot\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
                $system = "$hiveRoot\Software\Microsoft\Windows\CurrentVersion\Policies\System"
                foreach ($key in @($explorer, $system)) {
                    if (Test-Path $key) {
                        Remove-Item -Path $key -Recurse -Force -ErrorAction SilentlyContinue
                    }
                }
            }
            finally {
                if ($hiveLoaded) { Unload-NtUserHive }
            }
        }
    }
    else {
        Write-Host "  Sesión activa de $KioskUser: shell/restricciones quedan para próximo logoff manual."
    }
}

Do-Step "[4] Quitando Startup del usuario..." {
    $startup = Join-Path $profilePath "AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
    $vbs = Join-Path $startup "ExpendedoraKiosk.vbs"
    if (Test-Path $vbs) { Remove-Item $vbs -Force }
}

Do-Step "[4b] Quitando acceso directo del escritorio..." {
    if (Get-Command Remove-KioskDesktopShortcut -ErrorAction SilentlyContinue) {
        Remove-KioskDesktopShortcut -KioskUser $KioskUser
    }
}

Do-Step "[5] Limpiando ProgramData..." {
    if (Test-Path $kioskDir) {
        Remove-Item $kioskDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($RemoveUser) {
    Do-Step "[6] Eliminando usuario local..." {
        if (Test-KioskUserSessionActive -UserName $KioskUser) {
            throw "Cerrá la sesión de $KioskUser antes de eliminarlo."
        }
        Remove-LocalUser -Name $KioskUser -ErrorAction Stop
    }
}

Write-Host ""
Write-Host "Kiosk desinstalado. Reiniciá la PC."
