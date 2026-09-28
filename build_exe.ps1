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
    --name "EVC_GUI_v26.0.0" `
    --icon "smithchart.ico" `
    --add-data "ASM-logo-small.gif;." `
    "main.py"

if ($LASTEXITCODE -ne 0) {
    throw "Build failed."
}

Write-Host "Build complete: dist\EVC_GUI_v26.0.0.exe"
