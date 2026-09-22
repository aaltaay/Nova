# IBKR Force One Share (MASTER TEST QTY GATE)

> **Status:** ACTIVE while `IBKR_FORCE_ONE_SHARE = True`  
> **Not a bug.** Intentional testing safety.

## What

Every `place` / `bracket` through ADR 007 `execution.service.execute` is **capped at `IBKR_FORCE_ONE_SHARE_QTY` shares** before validate/broker send, on every venue (Live, Paper, Sim). A size at or under the cap goes through as asked; a larger one is cut to the cap and the execution record stamps `forced_one_share`. `/api/ibkr/status` carries `qty_cap`, and the ticket's confirm dialog and footer say "sends N of M shares" so no surface names a size the door will not send.

**Operator decision 2026-09-22 (#444):** cap raised from a forced 1 share to **10 shares** ("I need to be able to buy max 10 shares ... still ignore 100 quantity"). The constant names are kept for continuity of the execution record.

**One place to change it:** `IBKR_QTY_CAP=<whole number>` in the desk `.env` (default 10 from `IBKR_FORCE_ONE_SHARE_QTY`). The clamp, `qty_cap` on the status payload and the ticket's copy all read that single value through `execution/qty_gate.py`; nothing else names the number.

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
