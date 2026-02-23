param(
    [string]$TaskName = 'StateGameBot'
)

try {
    Import-Module ScheduledTasks -ErrorAction Stop
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
}
catch {
    schtasks /End /TN $TaskName 2>$null | Out-Null
    schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
}

Write-Host "Task '$TaskName' removed."
