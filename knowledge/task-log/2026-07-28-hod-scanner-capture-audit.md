# 2026-07-28 -- HOD scanner capture audit + mock replay harness

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo | market-feed | execution (audit)
- **Related:** `CHANGELOG.md` § 2026-07-28 HOD scanner capture audit · `PROBLEM_LOG.md` § 2026-07-28 (3 entries) · `docs/audits/2026-07-28-hod-scanner-capture-audit.md`

## Task

Audit the HOD Momo scanner against the outcome "if something happens in the market, we capture it", with a mock/replay test harness on real sample data, focused on IBKR API-layer data accuracy, plus a design comparison against other projects.

## Goal

A written audit with code evidence + ranked gaps, and a two-tier verification harness: deterministic engine replay of archived tape with golden/parity assertions, and a fake IBKR feed driving the real ticks/scanner_l1/bridge path. No product-code fixes in this pass (user chose audit + harness scope).

## Why it mattered

The scanner's failure modes are invisible: alerts that never fire look identical to a quiet market. The user specifically distrusted the IBKR layer's data accuracy, and there was no way to test HOD capture without market hours + a Gateway login.

## What we changed

- `tools/export_hod_replay_fixture.py`: exports a committed fixture (tape/bars/meta) from the local archive for any session date; ran it for 2026-07-17 (89,084 prints, 11 symbols, 794 production alerts).
- `backend/hod_momo_replay.py`: replay driver -- primes engine state like production (session-high floor from early bars, surge buffer seed, TickerSnap from movers cache + production enrichment stand-ins), feeds prints in ts order with reconstructed cumulative volume + running day-high, pins `time.time` and `market.now_et` to replay time, mirrors the consolidation flush without disk/WS side effects.
- `backend/tests/conftest.py`: canonical `reset_hod_engine_state` (extracted from test_hod_momo_engine; also clears metrics volume buffers and surge sets); engine tests delegate to it.
- `backend/tests/test_hod_momo_replay.py`: 8 golden + parity tests (mover fires, determinism, disabled-silent, rollover partitions, full-day parity vs production alert log).
- `backend/tests/fakes/fake_ibkr_feed.py` + `backend/tests/test_hod_pipeline_fake_feed.py`: scripted fake of the ib_async reqMktData surface driving the REAL L1 chain; 4 passing tests (admission gate, day-high-only updates, coalescing) + 1 strict xfail proving the post-reconnect zombie-subscription gap.
- `docs/audits/2026-07-28-hod-scanner-capture-audit.md`: full audit -- five capture dimensions, parity matrix, 9 ranked findings, external comparison, prioritized fix list.
- `PROBLEM_LOG.md`: 3 diagnoses (zombie L1 subs, delayed-data blindness, L1 archive gap).

## How it works now

Any agent can verify HOD capture offline in under a minute: replay a fixture day through the real engine and diff emitted alerts against what production persisted. The parity run for 2026-07-17 shows the momentum core (Squeeze 11, Running Up 12) reproduces on dense-tape movers, quiet symbols stay silent, and replay never fires a strategy production did not. The unreproducible rows (CNF/WZRD/SLND/KLRS) trace to one root cause: the archive records tape subscriptions only, not the L1 tick stream that actually drives evaluation.

## Why this approach

- **Replay the real engine, not a model of it.** Driving `hod_momo.on_trade_update` with an injected clock gives parity evidence; a reimplemented simulator would prove nothing about production behavior. Clock pinning (`time.time` + `market.now_et`) was the minimum seam -- surge windows, pace RVOL, session min-RVOL, and consolidation deadlines all evaluate on replay time.
- **Two tiers over one.** Engine replay (Tier 1) is deterministic and CI-safe but skips the IBKR-facing layer; the fake feed (Tier 2) drives the real ticks/scanner_l1/bridge modules so admission, coalescing, and reconnect behavior are covered too. The zombie-sub defect is encoded as a strict xfail -- it fails loudly the day someone fixes it (XPASS breaks the build until the marker is removed).
- **Committed fixtures over .cache reads.** The archive is local-only and untracked; exporting a small JSONL slice keeps CI deterministic and documents fidelity caveats in the fixture meta itself.
- **Rejected:** simulating the engine; testing only `on_trade_update` in isolation (already covered by unit tests); fixing the found defects in the same pass (user scope); exact alert-count parity assertions (config drift + unarchived enrichment make it unprovable today -- the audit recommends archiving enrichment + L1 ticks to unlock it).

## Verification

- `py -3 -m pytest tests/test_hod_momo_replay.py -q` -- 8 passed (module-scoped full-day replay ~45s)
- `py -3 -m pytest tests/test_hod_pipeline_fake_feed.py -q` -- 4 passed, 1 xfailed (zombie L1)
- Full HOD + L1 suite: 109 passed, 1 xfailed; `test_hod_momo_engine.py` 15/15 after conftest extraction
- Replay CLI parity matrix matches the audit doc table (SDOT/BIYA/CJMB -> 11/12; quiet set silent)

## Follow-ups

Ranked fix list lives in the audit doc section 5: P0 archive L1 ticks for active-set symbols; P0 clear/re-establish `ticks._subs` on generation bump + handle 1100/1101/1102/2104-2108; P1 `reqMarketDataType` + delayed-data labeling (10167); P1 persist `session_high_raised_ts`; P2 active-set rebuild on roster commit + uncovered-symbol UI; P2 archive enrichment snapshots; P3 Error 101 on L1 + quote-quality flag for close-as-last; P3 extract consolidation grouping into a shared pure function. Extra fixture days (2026-07-20, 2026-07-23) can be exported with the same tool when needed.

## Keywords

hod momo, capture audit, replay harness, fake ibkr feed, zombie L1, reqMarketDataType, delayed data, archive coverage, parity test, ADR 008, scanner_l1, tape_ibkr
