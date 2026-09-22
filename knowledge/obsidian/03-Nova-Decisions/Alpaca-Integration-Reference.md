---
title: Alpaca Integration Reference — every dependency, before any removal
date: 2026-07-14
status: reference
---

# Alpaca Integration Reference

## Why this doc exists

User wants Nova off Alpaca entirely (free IEX feed is too slow to be usable for
live scanning) and onto IBKR only. Scanner discovery already moved to IBKR
(`Scanner-Provider-IBKR-Primary.md`, 2026-07-13), but a full audit shows Alpaca
still powers several features that have **no IBKR replacement written yet** —
News, Charts, RVOL, After-Hours, HOD Momo's real-time feed, and L2 tape
recording would all go dark if Alpaca were deleted today.

This doc is the "how do we use Alpaca" reference so a future session can
rebuild each piece on IBKR (or another provider) one at a time without
guessing what breaks. See `PROBLEM_LOG.md` 2026-07-14 and `CHANGELOG.md` for
the session that produced this.

There is **no `backend/alpaca.py`** despite `backend-modularity.mdc` naming
one in the target layout — all Alpaca REST/WS code lives inline in
`backend/main.py` (~2,400 lines) and `backend/bars.py`. Extracting it into a
real `alpaca.py` module would itself be a useful first step before any
removal, so each call site is in one place.

## Classification key

- **(A) Already IBKR-native** — safe today, no Alpaca dependency for this path.
- **(B) IBKR-partial** — some code exists in `backend/ibkr/` but doesn't fully
  cover this feature yet.
- **(C) Alpaca-only** — no IBKR alternative exists; removing Alpaca here
  breaks the feature outright.

## Feature-by-feature inventory

### (A) Already IBKR-native — safe today

| Feature | Alpaca path (still exists, unused when `discovery_provider=ibkr`) | IBKR path |
|---|---|---|
| Premarket gappers discovery | `_run_discovery_scan` → `_compute_gappers` (`backend/main.py:636,919`) | `backend/ibkr/discovery.py` `get_gappers()` (scan code `TOP_OPEN_PERC_GAIN`) |
| Gainers / losers discovery | `_run_gainers_update` (`main.py:1168`) | `_run_gainers_update_ibkr` (`main.py:1151`) → `ibkr.discovery.get_gainers/get_losers` |
| Between-scan price refresh | Alpaca WS `_handle_trade` (`main.py:793`) | `_reprice_ibkr_caches` (`main.py:320`) — re-snapshots cached symbols every `IBKR_REPRICE_INTERVAL_SEC` (3s) |
| Ticker REST snapshot (if symbol is IBKR-cached) | `_fetch_ticker_snapshot` (`main.py:2041`) | `_fetch_ticker_snapshot_ibkr` (`main.py:2139`), used by `_build_ticker_detail` when `discovery_provider=ibkr` |
| Ticker WS live `trade_update` | Alpaca WS tick | IBKR reprice broadcast (blocked from Alpaca overlay via the `discovery_provider == "ibkr"` early-return in `_handle_trade`, added 2026-07-13 — see `PROBLEM_LOG.md`) |
| Level 2 order book | N/A (Alpaca never had L2 in Nova) | `backend/ibkr/depth.py` — `reqMktDepth(isSmartDepth=True)`, capped at `IBKR_MAX_DEPTH_SYMBOLS=3` concurrent |

### (B) IBKR-partial

| Feature | Gap |
|---|---|
| Exchange-per-symbol | Global `_symbol_exchange` map (`backend/exchanges.py`) is built from Alpaca `/v2/assets` only; IBKR discovery rows get `attach_exchange()` called on them but the map itself is Alpaca-fed |
| RVOL on IEX | `hod_momo_enrichment.py` falls back to yfinance only when Alpaca IEX bars are empty; scanner-row RVOL (`_ensure_avg_volume`, `main.py:472`) is Alpaca-only |
| Ticker WS initial payload | `_build_ticker_fast` (`main.py:2238`) always uses Alpaca asset + Alpaca snapshot even when `discovery_provider=ibkr`; only the REST path (`_build_ticker_detail`) has an IBKR branch |
| Ticker snapshot fallback | `_fetch_ticker_snapshot_ibkr` falls back to Alpaca if the IBKR cache is empty |

### (C) Alpaca-only — no IBKR alternative exists

