param(
    [string]$TaskName = "StateGameBot"
)

Write-Host "Stopping bot processes..."

# 1) Remove scheduled autostart task if it exists.
try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "remove_autostart_task.ps1") -TaskName $TaskName | Out-Null
} catch {
}

# 1.1) Remove Startup-folder autostart if it exists.
try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "remove_startup_folder_autostart.ps1") | Out-Null
} catch {
}

# 1.2) Remove registry autostart if it exists.
try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "remove_registry_autostart.ps1") | Out-Null
} catch {
}

# 2) Stop runner powershell processes.
$runnerProcs = @()
try {
    $runnerProcs = Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object { $_.Name -match '^powershell(\.exe)?$' -and $_.CommandLine -match 'run_bot_forever\.ps1' }
} catch {
    $runnerProcs = @()
}
foreach ($p in $runnerProcs) {
    try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {}
}

# 3) Stop bot main.py processes.
$botProcs = @()
try {
    $botProcs = Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object {
            $_.Name -match '^python(\.exe)?$' -and
            $_.CommandLine -match 'main\.py([\"\''\s]|$)'
        }
} catch {
    $botProcs = @()
}
foreach ($p in $botProcs) {
    try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {}
}

Write-Host "Bot stopped. Autostart task removed (if existed)."
