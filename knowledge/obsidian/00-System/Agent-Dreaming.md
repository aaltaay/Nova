# Agent Dreaming (fleet memory consolidation)

Nova-native sleep cycle for specialist living memory, course RAG, and decision hygiene. Inspired by OpenClaw light→REM→deep and open-second-brain nightly passes — **implemented in-repo**. Sibling tools (Claude Code Auto Dream, OpenClaw) are bridged, not vendored as Nova’s runtime.

Companion: [[Memory-Router]] · `docs/agent-operations.md` · diary `.cursor/agent-system/DREAMS.md`

## Why the early “out of scope” cuts existed (and why they’re in now)

| Surface | Original reason to defer | Mission completion |
|---------|--------------------------|--------------------|
| OpenClaw / Claude Auto Dream | Wrong primary runtime; risk of dual agent OS | **Bridges:** Claude `autoDreamEnabled`; OpenClaw `openclaw-MEMORY.md` export — Nova Cursor agents stay authoritative |
| Pinecone re-ingest | Long, key-gated, expensive | `--pinecone` → `tools/course_memory/ingest.py` (dry-run unless `--write`; `--pinecone-full` for unlimited) |
| Auto-edit `03-Nova-Decisions/` | Highest-trust strategy truth | Hygiene note + stamp footers on strategy notes; **does not rewrite Chosen strategy / Mechanical rules** |
| LLM-backed REM | Needs `OPENAI_API_KEY`; CI must work offline | Default on when key present; heuristic fallback; `--no-llm-rem` |
| Auto commit/push | Surprising git mutation | `--commit` / `--push` (requires `--write`) |

## Commands

```bash
# Dry-run fleet (safe)
py -3 tools/agent_dream.py

# Full mission dry-run (obsidian + pinecone dry-run + bridges preview)
py -3 tools/agent_dream.py --full-mission

# Apply everything Nova owns + ship
py -3 tools/agent_dream.py --write --full-mission --commit --push

# Pieces
py -3 tools/agent_dream.py --write --obsidian
py -3 tools/agent_dream.py --write --pinecone --pinecone-official
py -3 tools/agent_dream.py --write --bridges
py -3 tools/agent_dream.py --no-llm-rem
```

Owner: `docs`. Invoke: “Use the docs subagent to run agent dreaming.”

## Trust / safety

- Dry-run by default.
- Rejects WIP pending facts; skips dupes already in agent specs.
- Obsidian edits are hygiene + footers only — not silent strategy flips.
- OpenClaw/Claude bridges must never place Nova IBKR orders (`auto_live` NO-GO).
- `--push` only after `--commit` after `--write`.
