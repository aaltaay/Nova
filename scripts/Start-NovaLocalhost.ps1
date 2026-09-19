#Requires -Version 5.1
<#
.SYNOPSIS
  Start Nova localhost stack (API :8000 + Vite :5173) if not already up.
#>
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'NovaLocalhost.Common.ps1')
$ok = Start-NovaLocalhostStack
$status = Get-NovaLocalhostStatus
Write-Host ("Nova localhost: api={0} vite={1}" -f $status.api, $status.vite)
if (-not $ok) { exit 1 }
