# ADR 048 -- Short selling: one short check on every venue, Paper and Sim first, Live last

**Status:** Accepted · **Date:** 2026-10-07 · **Built in six steps under #778** (each step's PR says what it built)
**Amends:** [[009-short-entry]] (its gate grows into one short check that runs on every venue) · [[007-centralized-trading-execution]] (a short entry is held in flight; a cover is never locked) · [[020-three-venues-one-feed]] (Paper and Sim learn to short, the way IBKR does) · [[037-who-trades-the-stock]] (Who trades becomes Entry · Exit) · [[042-one-owner-for-novas-buys]] (one sleeve and one daily count cover both sides) · [[044-one-bots-page]] (Freeze all orders keeps protective stops; the squares learn shorts) · [[045-orders-refuse-a-stale-view]] (a short is a manual order like any other)
**Decided by:** the operator, between 2026-10-01 and 2026-10-07, in a design session whose plan and mockups they approved on 2026-10-07. The plan page is https://claude.ai/artifact/1bHeuPJWoFZSGWmb8PfvFC, and the spec, verbatim, is the body of #778. Answers recorded in it include:
- "Longs use margin too."
- No pattern-day-trader limit.
- The per-stock Long / Short / Both switch, dropped on 10/06.
- "One bot, one list": the strategy that triggers decides the side. This replaced an earlier draft with a separate short side, its own switch and its own sleeve.
- Freeze all orders "keeps every protective stop resting (on longs too)".
- Shorts allowed under SSR, above the bid only.

## Context

ADR 009 (2026-07-28) let Live open a short with three things: an explicit `short_entry`, an env key (`IBKR_SHORT_ENABLED`, still off), and IBKR's tick-236 borrow estimate. Paper and Sim refuse every opening short (`PRACTICE_NO_SHORTS`, operator decision 2026-09-21). The operator is opening an IBKR margin account funded with $5,000 and wants to short, by hand and through Nova's bot on Paper and Sim, under the same rules everywhere.

The design session read the code at `7d9948d` (2026-10-06); master at `60cbc82` was re-read for this ADR. Eight gaps sit in what exists:

1. A short entry gets no margin check. `execution/validate._check_short_entry_sell` reads the env key and the borrow, nothing else.
2. A short is not refused while the account holds the stock long. One SELL would close the long and open a short.
3. A cover (a BUY that reduces a short) is locked by the all-stop's day lock, because `bot.buy_lock.buy_refusal` locks every BUY. It is also held to buying power. Either can stop the account getting flat.
4. The borrow lookup (`ibkr.shortability.fetch_shortability`) asks IBKR synchronously, for up to 10 s (`IBKR_LISTING_FLAGS_TIMEOUT_SEC`). It does so inside the execution lock and on the socket loop. It would hold every other order behind it and break ADR 045's 750 ms send deadline.
5. A short entry is not held as an order in flight (`execution.venue_door.commit_position` skips it). Two of them can validate against the same borrow and margin, and over-short.
6. Freeze all orders (the kill switch) cancels every working order, including the stops that protect a position.
7. Fill now re-sends a working order's remainder as a plain order and drops `short_entry`, so a short entry becomes a plain SELL.
8. Nothing stops a fill from covering more than the short. A resting cover can fill after another cover has already closed the position.

## Decision

