# ADR 013 -- IBKR account kind vs listen port vs requested door

**Status:** Accepted · **Date:** 2026-08-19
**Builds on:** [[007-centralized-trading-execution]] · paper/live Gateway switch
**Incident:** Live capsule snap-back (2026-08-19) -- paper `DU…` login on port 4001

## Context

Nova used one label (`IBKR_GATEWAY_MODE` / port 4001=live, 4002=paper) for three different facts:

1. **Requested door** -- what the operator clicked (Paper / Live).
2. **Listen port** -- which TCP port Gateway has open.
3. **Account kind** -- `managedAccounts` (`DU`/`DF` = paper, `U`/`F`/`I` = live).

Port 4001 can serve a paper login. This chat attached Nova to that socket so scanners worked, then a Live click reconnected to the same paper account and demoted the capsule back to Paper. The operator reasonably read "4001 + green chip" as already live.

`auto_live` stays NO-GO. Spend gates stay in `ibkr.safety`.

## Decision

1. **Account kind is the capsule SSOT** when a session is connected. The Paper/Live control shows the IB account class, not the port number.

2. **A user Live click is a door change, not a reconnect to whoever is on 4001.**
   - Already `account_kind=live` -> no-op (do not restart Gateway).
   - Target door port already listening (live=4001, paper=4002) -> **reconnect only**. No kill. No 2FA. That is the only fast flip.
   - Target door port dark -> `start_ibc` with `force_restart`. Stop both 4001 and 4002, then IBC that door. One IBC install retargets one Java window -- leaving paper up means live never gets a new login / phone 2FA.
   - Wrong class glued to the target port (paper session on 4001 while Live is requested) -> `replace_target` (same force restart).
   - Do not "follow paper" and clear Live intent during an explicit Live click. Intentional mode stays until that door connects.

3. **Unattended reconnect** (no sticky door intent) may still follow a listening alternate port so the desk is not empty overnight. That path must not run while an intentional Paper/Live click is unresolved.

4. **Header Desk chip** is connection/delayed only. It must not say LIVE as a synonym for "socket up."

5. **IBC `TradingMode` + API port + login id** are aligned only when **starting** that door. Live and paper may use different IB usernames (`IbLoginIdLive` / `IbLoginIdPaper`). One Gateway process is one account. Two simultaneous Gateways need a second IBC + `IbDir` (not shipped). 2FA is for a **new** live login (4001 dark), not for dialing an already-logged-in live Gateway. A new live login clears `Restart=OK` so IBKR Mobile can fire. Nova cannot send the phone prompt.

## Consequences

- `ibkr/mode_identity.py` owns the switch plan (`noop` / `reconnect` / `start_ibc` / `replace_target`).
- `launch_or_focus_gateway(..., force_restart=True)` stops **both** listen PIDs, then starts IBC for the requested door. Used for `start_ibc` and `replace_target`. `reconnect` does not call it.
- Capsule uses `broker_account_kind`, plus `intentional_gateway_mode` while a door change is in flight.
- Live spend still needs `IBKR_LIVE_TRADING_CONFIRMED`. This ADR does not arm live money.

## Rejected alternatives

- Treat 4001 LISTEN as live (today's incident).
- Silent follow-paper while the operator is mid Live click.
- Auto-promote paper → live without an explicit click.
- Restart Gateway on every Live click even when already a live account.
- Kill both Gateways on every Paper/Live flip, including when the target port is already up (forced 2FA on every click).
- Leave paper running and start a second IBC live from one install (IBC hijacks the paper window; no live 2FA).

## Related

- `backend/ibkr/mode_identity.py`
- `backend/ibkr/account_kind.py`
- `backend/ibkr/client_ops.py` `request_gateway_mode`
- `frontend/src/ibkr/GatewayModeCapsule.tsx`
- PROBLEM_LOG 2026-08-19 API Client 17 red / Live snap-back
