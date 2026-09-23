# Nova architecture

Authoritative **target architecture** for the Pattern-Driven Architecture maintenance track (Phases 0–13).  
Plan: `maintenance-audit-roadmap_519236d4.plan.md` · Baseline: [`baseline-phase0.md`](./baseline-phase0.md)

Constitution (`gemini.md` / `AGENTS.md`) and `.cursor/rules/*` remain supreme for trading gates, single-feed, and modularity. This folder records **how** we structure code toward those laws.

## Decisions (ADRs)

| ADR | Title | Status |
|-----|-------|--------|
| [001](./decisions/001-modular-monolith.md) | Modular monolith (single FastAPI process) | Accepted |
| [002](./decisions/002-hexagonal-ports-adapters.md) | Selective hexagonal ports/adapters | Accepted |
| [003](./decisions/003-functional-core-imperative-shell.md) | Functional core / imperative shell | Accepted |
| [004](./decisions/004-strangler-facades.md) | Strangler facades + compatibility barrels | Accepted |
| [005](./decisions/005-frontend-feature-slices.md) | Frontend feature slices + workspace shell | Accepted |
| [006](./decisions/006-css-itcss-cascade-layers.md) | ITCSS-inspired CSS + native cascade layers | Accepted |
| [007](./decisions/007-centralized-trading-execution.md) | Centralized trading execution path | Accepted |
| [008](./decisions/008-persistent-ibkr-scanner-rosters.md) | Session-owned persistent IBKR scanner rosters | Accepted |
| [009](./decisions/009-short-entry.md) | Short entry (IBKR short selling) | Accepted |
| [010](./decisions/010-ib-loop-isolation.md) | IB loop isolation (connect-loop + hot/cold) | Accepted |
| [011](./decisions/011-trader-window-desk.md) | Trader desk (extract and dock) | Accepted |
| [012](./decisions/012-local-first-chart-bars.md) | Local-first chart bars + paced historicals | Accepted |
| [013](./decisions/013-ibkr-account-vs-port.md) | IBKR account kind vs listen port vs requested door | Accepted |
| [014](./decisions/014-large-cap-swing-table.md) | Large Cap swing table | Accepted |
| [015](./decisions/015-persistent-chart-drawings.md) | Persistent chart drawings | Accepted |
| [016](./decisions/016-bot-localhost-api.md) | Localhost bot API (brain-agnostic) | Accepted |
| [017](./decisions/017-single-replay-surface.md) | One Historical replay surface and IBKR print source | Accepted; live print fan-out implemented |
| [018](./decisions/018-desk-venue-vs-spend-arming.md) | Desk venue persists, spend arming does not | Accepted; implementation open (#302) |
| [019](./decisions/019-practice-fills-on-replayed-sessions.md) | Practice fills on replayed sessions | Accepted |
| [020](./decisions/020-three-venues-one-feed.md) | Three venues on one feed | Accepted |
| [021](./decisions/021-desk-self-heal.md) | Desk self-heal: what heals itself, what stays a human step | Accepted; backend shipped, UI + supervisor open |
| [022](./decisions/022-scanner-leaderboard.md) | Scanner leaderboard: one row per symbol per minute, recorded and rebuilt; halt log; one ranking; auto-record on free lines | Accepted |

## Rules and maps

- [`dependency-rules.md`](./dependency-rules.md) — allowed/forbidden imports (enforced warning-first in Phase 1, then blocking for new violations).
- [`phase-destination-map.md`](./phase-destination-map.md) — Phase 1–13 module destinations vs layers/slices.

## What Nova will **not** adopt

- Microservices, message brokers, or distributed runtime state
- Framework-wide class/service wrappers that only rename existing calls
- Full-repository Feature-Sliced Design renaming in one pass
- Big-bang CSS Modules or mandatory Tailwind conversion
- A new global event bus for cross-feature chat

## Source references (retrieved 2026-07-16)

| Reference | Use |
|-----------|-----|
| [full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) | App composition, testing, React/Vite, Playwright conventions |
| [python-hexagonal-architecture-template](https://github.com/MatthiasEg/python-hexagonal-architecture-template) | Inward dependency rules, ports |
| [fast-api-reference-project](https://github.com/maxkrivich/fast-api-reference-project) | Composition root, contract tests |
| [feature-sliced/documentation](https://github.com/feature-sliced/documentation) | Vertical slices, public APIs |
| [Steiger forbidden-import rules](https://github.com/feature-sliced/steiger/blob/master/packages/steiger-plugin-fsd/src/forbidden-imports/README.md) | One-way frontend deps |
| [inuitcss](https://github.com/inuitcss/inuitcss) + CSS Cascade Layers | Generic→specific stylesheet order |

These are **references**, not templates to copy wholesale. Nova's single-process IBKR connection, execution gates, workspace shell, and local-first deployment remain authoritative.

## Invariants every structural change must preserve

1. `discovery=ibkr` → IBKR-only prices, bars, depth, tape (no silent Alpaca fallback).
2. `auto_live` rejected; no live orders from maintenance work. All broker mutations go through `execution.service.execute` (ADR 007).
3. Quote / Level 2 / Time & Sales clear on symbol change; ignore stale WS instances.
4. Public HTTP/WS/local-storage contracts stay compatible unless a phase explicitly changes them.
