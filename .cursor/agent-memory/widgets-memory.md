# Widgets memory

Living knowledge for Nova's `widgets`. Read this file and
`docs/webull-widget-parity.md` at the start of every run. The capability map is
canonical; this memory tracks summary state, durable lessons, and next work.

## Current snapshot

```yaml
captured_at: 2026-07-18T22:15:00-04:00
source_revision: working-tree-2026-07-18
result: CLOSED_ORDERS_WID027
metrics:
  capabilities_total: 27
  matched: 7
  partial: 14
  missing: 5
  nova_only: 0
  not_comparable: 1
  unknown: 0
blockers: []
dashboard_freshness: clean
notes: "WID-027 Closed Orders feature slice + Positions Flatten via closeFullPosition (ADR 007). WID-020 narrowed to CSV/multi-day export. auto_live still NO-GO."
```


## Durable rules

- The canonical map is `docs/webull-widget-parity.md`; Canvas data is a dated
  presentation snapshot.
- Preserve stable `WID-NNN` capability IDs.
- Split complex widgets into atomic capabilities when one-to-one mapping would
  otherwise hide a partial gap.
- Require dated public Webull evidence and a Nova code path, test, or browser
  observation before changing status.
- Distinguish visual, functional, data-source, and operational parity.
- Webull is research-only. Never use Webull quotes, depth, tape, account data,
  or orders in Nova.
- Manual controls come before broader automation. Preserve Buy, Sell, Market,
  Limit, Flatten/Close, Confirm, Auto Paper, Signal, and Stop Automation while
  adding new knobs. Stock View header may hide the automate cluster when the
  user asks for capsule chrome — keep those controls on Trading → ExecutorPanel.
- Stock View header strip: symbol/price, Net Liq, BP, Paper/Live capsule,
  Manual/Normal/Fully Automated (Normal only; Fully Automated stays NO-GO),
  trading lock. Paper/Live mirrors Gateway mode and never silently arms live.
- Stock View rail: Level 2 and Time & Sales stay **side-by-side in one module**.
  The horizontal drag bar reallocates height between that combined depth block
  and **Order Entry** — never between L2 and T&S. Never remove the Open /
  Unlock Trading / ManualOrderTicket surface when adjusting layout.
- Working Orders (WID-026): primary surface is Trading tab account column;
  Stock View shows a symbol-scoped card under Trade only when working orders
  (or a just-placed highlight) exist. Cancel only — no modify, no auto_live.
- Closed Orders (WID-027): isolated `frontend/src/closed_orders/` slice +
  workspace registry `closed_orders` for Modules hide/show. Session terminal
  orders from `GET /api/ibkr/orders/closed`. No Cancel on this panel.
- Flatten / Close position ≠ Cancel: Flatten uses `closeFullPosition` →
  `placeIbkrOrder` (ADR 007). Cancel uses DELETE working-order routes.

## Backlog

- [ ] Implement WID-020 CSV / multi-day History Records export (after Closed
      Orders usage evidence); still no order-edit until export exists.
- [ ] Audit exact chart indicator/drawing coverage against WID-005.
- [ ] Break WID-009 research into fundamentals, statements, analyst estimates,
  ownership, and short-interest capabilities.
- [ ] Specify a paper-first Active Trade/TurboTrader panel without enabling
  live one-click execution.
- [ ] Research whether IBKR can provide an entitlement-honest NOII equivalent.
- [ ] Prioritize Price Ladder staging versus Chart Trading after the manual
  ticket has real usage evidence.
- [ ] Optional: Stock View dock for Closed Orders (symbol-scoped) once Trading
      usage is proven.

### Completed

- [x] 2026-07-18 — WID-027 Closed Orders feature slice + Positions Flatten
      (`closeFullPosition`); S15/S17 History/Closed surface documented; WID-020
      narrowed to export.
- [x] 2026-07-18 — WID-026 Working Orders panel (Trading + Stock View rail) +
      open_orders fill columns; research S17; column map in parity doc.
- [x] 2026-07-16 — Stock View header capsules (Paper/Live, mode, lock); removed Close/Hide charts/automate cluster from header.
- [x] 2026-07-16 — Established 25-capability public Webull-to-Nova baseline.
- [x] 2026-07-16 — Defined evidence, status, stable-ID, and safety rules.
- [x] 2026-07-16 — Created dedicated `agent-widgets` dashboard assignment.
- [x] 2026-07-16 — Added direct S1–S16 evidence keys to every capability row.

