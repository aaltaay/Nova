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

## Amendment 2026-09-17 -- arming, packs, adapters (#218-#222)

8. **Desk Activate is the only L1->L2 raise.** POST `/api/bot/session/arm`
   issues `X-Nova-Desk-Arm`. PATCH level above Eyes without that token is
   `403 BOT_ARM_REQUIRED`. Brains never PATCH level and cannot call arm/disarm
   (`403 BOT_ARM_DESK_ONLY`). Strategy left tab is settings only.

9. **Heartbeat fail-closed.** Exclusive claim is bound to the current arm
   token. Fire needs a heartbeat newer than `BOT_HEARTBEAT_STALE_SEC` (15s).
   UI `live_fire_ready` is L2 + armed + alive heartbeat.

10. **Mutating bot routes always need `NOVA_API_KEY`**, including loopback,
    on both `/api/bot/*` and `/bot/*`. GET session/watch/proposals stay open.

11. **One active pack.** Day-one live pack is halt/LULD resume. Quote-spike
    is live: shared L1 last or bid/ask mid up `min_pct` in `window_sec`,
    Eyes proposes, L2 + Activate fires once. Volume stays a selectable
    stub (`BOT_PACK_STUB` if it fires). Small-cap remains the risk sleeve.
    Propose/fire require symbol allowlist AND live Trader focus.

12. **Adapters are clients.** `backend/bot/sdk.py` + `docs/bot-adapters.md`
    point at OpenAPI. No MCP server in core. No model-vendor marriage.

## Amendment 2026-09-17 -- LLM decide live fire + header checkbox (#225-#227)

13. **`llm-decide` is a selectable pack inside `nova-brain`.** Validated
    JSON may `POST /api/bot/action` only when pack is `llm-decide` **and**
    L2 **and** desk Activate **and** exclusive claim + fresh heartbeat
    **and** symbol is allowlist ∩ live focus. L1 or Activate off is
    propose-only (or idle). Activate is the go -- no second hidden arm
    flag. Spend/rate caps, audit, small-cap sleeve, breakers, and
    `NOVA_API_KEY` stay. Brains never raise autonomy.

14. **L2 header checkbox.** GlobalAppBar `BotArmControls` live on the
    bot-only second header row (issue #230). They show **Bot is in
    control** when level is L2. Checked = arm. Unchecked = Stop. Flashy
    when `live_fire_ready`. L0/L1 hide the checkbox. Pack picker and
    Strategy settings show one sentence per pack.

## Amendment 2026-09-18 -- Not-active reject + one Desktop API key (#205)

15. **Level and Active are separate on the fire path.** Choosing Eyes or
    Strategy does not enable live fire. `POST /bot/action` / `actions.fire`
    reject when the desk is Not active (`armed` and `has_desk_arm` are the
    session SSOT; both must be true) with `409 BOT_NOT_ACTIVE`, even if
    level is L2, the pack is live, and the symbol is allowlisted. Eyes stay
    `409 BOT_L1_NO_FIRE`. L2 → Eyes or L0 runs `clear_arm_fields` so
    `live_fire_ready` cannot stay true. `live_fire_ready` remains
    L2 + Active + fresh exclusive heartbeat. Brains still cannot raise
    autonomy.

16. **One `NOVA_API_KEY` for Desktop.** Packaged Electron has no Vite
    `VITE_NOVA_API_KEY`. Main reads the same repo / `NOVA_ENV_PATH` /
    userData `.env` the API already uses, exposes it on
    `novaDesktop.apiKey`, and `novaFetch` sends `X-Nova-Api-Key`. Do not
    generate a second key when that file already has one. Do not bake the
    key into the renderer bundle.

## Amendment 2026-09-18 -- Quote-spike live pack

17. **Quote-spike is a live pack.** Detection reads `ticks.last_quotes`
    last and the shared depth book mid (`bot.quotes`). No new
    `reqMktData`. Settings: `spike_kind`, `min_pct` (3), `window_sec`
    (5), `cooldown_sec` (30). Rising-edge only. Down moves do not fire.
    Volume pack stays stub; Scanner tab Volume boost is that signal's
    SSOT.

## Consequences

- `source="bot"` is a first-class ADR 007 source. Kill / flatten /
  `cancel_working` remain the only protective sources that may spend during
  a kill or a -$200 day lock.
- FastAPI `/openapi.json` plus `docs/bot-localhost-api.md` are the client
  contract. Adapters stay optional (`docs/bot-adapters.md`). No live IBKR
  order tests in CI.
- Same-day -$50 re-arm stays allowed from the header Activate control.
