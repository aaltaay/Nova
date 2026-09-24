# ADR 031 -- A scanner for every setup: bull flag, flat-top breakout, red to green; a level per setup

**Status:** Accepted · **Date:** 2026-09-24
**Amends:** [[027-bot-playbook-readout-gate]] (one scanner, one level) · [[022-setup-scanner-tape-gate]] (one detector) · [[029-setup-templates-eyes-journal]] (lanes for first-pullback templates only; `setups.db` schema 2) · [[030-first-pullback-bot-on-paper]] (the bot trades the first pullback only)
**Decided by:** the operator, 2026-09-24 -- "Weren't we supposed to have a small scanner
for each one of these strategies?"; after the UX mockup, "I like it, but we are going to
need lots of hovers, explaining in detail what each means", "I also want you to add a
strategy called bull flag", and on the mockup's three questions: **A** Off still scores,
silently -- yes; **B** several setups at Eyes at once -- yes; **C** build flat-top and red
to green first, Gap and Go next, micro pullback parked. The rules below are the agent's
reading of the operator's material and the pre-registered research, under the operator's
standing grant for routine calls; each has the operator's veto.
**Resolves:** #572

## Context

ADR 027 listed the operator's setups and promised that each "gains a scanner, a backtest
and a read-out of its own before it can be chosen". Only the first pullback ever got one
(ADR 022), so four of the five cards on the Bots page said "No scanner yet" and nothing
filed the work. The research had already pre-registered the flat-top breakout (P2) and
red to green (P3) on bars (Bot-Trading-Plan §2f): both failed on bars alone, as the first
pullback did -- which is why the first pullback got a scanner with a tape gate. The same
question stands for the other two: does the tape at the trigger turn a losing bar shape
into a winning trade? Only live evidence answers it.

The level was one dial for the session (ADR 027): the chosen setup's. The setup scanner
ignored it and proposed at every level, Off included -- the open question the level-switch
PR left for the operator, answered here (A).

## Decision

1. **Three more detectors, on the same lanes.** Each is a pure state machine on one-minute
   bars (`backend/setup_scanner/`), fed the same bars, prices and tape as the first
   pullback, with the same ladder of states -- `watching`, `leg` (forming), `pullback`
   (formed but one rule blocks it), `armed`, `near`, `triggered`, `failed` -- and the same
   trigger on a live price (entry at the bar's open when it gapped over, skipped when that
   gap pushes the risk over the cap). Every number is a template parameter (ADR 029); the
   defaults below are the pre-registered rules.

   - **Flat-top breakout** (P2, `research/momentum/backtest_setups.py find_flat_top`). A
     base of 2-6 candles right after the candle that set the high of day: none makes a new
     high, every close within 2% under that high, every low at or above the 9 EMA, and the
     high came on an impulse at least 3% over the lowest low of the 10 candles ending at it.
     Armed when the last base candle's MACD histogram is above zero and the next minute is
     inside the arming window; the trigger is the high of day. Two entries, as the research:
     **hold** (the default, the taught way) -- after a price over the high, the first of the
     next three completed candles that holds the level (its low at or above it) and closes
     green triggers at its close: entry one cent over that close, stop that candle's low, and
     the risk check reads entry minus stop, the cent standing for the research's slippage; a
     close back under the high first fails it, three candles without a hold disarm it.
     **break** -- a price over the high triggers; entry one cent over it, stop the base low.
     Target 1 = entry + 2R. At most two a symbol a day (kinds `flat_top_breakout`,
     `second_flat_top_breakout`).
   - **Red to green** (P3, `find_red_to_green`). The level is the open of the first candle
     at or after 09:30 ET. Armed after a close under it (at least one so far, the last one
     included) with the MACD histogram above zero, before 10:30; the trigger is the open,
     entry one cent over, stop the lowest low since the open, target 1 = entry + 2R or the
     high of day, whichever is higher. **One try a day**: the first reclaim with the MACD
     above zero either triggers or, when its risk is outside $0.03-$0.20, ends the day -- as
     the research. A reclaim with the MACD under zero is not a try. Kind `red_to_green`.
   - **Bull flag** (new; pre-registered here from the operator's material, never tested on
     bars -- its read-out is its first test). A pole of at least 3 consecutive green
     candles (close above open) whose rise, from its lowest low to its highest high, is at
     least 5% or at least $0.30, the last pole candle's volume at least the first's; then a
     flag of 2-3 candles right after the pole top, each red or a doji (close at or under its
     open) and none with a high above the candle before it, the flag's low giving back no
     more than half the pole, the flag's average volume under the pole's, and every flag
     close at or above the 9 EMA. Rejected when the day's highest-volume candle so far is
     red, or the pole-top candle's upper wick is more than 40% of its range. Armed when the
     last flag candle's MACD histogram is above zero and the next minute is inside
     07:00-11:30; the trigger is the last flag candle's high ("the first candle to make a
     new high"), entry one cent over, stop the flag low, target 1 = the pole high or entry
     + 2R, whichever is higher; risk $0.03-$0.20 counting one cent of slippage. At most two
     a symbol a day, the first and second flag (kinds `bull_flag`, `second_bull_flag`).
     CHOSEN (the material gives no number): the 5% / $0.30 pole, the 40% wick, the risk
     band and the target, which are the first pullback's.

   The flat-top breakout and the bull flag arm from 07:00, as the first pullback does
   (CHOSEN in ADR 022, so the scoreboard splits pre-market from regular hours); the
   research ran them from 09:30, and a template can. Every setup's stop, risk band, near
   band, tape gate, grade and scoring exits are the first pullback's defaults.

