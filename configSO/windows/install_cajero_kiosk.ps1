#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Configura Windows 11 en modo kiosk para la expendedora (usuario cajero).

.DESCRIPTION
    - Crea usuario local limitado
    - Auto-login al arrancar
    - Shell personalizado que mantiene main.py en ejecución
    - Tarea programada de respaldo al iniciar sesión
    - Restricciones básicas de escritorio

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File configSO\windows\install_cajero_kiosk.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File configSO\windows\install_cajero_kiosk.ps1 `
        -KioskUser cajero -Password 'MiClaveSegura!' -AppPath 'C:\Expendedora'
#>
param(
    [string]$KioskUser = "cajero",
    [string]$Password = "cajero123",
    [string]$AppPath = "",
    [ValidateSet("Shell", "Startup", "Both")]
    [string]$LaunchMode = "Both",
    [switch]$SkipAutoLogon,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$TemplateDir = Join-Path $ScriptDir "templates"
$TaskName = "ExpendedoraKioskLauncher"
$KioskFolderName = "ExpendedoraKiosk"

if (-not $AppPath) {
    $AppPath = $RepoRoot.Path
}

Write-Host "=============================================="
Write-Host " Configuración Kiosk Expendedora (Windows 11)"
Write-Host "=============================================="
Write-Host "Usuario kiosk : $KioskUser"
Write-Host "App path      : $AppPath"
Write-Host "Modo arranque : $LaunchMode"
Write-Host ""

if (-not (Test-Path (Join-Path $AppPath "main.py"))) {
    throw "No se encontró main.py en AppPath: $AppPath"
}

# --- Usuario local ---
Write-Host "[1/7] Creando usuario kiosk..."
$user = Get-LocalUser -Name $KioskUser -ErrorAction SilentlyContinue
if (-not $user) {
    if ($WhatIf) {
        Write-Host "  (WhatIf) New-LocalUser $KioskUser"
    }
    else {
        $secPassword = ConvertTo-SecureString $Password -AsPlainText -Force
        New-LocalUser -Name $KioskUser -Password $secPassword -FullName "Cajero Expendedora" `
            -Description "Usuario kiosk expendedora" -PasswordNeverExpires | Out-Null
        Write-Host "  Usuario $KioskUser creado."
    }
}
else {
    Write-Host "  Usuario $KioskUser ya existe."
    if (-not $WhatIf) {
        $secPassword = ConvertTo-SecureString $Password -AsPlainText -Force
        Set-LocalUser -Name $KioskUser -Password $secPassword -ErrorAction SilentlyContinue
    }
}

if (-not $WhatIf) {
    Add-LocalGroupMember -Group "Users" -Member $KioskUser -ErrorAction SilentlyContinue
    # Quitar de Administradores si estuviera
    Remove-LocalGroupMember -Group "Administrators" -Member $KioskUser -ErrorAction SilentlyContinue
}

# --- Perfil y carpeta kiosk ---
$profilePath = Join-Path $env:SystemDrive "Users\$KioskUser"
$kioskDir = Join-Path $profilePath $KioskFolderName

Write-Host "[2/7] Preparando perfil y launcher..."
if (-not $WhatIf) {
    if (-not (Test-Path $profilePath)) {
        # Crear perfil mínimo copiando Default (sin login previo)
        $defaultProfile = Join-Path $env:SystemDrive "Users\Default"
        if (Test-Path $defaultProfile) {
            Write-Host "  Copiando perfil Default -> $KioskUser (primera vez)"
            robocopy $defaultProfile $profilePath /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS | Out-Null
        }
    }
    New-Item -ItemType Directory -Path $kioskDir -Force | Out-Null

    $launcherPs1 = Join-Path $kioskDir "launch_expendedora_kiosk.ps1"
    $launcherCmd = Join-Path $kioskDir "launch_expendedora_kiosk.cmd"
    $templatePs1 = Get-Content (Join-Path $TemplateDir "launch_expendedora_kiosk.ps1") -Raw
    $escapedAppPath = $AppPath.Replace("'", "''")
    $templatePs1 = $templatePs1.Replace("__APP_PATH__", $escapedAppPath)
    Set-Content -Path $launcherPs1 -Value $templatePs1 -Encoding UTF8
    Copy-Item (Join-Path $TemplateDir "launch_expendedora_kiosk.cmd") $launcherCmd -Force

    # Permisos de lectura/ejecución en la app
    icacls $AppPath /grant "${KioskUser}:(RX)" /T /C | Out-Null
    # Escritura en archivos de datos locales (registro, config si vive en app path)
    icacls $AppPath /grant "${KioskUser}:(M)" /C | Out-Null
}

