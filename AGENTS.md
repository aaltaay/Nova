# 🏛️ AGENTS.md — Project Constitution (Law)

> **Single source of truth.** `gemini.md` is a legacy alias that `@`-imports this file (consolidated 2026-07-28 after the two mirrors drifted).
>
> **Status:** ENFORCED — Active governance document
> **Last Updated:** 2026-09-11
> **Project:** Nova — Stock Alert Automation System
> **Enforcement:** Every AI agent (Cursor, Antigravity, any LLM assistant) MUST read this file before writing ANY code. Violations are NEVER acceptable.

---

## 0. PURPOSE

This document is the **single source of truth** for how this project is built, maintained, and extended. It exists because:

1. AI assistants lose context between sessions.
2. Without rules, assistants dump everything into monoliths.
3. The user has explicitly mandated modular, disciplined engineering.

**If a rule here conflicts with an agent's default behavior, this document wins.**

### Master Roadmap (product phases)

- **Canonical ledger:** `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md` — which phase is NEXT, checkboxes, History.
- **Target architecture (maintenance):** `architecture/README.md` + `architecture/dependency-rules.md` + ADRs under `architecture/decisions/` — modular monolith, selective ports/adapters, feature slices, CSS cascade layers. Structural moves must cite an ADR.
- **Continuity rule:** `.cursor/rules/nova-roadmap-continuity.mdc` — read status first; phase-close verify + CHANGELOG + commit + push; scope guard.
- **Phase B ops:** `docs/paper-shadow-protocol.md` — paper shadow (`signal` → `confirm` → `auto_paper`); **`auto_live` NO-GO**.
- **Plan / canvas:** `nova_master_roadmap_a_z.plan.md` · `nova-home.canvas.tsx`
- **Nova OS engine map (closed):** `knowledge/obsidian/03-Nova-Decisions/Nova-OS-Status.md` — still authoritative for P0–P10 internals; product “what’s next” is Roadmap-Status.
- **Docs (docs + canvases):** `.cursor/agents/docs.md` — documentation steward; memory in `.cursor/agent-memory/`; dashboard is Nova Home; preferred canvases `nova-home` + `agent-*` (+ Cursor `context-usage-*`). Continuity: `.cursor/rules/docs-continuity.mdc`. Agent OS: `.cursor/agent-system/` + `docs/agent-operations.md`.

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
| 6 | **Self-Annealing** | Any error -> Analyze -> Patch -> Test -> Update SOP/rules -> **MUST** log in `PROBLEM_LOG.md` (every agent; see `problem-log.mdc`). If the bug cannot be fixed this session (too big, wrong task, needs an ADR), **MUST** open or update a GitHub Issue labeled `deferred` instead of a band-aid (`deferred-log.mdc`). |
| 7 | **Broker Execution Gate** | Alpaca-sourced scanning is permanently read-only. Trade execution is permitted ONLY through the explicit opt-in `backend/ibkr/` module. Gateway connection default is **live** (port 4001); paper (4002) is the fallback when live is dark. Spending still requires `IBKR_ENABLED=true` and `IBKR_ORDERS_ENABLED=true`; live money also requires `IBKR_LIVE_TRADING_CONFIRMED=true` in `.env`. No other module may place orders. **Short entry (Phase K / ADR 009):** every SELL is risk-reducing unless an explicit `short_entry` opt-in on the execution command is approved by the short gate (`IBKR_SHORT_ENABLED=true` + fresh IBKR tick-236 `shortable_est`). Never infer shorts from side + flat position. `auto_live` remains NO-GO. |
| 8 | **Constitution is Law** | No code change may contradict this document. If a contradiction is needed, update this document FIRST with a maintenance log entry, THEN write the code. |

---

## 2. 📐 Modularity Laws (Enforced File Structure)

### 2.1 Backend Modularity

`backend/main.py` is the **app entry point ONLY**. It must contain:

- FastAPI app creation + middleware
- `lifespan` / startup hooks that wire together modules
- Route registrations (via `app.include_router` or thin `@app.get` calls that delegate immediately)

**NOTHING ELSE.** All logic lives in purpose-built modules:

```text
backend/
  main.py            # app factory + lifespan ONLY (target: <200 lines)
  constants.py       # all tunables (centralized constants rule)
  market.py          # _now_et, _in_premarket, _in_market_hours, _get_mode
  alpaca.py          # _alpaca_headers, _env, all Alpaca REST + WS client calls
  cache.py           # shared in-memory cache dicts, TTL helpers, invalidation
  scanner.py         # gapper / gainer / loser discovery and scoring logic
  news.py            # news fetch, dedup, scoring
  fundamentals.py    # yfinance fetch + TTL cache wrapper
  websocket.py       # WS connection manager, subscription state, streaming loop
  hod_momo.py        # HOD Momo engine: state, on_trade_update, config/blocklist CRUD, load_state
  hod_momo_models.py   # HOD Momo dataclasses + pure serialization + timestamp helpers
  hod_momo_filters.py  # HOD Momo pure per-strategy gate evaluation (no module state)
  hod_momo_debug.py    # HOD Momo pure debug-payload builders (no module state)
  hod_momo_metrics.py   # HOD Momo Warrior 5-min RVOL metrics
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

```text
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
| `backend/main.py` | 194 lines | <200 lines | ✅ Met (2026-07-14; CORS extraction 2026-07-15) |
| `frontend/src/App.tsx` | 73 lines | <150 lines | ✅ Met (2026-07-14) |
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

