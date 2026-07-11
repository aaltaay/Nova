# Automation Roadmap

## Phase 0 — Memory (now)

- [x] Download course slide PDFs (Basics, SS101, Algo)
- [x] Ingest PDFs → Pinecone (`tools/course_memory/ingest.py`) — ~1080 vectors
- [ ] Open this folder as Obsidian vault
- [ ] Decide Active Strategy via recall-assisted study

## Phase 1 — Signal only (no live orders)

- [ ] Encode strategy filters on top of existing scanner / HOD Momo
- [ ] Alert / UI badge when setup is valid
- [ ] Log paper signals to review

## Phase 2 — Paper execution (IBKR)

- [ ] Map signal → order ticket defaults
- [ ] Hard risk caps in `backend/ibkr/`
- [ ] Journal results back into Obsidian weekly

## Phase 3 — Tighten

- [ ] Remove discretionary edge cases that failed
- [ ] Only then consider live (requires `IBKR_LIVE_TRADING_CONFIRMED`)
