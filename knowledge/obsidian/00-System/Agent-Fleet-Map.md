# Agent Fleet Map

Durable domain/skill ownership matrix for Nova's agent OS. This is the source table `tools/agent_fleet.py` parses to compute cracks (unowned domains, orphan skills) — keep the `Status` column values exact: `Owned` | `Continuity-only` | `Unowned` for domains, `Owned` | `Ambient` | `Orphan` for skills.

**Owner:** `daddy` (fleet dispatch) jointly with `router` (classification/crack index) and `docs` (general docs hygiene). Update when a domain/skill gains, loses, or changes owner.

Companion: `.cursor/agent-system/registry.json` (machine wiring) · `tools/agent_fleet.py` (crack index) · `.cursor/rules/specialist-routing.mdc` (routing table).

**Mode legend:** `Dispatch` = orchestrates others · `Audit` = report-only · `Implement` = may edit its writable paths · `Research` = read/map only, no product feed into Nova.

---

## Domain ownership

| Domain | Owner | Status | Mode | Notes |
|--------|-------|--------|------|-------|
| Fleet dispatch / orchestration | daddy | Owned | Dispatch | top-of-fleet; may dispatch any specialist; never implements product code |
| Fleet triage / classification / crack index | router | Owned | Audit | report-only Routing card; `agent_fleet.py` |
| Docs, MDC rules, agent prompts, canvases | docs | Owned | Implement | `docs-continuity.mdc`; dashboard = Nova Home |
| Test / build / browser verification | tester | Owned | Implement | pytest / Vitest / Playwright |
| Maintainability / file limits / danger sniff | maintainer | Owned | Audit | read-only, `maintainer_checks.py` |
| Full-repo security posture + SEC-NNN | security | Owned | Audit | `security-continuity.mdc` |
| PR / branch / uncommitted diff security | security-review (Cursor built-in) | Owned | Audit | not a Nova registry agent |
| Warrior Trading authenticated site / Day Trade Dash map | warrior | Owned | Research | research-only snapshot producer |
| HOD Momo scanner data-quality + IBKR feed UML | hod-momo | Owned | Implement | owns `IBKR-Scanner-HOD-Architecture.md` |
| Webull-to-Nova widget capability mapping + selected UI gaps | widgets | Owned | Implement | `widgets-continuity.mdc` |
| Trading execution (`backend/execution/`, ADR 007, latency proof) | execution | Owned | Audit | `execution-continuity.mdc`; dashboard `agent-execution` |
| IB Gateway / discovery ops (login, IBC, port health) | ibkr-ops | Owned | Implement | waiver → `ibkr-gateway-login-warning.mdc` |
| General scanner tables + quote/chart/L2/T&S coherence | market-feed | Owned | Implement | waiver → `single-market-data-feed.mdc`; hand off HOD pool to `hod-momo`, UI to `widgets` |
| News / catalyst pipeline | news | Owned | Implement | `backend/news/` + News UI |
| Backtest product (Phase E) + VectorBT skill cluster | backtester | Owned | Implement | Nova-native runtime; skills research-only |
| Archive / R2 (Phase C remainder) | — | Continuity-only | — | Roadmap-Status Phase C partial |
| Alerts (Phase D) | — | Continuity-only | — | shipped in code, no ongoing steward |
| Reports v2 (Phase F) | — | Continuity-only | — | shipped in code, no ongoing steward |
| Hotkeys / brackets (Phase G/G2) | — | Continuity-only | — | shipped in code, no ongoing steward |
| Nova OS decision engine / control ladder | — | Continuity-only | — | `nova-os-continuity.mdc` + `Nova-OS-Status.md` |
| Master Roadmap phases A–Z / paper shadow ops | — | Continuity-only | — | `nova-roadmap-continuity.mdc` + `Nova-Roadmap-Status.md` |
| Frontend workspace (Phase H panel system) | — | Continuity-only | — | Playwright baseline exists; `widgets` touches Stock View only |
| Knowledge graph (graphify) | — | Continuity-only | — | `graphify` skill + rule; ambient, not agent-owned |

## Skill ownership

| Skill | Owner | Status | Notes |
|-------|-------|--------|-------|
| karpathy-guidelines | — | Ambient | always-apply coding discipline, all agents |
| graphify | — | Ambient | knowledge-graph rebuild/query, all agents |
| backtest | backtester | Owned | Phase E product + offline VectorBT scripts |
| optimize | backtester | Owned | same cluster |
| strategy-compare | backtester | Owned | same cluster |
| vectorbt-expert | backtester | Owned | reference hub for the cluster |
| backtesting-frameworks | backtester | Owned | bias/design guidance, same cluster |
| llm-trading-agent-security | security | Owned | methodology reference for exec-path threat modeling |

## Unmanaged canvas allowlist

Canvases that legitimately live outside the agent registry (do not flag as cracks):

- `nova-home.canvas.tsx` — home_section dashboard (`docs`)
- `context-usage-*.canvas.tsx` — Cursor-generated, not a Nova artifact
- `nova-design-audit.canvas.tsx` — design audit artifact (not an agent dashboard)

Everything else under the canvases directory not in `registry.json`'s `dashboard.canvas` set is a crack (unmanaged canvas) until reviewed by `docs` or absorbed by a specialist.

## Change protocol

1. When a specialist is scaffolded (`tools/create_nova_agent.py --write`), flip its domain row(s) here to `Owned` in the same commit.
2. When a domain keeps burning sessions without an owner, promote it here first (mark `Unowned`/`Continuity-only` with a note), then decide whether to scaffold a specialist.
3. `tools/agent_fleet.py` reads this file read-only — it never rewrites it. Edit by hand or via `daddy`/`router`/`docs` with an explicit ask.
