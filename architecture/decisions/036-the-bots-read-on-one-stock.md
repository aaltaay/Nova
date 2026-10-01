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

## Amendment 2026-09-30 -- the day's levels, on the chart each comes from

**Decided by:** the operator, 2026-09-30: "we can identify major resistance/support levels based on the full
day chart, how can we label those things ... and consider these additional rules when we trade? cuz say our
target is 1:2 ratio for trades is too generic"; then "the material teach us that there are stops at half
dollar or full dollar which are great psychological triggers". On the study and mockup v3 they chose, with
the recommendation each time: keep the 2R target and show the room; warn under 2R and let a trial decide
more; draw the daily levels, faint; and (asked "should we keep those in min1 chart or full day chart? ...
we are overloading the 1min chart") put each level on the chart it comes from. "2 go", then "cool. lets go
ahead and implement that!".

- **Measured first** (`F:\Nova\eyes\studies\levels-2026-09-30`, in sample, five years of minute bars on
  the pillar stocks, $1-$20):
  - Half and whole dollars turn price back before they break (a fresh approach printed through within
    10 minutes 76% of the time, against 84% at a random price 10-40c away) and act as a trigger once
    through (+1.5% before -1.5% in 77% of breaks, against 70%; a break under: 68% against 63%). Each gap
    held on a day-clustered bootstrap, on about 11,000 crossings.
  - On 1,478 harness trades, the high of day and tops tested twice or more slowed price a little (72%
    and 71% went 0.5R past them, against 77% and 76%); old daily highs did not (78% against 78%).
  - Capping the target a cent under the first level inside 2R lowered the mean (-0.097R against
    -0.087R), so the target stays 2R. Trades with no level of today's map inside 2R did better (+0.02R
    against -0.11R), within the noise: trial T7 (`knowledge/signal-trials-2.json`, ADR 041) decides
    whether Room ever blocks.
