# Data schema: The Cryptos page

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/crypto/, frontend/src/cryptos/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## The Cryptos page (ADR 040, operator ask 2026-09-30)

"give us a new tab called Cryptos ... what a person needs to see in the crypto world", then mockup v1
approved ("go ahead and build exact replica"). Owners `backend/crypto/` (read-only; constants in
`constants_crypto.py`) and `frontend/src/cryptos/`. Nothing here places, stages or cancels an order, and
nothing here feeds a scanner row, a stock's chart, HOD Momo, a setup lane or a bot. Percentages on this
page's wire are percent points (`2.84` = +2.84%), never fractions.

`GET /api/crypto/board` answers `{schema_version: 1, generated_at, enabled, loading, replay_desk, clock,
market, coins[], leverage, flows, bridge, next[], news[], sources[]}` from memory; asking marks the board
wanted for `CRYPTO_WANTED_SEC` and never waits on the network. `loading` is true until every source has
answered (or failed) once since it was wanted; `enabled` is false with `NOVA_CRYPTO=0`.
- `clock`: `{now, stock_session: "premarket" | "regular" | "after_hours" | "closed", stock_next: {kind:
  "premarket" | "open" | "close" | "after_hours_end", at}, crypto_day_start (the last 00:00 UTC),
  crypto_day_start_et ("HH:MM"), regions: {asia, europe, us} (that region's market hours by the clock),
  next_funding (the next 00:00 / 08:00 / 16:00 UTC settlement of the 8-hour exchanges), lanes: {asia, europe,
  premarket, regular, after_hours, funding}}` -- each lane `[[from, to], ...]` in minutes after ET midnight of
  today's ET date (Asia and Europe from their own clocks, weekdays; the stock lanes empty on a closed day; funding
  as `[m, m]`). The clock's own facts, no source.
- `market`: `{total_cap_usd, total_cap_change_24h_pct, btc_dominance_pct, btc_dominance_change_24h_pt,
  total_volume_usd, volume_x_30d, fear_greed: {value, label, week_ago, at} | null, eth_btc,
  eth_btc_change_24h_pct, btc_qqq_corr_30d}` -- CoinGecko's `/global` and `/coins/markets`; the dominance
  change is BTC's share 24 hours ago worked out from both answers' 24-hour changes; `volume_x_30d` is the
  listed coins' 24-hour volume over their own 30-day daily average (not the whole market's); Fear & Greed is
  alternative.me's; `btc_qqq_corr_30d` is the correlation of BTC's 16:00 ET-to-16:00 ET returns with QQQ's
  regular-hours closes over the last 30 shared sessions.
- `coins[]` (the `CRYPTO_COINS` table, rank order): `{symbol, name, rank, price, high_24h, low_24h,
  change_1h_pct, change_24h_pct, change_7d_pct, volume_24h_usd, volume_x_30d, market_cap_usd,
  from_ath_pct, spark_7d: number[], funding_8h_pct, groups: string[], why, news_checked, ibkr, etf,
  chart}`. `volume_x_30d` is the 24-hour volume over the coin's 30-day daily average (CoinGecko's
  `market_chart`, refreshed every `CRYPTO_VOLUME_HISTORY_TTL_SEC`). `funding_8h_pct` is Hyperliquid's hourly
  rate x 8. `why` is `{kind: "catalyst" | "negative" | "noise" | "news", title, source, published_ts, url} |
  null` -- the best Alpaca headline naming the coin in the last 24 hours, labelled by `crypto/classify.py`
  (rules `CRYPTO_NEWS_RULES_VERSION`); `news_checked` is true once Alpaca answered for the coin, so
  `why: null` with `news_checked: true` is "no news found" and with `false` is unknown. `ibkr` is `{listed,
  venue: "PAXOS" | "ZEROHASH" | null} | null` -- IBKR's own contract answer, `null` until asked (IBKR not
  ready). `etf` is the coin's US spot ETF on the desk (`IBIT`, `ETHA`) or `null`. `chart` says Coinbase
  carries a USD market for the candles route.
- `leverage`: `{funding: [{symbol, funding_8h_pct}] (high to low), open_interest_usd (the listed coins,
  Hyperliquid), btc_open_interest_usd, liquidations_24h: null, liquidations_note}` -- liquidations have no
  free source reachable from the desk and stay a stated absence.
- `flows`: `{etf: null, etf_note, stablecoins: {supply_usd, change_7d_usd, daily: [{date, net_usd}]} | null}`
  -- daily spot ETF flows have no free source and stay a stated absence; stablecoins are DefiLlama's USD-pegged
  supply and its daily change.
