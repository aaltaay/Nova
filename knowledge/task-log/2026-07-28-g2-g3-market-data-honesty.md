# 2026-07-28 -- G2/G3: market-data type honesty + close-fallback quote quality

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / ibkr-ops
- **Related:** `CHANGELOG.md` § G2/G3 · `PROBLEM_LOG.md` § Delayed IBKR market data · audit G2/G3

## Task

Remediate capture-audit findings G2 (delayed data indistinguishable from live) and G3 (`last or close` + receive-clock timestamps).

## Goal

READY requests live market data; status + Gateway chip surface delayed; L1 listeners can see close-fallback and exchange-time stamps without breaking legacy 5-arg listeners.

## Why it mattered

Paper / non-entitled sessions can feed 15-minute-delayed prices into HOD with a fresh receive clock and no UI warning -- silent false confidence.

## What we changed

- `client._on_session_ready` calls `reqMarketDataType(1)`; `get_market_data_type()`
- `/api/ibkr/status` adds `market_data_type` + `market_data_delayed` (from Error 10167)
- `ticks._on_ticker_update`: exchange-time preference + `quote_quality=close_fallback`; threaded via scanner_l1 + apply_l1_quote into price_patch rows
- Header Gateway chip amber `delayed` when status says so

## How it works now

READY asks for live type; IB 10167 flips delayed flag. UI polls status and warns. Quote patches may carry `quote_quality` for honesty; HOD engine input unchanged.

## Why this approach

Keyword-only `quote_quality` + TypeError fallback keeps every existing 5-arg listener working. Status exposes both requested type and delayed override rather than inventing a fake type number. Header reads `useIbkrStatus` so parents do not need new props.

## Verification

`pytest tests/test_ibkr_ticks.py tests/test_routes_trading.py tests/test_hod_pipeline_fake_feed.py tests/test_ibkr_session_errors.py tests/test_ibkr_bridge.py` -- 38 passed. `npx vitest run src/components/HeaderConnectionStatus.test.tsx` -- passed.

## Follow-ups

Phases 4-7 of the capture remediation plan.

## Keywords

G2, G3, reqMarketDataType, delayed, close_fallback, quote_quality, Error 10167
