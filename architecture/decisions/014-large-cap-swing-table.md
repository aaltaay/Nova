# ADR 014 — Large Cap swing table: always-live session, single filtered lease

**Status:** Accepted · **Date:** 2026-08-25

## Context

Every existing IBKR scanner table (Gappers, Gainers, Losers, Afterhours) exists to serve
Nova's day-trading product: freeze at a session boundary and hold an immutable snapshot
(ADR 008). A swing-oriented "Large Cap" table has a different contract — the operator
reviews it whenever they want, not once at a fixed boundary, and it should never go stale
just because RTH ended. `scanner_session.table_is_live()` / `table_should_be_frozen()`
only recognize tables present in `_LIVE_FROM_MIN` / `_FREEZE_AT_MIN`; a table absent from
both returns `False` from `table_is_live()` and can never satisfy `can_commit_roster()`.
An always-live table is therefore a deliberate carve-out in the session model, not a
parameter tweak.

Separately, `_open_lease()` (`backend/ibkr/scanner_stream.py`) builds every
`ScannerSubscription` from a fixed set of module constants
(`IBKR_SCAN_INSTRUMENT`, `IBKR_SCAN_LOCATION`, `IBKR_SCAN_ABOVE_PRICE`) plus the
`scan_code` from `desired_leases()`. No existing table applies a per-table filter such as
a market-cap floor. IB's `ScannerSubscription` natively supports `marketCapAbove` and
`aboveVolume`, so a large-cap universe can be expressed as one server-side-filtered lease
instead of a client-curated symbol list — but the lease-open/reconcile/watchdog code path
needs to compare more than `scan_code` to decide whether a lease is still current.



## Decision

