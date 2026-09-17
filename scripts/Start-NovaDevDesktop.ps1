<#
.SYNOPSIS
  Daily UI roll-out: attach unpackaged Electron to an already-running Nova API.

.DESCRIPTION
  Lock A: if GET /api/health is HTTP 200, this script never calls Stop-NovaPorts
  and never restarts the API. It only ensures Vite on 5173 and launches Electron
  with NOVA_VITE_URL=http://127.0.0.1:5173 and NOVA_SKIP_API_SIDECAR=1 so the
  desktop shell cannot recycle :8000.

  If the API is not healthy, print a clear reload-API message and exit 1.
  Backend changes need an explicit API reload -- this script will not do it.

  This is not Start-NovaDaily.ps1 (morning bootstrap). It is not
  Run Nova Desktop.bat (that file Stop-NovaPorts 8000+5173 first).

  IMPORTANT: ASCII-only, no BOM. powershell 5.1 + Task Scheduler.

.PARAMETER RepoRoot
  Nova repository root (default: parent of this scripts/ folder).

.PARAMETER PullMaster
  git fetch origin master. If HEAD is master, fast-forward only.

.PARAMETER ViteWaitSec
  Max seconds to wait for Vite on 5173 after Start-NovaUi.ps1.
#>
param(
    [string]$RepoRoot = "",
    [switch]$PullMaster,
    [int]$ViteWaitSec = 90
)

$ErrorActionPreference = "Continue"

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$logDir = Join-Path $RepoRoot "backend\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}
$logFile = Join-Path $logDir "dev-desktop.log"

function Write-DevDesktopLog {
    param([string]$Message, [string]$Level = "INFO")
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$Level] $Message"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    $color = switch ($Level) {
        "WARN" { "Yellow" }
        "ERROR" { "Red" }
        default { "Cyan" }
    }
    Write-Host $line -ForegroundColor $color
}

function Test-PortListening {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

function Test-ApiHealth200 {
    param([int]$TimeoutSec = 4)
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" `
            -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Test-ViteHttp {
    param([int]$TimeoutSec = 3)
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:5173" `
            -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Update-MasterIfRequested {
    if (-not $PullMaster) { return }
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        Write-DevDesktopLog "git not on PATH -- cannot -PullMaster" "ERROR"
        exit 1
    }
    Push-Location $RepoRoot
    try {
        Write-DevDesktopLog "PullMaster: git fetch origin master"
        git fetch origin master
        if ($LASTEXITCODE -ne 0) {
            Write-DevDesktopLog "git fetch origin master failed" "ERROR"
            exit 1
        }
        $branch = (git rev-parse --abbrev-ref HEAD).Trim()
        if ($branch -eq "master") {
            Write-DevDesktopLog "PullMaster: fast-forward master to origin/master"
            git merge --ff-only origin/master
            if ($LASTEXITCODE -ne 0) {
                Write-DevDesktopLog "PullMaster could not fast-forward master. Resolve locally." "ERROR"
                exit 1
            }
        } else {
            Write-DevDesktopLog (
                "PullMaster fetched origin/master but HEAD is $branch -- not switching."
            ) "WARN"
        }
    } finally {
        Pop-Location
    }
}

function Wait-ViteReady {
    param([int]$TimeoutSec = 90)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ((Test-PortListening 5173) -and (Test-ViteHttp)) {
            Write-DevDesktopLog "Vite ready at http://127.0.0.1:5173"
            return $true
        }
        Start-Sleep -Seconds 2
    }
    Write-DevDesktopLog "Vite did not become ready on 5173 after ${TimeoutSec}s" "ERROR"
    return $false
}

function Start-ViteIfNeeded {
    if ((Test-PortListening 5173) -and (Test-ViteHttp)) {
        Write-DevDesktopLog "Vite already up on 5173 -- skip Start-NovaUi"
        return
    }
    if (Test-PortListening 5173) {
        Write-DevDesktopLog "Port 5173 listening -- skip Start-NovaUi (HTTP not required yet)"
        return
    }
    $uiScript = Join-Path $RepoRoot "scripts\Start-NovaUi.ps1"
    if (-not (Test-Path $uiScript)) {
        Write-DevDesktopLog "Missing $uiScript" "ERROR"
        exit 1
    }
    Write-DevDesktopLog "Starting Vite via Start-NovaUi.ps1 (not recycling API)"
    $frontendDir = Join-Path $RepoRoot "frontend"
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $uiScript) `
        -WorkingDirectory $frontendDir `
        -WindowStyle Hidden
    if (-not (Wait-ViteReady -TimeoutSec $ViteWaitSec)) {
        exit 1
    }
}

function Start-UnpackagedElectron {
    $frontendDir = Join-Path $RepoRoot "frontend"
    $electronCmd = Join-Path $frontendDir "node_modules\.bin\electron.cmd"
    if (-not (Test-Path $electronCmd)) {
        $electronCmd = Join-Path $frontendDir "node_modules\.bin\electron"
    }
    if (-not (Test-Path $electronCmd)) {
        Write-DevDesktopLog (
            "electron is not installed under frontend/node_modules. Run npm ci in frontend/."
        ) "ERROR"
        exit 1
    }
    $env:NOVA_VITE_URL = "http://127.0.0.1:5173"
    $env:NOVA_SKIP_API_SIDECAR = "1"
    Write-DevDesktopLog (
        "Launching unpackaged Electron (NOVA_VITE_URL=$($env:NOVA_VITE_URL) NOVA_SKIP_API_SIDECAR=1)"
    )
    Start-Process -FilePath $electronCmd -ArgumentList @(".") -WorkingDirectory $frontendDir
}

Write-DevDesktopLog "===== Nova dev desktop attach (repo=$RepoRoot) ====="
Write-DevDesktopLog "Lock A: this script never calls Stop-NovaPorts and never restarts the API."

Update-MasterIfRequested

if (-not (Test-ApiHealth200)) {
    Write-DevDesktopLog "GET /api/health is not HTTP 200 at http://127.0.0.1:8000/api/health" "ERROR"
    Write-Host ""
    Write-Host "Nova API is not healthy. This helper will not recycle :8000 (Lock A)." -ForegroundColor Red
    Write-Host "If you changed backend code, reload the API yourself, then re-run this script." -ForegroundColor Yellow
    Write-Host "  scripts\Start-NovaApi.ps1" -ForegroundColor Yellow
    Write-Host "  or the header Reload backend control (not this attach helper)." -ForegroundColor Yellow
    Write-Host "Do not use Run Nova Desktop.bat for this -- it Stop-NovaPorts 8000 first." -ForegroundColor Yellow
    exit 1
}

Write-DevDesktopLog "API health 200 -- attach only (no Stop-NovaPorts, no API restart)"
Start-ViteIfNeeded
Start-UnpackagedElectron
Write-DevDesktopLog "Done. Log: $logFile"
exit 0
