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

function Get-BashCommandSetup {
  $commands = @("go", "gofmt", "rg", "node", "npm", "npx", "python", "uv")
  $lines = New-Object System.Collections.Generic.List[string]
  $resolvedCommands = New-Object System.Collections.Generic.List[string]

  foreach ($command in $commands) {
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

$bashRoot = Convert-ToGitBashPath $root
$bashCommandSetup = Get-BashCommandSetup
$tmpScriptName = ".tmp-$([guid]::NewGuid().ToString('N')).sh"
$tmpScriptPath = Join-Path $root $tmpScriptName

Push-Location $root
try {
  Ensure-DockerComposeServices

  $bashLines = @(
    "#!/usr/bin/env bash",
    "set -euo pipefail"
  )
  if ($bashCommandSetup.Count -gt 0) {
    $bashLines += $bashCommandSetup
  }
  $bashLines += "cd '$bashRoot'"
  $bashLines += "bash '$ScriptRelativePath'"

  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($tmpScriptPath, (($bashLines -join "`n") + "`n"), $utf8NoBom)

  & bash -lc "cd '$bashRoot' && source '$tmpScriptName'"
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed: bash -lc `"cd '$bashRoot' && source '$tmpScriptName'`""
  }
} finally {
  Remove-Item $tmpScriptPath -ErrorAction SilentlyContinue
  Pop-Location
}
