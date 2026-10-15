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
stages or cancels an order, and nothing here feeds a scanner row, a chart, HOD Momo or a setup lane. Copying a host's
trades is the Live Trader bot's (ADR 055; `bot.md`, "The Live Trader bot"): Paper only, never Live. It reads the feed
through this package -- `feed.fetch_day`, the page's sightings (`routes.seen`) with `view.closed_on_leaving`, and the
ticker check (`routes.ticker_for` over `exits.view`, advanced by `exits.pump`) -- and orders nothing through it.

### The gate

`NOVA_FOLLOW_FEED_URL` in the desk's `.env` (e.g. `http://127.0.0.1:8787`) turns the page on. Unset -- the default,
and every public install -- there is no page, no route and no request to any feed: `app_routers` registers the
router only when the value is set when the app is built. The desk asks `GET /api/followed-traders/config` once per
window (`{schema_version: 1, enabled: true}`); a 404 -- the route does not exist -- means off and is not asked again,
and only a backend that did not answer at all is asked again (every `FOLLOWED_PROBE_RETRY_MS`, a bounded number of
times). The sample desk asks nothing. The value must be an `http://` or `https://` URL; any other value is treated as
unset and logged once. It is never sent to the browser.

### Starting the feed again when it stops (operator ask, 2026-10-14)

"What do we do in the situations where the server shuts down? We need an auto-recovery, a part of the backend with
Nova" -- the feed's server had stopped with a power-off at 18:25 ET and nothing started it until the next morning, so
the page read "The feed is not answering · could not connect".

