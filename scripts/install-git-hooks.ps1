$ErrorActionPreference = "Stop"

$root = (git rev-parse --show-toplevel 2>$null)
if (-not $root) {
  $root = (Get-Location).Path
}

git config core.hooksPath "$root/.githooks"
Write-Host "Configured core.hooksPath=$root/.githooks"

