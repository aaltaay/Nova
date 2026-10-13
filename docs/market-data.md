# Market data for agents: what is on disk and how to read it

The operator's Massive files hold every US stock's trades, NBBO quotes and minute and daily bars, every trading day
from 2016-01-04. Nova's own stores add the day movers index (one row per stock per session that moved) and the
Scanner boards played back in the Sim. **Do not write a reader.** Use the front door, which knows the traps below:

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
| Past-day Scanner boards (recorded live, or rebuilt from minute bars) | `F:\Nova\leaderboard\leaderboard.sqlite3` | see `status` | `board`, the Sim |
| Reference (splits, news, IPOs, dividends, short interest, financials) | `...\store\reference\` | month files from 2016 | `research/leaderboard/lb_io.py`; FINRA short interest as published by a past moment, for the Sim's "Why it's moving": `backend/move_reason/short_interest.py`, from `short_interest/YYYY-MM.jsonl` (`research/orb/short_interest_months.py` splits the dump) |

`NOVA_MARKET_DATA_DIR` moves the Massive root; `NOVA_LEADERBOARD_DIR` the boards.

## How fast

A day file is one gzip of every US stock, sorted by ticker. With its seek index, one stock-day is read in about a
second (TSLA's 400,000 quotes on 2026-09-09: 1.1 s). Without one, the read inflates the file up to the ticker:
minutes for a late ticker (the same read on 2026-09-10: 152 s). `status` says how many days are indexed;
`index` builds the rest (`--workers`, newest day first; `E:\Nova\massive\sim\index\STOP` stops it after the
files in progress; resumable). The drive is one hard disk: a bulk index build slows every other reader on it.
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
- **Level 2** history is not here at all: Massive's stock plan is Level 1 only.

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
