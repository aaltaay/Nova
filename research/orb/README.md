# ORB research harness (Phase L, gate 1)

Offline backtest of the long-only **5-minute opening range breakout on stocks in play**
(Zarattini, Barbon & Aziz 2024) on five years of Massive (formerly Polygon) minute flat
files. Research only: nothing here is imported by `backend/` and nothing places orders.
Plan, decisions and results: `knowledge/obsidian/03-Nova-Decisions/Bot-Trading-Plan.md`.

## Data

`massive_flatfiles.py` downloads `us_stocks_sip/minute_aggs_v1` and `day_aggs_v1` to
`F:\Nova\data\massive` (`NOVA_MARKET_DATA_DIR` overrides) with the S3 pair from the desk
`.env` (`MASSIVE_S3_ACCESS_KEY_ID` / `MASSIVE_S3_SECRET_ACCESS_KEY`). Resumable, retried,
whole files in parallel. The files are unadjusted; `build_store.py --reference` pulls the
splits and ticker types through the REST API (`MASSIVE_API_KEY`) so selection can exclude
funds, warrants, units and any symbol with a split inside its lookback.

## Pipeline

| Step | Command (repo root) | Produces |
|---|---|---|
| 1 | `py -3 research/orb/build_store.py` | `open5`: per symbol-day pre-market volume, the 09:30-09:35 candle and the RTH OHLCV |
| 2 | `py -3 research/orb/build_store.py --reference` | `tickers`, `splits` |
| 3 | `py -3 research/orb/build_store.py --no-build --select --top 30` | `selection`: the published filter + opening relative-volume rank |
| 4 | `py -3 research/orb/extract_minutes.py` | `minutes_selected`: RTH minute bars for selected symbol-days only |
| 5 | `py -3 research/orb/backtest_orb.py --top 20 --tag base` | `store/orb_<tag>.json` + trades / equity CSVs |

The store is one DuckDB file, `F:\Nova\data\massive\store\orb.duckdb`. Steps 1 and 4 are
incremental (a day is built once). Re-run step 3 after step 2, then clear `extracted_days`
and `minutes_selected` before step 4 if the selection changed. `run_gate1.py` chains
build, select, extract, the base run and the robustness pass in one log.

Also here:

| Script | Purpose |
|---|---|
| `robustness.py` | stop x top-N grid, cost sensitivity, cutoffs, sizing, rank buckets, years, months |
| `swing_baseline.py` | the five published SPY mean-reversion rules on free yfinance daily bars (comparison row) |
| `massive_reference_dump.py` | everything else the plan serves: dividends, exchanges, ticker details, news archive, short data; writes `store/reference/manifest.json` with counts and anything refused |
| `fetch_seconds.py` | one-second bars 09:30-11:00 ET for the selected symbol-days into `store/seconds.duckdb` (settles entry-bar stop ambiguity) |
| `results_*_2026-09-22.json` | the gate-1 run, its robustness table and the SPY baseline, as produced |

Gap and Go (second candidate, same store):

| Script | Purpose |
|---|---|
| `build_premarket.py` | per symbol-day pre-market high / low / last / volume and the 09:30-10:00 range (`premarket`) |
| `build_news.py` | loads the news archive (`news_tickers`, with the Eastern session each article is a catalyst for) and ticker details (`ticker_details`) from the reference dump |
| `select_gng.py` | the Five Pillars at 09:30, ranked by pre-market relative volume; `--no-float` for the survivorship-safe variant |
| `backtest_gng.py` | buy stop at the pre-market high, $0.20 / 4% stop, half off at 2R with breakeven, rest at 4R or 11:30; `--grid` for the neighbourhood |
| `run_gate1_gng.py` | chains news load, both selections, one extraction for their union, base run and grid |

Large-cap daily mean reversion (third candidate, daily files):

| Script | Purpose |
|---|---|
| `build_daily.py` | `daily` from `day_aggs_v1`, split-adjusted `daily_adj` (factor = product of later `split_from / split_to`), `daily_ind` (prev close / high, SMA100 / SMA200, 20-day dollar ADV) and `daily_rsi` (Wilder RSI(2) as an EWM) |
| `backtest_mr.py` | buy the close on RSI2 < 10 above the 200-day, sell the first close above the prior high or after 10 days, 5 names at 20%; `--grid` for the neighbourhood, universe floors and costs; a delisted holding closes at its last print |

Gate-1 outcomes (2026-09-22): ORB not passed (§2b), Gap and Go not passed (§2c),
large-cap mean reversion not passed (§2d; its mega-cap cell A4b is recorded as the first
cost-robust cell, in sample) -- see `knowledge/obsidian/03-Nova-Decisions/Bot-Trading-Plan.md`.
The fourth candidate (the SPY swing rules through the kill tests) is pre-registered in §2e.

## Honesty

- Lookbacks are the ticker's prior 14 trading rows; nothing reads its own day or ahead.
- Entry: buy stop at the 5-minute high, filled at `max(bar open, level) + slippage` on the
  first later bar that trades through it (cutoff 15:30). Red or doji first candle: no trade.
- Stop: `stop_atr x ATR14` below the fill. On the entry bar it counts only when the bar
  closes at or below the stop (the low may have printed before the fill). Afterwards the
  first low at or below the stop fills it, at the open when the bar gaps through.
- Exit: last regular-session bar close, minus slippage.
- Costs: IBKR fixed ($0.005/share, min $1, max 1% of value) each side, plus `slippage`
  per share on every fill. `--commission 0.0035 --commission-min 0 --slippage 0` is the
  paper's assumption, for comparison only.
- Sizing: `risk_pct` of equity per position, notional capped per position
  (`max_position_pct`) and per day at the account's cash. No margin, no shorts (the
  operator's account is cash). Orders reserve cash at placement in rank order, so a
  never-triggered order still ties up its cash that day, as it would at IBKR.
