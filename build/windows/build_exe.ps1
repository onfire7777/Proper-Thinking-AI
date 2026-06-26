$ErrorActionPreference = "Stop"

# Build BOTH bundles (desktop + MCP), sequentially.
#
# If you need parallel builds / shorter iteration loops, prefer:
# - .\build\windows\build_desktop.ps1
# - .\build\windows\build_mcp.ps1
#
# Run from repo root:
#   powershell -ExecutionPolicy Bypass -File .\build\windows\build_exe.ps1

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

Write-Host "Repo: $RepoRoot"

$desktopSpec = Join-Path $RepoRoot "proper_thinking_ai_desktop.spec"
$mcpSpec = Join-Path $RepoRoot "proper_thinking_ai_mcp.spec"
$mcpEntry = Join-Path $RepoRoot "mcp_entry.py"

if (-not (Test-Path $desktopSpec)) {
  throw "Missing proper_thinking_ai_desktop.spec (expected at repo root)."
}
if (-not (Test-Path $mcpSpec)) {
  throw "Missing proper_thinking_ai_mcp.spec (expected at repo root)."
}
if (-not (Test-Path $mcpEntry)) {
  throw "Missing mcp_entry.py (expected at repo root next to the MCP spec)."
}

# Ensure build tooling exists in the active environment
python -m pip install --upgrade pip
python -m pip install --upgrade "pyinstaller>=6.10"
python -m pip install -r (Join-Path $RepoRoot "requirements.txt")

# Clean previous output (optional but avoids stale bundles)
$distDesktop = Join-Path $RepoRoot "dist\ProperThinkingAI"
if (Test-Path $distDesktop) {
  Write-Host "Removing existing $distDesktop"
  Remove-Item -Recurse -Force $distDesktop
}

$distMcp = Join-Path $RepoRoot "dist\ProperThinkingAI_MCP"
if (Test-Path $distMcp) {
  Write-Host "Removing existing $distMcp"
  Remove-Item -Recurse -Force $distMcp
}

$workDesktop = Join-Path $RepoRoot "build\pyinstaller_desktop"
if (Test-Path $workDesktop) {
  Write-Host "Removing existing $workDesktop"
  Remove-Item -Recurse -Force $workDesktop
}

$workMcp = Join-Path $RepoRoot "build\pyinstaller_mcp"
if (Test-Path $workMcp) {
  Write-Host "Removing existing $workMcp"
  Remove-Item -Recurse -Force $workMcp
}

Write-Host "Starting PyInstaller DESKTOP bundle (this can take a long time on first run)..."
python -m PyInstaller --clean --noconfirm --workpath $workDesktop $desktopSpec
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller DESKTOP build failed (exit code $LASTEXITCODE)."
}

Write-Host "Starting PyInstaller MCP bundle (this can also take a long time)..."
python -m PyInstaller --clean --noconfirm --workpath $workMcp $mcpSpec
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller MCP build failed (exit code $LASTEXITCODE)."
}

Write-Host "Done."
Write-Host "Desktop output folder: $(Join-Path $RepoRoot 'dist\ProperThinkingAI')"
Write-Host "Desktop run: $(Join-Path $RepoRoot 'dist\ProperThinkingAI\ProperThinkingAI.exe')"
Write-Host "MCP output folder: $(Join-Path $RepoRoot 'dist\ProperThinkingAI_MCP')"
Write-Host "MCP run: $(Join-Path $RepoRoot 'dist\ProperThinkingAI_MCP\ProperThinkingAI_MCP.exe')"
