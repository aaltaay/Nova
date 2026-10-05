# 2026-10-05 — GitHub restoration and backlog reconciliation

- **Status:** completed audit and first startup batch; remaining triage recorded
- **Agents:** parent, reconcile_merged_issues, current_backlog_review, delivery_issue_closure, startup_reliability_fixes
- **Domain:** delivery, execution, market-feed, frontend
- **Related:** GitHub Issues; PRs #731, #732, #733, #734, #735, #737, #738; startup batch #653 / #713

## Task

Resume the Nova backlog effort after several days, reconcile completed work, and
start a small grouped fix batch without duplicating the operator's local agents.

## Goal

Use current issue scopes and comments plus merged source to distinguish completed
work, partial implementation, ordinary code work and actual external evidence.
Close only complete work and refresh the generated offline issue snapshot.

## Why it mattered

The suspended ChatGPT Codex Connector installation rejected writes while public
reads kept working. Browser login did not change that installation state.
Unsuspending it restored actual issue writes. Separately, full merged fixes had
left issues open, so the raw open count overstated unfinished implementation.

The earlier paused snapshot contained 39 open issues; the fresh resumption read
contained 46. New issues had arrived in the meantime, so the old count was not
a stable baseline. Fifteen reconciliation closures reduced that count to 31.
The two completed startup issues now bring the final live count to 29: seventeen
unique completed issues, without counting #653's temporary reopen twice.

## What we changed

Seventeen completed issues were closed with reason `completed` and independently
read back from GitHub. Fourteen already had merged implementations before this
resumed effort; the operator's new archive fix and the two startup issues were
delivered during it.

| Issue | Merged completion evidence |
|---|---|
| #595 | #689 and ADR 044: backend-owned watched hot list, explicit cap and L1 admission |
| #625 | #727: thread-safe/coalesced viewer delivery and stale-view gates |
| #636 | #648: late book removals after traded-through prints |
| #649 | #666: forming setups on five-minute charts |
| #651 | #652: HOD trade-log suite isolation |
| #653 | #735 plus #737: immediate restart, OS-held ownership and exclusion across checkout caches |
| #655 | #660 plus #661: complete backend and desk venue-aware cancellation |
| #672, #673 | #676: feed-gap status and catch-up handling |
| #677 | #679: sender on Live working orders |
| #685 | #690: venue-day account calendar tests |
| #695 | #697: trading-day stock-read defaults |
| #698 | #699: tick-by-tick cap recovery |
| #700 | #703: filed-issuance float warning, without changing gates |
| #713 | #735: startup reconciliation uses persisted venue evidence and refuses ambiguous legacy Paper matches |
| #720 | #732: bounded incremental maintenance outside the trading session |
| #721 | #724: one clock and writer for ten-second candles, with closed-bucket fencing |

#595 and #720 have fresh evidence comments. For #720, PR #732's reported
33 focused / 5,321 full backend tests and real-archive read-only dry run support
its documented alternative to a separate process. A backend restart and the
first night's operational observation remain; this audit did not run that desk.

#585 carried only `enhancement` and was missing from the canonical deferred
listing. It now retains that kind and adds `deferred`, `P3`, `domain:ui` and the
existing Untriaged milestone. No feature behavior was changed by that metadata.

## How it works now

Issue state remains authoritative in GitHub. The generated deferred index is
refreshed through the existing parser/writer from paginated connector REST
responses, because the cloud CLI API path still rejects requests. No stale
snapshot was passed off as a live result. Closed #672/#673 do not carry
`deferred`, so they remain in GitHub rather than the label-filtered snapshot.

The operator's new #732 archive and #733 Paper-latency PRs were detected while
the audit ran. Their scopes were left to those agents. The startup batch checks
their changed files, uses a separate worktree and cooperative issue claims, and
rebases onto their merged code before verification.

The later #736 fill-timestamp correction was also detected and its file scope
checked. It changes exchange-time interpretation in the evidence store and a
measurement regression, without overlapping the startup batch's edits.

## Why this approach

The full scope and later comments decide completion. A merged PR or a `Closes`
string by itself is insufficient; partial `Refs` work stays open. The initial
automatic review concern about #655 was resolved with the later #661 patch and
current code, rather than overriding the older partial result.

