# 2026-07-18 — Fill now + EH flatten + Cancel+Flatten hotkey

- **Status:** completed
- **Agents:** parent
- **Domain:** hotkeys | widgets | execution (path alignment)
- **Related:** `CHANGELOG.md` §2026-07-18 Fill now · ADR 007

## Task

Add a panic control on working / partially filled orders (“fill immediately”), verify Flatten in extended hours, and ship useful cancel/flatten hotkeys.

## Goal

Traders can finish a stuck working order or get flat without guessing which button does what; EH market exits must not silently fail.

## Why it mattered

A partial working order that will not finish is a high-stress moment. Cancel alone leaves inventory; Flatten is position-scoped and previously forced RTH-only MKT so after-hours exits failed.

## What we changed

- **Fill now** on Working Orders: cancel order → MKT remaining qty (same side) via ADR 007
- Backend + execution validate: MKT may set `outside_rth`; STP still blocked
- Flatten / `exit_pos` / Ask± Bid±: auto `outside_rth` in pre/after-market (`extendedSession`)
- Nova Action **`cancel_and_exit`** (Ctrl+Shift+Backspace) = cancel-all symbol + flatten
- Existing **`cancel_symbol`** (Shift+Backspace) unchanged

## How it works now

| Control | Scope |
|---------|--------|
| Cancel | Remove resting order only |
| Fill now | Cancel that order + market its **remaining** shares |
| Flatten / exit_pos | Market to zero **position** |
| Cancel + Flatten | Cancel all symbol orders, then flatten position |

Sample Open Orders still hide mutation buttons.

## Why this approach

- Orchestrated cancel+place (not inventing a broker shortcut) keeps ledger/gates.
- Did not overload Flatten to mean “complete this order” — different risk (position vs remainder).
- Allowed MKT EH (not only aggressive LMT) so panic Fill/Flatten matches trader intent after hours; STP stays RTH-only.
- Rejected account-wide cancel-all (no symbol) for now — fat-finger surface; symbol-scoped matches existing cancel_symbol.

## Verification

- `pytest backend/tests/test_ibkr_orders.py`
- Vitest: fillWorkingOrderImmediately, extendedSession, closeFullPosition, WorkingOrdersPanel, novaActionDefaults

## Follow-ups

- Per-order Fill now hotkey needs a selected-order concept
- Confirm live Gateway accepts MKT+outsideRth for the user’s account permissions
- Refresh agent-hotkeys canvas when convenient

## Keywords

fill now, flatten, extended hours, outside_rth, cancel_and_exit, cancel_symbol, partial fill, ADR 007, Working Orders
