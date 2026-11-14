# ADR 072 -- Three traders: you, Claude, the brain

**Status:** Accepted (the design; the build follows in the batches below) · **Date:** 2026-11-13
**Replaces:** [[069-your-book-and-the-bots-book]] decisions 1-5 and 9's bots' rows (two books become three; the bots'
budget and Close on a bots' row go) · [[055-the-live-trader-bot]] (retired) · [[044-one-bots-page]] decisions 1-2 and 5-6
and its 2026-10-15 amendments (the Bot switch, the family keys, a strategy's On, the squares, the Bots page) ·
[[042-one-owner-for-novas-buys]] (Auto-entry and the strategy bot's buys) · [[052-the-bot-trades-a-sim-replay]] (no
strategy trades a replay; the brain may) · [[030-first-pullback-bot-on-paper]] (the first pullback trades nowhere) ·
[[037-who-trades-the-stock]] (the Who trades switch: Auto-entry, Approve and Nova takes the exit)
**Amends:** [[056-one-daily-loss-limit]] and [[063-a-loss-line-for-you-and-one-for-the-bots]] (the lines are account,
you, Claude and the brain) · [[068-claude-trades-paper-from-its-own-seat]] (an On / Off switch; its limits move into
Settings; the Account line stops Claude too; Stop Claude and Take Claude's line go) · [[071-three-lanes-for-level-2]]
(lane 3 is the brain's; decision 6 and amendment 1 go) · [[022-setup-scanner-tape-gate]] and
[[034-tape-flow-score-and-flush-exit]] (the strategies read Level 1; the tape gate and the tape's flush exit go) ·
[[016-bot-localhost-api]] (the bot API becomes the brain's door)
**Builds on:** [[007-centralized-trading-execution]] · [[018-desk-venue-vs-spend-arming]] ·
[[045-orders-refuse-a-stale-view]] · [[048-short-selling]]
**Decided by:** the operator, 2026-11-13, after the three lanes merged (PR #1312): "There are no more bots. There's
the brain, there's Claude, and then there's me." They answered the plan's questions one at a time that day (plan page
"The brain drives lane three", 2026-11-13) and approved the screens mockup v1 as drawn
(`F:\Nova\design\brain-switches\v1`). Asked four more questions while this ADR was written (multiple choice,
recommendation marked), they chose: four build PRs, each carrying the screens its own wire needs; a handed trade stays
theirs to close until flat; the Who trades switch's Sell = Nova retires with Buy = Bot (not the recommendation, which
was to keep it); and the TraderTV hosts' page stays on the rail without the bot.

## Context

- **Five holders share the bots' book on Paper** (ADR 069): the strategy bot, Auto-entry, the bot API, the Live
  Trader and Claude's seat. No strategy has shown it makes money on its own (Roadmap Phase L, Bot-Trading-Plan). The
  idea now is one model that sees every input at once: the brain.
- **Claude's seat already trades Paper on its own lane** (ADR 068, ADR 071 lane 2), with its own -$500 day stop in
  code (`agent_trader/constants_agent_trader.py`) and Stop Claude, which sells its shares.
- **Lane 3 is the bots'** (ADR 071): it follows the strategy bot's setups, a trade first.
- **Sim keeps one pile** (`practice/broker.py`: `use_owners(venue == PAPER)`), so on Sim nobody's shares are kept apart.
- **The first pullback waits on the tape** (ADR 022 / 030: GO, WAIT, VETO or BLIND), and the flush exit reads the
  tape (ADR 034). Off a lane neither can read anything, so a strategy that needs them sees one stock at a time.

## Decision

1. **Three traders.** Nova has three: **you**, **Claude** (ADR 068's seat) and **the brain**. Only they send an order
   that opens a position. Nova's own protective closes stay as they are: KILL, Freeze all orders, the day cover, a
   margin call, a loss line's Auto sell, Claude's lapsed lease and a trader's flat-by time. The strategy bot,
   Auto-entry and the Live Trader are retired, and the bot API's door becomes the brain's (decision 10).
   - **The Who trades switch goes** (ADR 037): Buy = Bot (Auto-entry) and Sell = Nova (Approve before you hold, and
     Nova takes the exit on your shares). Nova never places or manages an order of yours. An exit Nova had resting
     for you at the upgrade stays resting as your own order; Nova stops moving it.

2. **Three books in one account, on Paper and on Sim.** Each account (Paper, and now Sim's scratch account) keeps one
   cash and one buying power and, inside it, three books: yours, Claude's and the brain's. Every share, fill and
   dollar belongs to exactly one, each at its own cost, and they add up to the account to the cent. The wire says
   `owner`: `you` | `claude` | `brain`.
   - **Whose an order is** comes from its own stamps, never its side, size or time: origin `claude` is Claude's,
     origin `brain` the brain's; Nova's own closes belong to nobody and close each holder's own shares; everything
     else is yours.
   - **Earlier bots.** An order stamped by a retired bot (source `bot` with no `claude` or `brain` origin, a
     `bot_id`, or origin `bot`, `auto_entry`, `bot_api`, `live_trader`, `close_bots`, `loss_limit_bots`) is
     **Earlier bots** (`owner: "earlier_bots"`, and `bot` names which). Earlier bots is read-only: it holds history,
     never a new order. Claude's past trades stay Claude's (origin `claude`). Nothing in the ledger is rewritten.
   - **Sim gets the same books and rules as Paper.** Its scratch account still unwinds on a rewind; the books are
     replayed with it.
   - **Live is unchanged.** Every Live fill is yours. Claude and the brain never trade Live.

3. **A trader's stock is its own.** A stock is a trader's while it holds shares there or has an entry working. Nobody
   else opens or adds to it -- you, Claude or the brain -- refused in words: "XLAB is the brain's: nobody adds to
   another trader's stock." This is Claude's rule from ADR 068 decision 6, now everyone's. It replaces ADR 069's
   "bots stay out of yours" and "you may join a bot the same way". No two traders ever hold one stock, so nobody can
   hold the other side.

4. **While Claude or the brain is On, its stock is not yours to trade.** Your Buy, Sell, Cover, Flatten and the exit
   pair on its stock are refused: "XLAB is the brain's. Switch the brain off to close it yourself." Cancelling your
   own orders always goes. KILL and Freeze all orders still act on every book.

5. **One On / Off switch each for Claude and the brain.** It sits on the trader's header pill.
   - **On** lets the trader send orders. It is refused, with the reason under the pill, on Live, after the trader's
     day stop and after its flat-by time.
   - **Off sells nothing and asks nothing.** The trader sends no new order. Its unfilled entries are cancelled, and so
     are Claude's armed breaks and its reflexes. Its exits (the stop and any targets) keep resting. Nova's guard
     stops judging the stock, and its open position is **handed to you**.
   - Each switch is Off at 04:00 ET every morning. Within the day it survives a backend restart, so a restart never
     hands a trade over by itself. Spend arming still never survives a start (ADR 018).
   - The switch is the operator's alone: Claude cannot turn itself on, and the phone cannot flip it (ADR 070).
   - Claude's seat (its claim, lease and lane) is apart from the switch. Off does not end the seat, and the seat
     still reads and moves its lane.
   - **A handed trade stays yours to close until it is flat.** Turning the trader On again does not take it back:
     the trader stays out of that stock until it is flat, and nothing changes hands under you mid-trade.

6. **Your close of a handed trade is "closed by you", and the P&L stays on the trader's record.** Your Sell, Cover,
   Flatten and the exit pair close a handed position after your own shares, first cancelling that trader's resting
   exits in the stock. The fill is stamped `closed_by: "you"`. The trade stays on the trader's book, journal and loss
   line: "You closed the brain's 200 XLAB at 4.51 · +$38.00 on the brain's record." A short reads "You covered the
   brain's short". You can close a handed position but never add to it (decision 3).

7. **Limits in Settings, one column per trader.** Settings has one column each for You, Claude and The brain: daily
   loss limit, max shares, risk a trade, budget and flat by.
   - **Claude and the brain** start with Claude's numbers today: a $500 daily loss limit, 1,000 shares, $150 between
     entry and stop, a $25,000 budget and flat by 15:55 ET. Claude's code constants move into this setting.
   - **The budget** is the trader's open shares at the mark plus its working entries at their limits, the sum ADR 069
     counted for all the bots together, now one per trader. ADR 069's shared $25,000 bots' budget goes.
   - **Flat by** is never later than 15:55 ET: neither trader holds overnight. At its flat-by time Nova closes the
     trader's shares, as at 15:55 for Claude today.
   - **Your column** shows your existing settings in place: the You loss line and your own order size limit
     (ADR 064). Budget and flat by do not apply to you.
   - **Long only.** The brain starts long only, like Claude. A short for either needs its own decision.

8. **Four loss lines: account, you, Claude, the brain.** The Account line stops everyone, Claude included (ADR 068's
   exception goes). Each trader's line stops only that trader's entries, and its Auto sell sells only that trader's
   shares opened today (origin `loss_limit_claude`, `loss_limit_brain`). Each AI trader's line is its day stop:
   Claude's separate -$500 in code goes. At its day stop a trader reads **Done for today**: no new entry until
   04:00 ET, its open trade keeps its exits, On is refused, and Off still hands its trade to you. The Bots line goes.

9. **The strategies watch on Level 1, everywhere.** No strategy sends an order on any venue, Sim included. Flat top
   1m / 5m, the 5-minute setups, the first pullback, the pullback dip, the ABCD, trend lines and levels all keep
   forming setups from bars and Level 1, keep drawing on the charts as today (setups, scores, what price did next),
   and write each setup to one feed the brain reads: stock, setup, score and time.
   - Level 2 and the tape are read only on a lane's stock, opened by you, Claude or the brain.
   - The first pullback's tape gate (GO / WAIT / VETO / BLIND) comes out; its trigger forms on Level 1.
   - The flush exit becomes a Level 1 signal (a fast drop on Level 1's last and day volume). It is watch-only.
   - `BOT_NO_DEPTH_LINE` no longer applies to a strategy.
   - Per-strategy Off / Eyes / On goes, with each strategy's bot rules (grades, setups a stock a day, bot window) and
     the read-out counts. A stored level reads as watching. The chart's Eyes switch (ADR 044 decision 8) stays.

10. **The brain's door and lane.**
    - The bot API (`/api/bot/action`, already keyed by `brain_session_id`) becomes the brain's order door. Every order
      is stamped origin `brain` and passes the same gates as every order: the padlock, Freeze all orders, the loss
      lines, buying power, ADR 045's view gate, and a live Level 2 on its stock through lane 3.
    - The brain trades Paper and Sim only. `execution.venue_door` refuses any `brain` send to Live in words, as it
      does `claude`'s. The brain may arm Paper or Sim as an agent (ADR 018), never Live, and never over a padlock the
      operator locked.
    - **Lane 3 is the brain's** (`owner: "brain"`), always, even before it trades. It holds the one stock the brain
      names ("the brain wants X", with a reason). There is no rate limit and no minimum hold. ADR 071 decision 6 and
      amendment 1 (the bots' setup picker) go. Recording follows lane 3 as it does now.

11. **The screens follow mockup v1** (`F:\Nova\design\brain-switches\v1`, approved as drawn):
    - The header's Bots key goes. Claude's pill stays and the brain gets a twin pill and panel, each with its On / Off
      switch. Clicking the words opens the panel.
    - There is no Bots page, and the Bots entry leaves the left rail. The TraderTV hosts' page (today Bots >
      LiveTrader Bots) goes back on the rail as **TraderTV**: the hosts' rows, positions and P/L as today, with the
      bot parts of each card removed.
    - Settings > Loss limits becomes one column per trader (decision 7).
    - Every split reads **All / You / Claude / The brain / Earlier bots**: positions, the Account page, the journal,
      the calendar, Reports and the loss lines.
    - Gone from the screens: Strategy Bots and LiveTrader Bots, every per-strategy Off / Eyes / On and "On -- the bot
      trades these", the bot window, grades, setups a day, read-out collecting, the tape gate's GO / WAIT / VETO /
      BLIND, the bots' budget card, Close on a bots' row, Stop Claude (sells), Take Claude's line and the "Bots'
      trades" loss line, and the Who trades switch.

12. **Retired, kept readable.** The strategy bot's sends, Auto-entry, the Live Trader (fully: it trades nothing and is
    not wired into the brain), the Who trades switch (`/api/stock-mode`: Auto-entry, Approve, Nova takes the exit),
    the bots' budget (`owners-budget.json`), `POST /api/owners/close-bots`, the Bot switch and family keys, Stop
    Claude and Take Claude's line. The bot audit stream and every old origin's label stay
    readable. A retired bot's shares still open at the upgrade are handed to you, like a takeover, and stay on
    Earlier bots' record.

## Data

The confirmed shapes are in `architecture/schema/traders.md` ("Three traders"), with the account and history in
`recording-and-replay.md` ("Three traders' books"), the lines in `loss-limit.md` ("Four lines"), the Reports tab in
`journal.md`, the origins and refusals in `execution.md`, Claude's switch in `agent-trader.md` and the strategies and
the brain in `bot.md`. In short:

- `owner` is `you` | `claude` | `brain` | `earlier_bots` everywhere it is read: positions' `by_owner[]`, order rows,
  fills and their `parts[]`, the account's `books`, the history's `daily[]` and `equity[]`, and the journal's `owner`
  column. `bot` stays, only for Earlier bots. A fill adds `closed_by` (`you` | null).
- Refusals at the door on Paper and Sim: `OWNERS_TRADERS_STOCK` (decision 3), `OWNERS_TRADER_ON` (decision 4),
  `OWNERS_BUDGET` (a trader's budget), `OWNERS_NOT_YOURS` and `OWNERS_OTHER_SIDE` as before. `OWNERS_BOT_STAYS_OUT`,
  `OWNERS_BOTS_BUDGET` and `OWNERS_NOTHING_TO_CLOSE` retire.
- The switches and limits: `GET /api/traders`, `PUT /api/traders/{claude|brain}/switch {on}` and
  `PUT /api/traders/{claude|brain}/limits`. The files are `trader-limits.json` (the setting) and
  `trader-switches.json` (today's state). The owner is a new package, `backend/traders/`. `backend/owners/` keeps
  the books and the rules.
- `loss-limit.json` goes to `schema_version` 3: `limit_usd`, `you_usd`, `claude_usd`, `brain_usd`. A version 2 file
  reads with its Account and You lines unchanged, and Claude's and the brain's lines at $500. Its `bots_usd` is
  dropped, and the answer says so.
- Execution origins add `brain`. Nothing sends `bot`, `auto_entry`, `bot_api`, `live_trader` or `close_bots` again;
  their rows keep their labels.

## Scenarios

| Scenario | What happens |
|---|---|
| The brain holds 200 XLAB and is On; you press Sell | Refused: "XLAB is the brain's. Switch the brain off to close it yourself." |
| You switch the brain Off | Its unfilled entries are cancelled; its stop keeps resting; XLAB is yours to close. |
| ... then you Sell 200 XLAB at 4.51 | The brain's stop is cancelled first, then your Sell fills. The trade reads "The brain · closed by you", +$38 on the brain's record. |
| ... or the brain's resting stop fills first | The brain's own stop closed it; nothing reads "closed by you". |
| ... or you switch the brain On again before closing XLAB | XLAB stays yours to close; the brain stays out of XLAB until it is flat. |
| You hold RUNR; Claude wants RUNR | Refused: RUNR is yours. |
| Claude holds RUNR and is Off; you press Buy | Refused: nobody adds to another trader's stock. |
| You have a buy resting on SSII; the brain names SSII | Lane 3 moves to SSII; the brain's entry is refused while your order works. |
| Claude's day reaches -$500 | Done for today: no new entry, its open trade keeps its exits, On is refused until 04:00 ET. |
| The Account line trips | Every trader's new entries stop, Claude's and the brain's included. |
| 15:55 ET with the brain On and in a trade | Nova sells the brain's shares (its flat-by time). |
| 15:55 ET with a handed trade | It is yours: the close-of-day reminder names it, and a short is covered by the day cover as yours are. |
| KILL | Every share closes, each holder's into its own book. |
| The desk is on Live | Every fill is yours; Claude's and the brain's On are refused. |
| A Sim replay | The same three books and rules as Paper; the strategies only draw. |
| A strategy's first pullback triggers off every lane | It forms on Level 1, draws, and joins the brain's feed. Nothing is bought. |
| A past Paper day with Live Trader trades | Read-only under Earlier bots; Claude's trades that day read as Claude's. |
| You hold SOFI with Nova's exit resting at the upgrade | The exit stays resting as your own order; Nova no longer moves it. |

## Build order

Agreed by the operator, 2026-11-13: one PR each, and each carries the screens its own wire needs, so no merge leaves
a control that does nothing or reads wrong.

1. **ADR and schema** (this change).
2. **Books, rules and the switches:** three books and Earlier bots, owners on Sim, decisions 3-6, the per-trader
   budget, every split reading All / You / Claude / The brain / Earlier bots, and Claude's pill with its switch.
3. **Limits and loss lines in Settings:** decisions 7-8, the four lines, one column per trader, Claude's code limits
   moved into the setting.
4. **The strategies watch on Level 1:** decision 9, the retired senders (decision 12, the Who trades switch
   included), the Bots page, its rail entry and the header Bots key gone, TraderTV back on the rail.
5. **The brain:** decision 10, lane 3 and the door stamped `brain`, the brain's pill and panel.

## Consequences

- Each trader's record is its own, and a takeover never moves P&L between records.
- You cannot trade a stock Claude or the brain is in while it is On. Off is one click and sells nothing.
- No strategy trades on any venue. Their setups still draw on the charts and reach the brain.
- Claude's -$500 and its other limits become settings, and the Account line now stops Claude too.
- Sim's books now split like Paper's. A replay's P&L still never counts on a loss line (ADR 056).
- Approve and Nova takes the exit retire, so the parts of #604 and #606 (one manual order contract) that rest on
  them need re-scoping when that package is next worked.
- `auto_live` stays NO-GO. No venue or arming rule changes. Neither Claude nor the brain trades Live, and Invariant
  #7's gates are unchanged.

## Rejected

- **Keeping per-strategy trading switches**, or any strategy trading on its own: none makes money alone.
- **Wiring the Live Trader into the brain:** the operator retired it fully.
- **Off selling the trader's shares**, or cancelling its stop: Off hands the trade over untouched (mockup choice 1).
- **A small Bots page for the two traders:** the pills in the header are their home (mockup choice 2).
- **The trader taking a handed trade back when switched On:** the operator chose that it stays theirs until flat.
- **Keeping Sell = Nova** (Approve and Nova takes the exit) as your own orders: the operator retired it with the bots.
- **Moving the P&L of a closed-by-you trade to your record:** it would make a trader's record read better or worse
  than its own decisions.
