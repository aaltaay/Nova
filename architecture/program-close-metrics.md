# Pattern-Driven Architecture — program close metrics

Closed: **2026-07-16** · Tip at close: see Phase 13 / close-remediation SHA in `Nova-Roadmap-Status.md`.

## Before (Phase 0) → After (close remediation)

| Metric | Before | After (fresh verify) |
|--------|-------:|------:|
| `frontend/src/index.css` | 6168 | **16** (import-only + `@layer` imports) |
| `backend/main.py` | 168 | **18** |
| `frontend/src/App.tsx` | 83 | **83** |
| `backend/hod_momo.py` | 1079 | **~140** (facade + test aliases) |
| `backend/constants.py` | 951 | **~18** (barrel) |
| `frontend/src/constants.ts` | 821 | **~12** (barrel) |
| `frontend/src/TickerChart.tsx` | 496 | **~12** (facade → `chart/TickerChart`) |
| `backend/strategy/executor.py` | 494 | **494** (deferred Phase 12) |
| Maintainer non-baseline | 36+ | **0** (`--fail-on-findings`) |
| Cross-feature deep imports | 15 baselined | **0** (public barrels) |
| Swallowed exceptions (prod) | 11+ | **0** (maintainer + Phase 2 handlers) |
| Backend pytest | 617 collected | **636 passed** (fresh) |
| Frontend Vitest | 178 | **187 passed** (fresh) |
| ESLint / Ruff | noisy | **exit 0** |
| Playwright | 14 | last-known **14** (not re-run this close) |

## Architecture program SHAs (Phases 0–13)

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
| 13 | `342b6cc` |

## Close-remediation SHAs (post-review)

| Phase | SHA |
|-------|-----|
| 1 Truthful audit | `5a5e455` |
| 2 Deps + silent handlers | `2c9a95e` |
| 3 Feed + symbol correctness | `2111511` |
| 4 Ports/adapters | `95884f7` |
| 5 Barrels + CSS layers | `71ec21e` |
| 6 Lifecycle + lint green | `bb281f4` |
| 7 Honest close | `aad9bf9` |

## Remaining accepted risks

- `executor.py` 494-line safety baseline — see `phase-12-executor-deferral.md`
- Residual `torch` CVEs without upstream fix — see `security/dependency-compensating-controls.md`
- Local artifacts (`.env`, `dist`, `.cache`) present but gitignored (informational)
- Live IBKR Gateway market-session validation not re-run in this program window
- Playwright not re-run on close remediation tip (last-known 14 @ prior finish pass)
