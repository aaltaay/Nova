# 2026-07-23 — ADR 008 persistent scanner stream (shadow) + freeze + table-scoped WS

- **Status:** completed (shadow mode; authoritative cutover deferred)
- **Agents:** parent (Auto)
- **Domain:** market-feed / hod-momo adjacency (scanner ownership)
- **Related:** `CHANGELOG.md` §2026-07-23 ADR 008 persistent scanner stream · `PROBLEM_LOG.md` §2026-07-23 Error-322 recovery would cancel desired persistent scanner leases · ADR 008

## Task

Continue the Session-Owned Scanner Rosters plan after the HOD-narrowing checkpoint: build the persistent scanner manager, enforce freeze/rollover, push table-scoped WebSocket events, and prepare (but not blindly flip) cutover.

## Goal

One-shot poll path remains authoritative for UI/HOD while a parallel persistent subscription manager runs in shadow, freezes tables at 09:30/16:00/20:00, and exposes typed WS events so cutover is a flag flip after live evidence.

## Why it mattered

IBKR already pushes scanner updates; Nova was inventing 20/30/120s poll cadences and could not express “freeze Gappers at 09:30 and never mutate again.” Without an ownership-aware lease registry, Error-322 recovery would also cancel the new persistent handles.

## What we changed

- Added `ibkr/scanner_session.py` (period → desired leases, freeze/rollover, commit fencing).
- Added `ibkr/scanner_stream.py` + `scanner_hydrate.py` (persistent leases, hydrate, watchdog, shadow parity logs).
- Taught `recover_scanner_slots` to skip `persistent_reqids()`.
- `scan_loop` + discovery/movers/AH runners refuse frozen-table writes; lifespan starts the manager when enabled.
- `/ws/scanner`: bootstrap tables meta, `roster_replace`, `table_state`, table-scoped `price_patch`.
- Frontend: consume those events; drop IBKR membership REST poll when `scanner_persistent_authoritative` is true.
- Tests: `test_scanner_session_adr008.py`.

## How it works now

Desired leases: Premarket = Gainers+Gappers; RTH = Gainers+Losers; AH = AH Gainers; Closed = none (≤2 slots). Callbacks fence on IB READY generation + local epoch + session key + live window. Empty `TOP_OPEN_PERC_GAIN` derives gappers from the live Gainers symbol list without a second Gainers handle. Shadow mode writes only `_shadow` and logs parity vs caches every 60s. Authoritative mode (env `IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=true`) commits to runtime caches and broadcasts `roster_replace`. Frozen tabs return `[]` from `symbols_for_tab` so they burn no scanner-owner L1; HOD L1 stays independent.

## Why this approach

- **Shadow before cutover** — rejected hard cutover of a live trading feed; one-shot remains truth until Gateway evidence is logged.
- **Separate session/hydrate modules** — keep `scanner_stream.py` under the 400-line limit without spreading the lease invariant across discovery.py.
- **Freeze in scan_loop even before cutover** — product contract (immutable post-boundary tables) does not need to wait for push subscriptions.
- **Table on price_patch** — same symbol can sit on Gainers (live) and Gappers (frozen); unscoped patches would corrupt the frozen row.

## Verification

- `py -3 -m pytest` → 916 passed
- `npx vitest run` → 435 passed
- `npm run build` → green
- Focused: `tests/test_scanner_session_adr008.py` (session key, leases, freeze fence, recover skip)

## Follow-ups

1. Run a live Gateway session; collect `scanner_stream shadow parity` log lines (membership delta, slot count, reconnect).
2. Flip `IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=true` only after that evidence.
3. Do **not** reopen volume seeds / belowPrice=20 HOD paths.

## Follow-up pass (same day) — self-review found 4 real gaps, all fixed

A detailed review against the plan text (not just the todo checkmarks) found:

1. **Frozen-table mutation leak (real correctness bug).** `ibkr_bridge.apply_l1_quote`/`apply_table_quotes` unconditionally repriced scanner caches from every L1 tick, including HOD-reserved-pool ticks for symbols retained from an already-frozen table. Fixed by gating every reprice branch on the new `ibkr.scanner_session.is_table_frozen(state, table)`.
2. **WS relay could leak the same tick into the wrong (frozen) table.** `scanner_l1.flush_loop` tagged the whole batch by `get_dominant_tab()` (whichever tab a client was viewing), not by which owner (scanner-tab vs HOD-only) the tick actually belonged to. Fixed by tracking `_active_tab_symbols` and dropping any pending tick not in that set.
3. **Hydration re-quoted the full roster every batch.** Plan said "cold reqTickersAsync only for newly admitted symbols; preserve rows for unchanged symbols." Fixed with a per-table/session known-rows cache in `scanner_hydrate.py`.
4. **Integrity was never made session-aware.** Only a pre-existing Gappers-only mode bypass existed; Gainers/Losers had no freeze-aware pass, so a frozen table's growing cache age could eventually fail Integrity. Fixed by adding `*_frozen` flags to the scanner snapshot and a frozen bypass in `evaluate_scanner_integrity`.

Also wired the previously-dead `frozenTableLabel()` into a visible "Frozen at HH:MM ET" badge (item 3's UI counterpart was plumbed to the hook in the first pass but never rendered).

Re-verified: 924 backend pytest (8 new), 435 Vitest, build green.

## Keywords

ADR 008, scanner_stream, persistent subscription, shadow mode, freeze 09:30, session_key_et, roster_replace, recover_scanner_slots, persistent_reqids
