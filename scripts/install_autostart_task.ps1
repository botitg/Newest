param(
    [string]$TaskName = 'StateGameBot',
    [string]$ProjectDir = (Split-Path -Parent $PSScriptRoot),
    [bool]$KeepAwake = $true
)

$runner = Join-Path $ProjectDir 'scripts\run_bot_forever.ps1'
if (-not (Test-Path $runner)) {
    throw "Runner script not found: $runner"
}

$keepAwakeArg = if ($KeepAwake) { 1 } else { 0 }
$arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`" -ProjectDir `"$ProjectDir`" -KeepAwake $keepAwakeArg"

function Install-WithScheduledTasksCmdlets {
    Import-Module ScheduledTasks -ErrorAction Stop

    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $ProjectDir -ErrorAction Stop
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME -ErrorAction Stop
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ErrorAction Stop

    $userName = if ($env:USERDOMAIN) { "$($env:USERDOMAIN)\$($env:USERNAME)" } else { $env:USERNAME }
    $principal = New-ScheduledTaskPrincipal -UserId $userName -LogonType Interactive -RunLevel Limited -ErrorAction Stop

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "State Game bot auto-runner (main.py)" `
        -Force `
        -ErrorAction Stop | Out-Null

    Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
}

function Install-WithSchtasksFallback {
    $taskCommand = "`"powershell.exe`" $arguments"
    schtasks /Create /TN $TaskName /SC ONLOGON /TR $taskCommand /RL LIMITED /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "schtasks create failed with code $LASTEXITCODE"
    }

    schtasks /Run /TN $TaskName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "schtasks run failed with code $LASTEXITCODE (task created, but start-on-demand failed)."
    }
}

function Test-TaskExists {
    schtasks /Query /TN $TaskName >$null 2>$null
    return ($LASTEXITCODE -eq 0)
}

$installErrors = New-Object System.Collections.Generic.List[string]

try {
    Install-WithScheduledTasksCmdlets
}
catch {
    $installErrors.Add("ScheduledTasks cmdlets failed: $($_.Exception.Message)")
    Write-Warning "ScheduledTasks cmdlets failed: $($_.Exception.Message). Trying schtasks fallback."
    try {
        Install-WithSchtasksFallback
    }
    catch {
        $installErrors.Add("schtasks fallback failed: $($_.Exception.Message)")
    }
}

if (-not (Test-TaskExists)) {
    $startupInstaller = Join-Path $PSScriptRoot "install_startup_folder_autostart.ps1"
    $registryInstaller = Join-Path $PSScriptRoot "install_registry_autostart.ps1"
    if (Test-Path $startupInstaller) {
        Write-Warning "Task Scheduler unavailable, switching to Startup-folder autostart."
        & $startupInstaller -ProjectDir $ProjectDir -KeepAwake:$KeepAwake
        $startupExitCode = $LASTEXITCODE
        if ($startupExitCode -eq $null -or $startupExitCode -eq 0) {
            Write-Host "Startup-folder autostart installed."
            exit 0
        }
        $installErrors.Add("startup fallback failed with code $startupExitCode")
    }

    if (Test-Path $registryInstaller) {
        Write-Warning "Startup-folder unavailable, switching to Registry autostart."
        & $registryInstaller -ProjectDir $ProjectDir -KeepAwake:$KeepAwake
        $registryExitCode = $LASTEXITCODE
        if ($registryExitCode -eq $null -or $registryExitCode -eq 0) {
            Write-Host "Registry autostart installed."
            exit 0
        }
        $installErrors.Add("registry fallback failed with code $registryExitCode")
    }

    $errorText = if ($installErrors.Count -gt 0) { $installErrors -join " | " } else { "unknown error" }
    throw "Task '$TaskName' was not created. Details: $errorText"
}

Write-Host "Task '$TaskName' installed and started."
