# Data schema: Claude's seat

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owner: `backend/agent_trader/`. Same
law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1
and #5).

## Claude trades Paper from its own seat (ADR 068, operator decision 2026-10-26)

One AI trader, Claude, holds a seat on the desk: one of the 3 Level 2 lines, locked for it, and orders on **Paper
only**. Every send goes through `execution.service` in the Live Trader bot's shape (ADR 055); nothing here reaches
Live.

**Routes** (`/api/agent/trader`, loopback only; every write needs the desk's API key, `auth.is_agent_mutate`).
Claude's own writes also carry `X-Agent-Seat: <token>`; the operator's three buttons need no token.

| Route | Who | Answers |
|---|---|---|
| `GET /api/agent/trader` | anyone local | the status below |
| `GET /api/agent/trader/look?symbol=&seconds=120` | anyone local | `{symbol, at, line: {depth, tape, claude_holds, book_at}, quote: {last, bid, ask}, book: {bids, asks, l1_fallback, at_limit}, luld}` (top 10 rows each, the depth module's own rows), `tape: {seconds, summary: {prints, volume, high, low, vwap, at_ask, at_bid}, prints: [{ts, price, size, side?, exchange?, bid?, ask?, conditions?}]}` (newest 200), `locked}` (the view lock's answer or null). `luld` and `at_limit` as in "The LULD band" below. Opens no line. |
| `GET /api/agent/trader/eye?wait=0&after=` | anyone local | the eye below: every symbol the scanner follows, spikes first, and the spike events. `wait` (0-30 s) long-polls: the answer comes once a spike event newer than `after` (epoch seconds) is listed, or when `wait` runs out. Opens no line. |
| `GET /api/agent/trader/journal?day=YYYY-MM-DD` | anyone local | the journal below for `day` (default today) plus `open`: the trades open now. Refused (`AGENT_REFUSED`) when the day's file cannot be read |
| `POST /seat?take_over=` | Claude | `{token, status}`; with `take_over=true` a held seat is picked up (a new token, the old one stops; stock, breaks, reflexes, orders and shares kept). Without it: refused (`AGENT_SEAT_TAKEN`, 409) while another holder's lease is alive, and outside weekdays 04:00-16:00 ET (`AGENT_SEAT_OFF`) |
| `POST /beat` | Claude | status; renews the lease |
| `DELETE /seat` | Claude | `{problems, status}`: cancels Claude's orders, sells its shares, frees the line, seat off |
| `POST /watch {symbol}` | Claude | status; the seat's stock (refused while Claude has orders or shares on another) |
| `POST /note {text}` | Claude | status; one line (<= 400 chars) the desk shows |
| `POST /arm` | Claude | status; arms the desk on Paper as `actor: "bot"` (ADR 018). Refused off Paper and when the operator locked the padlock (`ibkr.safety.locked_by() == "operator"`). |
| `POST /order` | Claude | `{order_id, stop_order_id, warnings, status}` (a limit) or `{break, warnings, status}` (a break); `warnings` lists Nova's words (never a refusal) when the buy's price is within `AGENT_LULD_WARN_PCT` (1%) of the upper LULD band or over it. Body: `{kind: "limit" \| "break", symbol, qty, entry (limit), trigger + top (break), stop, target, target2?, target1_qty?, minutes? (break life, default 30, max 240), confirm? {seconds <= 60, shares, ratio} (a break), exit? "pop", pop_pct? (0.5-5, default 1.5), why}`. With `exit: "pop"` Nova sets `target` to entry x (1 + pop_pct/100), `target1_qty` to half the shares rounded down and `target2` to Claude's `target` (refused under 2 shares, or with a target at or under the pop) |
| `POST /reflex {kind, action, price?, shares?, seconds?, ratio?, minutes?, why}` | Claude | `{reflex, status}`: a reflex on the seat's stock (`kind` one of `bid_pulled` {price, shares}, `ask_wall` {price, shares}, `sellers` {seconds <= 60, shares, ratio}, `last_below` {price}; `action` `sell_all` or `cancel_buy`; default life 60 min, at most 390; 6 at most) |
| `DELETE /reflex/{id}` | Claude | status |
| `POST /stop {order_id, stop}` | Claude | status; raises Claude's own stop leg (never lowers it) |
| `DELETE /order/{id}` | Claude | status; cancels Claude's own working order |
| `DELETE /break/{id}` | Claude | status |
| `POST /close {symbol}` | Claude | status; cancels Claude's orders on it, sells Claude's shares at market |
| `POST /yield` | operator | status; "Take Claude's line": unfilled buys and breaks cancelled, lines released, no new trades; held shares keep their stop |
| `POST /give-back` | operator | status |
| `POST /stop-claude` | operator | `{problems, status}`: as `DELETE /seat` |
| `POST /take-back {symbol}` | operator | status; the right-click on a Trader tab whose line Claude borrowed (decision 14): that tab's lines come back, Claude stays on and waits. `AGENT_NOT_MINE` (404) when the tab's line is not lent to Claude, or when a tab of the operator's shares Claude's line (letting Claude go would free nothing; the error says to close that Level 2 first) |

The Level 2 socket's error frame gains `agent_reserved` (true when the desk's request waits for Claude's line), so the panel can offer Take Claude's line.

Refusals are `{detail: {reason, error}}` with `reason` one of `AGENT_SEAT_TAKEN`, `AGENT_NOT_HOLDER` (403),
`AGENT_SEAT_OFF`, `AGENT_YIELDED`, `AGENT_LIMIT`, `AGENT_NOT_PAPER`, `AGENT_NO_LINE`, `AGENT_NOT_MINE`, `AGENT_STALE`,
`AGENT_REFUSED`, `AGENT_HALTED` (the stock is halted, decision 17), or the execution door's own code; `error` says why in words.

**Status** (`schema_version: 1`): `{generated_at, name: "Claude", venue: "paper", state, text, on, since, beat_at,
lease_until, lapsed, yielded, symbol, line: {symbol, depth, tape, why_not, desk_lines, desk_cap, all_lines, from_tab,
taken_back},
positions: [{symbol, qty, mark}], working: [{order_id, symbol, side, order_type, qty, limit_price, stop_price,
leg_role, status, parent_id}], breaks: [{id, symbol, qty, trigger, top, stop, target, target2, target1_qty,
expires_at, created_at, why, confirm}], reflexes: [{id, symbol, kind, action, price, shares, seconds, ratio, why, expires_at, created_at, text}], exits: {SYMBOL: {mode: "pop", pop_pct}}, today: {entries, max_entries (null: no daily trade count, 2026-10-27), pnl, day_stop, fills}, limits: {max_shares,
max_risk_usd}, note: {text, at} | null, events: [{at, kind, text}] (newest first, 12), read_error}`. `read_error`, `line.why_not` and every refusal are Nova's own words: an exception's text never reaches this wire (it goes to the log). `state` is one
of `off`, `idle` (no stock yet), `waiting_line`, `watching`, `buy_set`, `in_trade`, `yielded`, `done`; `text` is the
header pill's words ("Claude · Buy set SMPL 4.39" -- the price a break triggers at or a resting buy's limit --,
"Claude · In SMPL +$42.00"). The holder token is never in it.

