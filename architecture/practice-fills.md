# Practice fills on a replayed session

How the Sim venue decides that a practice order filled, and what that fill does
and does not claim. Rules live in `backend/sim/fill_model.py` (pure) and are
pinned by `backend/tests/test_sim_fill_model.py`; the market they read comes
from `backend/sim/practice.py`. ADR 019 is the decision.

**Every practice fill is an estimate.** A replay has no order queue, and a
historical download carries trade prints with no bid/ask, so a fill is inferred
rather than observed. Each filled row carries `fill_estimated: true` and a
`fill_basis` naming the rule that produced it. Recorded prints in Time & Sales
are untouched facts; a practice fill is not one and must never be displayed as
one.

## What the desk can trade

Only the loaded replay's symbol, and only once it has printed at the playhead.
Everything else is refused with a reason code:

| Code | Meaning |
|---|---|
| `SIM_NO_REPLAY` | No recording or historical window is loaded. |
| `SIM_SYMBOL_MISMATCH` | The order names a symbol other than the loaded replay's. |
| `SIM_NO_TRADES` | The historical window holds candles only; its trades were never downloaded. |
| `SIM_NO_PRICE` | The replay has not printed yet at the playhead, or the playhead sits in a recording gap or an undownloaded stretch. |
| `SIM_ORDER_TYPE` | Practice supports `MKT`, `LMT` and `STP` only. |

## Paper: the live reference (ADR 020)

