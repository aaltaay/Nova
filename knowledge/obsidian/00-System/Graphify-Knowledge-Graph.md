# Graphify Knowledge Graph

Nova’s Obsidian vault is indexed into a **queryable knowledge graph** (not a vector index). Agents should prefer the graph for “how do our decisions connect?” questions before grepping the vault.

## Where it lives

| Path | Purpose |
|---|---|
| `graphify-out/graph.json` | Persistent graph — query via `py -3 tools/graphify_ask.py` |
| `graphify-out/usage.json` | Token-savings meter (cited notes minus query). Local; gitignored. |
| `graphify-out/GRAPH_REPORT.md` | God nodes, communities, surprising links |
| `graphify-out/graph.html` | Interactive browser visualization |
| `graphify-out/wiki/index.md` | Agent-crawlable wiki (start here for navigation) |
| `.cursor/rules/graphify.mdc` | Always-on Cursor rule to query the graph first |

Corpus root for this graph: `knowledge/obsidian/` (see `graphify-out/.graphify_root`).

## How this fits the memory router

| Store | Holds | Use when |
|---|---|---|
| **Obsidian notes** | Curated decisions / roadmap (source of truth) | Editing decisions; exact note body |
| **Graphify graph** | Concepts + typed links across those notes | “What connects X to Y?”, architecture of *our* decisions |
| **Pinecone** | Course PDFs + official caption chunks | “What does the course say…?” |

Trust order for automation advice is unchanged: Obsidian Active-Strategy / Roadmap → Pinecone course evidence → model prior. Graphify is a **navigation layer over Obsidian**, not a replacement and not course transcript storage.

## Commands (from repo root)

```powershell
# Ensure graphify is on PATH (Windows / uv tool)
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"

# Query / path / explain (wrapper records the savings meter -- required)
py -3 tools/graphify_ask.py query "What connects Gap and Go to IBKR safety gates?"
py -3 tools/graphify_ask.py path "Gap and Go Setup" "IBKR Safety Gates"
py -3 tools/graphify_ask.py explain "Nova OS Decision Brain"
py -3 tools/graphify_ask.py status

# Rebuild after vault note changes (in Cursor: ask for /graphify knowledge/obsidian --update --wiki)
# Full rebuild: /graphify knowledge/obsidian --wiki
```

Also: open `graphify-out/graph.html` in a browser, or start navigation at `graphify-out/wiki/index.md`.

## Install / skill locations

- CLI: `uv tool install graphifyy` (command is still `graphify`)
- Cursor always-on: `graphify cursor install` → `.cursor/rules/graphify.mdc`
- Project skill copies: `.cursor/skills/graphify/`, `.agents/skills/graphify/`, `.claude/skills/graphify/`
