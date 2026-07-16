# Phase → layer / slice destination map

Every Phase 1–13 product move must land in a destination consistent with [`dependency-rules.md`](./dependency-rules.md).

| Phase | Primary destinations | Layer / slice |
|-------|----------------------|---------------|
| 1 | `tools/maintainer_checks.py`, rules, maintainer memory | Tooling / governance |
| 2 | `frontend/src/styles/*`, feature `*.css`, `index.css` imports | CSS shared + features |
| 3 | `backend/constants_*.py` or `backend/*/constants.py`; `frontend` feature/shared constants; barrels | Domain + Shared constants |
| 4A | `frontend/src/hotkeys/*` child components | Feature: hotkeys |
| 4B–C | `frontend/src/hod_momo/*` settings/debug pieces | Feature: hod_momo |
| 5 | `frontend/src/chart/*` hooks; thin `TickerChart.tsx` | Feature: chart |
| 6A | `backend/hod_momo_integrity_*.py` | Domain (pure evaluators) |
| 6B | `backend/news/impact_*.py` | Domain + thin application |
| 6C | `backend/archive/r2_*.py` | Adapter + application orchestration |
| 6D | `tools/security_lib/checks_*.py` | Tooling |
| 7 | `backend/runtime_state/` or `scanner_state.py`; strip `main` caches | Composition / state |
| 8A | `backend/scan_*.py` use cases + discovery port | Application + Ports |
| 8B | `backend/ticker_*.py` + market-data ports + adapters | Application + Adapters |
| 9 | `backend/ibkr/depth_*.py` | Adapter (IBKR) |
| 10 | HOD shared state + persist/session/trade/admin modules; `hod_momo.py` facade | Application + Domain + state |
| 11 | Narrow exception handling across shell modules | Imperative shell observability |
| 12 | Optional `executor_fill.py` / state extract; gate chain stays in `executor.py` | Application (safety-sensitive) |
| 13 | Docs, memory, ledger only (plus verify) | Governance |

## Compatibility facades expected during migration

| Facade path | Removal criterion |
|-------------|-------------------|
| `backend/constants.py` | All callers import domain modules OR barrel is &lt;400 and documented permanent |
| `frontend/src/constants.ts` | Same for frontend |
| `backend/hod_momo.py` | Facade ≤400 after Phase 10; deep logic gone |
| `backend/scan_runners.py` | Thin re-export after 8A |
| `backend/ticker.py` | Thin re-export after 8B |
| `frontend/src/index.css` | Permanent import root (≤50 lines) |
