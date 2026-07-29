# HOD Scanner Capture Audit -- 2026-07-28

- **Status:** completed (audit + harness; no product-code fixes in this pass)
- **Scope:** HOD Momo scanner pipeline, IBKR market-data layer, capture verification
- **Question:** "If something happens in the market, are we able to capture it?"
- **Evidence:** code review + deterministic replay of real archived tape (2026-07-17, 89,084 prints) through the production engine + fake-feed integration tests through the real L1 path

## Verdict (short)

Nova's HOD capture pipeline is **architecturally ahead of most open-source IBKR
scanners** (persistent rosters, generation fencing, freeze semantics, capacity
budgeting, fail-loud staleness). It will capture a real momentum move **when the
symbol is inside the ADR 008 admission set, the L1 stream is alive, and the data
is real-time**. The audit confirmed the user's worry is justified: the weakest
layer is exactly the Interactive Brokers API boundary -- not because the design
is wrong, but because several failure modes are **silent**: zombie subscriptions
after reconnect, delayed data that is indistinguishable from real-time, and an
archive that does not record the tick stream the engine actually consumes.

## 1. Requirements review (five capture dimensions)

### Coverage -- what can fire at all

- Admission set (ADR 008): current-session Gappers ∪ Gainers ∪ Afterhours ∪
  curated Former Momo, capacity 40 (`HOD_MOMO_ACTIVE_SET_CAPACITY`,
  `backend/constants_hod_momo.py:85`). Admission: Former Momo first
  (guaranteed), then round-robin across ranked tables
  (`backend/hod_momo_active.py:174-263`).
- Only admitted symbols get L1 streams and `on_trade_update` evaluation;
  everything else is `uncovered` and can never fire
  (`backend/ibkr_bridge.py:291-309`).
- Discovery bottleneck: IB scanner rosters, 50 rows per scan code, max 10
  concurrent API scanners (IB limit); Nova holds at most 2 persistent slots
  (`backend/ibkr/scanner_stream.py`).
- Losers, open ticker, volume seeds, and explore tails are deliberately NOT
  HOD-eligible (ADR 008).

### Capacity -- how much of the market we can watch

- L1 budget: 100 reqMktData lines, 5 reserved, 50 active tab, <=45 HOD pool
  (`backend/constants_ibkr.py`; `backend/ibkr/scanner_l1.py:106-155`).
- Overflow is rejected by the planner and surfaced via
  `price_patch.subscription` -- loud when patches flow.

### Timeliness -- how fast a new mover becomes evaluable

- Streaming L1 + 0.35s batch flush for tables; HOD evaluates synchronously per
  tick (no coalescing loss -- proven by
  `tests/test_hod_pipeline_fake_feed.py::test_coalescing_drops_display_prints_but_not_hod_evaluations`).
- Alert consolidation: 10s window, one primary per strategy_id
  (`backend/hod_momo_alerts.py:18-69`) -- matches Warrior "(N in Xs)" bursts.
- Gap: active-set membership rebuilds primarily on the L1 reconcile tick, so a
  brand-new roster admit can wait ~1s+ before evaluation (finding G8).

### Accuracy -- is the data what we think it is

Findings G1-G4 below. This is the layer the user flagged, and the audit
confirms it is the weakest link.

### Durability -- does capture survive restarts and session boundaries

- Alerts/highs persist to dated JSON with throttled force-flush
  (`backend/hod_momo_persist.py`); session rollover archives then clears
  (`backend/hod_momo_session.py:79-133`).
- Gap: `session_high_raised_ts` is NOT persisted -- after a restart the
  "new HOD" grace clock is lost, so alerts can be suppressed as `hod:not_new`
  until the high rises again (finding G9).

## 2. Empirical capture parity (Tier 1 replay)

Method: `tools/export_hod_replay_fixture.py` exported the real 2026-07-17
session (tape + 1m bars + production alert log) into committed fixtures;
`backend/hod_momo_replay.py` replayed all 89,084 prints through the REAL
engine with an injected clock (time.time + ET session clocks pinned to replay
time). Comparison target: the 794 alerts production actually persisted that
day.

