# IBKR Force One Share (MASTER TEST QTY GATE)

> **Status:** ACTIVE while `IBKR_FORCE_ONE_SHARE = True`  
> **Not a bug.** Intentional testing safety.

## What

Every `place` / `bracket` through ADR 007 `execution.service.execute` is rewritten to **1 share** before validate/broker send. TRADE UI qty (100 / 500 / 1000) can stay unchanged.

## Where

| Piece | Path |
|-------|------|
| Master key | `backend/constants_ibkr.py` → `IBKR_FORCE_ONE_SHARE` |
| Clamp | `backend/execution/qty_gate.py` → `apply_force_one_share` |
| Ingress call | `backend/execution/service.py` → first line of `execute()` |
| Continuity | `.cursor/rules/execution-continuity.mdc` |
| Validation note | `docs/trading-execution-validation.md` |

## Disable (one line)

```python
IBKR_FORCE_ONE_SHARE = False
```

Or delete `cmd = apply_force_one_share(cmd)` in `service.py`.

## Agent rule

Do **not** "fix" fills that are always 1 share while the form shows a larger quantity until this gate is flipped off.
