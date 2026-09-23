# ADR 027 -- The bot plays the operator's setups: packs retired, the read-out gates Strategy

**Status:** Accepted · **Date:** 2026-09-23
**Supersedes:** ADR 016 items 11, 13 and 17-19 (the one-active-pack catalog, `llm-decide`,
quote-spike, volume, OpenRouter in `nova-brain`) and the `nova-brain` sidecar
**Builds on:** [[016-bot-localhost-api]] · [[022-setup-scanner-tape-gate]] · [[025-retire-nova-os]]
**Decided by:** the operator, 2026-09-23 ("no, I don't think we need the old packs -- remove";
"keep the Strategy L2 + all setups from my material"; approved Bots mockup v4)

## Context

ADR 016 gave the bot a pack catalog: halt / LULD resume, quote spike, volume
boost and an OpenRouter "LLM decide". None of them came from the operator's
trading material and none was ever backtested. They ran in a separate
`nova-brain` process (`backend/nova_brain/`) that the Desktop app and
`Run Nova.bat` started beside the API.

The operator's own playbook is their private course material (it stays off
the repo on `F:\Nova`): first pullback, Gap and Go,
flat-top breakout, red to green, micro pullback, and more in the catalogue.
The research (Bot-Trading-Plan §2b-2f) failed the bar-only versions of Gap
and Go (A2), the first pullback (P1), flat top (P2) and red to green (P3).
ADR 022 built one live scanner -- the first pullback -- with a tape gate
and a scoreboard, and pre-registered a read-out (§2g): once **50 triggered
first-pullback setups had the tape at go**, they pass when their **average
net R is above +0.2 and above the blind / wait average**. Only a pass earns
an L2 first-pullback bot on Paper.

The Bots page still showed the pack picker, so the one strategy with
evidence behind it was nowhere on it.

## Decision

1. **The packs are removed.** `bot/packs.py`, `bot/llm_guard.py`,
   `POST /api/bot/llm/spend`, the whole `nova_brain` package (pack loop,
   halt-luld, quote-spike, volume, llm-decide, OpenRouter client, sensor
   context), the Electron `brainSidecar.mjs`, `scripts/Start-NovaBrain.ps1`
   and the brain window in `Run Nova.bat`. The session file drops
   `active_pack`, `pack_settings` and `llm` (schema 4; a v1-3 file loads
   with those keys stripped). The HTTP client the SDK and the MCP adapter
   use moves to `bot/client.py`. The localhost bot API itself -- levels,
   Activate, claim, heartbeat, proposals, `/api/bot/action`, allowlist,
   sleeve, breakers -- is unchanged: an external brain may still use it,
   under every gate below.

2. **The playbook.** The session carries `setup` (the chosen setup,
   `first_pullback`) and `setups: [{id, scanner: bool}]` for the operator's
   material: `first_pullback` (scanner: ADR 022), `gap_and_go`,
   `flat_top_breakout`, `red_to_green`, `micro_pullback` (no scanner yet).
   One setup plays at a time and only a setup with a scanner can be chosen;
   the others are listed with their research verdict so the operator sees
   the whole playbook, and each gains a scanner, a backtest and a read-out
   of its own before it can be chosen. Level (Off / Eyes / Strategy) stays
   the session's; it is the chosen setup's level.

3. **The read-out gates Strategy.** `setup_scanner/readout.py` computes the
   §2g read-out from `setups.db` (every day, `kind: first_pullback`): `go`
   and pooled `blind / wait` stats over triggered rows, `state: collecting
   | passed | not_passed | failed | unavailable`. It is judged on the first
   100 go setups (and the blind / wait rows over the same stretch), so
   waiting longer never turns a fail into a pass; `failed` is 100 go
   setups without a pass; `unavailable` while the store is not open.
   While it has not passed:
   - Activate at Strategy is refused `409 BOT_READOUT_NOT_PASSED`;
   - raising to Strategy is allowed (the operator can choose it) but lands
     **not active** -- Activate is cleared -- so the bot proposes like Eyes;
   - every L2 fire (`/api/bot/action`) is refused `409
     BOT_READOUT_NOT_PASSED`, whatever brain sends it;
   - `live_fire_ready` is false.
   The read-out is cached for `SETUPS_READOUT_CACHE_SEC` (30 s) and recomputed; a
   pass that later slips below the line closes the gate again.

4. **The chosen setup's trading rules gate entries at Strategy.** An L2
   BUY (`buy_*` kinds) is refused outside the material's window
   07:00-10:00 ET on the venue's clock (`BOT_OUTSIDE_WINDOW`) and after
   `BOT_ENTRIES_PER_DAY` (1) filled-or-sent bot entry that venue day
   (`BOT_DAY_TRADE_CAP`). Exits, cancels and protective sources are never
   gated by either.

5. **One gate list.** `GET /api/bot/session` adds `gates: [{id, ok,
   stage, detail}]` -- level, allowlist, desk armed, depth lines, read-out,
   bot trip, day lock, kill switch, entry window -- computed server-side in
   `bot/gates.py`, so the Bots page draws what the fire path checks.
   `stage` is `activate` (Activate at Strategy needs it) or `fire` (each
   order meets it on its own). `readout` is on the session payload too.

6. **Proposals at L1 and L2.** With `llm-decide` gone, a brain may submit a
   proposal at Eyes or Strategy; it never places. Setup-scanner proposals
   (ADR 022) stay on `/ws/setups`; the Bots page shows both in one inbox.

## Consequences

- Nothing Nova ships fires a bot order today: the only setup with a scanner
  has not passed its read-out, and the first-pullback L2 fire path itself
  (what the bot sends when a go setup triggers) is a follow-up once it
  passes -- #514, not guessed here.
- The Desktop app and `Run Nova.bat` start one process fewer. Anyone who
  ran their own brain against the API keeps the contract, minus the pack
  fields and `/llm/spend`.
- Advise (`/api/bot/advise`, OpenRouter, read-only) is unchanged.
- `auto_live` remains NO-GO.
