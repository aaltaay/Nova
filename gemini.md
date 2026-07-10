# 🏛️ GEMINI.MD — Project Constitution (Law)
> **Status:** ENFORCED — Active governance document
> **Last Updated:** 2026-04-27
> **Project:** Nova — Stock Alert Automation System
> **Enforcement:** Every AI agent (Cursor, Antigravity, any LLM assistant) MUST read this file before writing ANY code. Violations are NEVER acceptable.

---

## 0. PURPOSE

This document is the **single source of truth** for how this project is built, maintained, and extended. It exists because:
1. AI assistants lose context between sessions.
2. Without rules, assistants dump everything into monoliths.
3. The user has explicitly mandated modular, disciplined engineering.

**If a rule here conflicts with an agent's default behavior, this document wins.**

---

## 1. ⚖️ Architectural Invariants (Unbreakable Law)

These rules CANNOT be violated under ANY circumstance:

| # | Invariant | Rationale |
|---|-----------|-----------|
| 1 | **Data-First** | No tool is written before the JSON schema is confirmed in this file. |
| 2 | **Deterministic Tools** | All Python scripts in `tools/` must be atomic, testable, and side-effect-free unless explicitly noted. |
| 3 | **Secrets in `.env` only** | No API keys, tokens, or credentials EVER appear in source code, logs, or commits. |
| 4 | **`.tmp/` is ephemeral** | Never treat `.tmp/` files as a source of truth. |
| 5 | **SOP before code** | If logic changes, update `architecture/` or relevant `.cursor/rules/` FIRST, then write code. |
| 6 | **Self-Annealing** | Any error → Analyze → Patch → Test → Update SOP/rules → Log in `PROBLEM_LOG.md`. |
| 7 | **Read-Only Mode** | The system only reads market data from API. It does NOT execute or manipulate trades. EVER. |
| 8 | **Constitution is Law** | No code change may contradict this document. If a contradiction is needed, update this document FIRST with a maintenance log entry, THEN write the code. |

---

## 2. 📐 Modularity Laws (Enforced File Structure)

### 2.1 Backend Modularity

`backend/main.py` is the **app entry point ONLY**. It must contain:
- FastAPI app creation + middleware
- `lifespan` / startup hooks that wire together modules
- Route registrations (via `app.include_router` or thin `@app.get` calls that delegate immediately)

**NOTHING ELSE.** All logic lives in purpose-built modules:

```
backend/
  main.py            # app factory + lifespan ONLY (target: <200 lines)
  constants.py       # all tunables (centralized constants rule)
  market.py          # _now_et, _in_premarket, _in_market_hours, _get_mode
  alpaca.py          # _alpaca_headers, _env, all Alpaca REST + WS client calls
  cache.py           # shared in-memory cache dicts, TTL helpers, invalidation
  scanner.py         # gapper / gainer / loser discovery and scoring logic
  news.py            # news-catalyst fetch, dedup, scoring
  fundamentals.py    # yfinance fetch + TTL cache wrapper
  websocket.py       # WS connection manager, subscription state, streaming loop
  hod_momo.py        # HOD Momo engine
  hod_momo_enrichment.py  # HOD Momo enrichment pipeline
  bars.py            # bar data fetching
  routes/
    health.py        # /health endpoint
    scan.py          # /gappers, /gainers, /losers endpoints
    ticker.py        # /ticker/{symbol} + ticker detail WS
    settings.py      # /settings GET/POST
```

### 2.2 Frontend Modularity

`frontend/src/App.tsx` is the **root layout + router ONLY**. It must contain:
- Provider wrappers, theme, top-level layout shell
- Route definitions that delegate to page-level components

**NOTHING ELSE.** All logic lives in purpose-built modules:

```
frontend/src/
  App.tsx             # root layout + router ONLY (target: <150 lines)
  main.tsx            # entry point
  constants.ts        # all tunables
  index.css           # global styles + design tokens
  App.css             # app-specific styles
  debug.ts            # debug utilities
  components/         # reusable UI components
    GapperTable.tsx
    GainerTable.tsx
    LoserTable.tsx
    NewsCatalystPanel.tsx
    TickerDetail.tsx
    SettingsPanel.tsx
    HealthBadge.tsx
    ...
  hooks/              # custom React hooks
    useWebSocket.ts
    useGappers.ts
    useGainers.ts
    useTicker.ts
    ...
  pages/              # page-level components (one per tab/view)
    DashboardPage.tsx
    SettingsPage.tsx
    ...
  types/              # shared TypeScript types
    scanner.ts
    ticker.ts
    ...
  hod_momo/           # HOD Momo feature module (already modular ✅)
```

