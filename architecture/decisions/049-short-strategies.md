# ADR 049 -- The five short strategies, pre-registered

**Status:** Accepted · **Date:** 2026-10-07 · **Built in step 4 of #778**
**Amends:** [[031-a-scanner-for-every-setup]] (five more detectors on the same lanes) · [[022-setup-scanner-tape-gate]] (the tape gate and the scoring, mirrored for a short) · [[034-tape-flow-score-and-flush-exit]] (a burst of buying is a short's flush) · [[044-one-bots-page]] (a short strategy is On only after its test passes)
**Decided by:** the operator, in the short-selling design approved on 2026-10-07 ([[048-short-selling]]; the spec is the body of #778). The five strategies, their windows, the shared rules and the five-year test are theirs. Every number they left open is marked CHOSEN below, the long mirror's where one exists, under the operator's standing grant for routine calls and with their veto.

## Context

Nova's setup scanners are all long: the first pullback, the bull flag, the flat-top breakout, red to green and Gap and Go (ADRs 022, 031). The operator's short book is their mirrors, plus one strategy that only exists because of Reg SHO's short-sale restriction (SSR): selling into a bounce, since an SSR stock cannot be shorted on a break below the bid. These rules are written down before any code reads a bar, so the five-year test and the Paper read-out test the rules as decided, not as tuned.

## Decision

1. **The same machinery as the long setups.** Each strategy is a pure state machine on the scanner's one-minute bars (`backend/setup_scanner/`), on the same lanes, with:
   - the same ladder of states (`watching`, `leg` / forming, `pullback` (formed with a rule blocking it), `armed`, `near`, `triggered`, `failed`);
   - the same templates (ADR 029), journal, `setups.db` rows and read-outs;
   - the same universe: the names the long scanners follow (HOD Momo's, the hot list and Former Momo included).

   Everything a long setup reads upward, a short setup reads downward:
   - **The trigger** is a low. A live price at or under it triggers, and the entry is one cent under the trigger.
   - **The stop** is above the entry.
   - **The target** is entry − 2 × risk: "cover at 2R", with no leg-or-R variant.
   - **Risk.** The risk is checked with one cent of slippage and must sit between $0.03 and $0.20, the long default.
   - **The near band** is the long default's, measured downward.

   Every number is a template parameter, and the defaults below are the pre-registered rules. Each row, proposal, trigger and stored row carries `side: "short"`; every long setup's carries `side: "long"`.

2. **The tape gate, mirrored.**

   | Verdict | Long gate | Short gate |
   | --- | --- | --- |
   | GO | green prints at the ask | 3 or more prints at the bid, no buyer holding the level |
   | WAIT | a 25,000-share seller not thinning | a 25,000-share buyer at the level not thinning, or a green burst |
   | VETO | spread over max($0.05, 1%) / a 100,000-share seller | spread over max($0.05, 1%) / a 100,000-share buyer at the level |
   | BLIND | no Level 2 | no Level 2 |

   The level is the bid side from the trigger + 1c down to the trigger − 5c, the long band mirrored. The flow score (ADR 034) reads the same, sign flipped:
   - a flush is a short's entry (`score` with `entry_mode: "score"` needs a score at or under minus the minimum);
   - a burst of buying is a short's flush exit (tighten the stop down to `flush_trail_r` R over the price, or cover at the ask).

3. **Scoring, mirrored.** R is (entry − exit) / risk:
   - The first touch is target 1 (at or under) or the stop (at or over), read over `SETUPS_SCORE_WINDOW_MIN`.
   - `bar_r` uses the long exit rules mirrored: half at target 1, then the stop to break-even, then a close above the 9 EMA covers the rest; after 5 candles without a close under the entry, the bailout covers.
   - MFE and MAE are measured in the short's favour.

4. **Defaults shared by all five:**
   - The bot buys grades A and B, never C (`bot_grades` "AB").
   - The bot trades one setup per stock per day (`bot_setups_a_day` 1).
   - The scanner scores at most two a stock a day (kinds `X` and `second_X`). Lost VWAP is the exception: one try a day.
   - Each strategy's arming window is also its bot window (CHOSEN, since a short outside 09:35-15:50 can never be placed, and scoring one would only blur the read-out). Every window sits inside those short hours.

5. **Backside lower high** (mirror of the first pullback). Window 09:35-11:30.
   - **The fade.** The lowest low of the last 30 candles is at least 8% under the high of day so far. The fade's low is that candle's low (CHOSEN: the 30-candle lookback is the first pullback's).
   - **The bounce.** 1 to 3 candles right after the fade's low.
     - None makes a new low below the fade's low, and every bounce high stays under the high of day: a lower high.
     - The bounce takes back less than half the fade, measured from the fade's low to the high of day.
     - Every bounce close is at or under the 9 EMA (CHOSEN: the mirror of the pullback's closes at or over it).
   - **Armed** when the last bounce candle's MACD histogram is under zero (the mirror of the pullback's MACD above zero).
   - **The trigger** is the last bounce candle's low, and the entry is one cent under it.
   - **The stop** is one cent over the bounce's highest high. Target 1 is entry − 2R.
   - A new low before the trigger fails it, and a new bounce re-arms at new levels, as the first pullback does.

6. **Bear flag** (mirror of the bull flag). Window 09:35-15:30.
   - **The pole.** At least 3 consecutive red candles (close under open). The drop from the pole's highest high to its lowest low is at least 5%. The last pole candle's volume is at least the first's (the mirror).
   - **The flag.** 2 or 3 candles right after the pole's bottom.
     - Each is green or a doji (close at or over its open), and none has a low under the candle before it: drifting up.
     - The flag's high takes back no more than half the pole.
     - The flag's average volume is under the pole's.
     - Every flag close is at or under the 9 EMA.
   - **Rejected** when the day's highest-volume candle so far is green, or when the pole-bottom candle's lower wick is more than 40% of its range (CHOSEN: both are the bull flag's rules, mirrored).
   - **Armed** when the last flag candle's MACD histogram is under zero.
   - **The trigger** is the last flag candle's low, and the entry is one cent under it.
   - **The stop** is one cent over the flag's highest high. Target 1 is entry − 2R.

7. **Failed breakout** (mirror of the flat-top breakout). Window 09:35-11:30.
   - **The flat top.** The high of day, touched at least twice. A touch is a candle whose high comes within `max(0.5% of it, $0.01)` under it: the flat top's touch rule (ADR 031 amendment 2026-10-06), counting the first touch.
   - **The poke.** A candle whose high goes at least one cent over the flat top.
   - **The failure.** The poke candle, or one of the 2 candles after it, closes back under the flat top. Two candles that all close over the flat top end the setup as a breakout that held, so it fails as a short.
   - **The trigger** is the low of the candle that closed back under, and the entry is one cent under it.
   - **The stop** is one cent over the highest high since the poke. Target 1 is entry − 2R.
   - **Armed** at that candle's close. No MACD rule by default (CHOSEN: the poke has just pushed momentum up, so its histogram is rarely under zero at the failure; the failure is the turn). A template can require one.

8. **Lost VWAP** (mirror of red to green). Window 09:35-12:00.
   - **Over VWAP from the open.** Every one-minute close from 09:30 up to the loss is at or over the session VWAP: the chart's, from 04:00 (`sensors.math_indicators.vwap_session_bars`).
   - **The loss.** A close under VWAP.
   - **The retest.** A later candle whose high comes within `max(0.2% of VWAP, $0.01)` under VWAP, or over it, and that closes under VWAP: VWAP turned it back (CHOSEN, the band).
   - **The trigger** is the retest candle's low, and the entry is one cent under it.
   - **The stop** is one cent over the higher of VWAP and the retest's high. Target 1 is entry − 2R.
   - **One try a day.** The first retest either triggers or, when its risk falls outside the band, ends the day, as red to green does. A close back over VWAP before the retest also ends the day.

9. **SSR bounce short.** SSR stocks only. It sells into a bounce instead of on a break. Window 09:35-15:50.
   1. The stock is under SSR today ([[048-short-selling]]: triggered today, or carried from yesterday) and below VWAP.
   2. It drops at least 6% to a new low of day, measured from the highest high of the 30 candles before that low (CHOSEN, the lookback). It then bounces for at least 2 consecutive green candles off the low.
   3. **The level** is the nearest above the price of these:
      - the SSR trigger price, the 10% line the stock broke;
      - a half or whole dollar;
      - the last lower high: the highest high between the previous low of day and this one;
      - VWAP.
   4. **Armed** when the bounce's price comes within 2% under the level. The short then **rests one cent under the level**, a sell limit, so buyers who push into the level fill it above the bid, as SSR requires. There is no break trigger: a fill is the trigger.
   5. **The stop** is 2% over the entry, at least five cents. Target 1 is entry − 2R.
   6. **Cancelled**, and failed, if any of these comes first:
      - the bounce makes a new low;
      - a one-minute candle closes above the level;
      - 10 minutes pass after arming.

   The mockup's example: FADE closed at 5.60 yesterday, broke 5.04 at 09:30 (SSR on), fell to 4.66 and bounced toward $5.00. The level is $5.00, the short rests at 4.99 with its stop at 5.09, and target 1 is 4.79.

10. **The short grade** (the long grade's Five Pillars, replaced for a short; A is all five known and passing, B four, C three or fewer):
    - ran 30% or more today (the high of day over the prior close);
    - faded 8% or more off the high (the price at arm over the high of day);
    - under VWAP at arm;
    - dilution or bad news on file: the stock read's "Dilution on file" (a shelf, a 424B, an S-1, an 8-K 3.02), or today's catalyst verdict negative (or `negative_too`);
    - borrow at least 10 times the order: tick 236 against the sleeve's size for the setup.

    A pillar Nova cannot read is unknown, never a pass. "Ran 30% or more today" will usually fail on a day-2 SSR stock (its run was yesterday). That is raised on #778 and left as written until the operator answers.

11. **SSR in the tests and the read-outs.**
    - **The four breakdown strategies.** Minute bars cannot show whether a short could have filled under SSR, where the short must sell above the bid on a falling print. Their five-year tests leave SSR days out of the main score, and report those days apart, stated.
    - **The SSR bounce short.** Its resting entry fills only when a later candle trades through the level (its high at least one cent over the entry), which the bars do show. It is tested on SSR days only.
    - **Paper read-outs** report SSR trades as their own group, so a losing SSR group can be switched off on its own (a template's `ssr: "skip"`).
    - **The bot.** Under SSR it trades the same strategies, but its short goes in as a limit at the ask, never at the bid, and is tagged SSR.

12. **The five-year test.** Each short strategy gets a five-year minute-bar test on the operator's store (`F:\Nova\data\massive`, 2021-09-21 onward), run by `research/shorts/` on the desk.
    - **What the bars cannot know is stated.**
      - Past borrow is unknown, so every stock is assumed shortable, and the result says so.
      - SSR days are found from the bars: the 10% line against the prior close, that day and the next.
      - VWAP is computed from the day's bars.
    - **Costs.** IBKR commissions plus one cent a share of slippage on every fill, as gate 1 (Bot-Trading-Plan §2, L3).
    - **Passing.** A strategy passes when its main score survives gate 1's kill criteria, unchanged:
      - at least 300 trades;
      - the edge not living in one year (still positive with its best year removed);
      - still profitable at twice the costs (profit factor over 1);
      - the parameter neighbourhood mostly positive;
      - a 1,000-shuffle permutation p at or under 0.05.
    - **The lock.** A strategy whose test failed, or has not run, stays at Eyes with On locked, and the card says why: "five-year test queued / running / failed". This applies to shorts only (ADR 048). No agent writes a result; the test's own output file is the only source.

13. **New strategies.** The operator asks for a pattern and it gets built; a variant is a template, with no code. "+ Add a setup" offers short setups too.

## Consequences

- Five more detectors on every lane cost CPU. The performance recorder (ADR 026) shows it, as it did for ADR 031.
- These rules are the agent's reading of the operator's design where the design gives no number. The scanner's rows and the five-year test may show that they need changing, and a template is the way to vary them without losing the default's evidence.
- Longs keep today's rule: a long strategy may be On with no passing test. The asymmetry is the operator's: a short's loss is unbounded until its stop fills.
