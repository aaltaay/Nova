# 2026-07-18 — Hotkeys cancel ownership vs open-order cancel gate

- **Status:** completed
- **Agents:** hotkeys (daddy dispatch, audit-only)
- **Domain:** hotkeys
- **Related:** Phase G3 · ADR 007 · WID-026 · `hotkeys-continuity.mdc`

## Task

Clarify whether cancel-open-order / cancel-symbol-orders belong in the hotkeys Nova Action dispatcher or a dedicated IBKR/execution gate, given WorkingOrdersPanel per-order cancel and the user’s “single source of truth” ask.

## Goal

Ownership recommendation + crack list without implementing product code.

## Why it mattered

Duplicate cancel UX (hotkey cancel-all-for-symbol vs row ✕) risks agents funneling everything into the keyboard dispatcher, or inventing a second broker path. Future work needs a clear SSOT layering.

## What we changed

- Audit-only: no product code.
- Documented conclusion in this task log + hotkeys memory run log.

## How it works now

**Broker SSOT (backend):** every cancel — per-order `DELETE /api/ibkr/order/{id}` and symbol orchestration `DELETE /api/ibkr/orders?symbol=` — already enters `execution.service.execute(operation="cancel", source="manual")`. ADR 007 owns that path.

**Hotkeys owns (System 2 discretionary):** one typed Nova Action, `cancel_symbol` → `cancelAllOrdersForSymbol` → symbol DELETE. Wired through `runNovaAction` / one shell dispatcher / Trading quick-bar. Client gates: open symbol, IBKR connected, PIN unlock, spend lock. No place-confirm on cancel today. No `cancel_one` / buy-sell-scope Nova Actions yet (catalog notes only).

**Not hotkeys:** WorkingOrdersPanel (WID-026) row cancel is widgets/IBKR UI chrome. Parents (`StockViewPage`, `TradingTab`) call per-order DELETE directly. That must not mount a second `useHotkeys` or become a Nova Action kind unless a future chord explicitly maps “cancel selected order.”

**Imported `.htk`:** `CXL ALLSYMB` maps to `cancel_symbol` only after Map-to-Nova-Action; raw DAS cancel strings stay inactive.

## Why this approach

- Rejected “funnel WorkingOrdersPanel through hotkeys dispatcher”: dispatcher is for chords/quick-bar intents, not table row clicks; forcing UI through it would couple widgets to hotkeys and encourage a second listener.
- Rejected “hotkeys owns per-order cancel SSOT”: broker SSOT is already ADR 007 `execute(cancel)`; hotkeys only orchestrates symbol-scope cancel as a Nova Action.
- Kept client gate gap visible: panel cancel skips PIN/spend that `gateManual` applies — that is an execution/safety policy question for a shared cancel helper, not a reason to absorb row cancel into hotkeys.

## Verification

Code read: `runNovaAction.ts`, `placeOrder.ts`, `trading.py` cancel routes, `WorkingOrdersPanel.tsx` + Stock View/Trading handlers, `capabilityCatalog.ts`, `hotkeys-continuity.mdc`, ADR 007. No vitest run (audit-only, no code change).

## Follow-ups

- Execution: shared client cancel helper + decide whether per-order cancel needs the same PIN/spend (and confirm) gate as Nova Actions; ledger honesty for both routes.
- Hotkeys: do not add `cancel_one` unless user asks for a chord; optional continuity one-liner clarifying panel cancel is out of dispatcher scope.
- Widgets: keep WorkingOrdersPanel as presentation + `onCancelOrder` callback only.

## Keywords

hotkeys, cancel_symbol, WorkingOrdersPanel, ADR 007, execution.service.execute, cancel-all, Nova Actions, Phase G3, SSOT, auto_live NO-GO
