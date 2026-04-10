$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $root "scripts\run-required-checks-fast.ps1"

if (-not (Test-Path $script)) {
  throw "Missing required script: $script"
}

powershell -NoProfile -ExecutionPolicy Bypass -File $script
exit $LASTEXITCODE
