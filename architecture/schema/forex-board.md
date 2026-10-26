# Data schema: The Forex page

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/forex_board/, frontend/src/forex_board/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## The Forex page (ADR 062, operator asks 2026-10-20)

"I want something similar but for forex", "We got to also say the total market, dude", "For each market, we want to
see what's going on, like how big it is and everything", mockup v2 approved: "build this to be on top of the global".
Owners `backend/forex_board/` (read-only; constants in `constants_forex_board.py`) and `frontend/src/forex_board/`.
Nothing here places, stages or cancels an order, and nothing here feeds a scanner row, a chart, HOD Momo, a setup lane,
a bot, the Market page or the Global page.

**Two kinds of number, never mixed.** The market's size -- the total, the desks, each currency's turnover and biggest
pair -- is the BIS Triennial Central Bank Survey's (April 2025 daily averages, published every three years, not live),
shown with that month and source, and it computes nothing. Everything else is IBKR's: spot forex on IDEALPRO (no extra
subscription) and CME currency futures, through the paced historical service and a line held for a moment. No figure
is estimated. Percentages are percent points (`0.42` = +0.42%); times are epoch seconds; money is US dollars.

`GET /api/forex/board?period=1D` (`period`: `"1D"` | `"7D"` | `"30D"`; anything else is 400 `FOREX_BAD_PARAM` with
`field`) answers from memory and never waits on IBKR; asking marks the page wanted for `FOREX_WANTED_SEC`:

`{schema_version: 1, generated_at, enabled, loading, replay_desk, period, fx_day, market, read, dollar, sessions[],
currencies[], sun, sources[], budget}` -- `enabled` false with `NOVA_FOREX_BOARD=0`; `loading` true until every read
has answered or failed once in this process (or was kept from the last one); `replay_desk` true on a Sim replay desk
(the page reads today's live market and says so).

- `fx_day`: `{from, to, open, next_open_at}` -- the FX day shown: 17:00 New York to 17:00 the next day, the market's
  own day. Forex trades from Sunday 17:00 to Friday 17:00 ET; between those (`open` false) the last FX day is shown and
  `next_open_at` is Sunday's 17:00.
- `market` (BIS): `{total_usd, exchange_traded_usd, covered_pct, instruments: [{name, usd}], desks: [{name, usd,
  share_pct}], regions: {asia_pacific, europe, americas: share_pct}, as_of: "2025-04", source, url}` -- `total_usd` the
  daily turnover, "net-net"; `exchange_traded_usd` the survey's memo of exchange-traded FX futures and options;
  `covered_pct` the share of all trading the page's currencies take part in (each currency's share / 2, since two take
  part in every trade); `desks` where the dealers' sales desks are ("net-gross"): the UK, the US, Singapore, Hong Kong,
  Japan, ..., `Other`.
- `read`: `{verdict: "safe_havens" | "risk_on" | "dollar_bought" | "dollar_sold" | "quiet" | null, headline, detail,
  rose: [code], fell: [code], rule}` -- `null` under `FOREX_READ_MIN_PRICED` priced currencies. `safe_havens` when the
  yen's and franc's average strength is at `+FOREX_READ_GROUP_PCT[period]` or more and the riskier currencies'
  (`FOREX_RISKIER`, those priced) at `-FOREX_READ_GROUP_PCT[period]` or less; `risk_on` the reverse; otherwise
  `dollar_bought` / `dollar_sold` when the dollar's strength is at `±FOREX_READ_DOLLAR_PCT[period]` or past; else
  `quiet`. `rose` / `fell` the three strongest and weakest (`FOREX_PEGGED`, the Hong Kong dollar, left out: it moves
  with the dollar); `detail` names the strongest three in words ("Money ran to the yen, the franc and the dollar").
- `dollar`: `{strength_pct, up_against, down_against, priced, pressure_usd, pressure_pct, traded_usd, size_usd,
  share_pct}` -- the dollar's strength and its futures money (below), against how many priced currencies it rose / fell.
