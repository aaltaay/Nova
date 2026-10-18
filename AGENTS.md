# 🏛️ AGENTS.md -- Project Constitution (Law)

> **Single source of truth.** Every agent reads this file; `CLAUDE.md` imports it.
>
> **Status:** ENFORCED -- Active governance document
> **Last Updated:** 2026-10-17
> **Project:** Nova -- Stock Alert Automation System
> **Enforcement:** Every AI agent (Cursor, Antigravity, any LLM assistant) MUST read this file before writing ANY code. Violations are NEVER acceptable.

---

## Retired ledgers (owner instruction, 2026-09-20)

`BACKLOG.md`, `PROBLEM_LOG.md` and `CHANGELOG.md` are retired and archived under `docs/archive/`. Do not read, update, regenerate, or require them during ordinary agent work; read archived material only when explicitly asked for historical context. Use GitHub Issues/milestones for current work and PR descriptions plus regression tests for completed fixes. No `problem_log=` footer, changelog entry, fragment, or collation job is supported.

## 0. PURPOSE

This document is the **single source of truth** for how this project is built, maintained, and extended. It exists because:

1. AI assistants lose context between sessions.
2. Without rules, assistants dump everything into monoliths.
3. The user has explicitly mandated modular, disciplined engineering.

**If a rule here conflicts with an agent's default behavior, this document wins.**

### Master Roadmap (product phases)

- **Canonical ledger:** `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md` -- which phase is NEXT, checkboxes, History.
- **Target architecture:** `architecture/README.md` + `architecture/dependency-rules.md` + ADRs under `architecture/decisions/` -- modular monolith, selective ports/adapters, feature slices, CSS cascade layers. Structural moves must cite an ADR.
- **Continuity rule:** `.cursor/rules/nova-roadmap-continuity.mdc` -- read status first; phase-close verify + commit + push; scope guard.
- **Phase B ops:** `docs/paper-shadow-protocol.md` -- paper shadow (historical mode ladder retired by ADR 025; **`auto_live` NO-GO**).
- **Plan / canvas:** `nova_master_roadmap_a_z.plan.md` · `nova-home.canvas.tsx`
- **Nova OS history (retired, ADR 025):** `knowledge/obsidian/03-Nova-Decisions/Nova-OS-Status.md` -- event log and kill switch remain; product NEXT is Roadmap-Status.
- **Docs & Agent OS:** `.cursor/agents/docs.md`, `.cursor/rules/docs-continuity.mdc`, `.cursor/agent-system/`, `docs/agent-operations.md`.
- **Historical charts:** `docs/NOVA_CHART_EXPORT.md` -- explicit local symbol/day data, Nova's native renderer.

---

## 1. ⚖️ Architectural Invariants (Unbreakable Law)

These rules CANNOT be violated under ANY circumstance:

| # | Invariant | Rationale |
|---|-----------|-----------|
| 1 | **Data-First** | No tool is written before the JSON schema is confirmed in `architecture/schema/` (§3 indexes it). |
| 2 | **Deterministic Tools** | All Python scripts in `tools/` must be atomic, testable, and side-effect-free unless explicitly noted. |
| 3 | **Secrets in `.env` only** | No API keys, tokens, or credentials EVER appear in source code, logs, or commits. |
| 4 | **`.tmp/` is ephemeral** | Never treat `.tmp/` files as a source of truth. |
| 5 | **SOP before code** | If logic changes, update `architecture/` or relevant `.cursor/rules/` FIRST, then write code. |
| 6 | **Self-Annealing** | Any error -> Analyze -> Patch -> Test -> Update SOP/rules -> Record the cause, fix, and verification in the PR or issue. If the bug cannot be fixed this session, **MUST** open or update a GitHub Issue labeled `deferred` instead of a band-aid (`deferred-log.mdc`). |
| 7 | **Broker Execution Gate** | Alpaca-sourced scanning is permanently read-only. Trade execution is permitted ONLY through the explicit opt-in `backend/ibkr/` module. Gateway default is **live** (port 4001); the paper Gateway (4002) is legacy by hand only (`POST /api/ibkr/gateway-mode {"mode":"paper"}`), never an automatic fallback (`IBKR_PAPER_GATEWAY_FALLBACK` off by default, ADR 020). Spending requires `IBKR_ENABLED=true`, `IBKR_ORDERS_ENABLED=true`, and the runtime arm latch (`POST /api/ibkr/arm`, ADR 018); live money also requires `IBKR_LIVE_TRADING_CONFIRMED=true` in `.env` and the operator's Live PIN. **Short entry (ADR 009, ADR 048):** every SELL is risk-reducing unless an explicit `short_entry` opt-in passes `backend/short_sale/` on every venue (limit + buy stop above it, never while long, margin account >= $2,000 equity, 09:35-15:50 ET, no halt, IBKR tick-236 borrow covering order + held + in-flight shorts, SSR above bid, IBKR what-if or published margin with 25% liquidation cushion; Live also requires `IBKR_SHORT_ENABLED=true`; Paper/Sim cover at 15:55 ET; readiness/research verdicts never grant or refuse permission, #791). A BUY covering a short is a close (never locked by the loss limit, buying power, or past flat). Never infer shorts from side + flat position. `auto_live` remains NO-GO, and a bot never trades Live. Schemas: `architecture/schema/execution.md`, `architecture/schema/short-selling.md`, `architecture/schema/loss-limit.md`. |
| 8 | **Constitution is Law** | No code change may contradict this document. If a contradiction is needed, update this document FIRST with a row in `architecture/maintenance-log.md`, THEN write the code. |

