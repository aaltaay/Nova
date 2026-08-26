# 2026-08-26 -- DEFERRED_LOG.md for known bugs and parked features

- **Status:** completed
- **Agents:** parent
- **Domain:** docs
- **Related:** `CHANGELOG.md` §2026-08-26 DEFERRED_LOG.md · `DEFERRED_LOG.md` D-001, D-002

## Task

Create one repo-root markdown file for known bugs and parked features, with the same respect and enforcement as `PROBLEM_LOG.md`.

## Goal

Agents write parked work here instead of specialist memory Backlog. A human can open one file, see severity, and decide what to pull next.

## Why it mattered

Agents find bugs mid-task that they cannot fix (too big, wrong job, needs an ADR). Humans ask for features that get parked as complicated. Those notes were dying in agent-memory Backlog, where nobody looks. The operator wanted one honored file.

## What we changed

- Repo-root `DEFERRED_LOG.md` with Open / Closed markers, durable `D-NNN` IDs, and a triage template (Kind, Severity, Effort, Why parked, Blast radius, Unblock, Next, Evidence)
- Always-on `.cursor/rules/deferred-log.mdc`
- Lifecycle `deferred_log=` wired through contract regex, specialist prompts, `subagentStop` hook, AGENTS.md, constitution, self-annealing
- `tools/deferred_log.py status|next-id`; session-start brief lists open P0/P1
- Seeded D-001 (scanner NEWS dead under ibkr) and D-002 (afterhours Gap % == Change %). Removed those two items from market-feed memory Backlog.

## How it works now

Park, do not band-aid. Prepend under `<!-- OPEN_START -->`. Ranked list: `py -3 tools/deferred_log.py status`. Fix later: move the section to Closed, write PROBLEM_LOG if it was a bug. Agent-memory Backlog is scratch. Roadmap NEXT stays in `Nova-Roadmap-Status.md`.

## Why this approach

A peer of PROBLEM_LOG (same Lifecycle field, same constitution severity, same prepend-below-marker habit) beats a new tracker app, a GitHub issues dependency, or a Roadmap parking lot (that file is product NEXT, not a bug queue). Durable IDs beat date-only headings so Lifecycle can say `deferred_log=D-001` after the item moves to Closed. Severity + Effort + Unblock is the minimum a human needs to decide "do this tomorrow" vs "that needs an ADR." Session brief only shouts P0/P1 so P3 polish does not drown the morning.

Rejected: putting this in agent-memory Backlog (user said no). Rejected: folding it into PROBLEM_LOG (that file is closed fixes; mixing open and closed trains agents to skip both). Rejected: Nova-Roadmap-Status parking lot (phase L-Z, not operational bugs).

## Verification

`py -3 -m pytest tools/test_deferred_log.py tools/test_subagent_lifecycle_hook.py tools/test_session_brief_hook.py` and `py -3 tools/agent_contract.py`.

## Follow-ups

None for the log itself. Pull D-001 / D-002 when a session is in that module.

## Keywords

DEFERRED_LOG, deferred-log.mdc, parked bugs, parked features, D-001, D-002, Lifecycle deferred_log
