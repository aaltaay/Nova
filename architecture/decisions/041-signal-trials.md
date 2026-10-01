# ADR 041 -- Signal trials: a tape reading becomes a call only by passing a pre-registered test, and setups get the Level 2 lines first

**Status:** Accepted · **Date:** 2026-09-30
**Builds on:** [[022-setup-scanner-tape-gate]] · [[023-scanner-leaderboard]] (auto-record) · [[033-focus-and-book-watch-sensors]] · [[034-tape-flow-score-and-flush-exit]] · [[036-the-bots-read-on-one-stock]] · [[037-who-trades-the-stock]]
**Decided by:** the operator, 2026-09-30. Looking at the Level 2 ladder's pulled / traded / hidden
marks, they asked "how can we use all this data to determine if we should buy or sell or hold?",
then added "combining time and sale with all 4 colors above ask / between the spread ... i want you
to think about all of that!". On the recommendation ("record the right stocks, register the tests
before new data, flush-30 on the Paper bot, calls in the Trader marked in trial; risk under 5c
warns, Approve may hold Nova's exits on Paper") they answered "i like it. go".

## Context

A study of every Level 2, Time & Sales and setup signal Nova has was run as a buy, sell or hold
call. It covered 25 Session Records over 6 days (2026-09-21..29) and setups.db, and every result
was checked by two independent reviewers: one for leakage and code, one for statistics. The results
and scripts are in `F:\Nova\eyes\studies\buy-sell-hold-2026-09-29\`, with `synthesis.md` and
`critique.md` at its root.

- **Nothing buys.** A random long (buy the ask, 20c / 20c / 15 min) loses 6.85c a trade. The
  following all failed to beat it:
  - every "green" Time & Sales event: a sweep up, a green burst, a print above the ask, a block at
    the ask, an offer taken;
  - every buy-side flow quintile;
  - a 12-feature model, predicting each day without seeing it: its top decile still lost 5.3c;
  - every setup type: -0.71R net over 57 legs.

  Above-ask adds nothing beyond at-ask, and up to 78% of above-ask prints may be the book catching
  up. Pulls, taken vs pulled, hidden sellers and buyers, and absorption show no direction.
- **What survived** is in sample, on 6 days, with the crash day GRML 2026-09-22 able to flip a
  result:
  - a **sell** when the 30 s flow reading turns flush: +1.1c against a random exit, +2c against
    the bracket;
  - two **don't-buy** states: sellers own the last 10 s, and a down-sweep;
  - a planned risk under 5c doing worse.

  With 6 day clusters a day-clustered t over-rejects (placebo |t| >= 2.57 in 10-13% of draws), so
  none of these numbers can promote a signal on its own.
- **The entries they would govern were never measured.** Only 4 setup triggers fell inside a
  recording, and Nova held no depth line at 50 of 62 triggers, so the tape gate read those `blind`.
  Auto-record (ADR 023) gave its three free lines to the Gainers leaders only.

## Decision

1. **A signal becomes a call only by passing a trial registered before its data exists.**
   `knowledge/signal-trials.json` (schema in AGENTS.md §3, "Signal trials") fixes each trial:
   - the rule and the population;
   - one primary metric and its test;
   - the sample size, the pass line and what happens on pass or fail.

   The data starts at `data_from` (2026-09-30). Each trial is read once, when its sample is
   complete, Holm-adjusted across the trials read that night. Until then only its n of N is shown.
   A failed trial leaves its signal as description, and it is never re-registered on the same days.
   `backend/tests/test_signal_trials_registry.py` holds the file to the hash it was registered with,
   so a change is a new trial, never an edit. The six trials:
   - **T1** the 30 s flush exit on random longs;
   - **T2** sellers own the last 10 s, as a don't-buy;
   - **T3** a red burst exit, at bot speed only;
   - **T4** a down-sweep, as a don't-buy;
   - **T5** a planned risk under 5c;
   - **T6** the 30 s flush on setup trades against the setup's own bracket. This is the population
     the calls would actually govern, and the reviewers' most important missing measurement.
2. **Auto-record takes setups first** (`leaderboard/auto_record.py`, 07:00-10:00 ET). The order is:
   - a setup of a template in play whose trade is inside its scoring window (`trade`);
   - a setup near its trigger (`near`), then an armed one (`armed`);
   - then the Gainers leaders, as before.

   A setup may take a leader's line once that line has been recorded for
   `LEADERBOARD_AUTO_RECORD_SETUP_MIN_KEEP_SEC` (60 s; IB refuses a depth line asked again within
   15 s), or a line whose name left both lists. It never takes another setup's line. A leader still
   waits `LEADERBOARD_AUTO_RECORD_MIN_HOLD_SEC` and takes only a line whose name left both lists.

   A trade keeps its line past 10:00 until its scoring window ends. Every operator rule of ADR 023
   holds unchanged: free lines only, the operator's Level 2 or Record takes a line back at once
   (the lowest-ranked goes first: a name that left both lists, then a leader, then armed, near, a
   trade), a hand recording is never touched, and a name the operator stopped is not retaken that
   day.

   `/api/ibkr/status` `auto_record` adds:
   - `why: {SYMBOL: "trade" | "near" | "armed" | "leader" | "left"}`;
   - `setups: [{symbol, why}]`;
   - `setups_error: string | null`. An unreadable setup scanner is stated there, never read as "no
     setups".
3. **The operator's decisions of 2026-09-30 are recorded here, to be built in later changes:**
   - a planned risk under 5c warns on the plan and never blocks until T5 passes;
   - a "Flush exit 30 s" template (`flow_window_sec 30`, `flush_exit exit`, `flush_hold_sec 10`)
     plays on Nova's Paper bot. It is created and put in play through the templates routes outside
     the bot's 07:00-10:00 window, and it leaves play if T1 fails;
   - Approve may hold Nova's flush and 15-minute exits on Paper and on Sim at the live edge. On
     Live it stays locked (#604 question 2);
   - the Trader's WAIT and SELL NOW · FLUSH lines show as calls marked "in trial" with their
     in-sample numbers, until their trial is read. On Live they are description only.

## What does not change

- The tape gate, the flow score and its defaults, the templates in play, the bot's rules and every
  order path.
- Invariant 7: Nova never buys or sells on Live by itself, and `auto_live` stays NO-GO.
- Level 2 marks, hidden sellers and buyers, pulls and the Time & Sales colours stay description.
- ADR 027's read-out stays the gate for a setup, and the operator's definition of done (Paper
  evidence, then their live test) stays the finish line.

## Consequences

- **More setup triggers read the tape instead of `blind`.** With a line held, the gate can say
  `go`, and so:
  - more Eyes proposals ping;
  - Nova's Paper bot can fire on an allowlisted symbol that now holds a line.

  That is the gate working as designed (ADR 022), and those triggers are what the read-out counts.
- **Leaders are recorded less often** while setups hold lines. The leaderboard (recorded always)
  and S5 do not depend on those recordings.
- **A trial is slow.** At about 20 recordings over 8 days, T1-T4 need two to three weeks, and T6
  needs 40 recorded triggers. The honest forecast (`synthesis.md` §5) is that the setups still lose
  and the flush exit helps by about 1c.
- **Not yet built:** the nightly trial reader, the Trader calls and the NBBO stamp on recorded
  prints. They follow in their own changes, and nothing here depends on them.

## Amendment 2026-09-30 -- T7 and the second registry version

`knowledge/signal-trials.json` is frozen, so trials registered after it go in a new registry version,
`knowledge/signal-trials-2.json` (`version: 2`, `follows` the first; held to its own hash by
`backend/tests/test_signal_trials_registry_2.py`; the same reading, multiplicity and peeking rules, and
Holm across every trial read the same night). Its first trial:

- **T7** Room under 2R to the first level of today's map (ADR 036 amendment 2026-09-30), as a warning.
  Population: triggered setups armed from 2026-10-01 (the 30th is left out: its setups were looked at
  while the levels were designed). Pass: the difference in mean gross `bar_r` against the rest is -0.2R or
  worse, Holm-adjusted p < 0.05, with 40 symbol-days each side over 8 session days. On pass it becomes a
  NOT A TRADE reason; on fail it stays a warning with the result on its hover.

## Amendment 2026-09-30 (evening) -- T8 and the third registry version

The operator, on 1-minute setups and the 5-minute chart: "sometimes the 1-minute setup aligns well with the
5-minute setup. It is a powerful strategy, and I want to make sure we are utilizing all of that"; offered
"show it and test it", "show it only" or "not now", they chose to show it and test it. The second registry
is frozen, so the trial goes in `knowledge/signal-trials-3.json` (`version: 3`, `follows` the second; held to
its own hash by `backend/tests/test_signal_trials_registry_3.py`; the same reading, multiplicity and peeking
rules):

- **T8** The 5-minute chart against a 1-minute setup at its trigger (`setup_scanner/five_minute.py`: the last
  complete 5-minute candle's close over its 9 EMA and the 5-minute MACD histogram over 0, from the scanner's
  own minutes before the trigger minute; recorded as `setups.db` `tf5_trigger`), as a warning. Population:
  triggered setups of the templates in play armed from 2026-10-01 whose row carries the read. Pass: agree
  minus against in mean gross `bar_r` is +0.2R or more, Holm-adjusted p < 0.05, with 40 symbol-days each side
  over 8 session days. On pass "5m against" becomes an amber warning on the plan and the setup rows; on fail it
  stays a neutral description with the result on its hover. Shown from the start as a description.
- **In sample** (`F:\Nova\eyes\studies\mtf-alignment-2026-09-30`, the split pre-registered before it ran): on
  the harness's 1,050 base-run trades the difference was +0.10R pooled (95% CI -0.08 to +0.28); red to green
  +0.40R [+0.02, +0.80] did not survive Holm and rested on its five biggest winners; the agreeing trades still
  lost -0.27R. A filter it is not; a lead for the live tape-gated setups it may be.
