# ADR 068 -- Claude trades Paper from its own seat

**Status:** Accepted · **Date:** 2026-10-26 · **Amended:** 2026-10-27 (decision 3: an auto-record line; decision 12: the eye; decision 13: the guard and the pop exit; decision 14: a hidden tab's line)
**Amends:** [[044-one-bots-page]] (decision 6: the seat's line is never lent; a hidden tab's line may be Claude's, decision 14, and the front does not recall that loan) · [[063-a-loss-line-for-you-and-one-for-the-bots]] (Claude's fills count on the Bots line)
**Builds on:** [[007-centralized-trading-execution]] · [[018-desk-venue-vs-spend-arming]] · [[045-orders-refuse-a-stale-view]] · [[055-the-live-trader-bot]] (the Paper-only send pattern) · [[050-agents-find-and-show-in-the-sim]] (the `/api/agent` door and its key)
**Decided by:** the operator, 2026-10-26 (about 20:00 ET). They asked Claude to trade Paper itself: "i want to ask you to be the one who uses your brain and place trades on paper". Then: "i agree.. lets do it ... you need to make your presence known." Then: "we only got 3 symbols to look at level 2, and you will need to control one of them.. and lock it so human wont be able to just open like 3 and you have taken one ... please think about every scenario." Limits as proposed and agreed: up to 1,000 shares, at most $150 risk a trade, 3 trades a day (removed 2026-10-27, Amendment below), long only, Paper only. On the day's max loss: "only activate this feature on a paper account without a max loss", then "i guess do a max loss of $500! for claude lane.." -- Claude's lane stops itself at -$500 a day, and the desk's shared loss lines do not stop its buys on Paper.

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

3. **Never take a line from the operator; take an auto-record line (amended 2026-10-27).** If the seat names a stock
   while the desk already holds 3 lines, the seat takes an **auto-record** line: of the auto-record lines whose
   only viewer is auto-record's own hold (stopping it frees the line), the one the desk has had in front least
   recently -- never in front counts as longest idle --, ties broken by auto-record's own lowest rank
   (`leaderboard.auto_record.yield_to_agent`). The recording stops as planned (segment `reason: "auto"`), the
   Records page lists it as yielded to Claude, and the reservation keeps auto-record from taking it back. With no
   such auto line the seat waits ("Waiting for a Level 2 line") and takes the first line that frees. It still never
   takes a Trader tab's line, a Session Record the operator started, the L2 recorder or a loan. Why: on 2026-10-27
   the desk and auto-record held all 3 lines and the seat waited all morning ("waiting_line"). With no auto line,
   a hidden Trader tab's line is next (decision 14).

4. **The operator overrides.** **Take Claude's line** gives the seat up: Claude's lines are released, new entries are refused, and an open trade keeps its stop and still closes at 15:55. **Stop Claude** cancels Claude's orders, sells Claude's shares and turns the seat off. Both are on the desk (mockup approval pending) and the `/api/agent/trader` routes.

5. **Paper only, always.** Claude's sends follow the Live Trader bot (ADR 055): entries are `source: "bot"`, `origin: "claude"`, `expected_venue: "paper"`, so the door refuses them while the desk shows Live or Sim; closes are protective flattens (`source: "flatten"`) and cancels (`source: "cancel_working"`) that name Paper (`target_venue`), so they reach Claude's shares whatever the desk shows. `venue_door` refuses any `claude` send to Live in words. The Paper matcher fills resting Paper orders whatever the desk shows (`practice.matcher`), so a stop keeps working.

6. **Claude's shares are only Claude's.** Claude's position is what its own fills add up to (orders with `order_origin: "claude"`). Claude may not open a trade in a stock where Paper holds any other shares or any other working order, and its closes sell only its own shares (`intent: "flatten"` while the desk is on Paper, which the door holds to the position).

7. **Same gates as everyone, and its own limits.** Freeze all orders, buying power, the desk's arm latch on Paper (Claude may arm Paper as an `agent`, never Live, ADR 018) and the backend's view lock (`market_view.gate.desk_lock`: the feed, the IB loop, the symbol's Time & Sales) all apply. Claude's lane has its own daily max loss: no new entry once its day is -$500 (fees included); the desk's shared loss lines (ADR 063) do not refuse Claude's buys on Paper (`loss_limit.gate.buy_refusal` with `origin: "claude"`), while Claude's fills still count in the Paper account's totals and on the Bots line's figures. Claude's other limits, also checked before the door: long only; every entry carries a stop; at most 1,000 shares; at most $150 between entry and stop; no daily trade count (Amendment, 2026-10-27; it was 3 entries a day); entries 07:00-15:30 ET; only on the seat's own stock, with its Level 2 live.

8. **Orders that do not need Claude's speed.** Claude is seconds to minutes slow, so the backend holds two entry kinds: a **limit** bracket sent at once, and a **break**: a trigger and a top price the seat watches every second; when a print reaches the trigger the seat sends the bracket at the top price. Both rest the stop and targets with the entry (`practice.bracket`, two halves when asked), so a fill is never unprotected. A break expires at its own time (default 30 minutes).

9. **If Claude goes quiet, Nova closes.** A lease that lapses (no check-in for 10 minutes) cancels Claude's orders, sells Claude's shares and releases the line. At 15:55 ET Nova does the same for any of Claude's shares (the day cover's time); the seat turns off at 16:00 ET.

11. **Flash decisions on Level 2 (reflexes).** The operator: "im hoping you are going to also watch level 2 and make
    'flash' decisions". Claude looks every minute or two, so on each look it arms conditions on its own stock and the
    seat judges them twice a second on the live book and the last prints, acting at once: `bid_pulled` (the bids at a
    price and up, added across market makers, fall under a size they held since arming), `ask_wall` (a seller of a size
    shows at or under a price), `sellers` (shares hitting the bid outweigh the ask by a ratio in the last seconds),
    `last_below` (a print at or under a price). Each either sells all of Claude's shares or calls off its buy, once. A
    break may carry `confirm` (buyers lifting the ask lead by a ratio in the last seconds) and then sends only while
    they do. Claude's judgment sets them; Nova pulls the trigger.

10. **Claude is seen and heard.** `GET /api/agent/trader` answers the seat's state, stock, line, position, working orders, the day's tally, Claude's latest note and its recent events; the desk draws the header pill, the panel, the chart lines and the Sent by badge from it (design `F:\Nova\design\claude-seat\v2`, drawn on the real desk and approved by the operator 2026-10-26).

12. **Claude sees the whole market at once (the eye, 2026-10-27).** The operator, driving the seat from a chat, asked for
    a "god eye": Claude should see every stock the scanner follows and move its one line to whatever is moving.
    `GET /api/agent/trader/eye` (read-only, loopback, opens no line) answers every symbol in the live scanner universe
    -- the Gappers, Gainers and After Hours rows and the setup scanner's universe (HOD Momo's active set) -- with its
    last price, day move, the price change and dollar volume over the last 10, 30 and 60 seconds, float, spread,
    halt and catalyst, spikes ranked first, and a list of spike events. A **spike** is a move of
    `AGENT_EYE_SPIKE_MOVE_PCT` (2%) or more, either way, over `AGENT_EYE_SPIKE_SECONDS` (60 s) with at least
    `AGENT_EYE_SPIKE_MIN_DOLLARS` ($50,000) traded in it (`constants_agent_trader`). Every number is IBKR's: the
    Level 1 line's last and cumulative day volume, sampled on each print (`hod_momo_metrics`, one hour kept), so the
    dollar volume is each day-volume step times the last that came with it; a window the samples do not reach back
    across is null, never filled in. The watcher scans once a second while the seat is on, so a spike between
    Claude's looks is still listed; `?wait=` long-polls for the next one. The eye only reads: Claude still moves its
    line with `POST /watch`.