- `sessions[]` (always the FX day shown, whatever the period): `{id: "asia" | "london" | "new_york", name, from, to,
  state: "done" | "now" | "later", rose: {code, pct} | null, fell: {code, pct} | null, desks: {label, share_pct}}` --
  each hour of the FX day belongs to the newest region open: Asia from the FX day's start until London's 08:00, London
  until New York's 08:00, New York to the FX day's end. `rose` / `fell` the biggest strength change over those hours
  (pegged left out); `desks` the BIS share of the region's dealers (Asia-Pacific, the UK, the US).
- `currencies[]`, `FOREX_CURRENCIES` order (biggest first): `{code, name, city, lat, lon, tz, home, size, price,
  strength_pct, by_session, range_x, volume_x, futures, mixed}`.
  - `home`: `{open, open_at, close_at, next_open_at}` -- 08:00-17:00 in the currency's home city on a weekday, while
    the FX day is open.
  - `size` (BIS): `{usd, share_pct, rank, pair, pair_usd}` -- the daily turnover of every trade the currency is on one
    side of, its share of all trades (the shares add to 200%), its rank in the survey, and its biggest pair.
  - `price`: `{basis: "spot" | "future" | null, instrument, pair, rate, open, pair_pct, vs_usd_pct, at, data_type,
    error}` -- `pair` as the market quotes it ("EUR/USD", "USD/JPY"); `rate` now; `open` the pair's level at the start
    of the period; `pair_pct` its move; `vs_usd_pct` the currency's own move against the dollar (the inverse for a
    pair quoted per dollar). 1 D: the midpoint now -- a line held for a moment (`ibkr.brief_lines`), else the newest
    one-hour bar -- against the close of the one-hour bar that ends at the FX day's start. 7 D / 30 D: daily midpoint
    closes 5 / 21 completed FX days back against the last completed one. `basis: "future"` when IBKR has no spot quote
    but the currency has a CME future (the Brazilian real): the same rule on the future's one-minute (1 D) or daily
    bars. `null` numbers with `error` (IBKR's own words) when nothing answered. The dollar's row: `basis: "spot"`,
    `pair: null`, `vs_usd_pct: 0`.
  - `strength_pct`: the currency against an even mix of the other priced currencies, `mean((1 + vs_usd_c) / (1 +
    vs_usd_k) - 1)` -- `null` without a price.
  - `by_session`: `{asia, london, new_york}` -- its strength change over each session's hours of the FX day shown
    (`null` for a session still to come).
  - `range_x`: the FX day's high-low range so far (one-hour bars and the quote) over the average range of its last
    `FOREX_NORMAL_DAYS` completed FX days (daily bars); `volume_x`: its future's contracts so far over their average
    full day over the same days. `null` when either side is missing.
  - `futures`: `{basis: "future" | "sum" | null, instrument, inverted, traded_usd, up_usd, down_usd, pressure_usd,
    pressure_pct, contracts, last_bar_at, at, error, refused: [{instrument, error}]}` -- 1 D: the FX day's one-minute
    TRADES bars of the currency's CME future (IBKR's continuous future); a bar is up when it closed above the bar
    before it, down when below, flat otherwise; its notional is volume x average price x multiplier (contracts priced
    in dollars per unit), or volume x multiplier for a contract worth dollars and priced in the currency (`inverted`:
    USD/CNH), whose up bar is the yuan sold. `pressure_usd = up_usd - down_usd` from the currency's side,
    `pressure_pct = pressure_usd / traded_usd x 100`. 7 D / 30 D: the last 5 / 21 completed FX days' daily bars, each
    day up or down by the currency's own move that day. The dollar's row is `basis: "sum"`: the other side of every
    future -- `traded_usd` their sum, `pressure_usd` minus the sum of theirs. `refused` lists what IBKR refused for
    the currency (its future, its spot pair) with IBKR's code and words.
  - `instrument`: `{kind: "spot" | "future", symbol, label, exchange, currency, contract (a future's front month),
    multiplier}`.
  - `mixed`: true when `futures.pressure_pct` and `strength_pct` point opposite ways, each past
    `FOREX_MIXED_PRESSURE_PCT` / `FOREX_MIXED_STRENGTH_PCT`.