| Feature | Alpaca call | Function(s) | Used by |
|---|---|---|---|
| **News (all of it)** | `GET data.alpaca.markets/v1beta1/news` | `_check_news` (`main.py:536`), `_fetch_ticker_news` (`main.py:2201`), `_run_news_catalyst_scan` (`main.py:1386`) | Scanner news-flame flags, `/api/news-catalysts` (Catalysts tab), `/api/ticker/{symbol}` news panel, `/api/news/impact/{symbol}` (`routes/news.py`) and the whole `backend/news/` scoring stack (`sentiment.py`, `lexicon.py`, `ai_reasoning.py`, `impact.py`) |
| **Charts / OHLCV bars** | `GET data.alpaca.markets/v2/stocks/{symbol}/bars` | `bars.fetch_bars` (`backend/bars.py:45`) | `TickerChart.tsx`, `routes/strategy.py`, `strategy/setups_stream.py` (Bull Flag / ABCD / Gap-and-Go setup evaluation every 15s) |
| **RVOL / avg daily volume for scanner rows** | `GET .../v2/stocks/bars` (1Day) | `_ensure_avg_volume` (`main.py:472`) | Every gapper/gainer/loser/after-hours row's `rel_volume`, ticker detail |
| **Tradable symbol universe + broker flags** | `GET /v2/assets`, `GET /v2/assets/{symbol}` | `_get_tradable_symbols` (`main.py:396`), `_is_common_stock` (`main.py:369`), `_fetch_ticker_asset` (`main.py:2001`) | Alpaca discovery, after-hours universe, HOD Momo universe refresh (`_refresh_hod_momo_universe`, `main.py:710`), news-catalyst symbol filter, quote-panel "Broker listing" grid (tradable/shortable/marginable/attributes) |
| **After-hours scanner** | Full universe + snapshots, no IBKR branch at all | `_run_afterhours_discovery_scan` / `_run_afterhours_focus_scan` (`main.py:1026,1055`) | After Hours tab |
| **HOD Momo real-time trade engine** | Alpaca WS ticks feed `hod_momo.on_trade_update` for the ~6,000-symbol universe | `_ws_stream_loop` (`main.py:1257`) → `_handle_trade` | HOD Momo alerts — this is always Alpaca WS regardless of `discovery_provider` |
| **L2 tape recorder** | Alpaca WS trade prints | `l2/tape.py` `on_alpaca_trade()`, called from `_ws_stream_loop` | `l2.db` `tape_trades` table (`TAPE_SOURCE_ALPACA` constant) |
| **Health badge** | `GET /v2/account` | `_ping_health` (`main.py:580`), `_set_health_broker_keys_missing` (`main.py:565`) | `/api/health`, startup gate — missing Alpaca keys sets a health error and several scans no-op early |
| **SIP/IEX feed fallback** | 403 REST / 409 WS auto-fallback | `_try_fallback_to_iex` (`main.py:245`) | N/A — Alpaca-specific by definition |
| **Startup gate** | Missing `APCA_*` keys | `_alpaca_headers()` (`main.py:205`, duplicated in `bars.py:33`) | Nearly every function above returns early / raises 503 without valid Alpaca headers — **this is the sharpest edge**: even with `discovery_provider=ibkr`, several IBKR-mode code paths still call Alpaca-shaped enrichment (RVOL, news) before returning, so Alpaca keys can't just be blanked out today without also patching those early-returns |

## Config surface (entirely Alpaca-shaped today)

### `.env` keys

| Key | Purpose | Read in |
|---|---|---|
| `APCA_API_KEY_ID` | Alpaca API key | `main._alpaca_headers`, `bars._alpaca_headers` |
| `APCA_API_SECRET_KEY` | Alpaca secret | same |
| `APCA_API_BASE_URL` | Trading API base (default `https://api.alpaca.markets`) | asset/health/ticker-asset calls |
| `ALPACA_DATA_FEED` | `iex` or `sip` | `main._get_feed`, `bars._get_feed` |
| `ALPACA_SCAN_SYMBOL_CAP` | Emergency override for `SCAN_CAP_DEFAULT` | `main.py` |
| `NOVA_DISCOVERY_PROVIDER` | `alpaca` or `ibkr` — already defaults away from Alpaca today (see `.env` in this repo: `NOVA_DISCOVERY_PROVIDER='ibkr'`) | `_get_discovery_provider` |

### `backend/constants.py`

| Constant | Configures |
|---|---|
| `SCAN_CAP_DEFAULT` (800) | Legacy scan cap; env override is `ALPACA_SCAN_SYMBOL_CAP` |
| `ALPACA_WS_BACKOFF_CAP` (60.0) | Max Alpaca WS reconnect backoff |
| `DATA_FEED_DEFAULT` (`"iex"`) / `DATA_FEED_OPTIONS` | IEX vs SIP |
| `CHART_TIMEFRAMES`, `CHART_DEFAULT_TIMEFRAME`, `CHART_LOOKBACK_DAYS`, `CHART_DEFAULT_BARS`, `CHART_MAX_BARS` | Alpaca bars API params for charts |
| `DISCOVERY_PROVIDER_DEFAULT` (`"alpaca"`) / `DISCOVERY_PROVIDER_OPTIONS` | Scanner provider toggle — default is still `"alpaca"` in code; this repo's `.env` overrides it to `ibkr` |
| `IBKR_REPRICE_INTERVAL_SEC` | Replaces the Alpaca WS overlay when IBKR discovery is active |
| `TAPE_SOURCE_ALPACA` (`"alpaca"`) | `l2.db` `tape_trades.source` tag — **defined twice** in `constants.py` (~line 455 and ~line 532), same value both times; harmless today but worth collapsing to one definition whenever that file is next touched |