1. **One short check.** A short entry can come from:
   - the ticket, a hotkey or the chart;
   - the bot, Auto-entry or Approve;
   - the localhost bot API.

   On Live, Paper or Sim, it passes the same rules, which have one backend owner (`backend/short_sale/`). The execution door runs them under its lock (ADR 007). The ticket, the plan, the bot's squares and the Bots page show the same verdict, read-only. A short is still never inferred: it carries `short_entry` (ADR 009). The rules:
   1. **Margin account.** Live has no Short side until IBKR reports the account as margin. A practice account is a margin account at or above $2,000 of equity (practice-account.md).
   2. **Equity.** At least $2,000, FINRA's margin minimum, before the trade.
   3. **Borrow.** IBKR's shortable estimate (tick 236) must cover this order, plus the shares already short in the stock, plus the short entries in flight. Unknown or stale borrow refuses. The door reads it from the cache and never asks IBKR under its lock. When the cache is stale, the door asks IBKR again in the background.
   4. **Margin.** The requirement must fit the account. The figure is IBKR's what-if first (decision 2), else the published rules, labelled "published rules".
   5. **A 25% cushion.** The price at which IBKR would liquidate the account must be at least 25% above the entry. With shorts of the stock still on the way, each keeps its own limit and the entry is the highest of those prices. That price is where equity falls to the maintenance requirement, with the other positions held still. With $5,000 on a stock under $5, this caps a short at about $3,300.
   6. **A stop on the entry.** A short goes out with a protective BUY stop above the entry, working once the short fills. On the wire it is a bracket whose target is optional: an entry limit, a BUY stop, and an optional BUY limit target. No stop price, no short. A short entry is a limit order (CHOSEN): the SSR rule, the margin and the cushion all need its price, and the ticket opens a short with a Limit.
   7. **No flips, no trading against a position.**
      - A short opens only from flat, or adds to a short.
      - A cover never buys past zero.
      - Nova never shorts a stock the account holds long.
      - Nova never buys a stock the account is short, except to cover.

      These hold for the operator and for the bot.
   8. **Halts.** No short while the stock is halted, and none for 10 minutes after an up-halt resumes. A halt state Nova cannot read refuses. CHOSEN: a halt is "up" when ADR 047's LULD view had the stock at its upper band, or when the last price before the halt was above the price five minutes earlier. One Nova cannot place counts as up.
   9. **Hours.** New shorts are taken from 09:35 to 15:50 ET by the venue's own clock, never premarket or after hours. At 15:55 Nova covers anything still short (decision 5).
   10. **SSR** (Reg SHO Rule 201). Under SSR a short may execute only above the national best bid:
       - the door refuses a short limit at or below the bid, and names the bid;
       - the ticket prefills the ask;
       - Paper and Sim fill an SSR short only above the bid (decision 4);
       - an SSR state Nova cannot read counts as on, which is always legal;
       - SSR never blocks a cover.
   11. **Live only.** The Live short proof must be complete (decision 9). Live's share cap and the PIN-armed latch apply, as to every Live order (ADR 018, #444).
   12. **Nothing is silent.** Every refusal names its rule, its numbers and its fix. Every locked control says why on hover (`data-why`, `data-tip`).

2. **Margin comes from IBKR first.** Before a Paper or Sim order, and before a Live short, Nova asks IBKR's what-if on the Live account. Nothing is placed. IBKR returns the order's initial and maintenance margin, including its extra charge on volatile names, and Nova applies that requirement to the venue's own account.

   When IBKR cannot answer (Gateway down, a past-day Sim replay), Nova uses the published rules and says "published rules":

   | Position | Price | Maintenance |
   | --- | --- | --- |
   | Short | under $2.50 | $2.50 a share |
   | Short | $2.50 to $5 | 100% of value |
   | Short | $5 to $16.67 | $5 a share |
   | Short | above $16.67 | 30% of value |
   | Long | any | 25% of value |

   Longs use margin too: Paper and Sim buying power for longs follows the same source. Nova builds no pattern-day-trader limit, since FINRA's intraday margin rule replaced it on 2026-06-04 (practice-account.md). The operator confirms this once the margin account is live.

