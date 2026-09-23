<#
.SYNOPSIS
  Morning / logon bootstrap: IB Gateway (IBC if configured) + Nova API + UI.

.DESCRIPTION
  Idempotent. Skips pieces that are already healthy so a 03:40 ET task and an
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

.PARAMETER GatewayPortWaitSec
  Max seconds to wait for Gateway API port 4001 or 4002 after launch.

.PARAMETER IbkrUsableWaitSec
  Max seconds to wait for /api/ibkr/status.connected (usable session) after API is up.
  Authenticating window title / LISTEN alone is never treated as healthy.
#>
param(
    [string]$RepoRoot = "",
    [switch]$SkipGateway,
    [switch]$SkipBrowser,
    [switch]$ForceRestart,
    [int]$OpenBrowserDelaySec = 8,
    [int]$HealthWaitSec = 180,
    [int]$GatewayPortWaitSec = 120,
    [int]$IbkrUsableWaitSec = 180
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

function Test-GatewayApiPort {
    return (Test-PortListening 4001) -or (Test-PortListening 4002)
}

function Wait-GatewayApiPort {
    param([int]$TimeoutSec = 120)
    if (Test-GatewayApiPort) {
        Write-DailyLog "Gateway API port already listening (4001 and/or 4002)"
        return $true
    }
    Write-DailyLog "Waiting up to ${TimeoutSec}s for Gateway API port 4001/4002..."
    Write-DailyLog (
        "STATUS: If IB Gateway shows Authenticating, complete IBKR Mobile 2FA on your phone now."
    ) "WARN"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-GatewayApiPort) {
            Write-DailyLog "Gateway API port is listening"
            return $true
        }
        Start-Sleep -Seconds 3
    }
    Write-DailyLog "Gateway API port still dark after ${TimeoutSec}s" "ERROR"
    Write-DailyLog (
        "ACTION REQUIRED -- IB Gateway login / phone 2FA. Scanners stay empty until the API port opens."
    ) "WARN"
    return $false
}

