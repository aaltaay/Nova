# Data schema: Focus sensor, book watcher and LULD bands

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/sensors/, backend/book_watch/, backend/luld/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## The operator's focus and the book watcher (ADR 033, operator ask 2026-09-24)

Sensors for agents and bots: ask the endpoint, never guess. Both are in the
sensor catalogue (`GET /sensors`: 19 `focus`, 20 `book-pulls`) and answer the
sensor envelope `{sensor, status: "live", as_of, data, symbol?, error?}`.

**Focus.** Every desk window posts `POST /sensors/focus` (owner
`sensors/focus_routes.py`; at most `FOCUS_REPORT_MAX_BODY_BYTES`, 413 over,
422 invalid) on each change and every `FOCUS_HEARTBEAT_MS`: `{schema_version:
1, role: "main" | "popout" | "browser", window_id, instance_id, focused,
visible, page: "trader" | "desk" | "scanner" | "account" | "bots" | "records" |
"cryptos" | null, tab: string | null, symbol: string | null, symbol_source: "trader_tab" |
"desk_board" | "scanner_row" | null, trader_tabs: string[], last_input_ts:
number | null, reason: "start" | "focus" | "blur" | "visibility" | "page" |
"symbol" | "input" | "heartbeat", ui_tag}` -- `window_id` is the perf
recorder's (`main`, `trader:SYM`), `instance_id` one per page load,
`focused` `document.hasFocus()`, `tab` the scanner tab on the Scanner page,
`last_input_ts` the last click / keypress / wheel there (epoch seconds). The
Electron main process posts `{schema_version: 1, role: "electron", window_id:
"electron-main", app_focused, focused_window_id: string | null, windows:
[{window_id, focused, visible, minimized, display: {id, label, index, count,
primary, scale_factor} | null}], reason}` (monitors numbered left to right
from 1; reason also `display`). The sample desk sends nothing. `GET
/sensors/focus` -> `data: {schema_version: 1, nova_in_front: boolean | null,
focus_source: "electron" | "window" | null, symbol, page, tab, symbol_source,
window_id, role, display, since, last_input_ts, last_input_age_sec, windows:
[{window_id, instance_id, role, focused, visible, minimized, page, tab, symbol,
symbol_source, trader_tabs, display, last_input_ts, ui_tag, reported_ts,
age_sec}], recent: [{ts, window_id, page, tab, symbol, focused, reason}]
(newest first, at most `FOCUS_RECENT_KEEP`), venue, live_edge, note}` -- the
window Windows has in front (Electron's word first, else the window's own),
else, with Nova behind another app (`nova_in_front: false`), the window last in
front; `since` is when that window last changed page or symbol. A report older
than `FOCUS_STALE_SEC` is ignored; with none, the answer is null with `error`.
In memory only (`sensors/focus_store.py`), never persisted. Where the
operator's eyes are cannot be known; the last input is the stated stand-in.

