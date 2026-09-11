# Point this repo at versioned hooks in .githooks/ (commit-count vNNN bump).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
git config core.hooksPath .githooks
Write-Host "core.hooksPath -> .githooks"
Write-Host "Run: py -3 tools/bump_version.py --sync   # align VERSION to current HEAD"
Write-Host "Next commit will auto-bump VERSION to vNNN and package.json to 0.1.N"
