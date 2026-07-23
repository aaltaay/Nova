---
title: Scanner Data Provider Decision (IBKR primary vs Alpaca SIP)
date: 2026-07-13
status: implemented
updated: 2026-07-23
---

# Scanner Data Provider — IBKR primary (no Alpaca SIP)

## Status (2026-07-23)

**Soft-toggle retired for the product UI.** Scanner discovery is **IBKR-only**:
`DISCOVERY_PROVIDER_DEFAULT=ibkr`, `DISCOVERY_PROVIDER_OPTIONS=("ibkr",)`,
Settings no longer offers Alpaca as a scanner source, and `/api/config` coerces
any stale `alpaca` value to `ibkr`. Alpaca remains for **news headlines + Assets
listing flags** only. Alpaca scanner adapters stay in-repo for tests/emergency
but are not selectable. Undo = code change, not Settings.

## Decision

**Do not buy Alpaca Algo Trader Plus ($99 SIP).**  
**Primary live discovery → Interactive Brokers market scanners + L1 subscriptions.**  
**Alpaca scanner codepaths kept in-repo but not exposed as a product option.**  
**Keep free Alpaca only for non-scanner needs: news headlines, listing metadata.**

## Why (strategy-grounded)

Warrior Trading Scanning 101 + Strategies Ch.3/7 (Pinecone + Obsidian):

1. Morning workflow is **Top Gainer / Top Gapper list scanners**, not a custom full-universe poll.
2. Those scanners already search the whole market and return a short list (~40–60 names meeting ≥5% etc.).
3. Ross then focuses on the **top 3–4 leading gainers** after checking % gain, price, float, RVOL, news freshness, charts, L2.
4. Gap and Go stock finding = **Gap Scanner** → Five Pillars → charts → Level 2 entry.

Nova only needs the **top of a universe-wide ranked list**, not 200 custom gapper rows. IBKR `reqScannerSubscription` (≤50 results, server-side universe search) matches that model.

## What each vendor is for

| Job | Provider | Notes |
|-----|----------|-------|
| Live top gappers / gainers / most active | **IBKR scanner** | Requires L1 Networks A/B/C or Equity Add-On |
| Quotes on the shortlist | **IBKR L1** | Uses market-data lines (~50 is fine) |
| Level 2 + orders | **IBKR** | Already in Nova |
| News flame / catalyst headlines | **Alpaca free news** (keep) | Does **not** require SIP |
| Float / mkt cap / short interest | **yfinance** (already) | Not Alpaca |
| Full-universe custom gap% over ~4k symbols | Alpaca SIP | **Reject** — strategy doesn't need it; costs $99 |
| Free IEX as live scanner | Alpaca Basic | **Reject for live** — thin tape, misses movers |

## Soft-toggle (do not destroy Alpaca)

When implementing, add constants (defaults keep current behavior until flipped):

```
DISCOVERY_PROVIDER = "alpaca" | "ibkr" | "hybrid"   # default alpaca until IBKR path proven
MOVER_PROVIDER     = "alpaca" | "ibkr"
NEWS_PROVIDER      = "alpaca"                       # only implemented source today
QUOTE_STREAM_PROVIDER = "alpaca" | "ibkr"
```

- Extract Alpaca discovery/stream into `providers/alpaca/` without behavior change first.
- Add `providers/ibkr/scanner.py` that normalizes IBKR scanner rows into the existing gapper/mover cache shape.
- Flip `DISCOVERY_PROVIDER=ibkr` only after side-by-side validation.
- Alpaca modules stay importable so rollback is a constant change, not a rewrite.

## IBKR subscriptions required for this path

1. **L1 streaming:** NYSE A + Network B + NASDAQ C (~$4.50) **or** Snapshot Bundle + Equity/Options Add-On.
2. **L2 (small-cap depth):** NASDAQ TotalView-OpenView (~$16.50); OpenBook optional for NYSE names.
3. Gateway running; `IBKR_ENABLED=true`.

## Risks / gaps to validate before flipping the flag

1. Premarket: confirm IBKR scan codes cover premarket % vs prior close (gapper) vs all-day gainer.
2. Data-line budget: ~50 L1 symbols + 3 L2 must fit account allotment (boosters if not).
3. API/off-platform: some depth packages need EDS for non-TWS API — verify TotalView works via Gateway/`ib_async`.
4. News remains Alpaca-free; if Alpaca news ever requires paid data, replace news provider separately.
5. HOD Momo today listens to a broad Alpaca WS universe — under IBKR it must shrink to scanner shortlist + watched symbols (acceptable for Ross-style focus).

