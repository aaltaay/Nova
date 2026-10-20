# Market data for agents: what is on disk and how to read it

The operator's Massive files hold every US stock's trades, NBBO quotes and minute and daily bars, every trading day
from 2016-01-04. Nova's own stores add the day movers index (one row per stock per session that moved) and the
Scanner boards played back in the Sim; Massive's reference dump adds financial statements, float, IPOs and short
interest, and SEC's bulk files add share counts and every filing. **Do not write a reader.** Use the front door,
which knows the traps below. Agents get the same reads as MCP tools from the `nova-data` server
(`tools/nova_mcp.py`, registered in `.cursor/mcp.json` and `.mcp.json`; `tools/nova_data_mcp.py` starts the same
server; ADR 059) -- start with `data_catalog`. Desk charts from that server are `docs/nova-mcp.md`.
A tripwire hook (`tools/data_access_hook.py`) blocks an agent's own reader of these stores.

```text
py -3 tools/market_data.py status                                  # what is on disk, how much is indexed
py -3 tools/market_data.py trades GME 2021-01-27 --from 09:30 --to 09:35 --out gme_trades.parquet
py -3 tools/market_data.py quotes GME 2021-01-27 --from 09:30 --to 09:31
py -3 tools/market_data.py bars GME 2021-01-27 --tf 10s --from 09:30 --to 10:00
py -3 tools/market_data.py bars GME 2021-01-27 --tf 5m
py -3 tools/market_data.py bars DSS 2026-09-03 --from 09:30 --to 10:30 --fill-gaps   # a row per minute with no trade
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
py -3 tools/market_data.py runway GURE 2024-03-01                  # cash, burn, runway, share growth, offering filings
py -3 tools/market_data.py float GURE                              # Massive's latest free float (no history)
py -3 tools/market_data.py short-interest GURE 2024-03-01          # FINRA, as published by that morning
py -3 tools/market_data.py find date_from=2025-01-01 date_to=2025-03-31 price_min=2 price_max=20 high_min=50 --float-max 20000000
py -3 tools/market_data.py find date_from=2026-09-01 date_to=2026-10-16 high_min=100 --sort high --limit 10   # the ten biggest highs
py -3 tools/market_data.py daily GME 2021-01-04 2021-02-26         # daily bars (raw; --adjust for split terms)
py -3 tools/market_data.py context 2026-09-09                      # SPY / QQQ / IWM that day
py -3 tools/market_data.py stats IRD 2026-09-09                    # premarket, first 5/30 min, VWAP, spread, rvol
py -3 tools/market_data.py flow IRD 2026-09-09 --bucket 5m         # dark pool, retail buy/sell, sweeps per minute
py -3 tools/market_data.py halts --symbol GME --from 2021-01-25 --to 2021-01-29
py -3 tools/market_data.py catalysts IRD --from 2026-09-08 --to 2026-09-09 [--verdicts]
py -3 tools/market_data.py symbols aurora                          # or: symbols --ticker AAP --day 2016-06-01
```

**Momentum research in one call.** `find` (MCP `find_stock_days`) is the movers index joined with what was known
that day: SEC shares outstanding filed by then (`outstanding_*`; the default `--float-max` basis, and it is not free
float), the desk's own float when it had one (`enrichment_float`, 2026-07-28 on), the catalyst verdict (null =
unknown), the day's halts, premarket high / volume and the first ET minute each +10% .. +300% line printed. Every
float value says its source (`float_source`). Pages come back with `next_cursor`. `find` returns common stock
(`CS`, `ADRC`) unless `kinds` says otherwise (`kinds=all` adds warrants, rights, units and ETFs), and `--sort`
ranks the rows like the movers search (`--sort high --limit 10` is the ten largest highs that pass your other
filters; `next_cursor` resumes the same ranking exactly). Then `stats`, `flow`, `catalysts`
and `daily` / `context` answer the questions about one stock-day. Builders and column definitions for the derived
tables (`trades_flow_v1` and the rest): `docs/massive-builders.md`.

