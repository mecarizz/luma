@echo off
setlocal
cd /d "%~dp0"

python -m PyInstaller --clean --noconfirm Luma.spec
if errorlevel 1 (
    echo Build failed. Install dependencies with: python -m pip install -r requirements-build.txt
    exit /b 1
)

if not exist "dist\Luma.exe" (
    echo Build finished without producing dist\Luma.exe.
    exit /b 1
)

powershell -NoProfile -Command "Compress-Archive -Force -LiteralPath '.\dist\Luma.exe' -DestinationPath '.\dist\Luma-windows-x64.zip'; $hash = (Get-FileHash '.\dist\Luma-windows-x64.zip' -Algorithm SHA256).Hash.ToLower(); \"$hash  Luma-windows-x64.zip\" | Set-Content '.\dist\Luma-windows-x64.zip.sha256' -Encoding ascii"
if errorlevel 1 (
    echo Executable built, but release ZIP/checksum packaging failed.
    exit /b 1
)

echo Build successful:
echo   "%~dp0dist\Luma.exe"
echo   "%~dp0dist\Luma-windows-x64.zip"
