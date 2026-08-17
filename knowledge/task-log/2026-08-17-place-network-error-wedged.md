# 2026-08-17 -- Place showed Network error; order never reached Gateway

- **Status:** completed
- **Agents:** parent
- **Domain:** execution
- **Related:** `PROBLEM_LOG.md` 2026-08-17 -- Place showed Network error · `CHANGELOG.md` same day

## Task

Explain and stop the live ticket "Network error" after a place.

## Goal

Tell the operator whether the order hit Gateway. Fail fast when the IB loop cannot take a place.

## Why it mattered

A live TRUG buy at 09:44:25 ET looked like a wifi failure. The ledger said `validated` with no `order_id`. Working orders were empty. Retrying blindly on live is dangerous.

## What we changed

- `execute` rejects place/cancel/replace with `IB_LOOP_WEDGED` after validate, before `ensure_handlers` / `placeOrder`.
- Ticket transport errors no longer say "Network error".

## How it works now

If IB-loop lag is wedged (historicals/charts), the ticket gets a clear "not sent" error. A dropped fetch tells you to check Working Orders.

## Why this approach

Rejected restarting the API (ADR 010: wedged is not a dead PID). Rejected leaving the catch-all (it hid the stall). Rejected auto-retry (live, unknown fill state).

## Verification

pytest wedged-place gate pass. Vitest transport + place timing pass.

## Follow-ups

Do not click Start API. The 09:44 TRUG row stays `validated` in the ledger (never sent). `IBKR_FORCE_ONE_SHARE` is still on (broker qty 1).

## Keywords

Network error, TRUG, IB_LOOP_WEDGED, validated, historical
