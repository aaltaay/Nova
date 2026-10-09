# Data schema: Market data: prints, tape, feed gaps, L1 lines, session end, chart bars

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/ibkr/, backend/sale_conditions.py, backend/chart_bars.py. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Prints that set a price (operator report, 2026-09-23)

Each live AllLast print on `/ws/ibkr/tape/{symbol}` gains two fields, and so does each Session Record print row: `unreported: boolean` (IBKR's `tickAttribLast.unreported`) and `sets_price: boolean`. `sets_price` is false when IBKR flags the print unreported, or when its sale conditions carry a code that never moves the consolidated high / low / last:

- `C` cash, `H` price variation, `I` odd lot
- `M` / `Q` official close / open, `N` next day
- `P` prior reference, `R` seller
- `U` extended hours out of sequence
- `V` / `7` contingent, `W` average price
- `4` derivatively priced, `9` corrected close

The owner is `backend/sale_conditions.py`; the codes live in `constants_tape.py`. Time & Sales shows every print, and dims one that does not set a price with the reason in its tooltip (#543). A Sim capture replay's prints on `/ws/ibkr/tape/{symbol}` -- the seed a socket gets on open or a scrub, and the stream as the playhead moves -- carry the same two fields, from the recorded row (`sale_conditions.tape_flags`). Every candle Nova builds from prints uses only the prints that set a price, volume included, because IBKR's own TRADES bars count the same prints. That covers the Trader's client 10Sec bar, `ibkr/tape_10sec`, the archive 1m builder, the recorder's bar buckets and a capture replay's print-built candles. A row without the fields (an older recording) is judged by its conditions. A Session Record replay draws every candle from its prints and never from the bar buckets stored beside them (#535, operator decision 2026-09-23): recordings made before this rule stored buckets built from every print, and `replay_load.counts` no longer lists `bars_10s` / `bars_1m` / `bars_5m`.

Practice fills follow the same rule (#511): on Paper, and on Sim at the live edge, the practice broker's newest-print last and its resting-order matcher read only the prints that set a price, and so do a capture replay's last and matcher. The live tape archive (`l2.db` `tape_trades`) adds a nullable `unreported` column (IBKR's flag) beside `conditions` for this; a row stored before it is judged by its conditions. It also keeps nullable `bid` / `ask`: the top of book the print met when it arrived, which a practice short under SSR reads at its fill (ADR 048); a row stored before them has neither, and such a short keeps resting. A historical download already excludes IBKR's `unreported` prints.

**Print times (#563).** ib_async 2.1.0 stamps each AllLast tick with the moment its message reached Nova (`Wrapper.lastTime`) and throws IBKR's own `time` argument away. A live print's `time` / `ts` is that arrival time, and it says so: `ts_source: "receive"`. IBKR's whole epoch second for the print rides beside it as `exchange_ts: integer | null`, on each live print on `/ws/ibkr/tape/{symbol}` and on each Session Record print row; `ibkr/tape_exchange_time.py` keeps the `time` argument with a thin override of `Wrapper.tickByTickAllLast`, installed on the IB that opens the tape line. `exchange_ts` is `null` when the override did not see the tick. Prints stay ordered by arrival, because the books they are classified against are arrival-timed too. Rows recorded before #563 say `ts_source: "exchange"` but hold arrival times as well, and carry no `exchange_ts`; they load as they are and are never rewritten. `l2.db` `tape_trades` and the archive keep no `exchange_ts`.

**A 10-second candle has one clock and one writer (#721; operator report 2026-10-05: "two candles drawing
together ... the previous candle should never move").** Built from prints -- the Trader's client bar
(`chart/barsStore.upsertTapePrint10SecBar`) and the backend's `ibkr/tape_10sec` -- a candle is keyed by
IBKR's own second for each print (`exchange_ts`, arrival time only when it is missing), the clock IBKR's own
10-second history uses, so a history fill moves no candle the tape drew. Arrival time had built 51-97% of the
day's candles differently from IBKR's, and trails IBKR's second by 0.6 s at the median, up to 9 s. IBKR
delivers prints in the order of that second: 1,219,396 October prints, none out of order. So a candle never
takes a print after the next one opened. The backend flushes a quiet bucket `TAPE_10SEC_FLUSH_GRACE_SEC`
after its ten seconds, and neither side reopens a closed candle. The 10-second pane's forming candle is the
tape's while the tape delivered a print within `CHART_10SEC_TAPE_OWNS_MS` (`chart/useChartLiveTrade`,
`tapeOwns10Sec`). The ticker's `trade_update`, stamped with Nova's clock when the Level 1 tick lands, opened
the next candle while prints still filled the last one, and now paints it only when no tape feeds it (Time &
Sales hidden, lent or silent). Minute candles and Sim replays keep their clocks.

The L1 last every quote reader takes (`ibkr/ticks_handler.py`) is IBKR's Last (tick 4, or 68 delayed). It is never the RTVolume or AllLast price that ib_async also writes into the one `ticker.last` it keeps per contract. A line that has not yet delivered a tick 4 falls back to `ticker.last`.

**The prior close is not a trade (#541).** Before a line's first trade its price is IBKR's prior close (tick 9), flagged `quote_quality: "close_fallback"`. Scanner rows show it as such; nothing else takes it as a trade: no live 1-minute candle (`ibkr/l1_minute`), no HOD Momo trade or L1 archive tick, no `trade_update` to a chart tip, no HOD enrichment price or change, and `snapshot_quotes` rows carry the same flag. `ibkr.ticks.last_quotes` rows add `quote_quality` and `last_trade_ts` (IBKR's Last Timestamp, tick 45 / 88, epoch seconds, `null` when IBKR has not sent one); a quote change keeps a line fresh but is not a trade. The ticker snapshot (`ticker_ibkr.fetch_ticker_snapshot_ibkr`) answers `latest_trade: null` and `daily_bar: null` before today's first trade (the prior close stays `prev_close`), stamps `latest_trade.timestamp` with the trade's own time (a stored bar's minute, a row's quote time, `null` when unknown -- never "now"), takes a stored 1-minute bar only from today's Eastern date, and reports an unknown volume as `null`, never `0`.

**Level 2 books are Nova's own (#540).** ib_async 2.1.0 keeps each side of a depth book in a dict keyed by row: an IBKR insert overwrites the row instead of shifting the rows below it, a delete leaves a hole, and a row inserted after a delete lands at the end, so `ticker.domBids` / `domAsks` fell out of price order (GRML 2026-09-22: 466 of 111,116 recorded books, 269 with a first bid or ask that was not the best). `ibkr/depth/book.py` keeps each line's book from `ticker.domTicks` with IBKR's row rules, reset on every depth request and on IBKR error 317 (depth reset); every Level 2 reader -- the ladder, Session Record quote and L2 rows, the tape gate, Time & Sales sides -- gets that book. A kept book found out of price order is sorted and logged once per line. Books recorded before this are read best-price-first (`sim/capture_player.book_at`, `l2/recall.book_before`); quote rows recorded from them are not rewritten.

## The tape archive never stops writing (operator report, 2026-09-24)

Owner `ibkr/tape_sink.py`. The L2 tape archive writer (`l2.db`
`tape_trades`, the prints Paper resting orders fill on) takes up to
`TAPE_RECORD_BATCH_MAX` prints per transaction off a queue of
`TAPE_RECORD_PENDING`. It **never latches**. A full backlog sheds the prints it
cannot hold (`backlog_full`) and a failed write loses that batch
(`write_failed`). Either way the loss is counted and stated, and the writer
takes prints again as soon as it can. `/api/l2/status` `tape.writer` is
`{error: string | null, pending, written, dropped, losing: boolean, losses:
[{cause: "backlog_full" | "write_failed", since, until: number | null,
dropped, symbols: string[], first_print_ts, last_print_ts, detail}]}`.
`losses` holds the newest `TAPE_RECORD_LOSS_KEEP` episodes, with `until: null`
while an episode is still open. `error` states an open episode or one that
ended within `TAPE_RECORD_LOSS_RECENT_SEC` (it also carries a shutdown that
timed out). `dropped` counts every print lost in this process. The Paper
matcher (and Sim at the live edge) reads resting orders' prints only as far as
the writer's written-through mark (`Sink.written_through`: every print
stamped earlier is written or counted lost), so a print the writer reaches late
is read next pass. `/api/diagnostics` adds the `tape_archive` row (group
`practice`, `evidence: {writer, resting, blind, unwatched, symbols}`):
`fail` while an order rests on a symbol whose prints are not reaching the
archive (the writer is losing prints now, the line prints with nothing
archived for over `TAPE_RECORD_STALE_SEC`, or the symbol is not archived),
`warn` on a recent loss or a blind symbol with nothing resting, `off` with
nothing archived. Before this fix, the first full backlog shed every print
until a restart. On 2026-09-24 that left every Paper resting order unfilled
from 07:29 ET: an APUS SELL limit at 4.96 sat while APUS printed 5.00.

## When IBKR data stops arriving (#672, #673, operator report 2026-10-01)

"There was a moment of lag, and that entire graph stopped working. Time and sales stopped ... This should
never happen." At the open the desk PC's Wi-Fi re-authenticated five times. Each time no IBKR data reached
Nova for 4, 4, 8, 16 and 4 s, while both loops stayed under 15 ms. The silences matched Windows' WLAN log
(11004 -> 11005) to the second. Nothing on the desk said why: the header read "STALE 0S" before and after.
Then everything IBKR held arrived in one burst, stamped on arrival (#563).

- **The heartbeat** (owner `ibkr/feed_pulse.py`, constants `constants_feed.py`). The L1, tick-by-tick and
  depth handlers call `note()`. A **gap** is a stretch with no market-data message on any line for at least
  `FEED_GAP_SEC` (3 s), after a busy stretch: data in at least 80% of the 10 whole seconds before it, not
  counting seconds inside an earlier gap. It must fall inside 04:00-20:00 ET of one exchange day, and an open
  gap also needs the Gateway session ready. A thin feed, the 20:00 close or a disconnect is never a gap.
  Gaps live in memory only.
- **`GET /api/ibkr/feed`** answers `{schema_version: 1, now, connected, in_session, last_data_ts, silent_sec,
  gap: Gap | null (open), recent: Gap[] (closed, newest first, at most FEED_GAP_KEEP), rule: {gap_sec,
  settle_sec, busy_window_sec, busy_fraction}}`. A **Gap** is `{start, end: number | null, silent_sec,
  ongoing, cause: "wifi" | null, wifi: {state: "read" | "pending" | "unknown" | "off", drops: [{stopped,
  back}]}, text}`. Times are epoch seconds, and `text` is the gap in plain words.
- **Wi-Fi** (owner `ibkr/wifi_drops.py`, read-only). Windows' WLAN AutoConfig log is read on a worker
  thread with `wevtutil`, never on a loop. Each 11004 "security stopped" pairs with the next 11005
  "succeeded". A drop that was down from 15 s before the silence to its end makes `cause: "wifi"`. A log that
  cannot be read is `unknown`, never "no drop"; off Windows it is `off`.
- **The desk** (`ibkr/feedPulse.ts`, `ibkr/feedPulseStore.ts`) reads the route once a second while it
  shows. The header chip reads **NO DATA 9s** (red) while a gap is open and **DATA GAP 16s** (amber) for 60 s
  after one closed, with `text` first on hover. Time & Sales' LIVE badge says the same. A replay desk leaves
  them out. The chip says **STALE** only when the newest scanner price is older than
  `SCANNER_PRICE_STALE_SEC`: an L1 subscription error with fresh prices (Error 101) is no longer
  "STALE 0s", and its words stay in the hover's scanner line.
- **The tape hold** (owner `setup_scanner/tape_gap.py`, pure). A live tape read reads `blind` with the gap as
  its reason when its window touches a gap. The gap runs from its last message to `FEED_GAP_SETTLE_SEC` (5 s)
  after the first one back. This covers the gate (`metrics.feed_gap`) and the flow reading (score `null`,
  `gap`, so no flush exit acts on a burst). A flow baseline starts again after a settled gap. The bot and
  Auto-entry skip such a trigger, and the skip line quotes the tape's first reason. Replays hand in no gaps.
- **`/api/diagnostics`** adds the `ibkr_feed_gaps` row (group `market_data`). It is `fail` while a gap is
  open, `warn` with the count and the longest in the last `FEED_DIAG_WINDOW_SEC` (30 min), naming Wi-Fi when
  Windows logged it, `off` while disconnected or outside the session, and otherwise `ok`.

## A Level 1 line IBKR refused (operator report 2026-10-05)

"Find out why 10 of the 50 after-hours rows never get a price." From 16:08 ET IBKR answered 176 Level 1
requests with Error 101 ("Max number of tickers has been reached") while Nova held 51-56 lines of its own: the
cap is the login's, and IBKR counts its other platforms against it (TWS and the API share it, per IBKR). ib_async 2.1.0 keeps a refused request
registered and hands it back to the next request for that contract, so the line stayed "subscribed" for good.
17 of the 50 After Hours rows had no price (INBS for 53 minutes), and Nova counted 76 of its 100 lines open.

- **A refused line is not open** (owner `ibkr/l1_refused.py`). Every Level 1 request id is kept with its symbol.
  Error 101 on a line's own id marks the line refused. It keeps its owners and handler (a Trader tab, the
  scanner, HOD Momo), but no longer counts as open, and is let go without a cancel (IBKR never opened it).
- **The cap Nova plans to.** The lines Nova held at the refusal become the cap (the fewest held within one
  burst of refusals). It rises by `IBKR_L1_CAP_RELAX_STEP` every `IBKR_L1_CAP_RELAX_SEC` without a refusal, and
  is forgotten at `IBKR_L1_STREAM_BUDGET`. The scanner plans within it, less the open lines no scanner or HOD
  owner holds (a Trader tab's own quote) and `IBKR_L1_STREAM_RESERVE`. Displayed rows come first and HOD Momo's
  other names get what is left, as before.
- **Asked for again.** The scanner's reconcile re-requests a refused line in place once its wait
  (`IBKR_L1_REFUSED_RETRY_SEC`: 15, 30, 60, then 120 s for refusals in a row within
  `IBKR_L1_REFUSED_RESET_SEC`) is over, and only while Nova holds fewer lines than the cap. A Trader tab's line
  goes first, then the displayed rows, then HOD Momo's.
- **On the wire.** `/api/ibkr/status`:
  - `reqMktData_lines` counts the open lines only;
  - adds `reqMktData_refused` (integer) and `reqMktData_cap` (`integer | null`, null while none is learned);
  - `reqMktData_remaining` is measured against the cap.

  The scanner subscription state (on `/ws/scanner` price patches) adds `refused: string[]` and
  `line_cap: integer | null`, and its `error` names the refused symbols. The desk shows that error in the
  header's scanner hover. The `market_data_lines` diagnostics row warns while any line is refused.

## When one tape line goes silent (#722, operator report 2026-10-05)

"time and sale is fully frozen". At 09:35:42 ET the AllLast lines of SAIQ (a Trader tab) and VEEA (a Session
Record) stopped together while both books kept updating, with no IBKR error and no farm notice. SAIQ's Time &
Sales sat on its last print under LIVE until about 09:42; its socket's only frame was the idle `ping`. Level 1
kept arriving, so this is not a feed gap (above).

- **What the record shows (2026-10-09).** The lines were dead, not quiet. In `archive.db` the same stocks'
  Level 1 lines (`l1_ticks`: RTVolume 233 day volume, else tick 8) kept counting while the tape
  (`tape_ibkr`, and VEEA's Session Record) had no print: SAIQ 1,381 volume updates, +2,496,982 shares in the
  332 s to its next print at 09:41:14.184; VEEA 1,645 updates, +1,050,187 shares in the 574 s to 09:45:16.291.
  When the lines print, tape shares and Level 1 volume agree within 1-3%. Both last prints carry the same
  arrival, 09:35:42.388; the IB loop's delay stayed under 40 ms and Level 1 and depth handlers ran throughout,
  so the prints never reached Nova. VEEA's asks at 09:37:34 and 09:39:54 brought nothing back, even after
  SAIQ's original line recovered by itself at 09:41:14; VEEA's came back at 09:45:16, seconds after a new ask
  (the perf record's tape subscribes fall in the 5 s samples ending 09:45:13 and 09:45:18).
- **The reading** (owner `ibkr/tape_silence.py`, memory only): `{schema_version: 2, state: "halted" | "dead"
  | "silent" | "quiet", since, last_print_ts, book_at, l1_trade_ts, halted, pipeline, notice, text}` or
  `null` while the line prints.
  - The facts are the line's last print, its IBKR second and the line's opening
    (`tape_recording.producer_status`: `last_print_ts`, `last_print_exchange_ts`, `line_since`), when its
    Level 2 line last delivered a book (`ibkr/depth/state.last_book_at`), `halt_status.halted_now`, and the
    symbol's Level 1 trade clock (`l1_trade_ts`: the newest of IBKR's Last Timestamp, tick 45, and RTVolume's
    trade time, 233; ib_async writes AllLast prints into `ticker.last` but never into these).
  - `halted`: a halt prints nothing, so it is never read as a dead line.
  - `dead`: no print for `TAPE_SILENT_SEC` (30) while Level 1 reported a trade at least
    `TAPE_DEAD_L1_LEAD_SEC` (3) after the last print by IBKR's second (or after the line's opening or the
    reopening, on the desk's clock): the tape missed trades.
  - `quiet`: Level 1, updating within `TAPE_SILENT_BOOK_FRESH_SEC`, reports no trade since either; or, with
    no Level 1 trade clock, the book is quiet too or there is no Level 2 line.
  - `silent`: no Level 1 trade clock can tell, and a book came within `TAPE_SILENT_BOOK_FRESH_SEC` (10): the
    line may be down.
  - `pipeline` (dead or silent only, else `[]`): the other live tape lines whose last print arrived within
    `TAPE_PIPELINE_SAME_SEC` (1) of this one's and that have printed nothing since, halted ones left out --
    one tick-by-tick event, not this line alone. `notice` (dead or silent only, else `null`): the newest farm
    or line notice that something stopped, from `IBKR_NOTICE_NEAR_SILENCE_SEC` before the silence began
    (`{ts, code, notice, farm, farm_type, message, symbol}`, below).
  - The silence counts from the newest of the last print, the line's opening and the last ping that found the
    symbol halted. Nothing here asks IBKR for anything. A line that turns dead or silent is logged once per
    silence and written to the perf day file as `{schema_version: 1, kind: "tape_silence", ts, symbol,
    reading}` (`architecture/schema/performance.md`).
- **The wire.** Each idle `ping` on `/ws/ibkr/tape/{symbol}` (every `TAPE_STREAM_HEARTBEAT_SEC` without a
  print) carries `silence: reading | null` on a live line, and `null` on a replay desk.
- **The desk** (`ibkr/tapeSilence.ts`). The badge reads LINE DOWN 47s (red) for `dead`, SILENT 47s or HALTED
  (amber), or QUIET 47s (grey), counting on the desk's clock, with the backend's words on hover. For the
  first three, a short line above the rows says why. Any print clears it, and NO DATA on every line (#672)
  comes first.
- **A recording's line** (`capture/tape_watch.py`, `architecture/schema/recording-and-replay.md`) uses the
  same witness: Level 1 trades after the last print make it dead, Level 1 updating with no trade since makes
  it quiet (no ask), and a line silent in the same second as others is held, not asked for, until one of them
  prints again (`CAPTURE_TAPE_PIPELINE_HOLD_MAX_SEC` at most), then asked for if still dead. The Trader's own
  line is only read, never asked for again, here.
- **IBKR's farm and line notices** (owner `ibkr/farm_notices.py`, via `session_errors`): farm broken 2103 /
  2105 / 2157, OK 2104 / 2106 / 2158, inactive 2107 / 2108 (the farm is the text after the last colon, or
  after "upon demand." for the inactive pair), depth halted 316 and competing live session 10197 are each
  kept as `{ts, code, notice: "broken" | "ok" | "inactive" | "depth_halted" | "competing_session", farm,
  farm_type, message, req_id, symbol}`, the last `IBKR_NOTICES_KEEP` in memory, logged (WARNING when
  something stopped) and written to the perf day file as `kind: "ib_notice"`. Record and display only: a
  notice never disconnects, reconnects or restarts the Gateway, which would also tear down the order channel.
  `/api/diagnostics` adds the `market_data_farms` row (group `market_data`): `warn` while a farm reads broken,
  or for `IBKR_NOTICES_DIAG_WINDOW_SEC` after a 316 or 10197; `ok` with the last notice named otherwise; its
  evidence is `{farms, recent}`.
- **Not done here:** bringing a silent Trader line back. Asks inside the event did nothing; whether a Gateway
  reconnect would have is still unknown, and a reconnect also drops the order channel.

## The trading session ends at 20:00 ET (operator report, 2026-10-01 23:33)

"How come these things are getting triggered right now? ... the entire market is closed, no?" -- the Bots
page showed OM's first pullback and flat top forming ("new high 4.20 on a 12% leg"), NAMM's bull-flag pole and
RIBBU / XRPNU "pushing HOD". After the 20:00 close IBKR keeps the same SMART Level 1 lines moving with its
overnight session (20:00-03:50 ET, its OVERNIGHT venue; IBKR dates those trades to the next trading day): the
last moves while IBKR's own day volume and day high stand still (XRPN printed 27.49 over a 23.99 day high).
Nova made each of those prints a one-minute candle and a HOD Momo trade (78 HOD Momo alerts after 20:00), and
the setup scanner's day ran to midnight with no close: OM's leg was one 200-share print at 20:48, RIBBU's a
15:52 move nothing had ended, and after midnight the same prints began the next day (red to green read a 23:59
print as "the 09:30 open" and armed SDEV at 00:12).

- **One rule** (`market.trading_session_bounds` / `in_trading_session`, pure): Nova's trading session is
  04:00-20:00 ET on an exchange day (a weekday that is not an NYSE holiday; half-days are not modelled).
- **Candles.** `ibkr/l1_minute` makes a minute only from a last inside the session; outside it a last opens no
  bucket, reaches no listener and drops the volume baseline, so the next session's first print is a baseline.
  The `ibkr_l1` minutes already stored between 20:00 and 04:00 stay in `bars_intraday`.
- **HOD Momo, its L1 tick archive and volume boost** take only trades inside the session (`ibkr/l1_apply`,
  beside #541's prior-close rule). The rows' price patch still carries the line's last.
- **The setup scanner's day is the session** (`setup_scanner/engine.py`). A minute or price outside it is not
  read; the seed reads 04:00-19:59 (`hooks.default_seed`: the newest 960 rows had let overnight minutes push a
  busy morning out). From 20:00 every lane ends its day on each tick: a setup still forming goes back to
  `watching` and an armed or near one is disarmed, its open proposal withdrawn, with the reason
  `SETUPS_SESSION_CLOSED_REASON` ("the session closed at 20:00 -- the scanners start again at 04:00"),
  journalled, so the playback and the past setups end it there too. A restart after the close replays the day
  and ends it the same way.

## Chart bars say when IBKR history stopped answering (ADR 012, #555)

`GET /api/ticker/{symbol}/bars` on the IBKR store-first path (not a Sim replay, not Alpaca) and every `bars_patch` frame on `/ws/ticker/{symbol}` carry, in `coverage` beside `filling`, `last_error: string | null` and `last_error_ts: number | null` (epoch seconds): the backend's reason and time for the last historical fetch of that (symbol, timeframe) that IBKR did not answer -- a timeout (504) or an error answer / failed qualify (502), never a Gateway-down 503 or a 400 / 404. Both are `null` when there is none; a success clears the pair at once, and a failure nobody has asked about again is forgotten after `IBKR_HISTORICAL_FAILURE_MEMORY_SEC` (owner `ibkr/historical_failures.py`, in memory only, never stored in `bars_coverage`). A failed pair is not sent to IBKR again, for any priority, for `IBKR_HISTORICAL_FAILURE_BACKOFF_SEC`: the request is shed and the pane's own retry asks again, so a farm outage stops spending the 60 / 10 min budget. A pane with no bars that is filling with `last_error` set reads "IBKR history did not answer — retrying" with the reason, not "Loading IBKR historical…"; a painted pane's header hint says the same.

**A crashed pane says why** (operator report, 2026-09-25: "Chart unavailable. The scanner is still running."). A chart pane that crashes (`components/TickerChartErrorBoundary.tsx`) shows the error's own words under that line and reports its timeframe (`source: "ticker-chart:1Min"`). It draws itself again once, after `CHART_CRASH_AUTO_RETRY_MS`; a second crash within `CHART_CRASH_AUTO_RETRY_WINDOW_MS` stays down. Its Retry button now takes the click. It had inherited the overlay's `pointer-events: none`, which passes clicks through to the chart, so it could never be pressed.

## The forming candle's volume (operator report, 2026-09-24)

"i do not see a volume coming up": a chart pane draws its forming candle from
`/ws/ticker/{symbol}` `trade_update` frames, which carry a price and the day's
running volume (`volume`: IBKR's RTVolume total, else tick 8) but no bar. The
bar store refreshes from IBKR history at most every
`IBKR_BARS_STORE_FRESH_INTRADAY_SEC` (the pane asks every `CHART_REFETCH_SEC`),
so the forming bar's volume used to appear only after the bar closed. Minute
and hour panes now count it on the desk (`chart/liveTradeApply.ts`): a bar's
volume is what the day volume grew by between its first update and its last.
The first day volume a pane sees is a baseline, so the bar it joined mid-way
has no live count -- the store's figure, or nothing, never a partial one. A
total that goes down restarts the baseline and leaves that bar unknown. Updates
arrive on price changes, so shares traded at an unchanged price just before a
bar closes count in the next bar; the store's bar replaces a closed bar's figure
when it lands, and a forming bar shows the larger of the two counts. 10Sec
volume stays the tape's own prints and daily volume the store's. No wire field
changed. A store refresh no longer rebuilds the forming candle from the last
trade (which flattened its open, high and low to one price every 30 s): the
live tip is put back on top, merged with the store's bar for the same minute.

