[CmdletBinding()]
param(
  [switch]$RemoveCache,
  [switch]$KeepSkill
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$home_ = Join-Path $env:LOCALAPPDATA 'CyberpunkForge'
$binDir = Join-Path $home_ 'bin'

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath) {
  $parts = $userPath -split ';' | Where-Object { $_ -and ($_ -ne $binDir) }
  [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
}
if (Test-Path $binDir) { Remove-Item -Recurse -Force $binDir }
Write-Host 'launcher and PATH entry removed'

if (-not $KeepSkill) {
  foreach ($t in @((Join-Path $env:USERPROFILE '.claude\skills\cyberpunk-forge'), (Join-Path $env:USERPROFILE '.agents\skills\cyberpunk-forge'))) {
    if ((Test-Path (Join-Path $t 'SKILL.md')) -and ((Get-Content (Join-Path $t 'SKILL.md') -Raw) -match 'name: cyberpunk-forge')) {
      Remove-Item -Recurse -Force $t
      Write-Host "agent skill removed: $t"
    }
  }
}

if ($RemoveCache -and (Test-Path $home_)) {
  Remove-Item -Recurse -Force $home_
  Write-Host "cache removed: $home_"
} else {
  Write-Host "kept index, logs and build dependencies in $home_ (use -RemoveCache to delete)"
}
$venv = Join-Path $root '.venv'
if (Test-Path $venv) { Write-Host "the virtual environment stays in $venv; delete the folder to remove it" }