- `sun` (always the FX day shown): `{from, to, now, hours: [{t, strength: {code: pct}, futures: {code: pct}}],
  tracks: [{id, name, from, to, share_pct}]}` -- 24 hours from the FX day's start; `strength` each priced currency's
  strength change in that hour (the hour now forming to the latest price), `futures` each future's pressure as a share
  of its money that hour (the dollar's the other side of all of them); an hour still to come is absent. `tracks` the
  Asia (Sydney's 08:00 to Tokyo's 17:00), London and New York sessions (08:00-17:00 local), with their desks' share.
- `sources[]`: `{id: "ibkr", label, ok: boolean | null, at, error}` -- `ok: null` until asked.
- `budget`: `{history_left: number | null, history_headroom, waiting: "history" | "lines" | null}` -- the page sends no
  historical request while `history_headroom` or fewer of IBKR's 60-a-10-minutes are left (`FOREX_HISTORY_HEADROOM`,
  or `FOREX_YIELD_HEADROOM` while the Market or Global page shows and this one does not), and opens no line while
  fewer than `IBKR_BRIEF_MIN_FREE_LINES` are spare.

**The currencies** (`FOREX_CURRENCIES`, the survey's 19 most traded, 95% of all trading): USD (New York), EUR
(Frankfurt), JPY (Tokyo), GBP (London), CNY (Shanghai; IBKR quotes the offshore yuan, USD.CNH), CHF (Zurich), AUD
(Sydney), CAD (Toronto), HKD (Hong Kong), SGD (Singapore), INR (Mumbai), KRW (Seoul), SEK (Stockholm), NZD (Wellington),
MXN (Mexico City), NOK (Oslo), TWD (Taipei), BRL (São Paulo), ZAR (Johannesburg). CME futures for EUR, JPY, GBP, CHF,
CAD, AUD, NZD, MXN, BRL, ZAR and the offshore yuan.

**Reads, last in line** (`backend/forex_board/refresh.py`, one daemon thread started with the process). IBKR is asked
only while it is connected. While the page is wanted: the spot quotes every `FOREX_QUOTES_TTL_SEC` (a line held for a
moment), each pair's one-hour bars once per completed hour, each future's one-minute bars every `FOREX_FLOW_TTL_SEC`
while the FX day is open (once more after it closes), and each pair's and future's daily bars once per FX day. Not
wanted: the quotes and futures at `FOREX_IDLE_QUOTES_TTL_SEC` / `FOREX_IDLE_FLOW_TTL_SEC`, but never from 09:30 to
16:00 ET (`NOVA_FOREX_BOARD_WARM=0` reads only while wanted). Every historical request goes through the paced service
at background priority under its own pacing kind `forex`, only while more than the page's headroom is left, at least
`FOREX_HISTORY_GAP_SEC` after its last. A refused instrument is not asked again for `FOREX_REFUSED_RETRY_SEC`.

**Kept across restarts** (`backend/forex_board/keep.py`): `<cache_dir>/forex-board/forex-store.json`,
`{schema_version: 1, saved_at, entries: {key: {at, value}}}` -- the reads' last answers (`quotes`, `hourly:<CODE>`,
`daily:<CODE>`, `flow:<CODE>`, `flow_daily:<CODE>`, `refused:<key>`), written at most every `FOREX_KEEP_SAVE_SEC` when
one changed and read back at the first start, each at its own answer time; an entry older than
`FOREX_KEEP_MAX_AGE_SEC` (a weekend and a day) is not read back, and a file of another `schema_version` reads as
absent.

**On the desk** (`frontend/src/forex_board/`): the first item of the nav rail, above Global. The page polls every
`FOREX_POLL_MS` while it shows and the window is visible, fills the window and never scrolls (the world board kit,
`frontend/src/world_board/`, shared with the Global page). Its switches (what the map and Follow the sun show, and the
period) are kept in localStorage `nova.forexBoard.prefs.v1`, `{schema_version: 1, period, color_by: "strength" |
"futures"}` (owner `prefs.ts`; another version or an unknown value reads as 1D / strength; the sample desk never writes
it). The head strip: all forex (the BIS total, its desks), the read, the dollar, the three sessions. A world map, one
bubble per currency sized by its BIS turnover, coloured by strength or futures pressure, a dashed ring while its home
session is open; Follow the sun (each currency hour by hour under the sessions); the 8 majors' pairs (row against
column, from each currency's move against the dollar); and the currencies biggest first with their size, strength and
futures. A currency IBKR does not price says "no price", one without a future "no futures", each with IBKR's reason on
hover.
