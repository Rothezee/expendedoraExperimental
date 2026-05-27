# Funciones compartidas para cargar NTUSER.DAT y aplicar shell/restricciones kiosk.

$script:KioskHiveName = "ExpKiosk"

function Test-KioskUserSessionActive {
    param([string]$UserName)
    try {
        $sessions = query.exe user 2>$null
        foreach ($line in $sessions) {
            if ($line -match "^\s*$([regex]::Escape($UserName))\s") {
                return $true
            }
        }
    }
    catch {
        # ignore
    }
    return $false
}

function Get-LocalUserSid {
    param([string]$UserName)
    try {
        $acct = New-Object System.Security.Principal.NTAccount($UserName)
        return $acct.Translate([System.Security.Principal.SecurityIdentifier]).Value
    }
    catch {
        return $null
    }
}

function Ensure-UserNtUserDat {
    param(
        [string]$ProfilePath
    )
    $ntuser = Join-Path $ProfilePath "NTUSER.DAT"
    $defaultNtuser = Join-Path $env:SystemDrive "Users\Default\NTUSER.DAT"
    if (-not (Test-Path -LiteralPath $defaultNtuser)) {
        return $null
    }

    $needsCopy = $true
    if (Test-Path -LiteralPath $ntuser) {
        $info = Get-Item -LiteralPath $ntuser
        if ($info.Length -gt 2048) {
            $needsCopy = $false
        }
        else {
            Write-Host "  NTUSER.DAT inválido o vacío; se reemplazará desde Default."
            Remove-Item -LiteralPath $ntuser -Force -ErrorAction SilentlyContinue
        }
    }

    if ($needsCopy) {
        New-Item -ItemType Directory -Path $ProfilePath -Force | Out-Null
        Copy-Item -LiteralPath $defaultNtuser -Destination $ntuser -Force
        if (Test-Path -LiteralPath $ntuser) {
            Write-Host "  NTUSER.DAT copiado desde perfil Default."
        }
    }

    if ((Test-Path -LiteralPath $ntuser) -and ((Get-Item -LiteralPath $ntuser).Length -gt 2048)) {
        return $ntuser
    }
    return $null
}

function Resolve-KioskUserHive {
    param(
        [string]$KioskUser,
        [string]$ProfilePath
    )
    if (Test-KioskUserSessionActive -UserName $KioskUser) {
        Write-Host "  Aviso: $KioskUser tiene sesión activa. Cerrá esa sesión y re-ejecutá para aplicar shell offline."
        return $null
    }

    $sid = Get-LocalUserSid -UserName $KioskUser
    if ($sid -and (Test-Path "Registry::HKEY_USERS\$sid")) {
        Write-Host "  Usando hive en línea HKU\$sid (perfil ya cargado en el sistema)."
        return @{
            HiveName = $sid
            OfflineLoaded = $false
        }
    }

    $ntuser = Ensure-UserNtUserDat -ProfilePath $ProfilePath
    if (-not $ntuser) {
        return $null
    }

    try {
        $hiveName = Load-NtUserHive -NtUserPath $ntuser
        return @{
            HiveName = $hiveName
            OfflineLoaded = $true
        }
    }
    catch {
        Write-Host "  Aviso: reg load falló ($($_.Exception.Message.Trim()))."
        if ($sid) {
            Write-Host "  Tras el primer inicio de $KioskUser, la tarea ExpendedoraKioskApplyRegistry aplicará HKCU."
        }
        return $null
    }
}

