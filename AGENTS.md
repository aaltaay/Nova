# 🏛️ AGENTS.md — Project Constitution (Law)

> **Single source of truth.** Every agent reads this file; `CLAUDE.md` imports it.
>
> **Status:** ENFORCED — Active governance document
> **Last Updated:** 2026-10-07
> **Project:** Nova — Stock Alert Automation System
> **Enforcement:** Every AI agent (Cursor, Antigravity, any LLM assistant) MUST read this file before writing ANY code. Violations are NEVER acceptable.

---

## Retired ledgers (owner instruction, 2026-09-20)

`BACKLOG.md`, `PROBLEM_LOG.md` and `CHANGELOG.md` are retired and archived under
`docs/archive/`. Do not read, update, regenerate, or require them during ordinary
agent work. Read archived material only when the user explicitly asks for
historical context. Old references in comments, past PRs, task logs, and
maintenance history are not instructions to restore these files. Use GitHub
Issues/milestones for current work and PR descriptions plus regression tests for
completed fixes. No `problem_log=` footer, problem-log fragment, changelog
entry, changelog fragment or collation job is required or supported.

## 0. PURPOSE

This document is the **single source of truth** for how this project is built, maintained, and extended. It exists because:

1. AI assistants lose context between sessions.
2. Without rules, assistants dump everything into monoliths.
3. The user has explicitly mandated modular, disciplined engineering.

**If a rule here conflicts with an agent's default behavior, this document wins.**

### Master Roadmap (product phases)

