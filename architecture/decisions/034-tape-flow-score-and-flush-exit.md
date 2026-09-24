# ADR 034 -- The tape flow score, and a flush exit a template can choose

**Status:** Accepted · **Date:** 2026-09-24
**Builds on:** [[022-setup-scanner-tape-gate]] (the tape gate) · [[029-setup-templates-eyes-journal]] (templates, lanes, replayed eyes, backtests) · [[030-first-pullback-bot-on-paper]] (Nova's bot) · [[031-a-scanner-for-every-setup]]
**Decided by:** the operator, 2026-09-24 -- a Time & Sales screenshot of a GLND flush: "can my bots
detect if we are seeing flush like this so we can exit a position or burst of greens where we can
enter ... just a ~small piece of the final decision"; then "build the flush-exit test ... we probably
going to have to fine tune the SHIT out of this, + 2 [a weighted score instead of a hard gate] ...
we need hybrid creative solution and mixing it in the strategies". The design below is the agent's,
under the operator's standing grant for routine calls; each item has the operator's veto.

## Context

- The tape gate (ADR 022) read the tape only at a trigger, and only as counts: at least three prints
  at the ask and more shares there than at the bid is `go`; twice as many shares at the bid is a
  "burst of red" and `wait`. The bot enters on `go` only. A pass / fail of two print counts, not a
  small piece of a decision.
- Nothing read the tape once a trade was on. Nova's bot exits on its target, a print at the stop, or
  a 15-minute time stop; the scoring exit on the bars. A flush like the screenshot did nothing
  until the price reached the stop.
- Session Records carry every print stamped `ask` / `bid` / `between` against the recorded book, and
  the recorded books -- the data a tape rule can be measured on. Fifteen usable recordings on
  2026-09-24 (four days), 65,774 recorded seconds.

## Decision

1. **One score for who is winning the tape** (`setup_scanner/tape_flow.py`, pure): four readings over
   the last `window_sec`, each from -1 to +1 -- *imbalance* (shares at the ask minus at the bid,
   lit prints only), *pace* (the tape's speed against its own last `baseline_sec`, signed by the
   imbalance), *drift* (the price move, full at `drift_full`), *book* (bid minus ask depth in the top
   `book_levels` prices) -- and their weighted mean. A reading Nova cannot take drops out of the
   mean and is `None`, never 0; the baseline never counts time before the feed could see the tape
   (`history_from`). Labels `burst` / `flush` / `neutral` / `quiet` (too little tape) / `blind` (no
   tape, no book). One rule, summed two ways: over a list of prints (the live lanes) and by prefix
   sums over a whole recording (`FlowIndex`, the replays and the study); a test holds them equal.
2. **Every number is a template parameter** (the catalogue's new *Tape flow* group, on every setup
   with a scanner). The defaults are the pre-registered rules: the entry reads the gate's prints,
   and a flush does nothing.
3. **Entry: the score can be a piece of the decision** (`tape_entry`): `gate` (the rule above), `score`
   (the vetoes and a seller that is not thinning still hold; the flow score at or over
   `flow_entry_min` replaces the print counts), or `both`. The verdict stays go / wait / veto /
   blind, so the bot, the proposals and the read-out read it as before; every tape read carries
   `flow`.
4. **Exit: a flush can act on a trade on** (`flush_exit`): `off`, `tighten` (the stop moves up to
   `flush_trail_r` R under the price -- never down), or `exit` (out at the bid), counting a flush
   only `flush_hold_sec` after the entry and, with `flush_min_r`, only while the trade is up that
   much. One rule (`tape_flow.flush_action`) for the scoring exit (`ScoreTracker.on_flow`, exits
   named `flush` / `flush_runner` / `flush_stop` / `flush_stop_runner`) and for Nova's bot
   (`bot/first_pullback/flush.py`, exit reason `flush`), so a template in play trades the way it is
   scored. Every lane reads each trade's flow for its scoring window; the live engine keeps the
   tape of a symbol with a trade on, and the scanner's newest reading is what the bot acts on (a
   reading older than 5 s is not).
5. **Measure before trusting it.** `eyes/flow_study.py` (`tools/flow_study.py`) reads every recorded
   second through the score and measures where the mid went 10 s to 5 min later, after every burst
   and flush onset, by the minute before it, and by score bucket, with a grid that ranks parameter
   combinations; backtests take **variants** -- templates made for one run, never stored
   (`tools/eyes_backtest.py sweep`) -- and pair each variant's R with the base on the same setups.
   The scoreboard splits by `flow_at_trigger`, and the eyes' journal records every turn into or out
   of a burst or a flush after a trigger (`flow`) and what a flush did (`flush`). `/sensors/flow`
   carries the score for agents.

## What the recordings said (2026-09-24, default numbers)

- Flush onsets (441): the mid fell 21 bp in the next 10 s (t -3.4) and 22 bp by a minute. Burst
  onsets (420): +13 bp in 10 s. The median spread at an onset was 48 bp: as an entry signal alone
  the move does not pay for crossing the spread.
- A flush **after a rise** (157) was followed by -40 bp in 10 s and -43 bp by a minute -- the case a
  flush exit is for. A burst after a rise kept going (+58 bp by a minute); a burst from a flat
  minute faded (-32 bp). Context matters more than the score alone.
- Tuning overfits at this size: ranking 54 combinations on seven recordings and checking the top on
  the other eight, the training winner came seventh of eight; the defaults ranked first on the
  unseen half. The flush-after-rise effect held in both halves, with a size that swings by day.
- Only two first-pullback trades triggered on the recordings (both improved with a flush exit,
  +0.5R tighten, +0.8R exit): mechanics, not evidence.

## Consequences

- Nothing changes until a template chooses it: the defaults are the pre-registered rules, the
  default template's rows and read-out are untouched, and the bot follows only the template in play
  (on Paper and Sim; Live still waits on the read-out).
- A flush-exit template collects live evidence beside the default on the same days (every template
  is watched at once), and each week's recordings widen the study.
- The live lanes read a two-minute tape history for symbols near a trigger or with a trade on; the
  sensor ring keeps 4,000 prints a symbol.
