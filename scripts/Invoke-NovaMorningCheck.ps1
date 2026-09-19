<#
.SYNOPSIS
  Pre-open self-check: Gateway, API, IBKR session, gappers, loop lag.

.DESCRIPTION
  ASCII-only. Run by scheduled task NovaMorningCheck at 03:55 ET (see
  Install-NovaDailyTask.ps1). On any failed leg: POST /api/alerts/system-event
  so Discord/Telegram names the failure. If the API itself is down, fall back
  to a direct Discord/webhook POST from alerts_channels.json.

  Does not treat empty gappers as OK during 04:00-09:30 ET once IBKR is
  connected. Outside premarket, empty rows are allowed; feed_error is not.

.PARAMETER RepoRoot
  Nova repository root (default: parent of this scripts/ folder).

.PARAMETER Base
  API origin (default http://127.0.0.1:8000).

.PARAMETER AlertOnPass
  Also dispatch a passed system event (default: silent on success).
#>
param(
    [string]$RepoRoot = "",
    [string]$Base = "http://127.0.0.1:8000",
    [switch]$AlertOnPass
)

$ErrorActionPreference = "Continue"

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$logDir = Join-Path $RepoRoot "backend\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}
$logFile = Join-Path $logDir "morning-check.log"

function Write-CheckLog {
    param([string]$Message, [string]$Level = "INFO")
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$Level] $Message"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    $color = switch ($Level) {
        "WARN" { "Yellow" }
        "ERROR" { "Red" }
        "PASS" { "Green" }
        default { "Cyan" }
    }
    Write-Host $line -ForegroundColor $color
}

