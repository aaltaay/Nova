# Data schema: The Market page

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/market_board/, frontend/src/market_board/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## The Market page (ADR 053, operator decisions 2026-10-12 and 2026-10-13)

"i want overall dashboard of the market ... identify the overall health of the market for the day in one glimpse",
mockups v1-v5 approved, then "go!". Owners `backend/market_board/` (read-only; constants in
`constants_market_board.py`) and `frontend/src/market_board/`. Nothing here places, stages or cancels an order, and
nothing here feeds a scanner row, a chart, HOD Momo, a setup lane or a bot. Percentages on this wire are percent
points (`2.84` = +2.84%), never fractions; times are epoch seconds; a period is `"1D" | "7D" | "30D"` (the session
so far, the last 5 sessions, the last 21 sessions, today included).

`GET /api/market/board?sectors=1D&industries=1D&climate=1D&top=biggest&top_period=1D` (`top`: `biggest` |
`runners`; `movers` was retired on 2026-10-14; an unknown value is 400 `MARKET_BAD_PARAM` with `field`) answers from memory and never waits on IBKR or
the network; asking marks the board wanted for `MARKET_WANTED_SEC` (the page's cadence; the board is kept warm at
a background cadence otherwise, below):

`{schema_version: 1, generated_at, enabled, loading, replay_desk, session, day_read, events, quotes[], breadth,
sectors, industries, climate, top, sources[]}` -- `enabled` false with `NOVA_MARKET_BOARD=0`; `loading` true until
every read the page waits on (the climate) has answered or failed once in this process; `replay_desk` true on a Sim replay
desk (the page reads today's live market and says so).

- `session`: `{date (the ET trading date, 04:00 rollover), phase: "premarket" | "regular" | "after_hours" | "closed",
  open_at, close_at, next: {kind: "premarket" | "open" | "close" | "after_hours_end", at} | null, holiday: string |
  null}` -- the NYSE calendar (`constants_nova_os` holidays, early closes); the clock's own facts.
- `day_read`: `{verdict: "bullish" | "mixed" | "bearish" | null, green, red, known, total, checks: [{id, label,
  state: "green" | "amber" | "red" | "waiting" | "unknown", value: number | null, text, starts_at: number | null,
  why}]}` --
  `id` one of `futures` (how many of ES, NQ, RTY, YM are up), `breadth` (NYSE advancing over declining), `vix`
  (VIX's change, green when falling), `small_caps` (RTY's change minus ES's, points), `runners` (today's 20%+
  runners against the same-minute average), `gappers` (gappers of 20%+ holding their 09:30 open). `waiting` with
  `starts_at` before the data can exist (breadth and gappers before 09:30); `unknown` with `why` when the source has
  not answered; `amber` when the check is neither green nor red. `known` counts the checks with data (green,
  amber, red); the verdict counts only green and red: `bullish` when `green - red >=
  MARKET_DAY_READ_BULLISH_NET` and `bearish` when `red - green >= MARKET_DAY_READ_BEARISH_NET`, else `mixed`;
  `null` under `MARKET_DAY_READ_MIN_KNOWN` known checks. Each check's rule and thresholds are constants. The
  `runners` check's `why` says when Nova recorded no Gainers board this session. `temperature: {day: "hot" | "warm"
  | "cold" | null, week: "good" | "ok" | "choppy" | "cold" | null, month: "hot" | "warm" | "cold" | null} | null`
  (ADR 053 amendment 2026-10-25) is the small-cap temperature of today, the last 5 and the last 21 sessions
  (`climate.heat`'s rules, below), whatever period the climate card shows; `null` until the climate has answered.
  It never counts toward the verdict.
- `events`: `{items: [{at, kind: "econ" | "fomc" | "earnings" | "holiday", title, detail: string | null, source:
  "bls" | "bea" | "fed" | "finnhub" | "sifma" | "nyse"}], bond_market: {closed: boolean, early_close_at: number |
  null, why: string | null}}` -- today and the next `MARKET_EVENTS_DAYS_AHEAD` days, soonest first, at most
  `MARKET_EVENTS_MAX`. BLS releases from its ICS calendar, BEA's from its release-dates JSON, FOMC decision days
  and SIFMA bond-market closes from constants copied from the published calendars (each with its URL), earnings
  from Nova's Finnhub calendar for the biggest names only (a member of a sector's top `MARKET_BIGGEST_PER_SECTOR`
  holdings).
- `quotes[]`: the futures and macro tiles, `MARKET_QUOTES` order: `{id, label, symbol, kind: "future" | "index" |
  "crypto" | "spread", exchange, contract: string | null (the front month's local symbol, e.g. "ESZ6"), last,
  prev_close, change, change_pct, price_basis: "last" | "mid" | "bars" | null (a coin with no print in the read
  shows its quoted midpoint; "bars" below), data_type: "live" | "frozen" | "delayed" | "delayed_frozen" | "bars" | null (IBKR's own
  market-data type for the read), at, stale: boolean, line: [[t, value]] (5-minute bars from 04:00 ET today, oldest first),
  error: string | null}`. `stale` is true when `last` came from a bar older than `MARKET_BARS_FRESH_SEC` (the
  market is not trading: CME's 17:00-18:00 ET pause, a weekend); the page dims the price and says "as of HH:MM". `prev_close` is IBKR's prior close from the read (a future's prior settlement), else the
  last daily bar before today (`prior:<id>`, read once a session: IBKR's Cboe index snapshots -- VIX, TNX -- came
  back with no last and no close on 2026-10-13 while their bars answered, so those tiles price from bars). The `small_caps`
  spread tile is RTY's `change_pct` minus ES's (`last` / `change` null, `change_pct` the points) and its line the
  difference of the two bar lines in percent from each prior close. A refused symbol carries IBKR's code and words
  in `error` ("10089: requires an additional subscription"), its numbers `null`.
- `breadth`: `{state: "ok" | "waiting" | "unavailable", why: string | null, at, data_type, advancing, declining,
  unchanged, up_volume, down_volume, tick, trin, ad_line: [[t, advancing - declining]], line_since, prior: {date,
  advancing, declining, up_volume, down_volume, tick, trin} | null}` -- IBKR's NYSE indicators: AD-NYSE (bid =
  advancing, ask = declining, bid size = unchanged), VOL-NYSE (bid = up volume, ask = down volume), TICK-NYSE and
  TRIN-NYSE (last). `ad_line` is Nova's own one-a-minute samples since `line_since` (the later of 09:30 and when
  Nova started sampling). `waiting` before 09:30 with `prior` the last session's last sample Nova kept;
  `unavailable` with IBKR's reason when it refuses the indicators, and in the session when the newest sample is
  older than `MARKET_BREADTH_STALE_SEC` ("no NYSE breadth sample since HH:MM ET"; the line is kept). After the
  close the day's last sample is the day's breadth, its volume and TRIN from `breadth-last.json` when that file is
  the same day's.
- `sectors` / `industries`: `{period, from, to, rows: [{name, etf, change_pct, context_pct, context_period,
  leader: {symbol, change_pct} | null, leader_why: string | null}]}` strongest first; `sectors` adds
  `offense_pct` and `defense_pct` (the mean of XLK, XLY, XLC and of XLP, XLU, XLV for the period). `change_pct` is
  the ETF's move over the period (1 D: last against the prior close; 7 D / 30 D: last against the regular-hours
  close 5 / 21 sessions back); `context_pct` is the 7 D move when the period is 1 D, else the 1 D move. The 1 D
  leader is the best member of the ETF (its State Street holdings file) among IBKR's large-cap gainers scan
  (`MARKET_MOVERS_SCAN`) and its top `MARKET_LEADER_POOL` holdings; 7 D / 30 D, the best of its top `MARKET_LEADER_POOL` holdings by daily closes. `leader:
  null` with `leader_why` when no member list exists (the theme ETFs of ADR 053) or no member has a price yet.
- `climate`: `{period, from, to, sessions, covered, lens, counts: {up20, up50, up100}, per_day: number | null,
  baseline: {up20, up50, up100, per_day, days, basis: "same_minute" | "per_session"} | null, temperature: "hot" |
  "warm" | "cold" | "good" | "ok" | "choppy" | null, heat: {...} | null (below), days: [{date, source: "recorded" | "reconstructed" | null, total, themes: {name:
  count}}] (the last 21 sessions, oldest first; `source: "massive"` = Nova holds no board that day and the Massive
  day movers index filled it, chart only (below); `source: null` = neither), theme: {name, count,
  total, share_pct, prev_share_pct} | null, themes: [{name, count, prev_count}], gappers: {held, total, rate_pct,
  gone, baseline_rate_pct}, halts: {count, last: {symbol, at} | null, by_side: null, by_side_why}, top: [{symbol,
  change_pct, date, price, float_shares, theme, news_at}]}` -- from the leaderboard store (ADR 023) through one
  `lens` (`{board: "gainers", rank_max: MARKET_CLIMATE_RANK_MAX, price_min: SCANNER_MIN_PRICE}`): the recorded
  Gainers board only. A rebuilt day's `market` board ranks every listed stock's minute bars rather than IBKR's
  scan and counted about 40% more runners a session, so it is left out (`MARKET_CLIMATE_USE_REBUILT`).
  **A past session with no board in the lens is filled from Massive** (ADR 053 amendment 2026-10-14, operator: "fill
  out the previous days by using data from Massive"): `backend/day_movers/`'s index, read-only, when it has built
  that session from its minute bars (`sessions.minute_bars = 1`; one indexed before its minute file arrived has no
  marks and stays `null`). A runner there is a common stock (`MARKET_CLIMATE_MASSIVE_KINDS`, not split-suspect)
  whose minute bars first reached +20 / 50 / 100% over the prior close before the close (`up20_ts` / `up50_ts` /
  `up100_ts`), at `SCANNER_MIN_PRICE` or more at +20%. That day reads `source: "massive"` with its `total` and
  `themes`, and is drawn on the chart only: it has no top-50 rank, so it never enters `covered`, `counts`,
  `baseline`, `temperature`, `theme` / `themes`, `gappers`, `halts`, `top` or the runners tab. An index that is
  missing, unreadable or behind leaves the day `source: null`; a past day with no board is asked of the index again
  each refresh until it fills, the index opened at most once a refresh. A runner is a symbol whose `change_pct` reached 20 / 50 / 100% that session by the
  close (by now, today). `covered` counts the period's sessions Nova recorded; a session whose recorded Gainers
  board kept no row all day (`coverage.row_count` sums to 0) is not one -- it reads as no board (2026-10-23: IBKR
  never answered the scan, and the board was `live` and empty for 719 minutes). 1 D's `baseline` is the same
  minute-of-day average over the prior `MARKET_CLIMATE_BASELINE_DAYS_1D` recorded sessions, the minute taken at the
  session's own clock (after its close -- that night, a weekend -- the close); 7 D / 30 D's is the
  per-session average over the prior `MARKET_CLIMATE_BASELINE_DAYS` (`null` when Nova recorded none).
  **The temperature** (ADR 053 amendment 2026-10-25; `market_board/temperature.py`, thresholds `MARKET_TEMP_*`) reads
  the same lens for stocks whose prior close is `MARKET_TEMP_PRICE_MIN`-`MARKET_TEMP_PRICE_MAX` dollars. Per session,
  minute by minute: `runners_100` (how many reached +100%) and `money` (shares x last price of the
  `MARKET_TEMP_TOP` biggest gainers, by peak gain of 20% or more -- an estimate the board allows, compared only with
  itself); at the session's last minute `hold_pct`, the share of runners that peaked at `MARKET_TEMP_HOLD_PEAK`+ still
  keeping `MARKET_TEMP_HOLD_SHARE` of that gain (one no longer on a full board whose 50th row is below that keep
  counts as faded, otherwise as unknown and left out). A day's `usual_money` is the median of the prior
  `MARKET_TEMP_BASELINE_DAYS` recorded sessions at the same minute (`usual_days` of them; under
  `MARKET_TEMP_BASELINE_MIN`, no label). Day: `hot` with `MARKET_TEMP_HOT_RUNNERS`+ runners and `money > usual_money`,
  `cold` with none and `money <= usual_money`, else `warm`. Week (7 D): `cold` with `MARKET_TEMP_WEEK_COLD_DAYS`+ cold
  days, `good` with `MARKET_TEMP_WEEK_HOT_DAYS`+ hot days and a mean `hold_pct` of `MARKET_TEMP_WEEK_GOOD_HOLD`+,
  `choppy` under `MARKET_TEMP_WEEK_CHOPPY_HOLD`, else `ok` (at least `MARKET_TEMP_WEEK_MIN_DAYS` labelled days). Month
  (30 D): `score_pct` = (hot - cold) / labelled days, `hot` at `+MARKET_TEMP_MONTH_SCORE`, `cold` at minus it, else
  `warm` (at least `MARKET_TEMP_MONTH_MIN_DAYS` labelled). Today is read as of now, past sessions at their close.
  `temperature` is the period's label; `heat` is `{label, why: string | null (why there is no label), price_min,
  price_max, days: [{date, label: "hot" | "warm" | "cold" | null, runners_100: number | null, money: number | null,
  usual_money: number | null, usual_days, hold_pct: number | null}] (the period's sessions, oldest first; `null`
  numbers for a session with no board), hot, warm, cold, labelled, hold_pct: number | null (the labelled days'
  mean), score_pct: number | null (30 D only)}`. A theme is IBKR's industry
  category for the symbol (contract details), `"Unclassified"` until IBKR answers; `prev_*` is the period before.
  A gapper is a symbol whose open gap (`gap_pct` after 09:30) was 20%+; it held when its last price that session
  (by now, today) is at or above its open (`prev_close x (1 + gap_pct)`) while still on the board at the period's
  last minute; `gone` counts gappers no longer on the board (unknown, left out of `rate_pct`). Halts are the Nasdaq
  halt feed's `start` events; their up / down side is not recorded (`by_side: null`).
- `top`: `{kind, period, cards: [{name, etf, change_pct, rows: [{symbol, last, change_pct, spark: number[] |
  null}]}], why: string | null}` -- sectors in strength order, every sector (`MARKET_TOP_CARDS`), `MARKET_TOP_ROWS` rows
  each. `biggest`: each sector's top `MARKET_TOP_ROWS` holdings by weight, in that order, each priced by IBKR (1 D a
  snapshot against the prior close; 7 D / 30 D daily closes) and listed with `last` / `change_pct` `null` until it
  is (`why` says "IBKR has not priced the sectors' stocks yet" while no row has a price). `movers` (the large-cap
  gainers scan with the biggest names, strongest first) was retired on 2026-10-14 (operator: its cards held one
  stock -- "these cards under Movers are just wasting space"); the scan still feeds the sector board's 1 D leader. `runners`: the climate's
  runners of the period grouped by theme. `spark` is the period's daily closes (7 D / 30 D); `null` for 1 D.
- `sources[]`: `{id: "ibkr" | "ssga" | "bea" | "finnhub" | "leaderboard", label, ok: boolean | null, at,
  error}` -- `ok: null` until asked. A failed read keeps its last good answer for at most `MARKET_STALE_MAX_SEC`.

Refresh (`backend/market_board/refresh.py` runs, `backend/market_board/jobs.py` lists what each thread reads; daemon
threads `ibkr`, `history` and `files`, started with the process).
**Warm** (ADR 053 amendment 2026-10-13 evening): every read runs whenever IBKR is connected, at the cadence below
while the page asked within `MARKET_WANTED_SEC`, else at its background cadence (`MARKET_IDLE_QUOTES_TTL_SEC`,
`MARKET_IDLE_ETF_TTL_SEC`, `MARKET_IDLE_MOVERS_TTL_SEC`, `MARKET_IDLE_POOL_TTL_SEC`, `MARKET_IDLE_LINES_TTL_SEC`,
`MARKET_IDLE_CLIMATE_TTL_SEC`); `NOVA_MARKET_BOARD_WARM=0` runs them only while the page is wanted. `ibkr` reads lines: the NYSE breadth sample once a minute 09:30-16:00 ET whether or not the page is open;
quotes every `MARKET_QUOTES_TTL_SEC`; ETF quotes every `MARKET_ETF_TTL_SEC`; the movers scan every
`MARKET_MOVERS_TTL_SEC`; the biggest names (`pool_quotes:<n>`, `MARKET_POOL_CHUNK` stocks a read, so tile quotes
run between them) every `MARKET_HOLDINGS_QUOTES_TTL_SEC`. `history` reads bars and contract details, so it never waits behind a quote (ADR 053
amendment 2026-10-13): each tile's prior close (once a session) and bar line (every `MARKET_LINES_TTL_SEC`), read
together and tiles without a price first; the ETFs' and leaders' daily closes once per session; the bar prices
below; a runner's industry once, then from the file below. `files` reads State Street, BLS and BEA once a day and
the leaderboard climate every `MARKET_CLIMATE_TTL_SEC` (a past session's summary once per process). No line is
opened while fewer than `IBKR_BRIEF_MIN_FREE_LINES` market-data lines are free beyond Nova's own reserve
(`IBKR_L1_STREAM_RESERVE`, kept for an opening Trader tab).

**A line held for a moment** (`ibkr/brief_lines.py`, shared since ADR 054). A quote -- a tile, a breadth
indicator, an ETF, a mover -- is read by opening at most `IBKR_BRIEF_LINE_BATCH` lines at once, waiting for IBKR's
first ticks (a price and the prior close; a price alone after `IBKR_BRIEF_LINE_SETTLE_SEC`) and cancelling them, at
most `IBKR_BRIEF_LINE_WAIT_SEC` after they opened. An ETF's or a stock's price is its last trade, never a quote that
arrived first, and its line asks the desk's generic ticks (`IBKR_L1_GENERIC_TICKS`). A contract that already has a line (the desk's) is read from it and
never cancelled; a line the desk subscribes to during the read, or that anything else now listens to, is left open
for it. A line this read opens starts from a cleared ticker, so a quote with no price by the deadline reads `null`,
never the last read's value. Brief lines do not take the cold snapshot slot (`ib_scheduler.cold_slot`).

**Measured** (the perf record, ADR 026). Every read's wall time is an op `market_board.<read>` (`quotes`,
`etf_quotes`, `movers`, `breadth_latest`, `prior`, `line`, `closes`, `industries`, ...), and the time from the page
opening (`wanted_since`) to that read's first answer `market_board.first.<read>`.

**Without a spare line.** IBKR shares an account's lines with every platform its login uses (2026-10-13: Nova
could hold 45 of 100, HOD Momo 40 of them). Then the page opens no line and reads prices from bars, which hold
no line: a tile's `last` is its last 5-minute bar's close (`data_type: "bars"`, `at` the bar's start, `stale` past
`MARKET_BARS_FRESH_SEC`; the same when a line gets no trade, e.g. CME's daily pause) and its `prev_close` the last daily bar before today (`prior:<id>`, once a
day); ETFs and movers read their regular-session daily bars (`bar_quotes`: today's bar's close against the bar
before, no price before 09:30), the movers ranked by IBKR's scan (a scan holds no line) and at most
`MARKET_BARS_MOVERS_MAX` priced. Each symbol's answer is `{price, prev_close, no_trade, date, at}`, plus `error`
(price `null`) when IBKR refused that symbol. A pass the historical service sheds part way keeps what it read on top
of the earlier passes' answers for the same `date` (another day's are dropped), and the next pass, after
`MARKET_SHED_RETRY_SEC` rather than the TTL, reads the symbols with no answer first, then the oldest (2026-10-16:
every pass had started over at XLK, so 25 of 26 ETFs never priced). Every historical request of the page -- these bars, a tile's
5-minute line and prior close, the daily closes -- is shed while `MARKET_HISTORY_HEADROOM` (30) or fewer of IBKR's 60
requests of the 10 minutes are left: charts, the TraderTV exits (which leave 20) and LULD read first (2026-10-16: the
page's bars spent all 60, and the TraderTV exits waited over 30 minutes). Breadth has no bar fallback: it reads `unavailable` with "waiting for spare
market-data lines".

**Fenced errors.** An IBKR error on a `FUT`, `CONTFUT`, `IND`, `CASH` or `CRYPTO` contract is the Market page's: it
is recorded on that tile (`market_board.ibkr_reads.note_error`) and never sets the session's delayed-data fallback
(Error 10089 / 10167), the max-tickers note (101) or a farm notice (`ibkr/session_errors.py`).

**Persisted.**
- `<cache_dir>/market-board/board-store.json` `{schema_version: 1, saved_at, entries: {key: {at, value}}}` -- the
  store's IBKR answers (`quotes`, `etf_quotes`, `etf_bars`, `movers`, `movers_bars`, `pool_quotes:<n>`,
  `line:<id>`, `prior:<id>`, `closes:<SYM>`), written by the `files` thread at most every `MARKET_KEEP_SAVE_SEC`
  when one changed, read once at process start; owner `market_board/keep.py`. An entry keeps its own answer time,
  so the store's age rules (`MARKET_STALE_MAX_SEC`, each read's TTL and freshness check) decide what is shown and
  what is read again; an entry older than `MARKET_KEEP_MAX_AGE_SEC`, a key not listed above or an unknown
  `schema_version` is ignored, and an answer already newer in memory is kept.
- `<cache_dir>/market-board/breadth-last.json` `{schema_version: 1, date, advancing, declining, unchanged, up_volume,
  down_volume, tick, trin, at}` -- the last regular-session breadth sample, overwritten each sample; owner
  `market_board/breadth.py`; an unknown `schema_version` is ignored (no prior shown).
- `<cache_dir>/market-board/breadth-<date>.json` `{schema_version: 1, date, line_since, samples: [[t, advancing,
  declining, tick]]}` -- the day's samples so a restart keeps the line; files older than
  `MARKET_BREADTH_KEEP_DAYS` are deleted.
- `<cache_dir>/market-board/industries.json` `{schema_version: 1, symbols: {SYM: {industry, category, subcategory,
  at}}}` -- IBKR contract details per symbol; an entry older than `MARKET_INDUSTRY_MAX_AGE_DAYS` is asked again;
  unknown `schema_version` starts empty.
- `<cache_dir>/market-board/holdings-<ETF>.json` `{schema_version: 1, etf, as_of, fetched_at, rows: [{symbol, name,
  weight_pct}]}` -- State Street's file parsed; refetched when older than `MARKET_HOLDINGS_TTL_SEC`; when State Street
  cannot be read, a kept file is used only while younger than `MARKET_HOLDINGS_MAX_AGE_SEC`, else its members are unknown.
- Desk memory (not stored): the page's hook keeps its last answer for the life of the window, so the page opens on
  it at once and asks again (`useMarketBoard`).
- Desk: `localStorage nova.marketBoard.periods.v1` `{schema_version: 1, sectors, industries, climate, top: {kind,
  period}}` (owner `frontend/src/market_board/periods.ts`; an unknown version or value falls back to `1D` /
  `biggest`, a saved `movers` among them).
