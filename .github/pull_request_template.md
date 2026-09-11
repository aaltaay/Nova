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
Closes #NNN only when this PR completes the entire issue.
Use Refs #NNN for partial progress and leave that issue open, or "none".
Also list: CHANGELOG entry date, PROBLEM_LOG entry (bug fixes), ADR, roadmap phase.
Parked something new instead of fixing it? Open a `deferred` issue and link it here.
-->

## GitHub delivery metadata

- **Issue owner:** <!-- human assignee or n/a with reason -->
- **Nova Delivery project status:** <!-- Todo / In Progress / Done, or blocked by permission -->
- **Milestone:** <!-- release/roadmap target, or n/a because not release-bound -->
- **Relationships:** <!-- parent / sub-issue / blocked-by / duplicate / related, or none -->
- **Development link:** <!-- issue number linked by Closes or Refs -->

## Logs

- [ ] `CHANGELOG.md` entry in this PR (behavior / endpoint / constant / rule / UI change)
- [ ] `PROBLEM_LOG.md` entry in this PR (any bug fixed or fully diagnosed)
- [ ] Issue labels, human owner, Project status, conditional Milestone, and real relationships are correct
- [ ] `Closes` is used only for full completion; partial work uses `Refs` and leaves the issue open
- [ ] GitHub issue opened or closed for anything parked or fully finished (label `deferred`)
- [ ] Live docs updated in the same commit if hosting / feed / phase / trading posture changed (`doc-invariants.mdc`)
- [ ] After this PR is merged or closed I will delete the head branch the same session (`stale_pr_branches.py`)
