# ADR 018 -- Desk venue persists, spend arming does not

**Status:** Accepted -- operator approved 2026-09-20 on [#391](https://github.com/aaltaay/Nova/pull/391)
**Date:** 2026-09-20
**Builds on:** [[007-centralized-trading-execution]] · [[013-ibkr-account-vs-port]]
**Issue:** [#302](https://github.com/aaltaay/Nova/issues/302) (D-054) -- Backend restart silently drops the desk from Sim to Live
**Incident:** localhost watchdog restarts 2026-09-19 04:21 / 04:24 / 04:37 / 04:43 / 05:07 / 05:30 ET

## Context

The header Paper / Live / Sim capsule looks like one three-way control. It is not. Behind it sit two facts with opposite lifetimes:

| Fact | Where it lives | Survives a restart? |
|------|----------------|---------------------|
| **Venue** -- Sim vs IBKR | `sim/mode.py` `_override`, a module global | **No.** Process start re-reads `NOVA_BROKER`, which defaults to `ibkr`. |
| **Spend arming** -- may real money move | `IBKR_ORDERS_ENABLED`, `IBKR_LIVE_TRADING_CONFIRMED`, `IBKR_GATEWAY_MODE` read by `ibkr/safety.py` `spend_state()` | **Yes.** They are env, and env outlives the process. |

The safety choice is the one that evaporates; the spending permission is the one that persists. On 2026-09-19 the watchdog bounced the API six times between 04:21 and 05:30 ET. Each time, an operator practising in Sim came back to `mode: live`, `gateway_mode: live`, `orders_enabled: true`, `live_trading_confirmed: true`. The magenta SIM flag disappears, but nothing else announces the change. A keystroke that was a practice fill before the bounce is a real live order after it.

Three further details decide the shape of the fix:

1. **The capsule is already inconsistent.** `GatewayModeCapsule.tsx` `requestMode('paper'|'live')` posts `/api/ibkr/gateway-mode`, and `client_ops.request_gateway_mode` durably writes the choice via `gateway_heal.persist_gateway_mode` (an `IBKR_GATEWAY_MODE` rewrite in `.env`) before planning the reconnect. `requestSim()` posts `/api/sim {enabled: true}` and nothing is written. Two of the three buttons are sticky, and the one that is not is the only one that cannot lose money. `sim/routes.py` `SimToggleRequest` already carries `persist: bool = False` -- the field exists and the header never sets it.

2. **Venue is currently the authority for spending.** `ibkr/trading_allowed.py` `places_allowed()` returns `(True, "")` immediately when `is_sim_mode()`. Asking "what venue am I on" and "may I spend" is the same question in code today, which is exactly why losing the venue silently changes the answer.

3. **Sticky intent has hurt before.** `.cursor/rules/persisted-state.mdc` records that sticky paper/live intent once blocked morning attach, and ADR 013 rule 3 lets an unattended reconnect follow a listening alternate port precisely when no intentional click is unresolved. Any persistence added here must not resurrect an *in-flight switch* across a restart.

The four options put to the operator (persist Sim / always drop to IBKR / blocking modal / park) all answer "which venue do we land in". None of them changes whether we land **armed**, which is the part that spends money. That is why each option carries a weakness that cannot be argued away on its own axis.

`auto_live` stays NO-GO. Invariant #7 is unchanged. This ADR does not arm anything.

## Decision

**Split the one dial into two latches with deliberately opposite lifetimes.**

1. **Venue persists.** The header's Sim choice is durable exactly as Paper and Live already are. A restart returns to the venue the operator last chose. This is the operator's *settled* choice, not an in-flight switch.

2. **Spend arming never survives a process start.** A fresh process comes up **disarmed regardless of venue**. `IBKR_ORDERS_ENABLED` and `IBKR_LIVE_TRADING_CONFIRMED` keep their present meaning -- they say this desk is *permitted* to spend -- and a new runtime latch says whether it is *currently* armed. A real-money place needs both. The existing `spend_state()` gates are unchanged and still authoritative; the latch is an additional AND, never a bypass.

3. **Re-arming is an explicit action in the running process**, taken from the UI. It is never an `.env` edit and never inferred from the venue, the port, or a successful reconnect.

4. **Protective paths are never gated by the latch.** Cancel, flatten and KILL stay available while disarmed, matching the deliberately softer cancel gate already documented in `ibkr/safety.py`. A disarmed desk can always get flat; it just cannot open.

5. **Status reports both facts separately.** `/api/ibkr/status` and `/api/sim` name venue and arm state as distinct fields so no surface can say "practice" while the engine is armed for live. The header reads the snapshot, and a restart-induced venue change is visible rather than inferred from a missing banner.

6. **The persisted venue is an operator cache file, not `.env`.** It lives under `paths.cache_dir()` with the three things `persisted-state.mdc` requires: an owner (`sim/mode.py`), an invalidation trigger (operator venue click; process start reads it once), and an integer `schema_version` handled through `cache_schema.accept_schema` -- unknown version refuses loud, missing version is legacy. `NOVA_BROKER=sim` in `.env` stays what `docs/sim-mode.md` already calls it: an optional bootstrap default. Precedence is **cache file > env default**, because the cache records a click and the env records a machine default.

7. **Persist the settled venue, never the unresolved switch.** `gateway_heal.set_intentional_mode` stays process-local and is not written to the cache. A restart therefore starts with no intentional switch outstanding, so ADR 013 rule 3 (unattended reconnect may follow a listening alternate port) behaves on a fresh process exactly as it does today. This is what keeps decision 1 from repeating the morning-attach failure.

Under these latches the failure that started this ADR is unreachable from either direction. If the cache is present, the desk returns to Sim and nothing can spend. If the cache is missing, unreadable or of an unknown version, the desk falls back to the env default and comes up on IBKR **disarmed** -- market data, charts and scanners work, and no live order can leave until the operator arms it by hand.

## Consequences

- **Naming, fixed at approval:** the env flags are **`permitted`** (this desk is allowed to spend) and the runtime latch is **`armed`** (this process currently may). Implementation uses those two words and does not reuse "armed" for the env capability, so the two cannot be confused in code or in the status payload.
- The arm / disarm control does not exist today. Building it is part of the #302 implementation PR, not a follow-up.
- `sim/mode.py` gains the cache read on process start and the cache write on `set_sim_mode`, and keeps owning both. `persist_nova_broker` (the `.env` rewrite) is no longer the persistence path for the venue.
- `ibkr/safety.py` gains the runtime arm latch, AND-ed into `spend_state()`. Exit paths continue to bypass it.
- `ibkr/trading_allowed.py` `places_allowed()` stops treating "in Sim" as the answer to "may I spend"; venue routing and spend permission become separate reads.
- `GatewayModeCapsule.tsx` sets the `persist` field the API already accepts, and renders the arm state as its own affordance rather than implying it from the venue chip.
- A regression test asserts the property directly: **a process start whose previous venue was Sim never lands on IBKR with spending armed** -- covering both the cache-present and cache-missing paths.
- **Ergonomic cost, explicitly accepted by the operator at approval:** an arm click after each watchdog bounce. The operator trades the old failure (a silent armed-live desk) for a loud disarmed one. The two errors are not symmetric -- a desk stuck disarmed misses a fill, a desk silently armed spends real money -- so the latch is biased toward the recoverable error.
- `AGENTS.md` §5 and `docs/sim-mode.md` ("In-memory ledger only -- restart clears practice positions" and the Optional bootstrap section) are updated **in the implementation PR**, per the process the operator set on #302: ADR first, approval, then docs, then code.
- Nothing here changes Invariant #7, the IBKR-only feed, or the `auto_live` NO-GO.

## Rejected alternatives

- **Persist Sim and nothing else.** Halves the fix. The arming still persists, so a missing or unreadable cache lands on an armed live desk -- the exact 05:07 state.
- **Always drop to Paper/Live on restart, require explicit Sim re-arm.** Makes the dangerous state the default several times a morning and puts the burden of noticing on the operator, which is the burden that already failed twice.
- **Drop Sim and show a blocking modal.** The desk is still armed behind the modal, and a modal that appears on every watchdog bounce is trained away within a session.
- **Warning banner only.** Rejected by the operator on #302 on 2026-09-19: it leaves a live, armed desk immediately after a restart.
- **Park the issue.** P1 with two reproductions a day apart on the operator's own machine.
- **Persist the venue in `.env`.** No `schema_version`, shares a file with secrets and hand edits, and makes a safety choice depend on rewriting the file that also configures the spend gates.
- **Infer the arm state from a healthy Gateway connection.** Would re-arm on exactly the event the watchdog generates.

## Related

- `backend/sim/mode.py` · `backend/sim/routes.py` · `backend/constants_sim.py`
- `backend/ibkr/safety.py` · `backend/ibkr/trading_allowed.py` · `backend/ibkr/gateway_heal.py` · `backend/ibkr/client_ops.py`
- `backend/cache_schema.py` · `backend/paths.py`
- `frontend/src/ibkr/GatewayModeCapsule.tsx`
- `.cursor/rules/persisted-state.mdc` · `docs/sim-mode.md`
