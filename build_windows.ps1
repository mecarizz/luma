$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
$artifactRoot = Join-Path $projectRoot "project_extras"
$distDirectory = Join-Path $artifactRoot "dist"
$buildDirectory = Join-Path $artifactRoot "build"

New-Item -ItemType Directory -Force -Path $distDirectory, $buildDirectory | Out-Null

python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed. Run: python -m pip install -r requirements-build.txt"
}

python -m PyInstaller --clean --noconfirm --distpath $distDirectory --workpath $buildDirectory Luma.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$executable = Join-Path $distDirectory "Luma.exe"
if (-not (Test-Path -LiteralPath $executable)) {
    throw "Build finished without producing project_extras\dist\Luma.exe."
}

$zipPath = Join-Path $distDirectory "Luma-windows-x64.zip"
$shaPath = Join-Path $distDirectory "Luma-windows-x64.zip.sha256"

Compress-Archive -Force -LiteralPath $executable -DestinationPath $zipPath
$hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLower()
"$hash  Luma-windows-x64.zip" | Set-Content -LiteralPath $shaPath -Encoding ascii

Write-Host "Build and packaging successful:"
Write-Host "  Executable: $executable"
Write-Host "  Archive:    $zipPath"
Write-Host "  Checksum:   $shaPath"
