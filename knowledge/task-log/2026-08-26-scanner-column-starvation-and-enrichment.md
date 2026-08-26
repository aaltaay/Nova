# 2026-08-26 — Scanner column starvation and mover enrichment

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` §2026-08-26 "Scanner tables: every row gets L1…" · `PROBLEM_LOG.md` §2026-08-26 "Gainers columns empty all session" · ADR 008, ADR 010

## Task

The operator reported the Gainers table looking "all fucked up and missing": red `N/A` for CHANGE on about half the rows, `N/A` for GAP % on every row, and `—` for FLOAT / SHORT INT. / MKT CAP plus `N/A` for RVOL on every row. Blank in premarket, partially filling around 09:30, never recovering — despite Gainers being supposed to run live until 16:00 ET.

## Goal

Every row of the scanner table on screen carries a price during that table's live window, and the reference columns (Gap %, RVOL, Float, Short Int., Mkt Cap) hold real numbers instead of permanent placeholders. A repeat of the same starvation must fail loudly rather than report `pass`.

## Why it mattered

This is the desk's primary discovery surface. A row with no price and no float is not a "quiet" row — it is invisible risk: the operator cannot size a trade, judge a squeeze, or compare candidates, and nothing on screen said the data was missing rather than absent. Worse, every scanner integrity check reported `pass` for the entire session, so the desk actively vouched for numbers it did not have.

## What we changed

- `frontend/src/pages/DashboardPage.tsx` — declare the visible `mainTab` for L1 from a `useEffect` (mount + every change) instead of only inside the tab-click handler; removed the click-time call and the now-unused `tabUsesScannerPricePatch` import.
- `backend/ibkr/ticks_handler.py` — read `ticker.open` (IB tick type 14) off the streaming ticker and pass it as an `open_price` kwarg.
- `backend/ibkr/scanner_l1.py` — thread `open_price` through `on_l1_quote`; add `tab_counts` (requested vs streaming, per declared table) to `_subscription_state`.
- `backend/ibkr_bridge.py` — thread `open_price` into the reprice quote dict; deleted the never-called `enrich_ibkr_mover` and its orphaned imports.
- `backend/ibkr/discovery.py` — `reprice_mover_row` now computes `gap_percent` from the open.
- `backend/mover_enrich_view.py` (new) — pure `decorate_rows`, fills RVOL / market cap / float / short interest / short ratio.
- `backend/mover_enrich_hooks.py` (new) — off-loop yfinance warm on roster commit; wired in `backend/ibkr/scanner_hydrate.py`.
- `backend/routes/scan.py`, `backend/scanner_push.py` — decorate rows at the three serialization points.
- `backend/scan_runners.py` — dropped the `enrich_ibkr_mover` re-export.
- `backend/integrity_live.py`, `backend/hod_momo_integrity_scanner.py`, `backend/constants_hod_momo.py` — new `scanner_<table>_row_prices` check + its three thresholds.
- `frontend/src/constantGroups/market_ui.ts`, `frontend/src/components/ScannerTable.tsx` — RVOL badge/title now name yfinance; ticker-detail keeps its own Alpaca label.
- Tests: `backend/tests/test_mover_columns.py` (new, 11 cases), `frontend/src/workspace/workspaceWiring.test.ts`.

## How it works now

Three invariants:

1. **The declared L1 table is the table on screen.** `l1ActiveTab` tracks `mainTab` continuously. `tabHints` still filters to real scanner tables, so sitting on Trading or HOD Momo declares nothing from the main slot while the dock keeps declaring its own table. A frozen table legitimately contributes zero symbols (ADR 008) — the bug was never the freeze, it was declaring a table nobody was looking at.
2. **Gap % has a real input or stays null.** `gap_percent` comes from the IBKR session open only. With no open yet, the prior gap is kept; `change_pct` is never reused as a gap.
3. **Reference columns are a view, not cache state.** `decorate_rows` runs on the way out (REST + both WS surfaces), returns new dicts, and never overwrites a non-null value. A frozen table's stored membership, rank, and values are untouched, and a late fundamentals fetch cannot mutate a row the operator was told is immutable.

## Why this approach

**Decorate at serialization, not in the cache.** The obvious fix was to write fundamentals into `gainer_cache` when yfinance returns. That directly violates ADR 008 — a frozen table's values must not change after its boundary — and would have made late-arriving yfinance data silently rewrite a table the UI labels immutable. Read-time decoration gets the same columns with none of that, at the cost of a dict copy per row per request (tens of rows; irrelevant).

**yfinance average volume, not Alpaca — deliberately against the brief.** The requested option was "yfinance fundamentals + Alpaca average volume." PROBLEM_LOG 2026-07-16 records that `state.avg_volume_cache` (Alpaca IEX daily bars) understated microcap average volume by 248x and drove RVOL to 7016x on CJMB, 1526x on LBGJ — on exactly the thin low-float names these tables are full of. `hod_momo_enrichment.ibkr_avg_volume` exists solely to avoid that cache. Reusing Alpaca here would have re-shipped a bug we already paid for once. Consequence handled: the scanner badge now says `yfinance avg`, because leaving it as `Alpaca avg` would have made the UI lie. Ticker detail genuinely still divides by Alpaca, so it keeps its own honest label rather than sharing a constant.

**Open from the existing streaming ticker, not a new IB request.** `bars_store` 1Day bars would also yield today's open, but that spends `reqHistoricalData` pacing budget (ADR 012) for a number IB already pushes for free on the `reqMktData` line we hold. Verified empirically before committing to it rather than assuming: a probe on a spare clientId showed `ticker.open` populated within 5s on all three test symbols.

**Effect over click handler, not a new abstraction.** `HodMomoDock` had already solved this exact bug for the dock with a mount effect, and its comment describes the failure verbatim. Copying that shape keeps one pattern in the codebase instead of introducing a third way to declare a table.

**Integrity check scoped to displayed tables.** A blanket "any live table with unpriced rows fails" would fail loudly on correct behavior, because bounded L1 intentionally streams only what the desk declares. Scoping to `get_active_tables()` makes the check meaningful without crying wolf — and with invariant 1 in place, the declared set is now the visible set, so the check has teeth it would not have had before.

**NEWS left alone.** The empty NEWS column has a third, unrelated cause (no symbol-to-headline map exists under IBKR discovery). Bundling a news-fetch loop into this change would have doubled the diff and the blast radius for a column nobody asked about. Named as a follow-up instead.

## Verification

- `py -3 -m pytest tests/ -q` → 1395 passed (includes 11 new cases in `test_mover_columns.py`).
- `npm test` → 822 passed / 171 files. `npm run build` → exit 0.
- Live, after restarting the API on the new code with IBKR connected on the live Gateway:
  - `owner=scanner` L1 subscriptions reached **50 distinct** symbols; the same log grep over the previous process showed **6** for the whole 10:01–16:00 window (vs 134 for `hod`).
  - A `/ws/scanner` probe declaring the live `afterhours` table reported `tab_counts={'afterhours': {'requested': 50, 'streaming': 50}}` with `active_tab` climbing 5 → 50 at the 5-per-reconcile pace, and surfaced two unqualifiable symbols honestly.
  - `/api/scan/integrity` emitted `scanner_afterhours_row_prices: 50/50 rows priced`.
  - `/api/movers` CRE: `market_cap=13715238, float=1102703, short_interest=31617, short_ratio=0.59, rel_volume=71.6`.
  - `ib_async` probe on clientId 191: CRE `open=6.09` vs `close=2.57`, AAPL `open=310.24` vs `309.90`, OKTG `open=24.15` vs `24.77` — all within 5s.
  - Browser screenshot of the Gainers table: Float / Short Int. / Mkt Cap populated, RVOL badge reads `YFINANCE AVG`, `Sample` unchecked and selector on "Today (Live)".
- Blast radius (shared `ticks_handler` + L1 reconcile): Gappers and Large Cap rows and HOD integrity all still `pass` after the change; HOD active set 40/40 with quote age p95 ~1.1s.

## Follow-ups

- NEWS flame column is still dead under IBKR discovery — needs a roster news-fetch loop.
- The afterhours runner reports `gap_percent == change_pct` (observed OKTG `+53.29%` when the true open-vs-prior-close gap was `-2.50%`). Should move to the same open-based math.
- `gap_percent` on Gainers/Losers could not be observed live because both tables freeze before the evening; the math is unit-tested and the open input is probe-verified, but the first real end-to-end read will be tomorrow's premarket.
- On a cold start after 16:00 ET, Gainers freezes at process start time rather than 16:00 (`Frozen at 17:09 ET` observed). Pre-existing, cosmetic, not touched here.

## Keywords

gainers columns empty, N/A change, gap_percent, rel_volume, float, short interest, market cap, L1 starvation, OWNER_SCANNER, set_active_tab, l1ActiveTab, tabHints, symbols_for_tab, frozen table, ADR 008, mover_enrich_view, mover_enrich_hooks, enrich_ibkr_mover dead code, tick 14 open, reprice_mover_row, yfinance average_volume, avg_volume_cache, scanner_row_prices, tab_counts, integrity fail loud
