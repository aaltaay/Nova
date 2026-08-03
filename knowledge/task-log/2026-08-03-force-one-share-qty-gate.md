# 2026-08-03 -- MASTER TEST QTY GATE (force one share)

- **Status:** completed
- **Agents:** parent
- **Domain:** execution
- **Related:** `CHANGELOG.md` §2026-08-03 -- MASTER TEST QTY GATE; [[IBKR-Force-One-Share-Test-Gate]]

## Task

Add one master key so every executed place/bracket is 1 share regardless of UI qty (100/500/1000), easy to remove in one line, documented so agents do not treat it as a bug.

## Goal

Broker send qty is always 1 while `IBKR_FORCE_ONE_SHARE` is True; UI/hotkey logic unchanged.

## Why it mattered

Fat-finger presets during paper/live testing can send large size; user wanted a hard testing clamp at the sole ADR 007 ingress.

## What we changed

- `IBKR_FORCE_ONE_SHARE` / `IBKR_FORCE_ONE_SHARE_QTY` in `constants_ibkr.py`
- `execution/qty_gate.py` + one call at top of `execute()`
- Docs: execution-continuity, trading-execution-validation, Obsidian decision note
- Tests: `test_execution_qty_gate.py`

## How it works now

UI may show any qty. `execute()` runs `apply_force_one_share` first; place/bracket qty+shares become 1 before validate/send. Cancel/replace untouched. Ledger payload can mark `forced_one_share`.

## Why this approach

Clamped at ADR 007 ingress (not UI) so every caller (TRADE form, hotkeys, Nova Actions, approve) is covered. Rejected env-only toggle as the primary key -- a code constant is the explicit one-line flip agents will see in review. Rejected frontend-only clamp (bypassable).

## Verification

`pytest tests/test_execution_qty_gate.py tests/test_execution_service.py` -- 21 passed.

## Follow-ups

Flip `IBKR_FORCE_ONE_SHARE = False` when done with 1-share testing.

## Keywords

force one share, IBKR_FORCE_ONE_SHARE, qty gate, ADR 007, testing safety
