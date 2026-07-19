# 2026-07-18 — Durable task log system

- **Status:** completed
- **Agents:** parent (docs/process)
- **Domain:** docs / agent-ops
- **Related:** `.cursor/rules/task-log.mdc` · `docs/agent-operations.md` · `CHANGELOG.md` §task log

## Task

After every completed job, record what the task was about and **why** the fix was shaped that way, in a growing log folder — not only CHANGELOG/PROBLEM_LOG one-liners.

## Goal

Cold agents (and humans) can always recover intent and tradeoffs for past work by reading `knowledge/task-log/`.

## Why it mattered

CHANGELOG answers “what does the code do now.” PROBLEM_LOG answers “what broke.” Neither reliably captures **rejected alternatives** or the safety/UX reasons behind a design. Without that, agents re-litigate settled decisions or “simplify” away important constraints.

## What we changed

- Created `knowledge/task-log/` (README, INDEX, template, seeded SEC remediation entry)
- Always-apply rule `.cursor/rules/task-log.mdc`
- Helper `tools/task_log_new.py`
- Wired into specialist-routing Lifecycle (`task_log=`), agent-operations, daddy/docs prompts, contract footer example

## How it works now

End of every completed task → write/update a dated entry → prepend INDEX → set Lifecycle `task_log=<path>|skipped|n/a`. Daddy writes one aggregate entry for multi-specialist jobs.

## Why this approach

- **Separate folder, not more CHANGELOG fields** — long reasoning belongs in dedicated narratives; CHANGELOG stays skimmable.
- **Always-apply rule** — process only works if every agent sees it, not only docs.
- **Optional Lifecycle field with optional regex** — remind without breaking older footers that omit `task_log` until agents catch up.
- **Scaffold tool** — reduces “I’ll write it later” friction and keeps INDEX consistent.

## Verification

- Folder + rule + tool present; `py -3 tools/task_log_new.py --help` works
- Contract still validates after footer example update

## Follow-ups

- Optionally teach `subagentStop` hook to nudge when `task_log=` is missing on implementer agents
- Backfill a few high-value historical jobs if useful

## Keywords

task-log, knowledge/task-log, continuity, tradeoffs, Lifecycle, daddy, docs
