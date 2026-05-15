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

function Import-DotEnv {
  param(
    [Parameter(Mandatory = $true)][string]$Path
  )

  if (-not (Test-Path $Path)) {
    return
  }

  foreach ($line in Get-Content $Path) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) {
      continue
    }

    $separatorIndex = $trimmed.IndexOf("=")
    if ($separatorIndex -lt 1) {
      continue
    }

    $name = $trimmed.Substring(0, $separatorIndex).Trim()
    $value = $trimmed.Substring($separatorIndex + 1).Trim().Trim("'`"")
    if (-not (Test-Path "env:$name")) {
      Set-Item "env:$name" -Value $value
    }
  }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Import-DotEnv -Path (Join-Path $root ".env")

Invoke-Exec -Name "Engine (Go) tests" -WorkDir (Join-Path $root "engine") -Exe "go" -Args @("test", "./...")

if (-not $Fast) {
  Write-Host ""
  Write-Host "=== Backend DB preflight ==="
  $postgresRunning = docker ps --format "{{.Names}}" | Select-String -SimpleMatch "forgegraph-postgres"
  if (-not $postgresRunning) {
    Write-Host "Starting postgres container..."
    docker compose up -d postgres
  }
  $redisRunning = docker ps --format "{{.Names}}" | Select-String -SimpleMatch "forgegraph-redis"
  if (-not $redisRunning) {
    Write-Host "Starting redis container..."
    docker compose up -d redis
  }
}

Push-Location (Join-Path $root "backend")
try {
  python -c "import pytest_asyncio" *> $null
} catch {
  Write-Host ""
  Write-Host "=== Backend deps ==="
  Write-Host "Installing missing test dependency: pytest-asyncio"
  python -m pip install --user pytest-asyncio
}
try {
  python -c "from grpc_health.v1 import health" *> $null
} catch {
  Write-Host ""
  Write-Host "=== Backend deps ==="
  Write-Host "Installing missing dependency: grpcio-health-checking"
  python -m pip install --user grpcio-health-checking
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
$old_DB_HOST = $env:DB_HOST
$old_DB_PORT = $env:DB_PORT
$old_DB_NAME = $env:DB_NAME
$old_DB_USER = $env:DB_USER
$old_DB_PASSWORD = $env:DB_PASSWORD
$old_TESTING = $env:TESTING
$old_SECRET_KEY = $env:SECRET_KEY
$old_ALLOWED_HOSTS = $env:ALLOWED_HOSTS
$old_ENCRYPTION_KEY = $env:ENCRYPTION_KEY
$old_SECURE_SSL_REDIRECT = $env:SECURE_SSL_REDIRECT

try {
  # Use Postgres for backend tests to match production parity.
  Set-ScopedEnvVar -Name "TESTING" -Value ($env:TESTING ? $env:TESTING : "true")
  Set-ScopedEnvVar -Name "SECRET_KEY" -Value ($env:SECRET_KEY ? $env:SECRET_KEY : "django-insecure-test-key-change-in-production")
  Set-ScopedEnvVar -Name "ALLOWED_HOSTS" -Value ($env:ALLOWED_HOSTS ? $env:ALLOWED_HOSTS : "localhost,127.0.0.1,testserver")
  Set-ScopedEnvVar -Name "ENCRYPTION_KEY" -Value ($env:ENCRYPTION_KEY ? $env:ENCRYPTION_KEY : "31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI=")
  Set-ScopedEnvVar -Name "SECURE_SSL_REDIRECT" -Value ($env:SECURE_SSL_REDIRECT ? $env:SECURE_SSL_REDIRECT : "false")
  Set-ScopedEnvVar -Name "USE_SQLITE" -Value "false"
  Set-ScopedEnvVar -Name "USE_IN_MEMORY_CHANNEL_LAYER" -Value "true"
  Set-ScopedEnvVar -Name "SQLITE_DB_PATH" -Value ""
  Set-ScopedEnvVar -Name "DB_HOST" -Value "localhost"
  Set-ScopedEnvVar -Name "DB_PORT" -Value "5433"
  Set-ScopedEnvVar -Name "DB_NAME" -Value "forgegraph"
  Set-ScopedEnvVar -Name "DB_USER" -Value "forgegraph"
  Set-ScopedEnvVar -Name "DB_PASSWORD" -Value "forgegraph_secret"

  if ($Fast) {
    Invoke-Exec `
      -Name "Backend (Django) tests [fast]" `
      -WorkDir (Join-Path $root "backend") `
      -Exe "python" `
      -Args @("-m", "pytest", "tests/integration/adapters/runs", "tests/integration/adapters/test_graph_api.py", "-q")
  } else {
    Invoke-Exec -Name "Backend (Django) tests" -WorkDir (Join-Path $root "backend") -Exe "python" -Args @("-m", "pytest")
  }
} finally {
  Set-ScopedEnvVar -Name "TESTING" -Value $old_TESTING
  Set-ScopedEnvVar -Name "SECRET_KEY" -Value $old_SECRET_KEY
  Set-ScopedEnvVar -Name "ALLOWED_HOSTS" -Value $old_ALLOWED_HOSTS
  Set-ScopedEnvVar -Name "ENCRYPTION_KEY" -Value $old_ENCRYPTION_KEY
  Set-ScopedEnvVar -Name "SECURE_SSL_REDIRECT" -Value $old_SECURE_SSL_REDIRECT
  Set-ScopedEnvVar -Name "USE_SQLITE" -Value $old_USE_SQLITE
  Set-ScopedEnvVar -Name "USE_IN_MEMORY_CHANNEL_LAYER" -Value $old_USE_IN_MEMORY_CHANNEL_LAYER
  Set-ScopedEnvVar -Name "SQLITE_DB_PATH" -Value $old_SQLITE_DB_PATH
  Set-ScopedEnvVar -Name "DB_HOST" -Value $old_DB_HOST
  Set-ScopedEnvVar -Name "DB_PORT" -Value $old_DB_PORT
  Set-ScopedEnvVar -Name "DB_NAME" -Value $old_DB_NAME
  Set-ScopedEnvVar -Name "DB_USER" -Value $old_DB_USER
  Set-ScopedEnvVar -Name "DB_PASSWORD" -Value $old_DB_PASSWORD
}

Invoke-Exec -Name "Frontend (Jest) tests" -WorkDir (Join-Path $root "frontend") -Exe "npm" -Args @("test")

if (-not $SkipE2E) {
  Invoke-Exec -Name "Frontend (Playwright) e2e tests" -WorkDir (Join-Path $root "frontend") -Exe "npm" -Args @("run", "test:e2e")
}
