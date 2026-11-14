[CmdletBinding()]
param(
  [switch]$SkipTests,
  [switch]$DryRun,
  [switch]$NoAgentIntegration
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if (-not $root) { $root = (Get-Location).Path }
$home_ = Join-Path $env:LOCALAPPDATA 'CyberpunkForge'
$binDir = Join-Path $home_ 'bin'
$launcher = Join-Path $binDir 'cpforge.cmd'
$skillSrc = Join-Path $root 'skills\cyberpunk-forge'
$skillTargets = @(
  (Join-Path $env:USERPROFILE '.claude\skills'),
  (Join-Path $env:USERPROFILE '.agents\skills')
) | Where-Object { Test-Path $_ }

Write-Host '== Cyberpunk Forge install =='
Write-Host "root: $root"
if ($DryRun) {
  Write-Host 'Dry run: nothing will be changed.'
  Write-Host "  venv:     $root\.venv (pip install -e this folder)"
  Write-Host "  launcher: $launcher (added to the user PATH)"
  if ($NoAgentIntegration) { Write-Host '  agent skill: skipped (-NoAgentIntegration)' }
  else { foreach ($t in $skillTargets) { Write-Host "  agent skill: $t\cyberpunk-forge (previous copy backed up)" } }
  return
}

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw 'Python 3.10+ was not found on PATH. Install it from python.org and run this again.' }
& $py.Source -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10 or newer is required.' }

$venv = Join-Path $root '.venv'
$vpy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $vpy)) {
  & $py.Source -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw "venv creation failed ($LASTEXITCODE)" }
}
& $vpy -m pip install --disable-pip-version-check --quiet -e $root
if ($LASTEXITCODE -ne 0) { throw "pip install failed ($LASTEXITCODE)" }

if (-not $SkipTests) {
  & $vpy (Join-Path $root 'tests\run_tests.py')
  if ($LASTEXITCODE -ne 0) { throw "tests failed ($LASTEXITCODE)" }
}

# Launcher so 'cpforge' works from any folder; it names this checkout's venv.
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$lines = @(
  '@echo off',
  'setlocal EnableExtensions DisableDelayedExpansion',
  ('if not exist "{0}" (' -f $vpy),
  '  echo Cyberpunk Forge is no longer in the folder this launcher points to. 1>&2',
  '  echo Run Install.ps1 from its current folder to repair the launcher. 1>&2',
  '  exit /b 3',
  ')',
  ('"{0}" -m cpforge %*' -f $vpy),
  'exit /b %ERRORLEVEL%'
)
[IO.File]::WriteAllText($launcher, (($lines -join "`r`n") + "`r`n"), (New-Object Text.UTF8Encoding($false)))
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $userPath) { $userPath = '' }
if (($userPath -split ';') -notcontains $binDir) {
  [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $binDir), 'User')
  Write-Host "added $binDir to the user PATH; open a new terminal to use 'cpforge'"
}

if (-not $NoAgentIntegration) {
  foreach ($t in $skillTargets) {
    $dest = Join-Path $t 'cyberpunk-forge'
    if (Test-Path $dest) {
      $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
      $backup = Join-Path $home_ ("skill-backup\" + (Split-Path $t -Parent | Split-Path -Leaf) + "-$stamp")
      New-Item -ItemType Directory -Force -Path $backup | Out-Null
      Copy-Item -Recurse -Force $dest $backup
      Remove-Item -Recurse -Force $dest
    }
    Copy-Item -Recurse $skillSrc $dest
    Write-Host "agent skill installed: $dest"
  }
}

& $vpy -m cpforge doctor | Out-Null
Write-Host ''
Write-Host 'Done. Next: cpforge doctor, then cpforge index'
