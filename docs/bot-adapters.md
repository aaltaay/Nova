# Bot adapters (optional, never core)

Nova's bot contract is the localhost OpenAPI. Adapters are clients. They
are not imported by `routes/bot.py` or the fire path. Do not start an MCP
server inside Nova. Do not marry Grok or any other model vendor.

## Client contract

- Spec: `GET http://127.0.0.1:8000/openapi.json` (tag `bot`)
- Human map: `docs/bot-localhost-api.md`
- Python client: `from bot.sdk import BotApiClient` (re-exports
  `nova_brain.client.BotApiClient`)
- Tool map: `from bot.mcp_adapter import TOOLS, DESK_ONLY`

`TOOLS` are what a brain/MCP host may call. `DESK_ONLY` (`/session/arm`,
`/session/disarm`, `PATCH /session`) stay on the desk. A brain that PATCHes
`level` to 2 is a contract violation even if it somehow has a token.

Required headers on mutating calls:

- `X-Nova-Api-Key: $NOVA_API_KEY`
- `X-Nova-Brain-Session: <exclusive id>` for claim / heartbeat / fire

Never send `X-Nova-Desk-Arm` from an adapter.

## What this is not

- Not a running MCP server
- Not a second order door
- Not a Grok/Astra/Fable SDK pin
- Not allowed to raise autonomy or Activate

If you want MCP later, wrap `TOOLS` in a host process outside this repo
and keep using the same HTTP paths.
