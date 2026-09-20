# Nova backlog — work packages

**The backlog is organised into ten work packages.** A package is an outcome
("after this, recording cannot wedge the desk"), not a module. Every open
issue belongs to exactly one.

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

1. **One PR per batch, not per issue.** The plan batches 44 issues into 23
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

Ranked by impact, dependency and readiness. `next` walks this order and
skips anything gated.

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
| 9 | One replay surface, one trade-print source | 308, 309, 310, 311, 315, 340 | ⛔ | **The chokepoint.** See below. |
| 10 | Live desk on master, plus residual product asks | 14, 90, 91, 94, 147, 331 | ⛔ | Needs the operator at the physical trading PC. |

Objectives and acceptance criteria live in `knowledge/backlog-packages.json`
and on each milestone's description — they are not duplicated here, so they
cannot drift.

---

## What you unblock by deciding

**19 of 44 issues (43%) are waiting on a human, not on engineering capacity.**
Packages 1–8 are all startable today, so agents are not idle — but the ranking
below is where a decision buys the most.

| Decision | Gates | Cost of not deciding |
|----------|-------|----------------------|
| **#340 Phase 3** — keep `backend/sim/history_*` as the single replay surface; fix or retire `backend/capture/` | **6 issues** (308, 309, 310, 311, 315, 340) — all of package 9 | Three overlapping record/replay stacks, only one working. Also a live constitution contradiction: `backend/l2/db.py` and the Local-Market-Data-Recorders note still name Alpaca WS as the time-and-sales source. |
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

```bash
# One package, 2 concurrent agents, ramps down before the budget runs out
# (see .claude/workflows/backlog-wave.js)
```

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

## Periodic triage

Automatic: **`.github/workflows/backlog-triage.yml` runs every Monday 13:05 UTC**
(09:05 ET). It refreshes the Backlog Map issue, and comments on it *only* when
something needs a human — so a clean backlog is silent.

Manual, any time:

```bash
py -3 tools/backlog_triage.py report
```

```bash
py -3 tools/backlog_triage.py check
```

`check` exits 1 when an open issue has no package or is missing a
`deferred` / priority / kind / `domain:*` label, or when the milestones
disagree with the authored plan. Deliberately **not** a required PR check: a
new issue is unpackaged for the minutes between filing and triage, and failing
CI for that would train agents to skip filing issues.

### Triaging a new issue

1. File it as usual (`.github/ISSUE_TEMPLATE/`, labels per AGENTS.md §7.2c).
2. Add it to a package in `knowledge/backlog-packages.json` — either into an
   existing PR batch or as a new one.
3. `py -3 tools/backlog_triage.py sync` to project it onto the milestone.
4. If it does not fit any package, that is a signal the plan needs a new one,
   not that the issue should stay unpackaged.

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
