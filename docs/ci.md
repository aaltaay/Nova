# Advisory, change-aware CI

Owner decision, 2026-09-20: **no verification check is required for merge**.
Ready PRs merge while checks are pending or running, or after failures. Red checks
remain visible as feedback. Drafts, `do-not-merge`, forks and real conflicts retain
their holds. Master still blocks force-push and deletion, including for admins.

| Changed files | Backend suite | Frontend lint/unit/build | Chromium E2E | Windows pack |
|---|---|---|---|---|
| Root/docs/knowledge Markdown, change fragments, marketing site | No | No | No | No |
| Frontend source/assets/tests | Trading-facing modules only | Yes | Yes | Yes |
| Backend source/tests | Yes, complete suite | No | Yes | Yes |
| Electron, build scripts, manifests, CI/tools, unknown paths | Yes | Yes | Yes | Yes |
| Manual full verification | Yes | Yes | Yes | Yes |

All rows run quick agent/doc validation and secret scanning. The IB event-loop
purity check remains in agent validation. Full backend coverage includes order
validation, idempotency, risk controls, shorts, runtime opt-ins and live safeguards.
This CI policy does not change any runtime trading permission or `auto_live` NO-GO.

Inside a job, each check reports its own result. Backend tests runs pytest even
after its Ruff step fails. Every Agent contract check (tool tests, structural
validation, doc invariants, skills audit, maintainer gate) runs even when an
earlier one fails. So one red never hides another, and the job is still red.
Only a failed checkout, setup or install, or a cancel, skips them.

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
(operator decision 2026-09-23, superseding #347's tag-only publishing). Broader
CI audit follow-ups remain in #342.
