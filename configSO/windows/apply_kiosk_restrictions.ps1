# Aplica restricciones de escritorio al usuario kiosk (hive HKU cargado o HKCU actual).
param(
    [Parameter(Mandatory = $true)]
    [string]$Sid
)

$ErrorActionPreference = "Stop"

$base = "Registry::HKEY_USERS\$Sid\Software"
$explorer = "$base\Microsoft\Windows\CurrentVersion\Policies\Explorer"
$system = "$base\Microsoft\Windows\CurrentVersion\Policies\System"

function Ensure-Key([string]$Path) {
    if (-not (Test-Path $Path)) {
        New-Item -Path $Path -Force | Out-Null
    }
}

Ensure-Key $explorer
Ensure-Key $system

# Bloquear Win, Alt+Tab parcial, administrador de tareas
New-ItemProperty -Path $explorer -Name "NoWinKeys" -Value 1 -PropertyType DWord -Force | Out-Null
New-ItemProperty -Path $explorer -Name "DisableTaskMgr" -Value 1 -PropertyType DWord -Force | Out-Null
New-ItemProperty -Path $explorer -Name "NoRun" -Value 1 -PropertyType DWord -Force | Out-Null
New-ItemProperty -Path $explorer -Name "NoControlPanel" -Value 1 -PropertyType DWord -Force | Out-Null
New-ItemProperty -Path $explorer -Name "NoFolderOptions" -Value 1 -PropertyType DWord -Force | Out-Null

# Ocultar elementos del escritorio
New-ItemProperty -Path $explorer -Name "NoDesktop" -Value 0 -PropertyType DWord -Force | Out-Null

# Deshabilitar cambio de contraseña desde Ctrl+Alt+Del (opcional kiosk)
New-ItemProperty -Path $system -Name "DisableChangePassword" -Value 1 -PropertyType DWord -Force | Out-Null

# Auto-ocultar barra de tareas
$adv = "$base\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
Ensure-Key $adv
New-ItemProperty -Path $adv -Name "TaskbarAutoHideInMode" -Value 1 -PropertyType DWord -Force | Out-Null
New-ItemProperty -Path $adv -Name "TaskbarSd" -Value 1 -PropertyType DWord -Force | Out-Null

Write-Host "Restricciones aplicadas para SID $Sid"
