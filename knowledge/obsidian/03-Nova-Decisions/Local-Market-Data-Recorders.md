# Local Market Data Recorders

> Decision note for efficient local L2 + time & sales recording.
> Status: ACCEPTED 2026-07-11
> Related: Phase F L2 package (`backend/l2/`), Automation-Strategy-Backbone §3

---

## Goal

Answer questions like: **“With ticker X open, what did Level 2 look like at second T? How was the tape?”** and keep a durable local archive for later relearning / backtesting — without building a replay UI yet.

---

## Storage choice: SQLite (WAL) + batched inserts

**Chosen:** extend the existing `l2.db` SQLite file under `paths.cache_dir()`.

| Option | Verdict |
|--------|---------|
| **SQLite + WAL + `executemany` batches** | **Ship this.** Already in repo (`journal/`, Phase F `l2/`). Fine for millions of rows with `(symbol, ts)` indexes. Zero new deps. |
| Parquet / pyarrow cold archive | **Deferred.** Add only if retention volume or analytics scans prove SQLite is the bottleneck. Hybrid (hot SQLite window → cold Parquet) is the migration path, not the v1 design. |
| Separate `backend/recorders/` package | **Rejected for now.** Extending `backend/l2/` avoids a competing parallel system. |

**Why this is fast enough locally**

- IBKR depth is capped (~3 symbols). Continuous snapshots at ~1 Hz → low write rate for books.
- Tape (Alpaca WS prints) is higher volume but only recorded for **watched** symbols (open depth session or active signal window), not the entire scanner universe.
- Writers enqueue in memory and flush on batch size **or** ~250 ms (`L2_BATCH_*` / `TAPE_BATCH_*` in `constants.py`).
- `PRAGMA journal_mode=WAL` + `synchronous=NORMAL` on every connection.

---

## What gets recorded

| Stream | Source | When | Table |
|--------|--------|------|-------|
| L2 book snapshots | `ibkr/depth.current_book()` | Signal window (`recorder.py`) **and** while DepthLadder / depth WS is open (`continuous.py`) | `l2_snapshots` |
| Time & sales | Alpaca WS trade msgs (`T=t`) | Symbol is watched (session open) | `tape_trades` |
| Session metadata | wall clock + reason | `signal` or `depth` start/stop | `record_sessions` |

**Schema (conceptual)**

- `l2_snapshots(recording_id, symbol, setup, signal_ts, ts, bids_json, asks_json, l1_fallback, session_id)`
- `tape_trades(symbol, ts, price, size, exchange, source, session_id)`
- `record_sessions(session_id, symbol, reason, setup, signal_ts, started_ts, ended_ts)`

**Retention:** `L2_RETENTION_DAYS` (default 14). Background sweep deletes old snapshots/tape/ended sessions.

**Not recorded (yet):** full-universe Alpaca tape, IBKR tick-by-tick, quotes/bars (already elsewhere), playback UI state.

---

## How to recall “L2 at second T”

```http
GET /api/l2/at?symbol=AAPL&ts=1710000000.0&window_sec=2
```

Returns nearest L2 snapshot within ±window, tape prints in that window, and any covering `record_sessions` row.

Range dump for backtests:

```http
GET /api/l2/range?symbol=AAPL&start_ts=...&end_ts=...
```

Python (same path future backtester should use):

```python
from l2.recall import recall_at, recall_range
recall_at("AAPL", ts, window_sec=2.0)
```

Status / list (no fancy UI): `GET /api/l2/status`, `GET /api/l2/sessions`.

---

## Future backtest / relearn read path

1. Select trades or signals of interest (journal + setups).
2. For each `(symbol, opened_ts)`, call `recall_at` / `recall_range` (or SQL on `l2.db`).
3. Feed `features.compute_feature_series` + tape prints into labeling / model training.
4. If archives grow past comfortable SQLite scan sizes, export ended days to Parquet and point the same recall helpers at a dual backend — **without** changing the API shape.

---

## Deferred

- Replay / scrubber UI
- Full backtester harness
- Parquet cold tier
- Recording all scanner symbols’ tape by default
- IBKR `reqTickByTickData` as a second tape source

> **Nova OS relation:** hot SQLite recorders (this note) remain the live facade. Permanent archive / Parquet / R2 / day-rewind are Nova OS phases P6–P9 — see [[Nova-OS-Status]]. Do not treat timer-only 14-day purge as “forever” until those phases land.