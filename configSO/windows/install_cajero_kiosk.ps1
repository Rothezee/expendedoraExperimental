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
    powershell -ExecutionPolicy Bypass -File configSO\windows\install_cajero_kiosk.ps1 -NoPassword -DeployTo

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File configSO\windows\install_cajero_kiosk.ps1 `
        -KioskUser cajero -Password 'MiClaveSegura!' -AppPath 'C:\expendedoraExperimental'
#>
param(
    [string]$KioskUser = "cajero",
    [string]$Password = "cajero123",
    [string]$AppPath = "",
    [switch]$DeployTo,
    [ValidateSet("Shell", "Startup", "Both")]
    [string]$LaunchMode = "Startup",
    [switch]$SkipAutoLogon,
    [switch]$NoPassword,
    [switch]$WhatIf,
    [switch]$SkipRestrictionsTask
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "kiosk_paths.ps1")
. (Join-Path $ScriptDir "kiosk_registry.ps1")
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$TemplateDir = Join-Path $ScriptDir "templates"
$TaskName = "ExpendedoraKioskLauncher"
$SetupTaskName = "ExpendedoraKioskApplyRegistry"
$KioskFolderName = "ExpendedoraKiosk"

if ($DeployTo) {
    $AppPath = $script:DefaultInstallPath
}
elseif (-not $AppPath) {
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

$sourceRepo = $RepoRoot.Path
if ($DeployTo -and -not $WhatIf) {
    Write-Host "Desplegando proyecto -> $AppPath ..."
    $AppPath = Deploy-ExpendedoraToInstallPath -SourcePath $sourceRepo -DestPath $AppPath
}

if (-not (Test-Path (Join-Path $AppPath "main.py"))) {
    throw "No se encontró main.py en AppPath: $AppPath"
}

$pythonForKiosk = $null
if (-not $WhatIf) {
    try {
        $pythonForKiosk = Ensure-VenvAtAppPath -AppPath $AppPath
        Write-Host "  Python kiosk: $pythonForKiosk"
    }
    catch {
        Write-Warning "No se pudo crear .venv en ${AppPath}: $($_.Exception.Message)"
        $pythonForKiosk = Find-PythonForKiosk -AppPath $AppPath
    }
    if (-not $pythonForKiosk) {
        Write-Warning "Instalá Python 3.10+ o usá -DeployTo y re-ejecutá el instalador."
    }
    else {
        New-Item -Path "HKLM:\SOFTWARE\Expendedora" -Force | Out-Null
        Set-ItemProperty -Path "HKLM:\SOFTWARE\Expendedora" -Name "AppPath" -Value $AppPath -Force
        Set-ItemProperty -Path "HKLM:\SOFTWARE\Expendedora" -Name "PythonExe" -Value $pythonForKiosk -Force
        Set-KioskConfig -AppPath $AppPath -PythonExe $pythonForKiosk
        Grant-KioskAppAccess -AppPath $AppPath -KioskUser $KioskUser
    }
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

# --- Launcher en ProgramData (no depende de copiar perfil Default) ---
$profilePath = Join-Path $env:SystemDrive "Users\$KioskUser"
$kioskDir = Join-Path $env:ProgramData $KioskFolderName

Write-Host "[3/8] Preparando launcher en ProgramData..."
if (-not $WhatIf) {
    New-Item -ItemType Directory -Path $kioskDir -Force | Out-Null

    $launcherPs1 = Join-Path $kioskDir "launch_expendedora_kiosk.ps1"
    $templatePs1 = Get-Content (Join-Path $TemplateDir "launch_expendedora_kiosk.ps1") -Raw
    $escapedAppPath = $AppPath.Replace("'", "''")
    $templatePs1 = $templatePs1.Replace("__APP_PATH__", $escapedAppPath)
    Set-Content -Path $launcherPs1 -Value $templatePs1 -Encoding UTF8
    Copy-Item (Join-Path $ScriptDir "apply_kiosk_user_registry.ps1") (Join-Path $kioskDir "apply_kiosk_user_registry.ps1") -Force
    Copy-Item (Join-Path $ScriptDir "kiosk_registry.ps1") (Join-Path $kioskDir "kiosk_registry.ps1") -Force
    Copy-Item (Join-Path $ScriptDir "apply_kiosk_restrictions.ps1") (Join-Path $kioskDir "apply_kiosk_restrictions.ps1") -Force
    Copy-Item (Join-Path $ScriptDir "kiosk_paths.ps1") (Join-Path $kioskDir "kiosk_paths.ps1") -Force

    $userLauncherCmd = Install-KioskUserCmd -AppPath $AppPath -DestDir $kioskDir `
        -TemplateCmdPath (Join-Path $TemplateDir "AbrirExpendedora.cmd")
    Install-KioskUserCmd -AppPath $AppPath -DestDir $AppPath `
        -TemplateCmdPath (Join-Path $TemplateDir "AbrirExpendedora.cmd") | Out-Null

    Grant-KioskPathAcl -Path $kioskDir -KioskUser $KioskUser
    Write-Host "  Launcher CMD: $userLauncherCmd"

    Install-KioskDesktopShortcut -KioskUser $KioskUser -AppPath $AppPath -LauncherCmd $userLauncherCmd
}

# --- Auto-login ---
Write-Host "[4/8] Configurando auto-login..."
if (-not $SkipAutoLogon) {
    Set-AutoLogon -UserName $KioskUser -PlainPassword $Password
}
else {
    Write-Host "  Auto-login omitido (-SkipAutoLogon)."
}

# --- Shell personalizado (HKU) y Startup ---
Write-Host "[5/8] Configurando shell / startup..."
$registryApplied = $false
if (-not $WhatIf) {
    if ($LaunchMode -in @("Shell", "Both")) {
        $registryApplied = Apply-KioskUserRegistry -KioskUser $KioskUser -ProfilePath $profilePath `
            -KioskDir $kioskDir -ScriptDir $ScriptDir -LaunchMode $LaunchMode
        if (-not $registryApplied) {
            Write-Host "  Shell no aplicado offline; usá Startup/tarea (sin bucle de reinicio)."
        }
    }
    else {
        Write-Host "  Modo Startup: sin shell custom (recomendado; evita bucles de reinicio)."
    }
}

