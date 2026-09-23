# Rebuilt leaderboard (ADR 023) and the S5 rolling universe

Offline research tool. It rebuilds the **whole-market, per-minute** scanner
leaderboard from the Massive minute flat files and writes it into Nova's
leaderboard store (`backend/leaderboard/store.py`) as `source="reconstructed"`,
`board="market"`. The same rows are the S5 rolling universe of
`knowledge/obsidian/03-Nova-Decisions/Bot-Trading-Plan.md` section 2f: "top-3 %
gainer with at least 5x relative volume at the minute of the trade".

Nothing in `backend/` imports this directory. It does import `backend/leaderboard`
(`rows.make_row`, `ranking.rank_rows` and its presets, `store`) so a rebuilt row has
the recorded row's shape and is ranked by the function playback and live
auto-record call.

## Commands (from the repo root)

```text
py -3 research/leaderboard/build_leaderboard.py --date 2026-09-21
py -3 research/leaderboard/build_leaderboard.py --start 2026-09-08 --end 2026-09-21
py -3 research/leaderboard/build_leaderboard.py --date 2026-09-21 --dry-run      # build, write nothing
py -3 research/leaderboard/build_leaderboard.py --date 2026-09-21 --top 200 --db C:\tmp\lb.sqlite3
py -3 research/leaderboard/s5_universe.py --date 2026-09-21 --from 07:00 --to 09:30
py -3 research/leaderboard/spot_check.py --date 2026-09-21 --minutes 07:05 07:42 08:30 09:31 09:58
cd backend && py -3 -m pytest tests/test_leaderboard_reconstruct*.py -q
```

The store defaults to `leaderboard.store.path()` -- `NOVA_LEADERBOARD_DIR`, else
`F:\Nova\leaderboard\leaderboard.sqlite3`. A rebuild is idempotent: it deletes that
day's `(date, reconstructed)` rows and coverage (`store.replace_day`) and writes them
again in hourly transactions; recorded rows are never touched. 50-72 s and
~96,000 rows (~18 MB of store) per day on the trading PC (one minute file, twenty prior minute files,
a Python ranking pass over ~4 million symbol-minutes). Needs `duckdb`, `pandas`,
`numpy` (installed locally; research convention, not in `requirements.txt`).

## What a row is

One row per symbol per minute, the board **as it stood at `minute_ts`**:

| Field | Definition |
|---|---|
| `minute_ts` | Every 60 s from 04:01 to 20:00 ET (960 per day). 04:01 is the first boundary with a closed bar. |
| bars used | A minute bar (`window_start` w) is used at `minute_ts` only when `w + 60 <= minute_ts`. The bar still forming is never used. |
| `price` | Close of the symbol's last bar that closed by `minute_ts`. |
| `volume` | Sum of the day's bar volumes that closed by `minute_ts` (read as DOUBLE: fractional from 2026). |
| `prev_close` | Close in the prior session's `day_aggs_v1` file (the previous minute-file date), split-adjusted (below). |
| `change_pct` | Computed by `make_row`: `(price - prev_close) / prev_close`, a fraction; null when either is unknown. |
| `rank` | Position in `rank_rows(rows, BOARD_RULES)` over **every** universe symbol with a closed bar at that minute (change desc, unknown change last; ties by volume, then symbol). |
| `rvol`, `rvol_basis` | `time_of_day_20`, below; null together when unknown. |
| `float_shares` | Nova's own `enrichment_snapshots` row for that symbol and session date (`backend/.cache/archive.db`, opened read-only). |
| `has_news`, `news_first_seen_ts` | The Massive news archive, below. |
| `gap_pct` | Fraction, like the desk's `gap_percent`: `(open of the first minute bar at or after 09:30 - prev_close) / prev_close`, null until that bar has closed. |
| `exchange` | Reference `primary_exchange` mapped to the desk's vocabulary (XNAS NASDAQ, XNYS NYSE, XASE AMEX, ARCX ARCA, BATS BATS). |
| `market_cap` | Always null. |

**Stored per minute:** the top `--top` (default 100) rows by `BOARD_RULES`, plus
every row `LEADERS_RULES` or `S5_RULES` picks at that minute, so playback's leaders
and the S5 universe read back exactly. Stored ranks are the `BOARD_RULES` ranks
(a leader outside the top 100 keeps its real rank, e.g. 237). One `coverage` row
per minute: `state: rebuilt`, `row_count` = rows stored that minute, `run_id: null`.

**Universe:** reference `type` in `CS` (common stock) or `ADRC` (ADR common). A
ticker missing from the reference, or with no type there, is left out (5 tickers on
2026-09-21 -- the ZZZT* test symbols; 118 on 2022-03-15, more on older dates). The
reference is today's dump, so a reused symbol carries its current type.

### Split handling (verified on a real reverse split)

