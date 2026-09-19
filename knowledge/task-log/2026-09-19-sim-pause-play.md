# 2026-09-19 -- Sim pause and play clock control

- **Status:** completed locally; no push
- **Agents:** Codex parent
- **Domain:** Sim clock/feed and UI
- **Related:** architecture/sim-clock.md; docs/sim-mode.md; D-050 #290; D-051 #291.

## Task
Add a Sim-only control using the same button with alternating pause/play icons. Continue on the current branch and commit locally without pushing, per the user's standing instruction.

## Goal
Freeze Sim time and stop ongoing synthetic/capture feed updates; resume from the same timestamp. Support inspection by scrubbing while paused. Preserve Trader tab selection.

## Why it mattered
A constantly advancing playhead makes replay charts and prints difficult to inspect.

## What we changed
Documented the clock API and ownership before code. Added process-local pause state, precise resume anchoring, a feed tick guard, Sim-only boolean pause requests, and an accessible icon toggle with inline request errors. Extracted shared clock types and the button so SimSessionHeader stays below 300 lines. Removed an unused fixed-interval import from the touched feed module.

## How it works now
Pause stores the actual timestamp. Play creates a monotonic anchor at that time and preserves the paused date even if midnight passed. Scrub moves the frozen timestamp without unpausing. Follow wall explicitly clears pause/resume date. Feed ticks return before generating prints, matching working fills, or fan-out while paused. Manual broker controls and IBKR paths are unchanged.

## Why this approach
The backend clock owns time for all Sim consumers, so a frontend-only frozen label would leave the tape running. Guarding the shared Sim tick covers synthetic and capture branches without coupling controls to IBKR. A boolean API is idempotent. Play resumes rather than jumping to wall time; an existing explicit Follow wall clock action handles that different intent. An extracted button owns request state/errors and keeps the header focused.

## Verification
- Backend clock/feed/mode/no-IBKR tests: 20 passed, two baseline failures deselected by name after confirming they reproduce at bd0d0cb in a clean detached checkout.
- Baselines: test_chart_bars_iso_ascending sees one bar before 06:00 ET instead of >5; test_overlay_forces_sim_even_when_gateway_looks_live lacks trading_allowed. D-051 #291 tracks both and is on Nova Delivery Todo.
- Vitest SimSessionHeader + traderOpen: 18 passed, including toggle, failure message, inactive Sim, and tab preservation.
- Chromium: mouse and keyboard scrubbing while paused, ticker selection, then Play toggle passed with a real WorkspaceProvider and API fixtures.
- npm run build passed; existing vendor chunk-size warning.
- Targeted ESLint and Ruff passed; doc_invariants passed.
- Full-project lint remains blocked by pre-existing D-050 #290, established in the immediately preceding task.
- No live broker requests or operator feed-mode changes used in tests.

## Follow-ups
Local commit only; no PR or push by explicit instruction. A running API process must reload to pick up the new paused field/action. No operator backend restart was performed.
Existing untracked backend/sim/data/ and logs/ remain untouched.

## Keywords
Sim, pause, play, monotonic, frozen timestamp, capture replay, clock, local commit
