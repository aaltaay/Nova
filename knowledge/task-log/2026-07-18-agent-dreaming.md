# 2026-07-18 — Nova agent dreaming

- **Status:** completed
- **Agents:** parent
- **Domain:** docs / agent OS
- **Related:** `CHANGELOG.md` §2026-07-18 — Nova agent dreaming · [[Agent-Dreaming]]

## Task

Implement a real Nova-native agent dream pass (not a memo), using OpenClaw light→REM→deep and open-second-brain hygiene as blueprints.

## Goal

Fleet living memory can be consolidated via CLI: stage → diary themes → promote durable pending facts + trim run logs, dry-run by default.

## Why it mattered

Specialists accumulate pending promotions and long run logs with no scheduled cleanup; Obsidian/Pinecone are separate stores and do not replace agent-memory hygiene.

## What we changed

- Added `tools/agent_dream.py` + `tools/agent_dream_lib/` (parse, phases)
- Tests in `tools/test_agent_dream.py`
- Diary `.cursor/agent-system/DREAMS.md`, vault note `Agent-Dreaming.md`

## How it works now

`py -3 tools/agent_dream.py` dry-runs all registered agents. `--write` promotes scored pending facts into agent specs (Known traps or Dream promotions), caps run logs at 30, stamps `last_dream_at`, appends REM/Deep diary. Owner: docs. Does not rewrite Obsidian decisions or Pinecone.

## Why this approach

Rejected adopting OpenClaw/Claude Auto Dream (wrong runtime). Deterministic scoring keeps CI free of API keys. Dry-run default matches Nova tool norms (`sync_agent_surfaces`, `create_nova_agent`). Docs owns the surface so we avoid a new specialist for a consolidation tool.

## Verification

- `py -3 -m pytest tools/test_agent_dream.py tools/test_agent_contract.py -q` → 18 passed
- `py -3 tools/agent_contract.py --ci` → PASS (14 agents)
- Dry-run CLI smoke on live registry

## Follow-ups

- OpenAI quota for LLM REM (429) — heuristic fallback works; top up billing to get real diaries
- Pinecone ingest returned exit=1 on first write pass — re-run `py -3 tools/agent_dream.py --write --pinecone` after keys/index are healthy
- OpenClaw remains a bridge export, not a vendored Nova runtime (by design)

## Keywords

agent dreaming, memory consolidation, light REM deep, agent-memory, DREAMS.md, Obsidian hygiene, Pinecone, Claude Auto Dream
