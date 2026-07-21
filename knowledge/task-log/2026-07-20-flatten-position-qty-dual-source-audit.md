# 2026-07-20 — Flatten SELL refusal: position-qty dual-source audit

- **Status:** completed (audit-only; no product code)
- **Agents:** execution (auditor) · parent plan expansion
- **Domain:** trading execution / ADR 007
- **Related:** `PROBLEM_LOG.md` (empty-vs-failed positions read) · ADR 007 · `docs/trading-execution-validation.md`

## Task

Expand the Flatten “SELL refused — no long position” incident into a full inventory of same-nature dual-source position-qty bugs and one coherent SSOT design (user rejected a validate.py→get_portfolio symptom patch).

## Goal

Complete consumer inventory + recommended SSOT + rejected alternatives + ordered file list + verification tests for the parent plan — without weakening anti-short or unlocking `auto_live`.

## Why it mattered

Positions UI showed SPY qty 1 while Flatten refused with `NO_POSITION`. Display and the place gate answered “do we have a long?” from different IBKR caches (`ib.portfolio()` vs `ib.positions()`). A one-line validate swap would leave flatten reconcile, preview, and other callers on the other cache.

## What we changed

- Audit-only: no `backend/execution/` or product caller edits.
- Updated `.cursor/agent-memory/execution-memory.md` (durable dual-source facts + backlog).
- Refined `agent-execution` canvas open-crack callout.
- This task-log entry.

## How it works now (current truth — pre-fix)

| Surface | Qty source |
|---------|------------|
| `GET /api/ibkr/positions` | `account.get_portfolio()` → `ib.portfolio()` |
| Manual Flatten / Close / `exit_pos` / `%` sells | FE sizes from portfolio rows; place `source="manual"`; gate uses `validate._position_qty` → `get_positions()` → `ib.positions()` |
| Nova OS typed flatten | `_actual_position_qty` → `get_positions()`; place `source="flatten"` **skips** anti-short in validate (reconcile is the gate) |
| Failed IBKR read | Raises `IbkrAccountError` (not `[]`); validate collapses failure into `NO_POSITION` text; flatten aborts |

## Why this approach

**Recommended SSOT:** one `ibkr.account` helper (e.g. `net_long_qty(symbol)`) backed by **`ib.positions()` as qty truth**, with UI `/positions` qty taken from that same helper (portfolio used only to join PnL/mark). Ensure positions subscription/refresh so the cache is not silently empty while portfolio shows shares.

**Rejected:**

1. **Only change `validate._position_qty` → `get_portfolio`** — leaves `executor_flatten` / preview / future callers on `positions()`; two truths remain.
2. **UI Flatten with `source="flatten"`** — skips anti-short/OVERSELL for every UI close; forbidden.
3. **max(positions, portfolio) without SSOT** — papers over cache skew; races and false allows.
4. **Trust FE last-good qty alone** — last-good can disagree with a live empty/stale gate.

## Verification

- `py -3 -m pytest backend/tests/test_execution_service.py backend/tests/test_execution_validate.py -q` → 19 passed
- `py -3 tools/agent_contract.py` → PASS
- Latency probe not re-run (SLA unchanged; audit-only)

## Follow-ups

Parent implements SSOT per inventory (product ask). Tests listed in execution report. Do not reopen as validate-only.

## Keywords

`NO_POSITION`, `get_positions`, `get_portfolio`, dual-source, Flatten, anti-short, OVERSELL, `source=flatten`, ADR 007, last-good