2. **One lane per template of every setup with a scanner.** The engine runs a lane for
   every usable template of the first pullback, the bull flag, the flat-top breakout and red
   to green, on the same bars and tape; each setup's template in play draws that setup's
   rows and is the only one of its lanes that may propose or announce a trigger. Gap and Go
   has no scanner yet (next: a pre-market-high detector); the micro pullback stays parked
   until one-second bars exist (S5).

3. **A level per setup** (A, B). The chosen setup's level is the session's (ADR 027:
   Off / Eyes / Strategy, and the localhost bot API reads it). Every other setup with a
   scanner has its own, Off or Eyes (`setup_levels` on the bot session, an optional key of
   schema 4). **Off** watches and scores, silently: no proposal, no ping -- this changes the
   first pullback, which proposed at every level before. **Eyes** proposes (near and the
   tape at go): a ping, the alert card, the inbox, a staged ticket at most. **Strategy** is
   the chosen setup's only. Several setups may sit at Eyes at once; each proposal names its
   setup, and the Bots page inbox groups a symbol's open proposals into one card that lists
   every setup that raised it, each with its own trigger and stop.

4. **The bot plays the chosen setup** (amends ADR 030). Nova's own bot (brain id
   `nova-first-pullback`, kept so a running session keeps its claim) trades the chosen
   setup's go triggers on Paper and Sim with ADR 030's rules unchanged: the first of the day
   on a symbol only (the kind without `second_`), the entry the scanner scored, target 1
   resting, the watched stop, the 15-minute time stop, one trade a day. Choosing another
   setup while the bot is active deactivates it -- a different setup is a new decision.
   Live waits on the chosen setup's own read-out; nothing places on Live.

5. **A read-out per setup.** The pre-registered rule (ADR 027, §2g: 50 triggered with the
   tape at go, average net R above +0.2 and above blind / wait, judged on the first 100) is
   read per setup and template revision over that setup's first-of-the-day kind. The
   session's `readout` and the `readout` gate are the chosen setup's.

6. **`setups.db` schema 3.** Rows add `setup_type` (the setup: `first_pullback`,
   `bull_flag`, ...) and `detail` (JSON: the setup's own facts -- pole candles, the base,
   the open, the entry mode). A schema-2 file migrates in place, its rows the first
   pullback's; a schema-1 file migrates through 2. Row ids keep their form for the first
   pullback and add `@<setup>` for the others (`SYMBOL-DATE-KEY@bull_flag`, then
   `~TEMPLATE_ID` for a template other than the default). `leg_high` / `leg_low` /
   `leg_pct` / `pullback_bars` carry each setup's own pattern: the leg, the pole, the
   impulse into the high of day, the open and the red phase.

7. **The board, schema 2.** `rows` and `proposals` carry `setup_type`; `setups[]`
   summarizes each setup with a scanner -- its level, whether it proposes, the template in
   play and how many are watched, its window and where the clock is in it, and today's
   counts -- so a card shows its own scanner without a second socket.

8. **Every chip explains itself.** A second tip beside `ux/whyTip.ts`: `ux/hoverTip.ts`
   shows the `data-tip` (and `data-tip-title`) of an enabled element on hover and focus --
   one tip per window, the same placement, plain text only. The setup cards, the Setups
   board and the Symbols card put a specific explanation on every state, tape verdict,
   grade, price, count, level and read-out: what it means, the numbers that made it, and
   what happens next. A card's "Open board" opens Watchlist > Setups filtered to that setup
   (a chip per setup, with its count; a setup without a scanner is a locked chip that says
   why), and a symbol on two setups carries a tag naming the other in both cards.

## Consequences

- The Bots page's five cards become six (the bull flag joins), four with a live scanner.
- At Off the first pullback no longer pings. The scoreboard still records every setup.
- Four setups' lanes cost more CPU than one; each tape read is per lane and per symbol
  near a trigger. The performance recorder (ADR 026) will show it.
- The bull flag's rules are the agent's reading of the operator's material; the scanner
  may show they need changing, and a template (ADR 029) is the way to vary them without
  losing the default's evidence.
- Not built here: Gap and Go's scanner, the micro pullback (one-second bars), the eyes'
  backtest across setups beyond one setup per run.