The new delivery work is recorded in its own PR bodies: #731 grants missing
Actions issue-write scope; #734 adds actual post-merge closure verification from
the full PR body. The 4,000-character squash-body cutoff is a demonstrated
truncation hazard, not a proven sole explanation of native GitHub auto-closure.

The reviewed startup implementation is recorded in #735. Automated review
identified legacy IBKR Paper labels that overlap practice Paper; the PR was
temporarily drafted while that correction and its service-level regression
were verified, then made ready again. Its implementation narrative and test
evidence remain in the PR body.

The PR delivery sweep for #735 actually logged independent confirmation of
both #653 and #713 closing, proving the #734 repair on a production merge.
A later review found that cache-local guards did not exclude different
checkouts. #735 merged before the draft transition could hold it, so #653 was
reopened with that remaining scope; #713's completed venue reconciliation
remains closed. The cross-checkout correction is delivered as a separate PR,
not by recreating the merged branch or counting unfinished work as complete.
The follow-up #737 merged as `725e77bc`; #653 was re-read closed/completed.
Its shared-guard, process-lifecycle and neighboring measurement scope passed
31 tests. The per-user scope, older unbound-version limit and unexecuted native
Windows locking remain explicit in that PR body.

The #737 merge also exposed a confirmation error: Actions reported a failed
PATCH (HTTP 422), while the actual issue had already closed. A native-closure
race is plausible, but the server's precise rejection reason is not established.
Ready PR #738 accepts a failed write only after a fresh read proves the same
genuine issue is closed; open or unreadable results remain failures. Its 94
focused delivery checks passed. No live replay of the race is claimed.

## Verification

- Fresh issue bodies, comments, merged PR metadata and source were inspected.
- Every closure above was independently re-read as `closed/completed`.
- The REST deferred collection was paginated to its empty final page, checked
  for duplicate issue numbers, and parsed using `tools/deferred_github.py`.
  The final snapshot contains 183 unique deferred issues: 29 open and 154 closed.
- Production patches have separate, truthful test/build evidence in their PRs.
- #735's exact reviewed commit passed GitHub's full backend suite (5,321 tests)
  and frontend build. Three existing UI E2E failures also present on #734 remain;
  this is not a claim that all CI checks passed.
- No live order, spending gate, trading-PC restart or archive repair was executed.

## Follow-ups

The next ordinary code batch is #657 / #658: venue-specific trade defaults and
bot response/snapshot fencing. Existing risk sleeves, caps and allowlists are
already implemented; per-venue defaults follow their established isolation.
Other startable work: #571 halt transitions, #612 explicit browser reload,
#617 replay book marks, #664 daily P&L, #681 practice exit-only OCO and #585
attention alerts. #504 can build its feeder and calculator before desk evidence.

Retain the following distinctions when resuming:

- #554 is partial shared-poll/ledger-read work, not completed by #568 or #727.
- #14 / #331 need physical-desk login, Gateway and diagnostic evidence.
- #459 is mostly complete; remaining Sim-fill wording and pane clipping need
  targeted verification. #601 needs the actual failing viewport/scale.
- #525 / #722 need evidence of reliable silent-tape recovery, beyond the shipped
  silence/halt indication. #674 still needs recorder lifecycle/lock diagnosis.
- #600 needs recorded strategy rescoring before full candle-source completion.
- #604 / #606 retain their stated Live evidence and authorization requirements;
  practice brackets already exist.
- #616 retains explicit manual backend updates; recurring pulls/restarts remain
  an operator policy choice.
- #619 needs remaining stall evidence; check the newly shipped archive fix first.
- #629's later comment supersedes its old timing/experiment condition: whole-trade
  tests show a one-second benefit. A shadow template can proceed alongside the
  unchanged default, with Live remaining off.
- #667 still needs timestamp-versus-arrival evidence; retain the freshness guard.
- #704's future-write fix is complete, while historical repair needs original
  journals/database and an application window. A dry-run tool is independent.
- #707's code remedies are merged; live 4K/GPU confirmation remains.
- #712 needs Live cancel-watch/bracket-fact verification after offline code work.
- #725's asynchronous send code is merged; the stated one-share operator check
  remains. #726 waits for a week of ADR 045 measurements before loop separation.

## Keywords

GitHub, suspended installation, backlog, triage, issue closure, startup, venues,
local agents, partial completion, deferred index
