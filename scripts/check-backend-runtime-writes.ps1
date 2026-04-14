$ErrorActionPreference = "Stop"

$repoRoot = Split-Path $PSScriptRoot -Parent
$script = Join-Path $repoRoot "scripts\ci\check_backend_runtime_writes.py"

Write-Host ""
Write-Host "==> Backend runtime write guardrails"

if (-not (Test-Path $script)) {
  throw "Missing required script: $script"
}

python $script
exit $LASTEXITCODE
