# Bot localhost API (ADR 016)

Brain-agnostic HTTP + WebSocket on loopback. Nova ships no brain process
(ADR 027 retired `nova-brain`); any client may use the API under every gate
below. MCP / Astra / Fable stay optional adapters (`docs/bot-adapters.md`). Advise never places. Every order goes
through `execution.service.execute` with `source=bot`. No SendKeys. No
free-form qty.

OpenAPI: `GET http://127.0.0.1:8000/openapi.json` (tags `bot`, `bot-ws`).
Aliases exist without the `/api` prefix (`/bot/session`, ...). `/bot/*` and
`/api/bot/*` share the same auth and arming gate.

Loopback only (`127.0.0.1`, `::1`, `localhost`). L3 Unrestricted is parked
(`#216`) -- `PATCH` level 3 returns `409 BOT_L3_PARKED`.

## Auth

Mutating bot routes **always** require a configured `NOVA_API_KEY` and a
matching `X-Nova-Api-Key` header, including on loopback. GET `/session`,
`/watch`, `/proposals`, `/focus`, `/audit`, `/pnl` stay open.

One key only. Vite `serve` maps repo-root `NOVA_API_KEY` onto
`VITE_NOVA_API_KEY`. Packaged Desktop has no Vite inject: Electron main
reads the same repo / `NOVA_ENV_PATH` / userData `.env` the API uses,
exposes it on `novaDesktop.apiKey`, and `novaFetch` sends the header.
Do not generate a second key when that file already has one. Do not bake
the key into the renderer bundle.

Brains send `X-Nova-Brain-Session`. They must not send a desk arm token and
must not PATCH `level`.

## Autonomy + Activate

| Level | Name | What the brain may do |
|---|---|---|
| 0 | Off | `GET /session` only. Everything else is dark. |
| 1 | Eyes | Watch + submit proposals for allowlisted ∩ live-focus names. Human places. |
| 2 | Strategy | Fire allowlisted kinds after desk Activate + exclusive claim + fresh heartbeat. |
| 3 | Unrestricted | Parked. |

L1 -> L2 is **desk UI only**:

1. Header **Activate** calls `POST /api/bot/session/arm` and stores
   `desk_arm_token` (response only; GET never returns it).
2. Header level dropdown PATCHes `{"level":2}` with `X-Nova-Desk-Arm`.
3. **Stop** is `POST /session/disarm`. Claim cannot outlive Activate.

`PATCH {"level":2}` without the token is `403 BOT_ARM_REQUIRED`.
`POST /arm` with `X-Nova-Brain-Session` is `403 BOT_ARM_DESK_ONLY`.
Setting `armed` in a PATCH body is refused.

Level and Active are separate. L2 + allowlist with the desk
**Not active** (`armed` / `has_desk_arm` false) is `409 BOT_NOT_ACTIVE`
on fire. Eyes never fire (`409 BOT_L1_NO_FIRE`). L2 → Eyes or L0
disarms so `live_fire_ready` cannot stay true.

Header owns L0/L1/L2 and arming. At L2 the header shows a
**Bot is in control** checkbox (checked = Activate / armed, unchecked =
Stop). L0/L1 hide that checkbox. The chip flashes when `live_fire_ready`
(L2 + armed + brain heartbeat). Strategy left tab is settings only.

Heartbeat older than 15s (`BOT_HEARTBEAT_STALE_SEC`) fail-closes fire
(`409 BOT_HEARTBEAT_STALE`). Same-day -$50 re-arm is allowed (Activate
sends `reenable`).

## The playbook and the read-out (ADR 027)

The old packs (halt-luld, quote-spike, volume, llm-decide) and the
`nova-brain` sidecar are retired. The session carries the operator's setups
instead: `setup` (the one that plays, `first_pullback`) and `setups: [{id,
scanner}]` -- `first_pullback` (the ADR 022 scanner), `gap_and_go`,
`flat_top_breakout`, `red_to_green`, `micro_pullback`. Only a setup with a
scanner can be chosen (`PATCH {"setup": ...}`, else `400
BOT_SETUP_NO_SCANNER`). Risk sleeve stays `small-cap`.

