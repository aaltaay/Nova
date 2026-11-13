# ADR 071 -- Three lanes for Level 2: yours, Claude's, the bots'

**Status:** Accepted (the design; the build follows in the order below) · **Date:** 2026-11-12
**Replaces:** [[023-scanner-leaderboard]] decisions 5-6 (auto-record of the leaders) · [[041-signal-trials]] decision 2
("Auto-record takes setups first") · [[044-one-bots-page]] decision 6 (line lending) ·
[[068-claude-trades-paper-from-its-own-seat]] decisions 3 and 14 (Claude takes an auto-record line; a hidden tab's line)
**Amends:** [[068-claude-trades-paper-from-its-own-seat]] decision 2 (Claude's line is kept whether the seat is on or
off) · [[020-three-venues-one-feed]] (a resting Paper order holds no tape line) ·
[[070-the-phone-reaches-the-desk-over-a-private-tunnel]] (the phone is one of the operator's surfaces)
**Decided by:** the operator, 2026-11-12, on the phone, holding 100 XLAB on Paper while its Time & Sales read
"Resubscribing in 10s -- please wait": "this is dangerous ... as a human who is trying to open, if I can, a slot, it has
to be instant. We have to prioritize one lane specifically for a human, almost always unused. If I think the logic is
complicated and if it is, I think we need to shorten it and make it better but don't rush please". Then: "I need one
empty lane for me! One empty lane for Claude training and one lane for bots trading .. keep it simple". On recording:
"the recording only starts when bots, Claude, or I are watching at level 2. We don't need random recorders when
nobody's watching anything". Asked whether they may use Claude's or the bots' lane while it sits empty, they chose no:
strict lanes. Asked where the lane goes when they hold a stock with an order resting and open another, they chose
that it moves, and the resting order fills from Level 1 (decision 9).

## Context

- **IBKR gives three lines of each kind.** Three Level 2 lines (`IBKR_MAX_DEPTH_SYMBOLS`) and, on this account, three
  tick-by-tick Time & Sales lines (learned from IBKR's 10190 refusals, `ibkr/tape_admission.py`).
- **Seven kinds of holder ask for them**, each with its own rule for taking, keeping and giving up a line: a Trader
  tab's socket, a Session Record (`capture/feed_hold.py`), auto-record (`leaderboard/auto_record.py`), a loan to a
  setup (`line_lending/loans.py`), Claude's seat (`agent_trader/lines.py`), a loan to Claude
  (`line_lending/claude_loan.py`), and a resting Paper order's tape hold (`practice/tape_hold.py`).
- **Claude has a line kept for it; the operator does not.** While the seat is on, every other holder may hold two
  (`agent_trader.lines.desk_cap`). The operator gets a line by auto-record giving one up
  (`auto_record.make_room_for`), each time they open a stock.
- **What happened on 2026-11-12** (`backend/logs/blast.log`, Eastern time):

  | Time | What the log shows |
  |---|---|
  | 12:12:33 | The phone opens XLAB. Auto-record stops recording TGHL to give up a line. |
  | 12:13:20 | The phone unlocks; the operator buys 100 XLAB on Paper. |
  | 12:14:50 | The phone's page goes to the background. Its Level 2 line is let go after 0.75 s (`IBKR_DEPTH_RELEASE_GRACE_SEC`). |
  | 12:15:02 | Auto-record takes that line for TGHL. |
  | 12:15:04 | XLAB's tape line is cancelled, "no viewer left": 16 s after the last viewer (`IBKR_TAPE_LINGER_SEC`). |
  | 12:15:06 | The phone is back. Level 2 returns in 2 s (auto-record stops TGHL again). The tape may not be asked for until 12:15:20. |

  In five minutes the phone's coming and going stopped and restarted TGHL's recording three times.
- **The wait is IBKR's rule, met by Nova's own cancel.** IBKR: "No more than 1 tick-by-tick request can be made for the
  same instrument within 15 seconds." Nova refuses a new request for 16 s after its own cancel
  (`IBKR_TAPE_RESUBSCRIBE_GUARD_SEC`). A viewer who returns 16 to 32 s after leaving meets a dead tape for up to 16 s.
  Whether IBKR counts from the previous request or from the cancel is not measured.
- **Auto-record does two jobs under one name.** Its `trade`, `near` and `armed` tiers hold the Level 2 a bot needs: a
  bot fires only on a stock whose depth line the backend holds (`bot/eligibility.py`, `BOT_NO_DEPTH_LINE`), and the
  setup scanner's tape gate reads only lines the desk already holds (it reads `blind` without one, ADR 022). Its
  `leader` tier records the top gainers whether or not anyone watches them.
- **Recording is started three ways:** by hand (`POST /api/capture`), by auto-record, and the Level 2 pane's own
  `l2.continuous` session, which follows the socket and not the line.
- **A resting Paper order needs its stock's prints to fill**, so it holds a tape line of its own
  (`practice/tape_hold.py`). When its tape misses trades the matcher already fills from IBKR's Level 1 Last
  (`fill_basis: "l1_last"`, ADR 045 amendment 2026-10-14).

## Decision

1. **Three lanes, three owners.** A lane is one Level 2 line and one Time & Sales line on the same stock. Lane 1 is the
   operator's, lane 2 is Claude's seat's, lane 3 is the bots'. No holder takes, borrows or is lent another's lane, and
   an empty lane stays empty (the operator: strict). One module owns which stock each lane is on; nothing else
   subscribes or cancels a live Level 2 or tape line.
2. **The operator's lane is on the last stock they opened**, on the PC or the phone. It is set by a Level 2 or
   Time & Sales socket from one of the operator's surfaces that says it is in front (`front=1`). A hidden tab, or a
   page in the background, never moves it.
3. **The operator's lane has no timer.** Closing the pane, hiding the tab, locking the phone or losing the link changes
   nothing: both lines stay up on that stock. The lane moves only when the operator opens another stock, and then at
   once: the old stock's two lines are cancelled and the new stock's are asked for in the same step.
4. **A pane on a stock the lane is not on says so** ("Your Level 2 is on XLAB") and offers to bring the lane to it.
   It never takes the lane by itself while another of the operator's panes is in front, so two visible windows do not
   take the lane from each other in a loop.
5. **Claude's lane is kept for the seat whether it is on or off.** It is on the stock the seat names (ADR 068
   decision 2, unchanged) and empty otherwise. Claude never waits for the desk to give up a line, and never takes a
   tab's.
6. **The bots' lane goes to one setup at a time**, chosen as auto-record chose (`auto_record_picks`): a setup in a
   trade first, then one near its trigger, then one armed; only setups of a template in play. A setup in a trade keeps
   the lane until its trade ends. With no such setup the lane is empty. A setup that has no lane says so on its row
   (`blind`, and why), as today.
7. **A stock two owners watch costs one pair of lines.** Each owner's lane counts as on it; the other physical lines
   stay unused. Letting go by one owner never ends the line while another is on it.
8. **Recording follows the lanes.** While recording is switched on (Records: On / Off for today / Off, unchanged), a
   stock is recorded for as long as it is on a lane and stops, as a planned stop, when it leaves. Each stay is a
   segment of that stock's day. There is no recorder of stocks nobody watches: the `leader` tier, its windows and the
   Record of a stock that is on no lane are removed. `l2.continuous` follows the lane, not a socket.
9. **A resting Paper or Sim order holds no line.** It fills on its stock's prints while that stock is on a lane, and on
   IBKR's Level 1 Last otherwise (`fill_basis: "l1_last"`, the existing stand-in). An order never waits for a line.
10. **IBKR's 15-second rule stays, and is said in its own words.** A stock whose tape Nova cancelled may not be asked
    for again for 16 s; the pane says how long. The guard moves to "since the last request" only after a measurement
    on a stock nobody watches shows IBKR accepts it.

## What this removes

- `leaderboard/auto_record.py`'s leader tier, windows, `make_room_for`, `yield_to_agent`, `free_lines`, the yield hold
  and the failed-start pause; the setup picker stays, as the bots' lane.
- `line_lending/`'s loans (`loans.py`, `claude_loan.py`, `borrowers.py`, `line_moves.py`, `loan.py`, `loan_tape.py`,
  `focus.py`, `sockets.py`, `socket_gate.py`, `setting.py`, `view.py`) and the lending switch. `tape_heal.py`'s re-ask
  of a refused, ended or silent tape line stays; its making of room goes.
- `agent_trader/room.py`, `agent_trader/tab_line.py`, `lines.desk_cap` / `desk_refusal`, and the take-back route.
- `practice/tape_hold.py`.
- The tape's 16 s linger and the depth's 0.75 s grace as ways a line ends; `evict_for_capacity`.
- On screen: the lent sentences and LENT badge, "Take my Level 2 back from Claude", "Take Claude's line" and the
  all-lines-in-use box, the Bots page's lines card and lending switch, the auto-record card and its "auto" rows, and
  the Record of market data from the tab's Record menu (the video clip stays).

## Scenarios

- **The phone leaves and returns.** The page goes to the background for 25 s. Both XLAB lines stay up; the tape and
  the book are live the moment the page is back. Nothing was recorded twice.
- **The operator opens another stock while holding one.** They hold 100 XLAB with a sell resting at 1.43 and open
  TGHL. The lane moves to TGHL. XLAB keeps its quote, its position line and its P&L; the resting sell fills from
  Level 1's Last; Sell, Flatten and Cancel always go (ADR 045). XLAB's pane, if still open, says the lane is on TGHL.
- **Back to the first stock within 16 seconds.** Level 2 is back at once; Time & Sales says "IBKR allows XLAB's tape
  again in 9 s".
- **Two setups arm at once.** One gets the bots' lane; the other's row says it has no Level 2 and why. When the first
  disarms or its trade ends, the lane goes to the next.
- **Claude's seat is off all day.** Lane 2 is empty all day. Nobody else uses it.
- **The operator and a bot are on the same stock.** One pair of lines. The operator opens another stock: the bot's
  setup keeps both lines.

## Consequences

- **Far fewer recordings.** Only what the operator, Claude or a bot watched, for as long as they watched. The leaders'
  recordings stop.
- **The bots see one setup at a time.** Signal trials (ADR 041) score fewer setups with a live tape.
- **The operator has one stock with Level 2 at a time**, on the PC and the phone together.
- **A stock held but not on the lane has no Level 2.** Its exits always go; a new buy on it is refused as any buy
  without a live view is (ADR 045).
- **A resting Paper order off-lane fills on Level 1's Last**, which reports fewer trades than Time & Sales. Paper then
  fills when Live would, wherever the operator is looking.
- **Opening a stock never waits on another holder.** The only wait left is IBKR's own 15 seconds on a tape Nova
  cancelled within the last 16.

## Rejected

- **Borrowing an empty lane** (the operator's second stock on Claude's or the bots' lane while idle). It keeps a lend,
  a recall and a "taken back" state alive. The operator chose strict lanes.
- **Keeping the operator's lane on a stock while an order rests there.** The operator could not look at a second stock
  without cancelling their stop. Offered both, the operator chose the lane that moves.
- **A shorter linger, or a longer one.** Any timer that cancels the operator's line meets IBKR's 15 seconds on the way
  back.

## Amendment 2026-11-13: what "watching" means, decided by the operator

The operator, seeing REC chips on DGXX, SSII and VTSI that nobody watched: "if a bot is watching a specific stock, if a
human is watching a stock, or if we're looking at a stock only, then we start the recordings". Then: "I need the
level 2 lane to always be for a human because a human could be trading on the web application, and a human could be
working on the desktop". Asked what each word means, they chose:

1. **A bot watches only what a bot may buy** (amends decision 6). A setup qualifies for the bots' lane only when its
   strategy is at effective On, the venue's bot is active, Nova may buy on that venue and the stock's Buy is Nova --
   then a setup in a trade first, near second, armed third. A setup a bot only watches (Eyes, a watch-only template
   such as the pullback dip, #847) never takes the lane. A stock Nova holds a trade in keeps the lane until it is flat;
   a better tier takes the lane from an armed or near stock only; a read that fails moves nothing.
2. **You watch a stock while a Trader tab you can see shows it** (amends decision 8 for your lane). Your lane's stock
   is recorded while a desk window shows it in front, or a socket opened in front on it (the phone, a browser) is
   still open and no desk window lists it as a hidden tab -- and for 5 minutes after (`LANES_YOU_RECORD_TAIL_SEC`).
   Your lane's lines stay up all the while (decision 3); only the recording stops. Claude's and the bots' lane stocks
   are recorded while on the lane, as decision 8 says.
3. **Record by hand needs a lane on the stock.** `POST /api/capture` refuses a stock no lane is on (409, in the lanes'
   words); the keepalive resumes a recording only while a lane holds its stock, and says why it gave up otherwise.
4. **A resting Paper or Sim order keeps a Level 1 line** (owner `practice`) and the tape archive's watch, so decision
   9's Level 1 Last has a quote to read off-lane. It holds no Level 2 and no Time & Sales line.
5. **A socket never ends a lane's line.** A socket that closes ends its line only when no lane is on its stock (a Sim
   replay slot, or a test with the lanes off).
6. **`evict_for_capacity` stays, as a guard against leaked lines** (amends "What this removes"): it cancels only a line
   no lane, socket or recording holds, and never a lane's.
7. **Decision 10's measurement is not made yet.** The 16 s guard stays as it is until it is.

## Build order

1. Measure IBKR's rule (decision 10) after 20:00 ET on a stock nobody watches.
2. Schema first: `recording-and-replay.md`, `market-data.md`, `agent-trader.md`, `bot.md`, `scanner.md`,
   `desk-ops.md`, `execution.md`.
3. The lanes on the backend, recording on the lanes, the removals above; the panes keep working with the words they
   have.
4. The screens (Records, the Bots page, the "your Level 2 is on" pane, the tab's Record menu), mockup first.
