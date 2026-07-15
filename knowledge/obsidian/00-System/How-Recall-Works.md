# How Recall Works (Pinecone + Obsidian)

You do **not** pick the database yourself. Ask normally. The recall router decides.

## Accuracy model (important)

| Material | What it is | Index it? |
|---|---|---|
| **Official LMS captions** (`source: warrior-trading-official-captions`) | Same English subtitle track the Wistia player shows, with the same timestamps | **Yes** — default for transcript memory |
| **Whisper local audio** (`source: whisper-local-audio`) | OpenAI Whisper on audio extracted from already-local MP4s | **Only if you opt in** (`--include-whisper`) — usually strong, not guaranteed perfect |
| **Old sparse/paraphrase notes** | Title-only summaries that were inaccurate | **Never** — purged from Pinecone |

There is no honest “100% word-perfect” guarantee for any ASR/caption pipeline. Official captions are the best video-aligned source we have for captioned units because they are the player’s own subtitle track.

## Two memories

| Store | Holds | Use when |
|---|---|---|
| **Pinecone** | Course slide PDFs + free ebook + grad/rehab PDFs + official LMS caption transcripts | “What does the course say…?”, rules, definitions, setups |
| **Obsidian** | Curated decisions/roadmap + library inventory + keyword search over official transcripts on disk | “What should Nova automate?” plus course keyword hits |

Library paths / de-dupe rule: [[Warrior-Trading/Local-Library-Inventory]], [[Warrior-Trading-Library-Merge]].

Full transcripts stay under gitignored `downloads/warrior-trading-caption-notes/` so paid course text is not committed. Obsidian recall also searches that folder for official-caption files.

## Router rules (automatic)

1. **Decision / Nova / build / automate / roadmap / we chose** → **Obsidian first**, then Pinecone for supporting course evidence.
2. **Course / chapter / Ross / setup / entry / exit / float / gap** → **Pinecone first**, then Obsidian if a Nova decision note exists.
3. **Ambiguous** → **both**, labeled so answers stay grounded.

## Commands

```bash
# From repo root
cd tools/course_memory

# Slide PDFs only
py ingest.py

# Purge stale caption notes + ingest ONLY official LMS caption transcripts
py ingest.py --official-transcripts

# Optional: also index Whisper gap transcripts (not guaranteed perfect)
py ingest.py --official-transcripts --include-whisper

# Dry-run first
py ingest.py --official-transcripts --dry-run

# Ask anything and get a SYNTHESIZED answer, grounded ONLY in retrieved chunks.
# The model cannot use outside knowledge; if the material isn't indexed it
# replies NOT_IN_KNOWLEDGE_BASE instead of guessing. Citations included.
py ask.py "How do we leverage Level 2?"
py ask.py --show-sources "What is the gap and go setup?"

# Raw retrieval (no synthesis) — router picks sources
py recall.py "What does the Warrior Sim mentor session say about loss limits?"

# Force one source
py recall.py --source pinecone "Break of VWAP rules"
py recall.py --source obsidian "What did we decide for Nova?"
```

## Your job vs agent job

- **You:** Install Obsidian, open this vault, add/edit notes under `03-Nova-Decisions/` when you decide something.
- **Agent:** Ingests PDFs + official caption transcripts → Pinecone; keeps stale paraphrase notes purged; runs `recall.py` before answering strategy questions.

## Setup checklist

1. Create free accounts: [Pinecone](https://www.pinecone.io/) + [OpenAI](https://platform.openai.com/) (embeddings).
2. Put keys in repo `.env` (see `.env.example`).
3. Run `py ingest.py` for slides, then `py ingest.py --official-transcripts` for video-aligned captions.
4. Install [Obsidian](https://obsidian.md/), **Open folder as vault** → this `knowledge/obsidian` directory.
