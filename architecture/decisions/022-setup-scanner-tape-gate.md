# ADR 022 -- The setup scanner: one first-pullback scanner, a tape gate, and Eyes that propose

**Status:** Accepted · **Date:** 2026-09-22 · **Amended by:** [[031-a-scanner-for-every-setup]] (the bull flag, flat-top breakout and red to green on the same lanes); the 2026-09-30 amendment below (the tape at a trigger is the tape Nova saw)
**Builds on:** [[016-bot-localhost-api]] · [[020-three-venues-one-feed]] · Bot-Trading-Plan §2f / §2g

## Context

Seven bar-level screens of momentum entries on five years of one-minute and
one-second bars failed the first gate (Bot-Trading-Plan §2e / §2f). The three
pullback-family shapes (P1 first pullback, P2 flat top, P3 red to green) were
negative even at zero cost. The operator's own trading method does not enter on
the bar shape: it enters when the shape is in place **and** the Level 2 and the
time and sales say buyers are taking the level. A minute-bar store cannot test
that read. Only the live tape can, so the next evidence has to be collected
live, one armed setup at a time.

The old `strategy/setups_stream.py` loop (`/ws/strategy`) pushed Gap and Go,
Bull Flag and ABCD "triggers" from a stateless scan. It had no notion of
"armed" or "near", no tape read and no scoring, and its BUY verdicts went to
the Phase D executor. The Watchlist's Signals sub-tab listed them.

The operator's framing: an alert is not "buy". A good alert says *"first
pullback armed on XYZ, trigger 4.52, stop 4.38, watch the tape"*, and the
human -- later the bot -- makes the call.

## Decision

### 1. One scanner with a state per symbol, not one scanner per strategy

