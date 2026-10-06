# Confirm a concurrent PR merge (#762)

Owner: `tools/pr_delivery_actions.py`. Authored batch: `delivery-pipeline#6`.

## Verified failure

PR #759's Auto-merge job returned exit 2 after GitHub answered `Merge already
in progress (HTTP 405)`. Another delivery actor merged the same head, closed
the completed issues and removed the remote head. The current helper returns
on the failed PUT without checking whether that exact merge completed.

## Correction boundary

Keep the existing eligibility decision and SHA-bound squash PUT. Only an
HTTP 405 explicitly saying `Merge already in progress`, with an expected head
SHA present, may enter confirmation. Do not issue a second merge PUT.

Read the PR resource at most three times, with one-second gaps only while the
same head remains open and unmerged. Confirm completion only when the resource
states `merged: true`, `state: closed`, the exact expected head SHA and a
nonempty merge commit SHA. Require both head and base repositories to be the
requested repository, and the base to be the existing release branch `master`.
Missing, malformed, foreign or moved identity never proves completion; an
unmerged closed PR, unreadable resource or exhausted wait remains a failure.

After confirmed completion, run the existing linked-issue closure verification,
explicit desktop-pack dispatch and guarded head cleanup. No issue or cleanup
mutation may precede proof. These steps keep their existing failure semantics;
the confirmation does not make an unsuccessful issue closure successful.

Preserve HTTP 409 head-moved re-decision, ordinary merge refusals, authorization
errors, review/settling gates, draft/hold policy and conditional branch deletion.
No workflow, application, trading, broker or operator policy changes belong here.

## Verification

Exercise the real `cmd_merge` and `cmd_sweep` with immediate and delayed
same-head completion. Assert one PUT, bounded reads and sleeps, unchanged
SHA payload, and issue/pack/cleanup ordering after proof. Before implementation,
these successful race cases must reproduce the nonzero result.

Cover still-open timeout, closed without merge, moved/missing SHA, incomplete
merge proof, foreign repositories/base, unreadable or malformed resources,
non-race 405/403 failures and missing expected SHA. Keep failed linked-issue
closure nonzero after a confirmed merge. Run delivery/review/cleanup neighbors,
authored package/footprint checks, documentation invariants, agent contract and
the maintainer gate. All GitHub behavior is mocked; no live merge is needed.

## Verified results (2026-10-06)

Before implementation, all six immediate/delayed `cmd_merge` and `cmd_sweep`
success cases failed with the original nonzero result. A refusal control also
caught an overbroad HTTP-status substring; the classifier now matches the exact
405 status token and explicit in-progress message.

The 144 focused delivery, review-status and guarded-cleanup tests pass, including
both entrypoints' still-open, invalid identity, malformed resource and delayed
read-failure controls. Combined with backlog triage/footprints/claims/branches,
documentation, agent-contract and maintainer-policy tests, 422 tests pass.
Production-file Ruff, live-document invariants, agent contract, the maintainer
gate against `bb4d3e72`, and `git diff --check` pass. The test file has the same
four pre-existing Ruff B023 findings as that base, with no new lint findings.
Only the four authored batch paths changed; no live GitHub merge was performed.