## Undo

Set providers back to `alpaca`. No deletion of Alpaca scan/WS/news code in the transition PR.

## Implementation (2026-07-13)

Shipped as a clean, self-contained module rather than threading IBKR calls into
the existing Alpaca-shaped functions:

- **`backend/ibkr/discovery.py`** (new) — `scan_symbols()` wraps
  `reqScannerDataAsync`, `snapshot_quotes()` wraps `qualifyContractsAsync` +
  `reqTickersAsync` (batched). `get_gappers()` / `get_gainers()` / `get_losers()`
  return rows in the **exact same dict shape** Alpaca's path already produces
  (`_compute_gappers` / `_build_mover_entry` in `main.py`), so the existing
  news/fundamentals/RVOL/exchange enrichment pipeline needed zero changes.
- **Scan codes:** `TOP_OPEN_PERC_GAIN` (gappers, today's open vs prior close),
  `TOP_PERC_GAIN` / `TOP_PERC_LOSE` (intraday movers). Location `STK.US.MAJOR`,
  50-row IB cap. All in `constants.py` (`IBKR_SCAN_*`).
- **Thread → event-loop bridge:** `main.py`'s scan loop runs Alpaca-style sync
  functions via `run_in_executor` (a worker thread), but `ib_async`'s `IB`
  instance is bound to the event loop that called `connectAsync()`. Added
  `ibkr/client.run_coro(coro, timeout)` using
  `asyncio.run_coroutine_threadsafe` so the worker thread can safely await
  IBKR coroutines. `main.py`'s `_run_ibkr()` wraps this with try/except →
  degrades to an empty scan on any Gateway hiccup rather than crashing the tick.
- **Provider toggle:** `DISCOVERY_PROVIDER` (`alpaca` default | `ibkr`), env
  override `NOVA_DISCOVERY_PROVIDER`, persisted via `/api/config` same as the
  existing Alpaca `data_feed` toggle. Frontend: new "Scanner Source" dropdown
  in Settings (`SettingsPanel.tsx`) + header badge
  (`SCANNER_DATA_SOURCE_LABELS`/`_TITLES` in `constants.ts`).
- **News/fundamentals unchanged either way** — `_ensure_avg_volume`,
  `_check_news`, `_fetch_fundamentals_batch` still run against Alpaca/yfinance
  regardless of discovery provider, exactly as this doc specified.
- **Bug found + fixed during live validation:** Alpaca's WS trade stream
  (`_handle_trade` in `main.py`) was still overlaying live "price" onto
  IBKR-sourced cache rows without a matching recompute basis (Alpaca ticks vs
  an IBKR-snapshot `prev_close`), producing internally-inconsistent rows
  (price/change_pct/prev_close no longer added up). Fixed by early-returning
  from `_handle_trade` when `discovery_provider == "ibkr"` — IBKR rows now only
  refresh on the normal scan cadence (20s for gainers/losers) instead of a
  mixed dual-feed. See `PROBLEM_LOG.md` 2026-07-13.
- **Also extracted** `backend/market.py` (`now_et`/`in_premarket`/
  `in_market_hours`/`in_after_hours`) out of `main.py` — required by
  `file-size-limits.mdc` before adding new code to an already-oversized file;
  zero behavior change, pure move.
- **Verified live** (2026-07-13, market hours): switched `discovery_provider`
  to `ibkr` against the running server, confirmed `/api/movers` returns live
  IBKR scanner data with self-consistent price/change/prev_close/exchange
  fields, and confirmed the frontend header badge + Settings dropdown reflect
  the switch (screenshots taken via agent-browser, not committed).
- **Not yet done:** gapper path (`TOP_OPEN_PERC_GAIN`) verified live via a
  standalone scan (10 symbols returned) but not exercised end-to-end through
  `/api/gappers` this session — premarket window had already passed. Ticker
  detail page (`/api/ticker/{symbol}`) and HOD Momo universe still use Alpaca
  regardless of this toggle (out of scope — see Risk #5 above).

## Related

- Course: BA101 Ch.12 Scanning 101; SS101 Ch.3 / Ch.7 Gap and Go
- Nova: `Automation-Strategy-Backbone.md`, IBKR module CHANGELOG 2026-07-10
- Alpaca SIP pricing: Algo Trader Plus ~$99/mo — explicitly out of scope