On the Paper venue the practice broker trades the **live tape**: any symbol
with a live print is admitted (`PRACTICE_NO_LIVE_PRINT` otherwise -- never a
guess), `last` is the L1 last when it traded within `PRACTICE_LIVE_FRESH_SEC`
(15 s, by IBKR's Last Timestamp -- a quote change keeps a line fresh but is
not a trade, and a line with no trade today carries IBKR's prior close, which
is never a price; #541), else the newest tape print that sets a price inside
the same window, and `bid` / `ask` the live top of book (Nova's own book,
kept with IBKR's row rules; #540). Fills follow the same rules
below with `fill_basis` `live_quote` (a quote was present) or `live_print`
(last print only); resting orders fill on live tape prints that set a price
and arrive after they were placed, which needs the symbol's tape line open --
the practice broker holds one while an order rests. The venue never changes the bot -- gating is identical on Paper,
Live and Sim. Fees and buying power: `architecture/practice-account.md`.

## The live edge (ADR 020 amendment, operator decision 2026-09-21 evening)

Sim is the time machine: at *now* it is live, dragging back is replay. The
Sim clock's `live_edge` is true while the playhead follows the wall clock on
today's Eastern date inside the session window -- not paused, not scrubbed,
no past-day replay loaded -- and it is the single truth for what a Sim tab
shows and fills against (`GET /api/sim/clock`, `/api/ibkr/status` on Sim).

- **At the edge** a Sim tab shows the live IBKR feed exactly as a Paper tab
  does (quote, Level 2, Time & Sales, live bars) and holds a real depth line
  the way a Trader tab does, so bots gate identically (`BOT_NO_DEPTH_LINE`).
  The Sim broker's market is Paper's live reference: any symbol with a live
  print is admitted (`PRACTICE_NO_LIVE_PRINT` otherwise -- never a guess),
  `last` is the fresh L1 last or newest tape print that sets a price, `bid` /
  `ask` the live top
  of book, `fill_basis` `live_quote` / `live_print` at placement, and resting
  orders fill on live tape prints through the live matcher as `print_cross` /
  `stop_trigger`. `SIM_NO_REPLAY` and `SIM_SYMBOL_MISMATCH` do not apply at
  the edge. The `MKT_OUTSIDE_RTH` clock is wall time there.
- **Off the edge** -- scrubbed, paused, or a past day loaded -- everything is
  the loaded replay under the rules above and below, and with nothing loaded
  the desk is a stated absence. Scrubbing or pausing off the edge with
  nothing loaded selects the tab symbol's usable Session Record for today
  when one exists, keeping the playhead where the operator put it and keeping
  the scratch account, because that recording is the tape the account already
  traded. "Follow wall clock" returns to the edge.
- **The scratch account is unchanged.** An order placed at the edge is stamped
  with the playhead (wall time there) and unwinds like any other when the
  operator scrubs back past it; bots get `practice_rewind`. Paper stays the
  persistent ledger; nothing at the edge writes to it.
- **Still an estimate.** A live NBBO is a better reference than a replay
  quote, but there is no queue: every biased rule in this document applies
  and every fill carries `fill_estimated: true`.

Owner: `backend/sim/session_clock.py` (`live_edge`), `backend/sim/mode.py`
(`is_replay_desk`, the gate every market read keys on),
`backend/practice/reference.py` (`SimReference`), `backend/sim/live_edge.py`
(leaving the edge selects today's recording).

## The market at the playhead

`practice.reference(symbol)` returns `last`, `bid` and `ask`, any of which may
be unknown:

- **Recorded capture** — `bid`/`ask` come from the recorded quote at the
  playhead (the recorder's quote rows carry the top of book with `last: null`,
  and load as quotes), `last` from the last recorded print that sets a price
  (see below). Every read stays inside the recorded stretch that
  holds the playhead (the manifest's segments, the open one, and data written
  past the last segment): **in a gap nothing was recorded, so there is no
  quote, no book and no last** -- a practice order is refused `SIM_NO_PRICE`
  ("not recorded at the replay playhead"), and the Level 2 pushed for that
  moment is an explicit empty book, never the one from before the gap. A
  capture whose manifest names no segment cannot say where the recorder was up
  and reads unbounded, as before.
- **Historical download** — `last` only. IBKR historical trades carry no
  bid/ask (see #311), so spread-aware fills are not available on this source.
  **A stretch the download has not covered has no last** (QA R34): the
  snapshot prices an uncovered playhead from a 1-minute candle close so the
  chart can draw, but that close is never a practice price -- an order there is
  refused `SIM_NO_PRICE` ("not downloaded at the replay playhead"), and a
  protective close gets flat at the last known mark (`last_mark`), exactly as
  a capture gap does.

## The rules

| Situation | Fills at | `fill_basis` |
|---|---|---|
| `MKT`, quote recorded | the far side (`ask` to buy, `bid` to sell) | `quote` |
| `MKT`, no quote | the last print | `last_print` |
| `LMT` marketable on arrival | the touch, never worse than the limit | `quote` / `last_print` |
| `LMT` resting, a later print reaches the limit | the limit | `print_cross` |
| `STP` already through the market on arrival | the touch | `stop_trigger` |
| `STP` resting, a later print crosses the stop | that print | `stop_trigger` |
| Protective close with the replay unloaded, or in a gap / undownloaded stretch | the last known mark | `last_mark` |

A resting order only ever fills on prints **after** it was placed, so scrubbing
backwards can never fill it, and moving the playhead forward fills it at the
first crossing print in between -- **paused or playing**: the Sim feed streams
nothing while paused, but it still matches (and expires `DAY` orders) across a
stretch the operator scrubbed over.

**Only prints that set a price fill anything or set a last** -- on every
venue and source, the rule every candle already follows
(`backend/sale_conditions.py`, codes in `constants_tape.py`). Some trades are
reported for volume only: odd lots (`I`), average-price (`W`), derivatively
priced (`4`), prior reference (`P`) and the rest of
`TAPE_NO_PRICE_CONDITIONS`, or any print IBKR flags `unreported`. Their price
can sit dollars from the market -- on 2026-09-23 PLTR printed FINRA
`190.38 x 100  4 W` against a 192.64 x 192.80 book -- so a resting buy limit at
191 must not fill on it. Time & Sales still shows them. The live tape archive
(`l2.db` `tape_trades`) keeps each print's `conditions` and IBKR's
`unreported` flag for this; a row stored before the flag was kept is judged by
its conditions. A historical download's `unreported` prints are excluded the
same way.

**Resting live fills read the archive, and the archive says when it lost
prints** (2026-09-24). On Paper, and on Sim at the live edge, the matcher
(`practice/matcher.py`) reads resting orders' prints from that archive once a
second. Its own thread writes the archive (`ibkr/tape_sink.py`), one
transaction per batch, so a pass reads only as far as the archive's
written-through mark: every print stamped before it has been written or
counted lost. A print written late is read on the next pass, not skipped. A
writer that cannot keep up sheds prints and says so: a loss episode with cause,
window, count and symbols goes to the log, to `/api/l2/status` `tape.writer`,
and to the `tape_archive` diagnostics row. It takes prints again as soon as it
has room, and a resting order fills on the next print that crosses it. Before
this fix, one full backlog stopped the writer until a restart. On 2026-09-24 an
overflow at 07:29 ET left every Paper resting order unfilled for the rest of
the morning: a SELL limit at 4.96 sat while APUS printed 5.00.

## Brackets (#606 step 1)

Paper and Sim take the bracket Live sends, so Paper rehearses the order Live
places. Live sends IBKR's bracket (`ibkr/orders.place_bracket_order`, ib_async
`bracketOrder`): a `LMT` entry, a take-profit `LMT` and a stop-loss `STP` on
the reverse side, one quantity, TIF and outside-RTH flag on all three, three
consecutive order ids, the exits carrying `parentId`. IBKR holds the exits
until the entry fills and treats them as one-cancels-other. The practice broker
(`PracticeBroker.place_bracket`, rules in `backend/practice/bracket.py`) takes
the same shape:

- **Rows.** Three consecutive ids, entry first. Every practice row carries
  `parent_id` / `oca_group` / `leg_role`: the entry `null` / `null` /
  `parent`, each exit the entry's id / `oca-<entry id>` / `target` or `stop`,
  a plain order `null` all three. The exits copy the entry's quantity, TIF,
  `expires_ts`, attribution and placement stamps.
- **Admission is the entry's.** The entry passes a place's gates in the
  execution door's order: shape (`BRACKET_GEOMETRY`, `QTY_INVALID`), TIF
  (`TIF_INVALID`), the venue's admission (`SIM_*` / `PRACTICE_NO_LIVE_PRINT`),
  no shorts -- a SELL entry is a short bracket and is refused
  `PRACTICE_NO_SHORTS` -- and buying power at the entry limit
  (`PRACTICE_BUYING_POWER`). The exits never pass a place's gates: its
  no-shorts rule would refuse a SELL before anything is held.
- **The exits wait.** They rest `PreSubmitted` (the blotter reads "Pending",
  as it does for IBKR's own held children) until the entry fills. The ledger
  wakes them when it applies the entry's `filled` event: `Submitted`, placed at
  the fill time. A resting order only fills on prints after it was placed, so
  **the print that fills the entry never fills an exit**, nor does another
  print in the same second. A waiting exit never fills by any path. Waking is
  derived from the ledger, not an event of its own, so a Sim scrub back before
  the entry's fill puts the exits back to waiting, and a Paper file written
  before brackets loads unchanged (no new event type, no schema change).
- **One-cancels-other.** One exit filling cancels the other, at the same
  moment: `Cancelled`, `PRACTICE_OCO_CANCELLED`, "One-cancels-other: the
  target filled" (or "the stop filled").
- **The entry takes its exits.** An entry that closes unfilled -- cancelled by
  the operator, refused by the venue at the fill (`order_rules.fill_refusal`),
  or expired -- cancels the exits waiting on it: `Cancelled`,
  `PRACTICE_PARENT_CANCELLED`, "its entry was cancelled" (or "its entry
  expired at the session close"). Both closures are ordinary `cancelled` ledger
  events stamped with the venue as their source, so a rewind before one
  restores the order it closed.
- **Cancel.** Cancelling the entry cancels its waiting exits; cancelling one
  exit cancels only that exit. Cancelling a leg its bracket already closed
  answers `ok: true`, `verified_gone: true`, `closed_by: <code>` -- KILL, the
  account flatten and cancel-all cancel a list of working orders one by one and
  must not report a failure for a leg the entry's cancel took along. A plain
  order, or a leg that filled, still answers "not open".
- **Replace.** An exit can be repriced and keeps its bracket fields. A waiting
  exit keeps waiting whatever its new price, even a marketable one.
- **Expiry.** A `DAY` bracket's legs share the entry's session close. An entry
  that expires unfilled takes its waiting exits along; exits that are working
  (the entry filled) expire on their own at the same close. `GTC` never expires.
- **Fill bases.** The entry fills like any `LMT` (`quote` / `last_print` /
  `live_quote` / `live_print` when marketable on arrival, `print_cross` when
  it rests); the target like a resting `LMT` (`print_cross`, at its limit); the
  stop like a resting `STP` (`stop_trigger`, at the triggering print). No
  partial fills: every leg fills whole, so IBKR's reduce-the-rest behaviour of
  an OCA group after a partial fill has nothing to act on.
- **The send** (`sim/execution.py`) creates Live's three watches -- the entry's
  counts toward the execution's fills, the exits' never do -- answers on the
  entry's watch (the next section), and writes `order_id` (the entry),
  `parent_order_id`, `target_order_id` and `stop_order_id` on the execution
  row and the receipt. An entry the venue cancels at the fill is a refusal in
  the venue's words, naming its ids.
- **The ticket's Flatten** (`execution/flatten_intent.py`) counts a bracket's
  two exits once, and exits still waiting on a working entry not at all: they
  sell what the entry has not bought yet.

**Stops before 09:30: Paper protects where Live would not.** A practice `STP`
triggers on any price-setting print, premarket included, and so does a
bracket's stop leg. IBKR holds a plain stop until 09:30 even with
`outsideRth`, so before the open a Live bracket's stop does not protect the
position while Paper's does. Nova keeps the practice behaviour for now; whether
Paper should hold the stop leg the way IBKR does is an open operator question
on #604 / #606 step 2.

## The venue's answer is the acknowledgment (operator report, 2026-09-24)

A Live order's reply waits for IBKR's first status -- a real round trip
through IB Gateway, 40 ms to about 1 s on the desk's record. The practice
broker answers inside the send, so that answer is the acknowledgment:
`practice/watch.note_answer` records it (`Submitted` for a resting order,
`Filled` for a fill at placement) on the execution's own watch, stamped when
the send reads it, and the reply leaves at once. Nothing waits and nothing is
delayed to look like IBKR. An order the venue cancels at the fill
(`order_rules.fill_refusal`) is a refusal in the venue's own words and code,
naming its order id -- never an order reported placed.

Before this, the broker's notice of a fill at placement reached a watch the
send then replaced, and a resting order sent no notice at all, so the
execution door's acknowledgment wait ran out its full `EXECUTION_ACK_WAIT_SEC`:
on 2026-09-24, 21 of 23 Paper orders answered in 5.1 s while their fills
landed in under 150 ms, and the ticket read "Placing..." the whole time. A
price replace waited the same 5 s. `py -3 tools/order_timing.py` prints each
order's stages from the running backend.

## Market orders need regular hours (operator decision, 2026-09-21)

A `MKT` from a non-protective source is refused `MKT_OUTSIDE_RTH` -- "use a
limit at the ask" -- whenever the venue's clock is outside weekday
09:30-16:00 ET (NYSE holidays excluded). The clock is the venue's: the wall
clock on Paper, the replay playhead on Sim, so a replayed 10:00 is regular
hours at any wall time. The rule mirrors the venues Nova imitates: no US
exchange accepts an unpriced order in an extended session, and IBKR holds an
RTH-only market order until the next open (Warning 399) while ignoring the
extended-hours flag on it (Warning 2109). Filling such an order instantly at
the far quote, as the practice broker did before, taught a habit Live refuses
(GRML at 8.86 after the close, a 3.6% spread). Protective closes (`flatten`,
`kill`, `cancel_working`) are exempt so a practice position can always get
flat; `STP` orders are unchanged (they trigger only on prints). Owner:
`backend/execution/session_gate.py`; the broker repeats the check in
`practice/order_rules.py`.

## Known biases

These are deliberate simplifications. Read a practice result with them in mind:

1. **No queue.** A resting limit fills when a print merely *touches* it, as if
   the order were first in line at that price. Real fills often do not happen.
2. **No size limit.** Full quantity fills on one print regardless of that
   print's size.
3. **No partial fills.** An order is working or filled, never part-filled.
4. **No slippage model** beyond the touch price. Commissions and regulatory
   fees are charged as `architecture/practice-account.md` describes.
5. **Stops do not model gap risk** beyond the triggering print's price.

## What is out of scope

Practice orders never reach a broker: `backend/practice/broker.py` fills them
(ADR 020). The Paper ledger is persistent (`practice-paper.json`, owner
`practice/ledger.py`, reset archives it); the Sim ledger is a scratch account
that unwinds on rewind and clears when the replay unloads. The venue is
durable (ADR 018); arming never survives a process start.

## Related

- `architecture/decisions/019-practice-fills-on-replayed-sessions.md`
- `architecture/decisions/017-single-replay-surface.md`
- `architecture/historical-replay.md` · `docs/sim-mode.md`
