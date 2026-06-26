$ErrorActionPreference = "Stop"

# Build ONLY the MCP stdio server bundle.
#
# Run from repo root:
#   powershell -ExecutionPolicy Bypass -File .\build\windows\build_mcp.ps1

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

Write-Host "Repo: $RepoRoot"

$mcpSpec = Join-Path $RepoRoot "proper_thinking_ai_mcp.spec"
$mcpEntry = Join-Path $RepoRoot "mcp_entry.py"

if (-not (Test-Path $mcpSpec)) {
  throw "Missing proper_thinking_ai_mcp.spec (expected at repo root)."
}
if (-not (Test-Path $mcpEntry)) {
  throw "Missing mcp_entry.py (expected at repo root next to the MCP spec)."
}

python -m pip install --upgrade pip
python -m pip install --upgrade "pyinstaller>=6.10"
python -m pip install -r (Join-Path $RepoRoot "requirements.txt")

$distMcp = Join-Path $RepoRoot "dist\ProperThinkingAI_MCP"
if (Test-Path $distMcp) {
  Write-Host "Removing existing $distMcp"
  Remove-Item -Recurse -Force $distMcp
}

$workMcp = Join-Path $RepoRoot "build\pyinstaller_mcp"
if (Test-Path $workMcp) {
  Write-Host "Removing existing $workMcp"
  Remove-Item -Recurse -Force $workMcp
}

Write-Host "Starting PyInstaller MCP bundle..."
python -m PyInstaller --clean --noconfirm --workpath $workMcp $mcpSpec
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller MCP build failed (exit code $LASTEXITCODE)."
}

Write-Host "Done."
Write-Host "MCP output folder: $distMcp"
Write-Host "MCP run: $(Join-Path $distMcp 'ProperThinkingAI_MCP.exe')"
