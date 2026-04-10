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

Write-Host ""
Write-Host "==> Engine ownership guardrails"

Assert-NoMatch "legacy-db" $engineFiles "Legacy engine fallback alias detected."
Assert-NoMatch "legacy_db" $engineFiles "Legacy engine fallback alias detected."
Assert-NoMatch "run_repository_fallback" $engineFiles "Silent engine fallback log detected."
Assert-NoMatch 'normalizeRunStateMode("postgres") = %s, want dual-write' @($engineTests) "Legacy postgres alias expectation detected in engine tests."

Assert-HasMatch "ENGINE_ALLOW_IN_MEMORY_MODE" @($engineMain) "Missing ENGINE_ALLOW_IN_MEMORY_MODE safeguard in engine startup."
Assert-HasMatch "control-plane-http" @($engineMain) "Missing explicit control-plane-http enforcement in engine startup."
