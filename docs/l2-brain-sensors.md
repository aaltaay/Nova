# L2 Brain -- Sensor List v1

- **Date:** 2026-09-19
- **Status:** implemented -- 18 independent GET sensors + Sensor Board
- **Count:** **18 sensors**
- **Scope:** read-only sensors. No autonomous order placement.
- **Smoke test:** each sensor is an independent GET endpoint.
- **Thresholds:** unset until Ahmed sets them from live sessions.
- **UI:** Settings &gt; Sensors (Sensor Board). Default symbol is `SIM1` while
  Sim is on, otherwise `AAPL`.

This note is the v1 contract for L2 Brain inputs. Agents treat the GET
paths and `status` values as the stable interface. Fill later without
reshaping URLs or the envelope.

## Contract

1. One GET per sensor. Call them independently. A down neighbor must not
   hide a healthy sensor.
2. Symbol sensors take `?symbol=`. Session phase is desk-wide (no symbol).
   Risk (14) is desk-wide `GET /sensors/risk` and may also take `?symbol=`
   when per-symbol state exists. Macro (18) is desk-wide `GET /sensors/macro`
   with optional `?symbol=` for an earnings stub row.
3. Responses are observations only. They never Place, cancel, flatten, or
   arm a bot.
4. Numeric trip/clear levels stay blank until Ahmed sets them from live
   sessions. Do not invent defaults.
5. Sensor 13 (news / catalyst) is **wired to the Advice feature**. Product
   name is **Advice** (Advise rail / Advice UI). Not Advisor. Not a stub.
   Not a separate news API. No new API keys.
6. Common envelope:

```json
{
  "sensor": "l2",
  "symbol": "AAPL",
  "status": "live",
  "as_of": 1770000000.0,
  "data": {},
  "error": null
}
```

`status` is `live` | `stub` | `computed_stub`. `error` is omitted when the
read is healthy. Empty / missing feed is still HTTP 200 with a loud
`error` string -- fail loud, not a fake zero.

Catalog: `GET /sensors`. Board snapshot: `GET /sensors/snapshot?symbol=`.
Brain write: `POST /sensors/memory`.

Existing Advice feature docs: [advise-rail.md](advise-rail.md).
Sim practice: [sim-mode.md](sim-mode.md).

## Live vs stub

| # | Sensor | GET | Status now | Source |
|---|--------|-----|------------|--------|
| 1 | L2 book | `/sensors/l2?symbol=` | **live** | IBKR depth / Sim SIM1 book. Imbalance and spread from `l2.features`. |
| 2 | Tape | `/sensors/tape?symbol=` | **live** | Tape ring (`tape_stream._push_queue` + Sim prints). Last ~20 prints. |
| 3 | VWAP | `/sensors/vwap?symbol=` | **live** | 1Min typical-price VWAP from `bars_store` / Sim bars. Not `ticker.vwap`. |
| 4 | MACD | `/sensors/macd?symbol=` | **live** | 12/26/9 on 1Min closes. Standard periods, not trip levels. |
| 5 | RVOL | `/sensors/rvol?symbol=` | **live** | ADV pace (`large_cap_metrics.compute_rvol`) + Warrior 5-min when present. `tod_20d` is null -- that series is not stored. |
| 6 | Day volume | `/sensors/day-volume?symbol=` | **live** | Shared L1 `last_quotes` / Sim volume. |
| 7 | Spread | `/sensors/spread?symbol=` | **live** | Current book spread vs oldest snapshot in the minute. |
| 8 | Session phase | `/sensors/session-phase` | **live** | Clock buckets from existing session constants. |
| 9 | Order-flow | `/sensors/flow?symbol=` | **live** | Sweeps / replenish hints from tape + book rings. |
| 10 | Last significant move | `/sensors/last-move?symbol=` | **live** | Last 1Min bar whose range >= median of last 20. No trip dollars. |
| 11 | Liquidity | `/sensors/liquidity?symbol=` | **live** | Cache-only ADV, current spread, bot `symbol_allowlist`. |
| 12 | EMA 9/20/200 | `/sensors/emas?symbol=` | **live** | 1Min closes. EMA 200 stays `ready=false` until 200 bars exist. |
| 13 | News / catalyst | `/sensors/news?symbol=` | **live** (wired to Advice) | `advise.service.latest` only. Stance maps LONG/SHORT/HOLD to bullish/bearish/neutral. |
| 14 | Risk | `/sensors/risk` | **live** | `strategy.risk` + bot soft/hard breaker session. |
| 15 | Halt / LULD | `/sensors/halt?symbol=` | **live** | `ibkr.halt_status.snapshot`. |
| 16 | Brain memory | `/sensors/memory?symbol=` | **stub** | New local store `l2-brain-memory.json`. Write: `POST /sensors/memory`. |
| 17 | Regime | `/sensors/regime?symbol=` | **computed_stub** | trending / mean-reverting / chopping from 1Min closes. Unknown until enough bars. |
| 18 | Macro calendar | `/sensors/macro` | **stub** | Static FOMC/CPI/NFP placeholders. Not Advice. Not `GET /sensors/news`. |

## Sensors

### 1. L2 book snapshot -- live

Imbalance ratio, top 3-5 level depth each side, spread in ticks,
replenishment/cancellation rate, spoofing hints (size that appeared then
dropped to zero). Tick dollars = 0.01 for display only -- not a trip.