- **The level map** (`stock_read/level_map.py`, pure; the read's `level_map`): today's map -- the high and
  low of day, the premarket high, the 09:30 open, VWAP, tops and bottoms tested twice or more (swing highs
  and lows within 0.3%), half and whole dollars within 25% of the price, yesterday's high, low and close --
  and the daily map -- daily highs and lows touched twice or more in 60 sessions (within 2%), the older
  daily highs above the price, unfilled gaps, the 200-day average and yesterday's levels. Levels close
  together (0.6% today, 1.5% daily) are one zone listing every reason it holds.
- **Each chart carries its own levels.** The 5-minute pane carries today's map: per side the nearest
  zone and the strongest others within 12% of the price, the zone the price is on, the high and low of
  day, the nearest whole and half dollar each side and yesterday's levels, each with a line and a label;
  every other zone is a tick on the price axis. The Full Day pane carries the daily map the same way
  within 40%. The 1-minute pane keeps what it drew (the high of day, the premarket high, the open, the
  nearest half dollar each side) and adds only the plan's levels between its stop and target, as thin
  price lines: no label column. A label or a tick opens the level's card: what holds it, its tests or
  dates, how far it is, and what the study measured. The 10-second pane is unchanged.
- **The plan says what stands in the way** (`stock_read/level_notes.py`): Room (the first zone of today's
  map over the entry, in R; amber under 2R, "in trial T7"; the daily levels in the way named but never
  counted), the half or whole dollar at the target and at the stop (5 cents either side), the next one
  over the entry, and a round the price broke or lost in the last 10 minutes. The ruler marks today's
  zones between the stop and the target. Every sentence quotes the study; nothing blocks or places, and
  the ADR 037 runners and the bot keep their own rules.
- **Not in it:** setup shapes on the 5-minute chart (the operator's other ask, parked as #649:
  the scanners read one-minute candles only, and the 5-minute versions of the setups lost less than the
  1-minute ones but still lost, 2026-09-29); ascending and descending trend lines (no rule yet for which
  two points to join).

## Amendment 2026-09-30 (evening) -- each chart reads its own candles

**Decided by:** the operator, on XRPN after hours: "why does it say it's a double top when, on the graph,
we only see one top? ... These types of information need to be on the 1-minute chart ... I don't want to
see misleading information ... Every chart has special needs and special powers, and you need to move these
lines to where they make sense. There's no reason to have duplicate information"; and on the cards: "these
hovers are very ugly and i can't understand them"; "where ever we need legend ... cuz i get lost".

- **What was wrong.** Today's map counted its tops and bottoms on 1-minute candles, and the 5-minute pane
  drew it: the high of day read "double top" for two 1-minute tops (17:41, 17:44) inside one 5-minute
  candle. The 1-minute pane's level lines were price lines without an axis label, and lightweight-charts
  5.1 shows a price line's title only beside its axis label, so they never showed their names. Two more
  were found with it: the read judged every level against a board row's price that stopped at the 16:00
  close (XRPN 16.40 while it traded 17.11), and its VWAP ran from 04:00 while the chart's restarts at 16:00
  (16.29 against the chart's 18.62).
- **Each chart's own map.** The level map adds `five_minute`: the same day read from 5-minute candles made
  of the session's minutes (high and low of day, premarket high, open, tops and bottoms by the same swing
  rule), with a round dollar only where it falls in a zone with another reason, no VWAP (the chart draws
  its own line) and nothing from yesterday (the Full Day pane's). The 5-minute pane draws it. The
  1-minute pane draws, from today's 1-minute map, the high of day (with what its candles made of it), the
  zone the price is on, the nearest top and bottom its candles made each side, the nearest round dollar
  each side and the plan's levels, drawn like the 5-minute pane's (labels, cards; no ticks). The premarket
  high and the open are the 5-minute pane's; the 10-second pane draws the plan's lines only.
- **Today's 1-minute map is unchanged** -- the plan reads it, and trial T7 is registered on it.
- **The same VWAP everywhere.** One rule (`sensors.math_indicators.vwap_session_bars`): from 04:00 ET,
  restarted at the 16:00 close once the newest bar is after it, as the chart does. The setup scanners'
  default windows end by 11:30, so no T7 data is touched.
- **The read's price** is the board row's, repriced by the L1 line's last trade (`/api/why` facts).
- **Words a trader reads.** A label is the price, what the level is and what the candles made of it
  ("$17.50 · double top", "23.52 · HOD · double top"); the card says what it is and how far, why it is
  there (each top or bottom with the candles it was counted on and when) and what usually happens, from
  the study, without its percentages. Every pane's corner has a Key chip listing what its colours mean.
- **Not in it:** 5-minute setup shapes (#649) and reading a 1-minute setup against the 5-minute chart.
  An in-sample split of the harness's 1,050 bar-level trades by 5-minute agreement (5-minute close over
  its 9 EMA and MACD histogram over 0, `F:\Nova\eyes\studies\mtf-alignment-2026-09-30`) leaned the right
  way and did not hold: pooled +0.10R (95% CI -0.08 to +0.28), and the agreeing trades still lost
  (-0.27R).

## Amendment 2026-10-01 -- the read while you hold the stock

Operator: "If I enter a trade, can it tell me on the chart when I should sell ... if we pass that level,
okay, this is the next level". Mockup v4 / v4b (the Trader Bot Read canvas) on the operator's own Paper trade
in APUS on 2026-09-24; then "1 go", and "lets move these targets ... to the 10 seconds chart".

- **Context.** Fed a position, the plan box measured from the entry. Holding APUS at 6.64 it read "$5.50 is
  42c above" and "Room 1.0R to $5.50", and the price sat off the end of its ruler. Its "$ now" counted a
  candle's high through $6.50 that no candle had closed over.
- **Decision.** The read takes the held position and answers `held` (`stock_read/held.py`, pure): the stop
  (yours, Nova's, else proposed by the hand plan's rule), the rounds a 1-minute candle closed over since you
  held (broke) and the ones only traded through, the raise that offers (up only, under the price), the 2R
  target, and a ladder of the levels over and under the price. The rows are measured from the price. The plan
  box keeps its look and becomes the trade's; the 10-second chart draws the ladder (the 1-minute chart keeps
  its setups, levels and the one call).
- **Why a close and not a print.** The 08:56:14 sweep to 6.02 on APUS reversed to 5.30 in six seconds. Read
  off a print, it would have raised the stop over the price.
- **What the calls are.** SELL NOW at the stop and the target are your plan's; BROKE offers a raise; the
  flush call is trial T1's reading (30 s window), marked in trial and description only on Live. On the
  operator's APUS trade the early calls (the flush and the proposed stop at 08:47) would have sold near the
  low of a trade that, averaged down, made +$156; on the last 100 shares the calls sold within cents of the
  operator. One trade proves nothing; the calls describe, and trial T1 measures.
