param(
    [string]$RunValueName = "MirnastanBot"
)

$ErrorActionPreference = "Stop"
$runPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

if (-not (Test-Path $runPath)) {
    Write-Host "Registry autostart key not found."
    exit 0
}

$item = Get-ItemProperty -Path $runPath -Name $RunValueName -ErrorAction SilentlyContinue
if ($null -ne $item) {
    Remove-ItemProperty -Path $runPath -Name $RunValueName -ErrorAction Stop
    Write-Host "Registry autostart removed: HKCU\\...\\Run\\$RunValueName"
}
else {
    Write-Host "Registry autostart value not found: $RunValueName"
}
