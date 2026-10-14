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

Four more pieces are optional: a feed that does not have them is read as before, and the page says what is missing
(amendment, 2026-10-13, for the approved page):

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
  frame the feed could not read at all) is skipped: it has no time to be placed at. A 404 means the feed keeps no
  read log for that day.

`<NAME>` in those paths is 1 to 16 of `A-Z0-9`; anything else is never asked for.

A field Nova reads that is missing or of another type makes the whole answer `feed.state: "bad_answer"` with the
field named; Nova never fills one in. Fields Nova does not read may come and go.

### `GET /api/followed-traders/day?date=YYYY-MM-DD`

`date` optional (default: the feed's own default, its today); anything but `YYYY-MM-DD` is 400
`FOLLOWED_BAD_DATE`. `quotes=0` asks for the feed only: no IBKR line is opened or kept for it, `prices.state` is
`not_asked` and every open trade's `now` is `off` (the desk's trade toasts read this way, so a closed page holds no
line). Answers in about the feed's own time (the feed is asked with a
`FOLLOWED_FEED_TIMEOUT_SEC` timeout); IBKR is never waited on:

`{schema_version: 1, generated_at, feed, date, today, dates[], capture, prices, overall, traders[]}`

- `generated_at`: epoch seconds.
- `feed`: `{state: "ok" | "unreachable" | "bad_answer", error: string | null}`. `unreachable`: the feed did not
  answer (`error` says why: "timed out after 3 s", "could not connect", "HTTP 500"). `bad_answer`: it answered
  something Nova cannot read (`error` names the field). Off `ok`, `date` is the date asked (or `null`), `today`,
  `capture`, `prices` and `overall` are `null`, and `dates` and `traders` are empty: the page shows the state, never
  an empty list.
