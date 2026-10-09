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
   - **The trigger** is a low, and the entry is one cent under it. A live price at or under the entry triggers: the short sells when its entry trades, as a long buys when its entry trades (wording fixed in step 4, before any code read a bar; it read "at or under it").
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

12. **The five-year test.** Each short strategy gets a five-year minute-bar test on the operator's store (the Massive minute files under `NOVA_MARKET_DATA_DIR`, by default `E:\Nova\massive`, 2021-09-21 to 2026-09-21 as gate 1 read them; this read `F:\Nova\data\massive` until step 4 corrected it), run by `research/shorts/` on the desk.
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

## Step 4: what the build chose (2026-10-07)

Written before any detector code existed, under the operator's standing grant for routine calls. Each choice is the
long mirror's where one exists.

### The scanner

- **The setups.** `backside_lower_high`, `bear_flag`, `failed_breakout`, `lost_vwap` and `ssr_bounce`.
  - They join the playbook after Gap and Go, and start at Off on every venue, like every new setup.
  - Their kinds are the setup's id and `second_<id>`; Lost VWAP has only its own.
  - Each is one more lane per template on the scanner's bars.
- **A short's trigger on a live price** (§1). An armed short triggers on a price at or under its entry before its
  cutoff.
  - When the minute opened under the entry, the entry is that open. When the gap pushes the risk over the cap, the
    setup is disarmed, the long rule mirrored.
  - The near band is above the trigger: `max(near_dollars, near_pct)` of the price.
  - A price under the trigger after the cutoff disarms it.
- **The SSR bounce's trigger.** Its entry rests: `trigger` and `entry` are both one cent under the level. A live price
  over the entry fills it, at the entry, never better or worse. That is §11's "a candle trades through the level"
  read live, so the live and the bar reading agree. Its near band is the long one, under the trigger.
- **Backside lower high.**
  - The fade's candle F is a new 30-candle low: its low is at or under every low of the 30 candles before it. Its
    fade is (high of day through F − its low) / high of day.
  - The first m of 1, 2, 3 that qualifies is the setup, as the first pullback reads its m.
  - A bounce candle with a low under F's low makes that candle the next fade.
  - A fade 4 to 10 candles back with no lower low since and no setup fails: "the bounce ran past 3 candles".
  - The fade's candle is the setup's key and its leg: `{t, high: the high of day, low, pct: the fade}`.
- **Bear flag.**
  - The pole drops (pole high − pole low) / pole high.
  - A flag candle is green or a doji: its close at or over its open.
  - "Drifting up": no flag candle's low is under the candle before it.
  - The pole-bottom candle is the key and the leg: `{t, high, low, pct, bars}`.
  - A flag of more than 3 candles fails: "too much buying".
- **Failed breakout.**
  - The flat top is the high of day before the poke. Its touches are the candles in the 30 before the poke whose
    high came within the tolerance under it (the one that made it included). Two or more are needed, and one after
    the first made no new high: the level was retested, as the flat top's touch rule reads it. Highs rising a
    cent at a time are a move, not a flat top.
  - The poke is the first candle whose high is at least one cent over it.
  - The failure is the first close under the flat top among the poke and the 2 candles after it.
  - The trigger must print within 3 candles after the failure candle (CHOSEN: the first pullback's three-candle
    pullback). Otherwise it fails: "no breakdown within 3 candles".
  - A close back over the flat top before then also fails it, as does a high over the poke's.
  - The poke candle is the key. The leg is `{t, high: the highest high since the poke, low: the flat top, touches,
    zone}`.
- **Lost VWAP.**
  - VWAP is the scanner's own: the typical price weighted by volume, from the session's first bar. That is the
    chart's rule (`sensors.math_indicators`).
  - "From the open" starts at the first candle at or after 09:30 (`lv_open`). A day whose opening candle closes
    under VWAP is out.
  - A retest before 09:35 is not the try: the scanner waits for one inside the window.
  - After it arms, the setup stays armed until it triggers, a candle closes back over VWAP (the day ends) or the
    window closes.
  - The loss candle is the key.
