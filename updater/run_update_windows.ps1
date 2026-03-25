$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 (Join-Path $ScriptDir "auto_updater.py") --once
} else {
    python (Join-Path $ScriptDir "auto_updater.py") --once
}

