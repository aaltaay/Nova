# 2026-07-20 — Flatten long_qty SSOT + BuyingPower fail-closed

- **Status:** completed
- **Agents:** parent (implement)
- **Domain:** trading execution / ADR 007
- **Related:** `CHANGELOG.md` §2026-07-20 long_qty · `PROBLEM_LOG.md` §dual-source + BuyingPower · plan `flatten_sell_refusal_14e16b28` · audits `2026-07-20-flatten-dual-source-daddy-audit.md`

## Task

Implement the approved flatten/sell refusal plan end-to-end: one broker long-qty SSOT, distinct unavailable vs flat reasons, BuyingPower fail-open fix, FE error gate, tests and docs.

## Goal

UI Positions qty, validate anti-short, and Nova OS flatten reconcile all answer “how many long shares?” from `ib.positions()` via `account.long_qty`. Portfolio is mark/PnL join only. Account summary failures refuse priced BUY.

## Why it mattered

Operators saw SPY qty 1 and Flatten refused `NO_POSITION` — trust-breaking and dangerous if OS flatten treated empty positions as flat then cancelled stops. BuyingPower swallow was fail-open on LMT BUY (worse class).

## What we changed

- `account.long_qty` + `positions_for_ui` + post-connect `refresh_positions_cache`
- `get_account_summary` / `refresh_account_summary` raise `IbkrAccountError`; `/account` 503
- validate: `POSITION_UNAVAILABLE` / `NO_POSITION` / `BUYING_POWER_UNKNOWN`
- `executor_flatten` via `long_qty`
- FE: Flatten/exit disabled when `useIbkrAccount.error`
- Tests + CHANGELOG / PROBLEM_LOG / ADR 007 / trading-execution note

## How it works now

```text
long_qty(symbol) → ib.positions() only → float | raises IbkrAccountError
  ├── validate manual SELL
  ├── executor_flatten reconcile + preview list still from get_positions
  └── GET /positions qty (+ portfolio MTM join)
```

UI Flatten stays `source="manual"`. OS place `source="flatten"` still skips validate anti-short; reconcile is the gate.

## Why this approach

**positions as SSOT (not portfolio):** safety paths already trusted positions; moving gates to portfolio can false-allow OVERSELL/short if portfolio is high/stale. Better: make positions fresh (connect refresh) and make UI qty follow the same fail-closed truth.

**Rejected:** validate→portfolio only; UI Flatten `source=flatten`; `max(positions, portfolio)`; trusting FE last-good as the live gate (we only disable Flatten when error is set).

**BuyingPower:** same swallow class as empty-on-error — raise and refuse priced BUY rather than disguise as disconnected summary.

## Verification

- `pytest` focused: 89 passed (`test_ibkr_account`, `test_execution_validate`, `test_execution_service`, `test_executor`, `test_orders_api_contract`, `test_routes_trading`)
- Vitest: ClosePositionButton + closeFullPosition 7 passed
- Paper buy→Flatten e2e optional (Gateway)

## Follow-ups

- Optional live paper Flatten e2e when Gateway logged in
- Kill/recovery `_open_positions` claim model still not SSOT (later)

## Keywords

long_qty, POSITION_UNAVAILABLE, NO_POSITION, BUYING_POWER_UNKNOWN, Flatten, positions vs portfolio, ADR 007, fail-closed
