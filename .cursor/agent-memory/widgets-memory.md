# Widgets memory

Living knowledge for Nova's `widgets`. Read this file and
`docs/webull-widget-parity.md` at the start of every run. The capability map is
canonical; this memory tracks summary state, durable lessons, and next work.

## Current snapshot

```yaml
captured_at: 2026-07-16T22:26:00-04:00
source_revision: working-tree-2026-07-16
result: STOCK_VIEW_HEADER_CLEANUP
metrics:
  capabilities_total: 25
  matched: 7
  partial: 12
  missing: 5
  nova_only: 0
  not_comparable: 1
  unknown: 0
blockers: []
dashboard_freshness: clean
notes: "Stock View header uses Paper/Live + Manual/Normal/Fully Automated capsules and trading lock; Confirm/Auto Paper cluster removed from header only (ExecutorPanel keeps them)."
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

## Backlog

- [ ] Audit exact chart indicator/drawing coverage against WID-005.
- [ ] Break WID-009 research into fundamentals, statements, analyst estimates,
  ownership, and short-interest capabilities.
- [ ] Specify a paper-first Active Trade/TurboTrader panel without enabling
  live one-click execution.
- [ ] Research whether IBKR can provide an entitlement-honest NOII equivalent.
- [ ] Prioritize Price Ladder staging versus Chart Trading after the manual
  ticket has real usage evidence.

### Completed

- [x] 2026-07-16 — Stock View header capsules (Paper/Live, mode, lock); removed Close/Hide charts/automate cluster from header.
- [x] 2026-07-16 — Established 25-capability public Webull-to-Nova baseline.
- [x] 2026-07-16 — Defined evidence, status, stable-ID, and safety rules.
- [x] 2026-07-16 — Created dedicated `agent-widgets` dashboard assignment.
- [x] 2026-07-16 — Added direct S1–S16 evidence keys to every capability row.

## Run log

<!-- RUN_LOG_START -->

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