# Respaldo Startup solo si el perfil ya existe (la tarea principal evita duplicados con mutex).
if ($LaunchMode -in @("Startup", "Both") -and -not $WhatIf) {
    $startup = Join-Path $profilePath "AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
    if (Test-Path (Split-Path $startup -Parent)) {
        New-Item -ItemType Directory -Path $startup -Force | Out-Null
        $vbs = Join-Path $startup "ExpendedoraKiosk.vbs"
        $startCmd = Join-Path $kioskDir "AbrirExpendedora.cmd"
        $cmdEsc = $startCmd.Replace('"', '""')
        @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd.exe /c ""$cmdEsc""", 0, False
"@ | Set-Content -Path $vbs -Encoding ASCII
        Write-Host "  Respaldo Startup: $vbs"
    }
    else {
        Write-Host "  Startup omitido hasta primer perfil (la tarea al logon alcanza)."
    }
}

# --- Tarea programada al logon (app fullscreen; sin shell custom) ---
Write-Host "[6/8] Registrando tarea al iniciar sesión..."
if (-not $WhatIf) {
    $startCmd = Join-Path $kioskDir "AbrirExpendedora.cmd"
    Register-KioskLogonTask -TaskName $TaskName -KioskUser $KioskUser -LauncherCmd $startCmd
    Write-Host "  Tarea: $TaskName"

    if (-not $SkipRestrictionsTask) {
        $applyScript = Join-Path $kioskDir "apply_kiosk_user_registry.ps1"
        $setupAction = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$applyScript`""
        $setupTrigger = New-KioskLogonTaskTrigger -KioskUser $KioskUser -DelaySeconds 15
        $setupSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $setupPrincipal = New-ScheduledTaskPrincipal -UserId $KioskUser -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $SetupTaskName -Action $setupAction -Trigger $setupTrigger `
            -Settings $setupSettings -Principal $setupPrincipal -Description "Restricciones kiosk (sin shell)" -Force | Out-Null
        Write-Host "  Tarea: $SetupTaskName (restricciones escritorio)"
    }
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
Write-Host "  2. Entrará a $KioskUser y abrirá la expendedora en pantalla completa (sin login interno)."
Write-Host "  3. NO uses -LaunchMode Shell (puede causar bucle de reinicio)."
Write-Host "  App en: $AppPath"
Write-Host "  Diagnóstico: configSO\windows\diagnose_kiosk.ps1"
Write-Host "  Log cajero: C:\Users\$KioskUser\expendedora-kiosk.log"
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
Write-Host "Salir del kiosk (admin): Ctrl+Alt+Del -> cambiar usuario"
Write-Host "Bucle de reinicio: recover_from_kiosk_loop.ps1 (como admin)"
Write-Host "Desinstalar: uninstall_cajero_kiosk.ps1"
