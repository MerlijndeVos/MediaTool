# Build the desktop app bundle locally (Windows PowerShell).
# Usage: .\packaging\build.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Version = python -c "from core.version import read_pyproject_version; print(read_pyproject_version())"
Write-Host "==> Version $Version (from pyproject.toml)"

Write-Host "==> Syncing frontend package version"
npm pkg set "version=$Version" --prefix web/frontend

Write-Host "==> Building frontend"
Push-Location web/frontend
if (-not (Test-Path node_modules)) { npm ci }
npm run build
Pop-Location

Write-Host "==> Installing Python build deps"
python -m pip install -e ".[desktop,pack]" -q

Write-Host "==> Running PyInstaller"
pyinstaller packaging/media-tool.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Done: dist/MediaTool/MediaTool.exe"
Write-Host "    Optional installer: iscc /DMyAppVersion=$Version packaging/windows/setup.iss"