### Execution command (ADR 007 — sole broker mutation entry)

All buy/sell/cancel/replace requests enter `execution.service.execute` with:

```json
{
  "operation": "place | bracket | cancel | replace",
  "idempotency_key": "stable-client-or-ticket-key",
  "source": "manual | approve | auto_paper | kill | cancel_working | flatten | benchmark | bot",
  "symbol": "AAPL",
  "side": "BUY",
  "qty": 1,
  "order_type": "MKT",
  "limit_price": null,
  "stop_price": null,
  "target_price": null,
  "entry_price": null,
  "order_id": null,
  "short_entry": false
}
```

Receipt includes stage timings (`validation_ms`, `persisted_ms`, `broker_sent_ms`, `broker_ack_ms`, `filled_ms`).
Paper and live share this path; only Gateway credentials/port and safety gates differ. `auto_live` remains rejected. Short opening requires `short_entry: true` plus `IBKR_SHORT_ENABLED` and fresh IBKR shortability (ADR 009).

---

## 4. 🔗 Integrations & Services

| Service | Purpose | Status |
|---------|---------|--------|
| Alpaca API | News + listing metadata (not price discovery) | ✅ Verified |
| IB Gateway (local) | Scanner discovery + market data + optional orders | ✅ Verified |
| Web UI (Localhost / Desktop) | Delivery dashboard for gappers | ✅ Verified |
| yfinance | Fundamental data (float, short interest, etc.) | ✅ Verified |
| Vercel | Optional host for the `site/` marketing page (`nova.altaystudio.com`), not the live scanner | ✅ Optional |

---

## 5. 📋 Behavioral Rules (Enforced)

