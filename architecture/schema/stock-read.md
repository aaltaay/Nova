# Data schema: The stock read, levels, who trades, managing a trade, why it's moving

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/stock_read/, backend/stock_mode/, backend/move_reason/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## The bot's read on one stock (ADR 036, operator ask 2026-09-24, #598)

On a Sim replay desk the read is the replay's at the playhead (`replay: true`; ADR 052, bot.md "The bot
trades a Sim replay"): the Sim eyes' setups, the replay's candles, the days before for the daily map; the
setups that ended are the Sim eyes' up to the playhead (#815), and the decisions timeline answers empty there.

"Show me the bot's decisions specifically for that stock ... if something is forming, can we start
highlighting it on the chart? ... all the tiny signals"; then "i want it to tell me my entry/exit
.. we typically want to aim for 2:1 ratio, like right on top of lvl2". Read-only everywhere: nothing
here places, stages or cancels an order.

**Every lane for one symbol.** `GET /api/setups/symbol/{symbol}` (owner `setup_scanner/`,
`symbol_view.py`) answers `{schema_version: 1, generated_at, session_date, symbol, followed:
boolean, followed_note: string | null, seeding: boolean, setups: SetupLane[]}` -- `followed` false
(with the note: the scanner follows the HOD Momo names) leaves `setups` empty. A **SetupLane** is
each setup's template in play: `{setup_type, template: {id, rev, name, params_hash}, level, chosen,
window: {start, end, state}, rules: {stop_cap, min_stop, targets: {first, second, fixed, split, stop} |
null, entry_offset, risk_slippage}, state, reason, kind, nth, setup_id: string | null, leg, setup, forming, last_price,
distance, grade, pillars, tape: {verdict, reasons, line, metrics, flow} | null, proposal, outcome,
bar_r, mfe, mae, failed_at, series}` -- the board row's fields for that symbol whatever its state
(`watching` included), plus `forming` and `series`. `forming` is `{trigger, entry, stop, risk,
target1, target2, target1_fraction, targets, bars, blocked: string | null, waiting: string | null}` or `null`
(the targets as setups.md, "Targets replace 2R"): the levels the setup
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
"triggered" | "manual", provisional: boolean, trigger, entry, stop, target, target2, target1_fraction,
targets, risk, reward, rr, reward2, rr2, target_rule, entry_rule, stop_rule, grade, reason, tape: {verdict, reasons} | null, flow: {score,
label} | null, window: {start, end, state} | null, checks: [{id, state, text}], marks: [{price,
label, kind: "hod" | "vwap" | "pmh" | "round" | "wall" | "open", before: 1 | 2}]}`. The setup plan is the most
advanced lane (near, armed, triggered within 30 minutes, then forming; the bot's chosen setup
first on a tie): entry, stop and targets are the lane's own (`setup`, else `forming`, then
`provisional`). Since #845 (operator decisions 2026-10-09 and 2026-10-12) a plan has two targets from the
menu (`setup_scanner/targets.py`; setups.md, "Targets replace 2R"): `target` is target 1 (the first part's
sell), `target2` the rest's or `null` (everything at target 1), `target1_fraction` the share sold at target 1
(1.0 without a target 2), and `targets` their reasons (`{first: {kind, price, why}, second, hod, pullback_high,
stop, rule}`; `why` like "+20c", "1c under $5.50", "1c under HOD 6.12"). `rr` / `rr2` are the targets in R and
`reward` / `reward2` in dollars -- R is the unit, never a target. `target_rule` names the strategy's choice
("target 1: 20c, or 1c before a half / whole dollar when that is closer; target 2: ...; 50% at target 1"), and
`stop_rule` the template's round-number stop when it picked one ("3c under $4.00"). With `entry` given the plan
is the operator's (`manual`): the stop is `stop`, else the lowest low of the last
`STOCK_READ_MANUAL_STOP_BARS` closed one-minute bars under the entry; the targets are the menu's defaults from
the entry, today's map and the high of day of its candles -- they never depend on the stop. `checks` name what
stands in the way; `marks` are the obstacles between the entry and the furthest target (a seller of the tape
gate's wait size or more on Nova's book), each `before` the target it comes before; a check says it ("$5.50
before target 1"). Size is the desk's (the Trader's risk per trade, a desk setting).

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
and on the 1-minute chart's badge, drops its targets in R ("+0.5R · +5.0R to targets 1 · 2"; a reward : risk
before #845) from the header, locks Stage in ticket
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
and is otherwise one line (the setup, entry / stop / target 1 / target 2, the size, the targets in R, Stage), so
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
dragged on the 1-minute chart with the entry; while it drags the targets keep their distance from the entry,
and on release the read answers the menu's targets for the new entry. The 1-minute chart draws
each lane's shapes (the plan's lane in colour, the rest faded), the plan's zones and lines, the
day's levels, a legend and the plan's badge. **The legend keeps a chip only for a lane doing something**
(operator 2026-10-12, of fifteen chips over the candles: "this is too much"): forming, near, armed,
triggered or failed, or the plan's, and not hidden or at Off (`LegendSetupsMenu.onLegendRow`). Its last
chip, Setups, counts the lanes without one and opens a menu: every lane's switch and where it stands,
longs and shorts side by side, a strategy at Off locked with why, then the past setups' switch and their
labels' Compact / Full. Hiding a lane moves it into the menu; a lane that starts forming gets its chip
back. Nothing persisted changes: the switches are `nova.stockRead.layers` as before. Its autoscale keeps the stop to the furthest target in view
(#845: target 2 when the plan has one, `planMath.planFrame`), so target 2 is a line on the chart; its edge
tag names it only where the operator's own price scale leaves it off. **A setup plan that is only forming** (operator
ask 2026-10-12, on a Gap and Go plan 30% over the price that squeezed MNDR's candles into a third of the pane: "square
it up like the original but show it more faded ... say gap and go strategy, but doesn't have to be entire horizontal
line from end to end ... more minimalist") draws neither zones nor plan lines on the 1-minute chart, only its strategy
box (`strategyBox.ts`, drawn by `strategyBoxRender.ts`): one faint box from its stop to target 1, from the room right
of the newest candle to the pane's edge, the setup's name and "strategy" with its window inside, the entry a dashed
line across it, its prices faint words in the edge column ("T1 2.99", "entry 2.91", "stop 2.79", no line of their
own), and target 2 a small arrow over it (under it for a short). While the setup's window is still ahead the box
stands on that window -- from Gap and Go's 09:30 -- when the window's start leaves room for its name left of the
column's words, and otherwise waits at the right edge saying "from 09:30 →"; with the window open, or none, it starts
after the newest candle. That chart's autoscale keeps the box in view (the stop to target
1), never target 2. **Once the setup is near or armed** (operator ask 2026-10-12, on MNDR's Gap and Go armed
at 09:30, its zones from the 09:30 candle and four lines across the pane: "its making the chart extremely big ... can
we do that for the rest of them?") the same box stands in full colour with a solid outline, from the room right of the
newest candle to the pane's edge, on every setup: its name and where it stands ("FLAT TOP BREAKOUT near", "FIRST
PULLBACK armed"; a word with no room beside the name leads the second line), and since when ("since 09:34", with
"until 10:00" while its window is open, from the lead lane's `setup.armed_at`). The entry is dashed
across the box only. Its levels keep their axis tags, price lines drawn without the line (`PriceLineSpec.line: false`,
lightweight-charts' `lineVisible`), and the edge column's words name them ("T1", "entry" or "short", "stop"). Target 2
in view is a dotted dash across the box ("T2 3.49"), and off the pane an arrow; either way the frame is the stop to
target 1. A short's name is cut before its "▼ SHORT". **Once it triggered** (operator ask 2026-10-12, option A of two
mockups, on MNDR's Gap and Go box still beside the price at 09:55, 24 minutes after its 09:31 trigger and 22 after the
eyes scored target 1 first) a plan with nothing behind it was taken or missed, and it leaves the 1-minute chart: no
box, no axis tags, no frame (`strategyBox.triggeredPlan`). A mark over its trigger candle stands in its place
(`triggerMark`, from the lead lane's `setup.triggered_at`; none without it): a triangle in the entry's blue, pointing
up (down on a short), and "✓ GAP AND GO 09:31", which makes room as a past setup's label does -- "✓" alone while the
labels are compact -- and tells the lane's story on hover. Where the lane already marks that candle (a flat top that
entered on its break), its own mark says it. It leaves the 10-second pane too (operator
report 2026-10-12, OFAL's first pullback in the Sim at 07:15: triggered at 07:05, its stop printed first at 07:10, and
its four unnamed lines still crossed both charts -- "whatr these lines supposed to be?"). A
level an order or a position stands behind, and the operator's own plan, draw the zones, lines and frame above. It frames a forming setup once per setup, and again
when the badge is pressed. Nothing else moves the view: when the plan's zones appear, a view that
follows the live edge slides over to give them room, and a view the operator moved stays put (the
time scale's `rightOffset`, which is its scroll position, is never set). **A view the operator
zoomed or panned is theirs** (operator report 2026-10-06: "As I was zooming in and watching the
chart, all of a sudden it resized itself randomly"; owner `chart/operatorView.ts`, in memory per
chart): once they move a pane with the wheel, a drag or a pinch, no newly leading setup frames it and
no plan zones slide it, until a first paint (another symbol or timeframe, a Sim seek) or Reset chart
hands it back; the badge and "show on chart" still frame on request. A setup is framed at most once
per symbol, so a lead that goes back and forth between setups never reframes the pane. **The 10-second chart draws
the plan as the 1-minute chart does** (operator report 2026-10-13, AIXI's Gap and Go still forming: its entry 3.74,
stop 3.59, T1 3.94 and T2 3.99 crossed the 5-minute and 10-second charts as four dotted lines with no name and no axis
tag -- "whats the points of these dotted lines??", "we cant keep them like this", then "for which strategy is this
specifically?"; of three mockups -- the plan on the 1-minute chart only, the strategy's name on each line, the 1-minute
chart's box -- the box): a setup's plan with nothing behind it is its strategy box, named, after the 10-second chart's
own newest candle, its window counted in 10-second candles (`strategyBox.strategyOnBars`), faint while forming, in full
colour once near or armed with its prices as axis tags, gone once it triggers; a view that follows the live edge
slides over to give it the same room as on the 1-minute chart. A level an order or a position stands behind is a thin
line named as the 1-minute chart names it ("ENTRY · working", "STOP · plan", "TARGET 1 · plan"), with its axis tag. The
**5-minute chart never draws the 1-minute plan**: it draws its own 5-minute setups' trigger, stop and target, each
named, and two sets of the same blue, red and green dashes read as one; its Key lists no plan. The daily chart marks
every +40% run. `localStorage` `nova.stockRead.layers` = `{schema_version:
1, value: {setups, levels, past, labels: "compact" | "full", hidden: string[], plan: "auto" | "open" |
"folded"}}` keeps the switches (`past`, added 2026-09-29, reads true when a stored value lacks it;
`labels`, added 2026-09-30, reads `compact` when a stored value lacks it or holds anything else). A decision's "show
on chart" frames its moment on the 1-minute chart with the levels it armed at. On a replay desk the
charts draw the replay's read at the playhead (ADR 052); nothing is drawn or read on the sample desk.

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
  floor, the setup's own targets when it armed and they are over the entry, else the menu's defaults from
  the entry, the high of day before the cross and the leg's high (#845) -- `{entry, stop, risk, target,
  target2, target1_fraction, outcome: "target_first" | "stop_first" | "open", outcome_at, bar_r, exit_reason,
  mfe_r, mae_r}`. The crossing candle counts its stop only on a close under it (the
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
without bars). The body adds `replay: boolean`.

**On a Sim replay desk** (ADR 052 amendment, #815) the route answers the Sim eyes' setups that ended on the
loaded replay at the playhead (`eyes/sim_past.py`; `replay: true`): the episodes are folded from the lines the
replay's lanes wrote up to the playhead -- a fold per rebuild, never the day's journal file -- and `after` reads
the replay's one-minute bars completed by the playhead, so a window still open reads `pending`. `date` is the
replayed day and `generated_at` the playhead; `journal.lines` counts the lanes' lines folded; `note` is null.
While the Sim eyes read the replay or catch up to a rewind it answers no episodes with `pending: true` and
`note` (also `journal.error`) saying which; for a symbol that is not the loaded replay's, or with nothing
loaded, it answers none with `note` saying so. `tf=5m` folds the 5-minute strategies' lanes the Sim eyes run
(the built-in chart-only 5-minute lanes do not run on a replay).

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
  did next and the refused trade's outcome. A candle inside the box wins the pointer (operator report
  2026-10-12: "if I'm specifically highlighting a candle, I do care about the candle information more
  than anything else"): the box's area is reported as an area (`chart/hoverTarget.ts`), so resting on a
  candle in it opens the candle's card as anywhere on the chart, and the box's story steps aside while
  that card is open. Off the candles the card closes and the story shows again; a label, a ring or a
  trend line keeps its own story over a candle.
- The "Past setups" switch in the legend's Setups menu switches the layer (`nova.stockRead.layers` `value.past`), counts what it
  draws, and says why when the backend has no such route. The read is fetched every
  `STOCK_READ_PAST_POLL_MS` while the Trader tab shows with the layer on, and at once when a lane's
  drawn state changes, so a setup that fails or ends is drawn as past within one read. On a replay desk
  (#815) it is read again the moment the playhead moves to another 5 s, and a read is drawn only when it
  is the replay's and was made at or before the playhead the tab shows (`pastNowOf`), so a rewind draws
  nothing from later while the next read comes. Nothing is drawn on the sample desk.
- **Labels make room** (operator report, 2026-09-30: "i do really like seeing the details, but perhaps
  it is extremely too crowded"; LGHL that morning drew 15 past setups, their labels piled on each
  other; then "maybe the compact form should just show (x) and when we hover, it shows the full failed
  setup"). The Compact / Full switch beside "Past setups" in the Setups menu (`value.labels`) sets how much a past setup's label
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
a level costs. So the target stayed 2R, and the levels described -- until the operator removed the 2:1 on
2026-10-09 (#845): the targets are now the menu's, at the levels ("Targets replace 2R", setups.md). Nothing here
places, stages or blocks.

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
target2, stop, next, recent, between} | null` (null without a map; `target2` is target 2's round note, #845). Each note is `{state, text, detail}` (`detail`
quotes the study):
- `room` adds `{r, t7, price, label, trial: "T7" | null}`: the first zone of today's map over the entry, read
  against the plan's targets (#845): `warn` when it stands before target 1 (target 1 needs it to break: "15c to
  HOD 8.77, before target 1"), `ok` when target 1 sells before it or with none (its detail says whether target 2
  is past it), `unknown` without a stop; the text is in cents, never an R threshold. `r` is the room in R of the
  risk. `t7` is trial T7's own reading under its registered rule (`knowledge/signal-trials-2.json`, frozen):
  `{id: "T7", r, under: boolean}` -- `under` when the room is under `STOCK_READ_T7_ROOM_R` (2) R of the risk, the
  measurement T7 was registered on; nothing on the plan reads it, and the trial decides whether it ever becomes
  a NOT A TRADE reason. `trial` and `t7` are null on a stock whose rounds are not half and whole dollars (T7's
  map counts those). The daily zones between the entry and the furthest target are named in its detail and
  never counted. It blocks nothing.
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
- `between`: today's zones strictly between the stop and the furthest target (target 2 when there is one),
  `{price, lo, hi, tag, label, round, hod}`.

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
pane's level lines never showed their names.) The **10-second** pane draws the plan only (its box, or an order's named lines). A
level's colour and line come from its strongest reason, a round number the weakest (`levelPicks.zoneColor`;
operator report 2026-10-12, the gold dashed lines were "too strong, too much"): coral over the price and teal
under it, so a top the price climbs over turns support on the next read whether or not it sits on a round; a
zone the price is on (`at`) is coral when highs made it more than lows (tops by their touches, the high of day,
the premarket high), else teal, so touching a top is not breaking it; VWAP alone purple, yesterday's levels
blue dots, old daily levels violet dashes; a round number alone a faint solid gold line
(`LEVEL_ROUND_LINE_ALPHA`, 0.4) whose label keeps the full colour. A strong zone's line is 2 px, any other 1.
Every pane's corner carries a **Key** chip: pointed at, focused or pressed, it lists what each colour on that
pane means -- the time-of-day background on the intraday panes, the levels, on the 1-minute the
setup boxes, and the plan's lines on every pane that draws them (the 5-minute Key lacked them until 2026-10-12, and its
"5m trigger" row read like them). The plan
card lists Room (T7's reading only in its hover since #845), Target 1, Target 2, Stop, "$ next" and "$ now", each one line with
its detail on hover, and the ruler marks the `between` levels. The toolbar's Levels switch
(`nova.stockRead.layers` `value.levels`) turns every chart's levels on or off. On a replay desk they are the replay's
at the playhead (ADR 052); nothing is drawn on the sample desk.

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

## Trend lines on the 1- and 5-minute charts (ADR 036 amendment, operator ask 2026-10-12)

"When we see an obvious ascending line and descending line, can we have them part of the strategy? Like it show in the chart obvious line for the long and short positions?"; "Maybe it's gonna end up like the breakout setup with some tolerance because I doubt there will just be perfect ascending or descending trend lines"; "It's like what visually make sense, and I think we r gonna need that on the 1min and 5min charts". The rule and why are in ADR 036's 2026-10-12 amendment; nothing here blocks, sizes or places.

**On the wire** (owner `stock_read/trend_lines.py`, pure). The level map adds `lines: {one_minute: TrendLine[],
five_minute: TrendLine[]}` (`level_map.schema_version` stays 1: a backend older than it sends no `lines`, and the
desk draws none). `one_minute` reads the session's closed one-minute bars, `five_minute` the 5-minute candles made
of them (`level_map.five_minute_bars`). A **TrendLine** is `{id: "<home>:<kind>:<first touch t>", home:
"one_minute" | "five_minute", kind: "support" | "resistance", dir: "up" | "down", state: "holding" | "broken",
touches: [{t, p, x}] (each touch's candle, where the line runs there, the candle's low or high), t1, p1 (first
touch), t2, p2 (last touch), now_t, now_p (the last closed candle), slope (price a candle), band (at the last
candle), side: "above" | "below" | "at" | null (against the price, within the band "at"), broke: {t, p, close} |
null, retest_t: number | null, label ("ascending support · 4 touches"), tag ("↗ support"), note ("4 touches: 09:14,
09:17, 09:46, 09:54; a candle closed under it at 09:59")}`. Times are epoch seconds, prices where the line runs
at that candle.
- Support rises through swing lows, resistance falls through swing highs (a swing: past the two candles before it,
  at least even with the two after). A line joins two of the latest 60 swing points of its kind. Its band is
  `max(0.5% x the line, $0.01)` (`STOCK_READ_LINE_TOUCH_PCT` / `_MIN`). A swing low touches a support line when its
  low reaches the band's top and its body stays over the band's floor; resistance is the mirror.
- A line has three touches or more (`STOCK_READ_LINE_MIN_TOUCHES`), ten candles or more from the first to the last
  (`_MIN_SPAN_BARS`), no candle closing through the band between them, and rises (falls) three bands or more
  (`_MIN_RISE`). `broke` is the first candle after the last touch to close through the band; a broken line is sent
  for ten candles (`_KEEP_BARS`). `retest_t`: the first later candle that reached the band from the other side and
  closed back away.
- Per kind and chart at most two: the holding line within 15% of the price (`_NEAR_PCT`) with the most touches,
  then the longest, then the latest last touch; and the latest broken one, unless the holding line was touched
  after that break.

**What the plan says** (owner `stock_read/line_notes.py`, pure). The Plan's `levels` adds `lines: LineNote[]`, at
most one per role in the order `way`, `stop`, `broke`; each `{role, state, text, detail, line (its id), price}`,
measured on the plan's side (a short's are the mirror), from both charts' lines:
- `way` -- the nearest holding descending resistance over a long's entry (past its band) and under its furthest
  target, or ascending support under a short's entry and over its furthest target: `warn`, with `r` (its distance in
  R), its text naming the target it comes before ("before target 1", #845). Else, a line
  between the price and the entry: `info`, "it trades the break".
- `stop` -- the nearest holding ascending support under a long's entry (descending resistance over a short's),
  within 2R of the entry: `ok` when the stop is beyond its band, `warn` when on it or between it and the entry;
  `info` without a stop.