### 2.3 File Size Limits

| File | Current | Target | Status |
|------|---------|--------|--------|
| `backend/main.py` | ~1,757 lines | <200 lines | ❌ VIOLATION |
| `frontend/src/App.tsx` | ~1,471 lines | <150 lines | ❌ VIOLATION |
| `frontend/src/index.css` | ~41,050 bytes | Split if >1000 lines | ⚠️ Monitor |
| Any new module | — | <400 lines | Enforced |

**Rule:** No single file may exceed 400 lines for new code. Existing violations must be addressed when any task touches the violating file.

### 2.4 Refactoring Protocol

When touching ANY function currently in a monolith file:
1. **Move** it to the correct module (see layout above).
2. **Import** it back in the original file if still referenced there.
3. **Do NOT leave the old copy** in the monolith.
4. **Update all callers** in the same commit.
5. **Never make a monolith worse.** If you're adding to `main.py` or `App.tsx`, extract first.

---

## 3. 📐 Data Schema (Confirmed)

### Input Payload (Raw)
```json
{
  "symbol": "AAPL",
  "previous_close": 150.00,
  "current_price": 155.00,
  "gap_percent": 3.33,
  "volume": 1200000,
  "timestamp": "2026-04-14T08:30:00Z"
}
```

### Output / Delivery Payload
```json
{
  "health": {
    "status": "connected",
    "latency_ms": 45
  },
  "gappers": [
    {
      "symbol": "AAPL",
      "previous_close": 150.00,
      "current_price": 155.00,
      "gap_percent": 3.33,
      "volume": 1200000
    }
  ]
}
```

---

## 4. 🔗 Integrations & Services

| Service | Purpose | Status |
|---------|---------|--------|
| Alpaca API | Source of truth for market data | ✅ Verified |
| Web UI (Localhost) | Delivery dashboard for gappers | ✅ Verified |
| yfinance | Fundamental data (float, short interest, etc.) | ✅ Verified |
| Railway | Cloud deployment | ✅ Verified |

---

## 5. 📋 Behavioral Rules (Enforced)

- **Read-Only Mode**: The system only reads market data from API and does not execute or manipulate trades.
- **Market Open Halt**: The gapper dashboard stops updating its data feed once the market formally opens.
- **Configurable**: API keys and base URLs must be configurable via UI.
- **Git Commit & Push After Every Task**: After completing any task, the assistant MUST run `git add .`, `git commit -m "<descriptive message>"`, and `git push origin master`. No exceptions — the user should never have to remind this.

---

## 6. 🔧 Coding Standards (Enforced)

### 6.1 Constants Policy
- **ALL** configuration values live in `backend/constants.py` or `frontend/src/constants.ts`.
- No magic numbers. No inline strings. Import from the constants file.
- Both files stay in sync for shared values.
- New constants go in the constants file FIRST, before the logic that uses them.
- Environment variable overrides are permitted, but the default MUST come from the constants file.

### 6.2 Naming
- Python: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants.
- TypeScript: `camelCase` for functions/variables, `PascalCase` for components/types, `UPPER_SNAKE` for constants.
- Files: `snake_case.py` for Python, `PascalCase.tsx` for React components, `camelCase.ts` for utilities.

### 6.3 Error Handling
- Use structured logging (`logging.getLogger(__name__)`) in Python.
- Never swallow exceptions silently — at minimum log a warning.
- Frontend: surface errors in UI debug panels, not just console.

### 6.4 Testing
- Backend: pytest for API behavior and pure Python logic.
- Frontend: Vitest + React Testing Library.
- New modules should include at least a minimal test.

### 6.5 Dependencies
- Python: pinned in `requirements.txt`.
- Node: `package-lock.json` committed, use `npm ci` in CI.

### 6.6 Secrets & Security
- Never commit secrets, API keys, or full `.env` files.
- No secrets in log messages.
- Use `.env.example` for documented safe examples.

---

## 7. 📝 Documentation Requirements (Enforced)

### 7.1 CHANGELOG.md
- Prepend entry after any task that changes behavior, endpoints, module boundaries, constants, build config, rules, or UI behavior.
- Entry ships in the SAME commit as the code it describes.
- Use the template in `CHANGELOG.md`.

