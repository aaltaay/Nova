# 2026-08-17 -- Close persist recording holes

- **Status:** completed
- **Agents:** parent
- **Domain:** execution / scanner (continuity-only; no specialist hop)
- **Related:** `CHANGELOG.md` §2026-08-17 -- Record permId, qty intent, cancel symbol, and scanner rosters · `PROBLEM_LOG.md` §2026-08-17 -- Ledger omitted permId and roster JSON · persist-audit canvas · ADR 007 · ADR 008

## Task

Close the recording holes from the persist audit: write the data Nova already has onto local SQLite / dated JSON. Leave the trail / Order ID 0 display work for later.

## Goal

New and existing `execution_ledger.db` rows keep requested vs sent qty, spend/short gates, `short_entry`, IB `permId`, fill qty / avg, and a symbol on cancels. Authoritative scanner commits write today's dated roster JSON. Orders (Today) still reads IB -- that is out of scope.

## Why it mattered

IVF fills were already in the ledger as client order ids 19085 / 19112, but without `permId` or fill size those rows cannot survive a Gateway reconnect as a forensic record. Cancel rows without a symbol are useless in a later trail. Today's Gappers/Gainers files were missing because ADR 008 lives in RAM. The operator asked to close recording first, then continue the trail audit.

## What we changed

- `execution/record_payload.py` -- reserve payload snapshots `requested_qty`, `sent_qty`, `forced_one_share`, `short_entry`, `orders_enabled`, `live_trading_confirmed`, `short_enabled`, `gateway_mode`.
- `execution/store_schema.py` + `store.py` -- ALTER `perm_id`, `filled_qty`, `avg_fill_price` on existing DBs; create those indexes only after the columns exist.
- `execution/store_facts.py` -- `record_broker_facts` and `lookup_symbol_for_order_id`.
- `execution/service.py` -- capture requested qty before `apply_force_one_share`; cancel symbol from ledger, then open orders only if IB is connected.
- `execution/telemetry.py` + `telemetry_handlers.py` -- remember and persist `permId` / fill qty / avg from orderStatus and execDetails.
- `routes/trading_execution.py` -- cancel-all passes the open-order symbol.
- `ibkr/scanner_persist.py` + `scanner_hydrate.commit_table` -- write dated gappers/gainers/losers/afterhours JSON on authoritative commit.

## How it works now

The ledger is still the local ADR 007 SoT. A place row now answers "what did the operator ask for, what did we send, which gates were on, and what IB `permId` / fill came back." A cancel row gets a symbol even when the hotkey only sent an order id. Scanner restart restore can read this session's roster files again. The blotter still polls `/api/ibkr/orders/closed` and can still show Order ID 0 -- that is display, not recording.

## Why this approach

- **Record on the existing ledger, do not add a sixth DB or Supabase.** Phase J is local-first. A hosted book is the wrong SoT and goes dark with the house net.
- **Keep `IBKR_FORCE_ONE_SHARE`.** Snapshot both qtys instead of removing the test gate.
- **Do not invent journal P/L from a single fill.** A fill is not a closed round-trip. Reports stay mock until a later, honest close.
- **Indexes after ALTER.** `CREATE TABLE IF NOT EXISTS` is a no-op on the live file; creating `idx_exec_perm_id` in the same script crashed existing ledgers.
- **Open-order symbol lookup is gated on `get_ib()`.** Cancel must not call `open_orders()` when disconnected -- that path errors and the verify poll held the 50ms urgent-cancel test in a thread.
- **Rejected:** blotter-reads-ledger in this pass (user deferred). Nightly R2 copy. Writing `bars_1d` or news catalysts.

## Verification

```text
py -3 -m pytest backend/tests/test_execution_record_payload.py backend/tests/test_execution_store_facts.py backend/tests/test_scanner_roster_persist.py backend/tests/test_execution_qty_gate.py backend/tests/test_execution_service.py backend/tests/test_execution_latency_regressions.py backend/tests/test_scanner_hydrate_hod_roster.py backend/tests/test_trading_cancel_all.py backend/tests/test_short_entry_e2e_gate.py -q --tb=short
```

47 passed.

## Follow-ups

- Orders (Today) union of ledger + IB recovered (Order ID 0 / qty 0).
- Trail / Activity UI: show `permId` or `--`, requested vs sent, gates.
- Journal-on-close (not on a single fill).
- Optional nightly copy of the five SQLite files.

## Keywords

permId, requested_qty, sent_qty, cancel symbol, persist_roster, execution_ledger, ADR 007, ADR 008
