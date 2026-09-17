# Standing nova-brain client -- localhost bot API only.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
Set-Location $backend
if (-not $env:NOVA_API_BASE) { $env:NOVA_API_BASE = "http://127.0.0.1:8000" }
if (-not $env:NOVA_BRAIN_SESSION_ID) { $env:NOVA_BRAIN_SESSION_ID = "nova-brain" }
Write-Host "Nova brain -> $($env:NOVA_API_BASE) as $($env:NOVA_BRAIN_SESSION_ID)"
py -3 -m nova_brain
