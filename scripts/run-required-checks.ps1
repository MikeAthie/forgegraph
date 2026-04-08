$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message"
}

function Test-Command {
  param([string]$Name)
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Missing required command: $Name"
  }
}

function Test-TcpService {
  param(
    [string]$HostName,
    [int]$Port,
    [string]$Label
  )

  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $async = $client.BeginConnect($HostName, $Port, $null, $null)
    if (-not $async.AsyncWaitHandle.WaitOne(2000)) {
      throw "$Label is not reachable at ${HostName}:${Port}"
    }
    $client.EndConnect($async) | Out-Null
  } catch {
    throw "$Label is not reachable at ${HostName}:${Port}. Start the local dependencies before pushing."
  } finally {
    $client.Dispose()
  }
}

function Invoke-External {
  param(
    [string]$WorkingDirectory,
    [string[]]$Command
  )

  Push-Location $WorkingDirectory
  try {
    $executable = $Command[0]
    $arguments = @()
    if ($Command.Length -gt 1) {
      $arguments = $Command[1..($Command.Length - 1)]
    }
    & $executable @arguments
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed: $($Command -join ' ')"
    }
  } finally {
    Pop-Location
  }
}

function Invoke-GoFmtCheck {
  param([string]$WorkingDirectory)

  Push-Location $WorkingDirectory
  try {
    $unformatted = & gofmt -l .
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed: gofmt -l ."
    }
    if ($unformatted) {
      Write-Error "gofmt required on:"
      $unformatted | ForEach-Object { Write-Error $_ }
      throw "Engine formatting check failed."
    }
  } finally {
    Pop-Location
  }
}

function Set-BackendEnvDefaults {
  $defaults = @{
    DB_HOST = "localhost"
    DB_PORT = "5433"
    DB_NAME = "forgegraph"
    DB_USER = "forgegraph"
    DB_PASSWORD = "forgegraph_secret"
    REDIS_HOST = "localhost"
    REDIS_PORT = "6379"
    SECRET_KEY = "ci-not-a-secret"
    DEBUG = "False"
    DJANGO_SETTINGS_MODULE = "config.settings"
    ALLOWED_HOSTS = "localhost"
    ENCRYPTION_KEY = "31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI="
    SECURE_SSL_REDIRECT = "false"
  }

  foreach ($pair in $defaults.GetEnumerator()) {
    $current = [System.Environment]::GetEnvironmentVariable($pair.Key)
    if ([string]::IsNullOrWhiteSpace($current)) {
      Set-Item -Path "Env:$($pair.Key)" -Value $pair.Value
    }
  }
}

function Invoke-BackendChecks {
  $backendDir = Join-Path $root "backend"
  Test-Command uv
  Set-BackendEnvDefaults
  Test-TcpService $env:DB_HOST ([int]$env:DB_PORT) "Postgres"
  Test-TcpService $env:REDIS_HOST ([int]$env:REDIS_PORT) "Redis"

  Write-Step "Backend format"
  Invoke-External $backendDir @("uv", "run", "ruff", "format", "--check", ".")

  Write-Step "Backend lint"
  Invoke-External $backendDir @("uv", "run", "ruff", "check", ".")

  Write-Step "Backend typecheck"
  Invoke-External $backendDir @("uv", "run", "mypy", ".")

  Write-Step "Backend tests"
  Invoke-External $backendDir @("uv", "run", "pytest")
}

function Invoke-EngineChecks {
  $engineDir = Join-Path $root "engine"
  Test-Command go

  Write-Step "Engine gofmt"
  Invoke-GoFmtCheck $engineDir

  Write-Step "Engine ownership guardrails"
  Invoke-External $root @("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "scripts\check-engine-ownership.ps1"))

  Write-Step "Engine vet"
  Invoke-External $engineDir @("go", "vet", "./...")

  Write-Step "Engine tests"
  Invoke-External $engineDir @("go", "test", "./...")

  Write-Step "Engine race tests"
  $previous = $env:CGO_ENABLED
  try {
    $env:CGO_ENABLED = "1"
    Invoke-External $engineDir @("go", "test", "-race", "./...")
  } finally {
    $env:CGO_ENABLED = $previous
  }
}

function Invoke-FrontendChecks {
  $frontendDir = Join-Path $root "frontend"
  Test-Command npm

  Write-Step "Frontend format"
  Invoke-External $frontendDir @("npm", "run", "format:check")

  Write-Step "Frontend lint"
  Invoke-External $frontendDir @("npm", "run", "lint")

  Write-Step "Frontend unit tests"
  Invoke-External $frontendDir @("npm", "test")

  Write-Step "Frontend build"
  Invoke-External $frontendDir @("npm", "run", "build")
}

function Invoke-LaunchQABackend {
  $backendDir = Join-Path $root "backend"
  Test-Command uv
  Set-BackendEnvDefaults
  Test-TcpService $env:DB_HOST ([int]$env:DB_PORT) "Postgres"
  Test-TcpService $env:REDIS_HOST ([int]$env:REDIS_PORT) "Redis"

  Write-Step "Launch QA backend"
  Invoke-External $backendDir @(
    "uv", "run", "pytest",
    "tests/integration/adapters/test_run_api.py",
    "tests/integration/adapters/test_run_history_security_api.py",
    "tests/integration/adapters/test_credentials_security_api.py",
    "tests/integration/adapters/test_audit_logs_api.py",
    "tests/integration/adapters/test_metrics_api.py",
    "tests/unit/services/test_redaction.py",
    "-q"
  )
}

function Invoke-LaunchQAEngine {
  $engineDir = Join-Path $root "engine"
  Test-Command go

  Write-Step "Launch QA engine"
  Invoke-External $engineDir @("go", "test", "./application/usecase", "-run", "Scheduler|OnError|RetryAfter|NonRetryable", "-count=1")
  Invoke-External $engineDir @("go", "test", "./adapter/executor", "-run", "HTTPExecutor|ToolExecutor|PromptExecutor", "-count=1")
  $previous = $env:CGO_ENABLED
  try {
    $env:CGO_ENABLED = "1"
    Invoke-External $engineDir @("go", "test", "-race", "./application/usecase", "./adapter/executor", "-count=1")
  } finally {
    $env:CGO_ENABLED = $previous
  }
}

function Invoke-LaunchQAFrontend {
  $frontendDir = Join-Path $root "frontend"
  Test-Command npx

  Write-Step "Launch QA frontend"
  Invoke-External $frontendDir @(
    "npx", "jest", "--runInBand",
    "__tests__/components/graph-editor/GraphEditor.test.tsx",
    "__tests__/components/graph-editor/wizard/AgentWizard.test.tsx",
    "__tests__/components/graph-editor/NodeConfigDialog.test.tsx"
  )
}

Invoke-BackendChecks
Invoke-EngineChecks
Invoke-FrontendChecks
Invoke-LaunchQABackend
Invoke-LaunchQAEngine
Invoke-LaunchQAFrontend
