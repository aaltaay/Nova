@AGENTS.md

## graphify

This project has a knowledge graph at `graphify-out/` built primarily from `knowledge/obsidian/` (decisions, strategies, course index, memory router), with god nodes, communities, and a wiki.

Rules:
- For Nova decision / strategy / IBKR-vs-Alpaca / "what connects X to Y?" questions, first run `py -3 tools/graphify_ask.py query "<question>"` when `graphify-out/graph.json` exists. Use `path` / `explain` / `status` on the same wrapper. Do not use a bare `graphify query` -- the wrapper records the token-savings meter.
- If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of reading every vault note.
- Read `graphify-out/GRAPH_REPORT.md` only for broad review or when query/path/explain are insufficient.
- After editing `knowledge/obsidian/`, rebuild with `/graphify knowledge/obsidian --update --wiki` (Markdown needs a semantic pass — not AST-only `graphify update`).
- See `knowledge/obsidian/00-System/Graphify-Knowledge-Graph.md`.
