# 2026-07-20 — Vitest act() environment warning audit

- **Status:** completed (audit-only, no fix applied — by explicit request)
- **Agents:** daddy (direct investigate, no specialist nesting needed)
- **Domain:** frontend test hygiene
- **Related:** `PROBLEM_LOG.md` §2026-07-20 "Vitest act() environment warning silently hides real async-update bugs"

## Task

Parent session flagged that `frontend/src/ibkr/workingOrderCells.test.tsx` and
`frontend/src/closed_orders/closedOrderCells.test.tsx` print
`The current testing environment is not configured to support act(...)` on
every test (tests still pass, 25/25) and had dismissed it as "pre-existing
environment noise, unrelated to this change" without verifying. Asked for a
full audit: root cause, scope, whether it's actually benign, and a named fix
recommendation — audit only, no source edits.

## Goal

Confirm or refute the root-cause hypothesis (`globalThis.IS_REACT_ACT_ENVIRONMENT`
never set), measure how many test files are affected, determine whether the
warning could be masking a real async-update-outside-act bug, and name an
exact, correctly-scoped fix — without applying it. Also flag (not fix) the
`PositionsPanel.tsx` missing-test-file gap.

## Why it mattered

"Pre-existing noise, unrelated" is exactly the kind of unverified claim the
self-annealing protocol exists to catch. If the flag omission also disables
React's real "update not wrapped in act" warning, every manual-mount test in
the suite (not just the two named) is running with a real safety net removed,
which is a materially different risk profile than "cosmetic log spam."

## What we changed

Nothing in source. Diagnostic-only:

- Read `frontend/vite.config.ts` (no `test.setupFiles`) and confirmed no
  `setupTests`-style file exists anywhere in `frontend/`.
- Confirmed via `rg`/Grep that `IS_REACT_ACT_ENVIRONMENT` is not set anywhere
  in the repo, and that `@testing-library/react` is not a dependency at all
  (absent from `package.json` and `node_modules`) — this project's entire
  `.tsx` test suite hand-rolls `createRoot` + `act` instead of using RTL.
- Wrote a throwaway probe test (`src/__act_probe__.test.tsx`) logging
  `globalThis.IS_REACT_ACT_ENVIRONMENT` before/inside/after `act()`; ran with
  `--reporter=verbose`; deleted the probe file afterward.
- Ran the full suite (`npx vitest run` and `--reporter=verbose`) to quantify
  scope (94 files / 386 tests / 653 warning instances across 24 real test
  files) and confirm all still pass.
- Read `react-dom/cjs/react-dom-client.development.js` source for
  `isConcurrentActEnvironment()` / `warnIfUpdatesNotWrappedWithActDEV` to
  determine exactly when each warning fires.
- Added the `PROBLEM_LOG.md` entry above (diagnosis, not a code fix).

## How it works now

- React 19's `act()` (imported from `'react'`, works because `react-dom`
  registers itself as the active renderer on first `createRoot` use) checks
  `globalThis.IS_REACT_ACT_ENVIRONMENT` inside `isConcurrentActEnvironment()`
  every time a top-level fiber update is scheduled (i.e. every `render()` and
  `unmount()` call, whether or not it's wrapped in `act()`).
- If the flag is `undefined` **and** we're currently inside an `act()` scope
  (`ReactSharedInternals.actQueue !== null`), React prints "not configured to
  support act(...)" — that's the noise the user saw.
- If the flag is `undefined` **and** we're NOT inside `act()` (a real bug: an
  update escaped the wrapper), `isConcurrentActEnvironment()` also returns
  falsy, which short-circuits `warnIfUpdatesNotWrappedWithActDEV`'s own guard
  — so the *other*, bug-catching warning ("update ... was not wrapped in
  act(...)") never fires either. **The missing flag disables the safety net
  in both directions**, not just the wrapped/noisy one.
- Today, for the two files named in the issue, this is inert: both
  `renderWorkingOrderCell`/`renderClosedOrderCell` are pure, hookless
  switch-statement functions (confirmed by reading them) — there is no
  effect, promise, or timer that could produce a stray update, so no live
  bug is currently hiding behind the warning in those two files specifically.
- The warning is invisible under Vitest's **default** reporter for passing
  tests (only shown via `--reporter=verbose` or on failure) — this explains
  why it looked like isolated/occasional noise rather than a suite-wide,
  deterministic condition affecting all 24 manual-mount `*.test.tsx` files.
- `frontend/src/ibkr/PositionsPanel.tsx` has no `PositionsPanel.test.tsx`
  (confirmed via glob), unlike its siblings `workingOrderCells.test.tsx` /
  `closedOrderCells.test.tsx`. Flagged only, not written.

## Why this approach

Considered dispatching to `maintainer` for a "broader test-hygiene audit,"
but the specific claim to verify (env flag + act warning semantics) required
reading React's own source and running a controlled probe — work a general
audit pass wouldn't add rigor to, and duplicating it through a nested
specialist would only add latency without new evidence. Direct daddy
investigation matches the existing memory precedent ("investigate-only →
direct explore + spot-check gates"). Did not apply the fix even though it's
a one-line change, per explicit "audit only" instruction — recommending
`test.setupFiles` + a dedicated setup module (not inlining into
`vite.config.ts`, and not touching `App.tsx`) keeps the eventual fix
compliant with `frontend-modularity.mdc` without deciding it here.

## Verification

- `npx vitest run <targeted files>` — reproduced 25/25 passing, warning
  invisible under default reporter (matches parent session's transcript).
- `npx vitest run <same files> --reporter=verbose` — warning appears 48
  times across the two named files; confirmed deterministic, not flaky.
- `npx vitest run --reporter=verbose` (full suite) — 94 files / 386 tests
  passed; 653 total warning instances across exactly the 24 files that use
  the `createRoot` + `act` manual-mount pattern (grep-confirmed same file
  set both ways).
- Read `react-dom/cjs/react-dom-client.development.js` to confirm the exact
  code path and short-circuit logic described above.
- `Glob frontend/src/ibkr/PositionsPanel*` — only `PositionsPanel.tsx`
  exists, no test file.
- Deleted the throwaway probe test file after use; no source files edited.

## Follow-ups

- Fix (not applied): create `frontend/src/testSetup/reactActEnvironment.ts`
  (or similarly named, under a `test`/`testSetup` module — not `App.tsx`,
  not `vite.config.ts` inline) that sets
  `globalThis.IS_REACT_ACT_ENVIRONMENT = true`, then add it to
  `test.setupFiles` in `frontend/vite.config.ts`. Re-run
  `npx vitest run --reporter=verbose` afterward to confirm the 653 instances
  drop to 0 and no new "not wrapped in act" warnings appear (that would mean
  a real bug was uncovered, not introduced).
- Coverage gap: `frontend/src/ibkr/PositionsPanel.tsx` has no dedicated test
  file, unlike sibling `workingOrderCells.test.tsx` / `closedOrderCells.test.tsx`.
  Candidate `tester` handoff — not actioned here.

## Keywords

IS_REACT_ACT_ENVIRONMENT, act environment, createRoot, react-dom-client,
isConcurrentActEnvironment, warnIfUpdatesNotWrappedWithActDEV, vitest verbose
reporter, testing-library/react absent, PositionsPanel test gap