---

## 2. 📐 Modularity Laws (Enforced by the checker)

One command enforces every rule in this section -- run it before you push (`deploy.yml`; `tools/maintainer_lib/gate.py`):

```text
py -3 tools/maintainer_checks.py --gate --base origin/master
```

### 2.1 Where code goes

- **Entry points hold wiring only.** `backend/main.py`: app factory, middleware, `lifespan`, router registration. `frontend/src/App.tsx`: providers, shell, route definitions. Anything else belongs to a module (§2.3 caps both).
- **New code goes where its concept is owned.** `py -3 tools/module_map.py [word]` prints what every backend package and frontend folder owns.
- **Nothing owns it? Make an owner in the same change.** A backend package's `__init__.py` opens with a docstring naming what it owns (`package_owner_missing`). A frontend folder gets a row in `frontend/src/FOLDERS.md` with its ADR 005 kind -- `feature`, `shared` or `app` (`folder_owner_missing` / `folder_owner_stale`).
- **Prefer a package to a new top-level `backend/*.py` module.**

### 2.2 Feature boundaries (ADR 005)

- A frontend feature imports another feature only through its barrel (`../chart`, never `../chart/barsStore`); `shared` code imports no feature internals (`cross_feature_import`).
- Pre-existing violations are frozen per file in `tools/maintainer_lib/baselines.json`; one more fails the gate. Frozen counts only go down (`--update-baselines`).

### 2.3 File size

**Never squeeze a file to fit a number** (deleting blank lines, joining statements, or moving code to an arbitrary sibling).

| Files | Rule | Kind |
|-------|------|------|
| `backend/main.py` | 200 **logical** lines | `file_size_hard` (gate) |
| `frontend/src/App.tsx` | 150 **logical** lines | `file_size_hard` (gate) |
| `frontend/src/index.css` | 50 raw lines (import-only barrel) | `file_size_hard` (gate) |
| Code (`.py` `.ts` `.tsx` `.js` `.jsx`) over 400 lines | split it, or state why it is one concern | `file_size` (advisory) |
| ... that grew in this change without that reason | split it or state the reason | `file_size_growth` (gate) |
| Any code file over 800 lines | split it; no reason covers this | `file_size_ceiling` (gate) |
| Constants tables (`backend/constants*.py`, `frontend/src/constantGroups/`) | exempt from 400; 800 still applies | -- |
| Stylesheets | advisory at 1000, prefer 700 or less | `file_size` |
| `AGENTS.md` | 700 raw lines | `file_size_hard` (gate) |
| Always-on context: this file + `CLAUDE.md` + every `alwaysApply: true` rule | one byte budget, ratchets down only (ADR 051, `tools/maintainer_lib/always_on.py`) | `always_on_budget` (gate); `always_on_growth` (advisory) |
| Tests | exempt | -- |

**Stating the reason:** one line in the file's first 40 lines, naming the single invariant or state it owns ("legacy" is not a reason):

```python
"""Scanner discovery.

maintainer: one-concern the never-leak-a-scanner-slot invariant must live in one place
"""
```

