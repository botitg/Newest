param(
    [string]$ProjectDir = (Split-Path -Parent $PSScriptRoot),
    [bool]$KeepAwake = $true,
    [int]$RestartDelaySeconds = 5,
    [string]$StartupFileName = "MirnastanBot_Autostart.cmd"
)

$ErrorActionPreference = "Stop"
if ($RestartDelaySeconds -lt 1) { $RestartDelaySeconds = 1 }

$runner = Join-Path $ProjectDir "scripts\run_bot_forever.ps1"
if (-not (Test-Path $runner)) {
    throw "Runner script not found: $runner"
}

$startupDir = [Environment]::GetFolderPath("Startup")
if ([string]::IsNullOrWhiteSpace($startupDir)) {
    $startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
}

if ([string]::IsNullOrWhiteSpace($startupDir)) {
    throw "Could not resolve Startup folder path."
}

if (-not (Test-Path $startupDir)) {
    New-Item -ItemType Directory -Path $startupDir -Force | Out-Null
}

$startupFilePath = Join-Path $startupDir $StartupFileName
$keepAwakeArg = if ($KeepAwake) { "1" } else { "0" }

$cmdContent = @(
    "@echo off"
    "cd /d `"$ProjectDir`""
    "start `"`" powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`" -ProjectDir `"$ProjectDir`" -RestartDelaySeconds $RestartDelaySeconds -KeepAwake $keepAwakeArg"
) -join "`r`n"

Set-Content -Path $startupFilePath -Value $cmdContent -Encoding ASCII -Force -ErrorAction Stop

Write-Host "Startup autostart installed: $startupFilePath"