| Symbol | Tape prints | Production strategies | Replay strategies | Missing |
|--------|------------:|-----------------------|-------------------|---------|
| SDOT   | 46,113 | 1, 4, 5, 7, 10, 11, 12 | **11, 12** | 1, 4, 5, 7, 10 |
| BIYA   | 14,365 | 1, 5, 7, 10, 11, 12 | **11, 12** | 1, 5, 7, 10 |
| CJMB   | 12,373 | 1, 5, 7, 11, 12 | **11, 12** | 1, 5, 7 |
| VEEE   | 12,658 | 3, 5 | -- | 3, 5 |
| SLND   | 2,728 | 1, 6, 10, 11, 12 | -- | all (tape gap) |
| KLRS   | 833 | 1, 5, 7, 10, 11, 12 | -- | all (tape gap) |
| CNF    | 4 | 5, 7, 10, 11, 12 | -- | all (tape gap) |
| WZRD   | 1 | 11 | -- | 11 (tape gap) |
| MVO / CNEY / NFXS | 4 / 4 / 1 | -- | -- | true negatives |

Reading the matrix:

- **The momentum core reproduces.** Dense-tape movers fire Squeeze 5%/5m (11)
  and Running Up (12) under replay; quiet symbols stay silent in both worlds;
  replay never fires a strategy production did not fire (no phantoms --
  enforced by `test_full_day_no_phantom_strategies`).
- **Missing strategies 1/4/5/7/10 on dense movers are fidelity gaps, not
  capture gaps:** strategy 1 (Former Momo) depends on that day's manual list
  (config drift); RVOL-gated strategies need `avg_volume`, which was never
  archived (finding G6); strategy 10 needs a 10%/10m surge reconstruction.
- **"Tape gap" rows are the audit's most important product finding:** CNF,
  WZRD, SLND, KLRS fired in production on **L1 ticks that were never
  archived** -- `tape_ibkr` only records symbols with an active tape
  subscription (open ticker). The L1 stream that actually drives HOD
  evaluation is not recorded anywhere (finding G5). Without fixing that, no
  replay harness can ever fully answer "did we capture it" for the whole
  active set.
- Consolidation works: 84 of 88 emitted alerts are consolidated primaries;
  0 alerts left unflushed at end of day.

## 3. Findings (ranked: severity x silence)

| ID | Finding | Evidence | Why it matters |
|----|---------|----------|----------------|
| G1 | **Zombie L1 subscriptions after reconnect.** `ticks.py` `_subs` is never cleared on disconnect/generation bump; `subscribe()` short-circuits when the symbol is present, so after a Gateway reconnect reconcile treats dead streams as live. HOD silently stops evaluating while looking subscribed. | `backend/ibkr/ticks.py:152-213`; proven by xfail `test_reconnect_recreates_streams_on_new_connection` | Silent capture death until process restart. Highest-severity finding. |
| G2 | **Delayed data is indistinguishable from real-time.** No `reqMarketDataType` anywhere; Error 10167 (delayed notice) unhandled; no UI label for data type 1/3/4. Paper logins are often delayed. | repo-wide grep; `backend/ibkr/ticks.py:192` | HOD alerts on 15-min-old prices look identical to live ones. |
| G3 | **`last or close` fallback + receive-clock timestamps.** A missing last prints the prior close as the current price with a fresh `quote_ts = time.time()` (receive time, not exchange time), masking farm lag. | `backend/ibkr/ticks.py:110,126` | Engine can evaluate yesterday's close as "now"; staleness badges stay green. |
| G4 | **Unhandled IB error codes on the L1 path.** 1100/1101/1102 (connectivity), 2104/2106/2108 (data farms), 101 (max tickers exceeded) have no handlers; L1 relies on a 5s `isConnected()` poll. | `backend/ibkr/client.py:316-434`; `backend/ibkr/ticks.py` | Farm breaks and line-cap rejections are invisible at the moment they happen. |
| G5 | **Archive does not record the L1 tick stream.** Only tape subscriptions (open ticker) are archived; the ticks that actually drive HOD are lost. | parity matrix "tape gap" rows; `backend/ibkr/tape_stream.py` | Capture can never be fully verified post-hoc; replay fidelity ceiling. |
| G6 | **Enrichment inputs not archived.** `avg_volume`, live RVOL, 52-week high are computed live and discarded; replay must prime stand-ins from production alerts. | fixture meta notes; `backend/hod_momo_enrichment.py` | Limits replay parity for RVOL/float-gated strategies. |
| G7 | **Former Momo crowd-out.** Priority admits fill the 40-slot pool first; a bloated list (433 symbols on 2026-07-23) can starve live Gappers/Gainers to 0-1 slots. | PROBLEM_LOG 2026-07-23; `backend/hod_momo_active.py:184-211` | Real movers never enter evaluation on the busiest days. |
| G8 | **Active-set refresh lags the reconcile loop.** `apply_l1_quote` only rebuilds when the set is empty; new roster admits wait for the next L1 reconcile before evaluation. | `backend/ibkr_bridge.py:291-295`; `backend/ibkr/scanner_l1.py:158-265` | First leg of a fresh mover can be missed (~1s+). |
| G9 | **`session_high_raised_ts` not persisted.** Restart loses the new-HOD grace clock; alerts suppress as `hod:not_new` until the next raise. | `backend/hod_momo_persist.py:209-231` (highs payload lacks it) | Post-restart alert drought for already-elevated symbols. |