### API endpoints (`main.py` — no separate `routes/settings.py`)

- `GET /api/config` — returns Alpaca keys (masked), base URL, feed, discovery provider, `ibkr_connected`.
- `POST /api/config` — writes all of the above to `.env`, invalidates the asset cache.
- `GET /api/health` — Alpaca connectivity + `data_feed` + `feed_fell_back`.

## Frontend references

| File | What it shows |
|---|---|
| `frontend/src/components/SettingsPanel.tsx` | Alpaca API key fields, IEX/SIP feed selector, discovery-provider dropdown |
| `frontend/src/components/GlobalBarConnectionChip.tsx`, `HeaderConnectionStatus.tsx` | Global-bar IBKR / API connection chip and the gear-menu status cluster (IBKR scanner). Alpaca is never a header integration chip (`HEADER_INTEGRATION_CHIP_ORDER` omits it) — news/listing aux only, not the scanner feed |
| `frontend/src/utils/dataSourceMap.ts` | Per-surface attribution ("Scanner rows", "Quote & chart", "Level 2", "Broker listing", "Fundamentals") shown in the ticker side panel's Data Sources block — explicitly documents *"Price prefers IBKR cache; bars/chart still Alpaca"* |
| `frontend/src/utils/quoteFormat.ts`, `frontend/src/constants.ts` | `ALPACA_ASSET_ATTRIBUTE_LABELS`, `QUOTE_BROKER_SECTION_TITLE` ("Broker listing (Alpaca)"), `QUOTE_LISTING_FEED_VALUE`, `DATA_FEED_*`, `DISCOVERY_PROVIDER_*`, `SCANNER_DATA_SOURCE_*`, chart timeframe/lookback comments |
| `frontend/src/TickerChart.tsx` | Fetches the Alpaca-backed `/api/ticker/{symbol}/bars` |
| `frontend/src/components/TickerBrokerGrid.tsx`, `TickerDataSources.tsx`, `TickerDetailContent.tsx`, `SidePanel.tsx`, `pages/StockViewPage.tsx` | Carry `alpacaFeed` prop through to the broker-flags grid and data-sources panel |
| `frontend/src/ibkr/TradingTab.tsx` | Copy explicitly says *"Alpaca scanning stays read-only"* (this is also the Constitution's Invariant #7 in `AGENTS.md`) |
| `frontend/src/utils/dataSourceMap.test.ts` | Tests the Alpaca attribution strings above |
| `frontend/electron/sidecar.mjs` | Seeds `APCA_*` / `ALPACA_DATA_FEED` into the desktop build's `.env` |

## What it would take to reach true IBKR-only

In rough order of tractability (per the phased-rebuild decision in
`PROBLEM_LOG.md` 2026-07-14 — Alpaca stays wired up for all of these until
each is replaced, nothing is cut off today):

1. **Charts/bars** — `ib_async` supports `reqHistoricalData`; a new
   `backend/ibkr/bars.py` returning the same `{symbol, timeframe, bars}` shape
   as `bars.fetch_bars` could slot into `routes/strategy.py` and
   `TickerChart.tsx` with no shape changes downstream. Most tractable —
   flagged as the next concrete build.
2. **RVOL / asset universe / broker flags** — IB `reqHistoricalData` (daily)
   for avg volume, and `reqContractDetails` / a static exchange list in place
   of `/v2/assets`. Moderate effort, no external blocker.
3. **Health check** — trivial once IBKR is the sole provider: swap
   `_ping_health`'s Alpaca account call for `ibkr.client`'s own connection
   state.
4. **After-hours scanner** — needs an IB scan code equivalent to Alpaca's
   full-universe after-hours gap computation, or accept a smaller
   scanner-shortlist-only after-hours view (mirrors how gappers/gainers
   already work on IBKR).
5. **HOD Momo real-time feed** — flagged for a separate conversation, not a
   drop-in rebuild. Alpaca WS today streams ticks for the full ~6,000-symbol
   universe; IBKR retail market-data-line limits make that scale of
   simultaneous L1 streaming impractical without redesigning HOD Momo to only
   watch a shortlist (e.g. IB scanner candidates + anything already on the
   scanner tables) instead of the whole market.
6. **News** — flagged for a separate conversation. IBKR has no free news feed
   comparable to Alpaca's `v1beta1/news`; would require either a paid IBKR
   news subscription, a third-party provider (not Alpaca, not IBKR), or
   accepting Alpaca stays permanently as the news source even after
   everything else moves off it.

## Related

- `Scanner-Provider-IBKR-Primary.md` — original discovery-provider decision (2026-07-13)
- `IBKR-Orders-Locked-On-Live-Gateway.md` — IBKR connection/safety flags
- `PROBLEM_LOG.md` 2026-07-14 — IB Gateway disconnected / empty gappers root cause, and the phased-rebuild decision
- `CHANGELOG.md` 2026-07-14
