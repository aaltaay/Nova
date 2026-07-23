# 2026-07-23 — Mandatory PROBLEM_LOG for every agent

- **Status:** completed
- **Agents:** parent
- **Domain:** docs / agent-ops
- **Related:** `CHANGELOG.md` §2026-07-23 — PROBLEM_LOG mandatory · `.cursor/rules/problem-log.mdc`

## Task

Make bug-fix logging in `PROBLEM_LOG.md` mandatory for any agent that works in this project.

## Goal

Every parent session and Nova specialist must write a PROBLEM_LOG entry when fixing/diagnosing a real failure, and declare `problem_log=` on Lifecycle footers.

## Why it mattered

The practice existed as always-on rules but was easy to skip (no Lifecycle field, weak “as required” wording). Future agents re-diagnosed known bugs without a durable shared memory.

## What we changed

- Strengthened `.cursor/rules/problem-log.mdc` (MUST for every agent; skip only cosmetic/status).
- Lifecycle contract regex now requires `task_log=` **and** `problem_log=`.
- Updated specialist-routing, constitution, self-annealing, agent-operations, gemini/AGENTS, all agent Lifecycle examples, subagentStop reminder + tests.
- `PROBLEM_LOG.md` header states the mandate.

## How it works now

1. Bug fix / diagnosis → prepend `PROBLEM_LOG.md` (Symptom / Cause / Fix / Keywords) same session.
2. Specialist report ends with Lifecycle including `problem_log=<YYYY-MM-DD title>|skipped|n/a`.
3. Missing footer → one fail-open `subagentStop` reminder (does not auto-write the log).
4. Cosmetic / no-failure work → `problem_log=skipped` or `n/a`, not silent omission after a real fix.

## Why this approach

- **Rejected:** A git hook that blocks commits without PROBLEM_LOG — too noisy for feature work that is not a bug, and hard to classify automatically.
- **Rejected:** Auto-generating PROBLEM_LOG from diffs — would invent fake “symptoms” and pollute search.
- **Chosen:** Strong always-on rule + mandatory Lifecycle declaration + existing fail-open reminder. Agents still write the narrative; the contract makes omission visible.

## Verification

- `py -3 -m pytest tools/test_subagent_lifecycle_hook.py -q` → 8 passed
- `py -3 tools/agent_contract.py --ci` → PASS (15 agents)

## Follow-ups

Still not a fully automatic “bot” — enforcement is rules + Lifecycle reminder, not CI that diffs PROBLEM_LOG against every code change. Could add a maintainer check later if skips keep happening.

## Keywords

PROBLEM_LOG, mandatory, lifecycle, problem_log=, agent-ops, constitution