3. **The eight gaps are closed** before anything new can short:
   1. A short entry is checked against margin and the 25% cushion. Until step 2 adds the what-if, the check uses the published rules.
   2. A short entry is refused while the account holds the stock long (`SHORT_WHILE_LONG`).
   3. A cover is never refused by the day lock or by buying power. A BUY while the account is short, up to the short, is a close, like selling what you hold.
   4. The door reads borrow from the cache before it takes its lock. With no fresh read it refuses `SHORT_STALE_BORROW` with the fix, and asks IBKR again in the background. An open Trader tab re-reads its stock's borrow before the read goes stale.
   5. A short entry, a place or a bracket, is held in flight as `SHORT` until its order resolves, and the borrow and margin checks count it.
   6. Freeze all orders keeps every protective stop resting: the working stops on the side that closes a held position, on longs and shorts alike, together never larger than that position (two stops that each cover it would both fill and flip it; the nearest the market is kept first). A bracket stop whose entry is still working protects nothing and is cancelled with it. It still cancels entries and targets, and the sweep lists the stops it kept.
   7. Fill now never turns a short into a plain sell. Order rows carry Nova's `short_entry`, and Fill now refuses a short entry before it cancels anything: a short goes out with its stop, so it is placed again from the ticket.
   8. Paper and Sim never fill past flat. A cover that would buy more than the short is cancelled at the fill (`PRACTICE_OVERCOVER`), mirroring QA R42's rule for sells. On Live a fill is IBKR's: the door holds a cover to the short less the covers in flight, as it holds a sell to the long.

4. **Paper and Sim short like IBKR.**
   - **Fills.** A short fills like a sell. Under SSR it fills only above the bid, when a buyer lifts it.
   - **Liquidation.** When equity falls below the maintenance requirement, the account covers at market at once and says so (origin `margin_call`). IBKR sends no margin call; it liquidates.
   - **Liquidation price.** Every position shows its liquidation price, on all three venues.
   - **Borrow fees.** None, because shorts are day-only. This is checked against the first Live statement.
   - **Short brackets.** Practice brackets accept a short entry: a SELL entry, a BUY stop and an optional BUY limit target, one-cancels-other as today.
   - **$5,000.** Paper and Sim start at $5,000, the operator's account. A reset to $5,000 archives the Paper ledger, whose history stays on the Account page; the operator presses it.
   - **Borrow recording.** From now on, borrow is recorded per symbol and time and kept for good.
     - A Sim replay of a past day refuses a short unless borrow was recorded for that moment.
     - Sim at the live edge uses live borrow.

5. **The day cover.** At 15:55 ET by the venue's clock, Nova covers every short still open on each venue. Each cover is a protective close with origin `day_cover`, and that stock's working short entries go first. On a half day the cover runs at 12:55 and new shorts stop at 12:50, because Nova learns the NYSE early closes (CHOSEN: the same ten and five minutes before the close). A cover that cannot go out (IBKR down) raises an alarm on every desk window until it does. The 15:50 close reminder names the cover.

6. **Orders say their side.** Every order row, working and closed, on every venue, carries `position_side` (`long` | `short` | null) and `effect` (`opens` | `closes` | null). They come from Nova's own record: `short_entry`, and the position when the order was sent. An order placed outside Nova is read against the position Nova knew. An unknown side says so and is never guessed. The Orders and Positions tables add a Side column right after Symbol, and "Sent by" adds Day cover and Margin call.

7. **Who trades is Entry · Exit.** ADR 037's switch becomes Entry You | Nova and Exit You | Nova. With Entry on Nova, the strategy that triggers decides long or short. There is no per-stock Long / Short switch: the operator dropped it on 10/06. Auto-entry and Approve work for short strategies too, always with the stop, on Paper and Sim only.

8. **One bot, one list, both sides.**
   - **Strategies.** Every strategy, long or short, is Off · Eyes · On (ADR 044). A long strategy buys and a short strategy shorts.
   - **One trade per stock.** On one stock the bot holds one trade at a time. The first go trigger wins, and the bot never flips: once a trade is flat, the other side needs its own trigger.
   - **Shared limits.** Both sides count toward the venue's daily cap, and share one sleeve, one bot trip and one all-stop.
   - **The test gate.** A short strategy may be On only after its five-year test passed (ADR 049). A failed or missing test keeps it at Eyes, with On locked. This is for shorts only; longs keep today's rule.
   - **SSR.** Under SSR the bot's short goes in as a limit at the ask.
   - **The localhost bot API** (ADR 016) adds short kinds. Every short carries its buy stop, and Live stays refused (`BOT_LIVE_NOT_BUILT`).