- **SSR bounce.**
  - **SSR** comes from the lane's own bars and the prior close. It is on when a bar's low today reached 90% of the
    prior close, or when yesterday's SSR carries:
    - the live host reads yesterday from `short_sale.ssr`'s daily reads, from memory;
    - a replay of a recording does not know yesterday.
  - The setup arms only on a known on. Unknown is not an SSR stock.
  - **The drop** is the candle that made the low of day. It is at least 6% under the highest high of the 30 candles
    before it, and the two candles after it are green.
  - **The half or whole dollar** is the next one over the price.
  - **The last lower high** is the highest high from the candle of the previous low of day up to this low.
  - The armed levels never move. A resting order is cancelled, never repriced.
  - **Cancelled** when a bar's low is under the drop's low, a bar closes over the level, or a live price comes 10
    minutes or more after it armed. Then it fails, and a new drop and bounce may arm again (two a day).
- **Every row, proposal and trigger event carries `side`** (`long` | `short`) and `ssr`.
  - `ssr` is `on` | `off` | `unknown` on a short row, `null` on a long one: the setup's SSR at its trigger, else at
    its arm.
  - `setups.db` is schema 6, adding `side` and `ssr`. A schema-5 file migrates in place: its rows read `long`, and
    `ssr` null.
- **SSR in the read-out and the templates** (§11).
  - For the four breakdown setups, a row whose SSR was `on` or `unknown` at its trigger counts in the read-out's SSR
    group, apart. The go and control pools read the other rows. Unknown counts as on, as the door prices it.
  - The SSR bounce's rows are all SSR, so its pools read them all.
  - A breakdown template's `ssr` is `trade` (the default) or `skip`. With `skip`, a setup armed while SSR is on or
    unknown is filtered, as the stock filter keeps a name out.
- **The short grade** (§10) reads:
  - the high of day and session VWAP from the lane's bars;
  - the prior close from the host (the board's, else the line's tick 9);
  - the price at the arm;
  - the stock read's "Dilution on file" reading (`stock_read.dilution_reader`, from memory) and today's catalyst
    verdict;
  - IBKR's cached tick 236 against the desk sleeve's size for the setup's risk (`bot.sizing`).

  A replay host knows none of the last two: those pillars are unknown there.
- **Liquidity.** A short's "Too thin to trade" walks the bids (ADR 048 step 3's rule).
- **The 5-minute read** (trial T8) is not taken on a short row. T8 reads long setups, and nothing has measured its
  mirror.

- **The journal.** A short's `armed` and `triggered` lines carry its `ssr`, so a playback of the day (the Sim eyes)
  draws the same card. A line's side is its setup's.
