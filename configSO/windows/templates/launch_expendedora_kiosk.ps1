# Launcher kiosk Expendedora (Windows)
param(
    [string]$AppPath = "__APP_PATH__",
    [string]$LogFile = "",
    [int]$RestartDelaySeconds = 5
)

$ErrorActionPreference = "Continue"
$LauncherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PathsHelper = Join-Path $LauncherDir "kiosk_paths.ps1"
if (-not (Test-Path $PathsHelper)) {
    $PathsHelper = Join-Path (Split-Path $LauncherDir -Parent) "windows\kiosk_paths.ps1"
}
if (Test-Path $PathsHelper) {
    . $PathsHelper
}

try {
    $script:KioskLauncherMutex = New-Object System.Threading.Mutex($false, "Global\ExpendedoraKioskLauncher")
    if (-not $script:KioskLauncherMutex.WaitOne(0, $false)) {
        exit 0
    }
}
catch { }

# Sin EXPENDEDORA_KIOSK: la app muestra pantalla de login (UserManagement).

if ($AppPath -eq "__APP_PATH__" -or [string]::IsNullOrWhiteSpace($AppPath)) {
    $AppPath = ""
}
if (Get-Command Resolve-KioskAppPath -ErrorAction SilentlyContinue) {
    $AppPath = Resolve-KioskAppPath -FallbackAppPath $AppPath
}
if (-not $AppPath -and (Get-Command Find-KioskAppPath -ErrorAction SilentlyContinue)) {
    $AppPath = Find-KioskAppPath
}

if (-not $LogFile) {
    $LogFile = Join-Path $env:USERPROFILE "expendedora-kiosk.log"
}

function Write-Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch { }
    Write-Host $line
}

function Start-ExpendedoraProcess {
    param(
        [string]$ResolvedAppPath,
        [string]$PythonResolved
    )

    $mainPy = Join-Path $ResolvedAppPath "main.py"
    $exePath = Join-Path $ResolvedAppPath "Expendedora.exe"
    if (Test-Path -LiteralPath $exePath) {
        Write-Log "Usando ejecutable: $exePath"
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $exePath
        $psi.WorkingDirectory = $ResolvedAppPath
        $psi.UseShellExecute = $true
        return [System.Diagnostics.Process]::Start($psi)
    }

    if (-not (Test-Path -LiteralPath $mainPy)) {
        throw "No se encontró main.py ni Expendedora.exe en: $ResolvedAppPath"
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    if ($PythonResolved -and $PythonResolved -ne "py" -and (Test-Path -LiteralPath $PythonResolved)) {
        $psi.FileName = $PythonResolved
        $psi.Arguments = "`"$mainPy`""
    }
    elseif ($PythonResolved -eq "py") {
        $psi.FileName = "py"
        $psi.Arguments = "-3 `"$mainPy`""
    }
    else {
        throw "Python no resuelto"
    }
    $psi.WorkingDirectory = $ResolvedAppPath
    # Tkinter NECESITA ventana visible; CreateNoWindow=true deja la app "invisible".
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $false

    return [System.Diagnostics.Process]::Start($psi)
}

function Hide-Taskbar {
    try {
        Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" `
            -Name "TaskbarAutoHideInMode" -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
        Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" `
            -Name "TaskbarSd" -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
    }
    catch { }
}

Write-Log "=== Inicio launcher kiosk ==="
Write-Log "AppPath=$AppPath Usuario=$env:USERNAME"

function Test-KioskWriteAccess {
    param([string]$Dir)
    $probe = Join-Path $Dir ".kiosk_write_test"
    try {
        [System.IO.File]::WriteAllText($probe, "ok")
        Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
        return $true
    }
    catch {
        Write-Log "Sin permiso de escritura en ${Dir}: $($_.Exception.Message)"
        return $false
    }
}

if (-not $AppPath -or -not (Test-Path -LiteralPath $AppPath)) {
    Write-Log "ERROR: AppPath no existe: $AppPath"
    Start-Sleep -Seconds 60
    exit 1
}

$pythonResolved = $null
if (Get-Command Find-PythonForKiosk -ErrorAction SilentlyContinue) {
    $pythonResolved = Find-PythonForKiosk -AppPath $AppPath
}
if (-not $pythonResolved) {
    $venvPy = Join-Path $AppPath ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) { $pythonResolved = $venvPy }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { $pythonResolved = "py" }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { $pythonResolved = (Get-Command python).Source }
}

$venvPy = Join-Path $AppPath ".venv\Scripts\python.exe"
if ($pythonResolved -and (Test-Path -LiteralPath $pythonResolved)) {
    try {
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = $pythonResolved
        $pinfo.Arguments = "-c `"import sys; print(sys.executable)`""
        $pinfo.WorkingDirectory = $AppPath
        $pinfo.UseShellExecute = $false
        $pinfo.RedirectStandardOutput = $true
        $pinfo.RedirectStandardError = $true
        $pinfo.CreateNoWindow = $true
        $p = [System.Diagnostics.Process]::Start($pinfo)
        $p.WaitForExit(15000)
        if ($p.ExitCode -ne 0) {
            $err = $p.StandardError.ReadToEnd()
            Write-Log "Python no ejecutable (exit $($p.ExitCode)): $err"
        }
    }
    catch {
        Write-Log "Acceso denegado al ejecutar Python: $($_.Exception.Message)"
    }
}

if (-not (Test-KioskWriteAccess -Dir $AppPath)) {
    Write-Log "ERROR: Ejecutá repair_kiosk.ps1 o fix_kiosk_permissions.ps1 como Administrador."
    Start-Sleep -Seconds 120
    exit 1
}

$hasExe = Test-Path (Join-Path $AppPath "Expendedora.exe")
if (-not $hasExe -and -not $pythonResolved) {
    Write-Log "ERROR: No hay Expendedora.exe ni Python. Reinstalá repair_kiosk.ps1 -AppPath C:\expendedoraExperimental"
    Start-Sleep -Seconds 60
    exit 1
}

if (-not (Get-Process explorer -ErrorAction SilentlyContinue)) {
    Start-Process explorer.exe -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}
Hide-Taskbar
Start-Sleep -Seconds 2

while ($true) {
    try {
        Write-Log "Iniciando expendedora (py=$pythonResolved)..."
        $proc = Start-ExpendedoraProcess -ResolvedAppPath $AppPath -PythonResolved $pythonResolved
        if ($null -eq $proc) {
            throw "Process.Start devolvió null"
        }
        $proc.WaitForExit()
        Write-Log "Proceso finalizado código $($proc.ExitCode)"
    }
    catch {
        $msg = $_.Exception.Message
        Write-Log "ERROR: $msg"
        if ($msg -match 'denegad|denied|acceso|access|permission|autorizaci') {
            Write-Log "Pausa larga por error de permisos (evitar bucle)..."
            Start-Sleep -Seconds 120
            continue
        }
    }
    Write-Log "Reinicio en ${RestartDelaySeconds}s..."
    Start-Sleep -Seconds $RestartDelaySeconds
}
