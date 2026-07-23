# ADR 008 — Session-owned persistent IBKR scanner rosters

**Status:** Accepted · **Date:** 2026-07-23

## Context

`backend/ibkr/discovery.py` polls IBKR's market scanner with `reqScannerSubscription` → wait → `cancelScannerSubscription`, repeated on fixed 20s/30s/120s cadences from `constants_scanner.py`. Those constants were inherited from Nova's original Alpaca REST integration (which has no push scanner API) — IBKR's own scanner API supports a **persistent** subscription that pushes `updateEvent` batches for as long as it stays open, so the polling cadence was never an IBKR requirement. It exists only because Nova's discovery loop was written as request/response.

The one-shot design is also unable to express Nova's real product contract: Gappers must stop updating at 09:30 ET and hold their exact premarket snapshot for the day, Gainers run continuously 04:00–16:00 then hold their close-of-day snapshot, and Afterhours runs 16:00–20:00 then holds. A polling loop with `if not cache or age > INTERVAL: rescan` cannot express "freeze until tomorrow" — it can only express "rescan slower."

HOD Momo eligibility was also entangled with discovery: `hod_momo_seed.py` ran a second uncapped `TOP_PERC_GAIN` scan plus `HOT_BY_VOLUME` / `TOP_VOLUME_RATE` / `MOST_ACTIVE`, and a third `belowPrice=20` `TOP_PERC_GAIN` pass, purely to backfill HOD's active set with names outside the displayed tables. This tripled scanner-slot usage and gave sub-$20 stocks a special, undocumented seed path.

## Decision

1. **Persistent scanner subscriptions, not polling.** `backend/ibkr/scanner_stream.py` owns every `ScanDataList` handle for the life of the process. `reqScannerSubscription` is called once per desired `(scan_code, filters)` lease; IB pushes `updateEvent` batches as the ranked list changes. Desired subscriptions by session period: Premarket = Gainers + Gappers; RTH = Gainers + Losers (UI-only); Afterhours = AH Gainers; Closed = none. At most two persistent slots at any time, far under IBKR's hard limit of ten (`IBKR_ERROR_SCANNER_SLOT_EXHAUSTED` / Error 322).
2. **Session-owned table state, not a single mutable cache.** Each table (Gappers, Gainers, Losers, Afterhours) carries `session_key` (04:00 ET-anchored), `state` (`live` | `frozen` | `unavailable`), `source`, monotonic `revision`, `roster_ts`, `quote_ts`, and `frozen_at` (`backend/runtime_state/state.py`). A table transitions `live → frozen` exactly once per session, at its documented boundary (09:30 / 16:00 / 20:00), and never mutates again until the next session's rollover.
3. **04:00 ET session key.** `session_key = (now_et - 4h).date()`. Midnight–03:59 belongs to the prior completed session so a restart in that window does not fabricate a new morning scan. On restart, only a snapshot matching the current session key is restored; a stale prior-session snapshot is archived, not resurrected as live.
4. **Fencing, not broad cleanup.** Every scanner/hydration callback is checked against IB READY generation (`ibkr.client.current_generation()`), a local subscription epoch (bumped on reconnect or desired-set change), the target table, and the session key before it is allowed to mutate state. Late results from a superseded generation/epoch/session are discarded, never applied. Error-322 recovery (`recover_scanner_slots`) still cancels only stale one-shot/orphan reqIds — it must never cancel a currently-desired persistent lease.
5. **HOD eligibility narrows to session data actually shown.** HOD Momo's active set is the union of the current-session Gappers, Gainers, Afterhours, and manually curated Former Momo — nothing else. Volume seeds (`hod_momo_seed.py`), the `belowPrice=20` pass, open-ticker priority, Losers, and rotating discovery "explore" are removed from the active-set builder. Sub-$20 stocks are ordinary Gainers rows; they receive no separate scan or reserved slot.
6. **Migration safety gate.** The persistent manager runs in shadow mode first — it builds its own rosters but a feature flag keeps the existing one-shot `scan_loop` path authoritative for HOD/UI. Only after shadow evidence (batch cadence, membership parity, slot occupancy, reconnect/cancellation behavior) is recorded does promotion flip the flag. This preserves a working system for the entirety of the rollout instead of a single all-or-nothing cutover of a live trading data feed.

**Implementation status (2026-07-23):** Code paths for (1)–(5) are in-tree. Shadow manager is enabled by default (`IBKR_SCANNER_PERSISTENT_ENABLED=true`); **authoritative cutover remains off** (`IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=false`). Flip the env flag only after live Gateway shadow-parity logs look clean.

## Consequences

- Gappers/Gainers/Afterhours become genuinely frozen artifacts after their window — the frontend can trust "Frozen at 09:30 ET" instead of re-deriving staleness from a poll timestamp.
- IBKR scanner slot usage drops from up to 3 simultaneous codes (movers + seed + sub-$20) to at most 2, with headroom for the historical/chart/detail slots that share the same 10-slot ceiling.
- `DISCOVERY_INTERVAL_SEC`, `FOCUS_INTERVAL_SEC`, `GAINERS_INTERVAL_SEC`, `AFTERHOURS_DISCOVERY_INTERVAL_SEC`, `AFTERHOURS_FOCUS_INTERVAL_SEC` stop governing IBKR scanner cadence; `scan_loop.py` keeps only session reconciliation (freeze/rollover) plus the independent news-catalyst schedule, which has no IBKR analog.
- HOD Momo loses the volume-seed / sub-$20 augmentation that used to surface mid-day runners absent from the top-% tables. This is an intentional narrowing — Warrior parity work on catching those runners becomes a `hod-momo` specialist follow-up (widening the *documented* Gainers/Gappers/AH union, e.g. via additional scan codes visible in the UI, not a hidden side-channel).
- Losers keeps its own persistent RTH-only subscription and its own snapshot/revision — a Gainers freeze or reprice must not touch Losers' revision, and vice versa.

## Rejected alternatives

- **Keep one-shot polling, just tune the intervals.** Does not solve the freeze-at-boundary requirement (a poll can only get slower, not "stop and hold"); still burns a scanner slot per poll even when nothing changed.
- **Single mutable "movers" cache with a `frozen: bool` flag.** Cannot express independent Gainers-vs-Losers freeze timing (Losers is RTH-only) or per-table revision/session bookkeeping without becoming an ad hoc nested dict; a typed per-table state model in `runtime_state` is clearer and testable.
- **Immediate hard cutover to persistent subscriptions.** Rejected — a live trading data feed regression (stuck/duplicated scanner rows, a leaked slot, a frozen table that silently never freezes) would be discovered by the user mid-session instead of caught in shadow evidence first.
- **Keep HOD volume seeds / sub-$20 pass "for now."** Rejected per explicit product decision: sub-$20 is not a special category, and HOD eligibility must equal what a user can see in a scanner tab plus their own curated Former Momo list — not an invisible side-channel scan.
