# Rutas y resolución de Python para kiosk (compartido install/launcher/diagnose).

$script:KioskProgramDataDir = Join-Path $env:ProgramData "ExpendedoraKiosk"
$script:KioskConfigFile = Join-Path $script:KioskProgramDataDir "kiosk.json"
$script:DefaultInstallPath = "C:\expendedoraExperimental"

function Get-KioskConfig {
    if (-not (Test-Path $script:KioskConfigFile)) {
        return $null
    }
    try {
        return Get-Content $script:KioskConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Set-KioskConfig {
    param(
        [string]$AppPath,
        [string]$PythonExe = ""
    )
    New-Item -ItemType Directory -Path $script:KioskProgramDataDir -Force | Out-Null
    $obj = [ordered]@{
        app_path    = $AppPath
        python_exe  = $PythonExe
        updated_at  = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    }
    $obj | ConvertTo-Json | Set-Content -Path $script:KioskConfigFile -Encoding UTF8
}

function Find-SystemPythonInstaller {
    $found = @()
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if (-not $base -or -not (Test-Path -LiteralPath $base)) { continue }
        Get-ChildItem -Path $base -Filter python.exe -Recurse -Depth 3 -ErrorAction SilentlyContinue |
            ForEach-Object { $found += $_.FullName }
    }
    foreach ($p in ($found | Sort-Object -Unique)) {
        if ($p -notmatch '\\Users\\') {
            return $p
        }
    }
    return $null
}

function Test-VenvUsesForeignUserPython {
    param(
        [string]$AppPath,
        [string]$KioskUser = "cajero"
    )
    $venvPy = Join-Path $AppPath ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPy)) {
        return $false
    }
    $cfgFile = Join-Path $AppPath ".venv\pyvenv.cfg"
    if (-not (Test-Path -LiteralPath $cfgFile)) {
        return $true
    }
    foreach ($line in Get-Content -LiteralPath $cfgFile -ErrorAction SilentlyContinue) {
        if ($line -match '^\s*home\s*=\s*(.+)\s*$') {
            $venvHome = $matches[1].Trim()
            if ($venvHome -match '\\Users\\([^\\]+)\\') {
                $owner = $matches[1]
                if ($owner -and $owner -ne $KioskUser) {
                    return $true
                }
            }
            if ($venvHome -match '\\AppData\\Local\\Python') {
                return $true
            }
        }
    }
    return $false
}

function Repair-KioskVenv {
    param(
        [string]$AppPath,
        [string]$KioskUser = "cajero"
    )

    $venvDir = Join-Path $AppPath ".venv"
    $basePy = Find-SystemPythonInstaller
    if (-not $basePy) {
        throw @"
No hay Python en Program Files (accesible para todos los usuarios).
Instalá Python desde https://www.python.org marcando 'Install for all users',
luego volvé a ejecutar repair_kiosk.ps1
"@
    }

    if (Test-Path -LiteralPath $venvDir) {
        Write-Host "  Eliminando .venv (apuntaba a Python de otro usuario)..."
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }

    Write-Host "  Creando .venv con: $basePy"
    & $basePy -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        throw "venv falló (exit $LASTEXITCODE)"
    }

    $venvPy = Join-Path $venvDir "Scripts\python.exe"
    $pip = Join-Path $venvDir "Scripts\pip.exe"
    $req = Join-Path $AppPath "requirements.txt"
    if ((Test-Path -LiteralPath $pip) -and (Test-Path -LiteralPath $req)) {
        Write-Host "  pip install -r requirements.txt ..."
        & $pip install -r $req
    }

    Grant-KioskAppAccess -AppPath $AppPath -KioskUser $KioskUser
    $pyPathFile = Join-Path $script:KioskProgramDataDir "python_exe.txt"
    New-Item -ItemType Directory -Path $script:KioskProgramDataDir -Force | Out-Null
    Set-Content -Path $pyPathFile -Value $venvPy -Encoding ASCII -NoNewline

    return (Resolve-Path -LiteralPath $venvPy).Path
}

