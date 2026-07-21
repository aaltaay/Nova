# 2026-07-19 — Dual listing flags, aux API chips, Alpaca RVOL label

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed | widgets (quote UI)
- **Related:** `CHANGELOG.md` §2026-07-19 — Dual listing flags… · [Alpaca usage inventory](2026-07-19-alpaca-usage-inventory.md)

## Task

Show Alpaca vs IBKR listing flags side-by-side on the quote panel; add header chips for aux APIs (Alpaca, OpenAI, yfinance, Archive) without calling Alpaca IEX the price feed under IBKR; label scanner/quote RVOL as Alpaca-sourced. Defer IBKR/yfinance RVOL replacement.

## Goal

Operators can compare broker metadata honestly, see which aux APIs are on, and watch Alpaca RVOL accuracy during live runs without changing the denominator yet.

## Why it mattered

Merged Yes/No listing flags hid Alpaca ETB vs IBKR locate differences. “Alpaca IEX” in the header under IBKR discovery implied the wrong price feed. Unlabeled RVOL made it easy to trust a thin-name denominator from the wrong venue.

## What we changed

- Backend: `listing_compare.py`, `ibkr/listing_flags.py`, ticker fast/slow/`detail_update` carry `listing`
- Backend: `integrations_health.py` + `/api/health` + scanner `health` → `integrations` chips (light R2 probe)
- Frontend: `TickerBrokerGrid` compare table; header aux chips; Volume/RVOL Alpaca badge + tooltips
- Tests: listing_compare, integrations_health, HeaderConnectionStatus, TickerBrokerGrid

## How it works now

- Quote `listing.alpaca` and `listing.ibkr` stay separate objects; UI never merges into one boolean
- Under `discovery=ibkr`, Gateway = prices; Alpaca chip = news/listing/scanner-RVOL aux only
- Scanner Volume secondary line shows `Nx rel` + `Alpaca` badge; hover explains daily-bar basis

## Why this approach

- **Side-by-side table** over dual Yes/No grids: one row per field makes disagreement obvious
- **Label RVOL, don’t swap source:** user deferred IBKR/yfinance warmer; attribution is enough for study runs
- **Light integrations probe:** avoid full `archive_health()` filesystem walk on every scanner poll
- **Rejected:** merging shortable into one “shortable” chip; keeping “Alpaca IEX” as the IBKR-mode price chip

## Verification

- `pytest backend/tests/test_listing_compare.py backend/tests/test_integrations_health.py` — 5 passed
- `vitest` HeaderConnectionStatus + TickerBrokerGrid — 3 passed

## Follow-ups

- Optional: yfinance-now / IBKR daily-bar warmer for RVOL (user deferred)
- Optional: live OpenAI ping (currently key+Lincoln flag only)

## Keywords

listing flags, alpaca, ibkr, shortable, easy_to_borrow, integrations chips, openai, yfinance, archive, rvol, alpaca badge, quote panel
