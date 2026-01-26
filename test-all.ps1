param(
  [switch]$Fast,
  [switch]$SkipE2E
)

$ErrorActionPreference = "Stop"

function Invoke-Exec {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$WorkDir,
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string[]]$Args
  )

  Push-Location $WorkDir
  try {
    Write-Host ""
    Write-Host ("=== {0} ===" -f $Name)
    & $Exe @Args
    $code = $LASTEXITCODE
    if ($code -ne 0) {
      throw ("{0} failed (exit {1})" -f $Name, $code)
    }
  } finally {
    Pop-Location
  }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Invoke-Exec -Name "Engine (Go) tests" -WorkDir (Join-Path $root "engine") -Exe "go" -Args @("test", "./...")

Push-Location (Join-Path $root "backend")
try {
  python -c "import pytest_asyncio" *> $null
} catch {
  Write-Host ""
  Write-Host "=== Backend deps ==="
  Write-Host "Installing missing test dependency: pytest-asyncio"
  python -m pip install pytest-asyncio
}
Pop-Location

function Set-ScopedEnvVar {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [AllowNull()][string]$Value
  )

  if ($null -eq $Value -or $Value -eq "") {
    Remove-Item "env:$Name" -ErrorAction SilentlyContinue
  } else {
    Set-Item "env:$Name" -Value $Value
  }
}

$old_USE_SQLITE = $env:USE_SQLITE
$old_SQLITE_DB_PATH = $env:SQLITE_DB_PATH
$old_USE_IN_MEMORY_CHANNEL_LAYER = $env:USE_IN_MEMORY_CHANNEL_LAYER

try {
  # Ensure backend tests don't touch the tracked dev DB at backend/db.sqlite3.
  Set-ScopedEnvVar -Name "USE_SQLITE" -Value "true"
  Set-ScopedEnvVar -Name "USE_IN_MEMORY_CHANNEL_LAYER" -Value "true"
  Set-ScopedEnvVar -Name "SQLITE_DB_PATH" -Value (Join-Path $env:TEMP "forgegraph-test-db.sqlite3")

  if ($Fast) {
    Invoke-Exec `
      -Name "Backend (Django) tests [fast]" `
      -WorkDir (Join-Path $root "backend") `
      -Exe "python" `
      -Args @("-m", "pytest", "tests/integration/adapters/test_run_api.py", "tests/integration/adapters/test_graph_api.py", "-q")
  } else {
    Invoke-Exec -Name "Backend (Django) tests" -WorkDir (Join-Path $root "backend") -Exe "python" -Args @("-m", "pytest")
  }
} finally {
  Set-ScopedEnvVar -Name "USE_SQLITE" -Value $old_USE_SQLITE
  Set-ScopedEnvVar -Name "USE_IN_MEMORY_CHANNEL_LAYER" -Value $old_USE_IN_MEMORY_CHANNEL_LAYER
  Set-ScopedEnvVar -Name "SQLITE_DB_PATH" -Value $old_SQLITE_DB_PATH
}

Invoke-Exec -Name "Frontend (Jest) tests" -WorkDir (Join-Path $root "frontend") -Exe "npm" -Args @("test")

if (-not $SkipE2E) {
  Invoke-Exec -Name "Frontend (Playwright) e2e tests" -WorkDir (Join-Path $root "frontend") -Exe "npm" -Args @("run", "test:e2e")
}
