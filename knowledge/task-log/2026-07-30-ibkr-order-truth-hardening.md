# 2026-07-30 -- IBKR order-truth hardening (10349 / TIF / wedge)

- **Status:** completed
- **Agents:** parent
- **Domain:** execution / ibkr-ops / market-feed (in-session)
- **Related:** `CHANGELOG.md` §2026-07-30 IBKR order-truth hardening · `PROBLEM_LOG.md` §Error 10349 · §API_WEDGED

## Task

Address every mistake from the CYCU live-order investigation so Nova never again marks a still-working order as failed/Cancelled while IB holds it Pending.

## Goal

Order ledger, Working Orders, and Gateway agree; false 10349 cancels cannot fail a place; cancels are verified gone; wedged API is visible and less self-deepening.

## Why it mattered

Live BUY 1 CYCU looked "failed" in Nova while still PreSubmitted (held to next open). Operator risk: believe flat, then get filled at open; or trust UI and miss a live working order. Wedged API made positions/orders unreadable.

## What we changed

- Immediate: restarted wedged API; cancelled order 95053; verified open orders empty / no CYCU position.
- `ib_async` pin to git `next@c9f4c14` (10349 as warning; PyPI 2.1.0 still wrong).
- Always `tif=DAY` on Nova orders.
- ACK upgrade + place reject grace / open_orders heal.
- Ledger `broker_status` upgrade Cancelled→working; closed_orders debounce.
- `held_until` from Warning 399 on order rows.
- `cancel_order_verified` after cancel.
- `loop_lag.wedged` + `run_coro` inflight circuit when wedged.

## How it works now

First Cancelled from 10349 is not terminal. Working status (PreSubmitted/Submitted) upgrades the watch and ledger. Before writing `failed`, place path waits grace and checks openTrades. Cancel polls until the id is gone. Health exposes wedged lag so the UI can scream instead of spinning.

## Why this approach

- Upgrade `ib_async` from `next` (user request) even though PyPI is stuck on 2.1.0 -- library fix is the right root for 10349; Nova guards remain as defense in depth.
- Rejected "trust Cancelled forever" -- that is the bug.
- Rejected dual IB clients / dual Gateway trading -- out of scope; single session stays.
- Grace + open_orders heal is cheaper and more honest than requiring a second place.

## Verification

- Live: DELETE 95053 ok; `/api/ibkr/orders` = `[]`; positions no CYCU.
- pytest: false-cancel, TIF/held, finish_place reject, closed_orders, execution service/measurement, health (52 passed).
- Vitest: workingOrderCells + orderDisplay (19).

## Follow-ups

- Wire a visible UI banner when `loop_lag_ms.wedged` is true (health field is ready).
- Paper AH smoke place after next API start to confirm no 10349 ERROR lines.

## Keywords

10349, TIF, DAY, PreSubmitted, Cancelled, CYCU, 95053, order truth, API_WEDGED, cancel verify, held_until
