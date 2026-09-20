# 2026-08-25 — Large Cap swing scanner (ADR 014)

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed, scanner, product
- **Related:** `CHANGELOG.md` 2026-08-25 "New Large Cap swing table" · `PROBLEM_LOG.md` 2026-08-25 "IBKR ScannerSubscription.marketCapAbove is in millions, not raw dollars" · `architecture/decisions/014-large-cap-swing-table.md`

## Task

User wanted a "Gainers, but for large caps" scanner for swing trading (TSLA/NVDA/AMD/META/AAPL-class names), explicitly not a day-trade table -- small caps dominate the existing Gainers/Losers tables and the user cares less about today's % change than about unusual activity and multi-day setups. User asked to be interviewed one question at a time rather than handed a spec up front, then to have the plan written after enough was known.

## Goal

A new "Large Cap" scanner tab that: filters to large-cap, liquid names server-side (IB scanner, not a client-curated list); ranks on relative volume, ATR-relative range expansion, and 5-day/20-day change plus a composite score; never freezes (swing tables get reviewed on the operator's own schedule, not at a session boundary); fires its own breakout alerts separate from HOD Momo; and has a tunable cap floor without a code edit.

## Why it mattered



## What we changed

- New IBKR persistent scanner lease (`TABLE_LARGE_CAP`) with per-table server-side filters (`marketCapAbove`, `aboveVolume`, `stockTypeFilter`), via a new `LeaseSpec` dataclass that replaced the bare `(table, scan_code)` tuple `desired_leases()` used to return.
- New always-live carve-out in `scanner_session.py` (`_ALWAYS_LIVE`) -- the only table exempt from ADR 008's freeze-at-boundary contract; its roster survives the 04:00 session-key rollover instead of being cleared.
- New `backend/large_cap_metrics.py` (RVOL, ATR(14), 5d/20d change, 20d high/low, composite percentile-rank score), `backend/large_cap_alerts.py` (20-day breakout channel, its own dedupe, separate from HOD), `backend/large_cap_admin.py` (tunable config with `schema_version`), `backend/large_cap_reprice.py` (L1-tick glue), `backend/large_cap_hooks.py` (background fundamentals warm + daily-bar prefetch on roster admission).
- Extracted `backend/hod_tick_feed.py` out of `ibkr_bridge.py` to keep that file under the 400-line limit while adding the new Large Cap L1 branch.
- `GET/POST /api/large-cap`, `/api/large-cap/config`, `/api/large-cap/alerts`; registered the table across `scanner_tab_registry`, `scanner_push`, `scanner_persist`/`cache.py`, `integrity_live.py`.
- Frontend: new "Large Cap" tab (icon, nav count, module registry entry), `LARGE_CAP_COLUMNS`, new `ScannerTable` render cases for the new metric columns, WS patch plumbing for the new fields, default sort RVOL descending.
- ADR 014 recording the scan-code decision with live evidence, plus a `single-market-data-feed.mdc` update and an ADR 008 ledger amendment.

## How it works now

One IBKR `TOP_VOLUME_RATE` lease (IB's own relative-volume-rate ranking) filtered to `marketCapAbove=50000` (millions of USD -- see units gotcha below), `aboveVolume=1000000`, `stockTypeFilter=CORP`. A ranked name is admitted immediately with `price=None` (ADR 010 decision 5); the L1 hot path fills price and recomputes RVOL/ATR-expansion on every tick. RVOL and days-to-earnings read `fundamentals.py`'s cache dict directly (never call `fetch_fundamentals`, which can block on a cold yfinance round trip) -- a background thread started from the roster-commit hook warms that cache for newly admitted symbols instead. ATR/5d/20d/20d-high-low read `bars_store` with a 15-minute TTL cache layered on top (daily bars don't change intraday) and schedule a paced background fill on a miss, never blocking. The composite score is computed at read time across the whole current roster (percentile ranks of `abs()` magnitude, not raw values, so RVOL multiples and ATR multiples are never summed in mismatched units) -- it cannot be computed per-row independently. Breakout alerts fire through the existing generic `alerts.dispatch` fan-out under a new event type, with their own per-symbol-per-direction once-per-session dedupe; they never touch `hod_momo.on_trade_update`, and `hod_roster_hooks.on_hod_roster_commit` already whitelists only Gappers/Gainers/Afterhours, so Large Cap needed no extra guard to stay out of HOD's active set.

## Why this approach

- **`TOP_VOLUME_RATE`, not a curated universe.** A curated ~100-300 name list was the obvious first idea, but Nova's total live L1 budget is 100 lines shared across every table -- a 300-name live-streamed table is architecturally impossible without starving Gainers/Losers/HOD/Trader. One IB lease with server-side filters stays inside the existing 50-row-per-scan-code ceiling and reuses the exact roster-admission/L1/freeze machinery every other table already has.
- **`TOP_VOLUME_RATE`, not `MOST_ACTIVE`.** Verified live (`tools/ibkr_scan_params.py` against the production Gateway) rather than assumed: `MOST_ACTIVE` ranks by dollar volume, which correlates directly with market cap, so a cap-gated `MOST_ACTIVE` table returns the same NVDA/AAPL/TSLA/MSFT/AMZN/GOOGL/META crowd every day and defeats the point of an "abnormal activity" table. `TOP_VOLUME_RATE` is IB's own relative-volume-rate ranking -- the literal built-in implementation of the signal the user asked for -- and its live roster included genuinely different names (SPCX, USB, CMCSA, ACN, LITE, GLW, NOW, NEE) alongside the familiar mega-caps.
- **Units bug caught before it reached production code.** A first live probe with `marketCapAbove` in raw dollars returned zero rows on every scan code tried, including ones whose baseline plainly had qualifying names. Reading IB's own `reqScannerParameters()` XML (not guessing) showed the wire field is `marketCapAbove1e6` -- millions of USD. Logged to `PROBLEM_LOG.md` before writing the `LeaseSpec`/lease-open code so the constant was correct from the first line, not discovered later against a live desk.
- **Always-live carve-out, not all-day min/max minute constants.** `_LIVE_FROM_MIN[TABLE_LARGE_CAP]=0` / `_FREEZE_AT_MIN[TABLE_LARGE_CAP]=1440` would have worked numerically but hidden the real intent (a table that is a deliberate exception to ADR 008, not a table with an unusually long session) behind two magic numbers. A named `_ALWAYS_LIVE` set that `table_is_live()`/`table_should_be_frozen()` check explicitly documents the exception at the point future readers will look.
- **Percentile-rank score, not summed raw metrics.** RVOL is a multiple (e.g. 2.5x), ATR expansion is a multiple, and 20-day change is a percentage -- summing them directly would let whichever metric happens to have the largest numeric range dominate the score by accident. Ranking each component within the current roster and blending the ranks keeps the weights (`LARGE_CAP_SCORE_WEIGHTS`) meaningful regardless of the metrics' native units.
- **Fundamentals cache read, never `fetch_fundamentals()` call, on the tick path.** `fetch_fundamentals()` does a synchronous yfinance HTTP call (up to 5s) on a cache miss. Calling it from `apply_l1_quote` -- reached from IB tick callbacks -- would have reintroduced exactly the kind of hot-path blocking the single-market-data-feed rule forbids. Warming the cache from a background thread on roster admission instead means the tick path only ever does a dict lookup.
- **Own alert channel, not HOD Momo.** The user explicitly asked for day-trade chimes and swing signals to never mix. Feeding Large Cap into HOD's engine would also have competed with HOD's reserved L1 pool for the same shared budget HOD was designed to protect.
- **`hod_tick_feed.py` extraction, not inlining the Large Cap branch into an already-397-line file.** `ibkr_bridge.py` was at the file-size-limits.mdc ceiling before this task. Rather than let a live-trading-critical shared file cross the limit, the self-contained HOD active-set tick tail (no table-cache side effects of its own) was moved out first, creating headroom for the new branch without touching the risky per-table reprice blocks.

## Verification

- Live probe against the production Gateway (`tools/ibkr_scan_params.py`) established the scan-code choice and the units/filter gotchas with real IB responses, not assumption.
- `pytest backend/tests -q` (excluding two pre-existing, unrelated collection/native-library issues): 1305 passed, including 60+ new Large Cap tests (`test_large_cap_metrics.py`, `test_large_cap_alerts.py`, `test_large_cap_admin.py`, `test_large_cap_reprice.py`, `test_large_cap_hooks.py`, `test_hod_tick_feed.py`, `test_scan_large_cap_route.py`, plus new cases in `test_scanner_session_adr008.py` and `test_ibkr_bridge.py`).
- Frontend: `tsc -b` clean, `vite build` clean, `vitest run` 709/709 passed, `eslint .` clean apart from pre-existing warnings in files this task never touched.
- Live end-to-end against the running production Gateway: restarted the local API (found its listening socket already dead from an unrelated pre-existing wedge, unrelated to `NOVA_API_RELOAD` which was off the whole time), confirmed IB reconnected cleanly, hit `/api/large-cap` and got a real 50-row roster, opened a raw WebSocket, sent `set_active_tab: ["large_cap"]`, and received a real `price_patch` with live IBKR prices and computed RVOL for AAPL/AMD/AMZN. Confirmed `/api/movers` Gainers stayed `table_state: live` with a sub-1-second-old roster and real prices throughout (blast-radius check), and `ib_loop_lag_ms.wedged`/`http_loop_lag_ms.wedged` both stayed `false`. Took a browser screenshot of the rendered "Large Cap" tab showing real prices, RVOL-descending default sort, and colored change/5D/20D columns.

## Follow-ups

- Frontend historical date-picker browsing is not wired for Large Cap (`fetchHistoryData`/`fetchHistoryDates` in `useScannerData.ts` still only cover gappers/movers/afterhours); the backend `/api/history/large_cap/{date}` path is ready whenever that's wanted.
- `Mkt Cap`/`Float` columns only populate after a symbol's first L1 tick (same honest-empty pattern as price) -- acceptable today since the background fundamentals warm runs immediately on roster admission, but worth knowing if a row looks incomplete right after a restart.
- The pre-existing dead-listening-socket issue found on the running API process during verification was not investigated further (out of scope for this task) -- worth a dedicated PROBLEM_LOG entry and root-cause pass if it recurs.

## Keywords

Large Cap, swing trading, ADR 014, TOP_VOLUME_RATE, marketCapAbove, scanner lease, RVOL, ATR expansion, always-live, LeaseSpec, composite score, breakout alert, IBKR scanner
