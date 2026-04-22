param(
  [Parameter(Mandatory = $true)][string]$ScriptRelativePath
)

$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent

function Find-DockerDesktopPath {
  $candidates = @(
    "C:\Program Files\Docker\Docker\Docker Desktop.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker\Docker Desktop.exe")
  )

  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path $candidate)) {
      return $candidate
    }
  }

  return $null
}

function Convert-ToGitBashPath {
  param([string]$Path)

  if ($Path -match '^[A-Za-z]:\\') {
    $drive = $Path.Substring(0, 1).ToLowerInvariant()
    $tail = $Path.Substring(2) -replace '\\', '/'
    return "/mnt/$drive$tail"
  }

  return ($Path -replace '\\', '/')
}

function Resolve-CommandPath {
  param([string]$Command)

  $candidates = @(Get-Command $Command -All -ErrorAction SilentlyContinue)
  foreach ($candidate in $candidates) {
    $paths = @($candidate.Path, $candidate.Source, $candidate.Definition) |
      Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) }

    if (-not $paths) {
      continue
    }

    $resolvedPath = (Resolve-Path -LiteralPath $paths[0]).Path
    $extension = [System.IO.Path]::GetExtension($resolvedPath).ToLowerInvariant()
    if ($extension -ne ".ps1") {
      return $resolvedPath
    }
  }

  return $null
}

function Resolve-NodeJsCli {
  param([Parameter(Mandatory = $true)][string]$CliName)

  $nodePath = Resolve-CommandPath "node"
  if (-not $nodePath) {
    return $null
  }

  $nodeDir = Split-Path -Parent $nodePath
  $cliFile = switch ($CliName) {
    "npm" { "npm-cli.js" }
    "npx" { "npx-cli.js" }
    default { return $null }
  }

  $cliPath = Join-Path $nodeDir "node_modules\npm\bin\$cliFile"
  if (-not (Test-Path -LiteralPath $cliPath -PathType Leaf)) {
    return $null
  }

  return @{
    NodePath = $nodePath
    CliPath  = (Resolve-Path -LiteralPath $cliPath).Path
  }
}

function Test-BashCommandAvailable {
  param([Parameter(Mandatory = $true)][string]$Command)

  & bash -lc "command -v $Command >/dev/null 2>&1"
  return $LASTEXITCODE -eq 0
}

function Test-BashNodeToolchainAvailable {
  & bash -lc "npm --version >/dev/null 2>&1 && npx --version >/dev/null 2>&1"
  return $LASTEXITCODE -eq 0
}

function Get-BashCommandSetup {
  $commands = @("go", "gofmt", "rg", "node", "npm", "npx", "python", "uv")
  $lines = New-Object System.Collections.Generic.List[string]
  $resolvedCommands = New-Object System.Collections.Generic.List[string]

  foreach ($command in $commands) {
    if (Test-BashCommandAvailable $command) {
      continue
    }

    if ($command -in @("npm", "npx")) {
      $nodeCli = Resolve-NodeJsCli $command
      if ($nodeCli) {
        $bashNodePath = Convert-ToGitBashPath $nodeCli.NodePath
        $bashCliPath = ($nodeCli.CliPath -replace '\\', '/')
        $lines.Add(('{0}() {{ ''{1}'' ''{2}'' "$@"; }}' -f $command, $bashNodePath, $bashCliPath))
        $resolvedCommands.Add($command)
        continue
      }
    }

    $resolvedPath = Resolve-CommandPath $command
    if (-not $resolvedPath) {
      continue
    }

    $bashPath = Convert-ToGitBashPath $resolvedPath
    $lines.Add(('{0}() {{ ''{1}'' "$@"; }}' -f $command, $bashPath))
    $resolvedCommands.Add($command)
  }

  if ($resolvedCommands.Count -gt 0) {
    $lines.Add("export -f $($resolvedCommands -join ' ')")
  }

  return $lines
}

function Write-Section {
  param([Parameter(Mandatory = $true)][string]$Title)

  Write-Host ""
  Write-Host "==> $Title"
}

function Invoke-BashRepoScript {
  param([Parameter(Mandatory = $true)][string]$RelativePath)

  $bashRoot = Convert-ToGitBashPath $root
  $bashCommandSetup = Get-BashCommandSetup
  $tmpScriptName = ".tmp-$([guid]::NewGuid().ToString('N')).sh"
  $tmpScriptPath = Join-Path $root $tmpScriptName

  try {
    $bashLines = @(
      "#!/usr/bin/env bash",
      "set -euo pipefail"
    )
    if ($bashCommandSetup.Count -gt 0) {
      $bashLines += $bashCommandSetup
    }
    $bashLines += "cd '$bashRoot'"
    $bashLines += "bash '$RelativePath'"

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($tmpScriptPath, (($bashLines -join "`n") + "`n"), $utf8NoBom)

    & bash -lc "cd '$bashRoot' && source '$tmpScriptName'"
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed: bash -lc `"cd '$bashRoot' && source '$tmpScriptName'`""
    }
  } finally {
    Remove-Item $tmpScriptPath -ErrorAction SilentlyContinue
  }
}

