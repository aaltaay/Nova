---
name: code-review-and-quality
description: >-
  Five-axis code review (correctness, readability, architecture, security,
  performance) with structural remedies. Use before claiming ship on non-trivial
  diffs, after features or bug fixes, or when reviewing agent-written code.
---

# Code review and quality (Nova)

Lineage: [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) `code-review-and-quality`, adapted for Nova.

**Approval standard:** Approve when the change improves overall code health and meets Nova invariants -- not when it is perfect.

## When to use

- Before merge / before claiming ship on non-trivial work
- After feature implementation or bug fix (+ regression test)
- When reviewing code from another agent or model

## Five axes

### 1. Correctness

Matches intent? Edge cases? Error paths? Tests testing the right thing?

### 2. Readability and simplicity

Clear names? Straightforward control flow? Fewer lines when equivalent? Abstractions earned (third use)?

### 3. Architecture

Fits Nova modularity? Logic in the right module (not `main.py` / `App.tsx`)? Constants centralized? File-size pressure addressed when touching violators?

### 4. Security

Secrets out of logs/code? Input validated at boundaries? No new spend/order path outside IBKR gates? No weakening of live trading confirmations?

### 5. Performance

No N+1 or unbounded fan-out on hot scanner/WS paths? No extra IBKR depth/tape subscriptions from Quote Panel? Coalescing still honest about staleness?

## Nova-specific checklist

- [ ] Single market-data feed respected (IBKR prices; Alpaca news/listing only)
- [ ] Symbol gates on quote/L2/tape (no cross-symbol bleed)
- [ ] Execution still ADR 007 shaped if orders touched
- [ ] `auto_live` remains NO-GO (no unlock path sneaked in)
- [ ] CHANGELOG / PROBLEM_LOG / task-log obligations noted when behavior changed or bugs fixed
- [ ] No silent `except: pass` introduced

## Structural remedies (propose the move)

- Replace conditional chains with typed model/dispatcher
- Move feature logic out of shared modules into the owner
- Reuse canonical helpers instead of near-duplicates
- Extract / split when a touched file is over the line budget
- Delete pass-through wrappers that add no clarity

## Output format

```text
## Review summary
Verdict: approve | approve-with-nits | request-changes

### Findings
- [critical|major|minor|nit] <file:line> — <issue> — <remedy>

### Nova invariants
- <pass/fail notes>
```

Critical/major block "ship" claims until fixed or explicitly waived by the user.

Default: run this review in the **parent session** (zero-hop). Do not auto-spawn `maintainer` / `security` / `tester` unless the user names them.

## Related

- Always-on verification: `.cursor/rules/verification-before-completion.mdc`
- Doubt for in-flight decisions: `.cursor/skills/doubt-driven-development/SKILL.md`
- Opt-in specialists: `maintainer`, `security`, `tester`
