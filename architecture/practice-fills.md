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

## The live edge

When the Sim clock follows the wall clock on today's date (`live_edge` on the
clock payload -- not scrubbed, not paused, no past day loaded), the practice
desk trades the **live tape**, not a replay: any symbol with a live print is
admitted, `last` is the live tape's last print and `bid` / `ask` the live top
of book. Fills follow the same rules below with `fill_basis` `live_quote` (a
quote was present) or `live_print` (last print only), and resting orders fill
on live prints that arrive after they were placed. Scrubbing or pausing leaves
the edge: from then on the desk is the replay again. The venue never changes
the bot -- gating is identical on Paper, Live and Sim (ADR 019 amendment).

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
