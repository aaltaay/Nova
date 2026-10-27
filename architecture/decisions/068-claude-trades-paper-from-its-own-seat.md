# ADR 068 -- Claude trades Paper from its own seat

**Status:** Accepted · **Date:** 2026-10-26
**Amends:** [[044-one-bots-page]] (decision 6: a hidden tab's line is never Claude's, and the seat's line is never lent) · [[063-a-loss-line-for-you-and-one-for-the-bots]] (Claude's fills count on the Bots line)
**Builds on:** [[007-centralized-trading-execution]] · [[018-desk-venue-vs-spend-arming]] · [[045-orders-refuse-a-stale-view]] · [[055-the-live-trader-bot]] (the Paper-only send pattern) · [[050-agents-find-and-show-in-the-sim]] (the `/api/agent` door and its key)
**Decided by:** the operator, 2026-10-26 (about 20:00 ET). They asked Claude to trade Paper itself: "i want to ask you to be the one who uses your brain and place trades on paper". Then: "i agree.. lets do it ... you need to make your presence known." Then: "we only got 3 symbols to look at level 2, and you will need to control one of them.. and lock it so human wont be able to just open like 3 and you have taken one ... please think about every scenario." Limits as proposed and agreed: up to 1,000 shares, at most $150 risk a trade, 3 trades a day, done for the day at -$400, long only, Paper only.

## Context

Claude works through tool calls. It reads Level 2 and Time & Sales from the backend, decides, and comes back a minute or two later. It cannot watch every print or click a ticket, and it shares one desk with the operator and the bots:

- IBKR gives the login 3 Level 2 lines (`IBKR_MAX_DEPTH_SYMBOLS`). Today a 4th is refused and an idle line is evicted; nothing reserves a line for anyone.
- The desk has one venue. An order is sent on whatever the desk shows unless it names a venue Nova allows (`execution.venue_door`).
- Paper is one account (`NOVA-PAPER`). Shares bought by the operator, a bot and Claude in one stock would be one position.
- An order sent with `source: "manual"` reads as the operator's everywhere: Orders today, the Account page, the You loss line.

## Decision

1. **One seat, one holder.** `backend/agent_trader/` owns Claude's seat on the desk: one holder at a time (a token the claim returns; a second claim is refused while the first is alive), with a lease Claude renews by checking in. Its state is persisted (`backend/.cache/agent-seat.json`) so a backend restart neither drops the reservation nor hides an open trade.

