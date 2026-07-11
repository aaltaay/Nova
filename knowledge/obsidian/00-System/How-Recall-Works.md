# How Recall Works (Pinecone + Obsidian)

You do **not** pick the database yourself. Ask normally. The recall router decides.

## Two memories

| Store | Holds | Use when |
|---|---|---|
| **Pinecone** | Full course slide text (chunked from PDFs) | “What does the course say…?”, rules, definitions, setups |
| **Obsidian** | Short curated notes *you and the agent write* | “What should Nova automate?”, decisions, roadmap, preferences |

## Router rules (automatic)

1. **Decision / Nova / build / automate / roadmap / we chose** → **Obsidian first**, then Pinecone for supporting course evidence.
2. **Course / chapter / Ross / setup / entry / exit / float / gap** → **Pinecone first**, then Obsidian if a Nova decision note exists.
3. **Ambiguous** → **both**, labeled so answers stay grounded.

## Commands

```bash
# From repo root
cd tools/course_memory

# 1) Load PDFs into Pinecone (needs keys in .env)
py ingest.py

# 2) Ask anything — router picks sources
py recall.py "Which Warrior strategy is best to automate on Nova first?"

# 3) Force one source
py recall.py --source obsidian "What did we decide for Nova?"
py recall.py --source pinecone "What are ABCD pattern rules?"
py recall.py --source both "Gap and Go risk rules for automation"
```

## Your job vs agent job

- **You:** Install Obsidian, open this vault, add/edit notes under `03-Nova-Decisions/` when you decide something.
- **Agent:** Ingests PDFs → Pinecone; updates strategy candidate notes; runs `recall.py` before answering strategy questions.

## Setup checklist

1. Create free accounts: [Pinecone](https://www.pinecone.io/) + [OpenAI](https://platform.openai.com/) (embeddings).
2. Put keys in repo `.env` (see `.env.example`).
3. Run `py ingest.py` once (re-run when new PDFs are added).
4. Install [Obsidian](https://obsidian.md/), **Open folder as vault** → this `knowledge/obsidian` directory.
