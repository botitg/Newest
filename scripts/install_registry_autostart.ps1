param(
    [string]$ProjectDir = (Split-Path -Parent $PSScriptRoot),
    [bool]$KeepAwake = $true,
    [int]$RestartDelaySeconds = 5,
    [string]$RunValueName = "MirnastanBot"
)

$ErrorActionPreference = "Stop"
if ($RestartDelaySeconds -lt 1) { $RestartDelaySeconds = 1 }

$runner = Join-Path $ProjectDir "scripts\run_bot_forever.ps1"
if (-not (Test-Path $runner)) {
    throw "Runner script not found: $runner"
}

$keepAwakeArg = if ($KeepAwake) { "1" } else { "0" }
$command = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`" -ProjectDir `"$ProjectDir`" -RestartDelaySeconds $RestartDelaySeconds -KeepAwake $keepAwakeArg"

$runPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (-not (Test-Path $runPath)) {
    New-Item -Path $runPath -Force | Out-Null
}

Set-ItemProperty -Path $runPath -Name $RunValueName -Value $command -Type String -ErrorAction Stop
Write-Host "Registry autostart installed: HKCU\\...\\Run\\$RunValueName"
