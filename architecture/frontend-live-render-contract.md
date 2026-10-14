# Frontend live render contract

Owners: `frontend/src/hot_list/`, `frontend/src/ibkr/`. Implements ADR 026's
measured performance work without weakening ADR 045's displayed-view stamps.
Wire shapes remain in `schema/bot.md`, `schema/book-watch-and-luld.md` and
`schema/execution.md`.

## Equal hot-list reads (#797)

The window's shared hot-list store compares every field in the normalized
`HotListView`, including entry and yesterday order, admission reasons, caps,
auto settings, feed errors and trading date. Equal reads retain the prior view
and state identities and do not notify subscribers. Changed data, a read error
or recovery, and write busy transitions publish immediately. A failed read
keeps the last view. This comparison changes neither poll cadence nor requests.

## Measure depth before changing it (#797)

A fixture renders the actual `DepthLadder` and depth socket hook with bounded,
synthetic books, plan levels, book-watch verdicts and LULD bands. It reports
React commit durations and deterministic formatting work for active updates.
These are controlled development-render measurements, not production frame or
GPU timings, and elapsed-time values have no pass threshold.

The fixture must verify the displayed bid/ask and ADR 045 book sequence on every
active update, no render for freshness beats, and latest-book publication when
a hidden tab resumes. Plan levels, book-watch marks and totals, and calculated
LULD bands must remain visible and update with their own frames. A benchmark
alone does not authorize slowing prices, withholding a displayed sequence,
disabling annotations or adding a stale-view permission exception.

Existing row memoization, hidden-tab paint suppression and freshness-only beats
remain in force. Change another depth path only after the fixture identifies
specific redundant work and a regression preserves these properties.

The active fixture identified repeated locale formatting in ladder rows,
book-watch tooltip/mark text and LULD annotations. `ibkr/depthNumberFormat.ts`
owns reusable `Intl.NumberFormat` instances for their existing en-US formats:
depth prices with two to four decimals, LULD prices with two decimals, and
ordinary grouped numbers with the locale's existing defaults. Formatters are
created once per module, while every changed number is still formatted and
displayed immediately. Stable annotation keys preserve row identity too.

The Chromium fixture in `frontend/e2e/desk-freezes.spec.ts` loads production
components and styles through the repository's isolated Playwright Vite server.
It intercepts requests only at the configured fixture API origin, so a route
such as `/src/api/novaFetch.ts` remains a source module. Every API reply and depth
socket is a fixture; console errors, uncaught page errors and unexpected API or
runtime-operation requests fail verification. Clock advancement exercises real
hot-list polling, and changed book/annotation frames exercise visible values and
displayed-view stamps without a broker or production desk.

The baseline's first navigation waits up to 20 seconds for the nav rail to
mount. A traced cold Vite load spent 8.3 seconds in the first readiness assertion
loading the lazy App module graph before the rail appeared (9.4 seconds from
navigation start); the former generic
5-second assertion ended with modules still pending, without a page exception.
The observed initial grid, toolbar and sample-badge waits in the chart-pane,
trendline, scanner-account and Fund account specs use the same bound when a fresh page still
shows the lazy Loading status. This bound applies only to initial browser-test
readiness. Subsequent interaction
assertions, product timing, market freshness and order deadlines are unchanged.

The Fund account browser spec fulfills the intended Client Portal destination
through a context route and asserts that exact navigation. It verifies Nova's
link behavior, with no dependency on the remote broker website's availability
and no account access or login.
