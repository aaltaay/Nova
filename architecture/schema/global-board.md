# Data schema: The Global page

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/global_board/, frontend/src/global_board/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## The Global page (ADR 060, operator asks 2026-10-15 and 2026-10-20)

"Does our dashboard show how much money entered and exited the stock market? ... a new tab called Global that shows
the entire world and how much money entered and left each exchange", mockups v1-v2 iterated as PNGs (v2 approved:
pressure and the index move side by side), "I want the tab to be above Market", and on the data: "we bought all the
needed data, we shouldn't have estimate unless we must, label those explicitly". Owners `backend/global_board/`
(read-only; constants in `constants_global_board.py`) and `frontend/src/global_board/`. Nothing here places, stages or
cancels an order, and nothing here feeds a scanner row, a chart, HOD Momo, a setup lane, a bot or the Market page.

**Every number is measured; none is estimated.** A market's money is the real trades of its own index futures in
its own hours (or, where IBKR has no such future or refuses it, of its US-listed country ETF, named on the row);
dollars are those trades' notional at IBKR's own exchange rates. An exchange's total value or turnover is not on
this wire: no feed publishes either live, and the operator ruled out estimates the page does not need. Percentages
on this wire are percent points (`2.84` = +2.84%); times are epoch seconds; money is US dollars.

`GET /api/global/board?period=1D` (`period`: `"1D"` | `"7D"` | `"30D"`; anything else is 400 `GLOBAL_BAD_PARAM` with
`field`) answers from memory and never waits on IBKR; asking marks the page wanted for `GLOBAL_WANTED_SEC`:

`{schema_version: 1, generated_at, enabled, loading, replay_desk, period, read, world, regions[], markets[], sun,
sources[], budget}` -- `enabled` false with `NOVA_GLOBAL_BOARD=0`; `loading` true until every market's flow has
answered or failed once in this process (or was kept from the last one); `replay_desk` true on a Sim replay desk
(the page reads today's live markets and says so).

- `markets[]`, `GLOBAL_MARKETS` order: `{id, name, exchange, city, region, lat, lon, tz, session, move, flow,
  mixed}` -- `id` e.g. `"jp"`; `region` one of `americas`, `europe`, `middle_east_africa`, `asia_pacific`.
  - `session`: `{date (the market's own date of the session shown), state: "open" | "break" | "closed" |
    "holiday", open_at, close_at, segments: [[start, end]], next_open_at, calendar: "nyse" | "clock"}` -- the
    session shown is today's once it has opened (by the market's own clock), else the last one. `break` is a lunch
    pause between two segments (Tokyo, Hong Kong, Shanghai). `calendar: "clock"` means Nova knows the market's hours
    and weekdays (Tadawul trades Sunday to Thursday) but not its holidays; `"nyse"` reads Nova's NYSE calendar
    (holidays and early closes).
  - `move` (the index move): `{basis: "index" | "future" | "etf" | null, instrument, pct, last, prev_close, at,
    data_type, error}` -- 1 D: the home index's last against its prior close, from a line held for a moment
    (`ibkr.brief_lines`); without one, the home future's last 1-minute close against its last 1-minute close of
    the market's previous session; without a home future, the country ETF's last against its last regular-hours
    close of the session before. 7 D / 30 D: the home index's
    (else the ETF's) regular-hours daily close 5 / 21 sessions back against its last. `null` numbers with `error`
    when nothing answered.
  - `flow` (the money): `{basis: "future" | "etf" | null, instrument, from, to, bars | sessions, up_usd, down_usd,
    flat_usd, traded_usd, pressure_usd, pressure_pct, last_bar_at, fx, at, error, refused: [{instrument, error}]}`.
    1 D: the session's 1-minute TRADES bars of the instrument, inside the market's own session (a future's overnight
    hours are not the market's). A bar is **up** when it closed above the bar before it in IBKR's answer, **down**
    when below, flat otherwise (a first bar with none before it is flat); its notional is volume x the bar's
    average price x the contract multiplier (1 for an ETF) x `fx.usd_per_unit`. `pressure_usd = up_usd -
    down_usd`; `pressure_pct = pressure_usd / traded_usd x 100`. 7 D / 30 D: the last 5 / 21 completed sessions of
    daily bars, each session up or down by its `move` instrument's close, its notional the future's (else the ETF's)
    daily volume x average x multiplier x `fx`. `fx`: `{currency, usd_per_unit, date}` from IBKR's daily MIDPOINT
    close of the pair (`null` for a USD instrument); without a rate the `_usd` fields are `null` and `error` says so,
    `pressure_pct` still stands. `refused` lists each instrument IBKR refused for this market today, with IBKR's
    code and words, so a row that fell back to its ETF says why.
  - `instrument`: `{kind: "index" | "future" | "etf", symbol, label, exchange, currency, contract: string | null
    (a future's front month, e.g. "N225Z6"), multiplier: number | null}`.
  - `mixed`: true when `pressure_pct` and `move.pct` point opposite ways, each past `GLOBAL_MIXED_PRESSURE_PCT` /
    `GLOBAL_MIXED_MOVE_PCT`: buyers were eager and the index still fell, or the reverse.
- `regions[]`: `{id, label, pressure_usd, traded_usd, pressure_pct, markets, flows, up, down, avg_move_pct}` --
  sums of the region's markets that have a flow in US dollars (`flows` counts them, `markets` all of them); `up` /
  `down` count markets whose `move.pct` is above / below zero; `avg_move_pct` is the plain average of the known
  moves (not weighted: weights would need each market's size). `world` has the same shape without `id` / `label`.
- `read`: `{verdict: "money_in" | "money_out" | "rotation" | "quiet" | null, headline, detail, rule}` -- `null` under
  `GLOBAL_READ_MIN_FLOWS` flows. `money_in` when the world's `pressure_pct >= GLOBAL_READ_NET_PCT`, `money_out` when
  `<= -GLOBAL_READ_NET_PCT`; otherwise `rotation` when one region is at `+GLOBAL_READ_REGION_PCT` or more and
  another at `-GLOBAL_READ_REGION_PCT` or less, else `quiet`. `detail` names the strongest buying and selling regions
  ("Asia-Pacific sold, the Americas bought").
- `sun` (always the last 24 hours, whatever the period): `{from, to, now, hours: [{t, net_usd, traded_usd,
  by_region: {id: net_usd}}], sessions: [{market, region, start, end}]}` -- 24 whole hours ending with the current
  one, oldest first; an hour sums the 1-minute bars of every market's flow that started in it, inside that market's
  session; `sessions` are the markets' session segments clipped to the window.
- `sources[]`: `{id: "ibkr", label, ok: boolean | null, at, error}` -- `ok: null` until asked.
- `budget`: `{history_left: number | null, history_headroom, waiting: "history" | "lines" | null}` -- why reads are
  waiting: the page sends no historical request while `GLOBAL_HISTORY_HEADROOM` or fewer of IBKR's 60-a-10-minutes
  are left, and opens no line while fewer than `IBKR_BRIEF_MIN_FREE_LINES` are spare.

**The markets** (`GLOBAL_MARKETS`; the instruments are IBKR's, the hours each market's own, in its own time zone):
the US (NYSE + Nasdaq; S&P 500 index and its futures on CME, SPY), Canada (TSX; S&P/TSX Composite, S&P/TSX 60
futures on CDE, EWC), Brazil (B3; EWZ), the UK (LSE; FTSE 100 and its futures on ICE Europe, EWU), France
(Euronext Paris; CAC 40 and its futures on MONEP, EWQ), Germany (Xetra; DAX and its futures on Eurex, EWG),
Switzerland (SIX; SMI and its futures on Eurex, EWL), Saudi Arabia (Tadawul; KSA), South Africa (JSE; EZA), India
(NSE; Nifty 50, INDA), China (SSE + SZSE; FTSE China A50 and its futures on SGX, ASHR), Hong Kong (HKEX; Hang Seng and
its futures on HKFE, EWH), Taiwan (TWSE; EWT), South Korea (KRX; KOSPI 200 and its futures on KSE, EWY), Japan (JPX;
Nikkei 225 and its futures on OSE, EWJ), Australia (ASX; S&P/ASX 200 and SPI 200 futures on SNFE, EWA). A market
with no home future reads its ETF, whose trades are US money in US hours, and the row says so.

**Reads, last in line** (`backend/global_board/refresh.py`, one daemon thread started with the process). IBKR is
asked only while it is connected. While the page is wanted: each open market's flow every `GLOBAL_FLOW_TTL_SEC`, a
market that closed once more after its close, the index quotes every `GLOBAL_QUOTES_TTL_SEC`, each currency's FX
close once per ET date, and -- for 7 D / 30 D only -- each market's daily bars once per ET date. Not wanted: the same
flows, quotes and FX closes at `GLOBAL_IDLE_FLOW_TTL_SEC` / `GLOBAL_IDLE_QUOTES_TTL_SEC`, but never from 09:30 to
16:00 ET, the desk's own hours, and no daily bars (`NOVA_GLOBAL_BOARD_WARM=0` reads only while wanted). Every historical request goes through the
paced service at background priority, under its own pacing kind `global` (the capacity strip's History hover names
it), and only while more than `GLOBAL_HISTORY_HEADROOM` are left: charts, the short check, the TraderTV exits, LULD
and the Market page all come first. A refused instrument is not asked again for `GLOBAL_REFUSED_RETRY_SEC`.

**Kept across restarts** (`backend/global_board/keep.py`): `<cache_dir>/global-board/global-store.json`,
`{schema_version: 1, saved_at, entries: {key: {at, value}}}` -- the reads' last answers (`flow:<id>`, `quotes`,
`daily:<id>`, `fx:<ccy>`, `refused:<key>`), written at most every `GLOBAL_KEEP_SAVE_SEC` when one changed and read
back at the first start, each at its own answer time; an entry older than `GLOBAL_KEEP_MAX_AGE_SEC` is not read back,
and a file of another `schema_version` reads as absent.

**On the desk** (`frontend/src/global_board/`): the first item of the nav rail, above Market. The page polls every
`GLOBAL_POLL_MS` while it shows and the window is visible. Its switches (the period and what the map's colour shows) are kept in localStorage `nova.globalBoard.prefs.v1`, `{schema_version: 1, period, color_by}` (owner `prefs.ts`; another version or an unknown value reads as 1D / pressure; the sample desk never writes it). A world map (Natural Earth land, public domain, through
`world-atlas` 2.0.2, drawn once into `worldLand.ts`), one bubble per market sized by `traded_usd` and coloured by
`pressure_pct` or `move.pct` (the switch), a dashed ring while the market is open; the four regions and the world;
the markets ranked by pressure with both bars; the last 24 hours of pressure; and pressure against the move. A row
that reads its ETF says "via EWZ"; a market IBKR has not answered says "no feed" and IBKR's reason.