- `bridge`: `{reference_close_at (the last regular-session 16:00 ET close), phase: "premarket" | "regular" |
  "after_hours" | "overnight", btc_since_close_pct, eth_since_close_pct, rows: [{symbol, what, driver: "BTC" |
  "ETH", beta, close, last, since_close_pct, implied_pct, read: "ahead" | "behind" | "in_line" | null,
  gap_pt}], error: string | null}` for `CRYPTO_BRIDGE` (IBIT, ETHA, MSTR, COIN, MARA, RIOT, CLSK, HOOD).
  `close` is IBKR's regular-hours daily close of that session (`historical_service.request_rth_daily_closes`,
  background priority), `last` IBKR's snapshot (`snapshot_quotes`, cold), `null` when IBKR has not answered
  (a snapshot with no trade since that close is `null`, never the close). `beta` is the least-squares slope of
  the stock's close-to-close returns on the driver's 16:00 ET-to-16:00 ET returns over the last
  `CRYPTO_BETA_DAYS` shared sessions (`null` under `CRYPTO_BETA_MIN_DAYS`); `implied_pct` is the driver's
  move since the close x beta; `read` is `ahead` / `behind` when `since_close_pct - implied_pct` (`gap_pt`)
  is beyond `CRYPTO_BRIDGE_READ_BAND_PT`, else `in_line`, `null` when either is unknown. The driver's 16:00 ET
  prices are Coinbase's (the open of the hourly candle that starts at 16:00 ET).
- `next[]`: `{at, kind: "funding" | "expiry" | "stocks" | "crypto_day", title, detail: string | null}`,
  soonest first, at most `CRYPTO_NEXT_MAX` -- the clock's events, and Deribit's options expiries (every
  Friday 08:00 UTC; the month's last Friday is the monthly) with the BTC open interest expiring then when
  Deribit answered. No macro calendar or token unlocks: no free source.
- `news[]`: `{published_ts, symbol, kind, title, source, url}`, catalysts and negatives first, then newest,
  at most `CRYPTO_NEWS_MAX`.
- `sources[]`: `{id: "coingecko" | "coinbase" | "fear_greed" | "hyperliquid" | "defillama" | "deribit" |
  "alpaca" | "ibkr", label, ok: boolean | null, at: number | null, error: string | null}` -- `ok: null`
  until asked. A failed source keeps its last good answer for at most `CRYPTO_STALE_MAX_SEC`, then its
  numbers read `null`; no source's numbers ever stand in for another's.

`GET /api/crypto/candles?symbol=BTC&tf=15m` (`tf`: `15m` | `1h` | `4h` | `1d`) answers `{schema_version: 1,
symbol, tf, product, source: "coinbase", loading, error, candles: [{t, o, h, l, c, v}] (oldest first, `t` the
bucket start, `v` null when Coinbase gave none), last, change_24h_pct, levels: {high_24h, low_24h, day_open,
day_open_at, stock_close: {at, price} | null}, sessions: [{kind: "premarket" | "regular" | "after_hours",
start, end}]}` -- Coinbase
Exchange's public candles (4h built from hourly), the levels from the 15-minute series, the US stock sessions
inside the window; 400 `CRYPTO_UNKNOWN_SYMBOL` / `CRYPTO_UNKNOWN_TF`. Nothing is fetched on the request:
it answers the cache (`loading` while the first read runs) and asks the refresher.

Refresh while wanted (`backend/crypto/refresh.py`, two daemon threads, web and IBKR): CoinGecko markets
every `CRYPTO_MARKETS_TTL_SEC`, global every `CRYPTO_GLOBAL_TTL_SEC`, volume history one coin at a time;
Hyperliquid every `CRYPTO_PERPS_TTL_SEC`; Alpaca news every `CRYPTO_NEWS_TTL_SEC`; Fear & Greed,
DefiLlama and Deribit every `CRYPTO_SLOW_TTL_SEC`; IBKR snapshots every `CRYPTO_BRIDGE_QUOTE_TTL_SEC`, daily
closes once per session (again after 16:00 until that session's bar lands), the crypto listing once per
process. Nothing polls when the page has not asked within `CRYPTO_WANTED_SEC`. `COINGECKO_DEMO_API_KEY`
(optional) is sent as CoinGecko's demo key. On the desk every number, chip, level and lane opens a hover
card (`frontend/src/cryptos/tips/`): what it means, a small drawing, what it reads now, why it matters.