### 7.2 PROBLEM_LOG.md
- Prepend entry after fixing any build/test/linter failure, runtime error, incorrect behavior, or subtle root cause.
- Use the template in `PROBLEM_LOG.md` (Symptom, Cause, Fix, Keywords).

### 7.3 .cursor/rules/
- MDC rules are peers of this constitution. They provide fine-grained, glob-scoped enforcement.
- When logic changes, update or add the relevant MDC rule BEFORE writing code.

---

## 8. 🚀 Run & Deploy

### Local Dev (Windows)
```
# From repo root:
Run Stock Alert.bat

# Or manually:
# Terminal A (backend/): py -3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
# Terminal B (frontend/): npm run dev
# Open: http://localhost:5173
```

### Deploy (Railway)
- Backend: auto-deploys from `master` branch.
- Frontend: Vite build, served via Vercel or Railway static.

---

## 9. 🔄 Self-Annealing Protocol

When ANY error occurs during a task:
1. **STOP** — Do not apply a band-aid.
2. **Analyze** — Read `PROBLEM_LOG.md` for prior matching entries.
3. **Root Cause** — Identify the actual cause, not the symptom.
4. **Patch** — Fix the root cause in the correct module (not in `main.py`).
5. **Test** — Verify the fix works (build, run, or test).
6. **Update SOP** — Add entry to `PROBLEM_LOG.md` and update relevant MDC rule if needed.
7. **Commit** — `git add . && git commit -m "<msg>" && git push origin master`.

---

## 10. 🚨 Compliance Audit (Current Violations)

| Violation | Severity | Rule Violated | Status |
|-----------|----------|---------------|--------|
| `backend/main.py` is 1,757 lines | 🔴 Critical | §2.1, §2.3 | Must fix on next backend task |
| `frontend/src/App.tsx` is 1,471 lines | 🔴 Critical | §2.2, §2.3 | Must fix on next frontend task |
| No `architecture/` directory exists | 🟡 Warning | §1.5 | Create when needed |
| No automated tests exist | 🟡 Warning | §6.4 | Add incrementally |

---

## 11. 🔧 Maintenance Log

| Date | Change | Author |
|------|--------|--------|
| 2026-04-27 | Complete constitution rewrite — added modularity laws, file limits, compliance audit, self-annealing protocol, coding standards | Antigravity + User Directive |
| 2026-04-27 | Added mandatory git commit & push rule | User Directive |
| 2026-04-13 | Project Constitution initialized | System Pilot |


---

## 12. 📜 Cursor Rules (.mdc files)

The following rules are imported from .cursor/rules and MUST be followed by all agents:


### Rule: backend-modularity.mdc
```markdown
---
description: Enforce modular design in the backend — no logic dumped into main.py
globs: backend/**/*.py
alwaysApply: true
---

# Backend Modularity Policy

`backend/main.py` is the **app entry point only**. It must contain nothing but:
- FastAPI app creation + middleware
- `lifespan` / startup hooks that wire together modules
- Route registrations (via `app.include_router` or thin `@app.get` calls that delegate immediately)

Everything else lives in a purpose-built module. When adding or refactoring code, always place it in the correct module below.

## Module Layout

```
backend/
  main.py            # app factory + lifespan only
  constants.py       # all tunables (see centralized-constants rule)
  market.py          # _now_et, _in_premarket, _in_market_hours, _get_mode
  alpaca.py          # _alpaca_headers, _env, all Alpaca REST + WS client calls
  cache.py           # shared in-memory cache dicts, TTL helpers, invalidation
  scanner.py         # gapper / gainer / loser discovery and scoring logic
  news.py            # news-catalyst fetch, dedup, scoring
  fundamentals.py    # yfinance fetch + TTL cache wrapper
  websocket.py       # WS connection manager, subscription state, streaming loop
  routes/
    health.py        # /health endpoint
    scan.py          # /gappers, /gainers, /losers endpoints
    ticker.py        # /ticker/{symbol} + ticker detail WS
    settings.py      # /settings GET/POST