**Cash runway and dilution filings in one call.** `runway` (MCP `cash_runway`) answers, for one stock and day and
with nothing read from after it: the newest balance sheet's cash and short-term investments, the newest quarterly
operating cash flow (the burn), runway in months (liquid cash / (burn / 3)), shares outstanding growth over 4 and 8
quarters, and the S-1 / S-3 / F-1 / F-3 / 424B1-5 / 8-K filings in the lookback before the day (default 3 years)
with their dates. It is composed from `financials`, `sec-shares` and `sec-filings`, so it is the method to use
when agents' numbers must agree. Every figure names its statement's `period_end`, `filing_date` and `age_days`;
unknown is null, never 0; the filings are counts and dates, not a verdict. **Read `age_days` / `stale` before
you trust a number:** Massive dates a period by the newest filing that carried it (87% of quarterly cash-flow
rows and 27% of balance sheets are dated 300+ days after their period), so on a past day the newest statement
known is often over a year old and the balance sheet can be newer than the burn. The runway is divided out only
when the two are from the same period, period ends within 14 days (else `status: periods_differ`, `months` null; a
balance sheet one quarter newer than the burn is refused, not divided) and carries
`stale` beside it. Shares growth is null when the two counts are not a window apart (`span_off_window`) or are one
count (`same_count`). Schema: `architecture/schema/agent-desk.md` ("The data front door over MCP").

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
| Daily bars (official open / high / low / close) | `...\day_aggs_v1\...` | 2016-01-04 on | `daily`, `context`, the movers index and the board rebuild |
| Order flow per ticker-minute (off exchange, retail buy / sell, sweeps, odd lots, blocks, venues) | `...\trades_flow_v1\YYYY\MM\YYYY-MM-DD.parquet` | 2,712 days from 2016 | `flow` (`research/market_reads/order_flow.py`; builder `research/massive_builders`) |
| Halt log (Nasdaq Trade Halt RSS, IBKR) | `F:\Nova\leaderboard\leaderboard.sqlite3` `halt_events` | 2019-02-22 on | `halts` |
| Catalyst items and verdicts | `F:\Nova\catalysts\catalysts.sqlite3` | items from 2016 (Massive news thin before 2021-04); verdicts 2021-10-11 .. 2026-09-21 | `catalysts` |
| Ticker list (active and delisted, CIK) | `...\store\reference\tickers.json` | latest dump | `symbols` (`research/market_reads/symbols.py`, `tickers.py`) |
| Seek indexes (one per day file) | `...\sim\index\<dataset>\...\<file>.idx` | see `status` | used by every read |
| Day movers index | `...\movers\day_movers.sqlite3` | see `status` | `movers`, `/api/agent/movers` |
| Relative-volume table (every minute bar of every common stock with its baselines; one row per stock-day) | `F:\Nova\rvol\minutes\YYYY\` and `...\days\YYYY\` (`NOVA_RVOL_DIR`) | 2016-01-04 on (`status` `rvol_table`) | `rvol`, `rvol-triggers`, `rvol-outcomes` (owner `research/market_reads/rvol_store.py`; builder `research/rvol/build_rvol.py`) |
| Signal table (the Trader's Signals panel at every minute of every in-play stock-day) | `F:\Nova\signals\minutes\YYYY\`, `...\days\YYYY\`, `...\tape\YYYY\` (`NOVA_SIGNALS_DIR`) | 2016-01-04 on (`status` `signal_table`) | `signals`, `signal-series`, `signal-scan`, `signal-test` (owner `research/market_reads/signals_store.py`; builder `research/signals/build_signals.py`) |
| Past-day Scanner boards (recorded live, or rebuilt from minute bars) | `F:\Nova\leaderboard\leaderboard.sqlite3` | about 1,750 of 2,713 sessions (see `status`) | `board`, the Sim |
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

A stock-day read once is kept in the read cache (`research/market_reads/read_cache.py`, contract "Read cache" in
`architecture/schema/agent-desk.md`): an Arrow file per dataset, symbol and day under `F:\Nova\market_read_cache`,
used only while the day file's path, size and time and the reader's code still match. Measured 2026-10-18 on the desk
PC (another job holding 85-90% of the CPU): HODO's 347,846 trades on 2026-10-16 in 2.25 s from the day file, 0.10 s
from the cache. `NOVA_MARKET_READ_CACHE=0` turns it off, `NOVA_MARKET_READ_CACHE_DIR` moves it,
`NOVA_MARKET_READ_CACHE_GB` caps it (default 50, least recently used first). About 20 bytes a trade and 18 a quote.

Sizes, measured 2026-10-12: 15.6 TB of gzip (quotes 12.1, trades 3.5, minute bars 0.05). Uncompressed text would
be about 81 TB; Parquet about 11 TB. The index is about 0.2% of a file.

## Relative volume across every stock (#1100)

One standard for every agent: the relative-volume table holds every minute bar of every common stock since 2016 with
its baselines, so a question over all stocks and all days is one call instead of a 30-45 minute read of the 46 GB
of minute files. Three measures, each as of the end of a minute:

| Measure | What it divides | Matches |
|---|---|---|
| `cumulative` (`rvol`) | volume since 04:00 / the prior sessions' mean volume to the same minute (20 sessions) | `stock_day_stats` `rvol.by_minute`, to the share |
| `five_minute` (`rvol_5m`) | the last 5 minutes / the prior sessions' mean of the same 5 minutes | the 5-minute relative-volume column momentum scanners show |
| `daily_rate` (`rvol_daily`) | volume since 04:00 / the mean whole-session volume of up to 50 sessions | the Five Pillars' "5x the 50-day average" |

```text
py -3 tools/market_data.py rvol 09:30 date_from=2021-01-01 date_to=2021-12-31 price_min=1 price_max=20 rvol_min=5
py -3 tools/market_data.py rvol-triggers 10 date_from=2025-01-01 date_to=2025-12-31 price_min=1 price_max=20 --window 06:00-08:00 --fresh
py -3 tools/market_data.py rvol-outcomes date_from=2016-01-04 date_to=2026-10-16 price_min=1 price_max=20 --at 09:30 --up 50 --down 50
py -3 tools/market_data.py rvol-outcomes date_from=2016-01-04 date_to=2026-10-16 price_min=1 price_max=20 --trigger 10 --window 06:00-08:00 --fresh --horizon days --days 5
py -3 research/rvol/build_rvol.py              # add the new sessions (each new day takes ~2 s); --status
```

MCP: `rvol_scan`, `rvol_triggers`, `rvol_outcomes`. Contract: `architecture/schema/agent-desk.md` ("Relative volume
across every stock, and what came next").

- **Already over the line.** A trigger is the first bar in the window at or above the line. A stock that was over it
  before the window opened triggers on the window's first bar: `above_before` says so, `fresh` leaves it out. A
  "6 AM surge" question wants `fresh`.
- **Both lines in one bar.** A minute bar whose high reached +X% and whose low reached -X% is `same_bar`: the minute
  file does not say which came first, and the answer never guesses. `p_up_resolved` ignores it.
- **No look-ahead.** The entry price is the close of the last bar before the entry clock; only later bars are read.
  A day's `day_*` columns and `hi` / `lo` are the finished day: never filter entries on them.
- **Compare with the control.** Hot stocks move more both ways. A trigger's `p_up` means little without the
  same-minute control beside it (`control`, on by default): read `p_up` and `p_down` against it.
- **Baselines start over.** A new company on the ticker or a likely unlisted reverse split starts the baseline again
  (`reset`; `base_sessions` counts up from 0). Listed splits are put on the day's share basis instead.
- **Only common stocks.** `CS`, `ADRC` and `unknown` (untyped in Massive's list) are in the table; ETFs, warrants,
  units and rights are not. Delisted common stocks are in it (no survivorship cut).

## The Trader's signals on past days, and mixing them

The Trader's Signals panel -- In play, Five Pillars, relative volume, catalyst, why it's moving, the boards, has it
run before, liquidity, HOD Momo, front side, every setup lane, float, halts and the tape -- for every in-play stock-day
since 2016, at the end of every minute, by the desk's own rules (the same functions the panel calls, never a copy).
One call tests any mix of them, scored like a relative-volume trigger, against a same-minute in-play control.

A stock-day is in play from the first minute a $1-$20 common stock closed 10% over the prior close or ran 5x its
relative volume, with 50,000 shares traded; its rows start there, so a later minute never chooses it earlier.

```text
py -3 tools/market_data.py signals                                   # every signal: values, desk rule, history
py -3 tools/market_data.py signal-series SMJF 2026-10-09 --signals pillars_n,front,setup_first_pullback
py -3 tools/market_data.py signal-scan 2026-10-09 09:45 --when "pillars_n>=4" --when "front=Front side"
py -3 tools/market_data.py signal-test date_from=2024-01-01 date_to=2024-12-31 --when "pillars_n>=4" \
    --when "setup_first_pullback=triggered" --window 07:00-10:30 --up 20 --down 10 --fresh
