# ADR 037 -- Who trades the stock: a Buy / Sell switch above Level 2, and the trade's moments live on the chart

**Status:** Accepted · **Date:** 2026-09-24
**Builds on:** [[018-desk-venue-vs-spend-arming]] (arming and the venue) · [[022-setup-scanner-tape-gate]] (triggers and the tape gate) · [[030-first-pullback-bot-on-paper]] (the bot's trade) · [[032-loss-breakers-per-venue]] · [[036-the-bots-read-on-one-stock]] (the plan on Level 2) · #604 (Approve & execute) · #606 (brackets on Paper, the road to Live)
**Amends:** [[007-centralized-trading-execution]] (the #91 note "Sim has no brackets"), [[019-practice-fills-on-replayed-sessions]] decision 3 ("brackets stay off the practice desk"), [[030-first-pullback-bot-on-paper]] (a bot trade can be handed over)
**Decided by:** the operator, 2026-09-24:
- "can we have two modes where the entry is automated but the exit is manual?"
- "When may Nova buy for you? I want a clear option next to level 2 ... if I just want to have an auto entry, the bot at strategy, fully entry and exit, just signal ... if I selected the exit is on me, then I'm going to be the one who exits, not the bot. I want to make sure we visualize this correctly before you implement anything."
- On mockup v2: "your mockup is right ... i also want the live when its actually forming ... keep those previous work in". Then "1 go".

The details are the agent's under the operator's standing grant for routine calls, and each one keeps the operator's veto.

## Context

- The stock read (ADR 036) draws the plan on top of Level 2: entry, stop, a 2:1 target and the size.
  It never places anything. "Stage in ticket" fills the ticket with a buy limit and no exits.
- Nova places orders for the operator in one way only today: the first-pullback bot (ADR 030). It
  runs at Strategy, on Paper and Sim, for every name on its list, and it owns both the entry and the
  exit.
- The operator trades one stock at a time from the Trader tab. They want to choose, per stock and in
  plain sight, who places each side of the trade. There are four combinations:
  - Nova only tells them: Signal only.
  - Nova sends the whole plan once they approve it: Approve.
  - Nova buys and they sell: Auto-entry.
  - The bot does both: Bot at Strategy.
- The operator was explicit about Auto-entry: when the exit is theirs, Nova never sells.
- Approve sends one order with three legs: the entry, a take-profit and a stop. The practice broker
  refused brackets (`SIM_NO_BRACKET`), so Paper could not rehearse the order shape Live would send (#606).
- The operator watches the chart, not a status panel. The approved mockup put the trade's moments on
  the 1-minute chart itself: forming, the trigger, holding, and the exit that is due. A switch that
  changes who trades must show, in the same place, what Nova did and what is left to the operator.

## Decision

1. **One switch per stock, two sides.**
   - The Trader tab gets one row, "Who trades SYMBOL", directly above Level 2. It holds two switches,
     Buy (You | Nova) and Sell (You | Nova).
   - The four combinations are the four modes: Signal only (you / you, the default), Approve (you /
     Nova), Auto-entry (Nova / you) and Bot at Strategy (Nova / Nova).
   - The same switch is a chip under the plan's badge on the 1-minute chart.
   - The backend holds the setting (`backend/stock_mode/`), so every window of the desk reads one
     answer.
2. **Nova places for a stock only on Paper, and on Sim at the live edge.**
   - On Live both Nova sides are locked, and each lock says why:
     - Nova buying on its own is `auto_live`, which stays NO-GO.
     - Approve on Live waits on #604's question 2 (the stop before 9:30) and on the operator's
       decision after Paper.
   - Live is where this is meant to end (#606). The order shapes are Live's own: a limit entry, and
     IBKR's bracket. So nothing here changes when the operator decides, and the Live quantity cap and
     the PIN still apply then.
   - Off the live edge the desk is a replay, and neither the switch nor the read is shown.
3. **Buy: Nova never survives a restart.** Auto-entry and Approve live in memory, stamped with the
   venue. A process start or a venue change returns every stock to Signal only, like arming (ADR 018).
   Bot at Strategy is the bot's own list (ADR 030's allowlist in `bot-session.json`). The Trader
   switch and the Bots page are two doors onto one list, so it lasts as the list does.
4. **Signal only.**
   - Nova places nothing.
   - The chart says what to do and when, with a ping:
     - ENTER NOW when the plan's setup triggers with the tape at go.
     - TARGET HIT and STOP HIT, then SELL NOW, when the target or the stop prints while the operator
       holds the stock.
   - Stage fills the ticket, and never sends: a buy at the entry, or a sell at the target (at the
     last price once an exit is due).
5. **Auto-entry.**
   - **The buy.** When a setup with a scanner triggers on the stock with the tape at go, and the
     trigger is at most 5 s old, Nova sends one BUY limit at the scanner's entry through the
     execution door (source `bot`). It never chases.
   - **The size.** Whole shares of the operator's risk per trade over the setup's risk per share.
     The desk sends its risk per trade with the switch.
   - **How often.** Once per stock per venue day. A fill counts; a miss gives it back.
   - **Unfilled.** An entry that has not filled after `STOCK_MODE_ENTRY_TTL_SEC` is cancelled.
   - **After the fill Nova is done.** It places no target, no stop and no time stop.
   - **The gates:**
     - the venue (decision 2);
     - the padlock;
     - the kill switch;
     - the day lock;
     - the bot trip (the soft breaker fired today);
     - the tape at go (a blind tape, with no Level 2 line, is not go);
     - no Nova order already working on the stock.
   - **Which stocks can trigger.** The scanner follows the HOD Momo names only. A stock it does not
     follow never triggers, and the row says so.
6. **Approve.**
   - **What is approved.** On an armed or near setup, the operator approves the plan: its setup id,
     entry, stop and target, and the size.
   - **The send.** At that setup's trigger, with the tape at go and a fresh trigger, Nova sends the
     whole plan as one bracket through the execution door:
     - a BUY limit at the entry;
     - a SELL limit at the target;
     - a SELL stop at the stop.

     The two exits are one-cancels-other at the broker.
   - **The approval binds to the levels.** It is withdrawn, and says so, when the setup re-arms at
     new levels, fails, or disarms.
   - **After a trigger without an approval.** "Approve: buy N now" sends the same bracket at once.
   - **The tape is not at go at the trigger.** Nothing is sent, the row says so, and the operator
     may approve now.
   - **Unfilled.** The entry is cancelled after the TTL, and its exits with it.
   - **The source is `manual`.** The operator decided the trade; Nova only picked the moment.
7. **Bot at Strategy on one stock.**
   - Switching a stock to Nova / Nova puts it on the bot's list, and switching it to anything else
     takes it off.
   - The bot trades it by its own rules (ADRs 030 and 031): its chosen setup, the first of the day,
     the template's window and cap, the resting target, the watched stop and the 15-minute time stop.
   - The row says when the bot will not trade it: not at Strategy, not active, another setup chosen,
     or the day's trade already used.
8. **Sell: You means Nova never sells.**
   - On a trade whose exit is the operator's, Nova places no target, no stop and no time stop.
   - The only exceptions are the account-wide ones that already exist: the day's loss breakers
     (ADR 032) and KILL flatten every position, hand trades included.
9. **Taking over, and which way the switch may move mid-trade.**
   - **Taking over.** While Nova holds a trade's exits (Approve's bracket, or the bot's trade), "Take
     over the exit" cancels them, and the stock's Sell becomes You.
     - The bot lets go of its trade with a new state, `handed`, and releases the shares from its
       budget.
     - A handed-over bot entry counts as the stock's Nova entry for the day.
   - **Sell never moves from You to Nova while the stock is held.** Nova exits only a trade it
     planned from the start.
   - **Turning Buy back to You** cancels a Nova entry that is still working.
10. **Paper and Sim fill brackets** (#606 step 1). This amends ADR 019 decision 3, ADR 007's "Sim has
    no brackets", and ADR 030's "practice venues take no brackets".
    - **The shape is Live's.** The entry is a limit, the target a limit, and the stop a plain stop,
      with the same quantity, TIF and extended-hours flag on every leg.
    - **The exits are held until the entry fills,** and then one-cancels-other.
    - **Cascades.** Cancelling the entry cancels its exits; cancelling one exit leaves the other.
    - **The contract** is `architecture/practice-fills.md`.
    - **A stated difference before 9:30.** A practice stop triggers on any price-setting print, while
      IBKR holds a plain stop until the open. This stands until #604's question 2 is answered.
11. **The moments live on the chart.**
    - **The badge's track.** The plan's badge on the 1-minute chart carries a track: Forming, then
      Trigger, then Holding, then the exit (Your exit, or Target / stop). It follows the lane's state,
      the position and the orders; nobody presses it.
    - **The calls.** ENTER NOW, SELL NOW, and what Nova just did appear in the same corner, with one
      ping per event.
    - **Line style.** The plan's stop and target are dashed while they are only a plan, and solid
      while an order stands behind them.
    - **Level 2** draws ENTRY, STOP and TARGET where they sit in the book.
12. **Every refusal and every act says why.**
    - A locked side carries its reason: `data-why` on the control, and `locks` in the view.
    - Each act and each skip is a `stock_mode` line on the bot's audit stream. The Bots page timeline
      shows these lines.
    - The stock's view keeps its last event.

## Consequences

**What changes for the operator**
- They can hand one stock's entry to Nova on Paper, without the bot at Strategy, and keep the exit.
- They can approve a whole plan once and let the broker hold both exits.
- They can put a single stock on the bot from the Trader tab.

**Paper and Live**
- Paper rehearses the bracket Live would send, so the Paper evidence #606 needs is measured on Live's
  order shape.
- The first-pullback bot still exits with a resting target and a watched stop. Moving it onto the
  bracket is #606's next step.

**Not built here**
- The Live door (#604 and #606).
- Handing a hand-entered position's exit to Nova: Sell from You to Nova while the stock is held.
- A partial take-over.
- More than one approval queued per stock.
- The bot trading a setup other than its chosen one on a Nova / Nova stock.

**The tape gate**
- Auto-entry and Approve read it from the trigger event. A trigger the scanner announces with the
  tape blind (no Level 2 line) sends nothing, so the operator keeps the stock's Level 2 open.

**Chosen numbers** (in `constants_stock_mode.py`, and mirrored in the frontend where the desk shows them):
- `STOCK_MODE_ENTRY_TTL_SEC`: 10 s.
- The 5 s trigger age: the bot's `BOT_FP_TRIGGER_MAX_AGE_SEC`.
- ENTER NOW stays up for 30 s after the trigger, and only while the price is within half a risk of
  the entry.
- The desk reads the view every 1.5 s while the Trader tab shows.
