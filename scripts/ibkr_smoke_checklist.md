# Nova — IBKR Live Smoke Checklist

Run this after every deployment or Gateway restart to catch the most common
failure classes before the market opens.

## Pre-flight (before market or test session)

- [ ] IB Gateway window is open and logged in
- [ ] `GET http://127.0.0.1:8000/api/ibkr/status` → `"connected": true`
- [ ] No `ConnectionRefusedError` in `backend/logs/api-console.log`

## Scanner health

- [ ] `GET /api/gappers` — non-empty during premarket, OR explicit `"connected": true` + `[]` (no gappers yet)
- [ ] `GET /api/movers` (gainers/losers) — non-empty during market hours
- [ ] UI header shows "updated Xs ago" ≤ 3s during active session
- [ ] Header badge shows IBKR (not IEX/SIP) when `NOVA_DISCOVERY_PROVIDER=ibkr`

## Feed coherence (single-feed rule)

- [ ] `GET /api/ticker/{symbol}` — `snapshot.latest_trade.price` matches scanner row price (same feed)
- [ ] `GET /api/ticker/{symbol}` with a symbol **not** in any scanner cache — returns empty snapshot, not Alpaca price
- [ ] Chart bars source label in UI says IBKR, not Alpaca
- [ ] Strategy endpoints (`/api/strategy/gap-and-go/{sym}`, `/api/strategy/setups/{sym}`) — return 503 if Gateway disconnected, NOT Alpaca bars

## Quote panel (rapid symbol switch test)

1. Click ticker A → verify quote price appears, chart loads, Level 2 shows bids/asks for A
2. Immediately click ticker B → confirm:
   - Quote price updates to B (not stale A price)
   - Level 2 book clears and repopulates for B
   - Time & Sales clears and shows B prints only
   - Chart replaces A candles with B candles
3. Click back to A → same check in reverse

## HOD Momo

- [ ] HOD tab loads and shows live alerts (no "no alerts" with active market)
- [ ] Scroll to 500+ rows without freeze or jank
- [ ] Header "updated Xs ago" advances (not frozen) while HOD alerts stream

## After-hours (if applicable)

- [ ] After-hours tab shows ≥ 1 row (not perpetually empty)
- [ ] Row prices match IBKR top-% gainers, not Alpaca IEX prices

## Quick API smoke script

```powershell
# Run from repo root with the backend running on :8000
$base = "http://127.0.0.1:8000"

function Check($label, $url, $expect) {
    $r = Invoke-RestMethod $url -ErrorAction SilentlyContinue
    $ok = if ($expect) { ($r | ConvertTo-Json -Compress).Contains($expect) } else { $null -ne $r }
    Write-Host ($(if ($ok) { "PASS" } else { "FAIL" }), " $label")
}

Check "IBKR status connected"   "$base/api/ibkr/status"     '"connected":true'
Check "Health endpoint OK"      "$base/api/health"           '"status"'
Check "Gappers endpoint exists" "$base/api/gappers"          $null
Check "Gainers endpoint exists" "$base/api/gainers"          $null
```

Save as `scripts/smoke_check.ps1` and run with `.\scripts\smoke_check.ps1` after startup.