- **Market data / trading:** Scanner and prices are IBKR-only (see `single-market-data-feed.mdc`). Alpaca is news/listing metadata only. Orders are allowed only via gated `backend/ibkr/` (Invariant #7). Gateway port default is live (4001); paper (4002) is the fallback. Spend stays gated; `auto_live` remains NO-GO.
- **Market Open Halt**: The gapper dashboard stops updating its data feed once the market formally opens.
- **Configurable**: API keys and base URLs must be configurable via UI.
- **PR-first delivery after every task:** Code, config, CI, security, and rule changes MUST follow §5.1 (clean start from `origin/master`, ready PR finish line). Direct `master` pushes are limited to status-only operations or explicit user instruction. Complete `.github/pull_request_template.md`, link the issue truthfully (`Closes` only for full completion; `Refs` for partial work), verify, commit, push the branch, and open a **ready** (non-draft) PR. **GitHub Actions merges ready PRs** when gating CI is green (`tools/pr_delivery.py`). Do not wait for the human to say merge. Draft or label `do-not-merge` is the hold, and only under §5.1. After that PR is merged or closed, **delete the head branch** (`git fetch --prune` then `py -3 tools/stale_pr_branches.py`; `--delete` only if the head remains). GitHub `delete_branch_on_merge` plus `.github/workflows/pr-delivery.yml` are the backup sweep. Never leave merged or superseded branches on origin. Never delete `master` or a branch that still has an open PR. **Master branch protection** (no force-push, no deletion, required gating CI) is the required GitHub setting; verify with `py -3 tools/master_branch_protection.py check` and do not claim it exists unless that command exits 0. Public Nova unlocks that setting on GitHub Free. A private personal repo still needs GitHub Pro. The public source home is `aaltaay/Nova`. `aaltaay/Nova-public` is a private archive.
- **Nova Delivery board:** Canonical project is https://github.com/users/aaltaay/projects/1 (user project number `1`, owner `aaltaay`, id `PVT_kwHOAXJK5M4Ab7Vq`). Do not recreate it. `.github/workflows/nova-delivery-project.yml` adds new issues and same-repo PRs. Agents must also run `gh project item-add 1 --owner aaltaay --url <html_url>` when the token has `project` scope, and default Status to Todo unless already In Progress. Priority stays on labels `P0`..`P3`. Classic `GITHUB_TOKEN` and the Cloud Agent GitHub App typically lack `project` scope; owner `gh` as `aaltaay` can mutate; Actions uses repo secret `NOVA_PROJECT_TOKEN`. On 403, report the limitation -- never claim the item exists.
- **Co-Pilot Coaching Footer**: At the very end of every substantive reply, the assistant MUST append two short paragraphs, in this order (each max ~5 sentences, plain language):
  1. **Better ask:** -- honest feedback on how the user's request could have been asked better or clearer, plus one thing the user likely did not know. The goal is direct judgment that makes the user a better co-pilot, not flattery.
  2. **Follow-up ask:** -- one concrete, well-phrased follow-up question the user could ask next about this problem or answer (the natural next step), plus one sentence on why that follow-up is the highest-value one. Teach the shape of a good follow-up by example: reference the specific answer or artifact, narrow the scope, and state the decision it informs.

  Skip both only for trivial exchanges (one-word pings, tiny confirmations, pure status checks) at the assistant's judgement -- never pad a small answer with forced content.

### 5.1 Session lifecycle (Deliver)

These gates are **MUST**. They override casual phrasing such as "quick fix" or "just tweak." Only an **explicit** user override ("stay on this branch", "leave as draft", "commit locally only") can waive them. If work still ships, state that waiver in the PR body.

**A. Clean start -- before any edits**

1. `git fetch origin`.
2. Create or switch to a **new** focused branch from `origin/master` only. Never branch from a dirty local `master` tip. Never continue another feature branch unless the user explicitly names that branch.
3. If the worktree has uncommitted or unrelated dirty files: do **not** proceed on top of them. Reset or clean tracked files you do not own in this task so they match `origin/master`, or abort and report the dirty paths. Never "just keep working" on mixed dirty state.
4. Cloud and desktop agents: "isolated" means a clean tip of `origin/master` plus a new branch. Local dirty IDE state is not a valid base.

**B. Mandatory finish -- end of every coding session or task**

1. Verify (tests and build appropriate to the change).
2. Commit intentional changes on the focused branch.
3. Push the branch.
4. Open a **ready (non-draft)** PR targeting `master`, filled from `.github/pull_request_template.md`. Attach the issue/PR to [Nova Delivery](https://github.com/users/aaltaay/projects/1) when the token allows.
5. Draft or `do-not-merge` only when the user explicitly asked to hold, or a hard external blocker (for example, needs live IBKR proof) is documented in the PR -- not because CI is still running.
6. Do not end the session with only local commits, unpushed commits, or "I'll open the PR later." The PR URL is the finish line.
7. Keep existing rules: Actions auto-merge when available; `Closes` vs `Refs`; delete the head after merge or close; required checks unchanged.

Always-on copies: `.cursor/rules/commit-push-deploy.mdc`, `.cursor/rules/github-delivery.mdc`, `.cursor/skills/github-delivery/SKILL.md`.

---

## 6. 🔧 Coding Standards (Enforced)

### 6.1 Constants Policy

- **Authoritative values** live in backend domain modules (`constants_scanner.py`, `constants_hod_momo.py`, `constants_ibkr.py`, `constants_archive_news.py`, `constants_nova_os.py`) and frontend `constantGroups/` (or feature-local constants).
- `backend/constants.py` and `frontend/src/constants.ts` are **compatibility barrels** — re-exports only; do not add new definitions there.
- No magic numbers. No inline strings in `main.py` / `App.tsx`. Import from domain modules or barrels.
- Keep backend/frontend mirrors in sync for shared values.
- New constants go in the owning domain/feature module FIRST, then re-export from the barrel if needed.
- Environment variable overrides are permitted, but the default MUST come from a domain constants module.

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

- **Mandatory for every agent** (parent + all specialists). Rule: `.cursor/rules/problem-log.mdc`.
- Prepend entry after fixing any build/test/linter failure, runtime error, incorrect behavior, or subtle root cause — same session as the fix. Skipping after a real fix is a constitution violation.
- Use the template in `PROBLEM_LOG.md` (Symptom, Cause, Fix, Keywords).
- Lifecycle footer **MUST** include `problem_log=<YYYY-MM-DD title>|skipped|n/a`.

### 7.2b Task narrative (PR body first, `knowledge/task-log/` when there is no PR)

- Every completed material task (parent or specialist) needs a reasoning narrative. **Default home is the pull request body** -- fill `.github/pull_request_template.md`: What / Why this approach / Verified by / Related issue.
- No PR (direct push, ops diagnosis, audit conclusion)? Append a dated file under `knowledge/task-log/` and prepend `INDEX.md`. Scaffold: `py -3 tools/task_log_new.py --slug <kebab> --title "…"`.
- **Why this approach** is mandatory in either home -- capture tradeoffs and rejected alternatives, not only the diff. Never write both homes for one job.
- Rule: `.cursor/rules/task-log.mdc`.
- Lifecycle footer includes `task_log=<PR URL>|<path>|skipped|n/a`, `problem_log=<entry>|skipped|n/a`, and `deferred_log=<D-NNN>|none|skipped|n/a`.

### 7.2c Deferred tracker (GitHub Issues)

- **Mandatory for every agent** (parent + all specialists). Rule: `.cursor/rules/deferred-log.mdc`. Source of truth is GitHub Issues labeled `deferred` -- https://github.com/aaltaay/Nova/issues?q=is%3Aissue+label%3Adeferred . `DEFERRED_LOG.md` is the how-to, not the to-do.
- **Before any fix:** run `py -3 tools/deferred_log.py status` (alias `priorities`) and search open `deferred` issues. If a `D-NNN` already covers the ask, work from that issue (honor `parked` / Unblock / Next). Do not start a parallel fix that ignores it. When the human asks "what's on the to-do / what's missing / priorities," that command is the answer.
- Open (or comment on) a GitHub issue after parking a known bug or a feature you will not build this session -- same session, same severity as skipping PROBLEM_LOG after a real fix.
- Close an issue only when its entire stated scope is complete and verified. Partial fixes use `Refs #NNN`, get an evidence comment, and leave the issue open. Follow `.cursor/skills/github-delivery/SKILL.md` for owner, Project, Milestone, relationship, Development-link, and close-reason rules.
- Title contract: `D-NNN -- short title`. Labels: `deferred` + `P0`..`P3` + `bug`/`enhancement`/`decision` + `domain:<name>`. Body fields: Kind, Severity, Effort, Why parked, Blast radius, Unblock, Next, Evidence. Next ID: `py -3 tools/deferred_log.py next-id`. Refresh the offline index in the creating PR. When `Closes` auto-closes after merge, refresh it immediately in a status-only commit.
- Lifecycle footer **MUST** include `deferred_log=<D-NNN>|none|skipped|n/a`. Agent-memory Backlog is not the SSOT. Product-phase NEXT stays in `Nova-Roadmap-Status.md`.

### 7.3 .cursor/rules/

- MDC rules are peers of this constitution. They provide fine-grained, glob-scoped enforcement.
- When logic changes, update or add the relevant MDC rule BEFORE writing code.

---

## 8. 🚀 Run & Deploy

### Local Dev (Windows)

```text
# From repo root — browser UI:
Run Nova.bat

# Desktop (Electron + local API sidecar):
Run Nova Desktop.bat
# or: cd frontend && npm run electron:dev

# Windows installer:
cd frontend && npm run electron:pack

# Or manually:
# Terminal A (backend/): py -3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
# Terminal B (frontend/): npm run dev
# Open: http://localhost:5173
```

### Deploy

- **Backend:** local only right now -- no cloud host (not Railway, not another PaaS). Run via `Run Nova.bat`, Desktop sidecar, or local uvicorn on `127.0.0.1:8000`.
- **Public site:** `nova.altaystudio.com` is a static marketing page (`site/`) -- features, screenshots, and the [source](https://github.com/aaltaay/Nova) link. It is not the live scanner and has no API. Point the Vercel project Root Directory at `site`.
- **Frontend (app UI):** local Vite / Desktop only (`http://localhost:5173`). Do not host the trading SPA on the public domain.
- **Desktop:** Electron + local API sidecar. Local pack: `frontend/release/Nova-Setup-vNNN.exe` and `Nova-Portable-vNNN.exe`. Every PR must pass the `Desktop pack` GitHub Actions job, which uploads both EXEs. Merges to master/main create git tag `vNNN` and a GitHub Release that attaches those EXEs. GitHub's Source code zip/tar is automatic and is not the app.

---

## 9. 🔄 Self-Annealing Protocol

When ANY error occurs during a task:

1. **STOP** — Do not apply a band-aid.
2. **Analyze** -- Read `PROBLEM_LOG.md` *and* run `py -3 tools/deferred_log.py status` (GitHub Issues labeled `deferred`) for prior matching entries. If an open/parked `D-NNN` already covers it, work from that issue (or leave it parked) -- do not start a parallel fix.
3. **Root Cause** — Identify the actual cause, not the symptom.
4. **Patch** — Fix the root cause in the correct module (not in `main.py`).
5. **Test** — Verify the fix works (build, run, or test).
6. **Update SOP** -- Add entry to `PROBLEM_LOG.md` (if fixed) or open/update a GitHub Issue labeled `deferred` (if parked), and update relevant MDC rule if needed.
7. **Deliver** -- follow §5.1: verify, commit on the focused branch created from `origin/master`, push, and open a **ready (non-draft)** PR. The PR URL is the finish line. Use `Closes #NNN` only when the full issue is complete; otherwise use `Refs #NNN`. After the PR is merged or closed, confirm the head is gone (`stale_pr_branches.py`; `--delete` only if it remains).

---

## 10. 🚨 Compliance Audit (Current Violations)

No open constitution compliance rows. `architecture/` (ADRs 001–009) and automated tests (pytest + Vitest) exist. Product/security open work lives in `Nova-Roadmap-Status.md` and `Security-Status.md`. Live-doc drift is gated by `py -3 tools/doc_invariants.py` (CI).

---

## 11. 🔧 Maintenance Log

| Date | Change | Author |
|------|--------|--------|
| 2026-09-17 | ADR 007 source list gains `bot` (localhost bot API, ADR 016). Same execution door; L3 parked. | User Directive + Cursor Agent |
| 2026-09-11 | Nova Delivery board is https://github.com/users/aaltaay/projects/1. New issues/PRs auto-add via workflow; agents attach metadata; 403 is reported, never a new project. | User Directive + Cursor Agent |
| 2026-09-11 | Session lifecycle (§5.1): clean start from `origin/master`; every coding session MUST end with a ready (non-draft) PR. Casual "quick fix" phrasing does not waive. | User Directive + Cursor Agent |
| 2026-09-11 | Public source home is `aaltaay/Nova`. Marketing site CTA points here. `Nova-public` is a private archive. Master protection no longer blocked on "keep private." | User Directive + Cursor Agent |
| 2026-09-11 | GitHub Actions merges ready PRs and deletes closed heads (`pr_delivery.py`). Agents do not wait for a human merge ask. Master protection policy + apply tool also shipped. | User Directive + Cursor Agent |
| 2026-09-11 | Desktop pack builds NSIS installer + portable EXE. Master/main GitHub Release attaches both. Source zip/tar is not the app. | User Directive + Cursor Agent |
| 2026-09-11 | Desktop pack CI uploads `Nova-Setup-vNNN.exe` on every PR. Public revision is `vNNN` (commit count). Master/main creates git tag `vNNN` only. | User Directive + Cursor Agent |
| 2026-09-11 | GitHub `delete_branch_on_merge` is on. Agents still confirm the head is gone (`stale_pr_branches.py`) and `--delete` only if it remains. | User Directive + Cursor Agent |
| 2026-09-11 | After a PR is merged or closed, every agent must delete the head branch in the same session. `github-delivery.mdc` item 8 + `tools/stale_pr_branches.py`. | User Directive + Cursor Agent |
| 2026-09-10 | GitHub delivery is PR-first for code/config/CI/security/rules. Added complete-only issue closure plus conditional Project/Milestone/relationship metadata and strict quality gates through `github-delivery`. | User Directive + Cursor Agent |
| 2026-09-08 | Deferred tracker SSOT is GitHub Issues labeled `deferred`. `DEFERRED_LOG.md` is how-to only. Invariant #6, §7.2c, §9 updated. | User Directive + Cursor Agent |
| 2026-09-08 | Task narrative default home is the PR body (`.github/pull_request_template.md`: What / Why this approach / Verified by / Related issue); `knowledge/task-log/` covers no-PR work. Roadmap note trimmed to a status page (closed detail in `Nova-Roadmap-Archive.md`). §7.2b / §12 updated. | User Directive + Cursor Agent |
| 2026-09-08 | Deferred tracker is GitHub Issues labeled `deferred`; `DEFERRED_LOG.md` is how-to only. Invariant #6 / §7.2c / §9 updated. | User Directive + Cursor Agent |
| 2026-08-31 | Public domain is a marketing page (`site/` on Vercel). Live scanner stays local Vite / Desktop. §4 / §8 updated. | User Directive + Cursor Agent |
| 2026-08-31 | DEFERRED_LOG.md is the to-do / what's-missing list (`deferred_log.py status` / `priorities`); agents must search it before any fix; D-010 parked chart Trend Line. | User Directive + Cursor Agent |
| 2026-08-26 | DEFERRED_LOG.md: parked bugs/features with same respect as PROBLEM_LOG; Lifecycle `deferred_log=`; always-on `deferred-log.mdc`; session brief lists open P0/P1. | User Directive + Cursor Agent |
| 2026-08-25 | Graphify rule always-on; agents must use `tools/graphify_ask.py` (token-savings meter). Rebuild skill stays on-demand. | User Directive + Cursor Agent |
| 2026-08-18 | Gateway connection default is live (4001); paper (4002) is fallback. Invariant #7 and §5 updated -- spend gates unchanged; `auto_live` still NO-GO. | User Directive + Cursor Agent |
| 2026-08-06 | Engineering methodology graft: Superpowers verification/plan teeth + Addy interview/doubt/review as Nova-adapted skills + always-on MDCs; `tools/engineering_skills_audit.py`; domain constitution + zero-hop preserved. | User Directive + Cursor Agent |
| 2026-08-05 | Doc invariants: `tools/doc_invariants.py` + CI gate; §5 trading wording + §10 compliance table corrected; posture-change rule in `doc-invariants.mdc`. | User Directive + Cursor Agent |
| 2026-08-05 | Deploy truth: Railway retired from live docs. Backend is local-only (no cloud host); Vercel remains optional for static frontend only. §4 / §8 updated. | User Directive + Cursor Agent |
| 2026-07-29 | Token economy: §12 no longer embeds full .mdc copies (stale duplicates of live rules). Replaced with a compact index pointing at `.cursor/rules/*.mdc`. Attachment modes: always-on vs glob vs agent-requested. Do not create `.cursorrules`. | Cursor Agent |
| 2026-07-28 | Short-entry invariant (Phase K / ADR 009): Invariant #7 amended -- SELL is risk-reducing unless explicit `short_entry` + `IBKR_SHORT_ENABLED` + fresh IBKR shortability; `auto_live` still NO-GO. | User Directive + Cursor Agent |
| 2026-07-28 | Co-Pilot Coaching Footer extended: §5 now requires two end-of-reply paragraphs -- **Better ask:** (request feedback + one new thing) and **Follow-up ask:** (a concrete next question about this problem/answer + why it is the highest-value follow-up). | User Directive + Cursor Agent |
| 2026-07-28 | Constitution single-sourced: `AGENTS.md` is now the sole constitution text (the two mirrors had drifted -- ADR 007 execution-command schema and stale agent table existed only in `gemini.md`; ADR 007 block ported here). `gemini.md` reduced to a legacy alias that `@`-imports this file; `constitution.mdc` / `self-annealing.mdc` pointers updated. | User Directive + Cursor Agent |
| 2026-07-28 | Co-Pilot Coaching Footer: §5 now requires a short end-of-reply **Better ask:** coaching note (how the request could have been asked better + one new thing learned); skip trivial exchanges at agent judgement. | User Directive + Cursor Agent |
| 2026-07-23 | PROBLEM_LOG mandatory for every agent: strengthened `problem-log.mdc`; Lifecycle requires `problem_log=`; contract regex + subagentStop reminder; agent prompts + ops docs updated. | Cursor Agent |
| 2026-07-18 | Phase G3: `hotkeys` specialist Owned; typed Nova Actions (cancel/exit/Ask±/Bid±); one dispatcher; Trading quick-bar; `auto_live` NO-GO. | Cursor Agent |
| 2026-07-18 | Task log archive: `knowledge/task-log/` + always-on `task-log.mdc`; Lifecycle `task_log=`; scaffold `tools/task_log_new.py`. Captures why/tradeoffs after every material job. | Cursor Agent |
| 2026-07-18 | Agent naming standardization: `nova-router`→`router`, `nova-agent`→`docs`, `security-sentinel`→`security`, `widgets-agent`→`widgets`, `news-catalyst`→`news`; canvases aligned to `agent-<id>`; fleet map Mode column; registry reordered. | Cursor Agent |
| 2026-07-18 | Fleet gap-fill: scaffolded `execution` (audit-only + `execution-continuity.mdc`), `ibkr-ops`, `backtester` (absorbs VectorBT skill cluster), `market-feed`, `news`, and top-of-fleet `daddy` dispatcher; flipped `Agent-Fleet-Map.md` Unowned→Owned / Orphan→Owned; routing + docs + contract updated to 14 agents. | Cursor Agent |
| 2026-07-18 | Agent Fleet Router: `Agent-Fleet-Map.md` domain/skill ownership matrix; `tools/agent_fleet.py` read-only crack index (+ tests); Nova Home "Fleet cracks" rollup; `router` specialist (report-only triage, `agent-router` dashboard); `sessionStart` hook (`tools/session_brief_hook.py`) leads every chat with top-3 cracks; `specialist-routing.mdc` gains an unowned-domain escalation path; fixed missing `hod-momo` in `AGENT_TITLES`. | Cursor Agent |
| 2026-07-16 | Webull Widget Parity Specialist (`widgets`): source-backed stock/day-trading capability map, continuity rule, and dedicated `agent-widgets` dashboard; selected implementations preserve manual controls and IBKR safety. | Cursor Agent |
| 2026-07-16 | Unified agent lifecycle OS: `.cursor/agent-system/` contract+registry; memories in `.cursor/agent-memory/`; specialist-routing + subagentStop hook; agent_contract / sync_agent_surfaces / create_nova_agent tools + CI job; docs/agent-operations.md. | Cursor Agent |
| 2026-07-16 | Warrior Trading Navigator (`warrior`): authenticated site navigation specialist; dashboard `agent-warrior`; durable map in Obsidian + `docs/warrior-authenticated-access.md`; retired unmanaged `warrior-site-map` canvas. | Cursor Agent |
| 2026-07-16 | Docs (`docs`): docs + canvas steward; Diátaxis / markdownlint-cli2 / Vale / Lychee pins; `docs-continuity.mdc`; `tools/nova_docs_inventory.py`; dashboard = Nova Home; merged unmanaged `nova-security-audit` into `agent-security`. | Cursor Agent |
| 2026-07-16 | Security-sentinel baseline enrichment: compensating controls seeded for SEC-001–SEC-006 in `security/findings-registry.json`; `Security-Status.md` open-findings table + verification ledger populated; `security-memory.md` run log updated. Findings open — no product fixes. | Cursor Agent |
| 2026-07-15 | Maintainer sentinel subagent: `.cursor/agents/maintainer.md` + `maintainer-memory.md` (read-only auditor for file limits, secrets, swallowed errors, deps); deterministic `tools/maintainer_checks.py` + tests; `pip-audit` added to `requirements-dev.txt`. Invoke: “Use the maintainer subagent to audit the repo.” | Cursor Agent |
| 2026-07-15 | Audit hygiene pass: `main.py` trimmed to 194 lines (CORS middleware setup extracted to `app_lifespan.configure_cors()`); stale `run-app.mdc` / file-size docs corrected to reflect Nova branding and real line counts; silent-except hygiene fixes in `cache.py`, `logging_setup.py`, `run_api.py`, `routes/news.py`, `news/enrich.py`; new tests for `routes/trading.py`, `ibkr/account.py`, `scan_runners.py`; `requirements.txt` pins recorded for previously-unpinned packages; scratch `_repro_test.py` removed. | Cursor Agent |
| 2026-07-14 | `frontend/src/App.tsx` reduced to 68 lines (Phase 7). Both main.py and App.tsx file-size targets met. | Cursor Agent |
| 2026-07-14 | `backend/main.py` reduced to 199 lines (Phases 1–6 product-health extraction). Compliance audit §2.3 / §10 updated: main.py target met. | Cursor Agent |
| 2026-07-10 | Invariant #7 amended: Alpaca scanning stays read-only; IBKR opt-in module (`backend/ibkr/`) now permitted for paper/live order execution, gated by `IBKR_ENABLED` + `IBKR_LIVE_TRADING_CONFIRMED` flags. Constitution updated first per §1.8. | User Directive + Cursor Agent |
| 2026-04-27 | Complete constitution rewrite — added modularity laws, file limits, compliance audit, self-annealing protocol, coding standards | Antigravity + User Directive |
| 2026-04-27 | Added mandatory git commit & push rule | User Directive |
| 2026-04-13 | Project Constitution initialized | System Pilot |
| 2026-07-15 | Phase A skills library: vendored vectorbt/backtesting/security skills into `.cursor/skills/` + Obsidian [[Skills-Library]] / [[Reference-Repos]] indexes. | Cursor Agent |

---

## Agent Skills Library (Nova Master Roadmap Phase A)

Discoverability for vendored Cursor skills (research/backtest advice only — **never** bypass IBKR execution, single-market-data-feed, or `auto_live` NO-GO):

| Resource | Path |
|----------|------|
| **Skills catalog** | `knowledge/obsidian/00-System/Skills-Library.md` |
| **Study-only repos** | `knowledge/obsidian/00-System/Reference-Repos.md` |
| **Local skill files** | `.cursor/skills/` (pins in `SOURCE-PINS.txt`) |

Pre-existing: `karpathy-guidelines`, `graphify`. Phase A adds: `backtest`, `optimize`, `strategy-compare`, `vectorbt-expert`, `backtesting-frameworks`, `llm-trading-agent-security`.

**Engineering methodology graft (2026-08-06):** Nova-adapted process skills (domain constitution still wins; zero-hop preserved):

| Skill | Path | Role |
|-------|------|------|
| `verification-before-completion` | `.cursor/skills/verification-before-completion/` | Evidence before done/fixed claims (always-on MDC twin) |
| `writing-plans` | `.cursor/skills/writing-plans/` | Bite-sized plans for Plan mode / multi-file work |
| `interview-me` | `.cursor/skills/interview-me/` | One-question requirements interview |
| `doubt-driven-development` | `.cursor/skills/doubt-driven-development/` | Adversarial review of non-trivial claims |
| `code-review-and-quality` | `.cursor/skills/code-review-and-quality/` | Five-axis review before ship |
| `github-delivery` | `.cursor/skills/github-delivery/` | Issue metadata, [Nova Delivery](https://github.com/users/aaltaay/projects/1) board, clean start from `origin/master`, ready-PR finish line, Actions merge, delete head after merge/close, strict gates |

Always-on rules: `verification-before-completion.mdc`, `engineering-methodology.mdc`, `github-delivery.mdc`. Audit: `py -3 tools/engineering_skills_audit.py`. Lineage pins in `.cursor/skills/SOURCE-PINS.txt`. **Not imported:** default subagent-per-task, always-hard brainstorming, replacing `AGENTS.md`.

### Specialized Cursor subagents

Wiring: `.cursor/agent-system/registry.json` · memory: `.cursor/agent-memory/` · ops: `docs/agent-operations.md` · validate: `py -3 tools/agent_contract.py`.

**Zero-hop default:** every subagent below is **opt-in only** — invoke by name when you explicitly want it. The parent Auto session classifies and does multi-domain work in-session by default (no automatic dispatch); see `.cursor/rules/specialist-routing.mdc`.

| Agent | Invoke | Dashboard |
|-------|--------|-----------|
| **router** | “Use the router subagent to triage this” | [agent-router](canvases/agent-router.canvas.tsx) |
| **execution** | “Use the execution subagent to audit trading execution” | [agent-execution](canvases/agent-execution.canvas.tsx) |
| **hotkeys** | “Use the hotkeys subagent to …” | [agent-hotkeys](canvases/agent-hotkeys.canvas.tsx) |
| **ibkr-ops** | “Use the ibkr-ops subagent to diagnose IB Gateway” | [agent-ibkr-ops](canvases/agent-ibkr-ops.canvas.tsx) |
| **market-feed** | “Use the market-feed subagent to fix feed coherence” | [agent-market-feed](canvases/agent-market-feed.canvas.tsx) |
| **hod-momo** | “Use the hod-momo subagent to continue HOD Momo parity” | [agent-hod-momo](canvases/agent-hod-momo.canvas.tsx) |
| **backtester** | “Use the backtester subagent to work the backtest product” | [agent-backtester](canvases/agent-backtester.canvas.tsx) |
| **news** | “Use the news subagent to work the news pipeline” | [agent-news](canvases/agent-news.canvas.tsx) |
| **widgets** | “Use the widgets subagent to map Webull widgets to Nova” | [agent-widgets](canvases/agent-widgets.canvas.tsx) |
| **warrior** | “Use the warrior subagent to navigate Warrior Trading” | [agent-warrior](canvases/agent-warrior.canvas.tsx) |
| **tester** | “Use the tester subagent to verify …” | `agent-tester.canvas.tsx` |
| **maintainer** | “Use the maintainer subagent to audit the repo” | `agent-maintainer.canvas.tsx` |
| **security** | “Use the security subagent to audit the repo” | `agent-security.canvas.tsx` |
| **docs** | “Use the docs subagent to review documentation” | [nova-home](canvases/nova-home.canvas.tsx) |

Canvas naming: prefer `nova-home` + `agent-*` (+ Cursor `context-usage-*`). Unmanaged boards are reviewed by Docs. **`router`** remains the pure classification / crack-index tool, invoked only on explicit ask (default is `py -3 tools/agent_fleet.py`, no LLM hop). `hod-momo` owns HOD Momo ↔ Warrior parity (`agent-hod-momo`); never feeds Warrior data into Nova's alert engine. `widgets` owns Webull ↔ Nova widget mapping (`agent-widgets`); Webull remains research-only. `execution` is audit-only for ADR 007. `market-feed` owns general L1 + quote/L2/T&S coherence (HOD pool stays `hod-momo`). `backtester` owns Phase E + the VectorBT skill cluster. Route via `.cursor/rules/specialist-routing.mdc` (zero-hop default; specialists are opt-in).

---

## 12. Cursor Rules (.mdc files)

Live rule bodies live only under `.cursor/rules/*.mdc`. Do **not** paste full rule text into this file (it double-loads and drifts). Do **not** create a root `.cursorrules` file -- scoped `.mdc` frontmatter is strictly better.

### Index (name -- purpose -- attachment)

**Always-on** (every request):

- `constitution.mdc` -- read AGENTS.md; hierarchy; common violations + context economy
- `specialist-routing.mdc` -- zero-hop default; specialists opt-in only
- `single-market-data-feed.mdc` -- IBKR-only prices; quote-panel symbol gates; HOD pool rules
- `ibkr-gateway-login-warning.mdc` -- loud-warn when Gateway needs login/2FA
- `nova-roadmap-continuity.mdc` -- Master Roadmap phase continuity
- `engineering-standards.mdc` -- Tailwind direction, tests, CI, deps, patterns
- `karpathy-guidelines.mdc` -- think / simplify / surgical / verify
- `problem-log.mdc` -- mandatory PROBLEM_LOG after bug fixes
- `deferred-log.mdc` -- check GitHub Issues (`deferred`) before any fix; park known bugs/features; to-do via `deferred_log.py status` / `priorities`
- `change-log.mdc` -- CHANGELOG after behavior changes
- `task-log.mdc` -- reasoning narrative after material work (PR body first; file when no PR)
- `commit-push-deploy.mdc` -- clean start from `origin/master`; verify, commit, push, open a ready PR; Actions merges it; delete head after merge (+ deploy when applicable)
- `doc-invariants.mdc` -- posture-change same-commit live homes; CI `doc_invariants.py`
- `self-annealing.mdc` -- root-cause fix protocol on any error
- `verification-before-completion.mdc` -- no done/fixed claims without fresh evidence
- `engineering-methodology.mdc` -- soft TDD + plan/interview/doubt/review skill map
- `github-delivery.mdc` -- issue metadata, [Nova Delivery](https://github.com/users/aaltaay/projects/1) board, clean-start + ready-PR session gates, Actions merge of ready PRs, delete head after merge/close, strict gates
- `persisted-state.mdc` -- cache files need owner + invalidation + schema_version
- `graphify.mdc` -- vault/decision questions: `py -3 tools/graphify_ask.py query` + savings meter

**Glob-scoped** (attach when editing matching files; `alwaysApply: false`):

- `backend-modularity.mdc` -- `backend/**/*.py` -- no logic in `main.py`
- `frontend-modularity.mdc` -- `frontend/src/**/*.{ts,tsx}` -- no logic in `App.tsx`
- `file-size-limits.mdc` -- backend + frontend src -- max lines / extract-first
- `centralized-constants.mdc` -- backend + frontend src -- tunables in domain modules
- Continuity rules (already glob): `hotkeys-continuity`, `docs-continuity`, `execution-continuity`, `widgets-continuity`, `security-continuity`

**Agent-requested** (name + description always visible; body fetched on demand):

- `browser-testing.mdc` -- web verification / Playwright / agent-browser
- `run-app.mdc` -- how to run/open Nova locally
- `nova-os-continuity.mdc` -- Nova OS engine phases (closed; rare)

Karpathy full text: `.cursor/rules/karpathy-guidelines.mdc` (also `.cursor/skills/karpathy-guidelines/`).
Browser testing full text: `.cursor/rules/browser-testing.mdc`.