- `NOVA_FOLLOW_FEED_TASK` in the desk's `.env` names the Windows scheduled task that starts the feed (on the
  operator's desk, `TraderTV Feed`). Unset -- the default, and every public install -- Nova starts nothing. It is
  read only on Windows, and only while `NOVA_FOLLOW_FEED_URL` names this machine (`127.0.0.1`, `localhost`, `::1`);
  otherwise it is logged once and ignored. Nova never runs the feed's code itself: the task runs outside Nova's
  processes, so the feed outlives a restart or an update of Nova, and the task's own script starts whatever part of
  the feed is not running (its server; its capture in the capture's hours) and leaves alone what is.
- The keeper (`followed_traders/keeper.py`, a background loop started with the backend, page open or not) asks the
  feed's `/api/day` every `FOLLOWED_KEEPER_TICK_SEC` (30) and runs the task (`schtasks /Run /TN <name>`, no window)
  when:
  - the feed has not answered (`unreachable`) for `FOLLOWED_KEEPER_DOWN_SEC` (25): two asks in a row; or
  - on a weekday from `FOLLOWED_KEEPER_CAPTURE_FROM_ET` (07:56, after the task's own 07:55 start) to
    `FOLLOWED_KEEPER_CAPTURE_UNTIL_ET` (16:30, when the capture ends its day) ET, the capture's last sign of life --
    the newer of `status.updated_at` and `status.problem_at` -- is older than `FOLLOWED_KEEPER_STALE_SEC` (600), or
    there is no status.

  A `bad_answer` is not a stopped feed and starts nothing. At most one run every `FOLLOWED_KEEPER_COOLDOWN_SEC` (600):
  each start of the capture asks YouTube for the stream, and asks close together get the network a "confirm you're
  not a bot" wall.
- `/day` carries `keeper`: `{task, last: {at, why, ok, error} | null, next_at} | null`. `null` when no task is set.
  `last` is the newest run since the backend started: `at` epoch seconds, `why` Nova's words ("the feed did not
  answer for 30 s", "the capture has read nothing for 12 min"), `ok` whether Task Scheduler accepted the run, `error`
  its words when it did not. `next_at` is the earliest the task can run again (epoch seconds), `null` outside a
  cooldown. A backend without the keeper sends no `keeper`, read as `null`.
- On the page, the pill of a feed that is not answering, or of a capture that stopped, adds "Nova started TraderTV
  Feed 21:15:55 ET" when the last run is less than `FOLLOWED_KEEPER_SHOWN_SEC` (900) old, or "Nova could not start
  TraderTV Feed: <error>"; its hover says why the run was made.

### The feed Nova reads (the feed's own format; operator confirmed settled, 2026-10-13)

Nova reads two routes of the feed and one folder of images, and nothing else:

- `GET {url}/api/day?date=YYYY-MM-DD` answers `{date, today, dates[], status, trades[], events[]}`. Nova reads:
  - `date` (the day answered), `today` (the feed's ET date), `dates[]` (days the feed has, newest first);
  - `status`: `{video: {title}, live, clock ("HH:MM:SS" ET, the last frame read), updated_at (ISO 8601 with
    offset), bar_visible, traders: string[], problem?, problem_at?} | null` -- `null` when the feed has never run;
    `bar_visible` false means the feed cannot see positions right now and holds them as last seen. A `clock`
    that is no time of day (`09:34:97`) reads as `null`. `problem` (a
    string) and `problem_at` (ISO 8601) are optional: the feed's own words for why it cannot read, cleared on its
    next good read. A status holding only `problem` and `problem_at` (the feed stalled before its first read) is
    read as not live, never read, with that problem. `video.id` is optional: the stream's YouTube video id, passed on
    as `capture.video_id` only when it is 11 of `A-Za-z0-9_-` (anything else, or none, is no stream named -- never a
    bad answer);
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

Five more pieces are optional: a feed that does not have them is read as before, and the page says what is missing
(amendment, 2026-10-13, for the approved page; `read_as` 2026-10-14):

- `read_as` on a trade: `{symbol, price, until_ts} | null`, set when the feed confirmed the position under a ticker
  OCR glued to its price and later read it whole (the feed's `correct` event, "A ticker glued to its price" below):
  `symbol` and `price` are what it read until `until_ts`, and the trade's own `symbol` and prices are the ones the bar
  showed. Nova reads only `read_as.symbol` (a string), for the trade's `id`. Absent or null: never corrected.

- `status.positions`: `{<trader>: {"<side>:<symbol>": price}}`, each trader's bar as the feed last confirmed it (the
  same read on consecutive frames). Absent: Nova shows no "on their bar right now" read.
- `status.slots`: `{<trader>: "live/<NAME>.jpg"}`, each trader's slot as last seen, a path under the feed's data
  folder, so `GET {url}/files/live/<NAME>.jpg`. Absent, or a trader missing: the newest evidence image of that
  trader stands in, labelled with its time.
- `faces` on `/api/day`: `{<trader>: "faces/<NAME>.jpg"}`, the trader's photo from the stream that day, under the
  day's folder, so `GET {url}/files/<date>/faces/<NAME>.jpg`. Absent: the page draws the name's first letter.
- `GET {url}/files/<date>/reads.jsonl`, the feed's read log: one JSON object per line, `{clock: "HH:MM:SS" (ET),
  traders: {<name>: {positions: {"<side>:<symbol>": price}, unparsed: string[]}}}`, written each time a read differs
  from the one before, confirmed or not. A name read wrong (`TJOE`) is its own key. A line whose `clock` is null (a
  frame the feed could not read at all) is skipped: it has no time to be placed at -- and so is one whose `clock` is
  no time of day (`09:34:97`, a misread screen), so one bad frame never makes the whole log unreadable. A `clock`
  not shaped `HH:MM:SS` is still a bad answer. A 404 means the feed keeps no read log for that day.

`<NAME>` in those paths is 1 to 16 of `A-Z0-9`; anything else is never asked for.

A field Nova reads that is missing or of another type makes the whole answer `feed.state: "bad_answer"` with the
field named; Nova never fills one in. Fields Nova does not read may come and go.

### `GET /api/followed-traders/day?date=YYYY-MM-DD`

`date` optional (default: the desk's today, below, asked of the feed by name); anything but `YYYY-MM-DD` is 400
`FOLLOWED_BAD_DATE`. `quotes=0` asks for the feed only: no IBKR line is opened or kept for it, `prices.state` is
`not_asked` and every open trade's `now` is `off` (the desk's trade toasts read this way, so a closed page holds no
line). Answers in about the feed's own time (the feed is asked with a
`FOLLOWED_FEED_TIMEOUT_SEC` timeout); IBKR is never waited on:

`{schema_version: 1, generated_at, feed, date, today, resets_at, dates[], capture, prices, overall, traders[], keeper}`

(`keeper`: "Starting the feed again when it stops" above; sent whatever `feed.state` is.)

- `generated_at`: epoch seconds.
- `feed`: `{state: "ok" | "unreachable" | "bad_answer", error: string | null}`. `unreachable`: the feed did not
  answer (`error` says why: "timed out after 3 s", "could not connect", "HTTP 500"). `bad_answer`: it answered
  something Nova cannot read (`error` names the field). Off `ok`, `date` is the date asked (or `null`), `today`,
  `resets_at`, `capture`, `prices` and `overall` are `null`, and `dates` and `traders` are empty: the page shows the
  state, never an empty list.
- `date`, `dates[]`: the feed's.
- `today` is the **desk's** trading day, not the feed's (amendment, operator ask 2026-10-13: "we need to tell when the
  reset is going to be. Is it at 4 in the morning? right before the premarket?"): the ET date whose 04:00 ET has
  passed (`practice.clock`, the premarket open the hot list and the practice day already roll at), so from midnight to
  04:00 ET the page still shows the day that just traded. The feed's own `today` (its ET calendar date, turning at
  midnight) is not passed on. A day the feed has after the desk's today (a capture between midnight and 04:00 ET)
  is listed in `dates[]` and opens as today at 04:00. `resets_at`: epoch seconds when `today` ends, the next 04:00 ET.
- `capture`: the feed's own status, `{live, clock, updated_at, age_sec, bar_visible, title, video_id, traders: string[],
  problem, problem_at, bar} | null`. `age_sec` is now minus `updated_at`; past `FOLLOWED_CAPTURE_STALE_SEC` (60) the
  page says the capture stopped, with `problem` as the reason when the feed gave one. `title` is the feed's
  `status.video.title` and `problem` its own words, both shown as they are. `video_id` is the stream's YouTube id
  (above) or `null`. `null` when the feed has no status.
  `bar` is each trader's bar as the feed last confirmed it, `[{trader, positions: [{side, symbol, price}],
  image: url | null, face: url | null}]` in the feed's order, `image` this API's `live` path when the feed names a
  slot image, `face` this API's `faces` path for the trader's photo when the day answered is today and
  the feed has one (so a trader on the bar with no trade that day still has a face); `null` when the feed reports
  no `status.positions`. It is the feed's now, whatever day is asked.
- `prices`: how open positions are priced right now, `{state: "live" | "past_day" | "replay_desk" | "ibkr_down" |
  "not_asked", why: string | null}`. `past_day`: the day shown is not today, so nothing is priced now.
  `replay_desk`: the desk is on a Sim replay, whose quotes are the recording's, never today's. `ibkr_down`: IBKR is
  not ready. `not_asked`: the request said `quotes=0`. Exits are priced whatever this says.
- `overall`: everyone's record that day (below).
- `traders[]`: one per trader with a trade that day, in the order of their first trade: `{name, face, record, seen,
  open[], closed[]}`; `record` is that trader's record that day; `face` this API's `faces` path for the trader's photo
  that day, or `null` when the feed has none; `seen` when they were last on the bar and whether they left it (below,
  "A trader who left the bar").
  `open[]` holds `status: "open"` trades, newest entry first; `closed[]` holds `closed` and `unknown`, newest exit
  first (`unknown` by entry).

A trade on this wire:

```
{id, trader, side: "long" | "short", symbol, status: "open" | "closed" | "unknown",
 entry: {first_price, avg_price, ts, since_ts, known},
 adds: [{ts, price, prev_price}],
 left_bar: bool,            // closed because the trader left the bar (below)
 ticker: {...} | null,      // a read that may be a ticker glued to its price, checked against IBKR (below)
 now: {...} | null,         // open trades only
 exit: {...} | null,        // closed trades only
 pl: {...} | null,
 held: {min_sec, max_sec},
 result: "win" | "loss" | "scratch" | "unscored" | null,
 evidence: {entry: url | null, exit: url | null}}
```

- `id`: `<trader>|<side>|<symbol as first read>|<entry_ts>`, stable for the trade's life: the symbol is the feed's
  `read_as.symbol` when the feed corrected the trade, else its `symbol`, never the one Nova's ticker check shows.
- `entry.first_price` is the feed's `entry_price`; `entry.avg_price` its `price`, the latest average (equal to the
  first unless the trader added). P/L is always against `avg_price`, the trader's cost as the feed last saw it.
- `left_bar`: true for a trade Nova closed because the trader left the bar holding it (below, "A trader who left
  the bar"); false for every other trade, which is as the feed has it.
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
    `FOLLOWED_EXIT_MAX_TRIES` failures, "IBKR has no such ticker" -- said at once, never asked again before a
    restart). An `unknown`-status trade's exit is `unavailable` with `why` "the feed never saw it close".
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

### A ticker glued to its price (2026-10-14)

With no space between a ticker and its price on the stream's bar, the feed's OCR can take the ticker's last letter for
a digit, and the text alone cannot tell the two apart: on 2026-10-14 the feed read the bar's "SOFI 14.03" as SOF 114.03
37 times, and on 2026-10-13 "JBDI 8.67" as JBD 18.67. When the ticker one letter shorter is a real stock trading near
the true one's price, a position read glued from first frame to last would be priced against it at a gain or loss that
never happened. The feed puts a glued read back when the trader's own reads show the longer ticker (its `correct` event
and `read_as`, above). A position read glued from first frame to last stays as read, and Nova checks it
(`followed_traders/tickers.py`):

- **Which trades.** One whose read could be glued: the feed's `symbol` with the first digit of its `entry_price` put
  back on it as the letter OCR takes it for -- I for 1, S for 5, B for 8, the feed's own pairs (a glued O the feed's
  reader puts back itself) -- is still a ticker of at most 5 letters, and the rest still a price as the bar writes one
  (`tickers.unglued`: SOF 114.03 could be SOFI 14.03; JYD 1.29 and NVDL 35.41 cannot be glued). Any other trade has
  `ticker: null` and reads as before.
- **The check.** IBKR's tape at the entry, read as an exit's is (`exits`, kept the same way): the last price-setting
  trade at or before `entry_ts`, or the low and high of the trades over `entry_since_ts`..`entry_ts`. A price fits it
  within `FOLLOWED_TICKER_FIT_PCT` (1.5%) of that trade, or of that range widened by as much. The ticker as read fits
  its first price: as read. Else the longer ticker's tape at the same time: IBKR has no such ticker, as read (no glued
  reading exists); it fits the unglued price, corrected; anything else, unchecked.
- `ticker`: `{state: "checking" | "as_read" | "corrected" | "unchecked", read_symbol, read_price, other_symbol,
  other_price, why}`. `read_*` is what the feed read (its `symbol` and `entry_price`), `other_*` the glued reading
  (SOFI, 14.03). `why`: what the check waits on while `checking`; IBKR's tape at the entry for both tickers when
  `corrected` or `unchecked`; null when `as_read`.
- **Corrected**: the trade's `symbol` is the longer ticker, and `entry.first_price`, `entry.avg_price` and each add's
  prices are the feed's read back the same way. Its line, exit and P/L are that ticker's.
- **Checking or unchecked**: no line is held and no exit is read for it. `now` is `no_line` and `exit` is `pending`
  (checking) or `unavailable` (unchecked), each with `ticker.why`; `pl` is null and a closed one is `unscored`. A
  ticker that may be wrong never gives a number.
- `/record` checks the same way; an exit that waits on its ticker counts in `pending`.

### A trader who left the bar (operator decisions 2026-10-14)

The feed closes a trade only when it reads the trader's slot without the position, so a trader whose show ends with a
position on the bar is never seen to close it, and the feed keeps the trade `open` all day (operator, 13:11 ET, about
NEAL and SHAWN, whose segment ended at 11:00 with BAC short, TQQQ long and AMZN short on the bar: "why our software
still think they are holding trades?"). The rule, the operator's: **"if they are off air then all trades are
closed!"** Off air means the bar went on without them -- other traders on it, not them -- never a bar that is only off
screen (a guest, a chart, a break): that day JOE came back from a 40-minute guest segment still holding NVDL. Nothing
here names a trader or a time ("they may change the actors ... maybe neal is going to be sick and be replaced with
someone else"): whoever the bar reads is who is on it.

- `seen`: `{last_ts, left_ts} | null`, from the feed's read log (`reads.jsonl`, above). `last_ts` is when the feed last
  read the trader's slot: the time of the line after the last line that read their name, or the newest read time when
  that line is the newest. `left_ts` is the time of the first line after that which read anyone else on the bar -- a
  name tag of 2 to 16 letters and digits, starting with a letter, so a new host with no trade yet counts and the
  reader's empty reads of a guest's caption do not -- counted only once the newest read time is
  `FOLLOWED_LEFT_BAR_SEC` (60) past it, so a name tag misread for a frame is never a departure. It is `null` while
  they are on the bar and while the bar has been off screen since. The newest read time is the log's newest `clock`,
  or the capture's `clock` when the day is today and that is newer. Names read on the bar map onto the day's traders
  (a name with a trade that day, or on `capture.bar`) as the feed's tracker maps them: a stray letter or two beside a
  short name, one wrong letter in a name of five letters or more. `seen` is `null` when the name was never read, the
  feed keeps no read log for the day, or the log cannot be read (logged).
- Every `open` trade of a trader whose `left_ts` is set is **closed** when they left: `status: "closed"`,
  `left_bar: true`, its exit read like any other (IBKR's tape, `exit` above) at `left_ts`, or in the window
  `last_ts`..`left_ts` when the bar was not read between them; no exit image, since no close was seen. Its `held`,
  `pl` and `result` follow from that exit, and it moves to `closed[]` and into the records. Nova holds no IBKR line for
  it. The feed is not changed: a trader read on the bar again is on it again (`left_ts` back to `null`), and their
  trades read as the feed has them.
- `GET /record` applies the same rule to each day of its span with a trade still open, from that day's log.
- The log is asked of the feed with the day (`quotes=0` too, so the toasts say "closed" when a trader leaves), at most
  once every `FOLLOWED_SEEN_CACHE_SEC` (10) for today; a day before the desk's today is finished, and its log, once the
  feed answered (or said it keeps none), is not asked again.

### `GET /api/followed-traders/record?range=day|week|all&date=YYYY-MM-DD`

Each trader's record over a span ending on `date` (default: the desk's today, as on the day route): `day` that day, `week` the
`FOLLOWED_RECORD_WEEK_DAYS` (7) calendar days ending on it, `all` every day the feed has. Read from the feed's
`/api/trades`; another `range` is 400 `FOLLOWED_BAD_RANGE`, a bad `date` 400 `FOLLOWED_BAD_DATE`. Answers:

`{schema_version: 1, generated_at, feed, range, from, to, dates[], pending, overall, traders: [{name, record, scored}]}`

`traders[]` in the order of their first trade in the span; `pending` counts the exits not read yet (each is asked
for in the background like the day's, so a record fills in as they are read; until then they are `unscored`). Open
positions are not priced here; a trade still open at the end of its day counts as `open`. The feed down reads as on
the day route, with `overall: null` and no traders.

`scored` (2026-10-14, "What they made, per share in %" below): the trader's trades the record counts as `win`,
`loss` or `scratch`, oldest exit first, `[{ts, pct}]` -- `ts` the exit's `to_ts` (epoch seconds) and `pct` the trade's
`pl.pct` as on the day route. An unscored trade (no one exit price, its exit still pending, a ticker not settled) and
an open one are not in it; a pending exit joins it once read, as it joins the record. A desk whose backend sends no
`scored` says so beside the figure and shows none.

### The exits Nova keeps

`followed-exits.json` in the operator cache (`FOLLOWED_EXITS_FILE`; owner `followed_traders/exits.py`):
`{schema_version: 1, exits: [{symbol, exit_ts, exit_since_ts, exit}]}`, `exit` as on the wire, only `at` and
`range` -- an exit's tape is a fixed fact, so a past day's is asked of IBKR once. A row is IBKR's tape for `symbol` at
`exit_ts` (or over `exit_since_ts`..`exit_ts`), whichever asked for it: a trade's exit, or an entry checked for a
glued ticker ("A ticker glued to its price"); the tape at one time is the same fact either way. Written after each such read (a
temp file, then replaced); read on first use. No invalidation by time; a `schema_version` other than 1 is refused
loud (logged, not read, never overwritten), and an unreadable file the same.

### `GET /api/followed-traders/evidence/{date}/frames/{name}.jpg`

The feed's evidence image, passed through (`image/jpeg`, at most `FOLLOWED_EVIDENCE_MAX_BYTES`). `date` must be
`YYYY-MM-DD` and `name` 32 hex characters; anything else is 404 without asking the feed. A feed that does not
answer is 502 `FOLLOWED_FEED_UNREACHABLE`.

### `GET /api/followed-traders/live/{name}.jpg` and `/faces/{date}/{name}.jpg`

A trader's slot as the feed last saw it (`live/<NAME>.jpg`, `Cache-Control: no-store`, it changes every few
seconds) and their photo that day (`<date>/faces/<NAME>.jpg`, kept a day), passed through like evidence. `name` must
be 1 to 16 of `A-Z0-9` and `date` `YYYY-MM-DD`; anything else is 404 without asking the feed. The feed's own 404
is passed on as 404 (it has no such image); a feed that does not answer is 502 `FOLLOWED_FEED_UNREACHABLE`.

### `GET /api/followed-traders/reads?date=YYYY-MM-DD&trader=NAME&from_ts=&to_ts=`

What the feed read off one trader's slot between two times (epoch seconds), so a trade can be checked against the
screenshots: read from the feed's `reads.jsonl` for `date` (at most `FOLLOWED_READS_MAX_BYTES`). All four are
required; a bad one is 400 (`FOLLOWED_BAD_DATE`, `FOLLOWED_BAD_READS`). Answers:

`{schema_version: 1, generated_at, feed, date, trader, available, why, reads[], truncated}`

- `feed` as on the day route; off `ok` there is nothing else.
- `available`: false when the feed keeps no read log for that day (its 404), with `why`.
- `reads[]`: the trader's reads, oldest first, `{ts, until_ts, seen, positions: [{side, symbol, price}],
  unparsed: string[]}`. The first is the read in force at `from_ts` (it may start before it); a line identical to
  the one before for this trader is folded into it. `seen: false` is a line where this name was not read at all
  (the bar was off screen, or the name read as another); `until_ts` is when the next read began (`null` for the
  last). A read is only what the vision saw on the frame; the feed logs a change only once the same read holds on
  consecutive frames, so a read that differs from the trade and is not followed by an event was ignored.
- `truncated`: more than `FOLLOWED_READS_MAX` reads fell in the window; the first `FOLLOWED_READS_MAX` are sent.

### The lines it holds

Open positions on today are priced from IBKR Level 1 lines owned by `followed`
(`ibkr.ticks.set_owner_symbols`), at most `FOLLOWED_MAX_LINES`. A `followed` line counts against the line cap
like any line no scanner owner holds, so the scanner plans its rows around it, and IBKR's refusal is said as
`no_line`. The lines are asked for in the background on the IB loop (the route never waits) and are all
released when no request came for `FOLLOWED_WANTED_SEC`, so a closed page holds none. A Sim replay desk, a past
day or an IBKR that is not ready asks for none, and a trade closed when its trader left the bar holds none. A trade
whose ticker is checking or unchecked holds none; a corrected one holds the longer ticker's.

### On the desk

The **TraderTV LIVE** page (named "Following" until 2026-10-14, when the operator asked for it to be renamed "to the
name of the channel" the feed reads; the rail's label, the page's title and the proof's back link all read the
channel's name, `FOLLOWED_CHANNEL`), as the operator approved it on 2026-10-13 (mockup "E2", after "i dont want the
freakin scrolling bar"): it fills the window with no page scrollbar -- a head row, one block per trader stacked top to bottom,
and a right column with the stream above the Activity. It asks `/day` every `FOLLOWED_REFRESH_MS` while it shows;
images are fetched with the desk's API key into blob URLs (an `<img src>` cannot carry the key) and the live slot
images again with each answer.

- **Head**, one row: the capture pill (live with how far behind the stream and the bar's last read; reading behind
  the stream -- the bar's on-screen `clock` more than `FOLLOWED_CAPTURE_BEHIND_SEC` (30) behind `updated_at`, however far
  and across midnight (a clock up to `FOLLOWED_CLOCK_AHEAD_SEC` ahead is skew), a warning with how far, the read's time and that the positions shown are from then, never Live (operator report 2026-10-14:
  the feed read the stream 29 minutes behind and the page said Live and "Their slot now"); positions off screen,
  showing the last read; waiting for the stream; capture stopped with the feed's own reason; the feed not answering
  or not readable), the stream's title ("Last stream:" before it while the stream is not on air), **Watch
  live** (opens the player; disabled with why when the feed names no stream, or "Offline" and why off air), the record
  span (Day from `/day`, Week and All from `/record`) with everyone's record for it and everyone's P/L per share in %
  ("What they made, per share in %" below), the day (previous / a calendar /
  next; next and future days are disabled with why), on today when it resets ("Resets 4:00 AM ET" from `resets_at`,
  what starts again then in its hover), and Alerts. When open positions
  cannot be priced, a chip says why (`prices.why`).
- **One block per trader**: on today, everyone in `capture.bar` in the bar's order, then anyone else who
  traded that day in the order of their first trade; on a past day, those who traded. The card: photo (the trader's
  `face`, or the bar slot's; the name's first letter without one), name, on air or off air (today only), the record
  for the span picked with the scratches and unscored beside it, what they made over it (below), and their slot image
  on the right (the live slot,
  labelled "now" only while the capture reads the stream live and within `FOLLOWED_CAPTURE_BEHIND_SEC` of it and with
  the read's time otherwise, or the newest evidence stand-in labelled with its time, never passed off as now). A trader with a trade that day
  has, under the card, **Holding now** on the left -- an OPEN tile per open position: ticker, side, entry -> now,
  unrealised P/L per share and %, held, time in, proof -- and **Closed today** on the right: the count, won and lost,
  and one row per closed trade, newest exit first, striped by its result (WIN green, LOSS red, scratch and unscored
  grey): result, ticker, side, in -> out, entry (the average, with the first price when the trader added) -> exit
  (IBKR's last trade at the exit; a low-high range marked est. for a window; reading the tape or waiting for IBKR;
  no price, with why), P/L per share and %, held, proof. A trader who left the bar (`seen.left_ts`) reads "Left the
  bar HH:MM:SS" in place of on air or off air, and each trade closed then has "off air" beside its out time, saying
  why it closed; its Proof's exit reads "Closed when they left the bar". A past day reads "Open at the day's end" and
  "Closed". A
  time not seen reads "by HH:MM:SS" (open when capture started) or a window, and its trade unscored. A trader with no
  trade that day shows the card alone. A ticker -- on an OPEN tile, a closed row (in the list of all closed trades
  too), a Proof's title and an Activity line -- opens the stock in the Trader, as a symbol does on the Market and
  Records pages. A trade's Proof stays its own link on the tile and the row. A trade whose `ticker` is checking or
  unchecked reads **ticker check** in place of its P/L, with `ticker.why` on hover, and its ticker, on a tile, a row
  or an Activity line, carries a "?" mark saying the same; a corrected ticker carries a "fixed" mark whose hover says
  what the bar was read as and IBKR's tape for both tickers (`ticker.why`).
- **When it does not fit**, closed rows drop to one line, then each trader's oldest closed trades fold into "+N
  earlier closed trades", which opens them all over the stack; open tiles never shrink or fold. A window too small
  even for that scrolls the stack rather than hide a trade.
- **The stream**, above the Activity: the feed's video (`capture.video_id`) in an embedded YouTube player
  (`www.youtube.com/embed`, muted to start), LIVE, mute / unmute, Pop out (a small window of its own on the desktop, a
  browser tab elsewhere), close, and Open on YouTube (the system browser). It plays **only while the stream is on
  air**: the capture live and read within `FOLLOWED_CAPTURE_STALE_SEC`, its `age_sec` advanced by the time since
  the answer arrived so a backend that stops answering never keeps it on air (amendment, operator 2026-10-13: "if we're on
  the live right now for today, then I don't want it to be allowing me to show some video in the past or history";
  the feed leaves its last status saying live when a stream ends, so it was replaying the day's ended broadcast).
  Off air the player keeps its size and shows OFFLINE in place of the video, with why (waiting for the stream, or
  the feed's last read and its own reason) and "Last stream:" before the title (operator, the same evening: "dont
  shrink the display keep it just have icon that says OFFLINE"); only close stays, since mute, reload, Pop out and
  Open on YouTube would reach the ended broadcast. The video comes back by itself when the feed reads the next live
  stream. Its place shows while the feed names a stream; closed,
  it stays closed in that window (local storage, a per-window convenience) until Watch live. A page loaded from a file (the installed desk) sends YouTube no Referer and YouTube refuses such an
  embed, so the desktop app names Nova's site as the Referer on YouTube's player requests only
  (`frontend/electron/streamPlayer.mjs`). YouTube asks the desk's network to sign in before it plays; on the desktop,
  Sign in to YouTube opens Google's own page in a window of its own on the desk's persistent session, which closes as
  soon as it is on YouTube signed in (the session's YouTube login cookie -- a desk already signed in closes it at once)
  and reloads the players. The player is YouTube's ordinary embed, not `youtube-nocookie.com`: the privacy-enhanced
  one never carries that sign-in, so it asked again however often the operator signed in (operator report,
  2026-10-15). The sign-in survives restarts until Google ends it.
- **Activity**, under the stream, newest first, one line per event built from the day's trades: time, photo, opened
  (or holding, already open when capture started), added to (the average before and after), closed (held). No
  screenshots: clicking an event opens its stock in the Trader (operator, 2026-10-13); a desk with no Trader to open
  opens the trade's Proof, which has them. Events that do not fit fold into "+N earlier", which opens the whole list.
- **Proof on hover** (operator ask 2026-10-13: "I want the proof to be a hover"): hovering or focusing a trade's
  Proof link, on a closed row or an OPEN tile, shows its entry and exit images in a card under the link, right edges
  aligned so the row it proves stays readable (above the link when there is no room under it). Each image carries its
  time; an exit not yet seen reads "Still open" or "The feed never saw it close". The pointer can move into the card;
  Escape closes it. The images are asked for only once the card shows. Clicking the link or the card opens the Proof.
- **Proof** of one trade: the entry and exit images, what was read at each (`/reads`), and every read in between
  that differed from the trade and was ignored. A read of the trade's ticker glued to its price (its last letter as
  the digit OCR reads it, in front of the price: SOFI 14.03 as SOF 114.03) shows the trade, not an ignored read. Nova
  never edits the feed: no button drops or confirms a trade.
- **Calendar**: a month with a dot on each of the feed's `dates`, weekends dimmed, future days disabled; picking a
  day shows its traders, tickers and counts from that day's `/day` before opening it.
- **Toasts**: while the feed is configured and Alerts are on (a per-window setting kept in local storage, on by
  default), the main desk window asks `/day?quotes=0` every `FOLLOWED_TOAST_POLL_MS` and raises "CHERIF opened LONG JZ
  @ 1.55" / "added to" / "closed" for a change since its last answer (none for what it found on its first); a click
  anywhere on a toast opens the TraderTV LIVE page on today (whatever day or proof it was showing), and its Proof opens the page on that trade's proof (operator ask
  2026-10-15). A trade first seen while its ticker is `checking` is held back until the check
  ends or `FOLLOWED_TOAST_TICKER_WAIT_SEC` (60) has passed since its entry, so its "opened" names the ticker as checked;
  a toast raised while the ticker is still checking or unchecked says "ticker check" beside it. The window remembers
  which trades it held back, so a trade already announced, or already there in its first answer, is never news again
  when its ticker is checked once more (the feed corrected it, or a restart forgot an answer).

### What they made, per share in % (operator ask 2026-10-14)

"For each one, how much they make money. We're not going to be able to know how much they made money, but we can see
the PL per share in terms of percentage." The feed has no size, so a trader's dollars cannot be known. Each trader's
card, and Everyone in the head, shows over the span picked (Day, Week, All) **their scored trades' P/L per share in %,
added up** (the operator's pick from a mockup on the real page, over the average a trade and both): what the same
money in every trade would have made. Under it a small line draws that total trade by trade, oldest exit first, from 0
before the first and ending on the number, over a dashed zero; on the card "per share · N trades", in the head the
number and line alone. Up is green and down red, as the P/L is elsewhere on the page.

- **Which trades:** those scored `win`, `loss` or `scratch` -- one known exit price -- the same trades as the W / L
  beside it. An unscored trade (an exit seen only in a window, not read yet, a close the feed never saw, a ticker not
  settled) has no one price, so it is left out and still counted as "N unscored"; nothing is guessed from a range. An
  open position counts once it closes.
- **Where from:** Day from the day's own `closed[]` (`/day`); Week and All from `/record`'s `scored`. Everyone is
  every trader's trades on one list, so its total is the traders' totals added up. Each `pct` has two decimals, so the
  total does too.
- **None:** a span with no scored trade -- nothing closed yet, or only unscored trades -- shows a dash, never 0%, and
  its hover says why. While a Week or All record is read, while the feed is down (`feed.state` off `ok`: its own
  words, never read as a span with no trades), or from a backend that sends no `scored`, the dash's hover says that.
- **Hover:** what the number is, its average a trade, that their dollars are unknown because the feed shows no size,
  and what is left out (the unscored count, open positions).

The tab is placed after Cryptos on the rail, and the focus report names it `followed` (`book-watch-and-luld.md`).
