# Nova IBKR smoke check — run with: .\scripts\smoke_check.ps1
# Requires the backend running on http://127.0.0.1:8000 and IB Gateway connected.
param([string]$Base = "http://127.0.0.1:8000")

$pass = 0; $fail = 0

function Check([string]$label, [string]$url, [string]$expect = "") {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        $body = $r.Content
        $ok = if ($expect) { $body.Contains($expect) } else { $r.StatusCode -eq 200 }
        if ($ok) { Write-Host "  PASS  $label" -ForegroundColor Green; $script:pass++ }
        else      { Write-Host "  FAIL  $label (unexpected body)" -ForegroundColor Red; $script:fail++ }
    } catch {
        Write-Host "  FAIL  $label ($_)" -ForegroundColor Red; $script:fail++
    }
}

Write-Host "`nNova IBKR smoke check — $Base`n"

Check "IBKR connected"           "$Base/api/ibkr/status"   '"connected":true'
Check "Health endpoint"          "$Base/api/health"        '"status"'
Check "Gappers endpoint"         "$Base/api/gappers"       ""
Check "Gainers endpoint"         "$Base/api/gainers"       ""
Check "Losers endpoint"          "$Base/api/losers"        ""
Check "Ticker detail (AAPL)"     "$Base/api/ticker/AAPL"   '"symbol"'
Check "Ticker bars (AAPL 1Min)"  "$Base/api/ticker/AAPL/bars?timeframe=1Min&limit=10" '"bars"'

Write-Host "`nResult: $pass passed, $fail failed`n"
if ($fail -gt 0) { exit 1 }
