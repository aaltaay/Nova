# 2026-08-17 -- Persist-audit remainder (journal, Activity, last-good, capture)

- **Status:** completed
- **Agents:** parent
- **Domain:** execution / journal / archive / settings (off-roadmap persist follow-up)
- **Related:** `CHANGELOG.md` §2026-08-17 -- Persist-audit remainder · `PROBLEM_LOG.md` §Last-good wipe on disconnect · §Epoch-0 L1 ticks · persist-audit plan 5a36654c

## Task

Close the remaining persist-audit gaps after ledger recording and the Orders (Today) overlay: real journal trades on flat, an Activity trail, last-good blotter on disconnect, and capture/durability (daily bars, epoch-0 L1, catalysts, SQLite backups, prefs export).

## Goal

Four independently shippable phases in one session: journal-on-flat, Activity API+UI, last-good disconnect, capture/backups/prefs. TWS fills stay blotter-only. `auto_live` stays NO-GO. No hosted database.

## Why it mattered

Reports only had mock trades. There was no ledger trail UI. A Gateway drop wiped Working Orders and Positions. `bars_1d` was empty, L1 wrote `1969-12-31`, catalysts died on restart, and there was no SQLite backup or prefs bundle.

## What we changed

- `journal/round_trip.py`: per-symbol net from ledger fills; `is_mock=0` on flat; unique `close_key`; boot `rebuild_from_ledger`.
- Live hook from `OrderWatch.note_filled` (skips `operation=="bracket"`; executor still owns those).
- `GET /api/ibkr/executions` + Trading **Activity** section (`frontend/src/activity/`).
- `IbkrAccountContext` / `useClosedOrders` keep last-good rows; Flatten/Cancel/Fill stay disabled via `error`.
- `rollup_daily` in archive maintenance; epoch-0 L1 reject + purge; `news-catalysts-{date}.json`; `backup_sqlite_once`; Settings prefs export/import (trader tabs excluded).

## How it works now

Nova-placed fills move a per-symbol cycle. When net qty hits 0, a real journal row is written. `close_key` is unique so boot rebuild and the executor cannot double-write. Benchmarks and `ib_recovered` never journal. Activity is a local-ledger read (works while IB is down). Disconnect freezes the last snapshot and closes spend actions. Daily bars come from 1m rollup. Missing exchange stamps no longer become unix 0. Catalysts and SQLite backups live under `.cache`. Prefs are an allowlisted localStorage JSON file.

## Why this approach

- Journal on Nova flat only, not TWS, because TWS fills have no ADR 007 command and would invent a book the operator did not place here.
- Skip live `notify_watch_filled` for brackets so the executor remains the single writer; incomplete bracket evidence is not replayed into `_open` (avoids a ghost short after restart).
- Reuse `error` for last-good so existing `disabled={Boolean(error)}` / hotkey gates work without touching every consumer.
- Do not add news helpers to `cache.py` (already near the line cap); persist lives in `news_catalyst_persist.py`.
- Rejected: hosted Postgres, journaling TWS, commission-net P/L this pass, and wiping the blotter on disconnect.

## Verification

- `py -3 -m pytest` persist-remainder set: 48 passed; journal/executor/compact: 29 passed.
- Vitest Phase 1-3: 34 passed; Phase 2-4 UI: 29 passed.
- `npm run build` exit 0 (`tsc -b && vite build`).
- Live `GET /api/ibkr/executions?limit=5` 200 with shaped rows; `/api/ibkr/status` `connected=true` paper ready. API already on `127.0.0.1:8000` (reload); Vite already on `localhost:5173`.

## Follow-ups

- IB `CommissionReport` / net P/L.
- Journaling TWS / `ib_recovered` fills (explicit product decision).
- Reports import UI.
- Do not reopen unless a Nova flat fails to appear in Reports, Activity 404s, or disconnect wipes the book again.

## Keywords

journal, close_key, round_trip, Activity, /api/ibkr/executions, last-good, stale, bars_1d, 1969-12-31, news-catalysts, backup_sqlite, prefsBundle
