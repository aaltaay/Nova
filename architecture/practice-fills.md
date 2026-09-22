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
| `SIM_NO_PRICE` | The replay has not printed yet at the playhead. |
| `SIM_ORDER_TYPE` | Practice supports `MKT`, `LMT` and `STP` only. |

## Paper: the live reference (ADR 020)

On the Paper venue the practice broker trades the **live tape**: any symbol
with a live print is admitted (`PRACTICE_NO_LIVE_PRINT` otherwise -- never a
guess), `last` is the fresh L1 last or the newest tape print, and `bid` / `ask`
the live top of book. Fills follow the same rules below with `fill_basis`
`live_quote` (a quote was present) or `live_print` (last print only); resting
orders fill on live tape prints that arrive after they were placed, which
needs the symbol's tape line open -- the practice broker holds one while an
order rests. The venue never changes the bot -- gating is identical on Paper,
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
  `last` is the fresh L1 last or newest tape print, `bid` / `ask` the live top
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
  playhead, `last` from the last recorded print.
- **Historical download** — `last` only. IBKR historical trades carry no
  bid/ask (see #311), so spread-aware fills are not available on this source.

## The rules

| Situation | Fills at | `fill_basis` |
|---|---|---|
| `MKT`, quote recorded | the far side (`ask` to buy, `bid` to sell) | `quote` |
| `MKT`, no quote | the last print | `last_print` |
| `LMT` marketable on arrival | the touch, never worse than the limit | `quote` / `last_print` |
| `LMT` resting, a later print reaches the limit | the limit | `print_cross` |
| `STP` already through the market on arrival | the touch | `stop_trigger` |
| `STP` resting, a later print crosses the stop | that print | `stop_trigger` |
| Protective close with the replay unloaded | the last known mark | `last_mark` |

A resting order only ever fills on prints **after** it was placed, so scrubbing
backwards can never fill it, and moving the playhead forward fills it at the
first crossing print in between. Unreported prints (odd-lot / Form T) never
fill anything, matching their exclusion from candles, last and volume.

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
4. **No slippage model** beyond the touch price, and no commission.
5. **Stops do not model gap risk** beyond the triggering print's price.

## What is out of scope

Brackets and OCO are not available on the practice desk — `bracket` is refused
with `SIM_NO_BRACKET`. Practice orders never reach a broker: they are filled by
`backend/sim/broker.py` in an in-memory ledger that a restart clears. The venue
itself is durable (ADR 018); the ledger and the arming are not.

## Related

- `architecture/decisions/019-practice-fills-on-replayed-sessions.md`
- `architecture/decisions/017-single-replay-surface.md`
- `architecture/historical-replay.md` · `docs/sim-mode.md`