- **Past setups** (ADR 036's "what price did next") read a short episode on prices turned upside down, so the long
  rules apply unchanged: a breakdown under its level is the move it was waiting for, and the refused trade is a
  short. The SSR bounce has no aftermath: its entry rests over the price.
- **Auto-record** (CHOSEN) gives a short setup no line, and its setups window leaves the shorts' arming windows out.
  The three depth lines serve the trials that read long setups (ADR 041). A short's On is decided by its five-year
  test, not its tape, so its triggers mostly read the tape blind until step 5 settles how shorts share the lines
  (it did: "Step 5" below).

### Until step 5 (retired by step 5, below)

- Nova's bot and Auto-entry skip a short trigger (`BOT_SKIP_SHORT_LATER`, the first of its reasons), and a short
  proposal names no taker.
- Approve refuses a short setup (`STOCK_MODE_SHORT_LATER`), and the stock's Who trades view says why in a note
  (`short_later`) while the plan's setup is a short and the stock is not at Signal only.
- The Bots page's squares read a short trigger's "strategy on" square red, with the same reason.
- On the desk, a short proposal stages a short with its buy stop in the ticket, never a buy.

### The lock (§12)

- `PATCH /api/bot/session {setup_levels}` refuses On (2) for a short setup (`BOT_SHORT_TEST`) until a passed result
  exists for the rules of its template in play: the result's `rules_hash` equals the template's `params_hash`.
- A short setup already at On whose result stops matching (another template in play, a failed or removed result)
  is read as Eyes.
- The lock is checked against the file each time it is read, at most every 30 s.

### The five-year test

Run by `research/shorts/` on the desk, in three commands (`research/shorts/README.md`): `select_shorts.py` (the
universe), `research/orb/extract_minutes.py --selection shorts_selection --table minutes_shorts --start 04:00` (the
bars), then `test_shorts.py --setup <setup>` once per setup. Each card says its own command while its test is queued.

- **The universe** comes from the day movers index (ADR 050), with no hindsight:
  - a common stock is followed from the first minute its high reached +10% over the prior close (`up10_ts`);
  - at that price (110% of the prior close) it is $1 to $20;
  - it is followed only once its volume today reached 100,000 shares;
  - likely splits are left out;
  - for the SSR bounce, yesterday's +10% movers are followed from 04:00 too (Former Momo).
- **SSR days** are found from the minute bars: today's from its bars, yesterday's from yesterday's movers row.
- **The bars** are the minute files from 04:00 to 16:00 for those symbol-days, extracted into the store.
- **The detectors and exits are the scanner's own.** The detectors run on the bars. Each minute's open, and then its
  extreme, is fed as the live price: the low for a breakdown, the high for the SSR bounce. Exits are the scoring's,
  with costs on every fill. The harness reads no tape, so a template whose flush exit is on is refused: its result
  reads `error`, and On stays locked (PR #789 review).
- **Costs and size** are gate 1's: $25,000, 1% risk a trade, at most 25% of equity a trade, IBKR's fixed commission,
  and one cent of slippage on every fill. Since harness version 2 the same trades are also costed on a fixed
  $25,000, a readout only (amendment of 2026-10-09, below).
- **The neighbourhood** is a named list of variations per strategy: the risk cap, the target R, the window, the
  setup's own key numbers, and the MACD rule. "Mostly positive" means more than half of them have a positive net
  expectancy.
- **The permutation** (CHOSEN).
  - Each of 1,000 seeded shuffles moves every trade's entry to a random minute of the same symbol-day, inside the
    strategy's window. It keeps that trade's risk a share and exits by the same rules.
  - p is (1 + shuffles whose mean net R is at least the strategy's) / 1,001.
  - It asks whether the pattern's timing beats shorting the same stock-days at random.
- **The result file** is `<NOVA_MARKET_DATA_DIR>/research/short_tests/<setup>.json`; `NOVA_SHORT_TESTS_DIR` moves
  the folder. Its shape:

  ```
  {schema_version: 1, setup, state: "running" | "passed" | "failed" | "error",
   started_at, updated_at, finished_at, harness: {version, command},
   rules: {template_id, template_rev, rules_hash},
   data: {first_day, last_day, days, symbol_days}, assumptions: string[],
   progress: {done, total, unit: "days" | "shuffles"} | null,
   main, fixed_size, ssr_days,
   criteria: {trades, best_year_removed, costs_2x, neighbourhood, permutation} | null,
   passed: boolean | null, error: string | null}
  ```

  `fixed_size` came with harness version 2 (amendment of 2026-10-09, below); a version-1 result has none. The file
  is written through a temporary file and a rename. The harness writes `running` first and the verdict last. An
  unreadable file, or one of an unknown version, reads `error` and keeps On locked.

## Step 5: the bot trades both sides (2026-10-07)

The operator's §6.3: one bot, one Bot switch, one list; the strategy that triggers decides the side. Paper and Sim
only (ADR 042: a bot never trades Live). What the build chose where §6.3 gives no rule:

- **One trade per stock, never a flip.** The bot, Auto-entry and Approve read one rule (`admit.against_held`): no
  short while the venue holds the stock long, no buy while it holds it short, nothing while the position cannot be
  read. The daily cap counts both sides; the bot holds one trade at a time overall, as before.
- **The short's price** (CHOSEN). Off SSR it sells at the scanner's entry, as a long buys at its entry: it never
  chases. Under SSR, on or not known, it sells at the higher of the entry and the ask: above the bid, as Rule 201
  requires, and never under the plan. No ask, an ask not above the bid, or an ask at or over the buy stop is a
  skip (`BOT_SKIP_SHORT_PRICE`).
- **The short check before the send** (CHOSEN). The bot reads the one short check at that price and size on the
  door's own facts (memory reads) before anything goes out, so a short the door would refuse is a stated skip on
  the timeline -- borrow, SSR, the halt, the hours, the margin and its cushion -- never a refused order. The door
  still runs the check: this reading is the bot's, the door's is the rule.
- **The bot's short** is its long's bracket mirrored: a SELL limit with `short_entry`, a BUY limit at target 1, a
  BUY stop. The time stop, the flush (a burst of buying) and the last resort cover with a BUY limit at the ask +
  3c, then the protective flatten. R is (fill - exit) / risk.
- **Auto-entry's short** (CHOSEN) keeps Auto-entry's meaning -- the bot enters, you exit -- with ADR 048's rule that
  every short carries its buy stop: a two-leg bracket, the SELL limit and its BUY stop, no target. Its stop is
  cancelled once the position is gone. **Approve's short** sends the short bracket the operator approved.
- **The localhost bot API** (CHOSEN offsets): `short_limit_bid_offset` shorts at the bid + 1c with its buy stop 10c
  over, as a bracket, with no free-form size or stop; `cover_limit_ask_offset` covers with a BUY limit at the ask +
  5c; `cover_market` and `cover_pos` cover at market, never past flat (`cover_pos` is protective like Flatten).
- **The squares** (CHOSEN). A short trigger's shorts-only squares are what the bot or Auto-entry recorded at it --
  the latest skip, entry or refusal per setup id, with the short check it read -- never a check recomputed later. A
  trigger nothing judged (its Entry was You) reads not known. The SSR square is never red: on or unknown it is an
  amber pass ("SSR · at the ask"), because the price rule above already handles it.
- **Auto-record** (CHOSEN) gives a short setup a line only while its strategy is On (effective Strategy): a short the
  bot may trade needs its tape, and the other shorts keep leaving the lines to ADR 041's long trials.
- **The Bots page** (CHOSEN). The buckets sort by each strategy's own switch, except a short at On that its test
  holds at Eyes: it sits in Eyes and says so, because Nova trades it no more than an Eyes strategy.
- **Not built here.** The Live short proof checklist on the Bot card, the Live margin-account check and Live's 15:55
  cover and alarm are step 6. Until the operator finishes it and sets `IBKR_SHORT_ENABLED`, Live refuses every short.

## Amendment (2026-10-09): the fixed-size readout

**Why.** Gate 1's account compounds: each trade risks 1% of the day's equity, at most 25% of it, and a trade under
$500 is skipped as too small to survive the commission. On a setup that loses, the account shrinks until every later
trigger is under that minimum, and the test stops scoring triggers partway through the window. Every criterion that
reads that account then judges only the window's first months or years: `best_year_removed` may have one year left
to remove, and the result cannot say how the setup did after the account ran down. The permutation does not have
this problem: it already costs each trade on a fixed $25,000.

**Decision (operator, 2026-10-09: "Readout only").** Gate 1's compounding account stays the verdict of record for
every criterion, unchanged (§12): the trade count, the best year removed, twice the costs and the neighbourhood; the
permutation keeps its fixed account. `fixed_size` is a readout: kept in the result file, it never passes or fails a
setup, so no verdict moves because of it. If the readout ever gives a reason to change a criterion, that is a new
amendment, decided before the next run.

Rejected: judging `best_year_removed` on the fixed-size account. It would let the check see every year, but it
changes a pre-registered criterion after a run, with the trade count, the costs and the neighbourhood still on the
compounding account.

**The readout.** The result file adds `fixed_size`: the main score's trades (the same pool as `main`, so the SSR-off
triggers for the four breakdown shorts), each costed on a fixed $25,000 account -- 1% risk, at most 25% a trade, the
$500 minimum, the same commission and slippage, and equity that never moves. No trigger is skipped because an earlier
one lost; a trade is still skipped when it is too small at $25,000 or never closed. It carries `main`'s statistics:
`trades, skipped, win_pct, pf, no_losses, exp_r, net_usd, by_year`.

**Harness version 2.** `HARNESS_VERSION` is 2, so a version-1 result reads as a different test. A version-1 result
has no `fixed_size` and stays readable: the result file's `schema_version` stays 1, because the field is added and no
reader needs it.

## Consequences

- Five more detectors on every lane cost CPU. The performance recorder (ADR 026) shows it, as it did for ADR 031.
- These rules are the agent's reading of the operator's design where the design gives no number. The scanner's rows and the five-year test may show that they need changing, and a template is the way to vary them without losing the default's evidence.
- Longs keep today's rule: a long strategy may be On with no passing test. The asymmetry is the operator's: a short's loss is unbounded until its stop fills.
