# Rebuilt leaderboard (ADR 023) and the S5 rolling universe

Offline research tool. It rebuilds the **whole-market, per-minute** scanner
leaderboard from the Massive minute flat files and writes it into Nova's
leaderboard store (`backend/leaderboard/store.py`) as `source="reconstructed"`,
three boards per minute: `market` (shown on the desk as Gainers), `losers` and
`gappers` (ADR 023 amendment 2026-10-06). The `market` rows are the S5 rolling universe of
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
py -3 research/leaderboard/confirm_splits.py --start 2026-06-16 --end 2026-09-21   # splits Massive misses (#772)
py -3 research/leaderboard/build_leaderboard.py --dates 2026-09-09,2026-09-10      # the days it prints
cd backend && py -3 -m pytest tests/test_leaderboard_reconstruct*.py tests/test_leaderboard_rebuild_runner.py -q
```

**The five-year rebuild** runs unattended, a night at a time:

```text
py -3 research/leaderboard/build_leaderboard.py --all --newest-first --skip-complete --avoid-session >> F:\Nova\leaderboard\rebuild.log 2>&1
```

Newest session first; sessions already complete in the store (all 960 minutes on
each of the three boards) are skipped, so a run cut off mid-day rebuilds that day
next time, and so does a day rebuilt before its Losers and Gappers existed; it stops
before 03:45 ET on a weekday (`--avoid-session`) because the live recorder writes
the same store 04:00-20:00 and the desk needs the machine. Run it again after
20:05 ET to continue. Reference and news load per `--chunk-days` sessions (20) to
bound memory. All 1,255 sessions: about 21 hours of building and 23 GB of store
with the `market` board alone; with Losers and Gappers about twice the rows
(roughly 48 GB) and longer writes.

The store defaults to `leaderboard.store.path()` -- `NOVA_LEADERBOARD_DIR`, else
`F:\Nova\leaderboard\leaderboard.sqlite3`. A rebuild is idempotent: it deletes that
day's `(date, reconstructed)` rows and coverage (`store.replace_day`) and writes them
again in hourly transactions; recorded rows are never touched. About 205,000 rows
(~38 MB of store) per day: 2026-09-09 stored 96,023 `market`, 96,000 `losers` and
12,771 `gappers` rows. It built in 125 s at below-normal priority with the desk
running, and took 347 s with the writes into the live store (before Losers and
Gappers: 50-72 s and ~96,000 rows a day at night). One minute file, twenty prior
minute files, Python ranking passes over ~4 million symbol-minutes. Needs `duckdb`, `pandas`,
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
| `rank` | On `market`: position in `rank_rows(rows, BOARD_RULES)` over **every** universe symbol with a closed bar at that minute (change desc, unknown change last; ties by volume, then symbol). On `losers` / `gappers`: that board's own ranking (below). |
| `rvol`, `rvol_basis` | `time_of_day_20`, below; null together when unknown. |
| `float_shares` | Nova's own `enrichment_snapshots` row for that symbol and session date (`backend/.cache/archive.db`, opened read-only). |
| `has_news`, `news_first_seen_ts` | The Massive news archive, below. |
| `gap_pct` | Fraction, like the desk's `gap_percent`: `(open of the first minute bar at or after 09:30 - prev_close) / prev_close`, null until that bar has closed. |
| `exchange` | Reference `primary_exchange` mapped to the desk's vocabulary (XNAS NASDAQ, XNYS NYSE, XASE AMEX, ARCX ARCA, BATS BATS). |
| `market_cap` | Always null. |

**Stored per minute,** three boards, each from the same rows (every universe
symbol with a closed bar by the minute):

| Board | Rows | `rank` |
|---|---|---|
| `market` | the top `--top` (default 100) by `BOARD_RULES`, plus every row `LEADERS_RULES` or `S5_RULES` picks, so playback's leaders and the S5 universe read back exactly | `BOARD_RULES` (a leader outside the top 100 keeps its real rank, e.g. 237) |
| `losers` | the worst `--top` by `LOSERS_RULES`: a known change under 0 | 1 = the biggest drop |
| `gappers` | before 09:30, the top `--top` by `GAPPERS_RULES` -- the live premarket projection's own rule (`ibkr/gapper_view.row_qualifies`: price >= $0.50, change >= 10%, inclusive); `gap_pct` is the move, as on the live list. From the 09:30 minute (premarket bars only) the membership is frozen, as the live list freezes at 09:30, and each later minute reprices those symbols | 1 = the biggest move; from 09:30, the 09:30 order |

One `coverage` row per board per minute: `state: rebuilt` (`frozen` for `gappers`
from 09:30), `row_count` = that board's rows that minute, `run_id: null`. An empty
board still writes its minute, so the desk can tell an empty list from one that
was never rebuilt. After Hours and Large Cap are not rebuilt: the live After
Hours list ranks the move since the regular close, which this rebuild does not
measure, and the files carry no market cap as of the day.

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

### Splits Massive's list misses (#772)

The splits are Massive's list (`orb.duckdb`'s `splits`, else `splits.json`) **plus**
the ones an SEC filing proves, from `splits_confirmed.json` beside the store; on the
same ticker and day Massive's entry wins. PHGE's 1-for-10 reverse split on 2026-09-09
was missing from Massive's list, so the board read +925% (0.155 -> 1.60). With the
confirmed split it reads about +3%.

`confirm_splits.py` finds and proves them (rules in AGENTS.md section 3, "Splits a
rebuild confirms from SEC filings"; the reading is `split_confirm.py`, pure and tested):

1. **Suspects:** an overnight open at least 1.8x, or at most 0.7x, the prior close
   with no split listed in between (285 in 2026-06-16..09-21).
2. **Filings:** the ticker's 8-K with Item 5.03 / 3.03 or any 6-K, filed from 60 days
   before to 3 days after (181 of the 285 had one). The list comes from SEC's bulk
   `submissions.zip` (`F:\Nova\catalysts\edgar`, kept by the catalyst backfill), the
   live submissions JSON past its date. Each filing's primary document, then its EX-99
   exhibits, is fetched once and kept in `split_filings\<accession>.v1.txt`.
3. **Proof:** the filing states one ratio outside a range, the split-adjusted open is
   0.5-2x the prior close, and the filing's effective date falls after the prior
   session and by the session (0.67-1.5x when it names none). A ratio stated beside
   other dates only is an earlier split recalled.

On 2026-06-16..09-21 it confirmed PHGE alone and refused 107: filings about a split on
another date (GCDT's 6-for-1 consolidation is effective 2026-10-07), splits proposed
within a range, ADS ratios ("1 ADS for every 20 shares" on a new listing), and
boilerplate. Then rebuild the days it prints (the split's day and the next 20 sessions
the ticker traded, which the RVOL lookback reaches):

```text
py -3 research/leaderboard/confirm_splits.py --start 2026-06-16 --end 2026-09-21
py -3 research/leaderboard/build_leaderboard.py --dates 2026-09-09,2026-09-10
```

Run it over a span before building that span, so a missed split never lands in the store.

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

`news_tickers` in `E:\Nova\massive\store\orb.duckdb` (one row per article and
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
| `split_confirm.py` | Pure: a split ratio and effective date out of a filing, held against the overnight prices (#772) |
| `confirm_splits.py` | CLI: suspects, their SEC filings, `splits_confirmed.json`, the days to rebuild (#772) |
