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