9. **Live last.** Live shorts stay impossible in every merged state until the operator has done all of these:
   1. funded their margin account and seen IBKR show it as margin;
   2. reset Paper and Sim to $5,000;
   3. run the five-year tests on the desk;
   4. completed the **Live short proof**: three Paper days with shorts and no wrong refusal or wrong fill, and the drills with a short open (Freeze all orders, Flatten, the 15:55 cover, a Gateway drop). Nova records the proof, and the Bots page shows it, ticking what it can see;
   5. set `IBKR_SHORT_ENABLED=true` in their `.env`, which no agent ever sets.

   Until the proof is complete, the door refuses a Live short (`SHORT_PROOF_INCOMPLETE`) even with the key set. The bot never trades Live (ADR 042), and `auto_live` stays NO-GO.

## The build

Six pull requests under #778. Each is safe on its own: before step 2 nothing new can short, and before the operator's last step Live cannot.

1. This ADR, ADR 049, the constitution and the eight fixes.
2. Shorts on Paper and Sim: the short check, margin with IBKR's what-if and the cushion, borrow recording, SSR, halts, hours and the day cover, liquidation, short brackets, the $5,000 reset, and the Side column.
3. The Trader screens.
4. The five short scanners and the research harness.
5. The Bots page, with the bot trading both sides.
6. Live readiness: the proof and its enforcement, the margin-account check, and the Live day cover and its alarm.

## Consequences

- A short costs more checks than a buy, and every check states itself. A refusal the operator thinks is wrong is evidence for the Live proof, never a silent miss.
- Freeze all orders now leaves a position's stop working. The header's red KILL, which flattens, still cancels everything first, so a stop can never fill after the flatten and open the other side.
- The day cover means a short never survives the session on any venue, so borrow fees, overnight margin and Reg T calls never apply to Nova's shorts.
- Paper's and Sim's margin follows IBKR's own number when the Gateway answers, so a practice short is refused where IBKR would refuse it, including for IBKR's extra charge on a volatile name.

## After step 2's review (2026-10-07)

Four findings on step 2's pull request, each fixed with a regression test:

- **Adding to a short held.** The cushion counted the short already held as if sold at the new entry. Equity is read with that short at its mark now, so by the time the price reaches an entry over the market the held short has lost the move. It now keeps its mark (`margin.cushion(held=...)`): 100 short at $10 plus 250 resting at $20, on $5,000, liquidates near 24.18, under the 25 the cushion needs, and is refused; counted at $20 it passed at 26.37.
- **A short entry still resting when the hours end.** The door checks the hours when a short is placed, and a resting one could fill after 15:50, or a GTC one before 09:35. Outside the short hours Nova now cancels every working short entry (the runner's cutoff, origin `day_cover`), and the fill refuses one too (`SHORT_HOURS`), since a Sim jump past 15:50 fills on the prints it crossed before the next pass.
- **A SELL bracket without `short_entry`.** The practice broker opened a short from any SELL bracket. It now needs `short_entry`, as the door does, so a short is never inferred (ADR 009).
- **SSR at a print.** A resting short filling on a print read the bid at the matcher's pass, which a Sim jump or a late read moves. It now reads the bid that stood when the print traded: the NBBO before it on a Massive window, the recorded quote on a Session Record, and on the live feed the top of book the print met when it arrived, which the tape archive now keeps (`tape_trades.bid` / `ask`).

## Step 3: the Trader screens (2026-10-07)

What step 3 decided where the design left room:

- **The switch reads Entry · Exit, each You | Bot.** Decision 7 says You | Nova; ADR 044's amendment of 2026-10-06
  ("Let's not have Nova buy and sell terminology") already names the switch's Nova side Bot, so the answers read
  "Bot may trade RDYN: no · Entry is You". The wire adds `entry` / `exit` and keeps `buy` / `sell` one release.
- **Nova never enters against a position you hold**, from this step: the bot, Auto-entry and Approve skip a long
  entry on a stock you hold short, and any entry while the position cannot be read (`BOT_SKIP_HELD_OTHER_SIDE`).
  Step 5 adds the short side's mirror (done: ADR 049's step 5 section).
