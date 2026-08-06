# 2026-08-06 -- Engineering methodology graft (Superpowers + Addy)

- **Status:** completed
- **Agents:** parent
- **Domain:** docs / agent-os / engineering-methodology
- **Related:** `CHANGELOG.md` §2026-08-06 -- Engineering methodology graft · `AGENTS.md` maintenance log 2026-08-06

## Task

Keep Nova's domain constitution; graft Superpowers verification/plan teeth and Addy interview/doubt/review skills; then audit the graft.

## Goal

Close Nova's Spec/Plan/Prove/Review gap without installing a second agent OS (no full Superpowers/Addy plugins, no default subagent-per-task).

## Why it mattered

Nova was strong on trading/feed/execution law and post-hoc memory (PROBLEM_LOG / task-log) but weak on mandatory evidence-before-done, requirements interview, adversarial doubt, and five-axis review. Upstream methodologies are superior on those axes; a wholesale install would fight zero-hop and `AGENTS.md`.

## What we changed

- Always-on: `verification-before-completion.mdc`, `engineering-methodology.mdc` (soft TDD + skill map + import boundaries)
- Skills: `verification-before-completion`, `writing-plans`, `interview-me`, `doubt-driven-development`, `code-review-and-quality`
- Self-annealing tightened to investigate-before-fix + fresh verification + soft TDD
- Catalog/pins/`AGENTS.md` §12 + Skills Library updated
- Deterministic audit: `tools/engineering_skills_audit.py` + pytest + CI step

## How it works now

1. Domain constitution + feed/IBKR/execution MDCs still win.
2. Always-on verification blocks vibe-based "done" claims.
3. Methodology MDC routes intents to the five skills; plans are optional unless Plan mode / multi-file.
4. Zero-hop remains default; specialists stay explicit opt-in.
5. `py -3 tools/engineering_skills_audit.py` fails CI if the graft drifts or grows anti-Nova instructions.

## Why this approach

- **Rejected:** Full `/add-plugin superpowers` or dumping all 24 Addy skills -- second constitution, expensive default hops, always-hard brainstorming on hotfixes.
- **Rejected:** Only documenting "you should verify" in Karpathy text -- too soft; Superpowers iron law is the missing tooth.
- **Chosen:** Thin Nova-adapted skill bodies + always-on MDCs + machine audit. Steals the best loops while keeping trading law and cost model.

## Verification

- `py -3 tools/engineering_skills_audit.py` -- PASS (0 findings) after tightening zero-hop on all five skills
- `py -3 -m pytest tools/test_engineering_skills_audit.py -q` -- 3 passed
- `py -3 tools/agent_contract.py --ci` -- PASS (14 agents)
- `py -3 tools/doc_invariants.py` -- OK
- Conflict scan: no subagent-driven-dev requirement, no enable-auto_live, no replace-AGENTS.md
- First audit pass found `interview-me` + `code-review-and-quality` missing explicit zero-hop; fixed same session; audit rule now requires zero-hop/parent-session on all process skills
- Pre-existing (not introduced by graft): `test_sync_agent_surfaces` 2 failures (security open_findings count; stale freshness); maintainer FILE_SIZE debt; fleet stale snapshots

## Follow-ups

- Use `interview-me` on the next underspecified product ask
- Optional `docs/plans/README.md` when first real plan is written
- Do not reopen full Superpowers subagent-driven-dev unless user opts in per feature

## Keywords

superpowers, agent-skills, verification-before-completion, writing-plans, interview-me, doubt-driven-development, code-review, engineering-methodology, zero-hop, graft
