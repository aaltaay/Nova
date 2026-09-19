# L2 Brain -- Sensor List v1

- **Date:** 2026-09-18
- **Status:** draft -- pending Ahmed review
- **Count:** **16 sensors**
- **Scope:** read-only sensors. No autonomous order placement.
- **Smoke test:** each sensor is an independent GET endpoint.
- **Thresholds:** unset until Ahmed sets them from live sessions.

This note is the v1 contract for L2 Brain inputs (16 sensors). It does not
implement the `/sensors/*` routes. Endpoints below are the intended
smoke-test surface.

## Contract

1. One GET per sensor. Call them independently. A down neighbor must not
   hide a healthy sensor.
2. Symbol sensors take `?symbol=`. Session phase is desk-wide (no symbol).
   Risk (14) is desk-wide `GET /sensors/risk` and may also take `?symbol=`
   when per-symbol state exists.
3. Responses are observations only. They never Place, cancel, flatten, or
   arm a bot.
4. Numeric trip/clear levels stay blank until Ahmed sets them from live
   sessions. Do not invent defaults.
5. Sensor 13 (news / catalyst) is **wired to the Advice feature**. Product
   name is **Advice** (Advise rail / Advice UI). Not Advisor. Not a stub.
   Not a separate news API. No new API keys.

Existing Advice feature docs: [advise-rail.md](advise-rail.md).

## Sensors

### 1. L2 book snapshot

Imbalance ratio, top 3-5 level depth each side, spread in ticks,
replenishment/cancellation rate, spoofing hints.

`GET /sensors/l2?symbol=`

### 2. Time & sales tape

Last ~20 prints, aggressor side, print-size clustering, inter-print timing.

`GET /sensors/tape?symbol=`

### 3. VWAP

Price vs VWAP, distance in ticks, 5/15-min slope.

`GET /sensors/vwap?symbol=`

### 4. MACD

Value, signal line, histogram.

`GET /sensors/macd?symbol=`

### 5. Relative volume

Current vs 20-day average at this time of day.

`GET /sensors/rvol?symbol=`

### 6. Cumulative day volume

Total today.

`GET /sensors/day-volume?symbol=`

### 7. Spread

Width in ticks, widening/narrowing over last minute.

`GET /sensors/spread?symbol=`

### 8. Session phase

pre-market / open auction / morning momentum / midday chop / power hour /
after-hours.

`GET /sensors/session-phase`

### 9. Order-flow events

Sweeps, iceberg hints, level replenishment after a hit.

`GET /sensors/flow?symbol=`

### 10. Time since last significant move

`GET /sensors/last-move?symbol=`

### 11. Symbol liquidity profile

ADV, typical spread, liquid-names allowlist flag.

`GET /sensors/liquidity?symbol=`

### 12. EMA context (9/20/200)

Warrior-style.

`GET /sensors/emas?symbol=`

### 13. News / catalyst feed

Headline text, source, timestamp, sentiment/relevance flag (bullish /
bearish / neutral) for the symbol.

`GET /sensors/news?symbol=`

**Source:** the existing **Advice feature** in this repo (Advise rail /
Advice UI -- TradingAgents-style feed). `GET /sensors/news?symbol=` reads
headline, source, timestamp, and sentiment flag from the Advice feature's
output. Do not add a Finnhub, RSS, or other news key for this sensor.

**Status:** **wired to Advice**. Not "wired to Advisor". Not a stub. Not a
separate news API.

Advice feature code today lives under `frontend/src/advise/` and
`backend/advise/` with book routes at `/api/advise`. The smoke-test
endpoint is still `GET /sensors/news`. The Advice feature already spends
OpenRouter (`OPENROUTER_API_KEY`) for a debate; sensor 13 reuses that
output. No new API keys.

### 14. Risk state

Daily loss limit remaining; whether daily loss limit is hit (boolean);
cooldown active after consecutive losses; current streak of losses/wins.

`GET /sensors/risk` (and/or `?symbol=` if per-symbol)

**Source:** existing risk / account state in this repo. Desk-wide daily
discipline lives in `backend/strategy/risk.py` (`RiskState`:
`daily_realized_pnl`, `RISK_DAILY_GOAL_DOLLARS`, `halted` / `can_trade`,
`consecutive_losses`, `consecutive_wins`) and Nova OS loss policy
(`backend/nova_os/gates.py`, `codes.py`). Adjacent account lock:
`BOT_HARD_BREAKER_USD` / `hard_lock_until_date` in `backend/bot/breakers.py`.
Do not add a second risk engine.

**Status:** **wired to existing sources**.

### 15. Halt / LULD status

Whether the symbol is currently halted or in LULD; time since halt began;
halt type.

`GET /sensors/halt?symbol=`

**Source:** existing market data / LULD feed. IBKR `ticker.halted` observe
in `backend/ibkr/halt_status.py` plus the LULD clock in
`backend/ibkr/halt_eta.py` (kinds LULD / NEWS / UNK). Nasdaq Trade Halt RSS
may overlay official start / resume; missing RSS never invents those times.
Do not request generic tick 49. Do not invent a countdown from a quiet tape.

**Status:** **wired to existing sources**.

### 16. Brain memory

The brain's own last N decisions (go/no-go, confidence, timestamp, outcome
if known) for this symbol, so it avoids flip-flopping every tick.

`GET /sensors/memory?symbol=`

**Write path:** the brain appends to a small local log (not IBKR, not the
Advice feature). The GET is the smoke-test read of that log. When the store
is added it needs an owner module, invalidation trigger, and
`schema_version` (`persisted-state.mdc`). Pytest must not write
`backend/.cache`.

**Source:** a small local log the brain writes to.

**Status:** **new (small local store)**.

## Non-goals

- No Place / cancel / flatten from a sensor.
- No `auto_live`.
- No threshold defaults before Ahmed's live-session pass.
- No second news vendor for sensor 13. The Advice feature is the owner.
- No second risk engine or halt feed for sensors 14-15.
- Sensor 16 is a new local decision log only -- not a news, risk, or IBKR sensor.
