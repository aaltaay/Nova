# Market data for agents: what is on disk and how to read it

The operator's Massive files hold every US stock's trades, NBBO quotes and minute and daily bars, every trading day
from 2016-01-04. Nova's own stores add the day movers index (one row per stock per session that moved) and the
Scanner boards played back in the Sim; Massive's reference dump adds financial statements, float, IPOs and short
interest, and SEC's bulk files add share counts and every filing. **Do not write a reader.** Use the front door,
which knows the traps below. Agents get the same reads as MCP tools from the `nova-data` server
(`tools/nova_data_mcp.py`, registered in `.cursor/mcp.json` and `.mcp.json`; ADR 059) -- start with `data_catalog`.
A tripwire hook (`tools/data_access_hook.py`) blocks an agent's own reader of these stores.

```text
py -3 tools/market_data.py status                                  # what is on disk, how much is indexed
py -3 tools/market_data.py trades GME 2021-01-27 --from 09:30 --to 09:35 --out gme_trades.parquet
py -3 tools/market_data.py quotes GME 2021-01-27 --from 09:30 --to 09:31
py -3 tools/market_data.py bars GME 2021-01-27 --tf 10s --from 09:30 --to 10:00
py -3 tools/market_data.py bars GME 2021-01-27 --tf 5m
py -3 tools/market_data.py movers date_from=2021-01-01 date_to=2021-12-31 high_min=100 price_max=20
py -3 tools/market_data.py board 2026-09-09 --at 09:45 --list gappers --top 20
py -3 tools/market_data.py splits GRML --day 2026-07-15            # the splits, and that day's factor (50)
py -3 tools/market_data.py bars GRML 2026-07-15 --tf 5m --adjust   # trades / quotes / bars in today's terms
py -3 tools/market_data.py bench                                   # how fast each read is, measured
py -3 tools/market_data.py catalog                                 # every dataset: history, as-of rule, units
py -3 tools/market_data.py scan date_from=2021-01-01 price_min=2 price_max=20 high_min=50 --out r.parquet
py -3 tools/market_data.py financials GURE --statement income_statements --as-of 2024-03-01
py -3 tools/market_data.py sec-shares GURE --day 2024-03-01         # outstanding / issued / treasury filed by then
py -3 tools/market_data.py sec-filings GURE --as-of 2024-03-01 --forms "4,SC 13D,424B4"
py -3 tools/market_data.py float GURE                              # Massive's latest free float (no history)
py -3 tools/market_data.py short-interest GURE 2024-03-01          # FINRA, as published by that morning
```

From Python, the same reads return pandas DataFrames:

```python
import sys; sys.path.insert(0, "research")
from market_reads import reads
t = reads.trades("GME", "2021-01-27", "09:30", "09:35")   # every column as delivered, plus time_et, sets_price
q = reads.quotes("GME", "2021-01-27", "09:30", "09:31")
b = reads.bars("GME", "2021-01-27", "10s", "09:30", "10:00")
m = reads.movers(high_min=100, price_max=20, date_from="2021-01-01")   # the /api/agent/movers answer
g = reads.board("2026-09-09", "09:45", "gainers")

from market_reads import splits
splits.table("GRML")                         # Massive's list plus the splits SEC filings proved (source column)
splits.factor("GRML", "2026-07-15")          # 50.0: a raw price that day x 50 = today's terms
splits.adjust(reads.bars("GRML", "2026-07-15", "5m"), "GRML", "2026-07-15")   # prices x 50, shares / 50
```

To put a stock-day on the desk for the operator, use the `nova-sim-navigator` skill (`tools/nova_agent.py`).

## What is where

