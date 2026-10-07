# Data schema: The stock read, levels, who trades, managing a trade, why it's moving

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/stock_read/, backend/stock_mode/, backend/move_reason/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## The bot's read on one stock (ADR 036, operator ask 2026-09-24, #598)

"Show me the bot's decisions specifically for that stock ... if something is forming, can we start
highlighting it on the chart? ... all the tiny signals"; then "i want it to tell me my entry/exit
.. we typically want to aim for 2:1 ratio, like right on top of lvl2". Read-only everywhere: nothing
here places, stages or cancels an order.

**Every lane for one symbol.** `GET /api/setups/symbol/{symbol}` (owner `setup_scanner/`,
`symbol_view.py`) answers `{schema_version: 1, generated_at, session_date, symbol, followed:
boolean, followed_note: string | null, seeding: boolean, setups: SetupLane[]}` -- `followed` false
(with the note: the scanner follows the HOD Momo names) leaves `setups` empty. A **SetupLane** is
each setup's template in play: `{setup_type, template: {id, rev, name, params_hash}, level, chosen,
window: {start, end, state}, rules: {stop_cap, min_stop, target_r, target_mode, entry_offset,
risk_slippage}, state, reason, kind, nth, setup_id: string | null, leg, setup, forming, last_price,
distance, grade, pillars, tape: {verdict, reasons, line, metrics, flow} | null, proposal, outcome,
bar_r, mfe, mae, failed_at, series}` -- the board row's fields for that symbol whatever its state
(`watching` included), plus `forming` and `series`. `forming` is `{trigger, entry, stop, risk,
target1, bars, blocked: string | null, waiting: string | null}` or `null`: the levels the setup
would arm with, computed at the last bar close by the same rule that arms it -- a first pullback or
bull flag blocked by its risk, MACD or window, a bull flag with fewer flag candles than it needs
(`waiting` says how many more), a flat top's base blocked, red to green before its red closes or
with its risk out of the band. `series` is the lane's own indicators at its last closed bar:
`{bars_as_of, bars, close, ema, macd_line, macd_signal, macd_hist, hod}` (`null` before a bar) --
the values the gates read, on the scanner's own minutes. Nothing here changes what arms: the board,
`setups.db` rows and the journal keep their shapes.

**The read.** `GET /api/stock-read/{symbol}?entry=&stop=` (owner `backend/stock_read/`; cache reads
only, no network wait) answers `{schema_version: 1, symbol, generated_at, session_date, price,
prev_close, change_pct, followed, followed_note, setups: SetupLane[], no_scanner: [{setup_type,
label, reason}], plan: Plan | null, levels: Levels, groups: Group[], counts: {ok, warn, bad,
unknown, info}}`. A **Group** is `{id: "in_play" | "setups" | "front" | "tape" | "short" | "float" |
"halts", label, question, verdict, value, rows: Row[]}` and a **Row** `{id, label, value, detail:
string | null, state, source, as_of: number | null}`, where `state` is `ok` (for a long momentum
trade), `warn`, `bad`, `unknown` (Nova does not know -- the detail says why, never a pass) or `info`
(a fact that is neither). **Levels** `{hod: {price, ts} | null, pmh: number | null, open: number |
null, prev_close, vwap: number | null, round_above: number | null, round_below: number | null}`:
the high of day, the premarket high (today's bars 04:00-09:30 ET only), the 09:30 open (null before
it), the chart's session VWAP (from 04:00 ET, restarted at 16:00 for after hours), and the nearest
round number of the price's scale above and below (the stock's own round numbers, below). `price` (and the read's change) is `/api/why`'s `facts.price`.
A **Plan** is `{source: "setup" | "manual", setup_type, kind, state: "forming" | "armed" | "near" |
"triggered" | "manual", provisional: boolean, trigger, entry, stop, target, risk, reward, rr,
target_rule, entry_rule, stop_rule, grade, reason, tape: {verdict, reasons} | null, flow: {score,
label} | null, window: {start, end, state} | null, checks: [{id, state, text}], marks: [{price,
label, kind: "hod" | "vwap" | "pmh" | "round" | "wall" | "open"}]}`. The setup plan is the most
advanced lane (near, armed, triggered within 30 minutes, then forming; the bot's chosen setup
first on a tie): entry, stop and target are the lane's own (`setup`, else `forming`, then
`provisional`), the target the scanner's target 1 (entry + `target_r` x risk, or the leg high when
higher), `rr` = (target - entry) / risk. With `entry` given the plan is the operator's (`manual`):
the stop is `stop`, else the lowest low of the last `STOCK_READ_MANUAL_STOP_BARS` closed one-minute
bars under the entry; the target entry + `STOCK_READ_TARGET_R` x risk. `checks` name what stands in
the way; `marks` are the obstacles between entry and target (a seller of the tape gate's wait size
or more on Nova's book). Size is the desk's (the Trader's risk per trade, a desk setting).

**Not a trade (operator report, 2026-09-29).** The plan adds `pillars: {passed, known, total} |
null` (the lane's pillar checks: how many pass and how many are known, of five), `trade: {ok:
boolean, reasons: string[]} | null` and `result: {outcome: "target_first" | "stop_first", at, r,
text} | null`. `trade` is `null` for the operator's own plan; a setup plan is **not a trade**
(`ok: false`, each reason a sentence) when its grade is C (three pillars or fewer), the template's
stock filter keeps the name out, a triggered setup's tape at the trigger was not go, the setup
already played out (the scoring's first touch printed: `result`, with `r` the scoring's R), the
spread on Nova's book is at least the risk (`checks` adds `spread`: warn over half the risk, bad
at the risk or more), or the stock is too thin to trade ("Too thin to trade" above). A triggered plan's `tape` is the tape at the trigger (`trigger_tape`), else
the lane's last read; a `filtered` lane whose pattern triggered follows the 30-minute rule of a
triggered one. **It is one rule** (ADR 042, `setup_scanner/trade_verdict.py`, pure): the plan,
Nova's bot, Auto-entry, Approve and proposals all read it, so a plan that reads
NOT A TRADE is never bought by Nova either -- the bot and Auto-entry skip the
trigger with the reasons, and Approve refuses it (`STOCK_MODE_NOT_A_TRADE`). On the desk the plan's header carries the grade with its count in a chip that
never shrinks ("C 1/5"); a plan that is not a trade reads NOT A TRADE with its reasons, on the plan
and on the 1-minute chart's badge, drops its reward : risk from the header, locks Stage in ticket
and Approve with the reasons (`data-why`), and ENTER NOW is never called on it; a setup that played
out reads its result ("STOP FIRST 08:08 · -1.00R") instead of TRIGGERED.
The setup cards and Watchlist › Setups show every grade with its count ("C 1/5"), forming rows
too, and a filtered row greyed with its phase ("Filtered · near").

**Dilution on file** (the `float` group's last row; operator ask 2026-10-01: show the dilution filings on
file -- an S-3 / F-3 shelf, a 424B, an S-1 / F-1, an 8-K Item 3.02 -- on the stock read). Owners
`stock_read/dilution.py` (pure), `stock_read/dilution_reader.py` and `stock_read/dilution_store.py`;
constants `STOCK_READ_DILUTION_*`. Read-only: nothing places, stages or gates on it, and the Float tile's
verdict stays the float's. The row before it, `dilution` ("Dilution today"), reads today's catalyst items;
this one reads what the registrant has on file. It is `{id: "dilution_on_file", label: "Dilution on file",
value, detail, state: "warn" | "ok" | "unknown", source: "sec_edgar", as_of}`:
- **The facts** are SEC EDGAR's, from the registrant's submissions file
  (`data.sec.gov/submissions/CIK##########.json`: the columns `form`, `filingDate`, `items`). The CIK is
  looked up in SEC's `company_tickers.json`, a share class as SEC writes it (`BRK/B` is `BRK-B`). Four
  kinds, each by its filing date against today's Eastern date, the window's last day included:
  - **shelf**: an S-3, S-3/A, S-3ASR, F-3, F-3/A or F-3ASR within `STOCK_READ_DILUTION_SHELF_DAYS` (3 years);
  - **prospectus**: any 424B* within `STOCK_READ_DILUTION_PROSPECTUS_DAYS` (180);
  - **s1**: an S-1, S-1/A, F-1 or F-1/A within `STOCK_READ_DILUTION_S1_DAYS` (180);
  - **placement**: an 8-K whose Items include 3.02 within `STOCK_READ_DILUTION_PLACEMENT_DAYS` (180).