**The book watcher** (`backend/book_watch/`). The live IBKR depth handler and
AllLast handler only enqueue (ADR 010); one thread follows every held depth
line with its tape. Each book is summed per price across venues; only prices
wholly in view in two consecutive books are compared (with every row in use the
worst visible price may be cut off, and a price that scrolled out of view is
unknown, never pulled; a side that collapses at once, an L1-only book and IBKR's
book reset are not judged). A drop in size is judged `BOOK_WATCH_SETTLE_SEC`
later: lit prints at exactly that price inside `BOOK_WATCH_MATCH_SLACK_SEC` of
the two books are **filled** (each print claimed once; FINRA and midpoint
prints never fill; the window is `book_watch/matching.py`'s, measured below; a
level a print traded through first takes that print's own, #636 below), the
rest **pulled**. A pull is **large** at `BOOK_WATCH_LARGE_MIN_SHARES` and
`BOOK_WATCH_LARGE_MEDIAN_MULT` x the side's median level. A large pull event is
`{event: "pull", symbol, ts, side: "bid" | "ask", price, pulled, filled,
level_before, level_after, median_level, distance_ticks,
distance_at_post_ticks, lifetime_sec, approached, opposite_volume}` (unknowns
`null`: a level there before the watcher's first book has no post time). A flag
is `{event: "flag", id: "<ts_ms>-<SYMBOL>-<kind>", kind: "pulled_on_approach" |
"repeated_pulls", symbol, ts, side, price | null, shares, why, evidence}` --
`pulled_on_approach`: a large pull after the side's best came toward it
(posted `distance_at_post_ticks` >= 1 away, pulled closer); `repeated_pulls`:
`BOOK_WATCH_REPEAT_COUNT` large pulls on one side inside
`BOOK_WATCH_REPEAT_WINDOW_SEC` (evidence `{count, window_sec, pulls: [{ts,
price, pulled}]}`, once per side per window). Hints consistent with spoofing,
never a detection: on a busy premarket name they are frequent (PFSA
2026-09-24: 299 in 93 minutes), so read them as a description of the book, not
an alarm. `GET /sensors/book-pulls?symbol=` -> `data: {schema_version: 1,
source: "ibkr_depth", watching, since, feed: {books, prints, books_per_sec,
median_gap_ms, last_book_age_ms, window_sec}, window_sec, pulled_shares,
filled_shares, pulls, fills, large_pulls, sides: {bid | ask: {pulled_shares,
filled_shares, large_pulls}}, flags[], pulls_recent[] (newest first, at most
`BOOK_WATCH_READ_LIMIT`), caveats[], note}` over the last
`BOOK_WATCH_STATS_WINDOW_SEC`; a symbol without a depth line answers
`watching: false` with the reason. `GET
/sensors/book-pulls/events?since=<epoch>&symbol=` -> `{schema_version, now,
since, flags[] (oldest first), watcher: {enabled, symbols, queue_depth, queued,
dropped, processed, errors, journal}, note}` -- a poller's feed. The L2
sensor's `spoof_hints` are the watcher's newest large pulls `{side, price,
from_size, pulled, filled, ts}`, and its replenish / cancel counts sum venue
rows per price. The journal (`book_watch/journal.py`):
`<dir>/YYYY-MM-DD.jsonl` (`NOVA_BOOK_WATCH_DIR`, else `F:\Nova\book_watch`
when F: is mounted, else `<cache>/book_watch`), one line per flag, large pull,
large drop and symbol-minute `{schema_version: 1, wall_ts, event: "minute", symbol,
minute_ts, books, prints, pulled_shares, filled_shares, pulls, fills,
large_pulls, flags}`; nothing prunes it. `NOVA_BOOK_WATCH=0` stops the
watcher, `NOVA_BOOK_WATCH_JOURNAL=0` its journal. `py -3
tools/book_watch_replay.py <recording dir>` runs the same detector over a
Session Record.

**What left the book, on the ladder** (ADR 033 amendment, operator ask
2026-09-29: "I see massive orders in level 2, and I just think they're
disappearing. I don't see them on time and sales"). The detector also judges
every **large drop** -- the size that left a price, traded or not, by the same
size rule applied to the drop -- as `{event: "drop", symbol, ts, side, price,
dropped, pulled, filled, outcome: "pulled" | "traded" (pulled over filled),
level_before, level_after, median_level, distance_ticks,
distance_at_post_ticks, lifetime_sec, approached, large_pull, on_approach}`
(`on_approach`: the `pulled_on_approach` flag's own rule); the journal keeps
them. `/ws/ibkr/depth/{symbol}` carries, beside its books, `{"type":
"book_watch", symbol, data: {schema_version: 1, now, reset, seq, watching,
reason: string | null, window_sec, sides | null, drops[] (each with its `seq`),
note}}` (owner `book_watch/ladder.py`), asked at most every
`BOOK_WATCH_PUSH_SEC`: a socket's first frame (`reset: true`) holds the large
drops of the last `BOOK_WATCH_LADDER_MEMORY_SEC`, later frames only those
judged since, and `sides` rides on each (refreshed on its own at most every
`BOOK_WATCH_SIDES_PUSH_SEC`). While the ladder shows no live line (a replay
desk) or the watcher is off, one `watching: false` frame gives the `reason`,
then nothing; the desk ignores an unknown `schema_version`. The ladder
(`ibkr/bookWatch.ts`, pure, and `ibkr/BookWatchParts.tsx`) marks each large drop
of the last `L2_PULL_MARK_SHOW_MS` (6 s, fading over the last 2) where its price
sits between the rows -- "✕ 2,000 pulled" in amber (solid when it was pulled as
the price came closer), "✓ 8,200 traded" in slate; drops between the same two
rows share one mark per verdict, and a price above the book is marked over the
column head. It hatches every row at a price with a large pull in the last
minute (the count and times on hover), and puts each side's `✕ pulled ✓ traded`
for the watcher's minute above its column, amber when pulled is over 3x traded
and at least 1,000 shares. Nothing is drawn over a size or a price, no row is
added, and Time & Sales still shows prints only. Every mark's hover ends "a hint
consistent with spoofing, never a detection". The reading's `pulls` count read
`null` until then (the recent-pulls list overwrote it; the Tape tile showed
"None pulls").

**Hidden sellers and buyers** (ADR 033 amendment, operator ask 2026-09-30: "do we have a way to detect
hidden sellers? like we have spoofing!?", then mockup v1 and "1 go"). The mirror of a pull: size that
traded at a price that held beyond the most the book ever showed there (owner `book_watch/hidden.py`,
pure). Per side the watcher follows one **stretch**, the price that side's counted prints keep landing
at -- lit prints at or through its best price, odd lots included, and prints at that price after the
size shown there is gone -- while a book younger than `BOOK_WATCH_IDLE_SEC` stands (a Session Record can
keep the tape after its depth line is gone); a cross print (`BOOK_WATCH_AUCTION_CONDITIONS`), a
volume-only print, a FINRA report and a midpoint print never count. The stretch weighs what printed
there against the most the book showed there from `BOOK_WATCH_HIDDEN_SHOWN_BEFORE_SEC` before its
first print. It is a **hidden seller** (the ask) or **hidden buyer** (the bid) once its price has held
`BOOK_WATCH_HIDDEN_MIN_HOLD_SEC` (10) since its first print, at least `BOOK_WATCH_HIDDEN_MIN_SHARES`
(2,000) printed there and at least `BOOK_WATCH_HIDDEN_SHOWN_MULT` (3) x the most shown; a stretch the
book could not follow (a collapsed side, its price cut off, a reset) never is. It speaks as a detector
event `{event: "hidden", id: "<started_ms>-<SYMBOL>-<side>-<price>", kind: "hidden_seller" |
"hidden_buyer", symbol, ts, side: "ask" | "bid", price, state: "holding" | "broke" | "faded" | "moved" |
"auction" | "reset", hidden (printed beyond shown_max), printed, shown_max, shown_now: number | null,
prints, refills, started_ts, last_print_ts, flagged_ts, ended_ts: number | null}` when flagged, as it
grows (at most every `BOOK_WATCH_HIDDEN_UPDATE_SEC`) and once when it ends (`broke`: a print went
through it; `faded`: no print there for `BOOK_WATCH_HIDDEN_GAP_SEC`; `moved`: the offer came down or
the bid went up); the journal keeps each. The readings' `sides.{bid,ask}` add `hidden_shares` (the
hidden size at the side's flagged prices, holding or ended in the stats window) and the reading a total
`hidden_shares`. `GET /sensors/book-pulls` adds `hidden_recent[]` (the newest word on each stretch,
newest first, at most `BOOK_WATCH_READ_LIMIT`) and `hidden_note`; `/sensors/book-pulls/events` adds
`hidden[]` (the newest word on each stretch sent after `since`, oldest first). The depth socket's
`book_watch` frames add `hidden[]` (each word with its `seq`; a `reset` frame carries each stretch's
last word while it holds or was heard in `BOOK_WATCH_LADDER_MEMORY_SEC`) and `hidden_seq`.
`/sensors/flow`'s `iceberg_hint` is the watcher's word: `true` when it flagged one in the last minute,
`false` when it follows the line and flagged none, `null` without a depth line, and `hidden: {stretches,
window_sec, note} | null` beside it -- it used to be true whenever any level grew while anything
printed. The stock read's tape group adds the row `hidden` ("Hidden size": `warn` while a hidden seller
holds at the offer, `info` otherwise) and the Tape tile reads "Hidden seller" then. On the ladder
(`ibkr/bookWatchHidden.ts`, pure) the row a hidden seller or buyer holds at is outlined in violet and
its mark sits under it ("◆ 12.4K hidden"; after it ends, "· broke" / "· held" and so on, fading like a
pull mark); each side's minute line adds "◆"; a word the watcher has not refreshed for
`L2_HIDDEN_STALE_MS` is not drawn. Every hover gives what traded against what showed, how it stands and
what `tools/hidden_study.py` found, and ends "never a detection". One reserve (iceberg) order and several
orders refilling a price look the same here. The setup scanner's tape gate keeps its own hidden-seller
veto; nothing here gates, stages or places.

`tools/hidden_study.py` (read-only; owner `book_watch/hidden_study.py`) runs the same tracker over every
Session Record and answers `{schema_version: 1, rule: {min_shares, shown_mult, min_hold_sec},
horizons_sec: [10, 30, 60, 300], recordings: [{date, symbol, books, prints, depth_hours, stretches}],
depth_hours, groups: {flagged_ask | busy_ask | flagged_bid | busy_bid: {n, per_hour, horizons: {H:
{measured, broke_pct, beyond_pct, toward_bp: {n, mean, median, t}}}}}, by_day: {DATE: groups}, events[],
grid?}` -- `flagged`: the moment the rule held; `busy`: a stretch where as much printed at a price that
held while the book showed enough to explain it; `broke_pct`: a counted print went through the price by
then; `beyond_pct`: the mid past the price then; `toward_bp`: the mid's move toward the break (up for
an offer, down for a bid). A horizon past its recorded stretch is not measured. On the Session Records
of 2026-09-21..29 (26 hours with a book), a minute after a hidden seller the mid was past the offer 37%
of the time against 46% after a busy offer (104 against 66); a hidden buyer made no such difference.

**The matching window, measured** (ADR 033 amendment 2026-09-30; asked after the hidden-seller study:
the lit size at the quote that no drop claimed often had a pulled drop at its price nearby, so does the
window call fills "pulled"? "Change it only if the evidence is clear"). The detector takes the window
as a parameter, `MatchParams(before_sec, after_sec, settle_sec, sweep_hold_sec)` (owner
`book_watch/matching.py`; `settle_sec` must exceed `after_sec`, and a swept level's prints must still be
kept when its drop is judged), and an optional `judged` list that collects every judged drop with the
prints it claimed; the live watcher runs the defaults and collects nothing. A lit print fills only a
level at exactly its price (price keys, `matching.PRICE_EPS`): the old half-tick test let
floating-point error match a midpoint print to the level below it. `tools/book_watch_window_study.py`
(read-only; owners `book_watch/window_study.py` and `book_watch/sweep_study.py`) runs the detector over
every Session Record up to yesterday (`--until`; today's may still be recording), cross prints and
prints with no book within `BOOK_WATCH_IDLE_SEC` left out, and answers `{schema_version: 1,
windows_sec: [0.5, 1, 2, 3], extensions_sec: [1, 2, 3], shift_sec: [30, 60], seeds: [1, 2],
sweep_hold_sec, recordings: [{date, symbol, books, books_per_sec, prints, left_out: {cross, tape_only},
sweep, extension, evidence, depth_late, sweep_rule}], by_day: {DATE: {sweep, extension, evidence,
depth_late, sweep_rule}}, total}`:
- `sweep: {"0.5" | "1" | "2" | "3": {dropped, filled, pulled, large_pulls, flags: {pulled_on_approach,
  repeated_pulls}, large_drops, large_traded}}` -- the detector with that window either side of a
  drop's two books, judged 0.25 s after it closes (shares and counts), with the sweep rule on.
- `extension: {pulled, before | after: {"1" | "2" | "3": {real, moved_real, moved, tick_out}}}` --
  shares a window reaching that far before the earlier book (the print early: the book trailing the
  tape) or after the later one (the print late) would fill beyond the 0.5 s window, of the `pulled`
  shares: `real` from the prints no drop claimed; `moved_real` / `moved` from those a move of 30-60 s
  could place with their price in the same place against the quote, at their own time / moved (mean
  of the seeds); `tick_out` from all of them one tick away from the inside. A moved print first meets
  the drop's own 0.5 s window, as an unclaimed print had. Real less moved is what the window misses.
- `evidence: {real | moved: {volume, print_late_0.5_3, print_early_0.5_1, print_early_1_3}}` -- the
  unclaimed lit size at the best bid or ask, and how much of it had a pulled drop at its price shown
  0.5-3 s before it or 0.5-1 s / 1-3 s after it; real and moved are the same prints.
- `depth_late: {through, "<=0.5", "0.5-1", "1-3", "3-10", never, grew_first}` -- lit prints through the
  displayed best price (that level at least 100 shares), by when a book showed that level smaller or
  gone; `grew_first` counts those not shown smaller within 0.5 s whose level the book showed larger
  first (new size posted there: a refill, not the book trailing its tape).
- `sweep_rule: {sweeps, levels, pulled_off, off, on, covered: {drops, dropped, filled_off, filled_on},
  reach: {real, matched_real, moved, beyond}}` -- the sweep rule below: the sweeps and the levels they
  took; the detector at 0.5 s without the rule (`off`; its drops left `pulled_off` shares pulled) and
  with it (`on`), each shaped like a `sweep` entry; the drops the rule let take a sweep's prints
  (`covered`: their size, and what read filled without and with the rule); and the size the rule adds
  to what the detector fills (`reach`), always the detector itself: `real` with the sweeps it finds;
  `matched_real` / `moved` with its own sweeps off and given the sweeps that a move of 30-60 s could
  place at a moment their best price stood as the best again, at their own moments / moved (mean of
  the seeds); `beyond` given the level one tick past where each sweep stopped, at its own moments. Real
  less moved (or beyond) is what the rule recovers; moved and beyond are chance.

On the 27 recordings of 2026-09-21..29 the window stays 0.5 s: moved prints had a pulled drop 0.5-3 s
before them as often as the real ones (45.3% against 44.9%); 87.9% of 339,550 through-prints saw the
book show their level gone within 0.5 s and 10.2% took 0.5-3 s; and reaching 1 s before the earlier
book would fill 2.3% of the 82.0M shares called pulled, only 0.5-0.6 points beyond chance (3 s: 7.8%,
1.3-2.2 beyond; 1 s after the later book: 2.0%, 0.2-0.3 beyond).

**A level a print traded through reads traded** (ADR 033 amendment 2026-09-30, #636; the operator: "1
go"). A lit, price-setting print above the book's best ask (below its best bid) proves the size the book
showed at the round-lot levels from the best to its own price traded: a protected quote cannot be
traded through. `matching.Sweeps` keeps that size owed per level. For `BOOK_WATCH_SWEEP_HOLD_SEC` (3 s)
after the sweep, a drop at one of those levels first takes the sweep's own prints -- lit prints at its
exact price within 0.5 s of the sweep -- at most the size still owed, and then its own window; each
drop the book shows there pays the owed size down. New size posted at the level, or the level leaving
the view, ends it: a later drop there may be the new order, pulled, and the sweep's leftover prints (a
hidden order, a refill that traded) are not its own. A level pulled before the sweep reached it has no
print there and still reads pulled. An odd lot, a cross, a volume-only or an off-exchange print proves
nothing (`BOOK_WATCH_SWEEP_SKIP_CONDITIONS`), nor does a print through an odd-lot best
(`BOOK_WATCH_SWEEP_MIN_LEVEL`) or a book older than `BOOK_WATCH_IDLE_SEC`; a book reset forgets every
sweep. On the same 27 recordings: 9,695 sweeps; the drops the rule covers read 86.2% traded without
it and 88.7% with it; it adds 0.37% of the size called pulled (299,598 shares), 98% of it beyond chance
against the level a tick past each sweep and 76% against the same sweeps moved 30-60 s -- on the
recordings that kept every book IBKR sent (2026-09-25 and -29), 0.14%, 91% and 49%; large pulls 11,121 ->
11,071, flags 3,190 -> 3,176. A first build without the owed size or the end on new size added 1.6%, and
84% of what it relabeled on six busy recordings sat at levels refilled after the sweep: its chance tests
passed, because the prints were real and next to a real sweep and only the drop they filled was wrong.
Of the 12.1% of through-prints not shown smaller within 0.5 s, 4.2 points had new size posted at the
level first (`grew_first`); 7.8% sat in the book untouched until it showed them smaller. The window
stays 0.5 s: with the rule on, reaching 1 s before the earlier book still adds 2.0%, 0.3-0.4 points
beyond chance.

## LULD bands on Level 2 (ADR 047, operator ask 2026-10-06)

"do we have LULD levels?", then, beside DAS screenshots of red `LULD` rows at each band: "1 go.. make it obvious".
IBKR passes on the halt but no band, so Nova computes each stock's limit up / limit down from the published LULD
Plan rules (owner `backend/luld/`). Read-only: nothing places, stages, gates or cancels an order on it.

- **The rules** (`luld/rules.py`, `luld/tracker.py`, pure):
  - The percentage comes from the previous close (IBKR's tick 9), fixed for the day. Over $3.00 it is 5% (Tier 1)
    or 10% (Tier 2); from $0.75 to $3.00, 20%; under $0.75, the lesser of $0.15 or 75%. It doubles 15:35-16:00 for
    Tier 1 and for Tier 2 at or under $3.00.
  - Bands round to the penny, half up. There are none outside 09:30-16:00 ET.
  - The first reference is the listing exchange's opening print (condition `O`, from any venue but a trade-report
    facility). For five minutes the mean of the trades since it follows; after that, the arithmetic mean of the
    eligible (price-setting) trades of the preceding five minutes. A new mean replaces the reference only when it is
    1% or more away and the old one has stood 30 s. Five minutes without a trade keep it.
  - A limit state (the NBO on the lower band, or the NBB on the upper, not crossed) holds the reference; 15 s in it
    is a pause due. A halt shows no band; the reopening print (`5`) is the next reference.
  - Measured against the SIP's own band flags (the Massive NBBO indicators), a limit state's end makes no reference
    of its own. The Plan's text says it does; keeping the reference matched 81% exactly, against 64%.
- **Exact or approximate.** `exact` when Nova saw the stock open or reopen with its tape unbroken since.
  - Otherwise a band appears after five minutes of tape, seeded from the mean: `exact: false`, with `spread` (how
    far it may sit from the exchanges', in dollars). An approximate band never claims a limit state.
  - A lost tape line or an IBKR feed gap makes an exact band approximate until the next reopen.
  - The tier: a company of at least $15B is Tier 1 and one of at most $2B Tier 2 (sure). Between them, the side of
    $4.5B; with no size known, Tier 2. Both read `tier_sure: false` and show `≈`.
- **The live worker** (`luld/live.py`). The AllLast and Level 1 handlers only enqueue (ADR 010). One thread keeps a
  tracker for every stock whose tape line Nova holds, from its first live print until 30 minutes without one. Every
  0.25 s it reads the halt state (`halt_status.halted_now`), the line (`tape_stream.is_subscribed`) and feed gaps
  (`feed_pulse`). In memory only; `NOVA_LULD=0` turns it off.
- **The replay** (`luld/replay.py`). On a Sim desk off the live edge with a Session Record loaded: the bands at the
  playhead, from the recording's prints, book tops and the day's halt log, never ahead of the playhead. It runs on
  its own thread, with a checkpoint every 5 minutes of replay.
- **The view** (`luld/views.py`) is one shape for `GET /api/luld/{symbol}` and the depth socket's `{"type": "luld",
  "symbol", "data": view}` frames (sent on change, and at least every 5 s): `{schema_version: 1, symbol, source:
  "live" | "replay", state: "off" | "unknown" | "warming" | "bands" | "limit" | "pause_due" | "paused", exact, lower,
  upper, reference, reference_since, reference_source: "open" | "reopen" | "mean" | "open_mean" | "seeded" |
  "first_trade_after_halt" | "limit_exit" | null, reference_words, percent, prev_close, tier: 1 | 2 | null,
  tier_text, tier_sure, spread, limit: {side: "down" | "up", since, band, pause_at, overdue} | null, straddle: "down"
  | "up" | null, anchor: {kind, ts, price} | null, halted_since, watching_since, warm_until, gap: {ts, reason} |
  null, last, distance: {down_pct, up_pct} | null, near: "down" | "up" | null, reason, history: [{ts, reference,
  source}], note, rules, track, as_of, text, watching?}`.
  - `lower` / `upper` are null unless `state` is `bands`, `limit` or `pause_due`. `near` means within 2% of the
    price or 5 cents. `track` is the measured record (`luld/track_record.py`).
  - `GET /api/luld` lists the stocks the live worker follows. The stock read's halts row `luld` reads the view.
- **On the desk** (`frontend/src/ibkr/luld.ts`, `LuldStrip.tsx`, `luld.css`):
  - The Level 2 ladder draws the lower band in the bid column and the upper in the ask column: a bold rose line and
    a `LULD 4.40` tag where the price sits among the rows, or under the last row (`↓`) when deeper. It pulses while
    the price is near or on it.
  - A 15 px strip above the book reads `LULD ▼ 4.40 −18.6% | ▲ 6.60 +22.0%`, the side amber when near. In a limit
    state it reads `LIMIT DOWN 4.40 · PAUSE IN 9s` in red, the 15 s counting down. Outside 09:30-16:00 it is gone.
  - `≈` marks an approximate band or an assumed tier. Every piece's hover says it is Nova's calculation, how it
    knows, and the measured record.
- **Measured** (`tools/luld_check.py`): `massive` replays the Massive flat files' trades and NBBO and compares with
  the SIP's own flagged bands; `records` checks Nova's Session Records against the price the quote sat at for the
  15 s before each logged pause.

