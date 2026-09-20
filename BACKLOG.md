# Nova backlog — work packages

**The backlog is organised into eleven work packages, plus an inbox.** A package
is an outcome ("after this, recording cannot wedge the desk"), not a module.
Every open issue belongs to exactly one.

If you are an agent and you were told *"start on the next item in the backlog"*,
run this and do what it says:

```bash
py -3 tools/backlog_triage.py next
```

That prints one package, one pull request, the issues it resolves, and the
acceptance criteria. You do not need to read the rest of this file, and you do
not need to re-triage anything.

---

## Where the plan lives

| Home | What it holds | Authority |
|------|---------------|-----------|
| `knowledge/backlog-packages.json` | Rank, objective, definition of done, PR batching | **Authored.** Edit this to re-plan. |
| GitHub **milestones** | The same packages, projected by `backlog_triage.py sync` | Derived. Readable by any bot via the REST/GraphQL API or `milestone:"…"` search. |
| GitHub **issues + labels** | Open/closed, `P0`–`P3`, kind, `domain:*`, `deferred` | **Authoritative for state.** The JSON never overrides it. |
| [Backlog Map issue](https://github.com/aaltaay/Nova/issues) (pinned) | Rendered rollup, refreshed weekly | Read cache. Never authoritative. |
| This file | Why the packages exist and how to work them | Narrative. |

A stale JSON degrades a listing; it cannot resurrect closed work.
`backlog_triage.py check` reports drift between the plan and GitHub — it never
self-heals.

---

## Rules of engagement

1. **One PR per batch, not per issue.** The plan batches 46 issues into 25
   pull requests. The batches share a root cause and a file set; a reviewer
   should be able to hold one in their head. Do not split a batch to make
   the diff smaller, and do not staple unrelated issues onto one to look
   efficient.
2. **Finish the package before moving down the ranking.** `next` will keep
   handing you the same package until its ungated PRs are done.
3. **`Closes #N` only when the issue's *entire* stated scope is done.**
   Otherwise `Refs #N` plus an evidence comment, and the issue stays open
   (AGENTS.md §7.2c).
4. **Gated work is not yours to unblock.** A package or PR marked gated needs
   an operator decision. Record the question on the issue and move on — do
   not guess the policy and implement it.
5. **Constitution still wins.** IBKR is the only market-data feed, orders only
   via the gated `backend/ibkr/` module, `auto_live` is NO-GO. Several
   packages touch code near those lines.
6. **Clean start, ready PR.** Branch from `origin/master`, finish with a
   non-draft PR. AGENTS.md §5.1 is unchanged by any of this.

---

## The packages

Ranked by impact, dependency and readiness. `next` walks this order and picks
the first package holding an **ungated, unclaimed batch with open issues** — so
ready work inside a mostly-blocked package stays reachable, and a package whose
remaining batches are all gated does not stop the walk.

| # | Package | Issues | Ready | Why here |
|---|---------|--------|-------|----------|
| 1 | Recorder cannot wedge the desk or lose a session | 314, 318, 319, 339 | ✅ | Both open P0s. A deadlock that wedges the whole FastAPI event loop. |
| 2 | Recording and replay state stop lying | 316, 317 | ✅ | A stale flag can silence the IB Gateway alarm. Small, high trust value. |
| 3 | Close what already shipped or was refused | 131, 216, 222, 276, 292, 312 | ✅ | ~14% of the board is already done. Cheapest possible win. |
| 4 | A test run means the same thing on every machine | 293, 307, 326 | ✅ | Every later package's evidence is worth less until this lands. |
| 5 | Merging a PR ships a Release; red CI means code broke | 342, 344, 346, 347 | ✅ | No Release since v757. ~65% of red CI is noise. |
| 6 | The desk names how the Gateway is degraded | 302, 305, 333, 334 | ✅ | Read-Only API looks tradeable and rejects every order. |
| 7 | The replay desk is usable, readable and honest | 321, 322, 324, 338, 341 | ✅ | The surface the operator actually drives. |
| 8 | A replay reproduces the day, or refuses loudly | 303, 304, 320, 337 | ✅ | Silent holes and unbounded disk growth. |
| 9 | One replay surface, one trade-print source | 308, 309, 310, 311, 315, 340 | ◐ | ADR 017 accepted; live AllLast fan-out implemented. Replay import/depth/quotes/fills remain. |
| 10 | Live desk on master, plus residual product asks | 14, 90, 91, 94, 147, 331 | ◐ | #91's TIF half and #147 are startable; #14/#331/#90/#94 are gated. |
| 11 | Marketing site and parked WIP | 356, 357 | ✅ | Non-desk P3s, kept where they can never outrank desk work. |
| 00 | Untriaged (the inbox) | — | 🕓 | New issues land here automatically until someone routes them. |

Objectives and acceptance criteria live in `knowledge/backlog-packages.json`
and on each milestone's description — they are not duplicated here, so they
cannot drift.

---

## What you unblock by deciding

**19 of the 44 originally-triaged issues (43%) were waiting on a human, not on
engineering capacity.** Packages 1–8 and 11 are all startable today, so agents
are not idle — but the ranking below is where a decision buys the most.

| Decision | Gates | Cost of not deciding |
|----------|-------|----------------------|
| **#302** — persist the Sim choice, or force an explicit re-arm each boot | 1 issue, but it is a spend-safety gap | A backend restart silently returns the desk to Live with the banner gone and spend gates armed. |
| **#320** — retention: manual delete only, or auto-prune | Part of package 8 | Recordings grow unbounded with 29% duplicate rows. |
| **#347** — installer-only vs keep portable; notify-only vs auto-update | Part of package 5 | The portable target can never self-update. |
| **#311** — BID_ASK roughly doubles per-window acquisition time: worth it? | Part of package 9 | A replayed session has no spread and no book. |
| **#90 / #94 / #91** — one cost call and two policy calls | Package 10 | Three small implementations sit behind one-line answers. |

Answer a decision by commenting on its issue. The next `next` run picks it up
once the package's `readiness` is flipped in `knowledge/backlog-packages.json`.

---

## Running a swarm without burning the session

Parallel agents are useful here, but a wide fan-out that dies on a token limit
loses the whole wave. The rule is **2–3 agents at a time, with a reserve**.

Launch it by **path**, not by name:

```text
Workflow({ scriptPath: ".claude/workflows/backlog-wave.js", args: { concurrency: 2, maxAgents: 3 } })
```

`Workflow({ name: 'backlog-wave' })` was observed to fail on a Windows checkout
with *"script contains control characters"* even after the file was normalised
to LF and verified to be pure ASCII — the by-name lookup appears to resolve a
different copy than the repo file. `scriptPath` works. `.gitattributes` pins
`.claude/workflows/*.js` to `eol=lf` so a Windows checkout cannot reintroduce
CRLF into the script itself.

The runner is budget-aware: before each wave it checks the remaining budget
against the cost of the last wave, and when the margin is thin it **stops
cleanly and writes a handoff** instead of starting agents that will die
mid-edit. A stopped wave leaves finished PRs intact and names exactly where to
resume.

Constraints worth keeping:

- **Two or three agents, never ten.** These issues cluster by file; more
  agents mostly means more merge conflicts in `backend/capture/recorder.py`.
- **One package per wave.** Cross-package parallelism produces PRs that
  reviewers cannot sequence.
- **Never parallelise inside one PR batch.** The batches exist because the
  issues share files.

---

## Working alongside other agents

Agents run from several tools — Claude Code, Codex, Cursor — and **all of them
authenticate as the same GitHub account**, so `assignee` can say *taken* but
never *by whom*. GitHub is the only substrate every tool can see, so the claim
lives there.

**Claim before you work. The unit is the PR batch, not the issue.**

```bash
NOVA_AGENT_ID=codex@laptop py -3 tools/backlog_triage.py claim --package recorder-safety --batch 0 --branch agent/recorder
```

```bash
py -3 tools/backlog_triage.py claims
```

```bash
py -3 tools/backlog_triage.py release --package recorder-safety --batch 0
```

How it behaves:

- A claim is a `claimed` label (the cheap filter `next` uses) plus a structured
  comment carrying **agent id, branch and timestamp**.
- **`next` honours it.** A package whose every startable batch is claimed is
  skipped, so a second agent fans out to the next package instead of
  duplicating work.
- Holding **any** issue in a batch holds the whole batch — the batch is one PR.
- **Claims go stale after 4 hours** with no activity, so a crashed agent cannot
  deadlock a package. `claims` lists stale holders; `claim --force` takes one
  over. Nothing steals silently.
- A **merged PR closes the issues, which retires the claim on its own.** You
  only need `release` if you stop without opening a PR.

**This is advisory locking, not mutual exclusion.** Two agents can both read
"unclaimed" before either writes — GitHub has no compare-and-swap on labels.
`claim` re-reads after writing and yields if an earlier live claim exists
(earliest timestamp wins), which makes a collision *detectable and resolvable*
rather than impossible. An agent that ignores the protocol will still collide.

If you are running several swarms, the cheapest extra insurance is to hand each
one a different package explicitly:

```bash
# in the Workflow call: args: { package: 'test-integrity' }
```

---

## Periodic triage

Two automatic jobs:

- **`.github/workflows/backlog-inbox.yml`** — on `issues.opened`, queues the new
  issue into `00 - Untriaged` so it is never invisible. Runs in seconds.
- **`.github/workflows/backlog-triage.yml`** — every Monday 13:05 UTC (09:05 ET).
  Refreshes the Backlog Map issue, and comments on it *only* when something needs
  a human, so a clean backlog is silent.

Manual, any time:

```bash
py -3 tools/backlog_triage.py report
```

```bash
py -3 tools/backlog_triage.py check
```

`check` exits 1 when an open issue has no package or is missing a
`deferred` / priority / kind / `domain:*` label, when the milestones disagree
with the authored plan, or when a **P0/P1 sits untriaged**. Deliberately **not**
a required PR check: a new issue is briefly unrouted between filing and triage,
and failing
CI for that would train agents to skip filing issues.

### How a new issue reaches a package

New issues are **queued automatically**. `.github/workflows/backlog-inbox.yml`
assigns `00 - Untriaged` on `issues.opened`, so an issue is visible to `next`,
`report` and the Map within a minute of filing — never invisible, never waiting
for Monday. An issue that already has a milestone is left alone.

Nothing guesses the real package. Routing asks *which outcome does this issue
serve*, which is a weaker question than "which files does it touch" — a
heuristic on `domain:*` labels would silently mis-file work, and a mis-filed
issue is worse than an unrouted one because it looks handled.

Routing is **on demand**. Say *"triage the backlog"* and an agent will:

```bash
py -3 tools/backlog_triage.py triage
```

…which lists each inbox issue with its severity, domain labels, and which
packages already hold issues sharing those domains — **suggestions only**. The
agent then adds each issue to a package's `issues` and to a PR batch in
`knowledge/backlog-packages.json`, runs `sync`, and opens one small PR with the
JSON change plus a line of reasoning per issue. You review the PR, not the raw
issues.

If an issue fits no package, the **plan** needs a new package — the issue does
not stay unrouted.

**`check` fails while a P0 or P1 is in the inbox.** A routine package must never
be handed out while a desk-breaking bug sits unrouted; everything else in the
inbox can wait for the next triage pass.

### When a package completes

Close its milestone, leave the entry in `knowledge/backlog-packages.json`
(history), and re-rank the remainder if priorities moved. `report` lists any
milestone at 0 open as closable.

---

## Known backlog debt

- **Six duplicate `D-NNN` aliases** across twelve issues (D-057, D-059, D-073,
  D-074, D-076, D-077) — wreckage from the retired next-id allocator. GitHub
  `#NNN` is the durable id; `report` lists the collisions so nobody cites an
  ambiguous one. Titles are not rewritten (AGENTS.md §7.2c).
- **14 of 44 issues were not confirmed live** when the backlog was verified
  against the tree on 2026-09-19: ten partially fixed, two likely stale, two
  unverifiable. Package 3 exists to settle them.

## Parallel work must have disjoint footprints (#367)

The authored plan now records `touches` for each PR batch. A package can
supply a default; an explicit batch list overrides it. Use repository-relative
files and trailing-slash directory paths (for example `backend/capture/`).
Directories include descendants, never sibling prefixes. Matching normalizes
Windows separators and case. Keep footprints current when scope changes;
exclude routine ledger updates, but include substantive source, test and CI
files. These are advisory reservations, not filesystem locks.

New claim comments snapshot the batch footprint as JSON. Legacy claims are
resolved through the current authored batch (or the claimed issue); an unknown
live footprint blocks selection instead of being treated as safe. Both `next`
and `next --package` skip overlapping batches. The `claim` command checks too,
then re-reads after publication to yield to an earlier overlapping claim.
`--force` never overrides another live file reservation.

Run `py -3 tools/backlog_triage.py claims --conflicts` to see the blocked batch,
holder, branch and overlapping paths. Stale/released claims stop reserving
files. A disjoint later batch remains selectable inside the same package.

#367 belongs to delivery-pipeline: avoiding competing agent edits is delivery
coordination, not a replay product change. Its batch is separate from release
publishing so each change stays independently verifiable.
