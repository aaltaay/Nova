# 2026-07-19 — Daddy: Filled / active-trade field audit + polish

- **Status:** completed
- **Agents:** daddy | widgets | tester
- **Domain:** widgets (orders UI)
- **Related:** WID-026 · WID-027 · WID-015 (out of scope) · specialist logs `2026-07-19-filled-active-trade-verify.md`, `2026-07-19-filled-polish-tester-verify.md`

## Task

User asked (via daddy) for the field where you “actually actively trade them” — like “filled” — and to create it cleanly if missing.

## Goal

Classify the ask against Open/Closed Orders, confirm or ship Filled/active-fill surfaces, verify with tester, report where to find them — without TurboTrader scope creep or live trading unlocks.

## Why it mattered

After status-matrix mocks, paper traders need clear fill progress while orders are still working (partial fills), not only terminal Closed “Filled” status.

## What we changed

- **Daddy:** classified → widgets then tester; no product code from daddy.
- **widgets:** verified Filled / Remaining / Average fill / Partially filled / Fill now already complete; polished discoverability tooltips only (`orderTableColumns`, working/closed cells + tests + CHANGELOG/parity/memory).
- **tester:** Vitest 42 + pytest orders L2 12 PASS; browser skipped (titles-only).

## How it works now

- **Open Orders (WID-026):** columns **Filled**, **Remaining**, **Average fill**; status **Partially filled** when 0 &lt; filled &lt; qty; **Fill now** cancels rest and markets remaining (not Flatten). Stock View dock uses full columns (`compact={false}`); sample rows hide mutation buttons.
- **Closed Orders (WID-027):** **Filled** + **Average fill**; filters include Filled / partial-cancel history.
- **Not this ask:** WID-015 Active Trade / TurboTrader one-click grid remains missing.

## Why this approach

- Interpreted “like filled” as fill-progress columns + Fill now on working orders (matches Open/Closed context), not WID-015 TurboTrader.
- Rejected inventing a duplicate column — evidence showed fields already shipped; polish tooltips instead of gold-plate UI.
- Sequenced widgets → tester (implement then verify); skipped execution audit (no ADR 007 change).

## Verification

- Widgets: Vitest 44; pytest orders contract 6.
- Tester: Vitest 42 (cells/columns/panels + orderQtyMath); pytest 12 (orders API / open / times / closed).

## Follow-ups

- Commit/push when user asks (prefer-ask git rule vs constitution).
- WID-015 only if user wants paper-first TurboTrader grid.
- WID-020 CSV / multi-day export still open.

## Keywords

filled, remaining, average fill, fill now, partially filled, WID-026, WID-027, WID-015, daddy dispatch, open orders, closed orders
