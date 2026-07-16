<#
.SYNOPSIS
  Opens Warrior Trading in a headed Chromium session with a persistent local
  profile so authenticated navigation survives restarts.

.DESCRIPTION
  Profile path (outside the repo):
    %LOCALAPPDATA%\Nova\browser-profiles\warrior-site

  Credentials are never stored by this script. First launch: log in manually
  (or let an agent fill the form once). Later launches reuse the profile.

.PARAMETER Url
  Landing URL. Defaults to the member dashboard.

.PARAMETER Session
  agent-browser session name (isolates from other agent browsers).
#>
param(
    [string]$Url = "https://www.warriortrading.com/dashboard/",
    [string]$Session = "warrior-site"
)

$ErrorActionPreference = "Stop"

$profileDir = Join-Path $env:LOCALAPPDATA "Nova\browser-profiles\warrior-site"
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

$tmpDir = Join-Path (Split-Path -Parent $PSScriptRoot) ".tmp\warrior-site-map"
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null

Write-Host "Warrior profile: $profileDir"
Write-Host "Opening: $Url"
Write-Host "Session: $Session"
Write-Host "Screenshots/scratch: $tmpDir"
Write-Host ""
Write-Host "First login: complete email/password + any CAPTCHA/2FA in the window."
Write-Host "Later runs: profile should already be authenticated."

npx --yes agent-browser@latest --session $Session --headed --profile $profileDir open $Url
