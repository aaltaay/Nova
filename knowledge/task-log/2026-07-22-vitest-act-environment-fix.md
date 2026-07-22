# 2026-07-22 — Vitest act() environment fix

- **Status:** completed
- **Agents:** parent (implementer under daddy dispatch)
- **Domain:** frontend test harness / React 19
- **Related:** `CHANGELOG.md` §2026-07-22 Vitest act environment · `PROBLEM_LOG.md` §2026-07-22 FIXED + diagnosed 2026-07-20 · audit task-log `2026-07-20-vitest-act-environment-audit.md`

## Task

Apply the named root-cause fix from the 2026-07-20 Vitest act-environment audit: set `globalThis.IS_REACT_ACT_ENVIRONMENT = true` via a Vitest setup file and wire it in `vite.config.ts`.

## Goal

Zero instances of `The current testing environment is not configured to support act(...)` on `npx vitest run --reporter=verbose`, suite still green, and React’s real “update not wrapped in act” safety net re-enabled.

## Why it mattered

The unset flag was not purely cosmetic. React 19’s concurrent act check both (1) warned on every legitimate `act()`-wrapped `createRoot` mount and (2) short-circuited `warnIfUpdatesNotWrappedWithActDEV`, so escaped async updates could slip through tests silently. That removed a guardrail for all hand-rolled JSX tests in this repo (no `@testing-library/react`).

## What we changed

- Added `frontend/src/testSetup/reactActEnvironment.ts` — sets `globalThis.IS_REACT_ACT_ENVIRONMENT = true` (global typing only; not a product constant).
- Wired `test.setupFiles: ['./src/testSetup/reactActEnvironment.ts']` in `frontend/vite.config.ts`.
- Documented in CHANGELOG + PROBLEM_LOG (fixed entry referencing the 2026-07-20 diagnosis).

## How it works now

Vitest loads the setup file before each test file. React 19 sees `IS_REACT_ACT_ENVIRONMENT === true`, so `act()`-wrapped mounts are quiet and unwrapped async updates can warn again. Product code, `constants.ts`, and `App.tsx` are unchanged. Tests still use manual `createRoot` + `act`.

## Why this approach

**Required.** The 2026-07-20 audit already proved the root cause and named the fix; inventing a different approach would fight React’s documented contract.

- **Chosen:** one-line env bootstrap in a dedicated setup module + `setupFiles` — matches React 19’s check site, keeps the assignment out of `vite.config.ts` inline junk, and stays out of product constants.
- **Rejected:** adopting `@testing-library/react` solely to set the flag — RTL would set it, but the project has zero RTL usage and 24+ hand-rolled mounts; a full RTL migration is out of scope for silencing/re-enabling the guardrail.
- **Rejected:** inlining the assignment in `vite.config.ts` — harder to find, no typed global, and the audit explicitly asked for a setup file.
- **Rejected:** putting the flag in `constants.ts` — not a product tunable; test-harness only.
- **Rejected:** per-file `beforeAll` in every `*.test.tsx` — easy to miss new files; setupFiles is the single choke point.

## Verification

```text
cd frontend
npx vitest run --reporter=verbose
# → Test Files 99 passed | Tests 422 passed
# → zero "not configured to support act(...)"
# → remaining real warning: WorkspaceContext.test.tsx (WorkspaceProvider)

npx vitest run src/ibkr/workingOrderCells.test.tsx \
  src/closed_orders/closedOrderCells.test.tsx \
  src/stock_view/StockViewOpenOrdersDock.test.tsx \
  src/orders_today/OrdersTodayView.test.tsx --reporter=verbose
# → 4 files / 28 tests passed, no act-environment noise
```

## Follow-ups

- `src/workspace/WorkspaceContext.test.tsx` — “exposes defaults before config resolves” still fires two “An update to WorkspaceProvider … was not wrapped in act(...)” warnings because the stubbed `/api/config` fetch resolves after the synchronous `act(render)`. Sibling tests already flush with `await act(async () => { await Promise.resolve(); ... })`. Fix that test’s async flush without losing the defaults-before-resolve assertion. Out of scope for this env-only commit.

## Keywords

IS_REACT_ACT_ENVIRONMENT, Vitest, setupFiles, act, React 19, reactActEnvironment, WorkspaceContext