**On the desk** (`frontend/src/claude_seat/`, approved design `F:\Nova\design\claude-seat\v2`): one poll of this
route every 1.5 s (6 s while the window is hidden) feeds the header pill and its panel (Take Claude's line, Give it
back, Stop Claude after a confirm), Claude's toasts and voice (the header mute silences it), its order and break lines
on the 10-second, 1- and 5-minute charts, the violet frame on its Level 2, the lines-full box (`agent_reserved`) and
"Claude" in Sent by (`order_origin: "claude"`).

**Claude's limits** (checked before the door, `agent_trader.rules`): long only; every entry a bracket with its stop
and one or two targets; whole shares, at most 1,000; at most $150 between entry and stop; no daily trade count
(operator, 2026-10-27: "u have infinite trades so we LEARN!"; `AGENT_MAX_ENTRIES_A_DAY` is `None`, and an int there caps filled entries, working
entries and armed breaks again); Claude's lane's own daily max loss -- no new entry once its day is at -$500 or worse, fees included (the desk's shared loss lines do not refuse Claude's buys on Paper: `loss_limit.gate.buy_refusal(origin="claude")`);
entries 07:00-15:30 ET on weekdays; only on the seat's stock with Claude's Level 2 line live; never where Paper holds
shares or working orders that are not Claude's; never while the view lock holds (`market_view.gate.desk_lock`).

