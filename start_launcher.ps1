$ErrorActionPreference = 'Stop'
try {
    $launcherPython = Join-Path $PSScriptRoot 'myenv\Scripts\pythonw.exe'
    $launcherScript = Join-Path $PSScriptRoot 'launcher.py'
    if (-not (Test-Path -LiteralPath $launcherPython)) { throw 'Environment missing. Double-click Setup.bat first.' }
    Start-Process -FilePath $launcherPython -ArgumentList ('"' + $launcherScript + '"') -WorkingDirectory $PSScriptRoot -Verb RunAs -WindowStyle Hidden
} catch {
    Write-Host ('Launcher could not start: ' + $_.Exception.Message)
    exit 1
}
