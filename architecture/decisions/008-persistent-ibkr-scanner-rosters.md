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

**Implementation status (2026-08-07):** Code paths for (1)–(5) are in-tree. Persistent manager is enabled and **authoritative** by default (`IBKR_SCANNER_PERSISTENT_ENABLED=true`, `IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=true`). Cutover was forced after production evidence that shadow+one-shot dual ownership left UI caches empty (empty-shadow quiet window forever; competing one-shot `TOP_PERC_*` timed out against the same clientId leases). Set `IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=false` only for deliberate rollback.

**Amendment (2026-08-24) -- names-first admission, Gappers is a projection:**

Decision 1's premarket set changes from *Gainers + Gappers* to **Gainers only**, and
roster admission is decoupled from quotes (implements ADR 010 decision 5):

- **A ranked IB name is a row.** `commit_table` writes the batch immediately with
  `price=None`; the L1 hot path fills price / `prev_close` / `change_pct`. Admission
  never awaits `snapshot_quotes`. Row order is IB's rank -- Nova does not re-sort a
  ranked scan. Rationale: the old gate coupled "does this stock exist on the desk" to a
  COLD `reqTickersAsync` bounded at 20s by the HTTP->IB hop, and on 2026-08-24 that
  starved the entire premarket while IB was pushing names normally.
- **Premarket Gappers is derived, not scanned.** `backend/ibkr/gapper_view.py` filters
  the live Gainers roster at `GAPPER_MIN_GAP_PCT`. `TOP_OPEN_PERC_GAIN` compares today's
  open to the prior close, which is undefined before 09:30 ET (IB replies with Warning
  165), so it gets no premarket lease. The projection still freezes at 09:30 and is
  immutable afterward, exactly as decision 2 requires.
- **One writer, enforced.** With `discovery=ibkr` the persistent lease is the only roster
  owner: `scanner_runners/discovery.py` and `scanner_runners/movers.py` return early and
  `adapters/ibkr_scanner.py` raises. Decision 6's shadow/rollback flag is superseded by
  ADR 010 decision 10 -- rollback is git revert, not a second writer.
- **Empty is not fresh.** A batch with no names must not `mark_live` or stamp
  `last_scan`. Integrity fails a Gainers table that never committed a roster while IBKR
  is connected inside its window, instead of passing it as "OK if another list is live."

**Amendment (2026-08-18):** HOD Momo does not call `reqHistoricalData`. Session high is tick-6 + observed prints, with an observed-warmup floor after 60s of watching (`open_alert_window=False`). Squeeze buffer is a local `bars_store.read` of already-stored 1Min bars; empty store means live-only. The 60/10min IB historical budget belongs to Trader chart panes (max 4 timeframes per symbol).

**Amendment (2026-08-25) -- always-live carve-out for a non-freezing table:** ADR 014
adds `TABLE_LARGE_CAP`, a swing-oriented table that is deliberately exempt from this
ADR's freeze-at-boundary contract (decision 2). It is added to an explicit `_ALWAYS_LIVE`
set in `scanner_session.py` rather than reusing the freeze-boundary machinery with
all-day bounds, and its lease carries per-table `marketCapAbove` / `aboveVolume` /
`stockTypeFilter` via a new `LeaseSpec`, extending decision 1's bare
`(scan_code)` model. See ADR 014 for the full decision, live-verified scan-code choice,
and rejected alternatives.

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