```

## Rules

1. **Never add a function to `main.py`** unless it is a `@app.on_event` / lifespan hook or a one-liner route that calls an imported function.

2. **Each module owns its state.** Module-level globals (caches, flags) live in the module that reads/writes them. `main.py` must not declare any `_*` globals.

3. **Cross-module calls go through imports, not globals.** If `scanner.py` needs a cache, it imports it from `cache.py`. Do not pass state through `main.py` as a middleman.

4. **Route handlers are thin.** A route handler calls one service function and returns its result. Business logic (filtering, scoring, enrichment) belongs in `scanner.py`, `news.py`, etc.

5. **New features = new module or clear extension of an existing one.** Do not add a new domain (e.g. alerts, watchlist) to an existing module; create `alerts.py` instead.

## Bad vs Good

```python
# ❌ BAD — logic piled into main.py
@app.get("/gappers")
async def get_gappers():
    symbols = _fetch_assets()          # defined 300 lines above in same file
    filtered = [s for s in symbols if _score(s) > _MIN_GAP_PCT]
    ...

# ✅ GOOD — main.py delegates
from routes.scan import router as scan_router
app.include_router(scan_router)

# routes/scan.py
from scanner import get_gappers
@router.get("/gappers")
async def get_gappers_route():
    return await get_gappers()
```

## Refactoring Existing Code

When touching any function currently in `main.py`:
1. Move it to the correct module (see layout above).
2. Import it back in `main.py` if still referenced there.
3. Do not leave the old copy in `main.py`.
4. Update all callers in the same PR/commit.

```

### Rule: centralized-constants.mdc
```markdown
---
description: Enforce centralized constants policy for B.L.A.S.T.
globs:
  - "backend/**/*.py"
  - "frontend/src/**/*.ts"
  - "frontend/src/**/*.tsx"
alwaysApply: true
---

# Centralized Constants Policy

All configuration values in this project — thresholds, filters, regex patterns, keyword lists, intervals, counts, and any other named constant — **must** be defined in one of the two authoritative constants files:

- **Backend:** `backend/constants.py`
- **Frontend:** `frontend/src/constants.ts`

## Rules

1. **No magic numbers or inline strings in `main.py` or `App.tsx`.** If a value has a name or meaning, it belongs in the constants file and must be imported.

2. **Import, don't re-declare.** Never copy a value from constants and redefine it in another file. Always import it directly.

3. **Both files stay in sync** for values shared between backend and frontend (e.g. `GAPPER_MIN_GAP_PCT`, market-cap tiers). The frontend `constants.ts` comment block must note when a value mirrors a backend constant.

4. **New constants go in the constants file first.** When adding a feature, define all its tunable values in `constants.py` / `constants.ts` before writing the logic that uses them.

5. **Environment variable overrides** are permitted in `main.py` for ops-level tuning (e.g. `_MIN_GAP_PCT = float(os.environ.get("BLAST_MIN_GAP_PCT", str(GAPPER_MIN_GAP_PCT)))`), but the **default value** must still come from `constants.py` — never a bare literal.

## What belongs in constants

- Gap percentage floors and thresholds
- Exchange filter lists (`SCAN_EXCHANGES`)
- Symbol exclusion regex patterns (`SYMBOL_EXCLUDE_RE`)
- ETF / non-equity name keyword lists (`ETF_NAME_KEYWORDS`)
- Scan intervals (discovery, focus, gainers, catalyst, closed)
- Cache TTLs
- Top-N limits
- Market cap tier boundaries
- News flame hour thresholds
- Relative volume highlight thresholds
- Any future filter, tier, or tunable value

## What does NOT belong in constants

- Runtime state (caches, timestamps, flags)
- API URLs derived from environment variables
- One-off computed values used only within a single function

```

### Rule: change-log.mdc
```markdown
---
description: Maintain CHANGELOG.md with a human-readable summary after every task
alwaysApply: true
---

# Change log — summarize every task

The repo root file `CHANGELOG.md` is a **shared narrative** of what changed in this project and **why**. It exists so future agent and human sessions can get oriented in minutes without reading diffs or digging through files.

This rule is a peer of `problem-log.mdc` and `commit-after-tasks.mdc`. All three fire at task completion.

## When to add an entry

Prepend a new entry after completing any task that changes:

- Code behavior, logic, or control flow
- Public API shapes, endpoints, or WebSocket payloads
- Module boundaries or the file layout in `backend-modularity.mdc`
- Constants in `backend/constants.py` or `frontend/src/constants.ts`
- Build, run, CI, dependencies, or deployment config
- Rules in `.cursor/rules/` or top-level docs that agents rely on
- User-visible UI behavior or copy

**Skip** entries only for: pure typo fixes, formatting-only edits, scratch files under `backend/logs/` or `backend/.cache/`, or edits to generated artifacts.

## Where and how

1. Open `CHANGELOG.md`.
2. Prepend a new `##` section **immediately below** the `<!-- ENTRIES_START -->` marker (newest entries at the top — same convention as `PROBLEM_LOG.md`).
3. Fill in every field in the template that applies:

   ```markdown
   ## YYYY-MM-DD — Short descriptive title

   - **What:** 1–2 sentences on what changed (user-visible + internal).
   - **Why:** Trigger for the change (user request, bug, performance, cleanup).
   - **Files touched:** Key files only.
   - **How it works now:** The mental model a future agent needs.
   - **Verified by:** How you confirmed it works (built + ran, test, click path).
   - **Follow-ups:** (optional) anything deferred.
   - **Related:** (optional) commit SHA, PROBLEM_LOG date, issue link.
   ```