# --- Auto-login ---
Write-Host "[3/7] Configurando auto-login..."
$winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
if (-not $SkipAutoLogon) {
    if ($WhatIf) {
        Write-Host "  (WhatIf) AutoAdminLogon para $KioskUser"
    }
    else {
        Set-ItemProperty -Path $winlogon -Name "AutoAdminLogon" -Value "1" -Type String -Force
        Set-ItemProperty -Path $winlogon -Name "DefaultUserName" -Value $KioskUser -Type String -Force
        Set-ItemProperty -Path $winlogon -Name "DefaultPassword" -Value $Password -Type String -Force
        Set-ItemProperty -Path $winlogon -Name "DefaultDomainName" -Value "." -Type String -Force
        if (Get-ItemProperty -Path $winlogon -Name "ForceAutoLogon" -ErrorAction SilentlyContinue) {
            Set-ItemProperty -Path $winlogon -Name "ForceAutoLogon" -Value "1" -Type String -Force
        }
        Write-Host "  Auto-login configurado (cambiá la contraseña luego con install o lusrmgr)."
    }
}
else {
    Write-Host "  Auto-login omitido (-SkipAutoLogon)."
}

# --- Shell personalizado (HKU) ---
Write-Host "[4/7] Configurando shell / startup..."
$sid = $null
try {
    $acct = New-Object System.Security.Principal.NTAccount($KioskUser)
    $sid = $acct.Translate([System.Security.Principal.SecurityIdentifier]).Value
}
catch {
    Write-Host "  Aviso: no se pudo resolver SID (se aplicará en primer inicio)."
}

if ($sid -and -not $WhatIf) {
    $ntuser = Join-Path $profilePath "NTUSER.DAT"
    $hiveLoaded = $false
    $tempHive = "ExpendedoraKiosk_$KioskUser"
    try {
        if (Test-Path $ntuser) {
            reg.exe unload "HKU\$tempHive" 2>$null | Out-Null
            reg.exe load "HKU\$tempHive" $ntuser | Out-Null
            $hiveLoaded = $true
            $hiveRoot = "Registry::HKEY_USERS\$tempHive"

            if ($LaunchMode -in @("Shell", "Both")) {
                $shellCmd = Join-Path $kioskDir "launch_expendedora_kiosk.cmd"
                $shellPath = "cmd.exe /c `"$shellCmd`""
                Set-ItemProperty -Path "$hiveRoot\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" `
                    -Name "Shell" -Value $shellPath -Force
                Write-Host "  Shell kiosk: $shellPath"
            }

            & (Join-Path $ScriptDir "apply_kiosk_restrictions.ps1") -Sid $tempHive

            [gc]::Collect()
            Start-Sleep -Seconds 1
            reg.exe unload "HKU\$tempHive" | Out-Null
        }
    }
    catch {
        if ($hiveLoaded) { reg.exe unload "HKU\$tempHive" 2>$null | Out-Null }
        Write-Warning "No se pudo cargar NTUSER.DAT: $($_.Exception.Message)"
        Write-Host "  Ejecutá de nuevo este script después del primer inicio del usuario $KioskUser."
    }
}

# Startup folder fallback
if ($LaunchMode -in @("Startup", "Both") -and -not $WhatIf) {
    $startup = Join-Path $profilePath "AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
    New-Item -ItemType Directory -Path $startup -Force | Out-Null
    $vbs = Join-Path $startup "ExpendedoraKiosk.vbs"
    $launcherPs1 = Join-Path $kioskDir "launch_expendedora_kiosk.ps1"
    @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""$launcherPs1""", 0, False
"@ | Set-Content -Path $vbs -Encoding ASCII
    Write-Host "  Acceso directo en Startup: $vbs"
}

# --- Tarea programada al logon ---
Write-Host "[5/7] Registrando tarea al iniciar sesión..."
if (-not $WhatIf) {
    $launcherPs1 = Join-Path $kioskDir "launch_expendedora_kiosk.ps1"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcherPs1`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $KioskUser
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
    $principal = New-ScheduledTaskPrincipal -UserId $KioskUser -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Description "Mantiene expendedora en modo kiosk" -Force | Out-Null
    Write-Host "  Tarea: $TaskName"
}

# --- Bloquear suspensión en AC (opcional kiosk) ---
Write-Host "[6/7] Ajustando energía (no suspender)..."
if (-not $WhatIf) {
    powercfg /change standby-timeout-ac 0 2>$null | Out-Null
    powercfg /change monitor-timeout-ac 0 2>$null | Out-Null
}

Write-Host "[7/7] Finalizado."
Write-Host ""
Write-Host "Próximos pasos:"
Write-Host "  1. Cambiá la contraseña:  Set-LocalUser -Name $KioskUser -Password (Read-Host -AsSecureString)"
Write-Host "  2. Si cambiás la contraseña, actualizá DefaultPassword en Winlogon o re-ejecutá este script."
Write-Host "  3. Reiniciá:  shutdown /r /t 0"
Write-Host ""
Write-Host "Usuario: $KioskUser"
Write-Host "Password inicial: $Password"
Write-Host ""
Write-Host "Salir del kiosk (admin): Ctrl+Alt+Del -> cambiar usuario, o desinstalar con:"
Write-Host "  powershell -ExecutionPolicy Bypass -File configSO\windows\uninstall_cajero_kiosk.ps1"
