$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
try {
    $launcherPython = Join-Path $projectRoot 'myenv\Scripts\pythonw.exe'
    $launcherScript = Join-Path $projectRoot 'launcher.py'
    if (-not (Test-Path -LiteralPath $launcherPython)) { throw 'Environment missing. Double-click Setup.bat first.' }
    Start-Process -FilePath $launcherPython -ArgumentList ('"' + $launcherScript + '"') -WorkingDirectory $projectRoot -Verb RunAs -WindowStyle Hidden
} catch {
    Write-Host ('Launcher could not start: ' + $_.Exception.Message)
    exit 1
}
