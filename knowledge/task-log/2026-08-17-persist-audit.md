# 2026-08-17 -- Persistence audit (what the DBs keep)

- **Status:** completed
- **Agents:** parent
- **Domain:** execution / archive / scanner (continuity-only inventory)
- **Related:** `PROBLEM_LOG.md` §2026-08-17 -- Orders (Today) ignores execution ledger · ADR 007 · ADR 008 · Phase J Productization-Decision

## Task

List what Nova keeps in its databases and audit what the desk still loses or rereads from IB.

## Goal

One inventory of every durable store, live row counts, and a kept-vs-missing list -- without standing up Postgres or Supabase.

## Why it mattered

Orders (Today) showed IVF fills as Order ID 0 / qty 0. The operator asked whether a real database already exists and what is missing from it.

## What we changed

- Read-only audit of `backend/.cache` (five SQLite files + JSON + cold archive).
- Canvas: [persist-audit](C:/Users/aalta/.cursor/projects/c-Users-aalta-github-Nova/canvases/persist-audit.canvas.tsx)
- PROBLEM_LOG diagnosis for blotter vs ledger.

No product code change.

## How it works now

Nova already has local SQLite. There is no hosted order book.

| File | Role | Live (2026-08-17) |
|------|------|-------------------|
| `execution_ledger.db` | ADR 007 executions + fill evidence | 413 exec (32 manual), 21 evidence. IVF 19085/19112 filled with qty 1. |
| `journal.db` | Signals + Reports trades | 93 signals, 12 mock trades only |
| `archive.db` | 1m bars, IB tape, L1, enrichment | tape 1.68M, L1 1.80M, bars_1m 3045, bars_1d 0 |
| `l2.db` | Depth snapshots | 717k snapshots, tape_trades 0 |
| `nova_os_events.db` | Nova OS audit | 604 events |
| `hod-momo-*.json` | Alerts, highs, config, blocklist | Today 9305 alerts; config 13 strategies |
| `gappers/gainers/losers/AH-*.json` | Roster snapshots | Last write Aug 4/5; **today missing** |
| `.env` | Secrets + gateway mode | Settings POST |
| Browser storage | Hotkeys, layout, docks, trader tabs | This profile / window |

Orders (Today) still reads IB session trades, not the ledger. `permId` is nowhere. Scanner stream (ADR 008 authoritative) does not write dated roster JSON -- the old scan_loop writers no longer run. Journal import from Gateway is probe-only (wants a JSON list). Phase J stays local-first; optional R2 is backup, default off.

## Why this approach

**Required.** A hosted Postgres/Supabase blotter would not fix Order ID 0 -- the row is already local and unread. Hosting the live book fights Phase J (offline desk, secrets, IB Gateway on this machine). IB remains SoT for open orders and positions. The missing work is wiring and a few columns (`permId`, fill qty, roster JSON from the stream path), not a new database product.

Rejected: replace SQLite with Supabase; treat IB completed-orders as the only history; invent journal P/L from incomplete IB replay.

## Verification

```text
py -3 .tmp-persist-audit.py
py -3 .tmp-persist-audit2.py
```

Live counts above. IVF ledger rows confirmed. Temp scripts deleted after the pass.

## Follow-ups

1. Ledger-first Orders (Today) for Nova-placed rows; IB-recovered labeled; show permId or `--`. **Done** -- see `2026-08-17-closed-blotter-ledger.md`.
2. Persist permId + fill qty/avg on the ledger. **Done** -- see `2026-08-17-persist-recording.md`.
3. Write ADR 008 roster JSON from the persistent stream path. **Done** -- same entry.
4. On fill, insert a real journal trade. (still deferred -- a fill is not a closed round-trip)
5. Optional nightly SQLite copy / R2. Do not make a host the live SoT.

## Keywords

persistence, SQLite, execution_ledger, journal, archive, l2.db, Orders Today, permId, scanner JSON, Phase J
