# 2026-07-18 — Closed Orders widget (WID-027) + Flatten SSOT

- **Status:** completed
- **Agents:** widgets (daddy-orchestrated)
- **Domain:** widgets / trading UI
- **Related:** `CHANGELOG.md` §2026-07-18 Closed Orders · WID-027 · WID-020 · ADR 005 · ADR 007

## Task

Research Webull Closed/Filled/History orders UI; ship an isolated Closed Orders
widget plus full-position Flatten affordances through the existing execution SSOT.

## Goal

Operators can see session filled/cancelled orders (Webull History lifecycle) and
flatten an entire position without confusing that with Cancel on working orders;
the Closed Orders UI is a hideable feature slice ready for future drag-drop.

## Why it mattered

Working Orders (WID-026) covered open status after place, but filled/cancelled
history and a clear Flatten control were still gaps versus Webull Account →
Orders / History. Baking another table into StockViewPage would fight workspace
hide/move goals.

## What we changed

- Added WID-027; narrowed WID-020 to CSV / multi-day export.
- Backend: `closed_orders()` + `GET /api/ibkr/orders/closed`.
- Frontend feature slice `frontend/src/closed_orders/` + registry module.
- Shared `ibkr/closeFullPosition.ts` used by Positions Flatten and Stock View
  Flatten (same path as hotkeys `exit_pos` → `placeIbkrOrder` / ADR 007).
- Docs, widgets memory, agent-widgets canvas, CHANGELOG.

## How it works now

- **Working Orders (WID-026):** cancel working order only.
- **Closed Orders (WID-027):** session terminal IBKR trades; All / Filled /
  Cancelled filters; Modules → Closed Orders toggles visibility on Trading tab.
- **Flatten:** market exit of full position qty via `POST /api/ibkr/order`.
  Spend gates unchanged; `auto_live` NO-GO.
- Sample rows appear only when the session has no closed orders (preview).

## Why this approach

- **Chose** a new WID-027 atomic capability over stuffing history into WID-026:
  Webull separates Working from History; mixing cancel + filled tables hides gaps.
- **Chose** ADR 005 feature slice + registry id over embedding in StockViewPage:
  Modules hide/show works today; move/drag-drop can host the same module later.
- **Chose** `ib.trades()` terminal filter over inventing a ledger-only history:
  broker session truth matches Working Orders' IBKR source; CSV export (WID-020)
  can layer later without a second broker path.
- **Chose** `closeFullPosition` → place path (hotkeys exit) over Nova OS
  account-wide flatten for per-row Positions Flatten: symbol-scoped, same gates
  as manual ticket; executor flatten remains the typed-confirm all-positions tool.
- **Rejected** authenticated Webull scrape — public S15/S17 suffice.
- **Rejected** Cancel on Closed Orders rows — cancel is Working-only.

## Verification

- `py -3 -m pytest backend/tests/test_closed_orders.py -q`
- `npm run test -- --run src/closed_orders src/ibkr/closeFullPosition.test.ts src/workspace/registry.test.ts`
  (from `frontend/`)
- Full browser / build gates → tester handoff (no live orders placed).

## Follow-ups

- WID-020 CSV / multi-day History Records export.
- Optional Stock View symbol-scoped Closed Orders dock.
- Do not enable `auto_live` or order-modify until export usage exists.

## Keywords

closed orders, WID-027, Flatten, closeFullPosition, ADR 007, Working Orders, Webull History, feature slice
