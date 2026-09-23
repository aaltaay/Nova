# IBKR Force One Share (MASTER TEST QTY GATE)

> **Status:** ACTIVE on Live while `IBKR_FORCE_ONE_SHARE = True`; Paper and Sim uncapped  
> **Not a bug.** Intentional testing safety.

## What

Every `place` / `bracket` through ADR 007 `execution.service.execute` **on the Live venue** is **capped at `IBKR_FORCE_ONE_SHARE_QTY` shares** (1) before validate/broker send, and the IBKR send refuses anything still above it (`QTY_CAP_LIVE`). **Paper and Sim are not capped.** A size at or under the cap goes through as asked; a larger one is cut to the cap and the execution record stamps `forced_one_share`. `/api/ibkr/status` carries `qty_cap` (null on Paper / Sim), and the Live ticket's confirm dialog and footer say "sends N of M shares" so no surface names a size the door will not send.

**Operator decisions 2026-09-22 (#444):** first the cap was raised from a forced 1 share to **10 shares on every venue** ("I need to be able to buy max 10 shares ... still ignore 100 quantity"); later that day the operator settled the issue's option 1 instead: *keep one share on Live "so we never mess it up", and remove the restriction for Paper and Sim*. Practice is fake money with buying power enforced, so the gate protected nothing there and stopped real sizes being practised. The constant names are kept for continuity of the execution record.

**One place to change it:** `IBKR_QTY_CAP=<whole number>` in the desk `.env` (default 1 from `IBKR_FORCE_ONE_SHARE_QTY`) sets the Live cap. The clamp, the IBKR send check, `qty_cap` on the status payload and the ticket's copy all read that single value through `execution/qty_gate.py`; nothing else names the number. A venue that cannot be read counts as Live.

## Where

| Piece | Path |
|-------|------|
| Master key | `backend/constants_ibkr.py` → `IBKR_FORCE_ONE_SHARE` |
| Clamp | `backend/execution/qty_gate.py` → `apply_force_one_share` |
| Ingress call | `backend/execution/service.py` → first line of `execute()` |
| IBKR send check | `backend/execution/broker_send.py` → `live_cap_refusal` before `place_order` / `place_bracket_order` |
| Continuity | `.cursor/rules/execution-continuity.mdc` |
| Validation note | `docs/trading-execution-validation.md` |

## Disable (one line)

```python
IBKR_FORCE_ONE_SHARE = False
```

Or delete `cmd = apply_force_one_share(cmd)` in `service.py`.

## Agent rule

Do **not** "fix" Live fills that are always 1 share while the form shows a larger quantity until this gate is flipped off. Do not re-cap Paper or Sim without an operator decision.