`GET /sensors/l2?symbol=`

### 2. Time & sales tape -- live

Last ~20 prints, aggressor side, print-size clustering, inter-print timing.

`GET /sensors/tape?symbol=`

### 3. VWAP -- live

Price vs VWAP, distance in ticks, 5/15-bar slope of running VWAP.

`GET /sensors/vwap?symbol=`

### 4. MACD -- live

Value, signal line, histogram.

`GET /sensors/macd?symbol=`

### 5. Relative volume -- live

Current vs ADV pace at this time of day. 20-day TOD series is **not**
invented (`tod_20d: null`).

`GET /sensors/rvol?symbol=`

### 6. Cumulative day volume -- live

Total today from the shared L1 / Sim quote.

`GET /sensors/day-volume?symbol=`

### 7. Spread -- live

Width in ticks, widening/narrowing over last minute (or oldest snapshot).

`GET /sensors/spread?symbol=`

### 8. Session phase -- live

pre-market / open auction / morning momentum / midday chop / power hour /
after-hours / closed.

Clock only. `midday chop` is a time-of-day label, not sensor 17.

`GET /sensors/session-phase`

### 9. Order-flow events -- live

Sweeps, iceberg hints, level replenishment after a hit. Same rings as 1-2.

`GET /sensors/flow?symbol=`

### 10. Time since last significant move -- live

`GET /sensors/last-move?symbol=`

### 11. Symbol liquidity profile -- live

ADV (fundamentals cache), current spread, bot allowlist flag.

`GET /sensors/liquidity?symbol=`

### 12. EMA context (9/20/200) -- live

Warrior-style periods on 1Min closes.

`GET /sensors/emas?symbol=`

### 13. News / catalyst feed -- live, wired to Advice

Headline text, source=`advice`, timestamp, sentiment/relevance flag
(bullish / bearish / neutral) from the Advice stance.

`GET /sensors/news?symbol=`

**Source:** the existing **Advice feature** (`/api/advise`, Advise rail /
Advice UI). Do not add a Finnhub, RSS, or other news key for this sensor.

**Status:** **wired to Advice**. Not "wired to Advisor". Not a stub.

### 14. Risk state -- live

Daily loss limit remaining; whether daily loss limit is hit; cooldown
after consecutive losses; current streak of losses/wins. Also echoes bot
soft breaker / hard lock date.

`GET /sensors/risk` (optional `?symbol=`)

**Source:** `backend/strategy/risk.py` + `backend/bot/breakers.py` session.
Do not add a second risk engine.

### 15. Halt / LULD status -- live

Whether the symbol is currently halted or in LULD; time since halt began;
halt type.

`GET /sensors/halt?symbol=`

**Source:** `backend/ibkr/halt_status.py` + LULD clock / Nasdaq RSS overlay.
Do not request generic tick 49. Do not invent a countdown from a quiet tape.

### 16. Brain memory -- stub (stable interface)

Last N decisions (go/no-go, confidence, timestamp, outcome if known).

`GET /sensors/memory?symbol=`

**Write path:** `POST /sensors/memory` with `{symbol, decision, confidence?, outcome?, note?}`.

Owner: `backend/sensors/memory_store.py`. Invalidation: unknown
`schema_version` refuses loud; missing version migrates to 1.
`schema_version`: 1. File: `l2-brain-memory.json` under `NOVA_CACHE_DIR`.

### 17. Regime detector -- computed_stub

trending / mean-reverting / chopping + confidence from existing 1Min
closes. `unknown` + low confidence until enough bars. No new feed.

`GET /sensors/regime?symbol=`

### 18. Macro event calendar -- stub

Upcoming scheduled catalysts (FOMC, CPI, NFP, optional symbol earnings
row) with timestamp and expected impact. Static placeholders are OK.

`GET /sensors/macro` (optional `?symbol=`)

**Source:** stub schedule in `constants_sensors.py`. Distinct from Advice
(sensor 13). Do not read Advice here. Do not add a news key.

## Architecture

- Registry + thin FastAPI router: `backend/sensors/registry.py`,
  `backend/sensors/routes.py`.
- Adapters read existing IBKR depth/tape, `bars_store`, Advice, risk, halt,
  and Sim (`SIM1`) pipes. No new IB subscriptions.
- Auth: GET sensors follow other read routes. `POST /sensors/memory` uses
  the same mutating API-key middleware as other writes.
- Sim: when Sim is on, SIM1 book/tape/volume/bars come from `backend/sim/`.

## Sensor Board

Settings overlay left rail **Sensors**. One tight row per sensor
(name / value / chip), scanner-table density. A row with `error` paints
an **error** chip -- not a green live chip. News value always includes
Advice provenance (`data.source`). Tape/flow do not invent `0 prints`.
Empty and load-fail states stay loud. Account settings points here. No
Place button.

## Non-goals

- No Place / cancel / flatten from a sensor.
- No `auto_live`.
- No threshold defaults before Ahmed's live-session pass.
- No second news vendor for sensor 13. The Advice feature is the owner.
- No second risk engine or halt feed for sensors 14-15.
- Sensor 16 is a new local decision log only.
- Sensor 17 must not open a new L1/L2/tape subscription.
- Sensor 18 is not the Advice feature and must not reuse `GET /sensors/news`.
