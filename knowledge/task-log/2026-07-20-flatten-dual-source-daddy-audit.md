# 2026-07-20 — Flatten dual-source position SSOT daddy audit

- **Status:** completed (audit / plan expansion only — no product code)
- **Agents:** daddy (hub) · [execution](6718f9f2-4776-4c8a-8aa7-4d6f75f8471f) · [maintainer](27690445-88d4-424c-9e88-25e82ec53756)
- **Domain:** trading execution / ADR 007 / fleet qty SSOT
- **Related:** execution task-log `2026-07-20-flatten-position-qty-dual-source-audit.md` · draft plan `flatten_sell_refusal_14e16b28.plan.md`

## Task

User Flatten → `SELL refused — no long position to reduce` while Positions showed SPY qty 1. Expand remediation beyond a validate.py symptom patch: inventory same-nature dual-source bugs and one coherent SSOT for parent plan update.

## Goal

Report-only: classify → parallel audit → aggregate inventory + SSOT design + ordered work + verification + rejected alternatives. No `backend/` / `frontend/` product edits; `auto_live` NO-GO.

## Why it mattered

Display (`ib.portfolio`) and safety gates (`ib.positions`) answered “do we have a long?” differently. Patching only the gate to portfolio would leave Nova OS flatten on the other cache (naked-cancel risk) and could false-allow OVERSELL if portfolio qty is inflated.

## What we changed

- Dispatch: parallel `execution` + `maintainer` (audit-only).
- No product code.
- This aggregate task-log + daddy memory run-log.
- Specialist also wrote `knowledge/task-log/2026-07-20-flatten-position-qty-dual-source-audit.md`.

## How it works now (current truth — pre-fix)

| Surface | Qty source |
|---------|------------|
| Positions UI | `GET /positions` → `get_portfolio()` → `ib.portfolio()` |
| Manual Flatten / Close / `exit_pos` / Fill-now SELL | FE sizes from portfolio; place `source="manual"`; gate `_position_qty` → `get_positions()` |
| Nova OS typed flatten | `_actual_position_qty` → `get_positions()`; place `source="flatten"` skips validate anti-short |
| FE last-good | `useIbkrAccount` keeps prior portfolio rows on 503 |

## Why this approach

**SSOT (chosen):** one `ibkr.account` helper (e.g. `long_qty(symbol)`) backed by **`ib.positions()`**, consumed by validate, `executor_flatten`, and `/positions` **qty** (portfolio joins mark/PnL only). Refresh/subscribe positions so the cache is not silently empty while portfolio shows shares. Distinguish `POSITION_UNAVAILABLE` from `NO_POSITION`.

**Why positions not portfolio as primary:** safety paths already trust positions; moving gates to portfolio can false-allow short if portfolio is high/stale. Better: UI qty follows the same fail-closed truth as gates, after making that truth fresh.

**Rejected:** validate-only→portfolio; UI Flatten `source="flatten"`; `max(positions, portfolio)`.

## Verification

Deferred to implement phase (see Daddy report / plan expansion). Existing scoped pytest still green under audit (`test_execution_service` + `test_execution_validate` = 19 passed per execution).

## Follow-ups

Parent updates draft plan with SSOT + file order; execute only when user says execute. Optional FE: block Flatten when `useIbkrAccount.error` (last-good).
