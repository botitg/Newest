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

    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $ProjectDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1)

    $userName = if ($env:USERDOMAIN) { "$($env:USERDOMAIN)\$($env:USERNAME)" } else { $env:USERNAME }
    $principal = New-ScheduledTaskPrincipal -UserId $userName -LogonType Interactive -RunLevel Limited

    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "State Game bot auto-runner (main.py)" `
        -Force | Out-Null

    Start-ScheduledTask -TaskName $TaskName
}

function Install-WithSchtasksFallback {
    $taskCommand = "`"powershell.exe`" $arguments"
    schtasks /Create /TN $TaskName /SC ONLOGON /TR $taskCommand /RL LIMITED /F | Out-Null
    schtasks /Run /TN $TaskName | Out-Null
}

try {
    Install-WithScheduledTasksCmdlets
}
catch {
    Write-Warning "ScheduledTasks cmdlets failed: $($_.Exception.Message). Trying schtasks fallback."
    Install-WithSchtasksFallback
}

Write-Host "Task '$TaskName' installed and started."