- **States.**
  - `warn` when any kind is on file. `value` names the newest filing of each kind with its month ("S-3
    shelf 2025-03, 424B5 2026-08, S-1/A 2026-07, 8-K 3.02 2026-09"); `detail` gives the dates and counts.
  - `ok` ("None on file") when the registrant is known, the list was read back to the start of every
    window, and none is on file.
  - `unknown` otherwise, the detail saying why -- never read as clean: the first read is under way
    ("Reading EDGAR…"); SEC's ticker list has no registrant for the symbol; EDGAR could not be read (the
    reason, and when Nova asks again); the reader is off; a kept read found none but is past its day; or
    EDGAR pages the list and a page that reaches into a window was not read.
  - `as_of` is when the submissions file was fetched, `null` without a kept read. A read past its day
    keeps a `warn` (what is on file stays on file) and says a new read is under way.
- **The read never waits on the network.** `gather` asks `dilution_reader.view(symbol, now)`, which
  answers from memory and queues the symbol when no fresh read is kept. One daemon thread reads EDGAR:
  - with the desk's SEC user agent (`SEC_USER_AGENT`, else the catalyst feed's default), at most one
    request every `STOCK_READ_DILUTION_SEC_MIN_GAP_SEC` (1 s; the catalyst feed paces its own);
  - a read is fresh until the next 04:00 ET, and never longer than `STOCK_READ_DILUTION_TTL_SEC` (a day);
  - a failed read is tried again after `STOCK_READ_DILUTION_RETRY_SEC` (30 s, 2 min, then every 10 min),
    the next time the symbol is asked about;
  - EDGAR's `recent` block holds a year or 1,000 filings, whichever is more. Older pages are read only
    when at most `STOCK_READ_DILUTION_MAX_PAGES` (2) reach into a window; else that kind is `unknown`.
- **Kept on disk:** `<cache_dir>/stock_read/dilution.sqlite3` (owner `stock_read/dilution_store.py`;
  `PRAGMA user_version = 1`; an unknown version refuses, and the reader then keeps its reads in memory).
  `reads (symbol, fetched_at, body)`, `body` the read as JSON: `{status: "read" | "no_cik", cik, name,
  filings: [{kind: "shelf" | "prospectus" | "s1" | "placement", form, date}], more: string[], unread_to:
  string | null}` (`no_cik` adds `listed_at`). `filings` holds at most `STOCK_READ_DILUTION_KEEP_PER_KIND`
  a kind, `more` names a kind cut there, and `unread_to` is the last filing date of the newest page not
  read. Rows older than `STOCK_READ_DILUTION_KEEP_DAYS` are deleted. `NOVA_DILUTION_READER=0` turns the
  reader off.
- **On the desk** the row shows with the Float tile's rows and in the Signals sheet like any other; its
  source reads "SEC EDGAR" (`stock_read/constants.ts` `sourceLabel`).