| Data | Where (default) | Covers | Read with |
|---|---|---|---|
| Trades (every print, conditions, exchange, nanosecond SIP time) | `E:\Nova\massive\trades_v1\YYYY\MM\YYYY-MM-DD.csv.gz` | 2016-01-04 on | `trades`, `bars --tf Ns` |
| NBBO quotes (one best bid and offer across venues, a row per change; Level 1, never depth) | `...\quotes_v1\...` | 2016-01-04 on | `quotes` |
| 1-minute bars, 04:00-20:00 ET | `...\minute_aggs_v1\...` | 2016-01-04 on | `bars --tf 1m / 5m / ...` |
| Daily bars (official open / high / low / close) | `...\day_aggs_v1\...` | 2016-01-04 on | the movers index and the board rebuild |
| Seek indexes (one per day file) | `...\sim\index\<dataset>\...\<file>.idx` | see `status` | used by every read |
| Day movers index | `...\movers\day_movers.sqlite3` | see `status` | `movers`, `/api/agent/movers` |
| Past-day Scanner boards (recorded live, or rebuilt from minute bars) | `F:\Nova\leaderboard\leaderboard.sqlite3` | 1,752 of 2,713 sessions (see `status`) | `board`, the Sim |
| Reference (splits, news, IPOs, dividends, short interest, financials) | `...\store\reference\` | month files from 2016 | `financials`, `float`, `ipos`, `ticker`, `short-interest` (`research/market_reads/reference.py`); splits via `lb_io` |
| Reference index (built from the dump on first read, rebuilt when a dump file changes) | `...\store\reference_index.sqlite3` | what the dump holds | owner `research/market_reads/reference.py` |
| SEC XBRL facts (shares outstanding / issued / treasury, 10-K public float) | `F:\Nova\catalysts\edgar\companyfacts.zip` | XBRL era (~2009-2011 on) | `sec-shares` (`research/market_reads/sec.py`) |
| SEC filing list (every form and date: 10-Q, 10-K, 20-F, 8-K, Forms 3/4/5, 13D/G, 424B) | `F:\Nova\catalysts\edgar\submissions.zip` | all of EDGAR | `sec-filings` |

The scripts that build the derived tables (`trades_flow_v1`, `trades_movers_v1`, the reference dump, `orb.duckdb`,
`seconds.duckdb`, `bb_mr.duckdb`) and every column's definition: `docs/massive-builders.md`.

`NOVA_MARKET_DATA_DIR` moves the Massive root; `NOVA_LEADERBOARD_DIR` the boards; `NOVA_CATALYST_DIR` the SEC
files. Heavy reads (bulk scans, index builds, MCP stock-day reads) share `NOVA_MARKET_READ_SLOTS` (default 2) slots
across every process on the PC.

## How fast

A day file is one gzip of every US stock, sorted by ticker. With its seek index, one stock-day is read in about a
second (TSLA's 400,000 quotes on 2026-09-09: 1.1 s). Without one, the read inflates the file up to the ticker:
minutes for a late ticker (the same read on 2026-09-10: 152 s). `status` says how many days are indexed;
`index` builds the rest (`--workers`, newest day first; `E:\Nova\massive\sim\index\STOP` stops it after the
files in progress; resumable). A run is watched: a fresh worker per file, no build below 3 GB of free memory
(`--ram-floor-gb`), a halt after 5 failures in a row (`--halt-after`), a Windows notification on the first failure,
a halt and the end, and `E:\Nova\massive\sim\index\index-status.json`, which `status` reads (`died` when the run's
process is gone). The drive is one hard disk: a bulk index build slows every other reader on it.
Several builds reading it at once make its head jump between files (6 builds: 121 MB/s, against 213 MB/s for one
stream), so on the desk PC run it with `--workers 6 --stage <a folder on an SSD>`: each file is copied off the
hard drive in one stream and built from the copy, which is deleted after. `--read-mb` does nothing.

Sizes, measured 2026-10-12: 15.6 TB of gzip (quotes 12.1, trades 3.5, minute bars 0.05). Uncompressed text would
be about 81 TB; Parquet about 11 TB. The index is about 0.2% of a file.

## The traps (each one cost a wrong answer once)

- **Quoted commas.** `conditions` and `indicators` hold lists like `"12,37"`: parse with a CSV reader, never
  `split(",")`, or every later column shifts.
- **Sort order.** Files are sorted by ticker but not all in byte order: the trades files put a preferred or
  warrant right after its stock (`AA`, `AApB`, `AAAP`). Only plain A-Z tickers are in byte order everywhere.
  A reader that stops at the first ticker sorting after the one it wants misses stocks.
- **Unadjusted prices.** Nothing in the files is split-adjusted. A reverse split reads as a giant mover unless
  the split list says otherwise (the movers index and the board rebuild adjust; raw reads do not). IBKR's daily
  bars are adjusted, so the desk's Full Day chart and a raw read of the same day can differ by the split: GRML
  on 2026-07-15 traded at $0.19 and the chart showed ~$9.25 (1-for-50 on 2026-08-24). Compare across a split
  only through `splits` (`--adjust` on the command line); a read inside one session needs none.
- **Which prints set a price.** Corrections 10 / 11 are not trades; some conditions (odd lots, average price,
  late reports such as 32 / 33) never move the last or a candle. `trades` adds `sets_price`; `bars --tf Ns`
  uses only those for prices and every trade for volume. The minute files are as Massive built them.
- **The day bar's volume is the whole session** (04:00-20:00 with odd lots); its prices are regular hours. The
  minute bars carry no closing cross.
- **No look-ahead.** A minute bar starting at 09:30 is known at 09:31. A "top gainer at 09:30" ranked on the
  whole day's volume reads the future.
- **News coverage** at Massive is nearly empty before 2021-04: a missing headline before then is unknown, not
  "no news".
- **Float as of a day** is not in the files; the movers index uses SEC share counts filed by the session.
  Massive's `float` is today's only. Insider holdings (SEC Form 3/4/5 data sets) and lockup terms are not on disk.
- **Percent units in the movers store.** `high_pct` / `low_pct` / `close_pct` / `gap_pct` are stored as fractions
  (0.10 = 10%); a raw `high_pct >= 10` matched only +1000% days (2026-10-18). `movers` and `scan` take and return
  percent points, and so does `board` (`change_pct` / `gap_pct`; the board store keeps fractions too).
- **Reverse splits look like runners.** Of 3,615 stock-days with a high of +300% or more, 1,844 are split suspects
  and 484 are likely splits. `movers` and `scan` share one rule (`day_movers.query.splits_sql`): likely splits are
  left out unless `splits=include`; `splits=only_suspects` lists the suspects; every scan row says `split`.
- **A broad scan is refused.** `scan` needs `date_from` / `date_to`, a symbol or a `limit`, and without a limit
  returns at most 100,000 rows (`capped` says when more matched). The store is 3.0M rows on the desk's drive.
- **Boards do not cover every day.** 1,752 of 2,713 sessions have a board (recorded or rebuilt, from 2016-11-30,
  with holes such as 2023-06-01). A day without one answers `covered: false` with its `gap`, not just 0 rows.
- **Two companies, one ticker.** 84 tickers in Massive's list belonged to two companies (AAP was Alcoa's preferred
  until 2016-11-01). SEC shares and filings, financials and splits read the company that held the ticker on the
  day asked (`research/market_reads/tickers.py`), say so in `ticker`, and refuse a day they cannot settle with the
  candidate CIKs (`--cik` picks one). Without a day they read today's holder and warn.
- **Two volume rules.** Minute bars are Massive's (its SIP volume rules); `bars --tf 10s` counts every trade but
  cancel / error records, so a minute of seconds bars can sum higher: GME 2021-01-27 09:30 is 185,567 from the
  trades and 179,397 in the minute file (+3.4%). Daily bars are not a `bars` timeframe.
- **`float_max` is shares outstanding.** The movers float filter is SEC shares outstanding filed by the day (insiders
  and locked-up shares included), not free float.
- **Filed, not period end.** A statement or SEC fact counts from the day it was filed: a quarter ending 03-31 is
  unknown until its 10-Q lands in May. `--as-of` / `--day` apply that rule. Balance-sheet `common_stock` and
  `treasury_stock` are dollars; share counts are SEC facts.
- **Level 2** history is not in the Massive files: its stock plan is Level 1 only. Nova's own IBKR recordings
  (`F:\Nova\sim_capture` sessions from 2026-09-19, the desk cache's `l2.db` depth and `archive.db` tape from
  2026-07-15, `F:\Nova\book_watch`) replay in the Sim; the front door does not serve them yet.

## Past-day boards in the Sim

A recorded day (the desk was running) plays back its own lists. Any other day plays back a board rebuilt from
the minute files: Gainers (the `market` board), Losers, Gappers (frozen at 09:30 like the live list) and, from
16:01, After Hours (IBKR's after-hours scan rebuilt against the day's official close, then the live list's
rule). Large Cap is not rebuilt (no market cap as of the day). Rules: `architecture/schema/scanner.md`,
"Scanner leaderboard". The rebuild for many days runs into staging stores and `merge_rebuilt.py` copies each
finished day into the board store in short transactions, so the live recorder never waits on it:

```text
py -3 research/leaderboard/build_leaderboard.py --start 2016-01-04 --end 2019-08-31 --newest-first --skip-complete --db F:\Nova\leaderboard\staging\c.sqlite3
py -3 research/leaderboard/merge_rebuilt.py --stage F:\Nova\leaderboard\staging\c.sqlite3 --loop 300
```
