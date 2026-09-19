# Deferred tracker (GitHub Issues -- MANDATORY)

The parking lot for known bugs and parked features is **GitHub Issues** labeled `deferred`:

https://github.com/aaltaay/Nova/issues?q=is%3Aissue+label%3Adeferred

`DEFERRED_LOG.md` is the how-to. It is **not** the to-do list. Do not prepend new `## D-NNN` sections here.

**Mandatory for every agent.** Rule: `.cursor/rules/deferred-log.mdc`. Finding a real bug (or parking a real feature) and walking away with no GitHub issue is a constitution violation -- same severity as skipping `PROBLEM_LOG.md` after a real fix. Lifecycle footers must declare `deferred_log=<#NNN or D-NNN>|none|skipped|n/a`.

This is **not** `PROBLEM_LOG.md` (closed: symptom / cause / fix). This is **not** `CHANGELOG.md` (what the code does now). This is **not** `knowledge/task-log/` (why we shipped a change). This is **not** `Nova-Roadmap-Status.md` (product NEXT / phases L-Z). This is **not** an agent-memory Backlog.

Ranked list:

```text
py -3 tools/deferred_log.py status
py -3 tools/deferred_log.py priorities
```

`priorities` is the same ranked list as `status`. When the human asks "what's on the to-do / what's missing / priorities," run that command -- do not invent a second tracker. Every new chat also sees open P0/P1 items in the session-start fleet brief.

If `gh` cannot read Issues (some CI / cloud tokens, or a container with no `gh` installed at all), the command says so on stderr and falls back to `knowledge/deferred-index.json` (schema_version 1, owner `tools/deferred_github.py`). That file is a **read cache**, not a second to-do. Refresh it when convenient:

```text
py -3 tools/deferred_log.py refresh-index
```

Nothing allocates from the snapshot any more, so a stale one degrades a listing but cannot corrupt the tracker. `refresh-index` still refuses to overwrite a nonempty snapshot when `gh` returns zero issues, so a token that cannot read Issues cannot erase the fallback.

Browse in the browser: filter Issues by label `deferred`, then `P0` / `P1` / `bug` / `decision` / `domain:execution` (and the other domain labels).

## How to triage

| Field | What it answers |
|-------|-----------------|
| **Kind** | `bug` (wrong today) / `feature` (wanted, not built) / `decision` (blocked on a human call) |
| **Severity** | `P0` desk-broken, wrong money, trading safety, cannot operate. `P1` daily-use wrong. `P2` edge session / annoying / honesty gap that is not silent-wrong-money. `P3` polish. |
| **Effort** | `S` hours in one session. `M` a full session, shape is known. `L` architectural / multi-session / needs an ADR. |
| **Why parked** | Doing other work / too big for this task / needs an ADR / blocked on a human decision. Never "didn't feel like it." |
| **Blast radius** | What else is lying or missing while this stays open. |
| **Unblock** | The one decision or missing piece that lets an agent start. |
| **Next** | One concrete first step, not a design essay. |
| **Evidence** | How we know it is real (endpoint, screenshot, log line). No issue without this. |

Pull into a session when: severity is P0, or the human names the ID, or you are already in that module and Effort is S. Do **not** silently expand the current task into an L item -- open or comment on the issue and finish what you were asked.

## How agents open or close an item

1. **Search first.** `py -3 tools/deferred_log.py status` and `gh issue list --repo aaltaay/Nova --label deferred --search "<symptom>"`. If an existing issue already covers the ask: comment on that issue. Honor `parked` (label `parked` -- do not start it), `blocked`, Unblock, and Next.
2. **New item.** Title it plainly -- there is no ID to allocate. GitHub mints the durable `#NNN` when the issue is created:

```text
gh issue create --repo aaltaay/Nova \
  --title "short title" \
  --label deferred --label P1 --label bug --label "domain:execution" \
  --body-file - <<'EOF'
- **Status:** open
- **Kind:** bug
- **Severity:** P1
- **Effort:** S
- **Domain:** execution
- **User-visible:** yes
- **Logged:** YYYY-MM-DD
- **Why parked:** ...
- **Blast radius:** ...
- **Unblock:** ...
- **Next:** ...
- **Evidence:** ...
- **Keywords:** ...
EOF
```

Title is a plain short title -- the durable id is GitHub's `#NNN`, and `D-NNN` is a legacy alias kept only on issues that already carry one. Labels: always `deferred` plus one of `P0`..`P3`, plus `bug` / `enhancement` (feature) / `decision`, plus `domain:<name>` from `execution`, `market-feed`, `widgets`, `news`, `hod-momo`, `ibkr-ops`, `tester`, `security`, `docs`, `frontend`. Add `blocked` or `parked` when that is the status.
3. **Done.** Close the GitHub issue (reason completed). Write `PROBLEM_LOG.md` if it was a bug. Set Lifecycle `deferred_log=#NNN` plus `problem_log=...`. Do not delete history.
4. **Keep it short.** No secrets, tokens, or personal data.

IDs are durable: GitHub never reuses `#NNN`, including for closed issues.

## Do not

- Dump parked work only into `.cursor/agent-memory/*-memory.md` Backlog
- Dump product-phase NEXT / L-Z parking-lot work here -- that stays in `Nova-Roadmap-Status.md`
- Treat a CHANGELOG `Follow-ups:` bullet as enough
- Prepend a new `## D-NNN` section to this markdown file
- Band-aid a P0/P1 so you can skip the issue
- Mint a new `D-NNN`; the prefix is legacy-only and hand-allocating one re-opens the collision class
- Start a fix that is already an open issue without reading that issue first

## When skip is allowed

Only for: you fixed the bug this session (`PROBLEM_LOG.md`); purely cosmetic edits; status-only polls with no new gap; the gap is already an open issue and you learned nothing new (still declare `deferred_log=#NNN` if you touched that area).

## Relationship to other logs

| Log | Answers |
|-----|---------|
| `PROBLEM_LOG.md` | What went wrong and how it was **fixed** |
| GitHub Issues (`deferred`) | What is **still wrong or not built** |
| `CHANGELOG.md` | What the codebase does now |
| `knowledge/task-log/` | Full job narrative + why this approach |
| `Nova-Roadmap-Status.md` | Product phase NEXT (not a bug tracker) |

Pre-2026-09-08 entries lived in this file. Git history still has them. Live items are the GitHub issues.
