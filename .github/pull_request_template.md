<!--
Nova PR template. This body IS the task-log narrative (`.cursor/rules/task-log.mdc`).
Write a separate knowledge/task-log/ file only when the work ships without a PR.
No secrets, tokens, or .env contents anywhere in this body.
-->

## What

<!-- 1-3 sentences: what changed, user-visible + internal. Same shape as the CHANGELOG "What" field. -->

## Why this approach

<!--
REQUIRED. Tradeoffs and rejected alternatives, not a file tour.
Why is this shape correct under growth, safety, and local-first constraints?
What would a cold agent get wrong if it re-derived this from the diff alone?
-->

## Verified by

<!--
REQUIRED. Fresh evidence from this branch, not "should work" (verification-before-completion.mdc).
Paste the commands and their results, e.g.:
- `pytest backend/ -q` -> N passed
- `npm run build` (frontend) -> exit 0
- browser / Playwright path clicked, screenshot or recording
Touched a shared resource? Also verify its loudest neighbor (blast-radius table in verification-before-completion.mdc).
-->

## Related issue

<!--
Closes #NNN for the deferred GitHub issue this ships (label `deferred`), or "none".
Also list: CHANGELOG entry date, PROBLEM_LOG entry (bug fixes), ADR, roadmap phase.
Parked something new instead of fixing it? Open a `deferred` issue and link it here.
-->

## Logs

- [ ] `CHANGELOG.md` entry in this PR (behavior / endpoint / constant / rule / UI change)
- [ ] `PROBLEM_LOG.md` entry in this PR (any bug fixed or fully diagnosed)
- [ ] GitHub issue opened or closed for anything parked or finished (label `deferred`)
- [ ] Live docs updated in the same commit if hosting / feed / phase / trading posture changed (`doc-invariants.mdc`)
