---
name: verification-before-completion
description: >-
  Requires fresh verification evidence before any done, fixed, or passing claim.
  Use when about to claim work is complete, before commit/PR language, after bug
  fixes, or when a subagent reported success. Companion always-on rule:
  verification-before-completion.mdc.
---

# Verification before completion (Nova)

**Core principle:** Evidence before claims, always.

Lineage: [obra/superpowers](https://github.com/obra/superpowers) `verification-before-completion`, adapted for Nova. Domain constitution wins on trading/feed/modularity. Never treat a green test run as permission to weaken `auto_live` NO-GO or IBKR gates.

## Iron law

```text
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you have not run the proving command in this turn, you cannot claim it passes.

## Process

1. Identify the command that proves the claim.
2. Run it fresh (full suite or focused tests as appropriate).
3. Read exit code and failures.
4. Only then claim success -- quote the evidence briefly.
5. If evidence fails, state actual status; do not soften into "should work."

## Nova commands (prefer these)

- Backend: `py -3 -m pytest <path> -q`
- Frontend: `npm test -- --run <pattern>` or package scripts already used in-repo
- Build: `npm run build` when UI/bundle risk
- Agent OS: `py -3 tools/agent_contract.py`, `py -3 tools/doc_invariants.py`
- Engineering graft audit: `py -3 tools/engineering_skills_audit.py`

## Anti-patterns

- Trusting "looks correct" or a prior session's green run
- Trusting a subagent "success" without diff + re-verify
- Treating PR evidence/task-log as proof of correctness
- Skipping verification because work stayed in the parent session (zero-hop does not waive evidence)
- Verifying only the unit you changed when you touched a shared resource (IB socket, bars store, ledger) -- see the blast-radius table in `.cursor/rules/verification-before-completion.mdc`

## Related

- Always-on: `.cursor/rules/verification-before-completion.mdc`
- Methodology: `.cursor/rules/engineering-methodology.mdc`