function Invoke-FrontendLaunchQa {
  $npxPath = Resolve-CommandPath "npx"
  if (-not $npxPath) {
    throw "Missing required command: npx"
  }

  Push-Location (Join-Path $root "frontend")
  try {
    Write-Section "Launch QA frontend"
    & $npxPath "jest" "--runInBand" `
      "__tests__/components/graph-editor/GraphEditor.test.tsx" `
      "__tests__/components/graph-editor/wizard/AgentWizard.test.tsx" `
      "__tests__/components/graph-editor/NodeConfigDialog.test.tsx"
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed: npx jest --runInBand ..."
    }
  } finally {
    Pop-Location
  }
}

function Invoke-FrontendRequiredChecks {
  $npmPath = Resolve-CommandPath "npm"
  if (-not $npmPath) {
    throw "Missing required command: npm"
  }

  $oldJestCacheDir = $env:JEST_CACHE_DIR
  $env:JEST_CACHE_DIR = Join-Path $root "frontend\.jest-cache"

  Push-Location (Join-Path $root "frontend")
  try {
    Write-Section "Frontend format"
    & $npmPath "run" "format:check"
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed: npm run format:check"
    }

    Write-Section "Frontend lint"
    & $npmPath "run" "lint"
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed: npm run lint"
    }

    Write-Section "Frontend unit tests"
    & $npmPath "test"
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed: npm test"
    }

    Write-Section "Frontend build"
    & $npmPath "run" "build"
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed: npm run build"
    }
  } finally {
    if ($null -ne $oldJestCacheDir) {
      $env:JEST_CACHE_DIR = $oldJestCacheDir
    } else {
      Remove-Item Env:\JEST_CACHE_DIR -ErrorAction SilentlyContinue
    }
    Pop-Location
  }
}

function Test-DockerDaemonAvailable {
  $startInfo = New-Object System.Diagnostics.ProcessStartInfo
  $startInfo.FileName = "docker"
  $startInfo.Arguments = "info"
  $startInfo.RedirectStandardOutput = $true
  $startInfo.RedirectStandardError = $true
  $startInfo.UseShellExecute = $false
  $startInfo.CreateNoWindow = $true

  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $startInfo

  try {
    [void]$process.Start()
    [void]$process.StandardOutput.ReadToEnd()
    [void]$process.StandardError.ReadToEnd()
    $process.WaitForExit()
    return $process.ExitCode -eq 0
  } finally {
    $process.Dispose()
  }
}

function Wait-ForDockerDaemon {
  param([int]$TimeoutSeconds = 120)

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-DockerDaemonAvailable) {
      return
    }
    Start-Sleep -Seconds 2
  }

  throw "Docker daemon did not become ready within $TimeoutSeconds seconds."
}

function Ensure-DockerComposeServices {
  Push-Location $root
  try {
    if (-not (Test-DockerDaemonAvailable)) {
      $dockerDesktop = Find-DockerDesktopPath
      if (-not $dockerDesktop) {
        throw "Docker is installed but the daemon is unavailable, and Docker Desktop.exe could not be found."
      }

      Write-Host ""
      Write-Host "==> Starting Docker Desktop"
      Start-Process -FilePath $dockerDesktop | Out-Null
      Wait-ForDockerDaemon
    }

    Write-Host ""
    Write-Host "==> Starting local dependencies"
    & docker compose up -d postgres redis
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed: docker compose up -d postgres redis"
    }
  } finally {
    Pop-Location
  }
}

if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
  throw "Missing required command: bash"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Missing required command: docker"
}

if (-not (Test-Path (Join-Path $root $ScriptRelativePath))) {
  throw "Missing required script: $ScriptRelativePath"
}

Push-Location $root
try {
  Ensure-DockerComposeServices

  $hasBashNodeToolchain = Test-BashNodeToolchainAvailable
  if ($ScriptRelativePath -eq "scripts/ci/run_required_checks.sh" -and -not $hasBashNodeToolchain) {
    Invoke-BashRepoScript "scripts/ci/run_backend_checks.sh"
    Invoke-BashRepoScript "scripts/ci/run_engine_checks.sh"
    Invoke-FrontendRequiredChecks
    Invoke-BashRepoScript "scripts/ci/run_launch_qa_backend.sh"
    Invoke-BashRepoScript "scripts/ci/run_launch_qa_engine.sh"
    Invoke-FrontendLaunchQa
  } else {
    Invoke-BashRepoScript $ScriptRelativePath
  }
} finally {
  Pop-Location
}