function Find-PythonForKiosk {
    param([string]$AppPath)

    if ($AppPath -and (Test-VenvUsesForeignUserPython -AppPath $AppPath)) {
        return $null
    }

    # Prioridad: venv junto a la app (solo si no apunta al perfil de otro usuario).
    if ($AppPath) {
        foreach ($rel in @(".venv\Scripts\python.exe", "python\python.exe")) {
            $p = Join-Path $AppPath $rel
            if (Test-Path -LiteralPath $p) {
                return (Resolve-Path -LiteralPath $p).Path
            }
        }
    }

    $pyTxt = Join-Path $script:KioskProgramDataDir "python_exe.txt"
    if (Test-Path -LiteralPath $pyTxt) {
        $px = (Get-Content -LiteralPath $pyTxt -Raw).Trim()
        if ($px -and (Test-Path -LiteralPath $px)) {
            return $px
        }
    }

    $candidates = @()

    if ($env:EXPENDEDORA_PYTHON) {
        $candidates += $env:EXPENDEDORA_PYTHON
    }

    $cfg = Get-KioskConfig
    if ($cfg -and $cfg.python_exe) {
        $px = [string]$cfg.python_exe
        if ((Test-Path -LiteralPath $px) -and (-not $AppPath -or $px.StartsWith($AppPath, [StringComparison]::OrdinalIgnoreCase))) {
            $candidates += $px
        }
    }

    $regBase = "HKLM:\SOFTWARE\Expendedora"
    foreach ($name in @("PythonExe", "Python")) {
        $v = (Get-ItemProperty -Path $regBase -Name $name -ErrorAction SilentlyContinue).$name
        if ($v -and (Test-Path -LiteralPath $v)) {
            if (-not $AppPath -or ([string]$v).StartsWith($AppPath, [StringComparison]::OrdinalIgnoreCase)) {
                $candidates += [string]$v
            }
        }
    }

    if ($AppPath) {
        $candidates += Join-Path $AppPath ".venv\Scripts\python.exe"
    }

    $sysPy = Find-SystemPythonInstaller
    if ($sysPy) { $candidates += $sysPy }

    $candidates += @(
        "C:\expendedoraExperimental\.venv\Scripts\python.exe"
        "${env:ProgramFiles}\Python314\python.exe"
        "${env:ProgramFiles}\Python313\python.exe"
        "${env:ProgramFiles}\Python312\python.exe"
        "${env:ProgramFiles}\Python311\python.exe"
        "${env:ProgramFiles}\Python310\python.exe"
    )

    foreach ($p in $candidates) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            return (Resolve-Path -LiteralPath $p).Path
        }
    }

    if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return (Get-Command python).Source
    }
    return $null
}

function Find-KioskAppPath {
    param([string]$PreferredPath = "")

    $candidates = @()
    if ($PreferredPath) { $candidates += $PreferredPath }

    $cfg = Get-KioskConfig
    if ($cfg -and $cfg.app_path) {
        $candidates += [string]$cfg.app_path
    }

    $reg = Get-ItemProperty -Path "HKLM:\SOFTWARE\Expendedora" -ErrorAction SilentlyContinue
    if ($reg -and $reg.AppPath) {
        $candidates += [string]$reg.AppPath
    }

    $candidates += @(
        $script:DefaultInstallPath
        "C:\expendedoraExperimental"
        "C:\Expendedora"
        (Join-Path $env:USERPROFILE "expendedoraExperimental")
    )

    foreach ($path in $candidates) {
        if (-not $path) { continue }
        $main = Join-Path $path "main.py"
        if (Test-Path -LiteralPath $main) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }
    return $null
}

function Resolve-KioskAppPath {
    param([string]$FallbackAppPath = "")

    $found = Find-KioskAppPath -PreferredPath $FallbackAppPath
    if ($found) {
        return $found
    }
    return $FallbackAppPath
}

function Deploy-ExpendedoraToInstallPath {
    param(
        [string]$SourcePath,
        [string]$DestPath = $script:DefaultInstallPath
    )

    if (-not (Test-Path -LiteralPath $SourcePath)) {
        throw "Origen no existe: $SourcePath"
    }
    $src = (Resolve-Path -LiteralPath $SourcePath).Path
    $dest = $DestPath.TrimEnd('\')
    if ($src -ieq $dest) {
        Write-Host "  Origen y destino iguales; no se copia."
        return $dest
    }

    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    Write-Host "  Copiando $src -> $dest ..."
    $robocopyArgs = @(
        $src, $dest,
        "/E", "/COPY:DAT", "/R:2", "/W:2", "/NFL", "/NDL", "/NJH", "/NJS",
        "/XD", ".git", "__pycache__", ".cursor", "node_modules", "dist", "build"
    )
    & robocopy @robocopyArgs | Out-Null
    $code = $LASTEXITCODE
    if ($code -ge 8) {
        throw "robocopy falló con código $code"
    }
    return $dest
}

function Ensure-VenvAtAppPath {
    param(
        [string]$AppPath,
        [string]$PythonExe = "",
        [string]$KioskUser = "cajero"
    )

    if (Test-VenvUsesForeignUserPython -AppPath $AppPath -KioskUser $KioskUser) {
        return Repair-KioskVenv -AppPath $AppPath -KioskUser $KioskUser
    }

    $venvPy = Join-Path $AppPath ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) {
        return (Resolve-Path -LiteralPath $venvPy).Path
    }

    $basePy = $PythonExe
    if (-not $basePy) {
        $basePy = Find-SystemPythonInstaller
    }
    if (-not $basePy) {
        throw "No hay Python en Program Files para crear .venv compartido."
    }

    Write-Host "  Creando .venv en $AppPath con $basePy ..."
    & $basePy -m venv (Join-Path $AppPath ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "venv falló (exit $LASTEXITCODE)"
    }

    $pip = Join-Path $AppPath ".venv\Scripts\pip.exe"
    $req = Join-Path $AppPath "requirements.txt"
    if ((Test-Path -LiteralPath $pip) -and (Test-Path -LiteralPath $req)) {
        & $pip install -r $req
    }

    if (Test-Path -LiteralPath $venvPy) {
        return (Resolve-Path -LiteralPath $venvPy).Path
    }
    throw "No se creó $venvPy"
}