13. **Nova guards Claude's open trade, and the pop exit (2026-10-27).** The operator, after Claude's scratch watcher
    closed AIOK at 12.87 for -$40 against -$140 at the hard stop, asked for it in Nova permanently. While Claude holds
    shares, every watcher pass (0.5 s) judges three conditions on the live book and the last prints and sells Claude's
    shares at market the moment one holds, with no arming and no Claude in the loop (`agent_trader.guard`):
    sellers lead (at least 2x what lifted the ask, and 1,500 shares or more at the bid, in the last 5 s); the bids
    leave (the top 5 bid prices hold under a third of their size when the position was first seen); the best bid
    0.4% or more under Claude's entry (its average buy since it was last flat). The thresholds are constants
    (`AGENT_GUARD_*`). A condition with nothing to read (no book, a Level 1 stand-in, no prints) is not judged; the
    bracket's stop still rests. Every close is a `reflex_fired` event the desk toasts and speaks ("Nova's guard on
    AIOK: sellers lead: ... -- sold 500 AIOK at market"). An entry may also carry `exit: "pop"`: half the shares
    (rounded down) at `pop_pct` over entry (default 1.5%, `AGENT_POP_PCT_*`), the rest at Claude's target, and the stop rises
    to Claude's entry once the first half sells or at the first stall: the price reached +1% over entry, then no new
    high for 30 s (`AGENT_GUARD_STALL_AFTER_PCT`, `AGENT_GUARD_STALL_SEC`; the operator's rule, 2026-10-27).

14. **A hidden Trader tab's line, kept until the operator takes it back (2026-10-27).** With all 3 lines held and no
    auto-record line to give (decision 3), the seat borrows the Level 2 and Time & Sales of a Trader tab the
    operator is not looking at, picked by a bot loan's rule (ADR 044 decision 6, `line_lending.lines.pick_lender`):
    hidden, not in front in the last 30 s, the tab looked at least recently, one that can give its Time & Sales too
    first; never a tab on a stock a bot's setup or Nova's own trade needs, never one the operator took back while it
    stays open (`line_lending.claude_loan`, `agent_trader.tab_line`). The tab reads "Level 2 lent to Claude
    (watching RUNR) -- back when Claude lets it go, or right-click this tab to take it back" (also "buy set on",
    "in a trade on"), its chip says "L2 · Claude", the pill "Claude · Watching RUNR · on your SMPL tab's line".
    **Bringing the tab to the front does not take it back**, whether Claude holds shares or only watches. The
    operator, shown both options (back at once; kept while Claude holds shares): "no unless i explicity right
    click and stop claude from holding the lane, let claude take care of it, the point is not to distrub claude
    while it learns from level 2". The loan ends only when the operator right-clicks the tab or its lent pane --
    **Take my Level 2 back from Claude** (`POST /api/agent/trader/take-back`): that line only; Claude stays on, its
    stop and targets keep resting, it waits for another line, and the tab's Level 2 is admitted past Claude's
    reservation --, when Claude's seat lets its line go (off, given up, gone quiet, the day's end), or when the tab
    closes. Lending's switch is the bots' and neither makes nor ends it. Design `F:\Nova\design\claude-seat\v3`,
    approved by the operator 2026-10-27.

