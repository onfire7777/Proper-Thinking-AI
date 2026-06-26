$ErrorActionPreference = "Stop"

# Build ONLY the desktop GUI bundle.
#
# Run from repo root:
#   powershell -ExecutionPolicy Bypass -File .\build\windows\build_desktop.ps1

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

Write-Host "Repo: $RepoRoot"

$desktopSpec = Join-Path $RepoRoot "proper_thinking_ai_desktop.spec"
if (-not (Test-Path $desktopSpec)) {
  throw "Missing proper_thinking_ai_desktop.spec (expected at repo root)."
}

python -m pip install --upgrade pip
python -m pip install --upgrade "pyinstaller>=6.10"
python -m pip install -r (Join-Path $RepoRoot "requirements.txt")

$distDesktop = Join-Path $RepoRoot "dist\ProperThinkingAI"
if (Test-Path $distDesktop) {
  Write-Host "Removing existing $distDesktop"
  Remove-Item -Recurse -Force $distDesktop
}

$workDesktop = Join-Path $RepoRoot "build\pyinstaller_desktop"
if (Test-Path $workDesktop) {
  Write-Host "Removing existing $workDesktop"
  Remove-Item -Recurse -Force $workDesktop
}

Write-Host "Starting PyInstaller DESKTOP bundle..."
python -m PyInstaller --clean --noconfirm --workpath $workDesktop $desktopSpec
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller DESKTOP build failed (exit code $LASTEXITCODE)."
}

Write-Host "Done."
Write-Host "Desktop output folder: $distDesktop"
Write-Host "Desktop run: $(Join-Path $distDesktop 'ProperThinkingAI.exe')"
