# Massive dataset builders

Every big research dataset Nova keeps beside the Massive flat files, the script that builds it, and what each column
means as the code computes it. Research tooling only: nothing in `backend/` imports these builders and none of them
places an order. Reading the data back is the market data front door (`docs/market-data.md`, ADR 059).

Paths below are relative to `NOVA_MARKET_DATA_DIR` (default `E:\Nova\massive`). Column lists were confirmed on disk on
2026-10-18 with schema-only reads (`pyarrow.parquet.read_schema` on the newest file; DuckDB `DESCRIBE` on a read-only
connection), except where a section says the product has no file yet.

## Where the builders live

| Builders | Folder | Builds |
|---|---|---|
| Trades, quotes and reference archives, raw-file verification | `research/massive_builders/` | `trades_flow_v1`, `trades_movers_v1`, `quotes_v1`, `quotes_movers_v1`, `store/reference/` (month files), `verified.jsonl`, `verify_all.json` |
| ORB / Gap and Go / daily research store | `research/orb/` (README there) | `minute_aggs_v1`, `day_aggs_v1`, `store/orb.duckdb`, `store/seconds.duckdb`, the first `store/reference/` dump |
| Other tables in `orb.duckdb` | `research/shorts/select_shorts.py`, `research/catalysts/build_shares.py` | `shorts_selection`, `sec_shares`, `short_interest` |
| Bollinger mean-reversion store | `research/bb_mr/data_builder.py` | `store/bb_mr.duckdb` |
| Signal table (the Trader's signals on past days) | `research/signals/build_signals.py` (README there) | `F:\Nova\signals` (`NOVA_SIGNALS_DIR`): `minutes/`, `days/`, `tape/`, `manifest.json`; contract in `architecture/schema/agent-desk.md` |
| Relative-volume table (#1100) | `research/rvol/build_rvol.py` (README there) | `F:\Nova\rvol` (`NOVA_RVOL_DIR`): `minutes/`, `days/`, `manifest.json`; contract in `architecture/schema/agent-desk.md` |

### Environment

| Variable | Read by | Meaning |
|---|---|---|
| `NOVA_MARKET_DATA_DIR` | every builder | data root (default `E:\Nova\massive`) |
| `NOVA_EDGE_LAB_DIR` | `research/massive_builders` | the research lab whose own ticker lists join each day's movers (`data/evt/d=<day>/part.parquet`, `data/archive_extra_tickers.parquet`); `massive_inventory.py` writes `data/massive_inventory.json` there. Default `F:\Nova\private\edge-lab`; missing files are skipped |
| `NOVA_ENV_PATH` | `research/massive_builders`, `research/orb` | the `.env` holding the keys (massive_builders default: the repo's `.env`; orb: the first `.env` walking up from the working folder) |
| `MASSIVE_S3_ACCESS_KEY_ID`, `MASSIVE_S3_SECRET_ACCESS_KEY`, `MASSIVE_S3_ENDPOINT` | flat-file downloads | the S3 pair (endpoint default `https://files.massive.com`); a process variable wins over the file; never printed |
| `MASSIVE_API_KEY` (else `POLYGON_API_KEY`, else the S3 secret) | REST pulls | Massive issues the REST key and the S3 secret as the same value |

### Commands (repo root)

| Builder | Command |
|---|---|
| Trades archive | `py -3 research/massive_builders/massive_archive.py plan [year]` / `fetch [workers] [year]` / `process [workers]` / `verify [workers] [year]` / `run [workers] [year]` / `one YYYY-MM-DD` |
| Quotes archive | `py -3 research/massive_builders/quotes_archive.py plan [year]` / `fetch [workers] [year]` / `run [workers] [year]` / `one YYYY-MM-DD` |
| Reference archive | `py -3 research/massive_builders/reference_archive.py run [workers] [--only name,name]` / `status` |
| Access probe | `py -3 research/massive_builders/massive_access.py` |
| End-to-end check | `py -3 research/massive_builders/verify_all.py [--quick]` |
| Bucket inventory | `py -3 research/massive_builders/massive_inventory.py` |
| ORB store and friends | see `research/orb/README.md` (pipeline table) |
| bb_mr store | `py -3 research/bb_mr/data_builder.py [--rebuild]` |

Every `research/massive_builders` command answers `--help` without touching the network or the disk. The jobs run
hours to days; `<root>/STOP` makes every one of them stop after the file in hand. On the operator's PC they are started
by the research lab's download supervisor (`downloader.py run`, scheduled task `NovaLabDownloads` at logon, outside this
repo): trades and quotes `fetch` per year, trades `process 3`, trades `verify 1`, and `reference_archive.py run 6` every
half hour.

**Switching the PC to these copies (operator step, not done by the PR that moved them).** The supervisor still spawns
the lab's own copies: in the lab's `lab/downloader.py`, the job table names `"lab/massive_archive.py"` and
`"lab/quotes_archive.py"`, and three `spawn([...])` calls name `lab/massive_archive.py` (`process 3`, `verify 1`) and
`lab/reference_archive.py` (`run 6`). Point those five strings at `research/massive_builders/` in the main checkout.
The repo copies keep the same data root, state files, `.env` and named mutexes, so a lab copy and a repo copy can never
run at once; stop the running job with `<root>/STOP` first, then remove `STOP` after the switch. The `.ps1` files in
`E:\Nova\massive` and `E:\Nova\massive\store` (`run_download`, `run_pipeline`, `run_extract`, `run_seconds`,
`run_reference_dump`) are stale -- they call deleted temp copies of `research/orb` scripts against the old
`F:\Nova\data\massive` root; run the `research/orb` commands above instead.

## Raw flat files (as Massive serves them)

`<dataset>/YYYY/MM/YYYY-MM-DD.csv.gz` for `trades_v1`, `quotes_v1`, `minute_aggs_v1`, `day_aggs_v1`; `.part` while
arriving. A day counts as downloaded only when its size equals the size Massive lists. Columns are Massive's (read with
the explicit column types in `trades_products.SRC` and `quotes_archive.QSRC`). Timestamps are integer nanoseconds since
the Unix epoch (UTC).

## trades_flow_v1

`trades_flow_v1/YYYY/MM/YYYY-MM-DD.parquet` (zstd, 500,000-row groups), under `archive_config.json` "products_root".
Built by `massive_archive.py process` (or `run` / `one`) through `trades_products.process` from the day's `trades_v1`
file. One row per **(ticker, minute)** that had at least one counted print. 2,712 days on disk on 2026-10-17.

**Which prints count.** Kept: `correction` 0 or 12, `price > 0`, `size > 0`, and minute `m` in 0..1439. Dropped
entirely: conditions 15 and 16 (the official open / close records) and 38 (corrected consolidated close), which repeat
the auction print. **Not-at-market prints** (`nm`) are conditions 2, 7, 10, 13, 20, 21, 22, 29, 52, 53 (average price,
cash, derivatively priced, sold out of sequence in extended hours, next day, price variation, prior reference, seller,
contingent, qualified contingent): they add to `np_vol` only and to no other column. Conditions are matched as whole
codes inside Massive's comma-separated `conditions` string.

**Sub-penny digits.** `z = round(price * 10000) mod 100`: the hundredths of a cent of the price (10.0071 gives 71).

**Venue ids** are Massive's `exchange` ids (its `exchanges.json`): 4 = FINRA ADF / TRF (every off-exchange print:
dark pools, wholesalers, internalizers; `trf_id` is not used here), 12 Nasdaq, 10 NYSE, 11 NYSE Arca, 19 Cboe BZX,
8 Cboe EDGX, 15 IEX, 21 MEMX, and the inverted (taker-maker) venues 2 Nasdaq BX ("Nasdaq Texas" in Massive's list),
7 Cboe EDGA, 18 Cboe BYX.

| Column | Type | Definition (every count and sum is over market prints, `nm` false, unless it says otherwise) |
|---|---|---|
| `ticker` | string | Massive ticker |
| `m` | int32 | minute of the day: `(sip_timestamp - 00:00 America/New_York of the file's day, in ns) // 60e9`; DST-correct; 570 = 09:30 ET, 240 = 04:00, 960 = 16:00 |
| `n` | int32 | number of prints |
| `vol` | int64 | shares |
| `dvol` | double | dollars, sum of `size * price` |
| `np_vol` | int64 | shares of not-at-market prints (`nm` true) |
| `off_n`, `off_vol` | int32, int64 | prints / shares off exchange (`exchange = 4`) |
| `rb_n`, `rb_vol` | int32, int64 | retail buys: off exchange, `price >= 1`, `z` 61..99 (priced just under a whole cent: a wholesaler's price improvement to a buyer; the sub-penny rule of Boehmer, Jones, Zhang and Zhang) |
| `rs_n`, `rs_vol` | int32, int64 | retail sells: off exchange, `price >= 1`, `z` 1..39 |
| `mid_vol` | int64 | shares off exchange, `price >= 1`, `z` 40..60 (near the half cent: midpoint crosses) |
| `iso_n`, `iso_vol` | int32, int64 | intermarket sweeps: condition 14 on an exchange print (`exchange <> 4`) |
| `odd_n`, `odd_vol` | int32, int64 | odd lots: `size < 100` or condition 37 |
| `big_n`, `big_vol` | int32, int64 | big prints: `size * price >= $25,000` |
| `blk_vol` | int64 | block shares: `size * price >= $200,000` |
| `max_sz` | int64 | largest single print's size |
| `v_xnas`, `v_xnys`, `v_arcx`, `v_bats`, `v_edgx`, `v_iexg`, `v_memx` | int64 | shares by venue: exchange 12, 10, 11, 19, 8, 15, 21 |
| `v_inv` | int64 | shares on the inverted venues (exchange 2, 7, 18) |
| `ext_vol` | int64 | shares with condition 12 (Form T: outside regular hours) |

Retail and midpoint shares are a subset of `off_vol`; off-exchange prints under $1 and those on a whole cent (`z = 0`)
count in `off_*` only.

## trades_movers_v1

`trades_movers_v1/YYYY/MM/YYYY-MM-DD.parquet` (zstd, 1,000,000-row groups), built in the same pass as the flow table.
**Every raw trade** of the day's movers, unfiltered (corrections, conditions and out-of-hours prints included), ordered
by `ticker, ts, seq`.

**The day's movers** (`trades_products.movers`, shared with the quotes archive): from that day's `minute_aggs_v1`
file, per ticker, dollar volume `sum(volume * close) >= $1,000,000`, `max(high) <= $100`, `min(low) >= $1`, and either
`max(high) / min(low) - 1 >= 20%` or `max(high) / prior close - 1 >= 10%` (prior close: the `close` of the nearest earlier
`day_aggs_v1` file within 7 days); plus every ticker of the lab's event file for that day and of
`archive_extra_tickers.parquet` for that day (both under `NOVA_EDGE_LAB_DIR`, when present).

| Column | Type | Definition |
|---|---|---|
| `ticker` | string | Massive ticker |
| `ts` | int64 | `sip_timestamp`: ns since epoch (UTC), when the SIP published the trade |
| `pts` | int64 | `participant_timestamp`: ns since epoch, the venue's own time |
| `p` | double | price |
| `s` | int32 | size, shares |
| `x` | int8 | Massive exchange id (4 = FINRA TRF / ADF, off exchange) |
| `c` | string | Massive's comma-separated condition codes, as served |
| `corr` | int8 | Massive's correction indicator |
| `seq` | int64 | Massive's sequence number |
| `trf` | int16 | Massive's `trf_id`: which FINRA trade reporting facility reported an off-exchange print |

## quotes_v1 and quotes_movers_v1

`quotes_archive.py fetch` keeps `quotes_v1/YYYY/MM/YYYY-MM-DD.csv.gz` (the raw NBBO file, 10 GB a day in 2026).
`quotes_archive.py run` also builds `quotes_movers_v1/YYYY/MM/YYYY-MM-DD.parquet`: every quote of the same day's movers
(the list above), ordered by `ticker, ts, seq`. **On 2026-10-18 the folder exists but holds no file**: the supervisor only
starts `fetch`, so no movers product has been built yet. The columns below are the code's (`quotes_archive.QRAW`),
pinned by `backend/tests/test_massive_builders.py`.

| Column | Type | Definition |
|---|---|---|
| `ticker` | string | Massive ticker |
| `ts` | int64 | `sip_timestamp`, ns since epoch (UTC) |
| `pts` | int64 | `participant_timestamp`, ns since epoch |
| `bp`, `bs`, `bx` | double, int32, int8 | bid price, bid size (Massive's `bid_size` cast to integer), bid exchange id |
| `ap`, `asz`, `ax` | double, int32, int8 | ask price, ask size, ask exchange id |
| `c` | string | Massive's quote condition codes |
| `ind` | string | Massive's quote indicators |
| `seq` | int64 | Massive's sequence number |

## Reference data (`store/reference/`)

Two writers share this folder. `research/orb/massive_reference_dump.py` made the first dump (from 2021-06 / 2021-09):
`tickers.json`, `exchanges.json`, `ticker_types.json`, `ticker_details.jsonl`, `manifest.json`, `news/`, and single
files. `research/massive_builders/reference_archive.py` keeps every dated dataset month by month from 2016-01 and
**rewrites** the single files `dividends.json`, `splits.json`, `short_interest.jsonl`, `short_volume.jsonl` from its
month files once every month is on disk (so they now start in 2016). `research/leaderboard/lb_io.py` reads that
`splits.json`.

Every row is Massive's own API result object, one JSON object per line (the `.json` single files are JSON arrays).
Month file: `<dataset>/YYYY-MM.jsonl`, each row filed by its own date field.

| Dataset | Endpoint | Date field | Fields (first row of a month file, 2026-10-18) |
|---|---|---|---|
| `news` | `/v2/reference/news` | `published_utc` | article_url, author, description, id, image_url, insights, keywords, published_utc, publisher, tickers, title |
| `dividends` | `/v3/reference/dividends` | `ex_dividend_date` | cash_amount, currency, declaration_date, dividend_type, ex_dividend_date, frequency, id, pay_date, record_date, ticker |
| `splits` | `/v3/reference/splits` | `execution_date` | execution_date, id, split_from, split_to, ticker |
| `ipos` | `/vX/reference/ipos` | `listing_date` | announced_date, currency_code, final_issue_price, highest_offer_price, ipo_status, isin, issuer_name, last_updated, listing_date, lot_size, lowest_offer_price, max_shares_offered, primary_exchange, security_description, security_type, shares_outstanding, ticker, total_offer_size, us_code |
| `short_interest` | `/stocks/v1/short-interest` | `settlement_date` | avg_daily_volume, days_to_cover, settlement_date, short_interest, ticker |
| `short_volume` | `/stocks/v1/short-volume` | `date` | adf_short_volume(_exempt), date, exempt_volume, nasdaq_carteret_short_volume(_exempt), nasdaq_chicago_short_volume(_exempt), non_exempt_volume, nyse_short_volume(_exempt), short_volume, short_volume_ratio, ticker, total_volume |
| `income_statements` | `/stocks/financials/v1/income-statements` | `filing_date` | cik, tickers, filing_date, fiscal_year, fiscal_quarter, period_end, timeframe, revenue, cost_of_revenue, gross_profit, operating_income, net income and EPS lines, ebitda, shares outstanding (basic, diluted) and the other statement lines |
| `balance_sheets` | `/stocks/financials/v1/balance-sheets` | `filing_date` | cik, tickers, filing_date, fiscal_year, fiscal_quarter, period_end, timeframe, total_assets, total_liabilities, total_equity, cash_and_equivalents, debt and the other balance-sheet lines |
| `cash_flow_statements` | `/stocks/financials/v1/cash-flow-statements` | `filing_date` | cik, tickers, filing_date, fiscal_year, fiscal_quarter, period_end, timeframe, net cash from operating / investing / financing and the other cash-flow lines |

Snapshots (Massive keeps no history, so one file a day from 2026-10-09): `snapshots/ratios/YYYY-MM-DD.jsonl` and
`ratios.jsonl` (the latest: average_volume, cash, cik, current, date, debt_to_equity, dividend_yield,
earnings_per_share, enterprise_value, ev_to_ebitda, ev_to_sales, free_cash_flow, market_cap, price, price_to_book,
price_to_cash_flow, price_to_earnings, price_to_free_cash_flow, price_to_sales, quick, return_on_assets,
return_on_equity, ticker); `snapshots/float/YYYY-MM-DD.jsonl` and `float.jsonl` (effective_date, free_float,
free_float_percent, ticker).

A month is final once fetched with both date bounds at least 14 days after it ended; until then a run fetches it again
when its last fetch is 12 hours old. The financial statements must fit one 50,000-row page per month (their cursor
loses rows across pages); `/stocks/v1` endpoints are fetched unsorted (sorted, their cursor skips rows).

## Store tables

### `store/orb.duckdb` (research/orb and neighbours)

All times are Eastern wall-clock (`window_start` ns converted `AT TIME ZONE 'America/New_York'`). Prices are unadjusted
except `daily_adj`, `daily_ind`, `daily_rsi`. Tables on disk on 2026-10-18 (`DESCRIBE` worked, read-only):
`built_days, daily, daily_adj, daily_days, daily_ind, daily_rsi, extracted_days, gng_selection, gng_selection_nofloat,
gng_union, minutes_gng, minutes_gng_days, minutes_pillars, minutes_pillars_all, minutes_pillars_all_days,
minutes_pillars_days, minutes_selected, minutes_shorts, minutes_shorts_days, news_months, news_tickers, open5,
pillars_all, premarket, premarket_days, sec_shares, selection, short_interest, shorts_selection, splits,
ticker_details, tickers`.

**`open5`** (`build_store.py`): one row per ticker-day from that day's minute file.

| Column | Type | Definition |
|---|---|---|
| `ticker`, `d` | VARCHAR, DATE | key |
| `pm_volume` | BIGINT | volume of bars before 09:30 |
| `o5_open`, `o5_high`, `o5_low`, `o5_close`, `o5_volume`, `o5_bars` | DOUBLE x4, BIGINT, INTEGER | the 09:30-09:35 bars: first open, max high, min low, last close, volume, bar count |
| `rth_open`, `rth_high`, `rth_low`, `rth_close`, `rth_volume`, `rth_bars` | DOUBLE x4, BIGINT, INTEGER | the same over 09:30-16:00 |

**`premarket`** (`build_premarket.py`): one row per ticker-day.

| Column | Type | Definition |
|---|---|---|
| `ticker`, `d` | VARCHAR, DATE | key |
| `pm_high`, `pm_low`, `pm_last` | DOUBLE | max high, min low, last close of bars before 09:30 (the minute file starts at 04:00) |
| `pm_volume`, `pm_bars` | BIGINT, INTEGER | volume and bar count before 09:30 |
| `pm_high_t` | TIME | bar time of the pre-market high (`arg_max(t, high)`) |
| `h30`, `l30`, `v30`, `c30` | DOUBLE, DOUBLE, BIGINT, DOUBLE | 09:30-10:00 high, low, volume, last close |

**`daily_ind`** (`build_daily.py`): from `daily_adj` (split-adjusted `daily`).

| Column | Type | Definition |
|---|---|---|
| `ticker`, `d` | VARCHAR, DATE | key |
| `close`, `high`, `low` | DOUBLE | adjusted bar |
| `factor` | DOUBLE | split factor: product of `split_from / split_to` over the ticker's later splits (1.0 when none) |
| `prev_close`, `prev_high` | DOUBLE | previous row's close / high |
| `sma200`, `sma100` | DOUBLE | mean close of the last 200 / 100 rows including today |
| `adv20_usd` | DOUBLE | mean `close * volume` of the 20 prior rows (excluding today) |
| `n_hist` | BIGINT | rows in the 200-row window |

Other tables, one line each (columns as `DESCRIBE` shows them):
- `daily` (ticker, d, open, high, low, close, volume, transactions): `day_aggs_v1` rows as served. `daily_adj` adds `factor` (prices times it, volume divided by it).
- `daily_rsi` (ticker, d TIMESTAMP, rsi2): Wilder RSI(2) on adjusted closes, an EWM with alpha 0.5.
- `tickers` (ticker, name, type, active, primary_exchange, list_date, delisted_utc) and `splits` (ticker, execution_date, split_from, split_to): from the reference JSON (`build_store.py --reference`).
- `selection` (`build_store.py --select`): the stocks-in-play filter with `prev_close, adv14, atr14, avg_o5_14, n14` over the 14 prior rows, `rvol = o5_volume / avg_o5_14`, `direction` of the first candle, `rank` per day by `rvol`.
- `gng_selection`, `gng_selection_nofloat`, `pillars_all` (`select_gng.py`, the last with `--no-float --no-news --top 10000`): `open5` joined to `premarket` plus `prev_close, prev_d, adv14, avg_pm14, n14, gap = o5_open / prev_close - 1, rvol_pm = pm_volume / max(avg_pm14, 1000), news_n, float_shares, market_cap, o5_dir, rank`. `gng_union` (`run_gate1_gng.py`): their (ticker, d) union.
- `minutes_selected`, `minutes_gng`, `minutes_pillars`, `minutes_pillars_all`, `minutes_shorts` (`extract_minutes.py --selection <table> --table <name>`): (ticker, d, t TIME, open, high, low, close, volume) minute bars of the selected ticker-days from `--start` (09:30 by default; 04:00 for shorts) to 16:00. The `*_days` / `extracted_days` / `built_days` / `premarket_days` / `daily_days` / `news_months` tables record which days or months each step built.
- `news_tickers` (ticker, published_utc, session_d, article_id, publisher, title) and `ticker_details` (`build_news.py`): `session_d` is the Eastern session an article is a catalyst for (after 16:00 ET rolls to the next weekday).
- `shorts_selection` (`research/shorts/select_shorts.py`): d, ticker, prior_close, up10_ts, mover, former_momo, ssr_yesterday.
- `sec_shares` (ticker, cik, end_d, filed_d, shares, form, concept) and `short_interest` (ticker, settlement_d, short_interest, avg_daily_volume, days_to_cover) (`research/catalysts/build_shares.py`).

### `store/seconds.duckdb` (`research/orb/fetch_seconds.py`)

`seconds_selected` (ticker, d, t_ms BIGINT, open, high, low, close, volume BIGINT, n INTEGER): Massive's unadjusted
one-second bars 09:30-11:00 ET (defaults) for the selected long ticker-days; `t_ms` is the bar start in epoch
milliseconds, `n` the trade count. `seconds_done` (ticker, d, rows, status, fetched_at) records each fetch.

### `store/bb_mr.duckdb` (`research/bb_mr/data_builder.py`)

Built from `orb.duckdb` (attached read-only). `close_min` / `open_min` are minutes after Eastern midnight of a bar's
close / open (a 09:30 bar has `open_min` 570, `close_min` 571).
- `corp_splits` (ticker, d, split_from, split_to) from `orb.splits`; `corp_dividends` (ticker, d, cash_amount) from `reference/dividends.json` (USD, positive, 2021-10-01..2026-10-01).
- `pit_daily_meta` (ticker, d, prev_close, adv20_usd over 20 prior rows, n_prior20, sec_type, primary_exchange, is_active_2026, pit_shares_out = latest `sec_shares` filed by d, in_split_window): common stocks / ADRs on the main listing exchanges, without split-window days.
- `meta_univ_a` (... has_ext, adv_rank): up to 30 names a day by `adv20_usd` among pre-session-known candidates (`former_momo`, `pillars_all`, `selection`), $5-$200, ADV >= $20M.
- `ub_scanner_top20` (ticker, d, close_min, close, cum_dvol, prev_close, is_active_2026, pit_shares_out, rnk): each minute's top 20 by cumulative dollar volume among `minutes_shorts` names at $1-$30, up 10% or more, cum dollar volume >= $500k. `meta_univ_b` is its per-day roll-up.
- `sig_1m_ext`, `sig_5m_ext`, `sig_5m_rth`, `sig_1h_rth` (ticker, d, close_min, bar_idx, OHLCV, then `n/sma/std` for 20 / 50 / 100 / 200 bars, population std): Bollinger inputs over each ticker's consecutive bars (1-minute 04:00-11:00 ET for `sig_1m_ext`, 5-minute 04:00-16:00 for `sig_5m_ext` and 09:30-16:00 for `sig_5m_rth`, hourly 09:30-16:00 for `sig_1h_rth`), kept only for ticker-days where a lower-band rejection happens while in a universe (`sig_1h_rth`: every bar of a ticker that signalled on a universe day). `bars_1m_exec` (ticker, d, open_min, close_min, OHLCV, cum_dvol, trail5_vol) holds the 1-minute execution bars of those days. The 5-minute tables come from `research/bb_mr/signal_5m.py`: built when missing (the band warmup runs over every day of the ticker, not only universe days), compacted when present. A rebuild reproduces the lab-built rows exactly, and it can keep a few more days than an old store because that store was compacted under an earlier universe.

## State and check files

| File | Writer | Shape |
|---|---|---|
| `verified.jsonl` | `massive_bucket.check_new_file` after each download; `massive_archive.py verify` (`raw_verify.py`) | one line per gzip read: `{f: path relative to the root, size, ok, why, at}`; the last line of a path wins |
| `verify_halted.txt` | `raw_verify.py` | written after 4 failures in one verify run; the check stays off until a person removes it |
| `verify_all.json` | `verify_all.py` | `{at, ts, from, to, quick, pass, passed, checks: [{id, name, ok, level, detail}], took_s}` |
| `archive_state.json` / `process_state.json` | `massive_archive.py` (fetch or run / process), every 60 s | `{at, mode, year, pass, days_with_products, raw_files_kept, days_in_this_pass, free_gb_products_drive, workers_alive, workers_replaced}` |
| `quotes_state.json` | `quotes_archive.py` | `{at, mode, year, pass, days_with_product, raw_files, free_gb_E, workers_alive, workers_replaced}` |
| `archive_config.json` | the operator | `{raw_dirs, products_root, keep_raw, other_drive_floor_gb}` |
| `plan_cache.json` | the lab's download supervisor (outside this repo) | `{built, from, plan: {dataset: {YYYY-MM-DD: size}}}`; the builders use it when under 12 hours old |
| `access.json` | `massive_access.py` | `{schema_version: 1, state, last_ok, last_ok_file, refused_since, refused_n, last_probe, last_result, last_reason, ended_at}` |
| `store/reference/reference_state.json` | `reference_archive.py` | `{schema_version: 1, months: {dataset: {YYYY-MM: {rows, bytes, at, fetched_at, bounded, first, last, outside, v}}}, errors, snapshots, last_run}`; another schema_version refuses loud |
| `archive.log`, `quotes_archive.log`, `store/reference/reference.log` | the jobs | one timestamped (Eastern) line per event |
| `STOP` | the operator | present = every job stops after the file in hand |

The three `*_state.json` progress files carry no `schema_version` (they are status snapshots rewritten every minute,
never read back by the builders).