- `broke` -- a broken line the price still stands through: `bad` against the plan (a long's support, a short's
  resistance), `info` with it.

**On the desk** (owner `frontend/src/stock_read/trendLines.ts`; drawing `sceneRender.ts` / `SetupShapesPrimitive.ts`).
The 1-minute pane draws `one_minute`, the 5-minute pane `five_minute`, under the Levels switch; the 10-second and
Full Day panes draw none. A line runs solid from its first touch to its last and dashed on to the pane's newest
candle (`slope` a candle, counted in the pane's candles), with a ring on each touch; a broken line is faint, dashed,
with a cross on the candle that closed through it. Its name ("↗ support · 4", "↘ resistance broke 09:52") sits in
the edge column where it runs on the newest candle (out of view, a tag with that price); the line and its name open
a card: where it runs against the price, the touches and the band, its slope, what a break means, and that how
often these lines hold is not measured. Each minute pane's Key lists them. The plan card adds a "Line" row per
note.

## Who trades the stock (ADR 037, operator ask 2026-09-24, #604, #606)

"When may Nova buy for you? I want a clear option next to level 2 ... if I selected the exit is on
me, then I'm going to be the one who exits, not the bot." Owner `backend/stock_mode/`: the routes,
the in-memory store and the runner. Nova places for a stock only on Paper, or on Sim -- at the live
edge, or on a loaded replay (ADR 052 and its amendment, #815; bot.md "The bot trades a Sim replay"). On Live every Nova side is locked, and the lock says why: a Nova buy is `auto_live`, NO-GO,
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
- An **Approval** is `{setup_id, setup_type, entry, stop, target, target2, target1_fraction, qty, approved_at,
  state: "waiting" | "sent" | "withdrawn", reason}` -- `target2` the plan's target 2 (null: every share at
  target 1) and `target1_fraction` the share sold at target 1 (null when the approval names none), #845.
- A **Trade** is `{kind: "auto_entry" | "approve" | "bot", state: "entering" | "holding" | "closed"
  | "missed" | "handed", venue, venue_day, setup_id, setup_type, qty, entry, stop, target,
  entry_order_id, target_order_id, stop_order_id, fill_price, filled_at, exit_price, exit_reason:
  "target" | "stop" | "time" | "flush" | "outside" | "handed" | null, exits: "nova" | "you", sent_at, closed_at:
  number | null, note, exiting: boolean, target2, target2_order_id, target1_qty, target2_qty, halves: [{leg,
  qty, price, ts, order_id}]}` -- `closed_at` when it closed, missed or was handed; `exiting` true while the bot
  is selling it. The two halves' fields (#681, #845) are null (`halves` empty) on a trade that sells every share
  at target 1; `exit_price` is the shares-weighted price of every sale. The bot's own trade is mapped from `bot-session.json`
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
- `POST /api/stock-mode/{symbol}/approve` takes `{setup_id, entry, stop, target, qty, now?, target2?,
  target1_fraction?}` and answers the view. The stock must be in Approve, and the plan must be the lane's own:
  the setup id, with its levels within a cent -- target 2 too (#845): on both or on neither, so an approval that
  leaves out the lane's target 2, or a lane that re-arms with another, is `STOCK_MODE_PLAN_CHANGED` and its
  error names the lane's levels ("10.02 / 9.89 / 10.28 / 10.50"). `target2` must be past target 1 (over it on a
  long, under it on a short) and `target1_fraction` over 0 and at most 1, else 400 `STOCK_MODE_INVALID` with
  `field: "target2"` / `"target1_fraction"`. `now: true` on a triggered setup sends the bracket at once.
- `DELETE /api/stock-mode/{symbol}/approve` withdraws a waiting approval, or cancels a sent entry
  that has not filled; its exits go with it.
- `POST /api/stock-mode/{symbol}/take-over` cancels the exits Nova holds on the stock:
  - Approve's bracket legs still resting (both targets and the stop; a half already sold is done);
  - or the bot's trade. The bot cancels its target and stop legs, stops watching, and ends the
    trade `handed`, releasing its shares from the sleeve.
  - Buy always stays on You after a take-over (ADR 042: it could turn into Auto-entry and buy the
    next trigger at the old risk), and a cancel that is refused keeps the trade and says the order
    still rests.

A refusal is `{detail: {reason, error, field}}`:
- 400: `STOCK_MODE_INVALID`, `STOCK_MODE_RISK`.
- 409 `STOCK_MODE_LIVE`: a Nova side on Live, or on a venue Nova cannot read.
- 409 `STOCK_MODE_REPLAY`: Sim off the live edge with nothing loaded (Auto-entry, Approve, Nova's exit).
- 409 `STOCK_MODE_HELD`: Sell to Nova while the stock is held.
- 409 `STOCK_MODE_NOT_APPROVE`.
- 409 `STOCK_MODE_FILTERED` / `STOCK_MODE_NOT_A_TRADE`: Approve on a setup the template's filter keeps
  out, or a plan that is not a trade.
- 409 `STOCK_MODE_PLAN_CHANGED`: the setup is no longer armed at those levels.
- 409 `STOCK_MODE_NOTHING_HELD`: Nova holds nothing of this stock to take over.
- 409 `STOCK_MODE_BOT_EXITING`: the bot is already selling.
- 409 `STOCK_MODE_SEND`: the execution door refused the send; `error` is the door's own reason.

**What Nova does.** The runner (`stock_mode/runner.py`) hears the setup scanner's triggers
(`SetupEngine.add_trigger_listener`) and the Sim eyes' (`SimEyes.add_trigger_listener`), each only on the desk
it is for: the live scanner's on Paper and at the live edge, the Sim eyes' for the replay loaded now. Its clock
is the venue's (the playhead on Sim).
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
  - **Two halves** (#845, operator decision 2026-10-12): with the approval's target 2 the bracket adds
    `target2_price` and `target1_qty` (`execution.md`, "A bracket in two halves"): target 1 sells
    `target1_fraction` of the shares (half by default, the smaller part of an odd count), target 2 the rest,
    the stop every share -- split by the bot's and Nova's exit's one rule (`exit_targets.apply`,
    `halves.split`); one share, or no target 2, sells every share at target 1 as before. The runner books a
    first half that fills (`stock_mode.exit_legs`): a `stock_mode` audit line `half` and the stock's last
    event ("Nova sold 76 at target 1 10.28; the stop 9.89 stays for the other 77"); the broker shrinks the
    stop to the shares left and it never moves. The stop, or the target that sells the last shares, closes
    the trade, its money over every share ("Closed: the target 2 10.50 filled at 10.50 (target 1 10.28 x 76,
    target 2 10.5 x 77) · +$56.72"). A short plan's is the mirror: covers under the entry, a buy stop over it.
    A Sim rewind puts a first half back with the trade (bot.md, "Auto-entry, Approve and Nova takes the exit
    on a replay").
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
- Level 2 draws ENTRY, STOP, TARGET and T2 (target 2, #845; a short's TARGET ↓ and T2 ↓ with the bids) as
  separator rows where they sit in the book (the `MontageSide` `markers`), dashed while only a plan and solid
  while an order stands behind them -- Approve's second limit marks T2 solid, and a target whose half sold
  reads as the plan's again.
- The plan card's buttons follow the mode:
  - Signal only: Stage in ticket; Stage sell (at the target, or at the bid once an exit is due)
    while shares are held.
  - Approve: Approve (an armed plan), Approve: buy N now (after its trigger), Approved · cancel,
    Cancel stop and target (take over the exit; "Cancel stop and targets" while both targets rest). With a
    target 2 the request carries `target2` and `target1_fraction` from the plan, and Approve's hover and the
    APPROVED card name both limits as they will rest: "Nova sends buy 100 @ 6.00 with stop 5.89, LMT 6.12 x 50
    and LMT 6.96 x 50 when 5.99 prints with the tape at go" (`exitTargets.limitWords`, the exit sheet's words).
  - Auto-entry: Auto-entry on · turn off; Stage sell once Nova bought.
  - Bot: Bot on SYMBOL · stop it; Take over the exit while the bot holds it.
- The badge promises a Nova buy ("THE BOT TRADES THIS", "NOVA BUYS AT ...") only when nothing
  blocks it (ADR 042); otherwise it says why, every reason on hover. The plan card shows the size
  Nova would send in a Nova mode. The Bots page lists every stock not at Signal only (`GET
  /api/stock-mode`), so an Auto-entry stock is never invisible once its tab closes.
  - A trade Nova closed on the plan's setup reads "Closed · +$X" (gross, from the fill to the exit).
- The Trader reads the view every `STOCK_MODE_POLL_MS` while the tab shows, on a replay desk too (ADR
  052). Nothing is read on the sample desk.

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
raise: {to, round, at, text} | null, target: {price, kind, rule, traded_at: number | null} | null,
target2: {price, kind, rule, traded_at: number | null} | null, target1_fraction: number,
ladder: [{role: "then" | "next" | "now" | "through" | "broke" | "support" | "stop" | "cost", price, text,
r: number | null, usd: number | null}], broke: [{round, at, close}], through: [{round, at, high}],
levels: {room, target, target2, stop, next, recent}, checks: Check[]}`:
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
- **The targets** (#845; `stock_read/held_targets.py`): the menu's defaults read from the position -- target 1
  (`target`) 20c over your average or 1c under a closer half / whole dollar, target 2 (`target2`) 1c under the
  high of day past it, else 1c under the next zone of today's map past it, else `null`; `target1_fraction` 0.5
  with a target 2, 1.0 without. A short's are under the average (1c over the low of day). `rule` says it ("your
  average +20c", "1c under HOD 6.97"); they never depend on R. `traded_at` when a candle since `held_since`
  reached each. These are the keys Nova's exits read (`target`, `target2`, `target1_fraction`).
- **The ladder**, highest price first: the first two zones of today's map over the price (`next`, `then`),
  the price (`now`), the through and broke rounds under it, the nearest zone under the price over the stop
  (`support`, when no broke round is there), the stop and the average (`cost`). `r` is in the held risk.
- **The rows** (`levels`, the plan's note shape) are measured from the price, never the entry: Room to the
  first zone over the price in R (`info`; trial T7 reads entries, not positions), each target behind or
  ahead ("Target 1 5.28 is 20c above", "Target 2 6.96 traded at 08:58: you are past it"; a short's rows say
  Cover 1 and Cover 2, as its tiles do: "Cover 1 5.57 is 9c below"), the stop's round (`level_notes.stop_note`), the next round over the price and a round just
  broken or lost. `checks` are the plan's checks that hold for a position: the spread against what the stop
  gives back, the 1-minute MACD, the 9 EMA, VWAP, the tape's flow, bids pulled and a halt.

`GET /api/stock-read/{symbol}/flush` (cheap: the sensor rings only) answers `{schema_version: 1, symbol,
at, score: number | null, label: "burst" | "flush" | "neutral" | "quiet" | "blind", window_sec}` -- trial
T1's reading (`tape_flow` with a 30 s window, every other number the default); the Trader reads it every
`STOCK_READ_FLUSH_POLL_MS` while you hold. It is a call in trial, never an order.

**A big seller over the price** (#846, operator ask 2026-10-12). While the tab's account holds shares -- long or
short, live or on a Sim replay -- the Trader reads `GET /api/book-watch/{symbol}/big-sellers`
(`book-watch-and-luld.md`) every `STOCK_READ_BIG_POLL_MS` (1 s; `useHeldTrade`, normalized by
`frontend/src/stock_read/bigSeller.ts`, which ignores another `schema_version`). Shown, never acted on: no order,
no stop move, no gate.
- **The held card's line** (`BigSellerLine.tsx`, under the card's header, folded or not): for a long, the nearest
  big seller still there -- "BIG SELLER 20,000 @ 4.50 · 3¢ over · held 42 s" (size now, its price, how far over
  the price -- "at the price" at or under it -- and how long it has been big; "held 3 min+" when it was there
  before the first book Nova read) in amber, the rest on hover (its multiple of the other asks, since when, the
  size first seen, what traded there); "BIG SELLER @ 4.50 · LEFT THE BOOK" for the second it is judged; then
  "BIG SELLER @ 4.50 TAKEN" (green: a print went through it, or N of the M that left traded there -- the seller
  is gone), "BIG SELLER @ 4.50 PULLED" (it left with N traded there) or "BIG SELLER @ 4.50 · OUT OF VIEW" (whether
  it traded is unknown) while the reading carries it. With a fresh line and none: "No big seller within 5¢ over
  the price", or "Too few asks on Level 2 to tell a big seller (N shown)". With no read: "No read on big sellers",
  the backend's `reason` on hover (no depth line, a stale line, the watcher off, nothing recorded on a replay);
  a failed poll says so the same way. For a short the mirror: BIG BUYER on the bid, "under", "bids". Nothing
  shows where the API has no such read (404) or on the sample desk.
- **The 1-minute chart's call** (`heldCalls.bigCall`): the same words as a call (tone `wait` while it is there,
  pinned at its price as BIG SELLER / BIG BUYER, one ping when it is called; `info` once it ended), keeping the
  moment's badge. A flush comes first; between a big seller and BROKE $X (a long's raise, a short's lower) the
  corner says the newer.

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

**Nova takes the exit** (Paper, and Sim -- at the live edge, or on a loaded replay, #815). `POST /api/stock-mode/{symbol}/take-exit` takes
`{stop, trail: boolean}`: Nova places a SELL stop for every share the venue holds at `stop` through the
execution door (source `manual`, origin `nova_exit`) and keeps a trade `{kind: "exit", state: "holding",
exits: "nova", qty, entry (the average), fill_price, stop, target: null, trail, stop_order_id,
raised: [{at, from, to, round}], ...}` (`stock-mode-trades.json`; the trade shape adds `trail` and
`raised`, and `kind` adds `exit`). **Targets beside the stop** (#681, operator ask 2026-10-12): the body
adds `target`, `target2` and `target1_fraction` (all optional). With a target, Nova sends the stop and the
target(s) as one exit-only pair through the door (`operation: "exit_oco"`, `execution.md`, "The exit-only
pair and two halves"), committed once: target 1 sells `target1_qty` (half by default, the smaller part of
an odd count), target 2 the rest; one share, or no `target2`, sells every share at target 1. The trade adds
`target2, target1_fraction, target1_qty, target2_qty, target_order_id, target2_order_id, halves: [{leg,
qty, price, ts, order_id}]`. A target's fill shrinks the stop to the shares left at the broker and the stop
stays where it is (never moved to the average); the trade stays `holding`, a `stock_mode` audit line
`half` and the stock's last event say "Nova sold 50 at target 1 10.30; the stop 9.80 stays for the other
50". The stop's fill, or the target that sells the last shares, closes it; `exit_price` is the
shares-weighted price of every sale and the event's money counts every share. Refusals add
`STOCK_MODE_INVALID` with `field: "target"` / `"target2"` (a target at or through the last price, past the
stop, a target 2 not beyond target 1, a target 2 alone). No target: the stop alone, as before. The view's
trade (and the bot's) carries `target2`, `target2_order_id` and `halves`. The runner (`exit_trade.manage`, every
`STOCK_MODE_POLL_SEC`): the stop that fills closes the trade; a position gone closes it `outside`; a stop
cancelled outside Nova hands the exit back (`handed`); with `trail`, at each closed minute a broke round
since the trade began raises the stop by a replace of the stop order (the rule above, up only), an audit
line `raised` and the stock's last event. On a replay the closed minutes are the replay's candles completed
by the playhead. Refusals: `STOCK_MODE_LIVE` / `STOCK_MODE_REPLAY` (Live, a venue Nova cannot read, Sim off
the edge with nothing loaded), `STOCK_MODE_NOTHING_HELD` (no shares, or the position cannot be
read), `STOCK_MODE_INVALID` (a stop at or over the last price), `STOCK_MODE_HELD` (Nova already holds an
exit or an entry on it), `STOCK_MODE_SEND` (the door refused). "Take it back" is `POST .../take-over`
(the stop and any target cancelled, the trade `handed`); Sell: You on the switch does the same. While it holds, the view's `sell` is `nova`. The Sell switch to Nova on a
held stock opens the sheet instead of `PUT` (which still answers `STOCK_MODE_HELD`). On Live the sheet is
locked and says why: Nova never moves a Live order by itself, and a Live stop does not trigger before
09:30 (#604).

## Why it's moving (ADR 028, operator ask 2026-09-23)

`GET /api/why/{symbol}` (owner `backend/move_reason/`, read-only, no network wait; rules
`move_reason/rules.py`, pure, thresholds in `constants_move_reason.py`) answers the Trader tab's
"Why it's moving" section: `{schema_version: 1, symbol, generated_at, session_date, rules_version,
replay: boolean, likely: {kind: "not_moving" | "news_pending" | "news" | "short_squeeze" | "routine_news" |
"split_squeeze" | "low_float_momentum" | "thin_trading" | "unexplained" | "not_read", label, detail,
confidence: "likely" | "possible", steps: [{kind, name, fits: boolean | null, why}]}, checks: [{id: "news" | "halts" | "float" | "float_rotation" |
"reverse_split" | "short_interest" | "borrow" | "volume", label, state: "yes" | "no" | "unknown",
value: string | null, detail: string | null, source, as_of: number | null}], facts: {board: string | null,
priced_by: "board_row" | "last_trade" | "row" | "quote" | "replay", last_trade: {price, change_pct, ts} | null, price,
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
The short-interest check is `yes` when the shares short are a fifth of the float, or three days to cover
with at least a tenth of the float short (`MOVE_SHORT_PCT_HIGH`, `MOVE_DAYS_TO_COVER_HIGH`,
`MOVE_SHORT_PCT_WITH_DTC`; rules v3, 2026-10-12): Yahoo's ratio divides by the volume from before a run,
so on its own it called a dormant stock's few shares short heavy (PFAI 2026-10-07: 9,077 shares, 0.25% of
its float, read 9.1 days to cover on a day it traded 27M shares). Days to cover under the floor adds
"Days to cover counts only with 10% of the float short" to the `detail`; without the share of the float
(no float or no shares short) the check is `unknown` on any days to cover. A share under 10% keeps a
decimal ("0.3% of float"), under 0.1% reads "under 0.1%".
`fee_rate` / `rebate_rate` are IBKR's annual percent; `open` / `prior` are `{listed, fee_rate,
available, as_of}` at the day's first poll at or after 04:00 ET and the last poll before it (null
when not recorded); `since` is the first poll the store holds. A symbol IBKR's file does not list is
`listed: false` (nothing to lend). Every unknown is `null` and its check `unknown`, never guessed;
`confidence` is `possible` when a deciding input is unknown. Descriptive only: nothing places or
gates on it.

On a Sim replay desk (`sim.mode.is_replay_desk`: the Sim off its live edge, a past day or today's
recording scrubbed back) the read is the replayed day's as of the playhead, never today's
(`move_reason/replay_facts.py`, ADR 028 amendment (2) 2026-10-12, rules v4): `generated_at` is the playhead,
`session_date` its day, `replay: true`, the payload's shape unchanged, and every fact comes from a record
that reaches the playhead and nothing after it:

- **Board row.** The recorded scanner board at the playhead (`leaderboard.playback.board_at`, ADR 023: a
  recorded minute counts from its stamp plus the settle) gives the price, change, volume, RVOL, the float
  Nova held that minute with its #532 check, and the day's exported news verdict (#498). A rebuilt board
  carries the session's enrichment-snapshot float, which may be later than the playhead, so there the float
  is the newest snapshot taken at or before it.
- **The loaded replay**, when it is this symbol: its last price-setting print, its previous close (#542) and
  its volume so far when it holds the day from 04:00 (`stats_scope: "session"`). It wins over the board row
  for price, change and volume.
- **News.** The board row's verdict, else the recorded catalyst feed's (`catalysts/recorded.py`): items
  published after the prior close and at or before the playhead, from the sources whose coverage spans,
  joined where they overlap, read the whole window. Alpaca and Finnhub are read live only and never answer
  here. A news halt comes from the day's halt log.
- **Short interest.** FINRA's newest settlement published by the replayed day, from Massive's archive
  (`<NOVA_MARKET_DATA_DIR>/store/reference/short_interest/<YYYY-MM>.jsonl`, `move_reason/short_interest.py`), the
  dump's one `short_interest.jsonl` split by settlement month by `research/orb/short_interest_months.py` (the
  reference dump runs it; a desk with only the dump reads `unknown` and names the command).
  FINRA publishes about seven business days after a settlement, after the close, so a settlement counts from
  the 8th exchange day after it (`MOVE_FINRA_PUBLISH_BUSINESS_DAYS`; a conservative rule, not FINRA's
  calendar): SDEV on 2026-10-02 reads Sep 15's 1,212,152 shares, not Sep 30's 3,436,239, which counts from
  Oct 12. Days to cover is FINRA's and says "(FINRA)"; `as_of` is the settlement date, and the `detail` names
  the day it counts from and a later settlement not out yet.
- **Borrow.** The borrow record at the playhead (`borrow_feed.view_at`): the last poll at or before it, the
  day's first poll by then and the changes up to it, never a later poll. Before the record's reach (it keeps
  `MOVE_BORROW_RETENTION_DAYS`) the check is `unknown`, value "Not recorded", with the reason ("Nova's borrow
  record starts Sep 28 20:21 ET (it keeps 14 days); Sep 18 10:00 is before it").
- **Split** from Massive's split list (the movers store, ADR 050): the last split executed on or before the
  replayed day. **Halts** from the day's halt log up to the playhead. **Shares issued** from the recorded
  feed's 8-Ks of the look-back up to the playhead.

Each check's `source` names the record it was read from and its `as_of` when; an unknown check's `detail`
says why no record reaches the playhead. Yahoo's fundamentals, the live boards, IBKR's latest borrow poll and
the live news memory are never read on a replay. When no record of the stock reaches the playhead (the halt
log alone, read for every day, does not count) the answer is `{..., replay: true, likely: {kind: "not_read",
label: "Not read on a Sim replay of Oct 2", detail: why, confidence: "likely"}, checks: [], facts: {}}`
(`move_reason.routes.not_read_on_replay`). A live edge that cannot be read counts as a replay. Off the replay
(Live, Paper, the Sim at its live edge) `replay` is `false`. The Trader card counts the checks' ages back from
the playhead and names the moment ("Sim replay, read as of Oct 2 10:31 ET"). It reads again when the Sim clock's
playhead goes back, when the desk moves between a replay and the live edge (the read on screen is dropped at
once, and an answer in flight across the rewind is thrown away), and when the playhead plays
`WHY_MOVING_REPLAY_REFRESH_SEC` past the last read -- a read from a later moment is never shown over an
earlier playhead. Before this the card showed
today's facts on a past day's desk: SDEV 2026-10-02 replayed on 2026-10-12 read "Not a big move today
(-3.9%)", Oct 12's change.

**The ladder** (`likely.steps`, rules v5, `move_reason/explain.py`): first `{kind: "move", name: "A real move"}`
-- `fits` false under the 10% move line either way (the cause is then `not_moving`), null with no change on record
-- then each cause in the order the rules try them (`news_pending`, `news`, `short_squeeze`, `routine_news`,
`split_squeeze`, `low_float_momentum`, `thin_trading`, `unexplained`), each with `fits` (`true`, `false`, or
`null` when a fact it needs is unknown) and `why`: the checks' own values with the threshold a failing part
missed ("Shorts 10% of float · 0.3 days to cover (Yahoo ratio) -- heavy is 20% of the float short, or 3+ days to
cover with 10%+ short"). It reads the same checks and thresholds as the cause: the first rung after the move that
fits is `likely.kind` (`tests/test_move_reason_explain.py` runs every combination of the deciding facts). Empty
on `not_read`.

**The Catalyst column** (operator ask 2026-10-12, ADR 028 amendment (3)): `GET /api/why?symbols=A,B,...&board=...`
answers `{schema_version: 1, rules_version, board, replay, generated_at, reads: {SYMBOL: <the read above> | null},
errors: {SYMBOL: "Type: message"}}` -- the same read for up to `MOVE_BATCH_MAX_SYMBOLS` (80) symbols, the halt log
read once for all; one symbol's failure is `null` with its error, never the batch's. `400` with no symbols, more
than 80, or a `board` not in `MOVE_BATCH_BOARDS` (`gappers`, `gainers`, `losers`, `afterhours`, `large_cap`).
With `board` each symbol's row on that board is read at the price the row shows (`priced_by: "board_row"`, a
frozen board's own price) and `last_trade` names the L1 line's last trade beside it (GIXI 2026-10-12: its frozen
Gappers row read $6.08, +56%; its last trade an hour later $3.94, +1.3%); a symbol the board does not hold is
read as the single route reads it. Without `board`, `priced_by` is `last_trade` (a row repriced by the L1 line,
the Trader card), `row` (no trade on the line) or `quote` (on no board); on a Sim replay it is `replay`, `board`
the recorded board the row was read from (the named board first, else Gainers first), `last_trade` null.

The column is the scanner boards' `newest_headline_at` column (its sort key unchanged), HOD Momo's `news`
column, the Contenders' `news` column and the focus rail's news mark, headed **Catalyst**. One cell shows one
cause: news keeps the News column's marks and words the catalyst class (`CATALYST_CATEGORY_SHORT`), and the other
causes get their own mark and word with a short second line built from the read's checks; a `possible` cause is a
hollow mark and its word carries "?". `not_moving` and `not_read` are a dash. The cells share one batch request
per board (`frontend/src/hooks/whyBatchStore.ts`), read again every `WHY_MOVING_POLL_MS`, and on a Sim replay
follow the playhead as the Trader card does (a rewind drops every read and any answer in flight). Hovering a cell
opens everything behind it (`CatalystExplain`): the call, the price it was read at and why, the news with its
class, source and time, the ladder up to the call (and later causes that fit too), and every check with its
source and age. Until a read is in -- and on an API without the batch route, or the sample desk -- the cell shows
the News column's own mark, never a guess.

The borrow feed (`move_reason/borrow_feed.py`, always on; `NOVA_BORROW_FEED=0` off) polls IBKR's
public short-stock file (`ftp://ftp2.interactivebrokers.com/usa.txt`, USD rows) every
`MOVE_BORROW_POLL_SEC` into `<cache_dir>/move_reason/borrow.sqlite3` (owner
`move_reason/borrow_store.py`; `PRAGMA user_version = 1`, unknown versions refuse): `polls (ts,
file_ts, rows)` and `changes (symbol, ts, listed, fee_rate, rebate_rate, available, capped)` -- a
row only when a symbol's listing, fee or availability changed, pruned after
`MOVE_BORROW_RETENTION_DAYS`. `/api/diagnostics` adds the `borrow_feed` row (group `recorder`).