function Load-NtUserHive {
    param([string]$NtUserPath)

    $hive = $script:KioskHiveName
    & reg.exe unload "HKU\$hive" 2>$null | Out-Null
    Start-Sleep -Milliseconds 250

    $regExe = Join-Path $env:SystemRoot "System32\reg.exe"
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $regExe
    $psi.Arguments = "load HKU\$hive `"$NtUserPath`""
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardOutput = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    if ($proc.ExitCode -ne 0) {
        $msg = ($stderr, $stdout | Where-Object { $_ }) -join " "
        if (-not $msg) { $msg = "exit code $($proc.ExitCode)" }
        throw $msg.Trim()
    }
    return $hive
}

function Unload-NtUserHive {
    param([string]$HiveName = $script:KioskHiveName)
    [gc]::Collect()
    Start-Sleep -Milliseconds 250
    & reg.exe unload "HKU\$HiveName" 2>$null | Out-Null
}

function Set-KioskShellInHive {
    param(
        [string]$HiveName,
        [string]$LauncherCmdPath
    )
    $winlogon = "Registry::HKEY_USERS\$HiveName\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
    if (-not (Test-Path $winlogon)) {
        New-Item -Path $winlogon -Force | Out-Null
    }
    # /k + call: si falla Python, no se cierra Winlogon (evita bucle de reinicio de sesión).
    $shellPath = "cmd.exe /k call `"$LauncherCmdPath`""
    Set-ItemProperty -Path $winlogon -Name "Shell" -Value $shellPath -Force
    return $shellPath
}

function Clear-KioskShellInHive {
    param([string]$HiveName)
    $winlogon = "Registry::HKEY_USERS\$HiveName\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
    if (Test-Path $winlogon) {
        Remove-ItemProperty -Path $winlogon -Name "Shell" -ErrorAction SilentlyContinue
    }
}

function Apply-KioskRestrictionsHKCU {
    $base = "HKCU:\Software"
    $explorer = "$base\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    $system = "$base\Microsoft\Windows\CurrentVersion\Policies\System"
    foreach ($path in @($explorer, $system)) {
        if (-not (Test-Path $path)) {
            New-Item -Path $path -Force | Out-Null
        }
    }
    New-ItemProperty -Path $explorer -Name "NoWinKeys" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $explorer -Name "DisableTaskMgr" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $explorer -Name "NoRun" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $explorer -Name "NoControlPanel" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $explorer -Name "NoFolderOptions" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $system -Name "DisableChangePassword" -Value 1 -PropertyType DWord -Force | Out-Null
    $adv = "$base\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    if (-not (Test-Path $adv)) { New-Item -Path $adv -Force | Out-Null }
    New-ItemProperty -Path $adv -Name "TaskbarAutoHideInMode" -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $adv -Name "TaskbarSd" -Value 1 -PropertyType DWord -Force | Out-Null
    Write-Host "  Restricciones aplicadas en HKCU."
}

function Set-KioskShellHKCU {
    param([string]$LauncherCmdPath)
    $winlogon = "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
    if (-not (Test-Path $winlogon)) {
        New-Item -Path $winlogon -Force | Out-Null
    }
    $shellPath = "cmd.exe /k call `"$LauncherCmdPath`""
    Set-ItemProperty -Path $winlogon -Name "Shell" -Value $shellPath -Force
    return $shellPath
}

function Apply-KioskUserRegistry {
    param(
        [string]$KioskUser,
        [string]$ProfilePath,
        [string]$KioskDir,
        [string]$ScriptDir,
        [ValidateSet("Shell", "Startup", "Both")]
        [string]$LaunchMode = "Both"
    )

    $target = Resolve-KioskUserHive -KioskUser $KioskUser -ProfilePath $ProfilePath
    if (-not $target) {
        Write-Host "  Aviso: no se pudo abrir el registro del usuario. La app igual arranca por tarea al logon."
        return $false
    }

    $hiveName = $target.HiveName
    $offlineLoaded = [bool]$target.OfflineLoaded
    try {
        if ($LaunchMode -in @("Shell", "Both")) {
            $shellCmd = Join-Path $KioskDir "launch_expendedora_kiosk.cmd"
            $shellPath = Set-KioskShellInHive -HiveName $hiveName -LauncherCmdPath $shellCmd
            Write-Host "  Shell kiosk: $shellPath"
        }

        & (Join-Path $ScriptDir "apply_kiosk_restrictions.ps1") -Sid $hiveName
        Write-Host "  Restricciones de escritorio aplicadas."
        return $true
    }
    catch {
        Write-Warning "No se pudo aplicar registro kiosk: $($_.Exception.Message)"
        return $false
    }
    finally {
        if ($offlineLoaded) {
            Unload-NtUserHive -HiveName $hiveName
        }
    }
}