**Strategy waits on the read-out -- on Live** (ADR 030). `readout` on the
session is the first-pullback read-out from `setups.db` (Bot-Trading-Plan §2g:
50 triggered go setups, average net R above +0.2 and above blind / wait). On
Paper and Sim (`readout_required: false`) Strategy skips it. On Live, until it
passes:

- choosing Strategy is allowed but lands **not active**;
- `POST /session/arm` at Strategy is `409 BOT_READOUT_NOT_PASSED`;
- every `POST /action` is `409 BOT_READOUT_NOT_PASSED`;
- `live_fire_ready` is false. Proposals still work at Eyes and Strategy.

**Nova's own first-pullback bot** (ADR 030) plays at Strategy on Paper and Sim:
it claims the session as brain `nova-first-pullback`, so an external brain
gets `409 BOT_BRAIN_EXCLUSIVE` while it plays. `runner` on the session says
whether it plays and why not; `trade` is its current or last trade.

**Entries keep the material's rules.** At Strategy a `buy_*` kind is refused
outside 07:00-10:00 ET on the venue's clock (`409 BOT_OUTSIDE_WINDOW`) and
after one bot entry that venue day (`409 BOT_DAY_TRADE_CAP`). Exits and
cancels are never held by either.

`gates: [{id, ok, stage, detail}]` on the session lists every gate the Bots
page draws: `level`, `allowlist`, `desk_armed`, `depth_lines`, `readout`,
`bot_trip`, `day_lock`, `kill_switch`, `window`.

## Symbol gate

**Eyes** (watch / propose) see **allowlist AND live Trader focus** -- the
tabs the UI reports through `POST /api/bot/focus/sync`. Empty allowlist is
fail-closed (`409 BOT_SYMBOL_BLOCKED`). Right-click Add / Remove on scanner
rows, trader tabs, and the chart menu. The Bot Autonomy strip **Allowlist**
control and the Strategy left tab list the same `session.symbol_allowlist`
(chips + add ticker) and call the same `POST /api/bot/allowlist` -- neither
owns a second list. That is symbols only, not `caps.allowlist` action kinds.

**Fire** (`POST /api/bot/action`, every kind) needs **allowlist AND a depth
line Nova itself holds** (ADR 020 second pass, 2026-09-21). The backend
cannot see UI tabs, so the held line is the fact: an open Trader Level 2
(`ibkr.depth.state.is_subscribed`, the replay slot on a Sim desk included)
or a Session Record line (`is_live`). No line budget. A symbol with no line
is `409 BOT_NO_DEPTH_LINE` -- "open its Level 2 or record it" -- before the
execution door is reached. Enforced in one place:
`bot/eligibility.assert_symbol_can_fire`, called from `bot/actions.fire`.

## Practice rewind (Sim time travel)

On the Sim venue the scratch account follows the playhead (ADR 020
decision 3): scrubbing backwards drops every practice order and fill after
the new playhead -- they never happened. Whenever that unwind dropped
anything, Nova publishes a `practice_rewind` event:

```json
{"venue": "sim", "playhead_ts": 1758463200.0, "dropped_orders": 1, "dropped_fills": 1}
```

- **Push:** an entry on the bot audit stream (`ws://127.0.0.1:8000/ws/bot/audit`,
  the same channel breaker and TTL events use) with `action: "practice_rewind"`,
  `outcome: "ok"` and the event under `inputs`. It is also in `GET /api/bot/audit`.
- **Poll:** `GET /api/bot/session` carries `last_rewind` -- the same event plus
  `ts` (when it was published), or `null` until one happens. Process-local: a
  restart clears it, and the scratch account with it.

`dropped_orders` counts placements that never happened, `dropped_fills` the
fills. A forward move, or a backward move that dropped nothing, publishes
nothing -- the ledger did not change.