- `date`, `today`, `dates[]`: the feed's.
- `capture`: the feed's own status, `{live, clock, updated_at, age_sec, bar_visible, title, video_id, traders: string[],
  problem, problem_at, bar} | null`. `age_sec` is now minus `updated_at`; past `FOLLOWED_CAPTURE_STALE_SEC` (60) the
  page says the capture stopped, with `problem` as the reason when the feed gave one. `title` is the feed's
  `status.video.title` and `problem` its own words, both shown as they are. `video_id` is the stream's YouTube id
  (above) or `null`. `null` when the feed has no status.
  `bar` is each trader's bar as the feed last confirmed it, `[{trader, positions: [{side, symbol, price}],
  image: url | null, face: url | null}]` in the feed's order, `image` this API's `live` path when the feed names a
  slot image, `face` this API's `faces` path for the trader's photo when the day answered is the feed's today and
  the feed has one (so a trader on the bar with no trade that day still has a face); `null` when the feed reports
  no `status.positions`. It is the feed's now, whatever day is asked.
- `prices`: how open positions are priced right now, `{state: "live" | "past_day" | "replay_desk" | "ibkr_down" |
  "not_asked", why: string | null}`. `past_day`: the day shown is not the feed's today, so nothing is priced now.
  `replay_desk`: the desk is on a Sim replay, whose quotes are the recording's, never today's. `ibkr_down`: IBKR is
  not ready. `not_asked`: the request said `quotes=0`. Exits are priced whatever this says.
- `overall`: everyone's record that day (below).
- `traders[]`: one per trader with a trade that day, in the order of their first trade: `{name, face, record, open[],
  closed[]}`; `record` is that trader's record that day; `face` this API's `faces` path for the trader's photo that
  day, or `null` when the feed has none.
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

Open positions on the feed's today are priced from IBKR Level 1 lines owned by `followed`
(`ibkr.ticks.set_owner_symbols`), at most `FOLLOWED_MAX_LINES`. A `followed` line counts against the line cap
like any line no scanner owner holds, so the scanner plans its rows around it, and IBKR's refusal is said as
`no_line`. The lines are asked for in the background on the IB loop (the route never waits) and are all
released when no request came for `FOLLOWED_WANTED_SEC`, so a closed page holds none. A Sim replay desk, a past
day or an IBKR that is not ready asks for none.

### On the desk

The **Following** page, as the operator approved it on 2026-10-13 (mockup "E2", after "i dont want the freakin
scrolling bar"): it fills the window with no page scrollbar -- a head row, one block per trader stacked top to bottom,
and a right column with the stream above the Activity. It asks `/day` every `FOLLOWED_REFRESH_MS` while it shows;
images are fetched with the desk's API key into blob URLs (an `<img src>` cannot carry the key) and the live slot
images again with each answer.

- **Head**, one row: the capture pill (live with how far behind the stream and the bar's last read; positions off
  screen, showing the last read; waiting for the stream; capture stopped with the feed's own reason; the feed not
  answering or not readable), the stream's title, **Watch live** (opens the player; disabled with why when the feed
  names no stream), the record span (Day from `/day`, Week and All from `/record`) with everyone's record for it, the
  day (previous / a calendar / next; next and future days are disabled with why), and Alerts. When open positions
  cannot be priced, a chip says why (`prices.why`).
- **One block per trader**: on the feed's today, everyone in `capture.bar` in the bar's order, then anyone else who
  traded that day in the order of their first trade; on a past day, those who traded. The card: photo (the trader's
  `face`, or the bar slot's; the name's first letter without one), name, on air or off air (today only), the record
  for the span picked with the scratches and unscored beside it, and their slot image on the right (the live slot,
  or the newest evidence stand-in labelled with its time, never passed off as now). A trader with a trade that day
  has, under the card, **Holding now** on the left -- an OPEN tile per open position: ticker, side, entry -> now,
  unrealised P/L per share and %, held, time in, proof -- and **Closed today** on the right: the count, won and lost,
  and one row per closed trade, newest exit first, striped by its result (WIN green, LOSS red, scratch and unscored
  grey): result, ticker, side, in -> out, entry (the average, with the first price when the trader added) -> exit
  (IBKR's last trade at the exit; a low-high range marked est. for a window; reading the tape or waiting for IBKR;
  no price, with why), P/L per share and %, held, proof. A past day reads "Open at the day's end" and "Closed". A
  time not seen reads "by HH:MM:SS" (open when capture started) or a window, and its trade unscored. A trader with no
  trade that day shows the card alone. A ticker -- on an OPEN tile, a closed row (in the list of all closed trades
  too) and a Proof's title -- opens the stock in the Trader, as a symbol does on the Market and Records pages; an
  Activity line stays one button that opens the trade's Proof.
- **When it does not fit**, closed rows drop to one line, then each trader's oldest closed trades fold into "+N
  earlier closed trades", which opens them all over the stack; open tiles never shrink or fold. A window too small
  even for that scrolls the stack rather than hide a trade.
- **The stream**, above the Activity: the feed's video (`capture.video_id`) in an embedded YouTube player
  (`youtube-nocookie.com`, muted to start), LIVE while the capture is live, mute / unmute, Pop out (a small window of
  its own on the desktop, a browser tab elsewhere), close, and Open on YouTube (the system browser). It shows while
  the feed names a stream; closed, it stays closed in that window (local storage, a per-window convenience) until
  Watch live. A page loaded from a file (the installed desk) sends YouTube no Referer and YouTube refuses such an
  embed, so the desktop app names Nova's site as the Referer on YouTube's player requests only
  (`frontend/electron/streamPlayer.mjs`).
- **Activity**, under the stream, newest first, one line per event built from the day's trades: time, photo, opened
  (or holding, already open when capture started), added to (the average before and after), closed (held). No
  screenshots: clicking an event opens its trade's Proof, which has them. Events that do not fit fold into "+N
  earlier", which opens the whole list.
- **Proof** of one trade: the entry and exit images, what was read at each (`/reads`), and every read in between
  that differed from the trade and was ignored. Nova never edits the feed: no button drops or confirms a trade.
- **Calendar**: a month with a dot on each of the feed's `dates`, weekends dimmed, future days disabled; picking a
  day shows its traders, tickers and counts from that day's `/day` before opening it.
- **Toasts**: while the feed is configured and Alerts are on (a per-window setting kept in local storage, on by
  default), the main desk window asks `/day?quotes=0` every `FOLLOWED_TOAST_POLL_MS` and raises "CHERIF opened LONG JZ
  @ 1.55" / "added to" / "closed" for a change since its last answer (none for what it found on its first); a toast
  opens the page on that trade's proof.

The tab is placed after Cryptos on the rail, and the focus report names it `followed` (`book-watch-and-luld.md`).
