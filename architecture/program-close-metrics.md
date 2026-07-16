# Pattern-Driven Architecture — program close metrics

Closed: **2026-07-16** · Tip at close: see Phase 13 commit SHA in `Nova-Roadmap-Status.md`.

## Before (Phase 0) → After (Phase 13)

| Metric | Before | After |
|--------|-------:|------:|
| `frontend/src/index.css` | 6168 | **18** (import-only) |
| `backend/main.py` | 168 | **18** |
| `frontend/src/App.tsx` | 83 | **83** |
| `backend/hod_momo.py` | 1079 | **137** (facade) |
| `backend/constants.py` | 951 | **14** (barrel) |
| `frontend/src/constants.ts` | 821 | **7** (barrel) |
| `frontend/src/TickerChart.tsx` | 496 | **187** |
| `backend/strategy/executor.py` | 494 | **494** (deferred Phase 12) |
| Maintainer findings | 38 (36 non-baseline) | **20** (4 non-baseline: sync_agent_surfaces was 401→fixed, artifacts×3) |
| Swallowed exceptions | 11+ | **0** |
| Backend pytest | 617 collected | **669 passed** |
| Frontend Vitest | 178 | **178 passed** |
| Playwright | 14 | **14 passed** |

## Phase SHAs

| Phase | SHA |
|-------|-----|
| 0 | `00f0d21` |
| 0A | `9fac089` |
| 1 | `67d369a` |
| 2 | `e15f252` |
| 3 | `b03f34c` |
| 4 | `71170c3` |
| 5 | `60f4764` |
| 6 | `b4e7033` |
| 7 | `50a14fe` |
| 8 | `10e3996` |
| 9 | `fc3535a` |
| 10 | `72ec84b` |
| 11 | `f14bcb8` |
| 12 | `8a6de9b` |
| 13 | _(this commit)_ |

## Remaining accepted risks

- `executor.py` 494-line safety baseline — see `phase-12-executor-deferral.md`
- Legacy frontend cross-feature imports flagged as baseline warnings
- Local artifacts (`.env`, `dist`, `.cache`) present but gitignored
- Ruff reports many pre-existing style findings (not introduced by this program; not a regression gate for this close)
- Live IBKR Gateway market-session validation not re-run in this program window
