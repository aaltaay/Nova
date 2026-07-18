# Agent Fleet Map

Durable domain/skill ownership matrix for Nova's agent OS. This is the source table `tools/agent_fleet.py` parses to compute cracks (unowned domains, orphan skills) — keep the `Status` column values exact: `Owned` | `Continuity-only` | `Unowned` for domains, `Owned` | `Ambient` | `Orphan` for skills.

**Owner:** `nova-router` (fleet triage) jointly with `nova-agent` (general docs hygiene). Update when a domain/skill gains, loses, or changes owner.

Companion: `.cursor/agent-system/registry.json` (machine wiring) · `tools/agent_fleet.py` (crack index) · `.cursor/rules/specialist-routing.mdc` (routing table).

---

## Domain ownership

| Domain | Owner | Status | Notes |
|--------|-------|--------|-------|
| Docs, MDC rules, agent prompts, canvases | nova-agent | Owned | `docs-continuity.mdc` |
| Test / build / browser verification | tester | Owned | pytest / Vitest / Playwright |
| Maintainability / file limits / danger sniff | maintainer | Owned | read-only, `maintainer_checks.py` |
| Full-repo security posture + SEC-NNN | security-sentinel | Owned | `security-continuity.mdc` |
| PR / branch / uncommitted diff security | security-review (Cursor built-in) | Owned | not a Nova registry agent |
| Warrior Trading authenticated site / Day Trade Dash map | warrior | Owned | research-only snapshot producer |
| HOD Momo scanner data-quality + IBKR feed UML | hod-momo | Owned | owns `IBKR-Scanner-HOD-Architecture.md` |
| Webull-to-Nova widget capability mapping + selected UI gaps | widgets-agent | Owned | `widgets-continuity.mdc` |
| Fleet triage / specialist+skill dispatch / crack index | nova-router | Owned | this map + `agent_fleet.py` |
| Trading execution (`backend/execution/`, ADR 007, latency proof) | — | Unowned | unmanaged `agent-execution-validation.canvas.tsx`; `docs/trading-execution-validation.md` |
| IB Gateway / discovery ops (login, IBC, port health) | — | Unowned | `ibkr-gateway-login-warning.mdc` covers the warn behavior, not an agent |
| General scanner tables (gappers/gainers/losers L1, not HOD) | — | Unowned | `single-market-data-feed.mdc`; only HOD path has a specialist |
| Quote / chart / L2 / T&S general coherence | — | Unowned | partial touch via `hod-momo` (feed) and `widgets-agent` (UI), no owner for the whole surface |
| News / catalyst pipeline | — | Unowned | — |
| Archive / R2 (Phase C remainder) | — | Continuity-only | Roadmap-Status Phase C partial |
| Backtest product (Phase E) | — | Continuity-only | shipped in code (`backend/backtest/`), no ongoing steward; skills below are orphan |
| Alerts (Phase D) | — | Continuity-only | shipped in code, no ongoing steward |
| Reports v2 (Phase F) | — | Continuity-only | shipped in code, no ongoing steward |
| Hotkeys / brackets (Phase G/G2) | — | Continuity-only | shipped in code, no ongoing steward |
| Nova OS decision engine / control ladder | — | Continuity-only | `nova-os-continuity.mdc` + `Nova-OS-Status.md` |
| Master Roadmap phases A–Z / paper shadow ops | — | Continuity-only | `nova-roadmap-continuity.mdc` + `Nova-Roadmap-Status.md` |
| Frontend workspace (Phase H panel system) | — | Continuity-only | Playwright baseline exists; `widgets-agent` touches Stock View only |
| Knowledge graph (graphify) | — | Continuity-only | `graphify` skill + rule; ambient, not agent-owned |

## Skill ownership

| Skill | Owner | Status | Notes |
|-------|-------|--------|-------|
| karpathy-guidelines | — | Ambient | always-apply coding discipline, all agents |
| graphify | — | Ambient | knowledge-graph rebuild/query, all agents |
| backtest | — | Orphan | Phase E shipped; no specialist owns ongoing VectorBT use |
| optimize | — | Orphan | same cluster as `backtest` |
| strategy-compare | — | Orphan | same cluster |
| vectorbt-expert | — | Orphan | reference hub for the orphan cluster |
| backtesting-frameworks | — | Orphan | bias/design guidance, same cluster |
| llm-trading-agent-security | security-sentinel | Owned | methodology reference for exec-path threat modeling |

## Unmanaged canvas allowlist

Canvases that legitimately live outside the agent registry (do not flag as cracks):

- `nova-home.canvas.tsx` — home_section dashboard (`nova-agent`)
- `context-usage-*.canvas.tsx` — Cursor-generated, not a Nova artifact

Everything else under the canvases directory not in `registry.json`'s `dashboard.canvas` set is a crack (unmanaged canvas) until reviewed by `nova-agent` or absorbed by a specialist.

## Change protocol

1. When a specialist is scaffolded (`tools/create_nova_agent.py --write`), flip its domain row(s) here to `Owned` in the same commit.
2. When a domain keeps burning sessions without an owner, promote it here first (mark `Unowned`/`Continuity-only` with a note), then decide whether to scaffold a specialist (see Phase 3 of `agent_fleet_router_*.plan.md`).
3. `tools/agent_fleet.py` reads this file read-only — it never rewrites it. Edit by hand or via `nova-router`/`nova-agent`.