**Sends.** Entries `operation: "bracket"`, `source: "bot"`, `origin: "claude"`, `expected_venue: "paper"`; stop
moves `replace` the same way; closes `source: "flatten"` market SELLs and cancels `source: "cancel_working"`, both
`target_venue: "paper"`. `execution.venue_door` refuses any `claude` send while the desk is not on Paper and any
`claude` close named to Live. Practice rows carry `order_origin: "claude"`; Claude's position is its own fills, never more than Paper holds in the stock: Nova's own closes (the loss limit's Auto sell, KILL, a margin call) sell Claude's shares under their own origin, and Claude's P&L counts those shares at the price those closes got.
Claude's fills still count in the Paper account's loss-limit totals and on the Bots line's figures (`loss_limit.accounts.by_of`, `LOSS_LIMIT_BOT_CLOSE_ORIGINS`), but no shared line refuses Claude's buys on Paper.

**Events** (`kind`): `on`, `off`, `watch`, `line`, `line_wait`, `armed`, `buy_set`, `break_set`, `break_wait`, `break_end`, `refused`, `stop`, `cancel`, `close`, `fill` ("Claude bought 510 SMPL at 4.40", each fill said once), `resumed` (read back after a restart), `taken_over`, `reflex_set`, `reflex_fired` (also the guard's closes), `reflex_end`, `yielded`, `line_back`, `day_close` and `close` (also each journaled trade: "trade on SMPL closed +$8.00: manual (Claude closed it at market)"), `line_taken` ("took KTTA's auto-record line for SMPL", not toasted), `tab_line` ("took your hidden SMPL tab's line · watching RUNR"), `tab_line_back` ("You took SMPL's line back from Claude · RUNR stop and sell still rest", said as written); the desk toasts and speaks them.

**Reflexes** (`agent_trader.reflexes`, ADR 068 decision 11). Judged every 0.5 s on the seat's stock: the depth book's rows added up by price, and Nova's tape archive (a print at or over its ask is a buyer's, at or under its bid a seller's). `bid_pulled` fires only after it has seen its size since arming. A `sell_all` reflex is live while Claude holds shares, a `cancel_buy` while a buy or break waits; each fires once, does its action and is gone (an event says what it saw and did).

**The eye** (`GET /api/agent/trader/eye`, `agent_trader.eye`, ADR 068 decision 12; `schema_version: 1`): `{generated_at,
source: "ibkr", rule: {move_pct, seconds, min_dollars}, line, universe, spikes: [event], symbols: [row]}`. `line` is
the symbol Claude's line is on (or null); `universe` the number of symbols. The universe is the live Gappers, Gainers
and After Hours rows (`runtime_state`, every row, not a top N) and the setup scanner's universe (HOD Momo's active set,
`hod_momo_active.get_active_symbols`), blocklisted symbols out. A row: `{symbol, lists: ["gappers" | "gainers" |
"afterhours" | "setups"], last, prev_close, day_pct, windows: {"10" | "30" | "60": {pct, shares, dollars} | null},
spike: {direction: "up" | "down", pct, dollars} | null, float_shares, bid, ask, spread, spread_pct, halted, luld, catalyst}`.
`last` is IBKR's Level 1 last (null while it is the prior close, `quote_quality: "close_fallback"`); `day_pct` is
`last` against IBKR's prior close (percent points, null when either is unknown); `bid` / `ask` the Level 1 line's;
`spread_pct` against the mid. `windows[n]` reads the Level 1 samples `hod_momo_metrics` keeps (one hour; each the
cumulative day volume and the last that came with it): `pct` is the newest sample's last against the last at or
before `n` seconds ago, `shares` the day-volume rise, `dollars` each rise times the last that came with it; a window
the samples do not reach back across is null, never filled in. `float_shares` and `halted` are the scanner row's
(`scanner_surface.surface_rows`), `catalyst` the scanner's verdict (`catalysts.board`: `{verdict, category, strength,
title, published_ts}` or null, unread). `spike` is set when the 60-second window moved `AGENT_EYE_SPIKE_MOVE_PCT`
(2.0) or more either way with `AGENT_EYE_SPIKE_MIN_DOLLARS` (50,000) or more traded in it (`AGENT_EYE_SPIKE_SECONDS`,
60; `constants_agent_trader`). Rows are ranked spikes first (largest move first), then by the 60-second move's size,
then the day move. A spike event `{symbol, at, direction, pct, dollars, last}` is listed once when a symbol starts
spiking and again only after it stopped; newest first, the last `AGENT_EYE_EVENTS_KEEP` (50) of the last
`AGENT_EYE_EVENTS_MAX_AGE_SEC` (1,800 s). The watcher scans once every `AGENT_EYE_SCAN_SEC` (1 s) while the seat is on;
each read scans too. In memory only: a restart starts the event list empty.

**The guard** (`agent_trader.guard`, ADR 068 decision 13). While Claude holds shares, every watcher pass (0.5 s) judges,
in order: sellers lead (`AGENT_GUARD_SELLERS_SECONDS` 5 s, at least `AGENT_GUARD_SELLERS_MIN_SHARES` 1,500 at or
under the bid and `AGENT_GUARD_SELLERS_RATIO` 2x what traded at or over the ask, `reflexes.flow`); the bids left (the
top `AGENT_GUARD_BID_LEVELS` 5 bid prices of the depth book, added up across market makers, under
`AGENT_GUARD_BID_STACK_FRACTION` of what they held when the guard first saw the position; not judged on a Level 1
stand-in book); the best bid (the book's, else Level 1's) `AGENT_GUARD_BID_UNDER_ENTRY_PCT` 0.4% or more under
Claude's entry, its average buy since its position in the stock was last flat. The first that holds cancels Claude's
orders on the stock and sells its shares at market (as a `sell_all` reflex), with event `reflex_fired` "Nova's guard
on SMPL: <condition> -- sold 500 SMPL at market"; a sale the door refuses is tried again after
`AGENT_GUARD_RETRY_SEC` (5 s). The marks (entry, stack, first seen) are in memory: a restart marks the stack again.
A pop exit (`exits[SYMBOL].mode == "pop"`) raises Claude's stop leg to its entry once the `target` leg filled, or at
the first stall: Level 1's last reached `AGENT_GUARD_STALL_AFTER_PCT` (1%) over entry and made no new high for
`AGENT_GUARD_STALL_SEC` (30 s) (event `stop`, saying which).

**A break.** The seat watches each break's symbol twice a second (`agent_trader.watcher`): the first print that sets a
price at or above `trigger` -- while its `confirm` holds, when it has one -- sends the bracket with its LMT entry at `top`, after the limits are checked again. A break
past `expires_at` is dropped. Each outcome is an event.

**A hidden Trader tab's line (ADR 068 decision 14, design `F:\Nova\design\claude-seat\v3`).** With all 3 lines
held and no auto-record line to give, the seat borrows a hidden Trader tab's Level 2 and Time & Sales by a bot loan's
rule (`line_lending.claude_loan`; the loan is `setup_type: "claude"` on `GET /api/ibkr/depth/lines`, its `tier`
`watching` | `buy_set` | `in_trade`, its `why` "watching RUNR"). `line.from_tab` names that tab; the pill's `text`
adds " · on your SMPL tab's line", and " · no Level 2" while Claude holds shares without a line. The front never
recalls this loan; it ends `taken_back` (`POST /take-back`), `claude_let_go` (the seat let its line go) or
`tab_closed`. `line.taken_back` lists the tabs the operator took back: never borrowed again while open, and their
Level 2 is admitted past the reservation. After a take-back the seat asks for no line for 10 s
(`AGENT_TAB_LINE_HOLD_SEC`), so the tab reconnects onto the line it was given back.

**The line kept for Claude.** While the seat is on and not yielded, every other depth subscriber may hold at most
`IBKR_MAX_DEPTH_SYMBOLS - 1` lines of its own (a line Claude shares with a tab is the desk's). A desk request past
that is refused by `ibkr.depth.subscribe_async` with `{ok: false, cap: true, agent_reserved: true, error: "All 3
Level 2 lines are in use: SPIK and FLTX are yours, SMPL is Claude's. Close one of yours, or take Claude's line."}`.
Auto-record and line lending count the same free lines (`agent_trader.lines.desk_free`). Claude's line is a viewer
reference on the depth and AllLast lines, like a Session Record's: never idle-evicted, never lent;
`GET /api/ibkr/depth/lines` shows it as `held_by: "agent"`. With 3 desk lines held (ADR 068 decision 3, amended
2026-10-27; a line Claude alone watches does not count, its move frees it), the seat takes an auto-record line: of
the auto lines whose only viewer is auto-record's hold and that the L2 recorder is not recording, the one
in front least recently on the desk (`line_lending.focus` `last_shown` and the Trader tab sockets' `front_seen`;
never counts as longest), ties by auto-record's lowest rank (`leaderboard.auto_record.yield_to_agent`). Its
recording stops as planned (segment `reason: "auto"`) and is listed in auto-record's status `yielded`, and the
seat says so (event `line_taken`). With no such line the seat waits (`waiting_line`); it never takes a Trader tab's line, a Session
Record the operator started, the L2 recorder or a loan. Moving to another stock (`agent_trader.lines.acquire`) lets
the old line go first, except a line Claude shares with a tab or auto-record while every line is in use: letting it
go would free nothing (it stays the desk's), so the seat keeps its reference there and waits (`waiting_line`,
`line.why_not` naming both stocks) until a line is free for the new stock. "Held" means up on this IBKR session: after a reconnect the seat's reference survives, Nova's renewal of Claude's own line is admitted past the reservation, and the watcher asks again until it is up (no second reference).

**Closes Nova makes.** A lease not renewed for 600 s, `POST /stop-claude` or `DELETE /seat`: Claude's orders
cancelled, its shares sold, the seat off, its lines released. 15:55 ET on a weekday: Claude's shares sold and orders
cancelled, seat on or off; 16:00 ET the seat turns off.

**Halts** (`agent_trader.halts`, decision 17). The halt is the scanner's (`ibkr.halt_status.halted_now`; `null`, not
known, is never read as halted). While Claude's stock is halted `POST /order` is refused with `AGENT_HALTED` (also a
`refused` event); every pass cancels Claude's unfilled buys and drops its breaks on a halted stock (`refused` events
"SMPL is halted: Nova cancelled Claude's buy at 4.1" / "... took back Claude's break at 4.4"); held shares keep their
resting stop and targets and the guard skips the stock until it trades again.

