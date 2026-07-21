# 2026-07-19 — Orders testing pyramid L1-L4

- **Status:** completed
- **Agents:** parent
- **Domain:** tester / execution UI
- **Related:** `CHANGELOG.md` §2026-07-19 Orders testing pyramid · `docs/paper-orders-field-checklist.md`

## Task

Implement the orders testing pyramid so Open/Closed qty, price, and time regressions are caught without placing real orders.

## Goal

L1 Vitest + L2 API contract + L3 Playwright mocks green; L4 human paper checklist documented; tester recipe wired.

## Why it mattered

Unit display tests alone left Remaining/Fill and live Gateway quirks uncovered. Tester must never place/cancel; pyramid separates mock automation from human paper smoke.

## What we changed

- L1: `closedFillProgressAcceptable`, broker-remaining-preferred tests, closed mock coherence
- L2: `backend/tests/test_orders_api_contract.py`
- L3: `frontend/e2e/open-closed-orders.spec.ts` + `e2e/fixtures/orderRows.ts` (hard-ban place/cancel)
- L4: `docs/paper-orders-field-checklist.md` linked from paper-shadow protocol
- Wiring: `npm run test:orders-pyramid`, `test:e2e:orders`, `.cursor/agents/tester.md` recipe

## How it works now

Code changes → L1→L3. Gateway-only risks → human L4. Agents never click Fill now / Cancel on live paper for verification.

## Why this approach

- Rejected live auto-place in CI (tester ban + `auto_live` NO-GO).
- Playwright mocks catch Stock View dock wiring; pytest catches HTTP JSON invariants; Vitest catches pure math.
- Trust IB remaining when present (documented + tested) rather than silently recomputing.

## Verification

- `npm run test:orders-pyramid` → 43 passed
- `py -3 -m pytest backend/tests/test_orders_api_contract.py …` → 12 passed
- `npm run test:e2e:orders` → 2 passed

## Follow-ups

- Optional CI job for L1+L2 on every PR; L3 with existing Playwright gate.
- Humans run L4 after meaningful order-UI releases.

## Keywords

orders pyramid, Playwright mock, orderQtyMath, paper checklist, tester recipe, Remaining, submitted_at