4. Keep each field to a few lines. The **"How it works now"** field matters most — write it for a cold agent re-entering the repo.

## Relationship to PROBLEM_LOG.md

- `CHANGELOG.md` = "what does the codebase do now and why" (every non-trivial task).
- `PROBLEM_LOG.md` = "what went wrong and how was it fixed" (bugs, failures, subtle root causes only — see `problem-log.mdc`).
- When a task is a bug fix, write **both**, and cross-reference in the `Related` field.

## Commit discipline

- The changelog entry must ship in the **same commit** as the code it describes. Never push code without the matching entry.
- Task completion is **not** complete until the entry exists. This rule runs alongside `commit-after-tasks.mdc`: write entry → stage all → commit → push.

## Content guardrails

- No secrets, tokens, API keys, or personal data in entries.
- No verbatim stack traces longer than one line (summarize).
- If an entry would duplicate an existing recent one, extend the existing entry's fields instead of creating a near-identical new one.

```

### Rule: commit-after-tasks.mdc
```markdown
---
description: After each completed task, commit and push to GitHub
alwaysApply: true
---

# Commit and push after tasks

When you finish a task that touched the codebase or project files:

1. **Build and run** — Follow the project’s normal build/run steps (see existing user or project rules) so the change is verified before publishing.
2. **Commit** — Stage only intentional changes. Use a clear, imperative subject line (and optional body) that states what changed and why. Do not commit secrets, local env files, or generated artifacts you would not want on GitHub.
3. **Push** — Push to `origin` on the current branch (e.g. `git push -u origin HEAD` when upstream is missing).

If there is nothing new to commit, say so briefly. If `git push` fails (auth, network, conflicts), report the error and what the user should do; do not claim the push succeeded.

This applies at **task completion** — after the requested work is done and validated, not after every tiny intermediate edit.

```

### Rule: constitution.mdc
```markdown
---
description: Master governance rule — read gemini.md before any code change
globs: "**/*"
alwaysApply: true
---

# Constitution Governance

Before writing ANY code in this project, you MUST:

1. **Read `gemini.md`** in the repo root. It is the project constitution.
2. **Follow ALL rules** defined there. They override your default behavior.
3. **Check `.cursor/rules/`** for fine-grained, glob-scoped policies.
4. **Never violate modularity.** Do not add logic to `main.py` or `App.tsx`. Extract to modules.
5. **Never violate file size limits.** No file > 400 lines for new code.
6. **Log your work.** Update `CHANGELOG.md` and `PROBLEM_LOG.md` as required.
7. **Commit and push** at the end of every task. `git add . && git commit -m "<msg>" && git push origin master`.

## Rule Hierarchy (highest to lowest)

1. `gemini.md` — Project Constitution (supreme law)
2. `.cursor/rules/*.mdc` — Fine-grained enforcement policies
3. Agent system prompts — Default AI behavior (overridden by above)

## Quick Reference: Common Violations to Avoid

- ❌ Adding a function to `backend/main.py` → put it in the correct module
- ❌ Adding a component to `frontend/src/App.tsx` → put it in `components/`
- ❌ Hardcoding a number or string → put it in `constants.py` / `constants.ts`
- ❌ Forgetting to commit and push → always run git add/commit/push
- ❌ Forgetting CHANGELOG.md → entry required for every behavior change
- ❌ Swallowing an error silently → log it, fix root cause, update PROBLEM_LOG.md

```

### Rule: engineering-standards.mdc
```markdown
---
description: Scale-ready engineering — Tailwind direction, tests, CI, deps, observability
alwaysApply: true
---