py -3 research/signals/build_signals.py --workers 10        # new sessions (newest first); --status
py -3 research/signals/build_signals.py --stage tape --start 2026-01-01   # the tape stage, Massive trades
```

MCP: `signal_catalog`, `signal_series`, `signal_scan`, `signal_test`. Contract: `architecture/schema/agent-desk.md`
("The Trader's signals on past days, and mixing them").

- **What has no history is unknown.** Borrow (the Short tile), HOD Momo's gate decisions, the Level 2 book walk and a
  float as of the day are not in any archive: `signal_catalog` lists them under `not_rebuilt`. The float is SEC's
  shares outstanding filed by the day before -- an upper bound, so under 20M proves the pillar and over it is unknown.
- **Partly covered signals.** Boards (1,752 of 2,713 sessions), catalysts (only tickers the backfill targeted),
  halts (Nasdaq's log 2021-09-21 on), HOD Momo (rebuilt days only, whose float is today's -- look-ahead) and the tape
  (the days the tape stage reached) read `unknown` / `not_built` elsewhere. `meta.coverage` names a test's partly
  covered conditions; a test on the tape runs only over the days the tape stage reached.
- **Inside a minute.** The setup lanes see a bar's open, then its high (long lanes) or low (short lanes), then its
  close: a long trigger needs the bar's high to reach the line. The order inside a bar is not in the data.
- **Compare with the control, and hold years out.** In-play stocks move a lot both ways; read `p_up` and `p_down`
  against the control. Mixing many signals finds patterns by chance: decide the mix before it runs, search some years
  and confirm on others (`group_by: year`).

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
- **Boards do not cover every day.** About 1,750 of 2,713 sessions have a board (recorded or rebuilt, from
  2016-11-30, with holes such as 2023-06-01; `status` has today's count). A day without one answers
  `covered: false` with its `gap`, not just 0 rows. **`status` counts stored boards, not lists.** Gainers on a rebuilt
  day is the `market` board (2016-11-30 .. 2026-09-22) and the recorded `gainers` board takes over from 2026-09-23, so
  "Gainers on day X" has an answer on every covered session; only `large_cap` is recorded-days-only (2026-09-23 on,
  nothing rebuilds it).
- **A null `catalyst_verdict` is not covered, never "no news".** The backfill judged the Five Pillars gap universe
  from 2021-10-11 to 2026-09-21 and the leaderboard's top-10 movers from 2026-06-17 to 2026-09-21; any other
  stock-day, and every day before 2021-10-11, has no verdict (`catalysts` `verdicts_meta.coverage` says so).
- **Two companies, one ticker.** 84 tickers in Massive's list belonged to two companies (AAP was Alcoa's preferred
  until 2016-11-01). SEC shares and filings, financials and splits read the company that held the ticker on the
  day asked (`research/market_reads/tickers.py`), say so in `ticker`, and refuse a day they cannot settle with the
  candidate CIKs (`--cik` picks one). Without a day they read today's holder and warn.
- **Two volume rules.** Minute bars are Massive's (its SIP volume rules); `bars --tf 10s` counts every trade but
  cancel / error records, so a minute of seconds bars can sum higher: GME 2021-01-27 09:30 is 185,567 from the
  trades and 179,397 in the minute file (+3.4%). Daily bars are not a `bars` timeframe.
- **`float_max` is shares outstanding.** The movers float filter is SEC shares outstanding filed by the day (insiders
  and locked-up shares included), not free float. `find` takes `--outstanding-max` (MCP `outstanding_max`) as the
  same limit under the name of what it filters, so the call shows its intent (an insider-heavy name's real float is
  smaller; `float` gives Massive's free float, today's only); it needs the default `sec_outstanding` basis and is refused beside
  `float_max`. The movers search's `float_max` is a proof on the desk's float or SEC outstanding; `--float-basis best`
  is the nearest here.
- **Common stock by default.** `find` keeps the movers search's `common` kinds (`CS`, `ADRC`, plus an unlabelled
  symbol of at most four letters). In Sep 2026 the movers rows were 15,687 `CS` and 1,209 `ADRC` beside 3,288
  `WARRANT`, 616 `RIGHT` and 6,173 `ETF`: most warrants are sub-penny and not tradeable. A named symbol is not filtered
  by kind. `scan` still keeps every kind unless `kinds=` says otherwise.
- **Bars have holes where nothing traded.** A minute or seconds bar exists only for a bucket with a trade, so a halt
  is a gap in the series (DSS 2026-09-03 1m jumps 09:45 -> 09:50, 09:51 -> 09:56, 10:05 -> 10:10, 10:10 -> 10:15: its
  four recorded halts). The answer's `meta.gaps` lists each run (`first_et`, `last_et`, `buckets`; the longest 50, with
  `gap_runs` / `gap_buckets` counting all), and `--fill-gaps` (MCP `fill_gaps`) adds a row per hole with no prices,
  zero volume and `filled` true. No price is carried forward: a filled minute has none.
- **Daily bars mix two sessions.** `volume` is the whole 04:00-20:00 session; `open` / `high` / `low` / `close` are
  regular hours. FLYE 2026-09-01 shows `high` 2.79 but `find`'s `day_high` is 3.97 at 05:38 ET, so a bar's volume can
  have built a range the bar does not show. `stats` gives premarket, regular and whole-day figures apart.
- **Filed, not period end.** A statement or SEC fact counts from the day it was filed: a quarter ending 03-31 is
  unknown until its 10-Q lands in May. `--as-of` / `--day` apply that rule. Balance-sheet `common_stock` and
  `treasury_stock` are dollars; share counts are SEC facts.
- **Old statements on a past day.** `financials` (and `runway` on top of it) counts a statement from Massive's
  `filing_date`, which is the newest filing that carried the period, usually the next year's comparative. On a past
  day the newest statement counted is therefore often 300+ days past its period end, and the original filing of a
  recent quarter can be absent. Check `period_end` / `age_days` against the day; never assume the latest row is the
  latest quarter.
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
