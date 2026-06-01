$ErrorActionPreference = "Stop"

$repoRoot = Split-Path $PSScriptRoot -Parent

function Assert-NoMatch {
  param(
    [string]$Pattern,
    [string[]]$Paths,
    [string]$Message
  )

  if (-not $Paths -or $Paths.Count -eq 0) {
    throw "No files provided for pattern check: $Message"
  }

  $matches = Select-String -Path $Paths -Pattern $Pattern -SimpleMatch
  if ($matches) {
    $matches | ForEach-Object { Write-Error $_ }
    throw $Message
  }
}

function Assert-HasMatch {
  param(
    [string]$Pattern,
    [string[]]$Paths,
    [string]$Message
  )

  if (-not $Paths -or $Paths.Count -eq 0) {
    throw "No files provided for pattern check: $Message"
  }

  $matches = Select-String -Path $Paths -Pattern $Pattern -SimpleMatch
  if (-not $matches) {
    throw $Message
  }
}

$engineMain = Join-Path $repoRoot "engine\main.go"
$engineTests = Join-Path $repoRoot "engine\main_test.go"
$engineFiles = Get-ChildItem -Path (Join-Path $repoRoot "engine") -Recurse -File | Select-Object -ExpandProperty FullName
$excludedGuardTests = @("architecture_enforcement_test.go", "statelessness_guard_test.go")
$engineGoFiles = Get-ChildItem -Path (Join-Path $repoRoot "engine") -Recurse -Filter *.go -File |
  Where-Object { $excludedGuardTests -notcontains $_.Name } |
  Select-Object -ExpandProperty FullName
$runtimeInvariants = Join-Path $repoRoot "docs\architecture\runtime-invariants.md"

Write-Host ""
Write-Host "==> Engine ownership guardrails"

if (-not (Test-Path $runtimeInvariants)) {
  throw "Missing canonical runtime contract: docs/architecture/runtime-invariants.md"
}

Assert-NoMatch "legacy-db" $engineFiles "Legacy engine fallback alias detected."
Assert-NoMatch "legacy_db" $engineFiles "Legacy engine fallback alias detected."
Assert-NoMatch "run_repository_fallback" $engineFiles "Silent engine fallback log detected."
Assert-NoMatch '"database/sql"' $engineGoFiles "Direct database persistence import detected in engine Go source."
Assert-NoMatch "gorm.io" $engineGoFiles "Direct database persistence import detected in engine Go source."
Assert-NoMatch "github.com/lib/pq" $engineGoFiles "Direct database persistence import detected in engine Go source."
Assert-NoMatch "github.com/jackc/pgx" $engineGoFiles "Direct database persistence import detected in engine Go source."
Assert-NoMatch "github.com/jmoiron/sqlx" $engineGoFiles "Direct database persistence import detected in engine Go source."
Assert-NoMatch 'normalizeRunStateMode("postgres") = %s, want dual-write' @($engineTests) "Legacy postgres alias expectation detected in engine tests."

Assert-HasMatch "ENGINE_ALLOW_IN_MEMORY_MODE" @($engineMain) "Missing ENGINE_ALLOW_IN_MEMORY_MODE safeguard in engine startup."
Assert-HasMatch "control-plane-http" @($engineMain) "Missing explicit control-plane-http enforcement in engine startup."

$durableMemoryPattern = "RedisMemoryStore|NewRedisMemoryStore|StoreSummary\(|StoreFacts\(|keyPatternMemory"

$durableMemoryMatches = Select-String -Path $engineGoFiles -Pattern $durableMemoryPattern |
  Select-Object -ExpandProperty Path -Unique

if ($durableMemoryMatches) {
  $durableMemoryMatches | ForEach-Object { Write-Error "Engine durable product-memory persistence detected: $_" }
  throw "Engine product memory/summaries/facts must move through backend-owned memory intents only."
}

$manifest = Join-Path $repoRoot "scripts\ci\engine_durable_memory_temporary_violations.tsv"
if (Test-Path $manifest) {
  throw "Temporary engine durable memory exception manifest must not be reintroduced."
}
