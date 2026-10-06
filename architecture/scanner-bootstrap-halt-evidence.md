# Scanner bootstrap halt evidence

Issue: #764. Authored delivery batch: `desk-and-leftovers#11`.

## Verified defect

The real scanner hook can receive a current live `halt_patch` while an older
REST bootstrap body is still decoding. Applying that body then replaces the
newer served halt state. On a persistent-authoritative desk, structural REST
does not recur to repair the state. The existing history guard runs before
JSON decoding, so a view change during decoding can also apply obsolete rows.

Controlled Chromium probes separately reproduce a stale test socket route and
the production overwrite: a new route paints HALTED, then a delayed false REST
body paints TRADING. The failing CI run has no uploaded Playwright trace, so
those two verified timing paths do not establish which caused that CI failure.

## Runtime boundary

Use a live request scope owned by `useScannerData`, with a small scanner helper.
Fence the complete asynchronous request against live/history, provider and
mount changes, including leaving and reentering the same view. A newer request
supersedes its older pending predecessor. Check scope at each state application,
including after JSON decoding; obsolete errors and catalysts cannot paint the
new view either.
When provider or persistent-authoritative settings invalidate a pending history
load, restart that selected date's load in the replacement scope. Discarding an
old result must not strand live rows beneath a selected history date.

Retain only halt receipts received while that particular live request is
pending. Its guarded row setters merge those receipts into the incoming roster
after shape/last-good processing. Preserve true, false and null explicitly.
The merge changes only `halted`; it admits no patch-only symbol and changes no
price, order, membership, metadata, revision or freshness field. A later fresh
REST request starts without the previous request's receipts and can supply a
new halt value. Historical rows and normal WS roster ownership keep their
existing behavior.

Keep one pending request and a centralized 256-symbol receipt bound, matching
the native halt-state retention bound. Clear retained receipts on completion,
scope exit or the existing fetch timeout. If the bound is exceeded, reject that
request's older snapshot and use the existing REST retry instead of applying
incomplete halt evidence. Do not add a polling loop, new socket, clock policy,
backend halt rule, source decision or trading gate.

The hook keeps the single scanner state lifecycle: REST, stream and history
must apply to the same owned setters. Its request mechanics are extracted into
the new helper; modest growth past the 400-line advisory limit is documented
with that one-concern reason rather than moving unrelated state into a new file.

## Browser boundary

The halt fixture must wait for a newly assigned socket route and that route's
`set_active_tab` handshake after history-to-live. Use different history and live
prices to prove body application rather than a label that was already present.
Exercise a deliberately held returning-live REST body: receive the current halt
frame first, release the older body, and verify the newer halt survives. Retain
the frozen-table, unknown, resume, history-ignore and Halted-chip acceptance.
Use observable barriers, not elapsed-time waits.

## Verification

Add red-first real-hook tests for delayed JSON bodies and newer true/false/null
receipts, initial bootstrap before row admission, fresh subsequent REST, scope
round trips and timeout/supersession. Verify that only halt decoration is merged
and that receipt retention is bounded and disposed. Run scanner REST, history,
stream, roster, price and board-filter neighbors; run the real browser fixture,
TypeScript build, frontend lint and repository document/maintainer checks.
Record exact outcomes before publication. No physical-PC operation or measured
feed/GC evidence gate is part of this issue.

## Runtime verification results (2026-10-06)

The first unchanged-runtime hook run reproduced five failures: each newer
true/false/null receipt was lost, a decoded live body replaced a history view,
and an old live body replaced the new view after a history round trip. Provider
scope and delayed catalyst regressions cover the same application boundary.
Review then caught timeout cancellation suppressing the existing failure/retry;
two red header/body abort regressions verified that defect before correction.

The final two focused files pass 18 tests. A nine-file scanner REST, history,
honesty, halt, filter and stream run passed 63 tests before the final provider
guard; the focused rerun includes that additional provider regression. Tests
explicitly queue React-style functional updates until after receipt disposal,
exercise timeout/supersession/unmount, and reject incomplete overflow snapshots
before permitting a fresh request. Owned-file ESLint, TypeScript, document
invariants and maintainer gate against `36c4cf3` pass. The stable-source cold
Chromium run passes all four browser cases; broader publication checks are
recorded by the parent in the PR.

Independent review then reproduced pending history stranded on live price 4.3
after either provider or persistent-setting changes. Both additional real-hook
regressions failed before the minimal history-effect dependency correction.
They now prove a replacement history load paints 4.2 before the obsolete body
is released and that its later 9.9 value is ignored. The final nine-file scanner
run passes 66 tests, including 20 request/hook tests, and changed hook/test
ESLint and the diff check pass. This correction preserves the obsolete-result
guard and adds no runtime beyond restarting the selected history load.

## Committed view ownership (#766)

Native review of merged #765 identified render-time scope mutation. A real
React `startTransition` render that changes the provider and suspends after
calling the scanner hook leaves the old live view committed. Nevertheless,
render-time `setView` cancels its pending request; discarding the preview then
leaves that original request rejected without a replacement. The same proof
passes before #764 and fails on the merged implementation. A suspended history
preview also makes the render-written history ref reject a current live halt
frame; that latent ref-ownership defect reproduces before and after #764.

Publish scanner scope, history-date, health and callback-sink refs in a layout
effect for the committed render, before the existing passive fetch and stream
effects. Invalidate on layout unmount cleanup. A speculative or abandoned render
must not cancel committed requests, block current halt evidence, or publish
preview feed callbacks. Keep the envelope callback stable and dispatch through
the committed sink, so the existing envelope poll's render-written callback ref
cannot introduce a preview callback. No poll or stream hook rewrite is needed.

Preserve all request-local receipt, timeout/retry, overflow, committed scope
transition and history reload behavior from #764. Use real Suspense/transition
tests with observable committed output and an attempted suspended-render
barrier; verify pending live and history responses survive discarded provider
and persistent-setting previews, live halt frames survive a history preview,
and current feed callbacks are used. Run the existing scanner neighbors,
TypeScript, lint, real browser, document and maintainer checks. This follow-up
uses authored `desk-and-leftovers#12` and does not reopen measured evidence or
source-policy acceptance.

### Committed ownership verification (2026-10-06)

All seven real React regression cases failed before the source correction:
discarded provider/persistent previews stranded live and selected-history
responses, a suspended history preview blocked the committed live halt, and
preview feed callbacks leaked into current envelope polling and a fresh live
refresh. The tests observe the old committed DOM and a real attempted Suspense
render, release actual response JSON promises, and verify no replacement fetch
was needed for props that never committed.

After layout publication and the stable envelope callback, the ten-file scanner
run passes 73 tests. The final three hook/request files pass 27 tests after the
layout effect dependency list is explicit; this includes all existing timeout,
scope-transition and receipt regressions. Owned-file ESLint, TypeScript build,
document invariants, maintainer gate against `368dc564` and diff checks pass.
No helper, stream, envelope-poll, backend, trading or evidence-policy runtime
changed. The parent records current-head browser/full-suite review before
publication, together with the separately owned recorder test correction.
