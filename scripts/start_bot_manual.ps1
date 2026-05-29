param(
    [string]$ProjectDir = (Split-Path -Parent $PSScriptRoot),
    [int]$RestartDelaySeconds = 5,
    [string]$KeepAwake = "1",
    [ValidateSet("persistent", "detached", "foreground")]
    [string]$Mode = "detached",
    [string]$TaskName = "StateGameBot"
)

$runner = Join-Path $ProjectDir "scripts\run_bot_forever.ps1"
if (-not (Test-Path $runner)) {
    throw "Runner script not found: $runner"
}

$keepAwakeEnabled = $true
$keepAwakeValue = ([string]$KeepAwake).Trim().ToLower()
switch ($keepAwakeValue) {
    "0" { $keepAwakeEnabled = $false; break }
    "false" { $keepAwakeEnabled = $false; break }
    "no" { $keepAwakeEnabled = $false; break }
    "off" { $keepAwakeEnabled = $false; break }
    default { $keepAwakeEnabled = $true; break }
}

$keepAwakeArg = if ($keepAwakeEnabled) { "1" } else { "0" }

if ($Mode -eq "persistent") {
    $installer = Join-Path $ProjectDir "scripts\install_autostart_task.ps1"
    $startupInstaller = Join-Path $ProjectDir "scripts\install_startup_folder_autostart.ps1"
    $registryInstaller = Join-Path $ProjectDir "scripts\install_registry_autostart.ps1"
    if (-not (Test-Path $installer)) {
        throw "Installer script not found: $installer"
    }

    Write-Host "Enabling persistent bot mode (survives VS Code close and starts at logon)..."
    try {
        & $installer -TaskName $TaskName -ProjectDir $ProjectDir -KeepAwake:$keepAwakeEnabled
        $installerExitCode = $LASTEXITCODE
        if ($installerExitCode -ne $null -and $installerExitCode -ne 0) {
            throw "Installer exited with code $installerExitCode"
        }
        return
    }
    catch {
        Write-Warning "Persistent mode failed: $($_.Exception.Message)"
        if (Test-Path $startupInstaller) {
            Write-Host "Trying Startup-folder autostart fallback..."
            try {
                & $startupInstaller -ProjectDir $ProjectDir -KeepAwake:$keepAwakeEnabled -RestartDelaySeconds $RestartDelaySeconds
                $startupExitCode = $LASTEXITCODE
                if ($startupExitCode -ne $null -and $startupExitCode -ne 0) {
                    throw "Startup installer exited with code $startupExitCode"
                }
                return
            }
            catch {
                Write-Warning "Startup-folder fallback failed: $($_.Exception.Message)"
            }
        }
        else {
            Write-Warning "Startup-folder installer script not found: $startupInstaller"
        }

        if (Test-Path $registryInstaller) {
            Write-Host "Trying Registry autostart fallback..."
            try {
                & $registryInstaller -ProjectDir $ProjectDir -KeepAwake:$keepAwakeEnabled -RestartDelaySeconds $RestartDelaySeconds
                $registryExitCode = $LASTEXITCODE
                if ($registryExitCode -ne $null -and $registryExitCode -ne 0) {
                    throw "Registry installer exited with code $registryExitCode"
                }
                return
            }
            catch {
                Write-Warning "Registry fallback failed: $($_.Exception.Message)"
            }
        }
        else {
            Write-Warning "Registry installer script not found: $registryInstaller"
        }

        Write-Warning "Falling back to detached background mode for this session."
        $Mode = "detached"
    }
}

$runnerArgs = @(
    "-NoProfile"
    "-ExecutionPolicy"
    "Bypass"
    "-File"
    $runner
    "-ProjectDir"
    $ProjectDir
    "-RestartDelaySeconds"
    "$RestartDelaySeconds"
    "-KeepAwake"
    $keepAwakeArg
)

if ($Mode -eq "detached") {
    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $runnerArgs -WorkingDirectory $ProjectDir -WindowStyle Hidden -PassThru
    Write-Host "Bot started in background (PID: $($proc.Id))."
    return
}

Write-Host "Starting bot in foreground (bound to current terminal)..."
& powershell @runnerArgs