# Engineering standards (scale readiness)

This project is expected to grow. Agents and contributors should align new work with these policies alongside `centralized-constants.mdc`, `backend-modularity.mdc`, and `commit-after-tasks.mdc`.

## Styling: shift toward Tailwind (incremental)

- **Direction:** Prefer **Tailwind CSS** for new UI and for refactors that touch layout or styling, **once** Tailwind is installed and wired in the frontend (official Vite integration or PostCSS, per current Tailwind docs). Until that wiring exists, keep using `frontend/src/index.css` and existing class names.
- **Coexistence:** Do not rip out global CSS or `:root` design tokens in one change. Tailwind should **map to the same visual system**: extend Tailwind theme (or `@theme` in v4) so colors, spacing, and typography stay consistent with existing CSS variables and with **`frontend/src/constants.ts`** for any named tunables shared across the app.
- **Constants:** Tunable thresholds, tiers, and product-level numbers still belong in **`constants.ts` / `constants.py`**, not as unexplained literals in `className` strings. If a value is purely presentational and comes only from the design scale, Tailwind utilities are fine.
- **Components:** Prefer small reusable React components over pasting the same long utility string everywhere. Use `@apply` sparingly; favor utilities in JSX or a thin wrapper component.

## Automated testing (grow with the code)

- **Backend:** Use **pytest** for API behavior and pure Python logic. When changing behavior under `backend/`, add or update tests that cover the change when the change is non-trivial.
- **Frontend:** Use **Vitest** (and **React Testing Library** for components) for logic and regressions; add tests when introducing or fixing non-trivial UI behavior.
- **Bar:** New modules or risky changes should include at least a **minimal** test (happy path or one critical edge case) rather than shipping untested core paths.

## CI and quality gates

- When CI exists (lint, test, build), task completion means **keeping the pipeline green**. Do not leave the repo in a state with known failing checks unless the task explicitly documents a follow-up and scope.
- **Python:** Prefer **Ruff** for lint/format when the project adopts it. **Frontend:** follow existing **ESLint** configuration.

## Dependencies (reproducible installs)

- **Python:** Prefer **pinned** or lockfile-based dependencies (e.g. `uv` lock, Poetry, or `pip-tools` with a compiled requirements file) instead of loose, unpinned packages in `requirements.txt`. When adding or upgrading dependencies, move toward reproducible installs.
- **Node:** Keep the lockfile (**`package-lock.json`**) committed; use **`npm ci`** in automation when that is the project standard.

## Observability and secrets

- Backend changes should use **clear, structured logging** suitable for production debugging (no secrets or tokens in log messages).
- Never commit secrets, API keys, or full `.env` files; use environment variables and documented safe examples only.

## Cross-references

- **Constants:** `centralized-constants.mdc`
- **Backend layout:** `backend-modularity.mdc`
- **Incidents:** prepend to `PROBLEM_LOG.md` when resolving non-trivial bugs (see `problem-log.mdc`)

```

### Rule: file-size-limits.mdc
```markdown
---
description: Enforce maximum file size limits to prevent monolith files
globs:
  - "backend/**/*.py"
  - "frontend/src/**/*.ts"
  - "frontend/src/**/*.tsx"
alwaysApply: true
---

# File Size Limits

No single source file may grow beyond the limits below. When a file approaches or exceeds its limit, the agent MUST refactor before adding more code.

## Limits

| File Category | Max Lines | Action |
|---------------|-----------|--------|
| `backend/main.py` | 200 | Extract logic to modules |
| `frontend/src/App.tsx` | 150 | Extract to components/pages |
| Any new Python module | 400 | Split into sub-modules |
| Any new React component | 300 | Break into child components |
| Any new TypeScript file | 400 | Split into focused modules |

## Enforcement

1. **Before adding code to ANY file**, check its current line count.
2. If the file is at or above its limit, **extract first, add second.**
3. If you are creating a new file and it will exceed 400 lines, design it as multiple files from the start.
4. **Never make a monolith worse.** If touching a file that already violates limits, extract at least one function/component to its correct module before adding new code.

## Known Violations (must be addressed incrementally)

- `backend/main.py` (~1,757 lines → target 200) — extract on every backend task
- `frontend/src/App.tsx` (~1,471 lines → target 150) — extract on every frontend task

```

### Rule: frontend-modularity.mdc
```markdown
---
description: Enforce modular design in the frontend — no logic dumped into App.tsx
globs: frontend/src/**/*.{ts,tsx}
alwaysApply: true
---

