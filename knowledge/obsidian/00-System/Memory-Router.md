# Memory Router — when to use which store

This note is the human-readable twin of `tools/course_memory/recall.py`.

## Intent → source

| Intent examples | Primary | Secondary |
|---|---|---|
| “What did *we* decide for Nova?” | Obsidian `03-Nova-Decisions/` | — |
| “Which strategy should I *build*?” | Obsidian `02-Strategies/` | Pinecone (course evidence) |
| “What are the *entry rules* for Gap and Go?” | Pinecone | Obsidian if we already chose it |
| “Summarize Chapter 5 psychology” | Pinecone | — |
| “How does this map to IBKR / scanner?” | Obsidian + Pinecone | — |

## Trust order for automation advice

1. **Obsidian Active-Strategy / Roadmap** (explicit decisions)  
2. **Pinecone course chunks** (cited course/chapter/page)  
3. **Model prior knowledge** (lowest — never override 1–2)

If Pinecone is empty (not ingested yet), say so and fall back to Obsidian + ask to run ingest.
