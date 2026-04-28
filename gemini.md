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
