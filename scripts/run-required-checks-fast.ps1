$ErrorActionPreference = "Stop"

$script = Join-Path $PSScriptRoot "invoke-ci-script.ps1"
if (-not (Test-Path $script)) {
  throw "Missing required script: $script"
}

powershell -NoProfile -ExecutionPolicy Bypass -File $script -ScriptRelativePath "scripts/ci/run_required_checks_fast.sh"
exit $LASTEXITCODE