Strengths verified (keep): READY generation + subscription-epoch fencing;
frozen-table immutability with HOD L1 continuing for retained symbols; L1
capacity budgeting with loud rejection; Error 322 scanner-slot recovery;
gateway port self-heal; fail-loud disconnect + L1-age staleness badges;
no Alpaca fallback under discovery=ibkr.

## 4. External comparison

- **IB TWS API docs (interactivebrokers.github.io/tws-api):** scanners return
  contracts only (no prices), 50 rows per scan code, 10 concurrent API scans;
  prices require separate `reqMktData`. Nova's roster + L1 split matches IB's
  intended architecture exactly.
- **ib_insync / ib_async community recipes:** most projects poll one-shot
  `reqScannerData` on a timer, with no reconnect fencing, no freeze semantics,
  and no capacity budgeting. Nova is structurally ahead of this baseline
  (persistent `reqScannerSubscription` + epoch fencing + shadow parity
  logging).
- **Community gotchas Nova already handles:** scanner-slot leaks (Error 322
  detection + recovery), `tickSnapshotEnd` ~11s making 1Hz snapshots infeasible
  (Nova streams L1 instead), event-loop blocking (fully async), duplicate
  clientId (documented, though Error 326 is not heal-eligible).
- **Where peer practice is ahead of Nova:** ib_async's docs and most production
  TWS integrations treat `reqMarketDataType` + error-event-driven reconnect
  (1100/1101/1102, 2104/2106/2108) as table stakes -- Nova has neither
  (G2/G4). Deterministic trading systems (QuantConnect Lean, Nautilus Trader)
  record the exact tick stream decisions consume so backtest/replay parity is
  provable -- Nova archives tape but not the L1 decision stream (G5).

## 5. Recommended fixes (not implemented in this pass)

| Pri | Fix | Addresses |
|-----|-----|-----------|
| P0 | Archive L1 ticks (or >=1/min L1 snapshots) for every active-set symbol into `archive.db` | G5 -- makes capture provable for the whole pool |
| P0 | Clear/re-establish `ticks._subs` on READY generation bump; add error-event handling for 1100/1101/1102 + 2104/2106/2108 | G1, G4 -- zombie streams, silent farm breaks |
| P1 | Call `reqMarketDataType`, handle Error 10167, label delayed vs real-time in `/api/ibkr/status` + UI badge | G2, G3 (partially) |
| P1 | Persist `session_high_raised_ts` in the highs payload | G9 |
| P2 | Rebuild the HOD active set on roster commit (not only on L1 reconcile); show `uncovered` symbols in the UI | G7, G8 |
| P2 | Archive per-session enrichment snapshots (avg_volume, float, 52wk high) for replay parity | G6 |
| P3 | Handle Error 101 (max tickers) on the L1 error path; add quote-quality flag when serving `close` as price | G3, G4 |
| P3 | Extract the consolidation-flush grouping into a pure function shared by `hod_momo_alerts` and the replay mirror (currently mirrored) | harness drift risk |

## 6. The harness (how to re-run this audit)

```bash
# Export a new fixture day from the local archive (committed, CI-safe):
py -3 tools/export_hod_replay_fixture.py --date 2026-07-17

# Replay it through the real engine (prints parity summary JSON):
cd backend && py -3 hod_momo_replay.py --date 2026-07-17

# Golden + parity tests (module-scoped full-day replay ~45s):
py -3 -m pytest tests/test_hod_momo_replay.py -q

# Fake-feed integration tests (real ticks/scanner_l1/bridge path):
py -3 -m pytest tests/test_hod_pipeline_fake_feed.py -q
```

Files: `backend/hod_momo_replay.py` (driver + injected clock),
`backend/tests/fixtures/hod_replay/` (tape/bars/meta for 2026-07-17),
`backend/tests/test_hod_momo_replay.py` (golden + parity),
`backend/tests/fakes/fake_ibkr_feed.py` +
`backend/tests/test_hod_pipeline_fake_feed.py` (Tier 2, incl. G1 xfail),
`backend/tests/conftest.py` (canonical engine reset).

Fidelity caveats (encoded in fixture meta + tests): tape covers only symbols
with an active tape subscription; `avg_volume` / live enrichment were not
archived; Former Momo list and configs reflect load time (config drift).