1. **One persistent lease, scan code `TOP_VOLUME_RATE`, in every session period
   including `PERIOD_CLOSED`.** `TOP_VOLUME_RATE` ranks by IB's own volume-rate
   (today's pace vs. average), which is IB's native implementation of "unusual volume,
   direction-agnostic" — the signal actually requested. Verified live against the
   production Gateway (`tools/ibkr_scan_params.py`, 2026-08-25): with
   `marketCapAbove=50_000` ($50B, in millions per IB's wire format — see gotcha below),
   `aboveVolume=1_000_000`, `abovePrice=20`, `stockTypeFilter="CORP"`, `TOP_VOLUME_RATE`
   returned 50 pure single-name large-cap equities (`MRNA, INTC, NVDA, SPCX, USB, MU,
   CMCSA, T, ACN, TSLA, AAPL, AMD, LITE, GOOGL, NFLX, ...`) that differ meaningfully day
   to day, unlike a static top-N list.
2. **`MOST_ACTIVE` is rejected.** Same live probe: with identical filters, `MOST_ACTIVE`
   returned the same mega-cap dollar-volume crowd every time
   (`NVDA, INTC, TSLA, AAPL, AMZN, MSFT, GOOGL, META, ...` — essentially the Mag-7-plus
   set), because it ranks by dollar volume, which correlates directly with market cap.
   A table gated on market cap and ranked by dollar volume would look nearly identical
   every day and would not find the "abnormal activity" signal this table exists for.
3. **Filter unit gotcha, fixed before it reached production code.**
   `ScannerSubscription.marketCapAbove` is documented in IB's live
   `reqScannerParametersAsync()` XML as wire code `marketCapAbove1e6` with suffix
   `*1,000,000` — the field is **millions of USD**, not raw dollars. A first probe using
   raw dollars (`50_000_000_000`) returned zero rows on every scan code, including ones
   whose baseline plainly contained qualifying names. `aboveVolume` is unaffected (raw
   share-count `IntField`, no scaling). See PROBLEM_LOG 2026-08-25.
4. **`stockTypeFilter="CORP"` is required to exclude ETF/ETN/REIT/CEF pollution.**
   `instrument="STK"` alone does not exclude ETFs — they are `STK`-typed contracts in
   IB's model. Without this filter, `TOP_VOLUME_RATE` and `HOT_BY_VOLUME` both returned
   ETFs (`IBIT, GLD, SCHD, QQQ, XLF, SPY, ...`) mixed into the roster. The plain wire
   value is `"CORP"`; the XML-internal label `"inc:CORP"` does **not** work as a filter
   value and silently no-ops.
5. **`LeaseSpec` replaces the bare `(table, scan_code)` tuple.** `desired_leases()`
   returns a small dataclass carrying `table`, `scan_code`, and optional
   `market_cap_above` / `above_volume` / `stock_type_filter`. `_open_lease()` and the
   reconcile/watchdog comparison in `scanner_stream.py` compare the full spec, not just
   `scan_code` — so a runtime change to the cap floor (Step 8, tunable config) correctly
   triggers a resubscribe instead of being silently ignored by the "already have this
   scan_code" short-circuit.
6. **Always-live is a named carve-out in `scanner_session.py`, not a numeric trick.**
   `TABLE_LARGE_CAP` is added to a `_ALWAYS_LIVE` set that `table_is_live()` and
   `table_should_be_frozen()` check explicitly (rather than encoding it as
   `_LIVE_FROM_MIN[TABLE_LARGE_CAP] = 0` / `_FREEZE_AT_MIN[TABLE_LARGE_CAP] = 1440`,
   which would work numerically but hide the intent behind a magic pair of minute
   constants). `reconcile_session_tables()` still bumps `large_cap`'s `session_key` at
   the 04:00 rollover for bookkeeping consistency with other tables, but does **not**
   clear `large_cap_cache` — the roster persists across the rollover exactly as the
   underlying IB lease does.
7. **Roster admission stays name-only (ADR 010 decision 5).** A ranked name becomes a
   row immediately with `price=None`; the L1 hot path fills price. No cold
   `snapshot_quotes` gate.
8. **Daily-bar metrics are local reads first, background IB fills on miss — never a
   blocking request.** RVOL, days-to-earnings, and direction come from data already on
   hand (`fundamentals.py` yfinance cache: `average_volume`, `earnings_date`). ATR(14),
   5-day/20-day change, and the 20-day high/low come from
   `bars_store.read(sym, "1Day", 21)`; a miss schedules
   `historical_service.schedule_fill(..., priority="background")` (fire-and-forget, paced,
   sheds under wait per ADR 012) rather than blocking roster commit or L1 ticks. At ~50
   rostered symbols this is at most 50 background daily-bar fills, an order of magnitude
   below the chart/detail historical budget.
9. **Large Cap is excluded from HOD Momo admission.** ADR 008 decision 5's active-set
   union (Gappers ∪ Gainers ∪ Afterhours ∪ Former Momo) is unchanged. Large Cap alerts
   (20-day high/low break confirmed by RVOL >= 2x) run on their own dedicated alert
   channel, separate from HOD's day-trade chimes.

## Consequences



## Rejected alternatives

- **Curated ~100-300 name universe (S&P 100 ∪ Nasdaq-100), not an IB lease.** Rejected —
  Nova's total live L1 budget is `IBKR_L1_STREAM_BUDGET = 100` lines shared across
  Gainers, Losers, HOD's reserved pool, the open ticker, and Trader tabs. A 300-name
  live-streamed table is architecturally impossible without starving every other table;
  only the visible top rows could ever be live, the rest permanently stale.
- **`MOST_ACTIVE` as the scan code.** Rejected on live evidence (decision 2 above) — it
  is dollar-volume ranked, which is materially the same ranking as market cap. Gating on
  cap and ranking on cap-correlated volume returns the same names every day and defeats
  the purpose of an "abnormal activity" table.
- **Two-lease union (`TOP_PERC_GAIN` + `TOP_PERC_LOSE`), each with `marketCapAbove`.**
  This was the documented fallback if no single code proved direction-agnostic and
  filter-compatible. Not needed — `TOP_VOLUME_RATE` satisfied both requirements in the
  live probe, so the simpler single-lease design ships instead.
- **yfinance for daily bars (ATR / 5d / 20d change).** Rejected — would put a
  non-IBKR source behind a price-derived alert trigger (20-day high/low break),
  violating `single-market-data-feed.mdc`'s IBKR-only price rule. `bars_store` already
  holds IBKR-sourced daily bars for symbols warmed by chart/HOD; Large Cap reads that
  store and schedules its own background fills through the same paced
  `historical_service`, never a second source.
- **Feed Large Cap into the existing HOD Momo alert engine.** Rejected — mixes a
  multi-day swing signal (20-day breakout) into an engine built and tuned for intraday
  momentum chimes, and would compete with HOD's reserved L1 pool for the same
  `IBKR_L1_STREAM_BUDGET`. A separate alert channel keeps the two products legible.

## Related

- `architecture/decisions/008-persistent-ibkr-scanner-rosters.md` — session-owned roster
  model this ADR amends with an always-live carve-out.
- `architecture/decisions/010-ib-loop-isolation.md` — hot/cold work classification;
  daily-bar background fills follow the COLD classification already established there.
- `architecture/decisions/012-local-first-chart-bars.md` — store-first bars + paced
  `historical_service`, reused unmodified for Large Cap's daily-bar metrics.
- `tools/ibkr_scan_params.py` — the live diagnostic that produced the evidence in
  decisions 1-4.
- `PROBLEM_LOG.md` 2026-08-25 — `marketCapAbove` units + `stockTypeFilter` value gotchas.
- `.cursor/rules/single-market-data-feed.mdc` — rule 6 extended with the `large_cap`
  table entry and its always-live exemption.