function Get-KioskUserSid {
    param([string]$KioskUser)
    try {
        $lu = Get-LocalUser -Name $KioskUser -ErrorAction Stop
        return $lu.Sid.Value
    }
    catch {
        try {
            $acct = New-Object System.Security.Principal.NTAccount($KioskUser)
            return $acct.Translate([System.Security.Principal.SecurityIdentifier]).Value
        }
        catch {
            return $null
        }
    }
}

function Grant-KioskPathAcl {
    param(
        [string]$Path,
        [string]$KioskUser
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $sid = Get-KioskUserSid -KioskUser $KioskUser
    if ($sid) {
        Grant-KioskPathAclToSid -Path $Path -Sid $sid -Rights "(OI)(CI)(RX)"
    }
    $machine = $env:COMPUTERNAME
    icacls $Path /grant "${machine}\${KioskUser}:(OI)(CI)(RX)" /T /C 2>$null | Out-Null
    icacls $Path /grant "${KioskUser}:(OI)(CI)(RX)" /T /C 2>$null | Out-Null
}

function Grant-KioskPathAclToSid {
    param(
        [string]$Path,
        [string]$Sid,
        [string]$Rights = "(OI)(CI)M",
        [switch]$InheritOnly
    )
    if (-not (Test-Path -LiteralPath $Path) -or -not $Sid) {
        return $false
    }
    icacls $Path /inheritance:e /C 2>$null | Out-Null
    $grant = "*${Sid}:${Rights}"
    if ($InheritOnly) {
        icacls $Path /grant "${grant}" /C 2>$null | Out-Null
    }
    else {
        icacls $Path /grant "${grant}" /T /C 2>$null | Out-Null
    }
    return ($LASTEXITCODE -lt 8)
}

function Grant-KioskAppAccess {
    param(
        [string]$AppPath,
        [string]$KioskUser
    )
    $sid = Get-KioskUserSid -KioskUser $KioskUser
    if (-not $sid) {
        Write-Warning "No se pudo obtener SID de $KioskUser"
        return
    }

    $machine = $env:COMPUTERNAME
    $acct = "${machine}\${KioskUser}"

    foreach ($path in @($AppPath)) {
        if (-not (Test-Path -LiteralPath $path)) { continue }
        Grant-KioskPathAclToSid -Path $path -Sid $sid -Rights "(OI)(CI)M"
        # Respaldo con nombre de cuenta (Windows en español a veces falla solo con nombre corto).
        icacls $path /grant "${acct}:(OI)(CI)M" /T /C 2>$null | Out-Null
        icacls $path /grant "${KioskUser}:(OI)(CI)M" /T /C 2>$null | Out-Null
    }

    $venvScripts = Join-Path $AppPath ".venv\Scripts"
    if (Test-Path -LiteralPath $venvScripts) {
        Grant-KioskPathAclToSid -Path $venvScripts -Sid $sid -Rights "(OI)(CI)RX"
        icacls $venvScripts /grant "${acct}:(OI)(CI)RX" /T /C 2>$null | Out-Null
    }

    foreach ($dataFile in @("config.json", "machine_state.json", "registro.json", "buffer_state.json")) {
        $f = Join-Path $AppPath $dataFile
        if (Test-Path -LiteralPath $f) {
            icacls $f /grant "*${sid}:F" /C 2>$null | Out-Null
        }
    }

    Write-Host "  Permisos ACL: $AppPath -> $KioskUser ($sid)"
}

function Get-KioskUserDesktopPaths {
    param([string]$KioskUser)

    $profileRoot = Join-Path $env:SystemDrive "Users\$KioskUser"
    $candidates = @(
        (Join-Path $profileRoot "Desktop")
        (Join-Path $profileRoot "Escritorio")
        (Join-Path $profileRoot "OneDrive\Desktop")
        (Join-Path $profileRoot "OneDrive\Escritorio")
    )

    $found = @()
    foreach ($path in $candidates) {
        if (Test-Path -LiteralPath $path) {
            $resolved = (Resolve-Path -LiteralPath $path).Path
            if ($found -notcontains $resolved) {
                $found += $resolved
            }
        }
    }

    if ($found.Count -eq 0) {
        $defaultDesktop = Join-Path $profileRoot "Desktop"
        New-Item -ItemType Directory -Path $defaultDesktop -Force | Out-Null
        $found += $defaultDesktop
    }

    return $found
}

function Install-KioskUserCmd {
    param(
        [string]$AppPath,
        [string]$DestDir,
        [string]$TemplateCmdPath = ""
    )
    $template = $TemplateCmdPath
    if (-not $template) {
        $template = Join-Path $PSScriptRoot "templates\AbrirExpendedora.cmd"
    }
    if (-not (Test-Path $template)) {
        $template = Join-Path (Split-Path $PSScriptRoot -Parent) "windows\templates\AbrirExpendedora.cmd"
    }
    if (-not (Test-Path $template)) {
        throw "No se encontró templates\AbrirExpendedora.cmd"
    }

    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
    $cmdPath = Join-Path $DestDir "AbrirExpendedora.cmd"
    $content = Get-Content $template -Raw -Encoding Default
    $content = $content.Replace("__APP_PATH__", $AppPath)
    Set-Content -Path $cmdPath -Value $content -Encoding ASCII
    return $cmdPath
}

function Install-KioskDesktopShortcut {
    param(
        [string]$KioskUser,
        [string]$AppPath,
        [string]$LauncherCmd,
        [string]$ShortcutName = "Expendedora"
    )

    if (-not (Test-Path -LiteralPath $LauncherCmd)) {
        Write-Warning "Launcher .cmd no encontrado: $LauncherCmd"
        return
    }

    $cmdExe = Join-Path $env:SystemRoot "System32\cmd.exe"
    $icon = Join-Path $AppPath ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $icon)) {
        $icon = Join-Path $AppPath "Expendedora.exe"
    }

    foreach ($desktop in (Get-KioskUserDesktopPaths -KioskUser $KioskUser)) {
        New-Item -ItemType Directory -Path $desktop -Force | Out-Null
        $lnkPath = Join-Path $desktop "$ShortcutName.lnk"

        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($lnkPath)
        $shortcut.TargetPath = $cmdExe
        $shortcut.Arguments = "/c `"$LauncherCmd`""
        $shortcut.WorkingDirectory = $AppPath
        $shortcut.Description = "Abrir expendedora"
        $shortcut.WindowStyle = 1
        if (Test-Path -LiteralPath $icon) {
            $shortcut.IconLocation = "$icon,0"
        }
        $shortcut.Save()

        icacls $desktop /grant "${KioskUser}:(M)" /C 2>$null | Out-Null
        icacls $lnkPath /grant "${KioskUser}:(F)" 2>$null | Out-Null
        Write-Host "  Acceso directo: $lnkPath"
    }
}

function Register-KioskLogonTask {
    param(
        [string]$TaskName,
        [string]$KioskUser,
        [string]$LauncherCmd,
        [int]$DelaySeconds = 12
    )

    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$LauncherCmd`""
    $trigger = New-KioskLogonTaskTrigger -KioskUser $KioskUser -DelaySeconds $DelaySeconds
    try {
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -ExecutionTimeLimit ([TimeSpan]::Zero) `
            -MultipleInstances IgnoreNew
    }
    catch {
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -ExecutionTimeLimit ([TimeSpan]::Zero)
    }
    $principal = New-ScheduledTaskPrincipal -UserId $KioskUser -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Description "Expendedora kiosk" -Force | Out-Null
}

function New-KioskLogonTaskTrigger {
    param(
        [Parameter(Mandatory)]
        [string]$KioskUser,
        [int]$DelaySeconds = 0
    )

    try {
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $KioskUser -ErrorAction Stop
    }
    catch {
        $trigger = New-ScheduledTaskTrigger -AtLogOn
    }

    if ($DelaySeconds -gt 0) {
        $delayIso = "PT${DelaySeconds}S"
        try {
            $trigger.Delay = $delayIso
        }
        catch {
            Write-Host "  Aviso: delay de ${DelaySeconds}s no disponible en este Windows (tarea al logon inmediata)."
        }
    }

    return $trigger
}

function Remove-KioskDesktopShortcut {
    param(
        [string]$KioskUser,
        [string]$ShortcutName = "Expendedora"
    )

    foreach ($desktop in (Get-KioskUserDesktopPaths -KioskUser $KioskUser)) {
        $lnkPath = Join-Path $desktop "$ShortcutName.lnk"
        if (Test-Path -LiteralPath $lnkPath) {
            Remove-Item -LiteralPath $lnkPath -Force
            Write-Host "  Eliminado: $lnkPath"
        }
    }
}