## Run log

<!-- RUN_LOG_START -->

### 2026-07-18 — Closed Orders widget + Flatten (WID-027)

- **Scope:** Research Webull History / filled+cancelled (S15, S17) + ship
  isolated `closed_orders/` slice; Positions Flatten via ADR 007 place path.
- **Result:** WID-027 added; WID-020 narrowed to CSV/multi-day; registry module
  for hide/show; `GET /api/ibkr/orders/closed`; Cancel vs Flatten copy clear.
- **Learning:** Public Webull FAQs never name a literal "Closed Orders" tab —
  map to History → Orders Records + S15 filled/cancelled lifecycle. Keep the
  feature out of StockViewPage monolith (ADR 005) so Modules can hide/move it.
- **Verified:** Vitest closed_orders + closeFullPosition + registry; pytest
  test_closed_orders (hand tester for full UI gates).

### 2026-07-18 — Working Orders post-place panel (WID-026)

- **Scope:** Research Webull Orders → Working / history (S15, S17) + ship thin
  Nova WorkingOrdersPanel wired to GET /api/ibkr/orders (no live orders in test).
- **Result:** Column map documented; `open_orders` adds filled/remaining/avg;
  Trading highlights just-placed id; Stock View rail card under Trade when
  symbol has working orders. WID-020 remains history/export gap.
- **Learning:** Webull public docs name lifecycle statuses and Working tab
  paths but not an exhaustive column schema — map IBKR openTrades fields to
  those concepts; keep history/export as a separate capability (WID-020).
- **Verified:** Vitest WorkingOrdersPanel + stockViewTerminal; pytest
  test_open_orders_row.

### 2026-07-16 — Stock View trading header cleanup

- **Scope:** Implementation — replace Confirm/Auto Paper/Signal/Stop Automation
  + LIVE badge + Close + Hide charts with Paper/Live capsule, Manual/Normal/
  Fully Automated capsule (Normal only), Net Liq/BP, trading lock.
- **Result:** Header chrome cleaned; `auto_live`/Fully Automated stay disabled;
  Paper/Live click only surfaces reconnect/confirm guidance (no silent arm).
- **Learning:** Operator knobs removed from Stock View header must remain on
  Trading → ExecutorPanel; Paper/Live must mirror Gateway `mode`, not invent a
  client-side mode that bypasses spend gates.
- **Verified:** Vitest StockViewHeader + stockViewTerminal (15 passed).

### 2026-07-16 — Stock View L2+T&S / Order Entry layout correction

- **Scope:** Implementation — restore combined L2|T&S; move horizontal splitter
  to depth vs Open ticket; keep ManualOrderTicket.
- **Result:** Side-by-side `.depth-and-tape` in one card; rail trade-stack
  splitter persists `nova.stockView.depthOrderSplitPct` (default 72% depth).
- **Learning:** "Horizontal drag for more L2 space" means more height for the
  combined depth module versus the order ticket — not a split between L2 and
  T&S. Confirm layout intent before moving ResizeHandle targets.
- **Verified:** `npm run test -- --run src/stock_view/stockViewTerminal.test.tsx`
  (11 passed).

### 2026-07-16 — Row-level evidence hardening

- **Scope:** Follow-up smoke audit of the 25-row baseline.
- **Result:** Counts unchanged; every capability now cites one or more S1–S16
  Webull sources directly in its row.
- **Learning:** A source list at the bottom is insufficient when readers cannot
  tell which claim it supports. Keep row-level evidence keys mandatory.

### 2026-07-16 — Initial stock/day-trading baseline

- **Scope:** Public Webull stock/ETF and active-trading widgets versus Nova.
- **Result:** BASELINE — 7 matched, 12 partial, 5 missing, 1 not-comparable.
- **Sources:** Webull Desktop, active-trading, order-type, extended-hours,
  fractional-share, navigation, and Desktop 4.0 public pages; Nova registry and
  relevant frontend/backend feature paths.
- **Learning:** Webull advertises 45+ widgets but does not publish a complete
  current public catalog. The ledger must remain source-verifiable rather than
  pretending that marketing count is enumerable.
- **Files established:** `docs/webull-widget-parity.md`, this memory,
  `agent-widgets.canvas.tsx`.

<!-- RUN_LOG_END -->