- **Canonical ledger:** `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md` — which phase is NEXT, checkboxes, History.
- **Target architecture (maintenance):** `architecture/README.md` + `architecture/dependency-rules.md` + ADRs under `architecture/decisions/` — modular monolith, selective ports/adapters, feature slices, CSS cascade layers. Structural moves must cite an ADR.
- **Continuity rule:** `.cursor/rules/nova-roadmap-continuity.mdc` — read status first; phase-close verify + commit + push; scope guard.
- **Phase B ops:** `docs/paper-shadow-protocol.md` — paper shadow (historical: its `signal` → `confirm` → `auto_paper` ladder was retired by ADR 025; the bot's Off / Eyes / Strategy + Activate is the one automation path); **`auto_live` NO-GO**.
- **Plan / canvas:** `nova_master_roadmap_a_z.plan.md` · `nova-home.canvas.tsx`
- **Nova OS engine map (retired, ADR 025):** `knowledge/obsidian/03-Nova-Decisions/Nova-OS-Status.md` — history of P0–P10; the verdict, mode ladder and executor are gone, the event log and kill switch remain. Product “what’s next” is Roadmap-Status.
- **Docs (docs + canvases):** `.cursor/agents/docs.md` — documentation steward; memory in `.cursor/agent-memory/`; dashboard is Nova Home; preferred canvases `nova-home` + `agent-*` (+ Cursor `context-usage-*`). Continuity: `.cursor/rules/docs-continuity.mdc`. Agent OS: `.cursor/agent-system/` + `docs/agent-operations.md`.

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
| 6 | **Self-Annealing** | Any error -> Analyze -> Patch -> Test -> Update SOP/rules -> Record the cause, fix, and verification in the PR or issue. If the bug cannot be fixed this session (too big, wrong task, needs an ADR), **MUST** open or update a GitHub Issue labeled `deferred` instead of a band-aid (`deferred-log.mdc`). |
| 7 | **Broker Execution Gate** | Alpaca-sourced scanning is permanently read-only. Trade execution is permitted ONLY through the explicit opt-in `backend/ibkr/` module. Gateway connection default is **live** (port 4001). The IBKR paper Gateway (4002) is **legacy**: by hand only (`POST /api/ibkr/gateway-mode {"mode":"paper"}`), never an automatic fallback -- `IBKR_PAPER_GATEWAY_FALLBACK` is off by default because a paper login beside a live session is read-only and carries no tape (ADR 020). Spending still requires `IBKR_ENABLED=true` and `IBKR_ORDERS_ENABLED=true`; live money also requires `IBKR_LIVE_TRADING_CONFIRMED=true` in `.env`. No other module may place orders. **Short entry (ADR 009, ADR 048):** every SELL is risk-reducing unless an explicit `short_entry` opt-in on the execution command passes the one short check (`backend/short_sale/`), on every venue: a limit price with a buy stop above it, never while the account holds the stock long, a margin account with $2,000 of equity, 09:35 to 15:50 ET by the venue's clock, no halt, IBKR's tick-236 borrow covering the order plus the short held and in flight, SSR priced above the bid, and margin (IBKR's what-if, else the published rules) with a 25% liquidation cushion. Live also needs `IBKR_SHORT_ENABLED=true`, which only the operator sets, last, after the Live short proof (ADR 048); Paper and Sim need no Live key and short on their own ledger (ADR 048 step 2), where Nova covers every short at 15:55 ET. A BUY that covers a short is a close: never locked by the day lock, never held to buying power, never past flat. Never infer shorts from side + flat position. `auto_live` remains NO-GO, and a bot never trades Live. |
| 8 | **Constitution is Law** | No code change may contradict this document. If a contradiction is needed, update this document FIRST with a row in `architecture/maintenance-log.md`, THEN write the code. |

---

## 2. 📐 Modularity Laws (Enforced by the checker)

These rules describe behavior, not a snapshot of the tree. A hand-kept file tree
and hand-copied line counts lived here and went stale (11 of 24 listed files were
gone by 2026-09-20); the statements now live next to the code and the checker
keeps them honest. One command answers every rule in this section -- it is the
CI gate (`deploy.yml`; kinds in `tools/maintainer_lib/gate.py`), so run it
before you push:

```text
py -3 tools/maintainer_checks.py --gate --base origin/master
```

### 2.1 Where code goes

- **Entry points hold wiring only.** `backend/main.py`: app factory, middleware,
  `lifespan`, router registration. `frontend/src/App.tsx`: providers, shell,
  route definitions. Anything else belongs to a module (§2.3 caps both).
- **New code goes where its concept is owned.** `py -3 tools/module_map.py [word]`
  prints what every backend package and frontend folder owns, from the code.
- **Nothing owns it? Make an owner in the same change.** A backend package's
  `__init__.py` opens with a docstring whose first line names what it owns
  (`package_owner_missing`). A frontend folder gets a row in
  `frontend/src/FOLDERS.md` with its ADR 005 kind -- `feature`, `shared` or `app`
  (`folder_owner_missing` / `folder_owner_stale`).
- **Prefer a package to a new top-level `backend/*.py` module.** The backend root
  already holds about a hundred modules; a flat namespace is the hardest place to
  find anything.

### 2.2 Feature boundaries (ADR 005)

- A frontend feature imports another feature only through its barrel
  (`../chart`, never `../chart/barsStore`); `shared` code imports no feature
  internals. A deep import into another feature is a `cross_feature_import`.
- The ones that existed when this rule landed (2026-09-23) are frozen, per file,
  in `tools/maintainer_lib/baselines.json` (no count here -- it would go stale);
  one more fails the gate. The slice has no
  barrel yet? Add an `index.ts` exporting what you need.
- Frozen counts only go down. `--update-baselines` rewrites them to the tree; a
  PR that raises one says why.

### 2.3 File size

A line count is a proxy for "an agent can read this file in one pass and see one
concern". It prompts a judgment; it is not a target. **Never squeeze a file to
fit a number** -- deleting blank lines, joining statements or moving code to an
arbitrary sibling. The old hard 400 made agents do exactly that: on 2026-09-23
ten Python / TS files sat at 395-400 lines, against seven in the fifteen lines
below.

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
| The always-on context: this file + `CLAUDE.md` + every `alwaysApply: true` rule | one byte budget, ratchets down only (ADR 051, `tools/maintainer_lib/always_on.py`) | `always_on_budget` (gate); `always_on_growth` (advisory) |
| Tests | exempt | -- |

**Stating the reason:** one line in the file's first 40 lines, next to what the
file owns:

```python
"""Scanner discovery.

maintainer: one-concern the never-leak-a-scanner-slot invariant must live in one place
"""
```

A reason names the one invariant or state the file owns. "Legacy" or "too big to
split now" is not a reason -- split it, or leave the advisory finding and open a
`deferred` issue. **Growth** is judged against `--base` (in CI, the PR's target
branch); a new file over 400 counts as growth.

**Logical lines** exclude imports, comments and blank lines, so an entry point
is capped on the wiring it holds rather than on how many providers it imports
(`tools/maintainer_lib/sizes.py`). No counts are maintained here: a hand-copied
number goes stale (#393). `py -3 tools/maintainer_checks.py --json` ->
`logical_line_counts`, and the human report lists every oversize file.

### 2.4 Refactoring Protocol

When you split a file or move a function out of an oversize one:

1. **Move** it to the module that owns its concept (§2.1).
2. **Import** it back in the original file if still referenced there.
3. **Do NOT leave the old copy** behind.
4. **Update all callers** in the same commit.
5. **Never make a monolith worse.** If you're adding to `main.py` or `App.tsx`, extract first.
6. **Split along a seam** -- one concern per file -- never at an arbitrary line to pass a check.

---

## 3. 📐 Data Schema (Confirmed)

Every confirmed wire and persisted shape lives in `architecture/schema/`, one file per domain. They carry the same force as this file: read the domain's file before changing a route, a socket frame or a persisted file it owns, and change the file first, in the same commit (Invariants #1 and #5). `.cursor/rules/schema-docs.mdc` points at it when you edit the owners.

| Subsection | File |
|---|---|
| Capture / replay truth (issues #316, #317) | `architecture/schema/recording-and-replay.md` |
| Replay progress and capture fidelity (#321, #337) | `architecture/schema/recording-and-replay.md` |
| Recording persistence and coverage (operator decision, 2026-09-21) | `architecture/schema/recording-and-replay.md` |
| Recorded depth in historical replay (#309) | `architecture/schema/recording-and-replay.md` |
| The replayed session's previous close (#542) | `architecture/schema/recording-and-replay.md` |
| Massive flat files in Sim replay (ADR 046, operator ask 2026-10-06) | `architecture/schema/recording-and-replay.md` |
| Agents find stock-days and show them in the Sim (ADR 050, operator ask 2026-10-06) | `architecture/schema/agent-desk.md` |
| Desk diagnostics (ADR 021) | `architecture/schema/desk-ops.md` |
| Which backend answers (operator report, 2026-09-24) | `architecture/schema/desk-ops.md` |
| Who may reach the API: Host names and socket origins (security alerts, 2026-10-09) | `architecture/schema/desk-ops.md` |
| Where Nova keeps its data (operator ask, 2026-09-24) | `architecture/schema/desk-ops.md` |
| Why the Gateway needed a phone login; premarket evidence (#14) | `architecture/schema/desk-ops.md` |
| Scanner rows and HOD Momo alerts on the wire (QA batch, 2026-09-22) | `architecture/schema/scanner.md` |
| Float credibility and short-interest dates (#532) | `architecture/schema/scanner.md` |
| Scanner leaderboard: recorded, reconstructed, played back (ADR 023, operator decision 2026-09-22) | `architecture/schema/scanner.md` |
| Setup scanner and tape gate (ADR 022) | `architecture/schema/setups.md` |
| The flat top counts its touches (ADR 031 amendment, operator ask 2026-10-06) | `architecture/schema/setups.md` |
| The 5-minute flat top (ADR 031 amendment, operator ask 2026-10-06) | `architecture/schema/setups.md` |
| One row per trigger (ADR 022 amendment, 2026-10-02) | `architecture/schema/setups.md` |
| Too thin to trade (ADR 022 amendment, operator decision 2026-10-01) | `architecture/schema/setups.md` |
| The 5-minute chart on a 1-minute setup (trial T8, operator decision 2026-09-30) | `architecture/schema/setups.md` |
| The 5-minute setups (operator decisions 2026-09-30) | `architecture/schema/setups.md` |
| The tape flow score and the flush exit (ADR 034, operator ask 2026-09-24) | `architecture/schema/setups.md` |
| Signal trials (ADR 041, operator decision 2026-09-30) | `architecture/schema/setups.md` |
| The bot's read on one stock (ADR 036, operator ask 2026-09-24, #598) | `architecture/schema/stock-read.md` |
| Setups that ended stay on the chart, and what price did next (ADR 036 amendment, operator ask 2026-09-29) | `architecture/schema/stock-read.md` |
| The day's levels: support and resistance on the charts and in the plan (ADR 036 amendment, operator ask 2026-09-30) | `architecture/schema/stock-read.md` |
| Who trades the stock (ADR 037, operator ask 2026-09-24, #604, #606) | `architecture/schema/stock-read.md` |
| Managing a trade you hold (ADR 036 / 037 amendment, operator ask 2026-10-01) | `architecture/schema/stock-read.md` |
| Catalysts (ADR 024) | `architecture/schema/catalysts.md` |
| Performance recorder (ADR 026) | `architecture/schema/performance.md` |
| The operator's focus and the book watcher (ADR 033, operator ask 2026-09-24) | `architecture/schema/book-watch-and-luld.md` |
| LULD bands on Level 2 (ADR 047, operator ask 2026-10-06) | `architecture/schema/book-watch-and-luld.md` |
| The trading screen is always recorded (ADR 035, operator decision 2026-09-24) | `architecture/schema/screen-and-clips.md` |
| The desk draws with the graphics card (operator decision 2026-10-05, #707) | `architecture/schema/screen-and-clips.md` |
| Share clips (ADR 039, operator ask 2026-09-29) | `architecture/schema/screen-and-clips.md` |
| Watchlist rows (operator decision 2026-09-23) | `architecture/schema/scanner.md` |
| Bot playbook and the read-out gate (ADR 027, operator decision 2026-09-23) | `architecture/schema/bot.md` |
| One Bots page (ADR 044, operator decisions 2026-10-01) | `architecture/schema/bot.md` |
| The bot trades a Sim replay (ADR 052, operator ask 2026-10-09, #814) | `architecture/schema/bot.md` |
| Release notes and the update notice (operator ask, 2026-09-23) | `architecture/schema/desk-ops.md` |
| Filing an issue from the desk (operator ask, 2026-09-24) | `architecture/schema/desk-ops.md` |
| Setup templates, the eyes' journal and replayed eyes (ADR 029, operator ask 2026-09-23) | `architecture/schema/setups.md` |
| Practice venues and fills (ADR 019, ADR 020) | `architecture/schema/recording-and-replay.md` |
| Sim at now is live -- the live edge (ADR 020 amendment, operator decision 2026-09-21 evening) | `architecture/schema/recording-and-replay.md` |
| Who may arm the desk (ADR 018 amendment, operator decision 2026-09-23) | `architecture/schema/execution.md` |
| Account identity on `/api/ibkr/status` (operator ask, 2026-09-21) | `architecture/schema/execution.md` |
| Prints that set a price (operator report, 2026-09-23) | `architecture/schema/market-data.md` |
| The tape archive never stops writing (operator report, 2026-09-24) | `architecture/schema/market-data.md` |
| When IBKR data stops arriving (#672, #673, operator report 2026-10-01) | `architecture/schema/market-data.md` |
| A Level 1 line IBKR refused (operator report 2026-10-05) | `architecture/schema/market-data.md` |
| When one tape line goes silent (#722, operator report 2026-10-05) | `architecture/schema/market-data.md` |
| Orders refuse a stale view; the market path stays real time (ADR 045, operator report 2026-10-05) | `architecture/schema/execution.md` |
| The trading session ends at 20:00 ET (operator report, 2026-10-01 23:33) | `architecture/schema/market-data.md` |
| Chart bars say when IBKR history stopped answering (ADR 012, #555) | `architecture/schema/market-data.md` |
| The forming candle's volume (operator report, 2026-09-24) | `architecture/schema/market-data.md` |
| Why it's moving (ADR 028, operator ask 2026-09-23) | `architecture/schema/stock-read.md` |
| The Cryptos page (ADR 040, operator ask 2026-09-30) | `architecture/schema/cryptos.md` |
| Symbol directory for the header search (operator ask, 2026-09-23) | `architecture/schema/desk-ops.md` |
| The operator's watch list and its toasts (operator asks, 2026-09-23 and 2026-09-24) | `architecture/schema/desk-ops.md` |
| The close-of-day reminder (operator ask, 2026-10-01) | `architecture/schema/desk-ops.md` |
| Short selling (ADR 048, operator decisions 2026-10-01 to 2026-10-07; #778) | `architecture/schema/short-selling.md` |
| The short setups on the scanner (ADR 049, step 4 of #778) | `architecture/schema/short-selling.md` |
| The bot trades both sides (ADR 049, step 5 of #778) | `architecture/schema/short-selling.md` |
| Live readiness: the Live short proof and Live's day cover (ADR 048 step 6, #778 §7) | `architecture/schema/short-selling.md` |
| Execution command (ADR 007 — sole broker mutation entry) | `architecture/schema/execution.md` |
| Execution venue provenance (#713) | `architecture/schema/execution.md` |
| Live order state: orderRef, whyHeld, reconnects, IBKR's own events (audit 2026-10-09) | `architecture/schema/execution.md` |

### CI scope output

`tools/ci_scope.py` classifies changed repository paths into boolean JSON fields:
`{"backend": true, "frontend": true, "e2e": true, "desktop": true, "source": true, "dependencies": true}`.
GitHub job outputs serialize these booleans as `true` / `false`. Unknown paths,
unavailable diffs, and manual runs select full verification. See `.cursor/rules/ci-scope.mdc`.

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

Capture market projections preserve missing facts: print-only rows have null
bid/ask/sizes and the replay's own previous close (null when nothing records
one, #542); depth is empty without recorded books; daily OHLC
is null unless a replay source provides it. Loading, failed, and pre-first-event
capture selections have no market data to fall back to -- there is no synthetic
instrument (ADR 019), and `replay_source` is `none` when nothing is loaded.

---

## 4. 🔗 Integrations & Services

| Service | Purpose | Status |
|---------|---------|--------|
| Alpaca API | News + listing metadata (not price discovery) | ✅ Verified |
| IB Gateway (local) | Scanner discovery + market data + optional orders | ✅ Verified |
| Web UI (Localhost / Desktop) | Delivery dashboard for gappers | ✅ Verified |
| yfinance | Fundamental data (float, short interest, etc.) | ✅ Verified |
| CoinGecko, Coinbase Exchange, alternative.me, Hyperliquid, DefiLlama, Deribit (public, keyless) | The Cryptos page's crypto reference data (ADR 040): read-only, each labelled on the page, never a stock or order source | 🧪 Fixture-tested |

---

## 5. 📋 Behavioral Rules (Enforced)

### Advisory verification policy (owner override, 2026-09-20)

All CI and local verification is advisory for delivery. Ready PRs may merge while
checks are running, or after failed/cancelled/missing checks. Do not wait for tests,
builds, or Desktop pack before merging. Report observed results truthfully; red
checks remain visible and can be fixed later. This policy supersedes older
verification-before-merge wording in this constitution and its delivery rules.
Drafts, `do-not-merge`, forks and actual conflicts retain their existing holds.
Master protection blocks force-push and deletion (including admins), with **no
required status checks**. Trading runtime gates, opt-ins and `auto_live` NO-GO
remain unchanged. Conditional coverage is specified in `.cursor/rules/ci-scope.mdc`.

- **Market data / trading:** Scanner and prices are IBKR-only (see `single-market-data-feed.mdc`). Alpaca is news/listing metadata only. The Cryptos page (ADR 040) shows the crypto market from labelled public reference sources (rule 13 there); it is never a scanner, stock chart, order or bot source. Orders are allowed only via gated `backend/ibkr/` (Invariant #7). Gateway port default is live (4001); the paper Gateway (4002) is legacy, by hand only, never an automatic fallback (ADR 020). Spend stays gated; `auto_live` remains NO-GO. Header Live / Paper / Sim are **venue** pills (ADR 020): **Live** places to IBKR; **Paper** is Nova's practice account on the live feed -- fake money, full live data, fills estimated locally, never an IBKR place; **Sim** replays a **real recorded or downloaded session** and fills locally on a scratch account that unwinds when the playhead is scrubbed back (ADR 019); at the **live edge** -- the Sim clock following the wall clock on today's date, not paused, not scrubbed, no past day loaded (`live_edge` on the clock payload and on `/api/ibkr/status`) -- a Sim tab shows the live IBKR feed exactly as a Paper tab does and the scratch account fills against the live reference, and scrubbing back leaves the edge for the loaded replay (today's Session Record when one exists, a stated absence otherwise; ADR 020 live-edge amendment). The IBKR paper Gateway (4002) is legacy with no desk button -- `POST /api/ibkr/gateway-mode {"mode":"paper"}` by hand is its only door. The venue never changes the bot: operator and bots are gated identically everywhere, and a bot fires only on an allowlisted symbol whose depth line the backend itself holds (`409 BOT_NO_DEPTH_LINE` otherwise); after a Sim rewind (`practice_rewind`) bots re-read the ledger. On a Sim replay Nova's own bot trades the loaded replay's Sim eyes triggers on the playhead's clock, its line the replay's own book, and goes back with a rewind (ADR 052). There is no synthetic instrument: a Sim desk with nothing loaded is empty off the live edge, and live at it. `NOVA_BROKER=sim` is bootstrap only. Switching to Live restores the IBKR paths.
- **Desk venue vs spend arming (ADR 018, #302):** two facts with opposite lifetimes, never one dial. The **venue** (Paper / Live / Sim) is durable -- `sim/mode.py` owns `desk-venue.json` under the operator cache (`schema_version`, unknown version refuses loud), and it wins over the `NOVA_BROKER` bootstrap default. **Spend arming never survives a process start**, in any venue: `IBKR_ORDERS_ENABLED` / `IBKR_LIVE_TRADING_CONFIRMED` say this desk is *permitted*, the runtime latch in `ibkr/safety.py` says it is currently *armed*, and a place needs both. Arming is an explicit act through one door, `POST /api/ibkr/arm`, and one rule in `ibkr/safety.arm` (ADR 018 amendment, operator decision 2026-09-23): **Live arms only with the operator's PIN, checked by the backend** against a hash in `.env` (`NOVA_LIVE_ARM_PIN_HASH`, set with `py -3 tools/set_live_arm_pin.py`; none set = Live refuses to arm); **Paper and Sim arm with no PIN** -- the padlock in one click, a bot through the same endpoint. The latch is stamped with the venue it was armed on and reads disarmed on any other, so a practice arm is never a Live arm. Never an `.env` edit, never inferred from a connect, reconnect or self-heal, and never re-armed by any automatic path. A venue change disarms. Protective sources (`flatten`, `kill`, `cancel_working`) and cancel are exempt: a disarmed desk must always be able to get flat. Only the *settled* venue persists -- an in-flight gateway-mode switch stays process-local in `gateway_heal.py` so ADR 013's unattended reconnect is unchanged.
- **Market Open Halt**: The gapper dashboard stops updating its data feed once the market formally opens.
- **Configurable**: API keys and base URLs must be configurable via UI.
- **PR-first delivery after every task:** Code, config, CI, security, and rule changes MUST follow §5.1 (clean start from `origin/master`, ready PR finish line). Direct `master` pushes are limited to status-only operations or explicit user instruction. Complete `.github/pull_request_template.md`, link the issue truthfully (`Closes` only for full completion; `Refs` for partial work), verify, commit, push the branch, and open a **ready** (non-draft) PR. **GitHub Actions merges ready PRs** without waiting for CI (`tools/pr_delivery.py`). Do not wait for the human to say merge. Draft or label `do-not-merge` is the hold, and only under §5.1. After that PR is merged or closed, **delete the head branch** (`git fetch --prune` then `py -3 tools/stale_pr_branches.py`; use the guarded `pr_delivery.py delete-closed --ref <branch>` only for a verified safe tip). GitHub `delete_branch_on_merge` plus `.github/workflows/pr-delivery.yml` are the backup sweep. Never leave merged or superseded branches on origin. Never delete `master` or a branch that still has an open PR. **Master branch protection** (no force-push, no deletion, no required CI checks) is the required GitHub setting; verify with `py -3 tools/master_branch_protection.py check` and do not claim it exists unless that command exits 0. Public Nova unlocks that setting on GitHub Free. A private personal repo still needs GitHub Pro. The public source home is `aaltaay/Nova`. `aaltaay/Nova-public` is a private archive.
- **Backlog work packages:** The backlog is organised into ranked work packages -- one **GitHub milestone** per package, every open issue in exactly one. Current narrative in GitHub Issues/milestones; authored package configuration in `knowledge/backlog-packages.json`; milestones are its projection (`py -3 tools/backlog_triage.py sync`). Agents asked "what's next" run `py -3 tools/backlog_triage.py next` -- it returns one package, one PR batch, and the acceptance criteria. **Batch related issues into one reviewable PR**; do not open a PR per issue. New issues get a package plus the `deferred` / `P0`-`P3` / kind / `domain:*` labels -- `backlog_triage.py check` reports the gaps, and `.github/workflows/backlog-triage.yml` sweeps weekly and fails when any remain. There is no pinned rollup issue -- `py -3 tools/backlog_triage.py report` answers "what is the state of the backlog" on demand, from GitHub. Gated work needs an operator decision -- record the question on the issue, never guess the policy.
- **Nova Delivery board:** Canonical project is https://github.com/users/aaltaay/projects/1 (user project number `1`, owner `aaltaay`, id `PVT_kwHOAXJK5M4Ab7Vq`). Do not recreate it. `.github/workflows/nova-delivery-project.yml` adds new issues and same-repo PRs. Agents must also run `gh project item-add 1 --owner aaltaay --url <html_url>` when the token has `project` scope, and default Status to Todo unless already In Progress. Priority stays on labels `P0`..`P3`. Classic `GITHUB_TOKEN` and the Cloud Agent GitHub App typically lack `project` scope; owner `gh` as `aaltaay` can mutate; Actions uses repo secret `NOVA_PROJECT_TOKEN`. On 403, report the limitation -- never claim the item exists.
- **Next-move footer** (replaces the Better ask / Follow-up ask paragraphs, 2026-09-20): every substantive user-facing reply ends with an optional one-sentence **Better ask:** and a numbered **Next move** menu the operator answers with a digit. Lanes in this order: `[thread]` (continue this reply), `[ship]` (the human step that gets Nova out the door), `[backlog]` (the batch `backlog_triage.py next` would hand out), `[decide]` (the operator decision that unblocks the most issues). Exactly one line is starred; every line is a pasteable prompt. The `[ship]` / `[backlog]` / `[decide]` lines are copied from `py -3 tools/next_moves.py seed` (the session brief injects it), never from memory. Never offer `auto_live`, a live-gate flip, a claimed or gated batch, or a per-issue PR. Template, failure / question modes, skip rule: `.cursor/rules/next-move-footer.mdc`; check a draft with `py -3 tools/next_moves.py lint`. Specialist subagent reports keep the Lifecycle line instead. Skip only trivial exchanges (pings, tiny confirmations, status polls) -- never pad.

### 5.1 Session lifecycle (Deliver)

**Branch preservation (#369):** A closed PR's branch name is never proof that its current tip is disposable. Cleanup must preserve and report tips not contained in `origin/master`; this safety rule overrides head-deletion and clean-clone requirements below. Squash-only or closed-unmerged tips require explicit review, not automatic deletion. Remote deletion must compare-and-delete the verified SHA so a concurrent push survives. A later `git push` reporting `* [new branch]` may have recreated an already-merged head: check PR state and move new work to a fresh branch.

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
7. Keep existing rules: Actions auto-merge when available; `Closes` vs `Refs`; delete the head after merge or close; all verification advisory.
8. **Leave it clean.** No modified, staged or untracked files, no `git stash`, no leftover scratch worktree; `py -3 tools/repo_hygiene.py status` is OK for what you own. Stage explicit paths, never `git add -A`. The Claude Code Stop hook (`repo_hygiene.py stop-gate`) refuses the first dirty stop; `repo_hygiene.py fix` and the nightly `NovaRepoHygiene` task reclaim merged local branches and stale worktrees (`workspace-hygiene.mdc`).

Always-on copies: `.cursor/rules/commit-push-deploy.mdc`, `.cursor/rules/github-delivery.mdc`, `.cursor/rules/workspace-hygiene.mdc`, `.cursor/skills/github-delivery/SKILL.md`.

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
- **The money path fails the gate on silence.** In `backend/execution/`,
  `backend/ibkr/`, `backend/practice/`, `backend/sim/`, `backend/kill_switch/`,
  `backend/bot/` and `frontend/src/ibkr/` an `except …: pass`, an
  `except …: return []` / `{}`, or an empty `catch` is a `*_money` finding, because
  a desk that swallows an order, position or account read is lying about its
  state. Log it, turn "unknown" into a stated unknown (never "empty", "flat" or
  "abandoned"), or -- when silence is the correct behavior (a timeout that ends a
  wait, an idempotent `list.remove`, a parse that falls through to the next
  format) -- say so at the site:
  `except asyncio.TimeoutError:  # maintainer: allow-swallow the timeout ends the wait`.
  File-wide allowlists never apply there (`tools/maintainer_lib/swallow.py`).
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

### 6.7 Lint

- `ruff check backend` is part of `py -3 tools/maintainer_checks.py --gate` (`tools/maintainer_lib/lint.py`),
  so a lint finding is caught before the push. The rules are in `backend/ruff.toml`, and the version is
  the `ruff==` pin in `backend/requirements-dev.txt`, which CI installs. If ruff is missing or cannot
  finish, the gate fails: an unrun lint is never a pass.
- CI's Backend tests job runs pytest even when its Ruff step fails, so a lint finding never hides the
  test results. Before this, five findings on master skipped pytest on every backend PR (PR #603).

---

## 7. 📝 Documentation Requirements (Enforced)

### 7.1 CHANGELOG.md -- RETIRED. The PR body is the record.

There is no changelog. `CHANGELOG.md` is archived under `docs/archive/` and is not
maintained, generated, or required. Do not recreate it, and do not add a
changelog entry, fragment, or collation step to any workflow.

- **A PR that changes behavior carries its entry in its own body:** **What** /
  **Why this approach** / **Verified by**, per
  `.github/pull_request_template.md`. That is the record, and the merged PR is
  its permanent home.
- **No PR?** (direct push, ops diagnosis, audit conclusion) -- write the
  narrative under `knowledge/task-log/` (§7.2b). Nothing else is needed.
- **Why retired:** the entry already exists in the PR body. A second generated
  copy added a file nothing read, a workflow that could silently fail to open
  its PR (it did -- master drifted 11 PRs behind without anyone noticing), and a
  `merge=union` attribute to stop the paperwork causing merge conflicts (#344).
  Removing the mirror removes all three.
- Existing history is untouched and stays readable in the archive.

### 7.2 Bug-fix evidence

Record the symptom, cause, fix, and verification in the relevant PR or issue.
Keep useful regression tests. Do not create a separate problem ledger or footer.

### 7.2b Task narrative (PR body first, `knowledge/task-log/` when there is no PR)

- Every completed material task (parent or specialist) needs a reasoning narrative. **Default home is the pull request body** -- fill `.github/pull_request_template.md`: What / Why this approach / Verified by / Related issue.
- No PR (direct push, ops diagnosis, audit conclusion)? Append a dated file under `knowledge/task-log/` and prepend `INDEX.md`. Scaffold: `py -3 tools/task_log_new.py --slug <kebab> --title "…"`.
- **Why this approach** is mandatory in either home -- capture tradeoffs and rejected alternatives, not only the diff. Never write both homes for one job.
- Rule: `.cursor/rules/task-log.mdc`.
- Lifecycle footer includes `task_log=<PR URL>|<path>|skipped|n/a` and `deferred_log=<#NNN or D-NNN>|none|skipped|n/a`.

### 7.2c Deferred tracker (GitHub Issues)

- **Mandatory for every agent** (parent + all specialists). Rule: `.cursor/rules/deferred-log.mdc`. Source of truth is GitHub Issues labeled `deferred` -- https://github.com/aaltaay/Nova/issues?q=is%3Aissue+label%3Adeferred . `docs/deferred-log.md` is the how-to, not the to-do.
- **Before any fix:** run `py -3 tools/deferred_log.py status` (alias `priorities`) and search open `deferred` issues. If an existing issue already covers the ask, work from that issue (honor `parked` / Unblock / Next). Do not start a parallel fix that ignores it. When the human asks "what's on the to-do / what's missing / priorities," that command is the answer.
- Open (or comment on) a GitHub issue after parking a known bug or a feature you will not build this session -- same session.
- Close an issue only when its entire stated scope is complete and verified. Partial fixes use `Refs #NNN`, get an evidence comment, and leave the issue open. Follow `.cursor/skills/github-delivery/SKILL.md` for owner, Project, Milestone, relationship, Development-link, and close-reason rules.
- **Durable id is the GitHub issue number (`#NNN`).** Title an issue plainly -- no `D-NNN` prefix, no allocation step. GitHub mints `#NNN` atomically, so two agents filing at once can never collide. `D-NNN` is a **legacy alias**: the ~90 issues that carry one keep it, the tooling still parses and displays it, and history (`CHANGELOG.md`, `PROBLEM_LOG.md`, test docstrings) is never rewritten. Never mint a new `D-NNN`.
- Labels: `deferred` + `P0`..`P3` + `bug`/`enhancement`/`decision` + `domain:<name>`. Body fields: Kind, Severity, Effort, Why parked, Blast radius, Unblock, Next, Evidence. Refresh the offline index in the creating PR when convenient; it is a read cache only, and no correctness now depends on it.
- Lifecycle footer **MUST** include `deferred_log=<#NNN or D-NNN>|none|skipped|n/a`. Agent-memory Backlog is not the SSOT. Product-phase NEXT stays in `Nova-Roadmap-Status.md`.

### 7.3 .cursor/rules/

- MDC rules are peers of this constitution. They provide fine-grained, glob-scoped enforcement.
- When logic changes, update or add the relevant MDC rule BEFORE writing code.

---

## 8. 🚀 Run & Deploy

Operator runbook for syncing the trading PC to master, cold-restarting IB
Gateway and arming the unattended premarket: `docs/live-desk-sync.md`.

### Local Dev (Windows)

```text
# From repo root — browser UI:
scripts/windows/Run Nova.bat

# Desktop (Electron + local API sidecar):
scripts/windows/Run Nova Desktop.bat
# or: cd frontend && npm run electron:dev

# Windows installer:
cd frontend && npm run electron:pack

# Or manually:
# Terminal A (backend/): py -3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
# Terminal B (frontend/): npm run dev
# Open: http://localhost:5173
```

### Deploy

- **Backend:** local only right now -- no cloud host (not Railway, not another PaaS). Run via `scripts/windows/Run Nova.bat`, Desktop sidecar, or local uvicorn on `127.0.0.1:8000`.
- **Public site:** not in this repo. `nova.altaystudio.com` is built from [`aaltaay/nova-site`](https://github.com/aaltaay/nova-site), which owns the page, its screenshots, the AI-in-trading digest and the Vercel deploy. Nothing here builds, deploys or tests it.
- **Frontend (app UI):** local Vite / Desktop only (`http://localhost:5173`). Do not host the trading SPA on the public domain: a public page that runs the desk could reach a visitor's own Nova on `127.0.0.1:8000`. **One exception (ADR 043):** the demo build (`npm run build:demo`), the desk on Nova Marketing Sample Data with its backend inside the page, is hosted at `nova.altaystudio.com/demo/`. It has no path to any backend: `fetch`, `WebSocket` and `sendBeacon` are replaced before the app loads, every API call, loopback request and socket is answered in the page, and nothing is ever sent.
- **Desktop:** Electron + local API sidecar. A "Starting Nova" window (`frontend/electron/startupSplash.mjs`) is on screen from launch until the desk window shows, naming the step (looking for, starting or connecting to the local engine, loading the desk); closing it calls the launch off. **Installer only** (#347): local pack produces `frontend/release/Nova-Setup-vNNN.exe` plus `latest.yml` + `.blockmap` -- the in-app update feed. The portable EXE is retired; it could never self-update. Application-affecting PRs run the advisory `Desktop pack` GitHub Actions job, which uploads those three files; docs/site-only PRs skip packaging under `.cursor/rules/ci-scope.mdc`. Every commit that lands on master gets its `vNNN` tag, and an application-affecting one also gets a GitHub Release (see below).
- **Releases are automatic (operator decision, 2026-09-23 -- supersedes #347's tag-only publishing):** every commit that lands on master -- a human push, or PR delivery's dispatch after an Actions merge (#346) -- is tagged `vNNN` (its commit count) by `Desktop pack`, which tags the commit through the API. An application-affecting commit packs the installer and publishes it as the `vNNN` GitHub Release with the installer, `.blockmap` and `latest.yml`; a docs/site-only commit gets the tag and no Release, because a Release without `latest.yml` would break the update feed. A Release is marked latest only when no higher `vNNN` Release exists, so a slow run never rolls the feed back. The tag is pushed with `GITHUB_TOKEN`, so it starts no second run. A hand tag still works: `py -3 tools/bump_version.py --ensure-tag --push-tag` on an up-to-date `master`, and the pack refuses a tag that is not that commit's revision. Re-run one with `gh workflow run desktop-pack.yml --ref vNNN`. GitHub's Source code zip/tar is automatic and is not the app.
- **In-app updates (#347):** the installed desk checks GitHub Releases shortly after launch. A newer release is **offered, not fetched** (operator ask, 2026-09-23): a notice under the header names it, with the release notes of every release since the installed one, and asks **Update** / **Later**. Nothing downloads before Update; the notice then follows the download to **Restart to update** / **Later**. It never installs or restarts on its own -- not on quit, not on a timer -- and the notice never takes keyboard focus, so a hot key still reaches the desk. From the Restart click until the new version's window is up, an "Updating Nova" window (`frontend/electron/updateSplash.ps1`, its own PowerShell process, since the installer ends every Nova.exe) names the step -- closing, installing, starting -- and says so if Nova does not reopen; the silent installer otherwise leaves nothing of Nova on screen for most of a minute. Later hides it for that version until the next launch or Help > Check for Updates; a download the operator chose that stops is resumed by the next check without asking again. **Update takes the newest release** (operator report, 2026-09-24): a notice whose release was found more than a minute before the click asks GitHub again first and downloads what is newest then, so a release that shipped while the notice waited out trading hours is not missed (`frontend/electron/newestRelease.mjs`); that check never shows on the notice, and if it fails the release on offer downloads as before. A window that cannot show the notice (an error page) gets the same two questions as dialogs. While the desk stays open it checks again every two hours, but never 07:00-16:00 ET on a weekday (operator decision, 2026-09-23): a re-check neither downloads nor asks in trading hours, because the 150 MB download shares the desk's link with the market data. A release a re-check finds as trading starts waits in Help > Update to vNNN and is offered after 16:00; the launch check and Help > Check for Updates are not held. The first launch of a new version shows **What's new** -- a floating card with the notes of every release the update brought -- until the operator closes it; Help > What's New reopens the latest releases. `NOVA_UPDATE_CHECK=0` (desk `.env` or process env) turns the automatic checks off; Help > Check for Updates still works. Builds are unsigned, so SmartScreen warns on a fresh download.
- **Release notes (operator ask, 2026-09-23):** every Release's body is written by `Desktop pack` from the commit that made it (`tools/release_notes.py`): the PR title, and the first paragraph of its `## What` written for the operator (quotes of an operator report, tables and engineering bullets are skipped; a list the paragraph introduces, or a list of bold lead-ins, comes along). The schema is in `architecture/schema/desk-ops.md`, "Release notes and the update notice".
- **The installer download is resumable (2026-09-23):** electron-updater checks and installs, but Nova fetches the installer itself (`frontend/electron/updateDownload.mjs`) in 8 MB Range chunks, each retried on its own (1 s up to 2 min, about 4 min per chunk). What arrived is kept across failures and desk restarts under `%LOCALAPPDATA%\nova-updater\nova-partial\` -- `<installer>.part` plus `<installer>.part.json` `{schema_version: 1, version, sha512, size}`, discarded when the release, size or schema changes or the finished file fails the release sha512. The verified file goes into electron-updater's `pending` cache with its `update-info.json`, and electron-updater hashes it again before it offers Restart to update. A download that gives up reads "Download of vNNN stopped at N% -- Resume" and Resume continues from the kept part; an installer already downloaded (Later, then a restart) is not fetched again. Every update line is also written to `%APPDATA%\nova\logs\update.log` (rolls at 1 MB). Why: a link that corrupts a TLS record every few dozen MB made electron-updater's one-shot 150 MB download fail every time (`net::ERR_SSL_PROTOCOL_ERROR`).

---

## 9. 🔄 Self-Annealing Protocol

When ANY error occurs during a task:

1. **STOP** — Do not apply a band-aid.
2. **Analyze** -- Search relevant GitHub issues/PRs and run `py -3 tools/deferred_log.py status` (GitHub Issues labeled `deferred`) for prior matching entries. If an open/parked issue already covers it, work from that issue (or leave it parked) -- do not start a parallel fix.
3. **Root Cause** — Identify the actual cause, not the symptom.
4. **Patch** — Fix the root cause in the correct module (not in `main.py`).
5. **Test** — Verify the fix works (build, run, or test).
6. **Update SOP** -- Document the cause and fix in the PR/issue (if fixed) or open/update a GitHub Issue labeled `deferred` (if parked), and update relevant MDC rule if needed.
7. **Deliver** -- follow §5.1: verify, commit on the focused branch created from `origin/master`, push, and open a **ready (non-draft)** PR. The PR URL is the finish line. Use `Closes #NNN` only when the full issue is complete; otherwise use `Refs #NNN`. After the PR is merged or closed, confirm the head is gone (`stale_pr_branches.py`; the guarded delete command only for a verified safe tip).

---

## 10. 🚨 Compliance Audit (Current Violations)

No open constitution compliance rows. `architecture/` (ADRs 001–009) and automated tests (pytest + Vitest) exist. Product/security open work lives in `Nova-Roadmap-Status.md` and `Security-Status.md`. Live-doc drift is gated by `py -3 tools/doc_invariants.py` (CI).

---

## 11. 🔧 Maintenance Log

Moved to `architecture/maintenance-log.md` (newest first). A change to this file or to `architecture/schema/` adds its row there in the same commit.

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
| **tester** | “Use the tester subagent to verify …” | `agent-tester.canvas.tsx` |
| **maintainer** | “Use the maintainer subagent to audit the repo” | `agent-maintainer.canvas.tsx` |
| **security** | “Use the security subagent to audit the repo” | `agent-security.canvas.tsx` |
| **docs** | “Use the docs subagent to review documentation” | [nova-home](canvases/nova-home.canvas.tsx) |



---

## 12. Cursor Rules (.mdc files)

Live rule bodies live only under `.cursor/rules/*.mdc`. Do **not** paste full rule text into this file (it double-loads and drifts). Do **not** create a root `.cursorrules` file -- scoped `.mdc` frontmatter is strictly better.

**What earns always-on (ADR 051):** a rule loads on every request only when an agent editing *any* file -- a README typo included -- could lose money or break delivery without it. Everything else gets `globs` or stays agent-requested. One law has one home; the other files hold a line and a link. A rule a script enforces is a pointer to the script. A rule says what to do; the incident story lives in the ADR or on the issue. `maintainer_checks.py` caps the set's byte total (`always_on_budget`) and the session brief prints it.

### Index (name -- purpose -- attachment)

**Always-on** (every request):

- `constitution.mdc` -- read AGENTS.md; hierarchy; common violations + context economy
- `specialist-routing.mdc` -- zero-hop default; specialists opt-in only
- `single-market-data-feed.mdc` -- IBKR-only prices; the 13 feed rules as headlines (mechanics and anti-patterns: `single-market-data-feed-catalog.mdc`, glob)
- `ibkr-gateway-login-warning.mdc` -- loud-warn when Gateway needs login/2FA
- `nova-roadmap-continuity.mdc` -- Master Roadmap phase continuity
- `engineering-standards.mdc` -- Tailwind direction, tests, CI, deps, patterns
- `karpathy-guidelines.mdc` -- think / simplify / surgical / verify
- `deferred-log.mdc` -- check GitHub Issues (`deferred`) before any fix; park known bugs/features; to-do via `deferred_log.py status` / `priorities`
- `task-log.mdc` -- reasoning narrative after material work (PR body first; file when no PR)
- `commit-push-deploy.mdc` -- pointer to §5.1 (clean start from `origin/master`, ready PR, delete head) + the deploy step
- `doc-invariants.mdc` -- posture-change same-commit live homes; CI `doc_invariants.py`
- `self-annealing.mdc` -- root-cause fix protocol on any error
- `verification-before-completion.mdc` -- no done/fixed claims without fresh evidence
- `engineering-methodology.mdc` -- soft TDD + plan/interview/doubt/review skill map
- `github-delivery.mdc` -- issue metadata, [Nova Delivery](https://github.com/users/aaltaay/projects/1) board, Actions merge of ready PRs, delete head after merge/close, closure after merge; session gates point to §5.1
- `persisted-state.mdc` -- cache files need owner + invalidation + schema_version
- `workspace-hygiene.mdc` -- never stash; one worktree per task; finish with a clean tree; `tools/repo_hygiene.py status|fix|stop-gate`
- `graphify.mdc` -- vault/decision questions: `py -3 tools/graphify_ask.py query` + savings meter
- `next-move-footer.mdc` -- numbered Next move menu at the end of every substantive reply; seed `py -3 tools/next_moves.py seed`; lint `next_moves.py lint`

**Glob-scoped** (attach when editing matching files; `alwaysApply: false`):

- `backend-modularity.mdc` -- `backend/**/*.py` -- no logic in `main.py`
- `frontend-modularity.mdc` -- `frontend/src/**/*.{ts,tsx}` -- no logic in `App.tsx`
- `file-size-limits.mdc` -- backend + frontend src -- soft 400 with a one-concern reason, no growth without one, 800 ceiling
- `centralized-constants.mdc` -- backend + frontend src -- tunables in domain modules
- `schema-docs.mdc` -- backend, frontend, electron, research -- read and update the owning `architecture/schema/<domain>.md` in the same commit
- `single-market-data-feed-catalog.mdc` -- backend + frontend src -- the full feed law: mechanics of the 13 rules, the ❌ anti-pattern catalog, the module map
- Continuity rules (already glob): `hotkeys-continuity`, `docs-continuity`, `execution-continuity`, `widgets-continuity`, `security-continuity`

**Agent-requested** (name + description always visible; body fetched on demand):

- `browser-testing.mdc` -- web verification / Playwright / agent-browser
- `run-app.mdc` -- how to run/open Nova locally
- `nova-os-continuity.mdc` -- Nova OS engine phases (retired, ADR 025; history)

Karpathy full text: `.cursor/rules/karpathy-guidelines.mdc` (also `.cursor/skills/karpathy-guidelines/`).
Browser testing full text: `.cursor/rules/browser-testing.mdc`.
