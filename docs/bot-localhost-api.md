# Bot localhost API (ADR 016)

Brain-agnostic HTTP + WebSocket on loopback. MCP / Astra / Fable are clients
later. Advise never places. Every order goes through
`execution.service.execute` with `source=bot`. No SendKeys. No free-form qty.

OpenAPI: `GET http://127.0.0.1:8000/openapi.json` (tags `bot`, `bot-ws`).
Aliases exist without the `/api` prefix (`/bot/session`, ...).

Loopback only (`127.0.0.1`, `::1`, `localhost`). L3 Unrestricted is parked
(`#216`) -- `PATCH` level 3 returns `409 BOT_L3_PARKED`.

## Autonomy

| Level | Name | What the brain may do |
|---|---|---|
| 0 | Off | `GET /session` only. Everything else is dark. |
| 1 | Eyes | Watch quotes + submit proposals. Human places. |
| 2 | Strategy | Fire allowlisted `NovaActionKind` values. One exclusive `brain_session_id`. First sub-strategy is `small-cap`. |
| 3 | Unrestricted | Parked. |

Proposal schema (L1): `symbol`, `side`, `kind`/`action`/`shortcut`, session
preset qty, short `reason`, optional `confidence` 0..1.

L2 header: `X-Nova-Brain-Session: <id>` or `brain_session_id` in the body.

## Small-cap filters

Allowlist: `buy_market`, `buy_limit_ask_offset`, `sell_limit_bid_offset`,
`sell_limit_ask_offset`, `exit_pos`, `cancel_symbol`, `exit_pos_pct`,
`sell_pos_pct_ask`, `sell_pos_pct_bid_offset`.

- Max shares default 1, cap 10. Sizes come from the session preset.
- BP budget = open bot $ + working BUY reservations, hard max $50.
- New bot buy blocked while any bot working order exists.
- TTL auto-cancel default 3s (1-10). Nova cancels, not the brain.
- Extended hours off unless the session enables it.

## Breakers (whole-account Day P&L)

Meter is IBKR RealizedPnL + UnrealizedPnL minus session commissions
(includes manual).

- `-$50`: MKT flatten all (existing door, 1 retry, system alert) then L0.
  Desk may still trade. Manual re-enable same day.
- `-$200`: flatten all, then lock bot **and** manual BUY until the next
  America/New_York midnight. Flatten / kill / cancel_working still spend.

## Curl (localhost)

```bash
# Session (L0 is a valid GET)
curl -s http://127.0.0.1:8000/api/bot/session | python3 -m json.tool

# Desk arms Eyes, then Strategy (small-cap)
curl -s -X PATCH http://127.0.0.1:8000/api/bot/session \
  -H 'Content-Type: application/json' \
  -d '{"level":1}'

curl -s -X PATCH http://127.0.0.1:8000/api/bot/session \
  -H 'Content-Type: application/json' \
  -d '{"level":2,"caps":{"max_shares":1,"bp_budget_usd":50,"working_ttl_sec":3,"extended_hours":false}}'

# Exclusive L2 brain
curl -s -X POST http://127.0.0.1:8000/api/bot/session/claim \
  -H 'Content-Type: application/json' \
  -d '{"brain_session_id":"brain-1"}'

# L1 proposal -- does not place
curl -s -X POST http://127.0.0.1:8000/api/bot/proposals \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"ABCD","side":"BUY","kind":"buy_market","reason":"gap and tape","confidence":0.6}'

# L2 fire -- qty is the session preset, never send shares
curl -s -X POST http://127.0.0.1:8000/api/bot/action \
  -H 'Content-Type: application/json' \
  -H 'X-Nova-Brain-Session: brain-1' \
  -d '{"kind":"buy_market","symbol":"ABCD"}'

# Eyes + audit sockets
# ws://127.0.0.1:8000/ws/bot/eyes
# ws://127.0.0.1:8000/ws/bot/audit
```

Mutating routes also take `X-Nova-Api-Key` when `NOVA_API_KEY` is set.
Focus live tabs are reported by the UI (`POST /api/bot/focus/sync`) so Eyes
share the max-3 Trader L2 cap. Do not open a private `reqMktData`.
