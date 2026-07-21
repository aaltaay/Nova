# 2026-07-19 — Warrior transcript harvest → KB / automation / AI plan

- **Status:** completed (plan only — no product ingest yet)
- **Agents:** daddy (aggregate) · surfaces: warrior, docs, hod-momo (consumers)
- **Domain:** docs / warrior course memory
- **Related:** [[How-Recall-Works]] · [[Local-Library-Inventory]] · `tools/course_memory/` · warrior-memory LMS harvest 2026-07-17

## Task

After completing a full Warrior LMS transcript harvest (544 videos), decide how those transcripts enter Nova’s knowledge base, automation, and AI — without leaking paid content into git or feeding Warrior market data into the alert engine.

## Goal

An opinionated phased plan the parent can present: what goes where, what must not be committed, recommended next step, and blockers.

## Why it mattered

Harvest alone is not recall. Without a clear ingest + trust model, agents either re-scrape, dump paid bodies into Obsidian/git, or treat Whisper ASR as equal to official captions — and HOD/Former Momo research stays stuck on “watch the video.”

## What we changed

- Daddy plan only (no Pinecone write, no transcript commit).
- Aggregate task-log entry + daddy-memory run log.
- On-disk spot-check: ~30 official-caption + ~533 Whisper markdown files under gitignored `downloads/warrior-trading-caption-notes/`.

## How it works now (target architecture — already mostly built)

| Layer | Role | Paid transcript bodies? |
|-------|------|-------------------------|
| `downloads/warrior-trading-caption-notes/` | Canonical local store (gitignored) | Yes — stay here |
| `downloads/warrior-trading-videos/` | Whisper source MP4s (gitignored) | N/A |
| Pinecone `nova-warrior-courses` | Searchable chunks + citations | Official by default; Whisper opt-in |
| Obsidian | Inventory, site map, decisions — **pointers only** | No verbatim bodies in vault |
| Graphify | Navigation over Obsidian decisions | Never a transcript store |
| `tools/course_memory/{ingest,recall,ask}.py` | Ingest + grounded Q&A | Uses above rules |
| Agent dream `--pinecone-official` | Automation hook for official re-ingest | Dry-run unless `--write` |
| warrior / hod-momo | Research consumers via recall/ask | Never feed Warrior scanner rows into Nova HOD engine |

Trust: Obsidian decisions > Pinecone citations (label `source`) > model prior. Whisper chunks must be labeled lower trust than `warrior-trading-official-captions`.

## Why this approach

- **Reuse existing pipeline** (`--official-transcripts` / `--include-whisper`) instead of inventing a second RAG stack.
- **Do not commit paid bodies** — already enforced by `.gitignore` `downloads/` + vault fidelity tests.
- **Staged Whisper** (priority courses / HOD keywords first) over bulk `--include-whisper` for all 533 — cost, ASR noise, and citation honesty.
- **Rejected:** dumping transcripts into Obsidian vault; graphify-ing caption markdown; wiring Warrior live HOD scrape into alert engine; treating Whisper as “official.”

## Verification

- Spot-count on disk (official ≈ 30, whisperish ≈ 533).
- Confirmed ingest CLI + `How-Recall-Works.md` + `obsidian_store.py` official-only keyword path.
- No Pinecone write in this dispatch.

## Follow-ups

1. docs/warrior: refresh inventory coverage counts (harvest complete).
2. Dry-run then write: `py ingest.py --official-transcripts` (keys required).
3. Curated Whisper slice for SS101 / Scanning / HOD / Former Momo — then optional `--include-whisper` or filtered namespace.
4. Wire warrior/hod-momo prompts to `ask.py` / `recall.py` for course questions.
5. Dream: `--pinecone-official` on cadence after catalog deltas.

## Keywords

warrior, transcripts, pinecone, whisper, official-captions, course_memory, gitignore, HOD, Former Momo, recall, agent dream
