---
name: nova-market-data
description: "Use when a task needs past market data -- a stock's trades, NBBO quotes, intraday or daily bars on a past day (2016 on), seconds-scale moves, spreads, premarket / VWAP / relative-volume stats, order flow (dark pool, retail buy/sell, sweeps), halts, news catalysts, finding small-cap runner stock-days with their float as known that day, the day movers index, a past day's Gainers / Losers / Gappers / After Hours board, financial statements, float, shares outstanding, cash runway or dilution filings, SEC filings, IPOs, short interest or symbol lookups -- or asks how fast or how complete that data is, or wants charts of trades with the entry and exit marked. Reads the operator's Massive files, Nova's stores, Massive's reference dump and SEC's bulk files through the nova-data MCP tools or tools/market_data.py; never write a new reader for them."
---

# Nova market data

Every US stock's trades, NBBO quotes and minute / daily bars from 2016-01-04 are on the operator's E: drive, plus
Nova's day movers index and past-day Scanner boards. Read them through the front door, never with your own parser:

```text
py -3 tools/market_data.py status                          # what is on disk and how much is indexed (fast reads)
py -3 tools/market_data.py trades SYMBOL YYYY-MM-DD --from 09:30 --to 09:35 [--out file.parquet]
py -3 tools/market_data.py quotes SYMBOL YYYY-MM-DD --from 09:30 --to 09:31
py -3 tools/market_data.py bars SYMBOL YYYY-MM-DD --tf 10s|1m|5m [--from --to]
py -3 tools/market_data.py movers high_min=100 price_max=20 date_from=2021-01-01 [limit=200]
py -3 tools/market_data.py board YYYY-MM-DD --at 09:45 --list gainers|losers|gappers|afterhours
py -3 tools/market_data.py splits SYMBOL --day YYYY-MM-DD    # splits, and the factor for that day's raw prices
py -3 tools/market_data.py bench
py -3 tools/market_data.py catalog                          # every dataset: history, as-of rule, units
py -3 tools/market_data.py scan price_min=2 price_max=20 high_min=50 date_from=2021-01-01 --out r.parquet
py -3 tools/market_data.py sec-shares SYMBOL --day YYYY-MM-DD   # shares outstanding / issued / treasury filed by then
py -3 tools/market_data.py sec-filings SYMBOL --as-of YYYY-MM-DD --forms "4,SC 13D,424B4"
py -3 tools/market_data.py financials SYMBOL --statement balance_sheets|income_statements --as-of YYYY-MM-DD
py -3 tools/market_data.py float SYMBOL | ipos --symbol SYMBOL | ticker SYMBOL | short-interest SYMBOL YYYY-MM-DD
py -3 tools/market_data.py runway SYMBOL YYYY-MM-DD       # cash, burn, runway, share growth, offering filings (read age_days / stale)
py -3 tools/market_data.py find date_from=... price_min=2 price_max=20 high_min=50 --float-max 20000000
py -3 tools/market_data.py daily SYMBOL FROM TO | context DAY | stats SYMBOL DAY | flow SYMBOL DAY --bucket 5m
py -3 tools/market_data.py halts --symbol SYMBOL --day DAY | catalysts SYMBOL --from DAY --to DAY | symbols QUERY
```

The same reads are MCP tools on the `nova-data` server (ADR 059; `.cursor/mcp.json`, `.mcp.json`): call
`data_catalog` first. For small-cap momentum research start with `find_stock_days` (movers + shares known that day +
catalyst + halts + premarket marks, paged by `next_cursor`), then `stock_day_stats`, `order_flow`, `catalysts`,
`halts`, `daily_bars` / `market_context`, `symbols`; plus `stock_day`, `movers_search` / `movers_scan`, `board`,
`splits`, `financials`, `sec_shares`, `sec_filings`, `cash_runway` (cash, burn, runway, share growth and shelf /
offering filings as known on a day), `float_latest`, `ipos`, `ticker_details`, `short_interest`.
Percents are points in and out (the movers and board stores keep fractions); `--as-of` / `day` count a statement or
SEC fact from the day it was filed; a float filter is SEC shares OUTSTANDING unless you pick another basis -- say
which one you used. A ticker two companies used reads the company that held it that day (`ticker` in the answer).
A hook blocks reading the raw stores any other way.

trades / quotes / bars are raw (never split-adjusted); add `--adjust` for today's terms, or in Python
`from market_reads import splits` -- `splits.table / factor / adjust`.

In Python: `sys.path.insert(0, "research"); from market_reads import reads` -- `reads.trades / quotes / bars /
movers / board` return pandas DataFrames (movers: the agent endpoint's answer).

Before you trust a number, read `docs/market-data.md` ("The traps"): unadjusted prices, which prints set a price,
the day bar's whole-session volume, look-ahead, news before 2021-04, no Level 2 history.

- A read on a day without its seek index takes minutes; `status` shows the indexed share. Don't start a bulk
  `index` run without checking one is not already running (`E:\Nova\massive\sim\index\index-build.log`).
- Large scans (hundreds of stock-days) go in the background at below-normal priority; the desk shares the PC.
- To show a stock-day to the operator on the desk, use the `nova-sim-navigator` skill.
- To chart trades (entry / exit marked, 10-second bars), never write a plotting script: one call draws up to 9
  stock-days -- MCP `nova_trade_charts` on `nova_charts`, or
  `py -3 tools/nova_trade_charts.py export --trades-file t.json --output NEWDIR --massive-root E:\Nova\massive`
  with `[{"symbol","date","entry_time":"HH:MM:SS","entry_price","exit_time","exit_price","stop?","pivot?"}]`
  (`exits:[{time,price}]` for partials). Only each chart's window of trades is read. The MCP tool keeps a warm
  renderer (stops after 10 idle minutes and with the server); from a shell add `--warm` (same idle stop;
  `py -3 tools/nova_chart_warm.py stop` ends it sooner). Warm, 9 charts: about 3 s for stock-days charted before
  (cached bars), about 6 s for fresh ones on a busy PC. Contract in
  `architecture/schema/local-historical-charts.md` ("Trade charts").
- A `trades` / `quotes` read with `--from` / `--to` parses only that window (the same rows and dtypes as the whole
  day cut to it), so a few minutes of a busy day are quick even when the day is not in the read cache.
- Never place orders from this data, and never call it live: it is history.
