$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run: python -m pip install -r requirements-build.txt"
}

python -m PyInstaller --clean --noconfirm Luma.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$executable = Join-Path $projectRoot "dist\Luma.exe"
if (-not (Test-Path -LiteralPath $executable)) {
    throw "Build finished without producing dist\Luma.exe."
}

Write-Host "Build successful: $executable"
