# An explicit allowlist prevents local locations, screenshots and runtimes leaking into releases.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
$files = @('README.md', 'requirements.txt', 'requirements-lock.txt', '.gitignore', '.gitattributes', 'Setup.bat', 'Start.bat', 'start_launcher.ps1', 'launcher.py', 'main.py', 'fly.py')
$folders = @{'pikmin'=@('.py'); 'tests'=@('.py'); 'scripts'=@('.ps1'); 'docs'=@('.md'); 'examples'=@('.txt'); 'mushroom_pics'=@('.png'); '.github'=@('.yml', '.yaml')}
foreach ($folder in $folders.Keys) {
    $folderPath = Join-Path $projectRoot $folder
    if (-not (Test-Path -LiteralPath $folderPath)) { continue }
    foreach ($file in Get-ChildItem -LiteralPath $folderPath -Recurse -File) {
        if ($file.FullName -match '[\\/]__pycache__[\\/]' -or $file.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
        if ($folders[$folder] -contains $file.Extension) {
            $files += $file.FullName.Substring($projectRoot.Length + 1)
        }
    }
}
$outputFolder = Join-Path $projectRoot 'dist'
New-Item -ItemType Directory -Force -Path $outputFolder | Out-Null
$output = Join-Path $outputFolder ('Pikmin-mushroom-source-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.zip')
$archive = [IO.Compression.ZipFile]::Open($output, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($relative in $files | Sort-Object -Unique) {
        $source = Join-Path $projectRoot $relative
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $source, $relative.Replace('\', '/'), [IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
} finally {
    $archive.Dispose()
}
Write-Host $output
