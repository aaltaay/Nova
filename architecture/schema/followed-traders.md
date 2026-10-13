# Data schema: Followed traders

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/followed_traders/,
frontend/src/followed_traders/. Same law as the constitution: a wire or persisted shape changes here first, in the
same commit as the code (Invariants #1 and #5).

## Followed traders (operator ask, 2026-10-13)

The operator follows a group of traders whose open positions another program of theirs records: a **feed** on the
operator's own machine, outside this repository. The feed knows each trader's name, side, ticker and entry or average
price, and when a position opened, changed or closed. It knows no size, stop, target or exit price. Nova shows the
feed's open positions and closed trades on a page of their own and prices them with Nova's own IBKR data: the price
now for an open position, and the tape at the exit for a closed one. Owners `backend/followed_traders/` (read-only;
constants in `followed_traders/constants_followed.py`) and `frontend/src/followed_traders/`. Nothing here places,
stages or cancels an order, and nothing here feeds a scanner row, a chart, HOD Momo, a setup lane or a bot. Copying a
trade is a later, Paper-only bot, never Live; it is not built here.

### The gate

`NOVA_FOLLOW_FEED_URL` in the desk's `.env` (e.g. `http://127.0.0.1:8787`) turns the page on. Unset -- the default,
and every public install -- there is no page, no route and no request to any feed: `app_routers` registers the
router only when the value is set when the app is built. The desk asks `GET /api/followed-traders/config` once per
window (`{schema_version: 1, enabled: true}`); a 404 -- the route does not exist -- means off and is not asked again,
and only a backend that did not answer at all is asked again (every `FOLLOWED_PROBE_RETRY_MS`, a bounded number of
times). The sample desk asks nothing. The value must be an `http://` or `https://` URL; any other value is treated as
unset and logged once. It is never sent to the browser.

### The feed Nova reads (the feed's own format; operator confirmed settled, 2026-10-13)

Nova reads two routes of the feed and one folder of images, and nothing else:

- `GET {url}/api/day?date=YYYY-MM-DD` answers `{date, today, dates[], status, trades[], events[]}`. Nova reads:
  - `date` (the day answered), `today` (the feed's ET date), `dates[]` (days the feed has, newest first);
  - `status`: `{video: {title}, live, clock ("HH:MM:SS" ET, the last frame read), updated_at (ISO 8601 with
    offset), bar_visible, traders: string[], problem?, problem_at?} | null` -- `null` when the feed has never run;
    `bar_visible` false means the feed cannot see positions right now and holds them as last seen. `problem` (a
    string) and `problem_at` (ISO 8601) are optional: the feed's own words for why it cannot read, cleared on its
    next good read. A status holding only `problem` and `problem_at` (the feed stalled before its first read) is
    read as not live, never read, with that problem;
  - `trades[]`, one per open..close of a `(trader, side, symbol)`, in the order they opened: `{trader, side: "long" |
    "short", symbol, entry_price, price (the latest average the feed saw), entry_ts, entry_since_ts, entry_known,
    adds: [{ts, price, prev_price}], exit_ts, exit_since_ts, status: "open" | "closed" | "unknown",
    entry_evidence, exit_evidence}`. Times are ISO 8601 with the ET offset. `*_since_ts` set means the change
    happened somewhere between it and the `*_ts` beside it (the feed could not see the trader then).
    `entry_known: false` means the position was already open when the feed started; its real entry time is
    unknown. `status: "unknown"` means the feed saw the same position open again without seeing it close.
    `*_evidence` is a path relative to the day's folder (`frames/<32 hex>.jpg`) or `null`.
  - `events[]` is not read.
- `GET {url}/api/trades?from=YYYY-MM-DD&to=YYYY-MM-DD` (`from` left out: every day the feed has) answers `{from, to,
  dates[], trades[]}`: the same trades as above from every day in the range, oldest first, each with its `date`.
- `GET {url}/files/<date>/<evidence>` answers the evidence image (JPEG).

A field Nova reads that is missing or of another type makes the whole answer `feed.state: "bad_answer"` with the
field named; Nova never fills one in. Fields Nova does not read may come and go.

### `GET /api/followed-traders/day?date=YYYY-MM-DD`

`date` optional (default: the feed's own default, its today); anything but `YYYY-MM-DD` is 400
`FOLLOWED_BAD_DATE`. Answers in about the feed's own time (the feed is asked with a
`FOLLOWED_FEED_TIMEOUT_SEC` timeout); IBKR is never waited on:

`{schema_version: 1, generated_at, feed, date, today, dates[], capture, prices, overall, traders[]}`

- `generated_at`: epoch seconds.
- `feed`: `{state: "ok" | "unreachable" | "bad_answer", error: string | null}`. `unreachable`: the feed did not
  answer (`error` says why: "timed out after 3 s", "could not connect", "HTTP 500"). `bad_answer`: it answered
  something Nova cannot read (`error` names the field). Off `ok`, `date` is the date asked (or `null`), `today`,
  `capture`, `prices` and `overall` are `null`, and `dates` and `traders` are empty: the page shows the state, never
  an empty list.
- `date`, `today`, `dates[]`: the feed's.
- `capture`: the feed's own status, `{live, clock, updated_at, age_sec, bar_visible, title, traders: string[],
  problem, problem_at} | null`. `age_sec` is now minus `updated_at`; past `FOLLOWED_CAPTURE_STALE_SEC` (60) the
  page says the capture stopped, with `problem` as the reason when the feed gave one. `title` is the feed's
  `status.video.title` and `problem` its own words, both shown as they are. `null` when the feed has no status.
- `prices`: how open positions are priced right now, `{state: "live" | "past_day" | "replay_desk" | "ibkr_down",
  why: string | null}`. `past_day`: the day shown is not the feed's today, so nothing is priced now. `replay_desk`:
  the desk is on a Sim replay, whose quotes are the recording's, never today's. `ibkr_down`: IBKR is not ready.
  Exits are priced whatever this says.
- `overall`: everyone's record that day (below).
- `traders[]`: one per trader with a trade that day, in the order of their first trade: `{name, record, open[],
  closed[]}`; `record` is that trader's record that day.
  `open[]` holds `status: "open"` trades, newest entry first; `closed[]` holds `closed` and `unknown`, newest exit
  first (`unknown` by entry).

A trade on this wire:

```
{id, trader, side: "long" | "short", symbol, status: "open" | "closed" | "unknown",
 entry: {first_price, avg_price, ts, since_ts, known},
 adds: [{ts, price, prev_price}],
 now: {...} | null,         // open trades only
 exit: {...} | null,        // closed trades only
 pl: {...} | null,
 held: {min_sec, max_sec},
 result: "win" | "loss" | "scratch" | "unscored" | null,
 evidence: {entry: url | null, exit: url | null}}
```

- `id`: `<trader>|<side>|<symbol>|<entry_ts>`, stable for the trade's life.
- `entry.first_price` is the feed's `entry_price`; `entry.avg_price` its `price`, the latest average (equal to the
  first unless the trader added). P/L is always against `avg_price`, the trader's cost as the feed last saw it.
- `now` (open trades): `{state: "live" | "waiting" | "no_trade" | "no_line" | "off", price, trade_ts, why}`.
  `live`: `price` is the last trade on Nova's IBKR Level 1 line, `trade_ts` when it printed (epoch seconds, `null`
  when IBKR did not say). `waiting`: the line is being opened. `no_trade`: IBKR's only price is the prior close
  (`close_fallback`), so there is none. `no_line`: no line (`why`: IBKR refused it, the line cap, or more than
  `FOLLOWED_MAX_LINES` open positions). `off`: `prices.state` is not `live`. `price` is `null` off `live`.
- `exit` (closed trades): `{state: "pending" | "at" | "range" | "unavailable", price, low, high, from_ts, to_ts,
  trade_ts, source, why}`:
  - `at` (the feed's `exit_since_ts` is null): `price` is the last price-setting IBKR trade at or before `exit_ts`,
    `trade_ts` when it printed. `low` and `high` are `null`.
  - `range` (`exit_since_ts` is set): the exit happened somewhere in `from_ts`..`to_ts`, so there is no single fill:
    `low` and `high` are the lowest and highest price-setting IBKR trades in that window and `price` is `null`.
    `source: "ibkr_trades"` when every trade in it was read; `"ibkr_1min_bars"` when the window held more trades than
    `FOLLOWED_EXIT_MAX_PAGES` pages, in which case `low`/`high` are IBKR's 1-minute bars' low and high over the
    minutes that overlap the window (wider by up to a minute at each end, never narrower). A window with no trade is
    `unavailable`.
  - `pending`: not read yet; `why` says what it waits on (IBKR not connected, IBKR's history budget, a retry) or is
    `null` while the read is due. Exits are read in the background, one at a time, through IBKR's historical budget
    with `FOLLOWED_EXIT_HEADROOM` requests left for charts (`ibkr.historical_trades`, `ibkr.historical_service`),
    newest exit first, so today's come before a record's history. An `at` or `range` once read is kept (below).
  - `unavailable`: `why` says what (no trade before the exit in `FOLLOWED_EXIT_LOOKBACK_SEC`, IBKR refused,
    `FOLLOWED_EXIT_MAX_TRIES` failures). An `unknown`-status trade's exit is `unavailable` with `why` "the feed never
    saw it close".
  - Times are epoch seconds. `source` is `"ibkr_trades" | "ibkr_1min_bars" | null`.
- `pl`: per share, since the feed has no size. `{per_share, pct}` from `now.price` (open, `live`) or `exit.price`
  (`at`); `{low_per_share, high_per_share, low_pct, high_pct}` from an exit `range`; `null` when there is no price.
  Long: price minus `avg_price`; short: `avg_price` minus price. `pct` is that over `avg_price`, in percent points
  (`2.5` = +2.5%).
- `held`: seconds from entry to exit (closed) or to `generated_at` (open). `min_sec` uses the latest the entry can
  have been and the earliest the exit can have been; `max_sec` the other way round, `null` when `entry.known` is
  false (only a floor is known). Equal when both times are exact. Both `null` for an `unknown` trade.
- `result` (operator decisions, 2026-10-13; nothing more complex): `win` when the exit is one price (`at`) and the P/L
  per share is above zero, `loss` below zero, `scratch` at exactly zero; `unscored` when the exit is not one known
  price (a window, not read yet, not read, a close the feed never saw); `null` while open.
- `evidence`: this API's own path for each image (below, relative to the API base), or `null`.

A **record** is `{wins, losses, scratches, unscored, open, win_rate}`: counts of `result`, `open` the trades with
none, and `win_rate` wins over wins plus losses in percent points (one decimal), `null` when there is neither.
Scratches and unscored trades are left out of the win rate.

### `GET /api/followed-traders/record?range=day|week|all&date=YYYY-MM-DD`

Each trader's record over a span ending on `date` (default: today, ET): `day` that day, `week` the
`FOLLOWED_RECORD_WEEK_DAYS` (7) calendar days ending on it, `all` every day the feed has. Read from the feed's
`/api/trades`; another `range` is 400 `FOLLOWED_BAD_RANGE`, a bad `date` 400 `FOLLOWED_BAD_DATE`. Answers:

`{schema_version: 1, generated_at, feed, range, from, to, dates[], pending, overall, traders: [{name, record}]}`

`traders[]` in the order of their first trade in the span; `pending` counts the exits not read yet (each is asked
for in the background like the day's, so a record fills in as they are read; until then they are `unscored`). Open
positions are not priced here; a trade still open at the end of its day counts as `open`. The feed down reads as on
the day route, with `overall: null` and no traders.

### The exits Nova keeps

`followed-exits.json` in the operator cache (`FOLLOWED_EXITS_FILE`; owner `followed_traders/exits.py`):
`{schema_version: 1, exits: [{symbol, exit_ts, exit_since_ts, exit}]}`, `exit` as on the wire, only `at` and
`range` -- an exit's tape is a fixed fact, so a past day's is asked of IBKR once. Written after each such read (a
temp file, then replaced); read on first use. No invalidation by time; a `schema_version` other than 1 is refused
loud (logged, not read, never overwritten), and an unreadable file the same.

### `GET /api/followed-traders/evidence/{date}/frames/{name}.jpg`

The feed's evidence image, passed through (`image/jpeg`, at most `FOLLOWED_EVIDENCE_MAX_BYTES`). `date` must be
`YYYY-MM-DD` and `name` 32 hex characters; anything else is 404 without asking the feed. A feed that does not
answer is 502 `FOLLOWED_FEED_UNREACHABLE`.

### The lines it holds

Open positions on the feed's today are priced from IBKR Level 1 lines owned by `followed`
(`ibkr.ticks.set_owner_symbols`), at most `FOLLOWED_MAX_LINES`. A `followed` line counts against the line cap
like any line no scanner owner holds, so the scanner plans its rows around it, and IBKR's refusal is said as
`no_line`. The lines are asked for in the background on the IB loop (the route never waits) and are all
released when no request came for `FOLLOWED_WANTED_SEC`, so a closed page holds none. A Sim replay desk, a past
day or an IBKR that is not ready asks for none.

### On the desk

The page's design is held for the operator's approval (2026-10-13). Until it lands, the Followed traders tab is a
placeholder that proves the data flows: every state above said in words (not configured, the feed down or
unreadable, the capture stopped with the feed's own reason, how open positions are priced), each trader's record,
and each trade as one line -- entry ("by HH:MM:SS" when the entry was not seen, a window when it was seen late), the
price now or the exit (a low-high range marked estimated for a window), P/L per share and %, the result, held. It
asks every `FOLLOWED_REFRESH_MS` while the page is open. The tab is placed after Cryptos on the rail, and the focus
report names it `followed` (`book-watch-and-luld.md`).
