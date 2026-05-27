#Requires -RunAsAdministrator
<#
Repara kiosk sin reinstalar todo: config, launcher actualizado y tarea al logon.

  powershell -ExecutionPolicy Bypass -File configSO\windows\repair_kiosk.ps1
#>
param(
    [string]$KioskUser = "cajero",
    [string]$AppPath = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
. (Join-Path $ScriptDir "kiosk_paths.ps1")
. (Join-Path $ScriptDir "kiosk_registry.ps1")

$TaskName = "ExpendedoraKioskLauncher"
$kioskDir = $script:KioskProgramDataDir
$TemplateDir = Join-Path $ScriptDir "templates"

if (-not $AppPath) {
    $AppPath = Find-KioskAppPath
}
if (-not $AppPath -or -not (Test-Path (Join-Path $AppPath "main.py"))) {
    throw "No se encontró main.py. Probá -AppPath C:\expendedoraExperimental o install -DeployTo."
}
$AppPath = (Resolve-Path -LiteralPath $AppPath).Path
Write-Host "AppPath: $AppPath"

if (Test-VenvUsesForeignUserPython -AppPath $AppPath -KioskUser $KioskUser) {
    Write-Host "  .venv apunta al Python de otro usuario; recreando..."
    $pythonExe = Repair-KioskVenv -AppPath $AppPath -KioskUser $KioskUser
}
else {
    $venvPy = Join-Path $AppPath ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPy)) {
        Write-Host "  Creando .venv en $AppPath (no existia)..."
        $pythonExe = Ensure-VenvAtAppPath -AppPath $AppPath -KioskUser $KioskUser
    }
    else {
        $pythonExe = (Resolve-Path -LiteralPath $venvPy).Path
        Write-Host "  Usando venv existente: $pythonExe"
        $pyPathFile = Join-Path $script:KioskProgramDataDir "python_exe.txt"
        New-Item -ItemType Directory -Path $script:KioskProgramDataDir -Force | Out-Null
        Set-Content -Path $pyPathFile -Value $pythonExe -Encoding ASCII -NoNewline
    }
}

if (-not $pythonExe -or -not (Test-Path -LiteralPath $pythonExe)) {
    throw "No hay Python usable en $AppPath. Instalá Python para todos los usuarios y ejecutá repair_kiosk.ps1"
}

Write-Host "[1] kiosk.json + registro..."
Set-KioskConfig -AppPath $AppPath -PythonExe $pythonExe
New-Item -Path "HKLM:\SOFTWARE\Expendedora" -Force | Out-Null
Set-ItemProperty -Path "HKLM:\SOFTWARE\Expendedora" -Name "AppPath" -Value $AppPath -Force
Set-ItemProperty -Path "HKLM:\SOFTWARE\Expendedora" -Name "PythonExe" -Value $pythonExe -Force
Grant-KioskAppAccess -AppPath $AppPath -KioskUser $KioskUser
Grant-KioskPathAcl -Path $kioskDir -KioskUser $KioskUser

Write-Host "[2] Launcher .cmd (login de app, sin EXPENDEDORA_KIOSK)..."
New-Item -ItemType Directory -Path $kioskDir -Force | Out-Null
$launcherCmd = Install-KioskUserCmd -AppPath $AppPath -DestDir $AppPath `
    -TemplateCmdPath (Join-Path $TemplateDir "AbrirExpendedora.cmd")
Install-KioskUserCmd -AppPath $AppPath -DestDir $kioskDir `
    -TemplateCmdPath (Join-Path $TemplateDir "AbrirExpendedora.cmd") | Out-Null
Grant-KioskPathAcl -Path $kioskDir -KioskUser $KioskUser
Write-Host "  CMD (tarea/acceso directo): $launcherCmd"

Write-Host "[2b] Acceso directo en escritorio de $KioskUser..."
Install-KioskDesktopShortcut -KioskUser $KioskUser -AppPath $AppPath -LauncherCmd $launcherCmd

Write-Host "[3] Tarea al iniciar sesión ($KioskUser)..."
Register-KioskLogonTask -TaskName $TaskName -KioskUser $KioskUser -LauncherCmd $launcherCmd

Write-Host "[4] Auto-login..."
$winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
Set-ItemProperty -Path $winlogon -Name "AutoAdminLogon" -Value "1" -Force
Set-ItemProperty -Path $winlogon -Name "DefaultUserName" -Value $KioskUser -Force
Set-ItemProperty -Path $winlogon -Name "DefaultDomainName" -Value "." -Force
Set-ItemProperty -Path $winlogon -Name "DefaultPassword" -Value "" -Force

Write-Host ""
Write-Host "Listo. AppPath=$AppPath Python=$pythonExe"
Write-Host "Probar ahora (como cajero): doble clic Expendedora o:"
Write-Host "  $launcherCmd"
Write-Host "Reiniciar: shutdown /r /t 0"
