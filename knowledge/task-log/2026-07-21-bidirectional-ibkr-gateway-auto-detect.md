# 2026-07-21 — Bidirectional IBKR Gateway auto-detect (paper↔live heal)

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops | market-feed
- **Related:** `CHANGELOG.md` §2026-07-21 Bidirectional IBKR Gateway auto-detect · Phase B note in `Nova-Roadmap-Status.md`

## Task

Make the Gateway status chip reflect whether IBKR is actually logged in (and paper vs live), instead of staying “offline · PAPER” when only the live Gateway port is up.

## Goal

Preferred port hard-refused + alternate reachable → self-heal in either direction; header shows online with the correct LIVE/PAPER tag; spend gates unchanged.

## Why it mattered

Operator confusion: IB Gateway app showed connected (live) while Nova showed offline · PAPER because heal was one-directional. That looked broken even though it was intentional Phase B paper-pin behavior.

## What we changed

- `backend/ibkr/account_kind.py` — `accounts_match_mode(kind, mode_label)` for both directions; `paper_mode_accounts_ok` kept as wrapper
- `backend/ibkr/client.py` — `_accept_connected_session` always checks kind vs mode_label
- `backend/ibkr/gateway_heal.py` — bidirectional `heal_target_allowed`; docstring/log updates
- `backend/ibkr/client_connect.py` — alternate-port heal tries either direction
- Tests rewritten for paper→live heal + kind-mismatch refusal
- Rules/docs: `ibkr-gateway-login-warning.mdc`, `docs/ibc-gateway-setup.md`, Phase B note, CHANGELOG

## How it works now

If preferred Gateway port refuses and the other listens, Nova connects there, classifies managedAccounts, accepts only when kind matches the mode being established, persists `IBKR_GATEWAY_MODE`, and shows online · LIVE or online · PAPER. Intentional capsule switches still suppress heal mid-switch. Timeouts/Error 326 are not heal-eligible. Orders still need `IBKR_ORDERS_ENABLED` + live confirm for live spends.

## Why this approach

Rejected keeping the old paper-only pin: it optimized Phase B hygiene at the cost of lying about connection state. Auto-detect matches “Gateway = logged-in reality”; spend authority stays in `safety.py` so connecting to live never unlocks live orders. Symmetric account-kind checks close the prior live-mode gap (live sessions were accepted without kind validation).

## Verification

- `pytest tests/test_gateway_heal.py tests/test_ibkr_account_kind.py tests/test_gateway_mode_switch.py tests/test_port_diagnostics.py` → 28 passed
- Full backend pytest → 849 passed, 1 pre-existing `test_hod_momo_universe` failure
- Frontend vitest (header/disconnect/capsule) → 19 passed
- Manual: `/api/ibkr/status` → `connected=true`, `mode=live`, `spend_status=locked_live_unconfirmed`
- Browser: header button “IB Gateway connected · LIVE”

## Follow-ups

Phase B shadow days: keep Gateway logged into paper as operator discipline (no longer a hard software refuse of live). Yellow Historical Data Farm in the IBKR Gateway UI is IBKR farm status, not Nova.

## Keywords

ibkr, gateway, self-heal, bidirectional, paper, live, auto-detect, accounts_match_mode, disconnect_hint