function Get-IbkrStatusJson {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/ibkr/status" `
            -UseBasicParsing -TimeoutSec 4
        if ($resp.StatusCode -lt 200 -or $resp.StatusCode -ge 500) { return $null }
        return ($resp.Content | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Wait-IbkrUsable {
    param([int]$TimeoutSec = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    Write-DailyLog "Waiting up to ${TimeoutSec}s for /api/ibkr/status.connected (usable session)..."
    while ((Get-Date) -lt $deadline) {
        $st = Get-IbkrStatusJson
        if ($null -ne $st) {
            $usable = ($st.connected -eq $true)
            $transport = $st.transport_connected
            $reason = $st.session_reason
            if ($usable) {
                Write-DailyLog (
                    "IBKR usable/ready (mode=$($st.mode) transport=$transport reason=$reason)"
                )
                return $true
            }
            if ($transport -eq $true) {
                Write-DailyLog (
                    "IBKR transport up but not usable yet (reason=$reason) -- waiting"
                )
            }
        }
        Start-Sleep -Seconds 3
    }
    $st = Get-IbkrStatusJson
    $transport = if ($null -ne $st) { $st.transport_connected } else { "unknown" }
    $reason = if ($null -ne $st) { $st.session_reason } else { "unknown" }
    Write-DailyLog (
        "IBKR not usable after ${TimeoutSec}s (transport=$transport reason=$reason)"
    ) "ERROR"
    Write-DailyLog (
        "ACTION REQUIRED -- look at IB Gateway / phone 2FA. " +
        "Authenticating window title or LISTEN alone is not a healthy session."
    ) "WARN"
    return $false
}

function Repair-IbcAutoRestartConfig {
    <#
    This scheduled/unattended path starts IBC directly -- it never calls
    Nova's Python launch_gateway.py, so that code's AutoRestartTime fix
    (PROBLEM_LOG 2026-08-25) never reaches the one path that actually
    caused the bug (an unattended 03:40 cold start with nobody there for
    the phone prompt). Repair the two keys here too so config.ini is
    correct even before any UI-triggered Paper/Live click has run.
    #>
    $ibcIni = Join-Path $env:USERPROFILE ".nova\ibc\config.ini"
    if (-not (Test-Path $ibcIni)) { return }
    $text = Get-Content -Path $ibcIni -Raw -ErrorAction SilentlyContinue
    if (-not $text) { return }
    $changed = $false
    if ($text -match '(?m)^AutoRestartTime\s*=.*$') {
        if ($Matches[0] -ne "AutoRestartTime=11:45 PM") {
            $text = [regex]::Replace($text, '(?m)^AutoRestartTime\s*=.*$', "AutoRestartTime=11:45 PM", 1)
            $changed = $true
        }
    }
    if ($text -match '(?m)^AutoLogoffTime\s*=.*$') {
        if ($Matches[0] -ne "AutoLogoffTime=") {
            $text = [regex]::Replace($text, '(?m)^AutoLogoffTime\s*=.*$', "AutoLogoffTime=", 1)
            $changed = $true
        }
    }
    if ($changed) {
        Set-Content -Path $ibcIni -Value $text -Encoding UTF8 -NoNewline
        Write-DailyLog "Repaired IBC config.ini: AutoRestartTime=11:45 PM, AutoLogoffTime= (week-long token for both doors)"
    }
}

function Get-ReloginReason {
    # One line from tools/premarket_verify.py: why the Gateway's latest start
    # needed (or did not need) a phone login -- a Windows restart and who
    # asked for it, or a fresh start (#14). Empty when Python is unavailable.
    $tool = Join-Path $RepoRoot "tools\premarket_verify.py"
    if (-not (Test-Path $tool)) { return "" }
    try {
        $line = & py -3 $tool relogin 2>$null | Select-Object -Last 1
        return [string]$line
    } catch {
        return ""
    }
}

function Set-IbcDayOfWeek {
    # IBC names its log after the weekday it reads from wmic, which Windows 11
    # no longer ships: every log became IBC-..._.txt and each cold start
    # deleted the last one, so no login history survived a day. IBC keeps an
    # inherited DAYOFWEEK when wmic prints nothing (constants_relogin.py).
    $env:DAYOFWEEK = (Get-Date).DayOfWeek.ToString().ToUpperInvariant()
}

function Start-IbGateway {
    Repair-IbcAutoRestartConfig
    Set-IbcDayOfWeek
    $ibcPs1 = Join-Path $env:USERPROFILE ".nova\ibc\start_gateway.ps1"
    $ibcBat = Join-Path $env:USERPROFILE ".nova\ibc\StartGateway.bat"
    $gatewayExe = $env:IBKR_GATEWAY_EXE
    if (-not $gatewayExe) {
        $defaultExe = "C:\Jts\ibgateway\1045\ibgateway.exe"
        if (Test-Path $defaultExe) { $gatewayExe = $defaultExe }
    }

    # Only skip launch when the API port is already listening.
    # Process / Authenticating window title alone is NOT healthy -- may still need 2FA.
    if (Test-GatewayApiPort) {
        Write-DailyLog "IB Gateway API port already listening -- skip launch"
        return
    }

    if (Test-GatewayProcess) {
        Write-DailyLog (
            "IB Gateway process present but API ports dark -- not launching another instance. " +
            "Complete login / IBKR Mobile 2FA if the window says Authenticating."
        ) "WARN"
        return
    }

    if (Test-Path $ibcPs1) {
        Write-DailyLog "Starting IB Gateway via IBC ($ibcPs1)"
        Write-DailyLog "STATUS: Complete IBKR Mobile 2FA on your phone if prompted." "WARN"
        Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ibcPs1
        ) -WorkingDirectory (Split-Path $ibcPs1)
        return
    }

    if (Test-Path $ibcBat) {
        Write-DailyLog "Starting IB Gateway via IBC bat ($ibcBat)"
        Write-DailyLog "STATUS: Complete IBKR Mobile 2FA on your phone if prompted." "WARN"
        Start-Process -FilePath $ibcBat -WorkingDirectory (Split-Path $ibcBat)
        return
    }

    if ($gatewayExe -and (Test-Path $gatewayExe)) {
        Write-DailyLog "IBC not configured -- launching Gateway exe (manual login required): $gatewayExe" "WARN"
        Write-DailyLog "STATUS: Complete IBKR Mobile 2FA on your phone if prompted." "WARN"
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
    $st = if ($apiListen -and $healthMs -ge 0) { Get-IbkrStatusJson } else { $null }
    $usable = if ($null -ne $st) { $st.connected } else { "n/a" }
    $transport = if ($null -ne $st) { $st.transport_connected } else { "n/a" }
    $reason = if ($null -ne $st) { $st.session_reason } else { "n/a" }
    Write-DailyLog (
        "STATUS gateway4001=$gw4001 gateway4002=$gw4002 " +
        "apiListen=$apiListen health=$healthTxt uiListen=$uiListen " +
        "ibkrUsable=$usable transport=$transport reason=$reason"
    )
    if (-not $gw4001 -and -not $gw4002) {
        Write-DailyLog (
            "IB Gateway API ports are down -- approve the IBKR Mobile login on your phone; " +
            "scanners stay empty until the API port opens."
        ) "WARN"
        $why = Get-ReloginReason
        if ($why) { Write-DailyLog "WHY: $why" "WARN" }
    }
    elseif ($usable -ne $true) {
        Write-DailyLog (
            "STATUS WARN: IBKR session not usable yet (transport=$transport reason=$reason). " +
            "If Gateway says Authenticating, complete phone 2FA now."
        ) "WARN"
    }
}

Write-DailyLog "===== Nova daily start (repo=$RepoRoot) ====="

if (-not $SkipGateway) {
    Start-IbGateway
    $null = Wait-GatewayApiPort -TimeoutSec $GatewayPortWaitSec
} else {
    Write-DailyLog "SkipGateway set -- not launching Gateway"
}

Start-NovaStack

# Prefer usable session (status.connected) -- never treat Authenticating / LISTEN alone as healthy.
$apiOk = (Measure-HealthMs) -ge 0
if ($apiOk -and -not $SkipGateway) {
    $null = Wait-IbkrUsable -TimeoutSec $IbkrUsableWaitSec
}

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
Write-Host "Reminder: green Alpaca badges != IBKR logged in / usable." -ForegroundColor Yellow
Write-Host "Set Scanner Source to IBKR and confirm /api/ibkr/status.connected (phone 2FA if needed)." -ForegroundColor Yellow
