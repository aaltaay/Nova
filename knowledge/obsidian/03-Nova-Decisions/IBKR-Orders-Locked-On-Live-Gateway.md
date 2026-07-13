---
title: IBKR live Gateway with orders locked
date: 2026-07-13
status: active
---

# IBKR: live market data, orders locked by default

## Situation

User could not log into paper Gateway; connected **live** Gateway (funded ~$600) for market data / Level 2.

## Policy (single source of truth)

`backend/ibkr/safety.py` is the **only** gate for spends.

| Env | Purpose | Safe default |
|-----|---------|--------------|
| `IBKR_ENABLED` | Connect at all | false until opted in |
| `IBKR_GATEWAY_MODE` | `paper`→4002 / `live`→4001 | paper |
| `IBKR_ORDERS_ENABLED` | Master kill for BUY/SELL/brackets | **false** |
| `IBKR_LIVE_TRADING_CONFIRMED` | Second key if account is live | **false** |

Cancel remains allowed when connected (protective).

## Current user .env (2026-07-13)

```
IBKR_ENABLED=true
IBKR_GATEWAY_MODE=live
IBKR_ORDERS_ENABLED=false
IBKR_LIVE_TRADING_CONFIRMED=false
```

→ Live L1/L2 OK; **no Nova-originated spends**.

## Paper trading (when ready)

Client Portal → Settings → Account Configuration → **Paper Trading Account** → open / note paper username → Gateway login with **IB API** + **Paper Trading** + that paper user.
