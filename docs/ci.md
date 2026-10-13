# Change-aware CI: advisory for merge, required for a Release

Owner decision, 2026-09-20: **no verification check is required for merge**.
Ready PRs merge while checks are pending or running, or after failures. Red checks
remain visible as feedback. Drafts, `do-not-merge`, forks and real conflicts retain
their holds. Master still blocks force-push and deletion, including for admins.

Owner decision, 2026-10-13: **"Things should only be shipped with green builds."**
The desk's update feed offers whatever `vNNN` GitHub Release is newest, so a Release
is a shipment, and it waits for green (see "Releases wait for a green build" below).

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

`Auto-merge` has no dependency on verification jobs. `pr_delivery.py` never polls
check status, and `master_branch_protection.py` requires zero status-check contexts.
To reverse this policy, update those two policy tools, the workflow dependency,
the constitution/rules and the live branch setting together.

Packaging attempts the Windows installer for relevant changes without delaying
merge, and verifies its `latest.yml` update feed. Every master commit is tagged
`vNNN`, and an application-affecting one is published as that GitHub Release
(operator decision 2026-09-23, superseding #347's tag-only publishing) once its
build is green. Broader CI audit follow-ups remain in #342.

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
pushes pack nothing, so they get the tag and no Release, as before. The desk's
update code is unchanged: it simply never sees a red build.
