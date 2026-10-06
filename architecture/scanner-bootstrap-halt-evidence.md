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
