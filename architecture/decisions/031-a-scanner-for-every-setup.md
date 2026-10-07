# ADR 031 -- A scanner for every setup: bull flag, flat-top breakout, red to green; a level per setup

**Status:** Accepted · **Date:** 2026-09-24 · **Amended by:** [[042-one-owner-for-novas-buys]] (the chosen setup and its radio retired: every setup's own level under a master ceiling)
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

## Amendment 2026-09-30 -- the same setups on 5-minute candles, chart only

**Decided by:** the operator, 2026-09-30: "we need 5-minute strategies ... sometimes I see slow stocks moving
upwards, and you can see clear patterns in the 5-minute chart, but they're not clear in the 1-minute chart";
offered a mockup first or a build, they chose the mockup. On it (IOVA 2026-09-29, drawn by the real chart code
from the detectors run on 5-minute candles) they chose: build it this way; chart only (no cards, no rows); a
chip and the trigger line on the 1-minute; arming 07:00-15:30.

- **One built-in lane per setup** (the first pullback, the bull flag, the flat top; red to green reads the open
  and stays 1-minute) runs the setup's own detector on 5-minute candles made of the scanner's minutes
  (`setup_scanner/five_minute_lane.py`). Its rules are the default template's except for the 2026-09-29 study's
  5-minute rules and the operator's window: a 5-minute candle, arming until 15:30, a risk up to 6% of the entry
  (a dollar cap would block nearly every 5-minute setup), the scoring exit on 5-minute candles, and the first
  touch read over an hour. The detectors and the scoring take the candle's length and a percent cap; at their
  defaults nothing changes for a 1-minute lane.
- **Template id `5m`:** its rows are its own (`~5m`), so no read-out, trial or bot reads them, and no Bots page
  template counts it. It never proposes or tells the bot (it never plays), and the Setups board and the cards
  show none of it. Its journal lines say `template: "5m"`, so `past-setups?tf=5m` folds them for the 5-minute
  chart.
- **Why built-in and not a template the operator makes:** a template's lane plays its setup's card and the read-out
  counts its revision; these are a different chart's view of the same rules, kept apart so the 1-minute evidence
  stays clean.
- **Evidence so far:** the bar-level 5-minute versions lost less than their 1-minute twins and still lost
  (2026-09-29: first pullback on 5-minute candles 785 trades, PF 0.74). On IOVA 2026-09-29 the 1-minute scanners
  saw 33 setups and triggered one, and the 5-minute lanes triggered four. They are scored to learn, never
  traded.


## Amendment 2026-10-02 -- Gap and Go gets its scanner, like the others

**Decided by:** the operator, 2026-10-02, after SDEV's open ("at the first minute of the opening, we don't even have
the gap-and-go strategy yet"), on being offered a chart-only lane: "why dont u treat it like every other strategy we
already got?" Decision **C** above had already made Gap and Go next; the other four strategies failed their bar-level
backtests worse than Gap and Go did (first pullback PF 0.54, flat top 0.20, red to green 0.58; Gap and Go 1.00) and
are full strategies because the bet is the live tape gate and the Paper read-out. Gap and Go is treated the same.

- **The rule** is the research's pre-registered A2 rule (`research/orb/backtest_gng.py`, 2026-09-22), read by a
  fifth detector on the same lanes (`setup_scanner/gap_and_go.py`): the pre-market high is the highest high of the
  day's candles before 09:30; the first price at or after 09:30 is the open; an open at or over the pre-market high
  skips the day (a gap through it); otherwise it arms at the open with trigger = the pre-market high, entry one
  cent over it, stop `min(20c, 4% of the entry)` under the entry, target 1 = entry + 2R; a live price over the high
  until 10:00 triggers (entry at the bar's open when it gapped over, the stop moving with the entry, as the
  research's did). **One try a day**: a gap through, the window closing, or a break the scanner did not see live (a
  restart's seed showing a candle over the high) ends the day. Before the open the board and the chart show the
  levels it would arm with (`forming`). The research has no MACD rule: `macd_positive` is off by default.
- **What differs from the research, stated:** the research picked its names by the Five Pillars at 09:30 ranked by
  pre-market relative volume (top 10); the live scanner reads the names it follows (HOD Momo's), like every other
  setup, and grades them. The research's target 2 (4R) and 11:30 time stop are its own exits; the scanner scores
  with the shared bar rules (half at target 1, break-even, the 9 EMA, the bailout).
- **Same as the others:** Off / Eyes / On per venue (a new setup starts Off: it watches and scores in silence),
  proposals at Eyes, Nova's bot and Auto-entry at On on Paper and Sim only, the tape gate, the grade, NOT A TRADE,
  `setups.db` rows (`@gap_and_go`), its own read-out (kind `gap_and_go`), templates, the Tickers today squares, the
  setup cards and the charts (the pre-market high as the lane's line; a past episode from the open to how it ended).
  Bot window default 09:30-10:00, inside its arming window.
- **The pre-market high needs the morning's minutes:** a name followed mid-session is held `seeding` until IBKR's
  1-minute history from 04:00 lands (`setup_scanner/seeder.py`, the same day's fix), so the level is the whole
  pre-market's. A history that never comes is given up and the name is seeded with what the store holds; its
  pre-market high is then only as complete as those minutes.
- Not built here: the micro pullback (one-second bars).


## Amendment 2026-10-06 -- the flat top counts its touches, within a tolerance

**Decided by:** the operator, 2026-10-06, with a sketch of the pattern (a run-up, candles tapping the high of day,
each touch ringed, the base boxed, the break and the hold candle marked): "Make it something special like this ...
when it starts forming. I doubt real life is going to be perfect as this, so we may need a drift or a ratio to still
consider flat top ... you need to study the material to make sure what I'm talking about is correct ... maybe it's
5 minutes, maybe it's 1 minute ... I don't know if it's worth adding the strategy as a short position ... do what you
think is best."

In the operator's material a flat top is a stock that ran up and then taps the same price, the high of day, again
and again: the consolidation candles sit at or just under the high, rest on the 9 EMA, and the pattern breaks on the
first candle over it. It reads best on 5-minute candles and is bought on the 1-minute, on the first pullback that
holds the level after the break.

Decision 1's flat top (the research's P2) counted no taps at all. It armed any 2-6 candles closing within 2% under
the high, so a base whose highs never came back to the level armed as a flat top. A candle that tied the high started
the setup over on a new row, and one a cent over it reset the base. Every flat top the live scanner had triggered so
far armed on that minimum 2-candle base.

- **The shape** (`setup_scanner/flat_top_shape.py`). The level is the high of day. A **touch** is a candle whose high
  is within the tolerance under it: `ft_touch_pct` of the level (default 0.5%) or `ft_touch_dollars` (default $0.01,
  one tick), whichever is more, so a consolidation a couple of cents under the high still counts. A candle a
  little over the earlier touches, inside the tolerance, is a touch too: the level drifts up to it and the setup
  keeps its row. The base runs from the **first touch**: the earliest candle in the zone after an impulse
  into it (unchanged: 3% over the 10-candle low), from which every close stays within 2% under the level and every
  low on the 9 EMA. At least one touch after the first must make no new high (a **retest**), so highs rising a cent at
  a time are a move, not a flat top.
- **Forming, then armed.** From its second touch it is drawn forming ("2 of 3 touches", state `leg` with `forming`
  levels and `waiting: "1 more touch"`). It arms at `ft_min_touches` (default 3: the high-of-day candle and two
  taps) on a base of `ft_min_consol`-`ft_max_consol` candles after the first touch, with the MACD and window rules
  as before. A flat top that began more than `ft_max_consol` candles back is stale; the default rises from 6 to 20.
  The material puts no limit on the base, and long ones keep tapping.
- **The hold** reads the zone as the level: after the break, the first of the next 3 candles whose low stays in the
  zone or over it and that closes green over the high triggers at its close (a retest of the level holds). Only a
  close under the zone fails it. At tolerance 0 this is exactly the old rule.
- **The research's P2 is one setting away.** `ft_base_start: "last_high"` with one touch and no tolerance, base at
  most 6, runs it exactly (`flat_top_shape.P2_RULE`), and the research parity test runs it. A template saved before
  these parameters keeps the rule it ran: a stored template that lacks one reads its `catalogue.LEGACY` value, never
  the new default.
- **A new revision.** The built-in default's rules revision is per setup now (`SETUP_TEMPLATE_DEFAULT_REVS`): the
  flat top's is 2, so its read-out starts over on the new rules. No other setup's moves. The 5-minute flat-top lane's
  revision is 2 too (`FIVE_MIN_REVS`).
- **On the wire.** A flat top's `leg` adds `touches: [[t, high], ...]` (oldest first) and `zone` (the lowest high
  that touches), and `bars` counts the base's candles. Its armed `detail` adds `touches`, `zone`, `min_touches` and
  `broke_bar_t` (the candle the break printed in; hold entry). A triggered hold adds `hold_bar_t` and `hold_high`.
- **On the desk** (`frontend/src/stock_read/flatTopShapes.ts`). The flat top is drawn as the sketch: a violet level from
  the first touch to the right edge, dashed while it forms and solid once armed. Each touch gets a lavender ring on its
  candle's high, and the last ring counts them ("4 touches", "2 of 3 touches"). The base is boxed. A green triangle
  marks the candle that broke it, and a green box marks the candle that held it. The level's name is in the edge
  column ("FLAT TOP = HOD 5.50" until it breaks). A flat top that is not the plan's lead is a dimmed violet without
  labels; a failed one is grey. Past flat tops keep their rings, faint. The same drawing runs on the 5-minute chart's
  lane (labels "5m"), where the lead's trigger line is named "5m FLAT TOP". Each pane's Key lists the marks. The
  5-minute flat top's chip on the 1-minute chart says how the material buys it there.
- **Both timeframes, unchanged roles.** The 1-minute flat top plays as before (Off / Eyes / On). The 5-minute one is
  still drawn and scored only (the 2026-09-30 decision); turning it into a buy is a separate decision.
- **No short.** The flat-bottom breakdown is the material's mirror (a short, a stop-out signal for a long, or a bear
  trap). Nova does not open shorts (Invariant 7: a short entry needs its own opt-in and the short gate, and the
  practice venues refuse one), so no flat-bottom strategy is built here.
