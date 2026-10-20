# Change-aware CI: green before a merge and before a Release

Owner decisions, 2026-10-13: **"Things should only be shipped with green builds"**
and **"Merge only green PRs too"** (they supersede the 2026-09-20 advisory merge).
Actions merges a ready PR only when Backend tests, Frontend build, Frontend E2E and Agent contract concluded `success` on its head, and the label `merge-approved` was most recently added by GitHub user `aaltaay`. Agents never add `merge-approved`; only the owner does. A
Release waits for the same four checks on the commit it ships (see "Releases wait for a
green build" below). The release does not require the label. Drafts never merge. `do-not-merge`, forks and real conflicts retain their
holds. Master still blocks force-push and deletion, including for admins, and the
`No force-push` ruleset refuses a force-push on every other branch, with no bypass
(AGENTS.md 5.1; `py -3 tools/no_force_push.py check`).

| Changed files | Backend suite | Frontend lint/unit/build | Chromium E2E | Windows pack |
|---|---|---|---|---|
| Root/docs/knowledge Markdown, images under `docs/`, change fragments, marketing site | No | No | No | No |
| Frontend source/assets/tests | Trading-facing modules only | Yes | Yes | Yes |
| Backend source/tests | Yes, complete suite | No | Yes | Yes |
| Electron, build scripts, manifests, CI/tools, unknown paths | Yes | Yes | Yes | Yes |
| Manual full verification | Yes | Yes | Yes | Yes |

All rows run quick agent/doc validation and secret scanning. The IB event-loop
purity check remains in agent validation. Full backend coverage includes order
validation, idempotency, risk controls, shorts, runtime opt-ins and live safeguards.
This CI policy does not change any runtime trading permission or `auto_live` NO-GO.

Inside a job, each check reports its own result. Once the job's checkout, setup
and install have succeeded, every check runs even when an earlier one failed, so
one red never hides another, and the job is still red. The checks that run this
way:

- Backend tests: Ruff and pytest.
- Frontend build: lint, unit tests and the build.
- Agent contract: tool tests, structural validation, doc invariants, skills
  audit and the maintainer gate.
- Desktop pack: its Windows maintenance tests, which run after the pack.

A step that needs an earlier step's output still stops there: Desktop pack
proves and uploads only an installer it built. Frontend E2E, Gitleaks and the
security scans each run a single check. Only a failed setup or install, or a
cancel, skips a check.

The classifier reads the complete Git merge-base diff for a PR, or before/after
for pushes. Renames include both old and new paths. Missing diffs, unknown paths,
and manual dispatch select full coverage. Job summaries explain selection.
Non-applicable jobs return a lightweight result without installing dependencies.
Frontend trading modules also select the full backend suite. No tests were deleted.

Source security scans run on source changes; dependency scans run on manifest
changes. Both also run daily and on manual dispatch. Branch housekeeping and
protection audits run in Repository maintenance instead of affecting PR results.
Superseded PR runs are cancelled; master runs are allowed to finish.

## Merges wait for a green PR

`Auto-merge` `needs` the four jobs and runs once they finish (never on a cancelled,
superseded run). It checks out master's `tools/pr_delivery.py`, never the PR's own,
and `decide()` reads the head's check runs (`tools/pr_checks.py`): each of Backend tests, Frontend build, Frontend E2E and Agent contract
must have concluded `success` at its newest run. The same `decide()` reads the issue events API and merges only when the PR currently has `merge-approved` and the latest `labeled` actor for that label is `aaltaay`. Agents never add `merge-approved`; only the owner does. The sweeps (CI completion through
`pr-delivery.yml`, hourly at :12, manual dispatch, and `pull_request` `labeled`) call the same `decide()`.

Create the label once if it is missing:

```text
gh label create merge-approved --repo aaltaay/Nova --color 0E8A16 --description "Owner aaltaay approved auto-merge. Agents never add this."
```

| The four on the head | Owner label | Decision |
|---|---|---|
| all `success` | `merge-approved` last added by `aaltaay` | merge (after the five-minute floor and any running review) |
| any | missing, removed, or last added by anyone else | do not merge. A wrong actor gets one short comment. The label stays. |
| one not reported yet, queued or running | owner label present | wait; Auto-merge or a sweep decides again |
| one failed, cancelled, timed out or skipped | owner label present | hold: a comment on the PR names it, once per head, and the job summary says it |

A check the diff does not need is not skipped at GitHub's level: its job runs, says
"Unaffected" and concludes `success`, so a docs-only PR merges once `aaltaay` has added `merge-approved`. Re-running a failed
check re-runs `Auto-merge` (it depends on the check), so a green re-run merges when
`aaltaay` has added `merge-approved`; a push starts a new run. Adding the label
after CI is already green is the `pull_request` `labeled` trigger, which runs
the same decision without starting the test jobs again. `master_branch_protection.py` still requires
zero status-check contexts: the merge job is the gate, and status-only master pushes
stay possible. Gitleaks and the security scans stay warning-only.

Packaging attempts the Windows installer for relevant changes without delaying
merge (Desktop pack on a PR is not one of the four), and verifies its `latest.yml`
update feed. Every master commit is tagged `vNNN`, and an application-affecting one
is published as that GitHub Release (operator decision 2026-09-23, superseding
#347's tag-only publishing) once its build is green. A commit PR delivery merged is
dispatched to Desktop pack, which selects every check: it packs and, when green,
publishes even a docs-only change; only a docs-only human push skips the pack.
Broader CI audit follow-ups remain in #342.

## Releases wait for a green build

A master run of `Desktop pack` (a human push, or PR delivery's dispatch after an
Actions merge) packs the installer and, beside it, calls this CI workflow on the
same commit as its `verify` job, `Release checks`, with `full: true`: every check
runs whatever the diff, because a frontend-only commit still ships the backend its
parent left. An Actions merge starts no CI run on master (#346), so this is the
only CI the shipped commit itself gets.

`Publish vNNN installer` then runs `tools/release_gate.py` before anything else. It
reads the run's jobs at their latest attempt and publishes only when:

| Must be green | Why |
|---|---|
| Desktop pack | the installer and its `latest.yml` exist and agree; the Windows maintenance tests pass |
| Release checks / Backend tests | Ruff and the complete backend suite, order and risk safeguards included |
| Release checks / Frontend build | lint, unit tests and the build |
| Release checks / Frontend E2E | Chromium Playwright |
| Release checks / Agent contract | tool tests, doc invariants, skills audit, the maintainer gate |

Failed, cancelled, timed out, skipped, still running or missing all hold the
Release: the job fails with "vNNN not published: <check> failed" in its summary and
as an error annotation, and the desk is never offered that build. Gitleaks and the
security scans stay warning-only and never hold one. **Re-run failed jobs** on that
run (or `gh workflow run desktop-pack.yml --ref vNNN`); a green re-run publishes it,
and it becomes latest only if no higher `vNNN` Release exists. Docs/site-only
pushes pack nothing, so they get the tag and no Release, as before; a docs-only PR
merged by Actions is dispatched, packs and is released once green. The desk's update
code is unchanged: it simply never sees a red build.
