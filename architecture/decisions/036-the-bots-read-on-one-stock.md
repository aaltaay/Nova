# ADR 036 -- The bot's read on one stock: a 2:1 plan on Level 2, signal tiles, setup drawings

**Status:** Accepted · **Date:** 2026-09-24
**Builds on:** [[022-setup-scanner-tape-gate]] (the scanner, its states and the tape gate) · [[028-why-its-moving]] (the per-symbol facts) · [[029-setup-templates-eyes-journal]] (the eyes' journal) · [[031-a-scanner-for-every-setup]] · [[033-focus-and-book-watch-sensors]] · [[034-tape-flow-score-and-flush-exit]]
**Decided by:** the operator, 2026-09-24 -- "show me the bot's decisions specifically for that stock ...
the full first pullback forming or ... the flat top breakout ... dynamic drawings on the graphs
themselves. If something is forming, can we start highlighting it on the chart? ... Is it
shortable ... all the tiny signals ... hover and see more options or drop down for complete
readings? Maybe historical charts"; then "part of that i want it to tell me my entry/exit .. we
typically want to aim for 2:1 ratio, like right on top of lvl2"; mockup v1 approved the same day
("I really like your approach and your mock. so start building it", #598). The design is the
agent's under the operator's standing grant for routine calls; each item has the operator's veto.

## Context

- Every scanner lane holds each followed symbol's state in memory (the leg, the pullback, the
  flag, the base, the open), but the desk sees a symbol only when a setup arms: the board hides
  `watching`, keeps failed rows five minutes, and has no per-symbol read. A forming setup's
  trigger, stop and risk are computed at every bar close and thrown away -- the reason text
  ("risk 0.29 is over 0.20") is all that survives.
- The eyes' journal (ADR 029) is the only record of why a setup never armed on a symbol, and the
  desk was barred from reading it ("never read by the desk"). The operator now asks to see exactly
  that, per stock.
- The facts the operator asked for already exist in a dozen owners (why it's moving, Five Pillars,
  the catalyst verdict, HOD Momo alerts and decisions, the borrow file, the halt log, the Level 2
  and tape sensors, the book watcher, the tape flow score) and none of them reach the Trader tab.
- The Trader chart draws candles, EMAs, VWAP and MACD; nothing of a setup, the high of day or the
  premarket high. The drawing library Nova ships already exports rectangles, channels and a long
  position tool, unwired.

## Decision

1. **One symbol across every lane.** Each detector keeps the levels its setup *would* arm with
   while it forms (`forming`: a blocked first pullback's trigger / stop / risk, a partial bull
   flag's, a flat top's base under the high, red to green's open and low) and exposes its own
   series at the last closed bar (the MACD line, signal and histogram and the 9 EMA the gates
   read, the high of day). None of it changes what arms: `view()`, the board, the rows and the
   journal are unchanged. `GET /api/setups/symbol/{symbol}` answers every setup's template in play
   for one symbol, and says so when the scanner does not follow it.
2. **The plan is the setup's own.** Entry, stop and target come from the setup's rule; the target is
   the scanner's target 1 -- entry + 2 x risk, or the leg high when that is higher -- so the plan is
   at least the operator's 2:1. A forming setup's levels are provisional and drawn dashed. With no
   setup, the operator names an entry (and may name a stop); the stop defaults to the low of the
   last closed one-minute candles and the target to 2R. Around the numbers the plan lists what
   stands in the way: risk over the cap or smaller than one normal candle, the 1-minute MACD, the
   9 EMA and VWAP, the high of day / VWAP / premarket high / a round number / a large seller
   between entry and target, the tape verdict and flow, bids being pulled, a halt, the bot's
   window. Size is the operator's risk per trade over the risk per share, computed on the desk
   (a desk setting). "Stage in ticket" fills the ticket and never sends.
3. **One read, many owners.** `backend/stock_read/` composes the owners above into seven groups
   (in play, setups, front side, tape, short, float, halts) of rows that each say where their
   number comes from, with a verdict per row and per group -- pure rules over gathered facts, cache
   reads only, no network wait. An unknown is a stated unknown, never a pass. Colours read for a
   long momentum trade (the account is long-only). The same payload serves agents and bots.
4. **The desk reads one symbol's day in the eyes' journal** (amending ADR 029): the decisions
   timeline folds the journal's lines for one symbol and date (repeats counted, not listed) with
   the day's HOD Momo alerts, the borrow changes, the catalyst items and the bot's own audit lines.
   Read-only, off the loop, the file never rewritten.
5. **The history is what Nova holds**: past runs from the stored daily bars, setups armed on the
   symbol on any day, the Level 2 Nova recorded, the latest short interest; what Nova does not hold
   per symbol yet (days on the boards, borrow before today, a short-interest trend) is said so.
6. **Drawings come from the scanner's levels, not the chart's candles.** The 1-minute pane draws
   each lane's leg / pole / base / open, the pullback or flag candles, the plan's lines and risk /
   reward boxes, per state; the 5-minute and 10-second panes mirror the lines. The scanner builds
   its live minutes from sampled Level 1 lasts (`ibkr/l1_minute`), so a level can sit off the
   chart's IBKR candle by a few cents; the drawing shows the scanner's number, and moving the
   scanner onto tape-built minutes is its own change.

## Consequences

- Nothing arms, triggers, proposes or trades differently; the board and `setups.db` are unchanged.
- The Trader rail grows two blocks above Level 2. The whole plan opens only when the quote card
  has room for it and Level 2 both; otherwise it is one line (the setup, entry / stop / target,
  size, reward : risk, Stage) and the tiles one row, and the operator can open it. Measured at
  1920x1080: Level 2 kept 302 px of its 354 with the one-line plan, against 118 with the whole plan
  always open.
- A new symbol-level read touches many owners: each is read with a stated fallback, so one broken
  owner blanks its rows with the reason, never the read.
- Found while building the mockup and fixed with it: `/sensors/vwap` covered only the last 240
  stored bars (now the session from 04:00 ET, the chart's), `/sensors/halt` read "not halted" when
  it did not know (now `null`), the Level 2 shortability chip asked IBKR once per tab (it asks
  again every `IBKR_SHORTABILITY_TTL_SEC`). The quote card's second row (Gap% / High / Low), seen
  cut off on the operator's screen, did not clip in a check at 720-1080 px tall windows with the
  read above Level 2; an e2e test now holds every stat row in view.

## Amendment 2026-09-29 -- setups that ended stay on the chart, and what price did next

**Decided by:** the operator, 2026-09-29, on a bull flag's grey "POLE" box that failed and then left
the chart: "we could probably go back and study them. What could we do better?" -- then "i like this!
1 go" to: say why a setup failed on the chart, keep the day's dead setups where they happened, and
score every failure by what price did next, with a report by fail reason.

- **The journal is the record; the chart reads it back.** Decision 6 drew each lane's *current* state,
  so a setup that failed or faded vanished at the next bar. The eyes' journal already held every line
  (ADR 029, decision 4 above). `eyes/episodes.py` folds a day's lines of each setup's template in play
  into episodes -- one per setup's life on a symbol, from the first line that leaves `watching` to the
  line that ends it -- and the 1-minute pane draws them faint, where they happened: a failed one from
  the moment it failed (a failed flat top can sit on the board for half an hour and drew nothing live),
  a faded or triggered one once it ended. Nothing is recomputed with today's rules and nothing changes
  what arms: the lanes, the board, `setups.db` and the journal are unchanged.
- **Why it died is the rule's own words.** A failed setup's reason is the first rule it broke; a
  faded one's is what it waited on or was blocked by. Reports group reasons with their numbers
  replaced, so every "the flag gave back N% of the pole" is one row.
- **What came next is measured, never inferred.** From the minute it died, the chart's one-minute bars
  say which it crossed first -- the high it was building under or the low it would have stopped under.
  A candle that did both counts as the low, because the order inside a minute is unknown. After a
  break, the trade the rule refused is scored the way the scoreboard scores an armed setup (first
  touch of 2R or the stop, and the bar exit rules). These are scores, not fills: no tape, no slippage.
  They are for judging a rule, and a change to a rule still goes through a template and a backtest.
- **Not drawn:** a faded setup that never got past its leg. It is already visible as the chart's own
  candles, and drawing it would double the boxes on a runner (59 of the 173 setups that had ended by
  10:00 ET on 2026-09-29; mostly the flat top's "new high of day, wait for a base" on every new high).
