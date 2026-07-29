# 2026-07-29 -- Cursor rules token economy (re-scope + AGENTS dedupe)

- **Status:** completed
- **Agents:** parent
- **Domain:** docs
- **Related:** `CHANGELOG.md` §2026-07-29 -- Cursor rules token economy · `problem_log=n/a`

## Task

Audit always-on Cursor rules / AGENTS.md for token waste; re-scope what should not load every request; decide whether a `.cursorrules` file is worth creating.

## Goal

Lower per-request and per-subagent-hop context cost without weakening safety or closeout discipline.

## Why it mattered

Every chat turn and every specialist hop was paying ~30k tokens for rules alone (~119 KB). AGENTS.md §12 also embedded full copies of 11 live `.mdc` rules -- stale and contradictory (e.g. "Run Stock Alert.bat", constants in `backend/constants.py`). That duplication was pure cost plus a drift hazard.

## What we changed

- Replaced `AGENTS.md` §12 (+ trailing Karpathy / Web Verification paste) with a compact attachment-mode index (~28 KB AGENTS vs ~50 KB before).
- Set `alwaysApply: false` on glob rules: `backend-modularity`, `frontend-modularity`, `file-size-limits`, `centralized-constants`.
- Set `alwaysApply: false` (agent-requested) on: `browser-testing`, `run-app`, `nova-os-continuity`, `graphify` (description strengthened).
- Added three context-economy bullets to `constitution.mdc`.
- Did **not** create `.cursorrules` (deprecated always-loaded single file; worse than scoped `.mdc`).

## How it works now

- **Always-on (12):** constitution, specialist-routing, single-market-data-feed, ibkr-gateway-login-warning, nova-roadmap-continuity, engineering-standards, karpathy-guidelines, problem/change/task-log, commit-push-deploy, self-annealing.
- **Glob:** modularity / file-size / constants attach when editing backend or frontend source.
- **Agent-requested:** browser-testing, run-app, nova-os-continuity, graphify -- name+description always visible; body on demand.
- Measured always-on total: ~74 KB (~19k tokens), down from ~119 KB (~30k).

## Why this approach

Re-scope + dedupe only (no prose rewrite) was the chosen aggressiveness: largest win with lowest risk of weakening enforcement wording. Closeout rules stay always-on because silent omission of PROBLEM_LOG / CHANGELOG is a constitution violation and the `subagentStop` hook is only a reminder. Safety feed rules stay always-on because agent-requested fetch can miss. `.cursorrules` was rejected because it cannot scope and would fight the three-mode model.

Rejected: merging the five closeout rules into one file in this pass (prose rewrite; deferred follow-up).

## Verification

- Size re-measure: AGENTS 28.2 KB + always-on .mdc 45.9 KB = 74.1 KB (~19k tokens).
- Frontmatter: 12 `alwaysApply: true`, 13 `alwaysApply: false` (including pre-existing continuity globs).
- `py -3 tools/agent_contract.py` PASS (14 agents).
- Attachment behavior in a fresh chat is a human spot-check (Cursor UI shows attached rules).

## Follow-ups

- Merge/trim closeout rule prose (~12 KB -> ~4 KB) and trim anti-pattern lists in `single-market-data-feed` / `specialist-routing` / `engineering-standards`.
- Outside repo: disable unused MCP servers and uninstall unused skills (large per-request catalogs).

## Keywords

cursor rules, tokens, alwaysApply, AGENTS.md, context economy, agent-requested, glob rules, .cursorrules
