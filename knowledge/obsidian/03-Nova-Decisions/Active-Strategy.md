# Active Strategy (Nova)

**Status:** `DIRECTION SET — Warrior/Ross momentum family` · **primary setup: Gap and Go** (signal-only today)
**Backbone doc:** [[Automation-Strategy-Backbone]]  
**Nova OS (decision pipeline):** [[Nova-OS-Decision-Brain]]

When decided, fill this template. The recall router treats this note as **highest trust** for “what should we build?”

## Chosen strategy

- Name: **Gap and Go** (momentum family; Bull Flag / ABCD later)
- Course / chapter evidence: SS101 Gap and Go; Basics Five Pillars; free ebook Gap and Go chapter; Pinecone + Obsidian
- Why this one:
  - Most mechanical morning play (PM high break, 9:30–10 window)
  - Already partially encoded in `backend/strategy/{five_pillars,gap_and_go}.py`
  - Matches Nova scanners (gappers) + IBKR discovery

## Mechanical rules (must be codeable)

- Universe / filters: Five Pillars (price $2–20, ≥10%, RVOL ≥5×, catalyst, float ≤20M)
- Entry: Break of premarket high in 9:30–10:00 ET (see Gap-and-Go spec)
- Stop / invalidation: cents-based stop (≤$0.20 scalp max); thesis fail / weakness
- Targets / exit: ≥2:1; scale half → BE; L2/T&S exits later
- Position sizing: risk budget + daily state (¼ size until cushion)
- Time-of-day constraints: Gap and Go window only for this setup

## Nova mapping

- Scanner signals to reuse: IBKR gappers / movers, news catalyst, float
- New modules needed: Nova OS decide API; risk state machine; paper brackets
- IBKR order types: bracket (entry + stop + target) on paper first
- Paper-trade checklist: backbone §5 go/no-go metrics

## Explicit non-goals

- Live money until paper bar cleared + env flags
- Blind LLM catalyst → full size
- Full L2-tape automation until IBKR L2 path proven
- “Ruby” / second broker stack — Python `backend/ibkr/` only
