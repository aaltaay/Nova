<#
.SYNOPSIS
  Morning / logon bootstrap: IB Gateway (IBC if configured) + Nova API + UI.

.DESCRIPTION
  Idempotent. Skips pieces that are already healthy so a 6am task and an
  AtLogon task can both fire without double-killing healthy servers.
  Credentials stay in %USERPROFILE%\.nova\ibc\ -- never in this script.

  IMPORTANT: This file must stay ASCII-only. Windows Task Scheduler launches
  powershell.exe (5.1), which reads .ps1 as the system ANSI code page when
  there is no BOM. UTF-8 punctuation (em dash, ellipsis) corrupts the recycle
  branch so a wedged API on port 8000 is never killed -- see PROBLEM_LOG
  2026-07-30 morning empty-scanners wedge.

.PARAMETER RepoRoot
  Nova repository root (default: parent of this scripts/ folder).

.PARAMETER SkipGateway
  Do not launch IB Gateway / IBC.

.PARAMETER SkipBrowser
  Do not open http://localhost:5173.

.PARAMETER ForceRestart
  Stop ports 8000/5173 and start API+UI fresh even if they already respond.

.PARAMETER OpenBrowserDelaySec
  Seconds to wait before opening the browser (default 8).

.PARAMETER HealthWaitSec
  Max seconds to wait for /api/health after starting or recycling the API.
#>
param(
    [string]$RepoRoot = "",
    [switch]$SkipGateway,
    [switch]$SkipBrowser,
    [switch]$ForceRestart,
    [int]$OpenBrowserDelaySec = 8,
    [int]$HealthWaitSec = 60
)

$ErrorActionPreference = "Continue"

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$logDir = Join-Path $RepoRoot "backend\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}
$logFile = Join-Path $logDir "daily-start.log"

function Write-DailyLog {
    param([string]$Message, [string]$Level = "INFO")
    # String concat (not -f): messages must not be format-strings.
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

function Test-HttpOk {
    param([string]$Url, [int]$TimeoutSec = 3)
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Measure-HealthMs {
    param([int]$TimeoutSec = 5)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" `
            -UseBasicParsing -TimeoutSec $TimeoutSec
        $sw.Stop()
        return [int]$sw.ElapsedMilliseconds
    } catch {
        $sw.Stop()
        return -1
    }
}

function Wait-ApiHealthy {
    param([int]$TimeoutSec = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $ms = Measure-HealthMs -TimeoutSec 4
        if ($ms -ge 0) {
            Write-DailyLog "API health ok (${ms}ms)"
            return $true
        }
        Start-Sleep -Seconds 2
    }
    Write-DailyLog "API health still failing after ${TimeoutSec}s" "ERROR"
    return $false
}

function Stop-NovaPortChecked {
    param([string]$Ports)
    $stopScript = Join-Path $RepoRoot "scripts\Stop-NovaPorts.ps1"
    Write-DailyLog "Recycling ports $Ports via Stop-NovaPorts.ps1"
    & $stopScript -Ports $Ports
    Start-Sleep -Seconds 1
    foreach ($p in ($Ports -split ",")) {
        $port = [int]$p.Trim()
        if (Test-PortListening $port) {
            Write-DailyLog "Port $port still listening after recycle attempt" "ERROR"
        } else {
            Write-DailyLog "Port $port is free"
        }
    }
}

function Test-GatewayProcess {
    $names = @("ibgateway", "tws")
    foreach ($n in $names) {
        if (Get-Process -Name $n -ErrorAction SilentlyContinue) { return $true }
    }
    # IBC often leaves Gateway as javaw with an IB window title.
    $java = Get-Process -Name javaw, java -ErrorAction SilentlyContinue | Where-Object {
        $_.MainWindowTitle -match "IBKR Gateway|IB Gateway|Authenticating|IBC"
    }
    return [bool]$java
}

function Start-IbGateway {
    $ibcPs1 = Join-Path $env:USERPROFILE ".nova\ibc\start_gateway.ps1"
    $ibcBat = Join-Path $env:USERPROFILE ".nova\ibc\StartGateway.bat"
    $gatewayExe = $env:IBKR_GATEWAY_EXE
    if (-not $gatewayExe) {
        $defaultExe = "C:\Jts\ibgateway\1045\ibgateway.exe"
        if (Test-Path $defaultExe) { $gatewayExe = $defaultExe }
    }

    if (Test-GatewayProcess -or (Test-PortListening 4001) -or (Test-PortListening 4002)) {
        Write-DailyLog "IB Gateway already running (process or API port) -- skip launch"
        return
    }

    if (Test-Path $ibcPs1) {
        Write-DailyLog "Starting IB Gateway via IBC ($ibcPs1)"
        Write-DailyLog "Complete IBKR Mobile 2FA on your phone if prompted." "WARN"
        Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ibcPs1
        ) -WorkingDirectory (Split-Path $ibcPs1)
        return
    }

    if (Test-Path $ibcBat) {
        Write-DailyLog "Starting IB Gateway via IBC bat ($ibcBat)"
        Write-DailyLog "Complete IBKR Mobile 2FA on your phone if prompted." "WARN"
        Start-Process -FilePath $ibcBat -WorkingDirectory (Split-Path $ibcBat)
        return
    }

    if ($gatewayExe -and (Test-Path $gatewayExe)) {
        Write-DailyLog "IBC not configured -- launching Gateway exe (manual login required): $gatewayExe" "WARN"
        Start-Process -FilePath $gatewayExe
        return
    }

    Write-DailyLog "No IBC launcher or ibgateway.exe found -- skip Gateway. See docs\ibc-gateway-setup.md" "WARN"
}

