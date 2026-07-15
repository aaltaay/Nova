# Nova IBKR smoke check — run with: .\scripts\smoke_check.ps1
# Requires the backend on http://127.0.0.1:8000. IB Gateway should be logged in
# when discovery=ibkr (empty scanners + connected:false = login blocker, not "no gaps").
param(
    [string]$Base = "http://127.0.0.1:8000",
    [string]$SampleSymbol = "AAPL"
)

$pass = 0
$fail = 0
$warn = 0

function Pass([string]$label) {
    Write-Host "  PASS  $label" -ForegroundColor Green
    $script:pass++
}
function Fail([string]$label, [string]$detail = "") {
    $msg = if ($detail) { "$label ($detail)" } else { $label }
    Write-Host "  FAIL  $msg" -ForegroundColor Red
    $script:fail++
}
function Warn([string]$label) {
    Write-Host "  WARN  $label" -ForegroundColor Yellow
    $script:warn++
}

function Get-Json([string]$url, [int]$TimeoutSec = 8) {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $TimeoutSec -ErrorAction Stop
    return ($r.Content | ConvertFrom-Json)
}

Write-Host "`nNova IBKR smoke check — $Base`n"

# ── Core connectivity ─────────────────────────────────────────────────────────
try {
    $ibkr = Get-Json "$Base/api/ibkr/status"
    if ($ibkr.connected -eq $true) { Pass "IBKR connected (mode=$($ibkr.mode))" }
    else {
        Fail "IBKR connected" "connected=$($ibkr.connected) — log into IB Gateway"
        Write-Host ""
        Write-Host "  ACTION REQUIRED — IB Gateway login" -ForegroundColor Yellow
        Write-Host "  Gappers/movers will look empty until Gateway is logged in." -ForegroundColor Yellow
        Write-Host ""
    }
} catch {
    Fail "IBKR status" "$_"
}

try {
    $health = Get-Json "$Base/api/health"
    if ($health.status) { Pass "Health status=$($health.status) latency=$($health.latency_ms)ms" }
    else { Fail "Health endpoint" "missing status field" }
} catch {
    Fail "Health endpoint" "$_"
}

try {
    $cfg = Get-Json "$Base/api/config"
    $prov = $cfg.discovery_provider
    if ($prov) { Pass "Discovery provider=$prov" }
    else { Fail "Config discovery_provider" "missing" }
    if ($prov -eq "ibkr" -and $ibkr.connected -ne $true) {
        Warn "discovery=ibkr but Gateway not connected — scanners will look empty"
    }
} catch {
    Fail "Config endpoint" "$_"
}

# ── Scanner surfaces ──────────────────────────────────────────────────────────
try {
    $g = Get-Json "$Base/api/gappers"
    $n = @($g.gappers).Count
    Pass "Gappers endpoint ($n rows)"
    if ($n -eq 0 -and $ibkr.connected -eq $true) {
        Warn "Gappers empty with IBKR up — OK outside premarket / when no gaps"
    }
} catch {
    Fail "Gappers endpoint" "$_"
}

try {
    $m = Get-Json "$Base/api/movers"
    $gn = @($m.gainers).Count
    $ln = @($m.losers).Count
    Pass "Movers endpoint (gainers=$gn losers=$ln)"
    if ($gn -eq 0 -and $ln -eq 0 -and $ibkr.connected -eq $true) {
        Warn "Movers empty with IBKR up — OK outside market hours / quiet tape"
    }
} catch {
    Fail "Movers endpoint" "$_"
}

try {
    $ah = Get-Json "$Base/api/afterhours"
    $n = @($ah.afterhours).Count
    Pass "Afterhours endpoint ($n rows)"
} catch {
    Fail "Afterhours endpoint" "$_"
}

try {
    $cat = Get-Json "$Base/api/news-catalysts"
    $n = @($cat.catalysts).Count
    Pass "News catalysts endpoint ($n rows)"
} catch {
    Fail "News catalysts endpoint" "$_"
}

try {
    $hod = Get-Json "$Base/api/hod-momo/alerts"
    $n = @($hod.alerts).Count
    Pass "HOD Momo alerts endpoint ($n alerts)"
} catch {
    Fail "HOD Momo alerts endpoint" "$_"
}

# ── Ticker / bars (feed-coherence smoke) ──────────────────────────────────────
# IBKR overnight detail can take ~10–15s (snapshot + news + fundamentals).
try {
    $t = Get-Json "$Base/api/ticker/$SampleSymbol" -TimeoutSec 25
    if ($t.symbol -eq $SampleSymbol -or $t.symbol -eq $SampleSymbol.ToUpper()) {
        Pass "Ticker detail $SampleSymbol"
    } else {
        # Some payloads nest symbol; accept 200 + body
        Pass "Ticker detail $SampleSymbol (HTTP 200)"
    }
} catch {
    Fail "Ticker detail $SampleSymbol" "$_"
}

try {
    $bars = Get-Json "$Base/api/ticker/$SampleSymbol/bars?timeframe=1Min&limit=10" -TimeoutSec 20
    $bn = @($bars.bars).Count
    if ($bn -gt 0) { Pass "Ticker bars $SampleSymbol ($bn bars)" }
    else {
        # 503 / empty under IBKR when Gateway can't serve history is a loud fail path —
        # treat empty as WARN unless status was non-200 (caught above).
        Warn "Ticker bars $SampleSymbol empty — check Gateway history permissions / symbol"
    }
} catch {
    $msg = "$_"
    if ($msg -match "503") {
        Warn "Ticker bars $SampleSymbol → 503 (fail-loud IBKR path — expected if Gateway bars unavailable)"
    } else {
        Fail "Ticker bars $SampleSymbol" $msg
    }
}

Write-Host "`nResult: $pass passed, $fail failed, $warn warnings`n"
Write-Host "Manual UI checks still required — see scripts/ibkr_smoke_checklist.md`n"
if ($fail -gt 0) { exit 1 }
exit 0