# Frontend Modularity Policy

`frontend/src/App.tsx` is the **root layout + router ONLY**. It must contain nothing but:
- Provider wrappers (Theme, Context, etc.)
- Top-level layout shell (header, sidebar skeleton, tab container)
- Route/tab definitions that delegate to page-level components

Everything else lives in a purpose-built module. When adding or refactoring code, always place it in the correct module.

## Module Layout

```
frontend/src/
  App.tsx             # root layout + router ONLY (target: <150 lines)
  main.tsx            # entry point
  constants.ts        # all tunables
  index.css           # global styles + design tokens
  App.css             # app-specific styles
  components/         # reusable UI components
    GapperTable.tsx
    GainerTable.tsx
    LoserTable.tsx
    NewsCatalystPanel.tsx
    TickerDetail.tsx
    SettingsPanel.tsx
    HealthBadge.tsx
  hooks/              # custom React hooks
    useWebSocket.ts
    useGappers.ts
    useGainers.ts
    useTicker.ts
  pages/              # page-level components (one per tab/view)
    DashboardPage.tsx
    SettingsPage.tsx
  types/              # shared TypeScript types
    scanner.ts
    ticker.ts
  hod_momo/           # HOD Momo feature module (already modular ✅)
```

## Rules

1. **Never add a component, hook, or utility function to `App.tsx`** unless it is purely a layout wrapper or tab-switch handler.

2. **Each module owns its state.** Component-level state lives in the component. Shared state lives in a custom hook or context. `App.tsx` must not declare business logic state.

3. **Cross-component communication goes through hooks or context, not prop drilling through App.tsx.** If a child needs data, it imports a hook. Do not pass data through App.tsx as a middleman.

4. **Components are focused and reusable.** Each `.tsx` file = one component. One concern per file. If a component exceeds 300 lines, break it up.

5. **New features = new component or new hook.** Do not add a new domain (e.g. watchlist, alerts UI) into an existing component; create a new file.

6. **Types live in `types/`.** Shared interfaces and type definitions must not be inline in components. Define them in a dedicated types file.

## Bad vs Good

```typescript
// ❌ BAD — 1500-line App.tsx with everything inline
function App() {
  const [gappers, setGappers] = useState([]);
  const [gainers, setGainers] = useState([]);
  // ... 1400 more lines of inline logic and JSX
}

// ✅ GOOD — App.tsx delegates to focused components
function App() {
  return (
    <ThemeProvider>
      <Layout>
        <TabRouter
          tabs={[
            { id: 'gappers', label: 'Gappers', component: <GappersPage /> },
            { id: 'gainers', label: 'Gainers', component: <GainersPage /> },
          ]}
        />
      </Layout>
    </ThemeProvider>
  );
}
```

## Refactoring Existing Code

When touching any component or logic currently in `App.tsx`:
1. Extract it to a new component in `components/` or a hook in `hooks/`.
2. Import it back in `App.tsx` if still referenced there.
3. Do not leave the old copy in `App.tsx`.
4. Update all callers in the same commit.

```

### Rule: problem-log.mdc
```markdown
---
description: Maintain PROBLEM_LOG.md when fixing errors or diagnosing issues
alwaysApply: true
---

# Problem log — append resolved issues

The repo root file `PROBLEM_LOG.md` is a **problem database** for future agent and human sessions.

## Before deep debugging

When the task involves an error, failing check, or wrong behavior, **search `PROBLEM_LOG.md`** (and the codebase) for matching keywords or symptoms. If a prior entry fits, reuse that fix pattern when appropriate.

## After fixing or fully diagnosing

When this session **resolves** any of the following, **prepend a new entry** to `PROBLEM_LOG.md` (newest first, directly under the `<!-- ENTRIES_START -->` line):

- Build, test, or linter failure
- Runtime or API error
- Incorrect behavior that required code or config changes
- A subtle root cause that would not be obvious on the next occurrence

**Skip** logging only for purely cosmetic edits with no failure involved, or a one-line typo with no diagnostic story.

Each entry must use the template in `PROBLEM_LOG.md` (Symptom, Cause, Fix, Keywords). Do not log secrets, tokens, or personal data.

This is part of **task completion**: add the log entry in the same session as the fix when practical, before or alongside commit.

```

### Rule: run-app.mdc
```markdown
---
description: How to run Stock Alert and what to do when the user says "run the app"
alwaysApply: true
---