**After a rewind a bot must re-read positions and working orders from the
account** (`GET /api/practice/account?venue=sim`, `/api/ibkr/positions`,
`/api/ibkr/orders`) and **never trust its own memory over the ledger**: the
buy it remembers may be gone, the resting order it forgot may be back, and
the tape from the new playhead is matched again against whatever still
rests. Nova's own bot bookkeeping is not exempt -- `working` rows for dropped
orders clear on the next TTL sweep.

## Small-cap filters

Action-kind allowlist: `buy_market`, `buy_limit_ask_offset`,
`sell_limit_bid_offset`, `sell_limit_ask_offset`, `exit_pos`,
`cancel_symbol`, `exit_pos_pct`, `sell_pos_pct_ask`,
`sell_pos_pct_bid_offset`.

- `buy_market`, `exit_pos` and `exit_pos_pct` are market orders and are
  refused `MKT_OUTSIDE_RTH` outside weekday 09:30-16:00 ET on every venue
  (the replay playhead on Sim). Premarket and after hours a bot enters with
  `buy_limit_ask_offset` and exits with `sell_pos_pct_bid_offset` -- the
  limit sweeps flatten itself uses.

- Max shares default 1, cap 10. Sizes come from the session preset.
- BP budget = open bot $ + working BUY reservations, hard max $50.
- New bot buy blocked while any bot working order exists.
- TTL auto-cancel default 3s (1-10). Nova cancels, not the brain.
- Extended hours off unless the session enables it.

## Breakers (whole-account Day P&L)

- `-$50`: MKT flatten all then L0. Desk may still trade. Header Activate
  re-enables the same day.
- `-$200`: flatten all, then lock bot **and** manual BUY until the next
  America/New_York midnight. Flatten / kill / cancel_working still spend.

## Your own brain

Nova ships no brain process. A brain of your own is a client of this API
(`bot/client.py`, `bot/sdk.py`): localhost only, `NOVA_API_KEY`, exclusive
claim + heartbeat, never PATCHes level, and every gate above applies to it.

## Curl (localhost)

```bash
# Session GET (no key)
curl -s http://127.0.0.1:8000/api/bot/session | python3 -m json.tool

# Mutating writes need the key. Brains cannot do these two calls.
curl -s -X POST http://127.0.0.1:8000/api/bot/session/arm \
  -H "X-Nova-Api-Key: $NOVA_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{}'

# Use desk_arm_token from the arm response -- GET never returns it.
curl -s -X PATCH http://127.0.0.1:8000/api/bot/session \
  -H "X-Nova-Api-Key: $NOVA_API_KEY" \
  -H "X-Nova-Desk-Arm: $DESK_ARM_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"level":2,"caps":{"max_shares":1,"bp_budget_usd":50,"working_ttl_sec":3}}'

# Alias path uses the same gate
curl -s -X POST http://127.0.0.1:8000/bot/session/claim \
  -H "X-Nova-Api-Key: $NOVA_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"brain_session_id":"nova-brain"}'

curl -s -X POST http://127.0.0.1:8000/api/bot/session/heartbeat \
  -H "X-Nova-Api-Key: $NOVA_API_KEY" \
  -H 'X-Nova-Brain-Session: nova-brain'

# L1 proposal -- does not place; symbol must be allowlisted and live
curl -s -X POST http://127.0.0.1:8000/api/bot/proposals \
  -H "X-Nova-Api-Key: $NOVA_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"ABCD","side":"BUY","kind":"buy_market","reason":"gap and tape","confidence":0.6}'

# L2 fire -- qty is the session preset, never send shares
curl -s -X POST http://127.0.0.1:8000/api/bot/action \
  -H "X-Nova-Api-Key: $NOVA_API_KEY" \
  -H 'X-Nova-Brain-Session: nova-brain' \
  -H 'Content-Type: application/json' \
  -d '{"kind":"buy_market","symbol":"ABCD"}'

# ws://127.0.0.1:8000/ws/bot/eyes
# ws://127.0.0.1:8000/ws/bot/audit
```

Focus live tabs are reported by the UI (`POST /api/bot/focus/sync`) so Eyes
share the max-3 Trader L2 cap. Do not open a private `reqMktData`.