**Logical lines** exclude imports, comments and blank lines (`tools/maintainer_lib/sizes.py`, #393).

### 2.4 Refactoring Protocol

1. **Move** to the module that owns its concept (§2.1) and **import** back if still referenced.
2. **Do NOT leave the old copy** behind; **update all callers** in the same commit.
3. **Never make a monolith worse** (`main.py` / `App.tsx`). **Split along a seam** -- one concern per file.

---

## 3. 📐 Data Schema (Confirmed)

Every confirmed wire and persisted shape lives in `architecture/schema/`, one file per domain. Read the domain's file before changing a route, socket frame, or persisted file it owns, and update it in the same commit (Invariants #1 and #5; `.cursor/rules/schema-docs.mdc`).

| Schema file | Indexed subsections |
|---|---|
| `architecture/schema/recording-and-replay.md` | Capture / replay truth (#316, #317); Replay progress and capture fidelity (#321, #337); Recording persistence and coverage; The Records page and turning recording off; Recorded depth in historical replay (#309); The replayed session's previous close (#542); Massive flat files in Sim replay (ADR 046); An exchange's own book in Sim replay (ADR 057); Practice venues and fills (ADR 019, ADR 020); Sim at now is live -- the live edge (ADR 020) |
| `architecture/schema/agent-desk.md` | Agents find stock-days and show them in the Sim (ADR 050); historical OHLCV charts/MCP |
| `architecture/schema/local-historical-charts.md` | Explicit local minute-Parquet symbol/day resolution and historical chart export |
| `architecture/schema/desk-ops.md` | Desk diagnostics (ADR 021); IBKR capacity on the desk; Which backend answers; Who may reach the API: Host names and socket origins; Where Nova keeps its data; Why the Gateway needed a phone login; premarket evidence (#14); Release notes and the update notice; Filing an issue from the desk; Symbol directory for the header search; The operator's watch list and its toasts; The close-of-day reminder; The desk's voice and the header mute |
| `architecture/schema/scanner.md` | Scanner rows and HOD Momo alerts on the wire; Float credibility and short-interest dates (#532); The company's country; Scanner leaderboard: recorded, reconstructed, played back (ADR 023); Watchlist rows |
| `architecture/schema/setups.md` | Setup scanner and tape gate (ADR 022); The flat top counts its touches (ADR 031); The 5-minute flat top (ADR 031); Targets replace 2R: the menu, two halves, every choice scored (#845); The pullback dip: a watch-only setup (#847); The ABCD: a watch-only setup; One row per trigger; Too thin to trade; The 5-minute chart on a 1-minute setup (trial T8); The 5-minute setups; The tape flow score and the flush exit (ADR 034); Signal trials (ADR 041); Setup templates, the eyes' journal and replayed eyes (ADR 029) |
| `architecture/schema/trade-ledger.md` | The author's trade ledger (S7) |
| `architecture/schema/stock-read.md` | The bot's read on one stock (ADR 036, #598); Setups that ended stay on the chart, and what price did next (ADR 036); The day's levels: support and resistance on the charts and in the plan (ADR 036); Trend lines on the 1- and 5-minute charts (ADR 036); Who trades the stock (ADR 037, #604, #606); Managing a trade you hold (ADR 036 / 037); Why it's moving (ADR 028) |
| `architecture/schema/catalysts.md` | Catalysts (ADR 024) |
| `architecture/schema/performance.md` | Performance recorder (ADR 026) |
| `architecture/schema/journal.md` | Journal statistics, operator judgment (#791) |
| `architecture/schema/book-watch-and-luld.md` | The operator's focus and the book watcher (ADR 033); LULD bands on Level 2 (ADR 047); The LULD band on the 1-minute chart (ADR 047) |
| `architecture/schema/screen-and-clips.md` | The trading screen is always recorded (ADR 035); The desk draws with the graphics card (#707); Share clips (ADR 039) |
| `architecture/schema/bot.md` | Bot playbook and the read-out gate (ADR 027); The Live Trader bot: a TraderTV host copied on Paper (ADR 055); One Bots page (ADR 044); The bot trades a Sim replay (ADR 052, #814); Fills on the bot audit stream |
| `architecture/schema/execution.md` | Who may arm the desk (ADR 018); Account identity on `/api/ibkr/status`; Orders refuse a stale view; the market path stays real time (ADR 045); Execution command (ADR 007); Execution venue provenance (#713); Live order state: orderRef, whyHeld, reconnects, IBKR's own events; The exit-only pair and two halves (#681) |
| `architecture/schema/market-data.md` | Prints that set a price; The tape archive never stops writing; When IBKR data stops arriving (#672, #673); A Level 1 line IBKR refused; Lines IBKR answers after Nova cancelled them; When one tape line goes silent (#722); The trading session ends at 20:00 ET; Chart bars say when IBKR history stopped answering (ADR 012, #555); Earnings and splits on the daily charts; The forming candle's volume |
| `architecture/schema/cryptos.md` | The Cryptos page (ADR 040) |
| `architecture/schema/followed-traders.md` | Followed traders: another feed's positions, priced with IBKR |
| `architecture/schema/market-board.md` | The Market page (ADR 053) |
| `architecture/schema/volume-profile.md` | Volume profile on the 5-minute chart (ADR 058) |
| `architecture/schema/short-selling.md` | Short selling (ADR 048, #778); The short setups on the scanner (ADR 049); The bot trades both sides (ADR 049); Operator trading judgment and Live's day cover (ADR 048, #791) |
| `architecture/schema/loss-limit.md` | One daily loss limit (ADR 056) |

### CI scope output

`tools/ci_scope.py` classifies changed repository paths into boolean JSON fields: `{"backend": true, "frontend": true, "e2e": true, "desktop": true, "source": true, "dependencies": true}`. Unknown paths, unavailable diffs, and manual runs select full verification (`.cursor/rules/ci-scope.mdc`).

### Input / Output Payloads

Raw input (`{symbol, previous_close, current_price, gap_percent, volume, timestamp}`) and delivery payload (`{health: {status, latency_ms}, gappers: [{symbol, previous_close, current_price, gap_percent, volume}]}`). Capture market projections preserve missing facts: print-only rows have null bid/ask/sizes and the replay's own previous close (null when unrecorded, #542); depth is empty without recorded books; daily OHLC is null unless a replay source provides it. There is no synthetic instrument (ADR 019); `replay_source` is `none` when nothing is loaded.

---

## 4. 🔗 Integrations & Services

| Service | Purpose | Status |
|---------|---------|--------|
| Alpaca API | News + listing metadata (not price discovery) | ✅ Verified |
| IB Gateway (local) | Scanner discovery + market data + optional orders | ✅ Verified |
| Web UI (Localhost / Desktop) | Delivery dashboard for gappers | ✅ Verified |
| yfinance | Fundamental data (float, short interest, etc.) | ✅ Verified |
| CoinGecko, Coinbase Exchange, alternative.me, Hyperliquid, DefiLlama, Deribit (public, keyless) | The Cryptos page's crypto reference data (ADR 040): read-only, each labelled on the page, never a stock or order source | 🧪 Fixture-tested |
| State Street SPDR holdings files, BEA release dates (public, keyless) | The Market page's sector membership and calendar (ADR 053): never a price source | 🧪 Fixture-tested |
| ntfy.sh (public, keyless) | The release ping (§8): a hint to ask GitHub now; never an installer, price or order source | 🧪 Fixture-tested |

---

## 5. 📋 Behavioral Rules (Enforced)

### Verification policy: green only (owner, 2026-10-13)

Nothing ships red. Actions merges a ready PR, and `Desktop pack` publishes a `vNNN` Release (§8), only when `Backend tests`, `Frontend build`, `Frontend E2E` and `Agent contract` pass (`tools/pr_checks.py`, `tools/release_gate.py`). Drafts, `do-not-merge`, forks and conflicts hold PRs; failed checks hold with a comment and merge on a green re-run. Master protection blocks force-push and deletion (admins included) with **no required status checks** (the merge job is the gate, so status-only pushes still work); every other branch refuses force-pushes too (§5.1). Trading runtime gates, opt-ins and `auto_live` NO-GO are unchanged. Coverage: `.cursor/rules/ci-scope.mdc`.

- **Market data / trading:** Scanner and prices are IBKR-only (`.cursor/rules/single-market-data-feed.mdc`); Alpaca is news/listing metadata only; the Cryptos page (ADR 040, `architecture/schema/cryptos.md`) is a public reference board only. Orders go only via gated `backend/ibkr/` (Invariant #7); `auto_live` remains NO-GO. Header **Live / Paper / Sim** are venue pills (ADR 019, ADR 020, `architecture/schema/recording-and-replay.md`): **Live** routes to IBKR (port 4001 default; paper Gateway 4002 is legacy by hand only); **Paper** fills locally on the live IBKR feed; **Sim** replays a recorded/downloaded session on a scratch account that unwinds on rewind, and at the **live edge** (`live_edge` on clock and `/api/ibkr/status`) shows the live IBKR feed like Paper (no synthetic instrument; `NOVA_BROKER=sim` is bootstrap only). Operator and bots share the same gates (`architecture/schema/bot.md`): strategy bots require an allowlisted symbol with a backend-held depth line (`409 BOT_NO_DEPTH_LINE`) or replay book on Sim (ADR 052); the Live Trader bot (ADR 055) copies TraderTV hosts on Paper only using its own Level 1 line.
- **Desk venue vs spend arming (ADR 018, #302):** Venue (`desk-venue.json`, owner `sim/mode.py`) is durable; spend arming (`ibkr/safety.py`) never survives process start or venue change. Arming goes only through `POST /api/ibkr/arm` (`architecture/schema/execution.md`): Live requires `NOVA_LIVE_ARM_PIN_HASH` (`py -3 tools/set_live_arm_pin.py`); Paper and Sim arm without a PIN. Protective sources (`flatten`, `kill`, `cancel_working`) and cancel are always exempt when disarmed.
- **Real time or no order (ADR 045):** A desk order is refused while its Level 2, quote or Time & Sales is behind or dead (`architecture/schema/execution.md`). Flatten and cancels always work.
- **Market Open Halt**: The gapper dashboard stops updating its data feed once the market formally opens.
- **Configurable**: API keys and base URLs must be configurable via UI.
- **PR-first delivery after every task:** Follow §5.1 and `.cursor/rules/github-delivery.mdc`: clean branch from `origin/master`, `.github/pull_request_template.md`, `Closes` vs `Refs`, ready (non-draft) PR finish line, Actions auto-merge when green (`tools/pr_delivery.py`), head branch deleted after merge/close (`tools/stale_pr_branches.py`), and master branch protection (`py -3 tools/master_branch_protection.py check`). Public source home is `aaltaay/Nova` (`aaltaay/Nova-public` is a private archive).
- **Backlog work packages:** Ranked milestones in `knowledge/backlog-packages.json` (`py -3 tools/backlog_triage.py next|triage|sync|check|report`; see `CLAUDE.md`). Batch related issues into one reviewable PR; never guess gated policy decisions.
- **Nova Delivery board:** Canonical project is https://github.com/users/aaltaay/projects/1 (user project `1`, owner `aaltaay`, id `PVT_kwHOAXJK5M4Ab7Vq`). Run `gh project item-add 1 --owner aaltaay --url <html_url>` when token scope allows; report 403 limitations truthfully (`.cursor/rules/github-delivery.mdc`).
- **Next-move picks** (fixed lanes retired, operator report 2026-10-13): every reply that ends a task ends with the best six next moves from `tools/next_moves.py` (`card` via `show_widget` in Claude desktop, numbered `menu` elsewhere) in plain English per `.cursor/rules/next-move-footer.mdc`; specialist subagent reports keep the `**Lifecycle:**` line instead.

### 5.1 Session lifecycle (Deliver)

**Never rewrite pushed history (owner, 2026-10-14: "Force push, meaning we're deleting work. Everything needs to be merged properly").** No `git push --force`, `--force-with-lease` or `+ref` push, ever, and no rebase, amend, reset or squash of a branch on origin. Bring `master` in with `git merge origin/master`, resolve, commit, and push normally. Enforced by the GitHub ruleset `No force-push` (`py -3 tools/no_force_push.py check`) and `.githooks/pre-push`.

**Branch preservation (#369):** A closed PR's branch name is never proof that its current tip is disposable. Preserve and report tips not contained in `origin/master` (squash-only or closed-unmerged tips require explicit review). Remote deletion re-reads the tip right before a plain delete (`branch_cleanup.delete_at_tip`, `pr_delivery.py delete-closed --ref <branch>`). See `.cursor/rules/branch-cleanup.mdc`.

These gates are **MUST** and override casual phrasing ("quick fix", "just tweak"); only an explicit user override waives them (state the waiver in the PR body).

**A. Clean start -- before any edits**

1. `git fetch origin`.
2. Create or switch to a **new** focused branch from `origin/master` only (never from a dirty local `master` or another feature branch unless named).
3. Do not proceed on uncommitted or unrelated dirty files; reset/clean untracked task-foreign files or abort and report dirty paths.
4. Use one isolated worktree per task when parallel agents may run (`workspace-hygiene.mdc`).

**B. Mandatory finish -- end of every coding session or task**

1. Verify (tests and build appropriate to the change).
2. Stage explicit paths (`git add <paths>`, never `-A` or `git stash`), commit on the focused branch, and push.
3. Open a **ready (non-draft)** PR targeting `master` from `.github/pull_request_template.md`; attach to [Nova Delivery](https://github.com/users/aaltaay/projects/1) when token scope allows.
4. Draft or `do-not-merge` only on an explicit user hold or documented hard external blocker -- never because CI is still running.
5. The PR URL is the finish line; Actions auto-merges green PRs and deletes the head branch.
6. **Leave it clean:** no modified/staged/untracked files, no stash, worktree removed, `py -3 tools/repo_hygiene.py status` OK (`workspace-hygiene.mdc`).

Pointers: `.cursor/rules/commit-push-deploy.mdc`, `.cursor/rules/github-delivery.mdc`, `.cursor/rules/workspace-hygiene.mdc`, `.cursor/skills/github-delivery/SKILL.md`.

---

## 6. 🔧 Coding Standards (Enforced)

### 6.1 Constants Policy

- **Authoritative values** live in backend domain modules (`constants_scanner.py`, `constants_hod_momo.py`, `constants_ibkr.py`, `constants_archive_news.py`, `constants_nova_os.py`) and frontend `constantGroups/` (or feature-local constants).
- `backend/constants.py` and `frontend/src/constants.ts` are **compatibility barrels** (re-exports only). No magic numbers or inline strings in `main.py` / `App.tsx`.

### 6.2 Naming

- Python: `snake_case` functions/variables/files, `PascalCase` classes, `UPPER_SNAKE` constants.
- TypeScript: `camelCase` functions/variables/utility files, `PascalCase` components/types/`.tsx` files, `UPPER_SNAKE` constants.

### 6.3 Error Handling

- Use structured logging (`logging.getLogger(__name__)`) in Python; surface errors in UI debug panels in the frontend. Never swallow exceptions silently.
- **The money path fails the gate on silence.** In `backend/execution/`, `backend/ibkr/`, `backend/practice/`, `backend/sim/`, `backend/kill_switch/`, `backend/bot/` and `frontend/src/ibkr/`, an `except ...: pass`, `except ...: return []` / `{}`, or empty `catch` is a `*_money` gate finding (`tools/maintainer_lib/swallow.py`). When silence is intentional, annotate the site: `except asyncio.TimeoutError:  # maintainer: allow-swallow the timeout ends the wait`.

### 6.4 Testing, Dependencies, Secrets & Lint

- **Testing:** pytest (backend) and Vitest + React Testing Library (frontend); every non-trivial change includes a test.
- **Dependencies:** pinned in `requirements.txt`; committed `package-lock.json` (`npm ci` in CI).
- **Secrets:** never commit secrets, API keys, or `.env` files; use `.env.example` for safe templates.
- **Lint (§6.7):** `ruff check backend` (`backend/ruff.toml`, pinned in `backend/requirements-dev.txt`) runs inside `py -3 tools/maintainer_checks.py --gate` (`tools/maintainer_lib/lint.py`). CI runs pytest even if Ruff fails so lint findings never hide test results.

---

## 7. 📝 Documentation Requirements (Enforced)

### 7.1 CHANGELOG.md -- RETIRED. The PR body is the record.

There is no changelog (`CHANGELOG.md` is archived under `docs/archive/`). Every behavior change is recorded in the PR body (`.github/pull_request_template.md`: **What** / **Why this approach** / **Verified by**), or under `knowledge/task-log/` when there is no PR (§7.2b).

### 7.2 Bug-fix evidence

Record symptom, root cause, fix, and verification in the PR or issue, with regression tests.

### 7.2b Task narrative (`.cursor/rules/task-log.mdc`)

Every completed material task requires a reasoning narrative (**Why this approach** is mandatory): in the PR body by default, or `knowledge/task-log/YYYY-MM-DD-<slug>.md` (`py -3 tools/task_log_new.py`) when there is no PR. Never write both homes for one job.

### 7.2c Deferred tracker (`.cursor/rules/deferred-log.mdc`)

- Source of truth is GitHub Issues labeled `deferred` (`py -3 tools/deferred_log.py status`). Run it before any fix and work from any matching issue (honoring `parked` / Unblock / Next).
- Same-session filing is mandatory when parking a known bug or feature. Use plain titles (GitHub `#NNN` is the durable ID; never mint a new `D-NNN`, which is a legacy alias only).
- Specialist Lifecycle footers must include `task_log=<PR URL|path|skipped|n/a>` and `deferred_log=<#NNN or D-NNN|none|skipped|n/a>`.

### 7.3 .cursor/rules/

Update or add the relevant `.cursor/rules/*.mdc` rule BEFORE changing governed behavior.

---

## 8. 🚀 Run & Deploy

Operator runbook for syncing the trading PC, cold-restarting IB Gateway, and arming the unattended premarket: `docs/live-desk-sync.md`.

### Local Dev (Windows)

```text
# Browser UI:          scripts/windows/Run Nova.bat
# Desktop sidecar:     scripts/windows/Run Nova Desktop.bat  (or: cd frontend && npm run electron:dev)
# Windows installer:   cd frontend && npm run electron:pack
# Manual:              backend: py -3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
#                      frontend: npm run dev  -> http://localhost:5173
```

### Deploy

- **Backend:** local only (`127.0.0.1:8000` via `Run Nova.bat`, Desktop sidecar, or local `uvicorn`) -- no cloud host (not Railway, not another PaaS).
- **Public site:** built from [`aaltaay/nova-site`](https://github.com/aaltaay/nova-site) (`nova.altaystudio.com`), outside this repo.
- **Frontend (app UI):** local Vite (`http://localhost:5173`) / Desktop only. Never host the live trading SPA on a public domain. **One exception (ADR 043):** the self-contained demo build (`npm run build:demo`, hosted at `nova.altaystudio.com/demo/`) stubs `fetch`, `WebSocket`, and `sendBeacon` in-page on sample data and makes zero network requests.
- **Desktop & automatic green-only Releases (#346, #347):** Electron + local API sidecar (`frontend/electron/startupSplash.mjs`). **Installer only:** `frontend/release/Nova-Setup-vNNN.exe` + `latest.yml` + `.blockmap` (the portable EXE is retired). Every `master` commit is tagged `vNNN` by `Desktop pack`; application-affecting commits (and PR-delivery dispatches) run full `Release checks` (`deploy.yml`) and publish the `vNNN` GitHub Release only when `Desktop pack`, `Backend tests`, `Frontend build`, `Frontend E2E`, and `Agent contract` are all green (`tools/release_gate.py`). Held builds fail loud and open a P1 `Release held: vNNN` issue closed by the next green Release (`tools/release_held.py`). Release notes are generated from the PR body by `tools/release_notes.py`.
- **In-app updates (#347, ADR 038):** `Desktop pack` posts each published `vNNN` to a public ntfy.sh topic (`frontend/electron/releasePing.mjs`) to trigger an immediate GitHub release check; the desk also checks at launch and every 2 hours, downloads in resumable 8 MB chunks (`frontend/electron/updateDownload.mjs`), and auto-installs outside weekday 07:00-16:00 ET when `GET /api/diagnostics/restart-check` holds only recordings and the PC is idle 5 minutes (`NOVA_UPDATE_AUTO_INSTALL=0` for offer-only; `NOVA_UPDATE_CHECK=0` disables automatic checks). Full update view, release notes, resumable `.part` cache, and backend-follow schema: `architecture/schema/desk-ops.md` ("Release notes and the update notice").

---

## 9. 🔄 Self-Annealing Protocol

When ANY error occurs during a task (`.cursor/rules/self-annealing.mdc`):

1. **STOP** -- do not apply a band-aid.
2. **Analyze** -- search GitHub issues/PRs and run `py -3 tools/deferred_log.py status`; work from any matching open/parked issue.
3. **Root Cause** -- identify the actual cause in the owning module (never `main.py` / `App.tsx`).
4. **Patch & Test** -- fix the root cause and verify with fresh tests/build.
5. **Update SOP & Deliver** -- record cause/fix/verification in the PR (or file a `deferred` issue if parked), update `.cursor/rules/` if needed, and deliver via §5.1.

---

## 10. 🚨 Compliance Audit (Current Violations)

No open constitution compliance rows. `architecture/` (ADRs 001--058) and automated tests (pytest + Vitest) exist. Product/security open work lives in `Nova-Roadmap-Status.md` and `Security-Status.md`. Live-doc drift is gated by `py -3 tools/doc_invariants.py` (CI).

---

## 11. 🔧 Maintenance Log

Moved to `architecture/maintenance-log.md` (newest first). A change to this file or to `architecture/schema/` adds its row there in the same commit.

---

## Agent Skills Library (Nova Master Roadmap Phase A)

Catalog: `knowledge/obsidian/00-System/Skills-Library.md` · Reference repos: `knowledge/obsidian/00-System/Reference-Repos.md` · Local skills: `.cursor/skills/` (pins in `.cursor/skills/SOURCE-PINS.txt`). Research/backtest skills (`backtest`, `optimize`, `strategy-compare`, `vectorbt-expert`, `backtesting-frameworks`, `llm-trading-agent-security`, `karpathy-guidelines`, `graphify`) never bypass IBKR execution, single-market-data-feed, or `auto_live` NO-GO.

**Engineering methodology graft:** `verification-before-completion`, `writing-plans`, `interview-me`, `doubt-driven-development`, `code-review-and-quality`, `github-delivery`. Always-on rules: `verification-before-completion.mdc`, `engineering-methodology.mdc`, `github-delivery.mdc`. Audit: `py -3 tools/engineering_skills_audit.py`. **Not imported:** default subagent-per-task, always-hard brainstorming, replacing `AGENTS.md`.

### Specialized Cursor subagents

Wiring: `.cursor/agent-system/registry.json` · memory: `.cursor/agent-memory/` · ops: `docs/agent-operations.md` · validate: `py -3 tools/agent_contract.py`. **Zero-hop default (`.cursor/rules/specialist-routing.mdc`):** every subagent below is opt-in only.

| Agent | Invoke | Dashboard |
|-------|--------|-----------|
| **router** | "Use the router subagent to triage this" | `agent-router.canvas.tsx` |
| **execution** | "Use the execution subagent to audit trading execution" | `agent-execution.canvas.tsx` |
| **hotkeys** | "Use the hotkeys subagent to ..." | `agent-hotkeys.canvas.tsx` |
| **ibkr-ops** | "Use the ibkr-ops subagent to diagnose IB Gateway" | `agent-ibkr-ops.canvas.tsx` |
| **market-feed** | "Use the market-feed subagent to fix feed coherence" | `agent-market-feed.canvas.tsx` |
| **hod-momo** | "Use the hod-momo subagent to continue HOD Momo parity" | `agent-hod-momo.canvas.tsx` |
| **backtester** | "Use the backtester subagent to work the backtest product" | `agent-backtester.canvas.tsx` |
| **news** | "Use the news subagent to work the news pipeline" | `agent-news.canvas.tsx` |
| **widgets** | "Use the widgets subagent to map Webull widgets to Nova" | `agent-widgets.canvas.tsx` |
| **tester** | "Use the tester subagent to verify ..." | `agent-tester.canvas.tsx` |
| **maintainer** | "Use the maintainer subagent to audit the repo" | `agent-maintainer.canvas.tsx` |
| **security** | "Use the security subagent to audit the repo" | `agent-security.canvas.tsx` |
| **docs** | "Use the docs subagent to review documentation" | `nova-home.canvas.tsx` |

---

## 12. Cursor Rules (.mdc files)

Live rule bodies live under `.cursor/rules/*.mdc` (never create a root `.cursorrules`). **What earns always-on (ADR 051):** a rule loads on every request only when editing *any* file could lose money or break delivery without it; everything else uses `globs` or stays agent-requested. `maintainer_checks.py` caps the set's byte total (`always_on_budget`).

- **Always-on (`alwaysApply: true`):** `constitution.mdc`, `specialist-routing.mdc`, `single-market-data-feed.mdc`, `ibkr-gateway-login-warning.mdc`, `nova-roadmap-continuity.mdc`, `engineering-standards.mdc`, `karpathy-guidelines.mdc`, `deferred-log.mdc`, `task-log.mdc`, `commit-push-deploy.mdc`, `doc-invariants.mdc`, `self-annealing.mdc`, `verification-before-completion.mdc`, `engineering-methodology.mdc`, `github-delivery.mdc`, `persisted-state.mdc`, `workspace-hygiene.mdc`, `graphify.mdc`, `next-move-footer.mdc`, `branch-cleanup.mdc`, `maintenance-finish.mdc`.
- **Glob-scoped (`alwaysApply: false`):** `backend-modularity.mdc`, `frontend-modularity.mdc`, `file-size-limits.mdc`, `centralized-constants.mdc`, `schema-docs.mdc`, `single-market-data-feed-catalog.mdc`, plus domain continuity rules (`hotkeys-continuity`, `docs-continuity`, `execution-continuity`, `widgets-continuity`, `security-continuity`).
- **Agent-requested:** `browser-testing.mdc`, `run-app.mdc`, `nova-os-continuity.mdc`.