# Run Stock Alert (local dev)

## Default way to open the app (Windows)

From the **repository root** (`stock_alert/`):

1. **Double-click** `Run Stock Alert.bat`, **or** in a terminal: run `Run Stock Alert.bat` from that folder.

That script:

- Starts the **API** in a titled window: FastAPI at `http://127.0.0.1:8000` (`uvicorn main:app --reload` in `backend/`).
- Starts the **UI** in another window: Vite dev server at `http://localhost:5173` (`npm run dev` in `frontend/`).
- Opens the browser to the UI after a short delay.

Close each titled CMD window to stop that server.

**Prerequisites:** Python with `py` launcher (or `python` on PATH), `backend` dependencies available for uvicorn; Node/npm in `frontend` (run `npm install` in `frontend/` once if needed).

## Manual equivalent (if not using the batch file)

- Terminal A, repo `backend/`: `py -3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000` (or `python -m uvicorn ...`).
- Terminal B, repo `frontend/`: `npm run dev`.
- Open `http://localhost:5173` in the browser.

## Agent behavior: "run the app" / "open the app"

When the user asks to **run** or **open** the app (or similar), **do it without debating**:

1. Prefer **starting from repo root** using `Run Stock Alert.bat` on Windows when an interactive dev experience (separate windows + browser) matches what they use day to day.
2. If the environment cannot launch `.bat` or needs headless terminals, start **both** servers the same way the batch file does: uvicorn in `backend/` and `npm run dev` in `frontend/` (background as appropriate), then note URLs `http://127.0.0.1:8000` and `http://localhost:5173`.

Do not spend turns listing options unless something fails; execute first, then report URLs and how to stop.

```

### Rule: self-annealing.mdc
```markdown
---
description: Self-annealing error protocol — never band-aid, always root-cause fix
alwaysApply: true
---

# Self-Annealing Protocol

When ANY error occurs during a task — build failure, runtime exception, incorrect behavior, test failure — follow this protocol without exception:

## Steps

1. **STOP** — Do not apply a quick band-aid or workaround.
2. **Search** — Check `PROBLEM_LOG.md` for prior matching entries by symptom or keyword.
3. **Analyze** — Identify the ROOT CAUSE, not the symptom. Read the actual error, trace the call stack, check the code.
4. **Patch** — Fix the root cause in the CORRECT MODULE (not in `main.py` or `App.tsx`).
5. **Test** — Verify the fix works (build, run, test, or manual verification).
6. **Document** — Add entry to `PROBLEM_LOG.md` using the template (Symptom, Cause, Fix, Keywords).
7. **Update SOP** — If the error reveals a gap in rules, update the relevant `.cursor/rules/*.mdc` file or `gemini.md`.
8. **Commit** — Ship the fix, the log entry, and any rule updates in the same commit.

## Anti-Patterns (NEVER do these)

- ❌ Catching an exception and silently ignoring it
- ❌ Adding a `try/except: pass` to make an error disappear
- ❌ Fixing the symptom without understanding the cause
- ❌ Applying a fix in `main.py` when the bug is in a module
- ❌ Skipping the PROBLEM_LOG entry because the fix was "obvious"
- ❌ Moving on without verifying the fix actually works

```

## ?? Karpathy Behavioral Guidelines
This project strictly enforces the Andrej Karpathy LLM principles to prevent common AI coding mistakes.
1. **Think Before Coding**: State assumptions, present tradeoffs, stop if confused.
2. **Simplicity First**: Write minimum viable code. No speculative abstractions.
3. **Surgical Changes**: Touch only requested lines. Leave unrelated code untouched.
4. **Goal-Driven Execution**: Define verifiable success criteria and loop until verified.

Before working on this project, ensure you adhere to these rules.

## Web Verification & Browser Testing
- **Web Verification**: At the end of every task involving web deployments or changes, agents MUST open a headless browser (using `agent-browser` or Playwright) and test the actual live subdomain URL (not localhost) to ensure it loads successfully and functions correctly before declaring the task complete.
- **Local Browser CDP**: Use `c:\Users\aalta\anaconda3\python.exe "c:\Users\aalta\github\AhmiOS\local-browser-skill\security_prompt.py"` before connecting to Edge (`9223`) or Chrome (`9222`) via CDP.
- **Agent Browser CLI**: Use `npx agent-browser@latest` for fast, lightweight interaction.