function Test-PortListening {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

function Get-Json {
    param([string]$Url, [int]$TimeoutSec = 8)
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec -ErrorAction Stop
    return ($r.Content | ConvertFrom-Json)
}

function Test-PremarketEt {
    try {
        $tz = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
        $et = [TimeZoneInfo]::ConvertTimeFromUtc((Get-Date).ToUniversalTime(), $tz)
        $mins = $et.Hour * 60 + $et.Minute
        return ($mins -ge (4 * 60) -and $mins -lt (9 * 60 + 30))
    } catch {
        return $false
    }
}

function Get-DirectWebhookUrl {
    $cacheDir = Join-Path $RepoRoot "backend\.cache"
    $envCache = [Environment]::GetEnvironmentVariable("NOVA_CACHE_DIR")
    if ($envCache) { $cacheDir = $envCache }
    $store = Join-Path $cacheDir "alerts_channels.json"
    if (-not (Test-Path $store)) { return $null }
    try {
        $data = Get-Content -Path $store -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($ch in @($data.channels)) {
            if (-not $ch.enabled) { continue }
            if ($ch.webhook_url -and ($ch.type -eq "discord" -or $ch.type -eq "webhook")) {
                return [string]$ch.webhook_url
            }
        }
    } catch {
        return $null
    }
    return $null
}

function Send-DirectWebhook {
    param([string]$Leg, [string]$Detail)
    $url = Get-DirectWebhookUrl
    if (-not $url) {
        Write-CheckLog "No Discord/webhook URL in alerts_channels.json for fallback" "WARN"
        return
    }
    $body = @{
        embeds = @(
            @{
                title       = "Nova Morning Check"
                description = "Nova morning check FAILED`nLeg: $Leg`n$Detail"
                color       = 14431526
            }
        )
    } | ConvertTo-Json -Depth 5
    try {
        Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json" -Body $body -TimeoutSec 10 | Out-Null
        Write-CheckLog "Direct webhook fallback posted for leg=$Leg" "INFO"
    } catch {
        Write-CheckLog "Direct webhook fallback failed: $($_.Exception.Message)" "ERROR"
    }
}

function Send-SystemAlert {
    param([string]$Leg, [bool]$Ok, [string]$Detail)
    $payload = @{
        leg    = $Leg
        ok     = $Ok
        detail = $Detail
    } | ConvertTo-Json
    try {
        Invoke-RestMethod -Uri "$Base/api/alerts/system-event" -Method Post -ContentType "application/json" -Body $payload -TimeoutSec 10 | Out-Null
        return $true
    } catch {
        Write-CheckLog "system-event POST failed: $($_.Exception.Message)" "WARN"
        if (-not $Ok) {
            Send-DirectWebhook -Leg $Leg -Detail $Detail
        }
        return $false
    }
}

$failedLeg = $null
$failedDetail = $null

# 1. Gateway API port
if ((Test-PortListening 4001) -or (Test-PortListening 4002)) {
    Write-CheckLog "gateway_port listening" "PASS"
} else {
    $failedLeg = "gateway_port"
    $failedDetail = "neither 4001 nor 4002 listening"
    Write-CheckLog $failedDetail "ERROR"
}

# 2. API health + IB loop lag
if (-not $failedLeg) {
    try {
        $health = Get-Json "$Base/api/health"
        $wedged = $false
        if ($health.ib_loop_lag_ms) { $wedged = [bool]$health.ib_loop_lag_ms.wedged }
        if ($wedged) {
            $failedLeg = "api_health"
            $failedDetail = "ib_loop_lag_ms.wedged=true last=$($health.ib_loop_lag_ms.last_ms)"
            Write-CheckLog $failedDetail "ERROR"
        } else {
            Write-CheckLog "api_health status=$($health.status) ib_wedged=false" "PASS"
        }
    } catch {
        $failedLeg = "api_health"
        $failedDetail = "GET /api/health failed: $($_.Exception.Message)"
        Write-CheckLog $failedDetail "ERROR"
    }
}

# 3. IBKR usable session (retry while still connecting -- Gateway can be up first)
if (-not $failedLeg) {
    $ibkrOk = $false
    $lastIbkrDetail = ""
    foreach ($attempt in 1..6) {
        try {
            $ibkr = Get-Json "$Base/api/ibkr/status"
            if ($ibkr.connected -eq $true) {
                Write-CheckLog "ibkr_status connected mode=$($ibkr.mode)" "PASS"
                # D-058: READY, but the Gateway stopped answering reqCompletedOrders.
                # The desk hides this in Sim (status forces connected=true there).
                $inSim = ($ibkr.mode -eq "sim") -or ($ibkr.sim -eq $true)
                if ($ibkr.completed_orders_unanswered_since -and -not $inSim) {
                    $at = [DateTimeOffset]::FromUnixTimeSeconds([long]$ibkr.completed_orders_unanswered_since).ToLocalTime()
                    $fmt = if ($at.Date -eq (Get-Date).Date) { "HH:mm" } else { "ddd HH:mm" }
                    Write-CheckLog "completed orders not answering since $($at.ToString($fmt)) -- prices/positions update; restart IB Gateway when convenient (2FA); if orders are rejected too, check Read-Only API" "WARN"
                }
                $ibkrOk = $true
                break
            }
            $reason = [string]$ibkr.session_reason
            $lastIbkrDetail = "connected=$($ibkr.connected) transport=$($ibkr.transport_connected) reason=$reason"
            if ($reason -eq "connecting" -or $reason -eq "synchronizing") {
                Write-CheckLog "ibkr_status wait attempt=$attempt $lastIbkrDetail" "WARN"
                Start-Sleep -Seconds 15
                continue
            }
            Write-CheckLog $lastIbkrDetail "ERROR"
            break
        } catch {
            $lastIbkrDetail = "GET /api/ibkr/status failed: $($_.Exception.Message)"
            Write-CheckLog $lastIbkrDetail "ERROR"
            break
        }
    }
    if (-not $ibkrOk) {
        $failedLeg = "ibkr_status"
        $failedDetail = $lastIbkrDetail
    }
}

# 4. Gappers roster honesty
if (-not $failedLeg) {
    try {
        $g = Get-Json "$Base/api/gappers"
        $n = @($g.gappers).Count
        $feedErr = [string]$g.feed_error
        $tableState = [string]$g.table_state
        if ($feedErr -and $feedErr -ne "") {
            $failedLeg = "gappers"
            $failedDetail = "feed_error=$feedErr table_state=$tableState rows=$n"
            Write-CheckLog $failedDetail "ERROR"
        } elseif ($tableState -eq "unavailable") {
            $failedLeg = "gappers"
            $failedDetail = "table_state=unavailable rows=$n"
            Write-CheckLog $failedDetail "ERROR"
        } elseif ((Test-PremarketEt) -and $n -eq 0) {
            # Gappers is a projection of the Gainers roster (ADR 008 amendment
            # 2026-08-24): zero rows can simply mean nothing clears the gap
            # floor yet. The load-bearing premarket signal is leg 4b below.
            Write-CheckLog "premarket and 0 gapper rows (table_state=$tableState)" "WARN"
        } else {
            Write-CheckLog "gappers rows=$n table_state=$tableState" "PASS"
        }
    } catch {
        $failedLeg = "gappers"
        $failedDetail = "GET /api/gappers failed: $($_.Exception.Message)"
        Write-CheckLog $failedDetail "ERROR"
    }
}

# 4b. Gainers roster honesty -- the feed that owns discovery 04:00-16:00 ET.
# Added after 2026-08-24: this check watched only gappers, so a Gainers feed
# that never committed a single row went unnoticed for the whole premarket.
if (-not $failedLeg) {
    try {
        $m = Get-Json "$Base/api/movers"
        $gn = @($m.gainers).Count
        $mFeedErr = [string]$m.feed_error
        $gainerState = [string]$m.table_state
        if ($mFeedErr -and $mFeedErr -ne "") {
            $failedLeg = "gainers"
            $failedDetail = "feed_error=$mFeedErr table_state=$gainerState rows=$gn"
            Write-CheckLog $failedDetail "ERROR"
        } elseif ((Test-PremarketEt) -and $gn -eq 0) {
            $failedLeg = "gainers"
            $failedDetail = "premarket and 0 gainer rows (table_state=$gainerState) -- IB names are not reaching the roster"
            Write-CheckLog $failedDetail "ERROR"
        } else {
            Write-CheckLog "gainers rows=$gn table_state=$gainerState" "PASS"
        }
    } catch {
        $failedLeg = "gainers"
        $failedDetail = "GET /api/movers failed: $($_.Exception.Message)"
        Write-CheckLog $failedDetail "ERROR"
    }
}

# 5. Scanner integrity (warn-loud; fail only on explicit error/fail status)
if (-not $failedLeg) {
    try {
        $integ = Get-Json "$Base/api/scan/integrity"
        $status = [string]$integ.status
        if ($status -eq "error" -or $status -eq "fail" -or $status -eq "failed") {
            $failedLeg = "integrity"
            $failedDetail = "scan integrity status=$status"
            Write-CheckLog $failedDetail "ERROR"
        } else {
            Write-CheckLog "integrity status=$status" "PASS"
        }
    } catch {
        Write-CheckLog "scan integrity skipped: $($_.Exception.Message)" "WARN"
    }
}

# 6. IBC AutoRestartTime format (warn only -- 23:45 is ignored by IBC)
$ibcIni = Join-Path $env:USERPROFILE ".nova\ibc\config.ini"
if (Test-Path $ibcIni) {
    $raw = Get-Content -Path $ibcIni -ErrorAction SilentlyContinue
    $restart = $null
    $relogin = $null
    $sfTimeout = $null
    foreach ($line in $raw) {
        if ($line -match '^\s*AutoRestartTime\s*=\s*(.*)$') {
            $restart = $Matches[1].Trim()
        } elseif ($line -match '^\s*ReloginAfterSecondFactorAuthenticationTimeout\s*=\s*(.*)$') {
            $relogin = $Matches[1].Trim()
        } elseif ($line -match '^\s*SecondFactorAuthenticationTimeout\s*=\s*(.*)$') {
            $sfTimeout = $Matches[1].Trim()
        }
    }
    if (-not $restart) {
        Write-CheckLog "IBC AutoRestartTime missing in config.ini" "WARN"
    } elseif ($restart -notmatch '(?i)^\d{1,2}:\d{2}\s*(AM|PM)$') {
        Write-CheckLog "IBC AutoRestartTime='$restart' is not HH:MM AM/PM (bare 23:45 is ignored)" "WARN"
    } else {
        Write-CheckLog "IBC AutoRestartTime=$restart" "PASS"
    }
    # PROBLEM_LOG 2026-08-25: 'yes' here retries an unanswered Second Factor
    # prompt in a loop and can hit IBKR's login rate limit (Aug 20 incident).
    if ($relogin -and $relogin -match '(?i)^yes$') {
        Write-CheckLog "IBC ReloginAfterSecondFactorAuthenticationTimeout=yes -- unattended 2FA will retry-loop (set to 'no')" "WARN"
    } elseif ($relogin) {
        Write-CheckLog "IBC ReloginAfterSecondFactorAuthenticationTimeout=$relogin" "PASS"
    }
    # backend/ibkr/second_factor.py's stale-prompt detector assumes this
    # matches IBC's own timeout -- see IBKR_SECOND_FACTOR_STALE_AFTER_SEC.
    if ($sfTimeout -and $sfTimeout -ne "180") {
        Write-CheckLog "IBC SecondFactorAuthenticationTimeout=$sfTimeout (Nova's stale-prompt detector assumes 180 -- update IBKR_SECOND_FACTOR_STALE_AFTER_SEC if this is intentional)" "WARN"
    } elseif ($sfTimeout) {
        Write-CheckLog "IBC SecondFactorAuthenticationTimeout=$sfTimeout" "PASS"
    }
} else {
    Write-CheckLog "IBC config.ini not found (optional)" "WARN"
}

if ($failedLeg) {
    Send-SystemAlert -Leg $failedLeg -Ok $false -Detail $failedDetail | Out-Null
    Write-CheckLog "RESULT FAIL leg=$failedLeg" "ERROR"
    exit 1
}

if ($AlertOnPass) {
    Send-SystemAlert -Leg "all" -Ok $true -Detail "all legs passed" | Out-Null
}
Write-CheckLog "RESULT PASS" "PASS"
exit 0