function Start-NovaStack {
    $apiHealthy = (Test-PortListening 8000) -and (Test-HttpOk "http://127.0.0.1:8000/api/health")
    $uiUp = Test-PortListening 5173

    if ($ForceRestart) {
        Write-DailyLog "ForceRestart: clearing ports 8000 / 5173"
        Stop-NovaPortChecked -Ports "8000,5173"
        $apiHealthy = $false
        $uiUp = $false
    }

    if ($apiHealthy -and $uiUp) {
        $ms = Measure-HealthMs
        Write-DailyLog "Nova API + UI already up (health=${ms}ms) -- skip start"
        return
    }

    if (-not $apiHealthy -and (Test-PortListening 8000)) {
        Write-DailyLog "Port 8000 occupied but /api/health failed -- recycling" "WARN"
        Stop-NovaPortChecked -Ports "8000"
        $apiHealthy = $false
    }
    if (-not $uiUp -and (Test-PortListening 5173)) {
        # rare: port held without a healthy Vite -- leave alone unless ForceRestart
        Write-DailyLog "Port 5173 already listening -- skip UI start"
        $uiUp = $true
    }

    if (-not $apiHealthy) {
        Write-DailyLog "Starting Nova API (http://127.0.0.1:8000)"
        $apiScript = Join-Path $RepoRoot "scripts\Start-NovaApi.ps1"
        Start-Process -FilePath "powershell.exe" `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $apiScript) `
            -WorkingDirectory (Join-Path $RepoRoot "backend") `
            -WindowStyle Hidden
        if (-not (Wait-ApiHealthy -TimeoutSec $HealthWaitSec)) {
            Write-DailyLog "API did not become healthy after start" "ERROR"
        }
    }

    if (-not $uiUp) {
        Start-Sleep -Seconds 2
        Write-DailyLog "Starting Nova UI (http://localhost:5173)"
        $uiScript = Join-Path $RepoRoot "scripts\Start-NovaUi.ps1"
        Start-Process -FilePath "powershell.exe" `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $uiScript) `
            -WorkingDirectory (Join-Path $RepoRoot "frontend") `
            -WindowStyle Hidden
    }
}

function Write-FinalStatus {
    $gw4001 = Test-PortListening 4001
    $gw4002 = Test-PortListening 4002
    $apiListen = Test-PortListening 8000
    $uiListen = Test-PortListening 5173
    $healthMs = if ($apiListen) { Measure-HealthMs } else { -1 }
    $healthTxt = if ($healthMs -ge 0) { "${healthMs}ms" } else { "FAIL" }
    Write-DailyLog (
        "STATUS gateway4001=$gw4001 gateway4002=$gw4002 " +
        "apiListen=$apiListen health=$healthTxt uiListen=$uiListen"
    )
    if (-not $gw4001 -and -not $gw4002) {
        Write-DailyLog (
            "IB Gateway API ports are down. First login of the day may need " +
            "IBKR Mobile 2FA -- scanners stay empty until the API port opens."
        ) "WARN"
    }
}

Write-DailyLog "===== Nova daily start (repo=$RepoRoot) ====="

if (-not $SkipGateway) {
    Start-IbGateway
} else {
    Write-DailyLog "SkipGateway set -- not launching Gateway"
}

Start-NovaStack
Write-FinalStatus

if (-not $SkipBrowser) {
    $healthMs = Measure-HealthMs
    if ($healthMs -lt 0) {
        Write-DailyLog "Skipping browser open -- API health failed" "WARN"
    } else {
        Write-DailyLog "Waiting ${OpenBrowserDelaySec}s before opening browser..."
        Start-Sleep -Seconds $OpenBrowserDelaySec
        Start-Process "http://localhost:5173"
        Write-DailyLog "Opened http://localhost:5173"
    }
}

Write-DailyLog "Done. Log: $logFile"
Write-Host ""
Write-Host "Reminder: green Alpaca badges != IBKR logged in." -ForegroundColor Yellow
Write-Host "Set Scanner Source to IBKR and confirm Gateway API connects (phone 2FA if needed)." -ForegroundColor Yellow
