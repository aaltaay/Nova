# 2026-08-05 -- Doc invariants CI gate

- **Status:** completed
- **Agents:** parent
- **Domain:** docs
- **Related:** `CHANGELOG.md` §2026-08-05 -- Doc invariants CI gate · prior `2026-08-05-retire-railway-deploy-docs.md`

## Task

Implement machine-checked live-doc invariants, wire them into GitHub Actions, and add an always-on posture-change rule so Railway/Alpaca/phase lies cannot quietly return.

## Goal

CI fails when live docs re-introduce known-stale present-tense claims; agents have a same-commit checklist for posture changes.

## Why it mattered

A fact-check found High-severity stale constitution/onboarding claims after Railway retirement and IBKR lock. Without a gate, the next ops shift would lag in docs again.

## What we changed

- Added `tools/doc_invariants.py` + `tools/test_doc_invariants.py`
- Wired into `.github/workflows/deploy.yml` `agent-contract` job (pytest + script)
- Added always-on `.cursor/rules/doc-invariants.mdc`; linked from `docs-continuity.mdc`, `AGENTS.md` §12, `docs/agent-operations.md`
- Fixed live docs that would fail the gate (AGENTS §5/§10, README, `.env.example`, ZAP tip, roadmap scope guard, `findings.md` banner, CORS audit copy, schema/SOURCE-PINS wording)

## How it works now

- Live paths only (constitution, README, env examples, rules, select docs/security/tools strings)
- Archives (CHANGELOG / PROBLEM_LOG / task-log) excluded
- `py -3 tools/doc_invariants.py` exits 1 on match; CI blocks merge when red
- Posture changes update live homes in the same commit per the MDC table

## Why this approach

- Regex CI over LLM audits: zero cost, deterministic, catches the exact failure class we just hit
- Fix High live lies in the same pass so the gate starts green (a red-from-day-one check gets disabled)
- Do not scan historical logs -- rewriting history creates noise and hides real narrative
- Rejected: full Obsidian rewrite in this job (deferred follow-up); rejected: warning-only CI (would not prevent recurrence)

## Verification

- `py -3 tools/doc_invariants.py` -> OK
- `pytest tools/test_doc_invariants.py` -> 6 passed

## Follow-ups

- Expand patterns for Dockerfile / `RAILWAY_VOLUME_MOUNT_PATH` comments if desired
- Banner remaining Obsidian Alpaca soft-toggle bodies (`Alpaca-Integration-Reference`, scanner soft-toggle sections)

## Keywords

doc invariants, CI, stale docs, Railway, Alpaca SoT, AGENTS.md, GitHub Actions
