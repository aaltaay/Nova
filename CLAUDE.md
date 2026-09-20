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
- After filing a new issue, add it to a package and run `sync`. `backlog_triage.py
  check` reports issues with no package or missing labels.
- Work marked gated needs an operator decision — record the question on the issue,
  never guess the policy.
- For a multi-agent pass over one package use `.claude/workflows/backlog-wave.js`
  (2–3 agents, ramps down before token limits). Only when the user has opted into
  workflows.
