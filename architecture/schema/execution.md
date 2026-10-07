# Data schema: Execution, arming and account identity

Part of `AGENTS.md` §3 (Data Schema), which indexes every file in this folder. Owners: backend/execution/, backend/ibkr/safety.py, backend/kill_switch/. Same law as the constitution: a wire or persisted shape changes here first, in the same commit as the code (Invariants #1 and #5).

## Who may arm the desk (ADR 018 amendment, operator decision 2026-09-23)

`POST /api/ibkr/arm` takes `{armed: boolean, pin?: string, actor?: "operator" | "bot"}`
(`actor` defaults to `operator` and is a label, never a permission). `armed: false`
always succeeds. `armed: true` on Live needs the operator's PIN, checked by
`ibkr/arm_pin.py` against `NOVA_LIVE_ARM_PIN_HASH` in `.env`
(`pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>`, written by
`tools/set_live_arm_pin.py`; re-read on each check, so no restart). Paper and Sim
arm with no PIN. A refusal is `403 {detail, code}` with `code` one of
`ARM_PIN_REQUIRED | ARM_PIN_NOT_SET | ARM_PIN_INVALID | ARM_PIN_LOCKED`
(`ARM_PIN_MAX_FAILURES` wrong PINs in a row lock Live arming for
`ARM_PIN_LOCKOUT_SEC`). `/api/ibkr/status` and the reply add `arm_requires_pin:
boolean` (the desk's venue needs the PIN), `live_arm_pin_set: boolean` and
`armed_by: "operator" | "bot" | null`; `armed` is true only on the venue the latch
was armed on. The PIN is never in the repository or the frontend. Locking the
padlock -- by anyone -- also clears the bot's Activate, in the backend (ADR 042).

## Account identity on `/api/ibkr/status` (operator ask, 2026-09-21)

`account_id: string | null` is the first IBKR managed account of the connected
session (`DU…` paper, `U…` live) and `account_ids: string[]` all of them; both
are empty while disconnected. They name *what Nova is logged into*, next to
`broker_account_kind`; the header shows the id beside Cash / Margin. IBKR's API
never exposes the login username, so the account id is the identity Nova can
state truthfully.

## Orders refuse a stale view; the market path stays real time (ADR 045, operator report 2026-10-05)

"If it lags, then we cannot place an order." At 08:30:25 ET the operator sold APUS at a 6.58 bid their Level 2
had shown since 08:30:18-21 (Nova's own book was 6.50 x 6.55 by then; Time & Sales showed 08:30:20 as newest);
the order reached the backend 2-3 s after the click and rested above the market.

- **Versions** (owner `market_view/versions.py`, memory only). Each symbol's Level 2 book (`book`) and quote
  (`quote`) has a version: `seq` (an integer, +1 per change, never reset while the process runs) and `at`
  (epoch seconds when Nova applied it), with the last `MARKET_VIEW_HISTORY_KEEP` versions kept so the gate can
  tell when any `seq` it is shown was replaced.
- **Level 2** (`/ws/ibkr/depth/{symbol}`). Each viewer holds the newest book only, never a backlog, plus a
  short FIFO of control frames; the IB thread wakes the socket's loop thread-safely, once per burst. A book is
  pushed only when its rows changed (an L1 tick or a print on the same contract no longer re-sends it).
  - `{"type": "subscribed", "symbol", "instance"}` -- `instance` is the backend process (`/api/health`
    `instance_id`).
  - `{"type": "book", "symbol", "data": {bids, asks, l1_fallback}, "seq", "at", "sent"}` -- `data` unchanged.
  - `{"type": "beat", "symbol", "seq", "at", "now"}` every `MARKET_VIEW_BEAT_SEC` (0.25) without a book frame:
    the line's newest version (`seq` 0 and `at` null before its first book) as of `now`. It replaces the
    15 s `ping`.
- **Time & Sales** (`/ws/ibkr/tape/{symbol}`). Each viewer's prints wait in a thread-safe FIFO
  (`IBKR_TAPE_QUEUE_MAXSIZE`, oldest dropped and counted in `tape.viewer_dropped`) with the same wake-up; two or
  more waiting prints go as one `{"type": "prints", "symbol", "items": [print...], "sent"}` frame, a single one
  as the `print` frame it was.
- **Quote** (`/ws/ticker/{symbol}`): `trade_update` adds `seq` and `at`, the symbol's quote version.
- **The view an order carries.** `POST /api/ibkr/order` and `PATCH /api/ibkr/order/{id}` accept `view:
  {schema_version: 1, symbol, action_wall_ms, instance: string | null, book: {seq, at, bid, ask} | null, quote:
  {seq, at, price} | null, desk: {silent_ms, transit_ms, undrawn_ms} | null}` -- when the operator acted
  (epoch ms), the Level 2 book and the quote the screen showed (null when it showed none), and the desk's own
  measures at that moment. The desk attaches it to every order it sends (`ibkr/placeOrder.ts`).
- **The gate** (owner `market_view/gate.py`; constants `constants_market_view.py`). For a `manual` place,
  bracket or replace that came through those routes (it carries `client_timing`), the execution door refuses,
  after the duplicate-key replay and before anything is validated or sent, HTTP 200 `{ok: false, reason_code,
  error}` like its other refusals:
  - `VIEW_STALE`: the book or quote the screen showed had been replaced for more than `ORDER_VIEW_MAX_LAG_MS`
    (500) at `action_wall_ms` (`lag = action - at(seq + 1)`), a `seq` older than the kept history, a `seq` past
    the newest, or an `instance` that is not this process;
  - `ORDER_LATE`: the door saw it more than `ORDER_MAX_ARRIVAL_MS` (500) after `action_wall_ms`, or the broker
    send would leave more than `ORDER_MAX_SEND_MS` (750) after it -- checked again just before the send, and
    on Live by the IB loop as it sends (`gate.send_deadline`, below);
  - `FEED_STALE`: an IBKR feed gap is open or settling (`ibkr/feed_pulse`), or the IB loop is stalled now for
    more than `ORDER_MAX_IB_STALL_MS` (500) (`perf/stall_watch.stalled_ms`) -- never on a Sim desk off the live
    edge, whose market is the replay;
  - `VIEW_MISSING`: no `view` (an older desk).

  The protective sources (`flatten`, `kill`, `cancel_working`), cancels and every command without
  `client_timing` (the bot, stock modes, the breakers) are exempt. The arithmetic mixes the desk's and the
  backend's wall clocks, sound because the backend binds 127.0.0.1; an action more than 1 s in the backend's
  future is `VIEW_STALE` ("the clocks disagree"). The execution row's payload keeps `view` and `view_check:
  {schema_version: 1, verdict: "ok" | "refused" | "exempt" | "missing", code, arrival_ms, book_lag_ms,
  quote_lag_ms, feed_gap: boolean | null (null on a replay desk), ib_stall_ms}`.
- **The desk locks first** (owner `frontend/src/market_view/`). A symbol's view is stale while its Level 2 has
  had no frame or beat for `VIEW_SILENT_LOCK_MS` (750), a frame took more than `VIEW_TRANSIT_LOCK_MS` (500)
  from `sent` to arrival, or a received book has not been drawn for `VIEW_UNDRAWN_LOCK_MS` (500). Then Place,
  the quick bar's and the hotkeys' priced actions and Fill now are locked with the reason (`data-why`); Flatten
  and cancels never are. No age readout: locked or live.
- **The Live send awaits the IB loop, and goes out once or never** (#725; owners `ibkr/send_hop.py`,
  `execution/live_send.py`). A Live place, replace or bracket runs its whole `ibkr.orders` call on the IB loop
  while the socket loop keeps serving every socket (`call_on_ib` blocked it for as long as the IB loop was busy,
  up to 15 s). One lock both loops take decides whether it went out:
  - the IB loop starts a send only while its caller still waits;
  - a caller that gives up marks a send not yet started abandoned, and it is never sent: refused
    `IB_LOOP_WEDGED` after `IBKR_SEND_HOP_TIMEOUT_SEC` (15), or `ORDER_LATE` past the desk order's deadline,
    which the IB loop enforces as it sends and at which the caller stops waiting;
  - a send already running reached IBKR and is awaited to its end. One that has not finished within
    `IBKR_SEND_RUNNING_GRACE_SEC` (30) is `SEND_UNKNOWN`: Nova says it cannot tell.

  The order's watch is registered in the IB-loop callback that placed it, and the order id joins its in-flight
  commitment there, so no status can arrive unheard and a fill heard first still frees the shares.
  `OrderWatch`'s ack and fill wake their waiter from any thread at once (an `asyncio.Event` set from the IB
  thread is not thread-safe and woke nothing). IBKR's order events are wired at READY on the IB loop
  (`ibkr/session_usable.py`); the order path's own wiring awaits too and refuses `IB_LOOP_WEDGED` past
  `IBKR_ORDER_EVENTS_WIRE_TIMEOUT_SEC` (5).
- **Nothing slow on the socket loop.** `ibkr/gateway_process.py` reads Windows' process list and listening
  ports in-process (no `tasklist`; the Gateway is the `java.exe` IBC launches, or an `ibgateway*` / `tws*`
  image); `paths.cache_dir()` / `log_dir()` create their folder once; the Closed blotter's place overlay is
  read again only after the ledger is written (`execution/place_overlay.py`); the IBC log and the gateway trail are re-read only when
  their file changed; a Time & Sales subscribe warms its 10-second bars off the loop.
- **Priority** (owner `process_priority/`, Windows only). The backend raises itself to Above Normal, opts out
  of Windows power throttling and keeps normal memory and I/O priority at start and every
  `PROCESS_PRIORITY_RECHECK_SEC` (2); its IB and socket loop threads run Above Normal; it keeps IB Gateway's
  process at Above Normal and IBC's launch loop, whose relaunch the Gateway inherits, at Normal. Nothing is lowered; a priority found lowered is raised and
  logged. `/api/diagnostics` adds the `process_priority` row (group `process`), `evidence: {processes: [{role:
  "api" | "gateway" | "ibc_loop", pid, name, priority, raised, error}]}`. The desk's Electron main raises its
  own and its desk windows' processes (`frontend/electron/processPriority.mjs`).
- **Freezes** (owner `perf/freeze_watch.py`). A C-level watchdog (`faulthandler`) re-armed every 0.5 s dumps
  every thread's stack when the process stops for `PERF_FREEZE_DUMP_SEC` (2), to
  `<cache_dir>/perf/freezes/YYYY-MM-DD.txt`, and `freezes.jsonl` beside it logs `{schema_version: 1, armed_at,
  noticed_at, frozen_sec, file, offset}` per dump. `/api/diagnostics` adds `perf_freezes` (group
  `performance`). Perf samples' `process` adds `page_faults` (in the interval) and `working_set_mb`, and `gc`
  adds `pause_ms_by_gen` and `max_pause_ms_by_gen`.

## Execution command (ADR 007 — sole broker mutation entry)

All buy/sell/cancel/replace requests enter `execution.service.execute` with:

```json
{
  "operation": "place | bracket | cancel | replace",
  "idempotency_key": "stable-client-or-ticket-key",
  "source": "manual | kill | cancel_working | flatten | benchmark | bot",
  "symbol": "AAPL",
  "side": "BUY",
  "qty": 1,
 "order_type": "MKT | LMT | STP | STP LMT | TRAIL",
 "limit_price": null,
 "stop_price": null,
 "target_price": null,
 "entry_price": null,
 "order_id": null,
 "short_entry": false,
 "tif": "DAY | GTC",
 "outside_rth": false,
 "intent": null,
 "expected_venue": null,
 "origin": null
}
```

**Who sent it** (operator report 2026-10-01: "Could you see who sold here? I don't remember selling it." -- the Paper bot trip sold 100 ACN, and the row read like any other market sell, because the ticket's Flatten, the header's KILL, both loss breakers and the bot's own last-resort exit all send source `flatten`). `origin` names which part of Nova sent an order, one of `constants_nova_os.EXECUTION_ORIGINS`: `ticket_flatten` (the ticket's, quick bar's or a hotkey's Flatten), `emergency_kill` (`POST /api/ibkr/flatten-account`, the header's KILL), `bot_trip` / `all_stop` (the loss breakers' flatten), `bot` (Nova's bot: entry, exits, last-resort close), `auto_entry`, `approve` (Who trades the stock), `bot_api` (the localhost bot API), `nova_exit` (Nova takes the exit) and `day_cover` / `margin_call` (ADR 048: Nova's own closes on Paper and Sim); `null` for the operator's own ticket. A label, never a permission -- with one exception: a `cancel_working` cancel or `flatten` place stamped `day_cover` / `margin_call` may name the venue that holds the position (`target_venue`, "Short selling" above). Only Nova's own code sets an origin; no HTTP caller can. The execution record's payload keeps it, a practice order row (Paper / Sim, working and closed, every bracket leg) carries it as `order_origin` beside `order_source`, and a Live row -- working (`GET /api/ibkr/orders`) or closed (`execution/closed_blotter.py`) -- takes both from today's execution row for this desk that sent it (`execution/sent_by.py`, #677: by permId, else order id, the symbols agreeing; a bracket's exit legs share their entry's sender, so a closed leg reads Nova's, not "Outside Nova"); a Live row no execution row claims carries neither. A row placed before 2026-10-01 has `order_origin: null`: a `flatten` there could be any of the five, and the desk says so rather than guessing. The Working and Closed order tables add a **Sent by** column (`frontend/src/ibkr/orderSentBy.ts`: You, You · Flatten, KILL, Bot trip, All-stop, Bot, Auto-entry, Approve, Bot API, Nova exit, Day cover, Margin call, Outside Nova; a breaker's, KILL's, the day cover's or a margin call's in amber), its reason on hover; a layout saved before it gets the column where the defaults put it (after Status), not off the far edge.

`STP LMT` requires both `limit_price` and `stop_price`. `TRAIL` uses `stop_price` as the IBKR trail dollar amount (`auxPrice`); trail percent is not a ticket field. `tif` defaults to `DAY` (`IBKR_ORDER_TIF_DEFAULT`), so a caller that omits it is unchanged; anything outside `DAY | GTC` is refused `TIF_INVALID`. `place` and every `bracket` leg carry `tif` and `outside_rth`; `replace` keeps the working order's own TIF. **Market orders need regular hours** (operator decision, 2026-09-21): a `MKT` place from a non-protective source is refused `MKT_OUTSIDE_RTH` ("use a limit at the ask") whenever the venue's clock is outside weekday 09:30-16:00 ET, NYSE holidays excluded -- no US exchange takes an unpriced order then and IBKR would hold it until the next open (Warning 399) while ignoring `outsideRth` on it (Warning 2109). The clock is the venue's (the replay playhead on Sim). Owner `execution/session_gate.py`; the practice broker repeats the check (`practice/order_rules.py`). Protective sources are exempt (flatten plans an extended-hours limit); `STP` orders are unchanged.

**The ticket's Flatten** (QA R32 / R42, 2026-09-22): `POST /api/ibkr/order` may carry `intent: "flatten"` -- the rail's Flatten, the quick-bar Flatten and the `exit_pos` / `cancel_and_exit` Nova Actions send it. The route sends it as source `flatten` with `ExecutionCommand.intent: "flatten"` (a protective source: never clamped by the test quantity gate and placeable while disarmed, like KILL), and the execution door accepts it, inside the execution lock, only when it closes shares not already being closed -- the side reduces the venue's own position, and the size does not exceed that position less the closing orders already working on the venue (open orders) or committed and not yet listed; no `short_entry` and no legs. Anything else is refused `FLATTEN_NOT_A_CLOSE` before any send ("cancel that order first, or use KILL" when a close is already working), so two flattens can never both fill into a short. The practice broker also cancels, at the fill, a SELL that would fill past what is held (`PRACTICE_NO_SHORTS`). A protective order that fills inside the send frees its in-flight commitment at once (QA R31). The mirror holds for a cover: the practice broker cancels, at the fill, a BUY that would buy past the short (`PRACTICE_OVERCOVER`, ADR 048).

**Manual-ticket protective legs** (operator decision on #91, 2026-09-20 -- supersedes "OCO / bracket stay off the manual ticket"): OCO stays off the manual ticket. A bracket reaches it only as the operator's optional default take-profit / stop-loss from Settings > Trade (`nova.trade.defaults.v1`), **off by default**. When on, an opening **Limit** entry (BUY while not short, or SELL with `short_entry`) posts `take_profit_price` + `stop_loss_price` with its `/api/ibkr/order` request, and the route sends `operation: "bracket"` (`entry_price` = the limit) through the same `execution.service.execute` -- never a second place path. Other entry types are refused while the defaults are on rather than sent unprotected; exits never carry legs; protective sources (`flatten`, `kill`, `cancel_working`) are refused a `bracket`. A bracket is checked like a place: whole shares, side agrees with `short_entry`, leg prices on the correct side of the entry, BuyingPower for a long entry, and no long bracket while the account is short that symbol.

Receipt includes stage timings (`validation_ms`, `persisted_ms`, `broker_sent_ms`, `broker_ack_ms`, `filled_ms`). The receipt adds `venue` (`live | paper | sim`), the desk venue the order was sent on (`mode` is the broker's label: `paper` there can also be the legacy Gateway).

**One venue per send** (#655, audit 2026-09-30; owner `execution/venue_door.py`). `execute` reads the desk's venue once, under its lock, and the order is validated against, committed on and sent to that venue -- a venue pill clicked mid-check refuses the order `VENUE_CHANGED` ("the desk moved ... it was not sent; place it again") and never sends it elsewhere. An order id is only meaningful on the venue that issued it (practice ids restart at 1 per venue; IBKR's are IBKR's), so in-flight commitments (`execution.inflight`), order watches (`execution.telemetry`: IBKR's by id, a practice venue's by `(venue, id)`) and releases are all per venue: a Paper sell still working never refuses a Live exit, and Paper's fill of order N never marks Live's order N filled. `expected_venue` on the command (cancel / replace by id) makes the door refuse `VENUE_CHANGED` when the desk is elsewhere; `DELETE /api/ibkr/order/{id}?venue=` and `PATCH` `venue` accept it, and the bot's and Who-trades cancels send their trade's venue. The desk's Cancel sends the venue its row came from: the account snapshot (`ibkr/ibkrAccountPoller.ts`) carries `venue`, a venue change clears the old venue's rows and reads the new one at once, and a read that finishes after the switch -- or another window's snapshot of another venue -- is dropped, so the desk never shows the old venue's orders or positions, not even as "last known" (#657). The Who-trades view resets on a venue change too.
Paper and live share this path; only Gateway credentials/port and safety gates differ. `auto_live` remains rejected -- a spend command whose `source` is not one of the listed values (e.g. `auto_live`) is refused `SOURCE_INVALID`; so are `approve` and `auto_paper`, the retired Phase D executor's sources (ADR 025), while ledger rows that already carry them still read. Short opening requires `short_entry: true` and the short check ("Short selling" above, ADR 048), `IBKR_SHORT_ENABLED` on Live (ADR 009).

**Kill switch** (D-037, ADR 025; owner `backend/kill_switch/`): a persisted latch (`kill_switch_state.json` under the operator cache, `schema_version: 1`; unreadable or unknown version reads tripped) that `execution.service.execute` checks before every `place` / `bracket` from a non-protective source, manual and bot included -- refused `KILL_SWITCH`; `kill`, `flatten`, `cancel_working` and every cancel still reach the broker. `GET /api/kill-switch` -> `{tripped, reason, ts}`; `POST /api/kill-switch` trips it (latch first, then the working orders of every venue that has any are cancelled through the `kill` source -- Live while IBKR is connected, else a stated error "Gateway disconnected: Live orders were not swept"; Paper always, even with the Gateway down (#656); Sim while its scratch account is open -- each cancel through the execution door with `ExecutionCommand.target_venue`, which only a `kill` cancel may carry (anything else is refused `TARGET_VENUE_REFUSED`), and a failed read is a stated failure, never "nothing to cancel"; the stops that protect a held position stay resting, ADR 048, "Short selling" above) and answers the status plus `sweep: [{venue, cancelled, failed, kept, error, note}]`, `persisted`, `receipt_error` and the legacy summed `cancelled_order_ids` / `failed_cancel_order_ids` / `kept_order_ids` (the route is async, on the app's loop: #656's lock from a second loop is gone); `POST /api/kill-switch/reset` clears it and is the only thing that does. A trip writes a `kill_switch` receipt to the event log. The control is a card on the Bots page. The header's Emergency KILL (bot to L0, desk lock, cancel, flatten) is a separate composite. The Nova OS verdict, the `signal | confirm | auto_paper` ladder, the staged approval queue and `/api/strategy/executor/*` were removed (ADR 025).

---

## Execution venue provenance (#713)

Execution ledger payload JSON adds `venue: "live" | "paper" | "sim"`, stamped
from the execution door's resolved venue at reservation. The broker `mode`
label remains unchanged; `paper` can name the legacy IBKR Paper Gateway.
Ambiguous legacy rows remain unverified rather than joining a practice book.

