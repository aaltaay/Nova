@AGENTS.md

## graphify

This project has a knowledge graph at `graphify-out/` built primarily from `knowledge/obsidian/` (decisions, strategies, course index, memory router), with god nodes, communities, and a wiki.

Rules:
- For Nova decision / strategy / IBKR-vs-Alpaca / "what connects X to Y?" questions, first run `py -3 tools/graphify_ask.py query "<question>"` when `graphify-out/graph.json` exists. Use `path` / `explain` / `status` on the same wrapper. Do not use a bare `graphify query` -- the wrapper records the token-savings meter.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of reading every vault note.
- Read `graphify-out/GRAPH_REPORT.md` only for broad review or when query/path/explain are insufficient.
- After editing `knowledge/obsidian/`, rebuild with `/graphify knowledge/obsidian --update --wiki` (Markdown needs a semantic pass — not AST-only `graphify update`).
- See `knowledge/obsidian/00-System/Graphify-Knowledge-Graph.md`.

## backlog

The backlog is organised into ranked **work packages** (GitHub milestones). When
asked to "start on the next item in the backlog", or whenever you need to know
what to work on next, run:

```text
py -3 tools/backlog_triage.py next
```

That prints one package, one pull request, the issues it resolves, and the
acceptance criteria. Do not re-triage the backlog or open a PR per issue — the
plan already batches related issues into one reviewable PR.

Rules:
- `BACKLOG.md` is the narrative; `knowledge/backlog-packages.json` is the authored
  plan; milestones are its GitHub projection (`backlog_triage.py sync`). Issue
  state (open/closed, labels) always comes from GitHub.
- New issues are queued into `00 - Untriaged` automatically the moment they are
  opened (`.github/workflows/backlog-inbox.yml`), so nothing is invisible to
  `next`. Nothing guesses the real package.
- When asked to **"triage the backlog"**: run `py -3 tools/backlog_triage.py triage`,
  decide which package's *outcome* each inbox issue serves, add it to that package's
  `issues` and to a PR batch in `knowledge/backlog-packages.json`, run `sync`, and
  open one small PR with the JSON change. Domain-overlap hints are suggestions, not
  assignments -- say why you routed each one.
- `backlog_triage.py check` fails while a **P0 or P1 sits untriaged**.
- Work marked gated needs an operator decision — record the question on the issue,
  never guess the policy.
- **Claim before you work** when other agents may be active — they run from
  Claude, Codex and Cursor against the same GitHub account, so `assignee` cannot
  identify a holder: `py -3 tools/backlog_triage.py claim --package <slug> --batch <n>
  --branch <name>` (set `NOVA_AGENT_ID`). `next` skips claimed batches. Claims go
  stale after 4h; `claims` lists holders; `release` clears one you did not ship.
  A merged PR retires its own claim. Advisory, not mutual exclusion.
- For a multi-agent pass over one package use `.claude/workflows/backlog-wave.js`
  (2–3 agents, claims each batch, ramps down before token limits). Only when the
  user has opted into workflows.

## ledger

`CHANGELOG.md` and `PROBLEM_LOG.md` are **generated** (AGENTS.md §7.1). Do NOT
prepend to them — that is what makes parallel PRs collide on paperwork (#344).

- A PR carries its entry in its own body: **What** / **Why this approach** /
  **Verified by**, from `.github/pull_request_template.md`. Nothing else.
- No PR (direct push, ops diagnosis)? Scaffold a fragment instead:
  `py -3 tools/changes_new.py --kind fix --scope <area> --title "..."`
  (add `--problem` for a PROBLEM_LOG entry). It is a new file, so it cannot
  conflict.
- `.github/workflows/ledger-collate.yml` folds merged PRs and fragments into
  the ledger on master and opens one PR. Only that job writes the ledger.
