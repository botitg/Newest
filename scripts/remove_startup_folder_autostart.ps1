param(
    [string]$StartupFileName = "MirnastanBot_Autostart.cmd"
)

$ErrorActionPreference = "Stop"

$startupDir = [Environment]::GetFolderPath("Startup")
if ([string]::IsNullOrWhiteSpace($startupDir)) {
    $startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
}

if ([string]::IsNullOrWhiteSpace($startupDir)) {
    Write-Host "Startup folder path not resolved."
    exit 0
}

$startupFilePath = Join-Path $startupDir $StartupFileName
if (Test-Path $startupFilePath) {
    Remove-Item -Path $startupFilePath -Force -ErrorAction Stop
    Write-Host "Startup autostart removed: $startupFilePath"
}
else {
    Write-Host "Startup autostart file not found: $startupFilePath"
}
