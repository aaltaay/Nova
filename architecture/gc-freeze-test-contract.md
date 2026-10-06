# GC freeze test contract and completed-batch routing

Issues: #757 and #758. Authored delivery batch: `test-integrity#3`.

## Verified defect

PR #755 CI read 388475 frozen objects from `freeze_now()` and 388473 from a
later count. Frozen objects remain subject to ordinary reference counting, as
the production policy documents. A real logging handler that releases two
frozen lists after the snapshot reproduces that difference in 25/25 cycles;
all 10001 strongly held keeper lists remain outside `gc.get_objects()`.

## Test boundary

Keep the real collector and freeze implementation. Strongly reference a parent
keeper list and its 10000 children, capture their identities before freezing,
and verify those identities are absent from the subsequent collection walk.
Retain the frozen-snapshot lower bound and smaller-walk assertion. Exercise
ordinary refcount release after the snapshot without asserting an exact count
at a different time. Restore logger state and unfreeze in unconditional cleanup.
Production collection policy, timing, thresholds and #619 measured-evidence
acceptance remain unchanged.

## Prior-close event contract

The full backend run exposed an obsolete test that counts all scheduled socket
callbacks. Merged #750 now schedules scanner halt metadata independently of
trades. Executing the actual callbacks proves a prior close emits no trade,
while a real last emits one correct trade. Run scheduled callbacks and await
their tasks in the test; inspect price payloads and isolate the halt broadcaster.
Keep the halt observer and the close-fallback early return active. Preserve
candle/HOD controls. Change no runtime or trading policy.

## Final routing reconciliation

Merged #746 completed the scoped recorder code; merged #750/#755 completed the
scoped feed and diagnostic code. #674/#619/#667 remain open for recorded physical
evidence. Gate authored desk batches 6/7 so their completed code is not offered
again. Retain existing indices and human decision gates, record actual merged
footprints and completion notes, and preserve test-integrity batches 0/1/2.

## Verification

Reproduce the old count-equality failure with real refcount release; verify held
object exclusion and existing startup, disabled and logged-failure controls.
Repeat focused tests and run GC/performance neighbors. Check the five routing
cases that previously offered completed batches 6/7, then run metadata, document,
agent-contract and maintainer checks. Independent review before the ready PR.
Reproduce the prior-close assertion failure, then verify zero close-price trade
events and exactly one actual-price event alongside valid halt callbacks.
No operator checkout, orders, restart or historical-data repair is in scope.

## GC verification results (#757, 2026-10-05 ET)

The deterministic real-policy regression failed with the old equality:
`72294 == 72296` after its standard logging handler released two frozen lists.
The corrected test captures all 10001 keeper identities before freezing and
checks that the subsequent `gc.get_objects()` walk excludes them. It also
checks that the release ran, preserves the snapshot lower bound and smaller
walk, and removes/closes its handler in `finally`; pytest restores the logger
level and the existing fixture unfreezes the heap.

The GC module passed in 15 fresh Python processes: 60 test executions, zero
failures, including startup, disabled-switch and logged-failure controls.

```sh
python -m pytest -q backend/tests/test_gc_policy_freeze.py backend/tests/test_perf_heap.py backend/tests/test_perf_sample.py backend/tests/test_perf_watch.py backend/tests/test_perf_store_routes.py backend/tests/test_perf_stall_budget.py backend/tests/test_perf_waits.py backend/tests/test_perf_report_tool.py
```

That selected GC/performance run passed 63 tests in 7.01 seconds, with the
existing FastAPI/TestClient deprecation warning. Document invariants,
maintainer gate against `35d934a4` and the owned-file diff check passed.
Production GC code and the measured-evidence acceptance remain unchanged.

## Trade verification results (#758, 2026-10-05 ET)

The untouched focused file reproduced one failure and three passes. Executing
all old/current handler callbacks demonstrated zero prior-close trade payloads
and one correct actual-last trade, with independent halt metadata on current
code. The corrected test drains queued callbacks and awaits their tasks, then
asserts those actual trade payloads. Seven focused trade, halt, candle and Paper
reference files passed 72 tests. Parent rerun of both corrected modules passed
all eight tests. Changed-file Ruff and diff checks passed; no runtime edits.