- **Approve on a short setup waits on step 5.** No short setup exists before step 4; between steps 4 and 5 the plan
  box says why and stages the short in the ticket instead. Step 5 lifted it: Approve sends the short with its buy
  stop and cover (ADR 049).
- **The held card's stop is the one resting at the broker** until you set one for the tab: a short always goes out
  with its buy stop, and a card proposing another stop beside it would misstate the trade. The same holds for a
  long's working sell stop.
- **No flush call on a short.** Trial T1 (ADR 041) reads a long's tape; nothing calls COVER NOW on a burst.
- **The 15:50 card names the 15:55 cover on Paper** (Sim is left out, as before). Live's day cover is step 6, so a
  Live short's card still says to be flat by 15:55.
- **A short entry lapses with its own day** (the PR #787 review, fixed here). The cutoff pass cancelled resting
  short entries only while the clock stood outside the short hours, so a GTC one Nova was closed over came back
  inside the next day's hours, and the next day's prints could fill it on the day before's borrow, SSR, halt and
  margin checks. Its day is when it was first placed (`entered_ts`; a replace re-dates `placed_ts`, never the
  session it was checked in), and both the pass and the fill read it.
- **A resting short entry is never repriced in place** (found with the review fix). A replace runs no short check,
  so a new price could skip the borrow, SSR, margin and cushion rules the entry passed at its own price. The door
  refuses it `SHORT_REPRICE` on Paper and Sim: cancel it and place it again. Its exits still move. No desk control
  reprices an order today; this closes the order API. Live gets the same rule with its short entries (step 6).

## Rejected

- A separate short bot, switch and sleeve. It was the operator's earlier draft, replaced by one bot and one list.
- A per-stock Long / Short / Both switch, dropped on 10/06.
- Inferring a short from a SELL with no position. ADR 009 still forbids it.
- Market short entries. There is no price for SSR, the margin or the cushion.
- Keeping the borrow ask under the lock with a shorter timeout. Any IBKR round trip under the lock holds every other order; the cache plus a background read never does.
- Freeze all orders keeping only bracket stop legs. A plain stop placed by hand protects a position just as much.
- A pattern-day-trader count. The rule is retired.

## Questions left with the operator (on #778)

- The every-trade squares in the spec list a Hot list square. ADR 044's 2026-10-06 amendment retired it ("just because it's starred or not, it shouldn't be a reason"), so it stays off until the operator says otherwise.
- The short grade pillar "ran 30%+ today" will usually fail on a day-2 SSR name (ADR 049).
- What "no wrong refusal or wrong fill" needs from the operator on each Paper day of the Live short proof.
- Notes to confirm against the live margin account: no pattern-day-trader limit, and no borrow fees on day-only shorts.
- Early closes (step 2): new shorts stop at 12:50 and Nova covers at 12:55 on an NYSE 13:00 close, ten and five minutes before it, by the same rule as 15:50 / 15:55.

## Related

- `backend/execution/validate.py`, `backend/execution/service.py`, `backend/execution/venue_door.py`, `backend/execution/inflight.py`
- `backend/ibkr/shortability.py`, `backend/bot/buy_lock.py`, `backend/kill_switch/sweep.py`
- `backend/practice/` (`broker.py`, `order_rules.py`, `bracket.py`, `margin.py`)
- `architecture/practice-account.md`, `architecture/practice-fills.md`
- [[049-short-strategies]]: the five short strategies, pre-registered