## Scenarios

| Scenario | What happens |
|---|---|
| Seat on, desk holds 1-2 lines | Claude takes a free line; the desk keeps 2 of its own. |
| Seat on, desk holds 3, one is auto-record's | Claude takes the auto line idle longest; the recording stops as planned. |
| Seat on, desk holds 3, none is auto-record's, a Trader tab hidden 30 s+ | Claude borrows that tab's Level 2 and Time & Sales; the tab says so, and still does in front. |
| The operator right-clicks that tab: Take my Level 2 back from Claude | The tab's lines come back at once; Claude stays on, its stop and targets rest, it waits; that tab is not taken again while open. |
| Seat on, desk holds 3, no auto-record line, no hidden tab | Claude waits and says so; the first line the desk lets go is Claude's. |
| A stock spikes between Claude's looks | The eye lists the spike event; Claude moves its line with `POST /watch`. |
| Operator opens a 3rd Level 2 while Claude holds one | Refused in words, with Take Claude's line. |
| Operator opens Claude's stock | Shares Claude's line; no extra line. |
| Claude moves to another stock | Old line released (its AllLast at once, #698), new line taken. A shared old line stays the desk's. |
| Claude moves off a line a tab or auto-record shares, all 3 in use | Claude keeps its reference on the old line (its slot: letting it go would free nothing) and moves once a line frees or an auto-record line is given up (amended 2026-10-27; SXTP -> AIOK left the seat waiting). |
| Desk switched to Live or Sim | Claude's entries refused (VENUE_CHANGED); its stop rests and fills on Paper; closes and cancels still reach Paper. |
| Operator or a bot holds the stock | Claude refuses to open a trade there. |
| Claude's session ends or hangs | Lease lapses after 10 min: Nova cancels, sells and frees the line. |
| Backend restarts | Seat and lease are read back; spend arming is not (ADR 018), so entries wait for a re-arm on Paper. |
| Gateway drops | Lines come back through `line_session`; entries refused while the view lock holds; stops still rest. |
| Freeze all orders | Entries refused; closes still work. |
| Claude's day at -$500 | Its lane is done for the day: no new entries; open trades keep their stops. |
| Claude's 4th (or 40th) trade of the day | Allowed: no daily trade count (2026-10-27); only the -$500 day stop ends Claude's day. |
| The desk's shared loss line trips on Paper | Your and the bots' buys stop; Claude's lane runs to its own -$500. |
| 15:55 ET with shares | Nova sells them; 16:00 seat off. |
| A second Claude session | Its claim is refused while the first holder's lease is alive. |
| Claude holds shares and sellers hit the bid | Nova's guard sells within half a second and says which condition held. |
| A pop exit's first half sells | The stop rises to Claude's entry. |
| The book turns between Claude's looks | An armed reflex acts within half a second; a break with a confirm waits while sellers lead. |

## Consequences

- The desk has 2 Level 2 lines while Claude trades. The operator can take the third back at any time.
- Claude's trades read apart from the operator's and the bots' everywhere. Its losses still count in the Paper account's total, so a bad Claude day can trip your shared Paper line (your Paper buys stop at its limit; Claude's lane does not).
- Claude never trades Live. Nothing here changes `auto_live` (NO-GO) or the Live arm.
- Claude's reasoning is kept off the repository; the desk shows only the one-line note Claude sends.

## Amendment, 2026-10-27: no daily trade count

The operator, 2026-10-27: "that 3 trades a day limit need to be removed all over the place actually", and "u have infinite trades so we LEARN!". Claude's 3-entries-a-day limit (decision 7) is removed:
`AGENT_MAX_ENTRIES_A_DAY` is `None` (no cap), and an int there caps the count again (filled entries, working
entries and armed breaks, as before). The status's `today.max_entries` is null; `done` now trips only on the
-$500 day stop. Everything else in decision 7 stands: the -$500 day stop, 1,000 shares, $150 between entry and
stop, long only, the 07:00-15:30 ET window, the seat's own stock with its Level 2 live, Paper only. The same day
the bot sleeve's daily cap went too (ADR 042 amendment of this date).
