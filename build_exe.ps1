$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    $python = "python"
}

Write-Host "Using Python: $python"

# Read version from version.py
$versionContent = Get-Content "version.py" -Raw
$versionMatch = $versionContent | Select-String -Pattern '__version__\s*=\s*"([^"]+)"' -AllMatches
if ($versionMatch.Matches.Count -eq 0) {
    throw "Could not find version in version.py"
}
$version = $versionMatch.Matches[0].Groups[1].Value
Write-Host "Building EVC_GUI v$version"

& $python -m pip show pyinstaller *> $null
if (-not $?) {
    Write-Host "PyInstaller not found. Installing..."
    & $python -m pip install pyinstaller
}

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "EVC_GUI_v$version" `
    --icon "smithchart.ico" `
    --add-data "ASM-logo-small.gif;." `
    "main.py"

if ($LASTEXITCODE -ne 0) {
    throw "Build failed."
}

Write-Host "Build complete: dist\EVC_GUI_v$version.exe"
