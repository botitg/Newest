param(
    [string]$ProjectDir = (Split-Path -Parent $PSScriptRoot),
    [int]$RestartDelaySeconds = 5,
    [string]$KeepAwake = "1"
)

$ErrorActionPreference = 'Continue'
if ($RestartDelaySeconds -lt 1) { $RestartDelaySeconds = 1 }

$keepAwakeEnabled = $true
$keepAwakeValue = ([string]$KeepAwake).Trim().ToLower()
switch ($keepAwakeValue) {
    "0" { $keepAwakeEnabled = $false; break }
    "false" { $keepAwakeEnabled = $false; break }
    "no" { $keepAwakeEnabled = $false; break }
    "off" { $keepAwakeEnabled = $false; break }
    default { $keepAwakeEnabled = $true; break }
}

Set-Location $ProjectDir

$logsDir = Join-Path $ProjectDir 'logs'
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir | Out-Null
}

$pythonExe = Join-Path $ProjectDir '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        $pythonExe = $pythonCmd.Source
    }
    else {
        throw "Python not found. Install Python or create .venv in $ProjectDir"
    }
}

$mainScript = Join-Path $ProjectDir 'main.py'
if (-not (Test-Path $mainScript)) {
    throw "main.py not found: $mainScript"
}

$logFile = Join-Path $logsDir 'bot_runner.log'

function Write-RunnerLog([string]$Text) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "[$stamp] $Text" | Out-File -FilePath $logFile -Append -Encoding utf8
}

if ($keepAwakeEnabled) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class PowerState {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@ -ErrorAction SilentlyContinue | Out-Null

    $ES_CONTINUOUS = 0x80000000
    $ES_SYSTEM_REQUIRED = 0x00000001
    $ES_AWAYMODE_REQUIRED = 0x00000040
    [PowerState]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_AWAYMODE_REQUIRED) | Out-Null
    Write-RunnerLog "KeepAwake enabled (sleep prevention for this process)."
}

while ($true) {
    Write-RunnerLog "Starting bot using: $pythonExe"

    try {
        & $pythonExe $mainScript 2>&1 | Out-File -FilePath $logFile -Append -Encoding utf8
        $exitCode = if ($LASTEXITCODE -ne $null) { $LASTEXITCODE } else { 0 }
    }
    catch {
        Write-RunnerLog "Runner error: $($_.Exception.Message)"
        $exitCode = 1
    }

    Write-RunnerLog "Bot stopped (exit code: $exitCode). Restarting in $RestartDelaySeconds sec..."

    if ($keepAwakeEnabled) {
        $ES_CONTINUOUS = 0x80000000
        $ES_SYSTEM_REQUIRED = 0x00000001
        $ES_AWAYMODE_REQUIRED = 0x00000040
        [PowerState]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_AWAYMODE_REQUIRED) | Out-Null
    }

    Start-Sleep -Seconds $RestartDelaySeconds
}
