# 2026-09-19 -- Sim scrubbing preserves the active Trader tab

- **Status:** completed locally; not pushed
- **Agents:** Codex parent
- **Domain:** Sim / Trader workspace
- **Related:** ADR 011 section 7b; CHANGELOG and PROBLEM_LOG 2026-09-19 Sim scrub entries; D-050 / #290 (unrelated lint blocker).

## Task
Fix the Sim slider reopening SIM1 when IMCC is active and SIM1 is closed. User explicitly instructed: stay on altaaya/sim-session-tape-local, commit, and do not push.

## Goal
Scrubbing changes replay time and refreshes data without changing tabs. Explicit replay ticker selection still opens/activates its ticker.

## Why it mattered
The clock control overrode deliberate desk navigation and resurrected a closed tab.

## What we changed
Documented the navigation boundary in ADR 011 before code. Removed openStockView from postScrub and its unused emitCharts parameter. Added pointer/debounced unit regressions and a Chromium fixture using the real WorkspaceProvider for mouse/keyboard scrubbing and explicit ticker selection.

## How it works now
The backend replay selection remains independent of the active Trader tab. Clock responses update time and emit the same refresh event. applyReplay remains the only header path that explicitly opens the selected ticker.

## Why this approach
Removing the clock's navigation side effect fixes the owner of the bug without changing workspace tab semantics or replay/feed selection. Automatically switching the replay symbol to the active tab would change which capture is loaded and was outside this request. The regression retains the refresh event to protect the earlier chart/tape resync behavior.

## Verification
- Before fix: two of three new Vitest cases failed, receiving SIM1 instead of IMCC.
- After fix: npx vitest run src/sim/SimSessionHeader.test.tsx src/workspace/traderOpen.test.tsx -- 15 passed.
- npx playwright test e2e/sim-session-scrub.spec.ts -- 1 Chromium test passed, real WorkspaceProvider with intercepted API fixtures on isolated port 4173.
- npm run build -- passed (existing vendor chunk size warning).
- Changed TS/TSX files: npx eslint -- passed.
- py -3 tools/doc_invariants.py -- passed.
- Full npm run lint -- blocked by three existing rules-of-hooks errors in unchanged GatewayDisconnectedBanner.tsx:93,94,96. Deferred as D-050 #290 and added to Nova Delivery Todo; no unrelated fix attempted.

## Follow-ups
No push or PR per explicit user instruction. No live broker calls in verification. Existing untracked backend/sim/data/ and logs/ left untouched.
A separate clean worktree was initially created at C:/Users/aalta/.codex/worktrees/nova-sim-scrub from origin/master, but master lacks this slider. It was not used for edits after the user required work in the current checkout.
D-050 remains open for a focused banner hook-order fix.

## Keywords
sim, scrub, replay, IMCC, SIM1, Trader, closed tab, focus, local commit
