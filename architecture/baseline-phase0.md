# Phase 0 — Pattern-Driven Architecture baseline

Captured: **2026-07-16**  
Tip SHA at capture: `078f9ad`  
Plan: `maintenance-audit-roadmap_519236d4.plan.md`

## Working-tree stabilization

- Git status at program start: **clean** on `master` (tracking `origin/master`).
- Prior uncommitted hotkey/settings work was already landed as Phase G2 (`645761b`) and follow-ups; no stash/reset/discard required.
- Cache paths (`backend/.cache/`, `.env`, `frontend/dist`) remain local and are not staged.

## Branch / phase ownership

- Work proceeds on **`master`** with **one intentional commit + push per phase** (0 → 13).
- No parallel writers on the same files; subagents are read-only / verify-only.
- Feature work must not interleave inside a structural phase.

## Line-count baseline (Python `count_lines` = same as `maintainer_checks`)

| Path | Lines | Notes |
|------|------:|-------|
| `frontend/src/index.css` | 6168 | CSS monolith; Phase 2 target |
| `backend/hod_momo.py` | 1079 | Accepted baseline (grew past 941) |
| `backend/constants.py` | 951 | Phase 3 |
| `frontend/src/constants.ts` | 821 | Phase 3 |
| `frontend/src/TickerChart.tsx` | 496 | Phase 5 |
| `backend/strategy/executor.py` | 494 | Accepted safety baseline; Phase 12 conditional |
| `backend/ticker.py` | 458 | Phase 8 |
| `backend/ibkr/depth.py` | 451 | Phase 9 |
| `backend/scan_runners.py` | 439 | Phase 8 |
| `tools/security_lib/checks.py` | 419 | Phase 6 |
| `backend/news/impact.py` | 408 | Phase 6 |
| `frontend/src/hod_momo/HodMomoSettings.tsx` | 406 | Phase 4 |
| `backend/hod_momo_integrity.py` | 402 | Phase 6 |
| `backend/archive/r2.py` | 402 | Phase 6 |
| `frontend/src/hod_momo/HodMomoDebugPanel.tsx` | 357 | Phase 4 |
| `frontend/src/hotkeys/HotkeyManager.tsx` | 317 | Phase 4 |
| `backend/main.py` | 168 | Within hard limit 200 |
| `frontend/src/App.tsx` | 83 | Within hard limit 150 |

## Maintainer scan baseline

```
py -3 tools/maintainer_checks.py
→ scanned 455 files
→ Findings: 38 (36 non-baseline)
```

Categories: file_size (many), swallowed_exception (production + tools), artifact_present (local), 2× BASELINE (hod_momo, executor).  
CSS not yet measured by the scanner (Phase 1 adds that).

## Test / build baseline (Phase 0)

| Suite | Result | Notes |
|-------|--------|-------|
| Maintainer checks | 38 findings / 36 non-baseline | recorded above |
| Backend pytest | **617 collected** | collect-only 2026-07-16; full run at Phase 13 |
| Frontend Vitest | **178 passed** / 38 files | 2026-07-16 Phase 0 |
| `npm run build` / Playwright | deferred to Phase 2+ UI gates | last-known Playwright 14 PASS (2026-07-15) |

## Production `import main` state access (Phase 7 inventory seed)

Lazy `import main` for caches/config appears in (non-exhaustive):  
`scan_runners.py`, `scan_loop.py`, `ticker.py`, `websocket.py`, `universe.py`, `ibkr_bridge.py`, `scanner.py`, `hod_momo_enrichment.py`, `integrity_live.py`, `health_status.py`, `app_lifespan.py`, `routes/scan.py`, `routes/health.py`, `routes/hod_momo.py`, `routes/news.py`, `routes/strategy.py`, `routes/nova_os.py`, `strategy/setups_stream.py`.  
Legitimate test imports of `main.app` are out of scope for the finding.

## Invariants preserved for all later phases

1. `discovery=ibkr` → IBKR-only prices/bars/depth/tape (no silent Alpaca fallback).
2. `auto_live` remains rejected; no live orders.
3. Quote/L2/T&S symbol gates and clear-on-switch remain mandatory.
4. Public API / WS / local-storage contracts stay compatible unless a phase explicitly changes one.
