@echo off
setlocal
cd /d "%~dp0"

set "ARTIFACT_ROOT=%~dp0project_extras"
set "DIST_DIR=%ARTIFACT_ROOT%\dist"
set "BUILD_DIR=%ARTIFACT_ROOT%\build"

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"

python -m PyInstaller --clean --noconfirm --distpath "%DIST_DIR%" --workpath "%BUILD_DIR%" Luma.spec
if errorlevel 1 (
    echo Build failed. Install dependencies with: python -m pip install -r requirements-build.txt
    exit /b 1
)

if not exist "%DIST_DIR%\Luma.exe" (
    echo Build finished without producing project_extras\dist\Luma.exe.
    exit /b 1
)

powershell -NoProfile -Command "Compress-Archive -Force -LiteralPath '.\project_extras\dist\Luma.exe' -DestinationPath '.\project_extras\dist\Luma-windows-x64.zip'; $hash = (Get-FileHash '.\project_extras\dist\Luma-windows-x64.zip' -Algorithm SHA256).Hash.ToLower(); \"$hash  Luma-windows-x64.zip\" | Set-Content '.\project_extras\dist\Luma-windows-x64.zip.sha256' -Encoding ascii"
if errorlevel 1 (
    echo Executable built, but release ZIP/checksum packaging failed.
    exit /b 1
)

echo Build successful:
echo   "%~dp0project_extras\dist\Luma.exe"
echo   "%~dp0project_extras\dist\Luma-windows-x64.zip"
