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
| `GET /api/agent/trader/look?symbol=&seconds=120` | anyone local | `{symbol, at, line: {depth, tape, claude_holds, book_at}, quote: {last, bid, ask}, book: {bids, asks, l1_fallback}` (top 10 rows each, the depth module's own rows), `tape: {seconds, summary: {prints, volume, high, low, vwap, at_ask, at_bid}, prints: [{ts, price, size, side?, exchange?, bid?, ask?, conditions?}]}` (newest 200), `locked}` (the view lock's answer or null). Opens no line. |
| `POST /seat` | Claude | `{token, status}`; refused (`AGENT_SEAT_TAKEN`, 409) while another holder's lease is alive, and outside weekdays 04:00-16:00 ET (`AGENT_SEAT_OFF`) |
| `POST /beat` | Claude | status; renews the lease |
| `DELETE /seat` | Claude | `{problems, status}`: cancels Claude's orders, sells its shares, frees the line, seat off |
| `POST /watch {symbol}` | Claude | status; the seat's stock (refused while Claude has orders or shares on another) |
| `POST /note {text}` | Claude | status; one line (<= 400 chars) the desk shows |
| `POST /arm` | Claude | status; arms the desk on Paper as `actor: "bot"` (ADR 018). Refused off Paper and when the operator locked the padlock (`ibkr.safety.locked_by() == "operator"`). |
| `POST /order` | Claude | `{order_id, stop_order_id, status}` (a limit) or `{break, status}` (a break). Body: `{kind: "limit" \| "break", symbol, qty, entry (limit), trigger + top (break), stop, target, target2?, target1_qty?, minutes? (break life, default 30, max 240), why}` |
| `POST /stop {order_id, stop}` | Claude | status; raises Claude's own stop leg (never lowers it) |
| `DELETE /order/{id}` | Claude | status; cancels Claude's own working order |
| `DELETE /break/{id}` | Claude | status |
| `POST /close {symbol}` | Claude | status; cancels Claude's orders on it, sells Claude's shares at market |
| `POST /yield` | operator | status; "Take Claude's line": unfilled buys and breaks cancelled, lines released, no new trades; held shares keep their stop |
| `POST /give-back` | operator | status |
| `POST /stop-claude` | operator | `{problems, status}`: as `DELETE /seat` |

Refusals are `{detail: {reason, error}}` with `reason` one of `AGENT_SEAT_TAKEN`, `AGENT_NOT_HOLDER` (403),
`AGENT_SEAT_OFF`, `AGENT_YIELDED`, `AGENT_LIMIT`, `AGENT_NOT_PAPER`, `AGENT_NO_LINE`, `AGENT_NOT_MINE`, `AGENT_STALE`,
`AGENT_REFUSED`, or the execution door's own code; `error` says why in words.

**Status** (`schema_version: 1`): `{generated_at, name: "Claude", venue: "paper", state, text, on, since, beat_at,
lease_until, lapsed, yielded, symbol, line: {symbol, depth, tape, why_not, desk_lines, desk_cap, all_lines},
positions: [{symbol, qty, mark}], working: [{order_id, symbol, side, order_type, qty, limit_price, stop_price,
leg_role, status, parent_id}], breaks: [{id, symbol, qty, trigger, top, stop, target, target2, target1_qty,
expires_at, created_at, why}], today: {entries, max_entries, pnl, day_stop, fills}, limits: {max_shares,
max_risk_usd}, note: {text, at} | null, events: [{at, kind, text}] (newest first, 12), read_error}`. `read_error`, `line.why_not` and every refusal are Nova's own words: an exception's text never reaches this wire (it goes to the log). `state` is one
of `off`, `idle` (no stock yet), `waiting_line`, `watching`, `buy_set`, `in_trade`, `yielded`, `done`; `text` is the
header pill's words ("Claude · In SMPL +$42.00"). The holder token is never in it.

**Claude's limits** (checked before the door, `agent_trader.rules`): long only; every entry a bracket with its stop
and one or two targets; whole shares, at most 1,000; at most $150 between entry and stop; at most 3 entries a day
(filled entries, working entries and armed breaks); no new entry once its day is at -$400 or worse, fees included;
entries 07:00-15:30 ET on weekdays; only on the seat's stock with Claude's Level 2 line live; never where Paper holds
shares or working orders that are not Claude's; never while the view lock holds (`market_view.gate.desk_lock`).

**Sends.** Entries `operation: "bracket"`, `source: "bot"`, `origin: "claude"`, `expected_venue: "paper"`; stop
moves `replace` the same way; closes `source: "flatten"` market SELLs and cancels `source: "cancel_working"`, both
`target_venue: "paper"`. `execution.venue_door` refuses any `claude` send while the desk is not on Paper and any
`claude` close named to Live. Practice rows carry `order_origin: "claude"`; Claude's position is its own fills.
Claude's fills count on the **Bots** loss line (`loss_limit.accounts.by_of`, `LOSS_LIMIT_BOT_CLOSE_ORIGINS`).

**A break.** The seat watches each break's symbol every second (`agent_trader.watcher`): the first print that sets a
price at or above `trigger` sends the bracket with its LMT entry at `top`, after the limits are checked again. A break
past `expires_at` is dropped. Each outcome is an event.

**The line kept for Claude.** While the seat is on and not yielded, every other depth subscriber may hold at most
`IBKR_MAX_DEPTH_SYMBOLS - 1` lines of its own (a line Claude shares with a tab is the desk's). A desk request past
that is refused by `ibkr.depth.subscribe_async` with `{ok: false, cap: true, agent_reserved: true, error: "All 3
Level 2 lines are in use: SPIK and FLTX are yours, SMPL is Claude's. Close one of yours, or take Claude's line."}`.
Auto-record and line lending count the same free lines (`agent_trader.lines.desk_free`). Claude's line is a viewer
reference on the depth and AllLast lines, like a Session Record's: never idle-evicted, never lent;
`GET /api/ibkr/depth/lines` shows it as `held_by: "agent"`. With 3 desk lines held, the seat waits (`waiting_line`)
and never evicts one. "Held" means up on this IBKR session: after a reconnect the seat's reference survives, Nova's renewal of Claude's own line is admitted past the reservation, and the watcher asks again until it is up (no second reference).

**Closes Nova makes.** A lease not renewed for 600 s, `POST /stop-claude` or `DELETE /seat`: Claude's orders
cancelled, its shares sold, the seat off, its lines released. 15:55 ET on a weekday: Claude's shares sold and orders
cancelled, seat on or off; 16:00 ET the seat turns off.

**Persisted:** `backend/.cache/agent-seat.json` (`schema_version: 1`, written whole and atomically): `{holder, since,
beat_at, yielded, yielded_at, symbol, breaks, note, events}` (the newest 40 events). A file with another
`schema_version` starts the seat off and is logged. Spend arming is never persisted (ADR 018).
