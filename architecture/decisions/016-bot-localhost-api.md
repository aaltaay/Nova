# ADR 016 -- Localhost bot API (brain-agnostic)

**Status:** Accepted · **Date:** 2026-09-17
**Builds on:** ADR 007 (one execution door) · ADR 011 (max-3 live Trader L2)
**Does not touch:** `auto_live` · L3 Unrestricted (#216 parked) · optional `nova` CLI

## Context

Ahmed locked a localhost bot contract (Nova Repo chat 2026-09-16/17, epic #205).
The brain lives **outside** Nova (MCP / Astra / Fable / scripts later). Nova
owns market data, risk, and the only order door. A second stack (SendKeys,
free-form qty, REST quote polls, a second broker path) was rejected.

## Decision

1. **Brain-agnostic localhost API.** OpenAPI + HTTP + WebSocket on loopback.
   Clients later. Advise never places.

2. **Same feed as the UI.** Eyes read `ticks.last_quotes` and the shared
   depth book. Bot focus is applied as Trader tabs and shares
   `TRADER_MAX_LIVE_TABS` / `IBKR_MAX_DEPTH_SYMBOLS` (3). No invisible feed.

3. **One risk gate; one execution door.** Allowlisted `NovaActionKind` values
   become `execution.service.execute(..., source="bot")`. No SendKeys. Qty
   comes from session presets (max shares 1-10), never free-form from the brain.

4. **Autonomy ladder.** L0 fully dark (GET session may report off). L1 Eyes
   watches and proposes; human places. L2 Strategy, first sub-strategy
   `small-cap`, one exclusive brain session. L3 is parked (#216).

5. **Small-cap filters.** Open $ + working reservations, hard max $50;
   block new bot buys while a bot working order exists; Nova TTL auto-cancel
   1-10s (default 3); EH off unless the session enables it.

6. **Breakers use whole-account Day P&L** (realized + unrealized, commissions
   count, includes manual). -$50 flatten-all then L0 with same-day manual
   re-enable. -$200 flatten-all then lock bot **and** manual buys until the
   next America/New_York midnight.

7. **Audit is append-only JSONL** with the locked schema. Every decision,
   breaker, TTL cancel, and Advise spend lands there.

## Consequences

- `source="bot"` is a first-class ADR 007 source. Kill / flatten /
  `cancel_working` remain the only protective sources that may spend during
  a kill or a -$200 day lock.
- FastAPI `/openapi.json` plus `docs/bot-localhost-api.md` are the client
  contract. No live IBKR order tests in CI.