Flat files are **unadjusted**. For splits executing in (prior session, rebuilt
date], the prior close is multiplied by `split_from / split_to`; for the RVOL
lookback, a prior session's volume is multiplied by `split_to / split_from` for
splits executing in (that session, rebuilt date].

Real case, `splits`: UZX, `execution_date` 2026-09-21, `split_from` 23,
`split_to` 1 (a 1-for-23 reverse split). UZX closed at 0.0813 on 2026-09-18 and
1.75 on 2026-09-21. Adjusted prior close 0.0813 x 23 = 1.870, change -6.4%.
Unadjusted it would read +2,052% and top the board. A 2-for-1 forward split
(`split_from` 1, `split_to` 2) halves the prior close.

### Prior close source

The day aggregate's close is the official session close, not the last minute bar:
AAPL on 2026-09-18 closed 336.13 in `day_aggs` -- the 16:00 closing-cross print
(the 16:00 minute bar's open) -- while its last 15:59 minute bar closed at 335.58
and its last extended-hours bar at 334.875.

### Time-of-day RVOL (`time_of_day_20`)

`rvol = volume so far / mean over the prior sessions of that symbol's volume by the
same time of day`, where "by the same time of day" uses the same boundary rule
(bars of that session that closed by the same ET clock time). The prior sessions
are the **20 minute-file dates before the rebuilt date** -- never the rebuilt date
or anything later. The mean divides by the sessions in which the symbol printed
at least one bar; a session without a print is not counted as zero. With fewer
than **10** such sessions (`RVOL_MIN_PRIOR_SESSIONS` in `lb_config.py`) rvol is
null, and it is null when the prior mean at that time is zero (the symbol never
traded that early before) -- unknown, never infinite. Consequence for S5: a name
that has never traded pre-market in its prior sessions cannot be an S5 pick
before its prior sessions' first print time, however hard it runs.

### News

`news_tickers` in `F:\Nova\data\massive\store\orb.duckdb` (one row per article and
ticker; deduplicated per article). `has_news` is true when an article naming the
symbol was published **after the prior session's 16:00 ET close and at or before
`minute_ts`**; `news_first_seen_ts` is the earliest such publish time (epoch
seconds); false when none. It is **null for the whole day** when the archive does
not hold every month the window spans or its newest article is older than the
rebuilt session's 20:00 ET -- an archive that stops early is not "no news". This is
the Massive archive, not the desk's news feed: a recorded day and a rebuilt day can
disagree about news.

## Honesty

- **No hindsight.** Every field at `minute_ts` is computed from bars that closed
  by `minute_ts`, the prior session's close, prior sessions, news published by
  `minute_ts`, and float as Nova knew it that day. Tests prove that later bars of
  the day, a later session, and the day's own `day_aggs` file never change an
  earlier minute (`backend/tests/test_leaderboard_reconstruct_rvol_news.py`).
- **Float** is mostly null: the flat files carry no float as of a date, and
  today's shares-outstanding snapshot (`ticker_details`) would be hindsight, so it
  is never read. Nova's own enrichment snapshots cover 2026-07-28 onward, only for
  symbols the desk enriched that day (262 of 5,571 on 2026-09-21). The snapshot's
  `ts` is its last refresh that day, so the value is used for the whole session.
- **`market_cap`** is always null (the reference value is today's).
- **`gap_pct`** uses the first minute bar's open at or after 09:30, not IBKR's
  official opening price (tick 14); null before that bar closes.
- **`exchange`** is today's listing from the reference: a symbol that changed
  exchange shows its current one.
- **`halted`** is not stored; playback derives it from the halt log, which a
  rebuilt day does not have. A gap in the prints is never read as a halt.
- **Unknown is null**, never 0: no prior close (a new listing) leaves
  `change_pct` null and the row ranks last; no prior sessions leaves `rvol` null.
- **`orb.duckdb` locked by a writer:** the builder says so and reads
  `store/reference/tickers.json`, `splits.json` and `news/*.jsonl` instead. It
  holds the research store open read-only only while loading reference data.

## Spot check

`spot_check.py` recomputes the board for chosen minutes with a separate, simple
pandas path (the minute file, the prior `day_aggs` file, `tickers.json` and
`splits.json` read directly; none of the builder's code or SQL) and compares every
stored row's rank, change, price and volume, and that the independent top N is
stored with the same ranks. It exits 1 on any mismatch.

## Files

| File | Role |
|---|---|
| `build_leaderboard.py` | CLI; `assemble` + `rebuild_day` |
| `lb_core.py` | Pure: as-of grid, RVOL, news first-seen, per-minute board, row selection |
| `lb_io.py` | Flat files (DuckDB in memory), reference, splits, news, float |
| `lb_config.py` | The rebuild's own tunables and paths |
| `s5_universe.py` | S5 per minute, read back from the store |
| `spot_check.py` | Independent pandas check against the flat files |
