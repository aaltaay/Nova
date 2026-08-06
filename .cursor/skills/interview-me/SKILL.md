---
name: interview-me
description: >-
  One-question-at-a-time requirements interview with hypothesis and confidence.
  Use when the ask is underspecified (missing who/why/success/constraint), when
  the user says interview me / grill me / stress-test my thinking, or before
  planning a non-mechanical feature.
---

# Interview me (Nova)

Lineage: [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) `interview-me`, adapted for Nova.

Closes the gap between what was asked and what is wanted **before** plan/code.

## When to use

- Missing at least one of: who, why, success metric, binding constraint
- Conventional asks ("build a dashboard", "make it faster") without specifics
- User invokes: "interview me", "grill me", "are we sure?"

## When NOT to use

- Mechanical ops (rename, typo, run tests, status check)
- User explicitly wants speed over clarification
- Pure information questions
- Non-interactive loops / CI

## Process

### 1. Hypothesize

```text
HYPOTHESIS: <one sentence>
CONFIDENCE: <0-100%> — <what's missing>
```

### 2. One question + guess

```text
Q: <one focused question>
GUESS: <your predicted answer + why>
```

Wait for the reply before the next question.

### 3. Listen for want vs should-want

If the user echoes a convention, ask what job that convention is supposed to do.

### 4. Stop near ~95% confidence

Stop when you can predict the next three answers. Summarize:

```text
INTENT: …
SUCCESS: …
CONSTRAINTS: …
OUT OF SCOPE: …
NEXT: writing-plans | implement | specialist X
```

## Nova overlays

- Surface trading/feed/execution constraints early when the ask touches them.
- Do not invent a requirement that weakens `auto_live` NO-GO or single-feed rules.
- After a solid interview on a multi-file feature, prefer `writing-plans` before code.
- Stay in the parent session (zero-hop default). Do not auto-dispatch specialists from an interview.

## Related

- `.cursor/skills/writing-plans/SKILL.md`
- `.cursor/skills/doubt-driven-development/SKILL.md`