2. **One Level 2 line, locked.** While the seat is on (not off, not given up), one of the 3 Level 2 lines is Claude's:
   - every other subscriber (Trader tabs, Session Records, auto-record, the L2 recorder, line lending) may hold at most 2 lines **of its own**. A line Claude and a tab both watch costs one line and counts as the desk's, so Claude can still move to another stock;
   - Claude's line is a held viewer reference on the depth line and the AllLast (Time & Sales) line, counted like a Session Record's (`capture.feed_hold`): never idle-evicted, never lent to a bot, never taken by auto-record;
   - a desk request refused for the reservation says so in words: "All 3 Level 2 lines are in use: SPIK and FLTX are yours, SMPL is Claude's. Close one of yours, or take Claude's line." It carries `agent_reserved: true`.
   - The tick-by-tick budget is not known in advance (#674), so the Time & Sales line is best effort: a refusal is shown and asked for again.

3. **Never take a line from the operator.** If the seat turns on while the desk already holds 3 lines, the seat waits ("Waiting for a Level 2 line") and takes the first line that frees. It never evicts a tab, a recording or a loan.

4. **The operator overrides.** **Take Claude's line** gives the seat up: Claude's lines are released, new entries are refused, and an open trade keeps its stop and still closes at 15:55. **Stop Claude** cancels Claude's orders, sells Claude's shares and turns the seat off. Both are on the desk (mockup approval pending) and the `/api/agent/trader` routes.

5. **Paper only, always.** Claude's sends follow the Live Trader bot (ADR 055): entries are `source: "bot"`, `origin: "claude"`, `expected_venue: "paper"`, so the door refuses them while the desk shows Live or Sim; closes are protective flattens (`source: "flatten"`) and cancels (`source: "cancel_working"`) that name Paper (`target_venue`), so they reach Claude's shares whatever the desk shows. `venue_door` refuses any `claude` send to Live in words. The Paper matcher fills resting Paper orders whatever the desk shows (`practice.matcher`), so a stop keeps working.

6. **Claude's shares are only Claude's.** Claude's position is what its own fills add up to (orders with `order_origin: "claude"`). Claude may not open a trade in a stock where Paper holds any other shares or any other working order, and its closes sell only its own shares (`intent: "flatten"` while the desk is on Paper, which the door holds to the position).

7. **Same gates as everyone, and its own limits.** Freeze all orders, the Bots loss line (ADR 063: Claude's fills count there, `by_of` reads `origin: "claude"` as the bots'), buying power, the desk's arm latch on Paper (Claude may arm Paper as an `agent`, never Live, ADR 018) and the backend's view lock (`market_view.gate.desk_lock`: the feed, the IB loop, the symbol's Time & Sales) all apply. Claude's own limits are checked before the door: long only; every entry carries a stop; at most 1,000 shares; at most $150 between entry and stop; 3 entries a day; no new entry once the day is -$400 (fees included); entries 07:00-15:30 ET; only on the seat's own stock, with its Level 2 live.

8. **Orders that do not need Claude's speed.** Claude is seconds to minutes slow, so the backend holds two entry kinds: a **limit** bracket sent at once, and a **break**: a trigger and a top price the seat watches every second; when a print reaches the trigger the seat sends the bracket at the top price. Both rest the stop and targets with the entry (`practice.bracket`, two halves when asked), so a fill is never unprotected. A break expires at its own time (default 30 minutes).

9. **If Claude goes quiet, Nova closes.** A lease that lapses (no check-in for 10 minutes) cancels Claude's orders, sells Claude's shares and releases the line. At 15:55 ET Nova does the same for any of Claude's shares (the day cover's time); the seat turns off at 16:00 ET.

10. **Claude is seen and heard.** `GET /api/agent/trader` answers the seat's state, stock, line, position, working orders, the day's tally, Claude's latest note and its recent events; the desk draws the header pill, the panel, the chart lines and the Sent by badge from it (mockup `F:\Nova\design\claude-seat\v1`, built only after the operator approves it).

## Scenarios

| Scenario | What happens |
|---|---|
| Seat on, desk holds 1-2 lines | Claude takes a free line; the desk keeps 2 of its own. |
| Seat on, desk holds 3 | Claude waits and says so; the first line the desk lets go is Claude's. |
| Operator opens a 3rd Level 2 while Claude holds one | Refused in words, with Take Claude's line. |
| Operator opens Claude's stock | Shares Claude's line; no extra line. |
| Claude moves to another stock | Old line released (its AllLast at once, #698), new line taken. A shared old line stays the desk's. |
| Desk switched to Live or Sim | Claude's entries refused (VENUE_CHANGED); its stop rests and fills on Paper; closes and cancels still reach Paper. |
| Operator or a bot holds the stock | Claude refuses to open a trade there. |
| Claude's session ends or hangs | Lease lapses after 10 min: Nova cancels, sells and frees the line. |
| Backend restarts | Seat and lease are read back; spend arming is not (ADR 018), so entries wait for a re-arm on Paper. |
| Gateway drops | Lines come back through `line_session`; entries refused while the view lock holds; stops still rest. |
| Freeze all orders / Bots loss line hit | Entries refused; closes still work. |
| 15:55 ET with shares | Nova sells them; 16:00 seat off. |
| A second Claude session | Its claim is refused while the first holder's lease is alive. |

## Consequences

- The desk has 2 Level 2 lines while Claude trades. The operator can take the third back at any time.
- Claude's trades read apart from the operator's and the bots' everywhere, and count against the Bots loss line.
- Claude never trades Live. Nothing here changes `auto_live` (NO-GO) or the Live arm.
- Claude's reasoning is kept off the repository; the desk shows only the one-line note Claude sends.
