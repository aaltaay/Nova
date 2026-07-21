# 2026-07-19 — Harvested Warrior materials vs AI / trading decision wiring (current truth)

- **Status:** completed (investigation only — no product code)
- **Agents:** daddy (direct investigate)
- **Domain:** docs / warrior course memory / Nova OS boundary
- **Related:** [[How-Recall-Works]] · [[Memory-Router]] · `tools/course_memory/` · task-log `2026-07-19-warrior-transcript-kb-plan.md`

## Task

Answer, as-of now: how already-harvested Warrior materials (especially Whisper under `downloads/warrior-trading-caption-notes/`) affect AI decision-making — wired vs on-disk unused.

## Goal

Precise affects / does-not-affect report with code + live Pinecone evidence for the parent to present.

## Why it mattered

Harvest completion does not equal recall or trading automation. Without a current-wiring truth, agents and humans may assume Whisper bulk already steers decide/HOD/ask.

## What we changed

- Investigation only (no ingest write, no product edits).
- Live Pinecone probe: namespace `warrior-slides` has **2094** vectors; sources seen = `warrior-trading-slides` + `warrior-trading-official-captions`; **zero** hits for `whisper-local-audio`, `groq-whisper-api`, `faster-whisper-local-cuda`, or stale `warrior-trading-caption-notes`.
- On-disk source tally under caption-notes: official=30, whisper-local-audio=57, groq-whisper-api=393, faster-whisper-local-cuda=82.

## How it works now

| Path | Whisper bulk harvest? | Official captions? | Slides? |
|------|----------------------|--------------------|---------|
| Pinecone (live index) | No | Yes (indexed) | Yes |
| `ingest.py` default | No (PDF only) | Only with `--official-transcripts` | Default |
| `ingest.py --include-whisper` | Only `whisper-local-audio` (57), **not** groq/faster-whisper labels | Yes | N/A |
| Obsidian keyword recall (`obsidian_store.py`) | Excluded (requires `source: warrior-trading-official-captions`) | Yes (on-disk search) | N/A (vault notes separate) |
| `ask.py` / `recall.py` | Only if already in Pinecone (currently not) | Via Pinecone + Obsidian disk search | Via Pinecone |
| Dream `--pinecone-official` | Never (`--include-whisper` not passed) | Dry-run unless `--write` | Via `--pinecone` |
| `decide` / `control_mode` / HOD engine | No | No | No |
| Active-Strategy | Curated Obsidian note only (not transcript bodies) | Indirect via human/agent writing | Same |

Trading automation does not read transcript files. AI answers change only when someone runs ask/recall (and keys work) or agents manually open files / follow Active-Strategy notes.

## Why this approach

- Code + live index probe beats plan docs alone (plan said “official first”; probe confirms Whisper not in Pinecone yet).
- Rejected claiming bulk harvest “is in memory” — most files use `groq-whisper-api` / `faster-whisper-local-cuda`, which `--include-whisper` does not even allowlist today.

## Verification

- `obsidian_store.py` official-only gate; `ingest.py` `--include-whisper` → only `whisper-local-audio`.
- `test_obsidian_recall.py` asserts Whisper excluded from keyword index.
- Pinecone `describe_index_stats` + filtered random-vector query (OpenAI embed key was 401; probe did not need embeddings).
- `backend/nova_os/decide.py` / `hod_momo.py`: no `course_memory` / caption-notes imports.

## Follow-ups

- Fix/refresh OpenAI embed key if ask/recall synthesis is needed.
- If Whisper should enter Pinecone: extend allowlist beyond `whisper-local-audio` or re-tag harvest frontmatter; prefer curated slice first.
- Inventory refresh for new source labels (groq / faster-whisper).

## Keywords

whisper, groq-whisper-api, official-captions, pinecone, course_memory, ask, recall, decide, hod-momo, Active-Strategy, harvest