**The LULD band** (`agent_trader.bands`, ADR 047's band from `luld.live.view`, decision 17). `luld: {upper, lower,
pct_to_upper, pct_to_lower, state, exact}` on `/look` and each eye row: `pct_to_upper` is the upper band over the last
(percent), `pct_to_lower` the last over the lower; `state` is the band source's (`bands`, `limit`, `pause_due`,
`unknown` where Nova holds no tape line for the stock, `off`, ...), with null numbers where it has no band.
`book.at_limit` (`/look`) is true when the best bid is at or over the upper band and nothing is offered at or under it:
buyers pinned by the band, not support.

**Each print and book** (`agent_trader.wake`, decision 15). The IBKR AllLast and depth callbacks call `wake.print_in` /
`wake.book_in`; for a stock the seat watches (its stock, its breaks', the ones it holds) the print `{ts, price, size, bid,
ask, exchange, conditions}` joins a ring of the last `AGENT_WAKE_RING_SEC` (60 s) and the watcher runs a pass at once,
never closer than `AGENT_WAKE_MIN_SEC` (0.1 s) to the last, else every `AGENT_TICK_SEC` (0.5 s). Breaks, reflexes and the
guard read the ring first and the tape archive only for what the ring does not reach back to. In memory only.

**The journal** (`agent_trader.journal`, decision 16): `backend/.cache/agent-journal/<YYYY-MM-DD>.json`, the trading day
the trade closed, `{schema_version: 1, day, trades: [trade]}`, written whole and atomically (a file of another
`schema_version` is refused, logged). A trade: `{symbol, opened_at, entry_price, why, entry: snapshot & {late}, closed_at,
shares, exit_price, exit_reason, exit_detail, exit: snapshot, pnl, fees, fills}`; a snapshot is `{at, bids, asks,
l1_fallback, prints}` (the book's top `AGENT_JOURNAL_BOOK_ROWS` 10 rows each side, the prints of the last
`AGENT_JOURNAL_PRINTS_SEC` 30 s, newest `AGENT_JOURNAL_PRINTS_MAX` 100). `entry_price` is Claude's average buy since it
was last flat; `why` the `why` of Claude's last order in the stock; `late` true when the trade was read back after a
restart (its entry snapshot taken then). Trades are Claude's own fills flat to flat, each written once (keyed by symbol
and `opened_at`, read back from the day's file after a restart): one that opened and closed between two passes is
written too, with `entry: null` (no pass saw it held) and an exit snapshot marked `late`. `exit_reason`: `stop` / `target` (the closing fill's bracket leg), else the
closer's (`guard`, `reflex`, `manual`, `day_close`, `stand_down`), else `nova` (Nova sold the shares under another
origin), else `unknown`. `pnl`: Claude's fills in the trade, fees included, plus shares Nova sold for it at the price
those closes got. Open trades are in memory.

**Persisted:** `backend/.cache/agent-seat.json` (`schema_version: 1`, written whole and atomically): `{holder, since,
beat_at, yielded, yielded_at, symbol, breaks, reflexes, exits, note, events}` (the newest 40 events). A file with another
`schema_version` starts the seat off and is logged. A seat read back gets a fresh lease from the read (`resumed`). Spend arming is never persisted (ADR 018).
