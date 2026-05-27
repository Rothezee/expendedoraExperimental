#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Configura Windows 11 en modo kiosk para la expendedora (usuario cajero).

.DESCRIPTION
    - Crea usuario local limitado
    - Auto-login al arrancar (con o sin contraseña)
    - Shell personalizado que mantiene main.py en ejecución
    - Tarea programada de respaldo al iniciar sesión
    - Restricciones básicas de escritorio

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File configSO\windows\install_cajero_kiosk.ps1 -NoPassword

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
    [switch]$NoPassword,
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

if ($NoPassword) {
    $Password = ""
}

Write-Host "=============================================="
Write-Host " Configuración Kiosk Expendedora (Windows 11)"
Write-Host "=============================================="
Write-Host "Usuario kiosk : $KioskUser"
Write-Host "App path      : $AppPath"
Write-Host "Modo arranque : $LaunchMode"
Write-Host "Sin contraseña: $NoPassword"
Write-Host ""

if (-not (Test-Path (Join-Path $AppPath "main.py"))) {
    throw "No se encontró main.py en AppPath: $AppPath"
}

function Enable-BlankPasswordLogon {
    if ($WhatIf) {
        Write-Host "  (WhatIf) Permitir cuentas locales sin contraseña (LimitBlankPasswordUse=0)"
        return
    }
    $lsa = "HKLM:\SYSTEM\CurrentControlSet\Control\Lsa"
    Set-ItemProperty -Path $lsa -Name "LimitBlankPasswordUse" -Value 0 -Type DWord -Force
    Write-Host "  Política LimitBlankPasswordUse deshabilitada (permite login sin clave)."
}

function Set-KioskUserPassword {
    param(
        [string]$UserName,
        [string]$PlainPassword
    )

    if ($WhatIf) {
        if ([string]::IsNullOrEmpty($PlainPassword)) {
            Write-Host "  (WhatIf) Usuario $UserName sin contraseña"
        }
        else {
            Write-Host "  (WhatIf) Actualizar contraseña de $UserName"
        }
        return
    }

    if ([string]::IsNullOrEmpty($PlainPassword)) {
        cmd.exe /c "net user `"$UserName`" `"`"" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "No se pudo dejar al usuario $UserName sin contraseña."
        }
        Write-Host "  Usuario $UserName configurado sin contraseña."
        return
    }

    $secPassword = ConvertTo-SecureString $PlainPassword -AsPlainText -Force
    Set-LocalUser -Name $UserName -Password $secPassword -ErrorAction Stop
    Write-Host "  Contraseña actualizada para $UserName."
}

function Set-AutoLogon {
    param(
        [string]$UserName,
        [string]$PlainPassword
    )

    $winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    if ($WhatIf) {
        Write-Host "  (WhatIf) AutoAdminLogon para $UserName"
        return
    }

    Set-ItemProperty -Path $winlogon -Name "AutoAdminLogon" -Value "1" -Type String -Force
    Set-ItemProperty -Path $winlogon -Name "DefaultUserName" -Value $UserName -Type String -Force
    Set-ItemProperty -Path $winlogon -Name "DefaultDomainName" -Value "." -Type String -Force
    Set-ItemProperty -Path $winlogon -Name "DefaultPassword" -Value $PlainPassword -Type String -Force
    if (Get-ItemProperty -Path $winlogon -Name "ForceAutoLogon" -ErrorAction SilentlyContinue) {
        Set-ItemProperty -Path $winlogon -Name "ForceAutoLogon" -Value "1" -Type String -Force
    }

    if ([string]::IsNullOrEmpty($PlainPassword)) {
        Write-Host "  Auto-login configurado sin contraseña."
    }
    else {
        Write-Host "  Auto-login configurado con contraseña."
    }
}

# --- Usuario local ---
Write-Host "[1/8] Creando usuario kiosk..."
$user = Get-LocalUser -Name $KioskUser -ErrorAction SilentlyContinue
if (-not $user) {
    if ($WhatIf) {
        Write-Host "  (WhatIf) New-LocalUser $KioskUser"
    }
    else {
        if ($NoPassword) {
            cmd.exe /c "net user `"$KioskUser`" `"`" /add /fullname:`"Cajero Expendedora`" /comment:`"Usuario kiosk expendedora`" /expires:never /passwordchg:no" 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "No se pudo crear el usuario $KioskUser sin contraseña."
            }
            Write-Host "  Usuario $KioskUser creado sin contraseña."
        }
        else {
            $secPassword = ConvertTo-SecureString $Password -AsPlainText -Force
            New-LocalUser -Name $KioskUser -Password $secPassword -FullName "Cajero Expendedora" `
                -Description "Usuario kiosk expendedora" -PasswordNeverExpires | Out-Null
            Write-Host "  Usuario $KioskUser creado."
        }
    }
}
else {
    Write-Host "  Usuario $KioskUser ya existe."
    Set-KioskUserPassword -UserName $KioskUser -PlainPassword $Password
}

if (-not $WhatIf) {
    Add-LocalGroupMember -Group "Users" -Member $KioskUser -ErrorAction SilentlyContinue
    Remove-LocalGroupMember -Group "Administrators" -Member $KioskUser -ErrorAction SilentlyContinue
}

if ($NoPassword) {
    Write-Host "[2/8] Habilitando login sin contraseña..."
    Enable-BlankPasswordLogon
}
else {
    Write-Host "[2/8] Modo con contraseña (sin cambios de política LSA)."
}

# --- Perfil y carpeta kiosk ---
$profilePath = Join-Path $env:SystemDrive "Users\$KioskUser"
$kioskDir = Join-Path $profilePath $KioskFolderName

Write-Host "[3/8] Preparando perfil y launcher..."
if (-not $WhatIf) {
    if (-not (Test-Path $profilePath)) {
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

    icacls $AppPath /grant "${KioskUser}:(RX)" /T /C | Out-Null
    icacls $AppPath /grant "${KioskUser}:(M)" /C | Out-Null
}

# --- Auto-login ---
Write-Host "[4/8] Configurando auto-login..."
if (-not $SkipAutoLogon) {
    Set-AutoLogon -UserName $KioskUser -PlainPassword $Password
}
else {
    Write-Host "  Auto-login omitido (-SkipAutoLogon)."
}

# --- Shell personalizado (HKU) ---
Write-Host "[5/8] Configurando shell / startup..."
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
Write-Host "[6/8] Registrando tarea al iniciar sesión..."
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

Write-Host "[7/8] Ajustando energía (no suspender)..."
if (-not $WhatIf) {
    powercfg /change standby-timeout-ac 0 2>$null | Out-Null
    powercfg /change monitor-timeout-ac 0 2>$null | Out-Null
}

Write-Host "[8/8] Finalizado."
Write-Host ""
Write-Host "Próximos pasos:"
Write-Host "  1. Reiniciá:  shutdown /r /t 0"
Write-Host "  2. La PC debería entrar sola al usuario $KioskUser y abrir la expendedora."
Write-Host ""
Write-Host "Usuario: $KioskUser"
if ($NoPassword) {
    Write-Host "Contraseña Windows: (sin contraseña)"
    Write-Host "Aviso: cualquiera con acceso físico puede entrar a Windows."
}
else {
    Write-Host "Password inicial: $Password"
    Write-Host "  Si cambiás la contraseña, re-ejecutá este script."
}
Write-Host ""
Write-Host "Salir del kiosk (admin): Ctrl+Alt+Del -> cambiar usuario, o desinstalar con:"
Write-Host "  powershell -ExecutionPolicy Bypass -File configSO\windows\uninstall_cajero_kiosk.ps1"
