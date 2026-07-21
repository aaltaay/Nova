# Paper orders field checklist (L4)

**~10–15 minutes.** Human-only rehearsal on **paper** Gateway. Agents and CI must **not** place, modify, or cancel orders for this checklist (see tester hard ban).

Use after Open/Closed Orders UI or qty/time math changes. Automated pyramid layers (Vitest / pytest contract / Playwright mocks) already cover fixtures; this catches live IB trade-log / remaining quirks.

## Preconditions

1. UI + API running (`Run Nova.bat` or uvicorn + Vite).
2. `GET /api/ibkr/status` → `connected: true`, `mode: paper` / `gateway_mode: paper`, `broker_account_kind: paper`, `spend_status: paper_armed`.
3. `live_trading_confirmed: false` (keep it that way).
4. Stock View open on a liquid paper symbol you can leave small.

## Steps

| # | Action | Pass when |
|---|--------|-----------|
| 1 | Place a small **LMT** (Open Orders). | Row appears with **Time**, Qty, Status, Limit, Order ID. |
| 2 | Note the **Time** value. Wait for a partial fill (or leave working). | **Time does not crawl** / does not jump to “now” on refresh. |
| 3 | Check **Filled** / **Remaining**. | Remaining ≈ qty − filled (or matches IB remaining). No "—" while Fill now is enabled. |
| 4 | Check **Average fill** after a partial. | Non-zero after fills; blank/"—" only when unfilled. |
| 5 | **Cancel** remaining after a partial (optional). | Closed tab: **Cancelled (partial fill)**; filled qty + avg kept. |
| 6 | Optional **Fill now** on a working remainder — **you** click only. | Resting cancelled; market remainder same side; no surprise live port. |

## Fail → log

If any step fails, prepend `PROBLEM_LOG.md` (Symptom / Cause / Fix / Keywords) and keep paper pin gates unchanged.

## Related

- Automated pyramid: `npm run test:orders-pyramid` (frontend) + `py -3 -m pytest backend/tests/test_orders_api_contract.py …` (repo root).
- Playwright mocked dock: `npm run test:e2e -- e2e/open-closed-orders.spec.ts`.
- Phase B ops: [paper-shadow-protocol.md](./paper-shadow-protocol.md).
