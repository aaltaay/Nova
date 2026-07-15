# Nova — IBKR Live Smoke Checklist

Run this after every deployment, Gateway restart, or when scanners look "empty"
for no reason. Empty gappers with `discovery=ibkr` usually means **Gateway login**,
not a quiet market.

## Automated API pass (do this first)

From the repo root, with the backend on `:8000`:

```powershell
.\scripts\smoke_check.ps1
```

Expect: all `PASS`, optional `WARN` for empty lists outside session hours.
`FAIL` on IBKR connected → stop and log into Gateway before anything else.

Optional: `.\scripts\smoke_check.ps1 -Base http://127.0.0.1:8000 -SampleSymbol SPY`

## Pre-flight

- [ ] IB Gateway window is open and logged in (Live + IB API)
- [ ] `.\scripts\smoke_check.ps1` → IBKR connected PASS
- [ ] No `ConnectionRefusedError` to `127.0.0.1:4001` in `backend/logs/`

## Scanner health

- [ ] Gappers non-empty in premarket, OR IBKR connected + empty is honest ("no gaps yet")
- [ ] Movers (gainers/losers via `/api/movers`) non-empty in regular hours when tape is active
- [ ] UI header "updated Xs ago" ≤ ~3s during an active IBKR session
- [ ] Header / Settings show discovery **ibkr** when `NOVA_DISCOVERY_PROVIDER=ibkr`

## Feed coherence (single-feed rule)

- [ ] Open a scanner row → quote price matches the table row (same feed)
- [ ] Chart source attribution says IBKR (not Alpaca) under discovery=ibkr
- [ ] Strategy bar endpoints return **503** if Gateway is down — never silent Alpaca bars
- [ ] Symbol not in any cache → ticker snapshot empty / error, not a sneaky Alpaca price

## Quote panel (rapid symbol switch)

1. Click ticker A → quote, chart, Level 2, T&S for A
2. Immediately click ticker B → confirm:
   - Quote is B (not stale A)
   - Level 2 clears then fills for B
   - Time & Sales clears; only B prints
   - Chart replaces A candles with B
3. Click back to A → same checks

**2026-07-15 — PASS (automated via `agent-browser`, live Gateway connected).** Rapidly
switched five Gainers rows (AEHG → KUST → VTAK → AEHR → JLHL, and back to AEHR/JLHL) with
Level 2 + Time & Sales + chart visible. Quote symbol, depth book, and chart price always
matched the just-selected symbol on both first visit and revisit; no leftover rows from a
prior symbol; no console errors or React crash warnings during the switching sequence. See
`CHANGELOG.md` 2026-07-15 "Live-verified rapid symbol-switch quote panel" for detail. This
item no longer requires a human to run manually — re-run any time via `agent-browser` with
Gateway logged in.

## HOD Momo

- [ ] HOD tab loads; alerts stream when the shortlist is active
- [ ] Scroll hundreds of rows without freeze
- [ ] Header age advances while alerts arrive (not frozen behind a scan)

## After-hours (if in the AH window)

- [ ] After-hours tab shows rows when IBKR top-% gainers exist
- [ ] Prices match IBKR gainers basis, not a silent Alpaca IEX list

## If something fails

1. Search `PROBLEM_LOG.md` for the symptom (stale, L2, empty, fallback, Gateway).
2. Confirm `/api/ibkr/status` → `connected: true` before debugging scanner logic.
3. Capture browser console (`npx agent-browser@latest console` or F12) on blank/freeze.
4. Fix root cause in the owning module — never band-aid in `main.py` / `App.tsx`.
