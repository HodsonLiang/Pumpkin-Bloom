$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

function Find-Python311 {
    $candidates = @(
        (Join-Path $projectRoot 'python11\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:ProgramFiles 'Python311\python.exe')
    )
    $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $detected = & $pyLauncher.Source -3.11 -c 'import sys; print(sys.executable)' 2>$null
        $detectedExit = $LASTEXITCODE
        $ErrorActionPreference = $previousPreference
        if ($detectedExit -eq 0 -and $detected) { $candidates = @($detected.Trim()) + $candidates }
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            & $candidate -c 'import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,11) and struct.calcsize(chr(80)) == 8 else 1)'
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    return $null
}

try {
    $venvPython = Join-Path $projectRoot 'myenv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $basePython = Find-Python311
        if (-not $basePython) {
            $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
            if (-not $winget) {
                throw 'Install Python 3.11.9 (Windows 64-bit, including Tcl/Tk) from https://www.python.org/downloads/release/python-3119/ and run Setup.bat again. Alternatively install App Installer to enable winget.'
            }
            Write-Host 'Installing Python 3.11 (64-bit) for the current Windows user...'
            & $winget.Source install --id Python.Python.3.11 --exact --source winget --scope user --architecture x64 --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
            if ($LASTEXITCODE -ne 0) { throw 'Python installation failed. Install Python 3.11 manually, then retry Setup.bat.' }
            $basePython = Find-Python311
            if (-not $basePython) { throw 'Python was not detected. Reopen Setup.bat, or install Python 3.11 (64-bit) manually.' }
        }
        Write-Host 'Creating the local myenv environment...'
        & $basePython -m venv (Join-Path $projectRoot 'myenv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create myenv. Check the project folder permissions.' }
    }
    # Existing environments are reused; never delete a user environment automatically.
    & $venvPython -c 'import sys,struct,tkinter; sys.exit(0 if sys.version_info[:2] == (3,11) and struct.calcsize(chr(80)) == 8 else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'myenv is not a working Python 3.11 64-bit environment with Tk. Rename myenv to myenv-backup and run Setup.bat again.' }
    Write-Host 'Installing project dependencies from PyPI...'
    & $venvPython -m pip --isolated install --index-url https://pypi.org/simple -r (Join-Path $projectRoot 'requirements.txt') -c (Join-Path $projectRoot 'requirements-lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check Internet access and the pip error above.' }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency conflicts detected; see pip check output above.' }
    & $venvPython -c "import tkinter, tkintermapview, PIL, cv2; from pymobiledevice3.tunneld.api import TUNNELD_DEFAULT_ADDRESS; import pikmin.scan_ui, pikmin.fly_ui; print('Application imports OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Application dependency check failed.' }
    $localWaypoints = Join-Path $projectRoot 'waypoints.txt'
    if (-not (Test-Path -LiteralPath $localWaypoints)) {
        Copy-Item -LiteralPath (Join-Path $projectRoot 'examples\waypoints.txt') -Destination $localWaypoints
    }
    Write-Host 'Ready. Connect/unlock the iPhone, then double-click Start.bat.'
} catch {
    Write-Host ('SETUP ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