`backend/setup_scanner/` follows every symbol in the HOD Momo active set (the
tradeable floor already applies there) on the one-minute bars Nova builds from
Level 1 (`ibkr/l1_minute`, the charts' own bars), seeded at first sight from
today's stored bars. The seed leaves out IBKR's bars for minutes without a
price-setting trade (zero volume, one price at the last trade -- the chart keeps
them, as TWS draws them, #304): the rules count bars and were measured on
minute files that have no bar there, and a live minute with no trade has none
either. Each symbol is in one state:

| State | Meaning |
|-------|---------|
| `watching` | nothing to act on |
| `leg` | a fresh high of the day on a leg of at least 5% inside 10 bars |
| `pullback` | pulling back, but one arming rule blocks it (MACD, risk size, time of day); the reason names it |
| `armed` | the pullback is in place; trigger, entry, stop and target are known |
| `near` | price is within max(3¢, 0.3%) of the trigger: the moment to read the tape |
| `triggered` | a print traded over the trigger |
| `failed` | the pullback broke a rule |

The first setup is the **first pullback** (the second pullback is the same
detector counting legs, at most two a symbol a day). Its rules are the
pre-registered P1 rules of the research harness
(`research/momentum/backtest_setups.py`), so the live board and the backtest
agree bar for bar:

- **Leg.** The leg high is the highest high of the prior 30 bars and the day's
  high so far (pre-market included), at least 5% over the lowest low of the 10
  bars before it.
- **Pullback.** One to three candles after the leg high, none making a new
  high; together they give back less than half the leg; every close holds the
  9 EMA.
- **Arm.** Trigger = the last pullback candle's high. Entry = trigger + 1¢.
  Stop = the pullback low. Risk (entry + 1¢ slippage − stop) between 3¢ and
  20¢. The prior bar's MACD histogram (12/26/9) above zero. The next bar
  starts between 07:00 and 11:30 ET. Target 1 = max(leg high, entry + 2R).
- **Trigger.** Price trades over the trigger. A bar that opens over it enters
  at that open, and disarms when that gap pushes the risk past the cap.
- **Fail.** A close under the 9 EMA, half the leg given back, a fourth
  pullback candle, or a leg that went stale without a pullback.

A new leg supersedes an armed setup (`disarmed`). Other setups join the same
board later as further detectors, not as further scanners.

**Parity.** The research selection (2,717 qualifying gapper symbol-days) was
replayed bar by bar through the live detector with the research's 09:30-11:30
window. On the 450 symbol-days where either side took a first trade, the live
detector took the same trade -- same minute, same entry price -- on 427
(94.9%). The misses are two known edges: a risk exactly at the 20¢ cap, where
the research's float arithmetic lands on the other side, and a gap-open entry
whose planned risk was under 3¢. Neither changes what the scanner is for.

### 2. The tape gate reads the book and the tape the desk already holds

`setup_scanner/tape_gate.py` is a pure function of the held book snapshots and
the side-classified prints in the last 10 seconds. Its verdict:

- **blind** -- no Level 2 book newer than 3 s: Nova holds no depth line for
  the symbol. The board says so and offers "Open L2".
- **veto** -- the spread is wider than max(5¢, 1% of price); a single ask
  level of 100k+ shares sits from 1¢ under to 5¢ over the trigger; or a hidden
  seller: ask-side prints of at least twice the displayed inside ask while the
  ask did not rise.
- **wait** -- a 25k+ ask level at the trigger that is not thinning (it must
  shrink by half inside the window); a burst of red (bid-side volume more than
  twice ask-side); or no green (fewer than three prints at the ask, or no more
  volume at the ask than at the bid).
- **go** -- green on the tape and nothing holding the level.

Off-exchange prints (FINRA / TRF / ADF) are ignored. The 100k and 25k seller
sizes come from the operator's method; every other number is ours and marked
`CHOSEN` in `constants_setups.py` -- the scoreboard exists to tell us whether
they are right.

**No invisible feed (ADR 016, decision 2).** The scanner reads only lines the
desk already holds -- a Trader tab's depth and tape, a Session Record. It never
opens, holds or releases an IBKR line: `tape_feed.py` samples
`ibkr.depth.state.current_book` and attaches a passive viewer queue to a tape
stream that is already subscribed. With three depth lines, the gate sees at
most three symbols; the rest are honestly `blind`.

### 3. Eyes propose; nothing places

When a live setup is `near` its trigger and the tape says `go`, the scanner
raises a **proposal**: symbol, setup, trigger, entry, stop, target, risk,
grade and the tape's reasons. A proposal:

- rings once (its own mute switch), and floats an alert card on every tab of
  the main desk window until the setup triggers, fails or is dismissed;
- can **stage** the manual ticket: open the symbol's Trader tab and fill a BUY
  limit at the entry. Every ticket gate -- arming, PIN, confirm, the quantity
  cap -- still stands, and a human presses Place;
- is written to the bot audit stream as `setup_proposal` / `proposed`.
- is withdrawn when the setup re-arms at new levels (a later pullback candle
  moves the trigger or the stop); the next `go` at those levels raises a fresh
  one. It closes as `triggered`, `failed` or `disarmed` with its setup.

Nothing in `setup_scanner/` imports the execution door, the order builders,
the practice broker, the Phase D executor or the bot's action, flatten,
proposal or loop modules; its one bot import is the audit record (a test walks
every module's imports). Because a proposal cannot place, it needs no
allowlist or L2 gate; the ADR 016 proposal store and fire path are unchanged.
No proposal is raised on a replay desk (Sim off the live edge): replayed tape
is for practice, not for a live alert.

### 4. Every armed setup is scored the way the backtest scored its trades

`setups.db` under the operator cache (owner `setup_scanner/store.py`, SQLite,
`PRAGMA user_version = 1`; an unknown version, or an unversioned file that
already holds the table, refuses to open and the board says the scoreboard is
not recording) keeps one row per armed setup: its levels, grade and Five
Pillars at arm time, the tape read when it came near and at the trigger, the
first touch (target 1 or the stop, until 15:55 ET), MFE and MAE over the first
15 minutes, and the R the research exit rules make of it (half at target 1
with the stop to break-even, the rest out on a close under the 9 EMA, a
five-bar bailout, flat by 15:55). These are **scores, not fills**: nothing in
the table was traded.

`GET /api/setups/scoreboard?days=N` splits the numbers by the tape at the
trigger, the grade, the session (pre-market / regular) and the setup kind. The
line that answers the question is "tape said go" against the others.

### 5. What is retired

`strategy/setups_stream.py`, `/ws/strategy`, its constants, and the Watchlist's
Signals sub-tab (and its hook, panel and sample rows). The Watchlist's
**Setups** sub-tab replaces it. Consequences, stated rather than hidden:

- The Phase D executor (Automation sub-tab: `signal` / `confirm` /
  `auto_paper`) no longer receives signals; its controls still work and it
  starts at `signal`. Whether setup proposals should ever feed it is an
  operator decision, recorded as #481 -- not guessed here.
- The Journal's signals table and the Level 2 recorder's signal windows keep
  their history but get no new rows from this path.

## Consequences

- The operator gets the alert they asked for: what, where, the levels, and
  whether the tape agrees -- on every tab, with the ticket one click away.
- The scanner is a measuring instrument as much as an alert: after enough
  sessions the scoreboard says whether "tape: go" turns the bar shape into a
  winning trade. Only then does the bot's Strategy level open for the first
  pullback (ADR 027 gates Activate and every L2 fire on this read-out).
- A symbol without a held depth line is never judged; its tape is `blind`.
  Seeing more symbols means holding more lines, which IBKR caps at three.
- Live minute bars come from Level 1 last and cumulative volume, not the
  exchange's consolidated bars; small differences from the chart vendor's bars
  are expected and do not move a trigger by more than a print.

## Verification

- `backend/tests/test_setup_scanner_pullback.py`, `..._tape_gate.py`,
  `..._scoring.py`, `..._engine.py` (fixtures in `setup_scanner_fixtures.py`).
- `frontend/src/setups/*.test.ts(x)`.
- Parity: the live detector against the research harness on the store's
  qualifying symbol-days (94.9%, residuals above).

## Amendment 2026-09-30 -- the tape at a trigger is the tape Nova saw

**Operator report.** "Why didn't we trade it? ... do we have an audit trail?" LGHL's
first pullback triggered at 07:16:10 ET on an 8.61 trigger and ran to its target in
under a minute. Its tape read at the trigger said WAIT, "burst of red on the tape (1.5k
at the bid vs 0.0k at the ask)".

**Cause.** The window the gate reads (decision 2, "the last 10 seconds") ended at the
trigger's own stamp. That stamp is the L1 last's: IBKR's trade time, in whole seconds
(07:16:10.000). Prints are stamped when they arrive (#563). The sweep that lifted the
offer from 8.52 to 8.63 arrived at 07:16:10.60, so it fell after the window. The gate
judged the pullback's own selling. The engine also read the tape before draining the
print queue that tick, so prints from the last quarter second could be missing too.

**Decision.**

- A lane reads the tape for a trigger, and for a setup coming near, at the moment it
  handles that price: its host's clock, never before the price's own stamp
  (`Lane.read_at`).
- A read takes every print received before it: `TapeFeed.prints` drains the symbol's
  print queue first.
- Every tape read's metrics carry `read_at`, the epoch second its window ends at.
- `triggered_at`, the scoring and a trigger's age keep the price's own stamp. The stamp
  lagged arrival by more than 2 s on 13 of 84 triggers; that is #667.

A replay (`eyes/replay.py`) already stepped to the end of the price's second, so the
live eyes and the backtests now read the same moment.

**Evidence.** The gate replayed on the Session Records (books sampled every 0.5 s, the
prints with the sides recorded live) reproduced the live verdict on all 5 recorded
triggers since 2026-09-23. At the arrival moment, 2 of the 5 change:

- LGHL 2026-09-30, from WAIT to GO: 124 prints and 7,882 shares at the ask, against
  1,454 shares at the bid and none at the ask.
- PFSA 2026-09-24, from GO to VETO: the spread had widened to 6¢ by then.

67 of the 84 triggers had no Level 2 line and read blind either way.

**Consequences.** `setups.db` rows and journal lines written before this read the
earlier window, and are not rewritten. A row's `trigger_tape.metrics.read_at` says
which window it read. The read-out still counts every row; whether to restart it on
the new reads is the operator's call.

## Amendment 2026-10-01 -- too thin to trade

**Operator report.** LPA (Logistic Properties of the Americas), Gainers #41 at +10%: "the problem with
it is that it really sucks. There's no way we can trade it, and there's no volume ... there's no way
I will ever trade something like that with a 20-cent spread". Then, on the proposal: "1 go".

**What happened.** LPA passed HOD Momo's tradeable floor (100K shares, $1, 1.5x relative volume) at
06:01. It had 549K shares by mid-morning, and its relative volume read 15x against its own 74K-share
average day. So the scanners followed it and armed five setups between 09:32 and 09:45, three of which
triggered. Every one was grade C, and the tape read blind each time: Nova held no Level 2 line. The rule
already made each of them NOT A TRADE, and nothing was proposed or sent. But the chart drew LPA's plan
like a trade, and its badge said "STOP FIRST 09:49 · -1.00R". The scoreboard scored all three triggers
as if fills at the trigger plus a cent were possible. Nothing measured whether the stock could be traded:

- every spread check read only the inside quote, and only with a Level 2 line;
- LPA's 08:44 Session Record showed 100 shares at 3.09 x 100 at 3.12, with the next offer at 3.30;
- by the first trigger it had traded $1.0M all day, and $42K in the five minutes before it.

**Measured first.** Read-only, on `setups.db` and the leaderboard's per-minute volume, the default
template's 102 triggers since 2026-09-23:

- 82 of them read blind, with no spread known.
- Triggers on names under $2M traded by the trigger averaged -0.72R gross; the rest averaged -0.17R.
  That was 37 against 49 triggers, a 95% CI on the difference of -1.01 to -0.11. The cut point was
  chosen on the same data, so this is a lean, not proof.
- Of 24 premarket triggers, 8 were on names under $2M (AVAT three times, XRPN, NAUT, NCPL three times).
  None of them reached its target first. The real premarket runners (LGHL $64M, INLF, PFSA, AIFF) traded
  far above $2M.
- On 2026-10-01, 16 of the 31 names that armed a setup (with known volume) had traded under $2M at the
  time.

The case does not rest on the score, though. The score assumes a fill one cent over the trigger, and a
6-cent risk cannot survive a 10-20 cent cost of filling.

**Decision.**

1. **One desk rule, pure** (`setup_scanner/liquidity.py`, constants `SETUPS_THIN_*`). A stock is too
   thin to trade at a moment when any of these fails:
   - it has traded at least $2M today (day volume x its minutes' average price);
   - its last five closed minutes traded at least $100K;
   - with a book and a size, buying the desk's risk per trade over the setup's risk walks the asks no
     more than 0.25R past the best ask.

   A check Nova cannot make is unknown, never thin and never a pass. It is not a template parameter, so
   it never restarts a read-out.
2. **The lanes read it** (`lane_liquidity.py`):
   - when a setup arms, when it first comes near, at each closed minute while it is armed or near, and at
     its trigger, where the reading freezes and is stored (`setups.db` schema 5, `liquidity`);
   - every change of verdict is journalled, so the Sim playback draws the same card.
3. **A thin setup never proposes.** Its trigger carries the reading, and NOT A TRADE
   (`trade_verdict.py`) adds "too thin to trade: ..." for the bot, Auto-entry, Approve and the plan.
4. **It is still scored, outside the read-out.** A setup thin at its trigger counts in neither pool
   (`thin_left_out`), and the scoreboard splits `by.liquidity`, so the rule itself can be checked later.
5. **Greyed, never hidden.**
   - The setup cards grey a thin row and give it a "Too thin" chip with its numbers.
   - The Trader's plan reads TOO THIN and leads its checks with the liquidity.
   - The 1-minute chart's badge reads "TOO THIN TO TRADE", with no track and no call to enter, and the
     chart draws no plan for it: no zones, no plan-only lines, its lane faded. The day's levels stay.
   - Level 2 marks no plan level.
   - The In play tile reads "Too thin".

**Not changed.** HOD Momo's floor and the scanner's universe stay as they are. The eyes still watch
thin names, and their records show what the rule kept out. The watch list's toasts are the operator's
own list and are untouched.
