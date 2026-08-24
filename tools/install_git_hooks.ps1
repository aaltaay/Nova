# Point this repo at versioned hooks in .githooks/ (commit-count semver bump).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
git config core.hooksPath .githooks
Write-Host "core.hooksPath -> .githooks"
Write-Host "Run: py -3 tools/bump_version.py --sync   # align VERSION to current HEAD"
Write-Host "Next commit will auto-bump to 0.1.<commit-count>"
