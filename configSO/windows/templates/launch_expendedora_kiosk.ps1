# Launcher kiosk Expendedora (Windows 11)
param(
    [string]$AppPath = "__APP_PATH__",
    [string]$LogFile = "",
    [int]$RestartDelaySeconds = 3
)

$ErrorActionPreference = "Continue"

if (-not $LogFile) {
    $LogFile = Join-Path $env:USERPROFILE "expendedora-kiosk.log"
}

function Write-Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -ErrorAction SilentlyContinue
    Write-Host $line
}

function Resolve-PythonCommand {
    if ($env:EXPENDEDORA_PYTHON -and (Test-Path $env:EXPENDEDORA_PYTHON)) {
        return $env:EXPENDEDORA_PYTHON
    }
    if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    return $null
}

function Start-ExpendedoraProcess {
    param([string]$PythonCmd)

    $mainPy = Join-Path $AppPath "main.py"
    if (-not (Test-Path $mainPy)) {
        throw "No se encontró main.py en: $AppPath"
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $venvPython = Join-Path $AppPath ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        Write-Log "Usando venv: $venvPython"
        $psi.FileName = $venvPython
        $psi.Arguments = "`"$mainPy`""
    }
    elseif ($PythonCmd -eq "py") {
        $psi.FileName = "py"
        $psi.Arguments = "-3 `"$mainPy`""
    }
    else {
        $psi.FileName = $PythonCmd
        $psi.Arguments = "`"$mainPy`""
    }
    $psi.WorkingDirectory = $AppPath
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    return [System.Diagnostics.Process]::Start($psi)
}

function Hide-Taskbar {
    try {
        Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" `
            -Name "TaskbarAutoHideInMode" -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
        Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced" `
            -Name "TaskbarSd" -Value 1 -Type DWord -Force -ErrorAction SilentlyContinue
    }
    catch {
        Write-Log "Aviso ocultar barra de tareas: $($_.Exception.Message)"
    }
}

Write-Log "=== Inicio launcher kiosk ==="
Write-Log "AppPath=$AppPath Usuario=$env:USERNAME"

if (-not (Test-Path $AppPath)) {
    Write-Log "ERROR: AppPath no existe."
    Start-Sleep -Seconds 30
    exit 1
}

$python = Resolve-PythonCommand
if (-not $python) {
    Write-Log "ERROR: No se encontró Python (py/python)."
    Start-Sleep -Seconds 60
    exit 1
}

Hide-Taskbar

while ($true) {
    try {
        Write-Log "Iniciando expendedora ($python)..."
        $proc = Start-ExpendedoraProcess -PythonCmd $python
        $proc.WaitForExit()
        Write-Log "Proceso finalizado con código $($proc.ExitCode)"
    }
    catch {
        Write-Log "ERROR al iniciar app: $($_.Exception.Message)"
    }
    Write-Log "Reiniciando en ${RestartDelaySeconds}s..."
    Start-Sleep -Seconds $RestartDelaySeconds
}
