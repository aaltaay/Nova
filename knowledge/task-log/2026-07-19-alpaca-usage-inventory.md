# 2026-07-19 — Alpaca API usage inventory (discovery=ibkr ops)

- **Status:** completed
- **Agents:** daddy | explore (inventory)
- **Domain:** market-feed
- **Related:** single-market-data-feed.mdc · user declined frontend DISCOVERY_PROVIDER_DEFAULT change

## Task

Inventory every live Alpaca API / credentials / feed usage path and answer whether Alpaca is used for anything when discovery is typically `ibkr`.

## Goal

A plain-language verdict: yes we still use Alpaca for X/Y/Z, or only leftovers — with no product code changes.

## Why it mattered

User declined flipping the frontend default to IBKR and asked what Alpaca is still for. Header can show “Alpaca IEX” when discovery≠ibkr; ops need an accurate inventory before any further Settings/default work.

## What we changed

- Investigate-only — no product code.
- Aggregate task log + daddy memory run-log.

## How it works now

When `NOVA_DISCOVERY_PROVIDER` / Settings `discovery_provider=ibkr`:

- **Not Alpaca:** live quotes, scanner row prices, charts, Alpaca trades WS, HOD trade ticks, live Time & Sales, order execution.
- **Still Alpaca (if keys present):** news (flames / catalysts / ticker news), Assets listing flags (tradable/shortable), scanner-row RVOL via daily bars (`ensure_avg_volume`), account health ping + Settings credentials / IEX|SIP.
- **HOD RVOL under ibkr:** yfinance avg volume only (`ibkr_avg_volume`) — deliberately ignores Alpaca IEX bar cache.
- **Silent IBKR→Alpaca price fallback:** not present on charts (503), ticker snapshot (empty), scanner, WS/HOD/T&S.
- Code defaults remain `DISCOVERY_PROVIDER_DEFAULT=alpaca`; runtime usually overridden by `.env` / Settings.
- Ticker detail REST still requires Alpaca headers to assemble (listing + news gate) even when prices come from IBKR.

## Why this approach

- Read-only explore + spot-check gates beat asking market-feed to “fix” anything — user asked inventory only.
- Rejected flipping frontend default again (user already declined).
- Distinguishing scanner RVOL (Alpaca bars) vs HOD RVOL (yfinance) avoids a false “Alpaca unused for volume” claim.

## Verification

Code-path audit: `chart_bars.py`, `websocket.py` (`alpaca_trades_drive_hod`), `scanner_runners/discovery.py`, `hod_momo_enrichment.py` / `test_hod_momo_enrichment.py`, `ticker_detail.py`, `composition/market_data_providers.py`, news via `scanner._check_news`.

## Follow-ups

- Optional: remove/soften ticker-detail hard require on Alpaca keys when discovery=ibkr (prices already IBKR).
- Optional: replace scanner `ensure_avg_volume` Alpaca bars under ibkr with yfinance (align with HOD).
- Docs: Obsidian `Alpaca-Integration-Reference.md` is stale vs current gates.

## Keywords

alpaca, discovery=ibkr, single-market-data-feed, news, listing metadata, avg_volume, RVOL, websocket idle, chart 503