`GET /api/stock-read/{symbol}/decisions?date=YYYY-MM-DD` (default today: the trading day, which starts at
04:00 ET, never the calendar date) answers
`{schema_version: 1, symbol, date, generated_at, summary: {text, legs, armed, near, triggered,
trades, refusals: [{reason, count}]}, events: Event[], sources: {journal, hod_momo, borrow,
catalysts, bot: {ok, error}}}` -- one symbol's day, oldest first: the eyes' journal lines of that
symbol (live source, the template in play's lanes only -- `playing: true`; ADR 042: every template
was folded, so each event counted once per template; a run of the same state and reason on one
lane is one event with `count` and
`last_ts`; tape verdict flips fold the same way), the first HOD Momo alert of each strategy and the
day's count, the borrow changes, the day's catalyst and negative news items (the News panel's, so only
while the calendar date is the day's: none for a past day or from midnight to 04:00), the 09:30 open and the
high of day, and the bot's own `bot_trade` / `setup_proposal` lines for the symbol. An **Event** is
`{ts, lane: "first_pullback" | "bull_flag" | "flat_top_breakout" | "red_to_green" | "gap_and_go" |
"hod_momo" | "market" | "bot", event, title, detail: string | null, count, last_ts: number | null, levels:
object | null}`. A source that cannot be read is `ok: false` with its error; the others still
answer.

`GET /api/stock-read/{symbol}/history` answers `{schema_version: 1, symbol, generated_at, daily:
[{d, o, h, l, c, v}] (the last `STOCK_READ_HISTORY_CHART_DAYS` stored sessions), runs: [{date,
prior_close, high, close, run_pct, close_pct, today}] (sessions whose high was
`STOCK_READ_RUN_MIN_PCT` or more over the prior close, newest first), split: {factor: "a:b" | null,
ts, reverse: boolean | null, days_ago} | null (Yahoo's last split), holdings: Row[]}` -- the Level 2
Nova recorded, setups armed on the symbol on any day, the latest short interest, and what Nova does
not keep per symbol yet, said so.

**Fixed with it.** `/sensors/vwap` is the session VWAP from 04:00 ET (the chart's; since 2026-09-30
restarted at the 16:00 close for after hours as the chart does, `anchor: "16:00 ET"` then --
`sensors.math_indicators.vwap_session_bars`, the stock read's VWAP too) instead of the
newest 240 stored bars, and adds `anchor: "04:00 ET"`; `/sensors/halt` answers `halted: null` when
the state is unknown instead of `false`; `ibkr/shortability.cached(symbol)` returns the last
snapshot with its age (a read, never a wait), and `/ws/ticker/{symbol}` re-reads shortability every
`IBKR_SHORTABILITY_TTL_SEC` while the socket is open, every `IBKR_SHORTABILITY_RETRY_UNKNOWN_SEC`
while it is unknown (the Level 2 "SHORT Unknown" chip asked once per tab). The eyes' journal is read
by the desk only through the decisions route and, since 2026-09-29, the past-setups route (below).

**On the desk** (owner `frontend/src/stock_read/`). The Trader tab polls the read every
`STOCK_READ_POLL_MS` while it shows. The plan box and seven tiles sit between the quote and Level 2
(hover a tile for its rows, click it or "All" for the sheet over the charts: Signals, Decisions,
History). The plan opens whole while the quote card is at least `STOCK_READ_PLAN_OPEN_MIN_PX` tall
and is otherwise one line (the setup, entry / stop / target, the size, reward : risk, Stage), so
Level 2 keeps its room; the operator's own open or fold is kept. The size is whole shares of the
operator's risk per trade over the risk a share. The risk per trade is the desk venue's bot sleeve
`caps.risk_usd` (ADR 042: one number sizes every Nova buy and the operator's Stage, per venue),
read from `GET /api/bot/session` and edited with `PATCH /api/bot/session {caps: {venue, risk_usd}}`;
the old `localStorage` `nova.stockRead.riskUsd` is moved there once and deleted only after the
sleeve confirms it (a refusal keeps it and says so on the card). In a Nova mode the plan also
shows the size Nova would send (the stock-mode view's `size`). "Stage in ticket" fills this tab's ticket with a BUY
limit at the entry for that size through the ticket prefill channel. It never places, and the
plan's stop and target stay the operator's to set: the ticket takes no bracket from it. With no
setup forming, the operator's own plan starts from a typed entry or the ask. Its stop is typed, or
dragged on the 1-minute chart with the entry, and the target stays 2R. The 1-minute chart draws
each lane's shapes (the plan's lane in colour, the rest faded), the plan's zones and lines, the
day's levels, a legend and the plan's badge. It frames a forming setup once per setup, and again
when the badge is pressed. Nothing else moves the view: when the plan's zones appear, a view that
follows the live edge slides over to give them room, and a view the operator moved stays put (the
time scale's `rightOffset`, which is its scroll position, is never set). **A view the operator
zoomed or panned is theirs** (operator report 2026-10-06: "As I was zooming in and watching the
chart, all of a sudden it resized itself randomly"; owner `chart/operatorView.ts`, in memory per
chart): once they move a pane with the wheel, a drag or a pinch, no newly leading setup frames it and
no plan zones slide it, until a first paint (another symbol or timeframe, a Sim seek) or Reset chart
hands it back; the badge and "show on chart" still frame on request. A setup is framed at most once
per symbol, so a lead that goes back and forth between setups never reframes the pane. The 5-minute and 10-second charts mirror the plan's levels as thin lines,
and the daily chart marks every +40% run. `localStorage` `nova.stockRead.layers` = `{schema_version:
1, value: {setups, levels, past, labels: "compact" | "full", hidden: string[], plan: "auto" | "open" |
"folded"}}` keeps the switches (`past`, added 2026-09-29, reads true when a stored value lacks it;
`labels`, added 2026-09-30, reads `compact` when a stored value lacks it or holds anything else). A decision's "show
on chart" frames its moment on the 1-minute chart with the levels it armed at. Nothing is drawn or
read on a replay desk (the read is today's live stock) or on the sample desk.

## Setups that ended stay on the chart, and what price did next (ADR 036 amendment, operator ask 2026-09-29)

"after it fails to form ... it says 'pole' with a gray square. Eventually, it removes itself from the
chart ... we could probably go back and study them": the 1-minute chart drew each lane's current state
only, so a setup vanished at the first bar that did not continue it (NCPL 2026-09-29: a bull flag's
pole failed at 09:20 -- "flag candle 2 made a higher high than the candle before it" -- and left the
chart at 09:21, while the price went on through the pole's high). The eyes' journal kept every line,
but nothing read them back as setups, and nothing scored a setup that died before it armed.

**Episodes** (`eyes/episodes.py`, pure). One day's live journal lines of each setup's template in play
(`playing: true`) fold into episodes, one per setup's life on a symbol. An episode opens at the first
line that leaves `watching` and grows while its leg only extends (the same leg, or a later one with a
high at or over it). It ends when the lane goes back to `watching`, when a failed or triggered setup
is followed by a new attempt, when a lower or earlier leg replaces it, or at a `session` line (Nova
restarted). An episode is `{id, symbol, setup_type, template, rev, started_at, ended_at, end: "failed"
| "faded" | "triggered" | "cut" | null, died_at, died_bar_t, reason, reason_key, ended_by, reached:
"leg" | "pullback" | "armed" | "near" | "triggered", leg: {t, high, low, pct, bars?}, setup: object |
null, setup_id, filtered, triggered_at, trigger_price, score: {outcome, bar_r, exit_reason, mfe, mae}
| null, after: After | null}`:
- `ended_at` / `end` / `ended_by` are `null` while the lane still shows it; `ended_by` is the reason on
  the line that ended it ("no pole", or "a new attempt began: ..."). A restart ends a setup that had
  failed or triggered as that, and any other as `cut` (how it would have ended is unknown).
- `died_at` / `died_bar_t` are set the moment it failed (its first `failed` state), while its lane may
  still show it failed for a while; a faded one's are the moment it ended. `reason` is the rule it
  broke -- the first, never a later one -- else what it was waiting on or blocked by when it ended;
  `reason_key` is `reason` with every number replaced by `#`, so a report counts "the flag gave back
  61.9% ..." with "... 83.3% ...".
- `died_bar_t` is the start of the candle the scanner had just read: a line written within
  `EYES_EPISODE_BAR_CLOSE_SEC` (3 s) of a minute is about the candle that closed (bar-close lines land
  about 0.3 s in), else about the one forming.
- `setup` is the levels it last armed with (`null` when it never armed); `score` is a triggered
  setup's own score, from its `scored` lines (they may come after the episode ended).

**After** (`eyes/aftermath.py`, pure): what price did in the `EYES_EPISODE_AFTER_MIN` (15) minutes
after a setup failed or faded, on the chart's one-minute bars (`bars_store`, less IBKR's no-trade
minutes). `{from_ts, price, level, entry, floor, window_min, complete, bars, high, low, first: "high" |
"low" | "neither" | "pending" | "unknown", crossed_at, trade}`:
- `level` is the high it was building under: its trigger when it armed, else its leg's high (for a
  pullback or a flag, above the trigger it would have had -- the test is conservative; red to green's
  is the open). `entry` is one cent over it, or the setup's own entry when it armed.
- `floor` is the low it would have stopped under: its stop when it armed; else red to green's lowest
  low since the open, and any other's lowest low from the candle after the leg's high through the
  candle it died on (`null` without those bars). `price` is that candle's close.
- `first` says which it crossed first, from the candle after the one it died on (the one it died
  inside, when it died between closes): over the level (`high`) or under the floor (`low`). A candle
  that did both reads `low`: the order inside a minute is unknown, and the study never credits a run
  it cannot prove. `neither` once the window passed, `pending` while it has not, `unknown` with no
  candle after it died. `crossed_at` is that candle's start.
- After `high`, `trade` is the trade the rule refused, scored the way an armed setup is: entry one cent
  over the level (the candle's open when it gapped over; the setup's own entry when it armed), stop the
  floor, target entry + `SETUPS_TARGET_R` x risk (the setup's own target 1 when it armed and over the
  entry) -- `{entry, stop, risk, target, outcome: "target_first" | "stop_first" | "open", outcome_at,
  bar_r, exit_reason, mfe_r, mae_r}`. The crossing candle counts its stop only on a close under it (the
  scoreboard's entry-bar rule), a later candle touching both counts the stop, `mfe_r` / `mae_r` read
  `SETUPS_SCORE_WINDOW_MIN` from the cross, and `bar_r` / `exit_reason` are `ScoreTracker`'s exit rules
  on the bars (a 9 EMA over the day's bars). `null` when the floor is unknown or not under the entry.
  Scores, never fills: no tape, no slippage.

**The route.** `GET /api/stock-read/{symbol}/past-setups?date=YYYY-MM-DD` (owner
`stock_read/past_setups.py`; default today: the trading day, from 04:00 ET; a sync route, off the loop) answers `{schema_version: 1,
symbol, date, generated_at, episodes: Episode[] (oldest first, open ones included), counts: {failed,
faded, triggered, cut, open}, journal: {ok, error, lines}, bars: {ok, error, count}}` -- `after` for
every failed or faded one, the failed ones the lane still shows included; `lines` the day's journal
lines read. The day's file is found by listing the journal folder (`eyes.journal.day_path`, which
`GET /api/eyes/at` and the Sim eyes use too): a date from a request is only compared with file names,
never made into a path. Today's file is read as it grows (`eyes.journal_day.JournalTail`: appended
bytes only, never a line the writer has not finished) and folded once for every symbol, in memory;
another day is folded on each ask. A source that cannot be read is `ok: false` with its error (a day
with no journal file: "no eyes' journal on file for DATE") and the rest still answers (`after: null`
without bars).

**On the desk** (`frontend/src/stock_read/`: `pastSetups.ts` the wire and the words, `pastShapes.ts`
the drawing, `ShapeTip.tsx` the hover):
- The 1-minute pane draws each failed, faded and triggered episode of a lane the operator has not
  hidden, where it happened and fainter than the live lanes, dashed, under them: its leg / pole /
  impulse / open, and the pullback / flag / base from the leg's high to the candle it died (or
  triggered) on, between the floor and the level. Its label says how it ended -- `✕` and the rule it
  broke, `○` what a faded one was waiting on, `✓` a trigger and its score -- and what came next ("↗
  then broke out", "↘ then broke down", "→ then went nowhere"). A rule is named in a few words (the
  scanners' rules are listed in `pastSetups.ts`; any other reason is cut to its first clause, 40
  characters).
- A setup that failed is drawn as past from the moment it failed: while its lane still shows it
  failed, the lane's own box gives way to it. Before the past setups are read (or with the layer off)
  the lane's failed box says `FAILED` and the rule, on the pole's box when a bull flag failed before
  its flag.
- A faded episode that never got past its leg (a leg, a pole or a new high with no pullback, flag or
  base) is not drawn: it is the chart's own candles (59 of the 173 setups that had ended by 10:00 ET
  on 2026-09-29).
- Hovering a setup's box -- live or past -- shows its whole story (`SetupShapesPrimitive.hitTest`
  names the box): the state or end with the full reason, the times, the level, the floor, what price
  did next and the refused trade's outcome.
- The legend's "Past" chip switches the layer (`nova.stockRead.layers` `value.past`), counts what it
  draws, and says why when the backend has no such route. The read is fetched every
  `STOCK_READ_PAST_POLL_MS` while the Trader tab shows with the layer on, and at once when a lane's
  drawn state changes, so a setup that fails or ends is drawn as past within one read. Nothing is drawn
  on a replay desk or the sample desk.
- **Labels make room** (operator report, 2026-09-30: "i do really like seeing the details, but perhaps
  it is extremely too crowded"; LGHL that morning drew 15 past setups, their labels piled on each
  other; then "maybe the compact form should just show (x) and when we hover, it shows the full failed
  setup"). The legend's labels chip beside "Past" (`value.labels`) sets how much a past setup's label
  says: `compact` (the default) its mark alone -- `✕` failed, `○` faded, `✓` triggered -- and no leg
  or pole label; `full` the whole label. Pointing at a label shows the story its box's hover tells
  (`SetupShapesPrimitive.hitTest` names the labels the last draw placed, then the boxes). Either way
  the labels are placed (`stock_read/sceneLabels.ts`, pure): the live lanes' labels, the levels'
  words, the edge tags and the moment's pin stay where they are; the past labels take the room left, a
  trigger's result first, then how the newest ended, then the legs. Each takes the longest form its
  setting allows -- in `full` whole, then a few words ("✕ topping tail ↘", "✓ +1.4R"), then its mark --
  that touches no label already placed, and none when even its mark would; its dashed box and its
  hover stay. A label whose box starts past the pane's left or right edge is kept inside the pane.

**The study.** `py -3 tools/setup_failures.py [--date D | --days N] [--setup S] [--symbol X] [--all]
[--list] [--json]` (read-only; owner `eyes/failure_study.py`) folds the journals and the stored bars
into the same episodes and totals the failed and faded ones by setup, end and reason, faded legs left
out unless `--all`: `{schema_version: 1, generated_at, dates, filters: {setup, symbol, include_legs},
ended, left_out_legs, missing_bars: string[], groups: [{setup_type, end, reason_key, example, count,
first: {high, low, neither, pending, unknown}, trade: {n, target_first, stop_first, open,
avg_bar_r}}], triggered: {count, target_first, stop_first, open, avg_bar_r}, episodes?}` (`episodes`
with `--list`; `triggered` totals the triggered setups' own scores, for comparison). A symbol-day
without stored bars counts its episodes `unknown` and is named in `missing_bars`.

## The day's levels: support and resistance on the charts and in the plan (ADR 036 amendment, operator ask 2026-09-30)

"say our target is 1:2 ratio for trades is too generic, sometimes we have to look at the very obvious
resistance/support levels"; then "the material teach us that there are stops at half dollar or full dollar
which are great psychological triggers", and, on the mockup, "we are overloading the 1min chart". Measured
first (`F:\Nova\eyes\studies\levels-2026-09-30`, in sample): half and whole dollars turn price back before
they break (76% of fresh approaches printed through within 10 minutes, against 84% at a random price) and
are a trigger once through (+1.5% before -1.5% in 77% of breaks, against 70%; a break under 68% against
63%); the high of day and tested tops slow price a little; old daily highs do not; capping the target at
a level costs. So the target stays 2R, and the levels describe. Nothing here places, stages or blocks.

**The level map** (owner `stock_read/level_map.py`, pure). `GET /api/stock-read/{symbol}` adds
`level_map: {schema_version: 1, price, rounds: {minor, major, measured, words} | null, intraday: Zone[],
five_minute: Zone[], daily: Zone[], daily_sessions, daily_error: string | null, study: {source, round_turn,
round_through, round_lost, hod_past, top_past, daily_past}}` -- each
study pair `[at the level, at a random price]` in percent (`STOCK_READ_LEVEL_STUDY`); `rounds` is the
price's scale of round numbers (below), `null` without a price. A **Zone** is
`{id: "<home>:<lo>", lo, hi, price (its edge nearest the price), side: "above" | "below" | "at" |
"unknown", strength, label ("$7.50 · top ×8 · VWAP"), tag ("$7.50"), home: "intraday" | "five_minute" |
"daily",
members: Member[]}`, highest first; a **Member** `{kind, price, label, touches: integer | null, times:
number[] (an intraday level's tests, epoch seconds), dates: string[] (a daily level's sessions), note:
string | null}`. `kind` is one of `hod | lod | pmh | open | vwap | top | bottom | whole | half |
yday_high | yday_low | prior_close` (today's map; `whole` is the scale's major round, `half` its minor one,
and `note` names it: "whole dollar", "$5 round number") and `daily_highs | daily_lows | daily_high | gap |
sma200 | yday_high | yday_low` (the daily map).
- Today's map reads the session's closed one-minute bars from 04:00 ET: the high and low of day; the
  premarket high once the regular session has a bar; the 09:30 open; the session VWAP; tops and bottoms
  -- swing highs (lows) over (under) the two candles before them and even with the two after, within 0.3%
  (at least a cent), tested twice or more; the round numbers within 25% of the price; yesterday's
  high and low (the stored daily bar, extended hours included) and the regular session's prior close.
  The plan reads it (Room, `between`; trial T7 is registered on it).
- The 5-minute map (`five_minute`, operator report 2026-09-30: "why does it say it's a double top when,
  on the graph, we only see one top?") reads the same day from 5-minute candles made of those minutes on
  the clock (`level_map.five_minute_bars`; a candle counts once its five minutes are over): the high and
  low of day, the premarket high, the open, and tops and bottoms by the same swing rule on the 5-minute
  candles -- so two 1-minute tops inside one 5-minute candle are one top here. A round number is
  kept only in a zone with another reason. No VWAP (the chart draws its own line) and nothing from
  yesterday (the Full Day pane's). A backend older than it sends no `five_minute`; the desk then draws no
  5-minute levels and says so.
- The daily map reads the stored daily bars before today: highs and lows within 2% touched twice or more
  in the last 60 sessions; up to three older daily highs above the price, reading right to left, each
  higher than every high after it ("look left and up"); unfilled gaps (the part no later session traded);
  the 200-day average (`history.summary` adds `sma200`: the last 200 stored daily closes before today,
  which close after hours; `null` with fewer); yesterday's high and low. `daily_error` says why the
  daily map is empty when the history could not be read.
- Levels within 0.6% (today) or 1.5% (daily), and always within 2 cents, are one zone, at most twice that
  wide; a zone lists every member, and its label counts one kind once ("top ×8", not "top ×5 · triple
  top"). `side` is `at` within 0.2% (at least a cent) of the price.

**The stock's own round numbers** (owner `stock_read/rounds.py`, pure; operator report 2026-10-01 on ACN at
$223: "I'm pretty sure you could see the problem here. How do we address this without losing important
visibility on important resistance and support levels?"). Every half dollar had been a level at any price:
ACN's plan listed 26 of them between a 217.53 stop and a 236.61 target, one check each, its ruler printed
27 prices on top of each other, and today's map was zones of six half dollars that buried its real levels
("$216.00 · top ×14 · $217.00 · $218.00 · $215.50 · open ..."). Round numbers now scale with the price
(`STOCK_READ_ROUND_LADDER`, a minor round always 2% of the price or more): half and whole dollars up to $25,
$1 and $5 to $50, $2.50 and $10 to $125, $5 and $10 to $250, $10 and $50 to $500, $25 and $100 to $1,250,
$50 and $100 to $2,500, then $100 and $500. One scale per read, from the map's price, for the map, the
plan's notes, marks and checks and the read's next-round row. `rounds` on the wire is `{minor, major,
measured, words}`: `measured` only for half and whole dollars on a $1-$20 stock, where the level study
looked; anywhere else a note's `detail` and the level's card say the rounds are not measured instead of
quoting the study, and Room is not trial T7's (`trial: null`, its detail says why: T7 counts half and whole
dollars). A target or stop is on a round within a tenth of its step (`STOCK_READ_ROUND_NEAR_SHARE`: 5c at a
half dollar, 50c at $5). The plan's checks list the rounds between the entry and the target on one line
("$225.00, $230.00 and $235.00 before the target"; past three, "4 round numbers ($15.50 to $17.00)"), and
the desk's ruler leaves off a label that would touch a stronger one (a seller on the book, then the high of
day and the day's levels, then a round; `planMath.placeRulerLabels`) and keeps its tick. On ACN's bars that
morning: checks 32 to 7, ruler marks 27 to 4, and the map names "217.99 · triple top", "$215.00 · top ×15 ·
bottom ×5 · VWAP · open" and "$220.00 · double top · PMH".

**What the plan says** (owner `stock_read/level_notes.py`, pure). The Plan adds `levels: {room, target,
stop, next, recent, between} | null` (null without a map). Each note is `{state, text, detail}` (`detail`
quotes the study):
- `room` adds `{r, price, label, trial: "T7" | null}`: the first zone of today's map over the entry, in R
  (`trial` null on a stock whose rounds are not half and whole dollars: T7's map counts those);
  `warn` under `STOCK_READ_ROOM_MIN_R` (2R), `ok` at or over it or with none, `unknown` without a stop. The
  daily zones between the entry and the target are named in its detail and never counted. It blocks
  nothing: trial T7 (`knowledge/signal-trials-2.json`) decides whether it ever becomes a NOT A TRADE reason.
- `target` / `stop`: a round number within a tenth of its step (5c at a half dollar) of the target or the stop
  -- a target under the round sells before it (`ok`), one on or over it needs the break (`warn`); a stop
  under a round the entry is over survives its test (`ok`), one on or just over it does not (`warn`).
  `null` when no round is near.
- `next`: the next round number over the entry (else the price) -- `warn` within a tenth of a step ("turns
  back about 1 in 4 before it breaks" where the study looked), else `info`, "resistance until it prints
  through, a trigger after".
- `recent`: a round the price broke (`ok`) or lost (`bad`) within `STOCK_READ_ROUND_CROSS_SEC` (10 min)
  while it still stands on that side; a cross is fresh when the 15 candles before it stayed on the other
  side. `null` otherwise.
- `between`: today's zones strictly between the stop and the target, `{price, lo, hi, tag, label, round,
  hod}`.

**On the desk** (owner `frontend/src/stock_read/`: `levelPicks.ts` which zones a chart draws and each
card, `levelRender.ts` the drawing, `levelTypes.ts` and `levelMapNormalize.ts` the wire, `PlanLevels.tsx` the
rows, `paneKeyRows.ts` / `ChartKey.tsx` each pane's Key). Each chart draws only the levels its own candles
show, and no level twice (operator, 2026-09-30: "Every chart has special needs and special powers ...
There's no reason to have duplicate information"). Every level is a line (a band when the zone is wide)
with a short label at the right edge (the pane's one column, below) -- its price, what it is and what
the candles made of it ("$17.50 · double top", "23.52 · HOD · double top", "16.38 · PMH") -- and a card
under the pointer: what it is and how far from the price, why it is there in plain words (each top or
bottom with the candles it was counted on and when), and what usually happens there, from the study. The
**5-minute** pane draws the 5-minute map: per side the nearest zone and the strongest others within 12% of
the price (three in all), the zone the price is on, the high and low of day; every other zone is a short
tick on the price axis. The **Full Day** pane draws the daily map the same way within 40%, with
yesterday's levels. The **1-minute** pane draws from today's 1-minute map the high of day, the zone the
price is on, the nearest zone over and under it that its candles made (a top or a bottom tested twice or
more), the nearest round dollar each side and the plan's `between` levels, with no ticks; the premarket
high and the open are the 5-minute pane's. (Until 2026-09-30 these were price lines without an axis
label, and lightweight-charts 5.1 shows a price line's title only beside its axis label: the 1-minute
pane's level lines never showed their names.) The **10-second** pane draws the plan's lines only. Every
pane's corner carries a **Key** chip: pointed at, focused or pressed, it lists what each colour on that
pane means -- the time-of-day background on the intraday panes, the levels, and on the 1-minute the
setup boxes and the plan's lines. The plan
card lists Room (with "in trial T7" while amber), Target, Stop, "$ next" and "$ now", each one line with
its detail on hover, and the ruler marks the `between` levels. The toolbar's Levels switch
(`nova.stockRead.layers` `value.levels`) turns every chart's levels on or off. Nothing is drawn on a replay
desk or the sample desk.

**One column at a pane's right edge** (operator report 2026-09-30: "everything is getting on top of each
other in the charts!"). The right edge had three owners -- the levels' labels stacked among themselves,
lightweight-charts drew the EMAs', VWAP's and the plan lines' titles on its own, and the tags for prices out
of view sat at a fixed spot the 1-minute pane's corner chips covered -- so they landed on each other. The
stock read now claims each pane's edge (`chart/edgeWords.ts`, in memory per chart):
- the overlays (`components/TickerChartOverlays.tsx`) blank their series titles and publish their names;
  the plan's price lines keep their prices on the axis and give their names to the column; the position tag
  reserves its spot;
- one column (`stock_read/edgeColumn.ts`) places every word: on its line where there is room, else the
  crowd centred on its lines in their order, with a hairline back to each line. A crowd that cannot sit
  within three rows of its lines drops its least important word first -- the plan's lines, VWAP, the high
  of day, the levels, the 9 / 20 / 200 EMA, then the tags -- and a level that loses its label keeps an axis
  tick that opens its card;
- the tags for prices out of view (an EMA's with its value: "↑ 200 EMA 1048.99") stack under the corner
  chips and at the bottom, at most three at each end; the 1-minute legend ends where the price axis begins.

A pane without the stock read (a replay desk, the sample desk) keeps the series' own titles. The EMAs no
longer stretch the price scale on any chart: the candles decide what prices a pane shows (LGHL's 200 EMA,
a year of reverse splits behind it, squeezed the Full Day candles into a flat line). The Full Day pane's
+40% runs are drawn by the scene: every run keeps its arrow, and where labels crowd today's and then the
biggest runs keep theirs.

**The close countdown keeps clear of the pane's words** (operator report, 2026-10-05: on a 5-minute pane the
countdown chip sat on the setup's "5m ... +83.3%" label). The chip over the forming candle
(`chart/BarCountdownPrimitive.ts`, on every minute pane) knew only the candle, and a live lane's label starts at
its box's left edge a few candles back, so it ran under the chip; a sell's price over the forming candle did too.
Each primitive that writes words on a pane now publishes the rectangles it drew (`chart/paneWords.ts`, in memory
per chart, nothing persisted): the stock read's labels, pins, fixed labels and edge column, and the fill arrows
with their prices. When the chip's usual spot (centred over the wick) touches one, it takes the first clear
spot: beside the candle on its right at the wick's middle, then over it, under the candle, beside it on the
left, and then a row at a time higher and lower. It never sits on the forming candle, and with no clear spot it
is not drawn for that paint: a covered label is information lost, a missing digit for a moment is not. Draw
order between primitives is not relied on: a change in the words after the chip's own paint is announced once,
after the paint (a microtask), and costs one more paint; a chip that painted after the words costs none. The
setups' labels still place as they did (a live lane's whole where it is); only the chip yields. No wire or
stored shape changed.

## Who trades the stock (ADR 037, operator ask 2026-09-24, #604, #606)

"When may Nova buy for you? I want a clear option next to level 2 ... if I selected the exit is on
me, then I'm going to be the one who exits, not the bot." Owner `backend/stock_mode/`: the routes,
the in-memory store and the runner. Nova places for a stock only on Paper, or on Sim at the live
edge. On Live every Nova side is locked, and the lock says why: a Nova buy is `auto_live`, NO-GO,
and Approve on Live waits on #604.

**The view.** `GET /api/stock-mode/{symbol}` answers `{schema_version: 1, symbol, generated_at,
venue: "live" | "paper" | "sim" | null, mode: "signal" | "approve" | "auto_entry" | "bot", buy:
"you" | "nova", sell: "you" | "nova", risk_usd: number | null, set_at: number | null, locks:
{buy: string | null, sell: string | null}, notes: [{id, tone: "info" | "warn", text}], approval:
Approval | null, trade: Trade | null, entries_today: {count, cap}, nova_entries_today: integer (one
release), size: {qty, by_risk, capped_by, text} | null, last_event: {ts, tone: "info" | "ok" | "warn" |
"bad", text} | null, bot: {on_list, playing, reason, setup_at_strategy, active} | null}` (ADR 042:
`risk_usd` is the venue sleeve's, read-only here; `size` is what Nova would send for the stock's plan;
`setup_at_strategy` is the plan's setup; the bot's skips on the stock become its `last_event`).
- `locks.buy` / `locks.sell` say why Nova cannot take that side now (`null` means it can): Live, a
  replay desk, or a venue Nova cannot read.
- `notes` name **every** thing that will keep Nova from acting although the switch is set (ADR
  042, not only the first): the venue, the padlock, the kill switch, the day lock, the bot trip, the
  bot not active, the plan's setup not at Strategy, its window, extended hours, no depth line, NOT A
  TRADE, a stock the scanner does not follow, the day's Nova entries used, and what could not be
  read (`bot_unreadable`, `trades_unreadable`, `scanner_unreadable`).
- An **Approval** is `{setup_id, setup_type, entry, stop, target, qty, approved_at, state:
  "waiting" | "sent" | "withdrawn", reason}`.
- A **Trade** is `{kind: "auto_entry" | "approve" | "bot", state: "entering" | "holding" | "closed"
  | "missed" | "handed", venue, venue_day, setup_id, setup_type, qty, entry, stop, target,
  entry_order_id, target_order_id, stop_order_id, fill_price, filled_at, exit_price, exit_reason:
  "target" | "stop" | "time" | "flush" | "outside" | "handed" | null, exits: "nova" | "you", sent_at, closed_at:
  number | null, note, exiting: boolean}` -- `closed_at` when it closed, missed or was handed;
  `exiting` true while the bot is selling it. The bot's own trade is mapped from `bot-session.json`
  (`entry_sent_ts` is its `sent_at`, `closed_ts` its `closed_at`; `open` and `exiting` read `holding`).

`GET /api/stock-mode` answers `{schema_version, generated_at, venue, stocks: [view]}` for every
stock that is not at Signal only.

**Changing it.** Writes need the desk's API key even on loopback (they place orders), like the bot
routes.
- `PUT /api/stock-mode/{symbol}` takes `{buy, sell}` and answers the view (a `risk_usd` it is
  sent is ignored: Nova sizes by the venue sleeve, ADR 042).
  - **One owner** (ADR 042): Nova / Nova puts the stock on this venue's bot list
    (`symbol_allowlist`), and the list is written only through these rules -- `POST
    /api/bot/allowlist {symbol, op}` and `PATCH /api/bot/session {symbol_allowlist}` (which answers
    `refused: [{symbol, reason, error}]` and applies the rest) go through them too, with the Live lock,
    "you hold it" and the 50-stock cap (`BOT_ALLOWLIST_FULL`) refused before anything changes. A
    stock has one mode: Bot clears an Auto-entry or Approve switch, and the reverse; `op: remove`
    sets Signal only.
  - Moving Sell from Nova to You takes over the exit (below). Moving Buy from Nova to You cancels a
    Nova entry that is still working.
- `POST /api/stock-mode/{symbol}/approve` takes `{setup_id, entry, stop, target, qty, now?}` and
  answers the view. The stock must be in Approve, and the plan must be the lane's own: the setup id,
  with its levels within a cent. `now: true` on a triggered setup sends the bracket at once.
- `DELETE /api/stock-mode/{symbol}/approve` withdraws a waiting approval, or cancels a sent entry
  that has not filled; its exits go with it.
- `POST /api/stock-mode/{symbol}/take-over` cancels the exits Nova holds on the stock:
  - Approve's two bracket legs;
  - or the bot's trade. The bot cancels its target and stop legs, stops watching, and ends the
    trade `handed`, releasing its shares from the sleeve.
  - Buy always stays on You after a take-over (ADR 042: it could turn into Auto-entry and buy the
    next trigger at the old risk), and a cancel that is refused keeps the trade and says the order
    still rests.

A refusal is `{detail: {reason, error, field}}`:
- 400: `STOCK_MODE_INVALID`, `STOCK_MODE_RISK`.
- 409 `STOCK_MODE_LIVE`: a Nova side on Live, or on a venue Nova cannot read.
- 409 `STOCK_MODE_REPLAY`: Sim off the live edge.
- 409 `STOCK_MODE_HELD`: Sell to Nova while the stock is held.
- 409 `STOCK_MODE_NOT_APPROVE`.
- 409 `STOCK_MODE_FILTERED` / `STOCK_MODE_NOT_A_TRADE`: Approve on a setup the template's filter keeps
  out, or a plan that is not a trade.
- 409 `STOCK_MODE_PLAN_CHANGED`: the setup is no longer armed at those levels.
- 409 `STOCK_MODE_NOTHING_HELD`: Nova holds nothing of this stock to take over.
- 409 `STOCK_MODE_BOT_EXITING`: the bot is already selling.
- 409 `STOCK_MODE_SEND`: the execution door refused the send; `error` is the door's own reason.

**What Nova does.** The runner (`stock_mode/runner.py`) hears the setup scanner's triggers
(`SetupEngine.add_trigger_listener`, live feed only).
- **Auto-entry is the bot's rules with the exit handed to you** (ADR 042, `admit.for_auto_entry`):
  the first go trigger of a setup at effective Strategy (never one at Off or Eyes), the first of the
  day, inside that setup's bot window, with extended hours as the sleeve says, within the shared
  daily cap, never NOT A TRADE, at most `BOT_FP_TRIGGER_MAX_AGE_SEC` old, and only while the bot is
  Active, sends one BUY limit at that setup's entry.
  - Size: the sleeve's (one size for every Nova buy).
  - Source: `bot`. A stock on the bot list never auto-enters (the bot trades it).
  - The gates as the bot's, plus no Nova order already working on the stock.
  - Unfilled after the sleeve's `working_ttl_sec`, it is cancelled and the trade ends `missed`.
  - After the fill the trade is `holding` with `exits: "you"`: Nova places no exit.
- **Approve.** The approved setup's go trigger (fresh) sends one bracket: `operation: "bracket"`,
  `source: "manual"`, an entry limit, a target limit and a stop.
  - It is cancelled unfilled after the sleeve's `working_ttl_sec`. Its size is the operator's
    approved quantity (no sleeve caps); it is counted, never capped, by the daily count.
  - A re-arm at other levels, or a failed or disarmed setup, withdraws the approval with the reason.
- **Every act and every skip** is a `stock_mode` line on the bot audit stream. `outcome` is one of
  `set`, `approved`, `withdrawn`, `sent`, `skipped`, `filled`, `missed`, `closed`, `handed` and
  `refused`, and `inputs` carry the symbol and the setup id.

The switches and approvals are in memory only (`stock_mode/store.py`) and stamped with the venue: a
restart or a venue change returns every stock to Signal only. **Nova's trades are persisted**
(ADR 042): `stock-mode-trades.json` in the operator cache, `{schema_version: 1, ...}` (an unknown
version refuses loudly and is never overwritten; kept `STOCK_MODE_TRADES_KEEP_DAYS`), so a restart
resumes managing them (TTL cancels, fill notices). The bot's list belongs to the venue's dial and
lasts; with Activate cleared on every start, nothing buys after a restart until the operator presses
Activate. **Leaving a venue cancels Nova's working entries there first** (`stock_mode/leave.py`):
before the desk moves, every Nova entry still working on the venue it leaves -- the bot's,
Auto-entry's, an approved bracket's -- is cancelled there (a `missed`); no new entry starts while it
runs (`BOT_VENUE_CHANGING`); `POST /api/desk/venue` answers `left: [{venue, symbol, order_id, by,
text, ok}]` and the desk toasts each. Open positions keep their resting exits.
Sell: You means Nova never sells the trade; the loss breakers and KILL still flatten every position.

**On the desk** (owner `frontend/src/stock_read/`, with the stock read):
- The "Who trades" row sits directly above Level 2. The same switch is a chip under the plan's badge
  on the 1-minute chart.
- The badge carries the moment track (Forming, Trigger, Holding, the exit), computed from the lane's
  state, the position and the orders (`stock_read/momentModel.ts`, pure). The chip opens the four
  modes; a mode Nova cannot take now is locked with the reason.
- ENTER NOW, SELL NOW and what Nova just did appear in the badge's corner, with one ping per event,
  and as a tag on the chart at the event's price and candle. ENTER NOW stays up 30 s after the
  trigger while the price is within half a risk of the entry; SELL NOW is kept once the target or the
  stop printed while the operator held the stock (this tab's memory of the position, never
  persisted); what Nova did stays up 30 s. `localStorage` `nova.stockRead.sound` = `{schema_version:
  1, value: boolean}` mutes the ping.
- The plan's stop and target are dashed while they are only a plan, and solid while an order stands
  behind them.
- Level 2 draws ENTRY, STOP and TARGET as separator rows where they sit in the book (the
  `MontageSide` `markers`).
- The plan card's buttons follow the mode:
  - Signal only: Stage in ticket; Stage sell (at the target, or at the bid once an exit is due)
    while shares are held.
  - Approve: Approve (an armed plan), Approve: buy N now (after its trigger), Approved · cancel,
    Cancel stop and target (take over the exit).
  - Auto-entry: Auto-entry on · turn off; Stage sell once Nova bought.
  - Bot: Bot on SYMBOL · stop it; Take over the exit while the bot holds it.
- The badge promises a Nova buy ("THE BOT TRADES THIS", "NOVA BUYS AT ...") only when nothing
  blocks it (ADR 042); otherwise it says why, every reason on hover. The plan card shows the size
  Nova would send in a Nova mode. The Bots page lists every stock not at Signal only (`GET
  /api/stock-mode`), so an Auto-entry stock is never invisible once its tab closes.
  - A trade Nova closed on the plan's setup reads "Closed · +$X" (gross, from the fill to the exit).
- The Trader reads the view every `STOCK_MODE_POLL_MS` while the tab shows. Nothing is read on a
  replay desk or on the sample desk.

## Managing a trade you hold (ADR 036 / 037 amendment, operator ask 2026-10-01)

"If I enter a trade, can it tell me on the chart when I should sell ... if we pass that level, okay, this is
the next level ... I can instruct Nova to sell it for me"; on mockup v4b: keep the plan box as it is and add
the THEN / NEXT / NOW / BROKE ladder, then "lets move these targets ... to the 10 seconds chart". Owners
`stock_read/held.py` (pure), `stock_mode/exit_trade.py`; on the desk `frontend/src/stock_read/`.

**The read while you hold.** `GET /api/stock-read/{symbol}` takes `held_qty`, `held_avg` (both > 0: the read
adds `held`), `held_stop` (your stop; absent, the read proposes one), `held_risk` (the risk a share your R is
measured in; absent, the average less the stop while the stop is under it, else R is unknown) and
`held_since` (epoch seconds you have held since). `held` is `null` without them.
`held: {schema_version: 1, qty, avg, price, open_usd, r: number | null, risk: number | null,
stop: {price, source: "yours" | "proposed" | "nova", rule, printed: boolean} | null,
raise: {to, round, at, text} | null, target: {price, rule, traded_at: number | null} | null,
ladder: [{role: "then" | "next" | "now" | "through" | "broke" | "support" | "stop" | "cost", price, text,
r: number | null, usd: number | null}], broke: [{round, at, close}], through: [{round, at, high}],
levels: {room, target, stop, next, recent}, checks: Check[]}`:
- **The stop**: Nova's when Nova holds the exit (`nova`, "Nova takes the exit" below), else `held_stop`
  (`yours`), else proposed: the lowest low of the last `STOCK_READ_MANUAL_STOP_BARS` closed 1-minute
  candles when it is under the price, else 1c under the nearest zone of today's map under the price
  (`proposed`; `null` when neither exists). `printed`: a price at or under it since `held_since`.
- **Broke and through** (the stock's own round scale, `rounds.of`): a round is **broke** when a closed
  1-minute candle since `held_since` closed 1c or more over it after the
  `STOCK_READ_ROUND_FRESH_BARS` closes before it stayed under it (`at`: when that candle closed), and
  **through** when the price stands over it, a candle's high since `held_since` crossed it and no close has.
  A one-second sweep is at most through: only a close moves a stop.
- **Raise**: the highest broke round whose `round - near` (the stock's own `rounds.near`: 5c under a half
  dollar) is over the stop and under the price -- `to` is that price ("raise the stop to 5.95, 5c under
  $6.00"); `null` otherwise. Up only.
- **The target**: the average plus `STOCK_READ_TARGET_R` x the risk (your 2:1); `traded_at` when a candle
  since `held_since` reached it.
- **The ladder**, highest price first: the first two zones of today's map over the price (`next`, `then`),
  the price (`now`), the through and broke rounds under it, the nearest zone under the price over the stop
  (`support`, when no broke round is there), the stop and the average (`cost`). `r` is in the held risk.
- **The rows** (`levels`, the plan's note shape) are measured from the price, never the entry: Room to the
  first zone over the price in R (`info`; trial T7 reads entries, not positions), the target behind or
  ahead, the stop's round (`level_notes.stop_note`), the next round over the price and a round just
  broken or lost. `checks` are the plan's checks that hold for a position: the spread against what the stop
  gives back, the 1-minute MACD, the 9 EMA, VWAP, the tape's flow, bids pulled and a halt.

`GET /api/stock-read/{symbol}/flush` (cheap: the sensor rings only) answers `{schema_version: 1, symbol,
at, score: number | null, label: "burst" | "flush" | "neutral" | "quiet" | "blind", window_sec}` -- trial
T1's reading (`tape_flow` with a 30 s window, every other number the default); the Trader reads it every
`STOCK_READ_FLUSH_POLL_MS` while you hold. It is a call in trial, never an order.

**On the desk.** While the tab's account holds shares (the venue's position):
- The plan box stays the box it is (#675): its header names the trade (THIS TRADE, shares @ average, the
  badge, open P&L and R); its five numbers become Average, Stop, Next, At the stop and Holding; its ruler runs
  from the average (●) past the stop to the level after next (dim green: locked in by a stop over the
  average; red: what the stop gives back from here; green to the next level; dotted to the one after); the
  ladder sits under the ruler; the rows and checks are `held`'s. The stop is yours to set: "Use stop",
  "Raise stop to X" and typing it set it for the tab (never an order); Stage sell fills the ticket.
- The 10-second chart draws the trade's levels -- THEN, NEXT, SUPPORT, STOP, the average (COST) and the
  broke rounds -- each a line with its name in the edge column. The 1-minute chart keeps its setups, levels,
  the badge and one call: SELL NOW · STOP (the stop printed), SELL NOW · FLUSH "in trial T1" (a flush 10 s or
  more after you held; description only on Live), BROKE $X · NEXT Y with the raise offered, TARGET HIT.
- Level 2 marks NEXT on the ask side and STOP on the bid side.

**Nova takes the exit** (Paper, and Sim at the live edge). `POST /api/stock-mode/{symbol}/take-exit` takes
`{stop, trail: boolean}`: Nova places a SELL stop for every share the venue holds at `stop` through the
execution door (source `manual`, origin `nova_exit`) and keeps a trade `{kind: "exit", state: "holding",
exits: "nova", qty, entry (the average), fill_price, stop, target: null, trail, stop_order_id,
raised: [{at, from, to, round}], ...}` (`stock-mode-trades.json`; the trade shape adds `trail` and
`raised`, and `kind` adds `exit`). No target rests beside it: the door lets one order sell the same shares,
and a one-cancels-other exit pair is built only as a bracket's legs, with an entry -- a target for a held
position waits on an exit-only pair in the door (#681). The runner (`exit_trade.manage`, every
`STOCK_MODE_POLL_SEC`): the stop that fills closes the trade; a position gone closes it `outside`; a stop
cancelled outside Nova hands the exit back (`handed`); with `trail`, at each closed minute a broke round
since the trade began raises the stop by a replace of the stop order (the rule above, up only), an audit
line `raised` and the stock's last event. Refusals: `STOCK_MODE_LIVE` / `STOCK_MODE_REPLAY` (Live, a venue
Nova cannot read, Sim off the edge), `STOCK_MODE_NOTHING_HELD` (no shares, or the position cannot be
read), `STOCK_MODE_INVALID` (a stop at or over the last price), `STOCK_MODE_HELD` (Nova already holds an
exit or an entry on it), `STOCK_MODE_SEND` (the door refused). "Take it back" is `POST .../take-over`
(the stop cancelled, the trade `handed`); Sell: You on the switch does the same. While it holds, the view's `sell` is `nova`. The Sell switch to Nova on a
held stock opens the sheet instead of `PUT` (which still answers `STOCK_MODE_HELD`). On Live the sheet is
locked and says why: Nova never moves a Live order by itself, and a Live stop does not trigger before
09:30 (#604).

## Why it's moving (ADR 028, operator ask 2026-09-23)

`GET /api/why/{symbol}` (owner `backend/move_reason/`, read-only, no network wait; rules
`move_reason/rules.py`, pure, thresholds in `constants_move_reason.py`) answers the Trader tab's
"Why it's moving" section: `{schema_version: 1, symbol, generated_at, session_date, rules_version,
likely: {kind: "not_moving" | "news_pending" | "news" | "short_squeeze" | "routine_news" |
"split_squeeze" | "low_float_momentum" | "thin_trading" | "unexplained", label, detail,
confidence: "likely" | "possible"}, checks: [{id: "news" | "halts" | "float" | "float_rotation" |
"reverse_split" | "short_interest" | "borrow" | "volume", label, state: "yes" | "no" | "unknown",
value: string | null, detail: string | null, source, as_of: number | null}], facts: {price,
change_pct, volume, rel_volume, float_shares, float_contradicted, float_rotation, short_interest,
short_interest_ts, short_above_float, short_pct_float, days_to_cover, split: {factor, ts, reverse,
days_ago} | null,
halts: {news, luld, volatility, other, source} | null, borrow: {listed, fee_rate, rebate_rate,
available, available_capped, as_of, since, open, prior, max_fee_today, min_available_today} | null,
catalyst: verdict | null, shares_issued: {published_ts, source, form, items, title, url} | null}}`.
`shares_issued` is the filed share issuance of "Float credibility and short-interest dates" (#700); while
one is on file the float and float-rotation checks read `unknown` ("631K? shares", "Float traded 82x?")
with the filing named in their `detail`, because Yahoo's float and share count predate it -- so the
likely cause is never low-float momentum on a float the filings say is out of date. The
news check's `detail` names the verdict's `prior_session` item while today's window holds no catalyst,
and the likely cause then says "no company news since the prior close" and names it. `price` / `change_pct` / `volume` are the scanner row's, repriced by the
symbol's L1 line when it holds a trade (`move_reason.facts.with_live_trade`; never IBKR's prior close
before the first trade): a board stops repricing a row when its session ends (XRPN 2026-09-30 read
16.40, its 16:00 price, while it traded 17.11 after hours, so the stock read judged every level against
the close). `float_contradicted` / `short_interest_ts` are the scanner row's (#532,
"Float credibility and short-interest dates"); a contradicted float's check reads "54K? shares"
with the reason as its `detail` and keeps its state, and the short-interest check's `as_of` is the
FINRA settlement date. `short_above_float` is judged on the float and short interest shown here; when
it is `true` the short-interest check's `detail` adds its reason and its state is unchanged (a
warning, never a gate). `days_to_cover` is Yahoo's short ratio and its value says "(Yahoo ratio)".
`fee_rate` / `rebate_rate` are IBKR's annual percent; `open` / `prior` are `{listed, fee_rate,
available, as_of}` at the day's first poll at or after 04:00 ET and the last poll before it (null
when not recorded); `since` is the first poll the store holds. A symbol IBKR's file does not list is
`listed: false` (nothing to lend). Every unknown is `null` and its check `unknown`, never guessed;
`confidence` is `possible` when a deciding input is unknown. Descriptive only: nothing places or
gates on it.

The borrow feed (`move_reason/borrow_feed.py`, always on; `NOVA_BORROW_FEED=0` off) polls IBKR's
public short-stock file (`ftp://ftp2.interactivebrokers.com/usa.txt`, USD rows) every
`MOVE_BORROW_POLL_SEC` into `<cache_dir>/move_reason/borrow.sqlite3` (owner
`move_reason/borrow_store.py`; `PRAGMA user_version = 1`, unknown versions refuse): `polls (ts,
file_ts, rows)` and `changes (symbol, ts, listed, fee_rate, rebate_rate, available, capped)` -- a
row only when a symbol's listing, fee or availability changed, pruned after
`MOVE_BORROW_RETENTION_DAYS`. `/api/diagnostics` adds the `borrow_feed` row (group `recorder`).

