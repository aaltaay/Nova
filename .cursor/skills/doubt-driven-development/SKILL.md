---
name: doubt-driven-development
description: >-
  Fresh-context adversarial review of non-trivial claims before they stand.
  Use for branching logic, module boundaries, irreversible ops, trading-adjacent
  safety claims, or when a confident answer would be cheaper to verify now than
  debug later. Prefer parent-session review (zero-hop).
---

# Doubt-driven development (Nova)

Lineage: [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) `doubt-driven-development`, adapted for Nova.

A confident answer is not a correct one. Materialize doubt **before** the decision hardens.

## When to use

Non-trivial if any of:

- New/changed branching logic
- Crosses a module or service boundary
- Asserts properties types cannot prove (ordering, idempotence, feed honesty)
- Irreversible blast radius (migrations, public API, production data)
- Trading-adjacent: orders, gates, short entry, scanner SoT, `auto_live` wording

## When NOT to use

- Renames, formatting, pure docs
- Clear unambiguous user instructions
- One-line obvious fixes
- User asked for speed over verification

## Process (parent session default)

```text
Doubt cycle:
- [ ] CLAIM — claim + why it matters (2–3 lines)
- [ ] EXTRACT — smallest artifact + contract (no journey narrative)
- [ ] DOUBT — adversarial pass biased to disprove (fresh subagent OR hard mental reset)
- [ ] RECONCILE — classify findings vs artifact text
- [ ] STOP — trivial findings, 3 cycles, or user override
```

### CLAIM

```text
CLAIM: …
WHY THIS MATTERS: …
```

### EXTRACT

Give the reviewer only: artifact (diff/function/proposal) + contract (must-hold invariants). Strip prior reasoning.

### DOUBT

Prefer a **fresh-context** reviewer when available. Prompt bias: disprove, not approve.

Nova default: stay in parent session with a hard separator prompt if spawning is not requested. Do **not** build persona→persona chains (zero-hop / specialist-routing).

If using a subagent, the user must be OK with the hop; otherwise self-doubt with degraded flag:

```text
DOUBT MODE: degraded-self (not fresh context)
```

### RECONCILE

For each finding: accept (fix now), reject (cite artifact text), or escalate to user.

### STOP

Stop after clean pass, three cycles, or user override. Do not infinite-loop.

## Nova invariants the doubter must check when relevant

- No Alpaca price silent fallback when discovery=ibkr
- No orders outside gated IBKR / ADR 007 path
- `auto_live` remains NO-GO
- Logic not dumped into `main.py` / `App.tsx`
- New files stay under line limits

## Related

- `.cursor/skills/code-review-and-quality/SKILL.md`
- `.cursor/rules/specialist-routing.mdc` (zero-hop)
- Explicit specialists: `maintainer`, `security`, `execution` on user ask
