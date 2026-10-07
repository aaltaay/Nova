# ADR 051 -- The always-on context has a byte budget

**Status:** Accepted · **Date:** 2026-10-07
**Amends:** [[001-modular-monolith]] (the constitution is itself a file the modularity rules apply to) · the `AGENTS.md` split of 2026-10-07 (§3 to `architecture/schema/`, §11 to `architecture/maintenance-log.md`), which capped one file and left the rest unmeasured
**Decided by:** the operator, 2026-10-07:
- The ask: "nova 'rules' is way too much, it takes massive load of context window. i thought we already fixed that in the previous chat, but it is still ALOT. we need to like achieve 70% efficiency!"
- On the shape of the fix: "i need advanced rules and policies that govern the project not just based on line #. do u have any suggestions so we avoid this dilemma and make sure our constitution is lean enough to where we don't have MASSIVE context window in every chat we start."
- On the five ideas offered (a byte budget for the whole set, a test for what earns always-on, one home per law, rules say what to do and not the story, a rule a script enforces shrinks to a pointer): "ok i like this. go ahead and do it!"

## Context

Every new agent chat on this repository pays, before the first question, for `AGENTS.md`, `CLAUDE.md` and every rule under `.cursor/rules/` whose front matter says `alwaysApply: true`. Cursor injects their full text; Claude Code imports `AGENTS.md` through `CLAUDE.md`'s first line.

Until 2026-10-07 `AGENTS.md` carried 69 schema subsections and the maintenance log inline: 629,779 bytes, about 159K tokens, on every request. The morning's split moved those to `architecture/schema/` and `architecture/maintenance-log.md` and capped `AGENTS.md` at 700 lines (`file_size_hard`). Measured right after, on `873b0527`:

| What loads every chat | Bytes |
|---|---|
| `AGENTS.md` | 57,037 |
| 21 rules marked `alwaysApply: true` | 107,825 |
| `CLAUDE.md` | 5,744 |
| **Total** | **170,606** |

The rules weighed twice the constitution, and nothing measured them. `single-market-data-feed.mdc` alone was 30,833 bytes -- 13 hard rules, their mechanics, a 60-line anti-pattern catalog and a module map -- loaded for a README typo. PR-first delivery was written out five times (`AGENTS.md` §5.1, `constitution.mdc` item 7, `commit-push-deploy.mdc`, `github-delivery.mdc` items 11-12, `workspace-hygiene.mdc`), about 20,000 bytes of the same law. Rule bodies carried incident narratives ("2026-08-18 Gainers freeze; D-025") whose home is the issue. A line cap on one file does not see any of this: the next bloat simply lands in a rule.

## Decision

1. **One budget for the set, in bytes.** `tools/maintainer_lib/always_on.py` sums `AGENTS.md`, `CLAUDE.md` and every `.cursor/rules/*.mdc` with `alwaysApply: true` in its front matter (CRLF counted as one byte, so a Windows checkout and the git blob agree). Past `ALWAYS_ON_BUDGET_BYTES` the gate fails (`always_on_budget`, in `GATE_KINDS`, run by CI's maintainer step and by `py -3 tools/maintainer_checks.py --gate --base origin/master`). A change that grows the total is reported against `--base` (`always_on_growth`, advisory) so the PR body says why. The session brief prints the total every chat. **The budget only ratchets down:** when the total sits 5,000 bytes or more under it, the next change to the set lowers it. It was set at 145,000 against 139,179 measured after this ADR's own cut. The 700-line cap on `AGENTS.md` stays; it is the one file every path imports.
2. **What earns always-on.** A rule loads on every request only when an agent editing *any* file -- a README typo included -- could lose money or break delivery without it. Everything else gets `globs` (attached when its files are edited) or stays agent-requested (its description is always visible; the body is fetched on demand). Stated in `AGENTS.md` §12 and `constitution.mdc` item 8. Required always-on rules (`tools/engineering_skills_audit.py` `REQUIRED_ALWAYS_ON_MDC`) are unchanged.
3. **One law, one home.** A rule's text lives in one file; every other file that needs it holds a line and a link. The delivery law's home is `AGENTS.md` §5.1. `constitution.mdc` item 7, `commit-push-deploy.mdc`, `github-delivery.mdc` items 11-12 and `workspace-hygiene.mdc` are pointers plus what each uniquely owns (the deploy step; issue metadata, the board and closure after merge; the hygiene tool's five rules). `doc_invariants.py` already scans rules for drift against the live homes; that is where a second home gets caught.
4. **A rule says what to do; the story lives elsewhere.** Incident narratives, dates and diagnosis belong on the issue, in the PR body or in an ADR. A rule keeps the instruction and the issue number. A rule that exists only to tell a story is deleted.
5. **A rule a script enforces is a pointer.** Once a check exists (`repo_hygiene.py` for hygiene, `next_moves.py lint` for the footer, `maintainer_checks.py` for size and ownership, `doc_invariants.py` for live docs), the rule names the check, how to run it and where the reason lives, and stops restating what the machine remembers.

Applied in the same change, with the text moved verbatim and nothing deleted:

- `single-market-data-feed.mdc` is the 13 rules as headlines (5,760 bytes) and names the catalog; `single-market-data-feed-catalog.mdc` (`globs: backend/**/*.py, frontend/src/**/*.{ts,tsx}`, `alwaysApply: false`) holds the full previous body. An agent editing feed, chart, scanner, Level 2 or tape code gets the whole law; one editing docs gets the headlines.
- Delivery: the four copies named in decision 3 became pointers. `github-delivery.mdc` keeps every line `engineering_skills_audit.py` and `test_pr_delivery_workflow.py` pin (`origin/master`, "quick fix", `pr-delivery-timing.mdc`, the board URL, `gh project item-add`, head deletion, master protection, "merges ready PRs").

## Consequences

- A new chat on this tip loads 139,179 bytes of always-on context: 18% under the morning's 170,606, 81% under the 743,348 the old `AGENTS.md` made it. The number is in the session brief, so a climb is seen the day it happens.
- The gate fails before the merge button does. Nova merges ready PRs while checks are red (owner policy 2026-09-20), so `always_on_budget` is a visible red check, not a hold; the fix is to move text, and the ratchet makes the next move cheaper.
- A rule behind `globs` is read by the agents who edit its files and not by the others. That is the point, and it is also the cost: an agent that changes a route from a docs-only session will not have the catalog in its head. `schema-docs.mdc` and the headlines both say to read it first.
- `always_on_total_at` reads the base commit through `git show` per file; `--base` adds about 25 subprocess calls to a run.

## Rejected

- **Flipping `single-market-data-feed.mdc` to `alwaysApply: false` whole.** The 13 headlines are trading law that a docs edit can still break (a README that says Alpaca prices the panel). The split keeps them always-on at a fifth of the cost.
- **Removing `@AGENTS.md` from `CLAUDE.md`.** Claude Code loads the constitution through that import; Cursor injects the literal `@AGENTS.md`, not a second copy, so there is nothing to save.
- **A token count instead of bytes.** Tokenizers differ by model; bytes are what both the checker and `git show` can count the same way everywhere.
- **A budget per rule.** Twenty small rules add up the same as one large one; the set is what the chat pays for.
